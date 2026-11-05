"""Price distances and explicit migration of legacy point/margin-PNL rules."""
from dataclasses import asdict, replace
from math import isfinite

from ckps.models import ExitSettings, load_record

DISTANCES = ('sl_distance','tp_distance','arm_gain','trail_gap','repeat_gap','retention_until')
TRAILING_DISTANCES = ('arm_gain', 'trail_gap', 'repeat_gap')


def trailing_needs_margin(rules):
    return (rules.trailing_unit or rules.distance_unit) == 'PNL_PERCENT' and bool(
        rules.arm_enabled or rules.dynamic_enabled and rules.dynamic_repeat and rules.dynamic_close_pct < 100)


def reference_margin(margin, reference, entry):
    if any(value is None or not isinstance(value,(int,float)) or not isfinite(value) or value<=0 for value in (margin,reference,entry)):
        return None
    return margin * entry / reference


def price_rules(rules, entry, margin):
    unit=rules.trailing_unit or rules.distance_unit
    if rules.distance_unit not in {'PRICE_PERCENT','PNL_PERCENT'} and unit==rules.distance_unit:return rules
    if rules.distance_unit=='PNL_PERCENT' and any((rules.sl_enabled,rules.tp_enabled,rules.arm_enabled,rules.dynamic_enabled)) and not reference_margin(margin,entry,entry):
        raise ValueError('Chờ ký quỹ xác minh để đọc cấu hình % PNL cũ.')
    if rules.distance_unit=='PRICE_PERCENT' and not reference_margin(entry,entry,entry):
        raise ValueError('Chờ giá vốn hợp lệ để tính % giá.')
    missing=not reference_margin(margin,entry,entry)
    if trailing_needs_margin(rules) and missing:
        raise ValueError('Chờ ký quỹ cơ sở/HĐ để tính ARM theo PNL.')
    values = {key:(0. if key in TRAILING_DISTANCES and unit=='PNL_PERCENT' and missing
                   else rules.points(getattr(rules,key),entry,margin,
                        unit=unit if key in TRAILING_DISTANCES else rules.distance_unit)) for key in DISTANCES}
    return replace(rules, distance_unit='POINTS', trailing_unit='POINTS' if rules.trailing_unit else None, **values)


def pnl_rule_draft(values, entry=None, margin=None):
    """Convert only complete unit groups; unresolved groups retain their units/values."""
    rules=load_record(ExitSettings,values).validate()
    result=asdict(rules);pending=set()
    groups=(('distance_unit',('sl_distance','tp_distance','retention_until'),'PRICE_PERCENT',rules.distance_unit),
            ('trailing_unit',TRAILING_DISTANCES,'PNL_PERCENT',rules.trailing_unit or rules.distance_unit))
    for field,keys,target,source in groups:
        source='PRICE_PERCENT' if source=='PERCENT' else source
        needs_basis=source!=target and any(getattr(rules,key)!=0 for key in keys)
        if needs_basis and (not reference_margin(entry,entry,entry) or
                'PNL_PERCENT' in {source,target} and not reference_margin(margin,entry,entry)):
            result[field]=source
            pending.update(keys)
            continue
        result[field]=target
        for key in keys:
            value=getattr(rules,key)
            if source==target or value==0:continue
            points=rules.points(value,entry,margin,unit=source)
            result[key]=points*100_000/margin*100 if target=='PNL_PERCENT' else points/entry*100
    return result,pending


def pnl_trailing_rules(values, entry=None, margin=None):
    """Strict conversion used when every target value is required for preview."""
    result,pending=pnl_rule_draft(values,entry,margin)
    if pending:
        if not reference_margin(entry,entry,entry):raise ValueError('Chờ giá vốn xác minh để quy đổi RULE; giữ nguyên mốc đang chạy.')
        raise ValueError('Chờ ký quỹ cơ sở/HĐ để quy đổi ARM; giữ nguyên RULE đã lưu.')
    return result


def price_percent_rules(values, entry=None, margin=None):
    """Build a price-percent draft; never relabel old numbers or mutate live rules."""
    rules = load_record(ExitSettings, values).validate()
    if rules.distance_unit == 'PRICE_PERCENT':return asdict(rules)
    if rules.distance_unit == 'PERCENT':
        return asdict(replace(rules,distance_unit='PRICE_PERCENT'))
    converted = {}
    for key in DISTANCES:
        if key in TRAILING_DISTANCES and rules.trailing_unit is not None:
            converted[key]=getattr(rules,key)
            continue
        value = getattr(rules,key)
        if value == 0:converted[key] = 0.;continue
        if not reference_margin(entry,entry,entry):
            raise ValueError('Cần giá vốn/giá hợp đồng xác minh để quy đổi cấu hình cũ sang % giá.')
        if rules.distance_unit=='PNL_PERCENT' and not reference_margin(margin,entry,entry):
            raise ValueError('Cần ký quỹ cơ sở đã lưu để quy đổi cấu hình cũ sang % giá vốn; giữ nguyên các mốc đang chạy.')
        converted[key] = rules.points(value,entry,margin) / entry * 100
    return asdict(replace(rules, distance_unit='PRICE_PERCENT', **converted))
