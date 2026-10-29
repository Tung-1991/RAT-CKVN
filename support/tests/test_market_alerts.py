from dataclasses import asdict
from datetime import datetime, timedelta
import threading
import time
from types import SimpleNamespace

import pytest

from ckps.models import ExitSettings, Settings
from ckps.rules.market_alerts import MarketAlertSettings, MovementDetector
from ckps.rules.p2.market import VN_TZ
from ckps.services.market_alerts import MarketAlerts
from ckps.services.runtime import Runtime
from ckps.services.signal_runtime import SignalRuntime


NOW = datetime(2026,10,26,10,0,tzinfo=VN_TZ).timestamp()


def test_market_alert_defaults_and_invalid_evidence_settings():
    defaults = MarketAlertSettings.from_dict()
    assert not defaults.trend_enabled and not defaults.movement_enabled
    assert (defaults.fast_points,defaults.window_seconds,defaults.session_points,defaults.confirmations)==(5,60,20,2)
    for values in ({'fast_points':float('nan')},{'window_seconds':0},{'confirmations':1.5},
                   {'trend_enabled':'false'},{'session_points':0}):
        with pytest.raises(ValueError):
            MarketAlertSettings.from_dict(values)


@pytest.mark.parametrize('direction',[1,-1])
def test_fast_move_requires_distinct_fresh_ticks_and_two_confirmations(direction):
    detector = MovementDetector()
    settings = MarketAlertSettings.from_dict()
    assert detector.observe('VN30F1M',2000,NOW,settings) is None
    assert detector.observe('VN30F1M',2000+direction*5,NOW+1,settings) is None
    assert detector.observe('VN30F1M',2000+direction*9,NOW+1,settings) is None
    result = detector.observe('VN30F1M',2000+direction*6,NOW+2,settings)
    assert result['movement_type']=='FAST' and result['change_points']==direction*6
    assert detector.observe('FPT',100,NOW+3,settings) is None


def test_movement_reset_across_gaps_days_and_contracts():
    settings = MarketAlertSettings.from_dict({'session_enabled':False})
    detector = MovementDetector()
    detector.observe('VN30F1M',2000,NOW,settings)
    assert detector.observe('VN30F1M',2006,NOW+20,settings,max_gap=10) is None
    assert detector.observe('VN30F1M',2007,NOW+21,settings) is None
    assert detector.observe('41I1GB000',2050,NOW+22,settings) is None
    assert detector.observe('41I1GB000',2100,NOW+86400,settings) is None


def test_trend_history_deduplicates_restart_and_rejects_stale_or_wrong_contract(system):
    engine,broker,store = system
    monitor = MarketAlerts(store)
    symbol = 'VN30F1M'
    quote = {'last':2001,'at':NOW}
    analysis = {'contract':symbol,'observed_at':NOW,'p1':{'state':'ABOVE','price':2001,'ma':2000}}
    first = monitor.observe(symbol,quote,analysis,{},now=NOW,max_age=10)
    assert first['events'][0]['channel']=='TREND'
    assert 'UPTREND' in first['events'][0]['reason']
    assert MarketAlerts(store).observe(symbol,quote,analysis,{},now=NOW,max_age=10)['events']==[]
    analysis['p1']={'state':'BELOW','price':1999,'ma':2000}
    assert not monitor.observe(symbol,quote,analysis,{},now=NOW+11,max_age=10)['events']
    analysis['contract']='41I1GB000'
    assert not monitor.observe(symbol,quote,analysis,{},now=NOW,max_age=10)['events']
    analysis['contract']=symbol
    analysis['observed_at']=NOW+1
    quote={'last':1999,'at':NOW+1}
    result = monitor.observe(symbol,quote,analysis,{},now=NOW+1,max_age=10)
    assert 'DOWNTREND' in result['events'][0]['reason']
    assert len(store.all('signal_history'))==2
    assert not store.orders() and not store.positions() and not engine.enabled.is_set()


