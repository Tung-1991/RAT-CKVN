from __future__ import annotations
from ckps.models import FINAL, number, quantity

class BrokerError(RuntimeError):
    pass

class UnknownOutcome(BrokerError):
    """A mutation may have reached DNSE. Never retry without reconciliation."""

class SubmissionCancelled(BrokerError):
    """The operator withdrew permission before the mutation was sent."""

def first(row, *names, default=None):
    return next((row[name] for name in names if row.get(name) is not None), default)

def rows(body, key):
    if isinstance(body, dict):
        total = body.get("total", body.get("totalElements"))
        value = body.get(key, body.get("data", body.get("content")))
        if isinstance(value, dict):
            result = rows(value, key)
        elif isinstance(value, list):
            result = value
        elif value is None and key in body:
            result = []
        else:
            raise BrokerError(f"DNSE thiếu danh sách {key}.")
        if total is not None and quantity(total) > len(result):
            raise BrokerError(f"DNSE trả {key} chưa đủ trang; tạm dừng đối soát.")
    elif isinstance(body, list):
        result = body
    else:
        raise BrokerError(f"DNSE trả {key} không hợp lệ.")
    if any(not isinstance(row, dict) for row in result):
        raise BrokerError(f"DNSE trả phần tử {key} không hợp lệ.")
    return result

def unwrap(body):
    while isinstance(body, dict) and isinstance(body.get("data"), dict):
        body = body["data"]
    return body

def normalize_order(row):
    status = str(first(row, "status", "orderStatus", default="UNKNOWN")).upper().replace("_", "").replace(" ", "")
    mapped = {"NEW": "WORKING", "PENDINGNEW": "WORKING", "WORKING": "WORKING",
              "PARTIALLYFILLED": "PARTIAL", "PARTIALFILLED": "PARTIAL", "PARTIAL": "PARTIAL",
              "FILLED": "FILLED", "MATCHED": "FILLED", "CANCELED": "CANCELLED", "CANCELLED": "CANCELLED",
              "REJECTED": "REJECTED", "EXPIRED": "EXPIRED", "PENDINGCANCEL": "CANCEL_PENDING"}
    fill = first(row, "fillQuantity", "filledQuantity", "matchedQuantity", "cumQty", "filledQty")
    avg = first(row, "averagePrice", "avgPrice", "averageFillPrice", "matchedPrice")
    state = mapped.get(status, "UNKNOWN")
    if fill is None and status in {"NEW", "PENDINGNEW"}:
        fill = 0  # The broker's NEW acknowledgement proves no execution yet.
    if fill is None or (number(fill) > 0 and (avg is None or number(avg) <= 0)):
        state = "UNKNOWN"
    return {
        "broker_id": str(first(row, "id", "orderId", default="")),
        "symbol": str(row.get("symbol", "")),
        "exchange_side": str(row.get("side", "")),
        "tag": str(first(row, "remark", "comment", default="")),
        "status": state, "filled": None if fill is None else quantity(fill),
        "avg_fill": number(avg),
        "quantity": quantity(first(row, "quantity", "orderQuantity", default=0)),
        "price": number(row.get("price")),
        "fee": number(first(row, "fee", "commission", default=0)) + number(row.get("tax")),
    }
