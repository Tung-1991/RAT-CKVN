from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import time
from urllib.parse import quote as urlquote
from zoneinfo import ZoneInfo
import uuid

import requests

from ckps.models import FINAL, Order, Quote, Settings, Snapshot, is_vn30, market_time, number, quantity



from ckps.connections.dnse.protocol import BrokerError, UnknownOutcome, SubmissionCancelled, first, rows, unwrap, normalize_order
from ckps.connections.dnse.account import amount, balances
from ckps.connections.dnse.fees import package_fees

class DNSEBroker:
    mode = "REAL"
    requires_account = True

    def __init__(self, key, secret, account_no="", loan_package_id="", session=None):
        if not key or not secret or (self.requires_account and not str(account_no).isdigit()):
            raise BrokerError("Cần API key, secret và tài khoản phái sinh DNSE.")
        self.key, self.secret, self.account_no = key, secret, str(account_no)
        self.loan_package_id = str(loan_package_id)
        self.session = session or requests.Session()
        self.token = ""
        self.token_until = 0.0
        self.retry_at = 0.0
        self.instruments = {}
        self.instrument_at = 0.0
        self.bars, self.bars_at = [], 0.0
        self.packages, self.packages_at = [], 0.0
        self.history_worker = None
        from ckps.connections.dnse.stream import MarketFeed
        self.feed = MarketFeed(key, secret)

    def request(self, method, path, *, params=None, body=None, trading=False):
        if time.time() < self.retry_at:
            raise BrokerError("DNSE đang giới hạn truy cập; chờ lần cập nhật kế tiếp.")
        if trading and (not self.token or time.time() >= self.token_until):
            raise BrokerError("Cần xác thực OTP giao dịch.")
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        nonce = uuid.uuid4().hex
        message = f"(request-target): {method.lower()} {path}\nx-aux-date: {date}\nnonce: {nonce}"
        digest = base64.b64encode(hmac.new(self.secret.encode(), message.encode(), hashlib.sha256).digest()).decode()
        signature = f'Signature keyId="{self.key}",algorithm="hmac-sha256",headers="(request-target) x-aux-date",signature="{urlquote(digest, safe="")}",nonce="{nonce}"'
        headers = {"X-API-Key": self.key, "X-Signature": signature, "X-Aux-Date": date,
                   "Content-Type": "application/json", "Accept": "application/json", "version": "2026-09-15"}
        if trading:
            headers["trading-token"] = self.token
        try:
            response = self.session.request(method, "https://openapi.dnse.com.vn" + path,
                                            params=params, json=body, headers=headers, timeout=(5, 12))
        except requests.RequestException as exc:
            self.retry_at = time.time() + 10
            error = UnknownOutcome if method in {"POST", "PUT", "DELETE"} and trading else BrokerError
            raise error("Mất kết nối DNSE; cần đối soát kết quả.") from exc
        if response.status_code == 429:
            self.retry_at = time.time() + max(10, min(300, number(response.headers.get("Retry-After"), 30)))
        if response.status_code >= 500:
            self.retry_at = time.time() + 10
            if trading and method != "GET":
                raise UnknownOutcome(f"DNSE HTTP {response.status_code}; cần đối soát.")
        if not response.ok:
            if trading and response.status_code in {401, 403}:
                self.token, self.token_until = '', 0.
                from ckps.connections.secure_session import save_trading_session
                try:save_trading_session(self.account_no, {'key': self.key, 'secret': self.secret}, '', 0.)
                except (OSError, ValueError):pass
            raise BrokerError(f"DNSE HTTP {response.status_code} · {method} {path}")
        try:
            return response.json()
        except ValueError as exc:
            if trading and method != "GET":
                raise UnknownOutcome("DNSE trả kết quả không đọc được; cần đối soát.") from exc
            raise BrokerError("DNSE trả dữ liệu không hợp lệ.") from exc

    def send_otp(self):
        self.request("POST", "/registration/send-email-otp")

    def verify_otp(self, passcode, otp_type="email_otp"):
        body = unwrap(self.request("POST", "/registration/trading-token",
                                   body={"otpType": otp_type, "passcode": str(passcode)}))
        token = first(body, "tradingToken", "trading-token", "token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise BrokerError("DNSE chưa trả trading token hợp lệ.")
        self.token, self.token_until = token, time.time() + 8 * 3600

    def resolve(self):
        if not self.instruments or time.time() - self.instrument_at > 300:
            values = rows(self.request("GET", "/market/instruments", params={"marketId": "DVX", "securityGroupId": "FU", "pageSize": 100}), "instruments")
            self.instruments = {row["symbolType"]: row["symbol"] for row in values
                                if str(row.get("symbolType", "")).startswith("VN30F") and row.get("symbol")}
            self.instrument_at = time.time()
        contract = self.instruments.get("VN30F1M")
        if not contract or not is_vn30(contract):
            raise BrokerError("Chưa xác minh được mã hợp đồng VN30F1M.")
        return contract

    def get_quote(self, symbol):
        streamed = self.feed.latest(symbol)
        if streamed:
            return streamed
        body = unwrap(self.request("GET", f"/price/{symbol}/trades/latest"))
        if isinstance(body, dict) and "trades" in body:
            body = body["trades"]
        if isinstance(body, list):
            body = body[0] if body else {}
        if not isinstance(body, dict):
            raise BrokerError("DNSE chưa trả giá hợp đồng.")
        price = number(first(body, "price", "lastPrice", "last", "matchPrice"))
        stamp = first(body, "time", "timestamp", "transactTime", "tradeTime", "tradingTime")
        at = market_time(stamp)
        # An HTTP receipt time must not make an old/undated trade fresh.
        return Quote(symbol, price, at=at, source="DNSE", floor=number(body.get("floorPrice")), ceiling=number(body.get("ceilingPrice")))

    def daily_bars(self):
        if time.time() - self.bars_at < 300:
            return self.bars
        body = unwrap(self.request("GET", "/price/ohlc", params={"symbol": "VN30F1M", "type": "DERIVATIVE",
            "resolution": "1D", "from": str(int(time.time() - 400 * 86400)), "to": str(int(time.time()))}))
        if isinstance(body, dict) and all(isinstance(body.get(k), list) for k in ("t", "o", "h", "l", "c")):
            self.bars = [dict(zip(("time", "open", "high", "low", "close"), values))
                         for values in zip(body["t"], body["o"], body["h"], body["l"], body["c"])]
            if isinstance(body.get("v"), list) and len(body["v"]) == len(self.bars):
                for row, volume in zip(self.bars, body["v"]):
                    row["volume"] = volume
        else:
            self.bars = rows(body, "candles")
        self.bars_at = time.time()
        return self.bars

    def snapshot(self):
        contract = self.resolve()
        balance = unwrap(self.request("GET", f"/accounts/{self.account_no}/balances"))
        derivative = balance.get("derivative") if isinstance(balance, dict) else None
        if not isinstance(derivative, dict):
            raise BrokerError("Thiếu ví ký quỹ phái sinh; không dùng tiền CKCS thay thế.")
        raw_positions = rows(self.request("GET", f"/accounts/{self.account_no}/positions",
                                         params={"marketType": "DERIVATIVE", "pageSize": 1000}), "positions")
        positions = []
        for row in raw_positions:
            symbol = str(first(row, "symbol", "symbolCode", default="")).upper()
            if not is_vn30(symbol):
                continue
            qty = quantity(first(row, "openQuantity", "quantity", "volume", "netQuantity", default=-1))
            if not qty:
                continue
            side_raw = str(first(row, "side", "positionSide", "positionType", default="")).upper()
            side = "LONG" if side_raw in {"NB", "LONG", "BUY", "B"} else "SHORT" if side_raw in {"NS", "SHORT", "SELL", "S"} else None
            entry = number(first(row, "priceOpen", "avgPrice", "averagePrice", "costPrice"))
            if not side or entry <= 0:
                raise BrokerError("Chưa xác minh được chiều/giá vốn vị thế VN30.")
            positions.append({"symbol": symbol, "side": side, "quantity": qty, "entry": entry,
                              "broker_id": str(first(row, "id", "positionId", default="")),
                              "loan_package_id": str(row.get("loanPackageId", ""))})
        raw_orders = rows(self.request("GET", f"/accounts/{self.account_no}/orders",
                                      params={"marketType": "DERIVATIVE", "pageSize": 1000}), "orders")
        orders = [normalize_order(row) for row in raw_orders if is_vn30(row.get("symbol", ""))]
        symbols = {contract, *(p["symbol"] for p in positions)}
        self.feed.start(symbols)
        quotes = {symbol: self.get_quote(symbol) for symbol in symbols}
        px = quotes[contract].last
        margin, qlong, qshort = None, None, None
        if time.time() - self.packages_at > 3600:
            self.packages = rows(self.request("GET", f"/accounts/{self.account_no}/loan-packages",
                                              params={"marketType": "DERIVATIVE", "symbol": "VN30F1M"}), "loanPackages")
            self.packages_at = time.time()
        if not self.loan_package_id and len(self.packages) == 1:
            self.loan_package_id = str(self.packages[0]["id"])
        package = next((p for p in self.packages if str(p.get("id")) == self.loan_package_id), None)
        if package is not None and px > 0:
            rate = number(package.get("initialRate"))
            if 0 < rate < 1:
                margin = px * 100_000 * rate
            ppse = unwrap(self.request("GET", f"/accounts/{self.account_no}/ppse",
                params={"marketType": "DERIVATIVE", "symbol": contract,
                        "loanPackageId": self.loan_package_id, "price": f"{px:g}"}))
            if isinstance(ppse, dict):
                qlong = quantity(ppse["qmaxBuy"]) if ppse.get("qmaxBuy") is not None else None
                qshort = quantity(ppse["qmaxSell"]) if ppse.get("qmaxSell") is not None else None
                margin = number(first(ppse, "marginPerContract", "initialMargin", "requiredSecure")) or margin
        # A rate is acceptable only when actually returned for this account.
        if margin is None and derivative.get("initialMarginRate") is not None:
            rate = number(derivative["initialMarginRate"])
            if rate > 1:
                rate /= 100
            if 0 < rate < 1:
                margin = px * 100_000 * rate
        funds = balances(derivative)
        stock = balance.get("stock") if isinstance(balance, dict) else None
        total_money = amount(stock.get("totalCash")) if isinstance(stock, dict) else None
        bars = self.history_worker.snapshot() if self.history_worker else self.bars
        # pendingSecure is a deposit/withdrawal awaiting approval, not an order reservation.
        pending_margin = amount(derivative.get("pendingOrderSecure"))
        if pending_margin is None and not any(row["status"] not in FINAL for row in orders):
            pending_margin = 0.0
        return Snapshot(contract, positions, orders, quotes,
            funds["remaining_margin"], funds["used_margin"],
            margin, qlong, qshort, funds["nav"], bars=bars, source="DNSE",
            pending_margin=pending_margin, total_money=total_money, collateral_total=funds["collateral_total"], margin_reference_price=px,
            package_fees=package_fees(package))

    def opening_limits(self, symbol, price):
        """Read broker capacity at the exact proposed price, never a POST retry."""
        package = next((p for p in self.packages if str(p.get("id")) == self.loan_package_id), None)
        if not package or price <= 0:
            raise BrokerError("Chưa xác minh gói ký quỹ/giá đặt.")
        response = unwrap(self.request("GET", f"/accounts/{self.account_no}/ppse", params={
            "marketType": "DERIVATIVE", "symbol": symbol, "loanPackageId": self.loan_package_id, "price": f"{price:g}"}))
        if not isinstance(response, dict):
            raise BrokerError("Chưa xác minh sức mở cho giá vé.")
        rate = amount(package.get("initialRate"))
        margin = amount(first(response, "marginPerContract", "initialMargin", "requiredSecure"))
        if margin is None and rate is not None and 0 < rate < 1:
            margin = price * 100_000 * rate
        return dict(qmax_long=quantity(response["qmaxBuy"]) if response.get("qmaxBuy") is not None else None,
                    qmax_short=quantity(response["qmaxSell"]) if response.get("qmaxSell") is not None else None,
                    margin_per_contract=margin, margin_reference_price=price, package_fees=package_fees(package))

    def submit(self, order, can_submit=None):
        if not is_vn30(order.symbol) or order.symbol.startswith("VN30F"):
            raise BrokerError("Lệnh REAL phải dùng mã hợp đồng VN30 đã xác minh.")
        package_id = self.loan_package_id
        close_path = None
        if order.action == "CLOSE":
            current = rows(self.request("GET", f"/accounts/{self.account_no}/positions",
                params={"marketType": "DERIVATIVE", "pageSize": 1000}), "positions")
            expected_side = "NB" if order.side == "LONG" else "NS"
            matching = [r for r in current if r.get("symbol") == order.symbol and str(r.get("side")).upper() == expected_side
                        and quantity(r.get("openQuantity", 0)) > 0]
            if sum(quantity(r["openQuantity"]) for r in matching) < order.quantity:
                raise BrokerError("DNSE xác nhận không còn đủ vị thế để đóng.")
            if len(matching) == 1 and order.kind != "LO" and quantity(matching[0]["openQuantity"]) == order.quantity:
                position_id = str(matching[0].get("id", ""))
                if position_id:
                    close_path = f"/positions/{position_id}/close"
            packages = {str(r["loanPackageId"]) for r in matching if r.get("loanPackageId") is not None}
            if len(packages) == 1:
                package_id = packages.pop()
            elif not close_path:
                raise BrokerError("Vị thế thuộc nhiều gói ký quỹ; đóng từng gói ở DNSE trước khi đóng từng phần qua app.")
        if not package_id and not close_path:
            raise BrokerError("Chọn gói ký quỹ DNSE trước khi đặt lệnh.")
        body = {"symbol": order.symbol, "side": order.exchange_side,
                "quantity": order.quantity, "orderType": order.kind,
                "price": order.price, "loanPackageId": int(package_id) if package_id else 0}
        if can_submit is not None and not can_submit():
            raise SubmissionCancelled("Đã dừng trước khi gửi lệnh bảo vệ.")
        result = unwrap(self.request("POST", close_path or f"/accounts/{self.account_no}/orders",
            params={"marketType": "DERIVATIVE", **({} if close_path else {"orderCategory": "NORMAL"})},
            body=None if close_path else body, trading=True))
        if not isinstance(result, dict):
            raise UnknownOutcome("DNSE chưa trả ID lệnh; chờ đối soát.")
        try:
            parsed = normalize_order(result)
        except (ValueError, TypeError, KeyError) as exc:
            raise UnknownOutcome("DNSE đã nhận yêu cầu nhưng phản hồi chưa xác minh được.") from exc
        if not parsed["broker_id"]:
            raise UnknownOutcome("DNSE chưa trả ID lệnh; chờ đối soát.")
        return parsed

    def cancel(self, order):
        self.request("DELETE", f"/accounts/{self.account_no}/orders/{order.broker_id}",
                     params={"marketType": "DERIVATIVE", "orderCategory": "NORMAL"}, trading=True)

    def replace(self, order, qty, price):
        self.request("PUT", f"/accounts/{self.account_no}/orders/{order.broker_id}",
                     params={"marketType": "DERIVATIVE", "orderCategory": "NORMAL"}, body={"quantity": qty, "price": price}, trading=True)

    def close(self):
        self.token = ""
        if self.history_worker:
            self.history_worker.close()
        self.feed.close()
        self.session.close()
