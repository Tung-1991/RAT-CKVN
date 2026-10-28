"""Validated derivative balances. Stock cash never supplies derivative buying power."""
from math import isfinite


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) and result >= 0 else None


def balances(derivative):
    remaining = amount(derivative.get("remainSecure"))
    used = amount(derivative.get("usedSecure"))
    nav = next((amount(derivative[key]) for key in ("netAssetValue", "nav", "equity")
                if derivative.get(key) is not None), None)
    total = next((amount(derivative[key]) for key in ("totalCash", "totalMoney", "totalSecure")
                  if derivative.get(key) is not None), None)
    if total is None and all(value is not None for value in (remaining, used)):
        # Confirmed deposited collateral only; pending transfers are not spendable money.
        total = remaining + used
    return dict(remaining_margin=remaining, used_margin=used, nav=nav, collateral_total=total)
