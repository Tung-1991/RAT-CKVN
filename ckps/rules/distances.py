"""Price distances and explicit migration of legacy point/margin-PNL rules."""
from dataclasses import asdict, replace
from math import isfinite

from ckps.models import ExitSettings, load_record

DISTANCES = ('sl_distance','tp_distance','arm_gain','trail_gap','repeat_gap','retention_until')


def reference_margin(margin, reference, entry):
    if any(value is None or not isinstance(value,(int,float)) or not isfinite(value) or value<=0 for value in (margin,reference,entry)):
        return None
    return margin * entry / reference


def price_rules(rules, entry, margin):
    if rules.distance_unit not in {'PRICE_PERCENT','PNL_PERCENT'}:return rules
    if rules.distance_unit=='PNL_PERCENT' and any((rules.sl_enabled,rules.tp_enabled,rules.arm_enabled,rules.dynamic_enabled)) and not reference_margin(margin,entry,entry):
        raise ValueError('Chờ ký quỹ xác minh để đọc cấu hình % PNL cũ.')
    if rules.distance_unit=='PRICE_PERCENT' and not reference_margin(entry,entry,entry):
        raise ValueError('Chờ giá vốn hợp lệ để tính % giá.')
    values = {key:rules.points(getattr(rules,key),entry,margin) for key in DISTANCES}
    return replace(rules, distance_unit='POINTS', **values)


def price_percent_rules(values, entry=None, margin=None):
    """Build a price-percent draft; never relabel old numbers or mutate live rules."""
    rules = load_record(ExitSettings, values).validate()
    if rules.distance_unit == 'PRICE_PERCENT':return asdict(rules)
    if rules.distance_unit == 'PERCENT':
        return asdict(replace(rules,distance_unit='PRICE_PERCENT'))
    converted = {}
    for key in DISTANCES:
        value = getattr(rules,key)
        if value == 0:converted[key] = 0.;continue
        if not reference_margin(entry,entry,entry):
            raise ValueError('Cần giá vốn/giá hợp đồng xác minh để quy đổi cấu hình cũ sang % giá.')
        if rules.distance_unit=='PNL_PERCENT' and not reference_margin(margin,entry,entry):
            raise ValueError('Cần ký quỹ cơ sở đã lưu để quy đổi cấu hình cũ sang % giá vốn; giữ nguyên các mốc đang chạy.')
        converted[key] = rules.points(value,entry,margin) / entry * 100
    return asdict(replace(rules, distance_unit='PRICE_PERCENT', **converted))
