import time

import pytest

from ckps.connections.dnse.protocol import BrokerError, SubmissionCancelled, UnknownOutcome, normalize_order, rows
from ckps.connections.dnse.client import DNSEBroker
from ckps.models import Order


def test_contract_month_comes_from_dnse_and_missing_alias_cannot_reuse_old_month(monkeypatch):
    broker=DNSEBroker('key','secret','123')
    instruments=[{'symbolType':'VN30F1M','symbol':'41I1GB000'}]
    def request(method,path,**kwargs):
        assert method=='GET' and path=='/market/instruments'
        return {'instruments':list(instruments)}
    monkeypatch.setattr(broker,'request',request)
    try:
        assert broker.resolve()=='41I1GB000'
        instruments[:]=[{'symbolType':'VN30F1M','symbol':'41I1GC000'}]
        broker.instrument_at=0
        assert broker.resolve()=='41I1GC000'
        instruments.clear();broker.instrument_at=0
        with pytest.raises(BrokerError,match='Chưa xác minh'):broker.resolve()
    finally:broker.close()


def test_daily_history_preserves_returned_volume_for_p2(monkeypatch):
    broker = DNSEBroker("key", "secret", "123")
    monkeypatch.setattr(broker, "request", lambda *a, **kw: {
        "t": [1, 2], "o": [2000, 2001], "h": [2002, 2003], "l": [1999, 2000],
        "c": [2001, 2002], "v": [123, 456]})
    assert [row["volume"] for row in broker.daily_bars()] == [123, 456]
    broker.close()


def test_new_acknowledgement_does_not_need_fill_price():
    row = normalize_order({"orderId": "one", "status": "New"})
    assert row["status"] == "WORKING" and row["filled"] == 0


def test_partial_fill_without_average_is_not_invented():
    row = normalize_order({"orderId": "one", "status": "PartiallyFilled", "fillQuantity": 1, "price": 2000})
    assert row["status"] == "UNKNOWN"


def test_incomplete_pagination_does_not_erase_positions():
    with pytest.raises(BrokerError):
        rows({"total": 2, "data": [{"symbol": "one"}]}, "positions")


def test_live_submit_uses_explicit_derivative_market_and_direction(monkeypatch):
    broker = DNSEBroker("key", "secret", "123", "2278")
    calls = []
    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return {"positions": [{"id": "pos", "symbol": "41I1GB000", "side": "NS", "openQuantity": 2, "loanPackageId": 2278}]}
        return {"orderId": "one", "status": "NEW"}
    monkeypatch.setattr(broker, "request", request)
    order = Order.create("41I1GB000", "SHORT", 1, action="CLOSE")
    broker.submit(order)
    method, path, args = calls[-1]
    assert method == "POST" and path == "/accounts/123/orders"
    assert args["params"]["marketType"] == "DERIVATIVE"
    assert args["body"]["side"] == "NB"
    assert args["body"]["loanPackageId"] == 2278
    assert "remark" not in args["body"]
    assert args["trading"] is True


def test_live_submit_refuses_stock_or_unresolved_alias():
    broker = DNSEBroker("key", "secret", "123")
    for symbol in ("FPT", "VN30F1M", "41I2GB000"):
        with pytest.raises(BrokerError):
            broker.submit(Order.create(symbol, "LONG", 1))


def test_undated_latest_trade_does_not_become_fresh(monkeypatch):
    broker = DNSEBroker("key", "secret", "123")
    monkeypatch.setattr(broker, "request", lambda *a, **kw: {"price": 2000})
    assert not broker.get_quote("41I1GB000").fresh()


def test_off_during_live_close_preflight_prevents_post(monkeypatch):
    broker = DNSEBroker("key", "secret", "123", "2278")
    permission = [True]
    calls = []
    def request(method, path, **kwargs):
        calls.append(method)
        assert method == "GET"
        permission[0] = False
        return {"positions": [{"id": "pos", "symbol": "41I1GB000", "side": "NB", "openQuantity": 1, "loanPackageId": 2278}]}
    monkeypatch.setattr(broker, "request", request)
    with pytest.raises(SubmissionCancelled):
        broker.submit(Order.create("41I1GB000", "LONG", 1, action="CLOSE"), can_submit=lambda: permission[0])
    assert calls == ["GET"]


def test_full_live_close_uses_native_position_close_endpoint(monkeypatch):
    broker = DNSEBroker("key", "secret", "123", "2278")
    calls = []
    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return {"positions": [{"id": "deal1", "symbol": "41I1GB000", "side": "NS", "openQuantity": 2, "loanPackageId": 2278}]}
        return {"id": "close", "orderStatus": "PendingNew"}
    monkeypatch.setattr(broker, "request", request)
    broker.submit(Order.create("41I1GB000", "SHORT", 2, action="CLOSE", kind="MOK"))
    assert calls[-1][0:2] == ("POST", "/positions/deal1/close")
    assert calls[-1][2]["body"] is None


def test_malformed_success_after_post_remains_unknown(monkeypatch):
    broker = DNSEBroker("key", "secret", "123", "2278")
    monkeypatch.setattr(broker, "request", lambda *a, **kw: {"id": "one", "orderStatus": "Filled", "fillQuantity": -1})
    with pytest.raises(UnknownOutcome):
        broker.submit(Order.create("41I1GB000", "LONG", 1))
