# -*- coding: utf-8 -*-

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.modules.setdefault(
    "MetaTrader5",
    SimpleNamespace(
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        TRADE_RETCODE_DONE=10009,
        DEAL_ENTRY_IN=0,
        DEAL_ENTRY_OUT=1,
        DEAL_TYPE_SELL=1,
        terminal_info=lambda: SimpleNamespace(ping_last=0),
        symbol_info_tick=lambda symbol: None,
        symbol_info=lambda symbol: None,
        history_deals_get=lambda *_args, **_kwargs: [],
        last_error=lambda: (0, ""),
    ),
)

from hedge.hedge_manager import HedgeManager


class HedgeManagerCoreTests(unittest.TestCase):
    def setUp(self):
        self.manager = HedgeManager()

    def test_entry_gate_all_filters_off_is_ready(self):
        settings = {"USE_SIGNAL_FILTER": False, "USE_ENTRY_EXIT_FILTER": False}
        gate = self.manager.evaluate_entry_gate("ETHUSD", {}, settings)
        self.assertTrue(gate["permission"])
        self.assertEqual(gate["reason"], "OK")
        self.assertEqual(gate["signal_status"], "OFF")
        self.assertEqual(gate["entry_status"], "OFF")

    def test_signal_filter_blocks_none_signal(self):
        settings = {"USE_SIGNAL_FILTER": True, "USE_ENTRY_EXIT_FILTER": False}
        gate = self.manager.evaluate_entry_gate("ETHUSD", {"latest_signal": 0}, settings)
        self.assertFalse(gate["permission"])
        self.assertEqual(gate["reason"], "SIGNAL_NONE")

    def test_entry_exit_filter_passes_ready_decision(self):
        settings = {"USE_SIGNAL_FILTER": False, "USE_ENTRY_EXIT_FILTER": True}
        context = {"current_price": 100.0}
        with patch.object(self.manager, "_entry_exit_decisions", return_value={"BUY": {"status": "READY", "reason": "OK"}}):
            gate = self.manager.evaluate_entry_gate("ETHUSD", context, settings)
        self.assertTrue(gate["permission"])
        self.assertEqual(gate["entry_status"], "PASS")

    def test_entry_exit_filter_blocks_wait_decision(self):
        settings = {"USE_SIGNAL_FILTER": False, "USE_ENTRY_EXIT_FILTER": True}
        context = {"current_price": 100.0}
        with patch.object(self.manager, "_entry_exit_decisions", return_value={"BUY": {"status": "WAIT", "reason": "ZONE"}}):
            gate = self.manager.evaluate_entry_gate("ETHUSD", context, settings)
        self.assertFalse(gate["permission"])
        self.assertEqual(gate["reason"], "ENTRY_EXIT_NOT_READY")

    def test_symbol_override_replaces_global(self):
        settings = {
            "FIXED_LOT": 0.1,
            "USE_TSL": True,
            "SYMBOL_OVERRIDES": {"BTCUSD": {"FIXED_LOT": 0.2, "USE_TSL": False}},
        }
        cfg = self.manager.settings_for_symbol("BTCUSD", settings)
        self.assertEqual(cfg["FIXED_LOT"], 0.2)
        self.assertFalse(cfg["USE_TSL"])

    def test_second_leg_fail_closes_first_leg(self):
        state = {
            "active_sessions": {},
            "last_decision": {},
            "last_decision_log_keys": {},
            "last_close_times": {},
            "date": "",
            "hedge_pnl_today": 0.0,
            "hedge_sessions_today": 0,
            "hedge_daily_loss_count": 0,
        }
        settings = {
            "USE_SIGNAL_FILTER": False,
            "USE_ENTRY_EXIT_FILTER": False,
            "USE_HEDGE_SLTP": False,
            "FIXED_LOT": 0.1,
            "MAX_PAIRS_PER_SYMBOL": 1,
            "COOLDOWN_AFTER_CLOSE_SECONDS": 0,
            "CHECK_PING": False,
            "CHECK_SPREAD": False,
        }
        first_pos = SimpleNamespace(ticket=101, symbol="ETHUSD", magic=55, comment="HEDGE_BUY")
        self.manager.connector = SimpleNamespace(_is_connected=True, get_all_open_positions=lambda: [first_pos])
        self.manager.executor = SimpleNamespace(calls=0, closed=[])

        def fake_place(*args, **kwargs):
            self.manager.executor.calls += 1
            return "SUCCESS|101" if self.manager.executor.calls == 1 else "HEDGE_FAIL|SECOND"

        def fake_close(pos, reason):
            self.manager.executor.closed.append((pos.ticket, reason))
            return "SUCCESS|101"

        self.manager.executor.place_hedge_leg = fake_place
        self.manager.executor.close_position = fake_close

        with patch("hedge.hedge_manager.load_hedge_settings", return_value=settings), \
             patch("hedge.hedge_manager.load_hedge_state", return_value=state), \
             patch("hedge.hedge_manager.save_hedge_state") as save, \
             patch("hedge.hedge_manager.get_magic_numbers", return_value={"hedge_magic": 55}), \
             patch("hedge.hedge_manager.is_symbol_trade_window_open", return_value=(True, "OK")):
            result = self.manager.start_manual_session("ETHUSD", {})

        self.assertIn("PAIR_OPEN_FAILED", result)
        self.assertEqual(self.manager.executor.closed, [(101, "PAIR_FAIL")])
        self.assertEqual(save.call_args.args[0]["hedge_sessions_today"], 0)

    def test_daily_loss_guard_blocks_new_pair(self):
        state = {
            "active_sessions": {},
            "last_decision": {},
            "last_decision_log_keys": {},
            "date": "",
            "hedge_pnl_today": -12.0,
            "hedge_sessions_today": 0,
            "hedge_daily_loss_count": 1,
        }
        settings = {"HEDGE_MAX_DAILY_LOSS": 10.0, "USE_SIGNAL_FILTER": False, "USE_ENTRY_EXIT_FILTER": False}
        with patch("hedge.hedge_manager.get_today_str", return_value=""):
            self.manager._ensure_hedge_state(state)
            result = self.manager._start_pair_session("ETHUSD", {}, settings, state, source="AUTO")
        self.assertEqual(result, "HEDGE_BLOCK|HEDGE_DAILY_LOSS")
        self.assertEqual(state["last_decision"]["ETHUSD"]["reason"], "HEDGE_DAILY_LOSS")

    def test_scan_auto_starts_from_watchlist(self):
        state = {
            "active_sessions": {},
            "last_decision": {},
            "last_decision_log_keys": {},
            "last_close_times": {},
            "date": "",
            "hedge_pnl_today": 0.0,
            "hedge_sessions_today": 0,
            "hedge_daily_loss_count": 0,
        }
        settings = {
            "ENABLED": True,
            "WATCHLIST": ["ETHUSD"],
            "USE_SIGNAL_FILTER": False,
            "USE_ENTRY_EXIT_FILTER": False,
            "USE_HEDGE_SLTP": False,
            "FIXED_LOT": 0.1,
            "MAX_PAIRS_PER_SYMBOL": 1,
            "COOLDOWN_AFTER_CLOSE_SECONDS": 0,
            "CHECK_PING": False,
            "CHECK_SPREAD": False,
        }
        opened = []
        self.manager.connector = SimpleNamespace(_is_connected=True, get_all_open_positions=lambda: opened)
        self.manager.executor = SimpleNamespace(calls=0)

        def fake_place(*args, **kwargs):
            self.manager.executor.calls += 1
            ticket = 100 + self.manager.executor.calls
            comment = "HEDGE_BUY" if self.manager.executor.calls == 1 else "HEDGE_SELL"
            opened.append(SimpleNamespace(ticket=ticket, symbol="ETHUSD", magic=55, comment=comment, profit=0.0, swap=0.0, commission=0.0))
            return f"SUCCESS|{ticket}"

        self.manager.executor.place_hedge_leg = fake_place

        with patch("hedge.hedge_manager.load_hedge_settings", return_value=settings), \
             patch("hedge.hedge_manager.load_hedge_state", return_value=state), \
             patch("hedge.hedge_manager.save_hedge_state") as save, \
             patch("hedge.hedge_manager.get_magic_numbers", return_value={"hedge_magic": 55}), \
             patch("hedge.hedge_manager.is_symbol_trade_window_open", return_value=(True, "OK")):
            result = self.manager.scan(["ETHUSD"], {"ETHUSD": {}})

        saved_state = save.call_args.args[0]
        self.assertIn("HEDGE_OPEN|ETHUSD|AUTO", result["actions"])
        self.assertEqual(saved_state["active_sessions"]["ETHUSD"]["source"], "AUTO")

    def test_daily_reset_uses_storage_today(self):
        state = {
            "date": "old",
            "hedge_pnl_today": -9.0,
            "hedge_sessions_today": 3,
            "hedge_daily_loss_count": 2,
        }
        with patch("hedge.hedge_manager.get_today_str", return_value="2026-05-25"):
            self.manager._ensure_hedge_state(state)
        self.assertEqual(state["date"], "2026-05-25")
        self.assertEqual(state["hedge_pnl_today"], 0.0)
        self.assertEqual(state["hedge_sessions_today"], 0)
        self.assertEqual(state["hedge_daily_loss_count"], 0)

    def test_account_risk_lot_mode_reuses_connector_lot_formula_and_cap(self):
        calls = []

        def calc_lot(symbol, risk_usd, sl_price, order_type, strict_fee_per_lot=0.0):
            calls.append((symbol, risk_usd, sl_price, order_type, strict_fee_per_lot))
            return (1.2, sl_price) if order_type == 0 else (0.8, sl_price)

        self.manager.connector = SimpleNamespace(
            get_account_info=lambda: {"equity": 10000.0, "balance": 9000.0},
            calculate_lot_size=calc_lot,
        )
        cfg = {
            "LOT_MODE": "ACCOUNT_RISK",
            "FIXED_LOT": 0.1,
            "RISK_PERCENT_PER_PAIR": 1.0,
            "MAX_LOT_CAP": 0.5,
            "SWING_GROUP": "G2",
        }
        context = {"swing_low_G2": 100.0, "swing_high_G2": 110.0, "atr_G2": 2.0}

        with patch("hedge.hedge_manager.mt5.symbol_info") as symbol_info:
            symbol_info.return_value = SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)
            lot, meta = self.manager._resolve_lot_size("ETHUSD", cfg, context)

        self.assertEqual(lot, 0.5)
        self.assertEqual(meta["LOT_MODE"], "ACCOUNT_RISK")
        self.assertTrue(meta["LOT_CAP_APPLIED"])
        self.assertEqual(meta["ACCOUNT_RISK_USD"], 100.0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1], 100.0)
        self.assertAlmostEqual(calls[0][2], 99.6)
        self.assertAlmostEqual(calls[1][2], 110.4)

    def test_entry_exit_ready_supplies_leg_sl_tp(self):
        cfg = {"USE_HEDGE_SLTP": False}
        context = {"current_price": 100.0}
        decision = {"status": "READY", "entry_tactic": "FALLBACK_R", "sl": 99.0, "tp": 102.0}
        plan = self.manager._resolve_leg_sltp("ETHUSD", "BUY", cfg, context, decision)

        self.assertTrue(plan["ready"])
        self.assertEqual(plan["sl"], 99.0)
        self.assertEqual(plan["tp"], 102.0)
        self.assertEqual(plan["source"], "ENTRY_EXIT:FALLBACK_R")

    def test_sync_history_adds_closed_leg_pnl_to_active_session(self):
        state = {
            "active_sessions": {
                "ETHUSD": {
                    "buy_ticket": 101,
                    "sell_ticket": 102,
                    "closed_leg_pnl": 0.0,
                }
            },
            "hedge_active_tickets": [101, 102],
            "hedge_pnl_today": 0.0,
            "hedge_daily_loss_count": 0,
        }
        self.manager.connector = SimpleNamespace(
            get_all_open_positions=lambda: [
                SimpleNamespace(ticket=102, symbol="ETHUSD", magic=55, comment="HEDGE_SELL")
            ]
        )
        deals = [
            SimpleNamespace(entry=0, time=1, price=100.0, comment="HEDGE_BUY"),
            SimpleNamespace(entry=1, type=1, symbol="ETHUSD", volume=0.1, profit=5.0, commission=-0.2, swap=-0.1),
        ]

        with patch("hedge.hedge_manager.get_magic_numbers", return_value={"hedge_magic": 55}), \
             patch("hedge.hedge_manager.mt5.history_deals_get", return_value=deals), \
             patch("hedge.hedge_manager.append_trade_log"):
            self.manager._sync_hedge_history(state)

        self.assertAlmostEqual(state["active_sessions"]["ETHUSD"]["closed_leg_pnl"], 4.7)
        self.assertEqual(state["active_sessions"]["ETHUSD"]["closed_legs"]["101"], 4.7)

    def test_session_tp_closes_open_legs(self):
        closed = []
        self.manager.connector = SimpleNamespace(
            get_all_open_positions=lambda: [
                SimpleNamespace(ticket=101, symbol="ETHUSD", magic=55, comment="HEDGE_BUY", profit=7.0, swap=0.0, commission=0.0),
                SimpleNamespace(ticket=102, symbol="ETHUSD", magic=55, comment="HEDGE_SELL", profit=4.0, swap=0.0, commission=0.0),
            ]
        )
        self.manager.executor = SimpleNamespace(
            close_position=lambda pos, reason: closed.append((pos.ticket, reason)) or f"SUCCESS|{pos.ticket}"
        )
        state = {"active_sessions": {"ETHUSD": {}}, "last_decision": {}, "last_decision_log_keys": {}}
        session = {
            "buy_ticket": 101,
            "sell_ticket": 102,
            "closed_leg_pnl": 0.0,
            "created_at": 1,
            "status": "PAIR_OPEN",
        }

        with patch("hedge.hedge_manager.get_magic_numbers", return_value={"hedge_magic": 55}):
            actions = self.manager._manage_session(
                "ETHUSD",
                session,
                {"HEDGE_SESSION_TP_USD": 10.0, "HEDGE_SESSION_SL_USD": 0.0, "HEDGE_MAX_HOLD_MINUTES": 0},
                state,
            )

        self.assertEqual(actions, ["SUCCESS|101", "SUCCESS|102"])
        self.assertEqual(closed, [(101, "SESSION_TP"), (102, "SESSION_TP")])
        self.assertNotIn("ETHUSD", state["active_sessions"])


if __name__ == "__main__":
    unittest.main()
