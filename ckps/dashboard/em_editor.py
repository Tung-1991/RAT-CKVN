"""The existing E/M controls presented as short pages; calculations unchanged."""
from dataclasses import asdict
import customtkinter as ctk
from ckps.models import ExitSettings, load_record
from .compact import CompactForm, columns, tabs


class ExitEditor(ctk.CTkFrame):
    def __init__(self, parent, values, *, variables=None):
        super().__init__(parent, fg_color="transparent")
        self.variables = variables if variables is not None else {}
        self.values = load_record(ExitSettings, values)
        form = CompactForm(self.variables)
        self.tabs = tabs(self)
        self.tabs.pack(fill="both", expand=True)
        common, arm, dynamic = (self.tabs.add(name) for name in ("SL / TP", "ARM", "DYNAMIC"))
        for page in (common, arm, dynamic):
            columns(page)
        def fields(host, specs):
            for spec in specs:
                key, label, *choices = spec
                form.field(host, key, label, getattr(self.values, key), choices=choices[0] if choices else None)
        a = form.card(common, "CẮT LỖ / CHỐT LỜI")
        fields(a, (("distance_unit", "Đơn vị", ("POINTS", "PERCENT")), ("sl_enabled", "Bật SL"),
                   ("sl_distance", "Khoảng SL"), ("tp_enabled", "Bật TP"), ("tp_distance", "Khoảng TP")))
        b = form.card(common, "QUYỀN THỰC THI", column=1)
        ctk.CTkLabel(b, text="BOT chung + quyền vị thế + nhánh E/M\nSL/TP đóng phần HĐ có thể đóng.\n1 HĐ × 33% = 1 HĐ.",
            justify="left", anchor="w", font=("Segoe UI", 12), height=92).grid(row=1, column=0, sticky="ew", padx=10, pady=8)
        a = form.card(arm, "KÍCH HOẠT / TRAILING")
        fields(a, (("arm_enabled", "Bật ARM"), ("arm_gain", "Lãi để ARM"), ("trail_gap", "Khoảng trailing"),
                   ("arm_policy", "Hành động", ("AUTO", "ALERT"))))
        b = form.card(arm, "KHỐI LƯỢNG / LẶP", column=1)
        fields(b, (("arm_close_pct", "Đóng (%)"), ("arm_basis", "Cơ sở", ("ORIGINAL", "REMAINING")),
                   ("arm_repeat", "Bật LẶP"), ("repeat_gap", "Bước lặp"), ("arm_repeat_below_arm", "Lặp dưới ARM")))
        a = form.card(dynamic, "DYNAMIC / ATR")
        fields(a, (("dynamic_enabled", "Bật DYNAMIC"), ("dynamic_policy", "Hành động", ("AUTO", "ALERT")),
                   ("atr_start_enabled", "Bật ATR START"), ("atr_start_multiplier", "START × ATR"),
                   ("atr_trail_enabled", "Bật ATR TRAIL"), ("atr_trail_multiplier", "TRAIL × ATR")))
        b = form.card(dynamic, "GIỮ LÃI / KHỐI LƯỢNG", column=1)
        fields(b, (("retention_enabled", "Bật giữ lãi"), ("retention_pct", "Giữ lãi (%)"),
                   ("retention_until_enabled", "Giới hạn vùng giữ"), ("retention_until", "Giữ tới mức"),
                   ("dynamic_close_pct", "Đóng (%)"), ("dynamic_basis", "Cơ sở", ("ORIGINAL", "REMAINING")),
                   ("dynamic_repeat", "Bật LẶP")))

    def read(self):
        values = asdict(self.values)
        for key in self.variables:
            old = values[key]
            value = self.variables[key].get()
            values[key] = bool(value) if isinstance(old, bool) else str(value) if isinstance(old, str) else float(value)
        return asdict(load_record(ExitSettings, values).validate())

    def set_enabled(self, enabled):
        def visit(widget):
            if getattr(widget, "_compact_control", False):
                widget.configure(state="normal" if enabled else "disabled")
            for child in widget.winfo_children():
                visit(child)
        visit(self)
