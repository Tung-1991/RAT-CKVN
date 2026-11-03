"""Local next-session LO: persistence, permissions, exact-once handoff and real quotes."""
from dataclasses import replace
from datetime import datetime

import pytest

from ckps.connections.dnse.protocol import UnknownOutcome
from ckps.models import Quote
from ckps.rules.p2.market import VN_TZ
from ckps.services import calendar
from ckps.services.entry_schedule import queue_session
from ckps.trading.execution import Engine


@pytest.fixture
def scheduled(system,monkeypatch):
    engine,broker,store=system
    clock=[datetime(2026,11,2,17,0,tzinfo=VN_TZ)]
    monkeypatch.setattr(calendar,'local_now',lambda:clock[0])
    monkeypatch.setattr('time.time',lambda:clock[0].timestamp())
    broker.contract='41I1GB000'
    broker._quote=lambda symbol:Quote(symbol,broker.price,broker.price,broker.price,at=clock[0].timestamp(),source='DNSE')
    original=broker.snapshot
    broker.snapshot=lambda:replace(original(),observed_at=clock[0].timestamp())
    engine.poll(manage=False)
    sent=[];submit=broker.submit
    def record(order,**kwargs):
        sent.append(order.id)
        return submit(order,**kwargs)
    broker.submit=record
    def advance(day=3,hour=9,minute=0):clock[0]=datetime(2026,11,day,hour,minute,tzinfo=VN_TZ)
    return engine,broker,store,sent,advance


def queue(engine,qty=1,price=2000):
    return engine.schedule_manual('LONG',qty,price,'41I1GB000',queue_session()['date'])


def test_queue_survives_restart_and_sends_same_id_only_after_ato_with_fresh_price(scheduled):
    engine,broker,store,sent,advance=scheduled
    order=queue(engine)
    assert order.status=='SCHEDULED' and order.scheduled_for=='2026-11-03' and not order.broker_id
    engine.poll()
    assert not sent and not store.positions() and not store.all('paper_order')
    restarted=Engine(store,broker,engine.settings)
    assert not restarted.enabled.is_set() and store.order(order.id).status=='SCHEDULED'
    advance(hour=8,minute=50);restarted.poll()
    assert not sent
    advance();broker.set_price(1999);restarted.poll();restarted.poll()
    assert sent==[order.id] and store.order(order.id).status=='FILLED'
    assert store.positions()[0].entry==1999


def test_lo_waits_for_market_price_and_expires_after_its_one_session(scheduled):
    engine,broker,store,sent,advance=scheduled
    order=queue(engine,price=1900)
    advance();engine.poll()
    assert store.order(order.id).status=='WORKING' and not store.positions()
    advance(hour=14,minute=45);engine.poll()
    assert store.order(order.id).status=='EXPIRED'
    advance(day=4);broker.set_price(1899);engine.poll()
    assert sent==[order.id] and not store.positions()


def test_fifo_reserves_queued_quantity_without_deadlocking_two_orders(scheduled):
    engine,broker,store,sent,advance=scheduled
    first,second=queue(engine),queue(engine)
    with pytest.raises(ValueError):queue(engine)
    advance();engine.poll();engine.poll();engine.poll()
    assert sent==[first.id,second.id] and store.positions()[0].quantity==2


def test_cancel_local_queue_uses_no_broker_and_releases_the_reservation(scheduled):
    engine,broker,store,sent,advance=scheduled
    order=queue(engine,qty=2)
    broker.cancel=lambda *_:pytest.fail('A local queue must not call broker DELETE')
    engine.cancel(order.id);engine.cancel(order.id)
    assert store.order(order.id).status=='CANCELLED'
    other=queue(engine,qty=2)
    advance();engine.poll()
    assert sent==[other.id]


@pytest.mark.parametrize('changed',['stale','calendar','auth','cancel','shutdown'])
def test_every_deferred_handoff_rechecks_data_permissions_and_cancel_during_get(scheduled,changed):
    engine,broker,store,sent,advance=scheduled
    order=queue(engine)
    advance()
    if changed=='stale':
        broker._quote=lambda symbol:Quote(symbol,2000,at=0,source='DNSE')
    elif changed=='calendar':
        calendar.write_settings(replace(calendar.read_settings(),manual_closed_dates=['2026-11-03']))
    elif changed=='auth':
        broker.mode='REAL';broker.token='';broker.token_until=0
    else:
        def limits(*_):
            if changed=='cancel':engine.suspended_entries.add(order.id)
            else:engine.entry_stopping.set()
            return {}
        broker.opening_limits=limits
    engine.poll()
    assert not sent and store.order(order.id).status=='SCHEDULED'
    if changed=='auth':
        broker.token='offline-token';broker.token_until=calendar.local_now().timestamp()+3600
        engine.poll();assert sent==[order.id]


