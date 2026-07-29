# -*- coding: utf-8 -*-

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


import core.storage_manager as storage_manager
from core.checklist_manager import ChecklistManager


class JsonAndManualBoundaryTests(unittest.TestCase):
    def test_brain_json_values_win_and_defaults_fill_missing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_path = storage_manager.BRAIN_FILE
            storage_manager.BRAIN_FILE = os.path.join(tmp, "brain_settings.json")
            storage_manager.invalidate_settings_cache()
            try:
                storage_manager.save_brain_settings({"MIN_MATCHING_VOTES": 99})
                loaded = storage_manager.load_brain_settings()
            finally:
                storage_manager.BRAIN_FILE = original_path
                storage_manager.invalidate_settings_cache()

        self.assertEqual(loaded["MIN_MATCHING_VOTES"], 99)
        self.assertIn("risk_tsl", loaded)
        self.assertIn("entry_exit", loaded)

    def test_symbol_overrides_are_atomic_dict_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_path = storage_manager.SYMBOL_OVERRIDES_FILE
            storage_manager.SYMBOL_OVERRIDES_FILE = os.path.join(tmp, "symbol_overrides.json")
            storage_manager.invalidate_settings_cache()
            try:
                storage_manager.save_symbol_overrides({"ETHUSD": {"entry_exit": {"enabled": True}}})
                with open(storage_manager.SYMBOL_OVERRIDES_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                loaded = storage_manager.load_symbol_overrides()
            finally:
                storage_manager.SYMBOL_OVERRIDES_FILE = original_path
                storage_manager.invalidate_settings_cache()

        self.assertEqual(raw, loaded)
        self.assertTrue(loaded["ETHUSD"]["entry_exit"]["enabled"])

    def test_symbol_indicator_override_merges_and_entry_exit_stays_preview_only(self):
        base = {
            "entry_exit": {"enabled": True, "preview_only": False},
            "indicators": {
                "ema": {"active": True, "params": {"period": 50}},
                "rsi": {"active": True, "params": {"period": 14}},
            },
        }
        overrides = {
            "VN30F1M": {
                "sandbox": {
                    "indicators": {
                        "ema": {
                            "groups": ["G0", "G1"],
                            "params": {"period": 20},
                        }
                    }
                }
            }
        }
        storage_manager._cache_merged.clear()
        with patch.object(storage_manager, "_load_brain_cached", return_value=base), patch.object(
            storage_manager,
            "_load_overrides_cached",
            return_value=overrides,
        ):
            loaded = storage_manager.get_brain_settings_for_symbol("VN30F1M")
        storage_manager._cache_merged.clear()

        self.assertEqual(loaded["indicators"]["ema"]["params"]["period"], 20)
        self.assertTrue(loaded["indicators"]["rsi"]["active"])
        self.assertTrue(loaded["entry_exit"]["preview_only"])

    def test_manual_checklist_counts_manual_positions_only(self):
        manual_pos = SimpleNamespace(magic=22, comment="[USER]_SCALPING")
        bot_pos = SimpleNamespace(magic=11, comment="[BOT]_AUTO_ENTRY")
        grid_pos = SimpleNamespace(magic=33, comment="[GRID]_CHILD")
        hedge_pos = SimpleNamespace(magic=44, comment="HEDGE_BUY")
        connector = SimpleNamespace(
            _is_connected=True,
            get_all_open_positions=lambda: [manual_pos, bot_pos, grid_pos, hedge_pos],
        )
        state = {
            "starting_balance": 1000.0,
            "manual_pnl_today": 0.0,
            "manual_daily_loss_count": 0,
            "manual_trades_today": 0,
            "trades_today_count": 999,
            "pnl_today": -999.0,
        }

        with patch("core.storage_manager.get_magic_numbers", return_value={
            "bot_magic": 11,
            "manual_magic": 22,
            "grid_magic": 33,
            "hedge_magic": 44,
        }):
            result = ChecklistManager(connector).run_pre_trade_checks(
                {"balance": 1000.0, "equity": 1000.0},
                state,
                "ETHUSD",
                strict_mode=True,
            )

        daily_check = result["checks"][1]
        trades_check = result["checks"][-2]
        status_check = result["checks"][-1]
        self.assertIn("1", status_check["msg"])
        self.assertIn("0", trades_check["msg"])
        self.assertEqual(daily_check["status"], "OK")


if __name__ == "__main__":
    unittest.main()
