"""Compact read-only context for the trading UI; no notification or execution gate."""
import json
import os
import time
from math import isfinite

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


def entry_context(analysis, contract, *, max_age=10, now=None):
    """Expose only a confirmed result, never the intermediate READY badge."""
    now=time.time() if now is None else now
    waiting={'state':'WAIT_SOURCE'}
    try:
        if analysis.get('contract')!=contract or analysis.get('error'):
            return waiting
        if not all(-2<=now-float(analysis[key])<=max_age for key in ('observed_at','quote_at')):
            return waiting
        p2=analysis.get('p2',{})
        if p2.get('badge')=='OFF':return {'state':'OFF'}
        if not p2.get('price_fresh') or not p2.get('indicators'):return waiting
        if not p2.get('buy_alert'):return {'state':'WAIT'}
        price=float(analysis['quote_price'])
        if not isfinite(price) or price<=0:return waiting
        return {'state':'READY','price':price,
            'observed_at':min(float(analysis['observed_at']),float(analysis['quote_at']))}
    except (ValueError,TypeError,KeyError):
        return waiting


def context(snapshot, *, max_age=10, now=None):
    now = time.time() if now is None else now
    quote = snapshot.quotes.get(snapshot.contract)
    if not quote or quote.symbol!=snapshot.contract or not quote.fresh(max_age, now):
        return {"state":"WAIT","entry":{"state":"WAIT_SOURCE"}}
    rows = completed_bars(snapshot.bars)
    p1 = p1_snapshot(rows, quote.last)
    text = {"ABOVE": "TRÊN MA200 1D", "BELOW": "DƯỚI MA200 1D", "EQUAL": "TẠI MA200 1D"}.get(p1['state'], "CHỜ MA200 1D")
    entry={'state':'WAIT_SOURCE'}
    try:
        shared = json.loads((runtime_root() / "signals" / "market-context.json").read_text(encoding="utf-8"))
        if not isinstance(shared,dict):shared={}
        if shared.get('contract') == snapshot.contract and -2 <= now - shared['observed_at'] <= max_age:
            candidate=shared.get('entry',{})
            if not isinstance(candidate,dict):candidate={}
            if candidate.get('state') in {'WAIT','OFF'}:entry={'state':candidate['state']}
            elif candidate.get('state')=='READY':
                value=float(candidate['price'])
                if isfinite(value) and value>0 and -2<=now-float(candidate['observed_at'])<=max_age:
                    entry={'state':'READY','price':value,'observed_at':candidate['observed_at']}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return {"text":text,"state":p1['state'],"ma":p1.get('ma'),"observed_at":quote.at,'entry':entry}
