# -*- coding: utf-8 -*-
from __future__ import annotations

import config


MONEY_DISPLAY_UNITS = {
    "VND": {"label": "VND đầy đủ", "short": "VND", "scale": 1.0, "digits": 0},
    "K_VND": {"label": "nghìn VND", "short": "nghìn VND", "scale": 1000.0, "digits": 0},
    "M_VND": {"label": "triệu VND", "short": "triệu VND", "scale": 1000000.0, "digits": 2},
}

MONEY_DISPLAY_LABELS = [item["label"] for item in MONEY_DISPLAY_UNITS.values()]
_LABEL_TO_UNIT = {item["label"]: key for key, item in MONEY_DISPLAY_UNITS.items()}
_LABEL_TO_UNIT.update({"VND": "VND", "nghìn VND": "K_VND", "triệu VND": "M_VND"})


def normalize_money_unit(value: str | None = None) -> str:
    raw = str(value or getattr(config, "MONEY_DISPLAY_UNIT", "K_VND") or "K_VND").strip()
    unit = _LABEL_TO_UNIT.get(raw, raw)
    return unit if unit in MONEY_DISPLAY_UNITS else "K_VND"


def money_unit_label(unit: str | None = None) -> str:
    return MONEY_DISPLAY_UNITS[normalize_money_unit(unit)]["short"]


def money_unit_note(unit: str | None = None) -> str:
    return f"Đơn vị tiền: {money_unit_label(unit)}"


def format_vnd(value: float | int | None, signed: bool = False, suffix: bool = False) -> str:
    unit = normalize_money_unit()
    meta = MONEY_DISPLAY_UNITS[unit]
    try:
        amount = float(value or 0.0) / float(meta["scale"])
    except Exception:
        amount = 0.0
    digits = int(meta["digits"])
    sign = ""
    if signed:
        sign = "+" if amount > 0 else "-" if amount < 0 else ""
    amount = abs(amount) if signed else amount
    text = f"{amount:,.{digits}f}"
    if digits == 0:
        text = text.split(".", 1)[0]
    if suffix:
        text = f"{text} {meta['short']}"
    return f"{sign}{text}"


def format_money_k(value: float | int | None, max_decimals: int = 2) -> str:
    """Chia theo đơn vị hiển thị (mặc định nghìn VND, ÷1000) nhưng GIỮ số lẻ cho
    giá trị nhỏ (vd phí 1500 -> 1.5, spread 111300 -> 111.3). Bỏ số 0 lẻ thừa."""
    unit = normalize_money_unit()
    meta = MONEY_DISPLAY_UNITS[unit]
    try:
        amount = float(value or 0.0) / float(meta["scale"])
    except Exception:
        amount = 0.0
    text = f"{amount:,.{max_decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-", "-0"):
        text = "0"
    return text


def parse_money_unit_label(label: str | None) -> str:
    return normalize_money_unit(label)


# [UNIT VND] Trong config/logic, unit tiền lưu là "USD" (di sản MT5) nhưng nghĩa thật là
# VND (đồng nguyên con). UI hiển thị "VND" cho khỏi nhầm; khi LƯU phải map ngược về "USD"
# để không đụng các so sánh == "USD" trong trade_manager và settings cũ đã lưu.
def unit_to_display(value: str | None) -> str:
    v = str(value or "USD").strip()
    return "VND" if v.upper() == "USD" else v


def unit_from_display(value: str | None) -> str:
    v = str(value or "VND").strip()
    return "USD" if v.upper() == "VND" else v


# [MONEY INPUT /1000] Ô nhập tiền trên UI tính bằng NGHÌN VND (khớp dashboard);
# file settings vẫn lưu đồng nguyên con. Chỉ scale khi unit là tiền (USD/VND);
# unit khác (R, %Equity, PERCENT, POINT, ATR) giữ nguyên số.
MONEY_INPUT_SCALE = 1000.0
_MONEY_UNITS = ("USD", "VND")


def _is_money_unit(unit: str | None) -> bool:
    return str(unit or "").strip().upper() in _MONEY_UNITS


def money_input_to_display(value, unit: str | None) -> str:
    """Giá trị lưu (đồng) -> chuỗi hiện trên ô nhập (nghìn VND nếu unit là tiền)."""
    try:
        v = float(value or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if _is_money_unit(unit):
        v = v / MONEY_INPUT_SCALE
    return f"{v:g}"


def money_input_from_display(value, unit: str | None) -> float:
    """Ô nhập (nghìn VND nếu unit là tiền) -> giá trị lưu (đồng)."""
    try:
        v = float(value or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if _is_money_unit(unit):
        v = v * MONEY_INPUT_SCALE
    return v
