from dataclasses import asdict, replace
import time

import pytest

from ckps.connections.dnse.protocol import BrokerError, UnknownOutcome
from ckps.models import ExitSettings, Order, Position, Quote
from ckps.trading.execution import Engine


@pytest.mark.parametrize("side,exit_price", [("LONG", 2010), ("SHORT", 1990)])
def test_manual_round_trip_and_no_automatic_entry(system, side, exit_price):
    engine, broker, store = system
    engine.arm(True)
    for _ in range(3):
        engine.poll()
    assert not store.orders()
    engine.open_manual(side, 1, "MOK")
    engine.poll()
    position = store.positions()[0]
    assert position.source == "APP" and position.managed
    broker.set_price(exit_price)
    engine.poll()
    engine.close_position(position.id, 1)
    engine.poll()
    assert not store.positions()
    assert store.positions(closed=True)[0].realized == pytest.approx(1_000_000)
    assert len(store.orders()) == 2


@pytest.mark.parametrize("side,hit", [("LONG", 1980), ("SHORT", 2020)])
def test_bot_off_preserves_manual_open_and_blocks_automatic_stop(system, side, hit):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(sl_enabled=True, sl_distance=10))
    engine.open_manual(side, 1, "MOK")
    engine.poll()
    broker.set_price(hit)
    engine.poll()
    assert len(store.positions()) == 1
    engine.arm(True)
    engine.poll()
    engine.poll()
    assert not store.positions()
    assert store.orders()[-1].reason == "SL"


def test_restart_disarms_without_losing_position_or_floor(system):
    engine, broker, store = system
    engine.open_manual("LONG", 1, "MOK")
    engine.poll()
    position = store.positions()[0]
    position.floor = 2015
    store.save_position(position)
    engine.arm(True)
    restarted = Engine(store, broker, engine.settings)
    assert not restarted.enabled.is_set()
    assert store.positions()[0].floor == 2015


def test_external_position_is_not_adopted_by_global_switch(system):
    engine, broker, store = system
    store.put("paper_position", "VN30F1M", {"symbol": "VN30F1M", "side": "SHORT", "quantity": 1, "entry": 2000})
    engine.poll()
    engine.arm(True)
    position = store.positions()[0]
    assert position.source == "EXTERNAL" and not position.managed
    engine.set_managed(position.id, True)
    assert store.position(position.id).managed


def test_external_increase_pauses_previously_managed_position(system):
    engine, broker, store = system
    engine.open_manual("LONG", 1, "MOK")
    engine.poll()
    order = store.orders()[0]
    order.updated_at = time.time() - 20
    # Preserve the old timestamp without save_order refreshing it.
    store.put("order", order.id, asdict(order))
    store.put("paper_position", "VN30F1M", {"symbol": "VN30F1M", "side": "LONG", "quantity": 2, "entry": 2005})
    engine.poll()
    position = store.positions()[0]
    assert position.quantity == 2 and not position.managed and position.source == "MIXED"


def test_pending_close_reserves_contracts_and_cannot_reverse(system):
    engine, broker, store = system
    engine.open_manual("SHORT", 2, "MOK")
    engine.poll()
    position = store.positions()[0]
    order = engine.close_position(position.id, 2, kind="LO", price=1990)
    assert order.exchange_side == "NB"
    with pytest.raises(ValueError, match="Không đủ"):
        engine.close_position(position.id, 1)


def test_partial_fills_apply_increment_only(system):
    engine, broker, store = system
    order = Order.create("VN30F1M", "LONG", 3)
    store.save_order(order)
    update = {"broker_id": "one", "status": "PARTIAL", "filled": 1, "avg_fill": 2000, "fee": 5000}
    for _ in range(2):
        with store.transaction():
            engine._apply_update(store.order(order.id), update)
    assert store.positions()[0].quantity == 1
    update.update(status="FILLED", filled=3, avg_fill=2010, fee=15000)
    with store.transaction():
        engine._apply_update(store.order(order.id), update)
    position = store.positions()[0]
    assert position.quantity == 3 and position.entry == pytest.approx(2010)
    assert position.fees == 15000


def test_late_fee_is_applied_once_after_fill(system):
    engine, broker, store = system
    order = engine.open_manual("LONG", 1, "MOK")
    update = {"broker_id": order.id, "status": "FILLED", "filled": 1, "avg_fill": 2000, "fee": 5000, "tag": "CKPS:" + order.id}
    engine._reconcile_orders([update])
    engine._reconcile_orders([update])
    assert store.positions()[0].fees == 5000


def test_transport_timeout_is_unknown_and_never_resent(system, monkeypatch):
    engine, broker, store = system
    calls = []
    def timeout(order,can_submit=None):
        calls.append(order.id)
        raise UnknownOutcome("timeout")
    monkeypatch.setattr(broker, "submit", timeout)
    engine.open_manual("LONG", 1, "MOK")
    assert store.orders()[0].status == "UNKNOWN"
    restarted = Engine(store, broker, engine.settings)
    restarted.poll()
    with pytest.raises(BrokerError):
        restarted.open_manual("LONG", 1, "MOK")
    assert len(calls) == 1


