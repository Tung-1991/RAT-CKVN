"""PAPER fills need an active session; every accepted order expires that day."""
from dataclasses import replace
from datetime import datetime

import pytest

from ckps.models import Quote
from ckps.rules.p2.market import VN_TZ
from ckps.services import calendar
from ckps.trading.execution import Engine


@pytest.fixture
def paper_session(system, monkeypatch):
    engine, broker, store = system
    clock = [datetime(2026, 11, 3, 10, tzinfo=VN_TZ)]
    monkeypatch.setattr(calendar, 'local_now', lambda: clock[0])
    monkeypatch.setattr('time.time', lambda: clock[0].timestamp())
    monkeypatch.setattr(broker, '_quote', lambda symbol: Quote(symbol, broker.price,
        at=clock[0].timestamp(), source='DNSE'))
    original = broker.snapshot
    monkeypatch.setattr(broker, 'snapshot', lambda: replace(original(), observed_at=clock[0].timestamp()))
    engine.poll(manage=False)
    return engine, broker, store, clock


@pytest.mark.parametrize('day,hour,minute', [(3, 14, 45), (3, 17, 0), (4, 9, 5)])
def test_ordinary_lo_expires_before_a_closing_or_next_day_price_can_fill_it(paper_session, day, hour, minute):
    engine, broker, store, clock = paper_session
    order = engine.open_manual('LONG', 1, 'LO', 1990)
    cash = store.get('paper', 'account')['cash']
    clock[0] = datetime(2026, 11, day, hour, minute, tzinfo=VN_TZ)
    broker.set_price(1989)
    engine.poll(manage=False)
    saved = store.order(order.id)
    assert saved.status == 'EXPIRED' and saved.filled == 0
    assert not store.positions() and store.get('paper', 'account')['cash'] == cash
    assert engine.latest.pending_margin == 0


def test_lunch_price_cannot_fill_a_working_order(paper_session):
    engine, broker, store, clock = paper_session
    order = engine.open_manual('LONG', 1, 'LO', 1990)
    clock[0] = datetime(2026, 11, 3, 12, tzinfo=VN_TZ)
    broker.set_price(1989)
    engine.poll(manage=False)
    assert store.order(order.id).status == 'WORKING' and not store.positions()
    clock[0] = clock[0].replace(hour=13)
    engine.poll(manage=False)
    assert store.order(order.id).status == 'FILLED' and store.positions()[0].entry == 1989


def test_already_accepted_lo_can_fill_in_atc_despite_entry_avoidance(paper_session):
    engine, broker, store, clock = paper_session
    order = engine.open_manual('LONG', 1, 'LO', 1990)
    clock[0] = clock[0].replace(hour=14, minute=35)
    assert calendar.block_reason().startswith('ATC')
    broker.set_price(1989)
    engine.poll(manage=False)
    assert store.order(order.id).status == 'FILLED' and store.positions()[0].quantity == 1


@pytest.mark.parametrize('legacy', [False, True])
def test_pending_lo_is_not_renewed_by_restart(paper_session, legacy):
    engine, broker, store, clock = paper_session
    order = engine.open_manual('LONG', 1, 'LO', 1990)
    if legacy:
        row = store.get('paper_order', order.id)
        row.pop('session_date')
        row['created_at'] = clock[0].timestamp()
        store.put('paper_order', order.id, row)
    clock[0] = datetime(2026, 11, 4, 9, 5, tzinfo=VN_TZ)
    broker.set_price(1989)
    restarted = Engine(store, broker, engine.settings)
    restarted.poll(manage=False)
    assert not restarted.enabled.is_set()
    assert store.order(order.id).status == 'EXPIRED' and not store.positions()


def test_unfilled_close_expires_without_changing_the_holding(paper_session):
    engine, broker, store, clock = paper_session
    engine.open_manual('LONG', 2, 'MOK')
    engine.poll(manage=False)
    position = store.positions()[0]
    order = engine.close_position(position.id, 1, kind='LO', price=2010)
    clock[0] = clock[0].replace(hour=14, minute=45)
    broker.set_price(2011)
    engine.poll(manage=False)
    assert store.order(order.id).status == 'EXPIRED'
    assert store.position(position.id).quantity == 2 and store.position(position.id).realized == 0
