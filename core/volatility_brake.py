# -*- coding: utf-8 -*-
"""Phanh biến động đơn giản, độc lập với indicator và không gọi thêm API."""

from __future__ import annotations

from collections import defaultdict, deque
import time
from typing import Any, Deque, Dict, Optional, Tuple

import config


DEFAULT_SETTINGS = {
    "VOLATILITY_BRAKE_ENABLED": False,
    "VOLATILITY_BRAKE_WINDOW_SECONDS": 60.0,
    "VOLATILITY_BRAKE_STOCK_PCT": 1.5,
    "VOLATILITY_BRAKE_DERIVATIVE_POINTS": 5.0,
    "VOLATILITY_BRAKE_CONFIRMATIONS": 2,
}


def settings_from_safeguard(safeguard: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    source = safeguard if isinstance(safeguard, dict) else {}
    result = dict(DEFAULT_SETTINGS)
    result.update({key: source[key] for key in DEFAULT_SETTINGS if key in source})
    result["VOLATILITY_BRAKE_ENABLED"] = bool(result["VOLATILITY_BRAKE_ENABLED"])
    result["VOLATILITY_BRAKE_WINDOW_SECONDS"] = max(
        5.0, float(result["VOLATILITY_BRAKE_WINDOW_SECONDS"] or 60.0)
    )
    result["VOLATILITY_BRAKE_STOCK_PCT"] = max(
        0.01, float(result["VOLATILITY_BRAKE_STOCK_PCT"] or 1.5)
    )
    result["VOLATILITY_BRAKE_DERIVATIVE_POINTS"] = max(
        0.01, float(result["VOLATILITY_BRAKE_DERIVATIVE_POINTS"] or 5.0)
    )
    result["VOLATILITY_BRAKE_CONFIRMATIONS"] = max(
        1, int(result["VOLATILITY_BRAKE_CONFIRMATIONS"] or 2)
    )
    return result


def is_derivative_symbol(symbol: str) -> bool:
    symbol = str(symbol or "").strip().upper()
    configured = {
        str(item or "").strip().upper()
        for item in (getattr(config, "CKPS_SYMBOLS", []) or [])
    }
    return symbol.startswith("VN30F") or symbol in configured


class VolatilityBrakeDetector:
    """Giữ một cửa sổ giá ngắn và phát sự kiện sau N lần xác nhận liên tiếp."""

    def __init__(self):
        self._history: Dict[str, Deque[Tuple[float, float]]] = defaultdict(deque)
        self._confirmations: Dict[str, int] = defaultdict(int)

    def clear(self) -> None:
        self._history.clear()
        self._confirmations.clear()

    def observe(
        self,
        symbol: str,
        price: float,
        safeguard: Optional[Dict[str, Any]],
        *,
        timestamp: Optional[float] = None,
        freshness: str = "FRESH",
    ) -> Optional[Dict[str, Any]]:
        cfg = settings_from_safeguard(safeguard)
        symbol = str(symbol or "").strip().upper()
        now = float(timestamp if timestamp is not None else time.time())
        try:
            price = float(price)
        except (TypeError, ValueError):
            return None

        if not cfg["VOLATILITY_BRAKE_ENABLED"] or not symbol or price <= 0:
            self._confirmations[symbol] = 0
            return None
        if str(freshness or "").strip().upper() in {"STALE", "OLD", "GIÁ CŨ", "GIA_CU"}:
            self._confirmations[symbol] = 0
            return None

        window = cfg["VOLATILITY_BRAKE_WINDOW_SECONDS"]
        history = self._history[symbol]
        if history and now <= history[-1][0]:
            return None
        history.append((now, price))
        while history and history[0][0] < now - window:
            history.popleft()

        if len(history) < 2:
            return None

        reference_ts, reference_price = history[0]
        if reference_price <= 0 or now <= reference_ts:
            return None

        change_points = price - reference_price
        change_pct = change_points / reference_price * 100.0
        derivative = is_derivative_symbol(symbol)
        threshold = (
            cfg["VOLATILITY_BRAKE_DERIVATIVE_POINTS"]
            if derivative
            else cfg["VOLATILITY_BRAKE_STOCK_PCT"]
        )
        magnitude = abs(change_points) if derivative else abs(change_pct)

        if magnitude < threshold:
            self._confirmations[symbol] = 0
            return None

        self._confirmations[symbol] += 1
        if self._confirmations[symbol] < cfg["VOLATILITY_BRAKE_CONFIRMATIONS"]:
            return None

        self._confirmations[symbol] = 0
        history.clear()
        return {
            "event": "VOLATILITY_BRAKE",
            "symbol": symbol,
            "direction": "UP" if change_points > 0 else "DOWN",
            "reference_price": reference_price,
            "current_price": price,
            "change_points": change_points,
            "change_pct": change_pct,
            "window_seconds": max(1.0, now - reference_ts),
            "threshold": threshold,
            "threshold_unit": "POINTS" if derivative else "PERCENT",
            "triggered_at": now,
        }
