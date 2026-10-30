"""Private telemetry only. This module has no broker/order dependency."""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

from ckps.rules.calculations import average_true_range_snapshot

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _session_day(stamp):
    try:
        number = float(stamp)
        return datetime.fromtimestamp(number / 1000 if number > 1e12 else number, VN).date()
    except (ValueError, TypeError, OverflowError, OSError):
        value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        return (value.astimezone(VN) if value.tzinfo else value).date()


def completed_bars(bars, now=None):
    today = (now or datetime.now(VN)).date()
    result = {}
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        stamp = bar.get("time", bar.get("timestamp", bar.get("date")))
        try:
            day = _session_day(stamp)
        except (ValueError, TypeError, OverflowError, OSError):
            continue
        if day < today and bar.get("closed", True):
            try:
                values = [float(bar[key]) for key in ("high", "low", "close")]
                high, low, close = values
                if all(isfinite(value) and value > 0 for value in values) and low <= close <= high:
                    result[day] = bar
            except (KeyError, ValueError, TypeError):
                continue
    return [result[day] for day in sorted(result)]


def completed_atr_pct(bars):
    return completed_atr_snapshot(bars)['pct'] or 0.0


def completed_atr_snapshot(bars, now=None):
    """The calculation and its closed-session provenance travel together."""
    result = {'period': 14, 'pct': None, 'as_of': None, 'count': 0}
    try:
        rows = completed_bars(bars, now)
        result['count'] = len(rows)
        if rows:
            last = rows[-1]
            result['as_of'] = _session_day(last.get('time', last.get('timestamp', last.get('date')))).isoformat()
        value = average_true_range_snapshot(rows, 14)[1]
        if isfinite(value) and value > 0:
            result['pct'] = value
    except (ValueError, TypeError, OverflowError, KeyError, OSError):
        pass
    return result
