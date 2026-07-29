# -*- coding: utf-8 -*-
"""Preview must label the exact timeframe resolved for each symbol."""

from types import SimpleNamespace

import main
import ui_bot_strategy
from core.storage_manager import brain_strategy_fingerprint


class _Widget:
    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)


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


def test_strategy_preview_rejects_cached_context_from_old_strategy():
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


def test_strategy_preview_rejects_legacy_context_without_fingerprint():
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
        "group_details": {
            "G0": {
                "B": 0,
                "S": 1,
                "N": 0,
                "inds": [{"name": "EMA", "signal": -1}],
            }
        },
        "trend_G0": "DOWN",
    }

    assert (
        ui_bot_strategy.BotStrategyUI._context_ready_for_preview(
            None,
            context,
            brain,
        )
        is False
    )


def test_preview_lists_configured_simple_breakout_when_legacy_cache_has_no_details():
    brain = {
        "indicators": {
            "simple_breakout": {
                "active": True,
                "groups": ["G2"],
                "is_trend": True,
            },
            "volume": {
                "active": False,
                "groups": ["G2"],
            },
        }
    }

    rows = ui_bot_strategy.BotStrategyUI._configured_group_indicator_placeholders(
        brain,
        "G2",
        trend_state="UP",
        stale=True,
    )

    assert rows == ["○ [WAIT] SIMPLE BREAKOUT [NONE|ANY]"]


def test_preview_data_age_uses_context_timestamp_instead_of_persisted_wait_timer():
    text = ui_bot_strategy.BotStrategyUI._preview_data_age_text(
        {"timestamp": 1_700_000_000},
        now=1_700_000_125,
    )

    assert text.startswith("UPDATED:")
    assert text.endswith("2m ago")
    assert "6d" not in text


def test_preview_data_age_marks_strategy_cache_as_stale():
    text = ui_bot_strategy.BotStrategyUI._preview_data_age_text(
        {"timestamp": 1_700_000_000},
        stale=True,
        now=1_700_000_030,
    )

    assert text.startswith("STALE DATA:")
    assert text.endswith("just now")


def test_preview_actually_renders_simple_breakout_row_for_legacy_cache(monkeypatch):
    class _Scroll:
        def __init__(self):
            self.labels = []

        def winfo_children(self):
            return []

    class _Label:
        def __init__(self, parent, text="", **_kwargs):
            parent.labels.append(text)

        def pack(self, **_kwargs):
            return None

    monkeypatch.setattr(ui_bot_strategy.ctk, "CTkLabel", _Label)

    brain = {
        "MASTER_EVAL_MODE": "VETO",
        "G2_TIMEFRAME": "5m",
        "voting_rules": {
            group: {"master_rule": "PASS", "max_opposite": 0, "max_none": 1}
            for group in ("G0", "G1", "G2", "G3")
        },
        "indicators": {
            "simple_breakout": {
                "active": True,
                "groups": ["G2"],
                "is_trend": True,
            }
        },
    }
    context = {
        "strategy_fingerprint": brain_strategy_fingerprint(brain),
        "group_details": {
            group: {"B": 0, "S": 0, "N": 0, "status": 0, "inds": []}
            for group in ("G0", "G1", "G2", "G3")
        },
        "trend_G0": "NONE",
        "trend_G1": "NONE",
        "trend_G2": "UP",
        "trend_G3": "NONE",
        "latest_signal": 0,
        "market_mode": "ANY",
        "mode_source": "G2",
        "macro_direction": 0,
        "block_reason": "WAIT",
    }
    cards = {}
    for group in ("G0", "G1", "G2", "G3"):
        cards[group] = {
            "title": _Widget(),
            "summary": _Widget(),
            "trend": _Widget(),
            "prev": _Widget(),
            "scroll_f": _Scroll(),
            "last_data": "__force_render__",
        }
    ui = SimpleNamespace(
        master=SimpleNamespace(latest_market_context={"VN30F1M": context}),
        override_symbol="VN30F1M",
        preview_symbol_var=None,
        preview_last_symbol="VN30F1M",
        preview_status_cache={},
        preview_cards=cards,
        preview_last_render_error="",
        master_action_lbl=_Widget(),
        market_mode_lbl=_Widget(),
        master_reason_lbl=_Widget(),
        entry_exit_preview_lbl=_Widget(),
        master_eval_var=SimpleNamespace(get=lambda: "VETO"),
        _context_for_symbol=lambda contexts, symbol: contexts.get(symbol, {}),
        _effective_preview_brain=lambda _symbol: brain,
        _context_ready_for_preview=lambda cached, effective: (
            ui_bot_strategy.BotStrategyUI._context_ready_for_preview(
                None,
                cached,
                effective,
            )
        ),
        _schedule_preview_context_fetch=lambda _symbol: None,
        _update_preview_status_timer=lambda *_args: ("0m", "Trước: --"),
        _group_label_for_brain=lambda group, _brain: group,
        _entry_exit_preview_text=lambda *_args: "E/E",
        update_preview=lambda: None,
        after=lambda *_args: None,
    )

    ui_bot_strategy.BotStrategyUI.update_preview(ui)

    assert cards["G2"]["scroll_f"].labels == [
        "○ [WAIT] SIMPLE BREAKOUT [NONE|ANY]"
    ]


