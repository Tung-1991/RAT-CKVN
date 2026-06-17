# -*- coding: utf-8 -*-
from types import SimpleNamespace

import core.trade_manager as trade_manager_module
from core.trade_manager import TradeManager


class DummyChecklist:
    def run_bot_safeguard_checks(self, *args, **kwargs):
        return {"passed": True, "checks": []}

    def run_pre_trade_checks(self, *args, **kwargs):
        return {"passed": True, "checks": []}


class DummyConnector:
    def __init__(self, positions=None):
        self.positions = positions or []
        self.orders = []
        self.closed = []

    def get_account_info(self):
        return {"balance": 100000000.0, "equity": 100000000.0}

    def get_all_open_positions(self):
        return list(self.positions)

    def close_position(self, pos):
        self.closed.append(pos)
        return SimpleNamespace(ok=True, error="", message="")

    def place_order(self, *args, **kwargs):
        self.orders.append((args, kwargs))
        return SimpleNamespace(ok=True, order_id="O1", position_id="P1")


def _manager(monkeypatch, tmp_path, positions=None, brain=None):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(trade_manager_module, "is_symbol_trade_window_open", lambda _symbol: (True, ""))
    monkeypatch.setattr(
        "core.storage_manager.get_magic_numbers",
        lambda: {"bot_magic": 9999, "manual_magic": 8888},
    )
    mgr = TradeManager(DummyConnector(positions), DummyChecklist(), log_callback=lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mgr,
        "_get_brain_settings",
        lambda _symbol=None: brain or {"bot_safeguard": {}, "risk_tsl": {}, "entry_exit": {}},
    )
    return mgr


def test_stock_sell_without_settled_long_is_blocked(monkeypatch, tmp_path):
    mgr = _manager(monkeypatch, tmp_path, positions=[])

    result = mgr.execute_bot_trade("SELL", "FPT", {}, signal_class="ENTRY")

    assert result.startswith("SAFEGUARD_FAIL|NO_SETTLED_LONG|")
    assert mgr.connector.orders == []


def test_stock_reverse_close_only_does_not_open_short(monkeypatch, tmp_path):
    pos = SimpleNamespace(
        ticket="P1",
        position_id="P1",
        order_id="O1",
        symbol="FPT",
        type=0,
        volume=100,
        profit=1000.0,
        swap=0.0,
        commission=0.0,
        time=0.0,
        magic=9999,
        comment="[BOT]_AUTO_ENTRY",
        raw={"settle_date": "2000-01-01"},
    )
    mgr = _manager(
        monkeypatch,
        tmp_path,
        positions=[pos],
        brain={"bot_safeguard": {"CLOSE_ON_REVERSE": True, "CLOSE_ON_REVERSE_MIN_TIME": 0}, "risk_tsl": {}, "entry_exit": {}},
    )

    result = mgr.execute_bot_trade("SELL", "FPT", {}, signal_class="ENTRY")

    assert result.startswith("SAFEGUARD_FAIL|REV_CLOSE_ONLY|")
    assert mgr.connector.orders == []


def test_derivative_sell_is_not_blocked_by_stock_guard(monkeypatch, tmp_path):
    mgr = _manager(monkeypatch, tmp_path, positions=[])

    assert mgr._stock_long_only_guard("VN30F1M", "SELL") is None
