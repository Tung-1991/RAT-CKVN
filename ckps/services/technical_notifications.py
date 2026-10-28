"""Private telemetry only. This module has no broker/order dependency."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ckps.rules.calculations import average_true_range_pct

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def completed_bars(bars, now=None):
    today = (now or datetime.now(VN)).date()
    result = {}
    for bar in bars:
        stamp = bar.get("time", bar.get("timestamp", bar.get("date")))
        try:
            stamp_number = float(stamp)
            day = datetime.fromtimestamp(stamp_number / 1000 if stamp_number > 1e12 else stamp_number, VN).date()
        except (ValueError, TypeError, OverflowError, OSError):
            try:
                day = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).date()
            except ValueError:
                continue
        if day < today and bar.get("closed", True):
            try:
                from math import isfinite
                values = [float(bar[key]) for key in ("high", "low", "close")]
                if all(isfinite(value) and value > 0 for value in values):
                    result[day] = bar
            except (KeyError, ValueError, TypeError):
                continue
    return [result[day] for day in sorted(result)]


def completed_atr_pct(bars):
    try:
        return average_true_range_pct(completed_bars(bars), 14)
    except (ValueError, TypeError, OverflowError):
        return 0.0
