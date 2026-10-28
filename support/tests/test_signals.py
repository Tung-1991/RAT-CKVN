from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta
import time

import pytest

from ckps.connections.dnse.history import NoHistory, ReadOnlyHistory
from ckps.models import Settings
from ckps.rules.signal_settings import SignalSettings
from ckps.rules.p2.market import VN_TZ, active_trading_minutes
from ckps.services.signals import SignalAnalysis, daily_rows, p1_snapshot
from ckps.storage import Store


NOW = datetime(2026, 10, 26, 9, 10, tzinfo=VN_TZ)


def test_vn30_clock_retains_close_lunch_weekend_and_exchange_holidays():
    from ckps.rules.p2.market import market_phase
    def phase(day,clock,working=None):
        stamp=datetime.fromisoformat(day+'T'+clock).replace(tzinfo=VN_TZ)
        return market_phase(stamp,working_dates=working,exchange='VN30')[0]
    assert phase('2026-10-27','08:44')=='CLOSED'
    assert phase('2026-10-27','08:45')=='ATO'
    assert phase('2026-10-27','11:30')=='LUNCH'
    assert phase('2026-10-27','13:00')=='OPEN'
    assert phase('2026-10-27','14:30')=='ATC'
    assert phase('2026-10-27','14:45')=='CLOSED'
    assert phase('2026-10-31','09:30')=='WEEKEND'
    assert phase('2026-10-27','09:30',['2026-10-28'])=='HOLIDAY'
    assert phase('2026-10-28','09:30',['2026-10-28'])=='OPEN'


def candles():
    rows = []
    day = NOW.date() - timedelta(days=420)
    while day < NOW.date():
        if day.weekday() < 5:
            rows.append({"time": datetime.combine(day, datetime.min.time(), VN_TZ).timestamp(),
                         "open": 2000., "high": 2002., "low": 1998., "close": 2000.,
                         "volume": 1000., "closed": True})
        day += timedelta(days=1)
    return rows[-260:]


