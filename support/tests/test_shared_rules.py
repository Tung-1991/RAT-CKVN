"""One shared protection policy governs every holding and pending/new entry."""
from dataclasses import asdict

import pytest

from ckps.config import read_settings, write_settings
from ckps.models import ExitSettings, Position, Settings
from ckps.rules.protection import levels
from ckps.trading.execution import Engine


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_changing_shared_stop_protects_an_existing_holding_despite_legacy_override(system, side, sign):
    engine, broker, store = system
    engine.settings.exit=asdict(ExitSettings(sl_enabled=True, sl_distance=.5))
    engine.open_manual(side, 1, 'MOK'); engine.poll()
    position=store.positions()[0]
    position.exit_overrides=asdict(ExitSettings(sl_enabled=True, sl_distance=99))
    store.save_position(position)
    engine.arm(True)
    broker.set_price(2000-sign*6); engine.poll()
    assert len(store.orders())==1 and store.positions()[0].quantity==1
    engine.settings.exit=asdict(ExitSettings(sl_enabled=True, sl_distance=.25))
    engine.poll(); engine.poll()
    assert not store.positions()
    close=store.orders()[-1]
    assert close.action=='CLOSE' and close.reason=='SL' and close.quantity==1
    assert store.positions(closed=True)[0].realized==-600_000


@pytest.mark.parametrize('side,fill', [('LONG', 1990), ('SHORT', 2010)])
def test_pending_entry_fills_with_current_shared_rule_instead_of_saved_private_policy(system, side, fill):
    engine, broker, store = system
    order=engine.open_manual(side, 1, 'LO', price=fill)
    assert order.status=='WORKING'
    # Old persisted settings may even lack a usable PNL margin basis.
    order.exit_settings=asdict(ExitSettings(distance_unit='PNL_PERCENT',sl_enabled=True,sl_distance=99))
    store.save_order(order)
    engine.settings.exit=asdict(ExitSettings(sl_enabled=True,sl_distance=.25))
    broker.set_price(fill); engine.poll()
    position=store.positions()[0]
    assert position.entry==fill and position.exit_overrides is None
    expected=fill*(1-.0025 if side=='LONG' else 1+.0025)
    assert levels(position,engine.exits(position))['sl']==pytest.approx(expected)
    assert not engine.enabled.is_set() and len(store.orders())==1


def test_same_percent_applies_to_each_contract_entry_without_resetting_protection_history(system):
    engine, broker, store = system
    engine.settings=Settings(exit=asdict(ExitSettings(sl_enabled=True,sl_distance=.25)))
    positions=[Position.create('VN30F2611','LONG',2,2000,margin_per_contract=40_000_000),
               Position.create('VN30F2612','SHORT',1,2400,margin_per_contract=10_000_000)]
    for position in positions:
        position.exit_overrides={'sl_enabled':True,'sl_distance':999,'distance_unit':'POINTS'}
        position.metrics={'ARM:AUTO':{'count':2,'anchor':position.entry}}
        position.floor=position.entry
        store.save_position(position)
    before=[asdict(p) for p in store.positions()]
    restarted=Engine(store,broker,engine.settings)
    assert [asdict(p) for p in store.positions()]==before
    assert levels(positions[0],restarted.exits(positions[0]))['sl']==1995
    assert levels(positions[1],restarted.exits(positions[1]))['sl']==2406
    assert not restarted.enabled.is_set() and not store.orders()


@pytest.mark.parametrize('side,price', [('LONG',2200),('SHORT',1800)])
def test_saved_tp_is_respected_and_closes_the_position(system,side,price):
    engine, broker, store = system
    settings=Settings(exit=asdict(ExitSettings(tp_enabled=True,tp_distance=.1))).validate()
    write_settings(settings)
    engine.settings=read_settings()
    assert engine.settings.exit['tp_enabled'] and engine.settings.exit['tp_distance']==.1
    engine.open_manual(side,1,'MOK');engine.poll();engine.arm(True)
    broker.set_price(price);engine.poll();engine.poll()
    assert not store.positions() and len(store.orders())==2
    assert store.orders()[-1].reason=='TP' and store.orders()[-1].applied==1


@pytest.mark.parametrize('stage', ['ARM','DYN'])
@pytest.mark.parametrize('side,sign', [('LONG',1),('SHORT',-1)])
def test_old_alert_original_and_custom_percent_cannot_change_ready_to_use_reductions(system,stage,side,sign):
    engine,broker,store=system
    engine.paper_capital(200_000_000)
    engine.open_manual(side,4,'MOK');engine.poll()
    position=store.positions()[0]
    engine.close_position(position.id,2);engine.poll()
    assert store.position(position.id).quantity==2 and store.position(position.id).original_quantity==4
    # Attempted old choices would either only alert or close all remaining HĐ.
    engine.settings.exit=asdict(ExitSettings(arm_enabled=stage=='ARM',arm_gain=1,trail_gap=.25,
        arm_policy='ALERT',arm_basis='ORIGINAL',arm_close_pct=100,arm_repeat=True,
        arm_repeat_below_arm=True,repeat_gap=.25,dynamic_enabled=stage=='DYN',
        dynamic_policy='ALERT',dynamic_basis='ORIGINAL',dynamic_close_pct=100,
        dynamic_repeat=True,atr_start_multiplier=.5,retention_pct=70,retention_until_enabled=False))
    engine._atr=lambda symbol:1.
    engine.arm(True)
    broker.set_price(2000+sign*(28 if stage=='ARM' else 12));engine.poll()
    broker.set_price(2000+sign*(23 if stage=='ARM' else 8));engine.poll();engine.poll()
    assert store.position(position.id).quantity==1
    closes=[o for o in store.orders() if o.source=='AUTO']
    assert len(closes)==1 and closes[0].quantity==1 and closes[0].reason==stage
    for _ in range(3):engine.poll()
    assert len([o for o in store.orders() if o.source=='AUTO'])==1
    broker.set_price(2000+sign*(18 if stage=='ARM' else 3));engine.poll();engine.poll()
    assert not store.positions()
    assert [o.quantity for o in store.orders() if o.source=='AUTO']==[1,1]


def test_loading_old_choices_uses_auto_and_half_remaining_without_enabling_disabled_branches():
    raw=asdict(ExitSettings(sl_enabled=True,sl_distance=.35,arm_enabled=False,dynamic_enabled=False,
        arm_policy='ALERT',dynamic_policy='ALERT',arm_basis='ORIGINAL',dynamic_basis='ORIGINAL',
        arm_close_pct=33,dynamic_close_pct=67))
    original=dict(raw)
    settings=Settings(exit=raw)
    write_settings(settings)
    loaded=read_settings().exit
    assert raw==original
    for prefix in ('arm','dynamic'):
        assert loaded[prefix+'_policy']=='AUTO' and loaded[prefix+'_basis']=='REMAINING'
        assert loaded[prefix+'_close_pct']==50 and not loaded[prefix+'_enabled']
    assert loaded['sl_distance']==.35 and loaded['sl_enabled'] and not loaded['tp_enabled']
