# -*- coding: utf-8 -*-

import config
import main
from core import storage_manager


def test_bot_runtime_state_is_separate_for_paper_and_real(monkeypatch, tmp_path):
    legacy = tmp_path / "bot_state.json"
    monkeypatch.setattr(storage_manager, "STATE_FILE", str(legacy))

    monkeypatch.setattr(config, "PAPER_TRADING", True)
    paper_state = storage_manager.load_state()
    paper_state["pnl_today"] = -123000.0
    paper_state["active_trades"] = ["PAPER-1"]
    storage_manager.save_state(paper_state)

    monkeypatch.setattr(config, "PAPER_TRADING", False)
    real_state = storage_manager.load_state()
    assert real_state["pnl_today"] == 0.0
    assert real_state["active_trades"] == []
    real_state["pnl_today"] = 456000.0
    real_state["active_trades"] = ["REAL-1"]
    storage_manager.save_state(real_state)

    monkeypatch.setattr(config, "PAPER_TRADING", True)
    restored_paper = storage_manager.load_state()
    assert restored_paper["pnl_today"] == -123000.0
    assert restored_paper["active_trades"] == ["PAPER-1"]

    assert (tmp_path / "bot_state.paper.json").exists()
    assert (tmp_path / "bot_state.real.json").exists()


def test_old_state_is_migrated_only_to_matching_mode(monkeypatch, tmp_path):
    import json

    legacy = tmp_path / "bot_state.json"
    legacy.write_text(
        json.dumps({"pnl_today": -62000000.0, "active_trades": ["PAPER-4"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(storage_manager, "STATE_FILE", str(legacy))

    monkeypatch.setattr(config, "PAPER_TRADING", False)
    assert storage_manager.load_state()["pnl_today"] == 0.0

    monkeypatch.setattr(config, "PAPER_TRADING", True)
    migrated = storage_manager.load_state()
    assert migrated["pnl_today"] == 0.0
    assert migrated["state_mode"] == "PAPER"


def test_ui_mode_switch_disarms_bot_and_reloads_matching_state(monkeypatch):
    from types import SimpleNamespace
    from core import env_utils

    monkeypatch.setattr(config, "PAPER_TRADING", True)
    saved_env = []
    monkeypatch.setattr(env_utils, "update_env", lambda values: saved_env.append(values))
    next_state = {"state_mode": "REAL", "pnl_today": 7.0}
    monkeypatch.setattr(main, "load_state", lambda: next_state)

    calls = []
    connector = SimpleNamespace(
        reset_session_caches=lambda: calls.append("reset"),
        connect=lambda: calls.append("connect"),
    )
    app = SimpleNamespace(
        _mode_switching=False,
        connector=connector,
        trade_mgr=SimpleNamespace(state={"state_mode": "PAPER"}),
        tsl_states_map={"PAPER-1": "Running"},
        _ui_all_positions_snapshot=["paper"],
        set_auto_trade_enabled=lambda enabled, reason="": calls.append((enabled, reason)),
        log_message=lambda *_args, **_kwargs: None,
        _save_brain_live_config=lambda: calls.append("save"),
        update_portfolio_table=lambda: calls.append("portfolio"),
    )

    main.BotUI.on_paper_mode_change(app, "REAL")

    assert config.PAPER_TRADING is False
    assert (False, "Đổi PAPER/REAL") in calls
    assert "reset" in calls and "connect" in calls and "portfolio" in calls
    assert app.trade_mgr.state is next_state
    assert app.tsl_states_map == {}
    assert app._ui_all_positions_snapshot == []
    assert app._mode_switching is False
    assert saved_env[-1] == {"PAPER_TRADING": "False"}
