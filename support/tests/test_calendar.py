from dataclasses import replace
from datetime import date, datetime

import pytest

from ckps.connections.dnse.protocol import BrokerError
from ckps.rules.calendar import CalendarSettings, dates, date_status, expiry_date, entry_block
from ckps.rules.p2.market import VN_TZ
from ckps.services import calendar
from ckps.services.calendar import CalendarNotices
from ckps.models import ExitSettings


def test_calendar_dates_are_strict_and_expiry_moves_to_known_previous_session():
    assert dates('2026-08-20, 2026-08-20;2026-08-19')==['2026-08-19','2026-08-20']
    with pytest.raises(ValueError):dates('20/08/2026')
    with pytest.raises(ValueError):dates('2026-02-30')
    settings=CalendarSettings()
    assert date_status(date(2026,8,20),settings,{})=='UNKNOWN'
    assert date_status(date(2026,8,20),settings,{'coverage_start':'2026-08-01','coverage_end':'2026-08-31','working_dates':[]})=='UNKNOWN'
    assert expiry_date(2026,8,settings,{})==date(2026,8,20)
    cache={'coverage_start':'2026-08-01','coverage_end':'2026-08-31','working_dates':['2026-08-19']}
    assert expiry_date(2026,8,settings,cache)==date(2026,8,19)
    assert date_status(date(2026,8,20),settings,cache)=='HOLIDAY'
    assert date_status(date(2026,8,22),settings,cache)=='WEEKEND'


@pytest.mark.parametrize('hour,minute,phase',[(8,50,'ATO'),(14,35,'ATC')])
def test_phase_exclusions_can_be_disabled_without_changing_date_rules(hour,minute,phase):
    now=datetime(2026,10,27,hour,minute,tzinfo=VN_TZ)
    assert phase in entry_block(now,CalendarSettings(),{})
    assert not entry_block(now,CalendarSettings(block_entry_ato=False,block_entry_atc=False),{})


@pytest.mark.parametrize('side,bad_price',[('LONG',1990),('SHORT',2010)])
def test_calendar_blocks_new_exposure_but_preserves_automatic_sl_and_manual_close(system,side,bad_price):
    engine,broker,store=system
    engine.settings.exit=replace(ExitSettings(),sl_enabled=True,sl_distance=10).__dict__
    engine.open_manual(side,2,'MOK')
    position=store.positions()[0]
    calendar.write_settings(CalendarSettings(manual_closed_dates=['2026-10-27']))
    with pytest.raises(BrokerError,match='Ngày nghỉ'):engine.preview(side)
    before=len(store.orders())
    with pytest.raises(BrokerError,match='Ngày nghỉ'):engine.open_manual(side,1,'MOK')
    assert len(store.orders())==before and store.positions()[0].quantity==2
    engine.close_position(position.id,1)
    engine.poll()
    assert store.positions()[0].quantity==1
    engine.arm(True)
    broker.set_price(bad_price);engine.poll()
    assert not store.positions()
    assert any(order.reason=='SL' and order.source=='AUTO' and order.status=='FILLED' for order in store.orders())


def test_calendar_is_rechecked_at_handoff_even_for_manual_entry(system,monkeypatch):
    engine,broker,store=system
    original=broker.submit
    def midnight_change(order,can_submit=None):
        calendar.write_settings(CalendarSettings(manual_closed_dates=['2026-10-27']))
        return original(order,can_submit=can_submit)
    monkeypatch.setattr(broker,'submit',midnight_change)
    order=engine.open_manual('LONG',1,'MOK')
    assert order.status=='CANCELLED' and not store.positions()
    assert not store.all('paper_order')


def test_expiry_and_rebalance_gate_use_configured_dates():
    expiry=datetime(2026,11,19,10,0,tzinfo=VN_TZ)
    assert not entry_block(expiry,CalendarSettings(avoid_vn30_expiry_entry=True),{})
    assert not entry_block(expiry,CalendarSettings(),{})
    settings=CalendarSettings(avoid_vn30_rebalance_entry=True,vn30_rebalance_dates=['2026-10-27'])
    assert 'ĐỔI RỔ' in entry_block(datetime(2026,10,27,10,0,tzinfo=VN_TZ),settings,{})


def test_notice_is_early_deduplicated_and_uses_same_signal_channel(system):
    _engine,_broker,store=system
    calendar.write_settings(CalendarSettings(manual_closed_dates=['2026-10-28'],notice_days=1,notice_time='15:00'))
    before=datetime(2026,10,27,14,59,tzinfo=VN_TZ)
    CalendarNotices(store).observe(now=before,enabled=True,chat='one-chat')
    assert not store.db.execute('SELECT id FROM outbox').fetchall()
    at=before.replace(hour=15,minute=0)
    CalendarNotices(store).observe(now=at,enabled=True,chat='one-chat')
    CalendarNotices(store).observe(now=at,enabled=True,chat='one-chat')
    rows=store.db.execute('SELECT target,text FROM outbox').fetchall()
    assert len(rows)==1 and rows[0][0]=='owner:one-chat'
    assert '2026-10-28' in rows[0][1] and 'CALENDAR' in rows[0][1]
    assert not store.orders() and not store.positions()


def test_disabled_notice_still_records_history_without_replay_on_enable(system):
    _engine,_broker,store=system
    settings=CalendarSettings(manual_closed_dates=['2026-10-28'],notify_enabled=False)
    calendar.write_settings(settings)
    now=datetime(2026,10,27,15,0,tzinfo=VN_TZ)
    CalendarNotices(store).observe(now=now,enabled=True,chat='one-chat')
    calendar.write_settings(replace(settings,notify_enabled=True))
    CalendarNotices(store).observe(now=now,enabled=True,chat='one-chat')
    assert len(store.all('signal_history'))==1
    assert not store.db.execute('SELECT id FROM outbox').fetchall()


def test_calendar_refresh_once_daily_failure_preserves_coverage():
    calls=[]
    now=datetime(2026,10,27,10,0,tzinfo=VN_TZ)
    def provider():calls.append(True);return ['2026-10-27','2026-10-29']
    first=calendar.refresh(provider,now=now)
    assert first['coverage_start']=='2026-10-27'
    assert calendar.refresh(provider,now=now)==first and len(calls)==1
    def failed():raise RuntimeError('offline')
    assert calendar.refresh(provider,now=now.replace(day=28))==first and len(calls)==1
    second=calendar.refresh(failed,now=now.replace(day=29))
    assert second['working_dates']==first['working_dates'] and second['error']
    assert date_status(date(2026,10,28),CalendarSettings(),second)=='HOLIDAY'


def test_calendar_bad_configuration_blocks_only_opening(system):
    engine,broker,store=system
    engine.open_manual('LONG',1,'MOK');position=store.positions()[0]
    from ckps.config import runtime_root
    runtime_root().mkdir(parents=True,exist_ok=True)
    (runtime_root()/'calendar.json').write_text('{bad json',encoding='utf-8')
    with pytest.raises(ValueError):engine.open_manual('LONG',1,'MOK')
    engine.close_position(position.id,1);engine.poll()
    assert not store.positions()