def test_strategy_preview_blanks_votes_from_stale_strategy():
    brain = {
        "MASTER_EVAL_MODE": "VETO",
        "G0_TIMEFRAME": "1h",
        "voting_rules": {
            "G0": {"master_rule": "PASS", "max_opposite": 0, "max_none": 1},
        },
        "indicators": {
            "ema": {
                "active": True,
                "groups": ["G0"],
                "is_trend": True,
                "params": {"period": 20},
            }
        },
    }
    context = {
        "strategy_fingerprint": "old-config",
        "group_details": {
            "G0": {
                "B": 0,
                "S": 1,
                "N": 0,
                "status": -1,
                "inds": ["[SELL] EMA [BASE|ANY]"],
            }
        },
        "trend_G0": "DOWN",
        "latest_signal": -1,
        "market_mode": "TREND",
        "mode_source": "G0",
        "macro_direction": -1,
        "block_reason": "OK / Ready",
    }
    cards = {}
    for group in ("G0", "G1", "G2", "G3"):
        cards[group] = {
            "title": _Widget(),
            "summary": _Widget(),
            "trend": _Widget(),
            "prev": _Widget(),
            "scroll_f": SimpleNamespace(),
            "last_data": (
                '["\\u25cb [WAIT] EMA [NONE|ANY]"]'
                if group == "G0"
                else "[]"
            ),
        }
    scheduled = []
    ui = SimpleNamespace(
        master=SimpleNamespace(latest_market_context={"VN30F1M": context}),
        override_symbol="VN30F1M",
        preview_symbol_var=None,
        preview_last_symbol="VN30F1M",
        preview_status_cache={},
        preview_cards=cards,
        preview_last_render_error="",
        master_action_lbl=_Widget(),
        market_mode_lbl=_Widget(),
        master_reason_lbl=_Widget(),
        entry_exit_preview_lbl=_Widget(),
        master_eval_var=SimpleNamespace(get=lambda: "VETO"),
        _context_for_symbol=lambda contexts, symbol: contexts.get(symbol, {}),
        _effective_preview_brain=lambda _symbol: brain,
        _context_ready_for_preview=lambda cached, effective: (
            ui_bot_strategy.BotStrategyUI._context_ready_for_preview(
                None,
                cached,
                effective,
            )
        ),
        _schedule_preview_context_fetch=lambda symbol: scheduled.append(symbol),
        _update_preview_status_timer=lambda *_args: ("0m", "Trước: --"),
        _group_label_for_brain=lambda group, _brain: group,
        _entry_exit_preview_text=lambda *_args: "E/E",
        update_preview=lambda: None,
        after=lambda *_args: None,
    )

    ui_bot_strategy.BotStrategyUI.update_preview(ui)

    assert cards["G0"]["summary"].options["text"] == "B: 0  |  S: 0  |  N: 0"
    assert cards["G0"]["trend"].options["text"] == "TREND: NONE | EMA"
    assert ui.master_action_lbl.options["text"] == "MASTER ACTION: WAIT"
    assert "CACHE CŨ" in ui.master_reason_lbl.options["text"]
    assert scheduled == ["VN30F1M"]


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
