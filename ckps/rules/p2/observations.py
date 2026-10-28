"""Read-only evidence for EMA transitions; never creates or approves orders."""
from __future__ import annotations

from math import isfinite
from typing import Any


def finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def ema_cross_evidence(current: dict, previous: dict, *, required: bool,
                       use_ema: bool = True, observed_at: str = "") -> dict:
    fast, slow = (finite(current.get(f"buy_ema_{side}")) for side in ("fast", "slow"))
    prior_fast, prior_slow = (finite(previous.get(f"buy_ema_{side}")) for side in ("fast", "slow"))
    ready = current.get("signal_ready") is not False and all(
        value is not None for value in (fast, slow, prior_fast, prior_slow))
    observed_at = str(current.get("indicator_observed_at") or observed_at or "")
    up = bool(ready and prior_fast <= prior_slow and fast > slow)
    down = bool(ready and prior_fast >= prior_slow and fast < slow)
    state = ("OFF" if not use_ema or not required else "UNKNOWN" if not ready
             else "CROSSED_UP" if up else "WAIT_DOWN" if fast > slow else "WAIT_UP")
    return {"required": bool(required and use_ema), "state": state,
            "previous_fast": prior_fast, "previous_slow": prior_slow,
            "current_fast": fast, "current_slow": slow,
            "crossed_up": up, "crossed_down": down,
            "observed_at": str(observed_at or ""),
            "cross_at": str(observed_at or "") if up else ""}
