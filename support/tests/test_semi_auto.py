from dataclasses import asdict
from datetime import datetime
import time

import pytest

from ckps.connections.dnse.account import balances
from ckps.models import ExitSettings, Order, Position, Snapshot, Settings
from ckps.rules.p2.market import VN_TZ
from ckps.rules.protection import evaluate, repeat_trigger, levels
from ckps.services import calendar
from ckps.services.calendar import CalendarNotices
from ckps.services.entry_notices import EntryNotices, EntryRelay
from ckps.trading.portfolio import capacity


def test_bad_broker_money_is_unknown_and_stock_is_never_used():
    assert balances({'remainSecure': 'bad', 'usedSecure': 0})['collateral_total'] is None
    assert balances({'remainSecure': 70_000_000, 'usedSecure': 30_000_000})['collateral_total'] == 100_000_000
    assert balances({'remainSecure': 70, 'usedSecure': float('nan')})['used_margin'] is None


def test_ticket_price_changes_margin_and_caps():
    snapshot = Snapshot('VN30F1M', [], [], {}, 100_000_000, 0, 40_000_000, 2, 2,
                        pending_margin=0, margin_reference_price=2000)
    result = capacity(Settings(capital_limit=80_000_000), snapshot, [], [], 'SHORT', 2100, ExitSettings())
    assert result.maximum == 1 and result.margin_per_contract == 42_000_000


def test_real_ppse_is_queried_at_ticket_price_without_candle_io(monkeypatch):
    from ckps.connections.dnse.client import DNSEBroker
    from ckps.models import Quote
    broker = DNSEBroker('key', 'secret', '123', '7')
    broker.resolve = lambda: '41I1GB000'
    broker.feed.start = lambda symbols: None
    broker.get_quote = lambda symbol: Quote(symbol, 2000)
    broker.daily_bars = lambda: pytest.fail('snapshot must not block on candles')
    broker.packages = [{'id': 7, 'initialRate': .2}]
    broker.packages_at = time.time()
    calls = []
    def request(method, path, **kwargs):
        assert method == 'GET'
        calls.append((path, kwargs.get('params', {})))
        if path.endswith('/balances'): return {'stock': {'totalCash': 900_000_000}, 'derivative': {'remainSecure': 100_000_000, 'usedSecure': 0}}
        if path.endswith('/positions'): return {'positions': []}
        if path.endswith('/orders'): return {'orders': []}
        if path.endswith('/ppse'): return {'qmaxBuy': 2, 'qmaxSell': 2}
        pytest.fail(path)
    monkeypatch.setattr(broker, 'request', request)
    try:
        snapshot = broker.snapshot()
        assert snapshot.collateral_total == 100_000_000 and snapshot.total_money == 900_000_000 and snapshot.bars == []
        assert snapshot.qmax_long == 2  # Stock total cash is display-only.
        limits = broker.opening_limits(snapshot.contract, 2100)
        assert calls[-1][1]['price'] == '2100'
        assert limits['margin_per_contract'] == 42_000_000
    finally:
        broker.close()


def test_filled_must_have_evidence_for_all_contracts(system):
    engine, _, store = system
    order = Order.create('VN30F1M', 'LONG', 3)
    with store.transaction():
        engine._apply_update(order, {'broker_id': 'x', 'status': 'FILLED', 'filled': 1, 'avg_fill': 2000})
    assert store.order(order.id).status == 'UNKNOWN'
    assert store.order(order.id).pending and store.positions()[0].quantity == 1


@pytest.mark.parametrize('side,limit,stop', [('LONG', 1990, 1995), ('SHORT', 2010, 2005)])
def test_full_exit_cancels_pending_additions(system, side, limit, stop):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(sl_enabled=True, sl_distance=5))
    pending = engine.open_manual(side, 1, 'LO', price=limit)
    engine.open_manual(side, 1, 'MOK')
    engine.arm(True)
    broker.set_price(stop)
    engine.poll()
    engine.poll()
    assert not store.positions()
    assert store.order(pending.id).status == 'CANCELLED'
    broker.set_price(limit)
    engine.poll()
    assert not store.positions()


