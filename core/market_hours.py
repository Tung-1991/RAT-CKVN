# -*- coding: utf-8 -*-
# FILE: core/market_hours.py
# V7: DNSE HoSE/Phái sinh — có ATO/ATC, tách phái sinh vs cổ phiếu

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import config


def _market_now() -> datetime:
    offset_hours = float(getattr(config, "MARKET_HOURS_UTC_OFFSET", 7))
    # Preserve the historical naive UTC+offset contract while avoiding the
    # deprecated datetime.utcnow() API on Python 3.13+.
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=offset_hours)


def market_now_hm() -> str:
    """Giờ thị trường hiện tại dạng HH:MM (để hiển thị cạnh đèn phiên)."""
    return _market_now().strftime("%H:%M")


def resolve_order_kind(symbol: str, mode: str = "NORMAL") -> Optional[str]:
    """Chọn orderType theo chế độ + phiên.

    mode NORMAL -> None (để connector tự dùng LO/MOK).
    mode AUTO   -> 'ATO'/'ATC' nếu đang trong phiên khớp định kỳ, ngược lại None.
    """
    if str(mode or "").upper() != "AUTO":
        return None
    phase, _ = market_session_phase(symbol)
    return phase if phase in ("ATO", "ATC") else None


def is_weekday_only_symbol(symbol: str) -> bool:
    """VN30F (phái sinh) chỉ giao dịch ngày trong tuần."""
    explicit = set(getattr(config, "WEEKDAY_ONLY_SYMBOLS", []))
    if symbol in explicit:
        return True
    if str(symbol).upper().startswith("VN30F"):
        return True
    return False


def _is_derivative(symbol: str) -> bool:
    return is_weekday_only_symbol(symbol)


def market_session_phase(symbol: str) -> tuple[str, str]:
    """Trả về (phase, label) cho phiên giao dịch HoSE.

    phase: WEEKEND / CLOSED / ATO / OPEN / LUNCH / ATC.
    Giờ (UTC+7):
      Phái sinh: ATO 8:45-9:00 | liên tục 9:00-11:30, 13:00-14:30 | ATC 14:30-14:45
      Cổ phiếu : ATO 9:00-9:15 | liên tục 9:15-11:30, 13:00-14:30 | ATC 14:30-14:45
    """
    now = _market_now()
    if now.weekday() >= 5:  # Thứ 7, CN
        return "WEEKEND", "NGHỈ T7/CN"

    mins = now.hour * 60 + now.minute
    deriv = _is_derivative(symbol)

    ato_start = 525 if deriv else 540          # PS 8:45 | CP 9:00
    cont_morning_start = 540 if deriv else 555  # PS 9:00 | CP 9:15
    morning_end = 690                           # 11:30
    lunch_end = 780                             # 13:00
    afternoon_end = 870                         # 14:30
    atc_end = 885                               # 14:45

    if mins < ato_start:
        return "CLOSED", "CHƯA MỞ"
    if mins < cont_morning_start:
        return "ATO", "ATO (mở cửa)"
    if mins < morning_end:
        return "OPEN", "MỞ"
    if mins < lunch_end:
        return "LUNCH", "NGHỈ TRƯA"
    if mins < afternoon_end:
        return "OPEN", "MỞ"
    if mins < atc_end:
        return "ATC", "ATC (đóng cửa)"
    return "CLOSED", "ĐÓNG PHIÊN"


def is_symbol_trade_window_open(symbol: str) -> tuple[bool, str]:
    """Có thể đặt lệnh không (ATO/OPEN/ATC = được; nghỉ trưa/đóng/cuối tuần = không)."""
    phase, _label = market_session_phase(symbol)
    if phase in ("ATO", "OPEN", "ATC"):
        return True, "OK"
    if phase == "WEEKEND":
        return False, f"{symbol} nghỉ cuối tuần"
    if phase == "LUNCH":
        return False, f"{symbol} nghỉ trưa"
    tz = f"UTC{float(getattr(config, 'MARKET_HOURS_UTC_OFFSET', 7)):+g}"
    return False, f"{symbol} ngoài giờ giao dịch HoSE ({_market_now().strftime('%H:%M')} {tz})"
