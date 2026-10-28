from __future__ import annotations

from dataclasses import asdict, replace
import threading
import time

from ckps.connections.dnse.protocol import BrokerError, SubmissionCancelled, UnknownOutcome
from ckps.trading.portfolio import capacity
from ckps.models import FINAL, Decision, ExitSettings, Order, Position, Settings, Snapshot, direction, is_vn30, load_record, number, quantity
from ckps.rules.protection import adverse_anchor, evaluate
from ckps.services.calendar import block_reason as calendar_block_reason


class Engine:
    """Serialized manual execution and optional position protection. No auto entry."""

    def __init__(self, store, broker, settings: Settings):
        self.store, self.broker, self.settings = store, broker, settings.validate()
        self.enabled = threading.Event()  # Always disarmed on process start.
        self.latest: Snapshot | None = None
        self.healthy = False
        self.consistent = False
        self.error = "Chưa đồng bộ tài khoản."
        self.suspended = set()
        for order in store.orders(pending=True):
            if order.status == "CREATED":
                order.status = "CANCELLED"
                order.message = "Khởi động lại: bỏ yêu cầu local chắc chắn chưa gửi."
                store.save_order(order)
            elif order.status == "SUBMITTING":
                order.status = "UNKNOWN"
                order.message = "Khởi động lại: chờ đối soát, không gửi lại."
                store.save_order(order)

    def disarm(self):
        # May be called directly by the Tk thread, including during broker I/O.
        self.enabled.clear()

    def suspend_position(self, position_id):
        self.suspended.add(position_id)

    def arm(self, enabled):
        if not enabled:
            self.disarm()
        else:
            self._ready()
            self._quote(self.latest.contract)
            self.enabled.set()
        self.store.event("BOT", "Bật quản lý tự động" if enabled else "Tắt quản lý tự động")

    def exits(self, position=None):
        raw = position.exit_overrides if position and position.exit_overrides is not None else self.settings.exit
        return load_record(ExitSettings, raw).validate()

    def paper_capital(self, value):
        if self.broker.mode!='PAPER':
            raise ValueError('Chỉ chỉnh vốn ảo trong PAPER.')
        snapshot=self.poll(manage=False)
        self.broker.set_capital(value,snapshot)
        self.settings.paper_balance=float(value)

    def _ready(self):
        if not self.healthy or not self.consistent or not self.latest:
            raise BrokerError(self.error or "Chưa đối soát đủ dữ liệu tài khoản.")
        if time.time() - self.latest.observed_at > self.settings.max_quote_age:
            raise BrokerError("Snapshot tài khoản đã cũ; chờ đồng bộ.")
        if any(o.status in {"UNKNOWN", "SUBMITTING", "REPLACE_PENDING"} for o in self.store.orders(pending=True)):
            raise BrokerError("Có lệnh chưa rõ kết quả; cần đối soát trước.")
        own_ids = {o.broker_id for o in self.store.orders() if o.broker_id}
        if any(row.get("status") not in FINAL and row.get("broker_id") not in own_ids
               for row in self.latest.orders):
            raise BrokerError("Có lệnh VN30 đang chờ ngoài app; cần đối soát/hủy ở DNSE trước.")

    def _quote(self, symbol):
        quote = self.latest.quotes.get(symbol) if self.latest else None
        if not quote or quote.symbol!=symbol or not quote.fresh(self.settings.max_quote_age):
            raise BrokerError("Giá chưa có mốc thời gian hợp lệ hoặc đã cũ.")
        return quote

    def poll(self, manage=True):
        try:
            snapshot = self.broker.snapshot()
            if not is_vn30(snapshot.contract):
                raise BrokerError("Dữ liệu không thuộc hợp đồng VN30.")
            self.consistent = True
            with self.store.transaction():
                self._reconcile_orders(snapshot.orders)
                self._reconcile_positions(snapshot)
            self.latest = snapshot
            self.healthy = True
            self.error = "" if self.consistent else "Đang chờ vị thế DNSE đồng bộ với kết quả khớp."
            self._retire_open_remainders()
            self._complete_full_exits()
            if manage:
                self._manage()
            return snapshot
        except Exception as exc:
            self.healthy = False
            self.error = str(exc)
            raise

    def _reconcile_orders(self, updates):
        for order in self.store.orders():
            matches = [row for row in updates if (order.broker_id and row.get("broker_id") == order.broker_id)
                       or "CKPS:" + order.id in str(row.get("tag", ""))]
            if len(matches) > 1:
                order.status, order.message = "UNKNOWN", "Có nhiều lệnh DNSE trùng ID yêu cầu."
                self.store.save_order(order)
            elif matches and (order.pending or number(matches[0].get("fee")) > order.applied_fee
                              or number(matches[0].get("filled")) > order.applied):
                self._apply_update(order, matches[0])
            # Absence is not cancellation, rejection or proof that a POST failed.

    def _apply_update(self, order, update):
        before = asdict(order)
        if update.get("broker_id"):
            order.broker_id = str(update["broker_id"])
        filled = update.get("filled")
        status = update.get("status", "UNKNOWN")
        if (update.get("symbol") and update["symbol"] != order.symbol) or (
                update.get("exchange_side") and update["exchange_side"] != order.exchange_side):
            raise BrokerError("Mã/chiều phản hồi lệnh không khớp yêu cầu; cần đối soát.")
        reported_qty = update.get("quantity")
        replacing = bool(order.replacement)
        if replacing:
            wanted = order.replacement
            if (reported_qty == wanted["quantity"] and
                    abs(number(update.get("price")) - wanted["price"]) < 0.051):
                order.quantity, order.price = wanted["quantity"], wanted["price"]
                order.replacement = None
            elif status not in FINAL:
                status = "REPLACE_PENDING"
        if filled is None or filled < order.applied or filled > order.quantity:
            order.status, order.message = "UNKNOWN", "Khối lượng khớp chưa được xác minh."
        elif filled > order.applied:
            average = number(update.get("avg_fill"))
            notional = filled * average
            delta = filled - order.applied
            price = (notional - order.applied_notional) / delta
            if average <= 0 or price <= 0:
                order.status, order.message = "UNKNOWN", "Thiếu giá khớp tích lũy."
            else:
                self._apply_fill(order, delta, price, number(update.get("fee")))
                order.filled, order.applied = filled, filled
                order.avg_fill, order.applied_notional = average, notional
                order.status = status
        else:
            order.filled = filled
            # FILLED without all contracts being evidenced is not a completed fill.
            order.status = "UNKNOWN" if status == "FILLED" and filled != order.quantity else status
        if status == "FILLED" and filled != order.quantity:
            order.status, order.message = "UNKNOWN", "Broker báo khớp đủ nhưng thiếu bằng chứng khối lượng."
        order.fee = max(order.fee, number(update.get("fee")))
        fee_delta = order.fee - order.applied_fee
        if fee_delta > 0 and order.position_id and order.applied:
            position = self.store.position(order.position_id)
            position.fees += fee_delta
            self.store.save_position(position)
            order.applied_fee = order.fee
        if asdict(order) != before:
            self.store.save_order(order)
            self.store.event("ORDER", f"{order.action} {order.side} {order.symbol} · {order.status} · {order.filled}/{order.quantity} HĐ")
            self._notify(f"{order.action} {order.side} {order.symbol} · {order.status}\nKhớp {order.filled}/{order.quantity} HĐ @ {order.avg_fill:g} · {order.reason}",
                         f"order:{order.id}:{order.status}:{order.filled}")
            self._record_entry_notice(order)
        if order.source == "AUTO" and order.reason == "ARM" and order.position_id:
            position = self.store.position(order.position_id)
            state = position.metrics.get("ARM:AUTO", {})
            if state.get("order_id") == order.id:
                state["pending"] = order.pending
                if not order.pending:
                    state.pop("round_best", None)
                position.metrics["ARM:AUTO"] = state
                self.store.save_position(position)

    def _record_entry_notice(self, order):
        if order.action == "OPEN":
            self.store.put("entry_notice", f"{order.id}:{order.status}:{order.filled}", {
                "at": time.time(), "mode": self.broker.mode, "symbol": order.symbol,
                "side": order.side, "status": order.status, "filled": order.filled,
                "quantity": order.quantity, "price": order.avg_fill or order.price,
            })

    def _apply_fill(self, order, qty, price, total_fee):
        fee_delta = max(0.0, total_fee - order.applied_fee)
        if order.action == "OPEN":
            candidates = [p for p in self.store.positions() if p.symbol == order.symbol]
            position = candidates[0] if candidates else None
            if not position and order.parent_position_id and order.abandon_remainder:
                position = self.store.position(order.parent_position_id)
                position.closed_at = 0.0
                position.managed = False
                position.note = "Khớp muộn phần mở đã yêu cầu hủy; tiếp tục đóng theo yêu cầu thoát toàn bộ."
            if position and position.side != order.side:
                raise BrokerError("Khớp mở ngược chiều với vị thế đang giữ; cần đối soát.")
            if not position:
                position = Position.create(order.symbol, order.side, 0, price, source="APP", managed=True,
                                           history_verified=True, exit_overrides=order.exit_settings)
                position.original_quantity = 0
                feed = getattr(self.broker, "feed", None)
                if feed:
                    feed.reset_extremes(order.symbol)
            total = position.quantity + qty
            position.entry = (position.entry * position.quantity + price * qty) / total
            position.quantity, position.original_quantity = total, position.original_quantity + qty
            if order.abandon_remainder:
                position.metrics["late_open_fill"] = True
            position.fees += fee_delta
            order.position_id = position.id
            order.parent_position_id = position.id
            self.store.save_position(position)
            for pending in self.store.orders(pending=True):
                if pending.action == "OPEN" and pending.symbol == position.symbol and not pending.parent_position_id:
                    pending.parent_position_id = position.id
                    self.store.save_order(pending)
        else:
            position = self.store.position(order.position_id)
            if position.closed_at or position.side != order.side or qty > position.quantity:
                raise BrokerError("Khớp đóng vượt vị thế trong sổ; dừng để đối soát.")
            position.quantity -= qty
            position.realized += position.sign * (price - position.entry) * qty * 100_000
            position.fees += fee_delta
            if order.source == "AUTO" and order.reason in {"ARM", "DYN"}:
                key = order.reason + ":AUTO"
                state = position.metrics.get(key, {})
                anchor = adverse_anchor(position.sign, price, order.trigger, order.protection_anchor)
                if state.get("order_id") != order.id:
                    state = {"count": state.get("count", 0) + 1, "anchor": anchor, "order_id": order.id, "pending": True}
                else:
                    state["anchor"] = adverse_anchor(position.sign, state.get("anchor"), anchor)
                position.metrics[key] = state
            if not position.quantity:
                position.metrics["closing_all"] = True
                self._abandon_open_remainders(position)
                position.closed_at = time.time()
                self._notify(f"ĐÓNG {position.side} {position.symbol}\nPnL {position.realized - position.fees:,.0f}đ · {'PAPER, phí theo cấu hình' if self.broker.mode == 'PAPER' else 'TẠM TÍNH, chờ đối chiếu phí DNSE'}",
                             "closed:" + position.id)
            self.store.save_position(position)
        order.applied_fee += fee_delta

    def _abandon_open_remainders(self, position):
        for pending in self.store.orders(pending=True):
            if pending.action == "OPEN" and pending.symbol == position.symbol and pending.side == position.side:
                pending.parent_position_id = position.id
                pending.abandon_remainder = True
                self.store.save_order(pending)

    def _retire_open_remainders(self):
        """Cancel once outside the fill transaction; absence never confirms cancellation."""
        for order in self.store.orders(pending=True):
            if order.abandon_remainder and order.broker_id and order.status in {"WORKING", "PARTIAL"}:
                try:
                    self.cancel(order.id)
                except BrokerError as exc:
                    self.store.event("ERROR", "Hủy phần mở còn chờ: " + str(exc))

    def _complete_full_exits(self):
        for position in self.store.positions():
            if not position.metrics.get("closing_all") or not position.metrics.get("late_open_fill"):
                continue
            available = position.quantity - sum(o.remainder for o in self._pending_closes(position.id))
            if available > 0:
                before = {o.id for o in self.store.orders()}
                position.metrics["late_open_fill"] = False
                self.store.save_position(position)
                try:
                    self.close_position(position.id, available)
                except (BrokerError, ValueError) as exc:
                    # Only retry a local precondition. Once an order was created,
                    # rejection or an unknown result needs operator reconciliation.
                    if not any(o.id not in before and o.action == "CLOSE" for o in self.store.orders()):
                        position = self.store.position(position.id)
                        position.metrics["late_open_fill"] = True
                        self.store.save_position(position)
                    self.store.event("ERROR", "Chờ hoàn tất thoát toàn bộ: " + str(exc))

    def _reconcile_positions(self, snapshot):
        actual = {}
        for row in snapshot.positions:
            symbol, side = row["symbol"], row["side"]
            direction(side)
            if not is_vn30(symbol) or row["entry"] <= 0:
                raise BrokerError("Vị thế không hợp lệ.")
            qty = quantity(row["quantity"])
            if not qty:
                continue
            previous = actual.get(symbol)
            if previous and previous["side"] != side:
                raise BrokerError("DNSE trả hai chiều cùng hợp đồng; chưa thể gộp vị thế.")
            total = qty + (previous["quantity"] if previous else 0)
            entry = (row["entry"] * qty + (previous["entry"] * previous["quantity"] if previous else 0)) / total
            actual[symbol] = {"side": side, "quantity": total, "entry": entry}
        active = {p.symbol: p for p in self.store.positions()}
        ambiguous = {o.symbol for o in self.store.orders(pending=True)
                     if o.status in {"UNKNOWN", "SUBMITTING", "REPLACE_PENDING"}}
        recent = {o.symbol for o in self.store.orders() if o.filled and time.time() - o.updated_at < 15}
        for symbol in actual.keys() | active.keys():
            row, position = actual.get(symbol), active.get(symbol)
            match = (row and position and row["side"] == position.side and
                     row["quantity"] == position.quantity and abs(row["entry"] - position.entry) < 0.051)
            if match:
                continue
            if symbol in ambiguous:
                self.consistent = False
                continue
            if symbol in recent:
                self.consistent = False
                continue
            if not row:
                if position:
                    position.quantity = 0
                    position.closed_at = time.time()
                    position.managed = False
                    position.pnl_verified = False
                    position.note = "Đã đóng ngoài app; chưa có đủ giá/chi phí để hạch toán PnL."
                    self.store.save_position(position)
                    self.store.event("EXTERNAL", f"{symbol}: đã đóng ngoài app")
                continue
            if position and position.side != row["side"]:
                position.quantity, position.closed_at, position.managed = 0, time.time(), False
                position.pnl_verified = False
                position.note = "Đảo chiều ngoài app; không chuyển E/M sang vị thế mới."
                self.store.save_position(position)
                position = None
            if not position:
                position = Position.create(symbol, row["side"], row["quantity"], row["entry"])
                position.note = "Vị thế DNSE: cần nhận quản lý thủ công."
            else:
                position.quantity, position.entry = row["quantity"], row["entry"]
                position.original_quantity = max(position.original_quantity, position.quantity)
                position.managed, position.history_verified, position.pnl_verified = False, False, False
                position.source = "MIXED"
                position.note = "Khối lượng/giá vốn thay đổi ngoài app; cần nhận quản lý lại."
            self.store.save_position(position)
            self.store.event("EXTERNAL", f"{position.side} {symbol} · {position.quantity} HĐ · {position.note}")
            self._notify(f"{position.side} {symbol} · {position.quantity} HĐ\n{position.note}",
                         f"external:{position.id}:{position.quantity}:{position.entry}")

    def _manage(self):
        allowed = self.enabled.is_set() and self.consistent
        try:
            self._ready()
        except BrokerError:
            allowed = False
        for position in self.store.positions():
            try:
                quote = self._quote(position.symbol)
            except BrokerError:
                continue
            decision = evaluate(position, quote.last, self.exits(position), self._atr(position.symbol))
            self.store.save_position(position)
            # Monitoring is independent of permission to act.
            if not allowed or not position.managed or position.id in self.suspended:
                continue
            if not decision or self._pending_closes(position.id):
                continue
            if decision.policy == "ALERT":
                state_key = decision.stage + ":ALERT"
                state = position.metrics.get(state_key, {})
                state.update(count=state.get("count", 0) + 1, anchor=quote.last, round_best=0.0)
                with self.store.transaction():
                    position.metrics[state_key] = state
                    self.store.save_position(position)
                    self.store.event("ALERT", f"{position.side} {position.symbol} · {decision.reason} · {quote.last:g}")
                    self._notify(f"{position.side} {position.symbol} · {decision.reason} ALERT\nGiá {quote.last:g} · Mốc {decision.price:g}",
                                 f"alert:{position.id}:{state_key}:{state['count']}")
            elif self.enabled.is_set():
                self.close_position(position.id, decision.quantity, automatic=decision)
                # A new broker snapshot is required before another automatic order.
                break

    def on_prices(self, quotes, extremes):
        if not self.latest or not self.healthy:
            return
        for symbol, quote in quotes.items():
            if quote.fresh(self.settings.max_quote_age):
                self.latest.quotes[symbol] = quote
        for position in self.store.positions():
            if position.symbol in extremes and position.symbol in quotes and quotes[position.symbol].fresh(self.settings.max_quote_age):
                low, high = extremes[position.symbol]
                position.best = max(position.best or position.entry, high) if position.sign > 0 else min(position.best or position.entry, low)
                position.worst = min(position.worst or position.entry, low) if position.sign > 0 else max(position.worst or position.entry, high)
                self.store.save_position(position)
        self._manage()

    def _pending_closes(self, position_id, exclude=""):
        return [o for o in self.store.orders(pending=True)
                if o.action == "CLOSE" and o.position_id == position_id and o.id != exclude]

    def _atr(self, symbol):
        from ckps.services.technical_notifications import completed_atr_pct
        return completed_atr_pct(self.latest.bars) if self.latest and symbol == self.latest.contract else 0.0

    def preview(self, side, price=0.0, exits=None, *, refresh=False):
        self._ready()
        reason=calendar_block_reason()
        if reason:raise BrokerError(reason)
        quote = self._quote(self.latest.contract)
        exits = self._entry_exits(side, exits)
        snapshot = self.latest
        if refresh and hasattr(self.broker, "opening_limits"):
            limits = self.broker.opening_limits(snapshot.contract, price or quote.last)
            snapshot = replace(snapshot, **limits)
        return capacity(self.settings, snapshot, self.store.positions(), self.store.orders(pending=True),
                        side, price or quote.last, exits)

    def _entry_exits(self, side, requested=None):
        """One net position has one E/M policy, including its pending additions."""
        positions = [p for p in self.store.positions() if p.symbol == self.latest.contract]
        orders = [o for o in self.store.orders(pending=True)
                  if o.symbol == self.latest.contract and o.action == "OPEN"]
        if any(p.side != side for p in positions) or any(o.side != side for o in orders):
            raise ValueError("Có vị thế/lệnh mở chiều ngược; đóng hoặc hủy trước khi mở chiều mới.")
        policies = [self.exits(p) for p in positions]
        policies.extend(load_record(ExitSettings, o.exit_settings or self.settings.exit).validate() for o in orders)
        existing = policies[0] if policies else self.exits()
        if any(rule != existing for rule in policies[1:]):
            raise ValueError("E/M vị thế và lệnh mở đang chờ khác nhau; cần đối soát trước khi vào thêm.")
        if requested is not None:
            requested.validate()
            if policies and requested != existing:
                raise ValueError("Vào thêm phải dùng cùng E/M với vị thế/lệnh đang chờ; sửa E/M trước.")
            return requested
        return existing

    def open_manual(self, side, qty, kind="LO", price=0.0, exit_settings=None):
        direction(side)
        self.poll(manage=False)
        self._ready()
        quote = self._quote(self.latest.contract)
        requested = load_record(ExitSettings, exit_settings).validate() if exit_settings is not None else None
        if kind not in {"LO", "MOK", "MTL"}:
            raise ValueError("Loại lệnh không hỗ trợ.")
        if kind == "LO" and (price <= 0 or abs(price * 10 - round(price * 10)) > 1e-6):
            raise ValueError("Giá LO phải dương và đúng bước 0,1 điểm.")
        if kind == "LO" and ((quote.floor and price < quote.floor) or (quote.ceiling and price > quote.ceiling)):
            raise ValueError("Giá LO ngoài biên hợp đồng.")
        current = [p for p in self.store.positions() if p.symbol == self.latest.contract]
        if current:
            if current[0].side != side:
                raise ValueError("Đang giữ chiều ngược: hãy đóng vị thế trước khi mở chiều mới.")
            if not current[0].managed:
                raise ValueError("Vị thế hiện tại chưa được nhận quản lý; nhận quản lý trước khi vào thêm qua app.")
            if self._pending_closes(current[0].id):
                raise ValueError("Có lệnh đóng đang chờ; không mở thêm.")
        if any(o.pending and o.action == "OPEN" and o.symbol == self.latest.contract and o.side != side for o in self.store.orders()):
            raise ValueError("Có lệnh mở chiều ngược đang chờ.")
        exits = self._entry_exits(side, requested)
        limit = self.preview(side, price if kind == "LO" else quote.last, exits, refresh=True)
        qty = limit.maximum if qty is None else quantity(qty)
        if qty <= 0 or qty > limit.maximum:
            raise ValueError(limit.reason or f"Tối đa {limit.maximum} HĐ theo vốn/sức mở/rủi ro.")
        pinned = exit_settings is not None or any(p.exit_overrides is not None for p in current) or any(
            o.exit_settings is not None for o in self.store.orders(pending=True)
            if o.symbol == self.latest.contract and o.action == "OPEN")
        order = Order.create(self.latest.contract, side, qty, kind=kind, price=price if kind == "LO" else 0,
                             exit_settings=asdict(exits) if pinned else None,
                             parent_position_id=current[0].id if current else "")
        self._send(order)
        return order

    def close_position(self, position_id, qty, automatic: Decision | None = None, kind="MOK", price=0.0):
        self._ready()
        position = self.store.position(position_id)
        quote = self._quote(position.symbol)
        qty = quantity(qty)
        reserved = sum(o.remainder for o in self._pending_closes(position_id))
        if position.closed_at or qty <= 0 or qty > position.quantity - reserved:
            raise ValueError("Không đủ HĐ còn lại sau khi trừ lệnh đóng đang chờ.")
        if automatic and (not self.enabled.is_set() or not position.managed):
            raise ValueError("Quản lý tự động đang tắt.")
        if kind not in {"LO", "MOK", "MTL"} or (kind == "LO" and price <= 0):
            raise ValueError("Lệnh đóng không hợp lệ.")
        self._validate_limit(kind, price, quote)
        order = Order.create(position.symbol, position.side, qty, action="CLOSE", position_id=position.id,
                             source="AUTO" if automatic else "MANUAL", kind=kind, price=price,
                             reason=automatic.reason if automatic else "MANUAL", trigger=automatic.price if automatic else 0)
        if automatic and automatic.reason in {"ARM", "DYN"}:
            order.protection_anchor = quote.last
        if qty + reserved == position.quantity:
            with self.store.transaction():
                position.metrics["closing_all"] = True
                self.store.save_position(position)
                self._abandon_open_remainders(position)
            self._retire_open_remainders()
        self._send(order)
        return order

    def _send(self, order):
        with self.store.transaction():
            self.store.save_order(order)
            self.store.event("REQUEST", f"{order.action} {order.side} {order.symbol} · {order.quantity} HĐ · {order.reason}")
        handed_off = False
        try:
            if order.action=='OPEN':
                reason=calendar_block_reason()
                if reason:raise BrokerError(reason)
            if order.action == "CLOSE":
                position = self.store.position(order.position_id)
                remaining = position.quantity - sum(o.remainder for o in self._pending_closes(position.id, order.id))
                if order.quantity > remaining:
                    raise BrokerError("Khối lượng đóng đã thay đổi.")
                if order.source == "AUTO":
                    if not self.enabled.is_set() or not position.managed:
                        raise BrokerError("BOT đã tắt trước khi gửi.")
                    quote = self._quote(position.symbol)
                    fresh_decision = evaluate(position, quote.last, self.exits(position), self._atr(position.symbol))
                    if not fresh_decision or fresh_decision.policy != "AUTO" or fresh_decision.reason != order.reason:
                        raise BrokerError("Điều kiện bảo vệ đã thay đổi trước khi gửi.")
                    if order.reason in {"ARM", "DYN"}:
                        order.protection_anchor = adverse_anchor(position.sign, order.protection_anchor, quote.last)
            self._ready()
            if order.source == "AUTO" and not self.enabled.is_set():
                raise BrokerError("BOT đã tắt trước khi gửi.")
            order.status = "SUBMITTING"
            self.store.save_order(order)
            # No POST retry path. SUBMITTING is durable before the network call.
            result = (self.broker.submit(order, can_submit=lambda: self._handoff_allowed(order))
                      if order.source == "AUTO" or order.action=='OPEN' else self.broker.submit(order))
            handed_off = True
            with self.store.transaction():
                self._apply_update(order, result)
        except UnknownOutcome as exc:
            order.status, order.message = "UNKNOWN", str(exc)
            with self.store.transaction():
                self.store.save_order(order)
                self._record_entry_notice(order)
            self._notify(f"LỆNH CHƯA RÕ · {order.symbol}\n{exc}", "unknown:" + order.id)
        except SubmissionCancelled as exc:
            order.status, order.message = "CANCELLED", str(exc)
            with self.store.transaction():
                self.store.save_order(order)
                self._record_entry_notice(order)
                self.store.event("ORDER", order.message)
        except Exception as exc:
            if handed_off:
                order = self.store.order(order.id)
                order.status, order.message = "UNKNOWN", "Đã gửi nhưng chưa hạch toán được: " + str(exc)
            else:
                order.status, order.message = "FAILED", str(exc)
            with self.store.transaction():
                self.store.save_order(order)
                self._record_entry_notice(order)
            raise

    def _handoff_allowed(self, order):
        if order.action=='OPEN':
            try:
                # This order is already SUBMITTING. Exclude its own durable
                # marker while checking the final permission before broker I/O.
                if not self.healthy or not self.consistent or not self.latest:return False
                if time.time()-self.latest.observed_at>self.settings.max_quote_age:return False
                if any(row.id!=order.id and row.status in {'UNKNOWN','SUBMITTING','REPLACE_PENDING'} for row in self.store.orders(pending=True)):return False
                self._quote(order.symbol)
                own = [row for row in self.store.orders(pending=True) if row.id != order.id]
                exits = load_record(ExitSettings, order.exit_settings or self.settings.exit)
                limit = capacity(self.settings, self.latest, self.store.positions(), own, order.side,
                                 order.price or self._quote(order.symbol).last, exits)
                if order.quantity > limit.maximum:
                    return False
                return not calendar_block_reason()
            except (BrokerError,ValueError,TypeError):return False
        if not self.enabled.is_set() or not self.healthy or not self.consistent or not self.latest:
            return False
        if order.position_id in self.suspended or time.time() - self.latest.observed_at > self.settings.max_quote_age:
            return False
        position = self.store.position(order.position_id)
        if not position.managed or position.closed_at or order.quantity > position.quantity:
            return False
        feed = getattr(self.broker, "feed", None)
        newest = feed.latest(position.symbol, self.settings.max_quote_age) if feed else None
        if newest:
            self.latest.quotes[position.symbol] = newest
        try:
            quote = self._quote(position.symbol)
        except BrokerError:
            return False
        decision = evaluate(position, quote.last, self.exits(position), self._atr(position.symbol))
        allowed = bool(self.enabled.is_set() and decision and decision.policy == "AUTO" and decision.reason == order.reason)
        if allowed and order.reason in {"ARM", "DYN"}:
            order.protection_anchor = adverse_anchor(position.sign, order.protection_anchor, quote.last)
            # Persist the final pre-POST observation, including UNKNOWN outcomes.
            self.store.save_order(order)
        return allowed

    def set_managed(self, position_id, enabled):
        position = self.store.position(position_id)
        if enabled:
            self._ready()
            quote = self._quote(position.symbol)
            if position.closed_at:
                raise ValueError("Vị thế đã đóng.")
            if not position.history_verified:
                feed = getattr(self.broker, "feed", None)
                if feed:
                    feed.reset_extremes(position.symbol)
                position.best = position.worst = quote.last
                position.floor = 0.0
                position.metrics = {}
            position.history_verified = True
            position.note = "Theo dõi MAE/MFE từ lúc nhận quản lý; không dựng đỉnh/đáy quá khứ."
        position.managed = bool(enabled)
        self.store.save_position(position)
        if enabled:
            self.suspended.discard(position_id)
        else:
            self.suspend_position(position_id)
        self.store.event("MANAGE", f"{position.side} {position.symbol} · {'Bật' if enabled else 'Tắt'} quản lý vị thế")

    def configure_position(self, position_id, exits):
        position = self.store.position(position_id)
        if exits is not None:
            exits = asdict(load_record(ExitSettings, exits).validate())
        position.exit_overrides = exits
        self.store.save_position(position)
        self.store.event("SETTINGS", f"{position.symbol}: cập nhật E/M riêng" if exits else f"{position.symbol}: dùng E/M chung")

    def bind_unknown(self, order_id, broker_id):
        order = self.store.order(order_id)
        if order.status != "UNKNOWN":
            raise ValueError("Chỉ gắn ID cho lệnh chưa rõ kết quả.")
        if any(o.id != order.id and o.broker_id == str(broker_id) for o in self.store.orders()):
            raise ValueError("ID DNSE đã thuộc một yêu cầu khác.")
        snapshot = self.broker.snapshot()
        matches = [r for r in snapshot.orders if r.get("broker_id") == str(broker_id)]
        if len(matches) != 1:
            raise ValueError("Chưa tìm thấy đúng một lệnh DNSE có ID này.")
        row = matches[0]
        if row.get("symbol") != order.symbol or row.get("exchange_side") != order.exchange_side or row.get("quantity") != order.quantity:
            raise ValueError("Mã/chiều/khối lượng DNSE không khớp yêu cầu.")
        with self.store.transaction():
            order.broker_id = str(broker_id)
            self._apply_update(order, row)
            self.store.event("RECONCILE", f"Operator gắn ID DNSE {broker_id} cho yêu cầu {order.id}")

    def cancel(self, order_id):
        order = self.store.order(order_id)
        if not order.pending or not order.broker_id:
            raise ValueError("Chưa thể hủy: lệnh đã kết thúc hoặc chưa xác định ID DNSE.")
        previous = order.status
        order.status = "CANCEL_PENDING"
        self.store.save_order(order)
        if order.source == "AUTO" and order.position_id:
            position = self.store.position(order.position_id)
            position.managed = False
            position.note = "Đã yêu cầu hủy lệnh tự động; quản lý vị thế tạm dừng."
            self.store.save_position(position)
        try:
            self.broker.cancel(order)
        except UnknownOutcome as exc:
            order.message = str(exc)
        except Exception:
            order.status = previous
            self.store.save_order(order)
            raise
        self.store.save_order(order)

    def replace(self, order_id, qty, price):
        self.poll(manage=False)
        self._ready()
        order = self.store.order(order_id)
        qty = quantity(qty)
        if not order.pending or not order.broker_id or order.kind != "LO" or qty < order.filled or price <= 0:
            raise ValueError("Chỉ sửa LO đang chờ, KL không nhỏ hơn đã khớp.")
        self._validate_limit("LO", price, self._quote(order.symbol))
        if order.action == "CLOSE":
            pos = self.store.position(order.position_id)
            available = pos.quantity - sum(o.remainder for o in self._pending_closes(pos.id, order.id))
            if qty - order.filled > available:
                raise ValueError("Sửa lệnh vượt khối lượng có thể đóng.")
        else:
            # Existing pending quantity is already reserved; validate only the extra.
            limit = self.preview(order.side, price)
            if qty - order.quantity > limit.maximum:
                raise ValueError("Sửa lệnh vượt sức mở.")
        prior = order.status
        order.status = "REPLACE_PENDING"
        order.replacement = {"quantity": qty, "price": price}
        self.store.save_order(order)
        try:
            self.broker.replace(order, qty, price)
        except UnknownOutcome as exc:
            order.message = str(exc)
        except Exception:
            order.status = prior
            order.replacement = None
            self.store.save_order(order)
            raise
        self.store.save_order(order)

    @staticmethod
    def _validate_limit(kind, price, quote):
        if kind != "LO":
            return
        if price <= 0 or abs(price * 10 - round(price * 10)) > 1e-6:
            raise ValueError("Giá LO phải đúng bước 0,1 điểm.")
        if (quote.floor and price < quote.floor) or (quote.ceiling and price > quote.ceiling):
            raise ValueError("Giá LO ngoài biên hợp đồng.")

    def _notify(self, text, key=None):
        # All order and protection events already live in the app LOG.
        # Only the independent signal backend may send Telegram messages.
        return None