class History:
    def get_ohlc(self, symbol, resolution, start, end):
        stamps = [int(start) // 60 * 60, int(start) // 60 * 60 + 60]
        return {"s": "ok", "t": stamps, "o": [1990, 2002], "h": [1990, 2002],
                "l": [1990, 2002], "c": [1990, 2002], "v": [10, 10]}


@pytest.fixture
def analysis(tmp_path):
    store = Store(tmp_path / "signals.sqlite")
    service = SignalAnalysis(store, History())
    yield service, store
    store.close()


def payload(price, now=NOW, symbol="41I1G6000"):
    return {"contract": symbol, "quotes": {symbol: {"last": price, "at": now.timestamp()}},
            "bars": candles(), "orders": [], "positions": []}


def config(**params):
    return Settings(signals=SignalSettings(**params).to_dict())


def test_ma200_is_contract_price_only_and_missing_is_not_zero():
    rows = [{"close": 2000}] * 200
    assert p1_snapshot(rows, 2001)["state"] == "ABOVE"
    assert p1_snapshot(rows, 1999)["state"] == "BELOW"
    assert p1_snapshot(rows, 2000)["state"] == "EQUAL"
    assert p1_snapshot(rows[:199], 2000)["ma"] is None
    assert p1_snapshot(rows, 2001, fresh=False)["state"] == "STALE"


def test_va_waits_for_live_cross_and_persists_fill_consumption(analysis):
    service, store = analysis
    settings = config()
    first = service.observe(payload(1990), settings, now=NOW)["p2"]
    assert not first["buy_alert"]
    when = NOW + timedelta(seconds=1)
    up = service.observe(payload(2002, when), settings, now=when)["p2"]
    assert up["memory"]["valid"] and up["buy_alert"]
    cross_id = up["memory"]["cross_id"]
    assert store.orders() == [] and store.positions() == []
    filled = payload(2002, when + timedelta(seconds=1))
    filled["orders"] = [{"id": "one-fill", "symbol": filled["contract"], "side": "LONG", "action": "OPEN",
                         "filled": 1, "updated_at": when.timestamp()}]
    used = service.observe(filled, settings, now=when + timedelta(seconds=1))["p2"]
    assert used["memory"]["used"] and not used["buy_alert"]
    restarted = SignalAnalysis(store, History())
    replay = restarted.observe(payload(2003, when + timedelta(seconds=2)), settings, now=when + timedelta(seconds=2))["p2"]
    assert replay["memory"]["cross_id"] == cross_id and replay["memory"]["used"]
    assert store.orders() == []


@pytest.mark.parametrize("mode,lookback,expected", [("VA", False, False), ("VA", True, True), ("SESSIONS", False, True)])
def test_historical_display_does_not_grant_va_permission(analysis, mode, lookback, expected):
    service, _ = analysis
    value = service.observe(payload(2005), config(buy_ema_cross_mode=mode, buy_ema_va_lookback_enabled=lookback), now=NOW)["p2"]
    assert value["xp"]["ready"] and value["xp"]["up"] >= 1
    assert bool(value["memory"]["valid"]) is expected
    assert bool(value["buy_alert"]) is expected


def test_history_failure_is_unknown_and_does_not_break_live_va(analysis):
    service, _ = analysis
    service.cache.client = NoHistory()
    service.observe(payload(1990), config(), now=NOW)
    when = NOW + timedelta(seconds=1)
    value = service.observe(payload(2002, when), config(), now=when)["p2"]
    assert value["buy_alert"] and value["xp"]["up"] is None and not value["xp"]["ready"]


def test_closed_mode_does_not_use_intraday_price_for_indicators(analysis):
    service, _ = analysis
    settings = config(signal_mode="CLOSED", buy_signal_require_ema_cross=False, buy_signal_use_rsi=False)
    value = service.observe(payload(2200), settings, now=NOW)
    assert value["p2"]["indicators"]["buy_ema_fast"] == 2000
    assert value["p1"]["state"] == "ABOVE"


@pytest.mark.parametrize('hour,minute', [(10, 0), (15, 0)])
def test_backend_ma200_matches_preview_previous_completed_daily_candles(analysis, hour, minute):
    service, _ = analysis
    when = NOW.replace(hour=hour, minute=minute)
    data = payload(2300, now=when)
    data['bars'].append({'time': when.replace(hour=0, minute=0).timestamp(),
        'open': 2100, 'high': 2500, 'low': 2000, 'close': 2400, 'closed': hour >= 15})
    result = service.observe(data, config(), now=when)
    assert result['p1']['ma'] == 2000 and result['p1']['state'] == 'ABOVE'
    # A new current-day candle cannot replace the missing 200th completed day.
    data['bars'] = data['bars'][-200:]
    result = service.observe(data, config(), now=when)
    assert result['p1']['ma'] is None and result['p1']['samples'] == 199


def test_minute_interval_uses_completed_bucket_and_keeps_live_memory(analysis):
    service, _ = analysis
    settings = config(realtime_indicator_interval="1M")
    first = service.observe(payload(1990), settings, now=NOW)["p2"]
    assert "CHỜ ĐÓNG NHỊP" in first["status"]
    when = NOW + timedelta(minutes=1)
    below = service.observe(payload(2002, when), settings, now=when)["p2"]
    assert below["indicators"]["buy_ema_fast"] < 2000
    when += timedelta(minutes=1)
    above = service.observe(payload(2003, when), settings, now=when)["p2"]
    assert above["indicators"]["buy_ema_fast"] == 2001
    assert above["memory"]["valid"] and above["buy_alert"]


def test_volume_gate_and_max_contracts_are_analysis_only(analysis):
    service, store = analysis
    settings = config(buy_signal_require_ema_cross=False, buy_signal_use_rsi=False, buy_volume_enabled=True)
    value = service.observe(payload(2002), settings, now=NOW)["p2"]
    assert not value["buy_alert"] and "VOLUME" in value["status"]
    settings = replace(config(buy_signal_require_ema_cross=False, buy_signal_use_rsi=False), max_contracts=1)
    data = payload(2002, NOW + timedelta(seconds=1))
    data["positions"] = [{"quantity": 1}]
    value = service.observe(data, settings, now=NOW + timedelta(seconds=1))["p2"]
    assert value["badge"] == "USED" and not value["buy_alert"]
    assert not store.orders()


def test_time_filter_waits_and_confirmation_excludes_lunch(analysis):
    service, _ = analysis
    params = SignalSettings(buy_window_enabled=True, buy_window_start="14:00")
    marks = {"buy_ema_fast": 2001, "buy_ema_slow": 2000, "rsi": 60, "rsi_previous": 50}
    ready, status, _ = service._filters("VN30F1M", True, marks, params, NOW, None)
    assert not ready and "14:00" in status
    at = NOW.replace(hour=14)
    ready, _, _ = service._filters("VN30F1M", False, marks, params, at, None)
    assert ready
    start, end = NOW.replace(hour=11, minute=29), NOW.replace(hour=13, minute=2)
    assert active_trading_minutes(start, end, "VN30") == 3
    params = SignalSettings(buy_confirmation_enabled=True, buy_confirmation_minutes=2)
    assert not service._filters("other", True, marks, params, NOW, None)[0]
    # Keep observations alive: unobserved downtime must not count as a hold.
    for seconds in range(10, 121, 10):
        result = service._filters("other", True, marks, params, NOW + timedelta(seconds=seconds), None)
    assert result[0]


def test_signal_reader_rejects_mutations_before_network():
    reader = ReadOnlyHistory("key", "secret", "123")
    try:
        for method in ("POST", "PUT", "DELETE"):
            with pytest.raises(Exception, match="chỉ cho phép GET"):
                reader.request(method, "/orders")
    finally:
        reader.close()


def test_settings_reject_invalid_cross_and_losing_confirmation_conditions():
    with pytest.raises(ValueError):
        config(buy_ema_fast=6, buy_ema_slow=3).validate()
    with pytest.raises(ValueError):
        config(buy_confirmation_enabled=True, buy_confirmation_require_ema=False, buy_confirmation_require_rsi=False).validate()


def test_ema_badge_is_independent_of_filters_and_refresh_keeps_used_id(analysis):
    service, store = analysis
    settings = config(buy_signal_require_ema_cross=False, buy_window_enabled=True, buy_volume_enabled=True)
    value = service.observe(payload(2005), settings, now=NOW)["p2"]
    assert value["badge"] == "READY" and not value["buy_alert"]
    service.observe(payload(1990, NOW + timedelta(seconds=1)), config(), now=NOW + timedelta(seconds=1))
    when = NOW + timedelta(seconds=2)
    value = service.observe(payload(2005, when), config(), now=when)["p2"]
    data = payload(2005, when + timedelta(seconds=1))
    data["orders"] = [{"id": "filled", "symbol": data["contract"], "side": "LONG", "action": "OPEN", "filled": 1, "updated_at": when.timestamp()}]
    before = service.observe(data, config(), now=when + timedelta(seconds=1))["p2"]["memory"]
    service.refresh()
    after = service.state.session_cross(data["contract"], "PAPER")
    assert before["cross_id"] == after["cross_id"] and after["used"]


def test_stale_quotes_cannot_accumulate_confirmation_time(analysis):
    service, store = analysis
    settings = config(buy_signal_require_ema_cross=False, buy_confirmation_enabled=True)
    service.observe(payload(2005), settings, now=NOW)
    assert store.get("analysis", "filter:41I1G6000")["confirmation"]
    value = service.observe(payload(2005), settings, now=NOW + timedelta(seconds=15))["p2"]
    assert not value["buy_alert"]
    assert store.get("analysis", "filter:41I1G6000") == {}


def test_slow_analysis_does_not_hold_execution_and_shutdown_releases_ledger(system, monkeypatch):
    import threading
    from ckps.services.signal_worker import SignalWorker
    engine, broker, store = system
    started, release = threading.Event(), threading.Event()
    def blocked_analysis(*args, **kwargs):
        started.set()
        assert release.wait(timeout=3)
        return {"p2": {"status": "READY"}}
    monkeypatch.setattr(SignalAnalysis, "observe", blocked_analysis)
    worker = SignalWorker(store.path)
    try:
        worker.update(payload(2000), asdict(engine.settings))
        assert started.wait(timeout=2)
        engine.open_manual("LONG", 1, "MOK")
        engine.poll()
        assert store.positions()[0].quantity == 1
    finally:
        release.set()
        worker.close()
    assert not worker.thread.is_alive()


def test_signal_history_survives_restart_and_records_only_new_conditions(analysis):
    service, store = analysis
    settings = config(buy_signal_require_ema_cross=False, buy_signal_use_rsi=False)
    service.observe(payload(2005), settings, now=NOW)
    service.observe(payload(2006, NOW + timedelta(seconds=1)), settings, now=NOW + timedelta(seconds=1))
    restarted = SignalAnalysis(store, History())
    restarted.observe(payload(2007, NOW + timedelta(seconds=2)), settings, now=NOW + timedelta(seconds=2))
    assert len([r for r in restarted.signal_history() if r["kind"] == "BUY"]) == 1
    restarted.observe(payload(1990, NOW + timedelta(seconds=3)), settings, now=NOW + timedelta(seconds=3))
    restarted.observe(payload(2008, NOW + timedelta(seconds=4)), settings, now=NOW + timedelta(seconds=4))
    history = restarted.signal_history()
    assert len([r for r in history if r["kind"] == "BUY"]) == 2
    assert any(r["kind"] == "E" for r in history)
    assert any(r["kind"].startswith("CẮT") for r in history)
    assert store.orders() == [] and store.positions() == []


def test_dashboard_atr_uses_execution_completed_candles(system):
    from queue import Queue
    from types import SimpleNamespace
    from ckps.services.runtime import Runtime
    engine, broker, store=system
    runtime=Runtime.__new__(Runtime)
    from ckps.services.quote_cache import QuoteCache
    runtime.quote_cache=QuoteCache()
    runtime.engine,runtime.store,runtime.settings=engine,store,engine.settings
    runtime.events=Queue()
    runtime.telegram_error=''
    runtime.analysis=SimpleNamespace(update=lambda *a:None,snapshot=lambda:{})
    runtime._publish()
    assert runtime.events.get()[1]['atr14_pct'] is None
    from ckps.rules.p2.market import VN_TZ
    from datetime import datetime, timedelta
    today=datetime.now(VN_TZ).date()
    engine.latest.bars=[{'time':(today-timedelta(days=30-i)).isoformat(),
        'open':2000,'high':2010,'low':1990,'close':2000,'closed':True} for i in range(20)]
    # A live candle's extreme must not change the completed daily ATR.
    engine.latest.bars.append({'time':today.isoformat(),'high':2300,'low':1700,'close':2100,'closed':False})
    runtime._publish()
    assert runtime.events.get()[1]['atr14_pct']==engine._atr(engine.latest.contract)==1.0
    assert store.orders()==[]


def test_toggling_alerts_keeps_analysis_and_confirmation_running(analysis):
    service, store=analysis
    settings=config(buy_signal_require_ema_cross=False,buy_signal_use_rsi=False,
                    buy_confirmation_enabled=True,buy_confirmation_require_rsi=False)
    before=service.observe(payload(2005),settings,now=NOW)
    started=store.get('analysis','filter:41I1G6000')['confirmation']['started_at']
    settings.signals.update(buy_alert_enabled=True,sell_alert_enabled=True)
    later=NOW+timedelta(seconds=1)
    after=service.observe(payload(2006,later),settings,now=later)
    assert store.get('analysis','filter:41I1G6000')['confirmation']['started_at']==started
    assert before['p2']['indicators'] and after['p2']['indicators']
    assert not after['p2']['buy_alert']  # Confirmation has not completed.
    settings.signals.update(buy_alert_enabled=False,sell_alert_enabled=False)
    later=NOW+timedelta(seconds=2)
    assert service.observe(payload(2007,later),settings,now=later)['p2']['indicators']
    assert store.orders()==[] and store.positions()==[]
