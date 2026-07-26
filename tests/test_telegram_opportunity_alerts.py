# -*- coding: utf-8 -*-
from telegram_notify import opportunity_alerts, settings
from telegram_notify.client import TelegramClient


class _FakeTimer:
    def __init__(self, delay, callback, kwargs=None):
        self.delay = delay
        self.callback = callback
        self.kwargs = kwargs or {}
        self.daemon = False

    def start(self):
        return None

    def cancel(self):
        return None


def _configure(monkeypatch, tmp_path, **overrides):
    monkeypatch.setattr(settings, "account_dir", lambda: str(tmp_path))
    monkeypatch.setattr(opportunity_alerts, "account_dir", lambda: str(tmp_path))
    monkeypatch.setattr(opportunity_alerts.threading, "Timer", _FakeTimer)
    data = {
        "opportunity_alerts_enabled": True,
        "opportunity_chat_id": "1001234567890",
        "opportunity_mode_filter": "ALL",
        "opportunity_ckps_enabled": True,
        "opportunity_ckcs_enabled": True,
        "opportunity_duplicate_cooldown_minutes": 60,
        "opportunity_batch_minutes": 5,
    }
    data.update(overrides)
    settings.save_settings(data)
    opportunity_alerts.reset_runtime_state()


def _item(symbol, side="BUY", mode="PAPER", market="CKCS"):
    return {
        "symbol": symbol,
        "side": side,
        "execution_mode": mode,
        "market_type": market,
        "last_price": 12.3,
        "block_reason": "BOT_OFF",
        "order_setup": {"price": 12.3, "lot": 100, "sl": 11.5, "tp": 14.0},
    }


def test_many_symbols_are_sent_as_one_read_only_digest(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    sent = []

    def fake_send(self, chat_id, text, chunk_size=3500, title=""):
        sent.append((chat_id, text, title))
        return {"ok": True, "sent": 1}

    monkeypatch.setattr(TelegramClient, "send_long_message", fake_send)

    for index in range(40):
        result = opportunity_alerts.queue_opportunity(_item(f"CK{index:02d}"))
        assert result["queued"] is True

    result = opportunity_alerts.flush_now()

    assert result["ok"] is True
    assert len(sent) == 1
    assert sent[0][0] == "1001234567890"
    assert "40 tín hiệu mới" in sent[0][1]
    assert "Chỉ thông báo, chưa gửi lệnh." in sent[0][1]
    assert sent[0][2] == "RAT6 GỢI Ý BOT"


def test_duplicate_symbol_and_side_obeys_cooldown(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)

    first = opportunity_alerts.queue_opportunity(_item("AAA", "BUY"))
    duplicate = opportunity_alerts.queue_opportunity(_item("AAA", "BUY"))
    opposite = opportunity_alerts.queue_opportunity(_item("AAA", "SELL"))

    assert first["queued"] is True
    assert duplicate["reason"] == "cooldown"
    assert opposite["queued"] is True


def test_mode_and_market_filters_are_independent(monkeypatch, tmp_path):
    _configure(
        monkeypatch,
        tmp_path,
        opportunity_mode_filter="PAPER",
        opportunity_ckps_enabled=True,
        opportunity_ckcs_enabled=False,
    )

    assert opportunity_alerts.queue_opportunity(
        _item("VN30F1M", mode="PAPER", market="CKPS")
    )["queued"] is True
    assert opportunity_alerts.queue_opportunity(
        _item("AAA", mode="PAPER", market="CKCS")
    )["reason"] == "filtered"
    assert opportunity_alerts.queue_opportunity(
        _item("VN30F1M", mode="REAL", market="CKPS")
    )["reason"] == "filtered"
