# -*- coding: utf-8 -*-
import ast
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot_daemon
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
