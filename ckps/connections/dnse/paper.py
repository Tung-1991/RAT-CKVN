from __future__ import annotations
from dataclasses import asdict
from math import isfinite
from ckps.models import FINAL, Order, Quote, Settings, Snapshot, number
from .protocol import BrokerError, SubmissionCancelled

class PaperBroker:
    """Virtual money/orders with DNSE quotes; synthetic prices are test-only."""
    mode = "PAPER"

    def __init__(self, store, settings: Settings, *, market=None, offline=False):
        self.store, self.settings = store, settings
        self.offline = offline
        self.market = market
        self.feed = getattr(market,"feed",None)
        self.contract, self.quotes, self.bars = "VN30F1M", {}, []
        self.market_view = {"configured":False,"connected":False,"error":"Chưa kết nối dữ liệu DNSE."}
        if store.get("paper", "account") is None:
            store.put("paper", "account", {"cash": settings.paper_balance,"capital":settings.paper_balance})
        elif "capital" not in store.get("paper","account"):
            account=store.get("paper","account")
            account["capital"]=settings.paper_balance
            store.put("paper","account",account)
        self.price = store.get("paper", "account").get("price",2000.0) if offline else None

    def set_capital(self, value, snapshot):
        """Change virtual contributed capital, preserving fills, fees and PnL."""
        value=float(value)
        if not isfinite(value) or value<=0:
            raise ValueError("Vốn PAPER phải là số dương hợp lệ.")
        with self.store.transaction():
            account=self.store.get("paper","account")
            delta=value-account["capital"]
            pending=[row for row in snapshot.orders if row['status'] not in FINAL]
            if delta<0 and (snapshot.positions or pending):
                symbols={row['symbol'] for row in snapshot.positions+pending}
                if (any(not snapshot.quotes.get(symbol) or not snapshot.quotes[symbol].fresh(self.settings.max_quote_age) for symbol in symbols)
                    or any(v is None for v in (snapshot.nav,snapshot.used_margin,snapshot.pending_margin))):
                    raise ValueError('Chờ giá hợp lệ trước khi giảm vốn PAPER đang có vị thế/lệnh chờ.')
                if snapshot.nav+delta<snapshot.used_margin+snapshot.pending_margin:
                    raise ValueError('Vốn PAPER còn lại không đủ ký quỹ cho vị thế/lệnh chờ.')
            if delta:
                account['cash']+=delta
                account['capital']=value
                self.store.put('paper','account',account)
                self.store.event('PAPER',f'Điều chỉnh vốn ảo {delta:+,.0f} đ · Vốn {value:,.0f} đ')
        self.settings.paper_balance=value

    def set_price(self, price):
        if not self.offline:
            raise BrokerError("PAPER lấy giá DNSE; không nhận giá nhập tay.")
        if number(price) <= 0:
            raise ValueError("Giá mô phỏng phải lớn hơn 0.")
        state = self.store.get("paper", "account")
        state["price"] = self.price = round(float(price), 1)
        self.store.put("paper", "account", state)

    def set_bars(self, rows):
        if not self.offline:
            raise BrokerError("PAPER tự lấy nến DNSE; CSV chỉ dùng kiểm thử offline.")
        from datetime import datetime
        from ckps.services.signals import daily_rows
        from ckps.rules.p2.market import VN_TZ
        values = daily_rows(rows, datetime.now(VN_TZ))
        if not values or len(values) != len(rows):
            raise ValueError("CSV cần các nến 1D hợp lệ, không trùng/ngày tương lai; có time/date và close.")
        self.store.put("paper", "daily_bars", values)

    def _quote(self, symbol):
        if self.offline:
            return Quote(symbol,self.price,self.price,self.price,source="OFFLINE / GIÁ KIỂM THỬ")
        quote=(self.feed.latest(symbol,self.settings.max_quote_age) if self.feed else None) or self.quotes.get(symbol)
        return quote if quote and quote.symbol==symbol else None

    def _fee(self, action):
        fees=self.market_view.get('account_profile',{}).get('fees',{})
        # PAPER uses the higher published close rate for its estimate.
        value=fees.get('close' if action=='CLOSE' else 'open')
        return self.settings.estimated_fee_per_contract if value is None else value

    def _fill(self, row):
        if row["status"] in FINAL:
            return
        quote = self._quote(row["symbol"])
        if not quote or not quote.fresh(self.settings.max_quote_age):
            return
        buy = (row["side"] == "LONG") == (row["action"] == "OPEN")
        fill_price = (quote.ask if buy else quote.bid) or quote.last
        if row["kind"] == "LO" and not (fill_price <= row["price"] if buy else fill_price >= row["price"]):
            return
        key = row["symbol"]
        holding = self.store.get("paper_position", key)
        qty = row["quantity"] - row["filled"]
        account = self.store.get("paper", "account")
        fee = self._fee(row['action']) * qty
        if row["action"] == "OPEN":
            if holding and holding["side"] != row["side"]:
                row["status"] = "REJECTED"
            else:
                previous = holding["quantity"] if holding else 0
                total = previous + qty
                entry = ((holding["entry"] * previous if holding else 0) + fill_price * qty) / total
                self.store.put("paper_position", key, {"symbol": key, "side": row["side"], "quantity": total, "entry": entry})
                row.update(status="FILLED", filled=row["quantity"], avg_fill=fill_price, fee=fee)
                account["cash"] -= fee
        else:
            if not holding or holding["side"] != row["side"] or holding["quantity"] < qty:
                row["status"] = "REJECTED"
            else:
                sign = 1 if holding["side"] == "LONG" else -1
                account["cash"] += sign * (fill_price - holding["entry"]) * qty * 100_000 - fee
                holding["quantity"] -= qty
                self.store.put("paper_position", key, holding)
                row.update(status="FILLED", filled=row["quantity"], avg_fill=fill_price, fee=fee)
        self.store.put("paper", "account", account)
        self.store.put("paper_order", row["id"], row)

    def submit(self, order: Order, can_submit=None):
        if can_submit is not None and not can_submit():
            raise SubmissionCancelled("Đã dừng trước khi gửi lệnh bảo vệ.")
        with self.store.transaction():
            existing = self.store.get("paper_order", order.id)
            if existing:
                return existing
            row = asdict(order)
            row.update(broker_id=order.id, status="WORKING", tag="CKPS:" + order.id)
            self.store.put("paper_order", order.id, row)
            self._fill(row)
            return row

    def cancel(self, order):
        with self.store.transaction():
            row = self.store.get("paper_order", order.broker_id)
            if not row or row["status"] in FINAL:
                raise BrokerError("Lệnh mô phỏng đã kết thúc.")
            row["status"] = "CANCELLED"
            self.store.put("paper_order", row["id"], row)

    def replace(self, order, qty, price):
        with self.store.transaction():
            row = self.store.get("paper_order", order.broker_id)
            if not row or row["status"] in FINAL or qty < row["filled"]:
                raise BrokerError("Không thể sửa lệnh đã kết thúc hoặc nhỏ hơn phần đã khớp.")
            row.update(quantity=qty, price=price)
            self.store.put("paper_order", row["id"], row)
            self._fill(row)

    def snapshot(self):
        symbols = {row["symbol"] for row in self.store.all("paper_position") if row["quantity"]}
        symbols.update(row["symbol"] for row in self.store.all("paper_order") if row["status"] not in FINAL)
        if self.offline:
            self.quotes = {symbol:self._quote(symbol) for symbol in symbols | {self.contract}}
            self.bars = self.store.get("paper", "daily_bars", [])
        elif self.market:
            self.market_view = self.market.snapshot(symbols)
            self.contract = self.market_view["contract"]
            self.quotes={symbol:quote for symbol,quote in self.market_view["quotes"].items() if quote.symbol==symbol}
            self.bars = self.market_view["bars"]
            for symbol in symbols | {self.contract}:
                quote = self._quote(symbol)
                if quote:
                    self.quotes[symbol] = quote
        with self.store.transaction():
            for row in self.store.all("paper_order"):
                self._fill(row)
            positions = [row for row in self.store.all("paper_position") if row["quantity"]]
            orders = self.store.all("paper_order")
            account = self.store.get("paper", "account")
            def margin_for(symbol):
                quote = self.quotes.get(symbol)
                return quote.last * 100_000 * self.settings.paper_margin_rate if quote and quote.last>0 else None
            def total(values):
                return sum(values) if all(v is not None for v in values) else None
            margin = margin_for(self.contract)
            used = total([row["quantity"]*margin_for(row["symbol"]) if margin_for(row["symbol"]) is not None else None for row in positions])
            pending = total([(row["quantity"]-row["filled"])*margin_for(row["symbol"]) if margin_for(row["symbol"]) is not None else None
                             for row in orders if row["status"] not in FINAL and row["action"]=="OPEN"])
            unrealized = total([(1 if row["side"]=="LONG" else -1)*(self.quotes[row["symbol"]].last-row["entry"])*row["quantity"]*100_000
                                if row["symbol"] in self.quotes else None for row in positions])
            nav = account["cash"]+unrealized if unrealized is not None else None
            remaining = max(0.0,nav-used-pending) if all(v is not None for v in (nav,used,pending)) else None
            qmax = int(remaining//margin) if margin and remaining is not None else None
            return Snapshot(self.contract, positions, orders, self.quotes, remaining, used, margin,
                            qmax,qmax,nav,source="PAPER · TIỀN ẢO",pending_margin=pending,bars=self.bars,paper_capital=account['capital'],
                            total_money=account['cash'],collateral_total=account['cash'],margin_reference_price=self.quotes[self.contract].last if self.contract in self.quotes else None,
                            package_fees=self.market_view.get('account_profile',{}).get('fees',{}))

    def close(self):
        if self.market:
            self.market.close()
