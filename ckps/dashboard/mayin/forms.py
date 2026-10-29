from __future__ import annotations
import tkinter as tk
from typing import Any
import customtkinter as ctk
from .widgets import FONT_KEY, FONT_VALUE, PALETTE, StableTabview
from .hover_hint import _HoverHint

class OriginalRuleForms:
    BG = '#181B20'
    SURFACE = '#22262D'
    BORDER = '#30353D'
    TEXT = '#E8EBEF'
    TITLE = PALETTE['TITLE']
    MUTED = '#C5CBD4'
    GREEN = '#22C55E'
    BLUE = '#2B6CB0'
    WARN = '#F59E0B'

    def _hint_icon(self, parent, text):
        if not text:
            return ctk.CTkLabel(parent, text='', width=1, height=1, fg_color='transparent')
        icon = ctk.CTkLabel(parent, text='?', width=20, height=20, font=('Segoe UI', 13, 'bold'),
                            fg_color=self.BLUE, text_color=self.TEXT, corner_radius=9, cursor='hand2')
        icon._hover_hint = _HoverHint(icon, text, click_to_toggle=True)
        return icon

    @staticmethod
    def _tab_font(tabview: ctk.CTkTabview, size: int) -> None:
        try:
            tabview._segmented_button.configure(font=('Segoe UI', size, 'bold'), text_color='#E8EBEF')
        except AttributeError:
            pass


    def _content(self, parent: ctk.CTkFrame, columns: int=3, *, weights: tuple[int, ...] | None=None) -> ctk.CTkScrollableFrame:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        body = ctk.CTkScrollableFrame(parent, fg_color='transparent', scrollbar_button_color=self.BORDER, scrollbar_button_hover_color='#4B515B')
        body.grid(row=0, column=0, sticky='nsew', padx=4, pady=4)
        for column in range(columns):
            if weights:
                body.grid_columnconfigure(column, weight=weights[column])
            else:
                body.grid_columnconfigure(column, weight=1, uniform='rule')
        body.grid_rowconfigure(1, weight=0)
        return body


    def _card(self, parent: ctk.CTkFrame, title: str, description: str, row: int, column: int, *, span: int=1, compact: bool=False) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=self.SURFACE, corner_radius=9, border_width=1, border_color=self.BORDER, height=1 if compact else 200)
        card.grid(row=row, column=column, columnspan=span, sticky='nsew', padx=4 if compact else 6, pady=4 if compact else 6)
        card._viking_compact = compact
        card.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(card, fg_color='transparent')
        header.pack(fill='x', padx=8 if compact else 12, pady=(6, 2) if compact else (8, 3))
        card._viking_header = header
        ctk.CTkLabel(header, text=title, height=22 if compact else 28, font=('Segoe UI', 13 if compact else 15, 'bold'), text_color=self.TITLE, anchor='w').pack(side='left')
        if description:
            self._hint_icon(header, description).pack(side='left', padx=(8, 0))
        return card

    def _field(self, card: ctk.CTkFrame, label: str, value: Any, hint: str, *, variable: tk.StringVar | None=None) -> ctk.CTkEntry:
        compact = getattr(card, '_viking_compact', False)
        row = ctk.CTkFrame(card, fg_color='transparent')
        row.pack(fill='x', padx=8 if compact else 12, pady=2 if compact else 3)
        row.grid_columnconfigure(0, weight=1)
        caption = ctk.CTkLabel(row, text=label, width=1, font=('Segoe UI', 12) if compact else FONT_KEY, text_color=self.TITLE, anchor='w', justify='left')
        caption.grid(row=0, column=0, sticky='ew')

        def wrap_caption(_event: Any) -> None:
            length = max(40, int(caption.winfo_width() / caption._get_widget_scaling()) - 4)
            if caption.cget('wraplength') != length:
                caption.configure(wraplength=length)
        caption.bind('<Configure>', wrap_caption, add='+')
        entry = ctk.CTkEntry(row, width=68 if compact else 92, height=27 if compact else 34, justify='right', font=('Segoe UI', 12) if compact else FONT_VALUE, fg_color='#181B20', border_color='#444B55', text_color=self.TEXT, textvariable=variable)
        if variable is None:
            entry.insert(0, str(value))
        entry.grid(row=0, column=1, padx=(8, 5))
        entry._hint_icon = self._hint_icon(row, hint)
        entry._hint_icon.grid(row=0, column=2)
        return entry

    def _dynamic_field(self, card: ctk.CTkFrame, label: str, value: float, enabled: bool, hint: str) -> tuple[ctk.CTkEntry, tk.BooleanVar]:
        """Keep each pre-ARM switch, value and explanation on one compact row."""
        compact=getattr(card,'_viking_compact',False)
        row = ctk.CTkFrame(card, fg_color='transparent')
        row.pack(fill='x', padx=6, pady=1 if compact else 3)
        row.grid_columnconfigure(1, weight=1)
        toggle = tk.BooleanVar(value=enabled)
        ctk.CTkSwitch(row, text='', width=36, variable=toggle, font=('Segoe UI', 11), progress_color=self.GREEN, button_color=self.TEXT, text_color=self.TEXT).grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(row, text=label, font=('Segoe UI', 11), text_color=self.TEXT, anchor='w').grid(row=0, column=1, sticky='w', padx=(2, 2))
        entry = ctk.CTkEntry(row, width=58, height=27 if compact else 30, justify='right', font=('Segoe UI', 12), fg_color='#181B20', border_color='#444B55', text_color=self.TEXT)
        entry.insert(0, str(value))
        entry.grid(row=0, column=2, padx=(2, 4))
        entry._hint_icon = self._hint_icon(row, hint)
        entry._hint_icon.grid(row=0, column=3)
        return (entry, toggle)

    def _switch(self, card: ctk.CTkFrame, label: str, value: bool, hint: str) -> tk.BooleanVar:
        compact = getattr(card, '_viking_compact', False)
        row = ctk.CTkFrame(card, fg_color='transparent')
        row.pack(fill='x', padx=8 if compact else 12, pady=3 if compact else 6)
        row.grid_columnconfigure(0, weight=1)
        variable = tk.BooleanVar(value=value)
        variable._viking_row = row
        ctk.CTkSwitch(row, text=label, variable=variable, font=('Segoe UI', 12), progress_color=self.GREEN, button_color=self.TEXT, text_color=self.TEXT).grid(row=0, column=0, sticky='w')
        variable._hint_icon = self._hint_icon(row, hint)
        variable._hint_icon.grid(row=0, column=1)
        return variable


    def _exit_manager_tab(self, frame: ctk.CTkFrame, *, include_signals=True) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        body = self._content(frame, columns=2)
        self.exit_body=body
        compact=not include_signals
        take = self._card(body, 'SL / TP', '', 1, 0, span=2,compact=compact)
        limits = ctk.CTkFrame(take, fg_color='transparent')
        limits.pack(fill='x', padx=4, pady=(0, 2 if compact else 6))
        limits.grid_columnconfigure((0, 1, 2), weight=1, uniform='exit-limits')
        limit_cells = []
        for column in range(3):
            cell = ctk.CTkFrame(limits, fg_color='transparent')
            cell.grid(row=0, column=column, sticky='nsew')
            cell._viking_compact=compact
            limit_cells.append(cell)
        self.initial_sl = self._field(limit_cells[0], 'SL (% GIÁ)', self.params.initial_sl_pct, 'Mức cắt lỗ theo % giá vốn bình quân. Nhập 0,25 hoặc -0,25: app dùng khoảng cách 0,25%. Giá vốn 2.000: Long cắt tại 1.995, Short tại 2.005, lỗ trước phí 500.000đ/HĐ. Không tính trên tiền hoặc NAV.')
        self.reentry_sl = self._field(limit_cells[1], 'LẶP (% GIÁ)', self.params.reentry_sl_pct, 'Khoảng giá giữa các lượt đóng = giá vốn × bước LẶP / 100. Chờ lệnh trước kết thúc, không gửi lặp cùng lượt; không phụ thuộc ký quỹ.')
        self.take_profit = self._field(limit_cells[2], 'TP (% GIÁ)', self.params.take_profit_pct, 'Mức tăng giá có lợi so với giá vốn bình quân; Long/Short đối xứng. Chạm mức thì đóng toàn bộ HĐ có thể đóng.')
        self.protect_card = self._card(body, 'BẢO VỆ HỢP ĐỒNG', 'DYNAMIC trước ARM; TSL bám đỉnh/đáy sau ARM. Khi BOT và quyền quản lý ON, mỗi lượt tự đóng 50% số HĐ còn lại, làm tròn xuống và tối thiểu 1 HĐ. Ví dụ 4 → 2 → 1 → 0 HĐ qua các lượt LẶP, không gửi liên tục cùng một mốc.', 2, 0, span=2,compact=compact)
        groups = ctk.CTkFrame(self.protect_card, fg_color='transparent')
        groups.pack(fill='x', padx=4, pady=(0, 0 if compact else 2))
        groups.grid_columnconfigure((0,1,2) if include_signals else (0,1), weight=1, uniform='protect-groups')
        self.exit_left_column = groups
        normal = self._card(groups, 'TSL / ARM', 'SAU ARM: bám đỉnh/đáy và tự đóng 50% HĐ còn lại khi giá lùi đến mốc, BOT và quyền quản lý đều ON.', 0, 0,compact=compact)
        self.protect_trail_card = normal
        self.normal_arm = self._field(normal, 'ARM (% GIÁ)', self.params.normal_arm_pct, 'Giá phải đi thuận lợi ít nhất ARM% so với giá vốn bình quân để bật TSL; đạt ARM chưa đóng ngay. Giá vốn 2.000, ARM 1%: Long đạt 2.020, Short đạt 1.980.')
        self.normal_giveback = self._field(normal, 'Lùi (% GIÁ)', self.params.normal_giveback_pct, 'Khoảng lùi = giá vốn × % Lùi / 100. Giá vốn 2.000, Lùi 0,25% là khoảng giá 5: Long đỉnh 2.020 thì mốc 2.015; Short đáy 1.980 thì mốc 1.985.')
        ctk.CTkLabel(normal, text='Đóng 50% HĐ còn lại', font=('Segoe UI',12), text_color=self.TITLE, anchor='w').pack(fill='x',padx=12,pady=4)
        self.normal_repeat = self._switch(normal, 'LẶP ĐÓNG', self.params.normal_repeat_enabled, 'Cho phép đóng tiếp sau khi lệnh trước kết thúc, theo Bước LẶP hoặc đỉnh/đáy mới.')
        self.repeat_switch = next((child for child in self.normal_repeat._viking_row.winfo_children() if isinstance(child, ctk.CTkSwitch)))
        dynamic_box = self._card(groups, 'DYNAMIC', 'TRƯỚC ARM: bảo vệ bằng ATR và/hoặc giữ lãi; tự đóng 50% HĐ còn lại khi đủ quyền. Nhường cho TSL khi đạt ARM. Telegram chỉ thông báo.', 0, 1,compact=compact)
        self.dynamic_settings_card = dynamic_box
        dynamic_header = dynamic_box._viking_header
        dynamic_header.pack_configure(padx=10, pady=(6, 4))
        dynamic_title = next((child for child in dynamic_header.winfo_children() if isinstance(child, ctk.CTkLabel) and child.cget('text') == 'DYNAMIC'))
        dynamic_title.configure(font=('Segoe UI', 13, 'bold'))
        self.normal_dynamic = tk.BooleanVar(value=self.params.normal_dynamic_enabled)
        ctk.CTkSwitch(dynamic_header, text='', width=36, variable=self.normal_dynamic, font=('Segoe UI', 12, 'bold'), progress_color=self.GREEN, button_color=self.TEXT, text_color=self.TEXT).pack(side='left', before=dynamic_title, padx=(0, 4))
        dynamic_groups = ctk.CTkFrame(dynamic_box, fg_color='transparent')
        dynamic_groups.pack(fill='x', padx=8, pady=(0, 2 if compact else 6))
        dynamic_groups.grid_columnconfigure(0, weight=1)
        atr_box = ctk.CTkFrame(dynamic_groups, fg_color='#20252C', corner_radius=7, border_width=1, border_color=self.BORDER)
        atr_box.grid(row=0, column=0, sticky='ew', pady=(0, 4))
        atr_box._viking_compact=compact
        self.dynamic_atr_card = atr_box
        ctk.CTkLabel(atr_box, text='ATR14 · PHIÊN TRƯỚC', font=('Segoe UI', 11, 'bold'), text_color='#60A5FA', anchor='w', height=18).pack(fill='x', padx=8, pady=(4, 0))
        self.normal_atr_activation_multiplier, self.normal_atr_activation_enabled = self._dynamic_field(atr_box, 'BẮT ĐẦU ×', self.params.normal_atr_activation_multiplier, self.params.normal_atr_activation_enabled, 'Bắt đầu khi lãi đạt ATR14 nến ngày đã đóng × hệ số. OFF: bắt đầu từ khi có lãi.')
        self.normal_atr_multiplier, self.normal_atr_trail_enabled = self._dynamic_field(atr_box, 'LÙI ĐỈNH ×', self.params.normal_atr_multiplier, self.params.normal_atr_trail_enabled, 'Khoảng lùi theo ATR14 × hệ số. Thiếu nến ATR thì chờ, không tự dựng mốc.')
        retention_box = ctk.CTkFrame(dynamic_groups, fg_color='#20252C', corner_radius=7, border_width=1, border_color=self.BORDER)
        retention_box.grid(row=1, column=0, sticky='ew')
        retention_box._viking_compact=compact
        self.dynamic_retention_card = retention_box
        ctk.CTkLabel(retention_box, text='GIỮ LÃI THEO ĐỈNH / ĐÁY', font=('Segoe UI', 11, 'bold'), text_color='#60A5FA', anchor='w', height=18).pack(fill='x', padx=8, pady=(4, 0))
        self.normal_retention_pct, self.normal_retention_enabled = self._dynamic_field(retention_box, 'GIỮ (% LÃI)', self.params.normal_retention_pct, self.params.normal_retention_enabled, 'Giữ phần trăm lãi đỉnh trước phí. Long giá vốn 2.000, đỉnh 2.020: giữ 70% của khoảng lãi 20 là mốc 2.014. Đây là % phần lãi, không phải % giá vốn.')
        self.normal_retention_until_pct, self.normal_retention_until_enabled = self._dynamic_field(retention_box, 'TỚI MFE (% GIÁ)', self.params.normal_retention_until_pct, self.params.normal_retention_until_enabled, 'Mức giá đi thuận lợi tối đa (% giá vốn) còn nâng mốc giữ lãi; OFF tiếp tục nâng tới trước ARM.')
        sale = ctk.CTkFrame(dynamic_groups, fg_color='#20252C', corner_radius=7)
        sale.grid(row=2, column=0, sticky='ew', pady=(5, 0))
        sale._viking_compact=compact
        ctk.CTkLabel(sale, text='Đóng 50% HĐ còn lại', font=('Segoe UI',12), text_color=self.TITLE, anchor='w').pack(fill='x',padx=8,pady=4)
        self.dynamic_repeat = self._switch(sale, 'LẶP', self.params.dynamic_repeat_enabled, 'Đóng tiếp khi giá đi bất lợi thêm đủ Bước LẶP và lệnh trước đã kết thúc.')
        repeat_row = self.dynamic_repeat._viking_row
        repeat_row.pack_configure(padx=6, pady=(2, 4))
        self.dynamic_repeat_switch = next((child for child in repeat_row.winfo_children() if isinstance(child, ctk.CTkSwitch)))
        self.dynamic_repeat_switch.configure(width=76, font=('Segoe UI', 11))
        self.dynamic_repeat_switch.grid_configure(column=0, padx=(0, 4))
        next((child for child in repeat_row.winfo_children() if isinstance(child, ctk.CTkLabel))).grid_configure(column=1)