def test_session_anchor_cooldown_and_ledger_isolation(system,tmp_path):
    from ckps.storage import Store
    engine,broker,store = system
    monitor = MarketAlerts(store)
    config = {'fast_points':100,'session_points':20,'cooldown_minutes':30}
    for offset,price in ((0,2000),(120,2020)):
        result = monitor.observe('VN30F1M',{'at':NOW+offset,'last':price},{},config,now=NOW+offset,max_age=10)
    assert len(result['events'])==1 and 'MỐC THEO DÕI' in result['events'][0]['reason']
    result = MarketAlerts(store).observe('VN30F1M',{'at':NOW+240,'last':2040},{},config,now=NOW+240,max_age=10)
    assert not result['events']
    other = Store(tmp_path/'other.sqlite3')
    try:
        assert not MarketAlerts(other).observe('VN30F1M',{'at':NOW+240,'last':2040},{},config,now=NOW+240,max_age=10)['events']
    finally:
        other.close()
    assert not monitor.observe('VN30F1M',{'at':NOW+86400,'last':2100},{},config,now=NOW+86400,max_age=10)['events']


@pytest.mark.parametrize('phase',['HOLIDAY','WEEKEND','CLOSED','LUNCH'])
def test_known_calendar_phase_prevents_market_alerts(system,phase):
    engine,broker,store=system
    monitor=MarketAlerts(store)
    analysis={'contract':'VN30F1M','observed_at':NOW,'market_phase':phase,
              'p1':{'state':'ABOVE','price':2000,'ma':1990}}
    assert not monitor.observe('VN30F1M',{'last':2000,'at':NOW},analysis,{},now=NOW,max_age=10)['events']
    assert not store.all('signal_history') and not store.orders()


def test_market_alert_channels_are_separate_from_p2_and_cannot_trade(system,monkeypatch):
    import queue
    engine,broker,store = system
    engine.settings.market_alerts = MarketAlertSettings.from_dict({'trend_enabled':True,'movement_enabled':True}).to_dict()
    engine.latest.quotes[engine.latest.contract].at = NOW
    engine.latest.quotes[engine.latest.contract].last = 2000
    runtime = SignalRuntime.__new__(SignalRuntime)
    runtime.latest,runtime.store,runtime.settings = engine.latest,store,engine.settings
    runtime.market_alerts = MarketAlerts(store)
    runtime.events = queue.Queue()
    runtime.telegram_error = ''
    runtime.owner_enabled,runtime.owner_token,runtime.owner_chat = True,'offline-token','offline-chat'
    runtime.analysis = SimpleNamespace(update=lambda *args:None,snapshot=lambda:{'contract':engine.latest.contract,
        'observed_at':NOW,'p1':{'state':'ABOVE','ma':1990,'price':2000}})
    runtime.market=SimpleNamespace(snapshot=lambda:{'contract':engine.latest.contract,'quotes':{k:asdict(v) for k,v in engine.latest.quotes.items()},'bars':[]})
    monkeypatch.setattr('ckps.services.signal_runtime.time.time',lambda:NOW)
    runtime._publish()
    assert store.db.execute('SELECT COUNT(*) FROM outbox WHERE sent=0').fetchone()[0]==1
    text = store.db.execute('SELECT text FROM outbox').fetchone()[0]
    assert 'TREND' in text
    runtime._publish()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
    engine.settings.market_alerts['trend_enabled']=False
    store.notify('owner:offline-chat','VN30F1M PAPER · VOLATILITY · ALERT\nnew movement')
    runtime._drop_disabled_owner()
    assert [row[0] for row in store.db.execute('SELECT sent FROM outbox ORDER BY rowid')]==[2,0]
    assert not store.orders() and not engine.enabled.is_set()


