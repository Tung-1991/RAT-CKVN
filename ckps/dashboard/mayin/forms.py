from __future__ import annotations
import tkinter as tk
from typing import Any
import customtkinter as ctk
from .widgets import FONT_KEY, FONT_VALUE, PALETTE, StableTabview, configure_changed
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
        icon = ctk.CTkLabel(parent, text='?', width=18, height=18, font=('Segoe UI', 11, 'bold'),
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
        card.grid(row=row, column=column, columnspan=span, sticky='new' if compact else 'nsew', padx=3 if compact else 6, pady=3 if compact else 6)
        card._viking_compact = compact
        card.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(card, fg_color='transparent')
        header.pack(fill='x', padx=8 if compact else 12, pady=(4, 1) if compact else (8, 3))
        card._viking_header = header
        ctk.CTkLabel(header, text=title, height=20 if compact else 28, font=('Segoe UI', 12 if compact else 15, 'bold'), text_color=self.TITLE, anchor='w').pack(side='left')
        if description:
            self._hint_icon(header, description).pack(side='left', padx=(8, 0))
        return card

    def _field(self, card: ctk.CTkFrame, label: str, value: Any, hint: str, *, variable: tk.StringVar | None=None) -> ctk.CTkEntry:
        compact = getattr(card, '_viking_compact', False)
        row = ctk.CTkFrame(card, fg_color='transparent')
        row.pack(fill='x', padx=8 if compact else 12, pady=2 if compact else 3)
        row.grid_columnconfigure(0, weight=1)
        caption = ctk.CTkLabel(row, text=label, width=1, height=24, font=('Segoe UI', 12 if compact else 14), text_color=self.TITLE, anchor='w', justify='left')
        caption.grid(row=0, column=0, sticky='ew')

        def wrap_caption(_event: Any) -> None:
            length = max(40, int(caption.winfo_width() / caption._get_widget_scaling()) - 4)
            if caption.cget('wraplength') != length:
                caption.configure(wraplength=length)
        caption.bind('<Configure>', wrap_caption, add='+')
        entry = ctk.CTkEntry(row, width=70 if compact else 92, height=28 if compact else 34, justify='right', font=('Segoe UI',14,'bold') if compact else FONT_VALUE, fg_color='#15202C', border_color='#3A526B', text_color=self.TEXT, textvariable=variable)
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
        if compact:take._viking_header.pack_forget()
        limits = ctk.CTkFrame(take, fg_color='transparent')
        limits.pack(fill='x', padx=4, pady=(0, 2 if compact else 6))
        limits.grid_columnconfigure((0, 1), weight=1, uniform='exit-limits')
        limit_cells = []
        for column in range(2):
            cell = ctk.CTkFrame(limits, fg_color='transparent')
            cell.grid(row=0, column=column, sticky='nsew')
            cell._viking_compact=compact
            limit_cells.append(cell)
        self.exit_limit_cells=limit_cells
        self.initial_sl = self._field(limit_cells[0], 'SL (% GIÁ)', self.params.initial_sl_pct, 'Mức cắt lỗ theo % giá vốn bình quân. Nhập 0,25 hoặc -0,25: app dùng khoảng cách 0,25%. Giá vốn 2.000: Long cắt tại 1.995, Short tại 2.005, lỗ trước phí 500.000đ/HĐ. Không tính trên tiền hoặc NAV.')
        self.take_profit = self._field(limit_cells[1], 'TP (% GIÁ)', self.params.take_profit_pct, 'Chốt toàn bộ theo % giá vốn. Giá vốn 2.000, TP 1%: Long chốt tại 2.020, Short tại 1.980. Chỉ tự đóng khi TP, BOT và quyền vị thế ON.')
        self.protect_card = self._card(body, 'BẢO VỆ HỢP ĐỒNG', 'DYNAMIC bảo vệ trước khi ARM đạt mức bắt đầu. ARM tự bám đỉnh/đáy sau mức đó. Chạm mốc khi BOT và quyền quản lý ON: đóng toàn bộ HĐ khả dụng, tiếp tục phần còn lại sau khi broker xác nhận. Không chia tỷ lệ hoặc chờ bước LẶP.', 2, 0, span=2,compact=compact)
        repeat_host=self.protect_card._viking_header if compact else self.protect_card
        repeat_host._viking_compact=compact
        self.reentry_sl = self._field(repeat_host, 'LẶP (điểm % PNL)', self.params.reentry_sl_pct, 'Khoảng lặp theo ký quỹ cơ sở/HĐ đã lưu: tiền/HĐ = cơ sở × bước LẶP / 100; điểm giá = tiền/HĐ ÷ 100.000. Chốt bớt không đổi cơ sở/HĐ. Áp dụng ARM và DYNAMIC, không mở lại lệnh.')
        if compact:
            self.reentry_sl.master.pack_configure(side='right',fill='none',padx=0,pady=0)
            self.reentry_sl.master.grid_columnconfigure(0,weight=0)
            next(w for w in self.reentry_sl.master.winfo_children() if isinstance(w,ctk.CTkLabel) and w.cget('text')).configure(width=150)
        self.reentry_sl.master.pack_forget()  # Keep legacy values for draft conversion only.
        self.pnl_basis_preview=ctk.CTkLabel(self.protect_card,text='',height=22,font=('Segoe UI',12,'bold'),anchor='w',justify='left',wraplength=650)
        self.pnl_basis_preview.pack(fill='x',padx=10,pady=(1,2))
        groups = ctk.CTkFrame(self.protect_card, fg_color='transparent')
        groups.pack(fill='x', padx=4, pady=(0, 0 if compact else 2))
        groups.grid_columnconfigure((0,1,2) if include_signals else (0,1), weight=1, uniform='protect-groups')
        self.exit_left_column = groups
        normal = self._card(groups, 'ARM', 'ARM gồm hai mức: Bắt đầu và Lùi. Lãi đủ mức Bắt đầu thì bám đỉnh Long/đáy Short; giá lùi đủ mức Lùi thì đóng toàn bộ HĐ khả dụng khi BOT và quyền quản lý ON.', 0, 0,compact=compact)
        self.protect_trail_card = normal
        self.normal_arm = self._field(normal, 'Bắt đầu (% PNL)', self.params.normal_arm_pct, 'Lãi chưa chốt / (ký quỹ cơ sở/HĐ × số HĐ còn giữ). Cơ sở 40 triệu/HĐ, Bắt đầu 5% là lãi 2 triệu/HĐ = 20 điểm giá. Từ mức này ARM bám đỉnh/đáy; giá lùi đủ mức Lùi mới đóng. Ký quỹ cơ sở không chạy theo tiền nạp/rút hoặc số dư.')
        self.normal_giveback = self._field(normal, 'Lùi (điểm % PNL)', self.params.normal_giveback_pct, 'Khoảng lùi tính bằng điểm phần trăm PNL trên ký quỹ cơ sở/HĐ. Đỉnh +10%, lùi 2 điểm % thì kích hoạt tại +8%. Cơ sở 40 triệu, lùi 1,25 điểm % = 500.000đ/HĐ = 5 điểm giá. Long bám đỉnh, Short bám đáy; trước phí.')
        self.pnl_distances_preview=ctk.CTkLabel(normal,text='',font=('Segoe UI',12),anchor='w',justify='left',wraplength=300)
        self.pnl_distances_preview.pack(fill='x',padx=8,pady=3)
        for widget in (self.pnl_basis_preview,self.pnl_distances_preview):
            widget.bind('<Configure>',lambda event,w=widget:configure_changed(w,wraplength=max(120,int(w.winfo_width()/w._get_widget_scaling())-4)),add='+')
        ctk.CTkLabel(normal, text='Đóng toàn bộ HĐ còn lại', font=('Segoe UI',12), text_color=self.TITLE, anchor='w').pack(fill='x',padx=12,pady=4)
        self.normal_repeat = self._switch(normal, 'LẶP ĐÓNG', self.params.normal_repeat_enabled, 'Cho phép đóng tiếp sau khi lệnh trước kết thúc, theo Bước LẶP hoặc đỉnh/đáy mới.')
        self.below_arm = self._switch(normal, 'LẶP DƯỚI ARM', self.params.arm_repeat_below_arm, 'Giữ cấu hình cũ; thoát toàn bộ không dùng bước lặp.')
        self.normal_repeat._viking_row.pack_forget()
        self.below_arm._viking_row.pack_forget()
        self.repeat_switch = next((child for child in self.normal_repeat._viking_row.winfo_children() if isinstance(child, ctk.CTkSwitch)))
        dynamic_box = self._card(groups, 'DYNAMIC', 'Bảo vệ trước ARM bằng ATR14 nến ngày đã đóng và/hoặc giữ lãi đỉnh. START quyết định lúc bắt đầu; Lùi ATR và Giữ lãi cùng bật thì chọn mốc bảo vệ chặt hơn. Tới MFE chỉ giới hạn nhánh giữ lãi; OFF giữ tới ARM. Mốc đã bảo vệ không tự nới khi đổi tham số. Chạm mốc thì đóng toàn bộ HĐ khả dụng khi đủ quyền.', 0, 1,compact=compact)
        self.dynamic_settings_card = dynamic_box
        dynamic_header = dynamic_box._viking_header
        dynamic_header.pack_configure(padx=8, pady=(4, 2))
        dynamic_title = next((child for child in dynamic_header.winfo_children() if isinstance(child, ctk.CTkLabel) and child.cget('text') == 'DYNAMIC'))
        dynamic_title.configure(font=('Segoe UI', 12, 'bold'))
        self.normal_dynamic = tk.BooleanVar(value=self.params.normal_dynamic_enabled)
        ctk.CTkSwitch(dynamic_header, text='', width=36, variable=self.normal_dynamic, font=('Segoe UI', 12, 'bold'), progress_color=self.GREEN, button_color=self.TEXT, text_color=self.TEXT).pack(side='left', before=dynamic_title, padx=(0, 4))
        for key,label,hint in (
            ('atr_start','START (× ATR)','Lãi đỉnh đạt hệ số này × ATR14 thì DYNAMIC bắt đầu. Tắt START: bắt đầu từ khi có lãi; nhánh Lùi ATR vẫn cần ATR hợp lệ.'),
            ('atr_trail','Lùi (× ATR)','Khoảng lùi từ đỉnh Long / đáy Short = hệ số × ATR14 (%). Dùng ATR từ nến ngày đã đóng, không dùng nến hôm nay.'),
            ('retention','Giữ lãi (%)','Giữ tỷ lệ % lãi đỉnh, không phải % giá vốn. Lãi đỉnh 10 điểm, giữ 70% đặt mốc còn lãi 7 điểm.'),
            ('retention_until','Tới MFE (% giá)','Giới hạn nhánh Giữ lãi khi lãi đỉnh chưa tới mức % giá vốn này. OFF: giữ lãi tới ARM. Mốc bảo vệ đã hình thành vẫn được giữ, không tự nới.')):
            attr={'atr_start':'atr_start_multiplier','atr_trail':'atr_trail_multiplier','retention':'retention_pct','retention_until':'retention_until'}[key]
            entry=self._field(dynamic_box,label,getattr(self.params,attr),hint)
            setattr(self,attr,entry)
            row=entry.master
            caption=next(w for w in row.winfo_children() if isinstance(w,ctk.CTkLabel) and w.cget('text'))
            caption.destroy()
            variable=tk.BooleanVar(value=getattr(self.params,key+'_enabled'))
            setattr(self,key+'_enabled',variable)
            ctk.CTkCheckBox(row,text=label,variable=variable,width=1,checkbox_width=18,checkbox_height=18,
                font=('Segoe UI',12),text_color=self.TITLE,command=self.render_atr).grid(row=0,column=0,sticky='w')
            entry.bind('<KeyRelease>',lambda _:self.render_atr(),add='+')
        dynamic_groups = ctk.CTkFrame(dynamic_box, fg_color='transparent')
        dynamic_groups.pack(fill='x', padx=8, pady=(0, 2 if compact else 6))
        dynamic_groups.grid_columnconfigure(0, weight=1)
        self.dynamic_atr_value=ctk.CTkLabel(dynamic_groups,text='',height=22,font=('Segoe UI',12,'bold'),text_color='#60A5FA',anchor='w',justify='left',wraplength=300)
        self.dynamic_atr_value.grid(row=0,column=0,sticky='ew',padx=0,pady=(3,1))
        self.dynamic_atr_detail=ctk.CTkLabel(dynamic_groups,text='',font=('Segoe UI',12),text_color=self.TEXT,anchor='w',justify='left',wraplength=300)
        self.dynamic_atr_detail.grid(row=1,column=0,sticky='ew',padx=0,pady=(0,3))
        for widget in (self.dynamic_atr_value,self.dynamic_atr_detail):
            widget.bind('<Configure>',lambda event,w=widget:w.configure(wraplength=max(120,int(w.winfo_width()/w._get_widget_scaling())-4)),add='+')
        sale = ctk.CTkFrame(dynamic_groups, fg_color='#20252C', corner_radius=7)
        sale.grid(row=2, column=0, sticky='ew', pady=(5, 0))
        sale._viking_compact=compact
        ctk.CTkLabel(sale, text='Đóng toàn bộ HĐ còn lại', font=('Segoe UI',12), text_color=self.TITLE, anchor='w').pack(fill='x',padx=8,pady=4)
        self.dynamic_repeat = self._switch(sale, 'LẶP', self.params.dynamic_repeat_enabled, 'Đóng tiếp khi giá đi bất lợi thêm đủ Bước LẶP và lệnh trước đã kết thúc.')
        repeat_row = self.dynamic_repeat._viking_row
        repeat_row.pack_configure(padx=6, pady=(2, 4))
        self.dynamic_repeat_switch = next((child for child in repeat_row.winfo_children() if isinstance(child, ctk.CTkSwitch)))
        self.dynamic_repeat_switch.configure(width=76, font=('Segoe UI', 11))
        self.dynamic_repeat_switch.grid_configure(column=0, padx=(0, 4))
        next((child for child in repeat_row.winfo_children() if isinstance(child, ctk.CTkLabel))).grid_configure(column=1)
        repeat_row.pack_forget()
