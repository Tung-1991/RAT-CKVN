# -*- coding: utf-8 -*-
"""Gom danh mục cổ phiếu cơ sở (CKCS) để hiển thị — Phase 1 read-only.

Tách phần TÍNH TOÁN THUẦN (không Tkinter, không network) khỏi UI để dễ test,
theo đúng pattern của `settlement.py` / `stock_rules.py`.

Nguồn dữ liệu:
- Danh mục: list `BrokerPosition` (hoặc list dict raw) từ `DNSEConnector.get_positions()`.
  Mỗi mã CKCS có (trong `position.raw`): openQuantity (KL sở hữu),
  tradeQuantity (KL bán được — đã về T+2), costPrice (giá vốn TB), marketPrice,
  status (= 'ODD_LOT' nếu là lô lẻ).
- Tiền mặt: khối `stock` trong response `GET /accounts/{acc}/balances`
  (availableCash / totalCash).

Phái sinh (VN30F / CKPS) bị bỏ qua — chỉ gom CKCS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from core import settlement, stock_rules

ODD_LOT_NOTE = "Lô lẻ — bán qua app DNSE"


@dataclass
class HoldingRow:
    """Một dòng danh mục cho 1 mã cổ phiếu cơ sở."""

    symbol: str
    quantity: float          # KL sở hữu (openQuantity)
    sellable: float          # KL bán được (tradeQuantity / đã về T+2)
    pending: float           # KL còn chờ về (= quantity - sellable, >= 0)
    avg_cost: float          # giá vốn TB (costPrice)
    market_price: float      # giá thị trường hiện tại (marketPrice)
    market_value: float      # quantity * market_price
    cost_value: float        # quantity * avg_cost
    pnl: float               # market_value - cost_value
    pnl_pct: float           # pnl / cost_value * 100
    is_odd_lot: bool         # status == ODD_LOT hoặc KL không chia hết lô
    odd_quantity: float = 0.0  # phần KL lẻ "kẹt" (= KL % lô) — bán qua app DNSE
    note: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


def _raw_of(position: Any) -> Dict[str, Any]:
    """Lấy dict raw từ BrokerPosition hoặc trả chính nó nếu đã là dict."""
    if isinstance(position, dict):
        return position
    raw = getattr(position, "raw", None)
    return raw if isinstance(raw, dict) else {}


def _get(position: Any, attr: str, *raw_keys: str, default: Any = None) -> Any:
    """Ưu tiên thuộc tính của BrokerPosition, fallback các key trong raw."""
    val = getattr(position, attr, None)
    if val is not None:
        return val
    raw = _raw_of(position)
    for key in raw_keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _symbol_of(position: Any) -> str:
    return str(_get(position, "symbol", "symbol", "symbolCode", "code", default="") or "").upper()


def _is_odd_lot(quantity: float, status: Any) -> bool:
    if str(status or "").upper() == "ODD_LOT":
        return True
    lot = stock_rules._round_lot()
    if lot <= 0:
        return False
    return int(round(quantity)) % lot != 0


def _odd_quantity(quantity: float, status: Any) -> float:
    """Phần KL lẻ 'kẹt' (không tạo nổi 1 lô chẵn). VD lô 100: 150->50, 30->30, 200->0.

    Nếu DNSE đánh status=ODD_LOT mà KL vẫn chia hết lô thì coi cả KL là lẻ.
    """
    lot = stock_rules._round_lot()
    if lot <= 0:
        return 0.0
    remainder = float(int(round(quantity)) % lot)
    if remainder == 0.0 and str(status or "").upper() == "ODD_LOT":
        return float(quantity)
    return remainder


def _odd_note(odd_quantity: float) -> str:
    q = int(round(odd_quantity or 0.0))
    if q > 0:
        return f"Lô lẻ {q:,} cp — bán qua app DNSE"
    return ODD_LOT_NOTE


def build_holding(position: Any) -> Optional[HoldingRow]:
    """Dựng 1 HoldingRow từ 1 position CKCS; trả None nếu không phải CKCS / KL<=0."""
    symbol = _symbol_of(position)
    if not settlement.is_cash_stock(symbol):
        return None

    raw = _raw_of(position)
    quantity = _to_float(_get(position, "volume", "openQuantity", "quantity", "netQuantity"))
    if quantity <= 0:
        return None

    # KL bán được: ưu tiên tradeQuantity của DNSE; thiếu -> coi như đã về hết.
    sellable_raw = raw.get("tradeQuantity")
    sellable = _to_float(sellable_raw, quantity) if sellable_raw is not None else quantity
    sellable = max(0.0, min(sellable, quantity))
    pending = max(0.0, quantity - sellable)

    avg_cost = _to_float(_get(position, "price_open", "costPrice", "avgPrice", "averagePrice"))
    market_price = _to_float(_get(position, "price_current", "marketPrice", "currentPrice", "lastPrice"), avg_cost)

    market_value = quantity * market_price
    cost_value = quantity * avg_cost
    pnl = market_value - cost_value
    pnl_pct = (pnl / cost_value * 100.0) if cost_value else 0.0

    odd = _is_odd_lot(quantity, raw.get("status"))
    odd_qty = _odd_quantity(quantity, raw.get("status")) if odd else 0.0
    return HoldingRow(
        symbol=symbol,
        quantity=quantity,
        sellable=sellable,
        pending=pending,
        avg_cost=avg_cost,
        market_price=market_price,
        market_value=market_value,
        cost_value=cost_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
        is_odd_lot=odd,
        odd_quantity=odd_qty,
        note=_odd_note(odd_qty) if odd else "",
        raw=raw,
    )


def _merge_rows(rows: List[HoldingRow]) -> HoldingRow:
    """Gộp nhiều lô CÙNG 1 mã thành 1 dòng: cộng KL, giá vốn = bình quân gia quyền."""
    symbol = rows[0].symbol
    quantity = sum(r.quantity for r in rows)
    sellable = sum(r.sellable for r in rows)
    pending = sum(r.pending for r in rows)
    cost_value = sum(r.cost_value for r in rows)
    market_value = sum(r.market_value for r in rows)
    avg_cost = (cost_value / quantity) if quantity else 0.0
    market_price = (market_value / quantity) if quantity else 0.0
    pnl = market_value - cost_value
    pnl_pct = (pnl / cost_value * 100.0) if cost_value else 0.0
    # Lô lẻ nếu bất kỳ lô nào là ODD_LOT, hoặc TỔNG KL không chia hết lô.
    odd = any(r.is_odd_lot for r in rows) or _is_odd_lot(quantity, None)
    odd_qty = _odd_quantity(quantity, "ODD_LOT" if odd else None) if odd else 0.0
    return HoldingRow(
        symbol=symbol,
        quantity=quantity,
        sellable=sellable,
        pending=pending,
        avg_cost=avg_cost,
        market_price=market_price,
        market_value=market_value,
        cost_value=cost_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
        is_odd_lot=odd,
        odd_quantity=odd_qty,
        note=_odd_note(odd_qty) if odd else "",
        raw={"lots": [r.raw for r in rows]},
    )


def build_holdings(positions: Iterable[Any]) -> List[HoldingRow]:
    """Lọc CKCS, GOM theo mã (nhiều lô cùng mã -> 1 dòng), sắp theo giá trị giảm dần."""
    by_symbol: Dict[str, List[HoldingRow]] = {}
    for pos in positions or []:
        row = build_holding(pos)
        if row is None:
            continue
        by_symbol.setdefault(row.symbol, []).append(row)
    merged = [
        lots[0] if len(lots) == 1 else _merge_rows(lots)
        for lots in by_symbol.values()
    ]
    merged.sort(key=lambda r: r.market_value, reverse=True)
    return merged


def total_stock_value(holdings: Iterable[HoldingRow]) -> float:
    return sum(h.market_value for h in holdings or [])


def odd_lot_value(holdings: Iterable[HoldingRow]) -> float:
    """Tổng GIÁ TRỊ phần KL lô lẻ 'kẹt' (= odd_quantity * giá TT) — cần ra app DNSE bán."""
    return sum((h.odd_quantity or 0.0) * (h.market_price or 0.0) for h in holdings or [])


def odd_lot_count(holdings: Iterable[HoldingRow]) -> int:
    """Số mã đang có lô lẻ."""
    return sum(1 for h in holdings or [] if (h.odd_quantity or 0.0) > 0)


def extract_stock_cash(account_info: Any) -> float:
    """Bóc tiền mặt phần cổ phiếu từ get_account_info()/balances.

    Chấp nhận: dict get_account_info (có ['raw']['stock']), dict balances thô
    (có key 'stock'), hoặc trực tiếp khối 'stock'. Ưu tiên availableCash, fallback totalCash.
    """
    if not isinstance(account_info, dict):
        return 0.0
    stock = None
    raw = account_info.get("raw")
    if isinstance(raw, dict) and isinstance(raw.get("stock"), dict):
        stock = raw["stock"]
    elif isinstance(account_info.get("stock"), dict):
        stock = account_info["stock"]
    elif "availableCash" in account_info or "totalCash" in account_info:
        stock = account_info
    if isinstance(stock, dict):
        cash = stock.get("availableCash")
        if cash is None:
            cash = stock.get("totalCash")
        if cash is not None:
            return _to_float(cash, 0.0)
    # Fallback: get_account_info đã chuẩn hoá (real) hoặc PAPER trả dict phẳng.
    flat = account_info.get("cash_available")
    if not flat:
        flat = account_info.get("balance")
    return _to_float(flat, 0.0)


def split_assets(stock_cash: float, stock_value: float) -> Dict[str, float]:
    """Tách tài sản: {cash, stock_value, total} với total = cash + stock_value."""
    cash = _to_float(stock_cash, 0.0)
    value = _to_float(stock_value, 0.0)
    return {"cash": cash, "stock_value": value, "total": cash + value}


def portfolio_summary(positions: Iterable[Any], account_info: Any) -> Dict[str, Any]:
    """Gói cho UI: danh mục + tách tài sản trong 1 lần gọi."""
    holdings = build_holdings(positions)
    stock_value = total_stock_value(holdings)
    stock_cash = extract_stock_cash(account_info)
    assets = split_assets(stock_cash, stock_value)
    # Tổng riêng phần lô lẻ (đã nằm trong stock_value, tách ra để hiển thị).
    assets["odd_lot_value"] = odd_lot_value(holdings)
    assets["odd_lot_count"] = odd_lot_count(holdings)
    return {"holdings": holdings, "assets": assets}
