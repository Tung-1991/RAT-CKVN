"""Original MayinTien signal calculations; no order-planning class is imported."""
from __future__ import annotations
from datetime import date, datetime
from math import isfinite
from typing import Any, Iterable
from ckps.rules.calculations import closes, ema, rsi
from ckps.rules.signal_settings import SignalSettings as StaticRuleParameters
from .market import VN_TZ, active_trading_minutes, normalize_exchange, validate_buy_window
from .observations import ema_cross_evidence





def crossover_signal_from_snapshots(
    current: dict[str, Any] | None,
    previous: dict[str, Any] | None,
    *,
    prefer: str = "BUY",
    buy_use_ema: bool = True,
    buy_use_rsi: bool = True,
    buy_signal_require_ema_cross: bool = True,
    sell_use_ema: bool = True,
    sell_use_rsi: bool = True,
    sell_signal_require_ema_cross: bool = False,
) -> str:
    """Evaluate BUY levels (or an optional fresh cross) and SELL conditions.

    ``current`` may be an unfinished daily candle rebuilt from a live tick or
    an intraday source bar. BUY defaults to requiring a fresh upward cross.
    When its fresh-cross option is enabled, compare with the preceding
    observation of that same candle, not repeatedly with yesterday's close.
    SELL defaults to exit EMA levels; the optional legacy mode requires a fresh
    downward cross. RSI compares against ``rsi_previous`` in both modes.
    """
    current = current if isinstance(current, dict) else {}
    previous = previous if isinstance(previous, dict) else {}
    if current.get("signal_ready") is False:
        return ""

    def number(source: dict[str, Any], key: str) -> float | None:
        try:
            value = source.get(key)
            parsed = None if value is None else float(value)
            return parsed if parsed is not None and isfinite(parsed) else None
        except (TypeError, ValueError, OverflowError):
            return None

    current_rsi = number(current, "rsi")
    previous_daily_rsi = number(current, "rsi_previous")
    current_buy_fast = number(current, "buy_ema_fast")
    current_buy_slow = number(current, "buy_ema_slow")
    previous_buy_fast = number(previous, "buy_ema_fast")
    previous_buy_slow = number(previous, "buy_ema_slow")
    current_sell_fast = number(current, "sell_ema_fast")
    current_sell_slow = number(current, "sell_ema_slow")
    previous_sell_fast = number(previous, "sell_ema_fast")
    previous_sell_slow = number(previous, "sell_ema_slow")
    sample_count = current.get("sample_count")
    try:
        count = int(sample_count) if sample_count is not None else None
    except (TypeError, ValueError):
        count = None
    buy_slow_period = int(current.get("buy_ema_slow_period", 1) or 1)
    sell_slow_period = int(current.get("sell_ema_slow_period", 1) or 1)
    period = int(current.get("rsi_period", 1) or 1)

    def side_ready(*, use_ema: bool, use_rsi: bool, slow_period: int,
                   ema_values: tuple[float | None, ...]) -> bool:
        required: list[float | None] = []
        if use_rsi:
            required.extend((current_rsi, previous_daily_rsi))
        if use_ema:
            required.extend(ema_values)
        history = max(2, slow_period + 1 if use_ema else 2, period + 2 if use_rsi else 2)
        return (count is None or count >= history) and not any(value is None for value in required)

    buy_ready = side_ready(
        use_ema=buy_use_ema, use_rsi=buy_use_rsi, slow_period=buy_slow_period,
        ema_values=(
            (current_buy_fast, current_buy_slow, previous_buy_fast, previous_buy_slow)
            if buy_signal_require_ema_cross else (current_buy_fast, current_buy_slow)
        ),
    )
    sell_ready = side_ready(
        use_ema=sell_use_ema, use_rsi=sell_use_rsi, slow_period=sell_slow_period,
        ema_values=(
            (current_sell_fast, current_sell_slow, previous_sell_fast, previous_sell_slow)
            if sell_signal_require_ema_cross else (current_sell_fast, current_sell_slow)
        ),
    )

    # Each side requires its own previous EMA only when its cross option is ON.
    buy_ema_ok = buy_ready and (
        not buy_use_ema or (
            current_buy_fast > current_buy_slow
            and (not buy_signal_require_ema_cross or previous_buy_fast <= previous_buy_slow)
        )
    )
    sell_ema_ok = sell_ready and (
        not sell_use_ema or (
            current_sell_fast < current_sell_slow
            and (not sell_signal_require_ema_cross or previous_sell_fast >= previous_sell_slow)
        )
    )
    buy_signal = buy_ready and bool(buy_use_ema or buy_use_rsi) and (
        (not buy_use_ema or buy_ema_ok)
        and (not buy_use_rsi or current_rsi > previous_daily_rsi)
    )
    sell_signal = sell_ready and bool(sell_use_ema or sell_use_rsi) and (
        (not sell_use_ema or sell_ema_ok)
        and (not sell_use_rsi or current_rsi < previous_daily_rsi)
    )
    if str(prefer or "BUY").upper() == "SELL":
        if sell_signal:
            return "SELL"
        if buy_signal:
            return "BUY"
    else:
        if buy_signal:
            return "BUY"
        if sell_signal:
            return "SELL"
    return ""


