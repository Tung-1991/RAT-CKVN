"""Read-only START/ARM/repeat milestones, adapted from MayinTien position_em.

The directional rule supplies every protective threshold. Rendering never
advances MFE, consumes a repeat, changes permissions or creates an order.
"""
from dataclasses import dataclass
from math import isfinite

from ckps.models import ExitSettings, Position
from ckps.rules.protection import close_quantity, levels, repeat_trigger
from ckps.rules.distances import price_rules
from ..formatting import price


@dataclass(frozen=True)
class BranchPreview:
    value: str
    detail: str = ""


def _atr(value):
    return value if value is not None and isfinite(value) and value > 0 else None


def ticket_milestones(entry: float, rules: ExitSettings, atr_pct=None, *, margin_per_contract=None):
    """A ticket has two possible directions and no observed peak yet."""
    try:rules=price_rules(rules,entry,margin_per_contract)
    except ValueError:
        waiting='CHỜ KÝ QUỸ' if rules.distance_unit=='PNL_PERCENT' else 'CHỜ GIÁ VỐN'
        return tuple(BranchPreview(getattr(rules,prefix+'_policy')+' · '+waiting)
            if getattr(rules,prefix+'_enabled') else BranchPreview('OFF') for prefix in ('arm','dynamic'))
    def pair(distance):
        return f"L {price(entry + distance)} / S {price(entry - distance)}"
    arm = BranchPreview("OFF")
    dynamic = BranchPreview("OFF")
    if rules.arm_enabled:
        arm = BranchPreview(rules.arm_policy + " · PREVIEW",
                            "ARM " + pair(rules.points(rules.arm_gain, entry)) if entry > 0 else "CHỜ GIÁ VÀO")
    if rules.dynamic_enabled:
        if rules.atr_start_enabled and _atr(atr_pct) is None:
            dynamic = BranchPreview(rules.dynamic_policy + " · CHỜ ATR", "START: CHỜ NẾN 1D")
        elif entry <= 0:
            dynamic = BranchPreview(rules.dynamic_policy + " · PREVIEW", "CHỜ GIÁ VÀO")
        elif rules.atr_start_enabled:
            dynamic = BranchPreview(rules.dynamic_policy + " · PREVIEW",
                                    "START " + pair(entry * atr_pct / 100 * rules.atr_start_multiplier))
        else:
            dynamic = BranchPreview(rules.dynamic_policy + " · PREVIEW", "START OFF · Chờ có lãi")
    return arm, dynamic


def position_milestones(position: Position, rules: ExitSettings, current_price=None,
                        atr_pct=None, *, ready=True, pending=()):
    """Describe the same effective trigger used by evaluate(), including LẶP."""
    try:converted=price_rules(rules,position.entry,position.margin_per_contract)
    except ValueError:
        return tuple(BranchPreview(getattr(rules,prefix+'_policy')+' · CHỜ DỮ LIỆU','Chưa đủ dữ liệu quy đổi sang % giá vốn')
            if getattr(rules,prefix+'_enabled') else BranchPreview('OFF') for prefix in ('arm','dynamic'))
    rules=converted
    def distance_text(value):
        return f'{value/position.entry*100:g}% giá'
    view = levels(position, rules, _atr(atr_pct) or 0.0)
    armed = rules.arm_enabled and view["mfe_points"] + 1e-9 >= rules.points(rules.arm_gain, position.entry)

    def branch(stage):
        prefix = "arm" if stage == "ARM" else "dynamic"
        policy = getattr(rules, prefix + "_policy")
        def show(status, detail=""):
            return BranchPreview(policy + " · " + status, detail)
        if not getattr(rules, prefix + "_enabled"):
            return BranchPreview("OFF")
        if not position.history_verified:
            return show("XÁC MINH", "Chưa đủ lịch sử MAE/MFE")
        if not ready or not current_price or not isfinite(current_price):
            return show("CHỜ GIÁ", "Chờ đồng bộ vị thế/giá")
        if stage == "DYN" and armed:
            return show("NHƯỜNG ARM", "SAU ARM đang tiếp quản")
        if stage == "ARM" and not armed:
            distance = max(0, position.sign * (view["arm"] - current_price))
            return show("CHỜ ARM", f'{price(view["arm"])} · còn {distance_text(distance)}')
        if stage == "DYN" and view["stage"] != "DYN":
            if rules.atr_start_enabled and _atr(atr_pct) is None:
                return show("CHỜ ATR", "START: CHỜ NẾN 1D")
            if rules.atr_start_enabled and view["start_points"] > 0:
                start = position.entry + position.sign * view["start_points"]
                return show("CHỜ START", f'{price(start)} · chưa có mốc')
            return show("CHỜ CÓ LÃI", "Chưa có mức bảo vệ")
        target = repeat_trigger(position, rules, stage, view["protect"])
        state = position.metrics.get(stage + ":" + policy, {})
        if target is None:
            return show("XONG" if not getattr(rules, prefix + "_repeat") else "CHỜ MỐC LẶP",
                        "LẶP OFF" if not getattr(rules, prefix + "_repeat") else "Thiếu mốc/bước lặp hợp lệ")
        if pending:
            return show("CHỜ KHỚP", "Có lệnh đóng đang chờ")
        qty = close_quantity(position.quantity, position.original_quantity,
                             getattr(rules, prefix + "_close_pct"), getattr(rules, prefix + "_basis"))
        distance = max(0, position.sign * (current_price - target))
        label = "LẶP" if state.get("count", 0) else "MỐC"
        if position.profit_points(target) <= 0:
            return show("CHỜ LÃI DƯƠNG", "Mốc kế vượt giá vốn")
        remaining = f"Còn {distance_text(distance)}" if distance > 1e-9 else "Đã chạm mốc"
        detail = remaining + (f" · đóng {qty} HĐ" if policy == "AUTO" else " · chỉ báo")
        if position.profit_points(current_price) <= 0:
            detail = "Giá chưa có lãi · chưa xử lý"
        return show(label + " " + price(target), detail)

    return branch("ARM"), branch("DYN")
