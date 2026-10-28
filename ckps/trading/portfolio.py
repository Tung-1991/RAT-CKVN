from __future__ import annotations

from dataclasses import dataclass
from math import floor

from ckps.models import ExitSettings, Settings, Snapshot, load_record


@dataclass
class Capacity:
    maximum: int
    broker_maximum: int
    risk_per_contract: float | None
    available_budget: float | None
    reason: str = ""
    margin_per_contract: float | None = None


def capacity(settings: Settings, snapshot: Snapshot, positions, orders, side, entry, exits: ExitSettings):
    """Account exposure includes unmanaged positions. Broker reservations count once."""
    broker_max = snapshot.qmax_long if side == "LONG" else snapshot.qmax_short
    margin = snapshot.margin_per_contract
    if broker_max is None or margin is None or margin <= 0:
        return Capacity(0, 0, None, None, "Chưa có sức mở/ký quỹ xác nhận.")
    reference = snapshot.margin_reference_price
    if reference and entry > 0 and abs(entry - reference) > 1e-9:
        # Quote preview is conservative; execution obtains PPSE for the actual ticket.
        ratio = entry / reference
        margin *= ratio
        if ratio > 1:
            affordable = (floor(snapshot.remaining_margin / margin) if snapshot.remaining_margin is not None
                          else floor(broker_max / ratio))
            broker_max = min(broker_max, affordable)
    # Accepted broker orders have already reduced PPSE. Reserve only local ones.
    local = [o for o in orders if o.pending and o.action == "OPEN" and not o.broker_id]
    local_qty = sum(o.remainder for o in local)
    maximum = max(0, int(broker_max) - local_qty)
    held = sum(p.quantity for p in positions)
    pending_qty = sum(o.remainder for o in orders if o.pending and o.action == "OPEN")
    if settings.max_contracts:
        maximum = min(maximum, max(0, settings.max_contracts - held - pending_qty))
    room = None
    if settings.capital_limit:
        if snapshot.used_margin is None or snapshot.pending_margin is None:
            return Capacity(0, int(broker_max), None, None, "Thiếu ký quỹ đã dùng/đang chờ.")
        room = max(0.0, settings.capital_limit - snapshot.used_margin - snapshot.pending_margin - local_qty * margin)
        maximum = min(maximum, floor(room / margin))
    risk_each = exits.points(exits.sl_distance, entry) * 100_000 + settings.estimated_fee_per_contract * 2 if exits.sl_enabled else None
    risk_ceiling = settings.risk_limit or None
    if settings.risk_nav_pct:
        if snapshot.nav is None or snapshot.nav <= 0:
            return Capacity(0, int(broker_max), risk_each, room, "Thiếu NAV để tính trần rủi ro.")
        by_nav = snapshot.nav * settings.risk_nav_pct / 100
        risk_ceiling = min(risk_ceiling, by_nav) if risk_ceiling is not None else by_nav
    if risk_ceiling is not None:
        if risk_each is None or risk_each <= 0:
            return Capacity(0, int(broker_max), risk_each, room, "Cần SL để kiểm tra trần rủi ro.")
        used_risk = 0.0
        for position in positions:
            rule = load_record(ExitSettings, position.exit_overrides or settings.exit)
            if not rule.sl_enabled:
                return Capacity(0, int(broker_max), risk_each, room, "Có vị thế chưa có SL; chưa xác định tổng rủi ro.")
            used_risk += position.quantity * (rule.points(rule.sl_distance, position.entry) * 100_000 + settings.estimated_fee_per_contract * 2)
        for order in orders:
            if order.pending and order.action == "OPEN":
                rule = load_record(ExitSettings, order.exit_settings or settings.exit)
                if not rule.sl_enabled:
                    return Capacity(0, int(broker_max), risk_each, room, "Lệnh mở đang chờ chưa có SL.")
                used_risk += order.remainder * (rule.points(rule.sl_distance, order.price or entry) * 100_000 + settings.estimated_fee_per_contract * 2)
        maximum = min(maximum, floor(max(0.0, risk_ceiling - used_risk) / risk_each))
    return Capacity(maximum, int(broker_max), risk_each, room,
                    "Đã hết sức mở hoặc chạm giới hạn vốn/rủi ro." if maximum <= 0 else "", margin)
