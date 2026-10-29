"""Price-based E/M, signed SL input and preserving old exposure during migration."""
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from ckps.models import ExitSettings, Order, Position, Settings
from ckps.rules.distances import price_percent_rules, price_rules
from ckps.rules.protection import evaluate, levels, repeat_trigger


def rules(**values):
    return ExitSettings(distance_unit='PRICE_PERCENT', **values)


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
@pytest.mark.parametrize('stop,distance',[(.25,5),(2.5,50)])
def test_sl_is_percent_of_entry_and_money_scales_with_actual_contracts(side,sign,stop,distance):
    policy=rules(sl_enabled=True,sl_distance=stop,tp_enabled=True,tp_distance=1)
    for margin in (None,10_000_000,80_000_000):
        position=Position.create('VN30F1M',side,3,2000,margin_per_contract=margin,history_verified=True)
        view=levels(position,policy)
        assert view['sl']==2000-sign*distance and view['tp']==2000+sign*20
        assert evaluate(position,view['sl']+sign*.1,policy) is None
        decision=evaluate(position,view['sl'],policy)
        assert decision.reason=='SL' and decision.quantity==3
        assert position.pnl(view['sl'])==-distance*100_000*3


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_price_arm_trail_dynamic_and_repeat_do_not_depend_on_margin(side,sign):
    position=Position.create('VN30F1M',side,4,2000,history_verified=True)
    policy=rules(arm_enabled=True,arm_gain=1,trail_gap=.25,arm_close_pct=50,arm_repeat=True,
        repeat_gap=.25,dynamic_enabled=True,dynamic_policy='AUTO',dynamic_repeat=True,
        dynamic_close_pct=50,atr_start_multiplier=.5,atr_trail_multiplier=.8,
        retention_pct=70,retention_until_enabled=False)
    evaluate(position,2000+sign*12,policy,1)
    assert levels(position,policy,1)['stage']=='DYN'
    assert levels(position,policy,1)['protect']==pytest.approx(2000+sign*8.4)
    evaluate(position,2000+sign*25,policy,1)
    trigger=2000+sign*20
    assert levels(position,policy,1)['protect']==pytest.approx(trigger)
    decision=evaluate(position,trigger,policy,1)
    assert decision.reason=='ARM' and decision.quantity==2
    position.metrics['ARM:AUTO']={'count':1,'anchor':trigger,'round_best':2000+sign*26}
    assert repeat_trigger(position,policy,'ARM',trigger)==pytest.approx(2000+sign*21)
    position.metrics['DYN:AUTO']={'count':1,'anchor':2000+sign*12}
    assert repeat_trigger(position,policy,'DYN',2000+sign*10)==pytest.approx(2000+sign*7)


@pytest.mark.parametrize('side,margin',[('LONG',40_000_000),('SHORT',20_000_000)])
def test_old_pnl_converts_all_distances_without_changing_prices_or_repeat_state(side,margin):
    old=ExitSettings(distance_unit='PNL_PERCENT',sl_enabled=True,sl_distance=2.5,
        tp_enabled=True,tp_distance=10,arm_enabled=True,arm_gain=5,trail_gap=1.25,
        arm_repeat=True,repeat_gap=1.25,dynamic_enabled=True,dynamic_repeat=True,
        retention_until=4)
    position=Position.create('VN30F1M',side,3,2000,margin_per_contract=margin,history_verified=True)
    position.best=2025 if side=='LONG' else 1975
    position.floor=2010 if side=='LONG' else 1990
    position.metrics={'ARM:AUTO':{'count':1,'anchor':position.floor,'round_best':position.best}}
    before=deepcopy(asdict(position)); source=asdict(old)
    converted=price_percent_rules(source,position.entry,position.margin_per_contract)
    modern=ExitSettings(**converted)
    assert modern.distance_unit=='PRICE_PERCENT'
    assert modern.sl_distance==pytest.approx(.5 if margin==40_000_000 else .25)
    assert price_rules(old,2000,margin)==price_rules(modern,2000,None)
    assert levels(position,old,1)==levels(position,modern,1)
    level=levels(position,old,1)['protect']
    assert repeat_trigger(position,old,'ARM',level)==repeat_trigger(position,modern,'ARM',level)
    assert asdict(position)==before and asdict(old)==source


