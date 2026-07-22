# -*- coding: utf-8 -*-
import ast
import concurrent.futures
import io
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot_daemon
import config
import main
from core import market_hours


class _Var:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Widget:
    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)


def _manual_mode_app():
    calls = []
    app = SimpleNamespace(
        cbo_symbol=_Var("VN30F1M"),
        var_manual_trade_mode=_Var("NORMAL"),
        var_preview_trade_after_apply=_Var(True),
        chk_preview_trade_after_apply=_Widget(),
        log_message=lambda *args, **kwargs: calls.append((args, kwargs)),
        refresh_limit_order_hint=lambda: calls.append("hint"),
        refresh_manual_preview_tab=lambda: calls.append("preview"),
    )
    return app, calls


def test_botui_has_no_duplicate_method_definitions():
    tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    bot_ui = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "BotUI")
    names = [node.name for node in bot_ui.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert duplicates == []


def test_bootstrap_without_dnse_builds_ui_without_network(monkeypatch):
    app = main.BotUI.__new__(main.BotUI)
    app.connector = SimpleNamespace(
        api_key="",
        api_secret="",
        account_no="",
        connect=lambda: pytest.fail("bootstrap must not connect before UI"),
        get_account_info=lambda: pytest.fail("bootstrap must not call DNSE before UI"),
    )
    initialized = []
    logs = []
    app._finish_init = lambda account: initialized.append(account)
    app.log_message = lambda *args, **kwargs: logs.append((args, kwargs))
    monkeypatch.setattr(main.config, "PAPER_TRADING", True)
    monkeypatch.setattr(main.config, "PAPER_INITIAL_BALANCE", 100000000.0)

    main.BotUI._bootstrap_connection(app)

    assert initialized[0]["login"] == "PAPER"
    assert initialized[0]["server"] == "DNSE_NOT_CONFIGURED"
    assert initialized[0]["balance"] == 100000000.0
    assert any("Advanced" in item[0][0] for item in logs)


def test_manual_ato_is_rejected_outside_ato_session(monkeypatch):
    app, calls = _manual_mode_app()
    monkeypatch.setattr(market_hours, "market_session_phase", lambda _symbol: ("OPEN", "Mở"))

    main.BotUI.on_manual_trade_mode_change(app, "ATO")

    assert app.var_manual_trade_mode.get() == "NORMAL"
    assert app.chk_preview_trade_after_apply.options["state"] == "normal"
    assert any(isinstance(item, tuple) and "ATO" in item[0][0] for item in calls)
    assert calls[-2:] == ["hint", "preview"]


def test_manual_atc_is_kept_during_atc_session(monkeypatch):
    app, calls = _manual_mode_app()
    monkeypatch.setattr(market_hours, "market_session_phase", lambda _symbol: ("ATC", "ATC"))

    main.BotUI.on_manual_trade_mode_change(app, "ATC")

    assert app.var_manual_trade_mode.get() == "ATC"
    assert app.var_preview_trade_after_apply.get() is False
    assert app.chk_preview_trade_after_apply.options["state"] == "disabled"
    assert calls == ["hint", "preview"]


def test_save_brain_live_config_preserves_unmanaged_sections(monkeypatch):
    source = {"indicators": {"rsi": {"active": True}}, "custom": "keep"}
    saved = []
    monkeypatch.setattr(main, "load_brain_settings", lambda: dict(source))
    monkeypatch.setattr(main, "save_brain_settings", lambda payload: saved.append(payload))
    monkeypatch.setattr(main.config, "AUTO_TRADE_ENABLED", True)
    app = SimpleNamespace(log_message=lambda *args, **kwargs: None)

    main.BotUI._save_brain_live_config(app)

    assert len(saved) == 1
    assert saved[0]["indicators"] == source["indicators"]
    assert saved[0]["custom"] == "keep"
    assert saved[0]["AUTO_TRADE_ENABLED"] is True


def test_startup_disarms_ui_config_and_persisted_daemon_flag(monkeypatch):
    saved = []
    monkeypatch.setattr(main.config, "AUTO_TRADE_ENABLED", True)

    class Var:
        def __init__(self, value=True):
            self.value = value

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    app = SimpleNamespace(
        var_auto_trade=Var(),
        var_bot_ckps=Var(),
        var_bot_ckcs=Var(),
        _save_brain_live_config=lambda: saved.append(main.config.AUTO_TRADE_ENABLED),
    )

    main.BotUI._disarm_auto_trade_on_startup(app)

    assert app.var_auto_trade.get() is False
    assert app.var_bot_ckps.get() is False
    assert app.var_bot_ckcs.get() is False
    assert main.config.AUTO_TRADE_ENABLED is False
    assert saved == [False]


def test_market_now_keeps_naive_offset_contract_without_utcnow_warning(monkeypatch):
    monkeypatch.setattr(market_hours.config, "MARKET_HOURS_UTC_OFFSET", 7)
    now = market_hours._market_now()
    assert now.tzinfo is None
    assert 0 <= now.hour <= 23


def test_log_reader_handles_append_and_rotation(tmp_path):
    path = tmp_path / "daemon.log"
    path.write_text("old\n", encoding="utf-8")
    offsets = {}

    assert main._read_appended_lines(str(path), offsets) == []
    with path.open("a", encoding="utf-8") as handle:
        handle.write("new-1\nnew-2\n")
    assert main._read_appended_lines(str(path), offsets) == ["new-1\n", "new-2\n"]

    path.write_text("rotated\n", encoding="utf-8")
    assert main._read_appended_lines(str(path), offsets) == ["rotated\n"]

    replacement = tmp_path / "replacement.log"
    replacement.write_text("replacement-is-longer-than-the-old-offset\n", encoding="utf-8")
    replacement.replace(path)
    assert main._read_appended_lines(str(path), offsets) == [
        "replacement-is-longer-than-the-old-offset\n"
    ]


def test_daemon_start_is_idempotent_and_shutdown_is_clean(monkeypatch):
    popen_calls = []
    handle = io.StringIO()

    class _Process:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

    process = _Process()
    monkeypatch.setattr(main.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "open", lambda *args, **kwargs: handle, raising=False)
    monkeypatch.setattr(main.subprocess, "Popen", lambda *args, **kwargs: popen_calls.append((args, kwargs)) or process)
    app = SimpleNamespace(
        daemon_process=None,
        daemon_output_file=None,
        running=True,
        log_message=lambda *args, **kwargs: None,
        destroy=lambda: None,
    )

    main.BotUI.start_daemon_process(app)
    main.BotUI.start_daemon_process(app)
    assert len(popen_calls) == 1

    with pytest.raises(SystemExit) as exc:
        main.BotUI.on_closing(app)
    assert exc.value.code == 0
    assert process.terminated is True
    assert handle.closed is True


def _daemon_stub():
    daemon = bot_daemon.StandaloneBotDaemon.__new__(bot_daemon.StandaloneBotDaemon)
    daemon.running = True
    daemon.pending_signals = [{"signal_id": "one"}]
    daemon.heartbeat_contexts = {"FPT": {"current_price": 100.0}}
    daemon._active_symbols = ["FPT"]
    return daemon


def test_atomic_signal_write_retries_file_contention(monkeypatch, tmp_path):
    target = tmp_path / "live_signals.json"
    temp = tmp_path / "live_signals.json.tmp"
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE", str(target))
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE_TMP", str(temp))
    real_replace = bot_daemon.os.replace
    attempts = []

    def flaky_replace(src, dst):
        attempts.append((src, dst))
        if len(attempts) < 4:
            raise PermissionError("reader holds file")
        real_replace(src, dst)

    monkeypatch.setattr(bot_daemon.os, "replace", flaky_replace)
    monkeypatch.setattr(bot_daemon.time, "sleep", lambda _seconds: None)

    _daemon_stub()._atomic_write_signals(["FPT"])

    assert len(attempts) == 4
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["brain_heartbeat"]["active_symbols"] == ["FPT"]
    assert payload["pending_signals"] == [{"signal_id": "one"}]


def test_signal_writer_falls_back_when_windows_blocks_replace(monkeypatch, tmp_path):
    target = tmp_path / "live_signals.json"
    target.write_text('{"old": true}', encoding="utf-8")
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE", str(target))
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE_TMP", str(target) + ".tmp")
    monkeypatch.setattr(
        bot_daemon.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(PermissionError("sharing violation")),
    )
    monkeypatch.setattr(bot_daemon.time, "sleep", lambda _seconds: None)

    daemon = _daemon_stub()
    assert daemon._atomic_write_signals(["FPT"]) is True

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["brain_heartbeat"]["active_symbols"] == ["FPT"]
    assert payload["pending_signals"] == [{"signal_id": "one"}]
    assert daemon.signal_write_fault is None


def test_daemon_startup_replaces_stale_invalid_signal_file(monkeypatch, tmp_path):
    target = tmp_path / "live_signals.json"
    target.write_text('{"broken":', encoding="utf-8")
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE", str(target))
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE_TMP", str(target) + ".tmp")

    class Connector:
        def connect(self):
            return True

        def get_account_info(self):
            return None

    monkeypatch.setattr(bot_daemon, "DNSEConnector", Connector)
    daemon = bot_daemon.StandaloneBotDaemon()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["brain_heartbeat"]["status"] == "HEALTHY"
    assert payload["brain_heartbeat"]["active_symbols"] == daemon._active_symbols
    assert payload["pending_signals"] == []


def test_daemon_startup_preserves_last_preview_context_but_clears_old_signals(monkeypatch, tmp_path):
    target = tmp_path / "live_signals.json"
    target.write_text(
        json.dumps(
            {
                "brain_heartbeat": {
                    "status": "HEALTHY",
                    "active_symbols": ["AAA"],
                    "contexts": {"AAA": {"current_price": 7.15, "atr_G2": 0.08}},
                },
                "pending_signals": [{"signal_id": "stale-order"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE", str(target))
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE_TMP", str(target) + ".tmp")

    class Connector:
        def connect(self):
            return True

        def get_account_info(self):
            return None

    monkeypatch.setattr(bot_daemon, "DNSEConnector", Connector)
    daemon = bot_daemon.StandaloneBotDaemon()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert daemon.heartbeat_contexts["AAA"]["current_price"] == 7.15
    assert payload["brain_heartbeat"]["contexts"]["AAA"]["atr_G2"] == 0.08
    assert payload["pending_signals"] == []


def test_daemon_restores_preview_price_from_scan_cache_when_heartbeat_is_empty(monkeypatch, tmp_path):
    target = tmp_path / "live_signals.json"
    target.write_text(
        json.dumps({"brain_heartbeat": {"active_symbols": [], "contexts": {}}, "pending_signals": []}),
        encoding="utf-8",
    )
    (tmp_path / "scan_snapshot_cache.json").write_text(
        json.dumps(
            {
                "symbols": {
                    "AAA": {
                        "days": {
                            "2026-07-20": {
                                "price": {"current": 7.15},
                                "bot": {"trend_G0": "DOWN", "market_mode": "TREND"},
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE", str(target))
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE_TMP", str(target) + ".tmp")

    class Connector:
        def connect(self):
            return True

        def get_account_info(self):
            return None

    monkeypatch.setattr(bot_daemon, "DNSEConnector", Connector)
    daemon = bot_daemon.StandaloneBotDaemon()

    assert daemon.heartbeat_contexts["AAA"]["current_price"] == 7.15
    assert daemon.heartbeat_contexts["AAA"]["synthetic_quote"] is True
    assert daemon.heartbeat_contexts["AAA"]["market_mode"] == "TREND"


def test_raw_only_symbol_is_scanned_but_cannot_emit_bot_signal(monkeypatch):
    from ai_advisor.scan_cache import recorder

    daemon = bot_daemon.StandaloneBotDaemon.__new__(bot_daemon.StandaloneBotDaemon)
    daemon.running = True
    daemon.heartbeat_contexts = {}
    daemon._scan_snapshot_enabled = True
    emitted = []
    recorded = []
    daemon._add_signal = lambda *args, **kwargs: emitted.append((args, kwargs))
    daemon._write_signal_debugger = lambda state: None
    monkeypatch.setattr(bot_daemon, "is_symbol_trade_window_open", lambda symbol: (True, "OPEN"))
    monkeypatch.setattr(
        bot_daemon.data_engine,
        "fetch_data_v4",
        lambda symbol: ({"G0": object()}, {"current_price": 10.0}),
    )
    monkeypatch.setattr(bot_daemon.signal_generator, "generate_signal_v4", lambda *args, **kwargs: 1)
    monkeypatch.setattr(recorder, "maybe_record", lambda symbol, *args, **kwargs: recorded.append(symbol))
    monkeypatch.setattr(recorder, "flush", lambda: None)

    daemon._scan_signals(
        ["HPG"],
        bot_active=True,
        trade_symbols=[],
        raw_symbols=["HPG"],
    )

    assert recorded == ["HPG"]
    assert emitted == []
    assert daemon.heartbeat_contexts["HPG"]["current_price"] == 10.0


def test_atomic_signal_writes_are_serialized_and_use_unique_temp_files(monkeypatch, tmp_path):
    target = tmp_path / "live_signals.json"
    temp = tmp_path / "live_signals.json.tmp"
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE", str(target))
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE_TMP", str(temp))
    real_replace = bot_daemon.os.replace
    state_lock = threading.Lock()
    active_writers = 0
    max_active_writers = 0
    temp_paths = []

    def observed_replace(src, dst):
        nonlocal active_writers, max_active_writers
        with state_lock:
            active_writers += 1
            max_active_writers = max(max_active_writers, active_writers)
            temp_paths.append(src)
        time.sleep(0.002)
        try:
            real_replace(src, dst)
        finally:
            with state_lock:
                active_writers -= 1

    monkeypatch.setattr(bot_daemon.os, "replace", observed_replace)
    daemon = _daemon_stub()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: daemon._atomic_write_signals(["FPT"]), range(40)))

    assert all(results)
    assert max_active_writers == 1
    assert len(temp_paths) == 40
    assert len(set(temp_paths)) == 40
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["brain_heartbeat"]["active_symbols"] == ["FPT"]
    assert payload["pending_signals"] == [{"signal_id": "one"}]


def test_concurrent_signal_adds_leave_latest_queue_fully_written(monkeypatch, tmp_path):
    target = tmp_path / "live_signals.json"
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE", str(target))
    monkeypatch.setattr(bot_daemon, "SIGNAL_FILE_TMP", str(target) + ".tmp")
    daemon = _daemon_stub()
    daemon.pending_signals = []
    daemon.last_entry_signal_times = {}
    daemon._entry_signal_on_cooldown = lambda *_args: False
    daemon._read_live_config = lambda: {"BOT_ACTIVE_SYMBOLS": ["FPT"]}

    def add(index):
        return daemon._add_signal(
            "BUY" if index % 2 == 0 else "SELL",
            "FPT",
            {"market_mode": "TEST", "index": index},
            "DCA",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(add, range(40)))

    assert all(results)
    assert len(daemon.pending_signals) == 40
    assert len({item["signal_id"] for item in daemon.pending_signals}) == 40
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["pending_signals"] == daemon.pending_signals[-10:]


def test_tick_loop_does_not_call_market_data_when_closed(monkeypatch):
    daemon = _daemon_stub()
    daemon._tick_symbols = lambda: ["VN30F1M"]
    sleeps = []
    monkeypatch.setattr(bot_daemon, "is_symbol_trade_window_open", lambda _symbol: (False, "closed"))
    monkeypatch.setattr(
        bot_daemon.data_engine,
        "fetch_realtime_tick",
        lambda _symbol: pytest.fail("market data must not be called while closed"),
    )

    def stop_after_idle(seconds):
        sleeps.append(seconds)
        daemon.running = False

    monkeypatch.setattr(bot_daemon.time, "sleep", stop_after_idle)
    daemon._tick_update_loop()

    assert sleeps == [30.0]


@pytest.mark.parametrize(
    ("kind", "price_current", "stop", "context", "expected_class"),
    [
        ("DCA", 98.0, 99.0, {"current_price": 98.0, "atr_G2": 1.0, "latest_signal": 1}, "DCA"),
        ("PCA", 102.0, 101.0, {"current_price": 102.0, "atr_G2": 1.0, "latest_signal": 1}, "PCA"),
    ],
)
def test_daemon_dca_pca_emits_only_eligible_scale_signal(
    monkeypatch, kind, price_current, stop, context, expected_class
):
    import core.storage_manager as storage_manager

    position = SimpleNamespace(
        symbol="FPT",
        ticket=1,
        type=0,
        price_open=100.0,
        price_current=price_current,
        sl=stop,
        time=1.0,
        comment="[BOT]_ENTRY",
        magic=1,
    )
    daemon = _daemon_stub()
    daemon.connector = SimpleNamespace(get_positions=lambda: [position])
    daemon.heartbeat_contexts = {"FPT": context}
    emitted = []
    daemon._add_signal = lambda action, symbol, ctx, signal_class: emitted.append(
        (action, symbol, signal_class)
    )
    dca_enabled = kind == "DCA"
    pca_enabled = kind == "PCA"
    brain = {
        "risk_tsl": {"base_sl": "G2"},
        "dca_config": {
            "ENABLED": dca_enabled,
            "MAX_STEPS": 3,
            "DISTANCE_ATR_R": 1.0,
            "COOLDOWN": 0,
            "MINI_BRAIN": {"active": False},
        },
        "pca_config": {
            "ENABLED": pca_enabled,
            "MAX_STEPS": 3,
            "DISTANCE_ATR_R": 1.5,
            "COOLDOWN": 0,
            "MINI_BRAIN": {"active": False},
        },
    }
    monkeypatch.setattr(bot_daemon, "is_bot_position", lambda _pos, _magics: True)
    monkeypatch.setattr(bot_daemon, "get_brain_settings_for_symbol", lambda _symbol: brain)
    monkeypatch.setattr(storage_manager, "get_magic_numbers", lambda: {1})
    monkeypatch.setattr(storage_manager, "load_state", lambda: {"trade_tactics": {}})
    monkeypatch.setattr(storage_manager, "get_last_dca_pca_close_time", lambda _symbol: 0)
    monkeypatch.setattr(storage_manager, "get_last_dca_pca_signal_time", lambda _symbol, _kind=None: 0)
    monkeypatch.setattr(storage_manager, "update_last_dca_pca_signal_time", lambda *args: None)
    monkeypatch.setattr(bot_daemon.time, "sleep", lambda _seconds: None)

    daemon._scan_dca_pca()

    assert emitted == [("BUY", "FPT", expected_class)]

def test_round_trip_fee_uses_open_and_close_sides():
    app = main.BotUI.__new__(main.BotUI)
    calls = []

    def fee(symbol, price, contracts, side=None):
        calls.append((symbol, price, contracts, side))
        return 10.0 if side == "BUY" else 20.0

    app.calculate_trade_fee = fee

    assert main.BotUI.calculate_round_trip_trade_fee(
        app, "VN30F1M", 1800.0, 1790.0, 2, "BUY"
    ) == 30.0
    assert calls == [
        ("VN30F1M", 1800.0, 2, "BUY"),
        ("VN30F1M", 1790.0, 2, "SELL"),
    ]


def test_stock_price_ui_follows_zero_trim_but_internal_stays_dnse_scale(monkeypatch):
    app = main.BotUI.__new__(main.BotUI)
    app.cbo_symbol = _Var("AAA")

    monkeypatch.setattr(config, "MONEY_DISPLAY_ZERO_TRIM", "000", raising=False)
    assert main.BotUI._fmt_price(app, 7.21, "AAA") == "7.21"
    assert main.BotUI._price_input_to_internal(app, "7.21", "AAA") == 7.21
    assert main.BotUI._price_internal_to_input(app, 7.21, "AAA") == "7.21"

    monkeypatch.setattr(config, "MONEY_DISPLAY_ZERO_TRIM", "NONE", raising=False)
    assert main.BotUI._fmt_price(app, 7.21, "AAA") == "7,210"
    assert main.BotUI._price_input_to_internal(app, "7210", "AAA") == 7.21
    assert main.BotUI._price_internal_to_input(app, 7.21, "AAA") == "7210"

    assert main.BotUI._fmt_price(app, 1800.5, "VN30F1M") == "1800.50"
    assert main.BotUI._price_input_to_internal(app, "1800.5", "VN30F1M") == 1800.5


def test_money_font_auto_shrinks_but_never_below_minimum():
    size = main.BotUI._responsive_money_font_size

    assert size("99,337", 32, 18, 8) == 32
    assert size("99,337,000", 32, 18, 8) < 32
    assert size("PNL: -999,999,999,999,999", 17, 11, 14) == 11


def test_header_pnl_includes_realized_and_open_positions():
    positions = [
        SimpleNamespace(profit=-181862.0, swap=0.0),
        SimpleNamespace(profit=-235252.0, swap=-10.0),
        SimpleNamespace(profit=-243813.0, swap=0.0),
    ]

    total, realized, floating = main.BotUI._combined_display_pnl(50000.0, positions)

    assert realized == 50000.0
    assert floating == -660937.0
    assert total == -610937.0


def test_market_health_startup_recovery_is_not_logged(monkeypatch):
    app = main.BotUI.__new__(main.BotUI)
    app._last_market_health_state = ""
    app._pending_market_health_state = ""
    app._pending_market_health_since = 0.0
    monkeypatch.setattr(config, "DNSE_MARKET_WARNING_GRACE_SECONDS", 5.0, raising=False)

    assert app._market_health_log_event("RECOVERING", now=100.0) is None
    assert app._market_health_log_event("LIVE", now=102.0) is None
    assert app._last_market_health_state == "LIVE"


def test_market_health_persistent_outage_and_recovery_are_logged(monkeypatch):
    app = main.BotUI.__new__(main.BotUI)
    app._last_market_health_state = "LIVE"
    app._pending_market_health_state = ""
    app._pending_market_health_since = 0.0
    monkeypatch.setattr(config, "DNSE_MARKET_WARNING_GRACE_SECONDS", 5.0, raising=False)

    assert app._market_health_log_event("RECOVERING", now=100.0) is None
    event = app._market_health_log_event("RECOVERING", now=106.0)
    assert event and event[1] is True
    recovered = app._market_health_log_event("LIVE", now=107.0)
    assert recovered and recovered[1] is False
