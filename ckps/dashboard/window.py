from __future__ import annotations

from dataclasses import replace

import customtkinter as ctk

from ckps.config import APP_NAME, read_settings, write_settings
from .theme import BG, RED
from ckps.services.runtime import Runtime



from .panels import DashboardPanelsMixin
from .actions import DashboardActionsMixin
from .tables import DashboardTablesMixin
from .workspace import WorkspaceMixin


class App(DashboardPanelsMixin, DashboardActionsMixin, DashboardTablesMixin, WorkspaceMixin, ctk.CTk):
    def __init__(self, *, settings=None, start_runtime=True):
        super().__init__()
        self.title(APP_NAME + " · Phái sinh")
        # CTk's Windows screen dimensions are already in logical units.
        width = min(1650, self.winfo_screenwidth() - 60)
        height = min(1000, self.winfo_screenheight() - 48)
        x, y = max(0, (self.winfo_screenwidth() - width) // 2), max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(1080, width), min(700, height))
        self.configure(fg_color=BG)
        self.settings = settings or read_settings()
        # Opening the program never reconnects to a REAL trading account silently.
        self.settings = replace(self.settings, mode="PAPER")
        self.runtime = None
        self.view = {}
        self.running = True
        self.closing = False
        self.switch_pending = None
        self.mode_requested = None
        self.credentials = {}
        self.popups = {}
        self.order_busy = False
        self.bot_requested = False
        self.ui_events = []
        self.ui_status = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        if start_runtime:
            self.runtime = Runtime(self.settings)
        self.after(100, self._drain)

    def _drain(self):
        if self.runtime:
            import queue
            for _ in range(100):
                try:
                    kind, payload = self.runtime.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "snapshot":
                    self.view = payload
                    capital=payload.get('account',{}).get('paper_capital')
                    if payload.get('mode')=='PAPER' and capital is not None:
                        self.settings.paper_balance=capital
                    self.render()
                elif kind == "error":
                    self.order_busy = False
                    self.bot_requested = self.runtime.engine.enabled.is_set()
                    if not self.closing:
                        self.status.configure(text=payload, text_color=RED)
                        self.report(payload, error=True)
                elif kind == "success":
                    self.order_busy = False
                elif kind == 'paper_capital_result':
                    if 'capital' in payload:self.settings.paper_balance=payload['capital']
                    popup=self.popups.get('connection')
                    if popup and popup.winfo_exists():popup.capital_result(payload)
                elif kind == "closed":
                    self.runtime = None
                    if self.closing:
                        self.destroy()
                        return
                    if self.switch_pending:
                        settings, credentials = self.switch_pending
                        self.switch_pending = None
                        self._start_runtime(settings, credentials)
        self.after(100, self._drain)

    def send(self, name, *args, **kwargs):
        if self.runtime and not self.closing:
            self.runtime.command(name, *args, **kwargs)

    def _start_runtime(self, settings, credentials):
        try:
            self.runtime = Runtime(settings, credentials)
            self.bot_requested = False
            self.credentials, self.settings = credentials, settings
            write_settings(settings)
            self.view = {}
            self.mode_requested = None
            self.mode_choice.set(settings.mode)
            self.status.configure(text="Đang kết nối và đối soát…")
        except Exception as exc:
            self.runtime = None
            self.view = {}
            self.bot_requested = False
            self.mode_requested = None
            self.mode_choice.set(self.settings.mode)
            self.render()
            self.status.configure(text=str(exc), text_color=RED)
            self.report("Kết nối chưa thành công: " + str(exc), error=True)

    def close(self):
        self.running = False
        self.closing = True
        timer=getattr(self,'_preview_layout_after',None)
        if timer:
            self.after_cancel(timer)
            self._preview_layout_after=None
        for popup in self.popups.values():
            if popup.winfo_exists():
                popup.destroy()
        if self.runtime:
            self.runtime.close()
            self.status.configure(text="Đang kết thúc đối soát và lưu sổ…")
        else:
            self.destroy()
