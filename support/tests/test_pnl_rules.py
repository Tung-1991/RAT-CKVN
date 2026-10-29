"""Gross PNL% uses each position's verified, persisted margin basis."""
from dataclasses import asdict, replace

import pytest

from ckps.models import ExitSettings, Position, Settings
from ckps.rules.pnl import pnl_rules, price_rules, reference_margin
from ckps.rules.protection import evaluate, levels, repeat_trigger


def rules(**kwargs):
    return ExitSettings(distance_unit='PNL_PERCENT',**kwargs)


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_pnl_sl_tp_arm_use_initial_margin_not_price_nav_or_current_quantity(side,sign):
    position=Position.create('VN30F1M',side,3,2000,margin_per_contract=40_000_000,history_verified=True)
    settings=rules(sl_enabled=True,sl_distance=2.5,tp_enabled=True,tp_distance=10,
        arm_enabled=True,arm_gain=5,trail_gap=1.25)
    view=levels(position,settings)
    assert view['sl']==2000-sign*10 and view['tp']==2000+sign*40
    assert position.pnl_pct(2000+sign*20)==5
    position.quantity=1
    assert position.pnl_pct(2000+sign*20)==5
    assert evaluate(position,2000-sign*10,settings).reason=='SL'
    assert evaluate(position,2000+sign*40,settings).reason=='TP'


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_pnl_trail_repeat_and_dynamic_share_the_same_fixed_margin_basis(side,sign):
    position=Position.create('VN30F1M',side,3,2000,margin_per_contract=40_000_000,history_verified=True)
    settings=rules(arm_enabled=True,arm_gain=5,trail_gap=1.25,arm_repeat=True,repeat_gap=1.25,
        dynamic_enabled=True,dynamic_policy='AUTO',dynamic_close_pct=50,retention_pct=70,dynamic_repeat=True)
    evaluate(position,2000+sign*12,settings,1)
    assert levels(position,settings,1)['stage']=='DYN'
    evaluate(position,2000+sign*25,settings,1)
    view=levels(position,settings,1)
    assert view['protect']==pytest.approx(2000+sign*20)
    position.metrics['ARM:AUTO']={'count':1,'anchor':2000+sign*20,'round_best':2000+sign*26}
    assert repeat_trigger(position,settings,'ARM',view['protect'])==pytest.approx(2000+sign*21)
    position.metrics['DYN:AUTO']={'count':1,'anchor':2000+sign*12}
    assert repeat_trigger(position,settings,'DYN',2000+sign*10)==pytest.approx(2000+sign*7)


def test_old_points_and_price_percent_are_converted_explicitly_without_mutating_source():
    old=ExitSettings(sl_enabled=True,sl_distance=10,tp_distance=40,arm_gain=20,trail_gap=5,repeat_gap=5)
    before=asdict(old)
    converted=pnl_rules(before,2000,40_000_000)
    assert converted['distance_unit']=='PNL_PERCENT' and converted['sl_distance']==2.5
    assert price_rules(ExitSettings(**converted),2000,40_000_000)==old
    assert asdict(old)==before
    percent=replace(old,distance_unit='PERCENT',sl_distance=.5)
    assert pnl_rules(asdict(percent),2000,40_000_000)['sl_distance']==2.5
    for margin in (None,0,float('nan')):
        with pytest.raises(ValueError):pnl_rules(before,2000,margin)
    assert Settings().exit['distance_unit']=='PNL_PERCENT'


def test_missing_margin_does_not_mutate_protection_or_block_manual_close(system):
    engine,broker,store=system
    engine.open_manual('LONG',1,'MOK');engine.poll()
    position=store.positions()[0]
    position.margin_per_contract=None
    position.exit_overrides=asdict(rules(sl_enabled=True,sl_distance=2.5))
    store.save_position(position)
    original=asdict(position)
    with pytest.raises(ValueError):evaluate(position,1980,ExitSettings(**position.exit_overrides))
    assert asdict(position)==original
    engine.close_position(position.id,1)
    assert not store.positions()


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_scale_in_weights_basis_reduction_keeps_it_and_restart_does_not_reprice(system,side,sign):
    from ckps.connections.dnse.paper import PaperBroker
    from ckps.trading.execution import Engine
    engine,broker,store=system
    engine.settings.exit=asdict(rules(sl_enabled=True,sl_distance=5))
    engine.open_manual(side,1,'MOK');engine.poll()
    position=store.positions()[0]
    assert position.margin_per_contract==40_000_000
    broker.set_price(2020);engine.poll()
    assert store.positions()[0].margin_per_contract==40_000_000
    engine.open_manual(side,1,'MOK');engine.poll()
    position=store.positions()[0]
    assert position.entry==2010 and position.margin_per_contract==40_200_000
    pnl=position.pnl_pct(2010+sign*20)
    engine.close_position(position.id,1);engine.poll()
    reduced=store.positions()[0]
    assert reduced.margin_per_contract==40_200_000 and reduced.pnl_pct(2010+sign*20)==pnl
    restarted=Engine(store,PaperBroker(store,engine.settings,offline=True),engine.settings)
    restarted.poll()
    assert store.positions()[0].margin_per_contract==40_200_000
    assert not restarted.enabled.is_set()


