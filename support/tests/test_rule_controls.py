"""Real RULE settings drive TP and E; UI edits never submit orders."""
from dataclasses import asdict
from datetime import datetime

import pytest

from ckps.models import ExitSettings
from ckps.rules.ema_exit import EMAExit
from ckps.rules.p2.market import VN_TZ
from test_ema_exit import bars, market, policy


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_tp_uses_price_percent_and_respects_pending_close_reservations(system,side,sign):
    engine,broker,store=system
    engine.settings.exit=asdict(ExitSettings(tp_enabled=True,tp_distance=.5))
    engine.open_manual(side,2,'MOK');engine.poll()
    position=store.positions()[0]
    old=engine.close_position(position.id,1,kind='LO',price=2000+sign*20)
    engine.poll();engine.arm(True)
    broker.set_price(2000+sign*11);engine.poll()
    closes=[o for o in store.orders() if o.reason=='TP']
    assert len(closes)==1 and closes[0].applied==1
    assert store.position(position.id).quantity==1 and store.order(old.id).status=='CANCEL_PENDING'
    engine.poll()
    assert not store.positions()
    assert sum(o.applied for o in store.orders() if o.action=='CLOSE')==2


def test_custom_ema_periods_and_clock_are_independent_of_alert_settings():
    now=datetime(2026,10,27,10,tzinfo=VN_TZ)
    snapshot=market(now,1990)
    settings=policy()
    settings.exit.update(ema_exit_fast=5,ema_exit_slow=13,ema_exit_mode='CLOSED',ema_exit_interval='5M')
    view=EMAExit().observe(snapshot,settings,snapshot.contract,now=now)
    assert view['ready'] and view['fast_period']==5 and view['slow_period']==13
    assert view['fast']==pytest.approx(2000) and view['slow']==pytest.approx(2000)
    settings.exit['ema_exit_mode']='REALTIME'
    settings.exit['ema_exit_interval']='TICK'
    settings.signals.update(enabled=False,signal_mode='CLOSED',realtime_indicator_interval='5M')
    view=EMAExit().observe(snapshot,settings,snapshot.contract,now=now)
    assert view['fast']<view['slow'] and view['mode']=='REALTIME' and view['interval']=='TICK'
    snapshot.bars=bars(now,count=10)
    assert not EMAExit().observe(snapshot,settings,snapshot.contract,now=now)['ready']


@pytest.mark.parametrize('values',[dict(ema_exit_fast=6,ema_exit_slow=3),dict(ema_exit_fast=3.5),
    dict(ema_exit_slow=0),dict(ema_exit_mode='1M'),dict(ema_exit_interval='15M'),dict(tp_enabled=True,tp_distance=0)])
def test_invalid_e_or_tp_cannot_be_saved(values):
    with pytest.raises(ValueError):ExitSettings(**values).validate()


def _rule_and_history_scenario():
    from dataclasses import asdict
    from ckps.dashboard.window import App
    from ckps.models import Settings,Position,Order
    app=App(settings=Settings(),start_runtime=False)
    app.withdraw()
    try:
        rule=app.settings_dialog('E/M');app.update()
        rule.tp_enabled.set(True)
        rule.take_profit.delete(0,'end');rule.take_profit.insert(0,'1,25')
        rule.ema_exit_enabled.set(True)
        for entry,value in ((rule.ema_exit_fast,'5'),(rule.ema_exit_slow,'13')):
            entry.delete(0,'end');entry.insert(0,value)
        rule.ema_exit_mode.set('CLOSED');rule.ema_exit_interval.set('2M')
        sent=[];app.send=lambda *args,**kw:sent.append(args)
        rule.save()
        assert app.settings.exit['tp_enabled'] and app.settings.exit['tp_distance']==1.25
        assert app.settings.exit['ema_exit_fast']==5 and app.settings.exit['ema_exit_slow']==13
        assert app.settings.exit['ema_exit_mode']=='CLOSED' and app.settings.exit['ema_exit_interval']=='2M'
        assert len(sent)==1 and sent[0][0]=='settings'
        long=Position.create('VN30F1M','LONG',1,2000,closed_at=1)
        short=Position.create('41I1GB000','SHORT',1,2000,closed_at=2)
        opened=Order.create(long.symbol,'LONG',1,status='FILLED',filled=1)
        unknown=Order.create(short.symbol,'SHORT',1,status='UNKNOWN')
        app.view.update(history=[asdict(long),asdict(short)],orders=[asdict(opened),asdict(unknown)])
        before=repr(app.view)
        history=app.history();app.update()
        assert len(app.history_tree.get_children())==2 and len(app.order_history_tree.get_children())==2
        history.side.set('SHORT');history.order_state.set('LỖI / CHƯA RÕ');app._render_history()
        assert app.history_tree.get_children()==(short.id,)
        assert app.order_history_tree.get_children()==(unknown.id,)
        history.contract.set(long.symbol);app._render_history()
        assert not app.history_tree.get_children() and not app.order_history_tree.get_children()
        assert repr(app.view)==before and len(sent)==1
    finally:
        app.close()


def test_rule_roundtrips_tp_and_e_and_history_filters_only_change_visible_rows():
    import inspect
    import subprocess
    import sys
    code="import requests, socket\ndef forbidden(*a,**k): raise AssertionError('Offline UI only')\nrequests.Session.request=socket.socket.connect=forbidden\n"
    code+=inspect.getsource(_rule_and_history_scenario)+'\n_rule_and_history_scenario()'
    result=subprocess.run([sys.executable,'-X','utf8','-c',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
