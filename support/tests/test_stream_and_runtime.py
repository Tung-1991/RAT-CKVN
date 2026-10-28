from dataclasses import asdict
from datetime import datetime, timedelta
import json
import queue
import threading
import time

import msgpack
import pytest

from ckps.models import Order, Quote, Settings, market_time
from ckps.trading.execution import Engine
from ckps.connections.dnse.stream import MarketFeed
from ckps.services.runtime import Runtime
from ckps.services.signal_runtime import SignalRuntime
from ckps.services.technical_notifications import VN, completed_atr_pct, completed_bars


def test_paper_without_dnse_never_invents_prices_or_enables_trading(system):
    from ckps.connections.dnse.paper import PaperBroker
    from ckps.connections.dnse.protocol import BrokerError
    engine,_,store=system
    account=store.get('paper','account')
    account['price']=2000  # An old synthetic price may remain in a migrated ledger.
    store.put('paper','account',account)
    live=Engine(store,PaperBroker(store,engine.settings),engine.settings)
    snap=live.poll()
    assert snap.quotes=={} and snap.margin_per_contract is None
    assert snap.nav==100_000_000 and snap.qmax_long is None
    with pytest.raises(BrokerError):live.open_manual('LONG',1,'MOK')
    with pytest.raises(BrokerError):live.arm(True)
    with pytest.raises(BrokerError):live.broker.set_price(2010)
    with pytest.raises(BrokerError):live.broker.set_bars([])
    assert not store.orders() and not live.enabled.is_set()


@pytest.mark.parametrize('side,entry,closed,pnl',[('LONG',2050.1,2059.9,980_000),('SHORT',2049.9,2060.1,-1_020_000)])
def test_paper_uses_dnse_bid_ask_and_real_contract_but_only_virtual_money(system,side,entry,closed,pnl):
    from copy import deepcopy
    from ckps.connections.dnse.paper import PaperBroker
    from ckps.models import Quote
    engine,_,store=system
    symbol='41I1GB000'
    class Market:
        feed=None
        quote=Quote(symbol,2050,2049.9,2050.1,source='DNSE')
        def snapshot(self,symbols):
            return {'contract':symbol,'quotes':{symbol:deepcopy(self.quote)},'bars':[{'time':1,'close':2000}],
                    'configured':True,'connected':True,'error':''}
    market=Market()
    engine.settings.estimated_fee_per_contract=25_000
    live=Engine(store,PaperBroker(store,engine.settings,market=market),engine.settings)
    opened=live.open_manual(side,1,'MOK')
    live.poll()
    assert opened.avg_fill==pytest.approx(entry) and opened.symbol==symbol
    assert store.get('paper','account')['cash']==99_975_000
    assert live.latest.bars==[{'time':1,'close':2000}]
    market.quote=Quote(symbol,2060,2059.9,2060.1,source='DNSE')
    live.poll()
    position=store.positions()[0]
    close=live.close_position(position.id,1)
    assert close.avg_fill==pytest.approx(closed)
    assert store.positions(closed=True)[0].realized==pytest.approx(pnl)
    assert store.get('paper','account')['cash']==pytest.approx(100_000_000+pnl-50_000)
    assert len(store.orders())==2  # No broker submission method exists on Market.


def test_paper_pending_limit_never_fills_from_stale_or_wrong_contract_quotes(system):
    from ckps.connections.dnse.paper import PaperBroker
    engine,_,store=system
    symbol='41I1GB000'
    class Market:
        feed=None
        quote=Quote(symbol,2050,source='DNSE')
        def snapshot(self,symbols):return {'contract':symbol,'quotes':{symbol:self.quote},'bars':[]}
    market=Market()
    live=Engine(store,PaperBroker(store,engine.settings,market=market),engine.settings)
    order=live.open_manual('LONG',1,'LO',2040)
    assert order.status=='WORKING'
    for quote in (Quote(symbol,2030,at=time.time()-300,source='DNSE'),Quote('41I1GC000',2030,source='DNSE')):
        market.quote=quote;live.poll(manage=False)
        assert store.order(order.id).filled==0 and not store.positions()
    market.quote=Quote(symbol,2030,source='DNSE');live.poll(manage=False)
    assert store.order(order.id).avg_fill==2030 and store.positions()[0].symbol==symbol


