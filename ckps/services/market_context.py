"""Compact read-only context for the trading UI; no notification or execution gate."""
import json
import os
import time

from ckps.config import runtime_root
from ckps.services.signals import p1_snapshot
from ckps.services.technical_notifications import completed_bars


def publish_context(value):
    folder = runtime_root() / "signals"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "market-context.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def context(snapshot, *, max_age=10, now=None):
    now = time.time() if now is None else now
    quote = snapshot.quotes.get(snapshot.contract)
    if not quote or not quote.fresh(max_age, now):
        return {"text": "CHỜ GIÁ DNSE", "state": "WAIT"}
    rows = completed_bars(snapshot.bars)
    p1 = p1_snapshot(rows, quote.last)
    text = {"ABOVE": "TRÊN MA200 1D", "BELOW": "DƯỚI MA200 1D", "EQUAL": "TẠI MA200 1D"}.get(p1['state'], "CHỜ MA200 1D")
    movement = f"Phiên {quote.last - float(rows[-1]['close']):+g}đ" if rows else "CHỜ NẾN"
    try:
        shared = json.loads((runtime_root() / "signals" / "market-context.json").read_text(encoding="utf-8"))
        if shared.get('contract') == snapshot.contract and -2 <= now - shared['observed_at'] <= max_age:
            movement = shared.get('movement', movement)
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return {"text": text + " · " + movement, "state": p1['state'], "observed_at": quote.at}
