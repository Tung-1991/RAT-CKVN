"""One price denominator; legacy conversion preserves actual exit levels."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from ckps.models import ExitSettings, Position, load_record
from ckps.rules.defaults import default_exit_settings
from ckps.rules.distances import price_rule_draft, price_rule_values
from ckps.rules.protection import evaluate, levels
from ckps.dashboard.mayin.pnl_preview import ProtectionReference, pnl_preview, dynamic_pnl_preview


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
@pytest.mark.parametrize('margin',[20_000_000,40_000_000])
def test_margin_pnl_migration_preserves_stops_targets_arm_floor_and_state(side,sign,margin):
    old=ExitSettings(distance_unit='PRICE_PERCENT',trailing_unit='PNL_PERCENT',
        sl_enabled=True,sl_distance=1,tp_enabled=True,tp_distance=4,
        arm_enabled=True,arm_gain=5,trail_gap=1.5,repeat_gap=1.5,
        dynamic_enabled=True,dynamic_policy='AUTO',retention_pct=65)
    p=Position.create('VN30F1M',side,3,2000,history_verified=True,margin_per_contract=margin)
    p.best=2000+sign*50;p.floor=2000+sign*10
    p.metrics={'ARM:AUTO':{'count':1,'anchor':2000+sign*15}}
    original,holding=asdict(old),asdict(p)
    converted=price_rule_values(original,p.entry,margin)
    modern=ExitSettings(**converted)
    assert modern.distance_unit==modern.trailing_unit=='PRICE_PERCENT'
    assert modern.arm_gain==pytest.approx(5*margin/100/100_000/2000*100)
    assert modern.trail_gap==pytest.approx(1.5*margin/100/100_000/2000*100)
    before,after=levels(p,old,1.43),levels(p,modern,1.43)
    assert before==pytest.approx(after)
    hit=before['protect']
    a,b=evaluate(deepcopy(p),hit,old,1.43),evaluate(deepcopy(p),hit,modern,1.43)
    assert a.reason==b.reason=='ARM' and a.quantity==b.quantity==3
    assert a.price==pytest.approx(b.price)
    assert asdict(old)==original and asdict(p)==holding


def test_pending_old_pnl_group_keeps_source_numbers_until_real_basis_is_available():
    raw=asdict(ExitSettings(distance_unit='PRICE_PERCENT',trailing_unit='PNL_PERCENT',
        sl_enabled=True,sl_distance=1,arm_enabled=True,arm_gain=5,trail_gap=1.5,repeat_gap=1.5))
    original=deepcopy(raw)
    draft,pending=price_rule_draft(raw,2000,None)
    assert pending=={'arm_gain','trail_gap','repeat_gap'}
    assert draft['trailing_unit']=='PNL_PERCENT' and draft['arm_gain']==5
    draft['sl_distance']=.8
    converted,pending=price_rule_draft(draft,2000,40_000_000)
    assert not pending and converted['sl_distance']==.8
    assert converted['arm_gain']==1 and converted['trail_gap']==converted['repeat_gap']==.3
    assert raw==original


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_new_price_rules_execute_without_margin_and_report_points_and_money(side,sign):
    rule=load_record(ExitSettings,default_exit_settings())
    p=Position.create('VN30F1M',side,2,2000,history_verified=True)
    assert levels(p,rule)['sl']==2000-sign*20
    assert levels(p,rule)['arm']==2000+sign*20
    assert evaluate(p,2000+sign*30,rule) is None
    decision=evaluate(p,2000+sign*24,rule)
    assert decision.reason=='ARM' and decision.quantity==2
    base,detail=pnl_preview(asdict(rule),ProtectionReference(2000,None,2,'VỊ THẾ'))
    assert 'Giá vào 2,000.0' in base and '2 HĐ' in base
    assert 'ARM 1 % giá vào = 20.0đ' in detail and '4,000,000 đ/2 HĐ' in detail
    assert 'Lùi 0.3 % giá vào = 6.0đ' in detail and '1,200,000 đ/2 HĐ' in detail
    assert 'PNL' not in detail and 'ký quỹ' not in base.lower()


def test_dynamic_preview_uses_entry_percent_even_without_margin_and_does_not_change_atr():
    rule=default_exit_settings()
    ref=ProtectionReference(2000,None,2,'VÉ MỚI')
    summary,detail=dynamic_pnl_preview({},rule,ref,1.43)
    assert 'START 0,71 % giá vào' in summary or 'START 0,72 % giá vào' in summary
    assert 'Lùi ATR 1,14 % giá vào' in summary
    assert '1,430,000 đ/HĐ' in detail and '2,860,000 đ/2 HĐ' in detail
    assert 'PNL' not in detail
    assert rule==default_exit_settings()
