"""Committed trade receipts and Telegram delivery, entirely offline."""
from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest
import requests

from ckps.connections.dnse.protocol import UnknownOutcome
from ckps.models import ExitSettings, Order, Quote, Settings
from ckps.services.entry_notices import EntryNotices, EntryRelay, notice_path, receipt_text
from ckps.services.signal_notifications import SignalNotifications
from ckps.services.signal_process import snapshot_status


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
@pytest.mark.parametrize('reason,label', [('SL', 'SL'), ('ARM', 'TSL / ARM'), ('DYN', 'DYNAMIC')])
def test_actual_automatic_closes_reach_the_existing_trade_group(system, monkeypatch, side, sign, reason, label):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(sl_enabled=reason == 'SL', sl_distance=.5,
        tp_enabled=reason == 'TP', tp_distance=.5, arm_enabled=reason == 'ARM', arm_gain=1,
        trail_gap=.25, arm_close_pct=50, dynamic_enabled=reason == 'DYN',
        dynamic_policy='AUTO', dynamic_close_pct=50, atr_start_multiplier=.5,
        retention_pct=70, retention_until_enabled=False))
    monkeypatch.setattr(engine, '_atr', lambda symbol: 1.)
    engine.open_manual(side, 2, 'MOK'); engine.poll()
    receiver = EntryNotices(store)
    engine.arm(True)
    if reason in {'ARM', 'DYN'}:
        broker.set_price(2000 + sign * (25 if reason == 'ARM' else 12)); engine.poll()
    broker.set_price(2000 + sign * {'SL': -10, 'TP': 10, 'ARM': 20, 'DYN': 8}[reason])
    engine.poll(); engine.poll()
    close = store.orders()[-1]
    assert close.action == 'CLOSE' and close.reason == reason and close.status == 'FILLED'
    relay = EntryRelay(store)
    try:
        relay.flush(); receiver.observe(enabled=True, chat='offline-chat')
        rows = store.db.execute('SELECT text FROM outbox').fetchall()
        assert len(rows) == 1
        text = rows[0][0]
        remaining = 0 if reason in {'SL', 'TP'} else 1
        assert ' · EXIT · PAPER' in text and f'ĐÓNG / GIẢM {side} · ĐÃ KHỚP' in text
        assert label in text and f'Còn {remaining} HĐ' in text
        receiver.observe(enabled=True, chat='offline-chat')
        assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0] == 1
        import sqlite3
        with sqlite3.connect(notice_path()) as db:
            receipts = [json.loads(raw) for raw, in db.execute('SELECT data FROM receipts')]
        assert all(set(row) <= {'at', 'mode', 'symbol', 'action', 'side', 'status', 'filled',
                                'quantity', 'price', 'reason', 'source', 'remaining'} for row in receipts)
    finally:
        relay.close()


def test_partial_close_reports_verified_remaining_without_repeating_on_poll_or_late_fee(system):
    engine, _, store = system
    engine.paper_capital(200_000_000)
    engine.open_manual('LONG', 3, 'MOK'); engine.poll()
    position = store.positions()[0]
    receiver = EntryNotices(store)
    order = engine.close_position(position.id, 2, kind='LO', price=2030)
    for status, filled in (('PARTIAL', 1), ('FILLED', 2), ('FILLED', 2)):
        update = dict(status=status, filled=filled, avg_fill=2030, fee=filled * 2000)
        with store.transaction():
            engine._apply_update(store.order(order.id), update)
    count = len(store.all('entry_notice'))
    with store.transaction():
        engine._apply_update(store.order(order.id), {**update, 'fee': 6000})
    assert len(store.all('entry_notice')) == count
    relay = EntryRelay(store)
    try:
        relay.flush(); receiver.observe(enabled=True, chat='offline-chat')
        texts = [text for text, in store.db.execute('SELECT text FROM outbox ORDER BY rowid')]
        assert len(texts) == 3
        assert 'ĐÃ GỬI' in texts[0] and 'Khớp 0/2' in texts[0] and 'Còn 3 HĐ' in texts[0]
        assert 'KHỚP MỘT PHẦN' in texts[1] and 'Khớp 1/2' in texts[1] and 'Còn 2 HĐ' in texts[1]
        assert 'ĐÃ KHỚP' in texts[2] and 'Khớp 2/2' in texts[2] and 'Còn 1 HĐ' in texts[2]
        assert all('ĐÓNG TAY' in text for text in texts)
    finally:
        relay.close()


