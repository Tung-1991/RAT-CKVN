from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from math import isfinite
import time
from typing import Literal
import uuid
from zoneinfo import ZoneInfo

Side = Literal["LONG", "SHORT"]
Mode = Literal["PAPER", "REAL"]
FINAL = frozenset({"FILLED", "CANCELLED", "REJECTED", "EXPIRED", "FAILED"})


def number(value, default=0.0):
    try:
        result = float(value)
        return result if isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def market_time(value):
    result = number(value)
    if result:
        return result / 1000 if result > 1e12 else result
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))).timestamp()
    except (ValueError, OverflowError, OSError):
        return 0.0


def quantity(value):
    result = number(value, -1)
    if result < 0 or result != int(result):
        raise ValueError("Khối lượng phải là số nguyên HĐ, không âm.")
    return int(result)


def direction(side: Side):
    if side not in ("LONG", "SHORT"):
        raise ValueError("Chiều vị thế phải là LONG hoặc SHORT.")
    return 1 if side == "LONG" else -1


def is_vn30(symbol):
    return str(symbol).upper().startswith(("VN30F", "41I1"))


def load_record(cls, raw):
    allowed = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in raw.items() if k in allowed})


@dataclass
class ExitSettings:
    # No stock preset is applied to a live derivatives account.
    sl_enabled: bool = False
    sl_distance: float = 0.0
    tp_enabled: bool = False
    tp_distance: float = 0.0
    distance_unit: str = "POINTS"
    arm_enabled: bool = False
    arm_gain: float = 0.0
    trail_gap: float = 0.0
    arm_policy: str = "AUTO"
    arm_close_pct: float = 100.0
    arm_basis: str = "REMAINING"
    arm_repeat: bool = False
    arm_repeat_below_arm: bool = False
    repeat_gap: float = 0.0
    dynamic_enabled: bool = False
    dynamic_policy: str = "ALERT"
    dynamic_close_pct: float = 100.0
    dynamic_basis: str = "REMAINING"
    dynamic_repeat: bool = False
    atr_start_enabled: bool = True
    atr_start_multiplier: float = 0.55
    atr_trail_enabled: bool = True
    atr_trail_multiplier: float = 0.8
    retention_enabled: bool = True
    retention_pct: float = 72.0
    retention_until_enabled: bool = True
    retention_until: float = 0.0

    def validate(self):
        if self.distance_unit not in {"POINTS", "PERCENT"}:
            raise ValueError("Đơn vị E/M không hợp lệ.")
        for name in ("sl_distance", "tp_distance", "arm_gain", "trail_gap", "repeat_gap",
                     "atr_start_multiplier", "atr_trail_multiplier", "retention_until"):
            value = getattr(self, name)
            if not isfinite(float(value)) or value < 0:
                raise ValueError(f"{name}: cần một số không âm.")
        for enabled, name in ((self.sl_enabled, "sl_distance"), (self.tp_enabled, "tp_distance"),
                              (self.arm_enabled, "arm_gain"), (self.arm_enabled, "trail_gap")):
            if enabled and getattr(self, name) <= 0:
                raise ValueError(f"{name}: phải lớn hơn 0 khi bật.")
        for stage in ("arm", "dynamic"):
            if getattr(self, stage + "_policy") not in {"AUTO", "ALERT"}:
                raise ValueError("Chế độ chỉ có AUTO hoặc ALERT.")
            if not 0 < getattr(self, stage + "_close_pct") <= 100:
                raise ValueError("Tỷ lệ đóng phải trong (0, 100].")
            if getattr(self, stage + "_basis") not in {"ORIGINAL", "REMAINING"}:
                raise ValueError("Cơ sở khối lượng không hợp lệ.")
            if getattr(self, stage + "_repeat") and self.repeat_gap <= 0:
                raise ValueError("Bật LẶP cần khoảng lặp lớn hơn 0.")
        if not 0 <= self.retention_pct <= 100:
            raise ValueError("Tỷ lệ giữ lãi phải trong [0, 100].")
        if self.dynamic_enabled and not (self.atr_trail_enabled or self.retention_enabled):
            raise ValueError("DYNAMIC cần ATR trail hoặc giữ lãi.")
        return self

    def points(self, value, entry):
        return value * entry / 100 if self.distance_unit == "PERCENT" else value


