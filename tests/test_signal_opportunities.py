# -*- coding: utf-8 -*-
import json

import config
from core import signal_opportunities, storage_manager


def _isolate(monkeypatch, tmp_path):
    account = tmp_path / "ACC"
    account.mkdir()
    brain = account / "brain_settings.json"
    brain.write_text(json.dumps({
        "opportunity_settings": {
            "enabled": True,
            "retention_hours": 24,
            "history_enabled": True,
        }
    }), encoding="utf-8")
    monkeypatch.setattr(storage_manager, "_active_account_dir", str(account))
    monkeypatch.setattr(storage_manager, "BRAIN_FILE", str(brain))
    storage_manager.invalidate_settings_cache()
    return account


def test_signal_opportunity_deduplicates_and_archives(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "PAPER_TRADING", True)
    signal = {
        "symbol": "AAA",
        "action": "BUY",
        "market_mode": "BREAKOUT",
        "context": {"current_price": 7.2, "trend_G0": "UP"},
    }
    first = signal_opportunities.record_signal(
        signal,
        now=1000,
        order_setup={"ok": True, "lot": 300, "price": 7.2, "sl": 6.6, "tp": 8.1},
    )
    second = signal_opportunities.record_signal(
        signal,
        now=1100,
        order_setup={"ok": True, "lot": 400, "price": 7.3, "sl": 6.7, "tp": 8.2},
    )
    rows = signal_opportunities.list_active(now=1101)
    assert first["id"] == second["id"]
    assert len(rows) == 1 and rows[0]["signal_count"] == 2
    assert rows[0]["execution_mode"] == "PAPER"
    assert rows[0]["order_setup"]["lot"] == 400
    assert rows[0]["order_setup"]["price"] == 7.3

    assert signal_opportunities.update_active(first["id"], order_setup={"ok": True, "lot": 500})
    assert signal_opportunities.get(first["id"])["order_setup"]["lot"] == 500

    final = signal_opportunities.finalize(first["id"], signal_opportunities.ACTIVATED, "test")
    assert final["status"] == signal_opportunities.ACTIVATED
    assert signal_opportunities.list_active(now=1102) == []
    assert signal_opportunities.list_history(include_active=False)[0]["status"] == signal_opportunities.ACTIVATED


def test_signal_opportunity_expires_to_history(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    signal = {"symbol": "VN30F1M", "action": "SELL", "context": {"current_price": 1900}}
    item = signal_opportunities.record_signal(signal, now=1000)
    expired = signal_opportunities.expire(now=item["expire_at"] + 1)
    assert expired[0]["status"] == signal_opportunities.EXPIRED
    assert signal_opportunities.list_active(now=item["expire_at"] + 2) == []
