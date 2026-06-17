# -*- coding: utf-8 -*-
from types import SimpleNamespace

import config
import core.data_engine as data_engine_module
from core.data_engine import DataEngine
import ui_bot_strategy
import ui_popups


def test_ui_symbol_helpers_use_ckps_and_ckcs_watchlists(monkeypatch):
    monkeypatch.setattr(config, "CKPS_SYMBOLS", ["vn30f1m", "VN30F1M"], raising=False)
    monkeypatch.setattr(config, "CKCS_WATCHLIST", ["fpt", "SSI", "fpt"], raising=False)
    monkeypatch.setattr(config, "COIN_LIST", ["OLDCOIN"], raising=False)

    assert ui_bot_strategy._build_trade_symbol_list() == ["VN30F1M", "FPT", "SSI"]
    assert ui_popups._build_watch_symbols() == ["VN30F1M", "FPT", "SSI"]


def test_fetch_bars_returns_empty_when_ohlc_t_is_none(monkeypatch):
    engine = DataEngine()
    fake_dnse = SimpleNamespace(
        market_type_for_symbol=lambda _symbol: "STOCK",
        get_ohlc=lambda *_args: {"t": None, "o": [], "h": [], "l": [], "c": [], "v": []},
    )
    monkeypatch.setattr(data_engine_module, "dnse_api", fake_dnse)

    df = engine._fetch_bars("FPT", "15m", 10, {}, None)

    assert df.empty