def test_fill_and_receipt_both_roll_back_if_the_ledger_transaction_fails(system):
    engine, _, store = system
    engine.open_manual('LONG', 2, 'MOK'); engine.poll()
    position = store.positions()[0]
    order = Order.create(position.symbol, position.side, 1, action='CLOSE', position_id=position.id)
    store.save_order(order)
    count = len(store.all('entry_notice'))
    with pytest.raises(RuntimeError, match='rollback'):
        with store.transaction():
            engine._apply_update(order, dict(status='FILLED', filled=1, avg_fill=2010, fee=0))
            raise RuntimeError('rollback')
    assert store.position(position.id).quantity == 2
    assert store.order(order.id).filled == 0
    assert len(store.all('entry_notice')) == count


def test_unknown_close_never_claims_filled_or_exposes_a_broker_error(system, monkeypatch):
    engine, broker, store = system
    engine.open_manual('SHORT', 1, 'MOK'); engine.poll()
    receiver = EntryNotices(store)
    calls = []
    def timeout(order):
        calls.append(order.id)
        raise UnknownOutcome('private account / OTP / token must stay local')
    monkeypatch.setattr(broker, 'submit', timeout)
    order = engine.close_position(store.positions()[0].id, 1)
    assert order.status == 'UNKNOWN' and store.positions()[0].quantity == 1
    relay = EntryRelay(store)
    try:
        relay.flush(); receiver.observe(enabled=True, chat='offline-chat')
        text = store.db.execute('SELECT text FROM outbox').fetchone()[0]
        assert 'CHỜ ĐỐI SOÁT' in text and 'Khớp 0/1' in text and 'Còn 1 HĐ' in text
        assert 'ĐÃ KHỚP' not in text and 'private' not in text and 'OTP' not in text
        with store.transaction():
            engine._apply_update(store.order(order.id), dict(status='FILLED', filled=1, avg_fill=1990, fee=0))
        relay.flush(); receiver.observe(enabled=True, chat='offline-chat')
        texts = [row[0] for row in store.db.execute('SELECT text FROM outbox ORDER BY rowid')]
        assert len(texts) == 2 and 'ĐÃ KHỚP' in texts[-1] and 'Còn 0 HĐ' in texts[-1]
        assert len(calls) == 1
    finally:
        relay.close()


def test_close_cancel_receipt_waits_for_broker_confirmation(system):
    engine, _, store = system
    engine.open_manual('LONG', 2, 'MOK'); engine.poll()
    receiver = EntryNotices(store)
    order = engine.close_position(store.positions()[0].id, 1, kind='LO', price=2030)
    relay = EntryRelay(store)
    try:
        engine.cancel(order.id)
        assert store.order(order.id).status == 'CANCEL_PENDING'
        relay.flush(); receiver.observe(enabled=True, chat='offline-chat')
        assert all('ĐÃ HỦY' not in row[0] for row in store.db.execute('SELECT text FROM outbox'))
        engine.poll()
        relay.flush(); receiver.observe(enabled=True, chat='offline-chat')
        texts = [row[0] for row in store.db.execute('SELECT text FROM outbox ORDER BY rowid')]
        assert len(texts) == 2 and 'ĐÃ HỦY' in texts[-1] and 'Khớp 0/1' in texts[-1]
        assert 'Còn 2 HĐ' in texts[-1] and store.positions()[0].quantity == 2
    finally:
        relay.close()


def test_disabled_trade_receipts_are_not_replayed_when_enabled_or_restarted(system):
    engine, _, store = system
    engine.open_manual('LONG', 1, 'MOK'); engine.poll()
    receiver = EntryNotices(store)
    engine.close_position(store.positions()[0].id, 1)
    relay = EntryRelay(store)
    try:
        relay.flush(); receiver.observe(enabled=False, chat='offline-chat')
        receiver.observe(enabled=True, chat='offline-chat')
        EntryNotices(store).observe(enabled=True, chat='offline-chat')
        assert not store.db.execute('SELECT id FROM outbox').fetchall()
        assert any(row['kind'] == 'ĐÓNG / GIẢM' for row in store.all('signal_history'))
    finally:
        relay.close()


