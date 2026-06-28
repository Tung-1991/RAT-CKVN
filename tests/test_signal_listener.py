# -*- coding: utf-8 -*-
from core.signal_listener import SignalListener


class FakeTradeManager:
    pass


def _listener():
    return SignalListener(
        trade_manager=FakeTradeManager(),
        get_auto_trade_cb=lambda: False,
        get_preset_cb=lambda: "",
        get_tsl_mode_cb=lambda: "",
        ui_heartbeat_cb=lambda payload: None,
        log_cb=lambda msg, error=False: None,
    )


def test_telegram_signal_phase_persists_across_restart(monkeypatch, tmp_path):
    monkeypatch.setattr("core.signal_listener._get_telegram_signal_phase_file", lambda: str(tmp_path / "phases.json"))
    sent = []
    listener = _listener()
    listener._save_telegram_signal_phase("ETHUSD", "BUY")

    def fake_send(*_args, **_kwargs):
        sent.append(True)
        return {"ok": True}

    monkeypatch.setattr("telegram_notify.signal_bridge.maybe_send_signal_proposal", fake_send)

    listener._process_signal({"signal_id": "S2", "symbol": "ETHUSD", "action": "BUY", "signal_class": "ENTRY"})
    assert sent == []

    listener._process_signal({"signal_id": "S3", "symbol": "ETHUSD", "action": "SELL", "signal_class": "ENTRY"})
    assert sent == [True]


def test_none_resets_telegram_signal_phase(monkeypatch, tmp_path):
    monkeypatch.setattr("core.signal_listener._get_telegram_signal_phase_file", lambda: str(tmp_path / "phases.json"))
    listener = _listener()
    listener._save_telegram_signal_phase("ETHUSD", "BUY")

    listener._process_signal({"signal_id": "S1", "symbol": "ETHUSD", "action": "NONE", "signal_class": "ENTRY"})

    assert listener._load_telegram_signal_phases() == {}


def test_auto_trade_gate_symbol_aware():
    """Callback symbol-aware: gate riêng theo nhóm mã (CKPS vs CKCS)."""
    # CKPS bật, CKCS tắt: VN30F1M -> True; cổ phiếu cơ sở (FPT) -> False.
    flags = {"VN30F1M": True, "FPT": False}
    listener = _listener()
    listener.get_auto_trade = lambda symbol=None: bool(flags.get(str(symbol or "").upper(), False))
    assert listener._auto_trade_for("VN30F1M") is True
    assert listener._auto_trade_for("FPT") is False


def test_auto_trade_gate_legacy_noarg():
    """Callback cũ no-arg vẫn chạy (tương thích ngược)."""
    listener = _listener()
    listener.get_auto_trade = lambda: True
    assert listener._auto_trade_for("VN30F1M") is True
    assert listener._auto_trade_for("FPT") is True
