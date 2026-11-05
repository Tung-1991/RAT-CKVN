"""PNL ARM/TSL/LẶP share a fixed per-contract basis; SL/TP remain price based."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from ckps.dashboard.mayin.pnl_preview import ProtectionReference, pnl_preview, protection_reference
from ckps.models import ExitSettings, Position, Quote, load_record
from ckps.rules.distances import pnl_trailing_rules, pnl_rule_draft
from ckps.rules.protection import evaluate, levels, repeat_trigger


def policy(**values):
    return ExitSettings(distance_unit='PRICE_PERCENT',trailing_unit='PNL_PERCENT',
        sl_enabled=True,sl_distance=.25,tp_enabled=True,tp_distance=2,
        arm_enabled=True,arm_gain=5,trail_gap=1.25,arm_close_pct=50,
        arm_repeat=True,arm_repeat_below_arm=True,repeat_gap=1.25,**values)


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
@pytest.mark.parametrize('margin,arm,trail',[(20_000_000,10,2.5),(40_000_000,20,5),(80_000_000,40,10)])
def test_pnl_trailing_uses_fixed_margin_while_sl_tp_stay_at_their_price_levels(side,sign,margin,arm,trail):
    p=Position.create('VN30F1M',side,4,2000,margin_per_contract=margin,history_verified=True)
    rule=policy()
    view=levels(p,rule)
    assert view['sl']==2000-sign*5 and view['tp']==2000+sign*40
    assert view['arm']==2000+sign*arm
    evaluate(p,2000+sign*(arm+2),rule)
    assert levels(p,rule)['protect']==pytest.approx(2000+sign*(arm+2-trail))
    pct=p.pnl_pct(2000+sign*arm)
    p.quantity=2
    assert pct==p.pnl_pct(2000+sign*arm)==5


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_migration_is_a_draft_and_preserves_price_levels_floor_and_repeat_memory(side,sign):
    old=ExitSettings(distance_unit='PRICE_PERCENT',sl_enabled=True,sl_distance=.5,
        arm_enabled=True,arm_gain=1,trail_gap=.25,repeat_gap=.25,arm_repeat=True)
    p=Position.create('VN30F1M',side,4,2000,margin_per_contract=40_000_000,history_verified=True)
    p.best=2000+sign*28;p.floor=2000+sign*23
    p.metrics={'ARM:AUTO':{'count':1,'anchor':p.floor,'round_best':p.best}}
    before=deepcopy((asdict(old),asdict(p)))
    draft=pnl_trailing_rules(asdict(old),p.entry,p.margin_per_contract)
    converted=load_record(ExitSettings,draft)
    assert draft['arm_gain']==5 and draft['trail_gap']==draft['repeat_gap']==1.25
    assert draft['sl_distance']==.5 and draft['distance_unit']=='PRICE_PERCENT'
    assert levels(p,old)==levels(p,converted)
    assert repeat_trigger(p,old,'ARM',p.floor)==repeat_trigger(p,converted,'ARM',p.floor)
    assert (asdict(old),asdict(p))==before
    with pytest.raises(ValueError,match='ký quỹ cơ sở'):
        pnl_trailing_rules(asdict(old),2000,None)


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_missing_trailing_basis_never_disables_price_stop_or_take_profit(side,sign):
    p=Position.create('VN30F1M',side,2,2000,history_verified=True)
    assert evaluate(p,2000-sign*5,policy()).reason=='SL'
    assert evaluate(p,2000+sign*40,policy()).reason=='TP'
    assert evaluate(p,2000+sign*20,policy()) is None
    assert pnl_preview(asdict(policy()),ProtectionReference(2000,None,2))[0]=='CHỜ KÝ QUỸ CƠ SỞ/HĐ'


def test_missing_trailing_basis_still_allows_manual_adoption_and_price_sl(system):
    engine,broker,store=system
    engine.settings.exit=asdict(policy())
    engine.open_manual('LONG',1,'MOK');engine.poll()
    p=store.positions()[0]
    p.margin_per_contract=None;p.managed=False
    store.save_position(p)
    engine.set_managed(p.id,True);engine.arm(True)
    broker.set_price(1995);engine.poll();engine.poll()
    assert not store.positions() and store.orders()[-1].reason=='SL'


def test_pending_draft_preserves_each_groups_units_and_can_resolve_without_resetting_saved_values():
    old=asdict(ExitSettings(distance_unit='POINTS',sl_enabled=True,sl_distance=10,
        arm_enabled=True,arm_gain=20,trail_gap=5,repeat_gap=5))
    before=deepcopy(old)
    draft,pending=pnl_rule_draft(old,2000,None)
    assert draft['sl_distance']==.5 and draft['distance_unit']=='PRICE_PERCENT'
    assert pending=={'arm_gain','trail_gap','repeat_gap'}
    assert draft['trailing_unit']=='POINTS' and draft['arm_gain']==20
    draft['sl_distance']=.75
    resolved,pending=pnl_rule_draft(draft,2000,40_000_000)
    assert not pending and resolved['sl_distance']==.75
    assert resolved['arm_gain']==5 and resolved['trail_gap']==resolved['repeat_gap']==1.25
    assert old==before


def test_new_preset_needs_no_market_data_to_fill_the_editor():
    from ckps.rules.defaults import default_exit_settings
    original=default_exit_settings()
    draft,pending=pnl_rule_draft(original)
    assert draft==original and not pending
    assert draft['sl_distance']==1 and draft['arm_gain']==5 and draft['repeat_gap']==1.5


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_cash_changes_and_restart_preserve_basis_before_full_trailing_exit(system,side,sign):
    from ckps.trading.execution import Engine
    engine,broker,store=system
    engine.settings.exit=asdict(policy())
    engine.paper_capital(200_000_000)
    engine.open_manual(side,4,'MOK');engine.poll();engine.arm(True)
    broker.set_price(2000+sign*28);engine.poll()
    p=store.positions()[0]
    floor=p.floor;metrics=deepcopy(p.metrics)
    engine.paper_capital(250_000_000)
    assert store.positions()[0].margin_per_contract==40_000_000
    engine=Engine(store,broker,engine.settings);engine.poll()
    assert not engine.enabled.is_set()
    assert store.positions()[0].floor==floor and store.positions()[0].metrics==metrics
    engine.arm(True)
    for gain in (23,18,13):
        broker.set_price(2000+sign*gain);engine.poll();engine.poll()
        assert not store.positions()
        assert store.positions(closed=True)[0].margin_per_contract==40_000_000
    assert [o.quantity for o in store.orders() if o.action=='CLOSE']==[4]


def test_preview_amount_scales_with_remaining_quantity_without_repricing_the_basis():
    rules=asdict(policy())
    ref=ProtectionReference(2000,40_000_000,4,'VỊ THẾ')
    base,detail=pnl_preview(rules,ref)
    assert '160,000,000' in base
    assert 'ARM 5 % PNL = 20.0đ' in detail and '8,000,000 đ/4 HĐ' in detail
    assert 'Lùi 1.25 điểm % PNL = 5.0đ' in detail and '2,000,000 đ/4 HĐ' in detail
    base,detail=pnl_preview(rules,ProtectionReference(2000,40_000_000,2,'VỊ THẾ'))
    assert '80,000,000' in base and '4,000,000 đ/2 HĐ' in detail
    assert '1,000,000 đ/2 HĐ' in detail
    assert pnl_preview(rules,ProtectionReference(2000,40_000_000,None))[0].endswith('CHỜ HĐ')


def test_reference_prefers_held_basis_and_does_not_use_cash_or_a_different_contract():
    p=Position.create('VN30F1M','LONG',2,2000,margin_per_contract=40_000_000)
    view={'contract':p.symbol,'positions':[asdict(p)],'account':{
        'margin_per_contract':80_000_000,'total_money':999_000_000}}
    before=deepcopy(view)
    assert protection_reference(view)==ProtectionReference(2000,40_000_000,2,'VỊ THẾ')
    view['positions'][0]['symbol']='VN30F2612'
    assert protection_reference(view)==ProtectionReference()
    view=before;view['positions']=[]
    view['quotes']={p.symbol:asdict(Quote(p.symbol,2000))}
    view['LONG']=view['SHORT']={'maximum':3}
    ref=protection_reference(view,entry=2010)
    assert ref.margin==80_400_000 and ref.quantity==3


@pytest.mark.parametrize('value',['','nan','inf','0','-2000'])
def test_invalid_lo_does_not_show_pnl_estimates_from_a_different_market_price(value):
    from types import SimpleNamespace
    from ckps.dashboard.mayin.protection_form import ProtectionFormMixin
    field=lambda raw:SimpleNamespace(get=lambda:raw)
    view={'contract':'VN30F1M','quotes':{'VN30F1M':asdict(Quote('VN30F1M',2000))},
          'account':{'margin_per_contract':40_000_000},'LONG':{'maximum':2},'SHORT':{'maximum':2}}
    form=SimpleNamespace(app=SimpleNamespace(view=view,settings=SimpleNamespace(max_quote_age=10),
        qty=field('2'),kind=field('LO'),limit=field(value)))
    ref=ProtectionFormMixin._pnl_reference(form)
    assert ref==ProtectionReference()
    assert pnl_preview(asdict(policy()),ref)[0]=='CHỜ GIÁ VỐN / GIÁ VÉ'


@pytest.mark.parametrize('side,peak,trail_pnl',[('LONG',2025,'4,05'),('SHORT',1975,'3,95')])
def test_dynamic_display_converts_atr_components_to_pnl_using_the_actual_peak(side,peak,trail_pnl):
    from ckps.dashboard.mayin.pnl_preview import dynamic_pnl_preview
    from ckps.rules.defaults import default_exit_settings
    p=Position.create('VN30F1M',side,2,2000,margin_per_contract=40_000_000)
    p.best=peak
    view={'contract':p.symbol,'positions':[asdict(p)]}
    before=deepcopy(view)
    ref=protection_reference(view)
    summary,detail=dynamic_pnl_preview(view,default_exit_settings(),ref,1.)
    assert 'START 2,50 % PNL' in summary and f'Lùi ATR {trail_pnl} điểm % PNL' in summary
    assert '1,000,000 đ/HĐ' in detail and '2,000,000 đ/2 HĐ' in detail
    assert view==before
    assert dynamic_pnl_preview(view,default_exit_settings(),ref,None) is None


def test_compact_dynamic_uses_the_same_trigger_and_keeps_full_distance_in_details():
    from ckps.dashboard.mayin.management_preview import position_milestones
    from ckps.rules.defaults import default_exit_settings
    rule=load_record(ExitSettings,default_exit_settings())
    p=Position.create('VN30F1M','LONG',1,2000,margin_per_contract=40_000_000,history_verified=True)
    evaluate(p,2012,rule,1.)
    p.metrics['DYN:AUTO']={'count':1,'anchor':2008.4}
    before=deepcopy(asdict(p))
    full=position_milestones(p,rule,2009,1.)[1]
    compact=position_milestones(p,rule,2009,1.,compact=True)[1]
    assert '2,007.8' in full.value and compact.value=='AUTO · MỐC 2,007.8'
    assert 'Còn' in full.detail and 'Còn' not in compact.detail
    assert '+1.95% PNL' in compact.detail and '780,000 đ/1 HĐ' in compact.detail
    assert asdict(p)==before


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_scale_in_uses_weighted_fill_basis_and_reduction_does_not_reset_it(system,side,sign):
    engine,broker,store=system
    engine.settings.exit=asdict(policy())
    engine.open_manual(side,1,'MOK');engine.poll()
    broker.set_price(2020);engine.poll()
    engine.open_manual(side,1,'MOK');engine.poll()
    p=store.positions()[0]
    assert p.entry==2010 and p.margin_per_contract==40_200_000
    arm=levels(p,engine.exits())['arm']
    assert arm==pytest.approx(2010+sign*20.1) and p.pnl_pct(arm)==pytest.approx(5)
    engine.close_position(p.id,1);engine.poll()
    p=store.positions()[0]
    assert p.margin_per_contract==40_200_000 and levels(p,engine.exits())['arm']==arm