def test_paper_readonly_client_needs_no_account_or_otp_and_blocks_all_trading(monkeypatch):
    from ckps.connections.dnse.history import ReadOnlyHistory
    from ckps.connections.dnse.paper_market import PaperMarket
    from ckps.connections.dnse.protocol import BrokerError
    calls=[]
    client=ReadOnlyHistory('offline-key','offline-secret')
    class Response:
        ok=True
        status_code=200
        headers={}
        def __init__(self,value):self.value=value
        def json(self):return self.value
    def request(method,url,**kwargs):
        calls.append((method,url,kwargs))
        return Response({'t':[1],'o':[2000],'h':[2010],'l':[1990],'c':[2005]}) if url.endswith('/price/ohlc') else Response({'price':2005,'timestamp':time.time()})
    monkeypatch.setattr(client.session,'request',request)
    monkeypatch.setattr(client,'resolve',lambda:'41I1GB000')
    monkeypatch.setattr(client.feed,'start',lambda symbols:None)
    market=PaperMarket(client,start=False)
    market._poll()
    data=market.snapshot()
    assert data['quotes']['41I1GB000'].last==2005 and data['bars'][0]['close']==2005
    for method,path in [('POST','/accounts/123/orders'),('GET','/accounts/123/balances'),('POST','/registration/send-email-otp')]:
        with pytest.raises(BrokerError):client.request(method,path)
    assert len(calls)==2 and all(method=='GET' and '/price/' in url and 'trading-token' not in kw['headers'] for method,url,kw in calls)
    market.close()


def test_slow_paper_market_history_does_not_block_sl_or_local_fills(system):
    from ckps.connections.dnse.paper import PaperBroker
    from ckps.connections.dnse.paper_market import PaperMarket
    from ckps.models import ExitSettings
    engine,_,store=system
    symbol='41I1GB000'
    entered,release=threading.Event(),threading.Event()
    class Feed:
        quote=Quote(symbol,2000,source='DNSE')
        def start(self,symbols):pass
        def reset_extremes(self,symbol):pass
        def latest(self,symbol,age):return self.quote
    class Client:
        feed=Feed()
        def resolve(self):return symbol
        def get_quote(self,symbol):return self.feed.quote
        def daily_bars(self):
            entered.set();assert release.wait(5);return []
        def close(self):pass
    client=Client()
    market=PaperMarket(client)
    try:
        assert entered.wait(2)
        engine.settings.exit=asdict(ExitSettings(sl_enabled=True,sl_distance=10))
        live=Engine(store,PaperBroker(store,engine.settings,market=market),engine.settings)
        started=time.monotonic()
        live.open_manual('LONG',1,'MOK');live.poll();live.arm(True)
        client.feed.quote=Quote(symbol,1989,source='DNSE')
        live.on_prices({symbol:client.feed.quote},{symbol:(1989,2000)})
        assert time.monotonic()-started<1
        assert store.orders()[-1].reason=='SL' and store.orders()[-1].filled==1
        assert store.positions()==[]
    finally:
        release.set();market.close()


def test_stream_ignores_heartbeat_and_non_vn30():
    feed = MarketFeed("test-key", "test-secret")
    feed.symbols = {"41I1GB000"}
    class Socket:
        def send(self, value):
            pass
    ws = Socket()
    feed._message(ws, json.dumps({"action": "ping"}))
    feed._message(ws, json.dumps({"symbol": "FPT", "matchPrice": 100, "timestamp": time.time()}))
    assert not feed.ticks


