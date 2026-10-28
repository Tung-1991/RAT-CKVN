"""Persist market observations and emit notification events, never trades."""
from datetime import datetime
from math import isfinite

from ckps.models import is_vn30
from ckps.rules.market_alerts import MarketAlertSettings, MovementDetector
from ckps.rules.p2.market import VN_TZ, market_phase


class MarketAlerts:
    def __init__(self, store):
        self.store = store
        self.movement = MovementDetector()

    def observe(self, symbol, quote, analysis, values, *, now, max_age):
        settings = MarketAlertSettings.from_dict(values)
        at,price = float(quote.get('at',0)),float(quote.get('last',0))
        result = {'events':[]}
        if not is_vn30(symbol) or not all(map(isfinite,(at,price))) or price<=0 or not -2<=now-at<=max_age:
            return result
        clock = datetime.fromtimestamp(at,VN_TZ)
        if market_phase(clock,exchange='VN30')[0] not in {'ATO','OPEN','ATC'}:
            return result
        if (analysis.get('contract')==symbol and -2<=now-float(analysis.get('observed_at',0))<=max_age
                and analysis.get('market_phase') in {'HOLIDAY','WEEKEND','CLOSED','LUNCH'}):
            return result
        anchor = self.store.get('market','anchor:'+symbol,{})
        movement = self.movement.observe(symbol,price,at,settings,session_anchor=anchor,max_gap=max_age)
        if self.movement.anchor!=anchor:
            self.store.put('market','anchor:'+symbol,self.movement.anchor)
        if movement:
            last = self.store.get('market','movement:'+symbol,{})
            if now-float(last.get('at',0))>=settings.cooldown_minutes*60:
                label = 'NHỊP NHANH' if movement['movement_type']=='FAST' else 'NHỊP TỪ MỐC THEO DÕI PHIÊN'
                reason = f"{label} · {movement['change_points']:+g} điểm / {movement['seconds']:g}s · {movement['reference_price']:g} → {price:g}"
                result['events'].append(self._record(symbol,'VOLATILITY','BIẾN ĐỘNG',reason,at))
                self.store.put('market','movement:'+symbol,movement)
        p1 = analysis.get('p1',{}) if analysis.get('contract')==symbol else {}
        observed = float(analysis.get('observed_at',0))
        if p1.get('state') in {'ABOVE','BELOW'} and p1.get('ma') and -2<=now-observed<=max_age:
            previous = self.store.get('market','trend:'+symbol,{})
            state = p1['state']
            result['trend'] = state
            if state!=previous.get('state') and observed>float(previous.get('at',0)):
                label = 'UPTREND · GIÁ TRÊN MA200' if state=='ABOVE' else 'DOWNTREND · GIÁ DƯỚI MA200'
                reason = f"{label} · Giá {p1['price']:g} · MA200 {p1['ma']:.2f} · 1D"
                event = self._record(symbol,'TREND','XU HƯỚNG',reason,observed)
                event['notify'] = observed-float(previous.get('sent_at',0))>=60
                result['events'].append(event)
                self.store.put('market','trend:'+symbol,{'state':state,'at':observed,
                    'sent_at':observed if event['notify'] else previous.get('sent_at',0)})
        return result

    def _record(self, symbol, channel, kind, reason, at):
        key = f'{symbol}:{channel}:{at}'
        self.store.put('signal_history',key,{'id':key,'symbol':symbol,'kind':kind,'reason':reason,'at':at})
        self.store.event('ALERT',symbol+' · '+reason)
        return {'id':key,'channel':channel,'reason':reason,'at':at}
