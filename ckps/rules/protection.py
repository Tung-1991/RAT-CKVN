"""Directional adapter around the original MayinTien PROTECT calculation."""
from __future__ import annotations

from math import floor, isfinite

from ckps.models import Decision, ExitSettings, Position
from ckps.rules.calculations import protect_level
from ckps.rules.pnl import price_rules


def close_quantity(remaining, original, pct, basis="REMAINING"):
    if not 0 < pct <= 100 or remaining <= 0:
        return 0
    base = original if basis == "ORIGINAL" else remaining
    return min(remaining, max(1, floor(base * pct / 100 + 1e-9)))


def adverse_anchor(sign, *prices):
    """Keep the least favourable evidenced price, ignoring absent legacy values."""
    values = [value for value in prices if value is not None and isfinite(value) and value > 0]
    return (min(values) if sign > 0 else max(values)) if values else 0.0


def repeat_trigger(position: Position, settings: ExitSettings, stage, level):
    """Read-only effective hit price, shared by execution and E/M Preview."""
    settings = price_rules(settings, position.entry, position.margin_per_contract)
    prefix = "arm" if stage == "ARM" else "dynamic"
    policy = getattr(settings, prefix + "_policy")
    state = position.metrics.get(stage + ":" + policy, {})
    if not state.get("count", 0):
        return level
    if not getattr(settings, prefix + "_repeat"):
        return None
    anchor = state.get("anchor", 0.0)
    if not isfinite(anchor) or anchor <= 0 or not isfinite(settings.repeat_gap) or settings.repeat_gap <= 0:
        return None
    if stage == "ARM":
        peak = state.get("round_best", 0.0) or anchor
        best = max(anchor, peak) if position.sign > 0 else min(anchor, peak)
        return best - position.sign * settings.points(settings.repeat_gap, position.entry)
    next_trigger = anchor - position.sign * settings.points(settings.repeat_gap, anchor)
    return min(level, next_trigger) if position.sign > 0 else max(level, next_trigger)


def levels(position: Position, settings: ExitSettings, atr_pct=0.0):
    """Keep the proven long formula; reflect short prices around their entry.

    A trail percentage is still measured from the actual favourable extreme,
    not its reflected coordinate. Point distances remain constant on both sides.
    """
    entry, sign = position.entry, position.sign
    settings = price_rules(settings, entry, position.margin_per_contract)
    best = position.best or entry
    mfe = max(0.0, sign * (best - entry))
    mirror_peak = entry + mfe
    factor = best / mirror_peak if sign < 0 else 1.0
    arm = settings.points(settings.arm_gain, entry) / entry * 100 if settings.arm_enabled else 1e12
    trail = settings.points(settings.trail_gap, entry) / entry * 100
    sl = entry - sign * settings.points(settings.sl_distance, entry) if settings.sl_enabled else 0.0
    tp = entry + sign * settings.points(settings.tp_distance, entry) if settings.tp_enabled else 0.0
    mirrored_sl = entry + sign * (sl - entry) if sl else 0.0
    previous = entry + sign * (position.floor - entry) if position.floor else 0.0
    until = settings.points(settings.retention_until, entry) / entry * 100
    result = protect_level(
        entry, mfe / entry * 100, arm, trail,
        dynamic_enabled=settings.dynamic_enabled,
        sl_price=mirrored_sl,
        atr_pct=atr_pct,
        atr_multiplier=settings.atr_trail_multiplier * factor,
        atr_activation_multiplier=settings.atr_start_multiplier,
        atr_activation_enabled=settings.atr_start_enabled,
        atr_trail_enabled=settings.atr_trail_enabled,
        retention_pct=settings.retention_pct,
        retention_until_pct=until,
        retention_enabled=settings.retention_enabled,
        retention_until_enabled=settings.retention_until_enabled,
        previous_trigger_price=previous,
    )
    trigger = entry + sign * (result.trigger_price - entry) if result.active else 0.0
    return {"sl": sl, "tp": tp, "protect": trigger,
            "stage": result.state, "mfe_points": mfe,
            "start_points": result.activation_mfe_pct * entry / 100,
            "arm": entry + sign * settings.points(settings.arm_gain, entry) if settings.arm_enabled else 0.0}


def observe_repeat(position: Position, price: float, settings: ExitSettings):
    """Only new post-completion prices can establish the next ARM round."""
    settings = price_rules(settings, position.entry, position.margin_per_contract)
    for policy in ("AUTO", "ALERT"):
        state = position.metrics.get("ARM:" + policy, {})
        anchor = state.get("anchor", 0.0)
        if not state.get("count") or not anchor or state.get("pending"):
            continue
        peak = state.get("round_best", 0.0)
        above_arm = position.profit_points(price) + 1e-9 >= settings.points(settings.arm_gain, position.entry)
        if peak or (above_arm and position.sign * (price - anchor) > 1e-9):
            state["round_best"] = (max(peak or price, price) if position.sign > 0 else min(peak or price, price))
            position.metrics["ARM:" + policy] = state


def evaluate(position: Position, price: float, settings: ExitSettings, atr_pct=0.0):
    if price <= 0 or position.entry <= 0 or position.quantity <= 0:
        return None
    settings = price_rules(settings, position.entry, position.margin_per_contract)
    sign = position.sign
    position.best = max(position.best or position.entry, price) if sign > 0 else min(position.best or position.entry, price)
    position.worst = min(position.worst or position.entry, price) if sign > 0 else max(position.worst or position.entry, price)
    observe_repeat(position, price, settings)
    view = levels(position, settings, atr_pct)
    if view["protect"]:
        position.floor = view["protect"]
    position.metrics["levels"] = view
    if settings.sl_enabled and sign * (price - view["sl"]) <= 1e-9:
        return Decision("SL", view["sl"], position.quantity)
    if settings.tp_enabled and sign * (price - view["tp"]) >= -1e-9:
        return Decision("TP", view["tp"], position.quantity)
    # PROTECT may never turn a positive-gain rule into a stop at a loss.
    if not position.history_verified or position.profit_points(price) <= 0:
        return None
    stage = view["stage"]
    if not view["protect"] or stage not in {"ARM", "DYN"}:
        return None
    if stage == "ARM" and not settings.arm_enabled:
        return None
    prefix = "arm" if stage == "ARM" else "dynamic"
    policy = getattr(settings, prefix + "_policy")
    state = position.metrics.get(stage + ":" + policy, {})
    if (stage == "ARM" and state.get("count") and not settings.arm_repeat_below_arm
            and position.profit_points(price) + 1e-9 < settings.points(settings.arm_gain, position.entry)):
        return None
    trigger = repeat_trigger(position, settings, stage, view["protect"])
    if trigger is None:
        return None
    if sign * (price - trigger) > 1e-9:
        return None
    qty = close_quantity(position.quantity, position.original_quantity,
                         getattr(settings, prefix + "_close_pct"), getattr(settings, prefix + "_basis"))
    return Decision(stage, trigger, qty, policy, stage)
