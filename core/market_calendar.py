# -*- coding: utf-8 -*-
"""Lịch giao dịch DNSE có cache đĩa và các ngày né ENTRY VN30F."""
from __future__ import annotations

import calendar
import copy
import json
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

import config


DEFAULT_SETTINGS = {
    "use_dnse_working_dates": True,
    "manual_closed_dates": [],
    "avoid_vn30_expiry_entry": False,
    "avoid_vn30_rebalance_entry": False,
    "vn30_rebalance_dates": [],
}

_LOCK = threading.RLock()
_CACHE_MEMORY = {"path": None, "mtime": None, "data": None}


def _market_now() -> datetime:
    offset = float(getattr(config, "MARKET_HOURS_UTC_OFFSET", 7) or 7)
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=offset)


def cache_path() -> str:
    return str(getattr(config, "MARKET_CALENDAR_CACHE_FILE", "data/market_calendar_cache.json"))


def _date_value(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def normalize_dates(values: Optional[Iterable]) -> list[str]:
    result = []
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = _date_value(text).strftime("%Y-%m-%d")
        if normalized not in result:
            result.append(normalized)
    return sorted(result)


def parse_date_text(text: str) -> list[str]:
    tokens = str(text or "").replace(";", ",").replace("\n", ",").split(",")
    invalid = []
    valid = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        try:
            valid.append(_date_value(token).strftime("%Y-%m-%d"))
        except Exception:
            invalid.append(token)
    if invalid:
        raise ValueError("Ngày sai định dạng YYYY-MM-DD: " + ", ".join(invalid))
    return normalize_dates(valid)


def normalize_settings(raw=None) -> dict:
    result = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        result.update(raw)
    result["use_dnse_working_dates"] = bool(result.get("use_dnse_working_dates", True))
    result["avoid_vn30_expiry_entry"] = bool(result.get("avoid_vn30_expiry_entry", False))
    result["avoid_vn30_rebalance_entry"] = bool(result.get("avoid_vn30_rebalance_entry", False))
    for key in ("manual_closed_dates", "vn30_rebalance_dates"):
        try:
            result[key] = normalize_dates(result.get(key, []))
        except Exception:
            result[key] = []
    return result


def load_settings() -> dict:
    try:
        from core.storage_manager import get_brain_settings_for_symbol

        return normalize_settings(get_brain_settings_for_symbol().get("market_calendar", {}))
    except Exception:
        return normalize_settings()


def empty_cache() -> dict:
    return {
        "version": 1,
        "fetched_at": None,
        "last_attempt_date": None,
        "coverage_start": None,
        "coverage_end": None,
        "working_dates": [],
        "last_error": None,
    }


def load_cache(path: Optional[str] = None) -> dict:
    target = path or cache_path()
    try:
        with _LOCK:
            if os.path.isfile(target):
                mtime = os.path.getmtime(target)
                if (
                    _CACHE_MEMORY.get("path") == target
                    and _CACHE_MEMORY.get("mtime") == mtime
                    and isinstance(_CACHE_MEMORY.get("data"), dict)
                ):
                    return copy.deepcopy(_CACHE_MEMORY["data"])
                with open(target, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    merged = empty_cache()
                    merged.update(data)
                    merged["working_dates"] = normalize_dates(merged.get("working_dates", []))
                    _CACHE_MEMORY.update({"path": target, "mtime": mtime, "data": copy.deepcopy(merged)})
                    return copy.deepcopy(merged)
    except Exception:
        pass
    return empty_cache()


def save_cache(data: dict, path: Optional[str] = None) -> bool:
    target = path or cache_path()
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with _LOCK:
        for attempt in range(5):
            tmp = f"{target}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, target)
                _CACHE_MEMORY.update({
                    "path": target,
                    "mtime": os.path.getmtime(target),
                    "data": copy.deepcopy(data),
                })
                return True
            except (PermissionError, OSError):
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except OSError:
                    pass
                if attempt < 4:
                    time.sleep(0.05)
    return False


def cache_covers(day, cache=None) -> bool:
    day_text = _date_value(day).strftime("%Y-%m-%d")
    cache = cache or load_cache()
    start, end = cache.get("coverage_start"), cache.get("coverage_end")
    return bool(start and end and str(start) <= day_text <= str(end))


def refresh_from_dnse(
    provider: Callable[[], Iterable[str]],
    *,
    now: Optional[datetime] = None,
    path: Optional[str] = None,
) -> dict:
    """Tối đa một lần thử/ngày; ngày nghỉ đã có cache thì không gọi DNSE."""
    now = now or _market_now()
    today = now.strftime("%Y-%m-%d")
    cache = load_cache(path)
    settings = load_settings()
    if not settings.get("use_dnse_working_dates", True):
        return cache
    if cache.get("last_attempt_date") == today:
        return cache
    if cache_covers(today, cache) and today not in set(cache.get("working_dates", [])):
        return cache

    cache["last_attempt_date"] = today
    try:
        dates = normalize_dates(provider() or [])
        if not dates:
            raise RuntimeError("DNSE không trả danh sách ngày giao dịch")
        cache.update({
            "version": 1,
            "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "coverage_start": today,
            "coverage_end": max(dates),
            "working_dates": dates,
            "last_error": None,
        })
    except Exception as exc:
        cache["last_error"] = str(exc)
    save_cache(cache, path)
    return cache


def date_status(value=None, settings=None, cache=None) -> dict:
    day = _date_value(value or _market_now())
    day_text = day.strftime("%Y-%m-%d")
    if day.weekday() >= 5:
        return {"status": "WEEKEND", "source": "LOCAL", "confirmed": True, "date": day_text}

    settings = normalize_settings(settings if settings is not None else load_settings())
    configured = set(getattr(config, "MARKET_HOLIDAYS", set()) or set())
    manual = set(settings.get("manual_closed_dates", []))
    if day_text in configured or day_text in manual:
        return {"status": "HOLIDAY", "source": "MANUAL", "confirmed": True, "date": day_text}

    cache = cache if cache is not None else load_cache()
    if settings.get("use_dnse_working_dates", True) and cache_covers(day_text, cache):
        is_working = day_text in set(cache.get("working_dates", []))
        return {
            "status": "TRADING" if is_working else "HOLIDAY",
            "source": "DNSE_CACHE",
            "confirmed": True,
            "date": day_text,
        }
    return {"status": "UNKNOWN", "source": "FALLBACK", "confirmed": False, "date": day_text}


def third_thursday(year: int, month: int) -> date:
    weeks = calendar.monthcalendar(int(year), int(month))
    thursdays = [week[calendar.THURSDAY] for week in weeks if week[calendar.THURSDAY]]
    return date(int(year), int(month), thursdays[2])


def vn30_expiry_date(year: int, month: int, settings=None, cache=None) -> date:
    candidate = third_thursday(year, month)
    cache = cache if cache is not None else load_cache()
    settings = normalize_settings(settings if settings is not None else load_settings())
    while date_status(candidate, settings=settings, cache=cache)["status"] in {"HOLIDAY", "WEEKEND"}:
        candidate -= timedelta(days=1)
    return candidate


def next_vn30_expiry(value=None, settings=None, cache=None) -> date:
    today = _date_value(value or _market_now())
    expiry = vn30_expiry_date(today.year, today.month, settings=settings, cache=cache)
    if expiry >= today:
        return expiry
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return vn30_expiry_date(year, month, settings=settings, cache=cache)


def bot_entry_block_reason(symbol: str, signal_class: str, settings=None, value=None):
    if not str(symbol or "").upper().startswith("VN30F"):
        return None
    if str(signal_class or "ENTRY").upper() != "ENTRY":
        return None
    settings = normalize_settings(settings if settings is not None else load_settings())
    today = _date_value(value or _market_now())
    if settings.get("avoid_vn30_expiry_entry"):
        expiry = vn30_expiry_date(today.year, today.month, settings=settings)
        if today == expiry:
            return (
                "VN30_EXPIRY_ENTRY_BLOCK",
                f"{symbol} không mở ENTRY trong ngày đáo hạn VN30F {today:%Y-%m-%d}",
            )
    if settings.get("avoid_vn30_rebalance_entry") and today.strftime("%Y-%m-%d") in set(
        settings.get("vn30_rebalance_dates", [])
    ):
        return (
            "VN30_REBALANCE_ENTRY_BLOCK",
            f"{symbol} không mở ENTRY trong ngày đổi rổ VN30 {today:%Y-%m-%d}",
        )
    return None


def calendar_summary(value=None) -> dict:
    settings, cache = load_settings(), load_cache()
    status = date_status(value, settings=settings, cache=cache)
    status.update({
        "fetched_at": cache.get("fetched_at"),
        "last_attempt_date": cache.get("last_attempt_date"),
        "last_error": cache.get("last_error"),
        "coverage_start": cache.get("coverage_start"),
        "coverage_end": cache.get("coverage_end"),
        "next_expiry": next_vn30_expiry(value, settings=settings, cache=cache).strftime("%Y-%m-%d"),
    })
    return status
