# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

import config
from core import storage_manager

PENDING = "PENDING"
SENDING = "SENDING"
SENT = "SENT"
FAILED = "FAILED"
EXPIRED = "EXPIRED"
CANCELLED = "CANCELLED"

FINAL_STATUSES = {SENT, FAILED, EXPIRED, CANCELLED}
_LOCK = threading.RLock()


def _path() -> str:
    base = getattr(storage_manager, "_active_account_dir", "data") or "data"
    return os.path.join(base, "pending_orders.json")


def _now() -> float:
    return time.time()


def _expire_hours() -> float:
    default = float(getattr(config, "PENDING_ORDER_EXPIRE_HOURS", 24.0) or 24.0)
    try:
        brain = storage_manager.load_brain_settings()
        safe = brain.get("bot_safeguard", {}) if isinstance(brain, dict) else {}
        return max(0.01, float(safe.get("PENDING_ORDER_EXPIRE_HOURS", default)))
    except Exception:
        return max(0.01, default)


def _normalize(entry: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(entry or {})
    item.setdefault("id", str(uuid.uuid4()))
    item["symbol"] = str(item.get("symbol", "") or "").strip().upper()
    item["side"] = str(item.get("side", "BUY") or "BUY").strip().upper()
    item["preset"] = str(item.get("preset", getattr(config, "DEFAULT_PRESET", "SCALPING")) or "SCALPING")
    item["lot"] = float(item.get("lot", 0.0) or 0.0)
    item["entry_price"] = float(item.get("entry_price", 0.0) or 0.0)
    item["sl"] = float(item.get("sl", 0.0) or 0.0)
    item["tp"] = float(item.get("tp", 0.0) or 0.0)
    target = str(item.get("target", "") or "").upper()
    item["target"] = target if target in ("ATO", "ATC", "OPEN") else ("OPEN" if item["entry_price"] > 0 else "ATO")
    item.setdefault("created_at", _now())
    item.setdefault("expire_at", float(item["created_at"]) + (_expire_hours() * 3600.0))
    item["status"] = str(item.get("status", PENDING) or PENDING).upper()
    item.setdefault("note", "")
    item.setdefault("result", "")
    item.setdefault("dnse_order_id", "")
    item.setdefault("order_kind", item["target"] if item["target"] in ("ATO", "ATC") else "")
    item.setdefault("manual_entry_tactic", "")
    item.setdefault("lot_source", "")
    item.setdefault("sl_source", "")
    item.setdefault("tp_source", "")
    item.setdefault("entry_source", "")
    item.setdefault("plan", "")
    return item


def _read_unlocked() -> List[Dict[str, Any]]:
    path = _path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [_normalize(x) for x in data if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _write_unlocked(items: List[Dict[str, Any]]) -> None:
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([_normalize(x) for x in items], f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def add_order(
    *,
    symbol: str,
    side: str,
    preset: str,
    lot: float = 0.0,
    entry_price: float = 0.0,
    sl: float = 0.0,
    tp: float = 0.0,
    target: Optional[str] = None,
    note: str = "",
    expire_hours: Optional[float] = None,
    manual_entry_tactic: str = "",
    lot_source: str = "",
    sl_source: str = "",
    tp_source: str = "",
    entry_source: str = "",
    plan: str = "",
) -> Dict[str, Any]:
    created_at = _now()
    hours = _expire_hours() if expire_hours is None else max(0.01, float(expire_hours))
    item = _normalize(
        {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "side": side,
            "preset": preset,
            "lot": lot,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "target": target or ("OPEN" if float(entry_price or 0.0) > 0 else "ATO"),
            "created_at": created_at,
            "expire_at": created_at + (hours * 3600.0),
            "status": PENDING,
            "note": note,
            "manual_entry_tactic": manual_entry_tactic,
            "lot_source": lot_source,
            "sl_source": sl_source,
            "tp_source": tp_source,
            "entry_source": entry_source,
            "plan": plan,
        }
    )
    with _LOCK:
        items = _read_unlocked()
        items.append(item)
        _write_unlocked(items)
    return deepcopy(item)


def list_all() -> List[Dict[str, Any]]:
    with _LOCK:
        return deepcopy(_read_unlocked())


def list_active() -> List[Dict[str, Any]]:
    return [x for x in list_all() if str(x.get("status", "")).upper() not in FINAL_STATUSES]


def mark(order_id: str, status: str, result: str = "", **updates: Any) -> Optional[Dict[str, Any]]:
    status = str(status or "").upper()
    with _LOCK:
        items = _read_unlocked()
        found = None
        for item in items:
            if str(item.get("id")) == str(order_id):
                item["status"] = status
                if result:
                    item["result"] = str(result)
                for key, value in updates.items():
                    item[key] = value
                if status in FINAL_STATUSES and "finalized_at" not in updates:
                    item["finalized_at"] = _now()
                found = _normalize(item)
                item.update(found)
                break
        _write_unlocked(items)
    return deepcopy(found) if found else None


def cancel(order_id: str, result: str = "User cancelled") -> Optional[Dict[str, Any]]:
    with _LOCK:
        items = _read_unlocked()
        found = None
        for item in items:
            if str(item.get("id")) == str(order_id):
                if str(item.get("status", "")).upper() in (PENDING, FAILED, EXPIRED):
                    item["status"] = CANCELLED
                    item["result"] = result
                    found = _normalize(item)
                    item.update(found)
                break
        _write_unlocked(items)
    return deepcopy(found) if found else None


def delete_final(order_id: str) -> bool:
    with _LOCK:
        items = _read_unlocked()
        next_items = [
            item for item in items
            if not (str(item.get("id")) == str(order_id) and str(item.get("status", "")).upper() in FINAL_STATUSES)
        ]
        changed = len(next_items) != len(items)
        if changed:
            _write_unlocked(next_items)
        return changed


def expire_pending(now: Optional[float] = None) -> List[Dict[str, Any]]:
    now = _now() if now is None else float(now)
    expired: List[Dict[str, Any]] = []
    with _LOCK:
        items = _read_unlocked()
        for item in items:
            if str(item.get("status", "")).upper() == PENDING and float(item.get("expire_at", 0.0) or 0.0) <= now:
                item["status"] = EXPIRED
                item["result"] = "Expired before market phase"
                item["finalized_at"] = now
                expired.append(_normalize(item))
                item.update(expired[-1])
        if expired:
            _write_unlocked(items)
    return deepcopy(expired)


# Trạng thái cuối đã "chết" -> được phép dọn khỏi bảng running (SENT giữ lại vì đã lên sàn).
_PURGEABLE_STATUSES = {EXPIRED, FAILED, CANCELLED}


def purge_stale(max_age_sec: Optional[float] = None, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Xóa hẳn lệnh local đã EXPIRED/FAILED/CANCELLED quá lâu khỏi pending_orders.json.

    Để bảng "LỆNH ĐANG CHẠY" không giữ mãi lệnh chết. SENT không đụng (đã lên sàn).
    Mốc tuổi ưu tiên finalized_at, fallback expire_at/created_at cho item cũ chưa có field.
    """
    if max_age_sec is None:
        hours = float(getattr(config, "PENDING_PURGE_AFTER_HOURS", 2.0) or 0.0)
        max_age_sec = hours * 3600.0
    if max_age_sec <= 0:
        return []
    now = _now() if now is None else float(now)
    removed: List[Dict[str, Any]] = []
    with _LOCK:
        items = _read_unlocked()
        kept = []
        for item in items:
            status = str(item.get("status", "")).upper()
            if status in _PURGEABLE_STATUSES:
                ref = float(
                    item.get("finalized_at")
                    or item.get("expire_at")
                    or item.get("created_at")
                    or 0.0
                )
                if ref and (now - ref) >= max_age_sec:
                    removed.append(deepcopy(item))
                    continue
            kept.append(item)
        if removed:
            _write_unlocked(kept)
    return removed


def recover_stuck(max_age_sec: float = 600.0, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Đưa order kẹt SENDING quá lâu (app crash giữa claim→gửi) về PENDING để thử lại."""
    now = _now() if now is None else float(now)
    recovered: List[Dict[str, Any]] = []
    with _LOCK:
        items = _read_unlocked()
        changed = False
        for item in items:
            if str(item.get("status", "")).upper() == SENDING:
                claimed = float(item.get("claimed_at", 0.0) or item.get("created_at", 0.0) or 0.0)
                if now - claimed > max_age_sec:
                    item["status"] = PENDING
                    item["result"] = "Khôi phục từ trạng thái SENDING bị kẹt"
                    recovered.append(_normalize(item))
                    item.update(recovered[-1])
                    changed = True
        if changed:
            _write_unlocked(items)
    return deepcopy(recovered)


def claim_due(phase_fn: Callable[[str], Any], now: Optional[float] = None, limit: int = 20) -> List[Dict[str, Any]]:
    now = _now() if now is None else float(now)
    due: List[Dict[str, Any]] = []
    with _LOCK:
        items = _read_unlocked()
        changed = False
        for item in items:
            if len(due) >= limit:
                break
            status = str(item.get("status", "")).upper()
            if status != PENDING:
                continue
            if float(item.get("expire_at", 0.0) or 0.0) <= now:
                item["status"] = EXPIRED
                item["result"] = "Expired before market phase"
                changed = True
                continue
            try:
                phase_result = phase_fn(str(item.get("symbol", "")))
                phase = phase_result[0] if isinstance(phase_result, (tuple, list)) else str(phase_result)
            except Exception:
                phase = ""
            target = str(item.get("target", "") or "").upper()
            if (
                (target == "ATO" and phase == "ATO")
                or (target == "ATC" and phase == "ATC")
                or (target == "OPEN" and phase == "OPEN")
            ):
                item["status"] = SENDING
                item["claimed_at"] = now
                normalized = _normalize(item)
                item.update(normalized)
                due.append(normalized)
                changed = True
        if changed:
            _write_unlocked(items)
    return deepcopy(due)