def test_failed_late_fill_close_does_not_keep_sending(system, monkeypatch):
    from ckps.connections.dnse.protocol import BrokerError
    engine, _, store = system
    position = Position.create('VN30F1M', 'LONG', 1, 2000)
    position.metrics.update(closing_all=True, late_open_fill=True)
    store.save_position(position)
    calls = []
    def reject(*args, **kwargs):
        calls.append(True)
        order = Order.create('VN30F1M', 'LONG', 1, action='CLOSE', status='FAILED')
        store.save_order(order)
        raise BrokerError('DNSE từ chối')
    monkeypatch.setattr(engine, 'close_position', reject)
    engine._complete_full_exits()
    engine._complete_full_exits()
    assert len(calls) == 1


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_repeat_uses_new_round_and_arm_guard(side, sign):
    p = Position.create('VN30F1M', side, 4, 2000, history_verified=True)
    p.best = 2000 + sign * 100
    p.metrics['ARM:AUTO'] = {'count': 1, 'anchor': 2000 + sign * 40}
    rules = ExitSettings(arm_enabled=True, arm_gain=10, trail_gap=5, arm_repeat=True, repeat_gap=5)
    evaluate(p, 2000 + sign * 60, rules)
    assert repeat_trigger(p, rules, 'ARM', levels(p, rules)['protect']) == 2000 + sign * 55
    assert evaluate(p, 2000 + sign * 55, rules).reason == 'ARM'
    p.metrics['ARM:AUTO'] = {'count': 1, 'anchor': 2000 + sign * 12}
    assert evaluate(p, 2000 + sign * 7, rules) is None


def test_expiry_is_a_reminder_not_a_gate(system):
    _, _, store = system
    calendar.write_settings(calendar.CalendarSettings())
    notice = CalendarNotices(store)
    notice.observe(now=datetime(2026, 11, 18, 15, 0, tzinfo=VN_TZ), enabled=True, chat='test')
    assert 'ĐÁO HẠN' in store.db.execute('SELECT text FROM outbox').fetchone()[0]
    assert not calendar.block_reason(datetime(2026, 11, 19, 10, 0, tzinfo=VN_TZ))


def test_entry_receipts_do_not_expose_account_or_send_when_off(system):
    engine, _, store = system
    receiver = EntryNotices(store)
    engine.open_manual('LONG', 1, 'MOK')
    relay = EntryRelay(store)
    try:
        relay.flush()
        receiver.observe(enabled=False, chat='test', now=time.time())
        assert store.all('signal_history')
        assert not store.db.execute('SELECT id FROM outbox').fetchall()
        assert 'account' not in str(store.all('signal_history')).lower()
    finally:
        relay.close()


def test_entry_receipt_emits_once_and_does_not_replay_on_restart(system):
    engine, _, store = system
    receiver = EntryNotices(store)
    engine.open_manual('SHORT', 1, 'MOK')
    relay = EntryRelay(store)
    try:
        relay.flush()
        receiver.observe(enabled=True, chat='test')
        rows = store.db.execute('SELECT text FROM outbox').fetchall()
        assert len(rows) == 1 and 'SHORT' in rows[0][0] and 'ĐÃ KHỚP' in rows[0][0]
        receiver.observe(enabled=True, chat='test')
        EntryNotices(store).observe(enabled=True, chat='test')
        assert store.db.execute('SELECT count(*) FROM outbox').fetchone()[0] == 1
    finally:
        relay.close()


def test_expiry_old_block_preference_is_migrated_to_reminder():
    from ckps.rules.calendar import CalendarSettings, entry_block
    settings = CalendarSettings.from_dict({'avoid_vn30_expiry_entry': True})
    assert not settings.avoid_vn30_expiry_entry
    assert not entry_block(datetime(2026, 11, 19, 10, 0, tzinfo=VN_TZ), settings, {})


def test_confirm_rejects_changed_risk_before_queue():
    from types import SimpleNamespace
    from ckps.dashboard.actions import DashboardActionsMixin
    from ckps.trading.portfolio import Capacity
    class Value:
        def __init__(self, value): self.value = value
        def get(self): return self.value
    rule = ExitSettings(sl_enabled=True, sl_distance=10)
    captured, sent = [], []
    app = SimpleNamespace(mode_requested=None, switch_pending=None, qty=Value('1'), limit=Value('2000'),
        kind=Value('LO'), ticket_sl=Value('RULE'), ticket_tp=Value('RULE'),
        view={'contract': 'VN30F1M'}, settings=Settings(), open_buttons=[],
        ticket_rules=lambda _: (rule, None), ticket_capacity=lambda *args: Capacity(2, 2, 1_000_000, None, margin_per_contract=33_000_000),
        confirm=lambda text, callback: captured.append(callback), report=lambda *args, **kwargs: pytest.fail(str(args)),
        send=lambda *args, **kwargs: sent.append(args))
    DashboardActionsMixin.open_order(app, 'LONG')
    rule.sl_distance = 20
    with pytest.raises(ValueError, match='E/M đã thay đổi'):
        captured[0]()
    assert not sent
