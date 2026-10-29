from dataclasses import asdict
import csv
from pathlib import Path
from tkinter import filedialog
from ckps.config import write_settings
from ckps.models import FINAL, ExitSettings, Position, Quote, Snapshot, Order, load_record, quantity
from .formatting import price, clock
from .theme import BORDER

class DashboardActionsMixin:
    def ticket_capacity(self, side, entry, rules):
        from ckps.trading.portfolio import Capacity, capacity
        data = self.view.get('account', {})
        if not data:
            return Capacity(0, 0, None, None, 'Chờ sức mở DNSE.')
        quote = self.view.get('quotes', {}).get(self.view.get('contract'), {})
        snapshot = Snapshot(self.view.get('contract', self.settings.alias), [], [], {},
            data.get('remaining_margin'), data.get('used_margin'), data.get('margin_per_contract'),
            data.get('qmax_long'), data.get('qmax_short'), nav=data.get('nav'),
            pending_margin=data.get('pending_margin'), margin_reference_price=data.get('margin_reference_price') or quote.get('last'),
            package_fees=data.get('package_fees',{}))
        positions = [load_record(Position, row) for row in self.view.get('positions', [])]
        orders = [load_record(Order, row) for row in self.view.get('orders', [])]
        if any(p.symbol == snapshot.contract and p.side != side for p in positions):
            return Capacity(0, 0, None, None, 'Đang giữ chiều ngược; đóng trước khi mở chiều mới.')
        return capacity(self.settings, snapshot, positions, orders, side, entry, rules)

    def selected(self, tree, key):
        selected = tree.selection()
        row = next((r for r in self.view.get(key, []) if selected and r["id"] == selected[0]), None)
        if row is None:
            self.report("Chọn một dòng ở bảng lệnh.")
        return row

    def open_order(self, side):
        try:
            if self.mode_requested or self.switch_pending:
                raise ValueError("Hoàn tất hoặc hủy cấu hình sổ giao dịch trước khi gửi lệnh.")
            qty = None if not self.qty.get().strip() else quantity(self.qty.get())
            px = float(self.limit.get()) if self.kind.get() == "LO" else 0.0
            if qty == 0:
                raise ValueError("Khối lượng phải lớn hơn 0.")
            entry = px or self.view.get("quotes", {}).get(self.view.get("contract", "VN30F1M"), {}).get("last", 0)
            rules, overrides = self.ticket_rules(entry)
            limit = self.ticket_capacity(side, entry, rules)
            qty = limit.maximum if qty is None else qty
            if not 0 < qty <= limit.maximum:
                raise ValueError(limit.reason or f'Tối đa {limit.maximum} HĐ.')
        except ValueError as exc:
            self.report(str(exc), error=True)
            return
        kind = self.kind.get()
        amount = f"{qty} HĐ"
        original = (self.qty.get(), self.limit.get(), self.kind.get(), self.ticket_sl.get(), self.ticket_tp.get(), self.view.get('contract'))
        confirmed_rules = asdict(rules)
        def submit():
            current = (self.qty.get(), self.limit.get(), self.kind.get(), self.ticket_sl.get(), self.ticket_tp.get(), self.view.get('contract'))
            if current != original:
                raise ValueError('Vé đã thay đổi; xem và xác nhận lại.')
            new_entry = px or self.view.get('quotes', {}).get(self.view.get('contract', 'VN30F1M'), {}).get('last', 0)
            new_rules, _ = self.ticket_rules(new_entry)
            new_limit = self.ticket_capacity(side, new_entry, new_rules)
            if asdict(new_rules) != confirmed_rules or new_limit.maximum < qty:
                raise ValueError('Sức mở hoặc E/M đã thay đổi; xem và xác nhận lại.')
            for before, after in ((limit.margin_per_contract, new_limit.margin_per_contract),
                                  (limit.risk_per_contract, new_limit.risk_per_contract)):
                if before is not None and (after is None or abs(after-before) > max(10_000, abs(before)*.01)):
                    raise ValueError('Ký quỹ hoặc rủi ro đã thay đổi; xem và xác nhận lại.')
            self.order_busy = True
            for button in self.open_buttons:
                button.configure(state="disabled")
            self.send("open_manual", side, qty, kind, px, exit_settings=overrides)
        from .formatting import money
        margin = money(limit.margin_per_contract * qty) if limit.margin_per_contract else 'chờ xác minh'
        loss = money(limit.risk_per_contract * qty) if limit.risk_per_contract is not None else 'chờ phí DNSE' if rules.sl_enabled else 'chưa có SL'
        self.confirm(f"{self.settings.mode} · {side} {self.view.get('contract', 'VN30F1M')} · {amount}\n"
                     f"{kind} {price(px)} · Ký quỹ {margin} · Lỗ tại SL ~{loss}"
                     + (' · Phí gói DNSE; thuế/phí Sở chờ đối chiếu' if self.settings.mode=='REAL' else ' · Phí mô phỏng'), submit)

    def manage_position(self):
        return self.settings_dialog('E/M', scope='VỊ THẾ')

    def cancel_order(self):
        raw = self.selected(self.orders_tree, "orders")
        if raw:
            self.confirm(f"{self.settings.mode} · HỦY PHẦN CHƯA KHỚP · {raw['symbol']}\nID {raw['broker_id'] or raw['id']}",
                         lambda: self.send("cancel", raw["id"]))

    def history(self):
        from .history import HistoryWindow
        return self.popup("history", lambda: HistoryWindow(self))

    def settings_dialog(self,page="RULE", *, scope=None):
        if page in {"KẾT NỐI","Kết nối","Hệ thống"}:
            window=self.connection()
            window.select_page("DNSE")
            return window
        from .mayin.rule_window import RuleWindow
        window=self.popup("rule",lambda:RuleWindow(self,page))
        window.select(page)
        if scope:
            window.select_scope(scope)
        return window

    def connection(self,requested_mode=None):
        from .mayin.connection_window import ConnectionWindow
        window=self.popup("connection",lambda:ConnectionWindow(self,requested_mode))
        if requested_mode:
            window.select_mode(requested_mode)
        return window

    def open_signal_backend(self):
        window = self.connection()
        window.select_page('TELEGRAM / LỊCH')
        return window

    def _mode_selected(self, mode):
        if self.switch_pending:
            self.mode_choice.set(self.switch_pending[0].mode)
            return
        if mode != self.settings.mode:
            self.clear_confirmation()
            self.mode_requested = mode
            self.connection(mode)
        else:
            self.mode_requested = None
            window = self.popups.get("connection")
            if window and window.winfo_exists():
                window.select_mode(mode)
        self.render()

    def toggle_bot(self):
        if not self.runtime:
            return
        if self.mode_requested or self.switch_pending:
            self.report("Hoàn tất hoặc hủy cấu hình sổ trước khi bật BOT.")
            return
        enabled = not self.bot_requested
        self.bot_requested = enabled
        if not enabled:
            self.runtime.engine.disarm()
            self.bot.configure(text="BOT OFF", fg_color=BORDER)
        self.send("arm", enabled)


    def popup(self, key, factory):
        existing = self.popups.get(key)
        if existing and existing.winfo_exists():
            existing.lift()
            return existing
        window = factory()
        self.popups[key] = window
        return window


    def save_config(self, settings):
        settings.validate()
        write_settings(settings)
        self.settings = settings
        self.send("settings", asdict(settings))

    def ticket_rules(self, entry):
        """Preview and submit share the same per-ticket SL/TP interpretation."""
        contract = self.view.get("contract", self.settings.alias)
        position = next((p for p in self.view.get("positions", []) if p["symbol"] == contract), None)
        pending = next((o for o in self.view.get("orders", []) if o["symbol"] == contract
                        and o["action"] == "OPEN" and o["status"] not in FINAL), None)
        inherited = (position.get("exit_overrides") or self.settings.exit) if position else (
            (pending or {}).get("exit_settings") or self.settings.exit)
        values = dict(inherited)
        changed = False
        for prefix, variable in (("sl", self.ticket_sl), ("tp", self.ticket_tp)):
            text = variable.get().strip().upper()
            if not text or text in {"AUTO", "RULE"}:
                continue
            if values.get('distance_unit','POINTS')!='PNL_PERCENT' and text!='OFF':
                raise ValueError('Lưu RULE sang % PNL trước khi ghi đè SL/TP trên vé.')
            changed = True
            if text == "OFF":
                values[prefix + "_enabled"] = False
                continue
            distance = abs(float(text.removesuffix("%")))
            if distance <= 0:
                raise ValueError("Khoảng SL/TP phải lớn hơn 0, hoặc nhập OFF.")
            if entry <= 0:
                raise ValueError("Chờ giá hợp lệ để tính SL/TP.")
            values[prefix + "_enabled"] = True
            values[prefix + "_distance"] = distance
        rules = load_record(ExitSettings, values).validate()
        return rules, asdict(rules) if changed else None


    def export_history(self):
        target = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile="VN30_HISTORY.csv", filetypes=[("CSV", "*.csv")])
        if not target:
            return
        try:
            with Path(target).open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(("Mode", "Closed at", "Contract", "Side", "Total contracts", "Entry", "Gross PnL", "Recorded fees", "Verified fills", "Source"))
                for p in self.view.get("history", []):
                    writer.writerow((self.settings.mode, clock(p["closed_at"]), p["symbol"], p["side"], p["original_quantity"], p["entry"], p["realized"] if p["pnl_verified"] else "", p["fees"], p["pnl_verified"], p["source"]))
        except OSError as exc:
            self.report(str(exc), error=True)
