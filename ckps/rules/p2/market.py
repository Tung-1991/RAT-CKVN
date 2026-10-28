"""VN30 futures clock; session arithmetic retained from MayinTien."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
VN_TZ = timezone(timedelta(hours=7))
def normalize_exchange(value):
    return "VN30" if str(value).upper() in {"VN30", "HNX", "DERIVATIVE"} else ""
def exchange_sessions(exchange):
    return ((525, 540, "ATO"), (540, 690, "OPEN"), (780, 870, "OPEN"), (870, 885, "ATC")) if normalize_exchange(exchange) else ()
def exchange_close_minute(exchange):
    return 885

def parse_clock_minute(value: str) -> int:
    parts = str(value).strip().split(":")
    if len(parts) != 2 or any(len(part) != 2 or not part.isdigit() for part in parts):
        raise ValueError("Giờ mua phải có dạng HH:MM, ví dụ 14:00.")
    hour, minute = map(int, parts)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Giờ mua không hợp lệ.")
    return hour * 60 + minute


def validate_buy_window(start: str, end: str) -> tuple[int, int]:
    left, right = parse_clock_minute(start), parse_clock_minute(end)
    if not 525 <= left < right <= 885:
        raise ValueError("Khung giờ mua phải nằm trong 08:45–14:45; TỪ phải trước ĐẾN.")
    return left, right


def phase_at_minute(exchange: str, minute: int) -> str:
    for start, end, phase in exchange_sessions(exchange):
        if start <= int(minute) < end:
            return phase
    if 690 <= int(minute) < 780:
        return "LUNCH"
    return "CLOSED"


def active_trading_minutes(
    start: datetime,
    end: datetime,
    exchange: str,
    *,
    working_dates: Iterable[str] | None = None,
    holidays: Iterable[str] | None = None,
) -> float:
    """Elapsed exchange minutes, excluding lunch and closed trading days."""
    market = normalize_exchange(exchange)
    if not market or end <= start:
        return 0.0
    left = start.astimezone(VN_TZ) if start.tzinfo else start.replace(tzinfo=VN_TZ)
    right = end.astimezone(VN_TZ) if end.tzinfo else end.replace(tzinfo=VN_TZ)
    total = 0.0
    current = left.date()
    while current <= right.date():
        if is_working_day(current, working_dates, holidays):
            midnight = datetime.combine(current, datetime.min.time(), VN_TZ)
            for open_minute, close_minute, _phase in exchange_sessions(market):
                overlap_start = max(left, midnight + timedelta(minutes=open_minute))
                overlap_end = min(right, midnight + timedelta(minutes=close_minute))
                if overlap_end > overlap_start:
                    total += (overlap_end - overlap_start).total_seconds() / 60.0
        current += timedelta(days=1)
    return total


def market_now() -> datetime:
    return datetime.now(VN_TZ)


def market_phase(
    now: datetime | None = None,
    working_dates: Iterable[str] | None = None,
    holidays: Iterable[str] | None = None,
    exchange: str = "HOSE",
) -> tuple[str, str]:
    now = now.astimezone(VN_TZ) if now and now.tzinfo else (now.replace(tzinfo=VN_TZ) if now else market_now())
    if now.weekday() >= 5:
        return "WEEKEND", "NGHỈ T7/CN"
    if now.strftime("%Y-%m-%d") in {str(item)[:10] for item in holidays or []}:
        return "HOLIDAY", "NGHỈ ĐÃ THÊM"
    if working_dates is not None and now.strftime("%Y-%m-%d") not in {
        str(item)[:10] for item in working_dates
    }:
        return "HOLIDAY", "NGHỈ LỄ"
    market = normalize_exchange(exchange)
    if not market:
        return "UNKNOWN_EXCHANGE", "CHƯA XÁC ĐỊNH SÀN"
    minute = now.hour * 60 + now.minute
    if minute < 525:
        return "CLOSED", "CHƯA MỞ"
    phase = phase_at_minute(market, minute)
    if phase == "ATO":
        return "ATO", "ATO"
    if phase == "OPEN":
        return "OPEN", "MỞ"
    if phase == "LUNCH":
        return "LUNCH", "NGHỈ TRƯA"
    if phase == "ATC":
        return "ATC", "ATC"
    return "CLOSED", "ĐÓNG PHIÊN"




def is_working_day(
    value: date,
    working_dates: Iterable[str] | None = None,
    holidays: Iterable[str] | None = None,
) -> bool:
    if value.weekday() >= 5:
        return False
    if value.isoformat() in {str(item)[:10] for item in holidays or []}:
        return False
    if working_dates is None:
        return True
    known = {str(item)[:10] for item in working_dates}
    return value.isoformat() in known


def history_working_dates(working_dates, bars, now):
    """Extend a forward-only calendar with past sessions proved by daily bars."""
    if working_dates is None:
        return None
    known = {str(item)[:10] for item in working_dates}
    first = min(known) if known else now.date().isoformat()
    for row in bars:
        try:
            day = datetime.fromtimestamp(float(row["time"]), VN_TZ).date()
            if day <= now.date() and day.isoformat() < first and float(row["close"]) > 0:
                known.add(day.isoformat())
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
    return sorted(known)
