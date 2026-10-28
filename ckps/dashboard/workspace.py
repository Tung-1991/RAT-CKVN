"""Order and position editors share the main workspace, without extra windows."""
from dataclasses import asdict
import time
import tkinter as tk
import customtkinter as ctk

from ckps.models import FINAL, quantity
from .compact import CompactForm, columns
from .em_editor import ExitEditor
from .formatting import price
from .theme import BLUE, BORDER, GREEN, MUTED, RED, SLATE, SURFACE, SURFACE_2, TITLE


class WorkspaceMixin:
    def report(self, text, *, error=False):
        self.ui_events.append((time.time(), "LỖI" if error else "APP", str(text)))
        self.ui_events[:] = self.ui_events[-200:]
        self.ui_status = str(text), time.monotonic() + 8
        self.status.configure(text=str(text), text_color=RED if error else MUTED)

    def confirm(self, text, callback):
        self.clear_confirmation()
        book = (self.settings.mode,self.settings.account_no,self.settings.loan_package_id,self.runtime)
        self.confirmation.grid()
        self.confirmation.grid_columnconfigure(0, weight=1)
        label = ctk.CTkLabel(self.confirmation, text=text, anchor="w", justify="left",
            font=("Segoe UI", 11), wraplength=max(250, int(self.table_workspace.winfo_width() / self.table_workspace._get_widget_scaling()) - 240))
        label.grid(row=0, column=0, sticky="ew", padx=10, pady=7)
        def submit():
            self.clear_confirmation()
            try:
                current = (self.settings.mode,self.settings.account_no,self.settings.loan_package_id,self.runtime)
                if current != book or self.mode_requested or self.switch_pending:
                    raise ValueError('Sổ giao dịch đã thay đổi; kiểm tra và xác nhận lại thao tác.')
                callback()
            except Exception as exc:
                self.report(str(exc), error=True)
        self.confirm_primary = ctk.CTkButton(self.confirmation, text="XÁC NHẬN", width=105, height=30, command=submit)
        self.confirm_primary.grid(row=0, column=1, padx=5)
        ctk.CTkButton(self.confirmation, text="Bỏ qua", width=75, height=30, fg_color=SLATE,
            command=self.clear_confirmation).grid(row=0, column=2, padx=(0, 8))

    def clear_confirmation(self):
        for child in self.confirmation.winfo_children():
            child.destroy()
        self.confirmation.grid_remove()

    def show_editor(self, title, save_text, callback):
        self.clear_confirmation()
        self._workspace_editing = True
        self.info_panel.grid_remove()
        self.right.grid_rowconfigure(1, weight=1, minsize=0)
        self.right.grid_rowconfigure(2, weight=0, minsize=0)
        for child in self.detail_page.winfo_children():
            child.destroy()
        self.running_page.grid_remove()
        self.detail_page.grid()
        self.detail_page.grid_columnconfigure(0, weight=1)
        self.detail_page.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self.detail_page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=6)
        ctk.CTkLabel(header, text=title, font=("Segoe UI", 13, "bold"), text_color=TITLE).pack(side="left")
        ctk.CTkButton(header, text="← BẢNG LỆNH", width=115, height=27, fg_color=SLATE,
                      command=self.hide_editor).pack(side="right")
        self.editor_body = ctk.CTkFrame(self.detail_page, fg_color="transparent")
        self.editor_body.grid(row=1, column=0, sticky="nsew", padx=8)
        self.editor_footer = ctk.CTkFrame(self.detail_page, fg_color="transparent")
        self.editor_footer.grid(row=2, column=0, sticky="ew", padx=10, pady=7)
        self.editor_note = ctk.CTkLabel(self.editor_footer, text="", font=("Segoe UI", 11), text_color=MUTED)
        self.editor_note.pack(side="left")
        def save():
            try:
                callback()
            except Exception as exc:
                self.report(str(exc), error=True)
                self.editor_note.configure(text=str(exc), text_color=RED)
        self.editor_save = ctk.CTkButton(self.editor_footer, text=save_text, width=135, height=30, command=save)
        self.editor_save.pack(side="right")
        self.editor_variables = {}
        return CompactForm(self.editor_variables)

    def hide_editor(self):
        self.clear_confirmation()
        self.detail_page.grid_remove()
        self.running_page.grid()
        self._workspace_editing = False
        self.info_panel.grid()
        self._layout_preview()
        self._sync_selection()

    def current_position(self, position_id):
        raw = next((p for p in self.view.get("positions", []) if p["id"] == position_id), None)
        if raw is None:
            raise ValueError("Vị thế đã thay đổi hoặc đóng; chọn lại ở bảng lệnh.")
        return raw

    def position_exit(self):
        raw = self.selected(self.positions_tree, "positions")
        if not raw:
            return
        position_id = raw["id"]
        def save():
            self.current_position(position_id)
            values = None if self.inherit_exit.get() else self.position_editor.read()
            self.send("configure_position", position_id, values)
            self.hide_editor()
            self.report("Đã gửi cấu hình E/M vị thế.")
        self.show_editor(f"E/M · {raw['side']} {raw['symbol']} · {raw['quantity']} HĐ", "LƯU E/M", save)
        self.editor_body.grid_columnconfigure(0, weight=1)
        self.editor_body.grid_rowconfigure(1, weight=1)
        self.inherit_exit = tk.BooleanVar(value=raw.get("exit_overrides") is None)
        ctk.CTkSwitch(self.editor_body, text="Dùng RULE chung", variable=self.inherit_exit).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.position_editor = ExitEditor(self.editor_body, raw.get("exit_overrides") or self.settings.exit)
        self.position_editor.grid(row=1, column=0, sticky="nsew")
        self.inherit_exit.trace_add("write", lambda *_: self.position_editor.set_enabled(not self.inherit_exit.get()))
        self.position_editor.set_enabled(not self.inherit_exit.get())

    def close_position(self):
        raw = self.selected(self.positions_tree, "positions")
        if not raw:
            return
        reserved = sum(o["quantity"] - o["filled"] for o in self.view.get("orders", [])
            if o.get("position_id") == raw["id"] and o["action"] == "CLOSE" and o["status"] not in FINAL)
        available = max(0, raw["quantity"] - reserved)
        if not available:
            self.report("Toàn bộ HĐ đã có lệnh đóng đang chờ.", error=True)
            return
        def save():
            self.current_position(raw["id"])
            qty = quantity(self.editor_variables["qty"].get())
            kind = self.editor_variables["kind"].get()
            px = float(self.editor_variables["price"].get()) if kind == "LO" else 0
            if not 0 < qty <= available:
                raise ValueError(f"Khối lượng đóng phải từ 1 đến {available} HĐ.")
            def submit():
                self.send("close_position", raw["id"], qty, kind=kind, price=px)
                self.hide_editor()
            self.confirm(f"{self.settings.mode} · ĐÓNG {raw['side']} {raw['symbol']}\n{qty} HĐ · {kind} {price(px)}", submit)
        form = self.show_editor(f"ĐÓNG / GIẢM · {raw['side']} {raw['symbol']}", "XEM XÁC NHẬN", save)
        columns(self.editor_body)
        card = form.card(self.editor_body, f"CÓ THỂ ĐÓNG {available} HĐ")
        form.field(card, "qty", "Số HĐ đóng", available)
        form.field(card, "kind", "Loại lệnh", "MOK", choices=("LO", "MOK", "MTL"))
        form.field(card, "price", "Giá LO", self.view.get("quotes", {}).get(raw["symbol"], {}).get("last", 0))

    def edit_order(self):
        raw = self.selected(self.orders_tree, "orders")
        if not raw or raw["kind"] != "LO":
            return
        def save():
            qty, px = quantity(self.editor_variables["qty"].get()), float(self.editor_variables["price"].get())
            def submit():
                self.send("replace", raw["id"], qty, px)
                self.hide_editor()
            self.confirm(f"{self.settings.mode} · SỬA {raw['symbol']} · {raw['broker_id']}\n{qty} HĐ · LO {price(px)}", submit)
        form = self.show_editor("SỬA LO · " + raw["symbol"], "XEM XÁC NHẬN", save)
        columns(self.editor_body)
        card = form.card(self.editor_body, "THÔNG SỐ MỚI")
        form.field(card, "qty", "Tổng HĐ của lệnh", raw["quantity"])
        form.field(card, "price", "Giá LO", raw["price"])

    def bind_unknown(self):
        raw = self.selected(self.orders_tree, "orders")
        if not raw or raw["status"] != "UNKNOWN":
            return
        def save():
            value = self.editor_variables["id"].get().strip()
            if not value:
                raise ValueError("Nhập ID đã kiểm tra tại DNSE.")
            self.send("bind_unknown", raw["id"], value)
            self.hide_editor()
        form = self.show_editor("ĐỐI SOÁT · " + raw["symbol"], "GẮN ID", save)
        columns(self.editor_body)
        card = form.card(self.editor_body, "ID ĐÃ KIỂM TRA TẠI DNSE")
        form.field(card, "id", "ID lệnh", "", width=250)
