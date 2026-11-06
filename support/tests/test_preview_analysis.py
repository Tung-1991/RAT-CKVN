"""Automatic market-only analysis and clearly dated closing references."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from ckps.dashboard.mayin.connection_status import market_status
from ckps.dashboard.mayin.signal_preview import signal_preview
from ckps.dashboard.settings_state import ensure_preview_backend, save_signal_settings, signal_settings
from ckps.models import Quote, Settings
from ckps.rules.p2.market import VN_TZ
from ckps.services.market_context import context, publish_context
from ckps.services.session_preview import closing_analysis, closing_quote


NOW=datetime(2026,10,30,15,20,tzinfo=VN_TZ)


def closing_data(count=220):
    quote=Quote('41I1GB000',1990,source='DNSE',at=NOW.replace(hour=14,minute=45).timestamp())
    rows=[{'time':(NOW-timedelta(days=i)).date().isoformat(),'high':2010,'low':1990,'close':2000}
          for i in range(count,0,-1)]
    return {'contract':quote.symbol,'quotes':{quote.symbol:asdict(quote)},'bars':rows}


def test_closing_prices_compute_ema_and_ma_but_never_create_a_live_entry():
    data=closing_data();before=deepcopy(data)
    reference=closing_analysis(data,Settings(),now=NOW.timestamp())
    assert reference['ready'] and reference['indicators']['buy_ema_fast']==1995
    assert reference['indicators']['buy_ema_fast']<reference['indicators']['buy_ema_slow']
    assert reference['p1']['ma']==2000 and reference['p1']['state']=='BELOW'
    assert data==before
    publish_context({'contract':data['contract'],'observed_at':NOW.timestamp(),'reference':reference},preview=True)
    snapshot=SimpleNamespace(contract=data['contract'],quotes={data['contract']:Quote(**data['quotes'][data['contract']])},bars=data['bars'])
    view={**data,'market_context':context(snapshot,now=NOW.timestamp(),preview=True)}
    entry,trend=signal_preview(view,now=NOW.timestamp())
    assert entry[0]=='ĐÓNG PHIÊN' and 'Đã tính EMA/RSI' in entry[1] and entry[2]=='amber'
    assert trend[0]=='DOWN' and trend[2]=='red' and '14:45' in trend[1]
    assert not snapshot.quotes[snapshot.contract].fresh(now=NOW.timestamp())
    assert market_status(view,now=NOW.timestamp())==('DNSE · ĐÓNG PHIÊN','blue')
    # Refreshing the market cannot make old analysis appear newly calculated.
    view['market_context']['observed_at']-=30
    assert signal_preview(view,now=NOW.timestamp())[0][0]=='CHỜ'


def test_closing_reference_calculates_locally_without_shared_cache_and_only_unlocks_rule_preview(monkeypatch):
    from ckps.dashboard.mayin.pnl_preview import protection_reference
    data=closing_data();data['account']={'margin_per_contract':40_000_000,'margin_reference_price':1990}
    before=deepcopy(data)
    quote=Quote(**data['quotes'][data['contract']])
    snapshot=SimpleNamespace(contract=data['contract'],quotes={data['contract']:quote},bars=data['bars'])
    view=context(snapshot,now=NOW.timestamp(),preview=True)
    assert view['entry']=={'state':'CLOSED','calculated':True} and view['state']=='BELOW'
    monkeypatch.setattr('ckps.dashboard.mayin.pnl_preview.time.time',lambda:NOW.timestamp())
    ref=protection_reference(data)
    assert ref.entry==1990 and ref.margin==40_000_000 and ref.source=='ĐÓNG PHIÊN'
    assert data==before and not quote.fresh(now=NOW.timestamp())
    snapshot.bars=[]
    assert context(snapshot,now=NOW.timestamp(),preview=True)['entry']=={'state':'CLOSED','calculated':False}
    data['quotes'][data['contract']]['at']-=86400
    assert protection_reference(data).entry is None


def test_order_gate_explains_close_stale_and_cached_prices_without_unlocking_orders():
    from ckps.dashboard.mayin.connection_status import order_block_reason
    view=closing_data()
    view.update(healthy=True,consistent=True,mode='PAPER')
    assert order_block_reason(view,now=NOW.timestamp())=='ĐÓNG PHIÊN · Chờ giá mới để đặt lệnh'
    view['mode']='REAL'
    assert order_block_reason(view,now=NOW.timestamp()).startswith('ĐÓNG PHIÊN')
    quote=view['quotes'].pop(view['contract'])
    view['market_cache']={'quote':quote,'contract':view['contract']}
    assert order_block_reason(view,now=NOW.timestamp()).startswith('CHỜ GIÁ DNSE')
    view['quotes'][view['contract']]=quote
    current=NOW.replace(hour=10,minute=0).timestamp()
    quote['at']=current-30
    assert order_block_reason(view,now=current).startswith('GIÁ CŨ')
    quote['at']=current
    assert order_block_reason(view,now=current)==''
    view['calendar']={'reason':'ATO · Chặn theo lịch'}
    assert order_block_reason(view,now=current)=='ATO · Chặn theo lịch'
    view['consistent']=False
    assert 'đối soát' in order_block_reason(view,now=current)
    assert 'Đang gửi' in order_block_reason(view,now=current,busy=True)
    assert 'Đang đổi' in order_block_reason(view,now=current,requested=True)


@pytest.mark.parametrize('change',[dict(source='PAPER'),dict(source='CACHE'),dict(symbol='41I1GC000'),
    dict(at=NOW.timestamp()+10),dict(at=(NOW-timedelta(days=1)).timestamp()),
    dict(at=NOW.replace(hour=14,minute=44).timestamp()),dict(last=float('nan'))])
def test_missing_old_or_wrong_source_is_not_a_verified_closing_reference(change):
    data=closing_data();quote=data['quotes'][data['contract']];quote.update(change)
    assert not closing_quote(data['contract'],quote,now=NOW.timestamp())
    assert closing_analysis(data,Settings(),now=NOW.timestamp()) is None


def test_intraday_outage_remains_stale_and_missing_bars_never_invent_indicators():
    data=closing_data(5)
    assert not closing_analysis(data,Settings(),now=NOW.timestamp())['ready']
    now=NOW.replace(hour=10,minute=0).timestamp()
    data['quotes'][data['contract']]['at']=now-30
    assert closing_analysis(data,Settings(),now=now) is None
    view={**data,'market_context':{},'market_connection':{'configured':True}}
    assert all(v[0]=='CHỜ' and v[2]=='amber' for v in signal_preview(view,now=now))
    assert market_status(view,now=now)==('DNSE · GIÁ CŨ','amber')


def test_automatic_preview_is_market_only_and_rotates_api_after_previous_process_stops(monkeypatch):
    import ckps.services.signal_process as module
    sessions=[]
    class Process:
        def __init__(self,settings,credentials,*,preview_only):
            assert preview_only and not settings.telegram_enabled and not settings.entry_notifications and not settings.telegram_chat
            assert set(credentials)=={'key','secret'}
            self.running=True;self.closed=0;self.updates=[]
            sessions.append(self)
        def close(self):self.closed+=1
        def configure(self,settings,token):
            assert not settings.telegram_enabled and not settings.entry_notifications and token==''
            self.updates.append(settings)
    monkeypatch.setattr(module,'SignalProcess',Process)
    credentials={'key':'k','secret':'s'}
    settings=Settings(telegram_enabled=True,telegram_chat='private',entry_notifications=True)
    app=SimpleNamespace(preview_analysis_enabled=True,closing=False,runtime=object(),
        _mode_credentials=lambda:dict(credentials),_signal_settings=settings)
    ensure_preview_backend(app);ensure_preview_backend(app)
    assert len(sessions)==1 and settings.telegram_enabled
    save_signal_settings(app,settings)
    assert len(sessions[0].updates)==1
    # Blackbox writes the shared signal file from a separate process. The
    # already-running main Preview reloads it without gaining Telegram rights.
    from dataclasses import replace
    from ckps.services.signal_config import write_signal_settings
    changed=replace(settings,signals={**settings.signals,'buy_ema_fast':4})
    write_signal_settings(changed)
    ensure_preview_backend(app)
    assert sessions[0].updates[-1].signals['buy_ema_fast']==4
    assert signal_settings(app).signals['buy_ema_fast']==4
    credentials['key']='new'
    ensure_preview_backend(app);ensure_preview_backend(app)
    assert sessions[0].closed==1 and len(sessions)==1
    sessions[0].running=False;app._preview_retry_at=0
    ensure_preview_backend(app)
    assert len(sessions)==2
    app.preview_analysis_enabled=False
    sessions[-1].running=False
    ensure_preview_backend(app)
    assert len(sessions)==2


def test_preview_runtime_cannot_enable_telegram_even_from_saved_settings_or_environment(monkeypatch):
    from ckps.services.signal_runtime import SignalRuntime
    from ckps.services.signal_config import signal_folder
    from ckps.connections.secure_session import remember_telegram_token
    remember_telegram_token('saved-token-also-forbidden-in-preview')
    monkeypatch.setenv('CKPS_TELEGRAM_TOKEN','must-not-be-used')
    class Market:
        def snapshot(self):return closing_data()
        def close(self):pass
    settings=Settings(telegram_enabled=True,telegram_chat='private',entry_notifications=True)
    runtime=SignalRuntime(settings,{'telegram_token':'also-forbidden'},market=Market(),preview_only=True)
    try:
        assert runtime.owner_token=='' and not runtime.owner_enabled and runtime.owner_chat==''
        runtime._configure(asdict(settings),'new-forbidden-token')
        assert runtime.owner_token=='' and not runtime.owner_enabled and not runtime.settings.entry_notifications
        assert runtime.store.path.parent==signal_folder()/'preview'
        assert not (signal_folder()/'market-context.json').exists()
        assert not runtime.store.orders()
    finally:
        runtime.close();runtime.thread.join(timeout=5)
    assert not runtime.thread.is_alive()
