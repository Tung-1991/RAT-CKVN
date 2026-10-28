"""VN30 movement evidence only; deliberately no order or protection API."""
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite

from ckps.models import is_vn30
from .p2.market import VN_TZ


@dataclass
class MarketAlertSettings:
    trend_enabled: bool = False
    movement_enabled: bool = False
    fast_points: float = 5.0
    window_seconds: float = 60.0
    confirmations: int = 2
    session_enabled: bool = True
    session_points: float = 20.0
    cooldown_minutes: float = 30.0

    @classmethod
    def from_dict(cls, values=None):
        result = cls(**{k:v for k,v in (values or {}).items() if k in cls.__dataclass_fields__})
        for key in ('trend_enabled','movement_enabled','session_enabled'):
            if not isinstance(getattr(result,key),bool):
                raise ValueError('ALERT thị trường cần công tắc bật/tắt.')
        for key in ('fast_points','window_seconds','session_points','cooldown_minutes','confirmations'):
            raw = getattr(result,key)
            if isinstance(raw,bool):
                raise ValueError('Ngưỡng biến động cần là số hợp lệ.')
            value = float(raw)
            if not isfinite(value) or value<0:
                raise ValueError('Ngưỡng biến động cần là số hữu hạn không âm.')
            setattr(result,key,value)
        if result.fast_points<=0 or result.session_points<=0 or not 5<=result.window_seconds<=3600:
            raise ValueError('Ngưỡng điểm phải lớn hơn 0; cửa sổ từ 5 đến 3600 giây.')
        if result.confirmations!=int(result.confirmations) or not 1<=result.confirmations<=100:
            raise ValueError('Số xác nhận biến động phải là số nguyên từ 1 đến 100.')
        result.confirmations = int(result.confirmations)
        return result

    def to_dict(self):
        return asdict(self)


class MovementDetector:
    """Retain RAT's short-window and observed-session moves for derivatives."""
    def __init__(self):
        self.symbol = None
        self.day = None
        self.history = deque(maxlen=4096)
        self.anchor = None
        self.count = 0
        self.direction = 0
        self.last_at = 0.0
        self.signature = None

    def observe(self, symbol, price, at, settings, *, session_anchor=None, max_gap=10):
        if not is_vn30(symbol) or not isfinite(price) or price<=0 or not isfinite(at):
            return None
        day = datetime.fromtimestamp(at,VN_TZ).date().isoformat()
        signature = (settings.fast_points,settings.window_seconds,settings.confirmations,
                     settings.session_enabled,settings.session_points)
        if (symbol,day,signature)!=(self.symbol,self.day,self.signature):
            self.history.clear()
            self.count,self.direction,self.last_at = 0,0,0
            self.symbol,self.day,self.signature = symbol,day,signature
            self.anchor = session_anchor if session_anchor and session_anchor.get('day')==day else {'day':day,'at':at,'price':price}
        if at<=self.last_at:
            return None
        if self.last_at and at-self.last_at>max_gap:
            self.history.clear()
            self.count,self.direction = 0,0
        self.last_at = at
        self.history.append((at,price))
        while self.history and self.history[0][0]<at-settings.window_seconds:
            self.history.popleft()
        reference_at,reference_price = self.history[0]
        change = price-reference_price
        direction = 1 if change>0 else -1
        if len(self.history)>1 and abs(change)>=settings.fast_points:
            self.count = self.count+1 if self.direction==direction else 1
            self.direction = direction
            if self.count>=settings.confirmations:
                self.count,self.direction = 0,0
                self.history.clear()
                return self._event('FAST',reference_at,reference_price,at,price)
        else:
            self.count,self.direction = 0,0
        if settings.session_enabled and abs(price-self.anchor['price'])>=settings.session_points:
            event = self._event('SESSION',self.anchor['at'],self.anchor['price'],at,price)
            self.anchor = {'day':day,'at':at,'price':price}
            return event
        return None

    @staticmethod
    def _event(kind, reference_at, reference_price, at, price):
        return {'movement_type':kind,'reference_at':reference_at,'reference_price':reference_price,
                'at':at,'price':price,'change_points':price-reference_price,'seconds':at-reference_at}