def test_msgpack_ticks_preserve_extremes_and_actual_event_time():
    feed = MarketFeed("test-key", "test-secret")
    feed.symbols = {"41I1GB000"}
    feed.authenticated = True
    for px in [2000, 2010, 2005]:
        feed._message(None, msgpack.packb({"data": {"symbol": "41I1GB000", "matchPrice": px, "timestamp": time.time()}}, use_bin_type=True))
    ticks, extremes = feed.drain()
    assert ticks["41I1GB000"].last == 2005
    assert extremes["41I1GB000"] == (2000, 2010)
    assert not feed.changed.is_set()


def test_undated_or_old_stream_tick_is_not_fresh():
    feed = MarketFeed("test-key", "test-secret")
    feed.symbols = {"41I1GB000"}
    feed.authenticated = True
    feed._message(None, json.dumps({"symbol": "41I1GB000", "matchPrice": 2000}))
    assert feed.latest("41I1GB000") is None
    feed._message(None, json.dumps({"symbol": "41I1GB000", "matchPrice": 2001, "timestamp": time.time() - 300}))
    assert feed.latest("41I1GB000") is None


def test_naive_dnse_time_is_gmt_plus_seven():
    expected = datetime(2026, 10, 23, 14, 0, tzinfo=VN).timestamp()
    assert market_time("2026-10-23 14:00:00.000") == expected
    assert market_time(expected * 1000) == expected


def test_atr_excludes_open_day_sorts_and_ignores_bad_rows():
    now = datetime(2026, 10, 25, 12, tzinfo=VN)
    bars = []
    for offset in range(20):
        at = now - timedelta(days=offset)
        bars.append({"time": at.timestamp(), "high": 2010, "low": 1990, "close": 2000})
    bars[0]["high"] = 999999
    bars.append({"time": (now - timedelta(days=2)).timestamp(), "high": "bad", "low": 1990, "close": 2000})
    closed = completed_bars(bars, now)
    assert len(closed) == 19
    assert closed[0]["time"] < closed[-1]["time"]
    assert all(bar["high"] == 2010 for bar in closed)


def test_restart_distinguishes_unsent_from_unknown_handoff(system):
    engine, broker, store = system
    unsent = Order.create("VN30F1M", "LONG", 1)
    sending = Order.create("VN30F1M", "LONG", 1, status="SUBMITTING")
    store.save_order(unsent)
    store.save_order(sending)
    Engine(store, broker, engine.settings)
    assert store.order(unsent.id).status == "CANCELLED"
    assert store.order(sending.id).status == "UNKNOWN"


