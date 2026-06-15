# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import datetime, timedelta

import MetaTrader5 as mt5

import config


def is_weekday_only_symbol(symbol: str) -> bool:
    explicit = set(getattr(config, "WEEKDAY_ONLY_SYMBOLS", []))
    if symbol in explicit:
        return True

    crypto_symbols = set(getattr(config, "CRYPTO_SYMBOLS", []))
    if symbol in crypto_symbols:
        return False

    return symbol.endswith("USD") and not symbol.startswith(("BTC", "ETH"))


def is_symbol_trade_window_open(symbol: str) -> tuple[bool, str]:
    if is_weekday_only_symbol(symbol):
        offset_hours = float(getattr(config, "MARKET_HOURS_UTC_OFFSET", 0))
        market_now = datetime.utcnow() + timedelta(hours=offset_hours)
        close_weekday = int(getattr(config, "WEEKEND_CLOSE_WEEKDAY", 4))
        close_hour = int(getattr(config, "WEEKEND_CLOSE_HOUR", 22))
        open_weekday = int(getattr(config, "WEEKEND_OPEN_WEEKDAY", 6))
        open_hour = int(getattr(config, "WEEKEND_OPEN_HOUR", 22))

        after_weekly_close = (
            market_now.weekday() > close_weekday
            or (
                market_now.weekday() == close_weekday
                and market_now.hour >= close_hour
            )
        )
        before_weekly_open = (
            market_now.weekday() < open_weekday
            or (
                market_now.weekday() == open_weekday
                and market_now.hour < open_hour
            )
        )
        if after_weekly_close and before_weekly_open:
            tz = f"UTC{offset_hours:+g}"
            return False, f"{symbol} nghi cuoi tuan ({tz})"

    info = mt5.symbol_info(symbol)
    if info is None:
        return False, f"Khong lay duoc thong tin symbol {symbol}"

    trade_mode = getattr(info, "trade_mode", None)
    disabled_modes = {
        getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", -1),
        getattr(mt5, "SYMBOL_TRADE_MODE_CLOSEONLY", -2),
    }
    if trade_mode in disabled_modes:
        return False, f"{symbol} dang khong cho mo lenh"

    return True, "OK"
