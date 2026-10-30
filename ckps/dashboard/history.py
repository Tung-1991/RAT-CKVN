"""One history window for trades and orders; no equity portfolio."""
import customtkinter as ctk
import tkinter as tk
from .compact import tabs
from .theme import BG, BORDER, MUTED, TITLE
from .mayin.widgets import _StableToplevel, size_popup, option_menu, choice_bar


class HistoryWindow(_StableToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app=app
        self.title("RAT VN30 · Lịch sử " + app.settings.mode)
        self.configure(fg_color=BG)
        size_popup(self,width=1180,height=700)
        self.transient(app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color='#1C2B3B',border_width=1,border_color='#344D66',corner_radius=8)
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12,8))
        ctk.CTkLabel(header, text="LỊCH SỬ · " + app.settings.mode, font=("Segoe UI", 18, "bold"), text_color='#DBEAFE').pack(side="left",padx=14,pady=12)
        ctk.CTkButton(header, text="XUẤT CSV", width=120, height=36, font=('Segoe UI',14,'bold'),fg_color='#286AA6',hover_color='#337EBE', command=app.export_history).pack(side="right",padx=12)
        filters=ctk.CTkFrame(self,fg_color='#1B222C',border_width=1,border_color='#344050',corner_radius=8)
        filters.grid(row=1,column=0,sticky='ew',padx=12,pady=(0,6))
        filters.grid_columnconfigure(0,weight=1)
        filters.grid_columnconfigure(1,weight=1)
        filters.grid_columnconfigure(2,weight=1)
        self.contract=tk.StringVar(value='TẤT CẢ HỢP ĐỒNG')
        self.side=tk.StringVar(value='TẤT CẢ')
        self.order_state=tk.StringVar(value='MỌI TRẠNG THÁI')
        for column,label in enumerate(('HỢP ĐỒNG','CHIỀU','TRẠNG THÁI LỆNH')):
            ctk.CTkLabel(filters,text=label,font=('Segoe UI',13,'bold'),text_color='#9FB8D1',anchor='w').grid(
                row=0,column=column,sticky='ew',padx=12,pady=(7,0))
        self.contract_menu=option_menu(filters,values=[self.contract.get()],variable=self.contract,
            command=lambda _:app._render_history(),width=200)
        self.contract_menu.grid(row=1,column=0,sticky='ew',padx=10,pady=(3,8))
        self.side_control=choice_bar(filters,values=['TẤT CẢ','LONG','SHORT'],variable=self.side,
            command=lambda _:app._render_history())
        self.side_control.grid(row=1,column=1,sticky='ew',padx=5,pady=(3,8))
        self.state_menu=option_menu(filters,values=['MỌI TRẠNG THÁI','ĐANG CHỜ','ĐÃ KHỚP','ĐÃ HỦY','LỖI / CHƯA RÕ'],
            variable=self.order_state,command=lambda _:app._render_history(),width=185)
        self.state_menu.grid(row=1,column=2,sticky='ew',padx=10,pady=(3,8))
        self.result_label=ctk.CTkLabel(filters,text='',font=('Segoe UI',13),text_color='#A8BBD0',anchor='w')
        self.result_label.grid(row=2,column=0,columnspan=3,sticky='ew',padx=12,pady=(0,6))
        self.tabs = tabs(self)
        self.tabs.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.pages = {name: self.tabs.add(name) for name in ("GIAO DỊCH", "LỆNH")}
        app.history_window=self
        app.history_tree = app._tree(self.pages["GIAO DỊCH"], (("closed", "ĐÓNG LÚC", 130),
            ("symbol", "HỢP ĐỒNG", 140), ("side", "CHIỀU", 72), ("quantity", "HĐ", 56),
            ("entry", "GIÁ VỐN", 100), ("pnl", "PNL SAU PHÍ", 145), ("fees", "PHÍ ĐÃ GHI", 110), ("source", "NGUỒN", 100)))
        app.order_history_tree = app._tree(self.pages["LỆNH"], (("time", "THỜI GIAN", 130),
            ("symbol", "HỢP ĐỒNG", 140), ("action", "THAO TÁC", 82), ("side", "CHIỀU", 72),
            ("kind", "LOẠI", 60), ("price", "GIÁ LO", 100), ("fill", "KHỚP/HĐ", 82),
            ("status", "TRẠNG THÁI", 150), ("reason", "LÝ DO", 130)))
        app._render_history()
        self.bind("<Escape>", lambda _: self.destroy())
        self.after(80, self.lift)

    def filtered(self,history,orders):
        from ckps.models import FINAL
        contracts=['TẤT CẢ HỢP ĐỒNG',*sorted({row['symbol'] for row in history+orders})]
        if self.contract_menu.cget('values')!=contracts:self.contract_menu.configure(values=contracts)
        if self.contract.get() not in contracts:self.contract.set(contracts[0])
        def match(row):
            return (self.contract.get()==contracts[0] or row['symbol']==self.contract.get()) and (
                self.side.get()=='TẤT CẢ' or row['side']==self.side.get())
        trades=[row for row in history if match(row)]
        groups={'ĐANG CHỜ':lambda row:row['status'] not in FINAL,
            'ĐÃ KHỚP':lambda row:row['status']=='FILLED',
            'ĐÃ HỦY':lambda row:row['status']=='CANCELLED',
            'LỖI / CHƯA RÕ':lambda row:row['status'] in {'UNKNOWN','REJECTED','FAILED','EXPIRED'}}
        gate=groups.get(self.order_state.get(),lambda _:True)
        filtered_orders=[row for row in orders if match(row) and gate(row)]
        self.result_label.configure(text=f'{len(trades)}/{len(history)} giao dịch · {len(filtered_orders)}/{len(orders)} lệnh')
        self.side_control.configure(selected_color={'LONG':'#20785D','SHORT':'#9A4052'}.get(self.side.get(),'#286AA6'))
        return trades,filtered_orders