@dataclass
class Settings:
    mode: str = "PAPER"
    account_no: str = ""
    loan_package_id: str = ""
    alias: str = "VN30F1M"
    capital_limit: float = 0.0
    max_contracts: int = 0
    risk_limit: float = 0.0
    risk_nav_pct: float = 0.0
    paper_balance: float = 100_000_000.0
    paper_margin_rate: float = 0.2
    estimated_fee_per_contract: float = 0.0
    poll_seconds: float = 2.0
    max_quote_age: float = 10.0
    exit: dict = field(default_factory=lambda: asdict(ExitSettings()))
    telegram_enabled: bool = False
    telegram_chat: str = ""
    signals: dict = field(default_factory=dict)
    market_alerts: dict = field(default_factory=dict)
    entry_notifications: bool = False

    def validate(self):
        if self.mode not in {"REAL", "PAPER"} or self.alias != "VN30F1M":
            raise ValueError("Chỉ hỗ trợ PAPER/REAL và VN30F1M.")
        if not isinstance(self.entry_notifications, bool):
            raise ValueError("Thông báo vào lệnh cần công tắc bật/tắt.")
        if self.account_no and not self.account_no.isdigit():
            raise ValueError("Số tài khoản DNSE chỉ chứa chữ số.")
        for name in ("capital_limit", "risk_limit", "risk_nav_pct", "estimated_fee_per_contract"):
            if not isfinite(float(getattr(self, name))) or getattr(self, name) < 0:
                raise ValueError(f"{name}: cần một số không âm.")
        self.max_contracts = quantity(self.max_contracts)
        if not 0 < self.paper_margin_rate < 1 or not isfinite(self.paper_balance) or self.paper_balance <= 0:
            raise ValueError("Vốn/ký quỹ PAPER không hợp lệ.")
        if not 1 <= self.poll_seconds <= 60 or not 1 <= self.max_quote_age <= 120:
            raise ValueError("Chu kỳ cập nhật không hợp lệ.")
        load_record(ExitSettings, self.exit).validate()
        from ckps.rules.signal_settings import SignalSettings
        self.signals = SignalSettings.from_dict(self.signals).to_dict()
        from ckps.rules.market_alerts import MarketAlertSettings
        self.market_alerts = MarketAlertSettings.from_dict(self.market_alerts).to_dict()
        return self


@dataclass
class Quote:
    symbol: str
    last: float
    bid: float = 0.0
    ask: float = 0.0
    at: float = field(default_factory=time.time)
    source: str = "PAPER"
    floor: float = 0.0
    ceiling: float = 0.0

    def fresh(self, age=10.0, now=None):
        elapsed = (time.time() if now is None else now) - self.at
        return is_vn30(self.symbol) and isfinite(self.last) and self.last > 0 and -2 <= elapsed <= age


@dataclass
class Position:
    id: str
    symbol: str
    side: Side
    quantity: int
    entry: float
    original_quantity: int = 0
    source: str = "EXTERNAL"
    managed: bool = False
    history_verified: bool = False
    best: float = 0.0
    worst: float = 0.0
    floor: float = 0.0
    metrics: dict = field(default_factory=dict)
    exit_overrides: dict | None = None
    opened_at: float = field(default_factory=time.time)
    closed_at: float = 0.0
    realized: float = 0.0
    fees: float = 0.0
    pnl_verified: bool = True
    note: str = ""

    @property
    def sign(self):
        return direction(self.side)

    def profit_points(self, price):
        return self.sign * (price - self.entry)

    def pnl(self, price):
        return self.profit_points(price) * self.quantity * 100_000

    @classmethod
    def create(cls, symbol, side, qty, entry, **kwargs):
        return cls(uuid.uuid4().hex, symbol, side, qty, entry,
                   original_quantity=qty, best=entry, worst=entry, **kwargs)


@dataclass
class Order:
    id: str
    symbol: str
    side: Side
    quantity: int
    action: str = "OPEN"
    source: str = "MANUAL"
    kind: str = "LO"
    price: float = 0.0
    position_id: str = ""
    status: str = "CREATED"
    broker_id: str = ""
    filled: int = 0
    avg_fill: float = 0.0
    applied: int = 0
    applied_notional: float = 0.0
    fee: float = 0.0
    applied_fee: float = 0.0
    reason: str = "MANUAL"
    trigger: float = 0.0
    message: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    exit_settings: dict | None = None
    replacement: dict | None = None
    protection_anchor: float = 0.0
    parent_position_id: str = ""
    abandon_remainder: bool = False

    @property
    def pending(self):
        return self.status not in FINAL

    @property
    def remainder(self):
        return max(0, self.quantity - self.filled)

    @property
    def exchange_side(self):
        buy = (self.side == "LONG") == (self.action == "OPEN")
        return "NB" if buy else "NS"

    @classmethod
    def create(cls, symbol, side, qty, **kwargs):
        return cls(uuid.uuid4().hex, symbol, side, quantity(qty), **kwargs)


@dataclass
class Snapshot:
    contract: str
    positions: list[dict]
    orders: list[dict]
    quotes: dict[str, Quote]
    remaining_margin: float | None
    used_margin: float | None
    margin_per_contract: float | None
    qmax_long: int | None
    qmax_short: int | None
    nav: float | None = None
    observed_at: float = field(default_factory=time.time)
    bars: list[dict] = field(default_factory=list)
    source: str = "PAPER"
    pending_margin: float | None = None
    paper_capital: float | None = None
    total_money: float | None = None
    collateral_total: float | None = None
    margin_reference_price: float | None = None


@dataclass
class Decision:
    reason: str
    price: float
    quantity: int
    policy: str = "AUTO"
    stage: str = ""
