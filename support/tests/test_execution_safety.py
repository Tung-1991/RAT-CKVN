"""Offline regressions for stop precedence and broker quantity evidence."""
from dataclasses import asdict
from datetime import datetime, timedelta

import pytest

from ckps.connections.dnse.protocol import UnknownOutcome, normalize_order
from ckps.models import ExitSettings, Order
from ckps.rules.p2.market import VN_TZ
from ckps.trading.execution import Engine


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_sl_closes_unreserved_contracts_while_limit_close_waits(system, side, sign):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(sl_enabled=True, sl_distance=.5))
    engine.open_manual(side, 2, 'MOK')
    engine.poll()
    position = store.positions()[0]
    waiting = engine.close_position(position.id, 1, kind='LO', price=2000 + sign * 10)
    engine.poll()
    engine.arm(True)
    broker.set_price(2000 - sign * 11)
    engine.poll()
    stops = [o for o in store.orders() if o.reason == 'SL']
    assert len(stops) == 1 and stops[0].filled == 1
    assert store.order(waiting.id).status == 'CANCEL_PENDING'
    assert store.position(position.id).quantity == 1
    engine.poll()
    assert not store.positions()
    assert sum(o.applied for o in store.orders() if o.action == 'CLOSE') == 2


def test_unrequested_broker_quantity_change_blocks_reconciliation(system):
    engine, _, store = system
    order = Order.create('VN30F1M', 'LONG', 1)
    store.save_order(order)
    with store.transaction():
        engine._apply_update(order, dict(broker_id='broker-one', symbol=order.symbol,
            exchange_side='NB', quantity=5, status='WORKING', filled=0, price=1990))
    saved = store.order(order.id)
    assert saved.status == 'UNKNOWN'
    assert saved.quantity == 1 and not store.positions()
    assert '5' in saved.message


def test_normalization_preserves_absent_quantity_in_ack():
    assert normalize_order({'orderId': 'ack', 'status': 'NEW'})['quantity'] is None


def test_sparse_ack_can_reconcile_but_explicit_zero_cannot(system):
    engine, _, store = system
    order = Order.create('VN30F1M', 'LONG', 1)
    store.save_order(order)
    with store.transaction():
        engine._apply_update(order, normalize_order({'orderId': 'ack', 'status': 'NEW'}))
    assert store.order(order.id).status == 'WORKING'
    with store.transaction():
        engine._apply_update(store.order(order.id), dict(broker_id='ack', status='WORKING', filled=0, quantity=0))
    assert store.order(order.id).status == 'UNKNOWN'


def protected_position(system, reason, side='LONG'):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(sl_enabled=reason == 'SL', sl_distance=.5,
                                               ema_exit_enabled=reason == 'E'))
    engine.open_manual(side, 2, 'MOK')
    engine.poll()
    now = datetime.now(VN_TZ)
    broker.set_bars([dict(time=(now-timedelta(days=n)).timestamp(), close=2000)
                    for n in range(30, 0, -1) if (now-timedelta(days=n)).weekday() < 5])
    return engine, broker, store, store.positions()[0]


@pytest.mark.parametrize('reason', ['SL', 'E'])
@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_full_reserved_exit_survives_cancel_confirmation_restart_and_rebound(system, reason, side, sign):
    engine, broker, store, position = protected_position(system, reason, side)
    waiting = engine.close_position(position.id, 2, kind='LO', price=2000+sign*10)
    engine.poll()
    engine.arm(True)
    broker.set_price(2000-sign*11)
    engine.poll()
    assert store.order(waiting.id).status == 'CANCEL_PENDING'
    assert not [o for o in store.orders() if o.reason == reason]
    restarted = Engine(store, broker, engine.settings)
    broker.set_price(2000)  # The stop was already observed before the rebound.
    restarted.poll()
    assert not restarted.enabled.is_set() and store.position(position.id).quantity == 2
    restarted.arm(True)
    restarted.poll()
    assert not store.positions()
    exits = [o for o in store.orders() if o.reason == reason]
    assert len(exits) == 1 and exits[0].applied == 2


@pytest.mark.parametrize('reason', ['SL', 'E'])
def test_cancel_timeout_never_releases_reservation_or_retries_automatically(system, monkeypatch, reason):
    engine, broker, store, position = protected_position(system, reason)
    waiting = engine.close_position(position.id, 1, kind='LO', price=2010)
    engine.poll()
    requests = []
    def timeout(order):
        requests.append(order.id)
        raise UnknownOutcome('cancel outcome unknown')
    monkeypatch.setattr(broker, 'cancel', timeout)
    engine.arm(True)
    broker.set_price(1989)
    for _ in range(4):
        engine.poll()
    assert requests == [waiting.id]
    assert store.position(position.id).quantity == 1
    exits = [o for o in store.orders() if o.reason == reason]
    assert len(exits) == 1 and exits[0].applied == 1
    assert store.order(waiting.id).pending


