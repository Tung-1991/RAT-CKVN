"""Position overrides use the same native E/M controls and hints as RULE."""
import customtkinter as ctk

from .mayin.protection_form import ProtectionFormMixin


class ExitEditor(ProtectionFormMixin, ctk.CTkFrame):
    def __init__(self, parent, values, *, app, symbol, status):
        super().__init__(parent, fg_color='transparent')
        self.app, self.protection_symbol, self.status = app, symbol, status
        self._init_protection(self, values)

    def read(self):
        return self._exits()

    def set_enabled(self, enabled):
        def visit(widget):
            if isinstance(widget, (ctk.CTkEntry, ctk.CTkSwitch, ctk.CTkOptionMenu, ctk.CTkSegmentedButton)):
                widget.configure(state='normal' if enabled else 'disabled')
                return
            for child in widget.winfo_children():
                visit(child)
        visit(self)
