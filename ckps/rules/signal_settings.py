"""P1/P2 configuration. Signal analysis has no execution permissions."""
from dataclasses import asdict, dataclass
from math import isfinite


@dataclass
class SignalSettings:
    enabled: bool = True
    buy_alert_enabled: bool = False
    sell_alert_enabled: bool = False
    signal_mode: str = "REALTIME"
    realtime_indicator_interval: str = "TICK"
    buy_ema_fast: int = 3
    buy_ema_slow: int = 6
    sell_ema_fast: int = 3
    sell_ema_slow: int = 6
    rsi_period: int = 14
    buy_signal_use_ema: bool = True
    buy_signal_use_rsi: bool = True
    sell_signal_use_ema: bool = True
    sell_signal_use_rsi: bool = False
    sell_signal_require_ema_cross: bool = False
    buy_signal_require_ema_cross: bool = True
    buy_ema_cross_mode: str = "VA"
    buy_ema_cross_sessions: int = 3
    buy_ema_va_lookback_enabled: bool = False
    buy_confirmation_enabled: bool = False
    buy_confirmation_minutes: int = 5
    buy_confirmation_require_ema: bool = True
    buy_confirmation_require_rsi: bool = True
    buy_window_enabled: bool = False
    buy_window_start: str = "14:00"
    buy_volume_enabled: bool = False
    buy_volume_average_sessions: int = 20
    buy_volume_min_ratio: float = 1.0
    whipsaw_enabled: bool = False
    whipsaw_n: int = 3
    whipsaw_x: int = 7

    @classmethod
    def from_dict(cls, values=None):
        return cls(**{k: v for k, v in (values or {}).items() if k in cls.__dataclass_fields__}).validate()

    def validate(self):
        for key in ("buy_alert_enabled", "sell_alert_enabled"):
            if not isinstance(getattr(self, key), bool):
                raise ValueError(f"{key}: cần công tắc bật/tắt.")
        for key in ("buy_ema_fast", "buy_ema_slow", "sell_ema_fast", "sell_ema_slow", "rsi_period",
                    "buy_ema_cross_sessions", "buy_confirmation_minutes", "buy_volume_average_sessions",
                    "whipsaw_n", "whipsaw_x"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value != int(value) or not 1 <= value <= 1000:
                raise ValueError(f"{key}: cần số nguyên từ 1 đến 1000.")
            setattr(self, key, int(value))
        if self.buy_ema_fast >= self.buy_ema_slow or self.sell_ema_fast >= self.sell_ema_slow:
            raise ValueError("EMA nhanh phải nhỏ hơn EMA chậm.")
        if self.signal_mode not in {"REALTIME", "CLOSED"} or self.realtime_indicator_interval not in {"TICK", "1M", "2M", "5M"}:
            raise ValueError("Chế độ nến / nhịp EMA không hợp lệ.")
        if self.buy_ema_cross_mode not in {"VA", "SESSIONS"}:
            raise ValueError("Giao cắt chỉ có VA hoặc X PHIÊN.")
        if not isfinite(self.buy_volume_min_ratio) or self.buy_volume_min_ratio <= 0:
            raise ValueError("Tỷ lệ volume phải lớn hơn 0.")
        if self.buy_confirmation_enabled and (not 1 <= self.buy_confirmation_minutes <= 120 or not (self.buy_confirmation_require_ema or self.buy_confirmation_require_rsi)):
            raise ValueError("Xác nhận cần EMA/RSI và từ 1 đến 120 phút.")
        from .p2.market import validate_buy_window
        validate_buy_window(self.buy_window_start, "14:45")
        return self

    def to_dict(self):
        return asdict(self)
