# -*- coding: utf-8 -*-

import unittest
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch


sys.modules.setdefault(
    "MetaTrader5",
    SimpleNamespace(
        DEAL_ENTRY_OUT=1,
        DEAL_ENTRY_IN=0,
        DEAL_TYPE_SELL=1,
        terminal_info=lambda: SimpleNamespace(ping_last=0),
        symbol_info_tick=lambda symbol: None,
        symbol_info=lambda symbol: None,
        history_deals_get=lambda position=None: [],
        history_orders_get=lambda position=None: [],
    ),
)

from grid.grid_manager import GridManager


class GridManagerCoreTests(unittest.TestCase):
    def setUp(self):
        self.manager = GridManager()

    def test_arithmetic_spacing(self):
        settings = {"GRID_TYPE": "ARITHMETIC", "GRID_COUNT": 10}
        boundary = {"lower": 100.0, "upper": 110.0}
        self.assertEqual(self.manager._resolve_spacing({}, settings, boundary), 1.0)

    def test_geometric_spacing(self):
        settings = {"GRID_TYPE": "GEOMETRIC", "GEOMETRIC_STEP_PERCENT": 1.0}
        self.assertEqual(self.manager._resolve_spacing({"current_price": 200.0}, settings), 2.0)

    def test_atr_spacing(self):
        settings = {"GRID_TYPE": "ATR_DYNAMIC", "GRID_TIMEFRAME_GROUP": "G2", "SPACING_ATR_MULTIPLIER": 2.0}
        self.assertEqual(self.manager._resolve_spacing({"atr_G2": 3.0}, settings), 6.0)

    def test_signal_source_off_uses_default_mode(self):
        settings = {
            "GRID_SIGNAL_SOURCE": "OFF",
            "DEFAULT_MANUAL_MODE": "SHORT",
            "BOUNDARY_MODE": "MANUAL",
            "MANUAL_LOWER_BOUNDARY": 100.0,
            "MANUAL_UPPER_BOUNDARY": 110.0,
            "GRID_TYPE": "ARITHMETIC",
            "GRID_COUNT": 10,
            "STOP_ON_BREAKOUT": False,
        }
        result = self.manager._evaluate_gate("X", {"current_price": 105.0, "latest_signal": 1}, settings)
        self.assertTrue(result["permission"])
        self.assertEqual(result["mode"], "SHORT")

    def test_signal_source_context_uses_latest_signal(self):
        settings = {
            "GRID_SIGNAL_SOURCE": "CONTEXT",
            "BOUNDARY_MODE": "MANUAL",
            "MANUAL_LOWER_BOUNDARY": 100.0,
            "MANUAL_UPPER_BOUNDARY": 110.0,
            "GRID_TYPE": "ARITHMETIC",
            "GRID_COUNT": 10,
            "STOP_ON_BREAKOUT": False,
        }
        result = self.manager._evaluate_gate("X", {"current_price": 105.0, "latest_signal": 1}, settings)
        self.assertTrue(result["permission"])
        self.assertEqual(result["mode"], "LONG")

    def test_signal_source_imported_uses_grid_signal(self):
        settings = {
            "GRID_SIGNAL_SOURCE": "IMPORTED",
            "BOUNDARY_MODE": "MANUAL",
            "MANUAL_LOWER_BOUNDARY": 100.0,
            "MANUAL_UPPER_BOUNDARY": 110.0,
            "GRID_TYPE": "ARITHMETIC",
            "GRID_COUNT": 10,
            "STOP_ON_BREAKOUT": False,
        }
        result = self.manager._evaluate_gate(
            "X",
            {"current_price": 105.0, "latest_signal": 1, "grid_latest_signal": -1},
            settings,
        )
        self.assertTrue(result["permission"])
        self.assertEqual(result["mode"], "SHORT")

    def test_out_of_range_stop_blocks(self):
        settings = {
            "GRID_SIGNAL_SOURCE": "OFF",
            "DEFAULT_MANUAL_MODE": "NEUTRAL",
            "BOUNDARY_MODE": "MANUAL",
            "MANUAL_LOWER_BOUNDARY": 100.0,
            "MANUAL_UPPER_BOUNDARY": 110.0,
            "GRID_TYPE": "ARITHMETIC",
            "GRID_COUNT": 10,
            "STOP_ON_BREAKOUT": False,
            "OUT_OF_RANGE_POLICY": "STOP",
        }
        result = self.manager._evaluate_gate("X", {"current_price": 120.0}, settings)
        self.assertFalse(result["permission"])
        self.assertEqual(result["reason"], "PRICE_OUT_OF_BOUNDARY")

    def test_out_of_range_auto_rebuild_allows_scan(self):
        settings = {
            "GRID_SIGNAL_SOURCE": "OFF",
            "DEFAULT_MANUAL_MODE": "NEUTRAL",
            "BOUNDARY_MODE": "MANUAL",
            "MANUAL_LOWER_BOUNDARY": 100.0,
            "MANUAL_UPPER_BOUNDARY": 110.0,
            "GRID_TYPE": "ARITHMETIC",
            "GRID_COUNT": 10,
            "STOP_ON_BREAKOUT": False,
            "OUT_OF_RANGE_POLICY": "AUTO_REBUILD",
        }
        result = self.manager._evaluate_gate("X", {"current_price": 120.0}, settings)
        self.assertTrue(result["permission"])
        self.assertEqual(result["reason"], "AUTO_REBUILD_RANGE")
        self.assertEqual(result["boundary"]["source"], "AUTO_REBUILD")
        self.assertLess(result["boundary"]["lower"], 120.0)
        self.assertGreater(result["boundary"]["upper"], 120.0)

    def test_clear_block_keeps_daily_counters(self):
        state = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "grid_pnl_today": -12.5,
            "grid_trades_today": 7,
            "grid_daily_loss_count": 2,
            "last_decision": {"X": {"status": "BLOCK", "reason": "MAX_GRID_ORDERS"}},
            "active_sessions": {
                "X": {
                    "status": "STOP_NEW",
                    "stop_reason": "MAX_GRID_ORDERS",
                    "last_block_reason": "MAX_GRID_ORDERS",
                }
            },
        }
        with patch("grid.grid_manager.load_grid_state", return_value=state), patch("grid.grid_manager.save_grid_state") as save:
            self.manager.clear_session_block("X")

        saved = save.call_args.args[0]
        self.assertEqual(saved["grid_pnl_today"], -12.5)
        self.assertEqual(saved["grid_trades_today"], 7)
        self.assertEqual(saved["grid_daily_loss_count"], 2)
        self.assertEqual(saved["active_sessions"]["X"]["status"], "ACTIVE")
        self.assertNotIn("X", saved["last_decision"])

    def test_stop_session_keeps_daily_counters(self):
        state = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "grid_pnl_today": 3.0,
            "grid_trades_today": 2,
            "grid_daily_loss_count": 0,
            "last_decision": {},
            "active_sessions": {"X": {"status": "ACTIVE"}},
        }
        with patch("grid.grid_manager.load_grid_state", return_value=state), patch("grid.grid_manager.save_grid_state") as save:
            self.manager.stop_session("X")

        saved = save.call_args.args[0]
        self.assertEqual(saved["grid_pnl_today"], 3.0)
        self.assertEqual(saved["grid_trades_today"], 2)
        self.assertEqual(saved["active_sessions"]["X"]["status"], "STOP_NEW")
        self.assertEqual(saved["active_sessions"]["X"]["stop_reason"], "USER_STOP_SESSION")

    def test_rebuild_range_keeps_daily_counters(self):
        state = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "grid_pnl_today": 3.0,
            "grid_trades_today": 2,
            "grid_daily_loss_count": 0,
            "last_decision": {},
            "active_sessions": {"X": {"status": "STOP_NEW"}},
        }
        settings = {
            "DEFAULT_MANUAL_MODE": "NEUTRAL",
            "GRID_SIGNAL_SOURCE": "OFF",
            "GRID_TYPE": "ATR_DYNAMIC",
            "GRID_TIMEFRAME_GROUP": "G2",
            "GRID_COUNT": 10,
            "SPACING_ATR_MULTIPLIER": 1.0,
            "BOUNDARY_MODE": "AUTO_SWING",
        }
        context = {"current_price": 120.0, "atr_G2": 2.0}
        with patch("grid.grid_manager.load_grid_state", return_value=state), \
             patch("grid.grid_manager.load_grid_settings", return_value=settings), \
             patch("grid.grid_manager.save_grid_state") as save:
            result = self.manager.rebuild_session_range("X", context)

        self.assertEqual(result, "SUCCESS|REBUILD_RANGE")
        saved = save.call_args.args[0]
        self.assertEqual(saved["grid_pnl_today"], 3.0)
        self.assertEqual(saved["grid_trades_today"], 2)
        self.assertEqual(saved["active_sessions"]["X"]["status"], "ACTIVE")
        self.assertEqual(saved["active_sessions"]["X"]["boundary"]["source"], "AUTO_REBUILD")

    def test_fast_rescan_does_not_open_same_level_twice(self):
        settings = {
            "GRID_SIGNAL_SOURCE": "OFF",
            "DEFAULT_MANUAL_MODE": "NEUTRAL",
            "BOUNDARY_MODE": "MANUAL",
            "MANUAL_LOWER_BOUNDARY": 100.0,
            "MANUAL_UPPER_BOUNDARY": 110.0,
            "GRID_TYPE": "ARITHMETIC",
            "GRID_COUNT": 10,
            "STOP_ON_BREAKOUT": False,
            "REOPEN_COOLDOWN_SECONDS": 60,
            "FIXED_LOT": 0.1,
            "MAX_GRID_ORDERS": 0,
            "MAX_TOTAL_LOT": 0.0,
            "MAX_BASKET_DRAWDOWN": 0.0,
            "CHECK_PING": False,
            "CHECK_SPREAD": False,
        }
        state = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "grid_pnl_today": 0.0,
            "grid_trades_today": 0,
            "grid_daily_loss_count": 0,
            "last_decision": {},
            "last_grid_action_times": {},
            "active_sessions": {},
        }
        session = self.manager._ensure_session(state, "X", settings, "NEUTRAL", "AUTO", False, {"current_price": 108.0})
        self.manager.connector = SimpleNamespace(_is_connected=True, get_all_open_positions=lambda: [])
        self.manager.executor = SimpleNamespace(calls=0)

        def fake_place_grid_order(**kwargs):
            self.manager.executor.calls += 1
            return "SUCCESS|1"

        self.manager.executor.place_grid_order = fake_place_grid_order
        with patch("grid.grid_manager.is_symbol_trade_window_open", return_value=(True, "OK")), \
             patch("grid.grid_manager.get_magic_numbers", return_value={"grid_magic": 1}):
            first = self.manager._scan_session("X", session, {"current_price": 108.0}, settings, state)
            second = self.manager._scan_session("X", session, {"current_price": 108.0}, settings, state)

        self.assertEqual(first, ["SUCCESS|1"])
        self.assertEqual(second, [])
        self.assertEqual(self.manager.executor.calls, 1)
        self.assertEqual(state["last_decision"]["X"]["reason"], "LEVEL_COOLDOWN")

    def test_open_level_detects_executor_comment(self):
        positions = [SimpleNamespace(comment="GRID_BUY_8")]

        self.assertTrue(self.manager._has_open_level(positions, "BUY_8"))


if __name__ == "__main__":
    unittest.main()
