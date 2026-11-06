"""Saved-rule imports preserve VPS account state and never create a runtime."""
from dataclasses import asdict,replace
import json
from pathlib import Path

import pytest

from ckps.config import read_settings,write_settings,runtime_root,book_path
from ckps.models import Settings
from ckps.services.presets import load_preset,validate_preset,current_preset
from ckps.services.signal_config import read_signal_settings,write_signal_settings
from ckps.storage import AccountLease

SHIPPED=Path(__file__).resolve().parents[1]/'presets'/'kaiser-vn30.json'


def saved_preset(tmp_path,data=None):
    path=tmp_path/'selected.json'
    path.write_text(json.dumps(data if data is not None else json.loads(SHIPPED.read_text(encoding='utf-8'))),encoding='utf-8')
    return path


def existing_settings():
    main=Settings(mode='REAL',account_no='1234567890',loan_package_id='2279',paper_balance=350_000_000,
        telegram_enabled=True,telegram_chat='main-chat',entry_notifications=True,poll_seconds=5,
        signals={'buy_ema_fast':5,'buy_ema_slow':13},market_alerts={'movement_enabled':True}).validate()
    main.exit['sl_distance']=.7
    write_settings(main)
    signals=replace(main,telegram_chat='backend-chat',poll_seconds=7,
        market_alerts={'trend_enabled':True,'movement_enabled':False}).validate()
    write_signal_settings(signals)
    return main,signals


def test_shipped_preset_is_portable_and_contains_only_saved_strategy_parameters():
    raw=json.loads(SHIPPED.read_text(encoding='utf-8'))
    preset=validate_preset(raw)
    assert preset['exit']['distance_unit']==preset['exit']['trailing_unit']=='PRICE_PERCENT'
    assert preset['exit']['sl_distance']==preset['exit']['arm_gain']==1
    assert preset['exit']['trail_gap']==.3 and preset['exit']['ema_exit_enabled']
    assert preset['exit']['arm_close_pct']==preset['exit']['dynamic_close_pct']==100
    assert preset['exit']['retention_pct']==65
    text=json.dumps(raw)
    for private in ('account_no','loan_package_id','paper_balance','telegram_token','telegram_chat','telegram_enabled','entry_notifications','credentials'):
        assert private not in text
    assert not {'movement_enabled','trend_enabled'} & raw['market_alerts'].keys()


def test_current_preset_exports_rules_without_any_account_or_notification_state():
    main,signals=existing_settings()
    exported=current_preset('Saved here')
    assert exported['exit']['sl_distance']==.7 and exported['signals']==signals.signals
    assert 'telegram_chat' not in exported and 'paper_balance' not in exported
    assert read_settings()==main and read_signal_settings().telegram_chat=='backend-chat'


def test_loading_on_a_new_vps_creates_valid_paper_settings_without_connection_or_bot_state(tmp_path):
    name,_=load_preset(saved_preset(tmp_path))
    settings=read_settings()
    assert name=='Kaiser VN30' and settings.mode=='PAPER' and settings.account_no==''
    assert not settings.telegram_enabled and settings.telegram_chat==''
    assert settings.exit['sl_distance']==1 and settings.exit['trailing_unit']=='PRICE_PERCENT'
    assert read_signal_settings().signals==settings.signals
    assert not any(p.name.endswith('.dpapi') or p.name=='ledger.sqlite3' for p in runtime_root().rglob('*'))


def test_loads_selected_file_and_preserves_vps_connections_funds_ledgers_and_notification_gates(tmp_path):
    main,signals=existing_settings()
    root=runtime_root()
    private={root/'connection.dpapi':b'private-connection',root/'telegram.dpapi':b'private-telegram',
        book_path(main)/'ledger.sqlite3':b'ledger-and-position-state'}
    for path,value in private.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
    old_main=(root/'settings.json').read_bytes();old_signals=(root/'signals/settings.json').read_bytes()
    filename=saved_preset(tmp_path)
    name,backup=load_preset(filename)
    assert name=='Kaiser VN30'
    actual=read_settings();expected=json.loads(filename.read_text())
    assert actual.exit==expected['exit'] and actual.signals==expected['signals']
    assert actual.mode=='REAL' and actual.account_no==main.account_no and actual.paper_balance==main.paper_balance
    for key in asdict(main).keys()-{'exit','signals','market_alerts'}:
        assert getattr(actual,key)==getattr(main,key)
    after=read_signal_settings()
    assert after.telegram_chat==signals.telegram_chat and after.telegram_enabled==signals.telegram_enabled
    assert after.entry_notifications==signals.entry_notifications and after.poll_seconds==signals.poll_seconds
    assert after.market_alerts['trend_enabled'] and not after.market_alerts['movement_enabled']
    assert actual.market_alerts['movement_enabled'] and not actual.market_alerts['trend_enabled']
    assert (backup/'settings.json').read_bytes()==old_main and (backup/'signals.json').read_bytes()==old_signals
    assert all(path.read_bytes()==value for path,value in private.items())