def runtime_notifications(store):
    runtime = SignalNotifications()
    runtime.store, runtime.settings = store, Settings(entry_notifications=True)
    runtime.owner_enabled, runtime.owner_token, runtime.owner_chat = True, 'offline-token', 'offline-chat'
    runtime.telegram_error = ''
    return runtime


def test_telegram_rate_limit_waits_for_retry_after_and_preserves_the_receipt(system, monkeypatch):
    runtime = runtime_notifications(system[2])
    runtime.store.notify('owner:offline-chat', 'VN30F1M · EXIT · PAPER\nSL', key='close-receipt')
    calls, clock = [], [100.]
    monkeypatch.setattr('ckps.services.signal_notifications.time.monotonic', lambda: clock[0])
    def send(*args, **kwargs):
        calls.append(kwargs['json'])
        if len(calls) == 1:
            return SimpleNamespace(ok=False, status_code=429,
                json=lambda: {'ok': False, 'parameters': {'retry_after': 12}, 'description': 'private'})
        return SimpleNamespace(ok=True, status_code=200, json=lambda: {'ok': True})
    monkeypatch.setattr('ckps.services.signal_notifications.requests.post', send)
    runtime._flush_telegram()
    assert '12 giây' in runtime.telegram_error and 'private' not in runtime.telegram_error
    assert runtime.store.db.execute('SELECT sent FROM outbox').fetchone()[0] == 0
    clock[0] = 111.9; runtime._flush_telegram()
    assert len(calls) == 1
    clock[0] = 112.; runtime._flush_telegram(); runtime._flush_telegram()
    assert len(calls) == 2 and runtime.telegram_error == ''
    assert runtime.store.db.execute('SELECT sent FROM outbox').fetchone()[0] == 1


def test_telegram_disconnect_keeps_queue_and_hides_token_from_error(system, monkeypatch):
    runtime = runtime_notifications(system[2])
    runtime.store.notify('owner:offline-chat', 'VN30F1M · EXIT · PAPER\nDYNAMIC')
    calls = []
    def send(*args, **kwargs):
        calls.append(args)
        raise requests.Timeout('https://api.telegram.org/botSECRET/sendMessage')
    monkeypatch.setattr('ckps.services.signal_notifications.requests.post', send)
    runtime._flush_telegram(); runtime._flush_telegram()
    assert len(calls) == 1 and 'SECRET' not in runtime.telegram_error
    assert runtime.store.db.execute('SELECT sent FROM outbox').fetchone()[0] == 0
    runtime.settings.entry_notifications = False
    runtime._drop_disabled_owner()
    assert runtime.store.db.execute('SELECT sent FROM outbox').fetchone()[0] == 2


def test_backend_reports_telegram_error_even_while_waiting_for_dnse():
    settings = Settings(telegram_enabled=True, telegram_chat='offline-chat')
    value = {'telegram_error': 'Telegram giới hạn gửi · chờ 12 giây.'}
    assert 'Chờ giá DNSE · Telegram giới hạn gửi' in snapshot_status(value, settings, token_available=True)
    value.update(contract='VN30F1M', quotes={'VN30F1M': asdict(Quote('VN30F1M', 2000))})
    assert 'Chờ nến 1D' in snapshot_status(value, settings, token_available=True)
    assert 'thiếu token' in snapshot_status(value, settings, token_available=False)
    settings.telegram_enabled = False
    assert snapshot_status(value, settings, token_available=True).endswith('Telegram OFF')


def test_legacy_open_receipt_still_renders_and_incomplete_fill_cannot_claim_success():
    value = dict(symbol='VN30F1M', side='LONG', mode='REAL', status='FILLED', filled=1, quantity=2, price=2000)
    text, kind = receipt_text(value, 1_000_000_000)
    assert kind == 'VÀO LỆNH' and ' · ENTRY · REAL' in text
    assert 'CHỜ ĐỐI SOÁT' in text and 'ĐÃ KHỚP' not in text
