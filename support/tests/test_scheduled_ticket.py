"""Deferred entry confirmation keeps the exact ticket and only stores locally."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from ckps.dashboard.scheduled_orders import request_scheduled,scheduled_ticket
from ckps.dashboard.mayin.connection_status import order_block_reason
from ckps.models import Settings,ExitSettings


def ticket():
    field=lambda text:SimpleNamespace(get=lambda:text)
    app=SimpleNamespace(kind=field('LO'),limit=field('1818'),qty=field('2'),settings=Settings(),
        mode_requested=None,switch_pending=None,view={'contract':'41I1GB000','entry_queue':{'date':'2026-11-03'},
            'quotes':{},'market_cache':{'contract':'41I1GB000','quote':{'last':1818}}})
    app.ticket_rules=lambda _: (ExitSettings(),None)
    app.ticket_capacity=lambda *args:SimpleNamespace(maximum=2)
    app.confirm=lambda text,callback:setattr(app,'confirmation',(text,callback))
    app.report=lambda text,**kw:setattr(app,'error',text)
    app.sent=[];app.send=lambda *args:app.sent.append(args)
    return app


def test_closed_ticket_only_stores_the_exact_confirmed_lo_and_never_submits_on_click():
    app=ticket()
    assert order_block_reason(app.view)==''
    request_scheduled(app,'LONG',scheduled_ticket(app.view))
    assert not app.sent and 'Chưa gửi broker' in app.confirmation[0]
    app.confirmation[1]()
    assert app.sent==[('schedule_manual','LONG',2,1818.,'41I1GB000','2026-11-03')]


@pytest.mark.parametrize('change',['price','quantity','contract','date','rule','mode','kind'])
def test_changed_confirmation_never_stores_another_order(change):
    app=ticket();request_scheduled(app,'SHORT',scheduled_ticket(app.view))
    if change=='price':app.limit.get=lambda:'1819'
    elif change=='quantity':app.qty.get=lambda:'1'
    elif change=='contract':app.view['contract']='41I1GC000'
    elif change=='date':app.view['entry_queue']['date']='2026-11-04'
    elif change=='rule':app.ticket_rules=lambda _: (ExitSettings(sl_enabled=True,sl_distance=.5),None)
    elif change=='mode':app.mode_requested='REAL'
    elif change=='kind':app.kind.get=lambda:'MOK'
    with pytest.raises(ValueError):app.confirmation[1]()
    assert not app.sent


@pytest.mark.parametrize('field,value',[('qty','0'),('limit','nan'),('limit','1818.01'),('kind','MOK')])
def test_bad_queued_ticket_never_opens_confirmation(field,value):
    app=ticket();getattr(app,field).get=lambda:value
    request_scheduled(app,'LONG',scheduled_ticket(app.view))
    assert not hasattr(app,'confirmation') and app.error and not app.sent


def test_a_verified_contract_takes_precedence_over_an_old_cached_contract():
    app=ticket();app.view['contract']='41I1GC000'
    assert scheduled_ticket(app.view)['symbol']=='41I1GC000'
    app.view['contract']='VN30F1M'
    assert scheduled_ticket(app.view)['symbol']=='41I1GB000'