def test_missing_old_basis_keeps_old_policy_but_new_price_rules_need_no_margin():
    old=asdict(ExitSettings(distance_unit='PNL_PERCENT',sl_enabled=True,sl_distance=2.5))
    before=dict(old)
    with pytest.raises(ValueError,match='ký quỹ cơ sở'):
        price_percent_rules(old,2000,None)
    assert old==before
    assert price_percent_rules(asdict(rules(sl_enabled=True,sl_distance=.25)))['sl_distance']==.25
    assert Settings().exit['distance_unit']=='PRICE_PERCENT'


@pytest.mark.parametrize('text',['-.25','-0,25%','0.25','0,25%'])
def test_ticket_accepts_point_or_comma_and_uses_negative_sl_as_distance(text):
    from ckps.dashboard.actions import DashboardActionsMixin
    class Value:
        def __init__(self,value):self.value=value
        def get(self):return self.value
    app=SimpleNamespace(settings=Settings(),ticket_sl=Value(text),ticket_tp=Value('RULE'),
                        view={'contract':'VN30F1M'})
    policy,override=DashboardActionsMixin.ticket_rules(app,2000)
    assert policy.distance_unit=='PRICE_PERCENT' and policy.sl_distance==.25
    assert policy.points(policy.sl_distance,2000)==5 and override['sl_enabled']


def test_modern_position_can_be_adopted_and_protected_without_margin_basis(system):
    engine,broker,store=system
    engine.settings.exit=asdict(rules(sl_enabled=True,sl_distance=.25))
    engine.open_manual('LONG',1,'MOK');engine.poll()
    position=store.positions()[0]
    position.margin_per_contract=None
    position.managed=False
    store.save_position(position)
    engine.set_managed(position.id,True)
    engine.arm(True)
    broker.set_price(1995);engine.poll();engine.poll()
    assert not store.positions()
    assert len([o for o in store.orders() if o.action=='CLOSE'])==1
    assert store.positions(closed=True)[0].realized==-500_000


def test_legacy_inheriting_positions_and_pending_orders_keep_their_own_policy_on_restart(system):
    from ckps.trading.execution import Engine
    engine,broker,store=system
    old=asdict(ExitSettings(distance_unit='PNL_PERCENT',sl_enabled=True,sl_distance=2.5))
    legacy_settings=replace(engine.settings,exit=old)
    positions=[Position.create('VN30F2611','LONG',1,2000,margin_per_contract=40_000_000),
               Position.create('VN30F2612','SHORT',2,2000,margin_per_contract=20_000_000)]
    for position in positions:store.save_position(position)
    order=Order.create('VN30F2611','LONG',1,status='WORKING',broker_id='existing')
    store.save_order(order)
    restarted=Engine(store,broker,legacy_settings)
    restarted.settings=Settings(exit=asdict(rules(sl_enabled=True,sl_distance=.25)))
    assert levels(store.position(positions[0].id),restarted.exits(store.position(positions[0].id)))['sl']==1990
    assert levels(store.position(positions[1].id),restarted.exits(store.position(positions[1].id)))['sl']==2005
    assert store.order(order.id).exit_settings==old
    assert not restarted.enabled.is_set() and len(store.orders())==1


def test_price_protection_uses_weighted_fill_entry_and_survives_reduction_restart(system):
    from ckps.connections.dnse.paper import PaperBroker
    from ckps.trading.execution import Engine
    engine,broker,store=system
    engine.settings.exit=asdict(rules(sl_enabled=True,sl_distance=.25))
    engine.open_manual('LONG',1,'MOK');engine.poll()
    broker.set_price(2020);engine.poll()
    engine.open_manual('LONG',1,'MOK');engine.poll()
    position=store.positions()[0]
    assert position.entry==2010
    target=2010*(1-.0025)
    assert levels(position,engine.exits(position))['sl']==pytest.approx(target)
    engine.close_position(position.id,1);engine.poll()
    restarted=Engine(store,PaperBroker(store,engine.settings,offline=True),engine.settings)
    restarted.poll()
    position=store.positions()[0]
    assert position.quantity==1 and position.entry==2010
    assert levels(position,restarted.exits(position))['sl']==pytest.approx(target)