def test_unknown_reconciles_by_client_tag(system, monkeypatch):
    engine, broker, store = system
    def timeout(order,can_submit=None):
        raise UnknownOutcome("timeout")
    monkeypatch.setattr(broker, "submit", timeout)
    engine.open_manual("LONG", 1, "MOK")
    order = store.orders()[0]
    engine._reconcile_orders([{"broker_id": "found", "tag": "CKPS:" + order.id,
        "status": "FILLED", "filled": 1, "avg_fill": 2000}])
    assert store.order(order.id).status == "FILLED"
    assert store.positions()[0].quantity == 1


def test_cancel_waits_for_broker_confirmation(system):
    engine, broker, store = system
    order = engine.open_manual("LONG", 1, "LO", price=1990)
    engine.cancel(order.id)
    assert store.order(order.id).status == "CANCEL_PENDING"
    engine.poll()
    assert store.order(order.id).status == "CANCELLED"
    assert not store.positions()


def test_replace_keeps_old_values_until_confirmed(system):
    engine, broker, store = system
    order = engine.open_manual("LONG", 1, "LO", price=1990)
    engine.replace(order.id, 2, 1995)
    pending = store.order(order.id)
    assert pending.status == "REPLACE_PENDING"
    assert pending.quantity == 1 and pending.price == 1990
    engine.poll()
    confirmed = store.order(order.id)
    assert confirmed.quantity == 2 and confirmed.price == 1995
    assert confirmed.status == "WORKING"


def test_stale_quote_blocks_open_and_auto_but_manual_orders_not_retried(system, monkeypatch):
    engine, broker, store = system
    original = broker.snapshot
    def stale():
        snap = original()
        snap.quotes["VN30F1M"].at = time.time() - 300
        return snap
    monkeypatch.setattr(broker, "snapshot", stale)
    with pytest.raises(BrokerError, match="Giá"):
        engine.open_manual("LONG", 1, "MOK")
    assert not store.orders()


def test_order_application_failure_is_unknown_not_safe_to_resend(system, monkeypatch):
    engine, broker, store = system
    monkeypatch.setattr(engine, "_apply_fill", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("ledger fault")))
    with pytest.raises(RuntimeError):
        engine.open_manual("LONG", 1, "MOK")
    assert store.orders()[0].status == "UNKNOWN"


@pytest.mark.parametrize("side,sign", [("LONG", 1), ("SHORT", -1)])
def test_repeat_keeps_gap_and_handoff_anchor_through_rebound_partial_fills_and_restart(system, monkeypatch, side, sign):
    from ckps.models import ExitSettings
    from ckps.rules.protection import evaluate
    engine, broker, store = system
    engine.settings.paper_margin_rate = .05
    engine.settings.exit = asdict(ExitSettings(arm_enabled=True, arm_gain=10, trail_gap=5,
        arm_repeat=True, arm_repeat_below_arm=True, repeat_gap=5, arm_close_pct=50))
    engine.open_manual(side, 6, "MOK")
    engine.poll()
    position = store.positions()[0]
    evaluate(position, 2000 + sign * 20, engine.exits(position))
    store.save_position(position)
    broker.set_price(2000 + sign * 12)  # Gap through the 15-point protective floor.
    engine.poll(manage=False)
    engine.arm(True)
    sent = []
    def delayed(order, can_submit=None):
        engine.latest.quotes[position.symbol].last = 2000 + sign * 11
        assert can_submit()  # A worse final observation before the broker POST.
        sent.append(order.id)
        return {"broker_id":"close-gap", "status":"WORKING", "filled":0}
    monkeypatch.setattr(broker, "submit", delayed)
    engine._manage()
    order = store.order(sent[0])
    assert order.trigger == pytest.approx(2000 + sign * 15)
    assert order.protection_anchor == pytest.approx(2000 + sign * 11)
    for filled, gain, status in [(1, 14, "PARTIAL"), (3, 13, "FILLED")]:
        with store.transaction():
            engine._apply_update(store.order(order.id), {"broker_id":"close-gap", "status":status,
                "filled":filled, "avg_fill":2000 + sign * gain})
    restarted = Engine(store, broker, engine.settings)
    assert not restarted.enabled.is_set()
    remaining = store.position(position.id)
    state = remaining.metrics["ARM:AUTO"]
    assert remaining.quantity == 3 and state["count"] == 1
    assert state["anchor"] == pytest.approx(2000 + sign * 11)
    assert evaluate(remaining, 2000 + sign * 7, restarted.exits(remaining)) is None
    assert evaluate(remaining, 2000 + sign * 6, restarted.exits(remaining)).reason == "ARM"
    assert len(sent) == 1