def test_off_cancels_a_queued_on_before_it_can_arm(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    calls = []
    original_poll, original_arm = Engine.poll, Engine.arm
    def blocked_poll(self, *args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original_poll(self, *args, **kwargs)
    def record_arm(self, enabled):
        calls.append(enabled)
        return original_arm(self, enabled)
    monkeypatch.setattr(Engine, "poll", blocked_poll)
    monkeypatch.setattr(Engine, "arm", record_arm)
    runtime = Runtime(Settings())
    try:
        assert entered.wait(5)
        runtime.command("arm", True)
        runtime.command("arm", False)
        release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and False not in calls:
            time.sleep(.02)
        assert False in calls and True not in calls
        assert not runtime.engine.enabled.is_set()
    finally:
        release.set()
        runtime.close()
        runtime.thread.join(timeout=5)
    assert not runtime.thread.is_alive()


def test_single_signal_telegram_defaults_off_and_ignores_old_owner_environment(monkeypatch):
    monkeypatch.setenv('CKPS_OWNER_ALERTS_ENABLED','1')
    monkeypatch.setenv('CKPS_OWNER_TELEGRAM_TOKEN','unused-legacy-token')
    monkeypatch.setenv('CKPS_OWNER_TELEGRAM_CHAT','unused-legacy-chat')
    runtime = SignalRuntime(Settings())
    try:
        assert not runtime.settings.telegram_enabled
        assert not runtime.owner_enabled
        assert not runtime.owner_token
        from ckps.rules.signal_settings import SignalSettings
        signals = SignalSettings.from_dict(runtime.settings.signals)
        assert not signals.buy_alert_enabled and not signals.sell_alert_enabled
    finally:
        runtime.close()
        runtime.thread.join(timeout=5)


@pytest.mark.parametrize('signal_alert,exit_alert,expected', [(False,False,0),(True,False,1),(False,True,1),(True,True,2)])
def test_signal_alert_switches_gate_notifications_without_orders(system, signal_alert, exit_alert, expected):
    from types import SimpleNamespace
    from ckps.rules.signal_settings import SignalSettings
    engine, broker, store=system
    engine.settings.signals=SignalSettings(buy_alert_enabled=signal_alert,sell_alert_enabled=exit_alert).to_dict()
    runtime=SignalRuntime.__new__(SignalRuntime)
    runtime.settings,runtime.latest,runtime.store=engine.settings,engine.latest,store
    runtime.owner_enabled,runtime.owner_token,runtime.owner_chat=True,'offline-token','offline-chat'
    runtime.owner_state,runtime.owner_last=None,0
    runtime.analysis=SimpleNamespace(snapshot=lambda:{'contract':engine.latest.contract,'p2':{
        'buy_alert':True,'exit_alert':True,'indicators':{'buy_ema_fast':2001,'buy_ema_slow':2000,
            'sell_ema_fast':1998,'sell_ema_slow':1999,'rsi':51}}})
    runtime._owner_telemetry()
    rows=store.db.execute('SELECT text FROM outbox WHERE sent=0').fetchall()
    assert len(rows)==expected
    text='\n'.join(row[0] for row in rows)
    assert (' · TÍN HIỆU · ALERT' in text)==signal_alert
    assert (' · E · ALERT' in text)==exit_alert
    runtime._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==expected
    assert store.orders()==[] and store.positions()==[] and not engine.enabled.is_set()


@pytest.mark.parametrize('disabled_label,signal_alert,exit_alert', [('TÍN HIỆU',False,True),('E',True,False)])
def test_disabled_signal_branch_drops_restored_alert_before_network(system, disabled_label, signal_alert, exit_alert):
    from ckps.rules.signal_settings import SignalSettings
    engine, broker, store=system
    engine.settings.signals=SignalSettings(buy_alert_enabled=signal_alert,sell_alert_enabled=exit_alert).to_dict()
    store.notify('owner:offline-chat',f'VN30F1M PAPER · {disabled_label} · ALERT\nold message')
    runtime=SignalRuntime.__new__(SignalRuntime)
    runtime.settings,runtime.store=engine.settings,store
    runtime.owner_enabled,runtime.owner_token=True,'offline-token'
    runtime._flush_telegram()  # The fixture rejects all real HTTP.
    assert store.db.execute('SELECT sent FROM outbox').fetchone()[0]==2
    assert store.orders()==[]


def test_saving_alert_off_discards_private_queue_without_changing_protection():
    from dataclasses import replace
    from ckps.rules.signal_settings import SignalSettings
    settings=Settings(signals=SignalSettings(buy_alert_enabled=True,sell_alert_enabled=True).to_dict())
    runtime=SignalRuntime(settings)
    try:
        runtime.store.notify('owner:offline-chat','old private alert')
        updated=replace(settings,signals=SignalSettings().to_dict())
        runtime.command('settings',asdict(updated),'')
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            kind,payload=runtime.events.get(timeout=5)
            if kind=='success' and payload=='settings':
                break
        else:
            pytest.fail('Settings command did not complete.')
        assert runtime.store.db.execute('SELECT sent FROM outbox').fetchone()[0]==2
        assert runtime.settings.exit==settings.exit
        assert not hasattr(runtime,"engine") and runtime.store.orders()==[]
    finally:
        runtime.close()
        runtime.thread.join(timeout=5)


def test_one_signal_channel_rejects_order_and_protection_notifications(system,monkeypatch):
    from ckps.rules.signal_settings import SignalSettings
    engine,broker,store=system
    engine.settings.telegram_enabled=True
    engine.settings.telegram_chat='one-chat'
    engine.settings.signals=SignalSettings(buy_alert_enabled=True,sell_alert_enabled=True).to_dict()
    engine.settings.market_alerts={'trend_enabled':True,'movement_enabled':True}
    runtime=SignalRuntime.__new__(SignalRuntime)
    runtime.settings,runtime.store=engine.settings,store
    runtime.owner_enabled,runtime.owner_token,runtime.owner_chat=True,'one-token','one-chat'
    sent=[]
    class Response:
        ok=True
        def json(self):return {'ok':True}
    def send(url,**kwargs):
        sent.append((url,kwargs['json']))
        return Response()
    monkeypatch.setattr('ckps.services.signal_notifications.requests.post',send)
    for kind in ('TÍN HIỆU','E','TREND','VOLATILITY'):
        store.notify('owner:one-chat',f'VN30F1M PAPER · {kind} · ALERT\nnew signal')
    engine._notify('LONG VN30F1M · ARM ALERT\nprice hit','alert:position:ARM:1')
    assert not store.db.execute("SELECT id FROM outbox WHERE text LIKE '%ARM ALERT%'").fetchall()
    store.notify('owner:one-chat','LONG VN30F1M · ARM ALERT\nlegacy protection')
    engine._notify('FILLED order','order:filled')
    store.notify('old-order-chat','legacy order status')
    store.notify('owner:old-signal-chat','VN30F1M PAPER · TREND · ALERT\nold recipient')
    runtime._flush_telegram();runtime._flush_telegram()
    assert len(sent)==4 and all(url.endswith('/botone-token/sendMessage') and body['chat_id']=='one-chat' for url,body in sent)
    assert all('legacy' not in body['text'] and 'FILLED' not in body['text'] for url,body in sent)
    assert store.db.execute('SELECT COUNT(*) FROM outbox WHERE sent=2').fetchone()[0]==3
    assert not store.orders() and not engine.enabled.is_set()


def test_runtime_applies_one_telegram_configuration_atomically_and_drops_old_queue(monkeypatch):
    from dataclasses import replace
    from ckps.config import runtime_root
    from ckps.services.signal_config import read_signal_settings
    runtime=SignalRuntime(Settings())
    try:
        runtime.store.notify('owner:old-chat','VN30F1M PAPER · TREND · ALERT\nold')
        settings=replace(runtime.settings,telegram_enabled=True,telegram_chat='only-chat')
        runtime.command('settings',asdict(settings),'session-only-token')
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            kind,payload=runtime.events.get(timeout=4)
            if kind=='success' and payload=='settings':break
        else:pytest.fail('Telegram settings did not finish.')
        assert runtime.owner_enabled and runtime.owner_chat=='only-chat'
        assert runtime.owner_token=='session-only-token'
        assert runtime.store.db.execute('SELECT sent FROM outbox').fetchone()[0]==2
        assert read_signal_settings().telegram_chat=='only-chat'
        assert 'session-only-token' not in (runtime_root()/'signals'/'settings.json').read_text(encoding='utf-8')
    finally:
        runtime.close();runtime.thread.join(5)


def test_runtime_paper_funding_applies_persists_and_rejects_invalid_amounts():
    from ckps.config import read_settings
    runtime=Runtime(Settings(),offline=True)
    try:
        runtime.command('paper_capital',275_000_000)
        def result():
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                kind,payload=runtime.events.get(timeout=4)
                if kind=='paper_capital_result':return payload
            pytest.fail('Paper funding result did not arrive.')
        assert result()=={'capital':275_000_000}
        assert read_settings().paper_balance==275_000_000
        runtime.command('paper_capital',float('nan'))
        assert 'error' in result()
        assert runtime.store.get('paper','account')['cash']==275_000_000
        assert not runtime.store.orders() and not runtime.engine.enabled.is_set()
    finally:
        runtime.close();runtime.thread.join(5)
