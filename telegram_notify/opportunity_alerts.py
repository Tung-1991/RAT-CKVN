# -*- coding: utf-8 -*-
"""Read-only Telegram digest for BOT opportunities.

Signals are grouped into a short digest so a scan of many symbols cannot flood
the Telegram group. This channel never creates or changes an order.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional

from .client import TelegramClient
from .settings import account_dir, load_settings


_LOCK = threading.RLock()
_PENDING: Dict[str, Dict[str, Any]] = {}
_TIMER: Optional[threading.Timer] = None


def cooldown_path() -> str:
    return os.path.join(account_dir(), "telegram_opportunity_cooldowns.json")


def _read_cooldowns() -> Dict[str, float]:
    try:
        with open(cooldown_path(), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return {
            str(key): float(value)
            for key, value in (raw.items() if isinstance(raw, dict) else [])
        }
    except Exception:
        return {}


def _write_cooldowns(data: Dict[str, float]) -> None:
    path = cooldown_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def _key(item: Dict[str, Any]) -> str:
    return (
        f"{str(item.get('execution_mode') or 'PAPER').upper()}|"
        f"{str(item.get('symbol') or '').upper()}|"
        f"{str(item.get('side') or '').upper()}"
    )


def _passes_filter(item: Dict[str, Any], settings: Dict[str, Any]) -> bool:
    mode = str(item.get("execution_mode") or "PAPER").upper()
    mode_filter = str(settings.get("opportunity_mode_filter") or "PAPER").upper()
    if mode_filter != "ALL" and mode != mode_filter:
        return False
    market = str(item.get("market_type") or "CKCS").upper()
    if market == "CKPS":
        return bool(settings.get("opportunity_ckps_enabled", True))
    return bool(settings.get("opportunity_ckcs_enabled", True))


def _number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number == 0:
        return "—"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _line(item: Dict[str, Any]) -> str:
    setup = item.get("order_setup") if isinstance(item.get("order_setup"), dict) else {}
    price = (
        setup.get("price")
        or item.get("last_price")
        or item.get("detected_price")
        or 0.0
    )
    lot = setup.get("lot", 0.0)
    reason = str(item.get("block_reason") or "BOT_OFF").split("|", 2)[0]
    return (
        f"{str(item.get('execution_mode') or 'PAPER').upper()} · "
        f"{str(item.get('market_type') or 'CKCS').upper()} | "
        f"{str(item.get('symbol') or '').upper()} "
        f"{str(item.get('side') or '').upper()} @{_number(price)} | "
        f"KL {_number(lot, 0)} | SL {_number(setup.get('sl'))} | "
        f"TP {_number(setup.get('tp'))} | {reason}"
    )


def _format_digest(items: list[Dict[str, Any]]) -> str:
    ordered = sorted(
        items,
        key=lambda item: (
            0 if str(item.get("market_type") or "").upper() == "CKPS" else 1,
            str(item.get("execution_mode") or ""),
            str(item.get("symbol") or ""),
            str(item.get("side") or ""),
        ),
    )
    lines = [
        f"GỢI Ý BOT — {len(ordered)} tín hiệu mới",
        "Chỉ thông báo, chưa gửi lệnh.",
        "",
    ]
    lines.extend(_line(item) for item in ordered)
    lines.extend(["", "Xem đầy đủ tại Lịch sử → Gợi ý BOT."])
    return "\n".join(lines)


def flush_now(log_cb=None) -> Dict[str, Any]:
    """Send and clear the current digest. Exposed for UI tests and shutdown tools."""
    global _TIMER
    log = log_cb or (lambda _message, error=False: None)
    with _LOCK:
        items = list(_PENDING.values())
        _PENDING.clear()
        _TIMER = None
    if not items:
        return {"ok": False, "skipped": True, "reason": "empty"}

    settings = load_settings()
    if not settings.get("opportunity_alerts_enabled"):
        return {"ok": False, "skipped": True, "reason": "disabled"}
    chat_id = str(settings.get("opportunity_chat_id") or "").strip()
    if not chat_id:
        return {"ok": False, "skipped": True, "reason": "missing_chat_id"}
    client = TelegramClient(
        token_env=settings.get("bot_token_env", "TELE_BOT_KEY"),
        allow_insecure_ssl=True,
    )
    result = client.send_long_message(
        chat_id,
        _format_digest(items),
        chunk_size=settings.get("chunk_size", 3500),
        title="RAT6 GỢI Ý BOT",
    )
    if result.get("ok"):
        log(f"[TELEGRAM GỢI Ý] Đã gửi bản tổng hợp {len(items)} tín hiệu.")
    else:
        log(
            f"[TELEGRAM GỢI Ý] Gửi lỗi: {result.get('error', 'unknown')}",
            error=True,
        )
    return result


def queue_opportunity(item: Dict[str, Any], log_cb=None) -> Dict[str, Any]:
    """Queue one opportunity after mode/market and per-symbol cooldown checks."""
    global _TIMER
    settings = load_settings()
    if not settings.get("opportunity_alerts_enabled"):
        return {"ok": False, "skipped": True, "reason": "disabled"}
    if not str(settings.get("opportunity_chat_id") or "").strip():
        return {"ok": False, "skipped": True, "reason": "missing_chat_id"}
    if not isinstance(item, dict) or not _passes_filter(item, settings):
        return {"ok": False, "skipped": True, "reason": "filtered"}

    key = _key(item)
    now = time.time()
    cooldown_seconds = (
        float(settings.get("opportunity_duplicate_cooldown_minutes", 60.0)) * 60.0
    )
    with _LOCK:
        cooldowns = _read_cooldowns()
        last = float(cooldowns.get(key, 0.0) or 0.0)
        if now - last < cooldown_seconds:
            return {
                "ok": False,
                "skipped": True,
                "reason": "cooldown",
                "remaining_seconds": int(cooldown_seconds - (now - last)),
            }
        cooldowns[key] = now
        cutoff = now - max(cooldown_seconds, 86400.0)
        _write_cooldowns(
            {name: value for name, value in cooldowns.items() if value >= cutoff}
        )
        _PENDING[key] = dict(item)
        if _TIMER is None:
            delay = max(
                1.0,
                float(settings.get("opportunity_batch_minutes", 5.0)) * 60.0,
            )
            _TIMER = threading.Timer(delay, flush_now, kwargs={"log_cb": log_cb})
            _TIMER.daemon = True
            _TIMER.start()
    return {"ok": True, "queued": True, "batch_size": len(_PENDING)}


def reset_runtime_state() -> None:
    """Test/QOL helper: cancel an unsent in-memory digest."""
    global _TIMER
    with _LOCK:
        if _TIMER is not None:
            _TIMER.cancel()
        _TIMER = None
        _PENDING.clear()
