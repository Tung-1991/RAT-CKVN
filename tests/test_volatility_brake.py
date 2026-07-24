from types import SimpleNamespace
import time

from core import storage_manager
from core.checklist_manager import ChecklistManager
from core.volatility_brake import VolatilityBrakeDetector
from ai_advisor import scan_report


def _settings(**overrides):
    data = {
        "VOLATILITY_BRAKE_ENABLED": True,
        "VOLATILITY_BRAKE_WINDOW_SECONDS": 60,
        "VOLATILITY_BRAKE_STOCK_PCT": 1.5,
        "VOLATILITY_BRAKE_DERIVATIVE_POINTS": 5,
        "VOLATILITY_BRAKE_CONFIRMATIONS": 2,
    }
    data.update(overrides)
    return data


def test_stock_brake_triggers_after_two_confirmations():
    detector = VolatilityBrakeDetector()
    assert detector.observe("AAA", 100.0, _settings(), timestamp=1000) is None
    assert detector.observe("AAA", 98.4, _settings(), timestamp=1030) is None
    event = detector.observe("AAA", 98.3, _settings(), timestamp=1031)

    assert event["event"] == "VOLATILITY_BRAKE"
    assert event["symbol"] == "AAA"
    assert event["direction"] == "DOWN"
    assert event["threshold_unit"] == "PERCENT"


def test_derivative_brake_uses_points_and_ignores_stale_tick():
    detector = VolatilityBrakeDetector()
    cfg = _settings(VOLATILITY_BRAKE_CONFIRMATIONS=1)
    assert detector.observe("VN30F1M", 1900.0, cfg, timestamp=1000) is None
    assert (
        detector.observe(
            "VN30F1M", 1890.0, cfg, timestamp=1030, freshness="STALE"
        )
        is None
    )
    event = detector.observe("VN30F1M", 1894.0, cfg, timestamp=1031)

    assert event["threshold_unit"] == "POINTS"
    assert event["change_points"] == -6.0


class _Connector:
    _is_connected = True
    last_latency_ms = 0.0

    def __init__(self):
        self.positions = [
            SimpleNamespace(symbol="AAA", comment="[BOT]", magic=0, type=0),
            SimpleNamespace(symbol="POW", comment="[BOT]", magic=0, type=0),
            SimpleNamespace(symbol="MBS", comment="[BOT]", magic=0, type=0),
        ]

    def get_all_open_positions(self):
        return list(self.positions)


def _state():
    state = {
        "date": storage_manager.get_today_str(),
        "starting_balance": 100_000_000,
        "bot_pnl_today": 0,
        "bot_trades_today": 0,
        "bot_daily_loss_count": 0,
    }
    storage_manager.apply_state_defaults(state)
    return state


def _safeguard():
    return {
        "MAX_DAILY_LOSS_PERCENT": 2.5,
        "MAX_OPEN_POSITIONS": 3,
        "MAX_TRADES_PER_DAY": 30,
        "MAX_LOSING_STREAK": 3,
        "MAX_POS_PER_SYMBOL": 1,
        "CHECK_PING": False,
        "CHECK_SPREAD": False,
        "COOLDOWN_MINUTES": 0,
    }


def test_priority_bypasses_only_total_open_position_limit(monkeypatch):
    monkeypatch.setattr(
        "core.checklist_manager.is_symbol_trade_window_open",
        lambda _symbol: (True, ""),
    )
    manager = ChecklistManager(_Connector())

    normal = manager.run_bot_safeguard_checks(
        {"balance": 100_000_000},
        _state(),
        "FPT",
        _safeguard(),
        "ENTRY",
        "BUY",
        priority_symbol=False,
    )
    priority = manager.run_bot_safeguard_checks(
        {"balance": 100_000_000},
        _state(),
        "FPT",
        _safeguard(),
        "ENTRY",
        "BUY",
        priority_symbol=True,
    )

    assert not normal["passed"]
    assert priority["passed"]
    assert any(item["name"] == "Priority" for item in priority["checks"])


def test_priority_does_not_bypass_global_cooldown(monkeypatch):
    monkeypatch.setattr(
        "core.checklist_manager.is_symbol_trade_window_open",
        lambda _symbol: (True, ""),
    )
    state = _state()
    state["cooldown_until"] = time.time() + 300

    result = ChecklistManager(_Connector()).run_bot_safeguard_checks(
        {"balance": 100_000_000},
        state,
        "FPT",
        _safeguard(),
        "ENTRY",
        "BUY",
        priority_symbol=True,
    )

    assert not result["passed"]
    assert result["checks"][0]["name"] == "Global Cooldown"


def test_md_event_only_updates_existing_reports(monkeypatch, tmp_path):
    manual = tmp_path / "scan_report.md"
    morning = tmp_path / "scan_report_morning.md"
    afternoon = tmp_path / "scan_report_afternoon.md"
    morning.write_text("# Morning\n", encoding="utf-8")
    monkeypatch.setattr(scan_report.paths, "scan_report_path", lambda: str(manual))
    monkeypatch.setattr(
        scan_report.paths,
        "scan_session_report_path",
        lambda session: str(morning if session == "morning" else afternoon),
    )
    event = {
        "symbol": "AAA",
        "direction": "DOWN",
        "change_pct": -2.0,
        "threshold_unit": "PERCENT",
        "window_seconds": 60,
        "triggered_at": 1000,
        "closed_positions": 1,
        "failed_positions": 0,
        "cooldown_hours": 4,
    }

    updated = scan_report.append_volatility_event_to_existing_reports(event)

    assert updated == [str(morning)]
    assert "PHANH BIẾN ĐỘNG" in morning.read_text(encoding="utf-8")
    assert not manual.exists()
    assert not afternoon.exists()
