from __future__ import annotations

from dataclasses import dataclass
from math import floor

from ckps.models import ExitSettings, Settings, Snapshot
from ckps.connections.dnse.fees import fee_pair


@dataclass
class Capacity:
    maximum: int
    broker_maximum: int
    risk_per_contract: float | None
    available_budget: float | None
    reason: str = ""
    margin_per_contract: float | None = None


def capacity(settings: Settings, snapshot: Snapshot, positions, orders, side, entry, exits: ExitSettings):
    """Broker buying power sets quantity; SL loss is an estimate, never an extra cap."""
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
    room = (max(0.0, snapshot.remaining_margin - local_qty * margin)
            if snapshot.remaining_margin is not None else None)
    fee_open, fee_close = fee_pair(settings, snapshot)
    fee_round = fee_open + fee_close if fee_open is not None and fee_close is not None else None
    risk_each = exits.points(exits.sl_distance, entry, margin) * 100_000 + fee_round if exits.sl_enabled and fee_round is not None else None
    return Capacity(maximum, int(broker_max), risk_each, room,
                    "Đã hết sức mở DNSE hoặc đang giữ chỗ cho lệnh mở." if maximum <= 0 else "", margin)