def test_signal_switch_does_not_replay_old_condition_and_channels_do_not_share_cooldown(system):
    from ckps.models import Quote
    from ckps.rules.signal_settings import SignalSettings
    engine,broker,store=system
    state={'buy_alert':True,'exit_alert':False,'indicators':{
        'buy_ema_fast':2001,'buy_ema_slow':2000,'sell_ema_fast':1998,'sell_ema_slow':1999,'rsi':51}}
    engine.settings.entry_notifications=True
    engine.settings.signals=SignalSettings().to_dict()
    runtime=SignalRuntime.__new__(SignalRuntime)
    runtime.settings,runtime.latest,runtime.store=engine.settings,engine.latest,store
    runtime.owner_enabled,runtime.owner_token,runtime.owner_chat=True,'offline-token','offline-chat'
    runtime.owner_state,runtime.owner_last=None,0
    runtime.analysis=SimpleNamespace(snapshot=lambda:{'contract':engine.latest.contract,'p2':state})
    runtime._owner_telemetry()
    engine.settings.signals.update(buy_alert_enabled=True,sell_alert_enabled=True)
    runtime._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==0
    state['buy_alert']=False
    runtime._owner_telemetry()
    state['buy_alert']=True
    runtime._owner_telemetry()
    state['exit_alert']=True
    runtime._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==2
    engine.latest.contract='41I1GC000'
    engine.latest.quotes[engine.latest.contract]=Quote(engine.latest.contract,2000)
    runtime._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==4
    assert not store.orders() and not engine.enabled.is_set()


def test_fresh_quote_cannot_grant_notification_to_stale_analysis(system):
    from ckps.rules.signal_settings import SignalSettings
    engine,broker,store=system
    engine.settings.entry_notifications=True
    engine.settings.signals=SignalSettings(buy_alert_enabled=True).to_dict()
    analysis={'contract':engine.latest.contract,'observed_at':time.time()-30,'p2':{
        'buy_alert':True,'indicators':{'buy_ema_fast':2001,'buy_ema_slow':2000,'rsi':51}}}
    runtime=SignalRuntime.__new__(SignalRuntime)
    runtime.settings,runtime.latest,runtime.store=engine.settings,engine.latest,store
    runtime.owner_enabled,runtime.owner_token,runtime.owner_chat=True,'offline-token','offline-chat'
    runtime.owner_state,runtime.owner_last=None,0
    runtime.analysis=SimpleNamespace(snapshot=lambda:analysis)
    runtime._owner_telemetry()
    assert not store.db.execute('SELECT id FROM outbox').fetchall()
    analysis['observed_at']=time.time()
    runtime._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
    assert not store.orders()


def test_slow_telegram_does_not_delay_automatic_sl(monkeypatch):
    entered,release = threading.Event(),threading.Event()
    monkeypatch.setenv('CKPS_TELEGRAM_TOKEN','offline-token')
    def blocked_send(*args,**kwargs):
        entered.set()
        assert release.wait(8)
        return SimpleNamespace(ok=True,json=lambda:{'ok':True})
    monkeypatch.setattr('ckps.services.signal_notifications.requests.post',blocked_send)
    settings = Settings(telegram_enabled=True,telegram_chat='offline-chat',
        exit=asdict(ExitSettings(distance_unit='POINTS', sl_enabled=True,sl_distance=10)))
    runtime = Runtime(settings,offline=True)
    signals_runtime=SignalRuntime(settings)
    try:
        signals_runtime.store.notify('owner:offline-chat','VN30F1M PAPER · TREND · ALERT\nuptrend')
        signals_runtime.settings.market_alerts=MarketAlertSettings.from_dict({'trend_enabled':True}).to_dict()
        assert entered.wait(4)
        runtime.command('open_manual','LONG',1,'MOK')
        runtime.command('arm',True)
        runtime.command('set_price',1990)
        deadline = time.monotonic()+3
        while time.monotonic()<deadline and not runtime.store.positions(closed=True):
            time.sleep(.02)
        assert not release.is_set()
        closed = runtime.store.positions(closed=True)
        assert len(closed)==1 and closed[0].quantity==0
        assert any(o.source=='AUTO' and o.reason=='SL' and o.status=='FILLED' for o in runtime.store.orders())
    finally:
        release.set()
        runtime.close();signals_runtime.close()
        runtime.thread.join(5);signals_runtime.thread.join(5)
    assert not runtime.thread.is_alive() and not signals_runtime.thread.is_alive() and not signals_runtime.telegram_thread.is_alive()
