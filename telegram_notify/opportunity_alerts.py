# -*- coding: utf-8 -*-
"""Telegram read-only feed for BOT opportunities and price events.

This module never places or changes an order.  It persists the last Telegram
state so restarting the app does not resend unchanged signals.
"""
from __future__ import annotations

import json
import os
import threading
import time
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Optional

from .client import TelegramClient
from .settings import account_dir, load_settings


_LOCK = threading.RLock()
_PENDING: Dict[str, Dict[str, Any]] = {}
_TIMER: Optional[threading.Timer] = None


def state_path() -> str:
    return os.path.join(account_dir(), "telegram_opportunity_state.json")


def shortlist_path() -> str:
    return os.path.join(account_dir(), "ckcs_research", "ckcs_shortlist.md")


def cooldown_path() -> str:
    """Compatibility alias for tools/tests that used the old filename."""
    return state_path()


def _empty_state() -> Dict[str, Any]:
    return {
        "current": {},
        "last_sent": {},
        "morning_baseline": {},
        "last_morning_date": "",
        "last_eod_date": "",
    }


def _read_state() -> Dict[str, Any]:
    try:
        with open(state_path(), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            return _empty_state()
        state = _empty_state()
        state.update(raw)
        for key in ("current", "last_sent", "morning_baseline"):
            if not isinstance(state.get(key), dict):
                state[key] = {}
        return state
    except Exception:
        return _empty_state()


def _write_state(state: Dict[str, Any]) -> None:
    path = state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def _shortlist_items(state: Dict[str, Any], settings: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Return current CKPS/CKCS signals eligible for the suggestion feed."""
    now = time.time()
    rows = []
    for current in (state.get("current", {}) or {}).values():
        if not isinstance(current, dict):
            continue
        if str(current.get("side") or "").upper() not in {"BUY", "SELL"}:
            continue
        try:
            updated_at = float(current.get("updated_at") or 0.0)
        except (TypeError, ValueError):
            updated_at = 0.0
        if updated_at and now - updated_at > 24 * 3600:
            continue
        item = current.get("item")
        if not isinstance(item, dict):
            continue
        if _passes_filter(item, settings) and _valid_setup(item):
            rows.append(deepcopy(item))
    return rows


def _shortlist_markdown(items: list[Dict[str, Any]], now: Optional[datetime] = None) -> str:
    """Build one compact user-facing shortlist for both CKPS and CKCS."""
    now = now or datetime.now()
    sections = {
        title: rows
        for title, rows in _sections(items)
        if title in {"CKPS", "PRIORITY", "CKCS BUY", "CKCS SELL"} and rows
    }
    lines = [
        "# SHORTLIST TÍN HIỆU",
        "",
        f"Cập nhật: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        (
            "Danh sách CKPS/CKCS từ Gợi ý BOT sau khi kiểm tra tín hiệu Lego "
            "và mức SL/CẮT/TP. Bộ lọc thanh khoản chỉ áp dụng cho CKCS. "
            "Đây không phải lệnh giao dịch."
        ),
        "",
    ]
    if not sections:
        lines.extend(
            [
                "Không có tín hiệu CKPS/CKCS hợp lệ trong cache hiện tại.",
                "",
            ]
        )
    else:
        for title in ("CKPS", "PRIORITY", "CKCS BUY", "CKCS SELL"):
            rows = sections.get(title, [])
            if not rows:
                continue
            lines.extend([f"## {title}", ""])
            lines.extend(f"- {_line(item)}" for item in rows)
            lines.append("")
    lines.extend(
        [
            "LLM chỉ phân tích sâu các mã trong file này; dùng scan_report.md để tra RAW nhiều ngày.",
            "Tăng trưởng 5 năm và định giá cơ bản chỉ áp dụng cho CKCS và vẫn phải đối chiếu nguồn công khai trên web.",
            "",
        ]
    )
    return "\n".join(lines)


def refresh_shortlist(*, state: Optional[Dict[str, Any]] = None) -> str:
    """Overwrite ckcs_shortlist.md from the existing Telegram opportunity state."""
    with _LOCK:
        current_state = deepcopy(state) if isinstance(state, dict) else _read_state()
        items = _shortlist_items(current_state, load_settings())
        content = _shortlist_markdown(items)
        path = shortlist_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
        return path


def _number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    rendered = f"{number:.{digits}f}"
    return rendered if digits <= 0 else rendered.rstrip("0").rstrip(".")


def _passes_filter(item: Dict[str, Any], settings: Dict[str, Any]) -> bool:
    market = str(item.get("market_type") or "CKCS").upper()
    if market == "CKPS":
        return bool(settings.get("opportunity_ckps_enabled", True))
    if not bool(settings.get("opportunity_ckcs_enabled", True)):
        return False
    try:
        from ai_advisor.scan_cache import liquidity_filter_allows

        return bool(liquidity_filter_allows(item.get("symbol")))
    except Exception:
        # Lỗi phụ trợ không được làm gãy luồng Telegram hiện hữu.
        return True


def _market_session_open(symbol: str) -> bool:
    try:
        from core.market_hours import market_session_phase

        return market_session_phase(symbol)[0] in {"ATO", "OPEN", "ATC"}
    except Exception:
        return False


def _priority_symbols() -> set[str]:
    try:
        from core.storage_manager import load_brain_settings

        brain = load_brain_settings()
        return {
            str(symbol or "").strip().upper()
            for symbol in (brain.get("PRIORITY_SYMBOLS", []) or [])
            if str(symbol or "").strip()
        }
    except Exception:
        return set()


def _valid_setup(item: Dict[str, Any]) -> bool:
    setup = item.get("order_setup") if isinstance(item.get("order_setup"), dict) else {}
    if setup.get("ok") is False:
        return False
    side = str(item.get("side") or "").upper()
    try:
        price = float(setup.get("price") or item.get("last_price") or 0.0)
        sl = float(setup.get("sl") or 0.0)
        tp = float(setup.get("tp") or 0.0)
    except (TypeError, ValueError):
        return False
    if min(price, sl, tp) <= 0:
        return False
    return (sl < price < tp) if side == "BUY" else (tp < price < sl)


def _line(item: Dict[str, Any], icon: str = "") -> str:
    setup = item.get("order_setup") if isinstance(item.get("order_setup"), dict) else {}
    symbol = str(item.get("symbol") or "").upper()
    side = str(item.get("side") or "").upper()
    market = str(item.get("market_type") or "CKCS").upper()
    price = setup.get("price") or item.get("last_price") or item.get("detected_price") or 0.0
    sl = setup.get("sl")
    tp = setup.get("tp")
    unit = str(setup.get("quantity_unit") or ("HĐ" if market == "CKPS" else "CP"))
    lot = float(setup.get("display_quantity", setup.get("lot", 0.0)) or 0.0)
    quantity = f" ({_number(lot, 0)} {unit})" if lot > 0 else ""
    level_label = "SL" if market == "CKPS" else "CẮT"
    direction = (
        "LONG" if side == "BUY" else "SHORT"
    ) if market == "CKPS" else side
    targets = []
    for value in setup.get("tp_targets") or []:
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value > 0:
            targets.append(value)
    if not targets and tp:
        targets = [tp]
    target_text = " | ".join(
        f"TP{index} {_number(value)}" for index, value in enumerate(targets[:3], 1)
    )
    prefix = f"{icon} " if icon else ""
    return (
        f"{prefix}{symbol} {direction} | Entry {_number(price)}{quantity} | "
        f"{level_label} {_number(sl)}"
        + (f" | {target_text}" if target_text else "")
    )


def _sections(items: list[Dict[str, Any]]) -> list[tuple[str, list[Dict[str, Any]]]]:
    priority = _priority_symbols()
    unique = {}
    for item in items:
        symbol = str(item.get("symbol") or "").upper()
        if symbol:
            unique[symbol] = item
    values = list(unique.values())
    return [
        ("CKPS", sorted(
            [x for x in values if str(x.get("market_type") or "").upper() == "CKPS"],
            key=lambda x: str(x.get("symbol") or ""),
        )),
        ("PRIORITY", sorted(
            [
                x for x in values
                if str(x.get("market_type") or "").upper() != "CKPS"
                and str(x.get("symbol") or "").upper() in priority
            ],
            key=lambda x: str(x.get("symbol") or ""),
        )),
        ("CKCS BUY", sorted(
            [
                x for x in values
                if str(x.get("market_type") or "").upper() != "CKPS"
                and str(x.get("symbol") or "").upper() not in priority
                and str(x.get("side") or "").upper() == "BUY"
            ],
            key=lambda x: str(x.get("symbol") or ""),
        )),
        ("CKCS SELL", sorted(
            [
                x for x in values
                if str(x.get("market_type") or "").upper() != "CKPS"
                and str(x.get("symbol") or "").upper() not in priority
                and str(x.get("side") or "").upper() == "SELL"
            ],
            key=lambda x: str(x.get("symbol") or ""),
        )),
    ]


def format_digest(
    items: list[Dict[str, Any]],
    *,
    heading: str = "RAT6 GỢI Ý BOT",
    changes: Optional[list[str]] = None,
    now: Optional[datetime] = None,
) -> str:
    now = now or datetime.now()
    heading_upper = str(heading or "").upper()
    lines = []
    if "CUỐI NGÀY" in heading_upper:
        lines.append(f"📋 CUỐI NGÀY · {now.strftime('%H:%M')}")
    elif "ĐẦU NGÀY" in heading_upper:
        lines.append(f"📋 ĐẦU NGÀY · {now.strftime('%H:%M')}")

    section_icons = {
        "PRIORITY": "⭐",
        "CKCS BUY": "🟢",
        "CKCS SELL": "🔴",
    }
    section_count = 0
    for title, rows in _sections(items):
        if not rows:
            continue
        section_count += len(rows)
        for item in rows:
            if title == "CKPS":
                icon = "🟢" if str(item.get("side") or "").upper() == "BUY" else "🔴"
            else:
                icon = section_icons.get(title, "•")
            lines.append(_line(item, icon=icon))
    if not section_count:
        if lines:
            lines.append("")
        lines.append(f"⏸ Không có tín hiệu BUY/SELL · {now.strftime('%H:%M')}")
    if changes is not None:
        lines.extend(["", "🔄 THAY ĐỔI"])
        lines.extend(changes or ["Không thay đổi"])
    return "\n".join(lines)


def _send(
    items,
    heading,
    log_cb=None,
    changes=None,
    now=None,
    *,
    allow_empty=False,
) -> Dict[str, Any]:
    settings = load_settings()
    if not settings.get("opportunity_alerts_enabled"):
        return {"ok": False, "skipped": True, "reason": "disabled"}
    chat_id = str(settings.get("opportunity_chat_id") or "").strip()
    if not chat_id:
        return {"ok": False, "skipped": True, "reason": "missing_chat_id"}
    valid = [item for item in items if _passes_filter(item, settings) and _valid_setup(item)]
    if not valid and not allow_empty:
        return {"ok": False, "skipped": True, "reason": "empty"}
    client = TelegramClient(
        token_env=settings.get("bot_token_env", "TELE_BOT_KEY"),
        allow_insecure_ssl=True,
    )
    result = client.send_long_message(
        chat_id,
        format_digest(valid, heading=heading, changes=changes, now=now),
        chunk_size=settings.get("chunk_size", 3500),
        title="",
    )
    log = log_cb or (lambda _message, error=False: None)
    if result.get("ok"):
        log(f"[TELEGRAM GỢI Ý] Đã gửi {len(valid)} tín hiệu.")
    elif not result.get("skipped"):
        log(f"[TELEGRAM GỢI Ý] Gửi lỗi: {result.get('error', 'unknown')}", error=True)
    return result


def flush_now(log_cb=None) -> Dict[str, Any]:
    """Send one consolidated delta digest and clear the in-memory debounce."""
    global _TIMER
    with _LOCK:
        items = [
            item
            for item in _PENDING.values()
            if _market_session_open(str(item.get("symbol") or ""))
        ]
        _PENDING.clear()
        _TIMER = None
    if not items:
        return {"ok": False, "skipped": True, "reason": "outside_session_or_empty"}
    result = _send(items, "RAT6 GỢI Ý BOT — CẬP NHẬT", log_cb=log_cb)
    if result.get("ok"):
        with _LOCK:
            state = _read_state()
            priorities = _priority_symbols()
            for item in items:
                symbol = str(item.get("symbol") or "").upper()
                state["last_sent"][symbol] = {
                    "side": str(item.get("side") or "").upper(),
                    "priority": symbol in priorities,
                    "sent_at": time.time(),
                }
            _write_state(state)
    else:
        with _LOCK:
            for item in items:
                _PENDING[str(item.get("symbol") or "").upper()] = item
    return result


def _archive_invalid(item: Dict[str, Any]) -> None:
    try:
        from core.signal_opportunities import finalize

        finalize(
            str(item.get("id") or ""),
            "INVALID_LEVELS",
            str((item.get("order_setup") or {}).get("error") or "INVALID_LEVELS"),
        )
    except Exception:
        pass


def queue_opportunity(item: Dict[str, Any], log_cb=None) -> Dict[str, Any]:
    """Observe a BUY/SELL state and queue it only when the state changed."""
    global _TIMER
    settings = load_settings()
    if not isinstance(item, dict) or not _passes_filter(item, settings):
        return {"ok": False, "skipped": True, "reason": "filtered"}
    if not _market_session_open(str(item.get("symbol") or "")):
        return {"ok": False, "skipped": True, "reason": "outside_session"}
    if not _valid_setup(item):
        setup = item.get("order_setup") if isinstance(item.get("order_setup"), dict) else {}
        error = str(setup.get("error") or "")
        if error.startswith("INVALID_LEVELS") or setup.get("ok") is not False:
            _archive_invalid(item)
            reason = "invalid_levels"
        else:
            reason = "setup_unavailable"
        return {"ok": False, "skipped": True, "reason": reason}

    symbol = str(item.get("symbol") or "").upper()
    side = str(item.get("side") or "").upper()
    if not symbol or side not in {"BUY", "SELL"}:
        return {"ok": False, "skipped": True, "reason": "invalid_signal"}
    priorities = _priority_symbols()
    with _LOCK:
        state = _read_state()
        previous_current = state["current"].get(symbol, {})
        state["current"][symbol] = {
            "side": side,
            "item": deepcopy(item),
            "priority": symbol in priorities,
            "updated_at": time.time(),
        }
        last = state["last_sent"].get(symbol, {})
        changed = (
            str(previous_current.get("side") or last.get("side") or "WAIT") != side
            or bool(previous_current.get("priority", last.get("priority", False)))
            != (symbol in priorities)
        )
        _write_state(state)
        refresh_shortlist(state=state)
        if not changed:
            return {"ok": False, "skipped": True, "reason": "unchanged"}
        if not settings.get("opportunity_alerts_enabled"):
            return {"ok": True, "stored": True, "reason": "telegram_disabled"}
        if not str(settings.get("opportunity_chat_id") or "").strip():
            return {"ok": True, "stored": True, "reason": "missing_chat_id"}

        _PENDING[symbol] = deepcopy(item)
        delay = max(
            1.0,
            float(settings.get("opportunity_batch_minutes", 5.0)) * 60.0,
        )
        # Debounce theo cấu hình: gom các thay đổi gần nhau thành một bản tin.
        if _TIMER is not None:
            _TIMER.cancel()
        _TIMER = threading.Timer(delay, flush_now, kwargs={"log_cb": log_cb})
        _TIMER.daemon = True
        _TIMER.start()
    return {"ok": True, "queued": True, "batch_size": len(_PENDING)}


def mark_wait(symbol: str) -> None:
    """Record WAIT silently so the next BUY/SELL is considered a new state."""
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        return
    with _LOCK:
        state = _read_state()
        previous = state["current"].get(symbol, {})
        if (
            str(previous.get("side") or "").upper() == "WAIT"
            and symbol not in _PENDING
        ):
            return
        state["current"][symbol] = {"side": "WAIT", "item": {}, "updated_at": time.time()}
        state["last_sent"][symbol] = {
            "side": "WAIT",
            "priority": symbol in _priority_symbols(),
            "sent_at": time.time(),
        }
        _PENDING.pop(symbol, None)
        _write_state(state)
        refresh_shortlist(state=state)


def _current_items(state: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows = []
    for current in state.get("current", {}).values():
        if not isinstance(current, dict) or str(current.get("side") or "") not in {"BUY", "SELL"}:
            continue
        item = current.get("item")
        if isinstance(item, dict) and _valid_setup(item):
            rows.append(deepcopy(item))
    return rows


def _baseline_changes(state: Dict[str, Any], items: list[Dict[str, Any]]) -> list[str]:
    baseline = state.get("morning_baseline", {})
    current = {
        str(item.get("symbol") or "").upper(): str(item.get("side") or "").upper()
        for item in items
    }
    lines = []
    for symbol in sorted(set(baseline) | set(current)):
        old = str(baseline.get(symbol) or "WAIT")
        new = str(current.get(symbol) or "WAIT")
        if old != new:
            lines.append(f"{symbol}: {old} → {new}")
    return lines


def run_scheduled_digest(*, now: Optional[datetime] = None, log_cb=None) -> Dict[str, Any]:
    """Optional 09:30/14:50 summaries. Disabled by default."""
    settings = load_settings()
    if not settings.get("opportunity_daily_digest_enabled", False):
        return {"ok": False, "skipped": True, "reason": "daily_digest_disabled"}
    if not settings.get("opportunity_alerts_enabled"):
        return {"ok": False, "skipped": True, "reason": "disabled"}

    try:
        from core.market_hours import _market_now
        from core.market_calendar import date_status

        now = now or _market_now()
        if str((date_status(now) or {}).get("status") or "").upper() in {
            "HOLIDAY",
            "WEEKEND",
        }:
            return {"ok": False, "skipped": True, "reason": "non_trading_day"}
    except Exception:
        now = now or datetime.now()
        if now.weekday() >= 5:
            return {"ok": False, "skipped": True, "reason": "non_trading_day"}

    today = now.strftime("%Y-%m-%d")
    minute = now.hour * 60 + now.minute
    with _LOCK:
        state = _read_state()
        items = _current_items(state)

    if minute >= 14 * 60 + 50 and state.get("last_eod_date") != today:
        result = _send(
            items,
            "RAT6 GỢI Ý BOT — CUỐI NGÀY",
            log_cb=log_cb,
            changes=_baseline_changes(state, items),
            now=now,
            allow_empty=True,
        )
        if result.get("ok"):
            with _LOCK:
                state = _read_state()
                state["last_eod_date"] = today
                _write_state(state)
        return result

    if minute >= 9 * 60 + 30 and state.get("last_morning_date") != today:
        result = _send(
            items,
            "RAT6 GỢI Ý BOT — ĐẦU NGÀY",
            log_cb=log_cb,
            now=now,
            allow_empty=True,
        )
        if result.get("ok"):
            with _LOCK:
                state = _read_state()
                state["last_morning_date"] = today
                state["morning_baseline"] = {
                    str(item.get("symbol") or "").upper(): str(item.get("side") or "").upper()
                    for item in items
                }
                _write_state(state)
        return result
    return {"ok": False, "skipped": True, "reason": "not_due"}


def send_volatility_event(event: Dict[str, Any], **_ignored) -> Dict[str, Any]:
    """Send one immediate price-shock alert to the opportunity chat."""
    settings = load_settings()
    chat_id = str(settings.get("opportunity_chat_id") or "").strip()
    if not chat_id:
        return {"ok": False, "skipped": True, "reason": "missing_chat_id"}
    direction_up = event.get("direction") == "UP"
    direction_icon = "🟢" if direction_up else "🔴"
    value = (
        f"{float(event.get('change_points', 0.0)):+.2f} điểm"
        if event.get("threshold_unit") == "POINTS"
        else f"{float(event.get('change_pct', 0.0)):+.2f}%"
    )
    action = str(event.get("action") or "ALERT_ONLY").strip().upper()
    action_label = str(event.get("action_label") or "").strip() or {
        "ALERT_ONLY": "CHỈ CẢNH BÁO",
        "BLOCK_NEW_EXPOSURE": "CHẶN BOT TĂNG VỊ THẾ",
        "CLOSE_ALL": "ĐÓNG HẾT + GLOBAL COOLDOWN",
    }.get(action, "CHỈ CẢNH BÁO")
    symbol = str(event.get("symbol") or "").upper()
    window = float(event.get("window_seconds", 0.0))
    try:
        reference_price = float(event.get("reference_price") or 0.0)
        current_price = float(event.get("current_price") or 0.0)
    except (TypeError, ValueError):
        reference_price = current_price = 0.0
    if reference_price > 0 and current_price > 0:
        message = (
            f"{direction_icon} {symbol} | "
            f"{_number(reference_price)}→{_number(current_price)} | "
            f"{value}/{window:.0f}s"
        )
    else:
        message = f"{direction_icon} {symbol} | {value}/{window:.0f}s"
    if action != "ALERT_ONLY":
        message += f" | ⛔ {action_label}"
    return TelegramClient(
        token_env=settings.get("bot_token_env", "TELE_BOT_KEY"),
        allow_insecure_ssl=True,
    ).send_long_message(
        chat_id,
        message,
        chunk_size=settings.get("chunk_size", 3500),
        title="",
    )


def reset_runtime_state() -> None:
    global _TIMER
    with _LOCK:
        if _TIMER is not None:
            _TIMER.cancel()
        _TIMER = None
        _PENDING.clear()