def indicator_snapshot(
    rows: Iterable[dict[str, Any]],
    fast: int = 3,
    slow: int = 6,
    rsi_period: int = 14,
    *,
    sell_fast: int | None = None,
    sell_slow: int | None = None,
) -> dict[str, Any]:
    """Return the exact latest values used by the static M/B rule."""
    rows = list(rows)
    values = closes(rows)
    fast = max(1, int(fast or 3))
    slow = max(1, int(slow or 6))
    rsi_period = max(1, int(rsi_period or 14))
    sell_fast = max(1, int(sell_fast if sell_fast is not None else fast))
    sell_slow = max(1, int(sell_slow if sell_slow is not None else slow))
    fast_values = ema(values, fast) if values else []
    slow_values = ema(values, slow) if values else []
    sell_fast_values = ema(values, sell_fast) if values else []
    sell_slow_values = ema(values, sell_slow) if values else []
    rsi_values = rsi(values, rsi_period) if values else []
    current_rsi = rsi_values[-1] if rsi_values else None
    previous_rsi = rsi_values[-2] if len(rsi_values) >= 2 else None
    return {
        "sample_count": len(values),
        "ema_fast_period": fast,
        "ema_slow_period": slow,
        "rsi_period": rsi_period,
        "ema_fast": fast_values[-1] if fast_values else None,
        "ema_slow": slow_values[-1] if slow_values else None,
        "buy_ema_fast_period": fast,
        "buy_ema_slow_period": slow,
        "buy_ema_fast": fast_values[-1] if fast_values else None,
        "buy_ema_slow": slow_values[-1] if slow_values else None,
        "sell_ema_fast_period": sell_fast,
        "sell_ema_slow_period": sell_slow,
        "sell_ema_fast": sell_fast_values[-1] if sell_fast_values else None,
        "sell_ema_slow": sell_slow_values[-1] if sell_slow_values else None,
        "rsi": current_rsi,
        "rsi_previous": previous_rsi,
        "rsi_previous_time": rows[-2].get("time", "") if len(rows) >= 2 else "",
    }


def crossover_count(rows: Iterable[dict[str, Any]], fast: int = 3, slow: int = 6, window: int = 10,
                    *, after_session: str = "") -> int:
    rows = [row for row in (rows or []) if closes([row])]
    values = closes(rows)
    if len(values) < 2:
        return 0
    fast_values = ema(values, fast)
    slow_values = ema(values, slow)
    start = max(1, len(values) - max(1, int(window or 10)))
    # Equality is neutral, just as it is in the live EMA memory. Find the
    # latest real side before this window, then count strict side changes.
    previous = 0
    for index in range(start - 1, -1, -1):
        previous = 1 if fast_values[index] > slow_values[index] else -1 if fast_values[index] < slow_values[index] else 0
        if previous:
            break
    count = 0
    for index in range(start, len(values)):
        current = 1 if fast_values[index] > slow_values[index] else -1 if fast_values[index] < slow_values[index] else 0
        if current:
            after_reset = True
            if after_session:
                after_reset = datetime.fromtimestamp(float(rows[index]["time"]), VN_TZ).date().isoformat() > after_session
            count += int(previous != 0 and current != previous and after_reset)
            previous = current
    return count


def whipsaw_reset_profile(reset: dict | None, fast: int, slow: int) -> dict:
    """A reset belongs to its BUY EMA pair; changing the pair restores raw history."""
    row = reset if isinstance(reset, dict) else {}
    try:
        cutoff = date.fromisoformat(row.get("after_session", "")).isoformat()
        valid = row.get("id") and row.get("pair") == f"{fast}/{slow}"
    except (ValueError, TypeError):
        return {}
    return {**row, "after_session": cutoff} if valid else {}


def whipsaw_snapshot(rows, fast=3, slow=6, window=10, *, reset=None) -> dict:
    """Shared LIVE/PAPER/replay/preview count; EMA always retains its full seed."""
    rows = list(rows)
    raw = crossover_count(rows, fast, slow, window)
    active = whipsaw_reset_profile(reset, fast, slow)
    if active:
        try:
            count = crossover_count(rows, fast, slow, window, after_session=active["after_session"])
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            # Unverifiable candle dates cannot grant a manual bypass.
            active, count = {}, raw
    else:
        count = raw
    return {"whipsaw_crossovers": count, "whipsaw_raw_crossovers": raw,
            "whipsaw_reset_id": active.get("id", ""),
            "whipsaw_reset_after": active.get("after_session", "")}