def test_ticket_pnl_loss_uses_prospective_margin_without_an_account_risk_gate(system):
    from ckps.trading.portfolio import capacity
    engine,broker,store=system
    settings=engine.settings
    exits=rules(sl_enabled=True,sl_distance=2.5)
    settings.exit=asdict(exits)
    snapshot=replace(engine.latest,margin_per_contract=40_000_000,margin_reference_price=2000)
    position=Position.create('VN30F1M','LONG',1,2000,margin_per_contract=20_000_000)
    result=capacity(settings,snapshot,[position],[],'LONG',2000,exits)
    assert result.risk_per_contract==1_000_000 and result.maximum==2
    position.margin_per_contract=None
    result=capacity(settings,snapshot,[position],[],'LONG',2000,exits)
    assert result.maximum==2 and result.risk_per_contract==1_000_000
    assert reference_margin(40_000_000,2000,2010)==40_200_000


def test_external_position_basis_is_taken_from_its_broker_row_and_never_repriced(system,monkeypatch):
    engine,broker,store=system
    broker.mode='REAL'
    snapshot=replace(engine.latest,positions=[{'symbol':'VN30F1M','side':'SHORT','quantity':2,'entry':2000,
        'margin_per_contract':40_000_000}])
    monkeypatch.setattr(broker,'snapshot',lambda:snapshot)
    engine.poll()
    position=store.positions()[0]
    assert not position.managed and position.margin_per_contract==40_000_000
    snapshot.positions[0]['margin_per_contract']=80_000_000
    engine.poll()
    assert store.positions()[0].margin_per_contract==40_000_000
    store.positions()[0].margin_per_contract=None
    # Another symbol's account-wide margin is never assigned to this position.
    snapshot.positions=[{'symbol':'VN30F2611','side':'LONG','quantity':1,'entry':2000}]
    engine.poll()
    carried=next(position for position in store.positions() if position.symbol=='VN30F2611')
    assert carried.margin_per_contract is None


def test_old_manual_caps_are_retired_on_load_and_cannot_silently_block_manual_orders(system):
    import json
    from ckps.config import read_settings, runtime_root, write_settings
    engine,broker,store=system
    old_caps={'capital_limit':1,'max_contracts':1,'risk_limit':1,'risk_nav_pct':.0001}
    saved={**asdict(engine.settings),**old_caps}
    folder=runtime_root()
    folder.mkdir(parents=True)
    path=folder/'settings.json'
    path.write_text(json.dumps(saved),encoding='utf-8')
    engine.settings=broker.settings=read_settings()
    assert not set(old_caps)&asdict(engine.settings).keys()
    engine.open_manual('LONG',2,'MOK');engine.poll()
    assert store.positions()[0].quantity==2
    assert not engine.enabled.is_set()
    write_settings(engine.settings)
    assert not set(old_caps)&json.loads(path.read_text(encoding='utf-8')).keys()
    assert asdict(read_settings())==asdict(engine.settings)


def test_partial_fills_pin_margin_with_position_and_do_not_count_same_fill_twice(system):
    from ckps.models import Order
    engine,broker,store=system
    order=Order.create('VN30F1M','SHORT',3,margin_per_contract=40_000_000,margin_reference_price=2000)
    store.save_order(order)
    update={'broker_id':'offline-order','status':'PARTIAL','filled':1,'avg_fill':2000,'fee':0}
    with store.transaction():engine._apply_update(order,update)
    assert store.positions()[0].margin_per_contract==40_000_000
    update.update(status='FILLED',filled=3,avg_fill=2010)
    with store.transaction():engine._apply_update(order,update)
    position=store.positions()[0]
    assert position.quantity==3 and position.entry==2010 and position.margin_per_contract==40_200_000
    with store.transaction():engine._apply_update(order,update)
    assert store.positions()[0]==position


def test_manual_ticket_cannot_reinterpret_legacy_units_as_pnl():
    from types import SimpleNamespace
    from ckps.dashboard.actions import DashboardActionsMixin
    class Value:
        def __init__(self,value):self.value=value
        def get(self):return self.value
    app=SimpleNamespace(settings=Settings(exit=asdict(ExitSettings(sl_enabled=True,sl_distance=10))),
        ticket_sl=Value('5%'),ticket_tp=Value('RULE'),view={'contract':'VN30F1M'})
    with pytest.raises(ValueError,match='% PNL'):DashboardActionsMixin.ticket_rules(app,2000)
    app.settings.exit=pnl_rules(app.settings.exit,2000,40_000_000)
    configured,_=DashboardActionsMixin.ticket_rules(app,2000)
    assert configured.distance_unit=='PNL_PERCENT' and configured.sl_distance==5
