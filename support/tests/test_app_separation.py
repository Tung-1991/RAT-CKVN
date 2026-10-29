from dataclasses import asdict, replace
from types import SimpleNamespace
import time

import pytest

from ckps.config import read_settings, runtime_root, write_settings
from ckps.models import Quote, Settings
from ckps.rules.signal_settings import SignalSettings
from ckps.services.runtime import Runtime
from ckps.services.signal_runtime import SignalRuntime
from ckps.services.signal_config import read_signal_settings, write_signal_settings


def test_backend_cannot_create_engine_or_accept_trading_commands(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('Backend must not create a trading engine or broker.')
    monkeypatch.setattr('ckps.trading.execution.Engine.__init__',forbidden)
    monkeypatch.setattr('ckps.connections.dnse.client.DNSEBroker.__init__',forbidden)
    runtime=SignalRuntime(Settings())
    try:
        for name in ('open_manual','close_position','arm','set_managed','cancel','replace','send_otp','set_price'):
            with pytest.raises(ValueError,match='không hỗ trợ giao dịch'):runtime.command(name,'LONG')
        assert not hasattr(runtime,'engine')
        assert not runtime.store.orders() and not runtime.store.positions()
        assert runtime.store.get('paper','account') is None
    finally:
        runtime.close();runtime.thread.join(5)
    assert not runtime.thread.is_alive() and not runtime.telegram_thread.is_alive()


def test_trading_and_signal_apps_can_run_together_with_isolated_ledgers_and_settings():
    trading=Settings(paper_balance=230_000_000)
    write_settings(trading)
    signals=replace(Settings(),signals=SignalSettings(buy_ema_fast=5,buy_ema_slow=13).to_dict(),telegram_chat='offline-chat')
    write_signal_settings(signals)
    main=Runtime(read_settings(),offline=True)
    backend=SignalRuntime(read_signal_settings())
    try:
        assert main.store.path!=backend.store.path
        assert not hasattr(main,'analysis') and not hasattr(main,'telegram_thread')
        assert read_settings().paper_balance==230_000_000
        assert read_signal_settings().signals['buy_ema_fast']==5
        main.command('open_manual','LONG',1,'MOK')
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and not main.store.positions():time.sleep(.02)
        assert len(main.store.positions())==1
        assert not backend.store.positions() and not backend.store.orders()
        main.engine._notify('LONG VN30F1M · ARM ALERT\nhit','alert:demo')
        assert not main.store.db.execute('SELECT id FROM outbox').fetchall()
        assert not (runtime_root()/'signals'/'settings.json').read_text(encoding='utf-8').count('paper_balance')
    finally:
        main.close();backend.close();main.thread.join(5);backend.thread.join(5)
    assert not main.thread.is_alive() and not backend.thread.is_alive()


def test_signal_condition_and_cooldown_survive_backend_restart_without_replay(system):
    engine,broker,store=system
    settings=Settings(telegram_enabled=True,telegram_chat='offline-chat',entry_notifications=True,
        signals=SignalSettings(buy_alert_enabled=True).to_dict())
    condition={'buy_alert':True,'indicators':{'buy_ema_fast':2001,'buy_ema_slow':2000,'rsi':51}}
    def session():
        result=SignalRuntime.__new__(SignalRuntime)
        result.settings,result.store=settings,store
        result.latest=SimpleNamespace(contract='VN30F1M',quotes={'VN30F1M':Quote('VN30F1M',2000)})
        result.analysis=SimpleNamespace(snapshot=lambda:{'contract':'VN30F1M','observed_at':time.time(),'p2':condition})
        result.owner_enabled,result.owner_token,result.owner_chat=True,'offline-token','offline-chat'
        result.owner_contract=None
        return result
    session()._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
    session()._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
    settings.signals['buy_alert_enabled']=False
    condition['buy_alert']=False;session()._owner_telemetry()
    condition['buy_alert']=True;session()._owner_telemetry()
    settings.signals['buy_alert_enabled']=True
    session()._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1


def test_demo_long_uses_same_dynamic_repeat_and_arm_milestones_without_ledger():
    from ckps.dashboard.demo import long_sample, demo_rules
    from ckps.dashboard.mayin.management_preview import position_milestones
    folder=runtime_root()
    for stage,target in [('DYNAMIC',2008.4),('LẶP',2003.4),('TSL / ARM',2020.)]:
        position,current=long_sample(stage)
        before=asdict(position)
        arm,dynamic=position_milestones(position,demo_rules(),current,1.)
        assert position.entry==2000 and position.metrics['levels']['sl']==1990 and position.metrics['levels']['tp']==0
        if stage=='TSL / ARM':
            assert f'{target:,.1f}' in arm.value and 'NHƯỜNG ARM' in dynamic.value
        else:assert f'{target:,.1f}' in dynamic.value
        assert position.quantity==(2 if stage=='DYNAMIC' else 1)
        assert asdict(position)==before
    assert not folder.exists()


def test_main_telegram_shortcut_uses_the_connection_settings_window():
    from ckps.dashboard.actions import DashboardActionsMixin
    pages=[]
    window=SimpleNamespace(select_page=pages.append)
    app=SimpleNamespace(connection=lambda:window)
    assert DashboardActionsMixin.open_signal_backend(app) is window
    assert pages==['TELEGRAM / LỊCH']
    assert not hasattr(app,'runtime')
