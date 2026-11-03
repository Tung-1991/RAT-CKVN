"""Compact read-only context for the trading UI; no notification or execution gate."""
import json
import os
import time
from dataclasses import asdict
from math import isfinite

from ckps.config import runtime_root
from ckps.services.signals import p1_snapshot
from ckps.services.technical_notifications import completed_bars


WAIT_REASONS = {'ANALYSIS_ERROR', 'ANALYSIS_STALE', 'PRICE_STALE', 'HISTORY', 'ANALYSIS_PENDING'}


def publish_context(value, *, preview=False):
    folder = runtime_root() / "signals"
    if preview:folder = folder / 'preview'
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
        if analysis.get('contract')!=contract:
            return waiting
        if analysis.get('error'):
            return {**waiting, 'reason':'ANALYSIS_ERROR'}
        if not -2<=now-float(analysis['observed_at'])<=max_age:
            return {**waiting, 'reason':'ANALYSIS_STALE'}
        if not -2<=now-float(analysis['quote_at'])<=max_age:
            return {**waiting, 'reason':'PRICE_STALE'}
        p2=analysis.get('p2',{})
        if p2.get('badge')=='OFF':return {'state':'OFF'}
        if not p2.get('indicators'):
            reason=('HISTORY' if p2.get('status')=='THIẾU LỊCH SỬ 1D'
                    else 'PRICE_STALE' if p2.get('price_fresh') is False else 'ANALYSIS_PENDING')
            return {**waiting, 'reason':reason}
        if not p2.get('price_fresh'):return {**waiting, 'reason':'PRICE_STALE'}
        if not p2.get('buy_alert'):return {'state':'WAIT'}
        price=float(analysis['quote_price'])
        if not isfinite(price) or price<=0:return waiting
        return {'state':'READY','price':price,
            'observed_at':min(float(analysis['observed_at']),float(analysis['quote_at']))}
    except (ValueError,TypeError,KeyError):
        return waiting


def context(snapshot, *, max_age=10, now=None, preview=False):
    now = time.time() if now is None else now
    quote = snapshot.quotes.get(snapshot.contract)
    from .session_preview import closing_quote
    closed = bool(quote and closing_quote(snapshot.contract, quote, now=now))
    if not quote or quote.symbol!=snapshot.contract or not (quote.fresh(max_age, now) or closed):
        return {"state":"WAIT","entry":{"state":"WAIT_SOURCE"}}
    rows = completed_bars(snapshot.bars)
    p1 = p1_snapshot(rows, quote.last)
    text = {"ABOVE": "TRÊN MA200 1D", "BELOW": "DƯỚI MA200 1D", "EQUAL": "TẠI MA200 1D"}.get(p1['state'], "CHỜ MA200 1D")
    entry={'state':'WAIT_SOURCE'}
    paths = [runtime_root() / 'signals' / 'market-context.json']
    if preview:paths.insert(0,runtime_root() / 'signals' / 'preview' / 'market-context.json')
    shared = {}
    for path in paths:
        try:
            candidate=json.loads(path.read_text(encoding='utf-8'))
            if (isinstance(candidate,dict) and candidate.get('contract')==snapshot.contract
                    and -2 <= now - float(candidate.get('observed_at',0)) <= max_age):
                shared=candidate
                break
        except (OSError,ValueError,TypeError):pass
    if closed:
        reference=shared.get('reference') or {}
        calculated=bool(isinstance(reference,dict) and reference.get('contract')==snapshot.contract
            and reference.get('ready') is True and reference.get('quote_at')==quote.at and reference.get('price')==quote.last)
        if not calculated:
            # Closing reference has no admission/crossover state or trading authority.
            from .session_preview import closing_analysis
            from .signal_config import read_signal_settings
            try:
                local=closing_analysis({'contract':snapshot.contract,'quotes':{snapshot.contract:asdict(quote)},
                    'bars':snapshot.bars},read_signal_settings(),now=now)
                calculated=bool(local and local.get('ready'))
            except (ValueError,TypeError,KeyError,OSError):pass
        return {'mode':'CLOSE','state':p1['state'],'ma':p1.get('ma'),'observed_at':now,'quote_at':quote.at,
                'entry':{'state':'CLOSED','calculated':calculated}}
    try:
        if not isinstance(shared,dict):shared={}
        if shared.get('contract') == snapshot.contract and -2 <= now - shared['observed_at'] <= max_age:
            candidate=shared.get('entry',{})
            if not isinstance(candidate,dict):candidate={}
            if candidate.get('state') in {'WAIT','OFF'}:entry={'state':candidate['state']}
            elif candidate.get('state')=='WAIT_SOURCE' and candidate.get('reason') in WAIT_REASONS:
                entry={'state':'WAIT_SOURCE','reason':candidate['reason']}
            elif candidate.get('state')=='READY':
                value=float(candidate['price'])
                if isfinite(value) and value>0 and -2<=now-float(candidate['observed_at'])<=max_age:
                    entry={'state':'READY','price':value,'observed_at':candidate['observed_at']}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return {"text":text,"state":p1['state'],"ma":p1.get('ma'),"observed_at":quote.at,'entry':entry}
