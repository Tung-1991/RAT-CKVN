"""One history window for trades and orders; no equity portfolio."""
import customtkinter as ctk
from .compact import tabs
from .theme import BG, BORDER, MUTED, TITLE


class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.title("RAT VN30 · Lịch sử " + app.settings.mode)
        self.configure(fg_color=BG)
        self.geometry(f"{min(1100, self.winfo_screenwidth()-40)}x{min(580, self.winfo_screenheight()-80)}")
        self.minsize(min(860,self.winfo_screenwidth()-40),min(440,self.winfo_screenheight()-80))
        self.transient(app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=6)
        ctk.CTkLabel(header, text="LỊCH SỬ · " + app.settings.mode, font=("Segoe UI", 15, "bold"), text_color=TITLE).pack(side="left")
        ctk.CTkButton(header, text="XUẤT CSV", width=100, height=28, fg_color=BORDER, command=app.export_history).pack(side="right")
        self.tabs = tabs(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.pages = {name: self.tabs.add(name) for name in ("GIAO DỊCH", "LỆNH")}
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
