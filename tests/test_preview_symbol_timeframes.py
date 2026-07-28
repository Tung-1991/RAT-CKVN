# -*- coding: utf-8 -*-
"""Preview must label the exact timeframe resolved for each symbol."""

import main


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
