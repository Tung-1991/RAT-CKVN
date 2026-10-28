from .mayin.controller import MayinController
import tkinter as tk
import customtkinter as ctk
from .theme import BLUE, MUTED, SLATE, SLATE_HOVER
from .mayin.tokens import (COL_SURFACE as SURFACE, COL_SURFACE_2 as SURFACE_2, COL_BORDER as BORDER,
    COL_TITLE as TITLE, COL_PANEL_HEADER, COL_GRID)
from .mayin.panels import INFO_PANEL_HEIGHT

class DashboardPanelsMixin(MayinController):
    """MayinTien: account/ticket at left, running orders and Preview/Log at right."""

    def _card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=8, border_width=1, border_color=BORDER, **kwargs)

    def _right_panel(self):
        header = ctk.CTkFrame(self.right, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', pady=(0, 5))
        ctk.CTkLabel(header, text='LỆNH ĐANG CHẠY', font=('Segoe UI', 16, 'bold'), text_color=TITLE).pack(side='left')
        self.running_count=ctk.CTkLabel(header,text='0 vị thế · 0 lệnh chờ',font=('Segoe UI',14),text_color=MUTED)
        self.running_count.pack(side='left',padx=14)
        self.history_button = ctk.CTkButton(header, text='◷ LỊCH SỬ', width=100, height=30, fg_color=SLATE, hover_color=SLATE_HOVER, command=self.history)
        self.history_button.pack(side='right')
        self.table_workspace = self._card(self.right)
        self.table_workspace.grid(row=1, column=0, sticky='nsew')
        self.table_workspace.grid_propagate(False)
        self.table_workspace.grid_columnconfigure(0, weight=1)
        self.table_workspace.grid_rowconfigure(0, weight=1)
        self.running_page = ctk.CTkFrame(self.table_workspace, fg_color='transparent')
        self.running_page.grid(row=0, column=0, sticky='nsew',padx=1,pady=1)
        self.running_page.grid_columnconfigure(0, weight=1)
        self.running_page.grid_rowconfigure(0, weight=1)
        tree_host = ctk.CTkFrame(self.running_page, fg_color='transparent')
        tree_host.grid(row=0, column=0, sticky='nsew',padx=4,pady=(4,2))
        self.positions_tree = self.orders_tree = self._running_tree(tree_host)
        self.running_rows = {}
        self.action_bar = ctk.CTkFrame(self.running_page, fg_color=COL_PANEL_HEADER,border_width=1,border_color=COL_GRID,corner_radius=6)
        self.action_bar.grid(row=1, column=0, sticky='ew', padx=5, pady=(0, 4))
        self.action_buttons = {}
        for key, label, command, color in (('close', 'ĐÓNG / GIẢM', self.close_position, '#B91C1C'), ('manage', 'BẢO VỆ LỆNH', self.position_exit, BLUE), ('adopt', 'NHẬN QUẢN LÝ', self.manage_position, SLATE), ('cancel', 'HỦY LỆNH', self.cancel_order, SLATE), ('edit', 'SỬA LO', self.edit_order, SLATE), ('reconcile', 'ĐỐI SOÁT', self.bind_unknown, SLATE)):
            button = ctk.CTkButton(self.action_bar, text=label, height=30, width=132 if key in {'manage','adopt'} else 108,
                font=('Segoe UI',14,'bold'),fg_color=color, command=command)
            self.action_buttons[key] = button
        self.action_bar.grid_remove()
        self.detail_page = ctk.CTkFrame(self.table_workspace, fg_color=SURFACE_2)
        self.detail_page.grid(row=0, column=0, sticky='nsew')
        self.detail_page.grid_remove()
        self.confirmation = ctk.CTkFrame(self.table_workspace, fg_color=SURFACE, border_width=1, border_color=BLUE)
        self.confirmation.grid(row=1, column=0, sticky='ew', padx=6, pady=5)
        self.confirmation.grid_remove()
        self.info_panel = self._card(self.right, height=INFO_PANEL_HEIGHT)
        self.info_panel.grid(row=2, column=0, sticky='nsew', pady=(8, 0))
        self.info_panel.grid_propagate(False)
        self.info_panel.grid_columnconfigure(0, weight=1)
        self.info_panel.grid_rowconfigure(1, weight=1)
        info_header = ctk.CTkFrame(self.info_panel, fg_color=COL_PANEL_HEADER,height=34,corner_radius=5)
        info_header.grid(row=0,column=0,sticky='ew',padx=8,pady=(8,6))
        info_header.grid_columnconfigure(1,weight=1)
        self.info_header=info_header
        self.info_choice=tk.StringVar(value='PREVIEW')
        self.info_selector=ctk.CTkSegmentedButton(info_header,values=['PREVIEW','LOG'],variable=self.info_choice,height=28,
            font=('Segoe UI',14,'bold'),fg_color=COL_PANEL_HEADER,unselected_color=COL_PANEL_HEADER,selected_color=BLUE,command=self._select_info)
        self.info_selector.grid(row=0,column=0,sticky='w',padx=3,pady=3)
        content=ctk.CTkFrame(self.info_panel,fg_color='transparent')
        content.grid(row=1,column=0,sticky='nsew',padx=7)
        content.grid_columnconfigure(0,weight=1)
        content.grid_rowconfigure(0,weight=1)
        self.info_pages={name:ctk.CTkFrame(content,fg_color='transparent') for name in ('PREVIEW','LOG')}
        for page in self.info_pages.values():
            page.grid(row=0,column=0,sticky='nsew')
        self._build_order_preview_tab(self.info_pages['PREVIEW'])
        self.logs=ctk.CTkTextbox(self.info_pages['LOG'],fg_color=SURFACE_2,font=('Cascadia Mono',13),wrap='word')
        self.logs.pack(fill='both',expand=True)
        self.logs.configure(state='disabled')
        self.status=ctk.CTkLabel(self.info_panel,text='Đang khởi động…',text_color='#DBEAFE',font=('Segoe UI',14),anchor='w',height=28,
            fg_color='#183047',corner_radius=4,justify='left')
        self.status.grid(row=3,column=0,sticky='ew',padx=10,pady=(4,7))
        self.status.bind('<Configure>',lambda _:self.status.configure(wraplength=max(250,int(self.status.winfo_width()/self.status._get_widget_scaling())-16)),add='+')
        self._select_info('PREVIEW')

    def _select_info(self, name):
        self.info_pages[name].tkraise()
        self.info_choice.set(name)
