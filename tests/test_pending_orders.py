# -*- coding: utf-8 -*-
import json
import os

from core import pending_orders, storage_manager


def _isolated_account(monkeypatch, tmp_path, expire_hours=24):
    account_dir = tmp_path / "ACC1"
    account_dir.mkdir()
    monkeypatch.setattr(storage_manager, "_active_account_dir", str(account_dir))
    monkeypatch.setattr(storage_manager, "BRAIN_FILE", str(account_dir / "brain_settings.json"))
    with open(storage_manager.BRAIN_FILE, "w", encoding="utf-8") as f:
        json.dump({"bot_safeguard": {"PENDING_ORDER_EXPIRE_HOURS": expire_hours}}, f)
    storage_manager.invalidate_settings_cache()
    return account_dir


def test_pending_order_add_cancel_and_delete(monkeypatch, tmp_path):
    account_dir = _isolated_account(monkeypatch, tmp_path, expire_hours=12)

    item = pending_orders.add_order(
        symbol="VN30F1M",
        side="BUY",
        preset="SCALPING",
        lot=1,
        entry_price=1200,
        sl=1190,
        tp=1220,
    )

    assert os.path.exists(account_dir / "pending_orders.json")
    assert item["target"] == "OPEN"
    assert round((item["expire_at"] - item["created_at"]) / 3600) == 12
    assert len(pending_orders.list_active()) == 1

    cancelled = pending_orders.cancel(item["id"])
    assert cancelled["status"] == pending_orders.CANCELLED
    assert pending_orders.delete_final(item["id"]) is True
    assert pending_orders.list_all() == []


def test_recover_stuck_sending_back_to_pending(monkeypatch, tmp_path):
    _isolated_account(monkeypatch, tmp_path)
    item = pending_orders.add_order(symbol="VN30F1M", side="BUY", preset="SCALPING", lot=1, entry_price=1200)
    # Ép sang SENDING với claimed_at đã lâu (mô phỏng app crash giữa claim->gửi).
    pending_orders.mark(item["id"], pending_orders.SENDING, "", claimed_at=1.0)
    recovered = pending_orders.recover_stuck(max_age_sec=600.0)
    assert len(recovered) == 1
    assert recovered[0]["status"] == pending_orders.PENDING
    # SENDING còn mới (vừa claim) thì KHÔNG đụng.
    import time as _t
    pending_orders.mark(item["id"], pending_orders.SENDING, "", claimed_at=_t.time())
    assert pending_orders.recover_stuck(max_age_sec=600.0) == []


def test_claim_due_is_atomic_and_does_not_claim_twice(monkeypatch, tmp_path):
    _isolated_account(monkeypatch, tmp_path)
    item = pending_orders.add_order(
        symbol="VN30F1M",
        side="BUY",
        preset="SCALPING",
        lot=1,
        entry_price=0,
    )

    due = pending_orders.claim_due(lambda _symbol: ("ATO", ""), now=item["created_at"] + 1)

    assert [x["id"] for x in due] == [item["id"]]
    assert pending_orders.list_all()[0]["status"] == pending_orders.SENDING
    assert pending_orders.claim_due(lambda _symbol: ("ATO", ""), now=item["created_at"] + 2) == []


def test_expired_pending_order_is_not_claimed(monkeypatch, tmp_path):
    _isolated_account(monkeypatch, tmp_path)
    item = pending_orders.add_order(
        symbol="VN30F1M",
        side="BUY",
        preset="SCALPING",
        lot=1,
        entry_price=1200,
        expire_hours=0.01,
    )

    due = pending_orders.claim_due(lambda _symbol: ("OPEN", ""), now=item["expire_at"] + 1)

    assert due == []
    stored = pending_orders.list_all()[0]
    assert stored["status"] == pending_orders.EXPIRED