def test_em_only_file_leaves_blackbox_and_telegram_file_unchanged(tmp_path):
    main,_=existing_settings()
    signal_path=runtime_root()/'signals/settings.json';before=signal_path.read_bytes()
    preset=json.loads(SHIPPED.read_text())
    preset.pop('signals');preset.pop('market_alerts')
    load_preset(saved_preset(tmp_path,preset))
    assert read_settings().exit==preset['exit'] and read_settings().signals==main.signals
    assert signal_path.read_bytes()==before


@pytest.mark.parametrize('case',['schema','account','legacy','ema','boolean','unknown','negative'])
def test_invalid_preset_does_not_touch_any_saved_settings(tmp_path,case):
    existing_settings()
    paths=[runtime_root()/'settings.json',runtime_root()/'signals/settings.json']
    before={p:p.read_bytes() for p in paths}
    raw=json.loads(SHIPPED.read_text())
    if case=='schema':raw['schema']='unknown'
    if case=='account':raw['account_no']='111111'
    if case=='legacy':raw['exit']['trailing_unit']='PNL_PERCENT'
    if case=='ema':raw['signals']['buy_ema_fast']=999
    if case=='boolean':raw['exit']['sl_enabled']='false'
    if case=='unknown':raw['exit']['api_secret']='forbidden'
    if case=='negative':raw['exit']['sl_distance']=-1
    with pytest.raises(ValueError):load_preset(saved_preset(tmp_path,raw))
    assert all(p.read_bytes()==value for p,value in before.items())
    assert not (runtime_root()/'presets/backups').exists()


@pytest.mark.parametrize('owner',['book','blackbox'])
def test_loading_refuses_a_running_app_or_blackbox_without_changing_rules(tmp_path,owner):
    main,_=existing_settings();path=runtime_root()/'settings.json';before=path.read_bytes()
    lock=(book_path(main) if owner=='book' else runtime_root()/'blackbox')/'session.lock'
    lease=AccountLease(lock)
    try:
        with pytest.raises(ValueError,match='Đóng app và Blackbox'):
            load_preset(saved_preset(tmp_path))
    finally:lease.close()
    assert path.read_bytes()==before


def test_partial_config_write_failure_restores_both_files(tmp_path,monkeypatch):
    existing_settings()
    import ckps.services.presets as module
    paths=[runtime_root()/'settings.json',runtime_root()/'signals/settings.json']
    before={p:p.read_bytes() for p in paths};original=module.os.replace
    failed=False
    def fail_second(source,target):
        nonlocal failed
        if Path(target)==paths[1] and not failed:
            failed=True
            raise OSError('simulated write failure')
        return original(source,target)
    monkeypatch.setattr(module.os,'replace',fail_second)
    with pytest.raises(OSError,match='simulated'):
        load_preset(saved_preset(tmp_path))
    assert failed and all(p.read_bytes()==value for p,value in before.items())


@pytest.mark.parametrize('cancel',[True,False])
def test_menu_file_picker_routes_only_the_explicitly_selected_preset(monkeypatch,tmp_path,cancel):
    import ckps.preset_app as app
    calls=[]
    class Root:
        def withdraw(self):pass
        def destroy(self):calls.append('closed')
    monkeypatch.setattr(app.tk,'Tk',Root)
    def choose(**kwargs):
        assert Path(kwargs['initialdir'])==SHIPPED.parent
        return '' if cancel else str(SHIPPED)
    monkeypatch.setattr(app.filedialog,'askopenfilename',choose)
    monkeypatch.setattr(app,'load_preset',lambda filename:calls.append(filename) or ('Kaiser VN30',tmp_path))
    monkeypatch.setattr(app.messagebox,'showinfo',lambda *a,**kw:calls.append('saved'))
    assert app.main()==0
    assert calls==(['closed'] if cancel else [SHIPPED,'saved','closed'])
