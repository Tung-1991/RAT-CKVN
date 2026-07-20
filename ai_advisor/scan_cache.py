# -*- coding: utf-8 -*-
"""Kho tổng hợp dữ liệu quét theo mã/ngày cho AI Advisor.

Chu kỳ 15 phút chỉ cập nhật bản ghi của ngày hiện tại. CHECK là nhánh báo cáo
độc lập: không sửa context, tín hiệu hoặc dữ liệu mà bộ đặt lệnh sử dụng.
"""
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime

import pandas as pd

import config
from ai_advisor import paths

logger = logging.getLogger("BotDaemon")

SCHEMA_VERSION = 2
SIGNAL_DEDUP_MINUTES = 30
WEEK_BARS = 5
_SESSION_WINDOWS = ((9 * 60, 11 * 60 + 30), (13 * 60, 14 * 60 + 45))
_IO_LOCK = threading.RLock()


def _f(value, nd=4):
    try:
        value = float(value)
        if pd.isna(value):
            return None
        return round(value, nd)
    except Exception:
        return None


def session_elapsed_fraction(now):
    minute = now.hour * 60 + now.minute
    total = sum(end - start for start, end in _SESSION_WINDOWS)
    elapsed = 0
    for start, end in _SESSION_WINDOWS:
        if minute >= end:
            elapsed += end - start
        elif minute > start:
            elapsed += minute - start
    return round(elapsed / total, 4) if total else 1.0


def pick_daily_df(dfs):
    for group in ("G0", "G1", "G2", "G3"):
        df = (dfs or {}).get(group)
        if df is None or df.empty or "time" not in df.columns or len(df) < 2:
            continue
        try:
            delta = (df["time"].iloc[-1] - df["time"].iloc[-2]).total_seconds()
            if delta >= 80000:
                return group, df
        except Exception:
            continue
    return None, None


def _compute_price_block(daily_df, current_price, now):
    empty = {
        "open": None, "high": None, "low": None, "close": None,
        "current": _f(current_price), "pct_1d": None, "pct_1w": None,
        "high_1w": None, "low_1w": None, "daily_bar_is_today": False,
    }
    if daily_df is None or daily_df.empty:
        return empty
    closes = daily_df["close"]
    try:
        last_bar_is_today = daily_df["time"].iloc[-1].date() == now.date()
    except Exception:
        last_bar_is_today = False
    prev_idx = -2 if last_bar_is_today and len(closes) >= 2 else -1
    previous_close = _f(closes.iloc[prev_idx])
    reference = _f(current_price) or _f(closes.iloc[-1])
    pct_1d = round((reference - previous_close) / previous_close * 100, 2) if reference is not None and previous_close else None
    week_idx = prev_idx - WEEK_BARS + 1
    week_close = _f(closes.iloc[week_idx]) if len(closes) >= abs(week_idx) else None
    pct_1w = round((reference - week_close) / week_close * 100, 2) if reference is not None and week_close else None
    tail = daily_df.tail(WEEK_BARS)
    last = daily_df.iloc[-1]
    return {
        "open": _f(last.get("open")), "high": _f(last.get("high")),
        "low": _f(last.get("low")), "close": _f(last.get("close")),
        "current": reference, "pct_1d": pct_1d, "pct_1w": pct_1w,
        "high_1w": _f(tail["high"].max()), "low_1w": _f(tail["low"].min()),
        "daily_bar_is_today": bool(last_bar_is_today),
    }


def _compute_volume_block(daily_df, market_open, now):
    if daily_df is None or daily_df.empty or "volume" not in daily_df.columns:
        return {"today": None, "avg20": None, "ratio": None, "projected_ratio": None,
                "trend_5d": None, "is_partial_bar": bool(market_open)}
    volumes = daily_df["volume"]
    try:
        last_bar_is_today = daily_df["time"].iloc[-1].date() == now.date()
    except Exception:
        last_bar_is_today = False
    today_volume = _f(volumes.iloc[-1], 0) if last_bar_is_today else None
    closed = volumes.iloc[:-1] if last_bar_is_today else volumes
    avg20 = _f(closed.tail(20).mean(), 0) if len(closed) else None
    ratio = round(today_volume / avg20, 2) if today_volume and avg20 else None
    partial = bool(market_open and last_bar_is_today)
    projected = None
    if partial and today_volume and avg20:
        projected = round((today_volume / max(session_elapsed_fraction(now), 0.1)) / avg20, 2)
    trend = None
    if len(closed) >= 10:
        recent = closed.tail(WEEK_BARS).mean()
        older = closed.tail(WEEK_BARS * 2).head(WEEK_BARS).mean()
        if older and not pd.isna(older):
            change = (recent - older) / older
            trend = "tăng" if change > 0.1 else ("giảm" if change < -0.1 else "đi ngang")
    return {"today": today_volume, "avg20": avg20, "ratio": ratio,
            "projected_ratio": projected, "trend_5d": trend, "is_partial_bar": partial}