def test_timeout_and_restart_never_resubmit_a_deferred_order(scheduled):
    engine,broker,store,sent,advance=scheduled
    order=queue(engine)
    def timeout(order,**kwargs):
        sent.append(order.id);raise UnknownOutcome('Simulated timeout')
    broker.submit=timeout
    advance();engine.poll()
    assert store.order(order.id).status=='UNKNOWN'
    restarted=Engine(store,broker,engine.settings)
    restarted.poll();restarted.poll()
    assert sent==[order.id] and store.order(order.id).status=='UNKNOWN'


@pytest.mark.parametrize('change',['missed','rollover'])
def test_missed_session_or_rollover_never_changes_date_or_contract(scheduled,change):
    engine,broker,store,sent,advance=scheduled
    order=queue(engine)
    advance(day=4 if change=='missed' else 3)
    if change=='rollover':broker.contract='41I1GC000'
    engine.poll()
    assert not sent and store.order(order.id).status=='EXPIRED'
    assert store.order(order.id).symbol=='41I1GB000'


def test_queue_rejects_changed_confirmation_and_invalid_parameters(scheduled):
    engine,broker,store,sent,advance=scheduled
    for qty,price,symbol,day in [(0,2000,'41I1GB000','2026-11-03'),(1,float('nan'),'41I1GB000','2026-11-03'),
            (1,2000.01,'41I1GB000','2026-11-03'),(1,2000,'VN30F1M','2026-11-03'),(1,2000,'41I1GB000','2026-11-04')]:
        with pytest.raises(ValueError):engine.schedule_manual('LONG',qty,price,symbol,day)
    assert not store.orders() and not sent


def test_weekend_holiday_and_ato_atc_flags_choose_the_eligible_session(scheduled):
    *_,advance=scheduled
    advance(day=6,hour=17)
    assert queue_session()['date']=='2026-11-09'
    calendar.write_settings(replace(calendar.read_settings(),manual_closed_dates=['2026-11-09']))
    assert queue_session()['date']=='2026-11-10'
    advance(day=3,hour=8,minute=50)
    assert queue_session()['date']=='2026-11-03'
    calendar.write_settings(replace(calendar.read_settings(),block_entry_ato=False))
    assert queue_session() is None
    advance(hour=14,minute=35)
    assert queue_session()['date']=='2026-11-04'
    calendar.write_settings(replace(calendar.read_settings(),block_entry_atc=False))
    assert queue_session() is None


@pytest.mark.parametrize('phase,hour,minute,flag',[('ATO',8,50,'block_entry_ato'),('ATC',14,35,'block_entry_atc')])
def test_auction_entry_switch_is_checked_before_sending_the_saved_lo(scheduled,phase,hour,minute,flag):
    engine,broker,store,sent,advance=scheduled
    order=queue(engine)
    advance(hour=hour,minute=minute);engine.poll()
    assert not sent and store.order(order.id).status=='SCHEDULED'
    calendar.write_settings(replace(calendar.read_settings(),**{flag:False}))
    engine.poll()
    assert sent==[order.id]


def test_runtime_routes_persists_and_cancels_scheduled_command_without_broker_io(monkeypatch):
    from ckps.models import Settings
    from ckps.services.runtime import Runtime
    from ckps.storage import Store
    monkeypatch.setattr(calendar,'local_now',lambda:datetime(2026,11,2,17,0,tzinfo=VN_TZ))
    runtime=Runtime(Settings(),offline=True)
    try:
        runtime.engine.broker.submit=lambda *a,**kw:pytest.fail('Outside-hours queue must not submit')
        runtime.command('schedule_manual','LONG',1,2000,'41I1GB000','2026-11-03')
        while True:
            kind,payload=runtime.events.get(timeout=5)
            if kind=='error':pytest.fail(payload)
            if kind=='success' and payload=='schedule_manual':break
        order=runtime.store.orders()[0]
        assert order.status=='SCHEDULED'
        path=runtime.store.path
    finally:
        runtime.close();runtime.thread.join(5)
    store=Store(path)
    try:assert store.order(order.id).status=='SCHEDULED'
    finally:store.close()
    restarted=Runtime(Settings(),offline=True)
    try:
        restarted.command('cancel',order.id)
        while True:
            kind,payload=restarted.events.get(timeout=5)
            if kind=='error':pytest.fail(payload)
            if kind=='success' and payload=='cancel':break
        assert restarted.store.order(order.id).status=='CANCELLED'
    finally:
        restarted.close();restarted.thread.join(5)