@pytest.mark.parametrize('reason', ['SL', 'E'])
def test_fill_during_cancel_cannot_reverse_position(system, monkeypatch, reason):
    engine, broker, store, position = protected_position(system, reason)
    waiting = engine.close_position(position.id, 1, kind='LO', price=2010)
    engine.poll()
    cancel = broker.cancel
    def fill_then_cancel(order):
        broker.set_price(2010)
        broker.snapshot()  # The old LO fills before the cancellation reaches it.
        cancel(order)
    monkeypatch.setattr(broker, 'cancel', fill_then_cancel)
    engine.arm(True)
    broker.set_price(1989)
    engine.poll()
    engine.poll()
    assert not store.positions()
    assert store.order(waiting.id).applied == 1
    assert sum(o.applied for o in store.orders() if o.action == 'CLOSE') == 2
    assert not [o for o in store.orders() if o.status == 'UNKNOWN']


def test_protective_cancel_keeps_management_but_operator_cancel_revokes_it(system):
    engine, broker, store, position = protected_position(system, 'SL')
    waiting = engine.close_position(position.id, 1, kind='LO', price=2010)
    order = store.order(waiting.id)
    order.source, order.reason = 'AUTO', 'ARM'
    store.save_order(order)
    engine.arm(True)
    broker.set_price(1989)
    engine.poll()
    assert store.position(position.id).managed
    engine.disarm()
    engine.poll()  # Confirm the protective cancellation without another stop.
    waiting = engine.close_position(position.id, 1, kind='LO', price=2010)
    order = store.order(waiting.id)
    order.source, order.reason = 'AUTO', 'ARM'
    store.save_order(order)
    engine.cancel(order.id)
    assert not store.position(position.id).managed
    assert 'full_exit' not in store.position(position.id).metrics


@pytest.mark.parametrize('reason', ['SL', 'E'])
@pytest.mark.parametrize('outcome', ['UNKNOWN', 'REJECTED', 'CANCELLED'])
def test_unknown_or_rejected_full_exit_is_not_submitted_again(system, monkeypatch, reason, outcome):
    engine, broker, store, _ = protected_position(system, reason)
    requests = []
    def timeout(order, can_submit=None):
        requests.append(order.id)
        if outcome == 'UNKNOWN':
            raise UnknownOutcome('unknown POST result')
        return dict(broker_id='rejected', status=outcome, filled=0, quantity=order.quantity)
    monkeypatch.setattr(broker, 'submit', timeout)
    engine.arm(True)
    broker.set_price(1989)
    for _ in range(3):
        engine.poll()
    assert len(requests) == 1
    assert store.order(requests[0]).status == outcome


def test_disabling_branch_cancels_its_latched_intent(system):
    engine, broker, store, position = protected_position(system, 'SL')
    engine.close_position(position.id, 2, kind='LO', price=2010)
    engine.poll()
    engine.arm(True)
    broker.set_price(1989)
    engine.poll()
    engine.settings.exit['sl_enabled'] = False
    engine.poll()
    assert store.position(position.id).quantity == 2
    assert 'full_exit' not in store.position(position.id).metrics


def test_amend_ack_only_accepts_old_or_requested_quantity_and_preserves_fill(system):
    engine, _, store = system
    order = Order.create('VN30F1M', 'LONG', 2, replacement={'quantity': 3, 'price': 1990})
    store.save_order(order)
    update = dict(broker_id='amended', symbol=order.symbol, exchange_side='NB',
                  quantity=2, status='PARTIAL', filled=1, avg_fill=2000, price=1980)
    with store.transaction():
        engine._apply_update(order, update)
    assert store.order(order.id).status == 'REPLACE_PENDING'
    assert store.positions()[0].quantity == 1
    with store.transaction():
        engine._apply_update(store.order(order.id), dict(update, quantity=5, filled=2))
    assert store.order(order.id).status == 'UNKNOWN' and store.order(order.id).applied == 1
    assert store.positions()[0].quantity == 1
    with store.transaction():
        engine._apply_update(store.order(order.id), dict(update, quantity=3, price=1990, filled=2))
    assert store.order(order.id).quantity == 3 and store.order(order.id).applied == 2
    assert store.positions()[0].quantity == 2


def test_free_stop_is_submitted_before_slow_cancellation(system, monkeypatch):
    engine, broker, store, position = protected_position(system, 'SL')
    engine.close_position(position.id, 1, kind='LO', price=2010)
    engine.poll()
    submit, cancel = broker.submit, broker.cancel
    requests = []
    def send(order, can_submit=None):
        requests.append('POST')
        return submit(order, can_submit)
    def remove(order):
        requests.append('DELETE')
        assert store.position(position.id).quantity == 1
        return cancel(order)
    monkeypatch.setattr(broker, 'submit', send)
    monkeypatch.setattr(broker, 'cancel', remove)
    engine.arm(True)
    broker.set_price(1989)
    engine.poll()
    assert requests == ['POST', 'DELETE']


def test_disabled_automatic_exit_never_falls_back_to_manual_late_fill_handler(system, monkeypatch):
    engine, broker, store, position = protected_position(system, 'SL')
    position.metrics.update(closing_all=True, auto_full_exit=True, late_open_fill=True)
    store.save_position(position)
    def forbidden(*args, **kwargs):
        pytest.fail('A disabled automatic exit must not become a manual close.')
    monkeypatch.setattr(engine, 'close_position', forbidden)
    engine._complete_full_exits()
    assert store.position(position.id).quantity == 2