def compute_snapshot(dfs, context, signal, now=None, symbol=None, settings=None):
    """Tạo mẫu cập nhật. Indicator báo cáo do CHECK engine trả về động."""
    from signals import check_engine

    now = now or datetime.now()
    context = context or {}
    market_open = bool(context.get("market_open", True))
    daily_group, daily_df = pick_daily_df(dfs)
    check = check_engine.evaluate(dfs, context, symbol=symbol, settings=settings)
    return {
        "price": _compute_price_block(daily_df, context.get("current_price"), now),
        "volume": _compute_volume_block(daily_df, market_open, now),
        "daily_group": daily_group,
        "bot": {
            "trend_G0": context.get("trend_G0"), "trend_G1": context.get("trend_G1"),
            "trend_G2": context.get("trend_G2"), "trend_G3": context.get("trend_G3"),
            "market_mode": context.get("market_mode"), "mode_source": context.get("mode_source"),
            "block_reason": context.get("block_reason"), "latest_signal": signal,
            "group_signals": context.get("group_signals"),
        },
        "check": check,
    }


def empty_cache():
    return {"schema_version": SCHEMA_VERSION, "updated_at": None, "symbols": {}}


def _day_entry(cache, symbol, day):
    node = cache.setdefault("symbols", {}).setdefault(symbol, {"days": {}})
    return node["days"].setdefault(day, {
        "samples": 0, "first_scan": None, "last_scan": None,
        "eod_final": False, "signals": [], "bot_signal_counts": {}, "check_segments": [],
    })


def _aggregate_metric(current, value, hhmm):
    if isinstance(value, bool):
        numeric = False
    else:
        numeric = isinstance(value, (int, float)) and not pd.isna(value)
    if numeric:
        value = float(value)
        if not current or current.get("kind") != "number":
            return {"kind": "number", "first": value, "min": value, "max": value,
                    "sum": value, "count": 1, "avg": value, "last": value}
        current["min"] = min(current["min"], value)
        current["max"] = max(current["max"], value)
        current["sum"] += value
        current["count"] += 1
        current["avg"] = round(current["sum"] / current["count"], 6)
        current["last"] = value
        return current
    if value is None:
        return current
    value = str(value)
    if not current or current.get("kind") != "state":
        return {"kind": "state", "first": value, "last": value, "changes": 0,
                "times": [{"time": hhmm, "value": value}]}
    if current.get("last") != value:
        current["changes"] += 1
        current["last"] = value
        current.setdefault("times", []).append({"time": hhmm, "value": value})
    return current


def _merge_check(entry, check, hhmm):
    if not isinstance(check, dict):
        return
    config_id = str(check.get("config_id") or "unknown")
    segments = entry.setdefault("check_segments", [])
    segment = segments[-1] if segments and segments[-1].get("config_id") == config_id else None
    if segment is None:
        segment = {"config_id": config_id, "first_scan": hhmm, "last_scan": hhmm,
                   "samples": 0, "groups": {}}
        segments.append(segment)
    segment["samples"] += 1
    segment["last_scan"] = hhmm
    for group, modules in (check.get("groups") or {}).items():
        group_node = segment["groups"].setdefault(group, {})
        for name, result in (modules or {}).items():
            module = group_node.setdefault(name, {
                "params": result.get("params", {}), "signal_counts": {},
                "latest_signal": 0, "metrics": {},
            })
            signal = int(result.get("signal") or 0)
            label = "BUY" if signal > 0 else ("SELL" if signal < 0 else "WAIT")
            module["signal_counts"][label] = module["signal_counts"].get(label, 0) + 1
            module["latest_signal"] = signal
            if result.get("error"):
                module["error"] = str(result["error"])
            for key, value in (result.get("metrics") or {}).items():
                module["metrics"][key] = _aggregate_metric(module["metrics"].get(key), value, hhmm)


