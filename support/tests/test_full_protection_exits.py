"""ARM/DYNAMIC close whole integer holdings and retain a durable exit intent."""
from dataclasses import asdict
import time

import pytest

from ckps.connections.dnse.protocol import UnknownOutcome
from ckps.models import ExitSettings, Quote
from ckps.rules.defaults import shared_exit_settings
from ckps.trading.execution import Engine


def protect(system, stage, side, qty=3):
    engine, broker, store = system
    engine.paper_capital(500_000_000)
    engine.settings.exit = asdict(ExitSettings(arm_enabled=stage == 'ARM', arm_gain=1,
        trail_gap=.25, arm_close_pct=33, dynamic_enabled=stage == 'DYN', dynamic_close_pct=50,
        arm_repeat=False, dynamic_repeat=False, atr_start_multiplier=.5, retention_pct=70))
    engine._atr = lambda _: 1.
    engine.open_manual(side, qty, 'MOK'); engine.poll(); engine.arm(True)
    sign = 1 if side == 'LONG' else -1
    peak = 2000 + sign * (28 if stage == 'ARM' else 12)
    hit = 2000 + sign * (23 if stage == 'ARM' else 8)
    broker.set_price(peak); engine.poll()
    assert len(store.orders()) == 1
    return engine, broker, store, peak, hit


def rebound(engine, symbol, hit, peak):
    now = time.time()
    samples = (Quote(symbol, hit, at=now), Quote(symbol, peak, at=now))
    engine.on_prices({symbol: samples[-1]}, {symbol: (min(hit, peak), max(hit, peak))}, samples)


@pytest.mark.parametrize('stage', ['ARM', 'DYN'])
@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
@pytest.mark.parametrize('qty', [1, 2, 3, 7])
def test_first_hit_closes_all_whole_contracts_even_when_price_rebounds(system, stage, side, qty):
    engine, broker, store, peak, hit = protect(system, stage, side, qty)
    rebound(engine, broker.contract, hit, peak)
    closes = [o for o in store.orders() if o.action == 'CLOSE']
    assert len(closes) == 1 and closes[0].reason == stage and closes[0].applied == qty
    assert closes[0].avg_fill == peak  # Submission/fill uses current price, not the earlier hit.
    assert not store.positions()
    for _ in range(3): engine.poll()
    assert len(store.orders()) == 2


@pytest.mark.parametrize('stage', ['ARM', 'DYN'])
@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_exit_waits_for_reserved_contracts_and_survives_restart_without_a_repeat_step(system, stage, side):
    engine, broker, store, peak, hit = protect(system, stage, side)
    p = store.positions()[0]
    waiting = engine.close_position(p.id, 3, kind='LO', price=2100 if side == 'LONG' else 1900)
    rebound(engine, broker.contract, hit, peak)
    assert store.order(waiting.id).status == 'CANCEL_PENDING'
    assert store.position(p.id).metrics['full_exit']['reason'] == stage
    restarted = Engine(store, broker, engine.settings)
    restarted._atr = engine._atr
    restarted.poll()
    assert not restarted.enabled.is_set() and store.position(p.id).quantity == 3
    restarted.arm(True); restarted.poll()
    assert not store.positions() and store.orders()[-1].applied == 3
    assert store.orders()[-1].reason == stage


@pytest.mark.parametrize('stage', ['ARM', 'DYN'])
@pytest.mark.parametrize('outcome', ['UNKNOWN', 'REJECTED', 'CANCELLED'])
def test_uncertain_or_failed_full_exit_is_not_posted_again(system, monkeypatch, stage, outcome):
    engine, broker, store, peak, hit = protect(system, stage, 'LONG')
    calls = []
    def submit(order, **kwargs):
        calls.append(order.id)
        if outcome == 'UNKNOWN': raise UnknownOutcome('offline unknown')
        return dict(broker_id='offline-close', status=outcome, filled=0, quantity=order.quantity)
    monkeypatch.setattr(broker, 'submit', submit)
    rebound(engine, broker.contract, hit, peak)
    for _ in range(3): engine.poll()
    assert len(calls) == 1 and store.order(calls[0]).status == outcome
    assert store.positions()[0].quantity == 3


