"""Recover admitted EMA observations and optional prior-session crossings."""
from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path

from .business import ema
from .market import VN_TZ, exchange_sessions
MAX_DECISION_AGE = 20.0


def merge_ranges(ranges):
    merged = []
    for left, right in sorted(ranges):
        if right <= left:
            continue
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(right, merged[-1][1])
        else:
            merged.append([left, right])
    return merged


def missing_ranges(targets, covered):
    missing = []
    for start, end in targets:
        cursor = start
        for left, right in merge_ranges(covered):
            if right <= cursor or left >= end:
                continue
            if left > cursor:
                missing.append([cursor, min(left, end)])
            cursor = max(cursor, right)
        if cursor < end:
            missing.append([cursor, end])
    return missing


class HistoryCache:
    """Read-only minute-history client and its SQLite cache state."""
    def __init__(self, state, client):
        self.store, self.client = state, client


class SessionCrossService:
    """Durable memory from admission; closed minutes recover only unseen gaps."""

    def __init__(self, cache, rule_state):
        self.cache, self.rule_state = cache, rule_state
        self.max_observation_gap = MAX_DECISION_AGE
        raw = cache.store.read()
        self.recovered = raw.get("cross_recovery", {}) if isinstance(raw, dict) else {}

    def _lookback(self, row, symbol, bars, params, now, args, observation_mode, recover=True, current=None):
        from .business import indicator_snapshot
        from .ema_memory import recent_session_start, seed_lookback
        from .market import exchange_close_minute, is_working_day
        if params.buy_ema_cross_mode != "SESSIONS" and not (
                params.buy_ema_cross_mode == "VA" and params.buy_ema_va_lookback_enabled):
            return row
        if row.get("tracking_version") != 2:
            row = {"tracking_version": 2, "watch_id": f"{args['pair']}:{now.timestamp()}",
                   "started_at": now.isoformat(), "started_at_epoch": now.timestamp(),
                   "initialized": False, "up_count": 0, "down_count": 0}
        # Rebuild a rolling window once per session, also repairing runtimes
        # whose old forward-only calendar silently skipped past observations.
        key = f"RECENT:{args['pair']}:{params.buy_ema_cross_sessions}:{observation_mode}:{params.buy_ema_cross_mode}:{now.date()}"
        activated = (params.buy_ema_cross_mode != "VA" or row.get("va_lookback_active") is True)
        if row.get("lookback_key") == key and row.get("lookback_ready") and activated:
            return row
        row = dict(row)
        if row.get("lookback_key") != key or not activated:
            row.update(lookback_key=key, lookback_requested_at=now.isoformat(),
                       lookback_ready=False,
                       lookback_up_count=0, lookback_down_count=0, lookback_last_down_at="")
        start = recent_session_start(now, params.buy_ema_cross_sessions, args["exchange"],
                                     working_dates=args.get("working_dates"), holidays=args.get("holidays"),
                                     closed=observation_mode == "CLOSED")
        if start is None:
            return {**row, "lookback_ready": False}
        row["lookback_anchor_at"] = now.isoformat()
        baseline = row.get("baseline") or {}
        baseline_at = datetime.fromisoformat(baseline['at']) if baseline.get('at') else None
        last = float(row.get("observed_at_epoch", 0) or 0)
        cutoff = min(now.timestamp(), last) if row.get("initialized") and last else now.timestamp()
        if cutoff <= start.timestamp():
            return {**row, "lookback_ready": True, "lookback_started_at": start.isoformat(),
                    "lookback_up_count": 0, "lookback_down_count": 0, "lookback_cross": {},
                    "lookback_last_down_at": ""}
        prior = [bar for bar in bars if bool(bar.get("closed", True))
                 and datetime.fromtimestamp(float(bar["time"]), VN_TZ).date() < start.date()]
        if len(prior) < params.buy_ema_slow:
            return {**row, 'lookback_ready': False}
        marks = indicator_snapshot(prior, params.buy_ema_fast, params.buy_ema_slow, params.rsi_period)
        observations = [(start - timedelta(microseconds=1), marks)]
        end = datetime.fromtimestamp(cutoff, VN_TZ)
        if observation_mode == "CLOSED":
            for index, bar in enumerate(bars):
                day = datetime.fromtimestamp(float(bar["time"]), VN_TZ).date()
                at = datetime.combine(day, datetime.min.time(), VN_TZ) + timedelta(minutes=exchange_close_minute(args['exchange']))
                if (bool(bar.get("closed", True)) and is_working_day(day,args.get('working_dates'),args.get('holidays'))
                        and start.timestamp() <= at.timestamp() < cutoff):
                    observations.append((at, indicator_snapshot(bars[:index+1], params.buy_ema_fast,
                                                                 params.buy_ema_slow, params.rsi_period)))
        else:
            points, ready = self._samples(symbol, start.timestamp(), end, args['exchange'],
                                          args.get('working_dates'), args.get('holidays'), checked_at=now) if recover else ([], False)
            if not ready:
                return {**row, "lookback_ready": False}
            for stamp, price in points:
                if stamp >= cutoff:
                    continue  # The fresh observation owns the current boundary.
                at = datetime.fromtimestamp(stamp, VN_TZ)
                marks, _ = self._marks(bars, price, at.date(), params)
                observations.append((at, marks or {}))
        if baseline_at and start.timestamp() <= baseline_at.timestamp() <= cutoff:
            observations.append((baseline_at, baseline))
        if row.get("initialized") and last and start.timestamp() <= last <= cutoff:
            observations.append((datetime.fromtimestamp(last, VN_TZ),
                                 {"buy_ema_fast": row["current_fast"], "buy_ema_slow": row["current_slow"]}))
        elif current is not None:
            observations.append((now,current))
        observations = sorted(dict(observations).items())  # Actual baseline/current owns equal-time boundaries.
        seeded = seed_lookback(row, observations, start=start, now=now, full_window=True, **args)
        if seeded.get("lookback_ready") and not row.get("initialized"):
            # Compare the first fresh quote with the last verified historical
            # sign, so an opening/current-minute cross is not missed.
            at, marks = observations[-1]
            fast, slow = marks['buy_ema_fast'], marks['buy_ema_slow']
            seeded.update(initialized=True, current_ready=True, current_fast=fast, current_slow=slow,
                          last_relation=1 if fast > slow else -1 if fast < slow else 0,
                          observed_at_epoch=at.timestamp(), observed_at=at.isoformat(), profile=args['pair'])
            if current is not None:
                seeded['baseline'] = {'at':now.isoformat(),'buy_ema_fast':fast,'buy_ema_slow':slow}
        return seeded

    def observe_closed(self, symbol, stream, bars, params, now, exchange, *, working_dates=None, holidays=None):
        """CLOSED counts completed daily observations, with bounded optional lookback."""
        from .business import indicator_snapshot
        from .ema_memory import advance_memory, refresh_memory
        from .market import exchange_close_minute, history_working_dates
        working_dates = history_working_dates(working_dates, bars, now)
        row = self.rule_state.session_cross(symbol, stream)
        if row.get("observation_mode") not in {None, "CLOSED"}:
            row["profile"] = "RESET:MODE"
        args = dict(pair=f"{params.buy_ema_fast}/{params.buy_ema_slow}", mode=params.buy_ema_cross_mode,
                    sessions=params.buy_ema_cross_sessions, exchange=exchange,
                     working_dates=working_dates, holidays=holidays,
                     va_lookback_enabled=params.buy_ema_va_lookback_enabled)
        completed = [bar for bar in bars if bool(bar.get("closed", True))]
        def marks(values):
            return indicator_snapshot(values, params.buy_ema_fast, params.buy_ema_slow, params.rsi_period)
        if row.get("profile") not in {None, "", args["pair"]}:
            row = advance_memory(row, marks(completed), now=now, **args)
        row = self._lookback(row, symbol, completed, params, now, args, "CLOSED")
        if not row.get("initialized"):
            row = advance_memory(row, marks(completed), now=now, **args)
        else:
            for index, bar in enumerate(completed):
                day = datetime.fromtimestamp(float(bar["time"]), VN_TZ).date()
                closed_at = datetime.combine(day, datetime.min.time(), VN_TZ) + timedelta(minutes=exchange_close_minute(exchange))
                if float(row.get("observed_at_epoch", 0)) < closed_at.timestamp() <= now.timestamp():
                    row = advance_memory(row, marks(completed[:index+1]), now=closed_at, **args)
        row = refresh_memory(row, now=now, **{key: value for key,value in args.items() if key != "pair"})
        row["exchange"] = exchange
        row["observation_mode"] = "CLOSED"
        return self.rule_state.save_session_cross(symbol, stream, row)

    def _samples(self, symbol, start, now, exchange, working_dates, holidays, *, checked_at=None):
        from .market import is_working_day
        row = self.recovered.setdefault(symbol, {"ranges": [], "prices": {}, "retry_at": 0})
        checked_at = checked_at or now
        targets = []
        day = datetime.fromtimestamp(start, VN_TZ).date()
        while day <= now.date():
            if is_working_day(day, working_dates, holidays):
                midnight = datetime.combine(day, datetime.min.time(), VN_TZ).timestamp()
                for left, right, _ in exchange_sessions(exchange):
                    lo = max(int(start) // 60 * 60, int(midnight + left * 60))
                    hi = min(int(now.timestamp()) // 60 * 60, int(midnight + right * 60))
                    if hi > lo:
                        targets.append([lo, hi])
            day += timedelta(days=1)
        gaps = missing_ranges(targets, row["ranges"])
        if gaps and checked_at.timestamp() < row.get("retry_at", 0):
            return [], False
        for left, right in gaps:
            try:
                data = self.cache.client.get_ohlc(symbol, "1", left, right - 1)
                if not isinstance(data, dict) or data.get("s", "ok") not in {"ok", "no_data"}:
                    raise ValueError("MINUTE_HISTORY_UNAVAILABLE")
                keys = ("t", "o", "h", "l", "c", "v")
                if data.get('s') == 'no_data':
                    data = {**data, **{key:data.get(key,[]) for key in keys}}
                if any(not isinstance(data.get(key), list) for key in keys):
                    raise ValueError("MINUTE_HISTORY_UNAVAILABLE")
                if any(len(data.get(key, [])) != len(data.get("t", [])) for key in keys):
                    raise ValueError("MINUTE_HISTORY_INCOMPLETE")
                for stamp, price in zip(data.get("t", []), data.get("c", [])):
                    stamp, price = int(float(stamp)), float(price)
                    if stamp % 60 or not isfinite(price) or price <= 0:
                        raise ValueError("MINUTE_HISTORY_INVALID")
                    if left <= stamp < right:
                        row["prices"][str(stamp)] = price
                row["ranges"] = merge_ranges([*row["ranges"], [left, right]])
                row["retry_at"] = 0
            except Exception:
                row["retry_at"] = checked_at.timestamp() + 60
                raw = self.cache.store.read()
                self.cache.store.write({**raw, "cross_recovery": self.recovered})
                return [], False
        if gaps:
            raw = self.cache.store.read()
            self.cache.store.write({**raw, "cross_recovery": self.recovered})
        return sorted((int(stamp) + 60, price) for stamp, price in row["prices"].items()
                      if start < int(stamp) + 60 <= now.timestamp()), True

    @staticmethod
    def _marks(bars, price, day, params):
        history = []
        for bar in bars:
            try:
                if datetime.fromtimestamp(float(bar["time"]), VN_TZ).date() < day:
                    value = float(bar["close"])
                    if isfinite(value) and value > 0:
                        history.append((float(bar["time"]), value))
            except (KeyError, ValueError, TypeError, OverflowError, OSError):
                continue
        values = [price for _, price in sorted(dict(history).items())]
        if len(values) < params.buy_ema_slow:
            return None, None
        fast = ema(values, params.buy_ema_fast)[-1]
        slow = ema(values, params.buy_ema_slow)[-1]
        a, b = 2 / (params.buy_ema_fast + 1), 2 / (params.buy_ema_slow + 1)
        threshold = (slow * (1 - b) - fast * (1 - a)) / (a - b)
        return {"buy_ema_fast": fast + a * (price - fast),
                "buy_ema_slow": slow + b * (price - slow)}, threshold

    def observe(self, symbol, stream, bars, indicators, params, now, exchange, *,
                recover=True, working_dates=None, holidays=None):
        from .ema_memory import advance_memory
        now = now.astimezone(VN_TZ)
        row = self.rule_state.session_cross(symbol, stream)
        from .market import history_working_dates
        working_dates = history_working_dates(working_dates, bars, now)
        if row.get("tracking_version") != 2:
            row = {}
        if row.get("watch_active") is False:
            return {**row, "valid": False, "ready": False, "state": "UNKNOWN"}
        if row.get("observation_mode") not in {None, "REALTIME"}:
            row["profile"] = "RESET:MODE"
        args = dict(pair=f"{params.buy_ema_fast}/{params.buy_ema_slow}",
                    mode=params.buy_ema_cross_mode, sessions=params.buy_ema_cross_sessions,
                     exchange=exchange, working_dates=working_dates, holidays=holidays,
                     va_lookback_enabled=params.buy_ema_va_lookback_enabled)
        if row.get("profile") not in {None, "", args["pair"]}:
            # A changed pair starts a new baseline now, not in recovered history.
            row = advance_memory(row, indicators, now=now, **args)
        row = self._lookback(row, symbol, bars, params, now, args, "REALTIME", recover, current=indicators)
        last = float(row.get("observed_at_epoch", 0))
        if row.get("initialized") and now.timestamp() - last > self.max_observation_gap:
            points, ready = self._samples(symbol, last, now, exchange, working_dates, holidays) if recover else ([], False)
            if not ready:
                return self.rule_state.save_session_cross(symbol, stream,
                    {**row, "current_ready": False, "ready": False, "valid": False, "state": "UNKNOWN"})
            for stamp, price in points:
                if stamp >= now.timestamp():
                    # The current fresh observation owns this exact boundary.
                    continue
                when = datetime.fromtimestamp(stamp, VN_TZ)
                marks, _ = self._marks(bars, price, when.date(), params)
                if marks is None:
                    return self.rule_state.save_session_cross(symbol, stream,
                        {**row, "current_ready": False, "ready": False, "valid": False, "state": "UNKNOWN"})
                row = advance_memory(row, marks, now=when, **args)
        row = advance_memory(row, indicators, now=now, **args)
        _, threshold = self._marks(bars, float(bars[-1]["close"]), now.date(), params) if bars else (None, None)
        row.update(threshold_price=threshold if threshold is not None else 1e30, exchange=exchange, observation_mode="REALTIME")
        if threshold is None or float(bars[-1]["close"]) <= threshold:
            row.update(valid=False, state="WAIT_UP" if row.get("ready") else "UNKNOWN")
        return self.rule_state.save_session_cross(symbol, stream, row)