def merge_sample(cache, sym, snapshot, now=None, eod=False):
    now = now or datetime.now()
    day, hhmm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    cache["schema_version"] = SCHEMA_VERSION
    entry = _day_entry(cache, sym, day)
    for key in ("price", "volume", "bot", "daily_group"):
        entry[key] = snapshot.get(key)
    latest_signal = (snapshot.get("bot") or {}).get("latest_signal")
    label = "BUY" if latest_signal == 1 else ("SELL" if latest_signal == -1 else "WAIT")
    counts = entry.setdefault("bot_signal_counts", {})
    counts[label] = counts.get(label, 0) + 1
    _merge_check(entry, snapshot.get("check"), hhmm)
    entry["samples"] += 1
    entry["first_scan"] = entry.get("first_scan") or hhmm
    entry["last_scan"] = hhmm
    if eod:
        entry["eod_final"] = True
    cache["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    return entry


def record_signal_event(cache, sym, side, context, now=None):
    now = now or datetime.now()
    day, hhmm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    entry = _day_entry(cache, sym, day)
    for event in reversed(entry["signals"]):
        if event.get("side") == side:
            try:
                previous = datetime.strptime(f"{day} {event['time']}", "%Y-%m-%d %H:%M")
                if (now - previous).total_seconds() < SIGNAL_DEDUP_MINUTES * 60:
                    return False
            except Exception:
                pass
            break
    entry["signals"].append({"time": hhmm, "side": side,
                             "mode": context.get("market_mode"),
                             "groups": context.get("group_signals"),
                             "note": context.get("block_reason")})
    cache["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    return True


def prune(cache, retention_days=None):
    keep = max(1, int(retention_days or getattr(config, "SCAN_SNAPSHOT_RETENTION_DAYS", 250)))
    for symbol in list(cache.get("symbols", {})):
        days = cache["symbols"][symbol].get("days", {})
        for day in sorted(days)[:-keep] if len(days) > keep else []:
            days.pop(day, None)
        if not days:
            cache["symbols"].pop(symbol, None)
    return cache


def derive_weekly(sym_node):
    buy = sell = 0
    for day_data in sym_node.get("days", {}).values():
        for event in day_data.get("signals", []):
            buy += event.get("side") == "BUY"
            sell += event.get("side") == "SELL"
    return {"buy": int(buy), "sell": int(sell)}


def load_cache(path=None):
    path = path or paths.scan_cache_path()
    try:
        with _IO_LOCK:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict) and isinstance(data.get("symbols"), dict):
                    data["schema_version"] = SCHEMA_VERSION
                    return data
    except Exception as exc:
        logger.warning("scan_cache: file hỏng, khởi tạo lại (%s)", exc)
    return empty_cache()


def save_cache(cache, path=None):
    path = path or paths.scan_cache_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with _IO_LOCK:
        for attempt in range(5):
            tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(cache, handle, indent=2, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
                return True
            except (PermissionError, OSError) as exc:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except OSError:
                    pass
                if attempt == 4:
                    logger.error("scan_cache: lỗi ghi sau 5 lần thử: %s", exc)
                time.sleep(0.05)
    return False


class ScanSnapshotRecorder:
    def __init__(self):
        self._cache = None
        self._cache_path = None
        self._dirty = False
        self._last_sample_ts = {}

    def _ensure_loaded(self):
        current_path = paths.scan_cache_path()
        if self._cache is None or self._cache_path != current_path:
            self._cache = load_cache(current_path)
            self._cache_path = current_path
            self._dirty = False
            self._last_sample_ts = {}

    def maybe_record(self, sym, dfs, context, signal, now=None):
        now = now or datetime.now()
        self._ensure_loaded()
        market_open = bool(context.get("market_open", True))
        if market_open and signal in (1, -1):
            side = "BUY" if signal == 1 else "SELL"
            if record_signal_event(self._cache, sym, side, context, now=now):
                self._dirty = True
        interval = float(getattr(config, "SCAN_SNAPSHOT_INTERVAL_MINUTES", 15)) * 60
        due = (time.time() - self._last_sample_ts.get(sym, 0.0)) >= interval
        day = now.strftime("%Y-%m-%d")
        entry = self._cache.get("symbols", {}).get(sym, {}).get("days", {}).get(day)
        if market_open and due:
            merge_sample(self._cache, sym, compute_snapshot(dfs, context, signal, now, sym), now)
            self._last_sample_ts[sym] = time.time()
            self._dirty = True
        elif not market_open and not (entry and entry.get("eod_final")):
            snapshot = compute_snapshot(dfs, context, signal, now, sym)
            if snapshot["price"].get("daily_bar_is_today"):
                merge_sample(self._cache, sym, snapshot, now, eod=True)
                self._last_sample_ts[sym] = time.time()
                self._dirty = True

    def flush(self):
        if self._cache is not None and self._dirty:
            prune(self._cache)
            if save_cache(self._cache, self._cache_path):
                self._dirty = False

    def finalize_closed_day(self, symbols=None, now=None):
        """Khóa bản ghi hôm nay sau 14:45; không gọi market API và không tạo mẫu mới."""
        now = now or datetime.now()
        if now.hour * 60 + now.minute < 14 * 60 + 45:
            return False
        self._ensure_loaded()
        day = now.strftime("%Y-%m-%d")
        allowed = {str(symbol).upper() for symbol in (symbols or [])}
        changed = False
        for symbol, node in self._cache.get("symbols", {}).items():
            if allowed and str(symbol).upper() not in allowed:
                continue
            entry = node.get("days", {}).get(day)
            if entry and not entry.get("eod_final"):
                entry["eod_final"] = True
                changed = True
        if changed:
            self._cache["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
            self._dirty = True
        return changed

    def status(self):
        self._ensure_loaded()
        symbols = self._cache.get("symbols", {})
        return {"updated_at": self._cache.get("updated_at"), "symbols": len(symbols),
                "days": max((len(node.get("days", {})) for node in symbols.values()), default=0)}


recorder = ScanSnapshotRecorder()