@pytest.mark.parametrize('stage', ['ARM', 'DYN'])
def test_turning_off_branch_stops_its_latched_full_exit(system, stage):
    engine, broker, store, peak, hit = protect(system, stage, 'LONG')
    p = store.positions()[0]
    engine.close_position(p.id, 3, kind='LO', price=2100)
    rebound(engine, broker.contract, hit, peak)
    engine.settings.exit['arm_enabled' if stage == 'ARM' else 'dynamic_enabled'] = False
    engine.poll(); engine.poll()
    assert store.position(p.id).quantity == 3 and len(store.orders()) == 2
    assert not store.position(p.id).metrics.get('full_exit')


@pytest.mark.parametrize('stage', ['ARM', 'DYN'])
@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_confirmed_partial_fill_then_cancel_closes_only_the_remainder_after_rebound(system, monkeypatch, stage, side):
    engine, broker, store, peak, hit = protect(system, stage, side)
    sent = []
    def submit(order, can_submit=None):
        assert can_submit()
        sent.append(order.quantity)
        return dict(broker_id=f'offline-{len(sent)}', status='CANCELLED' if len(sent) == 1 else 'FILLED',
            filled=1 if len(sent) == 1 else order.quantity, avg_fill=hit if len(sent) == 1 else peak)
    monkeypatch.setattr(broker, 'submit', submit)
    rebound(engine, broker.contract, hit, peak)
    assert store.positions()[0].quantity == 2
    engine._manage()
    assert not store.positions() and sent == [3, 2]
    engine._manage()
    assert sent == [3, 2]


@pytest.mark.parametrize('stage', ['ARM', 'DYN'])
@pytest.mark.parametrize('permission', ['bot', 'position'])
def test_crossing_without_bot_or_position_permission_cannot_latch_a_full_exit(system, stage, permission):
    engine, broker, store, peak, hit = protect(system, stage, 'LONG')
    p = store.positions()[0]
    if permission == 'bot': engine.disarm()
    else: engine.set_managed(p.id, False)
    rebound(engine, broker.contract, hit, peak)
    assert store.position(p.id).quantity == 3 and len(store.orders()) == 1
    assert not store.position(p.id).metrics.get('full_exit')


@pytest.mark.parametrize('stage', ['ARM', 'DYN'])
@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_full_protection_exit_cancels_pending_manual_additions(system, stage, side):
    engine, broker, store, peak, hit = protect(system, stage, side)
    pending = engine.open_manual(side, 1, 'LO', price=1900 if side == 'LONG' else 2100)
    rebound(engine, broker.contract, hit, peak)
    engine.poll()
    assert not store.positions() and store.order(pending.id).status == 'CANCELLED'
    assert store.order(pending.id).abandon_remainder


def test_full_dynamic_does_not_require_margin_for_an_unused_legacy_repeat(system):
    engine, broker, store, peak, hit = protect(system, 'DYN', 'LONG')
    engine.settings.exit.update(trailing_unit='PNL_PERCENT', dynamic_repeat=True, repeat_gap=1.25)
    p = store.positions()[0]
    p.margin_per_contract = None
    store.save_position(p)
    rebound(engine, broker.contract, hit, peak)
    assert not store.positions() and store.orders()[-1].applied == 3


def test_unused_legacy_repeat_with_zero_gap_cannot_block_full_exit_rules():
    values = asdict(ExitSettings(arm_enabled=True, arm_gain=1, trail_gap=.25,
        arm_repeat=True, dynamic_enabled=True, dynamic_repeat=True, repeat_gap=0))
    rules = ExitSettings(**shared_exit_settings(values)).validate()
    assert rules.arm_close_pct == rules.dynamic_close_pct == 100
    assert rules.repeat_gap == 0
