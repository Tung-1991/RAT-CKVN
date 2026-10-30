from __future__ import annotations
import tkinter as tk
from math import ceil
from typing import Any
import customtkinter as ctk
from .tokens import *
from .widgets import FONT_KEY, FONT_VALUE, FONT_MONO_VALUE, StatusLabel, fit_entry_text, fit_label_text, option_menu, choice_bar
from .hover_hint import _HoverHint
APP_NAME = 'RAT VN30'
APP_VERSION = '0.1.0'
INFO_PANEL_HEIGHT = 260

class OriginalPanels:

    def _left_panel(self) -> None:
        account = ctk.CTkFrame(self.left, fg_color=COL_SURFACE, corner_radius=10, border_width=1, border_color=COL_BORDER)
        account.pack(fill='x', pady=(2, 3), padx=6)
        account.grid_columnconfigure(0, weight=1)
        account.grid_columnconfigure(1, weight=0, minsize=180)
        nav_header = ctk.CTkFrame(account, fg_color='transparent')
        nav_header.grid(row=0, column=0, sticky='ew', padx=11, pady=(4, 0))
        self.lbl_equity_title = ctk.CTkLabel(nav_header, text='KÝ QUỸ', font=('Segoe UI', 13, 'bold'), text_color=COL_MUTED, anchor='w')
        self.lbl_equity_title.pack(side='left')
        self.btn_refresh_account = ctk.CTkButton(nav_header, text='↻', width=32, height=25, font=('Segoe UI', 13, 'bold'), fg_color='#282D34', hover_color='#3A414B', text_color=COL_TEXT, corner_radius=6, command=self._refresh_account_now)
        self.btn_refresh_account.pack(side='right', padx=(4, 0))
        self.lbl_equity = ctk.CTkLabel(account, text='----', font=('Segoe UI', 24, 'bold'), text_color=COL_GREEN, anchor='w')
        self.lbl_equity.grid(row=1, column=0, sticky='ew', padx=(11, 5), pady=(0, 0))
        self.lbl_equity.bind('<Configure>', lambda _event: fit_label_text(self.lbl_equity, base_font=('Segoe UI', 24, 'bold'), minimum_size=14), add='+')
        session_box = ctk.CTkFrame(account, width=180, height=52, fg_color='transparent')
        session_box.grid(row=0, column=1, rowspan=2, sticky='ne', padx=(3, 11), pady=(7, 0))
        session_box.pack_propagate(False)
        self.lbl_session = ctk.CTkLabel(session_box, text='PHIÊN: --', font=('Segoe UI', 13, 'bold'), text_color=COL_MUTED, anchor='e', justify='right', width=176)
        self.lbl_session.pack(fill='x')
        self.lbl_brain = ctk.CTkLabel(session_box, text='DAEMON: CHỜ', font=('Segoe UI', 13, 'bold'), text_color=COL_WARN, anchor='e')
        self.lbl_brain.pack(fill='x', pady=(2, 0))
        self.lbl_account = ctk.CTkLabel(account, text=f'ID: {self.account_id}  ·  PAPER', font=('Segoe UI', 13, 'bold'), text_color=COL_TEXT, anchor='w', justify='left')
        self.lbl_account.grid(row=3, column=0, columnspan=2, sticky='ew', padx=(11, 11), pady=(3, 6))
        account_footer = ctk.CTkFrame(account, fg_color='transparent')
        account_footer.grid_columnconfigure(0, minsize=82)
        account_footer.grid_columnconfigure(1, minsize=120)
        account_footer.grid_columnconfigure(2, weight=1)
        self.lbl_pnl = ctk.CTkLabel(account_footer, text='PNL: ĐANG TÍNH', font=('Segoe UI', 12, 'bold'), anchor='w')
        self.lbl_pnl.grid(row=0, column=0, sticky='w')
        self.lbl_cash = ctk.CTkLabel(account, text='Tổng tiền: —', font=('Segoe UI', 15, 'bold'), text_color='#A9C5E2', anchor='w')
        self.lbl_cash.grid(row=2, column=0, columnspan=2, sticky='ew', padx=11, pady=(0, 1))

        def fit_stats(_event=None):
            fit_label_text(self.lbl_cash, base_font=('Segoe UI', 15, 'bold'), minimum_size=15)
        self._fit_account_stats = fit_stats
        account_footer.bind('<Configure>', fit_stats, add='+')
        control = ctk.CTkFrame(self.left, fg_color=COL_SURFACE, corner_radius=10, border_width=1, border_color=COL_BORDER)
        control.pack(fill='x', padx=6, pady=4)
        control.columnconfigure(0, minsize=64)
        control.columnconfigure(1, weight=1)

        def setting_row(index: int, label: str) -> ctk.CTkFrame:
            padding = (8 if index == 0 else 3, 8 if index == 2 else 3)
            ctk.CTkLabel(control, text=label, font=FONT_KEY, text_color=COL_TITLE, anchor='w', justify='left').grid(row=index, column=0, sticky='ew', padx=(10, 8), pady=padding)
            frame = ctk.CTkFrame(control, width=1, height=36, fg_color='transparent')
            frame.grid(row=index, column=1, sticky='ew', padx=(0, 10), pady=padding)
            frame.grid_propagate(False)
            frame.grid_rowconfigure(0, weight=1)
            return frame
        symbol_row = setting_row(0, 'HĐTL')
        symbol_row.grid_columnconfigure(0, weight=1)
        self.symbol = tk.StringVar(value='VN30F1M')
        self.symbol_entry = ctk.CTkLabel(symbol_row, text='VN30F1M', font=FONT_BOLD, height=36, corner_radius=7, fg_color=COL_SURFACE_2)
        self.symbol_entry.grid(row=0, column=0, sticky='nsew')
        mode_row = setting_row(1, 'MODE')
        mode_row.grid_columnconfigure(0, weight=2, uniform='mode-action')
        mode_row.grid_columnconfigure(1, weight=1, uniform='mode-action')
        self.mode = tk.StringVar(value='PAPER')
        self.mode_selector = choice_bar(mode_row, values=['PAPER', 'REAL'], variable=self.mode, command=self._mode_changed, width=1, selected_color=COL_GREEN, selected_hover_color='#16A34A')
        self.mode_selector.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        self.bot_button = ctk.CTkButton(mode_row, text='BOT · OFF', height=36, font=('Segoe UI', 14, 'bold'), width=1, fg_color=COL_GRAY, hover_color='#4B515B', border_width=1, border_color='#47505D', corner_radius=7, command=self._toggle_bot)
        self.bot_button.grid(row=0, column=1, sticky='nsew')
        tools_row = setting_row(2, 'TOOLS')
        tool_specs = [('RULE', self._rule_settings), ('KẾT NỐI', self._advanced)]
        for column, (text, command) in enumerate(tool_specs):
            tools_row.grid_columnconfigure(column, weight=1, uniform='tool')
            button = ctk.CTkButton(tools_row, text=text, height=36, font=('Segoe UI', 14, 'bold'), width=1, fg_color='#24384C', hover_color='#2F4F70', text_color='#C5DDF7', border_width=1, border_color='#38536F', corner_radius=7, command=command)
            button.grid(row=0, column=column, sticky='nsew', padx=(0 if column == 0 else 3, 3 if column == 0 else 0))
            if column == 0:
                self.rule_button = button
            else:
                self.connection_button = button
        order = ctk.CTkFrame(self.left, fg_color=COL_SURFACE, corner_radius=10, border_width=1, border_color=COL_BORDER)
        order.pack(fill='x', padx=6, pady=3)
        quote = ctk.CTkFrame(order, fg_color=COL_SURFACE_2, corner_radius=8)
        quote.pack(fill='x', padx=8, pady=(7, 4))
        quote.grid_columnconfigure(0, weight=1)
        quote.grid_columnconfigure(1, weight=1)
        self.lbl_quote_symbol = ctk.CTkLabel(quote, text=self.symbol.get(), width=72, height=30, font=('Segoe UI', 16, 'bold'), fg_color='#2B3D51', corner_radius=7, text_color='#C4DFFA', anchor='center')
        self.lbl_quote_symbol.grid(row=0, column=0, sticky='w', padx=(11, 5), pady=(6, 0))
        change_box = ctk.CTkFrame(quote, fg_color='transparent')
        change_box.grid(row=0, column=1, sticky='e', padx=(5, 9), pady=(6, 0))
        self.lbl_change = ctk.CTkLabel(change_box, text='--', font=FONT_MONO_VALUE, text_color=COL_MUTED, anchor='e')
        self.lbl_change.pack(side='left')
        self.lbl_price = ctk.CTkLabel(quote, text='---', font=('Cascadia Mono', 24, 'bold'), text_color=COL_TEXT, anchor='center', corner_radius=4)
        self.lbl_price.grid(row=1, column=0, columnspan=2, sticky='ew', padx=10, pady=(0, 0))
        self.lbl_market = ctk.CTkLabel(quote, text='CHỜ DỮ LIỆU', font=('Segoe UI', 15, 'bold'), text_color=COL_WARN, anchor='center')
        self.lbl_market.grid(row=2, column=0, columnspan=2, sticky='ew', padx=10, pady=(0, 5))
        preview = ctk.CTkFrame(quote, fg_color='transparent')
        preview.grid(row=3, column=0, columnspan=2, sticky='ew', padx=7, pady=(0, 6))
        preview.grid_columnconfigure(0, weight=1)
        pnl_panel = ctk.CTkFrame(preview, fg_color='#1B1F25', corner_radius=7)
        pnl_panel.grid(row=0, column=0, sticky='ew')
        pnl_panel.grid_columnconfigure((0, 1, 2), weight=1, uniform='pnl_preview')
        pnl_specs = (('TP · đ', 'lbl_tp_title', 'lbl_tp_preview', COL_GREEN), ('SL · đ', 'lbl_sl_title', 'lbl_sl_preview', COL_RED), ('PHÍ · đ', 'lbl_fee_title', 'lbl_fee_preview', COL_WARN))
        for column, (title, title_attr, value_attr, title_color) in enumerate(pnl_specs):
            box = ctk.CTkFrame(pnl_panel, fg_color='transparent')
            box.grid(row=0, column=column, sticky='nsew', padx=5, pady=5)
            title_label = ctk.CTkLabel(box, text=title, font=FONT_PREVIEW_TITLE, height=22, text_color=title_color, anchor='center')
            title_label.pack(fill='x')
            label = ctk.CTkLabel(box, text='NA', font=FONT_PREVIEW_VALUE, text_color=title_color, anchor='center', height=32,wraplength=110)
            label.pack(fill='x')
            setattr(self, title_attr, title_label)
            setattr(self, value_attr, label)
        money_panel = ctk.CTkFrame(preview, fg_color='#1B1F25', corner_radius=7)
        money_panel.grid(row=1, column=0, sticky='ew', pady=(5, 0))
        money_panel.grid_columnconfigure(1, weight=1)
        self.lbl_order_value_title = ctk.CTkLabel(money_panel, text='KÝ QUỸ + PHÍ', font=FONT_PREVIEW_TITLE, height=28, text_color=COL_PREVIEW_TEXT, anchor='w')
        self.lbl_order_value_title.grid(row=0, column=0, sticky='w', padx=(12, 6), pady=2)
        self.lbl_order_value = ctk.CTkLabel(money_panel, text='NA', font=FONT_PREVIEW_VALUE, height=28, text_color=COL_PREVIEW_TEXT, anchor='e')
        self.lbl_order_value.grid(row=0, column=1, sticky='e', padx=(6, 12), pady=2)
        action = ctk.CTkFrame(order, width=1, height=38, fg_color='transparent')
        action.pack(fill='x', padx=9, pady=(1, 4))
        action.grid_propagate(False)
        action.grid_columnconfigure((1, 2), weight=1, uniform='direction')
        self.order_type = tk.StringVar(value='LO')
        self.order_type_menu = option_menu(action, values=['LO', 'MOK', 'MTL'], variable=self.order_type, command=self._order_type_changed, width=115, height=38)
        self.order_type_menu.grid(row=0, column=0, sticky='ew', padx=(0, 7))
        self.execute_button = ctk.CTkButton(action, text='LONG', font=('Segoe UI', 13, 'bold'), height=38, fg_color='#16A34A', hover_color='#15803D', border_width=1, border_color=COL_GREEN, corner_radius=8, command=lambda: self._submit('BUY'))
        self.execute_button.grid(row=0, column=1, sticky='ew')
        self.short_button = ctk.CTkButton(action, text='SHORT', font=('Segoe UI', 13, 'bold'), height=38, width=1, fg_color='#B91C1C', hover_color='#991B1B', border_width=1, border_color=COL_RED, corner_radius=8, command=lambda: self.open_order('SHORT'))
        self.short_button.grid(row=0, column=2, sticky='ew', padx=(7, 0))
        form = ctk.CTkFrame(order, fg_color='transparent')
        form.pack(fill='x', padx=8, pady=(1, 5))
        form.grid_columnconfigure((0, 1), weight=1, uniform='manual_input')
        self.quantity = self._manual_input(form, 0, 'HĐ · AUTO', '', placeholder='AUTO', row=0)
        self.quantity.bind('<FocusOut>', lambda _event: self._update_order_preview(), add='+')
        self.price = self._manual_input(form, 1, 'GIÁ LO', '', row=0)
        self.tp = self._manual_input(form, 0, 'TP % GIÁ', self._default_tp_text(), dimmed=True, row=1)
        self.sl = self._manual_input(form, 1, 'SL % GIÁ', 'RULE', dimmed=True, row=1)
        entries = (self.quantity, self.price)
        for entry in entries:
            entry.bind('<KeyRelease>', lambda _event: self._update_order_preview(), add='+')
            entry.bind('<KeyPress>', lambda _event, widget=entry: widget.configure(text_color=COL_TEXT), add='+')
        self.price.bind('<FocusIn>', self._activate_lo_input, add='+')
        self.quantity.bind('<Tab>', lambda _event: self._focus_widget(self.price if self.order_type.get() == 'LO' else self.execute_button))
        self.price.bind('<Tab>', lambda _event: self._focus_widget(self.execute_button))
        self.execute_button.bind('<Tab>', lambda _event: self._focus_widget(self.quantity))
        self.quantity.bind('<Shift-Tab>', lambda _event: self._focus_widget(self.execute_button))
        self.price.bind('<Shift-Tab>', lambda _event: self._focus_widget(self.quantity))
        self.execute_button.bind('<Shift-Tab>', lambda _event: self._focus_widget(self.price if self.order_type.get() == 'LO' else self.quantity))
        self.execute_button.bind('<Return>', lambda _event: self.execute_button.invoke())
        self.execute_button.bind('<space>', lambda _event: self.execute_button.invoke())
        self._sync_default_sl(force=True, refresh=False)
        self._update_order_preview()
        brand = ctk.CTkFrame(self.left, fg_color='transparent')
        brand.pack(fill='x', padx=6, pady=(1, 0))
        ctk.CTkLabel(brand, text=f'{APP_NAME} · v{APP_VERSION}', font=('Segoe UI', 16, 'bold'), text_color='#92B2D1').pack()

    @staticmethod
    def _manual_input(frame: ctk.CTkFrame, column: int, label: str, value: str, disabled: bool=False, *, placeholder: str='', dimmed: bool=False, row: int=0) -> ctk.CTkEntry:
        box = ctk.CTkFrame(frame, width=1, fg_color=COL_SURFACE_2, corner_radius=8, border_width=1, border_color=COL_BORDER)
        box.grid_columnconfigure(1, weight=1)
        box.grid(row=row, column=column, padx=(0 if column == 0 else 4, 0), pady=(0, 4), sticky='ew')
        title_widget = ctk.CTkLabel(box, text=label, width=96, font=FONT_KEY, text_color=COL_TITLE, anchor='w')
        title_widget.grid(row=0, column=0, sticky='w', padx=(8, 2), pady=4)
        entry = ctk.CTkEntry(box, width=1, font=FONT_MONO_VALUE, height=32, justify='right', fg_color='#1A1E23', border_width=0, text_color=COL_MUTED if dimmed else COL_TEXT, placeholder_text=placeholder, placeholder_text_color=COL_MUTED, takefocus=True)
        entry.insert(0, value)
        entry.grid(row=0, column=1, sticky='ew', padx=(2, 5), pady=4)
        entry._viking_title_widget = title_widget
        entry._viking_editing = False
        entry.bind('<FocusIn>', lambda _event: setattr(entry, '_viking_editing', True), add='+')
        entry.bind('<FocusOut>', lambda _event: setattr(entry, '_viking_editing', False), add='+')
        for click_target in (box, title_widget, entry._canvas):
            click_target.bind('<Button-1>', lambda _event: entry.focus_set(), add='+')

        def fit_current_text(_event: Any=None) -> None:
            shown = str(entry.get() or entry.cget('placeholder_text') or '')
            fit_entry_text(entry, shown)
        entry.bind('<Configure>', fit_current_text, add='+')
        entry.bind('<KeyRelease>', fit_current_text, add='+')
        entry._viking_fit_text = fit_current_text
        entry.after_idle(fit_current_text)
        if disabled:
            entry.configure(state='disabled')
        return entry

    def _build_order_preview_tab(self,parent):
        parent.grid_columnconfigure(0,weight=1)
        parent.grid_rowconfigure(0,weight=1)
        panel=ctk.CTkFrame(parent,width=1,fg_color='transparent')
        panel.grid(row=0,column=0,sticky='nsew')
        panel.grid_columnconfigure(0,weight=1)
        self.preview_focus_panel=self.preview_content=panel
        data=ctk.CTkFrame(panel,width=1,fg_color='transparent')
        data.grid(row=0,column=0,sticky='new')
        data.grid_columnconfigure(0,weight=1)
        self.preview_data=data
        self._preview_help={'arm':'','dynamic':''}
        self._preview_position_context=''
        self._preview_fit_labels=[]
        def label(parent,name,text='',size=16,color='#BDD4EC',bold=True,mono=False,**grid):
            font=('Cascadia Mono' if mono else 'Segoe UI',size,*(['bold'] if bold else []))
            widget=StatusLabel(parent,text=text,width=1,height=size+5,font=font,text_color=color,anchor='w')
            widget.grid_propagate(False)
            widget.grid(sticky='ew',**grid)
            # CTkLabel.bind targets its inner label/canvas. Observe the outer
            # allocation and Map as well: restored hidden rows may reuse inner
            # dimensions without another Configure on those children.
            tk.Misc.bind(widget,'<Configure>',self._queue_preview_layout,add='+')
            tk.Misc.bind(widget,'<Map>',self._queue_preview_layout,add='+')
            setattr(self,name,widget);self._preview_fit_labels.append((widget,font))
            return widget
        self.market_context_label=ctk.CTkLabel(self.info_header,text='CHỈ THAM KHẢO',height=28,
            font=('Segoe UI',15,'bold'),text_color='#9BB9D8',anchor='e')
        self.market_context_label.grid(row=0,column=1,sticky='ew',padx=(8,10))
        signals=ctk.CTkFrame(data,fg_color='transparent')
        signals.grid(row=0,column=0,sticky='ew',pady=(0,7))
        signals.grid_columnconfigure((0,1),weight=1,uniform='signals')
        self.preview_signal_cards=[]
        for column,prefix,title in ((0,'entry','ĐIỂM VÀO'),(1,'trend','THỊ TRƯỜNG')):
            card=ctk.CTkFrame(signals,width=1,height=112,fg_color='#1B2939',corner_radius=8,
                border_width=1,border_color=COL_GRID)
            card.grid(row=0,column=column,sticky='nsew',padx=(0,4) if column==0 else (4,0))
            card.grid_columnconfigure(0,weight=1)
            label(card,'preview_'+prefix+'_title',title,size=14,color='#B8D7F8',bold=True,row=0,column=0,padx=15,pady=(12,3))
            label(card,'preview_'+prefix+'_value','CHỜ',size=22,bold=True,row=1,column=0,padx=15,pady=5)
            label(card,'preview_'+prefix+'_detail','Chờ dữ liệu',size=16,row=2,column=0,padx=15,pady=(2,12))
            self.preview_signal_cards.append(card)
        metadata=ctk.CTkFrame(data,fg_color='transparent')
        metadata.grid(row=1,column=0,sticky='ew',pady=(2,7))
        metadata.grid_columnconfigure(0,weight=2,uniform='preview-metadata')
        metadata.grid_columnconfigure(1,weight=1,uniform='preview-metadata')
        atr=ctk.CTkFrame(metadata,width=1,fg_color='#1A2A3C',border_width=1,border_color='#344E6C',corner_radius=7)
        atr.grid(row=0,column=0,sticky='nsew',padx=(0,4))
        atr.grid_columnconfigure(0,weight=1)
        self.preview_atr=atr
        label(atr,'preview_atr_title','DYNAMIC · ATR14',size=14,color='#9EBEE1',bold=True,row=0,column=0,padx=12,pady=(8,0))
        label(atr,'preview_atr_value','ATR14 · CHỜ NẾN 1D',size=16,color=COL_WARN,bold=True,row=1,column=0,padx=12,pady=(4,2))
        label(atr,'preview_atr_detail','',size=16,color='#DCC59E',row=2,column=0,padx=12,pady=(1,9))
        atr._hover_hint=_HoverHint(atr,lambda:'ATR14 lấy cùng nến 1D đã đóng mà backend dùng cho DYNAMIC; ngày phiên đi kèm số ATR. Không lấy nến đang chạy. Bắt đầu = 0,5 × ATR%; lùi ATR = 0,8 × ATR%, giữ 70% lãi đỉnh. Các mốc vào/thoát chỉ tham khảo; BOT và quyền quản lý vẫn quyết định có gửi lệnh hay không.',click_to_toggle=True,hover=False)
        authentication=ctk.CTkFrame(metadata,width=1,fg_color='#202B31',border_width=1,border_color='#3D555F',corner_radius=7)
        authentication.grid(row=0,column=1,sticky='nsew',padx=(4,0))
        authentication.grid_columnconfigure(0,weight=1)
        self.preview_authentication=authentication
        label(authentication,'preview_auth_title','XÁC THỰC',size=14,color='#AFC7D1',bold=True,row=0,column=0,padx=12,pady=(8,0))
        self.preview_connection=label(authentication,'preview_connection_status',size=16,color='#B8D3E3',
            row=1,column=0,padx=12,pady=(6,10))
        management=ctk.CTkFrame(data,width=1,fg_color='transparent')
        management.grid(row=3,column=0,sticky='new')
        management.grid_columnconfigure(0,weight=1)
        self.preview_management=management
        header=ctk.CTkFrame(management,fg_color='transparent')
        header.grid(row=0,column=0,sticky='ew',pady=(2,4))
        header.grid_columnconfigure(0,weight=1)
        title=label(header,'preview_order_title','BẢO VỆ VỊ THẾ',14,COL_MUTED,True,row=0,column=0,padx=9,pady=4)
        title.configure(cursor='hand2')
        title._hover_hint=_HoverHint(title,lambda:self._preview_position_context,click_to_toggle=True,hover=False)
        label(header,'preview_rule_source',size=14,color=COL_MUTED,row=0,column=1,padx=9,pady=4).configure(width=100)
        for index,prefix,title,color in ((0,'normal','TSL / ARM',COL_ACCENT_BLUE),(1,'exit','DYNAMIC',COL_WARN)):
            row=ctk.CTkFrame(management,width=1,fg_color=COL_PANEL_BODY,corner_radius=4)
            row.grid(row=index+1,column=0,sticky='ew',pady=(0,3))
            row.grid_columnconfigure(0,minsize=112)
            row.grid_columnconfigure(1,weight=1,minsize=150)
            row.grid_columnconfigure(2,weight=2,minsize=170)
            name='preview_em_normal' if index==0 else 'preview_em_exit'
            caption=label(row,name,title+'  ⓘ',size=14,color=color,bold=True,row=0,column=0,padx=(10,8),pady=9)
            caption.configure(cursor='hand2',width=112)
            key='arm' if index==0 else 'dynamic'
            caption._hover_hint=_HoverHint(caption,lambda key=key:self._preview_help[key],click_to_toggle=True,
                fixed_size=True,max_width=480,font=('Segoe UI',15),hover=False)
            label(row,'preview_'+prefix+'_value',size=16,row=0,column=1,padx=8,pady=9)
            label(row,'preview_'+prefix+'_detail',size=16,row=0,column=2,padx=(8,10),pady=9)
        management.grid_remove()
        panel.bind('<Configure>',self._fit_preview_text,add='+')
        data.bind('<Configure>',self._layout_preview,add='+')
        self.right.bind('<Configure>',self._layout_preview,add='+')
        self.after_idle(self._layout_preview)

    def _fit_preview_text(self,_event=None):
        """Keep fixed type sizes; wrap long text instead of shrinking it."""
        for widget,font in self._preview_fit_labels:
            if not widget.cget('text'):
                if widget.winfo_manager():widget.grid_remove()
                continue
            if not widget.winfo_manager():widget.grid()
            if widget.winfo_width()>30:
                length=max(30,int(widget.winfo_width()/widget._get_widget_scaling())-4)
                if widget.cget('wraplength')!=length:widget.configure(wraplength=length)
                height=max(font[1]+5,ceil(widget._label.winfo_reqheight()/widget._get_widget_scaling()))
                if widget.cget('height')!=height:widget.configure(height=height)

    def _queue_preview_layout(self,_event=None):
        if getattr(self,'_preview_layout_after',None):return
        def settle():
            self._preview_layout_after=None
            self._layout_preview()
        self._preview_layout_after=self.after(25,settle)

    def _layout_preview(self,_event=None):
        if getattr(self,'_workspace_editing',False):return
        scale=self.right._get_widget_scaling()
        # Use requested children, not the currently allocated viewport: that
        # viewport may still have the previous size during a DPI/selection change.
        overhead=self.info_header.winfo_reqheight()+round(20*scale)
        if hasattr(self,'status') and self.status.winfo_manager():
            overhead+=self.status.winfo_reqheight()+round(11*scale)
        required=ceil((self.preview_data.winfo_reqheight()+overhead)/scale)+2
        # Reserve the short protection block as soon as a position is selected.
        # Tk may still report its previous (hidden) requested size in this turn.
        height=max(340 if self.preview_management.winfo_manager() else INFO_PANEL_HEIGHT,required)
        self.table_workspace.configure(height=170)
        if self.info_panel.cget('height')!=height:self.info_panel.configure(height=height)
        self.right.grid_rowconfigure(1,weight=1,minsize=170)
        self.right.grid_rowconfigure(3,weight=0,minsize=0)
        self.right.grid_rowconfigure(2,weight=0,minsize=height)
        self._fit_preview_text()

    def _sync_left_scrollbar(self) -> None:
        if not self.running or not self.left.winfo_exists():
            return
        try:
            canvas = self.left._parent_canvas
            scrollbar = self.left._scrollbar
            bounds = canvas.bbox('all')
            content_height = int(bounds[3] - bounds[1]) if bounds else 0
            needs_scroll = content_height > canvas.winfo_height() + 2
            visible = scrollbar.winfo_manager() == 'grid'
            if needs_scroll and (not visible):
                scrollbar.grid()
            elif not needs_scroll and visible:
                scrollbar.grid_remove()
                canvas.yview_moveto(0)
        except (AttributeError, tk.TclError):
            return
