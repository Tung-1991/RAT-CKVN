# -*- coding: utf-8 -*-
from types import SimpleNamespace
import sys
import types


sys.modules.setdefault("core.data_engine", types.SimpleNamespace(data_engine=SimpleNamespace()))

import core.trade_manager as trade_manager_mod
from core.trade_manager import TradeManager


class FakeConnector:
    _is_connected = True

    def __init__(self):
        self.orders = []

    def get_account_info(self):
        return {"balance": 1000.0, "equity": 1000.0}

    def get_all_open_positions(self):
        return []

    def calculate_profit(self, symbol, side, volume, entry_price, sl_price):
        return -10.0

    def calculate_lot_size(self, symbol, risk_usd, sl_price, order_type, strict_fee_per_lot=0.0):
        return 0.03, sl_price

    def place_order(self, symbol, order_type, lot, sl, tp, magic, comment):
        self.orders.append((symbol, order_type, lot, sl, tp, magic, comment))
        return SimpleNamespace(retcode=10009, order=12345)


class FakeChecklist:
    def __init__(self):
        self.passed = True

    def run_pre_trade_checks(self, account_info, state, symbol, strict_mode=True):
        if self.passed:
            return {"passed": True, "checks": []}
        return {"passed": False, "checks": [{"status": "FAIL", "msg": "Spr 700 (Max 150)"}]}


def _manager(monkeypatch):
    fake_mt5 = SimpleNamespace(
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        symbol_info_tick=lambda symbol: SimpleNamespace(ask=2000.0, bid=1999.0),
        symbol_info=lambda symbol: SimpleNamespace(volume_min=0.01, volume_max=10.0, volume_step=0.01),
    )
    monkeypatch.setattr(trade_manager_mod, "mt5", fake_mt5)
    monkeypatch.setattr(trade_manager_mod, "is_symbol_trade_window_open", lambda symbol: (True, ""))
    monkeypatch.setattr(trade_manager_mod, "save_state", lambda state: None)

    import core.storage_manager as storage_manager

    monkeypatch.setattr(storage_manager, "get_magic_numbers", lambda: {"manual_magic": 8888})
    mgr = TradeManager.__new__(TradeManager)
    mgr.connector = FakeConnector()
    mgr.checklist = FakeChecklist()
    mgr.log_callback = None
    mgr.state = {
        "trade_tactics": {},
        "entry_exit_tactics": {},
        "initial_r_dist": {},
        "initial_r_usd": {},
        "manual_trades_today": 0,
        "trades_today_count": 0,
    }
    mgr._sync_state_lifecycle = lambda: False
    mgr._get_brain_settings = lambda symbol=None: {
        "risk_tsl": {"bot_tsl": "BE+STEP_R+SWING"},
        "dca_config": {"ENABLED": True},
        "pca_config": {"ENABLED": False},
        "bot_safeguard": {"CLOSE_ON_REVERSE": True},
        "entry_exit": {"enabled": True, "active_tactics": ["FALLBACK_R"], "exit_tactic": "AUTO"},
    }
    mgr.log = lambda *args, **kwargs: None
    return mgr


def test_execute_telegram_sandbox_order_success_uses_sandbox_tactic(monkeypatch):
    mgr = _manager(monkeypatch)

    result = mgr.execute_telegram_sandbox_order("ETHUSD", "BUY", 0.03, 1980.0, 2050.0)

    assert result == "SUCCESS|12345"
    assert mgr.connector.orders == [("ETHUSD", 0, 0.03, 1980.0, 2050.0, 8888, "[USER]_TELEGRAM")]
    assert mgr.state["trade_tactics"]["12345"] == "BE+STEP_R+SWING+AUTO_DCA+REV_C"
    assert mgr.state["entry_exit_tactics"]["12345"] == "FALLBACK_R->AUTO"
    assert mgr.state["manual_trades_today"] == 1


def test_execute_telegram_sandbox_order_rejects_bad_buy_sl(monkeypatch):
    mgr = _manager(monkeypatch)

    result = mgr.execute_telegram_sandbox_order("ETHUSD", "BUY", 0.03, 2010.0, 2050.0)

    assert "BAD_SL" in result
    assert mgr.connector.orders == []


def test_execute_telegram_sandbox_order_can_bypass_checklist(monkeypatch):
    mgr = _manager(monkeypatch)
    mgr.checklist.passed = False

    blocked = mgr.execute_telegram_sandbox_order("ETHUSD", "BUY", 0.03, 1980.0, 2050.0)
    bypassed = mgr.execute_telegram_sandbox_order("ETHUSD", "BUY", 0.03, 1980.0, 2050.0, bypass_checklist=True)

    assert "CHECKLIST" in blocked
    assert bypassed == "SUCCESS|12345"


def test_build_telegram_signal_order_uses_sandbox_defaults(monkeypatch):
    mgr = _manager(monkeypatch)
    context = {
        "atr_G2": 10.0,
        "swing_low_G2": 1980.0,
        "swing_high_G2": 2020.0,
    }

    result = mgr.build_telegram_signal_order("ETHUSD", "BUY", context=context, market_mode="TREND")

    assert result["ok"] is True
    assert result["symbol"] == "ETHUSD"
    assert result["side"] == "BUY"
    assert result["lot"] == 0.03
    assert result["sl"] == 1978.0
    assert result["tp"] > 2000.0
