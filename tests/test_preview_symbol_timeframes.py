# -*- coding: utf-8 -*-
"""Preview must label the exact timeframe resolved for each symbol."""

from types import SimpleNamespace

import main
import ui_bot_strategy
from core.storage_manager import brain_strategy_fingerprint


class _TradeMgr:
    def _get_brain_settings(self, symbol):
        if symbol == "VN30F1M":
            return {
                "G0_TIMEFRAME": "1h",
                "G1_TIMEFRAME": "15m",
                "G2_TIMEFRAME": "5m",
                "G3_TIMEFRAME": "1m",
                "risk_tsl": {"base_sl": "G1"},
            }
        return {"G0_TIMEFRAME": "1d"}


class _PreviewShim:
    trade_mgr = _TradeMgr()
    _symbol_group_timeframe = main.BotUI._symbol_group_timeframe
    _group_tf_label = main.BotUI._group_tf_label
    _sandbox_sl_group_for_symbol = main.BotUI._sandbox_sl_group_for_symbol


APP = _PreviewShim()


def test_vn30_preview_uses_symbol_override_label():
    assert APP._group_tf_label("G0", "VN30F1M") == "G0 (1h)"
    assert APP._group_tf_label("G2", "VN30F1M") == "G2 (5m)"
    assert APP._sandbox_sl_group_for_symbol("VN30F1M", {}, "G0") == "G1"


def test_context_mapping_has_priority_over_live_settings():
    context = {"group_timeframes": {"G0": "30m"}}
    assert APP._group_tf_label("G0", "VN30F1M", context) == "G0 (30m)"


def test_non_group_label_is_unchanged():
    assert APP._group_tf_label("DYNAMIC", "VN30F1M") == "DYNAMIC"


def test_strategy_preview_group_label_uses_effective_symbol_timeframe():
    ui = SimpleNamespace(
        _get_group_timeframe=lambda _group: "1d",
        _format_tf_label=lambda timeframe: ui_bot_strategy.BotStrategyUI._format_tf_label(
            None,
            timeframe,
        ),
    )

    assert (
        ui_bot_strategy.BotStrategyUI._group_label_for_brain(
            ui,
            "G0",
            {"G0_TIMEFRAME": "1h"},
        )
        == "G0(H1)"
    )
    assert (
        ui_bot_strategy.BotStrategyUI._group_label_for_brain(
            ui,
            "G1",
            {"G1_TIMEFRAME": "15m"},
        )
        == "G1(M15)"
    )


def test_strategy_preview_loads_effective_settings_for_selected_symbol(monkeypatch):
    effective = {"G0_TIMEFRAME": "1h", "G1_TIMEFRAME": "15m"}
    monkeypatch.setattr(
        "core.storage_manager.get_brain_settings_for_symbol",
        lambda symbol: effective if symbol == "VN30F1M" else {},
    )
    ui = SimpleNamespace(
        override_symbol=None,
        brain_data={"G0_TIMEFRAME": "1d"},
    )

    assert (
        ui_bot_strategy.BotStrategyUI._effective_preview_brain(
            ui,
            "vn30f1m",
        )
        is effective
    )


def test_strategy_preview_rejects_context_from_old_strategy():
    brain = {
        "G0_TIMEFRAME": "1h",
        "voting_rules": {"G0": {"master_rule": "PASS"}},
        "indicators": {
            "ema": {
                "active": True,
                "groups": ["G0"],
                "params": {"period": 20},
            }
        },
    }
    context = {
        "strategy_fingerprint": "old-config",
        "group_details": {"G0": {"B": 1, "S": 0, "N": 0}},
        "trend_G0": "UP",
    }

    assert (
        ui_bot_strategy.BotStrategyUI._context_ready_for_preview(
            None,
            context,
            brain,
        )
        is False
    )

    context["strategy_fingerprint"] = brain_strategy_fingerprint(brain)
    assert (
        ui_bot_strategy.BotStrategyUI._context_ready_for_preview(
            None,
            context,
            brain,
        )
        is True
    )


def test_strategy_entry_exit_tactics_remain_preview_only():
    class _Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    ui = SimpleNamespace(
        _entry_exit_cfg=lambda: {
            "enabled": False,
            "preview_only": True,
            "active_tactics": [],
            "entry_tactics": ["SWING_REJECTION"],
            "exit_tactic": "AUTO",
            "sl_mode": "SANDBOX",
            "missing_data_policy": "FALLBACK_R",
            "default_exit": {},
        },
        bot_entry_exit_tactic_vars={"SWING_REJECTION": _Var(True)},
        bot_entry_exit_fallback_r_var=_Var(False),
        bot_entry_exit_var=_Var("TP theo Entry thắng"),
        bot_entry_exit_sl_var=_Var("SL Sandbox (không override)"),
        bot_entry_exit_missing_var=_Var("Thiếu dữ liệu -> dùng R"),
    )

    cfg = ui_bot_strategy.BotStrategyUI._collect_entry_exit_config(ui)

    assert cfg["enabled"] is True
    assert cfg["preview_only"] is True
