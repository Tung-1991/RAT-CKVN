"""EMA evidence and bounded historical lookback, independent of execution."""
from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite

from .market import VN_TZ, exchange_close_minute, is_working_day


def lookback_start(now, count, working_dates=None, holidays=None):
    """Midnight of the Xth prior trading session; never count today or holidays."""
    day = now.astimezone(VN_TZ).date()
    selected = 0
    for _ in range(1500):
        day -= timedelta(days=1)
        if is_working_day(day, working_dates, holidays):
            selected += 1
            if selected == count:
                return datetime.combine(day, datetime.min.time(), VN_TZ)
    return None


def recent_session_start(now, count, exchange, *, working_dates=None, holidays=None, closed=False):
    """Start of exactly X recent sessions, including the current one once open."""
    from .market import exchange_sessions
    boundary = exchange_close_minute(exchange) if closed else exchange_sessions(exchange)[0][0]
    current = is_working_day(now.date(), working_dates, holidays) and now.hour * 60 + now.minute >= boundary
    prior = count - int(current)
    return (lookback_start(now, prior, working_dates, holidays) if prior else
            now.replace(hour=0, minute=0, second=0, microsecond=0))


def adopt_history_cross(row, candidate):
    """Merge verified history without replaying a consumed or rounded live event."""
    row, candidate = dict(row), dict(candidate or {})
    if not candidate:
        return row
    def stamp(item, key="cross_at"):
        try:
            at = datetime.fromisoformat(str(item[key]))
            return (at.replace(tzinfo=VN_TZ) if at.tzinfo is None else at.astimezone(VN_TZ)).timestamp()
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
    at = stamp(candidate)
    if at is None:
        return row
    previous = row if row.get("cross_id") else row.get("lookback_cross") or {}
    prior_at = stamp(previous)
    if prior_at is not None and at <= (int(prior_at) // 60 + 1) * 60:
        # Keep the original ID/consumption when one tick event is reconstructed
        # at the close of its minute, or the scan only found an older event.
        return row
    used_at = stamp(row, "used_at")
    if used_at is not None and at <= (int(used_at) // 60 + 1) * 60:
        candidate["used"] = True
    elif row.get("used") and used_at is None:
        candidate["used"] = True  # Old consumption without a timestamp is ambiguous.
    for key in _CROSS_KEYS:
        row.pop(key, None)
    row.pop("cross_source", None)
    row["lookback_cross"] = candidate
    return row


_CROSS_KEYS = ("cross_id", "cross_at", "cross_timestamp", "previous_fast", "previous_slow", "used")


def consume_cross(row, *, now, order_id="", side="BUY"):
    """Commit an actual fill; keep lifetime audit/IDs, restart the VA scan count."""
    row = {**row, "used": True, "used_at": now.isoformat(),
           "used_order_id": str(order_id), "used_side": side, "used_phase": "FILLED"}
    if row.get("valid"):
        row["state"] = "SESSION_USED"
    if row.get("mode", "VA") == "VA":
        row["va_count_reset"] = {"at": now.isoformat(), "up": int(row.get("up_count", 0)),
                                 "down": int(row.get("down_count", 0)), "cross_id": row.get("cross_id", "")}
    return row


def va_scan_counts(row):
    """Crossings since admission or the latest actual fill, never a session window."""
    reset = row.get("va_count_reset") or {}
    if reset:
        return {"up": max(0, int(row.get("up_count", 0)) - int(reset["up"])),
                "down": max(0, int(row.get("down_count", 0)) - int(reset["down"])),
                "from": reset["at"]}
    if row.get("used") or row.get("counts_unknown"):
        # Old runtimes did not save counters at approval. A lifetime total is
        # not evidence of the number of crossings since that BUY.
        return {"up": None, "down": None, "from": ""}
    historical = bool(row.get("va_lookback_enabled"))
    up, down = crossing_totals(row)
    return {"up": up, "down": down,
            "from": (row.get("lookback_started_at") if historical else None) or row.get("started_at", "")}


def _local_day(value):
    try:
        at = datetime.fromisoformat(str(value))
        return (at.replace(tzinfo=VN_TZ) if at.tzinfo is None else at.astimezone(VN_TZ)).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def memory_day_counts(row, *, now):
    """Today's observed flips, independently of the retained BUY evidence."""
    today = now.astimezone(VN_TZ).date().isoformat()
    result = {"day": today, "up": None, "down": None, "from": "", "partial": False}
    day = _local_day(row.get("daily_count_day"))
    if day == today:
        try:
            return {**result, "up": max(0, int(row["daily_up_count"])),
                    "down": max(0, int(row["daily_down_count"])),
                    "from": row.get("daily_count_from", ""),
                    "partial": bool(row.get("daily_count_partial"))}
        except (KeyError, TypeError, ValueError, OverflowError):
            return result
    if day and day < today:
        return {**result, "up": 0, "down": 0}
    if day:
        return result
    started = _local_day(row.get("started_at") or (row.get("baseline") or {}).get("at"))
    observed = _local_day(row.get("observed_at"))
    if started == observed == today:
        # A legacy total is safe only when all admitted samples are from today.
        try:
            return {**result, "up": max(0, int(row.get("up_count", 0))),
                    "down": max(0, int(row.get("down_count", 0))),
                    "from": row.get("started_at") or (row.get("baseline") or {}).get("at", "")}
        except (TypeError, ValueError, OverflowError):
            return result
    if not row.get("initialized") or (observed and observed < today):
        return {**result, "up": 0, "down": 0}
    if row.get("up_count", 0) == row.get("down_count", 0) == 0:
        return {**result, "up": 0, "down": 0}
    return result  # A legacy multi-day total cannot invent today's count.




def seed_lookback(row, observations, *, start, now, full_window=False, **args):
    """Keep pre-admission evidence separate so VA and consumed live IDs survive toggles."""
    row = dict(row or {})
    history = {"tracking_version": 2, "watch_id": row.get("watch_id", str(now.timestamp())),
               "initialized": False, "up_count": 0, "down_count": 0}
    for at, marks in observations:
        history = advance_memory(history, marks, now=at, **args)
        if not history.get("current_ready"):
            return {**row, "lookback_ready": False}
    cross = {key: history[key] for key in _CROSS_KEYS if key in history}
    if cross:
        cross["cross_id"] = f"EMA:HISTORY:{history['watch_id']}:{args['pair']}:{cross['cross_timestamp']}"
    result = {**row, "lookback_ready": True, "lookback_started_at": start.isoformat(),
            "lookback_up_count": history.get("up_count", 0),
            "lookback_down_count": history.get("down_count", 0),
            "lookback_last_down_at": history.get("last_down_at", ""),
            "lookback_count_days": history.get("count_days", {}), "lookback_cross": cross}
    # Merge against the original event before replacing the historical slot.
    merged = adopt_history_cross(row, cross)
    for key in _CROSS_KEYS:
        if key in merged:
            result[key] = merged[key]
        else:
            result.pop(key, None)
    if "cross_source" in merged:
        result["cross_source"] = merged["cross_source"]
    else:
        result.pop("cross_source", None)
    result["lookback_cross"] = merged.get("lookback_cross", cross)
    if full_window:
        live_days = dict(row.get("count_days") or {})
        day = _local_day(row.get("daily_count_day"))
        if day:
            live_days[day] = {"up": row.get("daily_up_count", 0), "down": row.get("daily_down_count", 0)}
        result.update(lookback_full_window=True,
                      lookback_live_days=live_days,
                      lookback_live_counts={"up": int(row.get("up_count", 0)),
                                            "down": int(row.get("down_count", 0))})
    return result


def crossing_totals(row):
    """A recovered full window plus later live events, without counting both twice."""
    historical = row.get("mode") == "SESSIONS" or row.get("va_lookback_enabled")
    snapshot = row.get("lookback_live_counts") or {}
    return tuple(int(row.get("lookback_" + name + "_count", 0)) +
                 max(0, int(row.get(name + "_count", 0)) - int(snapshot.get(name, 0)))
                 if historical and row.get("lookback_full_window") else
                 int(row.get(name + "_count", 0)) + (int(row.get("lookback_" + name + "_count", 0)) if historical else 0)
                 for name in ("up", "down"))


def memory_deadline(cross_at, count, exchange, working_dates=None, holidays=None):
    start = datetime.fromisoformat(cross_at).astimezone(VN_TZ).date()
    selected = []
    day = start
    for _ in range(1500):
        if is_working_day(day, working_dates, holidays):
            selected.append(day.isoformat())
            if len(selected) == count:
                end = datetime.combine(day, datetime.min.time(), VN_TZ)
                return (end + timedelta(minutes=exchange_close_minute(exchange))).timestamp(), selected
        day += timedelta(days=1)
    return 0.0, []  # An incomplete explicit calendar cannot invent a deadline.


def refresh_memory(row, *, now, mode, sessions, exchange, working_dates=None, holidays=None,
                   va_lookback_enabled=False):
    row = dict(row or {})
    if row.get("cross_source") in {"HISTORY", "VA_HISTORY"}:
        # Preserve consumption even if the UI switches to VA and back.
        row["lookback_cross"] = {key: row[key] for key in _CROSS_KEYS if key in row}
        for key in _CROSS_KEYS:
            row.pop(key, None)
        row.pop("cross_source", None)
    historical = mode == "SESSIONS" or (mode == "VA" and va_lookback_enabled)
    if historical and not row.get("cross_id") and row.get("lookback_cross"):
        row.update(row["lookback_cross"],
                   cross_source="HISTORY" if mode == "SESSIONS" else "VA_HISTORY")
    expires, dates = (0.0, [])
    if mode == "SESSIONS" and row.get("cross_at"):
        expires, dates = memory_deadline(row["cross_at"], sessions, exchange, working_dates, holidays)
    expired = bool(expires and now.timestamp() >= expires)
    calendar_ready = mode == "VA" or not row.get("cross_id") or bool(expires)
    ready = bool(row.get("initialized") and row.get("current_ready") and calendar_ready
                 and row.get("watch_active", True)
                  and (not historical or row.get("lookback_ready") is not False
                      or row.get("cross_source") == "LIVE"))
    above = row.get("current_fast", 0) > row.get("current_slow", 0)
    valid = bool(ready and row.get("cross_id") and not expired and above)
    used = bool(row.get("used"))
    state = ("UNKNOWN" if not ready else "EXPIRED" if expired else
             "WAIT_UP" if not above else "SESSION_USED" if used and row.get("cross_id") else "SESSION_ACTIVE" if valid else
             "WAIT_UP" if not above else "WAIT_DOWN")
    return {**row, "required": True, "session": True, "tracking_version": 2,
             "mode": mode, "sessions": sessions,
             "va_lookback_enabled": bool(va_lookback_enabled), "expires_at": expires,
             "va_lookback_active": bool(mode == "VA" and va_lookback_enabled),
            "remaining_sessions": sum(day >= now.date().isoformat() for day in dates) if not expired else 0,
            "expiry_sessions": dates, "ready": ready, "valid": valid, "state": state,
            "day": now.date().isoformat()}


def advance_memory(row, current, *, now, pair, mode, sessions, exchange,
                   working_dates=None, holidays=None, va_lookback_enabled=False):
    row = dict(row or {})
    if row.get('tracking_version') == 2 and row.get('cross_id') and not row.get('cross_source'):
        row['cross_source'] = 'LIVE'  # Version 2 before lookback recorded only admitted live crossings.
    try:
        fast, slow = float(current.get("buy_ema_fast")), float(current.get("buy_ema_slow"))
        ready = current.get("signal_ready") is not False and isfinite(fast) and isfinite(slow)
    except (TypeError, ValueError, OverflowError):
        ready = False
    if not ready:
        return {**row, "current_ready": False, "ready": False, "valid": False, "state": "UNKNOWN"}
    if row.get("profile") not in {None, "", pair} or not row.get("tracking_version") == 2:
        row = {"tracking_version": 2, "profile": pair, "watch_id": f"{pair}:{now.timestamp()}",
               "started_at": now.isoformat(), "started_at_epoch": now.timestamp(),
               "up_count": 0, "down_count": 0, "initialized": False}
    if row.get("initialized") and now.timestamp() <= float(row.get("observed_at_epoch", 0)):
        return refresh_memory(row, now=now, mode=mode, sessions=sessions, exchange=exchange,
                              working_dates=working_dates, holidays=holidays,
                              va_lookback_enabled=va_lookback_enabled)
    count_days = dict(row.get("count_days") or {})
    old_day = _local_day(row.get("daily_count_day"))
    if old_day:
        count_days[old_day] = {"up": row.get("daily_up_count", 0), "down": row.get("daily_down_count", 0),
                               "partial": bool(row.get("daily_count_partial"))}
    daily = memory_day_counts(row, now=now)
    row.update(daily_count_day=daily["day"], daily_up_count=daily["up"] or 0,
               daily_down_count=daily["down"] or 0,
               daily_count_from=daily["from"] or now.isoformat(),
               daily_count_partial=daily["partial"] or daily["up"] is None)
    row["profile"] = pair
    events = [event for event in row.get("recent_cross_events", [])
              if 0 <= now.timestamp() - float(event.get("timestamp", 0)) <= 180]
    previous_fast, previous_slow = row.get("current_fast"), row.get("current_slow")
    if row.get("initialized") and now.timestamp() > float(row.get("observed_at_epoch", 0)):
        # Count strict sign changes. Touching equality is neutral: it cannot
        # generate multiple crosses by bouncing on the same boundary.
        previous_relation = int(row.get("last_relation", 0))
        relation = 1 if fast > slow else -1 if fast < slow else 0
        if relation == 1 and previous_relation == -1:
            row["up_count"] = int(row.get("up_count", 0)) + 1
            row["daily_up_count"] += 1
            row.update(cross_at=now.isoformat(), cross_timestamp=now.timestamp(), used=False,
                       cross_id=f"EMA:{row['watch_id']}:{row['up_count']}:{now.timestamp()}",
                       previous_fast=previous_fast, previous_slow=previous_slow)
            row["cross_source"] = "LIVE"
            events.append({"timestamp": now.timestamp(), "direction": "UP"})
            row.pop("used_at", None)
            row.pop("used_order_id", None)
            row.pop("used_phase", None)
            row.pop("used_side", None)
        elif relation == -1 and previous_relation == 1:
            row["down_count"] = int(row.get("down_count", 0)) + 1
            row["daily_down_count"] += 1
            row["last_down_at"] = now.isoformat()
            events.append({"timestamp": now.timestamp(), "direction": "DOWN"})
        if relation:
            row["last_relation"] = relation
    else:
        row["last_relation"] = 1 if fast > slow else -1 if fast < slow else 0
        row["baseline"] = {"at": now.isoformat(), "buy_ema_fast": fast, "buy_ema_slow": slow}
    row.update(initialized=True, current_ready=True, current_fast=float(fast), current_slow=float(slow),
               observed_at_epoch=now.timestamp(), observed_at=now.isoformat(), recent_cross_events=events)
    count_days[daily["day"]] = {"up": row["daily_up_count"], "down": row["daily_down_count"],
                                "partial": row["daily_count_partial"]}
    # Only the display ledger is bounded; retained VA evidence and used IDs are unchanged.
    eligible_days = [day for day in sorted(count_days) if _local_day(day) == day and
                     (day == daily["day"] or is_working_day(datetime.fromisoformat(day).date(), working_dates, holidays))]
    row["count_days"] = {day: count_days[day] for day in eligible_days[-251:]}
    return refresh_memory(row, now=now, mode=mode, sessions=sessions, exchange=exchange,
                          working_dates=working_dates, holidays=holidays,
                          va_lookback_enabled=va_lookback_enabled)
