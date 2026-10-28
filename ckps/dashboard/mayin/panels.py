from __future__ import annotations
import tkinter as tk
from typing import Any
import customtkinter as ctk
from .tokens import *
from .widgets import FONT_KEY, FONT_VALUE, FONT_MONO_VALUE, StatusLabel, fit_entry_text, fit_label_text
APP_NAME = 'RAT VN30'
APP_VERSION = '0.1.0'
INFO_PANEL_HEIGHT = 390

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
        self.lbl_equity = ctk.CTkLabel(account, text='----', font=('Segoe UI', 30, 'bold'), text_color=COL_GREEN, anchor='w')
        self.lbl_equity.grid(row=1, column=0, sticky='ew', padx=(11, 5), pady=(0, 0))
        self.lbl_equity.bind('<Configure>', lambda _event: fit_label_text(self.lbl_equity, base_font=('Segoe UI', 30, 'bold'), minimum_size=14), add='+')
        session_box = ctk.CTkFrame(account, width=180, height=52, fg_color='transparent')
        session_box.grid(row=0, column=1, rowspan=2, sticky='ne', padx=(3, 11), pady=(7, 0))
        session_box.pack_propagate(False)
        self.lbl_session = ctk.CTkLabel(session_box, text='PHIÊN: --', font=('Segoe UI', 11, 'bold'), text_color=COL_MUTED, anchor='e', justify='right', width=176)
        self.lbl_session.pack(fill='x')
        self.lbl_brain = ctk.CTkLabel(session_box, text='DAEMON: CHỜ', font=('Segoe UI', 11, 'bold'), text_color=COL_WARN, anchor='e')
        self.lbl_brain.pack(fill='x', pady=(2, 0))
        self.lbl_account = ctk.CTkLabel(account, text=f'ID: {self.account_id}  ·  PAPER', font=('Segoe UI', 11, 'bold'), text_color=COL_TEXT, anchor='w', justify='left')
        self.lbl_account.grid(row=3, column=0, columnspan=2, sticky='ew', padx=(11, 11), pady=(3, 6))
        account_footer = ctk.CTkFrame(account, fg_color='transparent')
        account_footer.grid_columnconfigure(0, minsize=82)
        account_footer.grid_columnconfigure(1, minsize=120)
        account_footer.grid_columnconfigure(2, weight=1)
        self.lbl_pnl = ctk.CTkLabel(account_footer, text='PNL: ĐANG TÍNH', font=('Segoe UI', 12, 'bold'), anchor='w')
        self.lbl_pnl.grid(row=0, column=0, sticky='w')
        self.lbl_cash = ctk.CTkLabel(account, text='Tổng tiền: —', font=('Segoe UI', 11), text_color=COL_MUTED, anchor='w')
        self.lbl_cash.grid(row=2, column=0, columnspan=2, sticky='ew', padx=11, pady=(0, 1))

        def fit_stats(_event=None):
            fit_label_text(self.lbl_cash, base_font=('Segoe UI', 11), minimum_size=10)
        self._fit_account_stats = fit_stats
        account_footer.bind('<Configure>', fit_stats, add='+')
        control = ctk.CTkFrame(self.left, fg_color=COL_SURFACE, corner_radius=10, border_width=1, border_color=COL_BORDER)
        control.pack(fill='x', padx=6, pady=4)
        control.columnconfigure(0, minsize=55)
        control.columnconfigure(1, weight=1)

        def setting_row(index: int, label: str) -> ctk.CTkFrame:
            ctk.CTkLabel(control, text=label, font=FONT_KEY, text_color=COL_TITLE, anchor='w', justify='left').grid(row=index, column=0, sticky='ew', padx=(7, 6), pady=3)
            frame = ctk.CTkFrame(control, width=1, height=34, fg_color='transparent')
            frame.grid(row=index, column=1, sticky='ew', padx=(0, 7), pady=1)
            frame.grid_propagate(False)
            return frame
        symbol_row = setting_row(0, 'HĐTL')
        symbol_row.grid_columnconfigure(0, weight=1)
        self.symbol = tk.StringVar(value='VN30F1M')
        self.symbol_entry = ctk.CTkLabel(symbol_row, text='VN30F1M', font=FONT_BOLD, height=32, corner_radius=7, fg_color=COL_SURFACE_2)
        self.symbol_entry.grid(row=0, column=0, sticky='ew')
        mode_row = setting_row(1, 'MODE')
        mode_row.grid_columnconfigure(0, weight=4)
        mode_row.grid_columnconfigure(1, weight=1)
        self.mode = tk.StringVar(value='PAPER')
        self.mode_selector = ctk.CTkSegmentedButton(mode_row, values=['PAPER', 'REAL'], variable=self.mode, command=self._mode_changed, height=34, font=('Segoe UI', 14, 'bold'), width=1, dynamic_resizing=False, selected_color=COL_GREEN, selected_hover_color='#16A34A', unselected_color=COL_GRAY, unselected_hover_color='#4B515B', text_color=COL_TEXT, corner_radius=7)
        self.mode_selector.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.bot_button = ctk.CTkButton(mode_row, text='BOT · OFF', height=32, font=('Segoe UI', 11, 'bold'), width=1, fg_color=COL_GRAY, hover_color='#4B515B', corner_radius=7, command=self._toggle_bot)
        self.bot_button.grid(row=0, column=1, sticky='ew')
        tools_row = setting_row(2, 'TOOLS')
        tool_specs = [('⚙  RULE', self._rule_settings), ('⛓  KẾT NỐI', self._advanced)]
        for column, (text, command) in enumerate(tool_specs):
            tools_row.grid_columnconfigure(column, weight=1, uniform='tool')
            button = ctk.CTkButton(tools_row, text=text, height=32, font=('Segoe UI', 11, 'bold'), width=1, fg_color=COL_GRAY, hover_color='#4B515B', corner_radius=7, command=command)
            button.grid(row=0, column=column, sticky='ew', padx=(0 if column == 0 else 3, 0))
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
        self.lbl_quote_symbol = ctk.CTkLabel(quote, text=self.symbol.get(), width=72, height=28, font=('Segoe UI', 14, 'bold'), fg_color='#2B3440', corner_radius=7, text_color=COL_TEXT, anchor='center')
        self.lbl_quote_symbol.grid(row=0, column=0, sticky='w', padx=(11, 5), pady=(6, 0))
        change_box = ctk.CTkFrame(quote, fg_color='transparent')
        change_box.grid(row=0, column=1, sticky='e', padx=(5, 9), pady=(6, 0))
        self.lbl_change = ctk.CTkLabel(change_box, text='--', font=FONT_MONO_VALUE, text_color=COL_MUTED, anchor='e')
        self.lbl_change.pack(side='left')
        self.lbl_price = ctk.CTkLabel(quote, text='---', font=('Cascadia Mono', 36, 'bold'), text_color=COL_TEXT, anchor='center', corner_radius=4)
        self.lbl_price.grid(row=1, column=0, columnspan=2, sticky='ew', padx=10, pady=(0, 0))
        self.lbl_market = ctk.CTkLabel(quote, text='CHỜ DỮ LIỆU', font=('Segoe UI', 11, 'bold'), text_color=COL_WARN, anchor='center')
        self.lbl_market.grid(row=2, column=0, columnspan=2, sticky='ew', padx=10, pady=(0, 5))
        preview = ctk.CTkFrame(quote, fg_color='transparent')
        preview.grid(row=3, column=0, columnspan=2, sticky='ew', padx=7, pady=(0, 6))
        preview.grid_columnconfigure(0, weight=1)
        pnl_panel = ctk.CTkFrame(preview, fg_color='#1B1F25', corner_radius=7)
        pnl_panel.grid(row=0, column=0, sticky='ew')
        pnl_panel.grid_columnconfigure((0, 1, 2), weight=1, uniform='pnl_preview')
        pnl_specs = (('TP', 'lbl_tp_title', 'lbl_tp_preview', COL_GREEN), ('SL', 'lbl_sl_title', 'lbl_sl_preview', COL_RED), ('PHÍ', 'lbl_fee_title', 'lbl_fee_preview', COL_WARN))
        for column, (title, title_attr, value_attr, title_color) in enumerate(pnl_specs):
            box = ctk.CTkFrame(pnl_panel, fg_color='transparent')
            box.grid(row=0, column=column, sticky='nsew', padx=5, pady=5)
            title_label = ctk.CTkLabel(box, text=title, font=FONT_PREVIEW_TITLE, height=22, text_color=title_color, anchor='center')
            title_label.pack(fill='x')
            label = ctk.CTkLabel(box, text='NA', font=FONT_PREVIEW_VALUE, text_color=COL_PREVIEW_TEXT, anchor='center', height=28)
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
        self.order_type_menu = ctk.CTkOptionMenu(action, values=['LO', 'MOK', 'MTL'], variable=self.order_type, command=self._order_type_changed, width=115, height=38, font=('Segoe UI', 11, 'bold'), fg_color=COL_GRAY, button_color='#4B515B', button_hover_color='#59616D', corner_radius=8, dynamic_resizing=False)
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
        self.tp = self._manual_input(form, 0, 'TP', self._default_tp_text(), dimmed=True, row=1)
        self.sl = self._manual_input(form, 1, 'SL', 'RULE', dimmed=True, row=1)
        entries = (self.quantity, self.price, self.tp)
        for entry in entries:
            entry.bind('<KeyRelease>', lambda _event: self._update_order_preview(), add='+')
            entry.bind('<KeyPress>', lambda _event, widget=entry: widget.configure(text_color=COL_TEXT), add='+')
        self.sl.bind('<KeyPress>', lambda _event: self.sl.configure(text_color=COL_TEXT), add='+')
        self.price.bind('<FocusIn>', self._activate_lo_input, add='+')
        self.sl.bind('<KeyRelease>', self._sl_edited, add='+')
        self.quantity.bind('<Tab>', lambda _event: self._focus_widget(self.price if self.order_type.get() == 'LO' else self.tp))
        self.price.bind('<Tab>', lambda _event: self._focus_widget(self.tp))
        self.tp.bind('<Tab>', lambda _event: self._focus_widget(self.sl))
        self.sl.bind('<Tab>', lambda _event: self._focus_widget(self.execute_button))
        self.execute_button.bind('<Tab>', lambda _event: self._focus_widget(self.quantity))
        self.quantity.bind('<Shift-Tab>', lambda _event: self._focus_widget(self.execute_button))
        self.price.bind('<Shift-Tab>', lambda _event: self._focus_widget(self.quantity))
        self.tp.bind('<Shift-Tab>', lambda _event: self._focus_widget(self.price if self.order_type.get() == 'LO' else self.quantity))
        self.sl.bind('<Shift-Tab>', lambda _event: self._focus_widget(self.tp))
        self.execute_button.bind('<Shift-Tab>', lambda _event: self._focus_widget(self.sl))
        self.execute_button.bind('<Return>', lambda _event: self.execute_button.invoke())
        self.execute_button.bind('<space>', lambda _event: self.execute_button.invoke())
        self._sync_default_sl(force=True, refresh=False)
        self._update_order_preview()
        brand = ctk.CTkFrame(self.left, fg_color='transparent')
        brand.pack(fill='x', padx=6, pady=(1, 0))
        ctk.CTkLabel(brand, text=f'{APP_NAME} · v{APP_VERSION}', font=('Segoe UI', 19, 'bold'), text_color='#A78BFA').pack()

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
        panel.grid_rowconfigure(0,weight=1)
        self.preview_focus_panel=self.preview_content=panel
        data=ctk.CTkFrame(panel,width=1,fg_color='transparent')
        data.grid(row=0,column=0,sticky='nsew')
        data.grid_columnconfigure(0,weight=1)
        data.grid_rowconfigure(0,weight=1)
        self.preview_data=data
        self._preview_fit_labels=[]
        def label(parent,name,text='',size=13,color=COL_PREVIEW_TEXT,bold=False,mono=False,**grid):
            font=('Cascadia Mono' if mono else 'Segoe UI',size,*(['bold'] if bold else []))
            widget=StatusLabel(parent,text=text,width=1,height=size+5,font=font,text_color=color,anchor='w')
            widget.grid(sticky='ew',**grid)
            setattr(self,name,widget);self._preview_fit_labels.append((widget,font))
            return widget
        em=ctk.CTkFrame(data,width=1,fg_color='transparent',corner_radius=0)
        em.grid(row=0,column=0,sticky='nsew',padx=3,pady=(0,4))
        em.grid_columnconfigure(0,weight=1)
        em.grid_rowconfigure(2,weight=1)
        self.market_context_label=ctk.CTkLabel(self.info_header,text='CHỜ GIÁ DNSE',height=28,
            font=('Segoe UI',12,'bold'),text_color=COL_MUTED,anchor='e')
        self.market_context_label.grid(row=0,column=1,sticky='ew',padx=(8,10))
        header=ctk.CTkFrame(em,fg_color=COL_PANEL_HEADER,corner_radius=5)
        header.grid(row=0,column=0,sticky='ew',pady=(0,8))
        header.grid_columnconfigure(0,weight=1)
        header.grid_columnconfigure(1,weight=1)
        label(header,'preview_order_title','E/M · VÉ LỆNH',17,COL_TEXT,True,row=0,column=0,padx=(12,0),pady=(7,0))
        label(header,'preview_status_reason',size=12,color=COL_MUTED,row=0,column=1,padx=8,pady=(7,0))
        self.preview_status_badge=StatusLabel(header,text='BOT OFF',width=80,height=22,font=('Segoe UI',12,'bold'),text_color=COL_MUTED)
        self.preview_status_badge.grid(row=0,column=2,sticky='e',padx=(0,12),pady=(7,0))
        label(header,'preview_position_context',size=13,color=COL_MUTED,row=1,column=0,columnspan=3,padx=12,pady=(3,7))
        management=ctk.CTkFrame(em,width=1,fg_color='transparent')
        management.grid(row=1,column=0,sticky='new')
        management.grid_columnconfigure(0,weight=1)
        self.preview_management=management
        metrics=ctk.CTkFrame(management,width=1,height=1,fg_color=COL_PANEL_BODY,corner_radius=5,border_width=1,border_color=COL_GRID)
        metrics.grid(row=0,column=0,sticky='ew')
        metrics.grid_columnconfigure((0,2,4),weight=1,uniform='levels')
        branches=ctk.CTkFrame(management,width=1,height=1,fg_color=COL_PANEL_BODY,corner_radius=5,border_width=1,border_color=COL_GRID)
        branches.grid(row=1,column=0,sticky='ew',pady=(8,0))
        branches.grid_columnconfigure((0,2),weight=1,uniform='branches')
        for column in (1,3):
            ctk.CTkFrame(metrics,width=1,height=1,corner_radius=0,fg_color=COL_GRID).grid(row=0,column=column,sticky='ns',pady=9)
        ctk.CTkFrame(branches,width=1,height=1,corner_radius=0,fg_color=COL_GRID).grid(row=0,column=1,sticky='ns',pady=10)
        self._preview_level_cards=[]
        for i,title,color,names in (
            (0,'SL',COL_RED,('preview_sl_title','preview_sl_value','preview_sl_detail')),
            (1,'TP',COL_GREEN,('preview_tp_title','preview_tp_value','preview_tp_detail')),
            (2,'ATR14 · NGÀY',COL_ACCENT_BLUE,('preview_atr_title','preview_atr','preview_atr_detail')),
            (3,'TSL / ARM',COL_TEXT,('preview_em_normal','preview_normal_value','preview_normal_detail')),
            (4,'DYNAMIC',COL_TEXT,('preview_em_exit','preview_exit_value','preview_exit_detail'))):
            cell=ctk.CTkFrame(metrics if i<3 else branches,width=1,fg_color='transparent')
            cell.grid_columnconfigure(0,weight=1)
            if i<3:
                cell.grid(row=0,column=i*2,sticky='nsew',padx=12,pady=9)
                a=label(cell,names[0],title,size=12,color=COL_TITLE,bold=True,row=0,column=0)
                b=label(cell,names[1],'Chưa bật',size=20,color=color,mono=True,row=1,column=0,pady=(2,0))
                c=label(cell,names[2],size=12,color=COL_MUTED,row=2,column=0,pady=(2,0))
            else:
                cell.grid(row=0,column=(i-3)*2,sticky='nsew',padx=12,pady=10)
                a=label(cell,names[0],title,size=13,color=COL_ACCENT_BLUE if i==3 else COL_WARN,bold=True,row=0,column=0)
                b=label(cell,names[1],'Chưa bật',size=16,color=color,row=1,column=0,pady=(4,0))
                c=label(cell,names[2],size=13,color=COL_PREVIEW_TEXT,row=2,column=0,pady=(3,0))
                label(cell,'preview_normal_parameters' if i==3 else 'preview_exit_parameters',size=12,color=COL_MUTED,row=3,column=0,pady=(4,0))
                label(cell,'preview_normal_config' if i==3 else 'preview_exit_config',size=12,color=COL_MUTED,row=4,column=0,pady=(3,0))
            self._preview_level_cards.append((a,b,c))
        panel.bind('<Configure>',self._fit_preview_text,add='+')
        self.right.bind('<Configure>',self._layout_preview,add='+')
        self.after_idle(self._layout_preview)

    def _fit_preview_text(self,_event=None):
        for widget,font in self._preview_fit_labels:
            if not widget.cget('text'):
                if widget.winfo_manager():widget.grid_remove()
                continue
            if not widget.winfo_manager():widget.grid()
            if widget.winfo_ismapped():fit_label_text(widget,base_font=font,minimum_size=12)

    def _layout_preview(self,_event=None):
        if getattr(self,'_workspace_editing',False):return
        height=self.right.winfo_height()/self.right._get_widget_scaling()
        table_height=max(150,min(340,round((height-38)*.43),round(height-INFO_PANEL_HEIGHT-44)))
        if getattr(self,'_table_height',None)!=table_height:
            self._table_height=table_height
            self.table_workspace.configure(height=table_height)
        self.right.grid_rowconfigure(1,weight=0,minsize=table_height)
        self.right.grid_rowconfigure(2,weight=1,minsize=INFO_PANEL_HEIGHT)
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
