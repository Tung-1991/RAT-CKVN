"""Gross position PNL% uses a pinned initial margin per contract."""
from dataclasses import asdict, replace
from math import isfinite

from ckps.models import ExitSettings, load_record

DISTANCES = ('sl_distance','tp_distance','arm_gain','trail_gap','repeat_gap','retention_until')


def reference_margin(margin, reference, entry):
    if any(value is None or not isinstance(value,(int,float)) or not isfinite(value) or value<=0 for value in (margin,reference,entry)):
        return None
    return margin * entry / reference


def price_rules(rules, entry, margin):
    if rules.distance_unit != 'PNL_PERCENT':return rules
    if any((rules.sl_enabled,rules.tp_enabled,rules.arm_enabled,rules.dynamic_enabled)) and not reference_margin(margin,entry,entry):
        raise ValueError('Chờ ký quỹ xác minh để tính % PNL.')
    values = {key:rules.points(getattr(rules,key),entry,margin) for key in DISTANCES}
    return replace(rules, distance_unit='POINTS', **values)


def pnl_rules(values, entry=None, margin=None):
    """Convert an old rule explicitly; unavailable basis never changes its units."""
    rules = load_record(ExitSettings, values).validate()
    if rules.distance_unit == 'PNL_PERCENT':return asdict(rules)
    converted = {}
    for key in DISTANCES:
        value = getattr(rules,key)
        if value == 0:converted[key] = 0.;continue
        if not margin or not isfinite(margin) or margin<=0 or not entry or not isfinite(entry) or entry<=0:
            raise ValueError('Cần giá và ký quỹ xác minh để quy đổi cấu hình cũ sang % PNL.')
        converted[key] = rules.points(value,entry) * 100_000 / margin * 100
    return asdict(replace(rules, distance_unit='PNL_PERCENT', **converted))