def buy_confirmation_conditions(
    indicators: dict[str, Any] | None,
    params: StaticRuleParameters,
) -> dict[str, bool]:
    """Current hold conditions layered on the enabled base BUY conditions."""
    values = indicators if isinstance(indicators, dict) else {}
    try:
        ema_ok = float(values.get("buy_ema_fast")) > float(values.get("buy_ema_slow"))
    except (TypeError, ValueError):
        ema_ok = False
    try:
        rsi_ok = float(values.get("rsi")) > float(values.get("rsi_previous"))
    except (TypeError, ValueError):
        rsi_ok = False
    selected_ok = (
        (not params.buy_confirmation_require_ema or ema_ok)
        and (not params.buy_confirmation_require_rsi or rsi_ok)
    )
    return {"ema": ema_ok, "rsi": rsi_ok, "selected": selected_ok}


def advance_buy_confirmation(
    state: dict[str, Any] | None,
    *,
    raw_trigger: bool,
    indicators: dict[str, Any] | None,
    observed_at: datetime,
    exchange: str,
    params: StaticRuleParameters,
    working_dates: Iterable[str] | None = None,
    holidays: Iterable[str] | None = None,
    max_observation_gap_seconds: float | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Advance one BUY candidate using only active minutes of its exchange."""
    if not params.buy_confirmation_enabled:
        return {}, "BYPASS", {}
    if not (params.buy_confirmation_require_ema or params.buy_confirmation_require_rsi):
        return {}, "INVALID", {"reason": "BUY_CONFIRMATION_NO_CONDITION"}
    market = normalize_exchange(exchange)
    if not market:
        return {}, "INVALID", {"reason": "UNKNOWN_EXCHANGE"}
    current = dict(state or {})
    if current.get("updated_at") and max_observation_gap_seconds is not None:
        previous_observation = datetime.fromisoformat(str(current["updated_at"]))
        if active_trading_minutes(previous_observation, observed_at, market,
                                  working_dates=working_dates, holidays=holidays) * 60 > max_observation_gap_seconds:
            current = {}  # Unobserved downtime is not confirmation time.
    rule_signature = (
        f"{params.buy_confirmation_minutes}:"
        f"{int(params.buy_confirmation_require_ema)}:"
        f"{int(params.buy_confirmation_require_rsi)}"
    )
    if current and current.get("rule_signature") != rule_signature:
        current = {}
    started_now = False
    if not current.get("active"):
        if not raw_trigger:
            return {}, "IDLE", {}
        current = {
            "active": True,
            "started_at": observed_at.isoformat(),
            "exchange": market,
            "rule_signature": rule_signature,
        }
        started_now = True
    try:
        started_at = datetime.fromisoformat(str(current.get("started_at") or ""))
    except ValueError:
        return {}, "CANCELLED", {"reason": "BUY_CONFIRMATION_STATE_INVALID"}
    checks = buy_confirmation_conditions(indicators, params)
    held = active_trading_minutes(
        started_at, observed_at, market,
        working_dates=working_dates, holidays=holidays,
    )
    details = {
        "signal_time": started_at.isoformat(),
        "observed_time": observed_at.isoformat(),
        "minutes_held": min(float(params.buy_confirmation_minutes), max(0.0, held)),
        "minutes_required": params.buy_confirmation_minutes,
        "require_ema": params.buy_confirmation_require_ema,
        "require_rsi": params.buy_confirmation_require_rsi,
        "ema_ok": checks["ema"],
        "rsi_ok": checks["rsi"],
    }
    if not checks["selected"]:
        details["reason"] = "BUY_CONFIRMATION_BROKEN"
        return {}, "CANCELLED", details
    if held >= params.buy_confirmation_minutes and not started_now:
        details["confirmed_time"] = observed_at.isoformat()
        return {}, "CONFIRMED", details
    current["updated_at"] = observed_at.isoformat()
    return current, "WAITING", details




def entry_volume_snapshot(
    bars: list[dict[str, Any]],
    sessions: int = 20,
) -> dict[str, Any]:
    """Compare the current candle volume with completed prior sessions.

    In REALTIME the last daily candle is cumulative volume known at the current
    instant. Historical input only uses preceding candles, so LIVE/PAPER and
    intraday replay never consume future volume.
    """
    rows = [row for row in bars if isinstance(row, dict)]
    lookback = max(1, int(sessions or 20))
    if not rows:
        return {
            "ready": False,
            "current": 0.0,
            "average": 0.0,
            "ratio": 0.0,
            "history_count": 0,
            "sessions": lookback,
        }
    try:
        current = max(0.0, float(rows[-1].get("volume", 0.0) or 0.0))
    except (TypeError, ValueError):
        current = 0.0
    history: list[float] = []
    for row in rows[:-1]:
        try:
            volume = float(row.get("volume", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if volume > 0 and bool(row.get("closed", True)):
            history.append(volume)
    history = history[-lookback:]
    average = sum(history) / len(history) if history else 0.0
    ready = len(history) >= lookback and average > 0
    return {
        "ready": ready,
        "current": current,
        "average": average,
        "ratio": current / average if average > 0 else 0.0,
        "history_count": len(history),
        "sessions": lookback,
    }
