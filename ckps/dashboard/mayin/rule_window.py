"""One shared E/M rule and a separate page of signal parameters."""
from dataclasses import replace
from copy import deepcopy
import customtkinter as ctk

from .protection_form import ProtectionFormMixin
from .signal_form import SignalForm
from .widgets import StableTabview, _StableToplevel, size_popup
from ..settings_state import signal_settings, save_signal_settings


class RuleWindow(ProtectionFormMixin, _StableToplevel):
    def __init__(self, app, page='E/M'):
        super().__init__(app)
        self.app = app
        self.title('RAT VN30 · RULE')
        size_popup(self)
        self.configure(fg_color='#111318')
        self.transient(app)
        self.book = self._book()
        self.position_id = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.tabs = StableTabview(self, fg_color=self.BG, border_width=1, border_color=self.BORDER,
            segmented_button_selected_color=self.BLUE, segmented_button_unselected_color='#3A3F47', command=self._page_changed)
        self.tabs.grid(row=0, column=0, sticky='nsew', padx=10, pady=(8, 3))
        self._tab_font(self.tabs, 14)
        em = self.tabs.add('E/M')
        em.grid_columnconfigure(0, weight=1)
        em.grid_rowconfigure(0, weight=1)
        self.protection_host = ctk.CTkFrame(em, fg_color='transparent')
        self.protection_host.grid(row=0, column=0, sticky='nsew')
        self._init_protection(self.protection_host, app.settings.exit)
        self.signal_form = SignalForm(self.tabs.add('TÍN HIỆU'), signal_settings(app))
        self.signal_form.pack(fill='both', expand=True)
        self.footer = ctk.CTkFrame(self, fg_color='transparent')
        self.footer.grid(row=1, column=0, sticky='ew', padx=12, pady=(3, 8))
        self.footer.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(self.footer, text='', width=1, font=('Segoe UI', 11), text_color=self.TEXT,
            anchor='w', justify='left', wraplength=300)
        self.status.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.status.bind('<Configure>', lambda _: self.status.configure(
            wraplength=max(120, int(self.status.winfo_width()/self.status._get_widget_scaling())-4)), add='+')
        self.manage_button = ctk.CTkButton(self.footer, text='', width=140, height=34,
            font=('Segoe UI', 12, 'bold'), fg_color='#3A3F47', command=self.request_management)
        self.manage_button.grid(row=0, column=1, padx=(0, 8))
        self.primary = ctk.CTkButton(self.footer, text='LƯU THAY ĐỔI', width=145, height=34,
            font=('Segoe UI', 12, 'bold'), fg_color=self.GREEN, command=self.save)
        self.primary.grid(row=0, column=2)
        self.confirmation = ctk.CTkFrame(self.footer, fg_color='#202731')
        self.confirmation.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(6, 0))
        self.confirmation.grid_columnconfigure(0, weight=1)
        self.confirm_note = ctk.CTkLabel(self.confirmation, text='', width=1, font=('Segoe UI', 12), anchor='w', wraplength=420)
        self.confirm_note.grid(row=0, column=0, sticky='ew', padx=8)
        self.confirm_note.bind('<Configure>', lambda _: self.confirm_note.configure(
            wraplength=max(120, int(self.confirm_note.winfo_width()/self.confirm_note._get_widget_scaling())-4)), add='+')
        self.confirm_primary = ctk.CTkButton(self.confirmation, text='XÁC NHẬN', width=110, height=28, command=self.confirm_management)
        self.confirm_primary.grid(row=0, column=1, padx=4, pady=5)
        ctk.CTkButton(self.confirmation, text='Bỏ qua', width=70, height=28, fg_color='#3A3F47',
            command=self.confirmation.grid_remove).grid(row=0, column=2, padx=4)
        self.confirmation.grid_remove()
        self.refresh_selection()
        self.select(page)
        self.bind('<Escape>', lambda _: self.destroy())
        self.after(100, self.lift)

    def _book(self):
        return (self.app.settings.mode, self.app.settings.account_no, self.app.settings.loan_package_id, self.app.runtime)

    def _position(self):
        if self.book != self._book() or self.app.mode_requested or self.app.switch_pending:
            raise ValueError('Sổ giao dịch đã thay đổi; mở lại RULE để kiểm tra.')
        return self.app.current_position(self.position_id)

    def select(self, page):
        self.tabs.set('TÍN HIỆU' if page == 'TÍN HIỆU' else 'E/M')
        self._page_changed()
        self.lift()

    def refresh_selection(self):
        # Selection identifies only the existing receive/release permission.
        # It never selects another E/M policy or changes the form values.
        selected = self.app.positions_tree.selection()
        identity = selected[0] if selected else None
        order = next((o for o in self.app.view.get('orders', []) if o['id'] == identity), None)
        if order:
            identity = order.get('position_id')
        self.position_id = next((p['id'] for p in self.app.view.get('positions', []) if p['id'] == identity), None)
        self._page_changed()

    def _page_changed(self):
        if not hasattr(self, 'primary'):
            return
        signal = self.tabs.get() == 'TÍN HIỆU'
        self.status.configure(text='' if signal else self._migration_error,text_color='#EF4444' if self._migration_error else self.TEXT)
        self.primary.configure(state='normal' if signal or not self._migration_error else 'disabled')
        self.primary.configure(text='LƯU TÍN HIỆU' if signal else 'LƯU RULE')
        self.manage_button.grid_remove()
        if not signal and self.position_id:
            try:
                raw = self._position()
                self.manage_button.configure(text='BỎ QUẢN LÝ' if raw['managed'] else 'NHẬN QUẢN LÝ')
                self.manage_button.grid()
            except ValueError:
                pass
        self.confirmation.grid_remove()

    def request_management(self):
        try:
            raw = self._position()
            if not raw['managed']:
                self._check_saved_protection(raw)
            self.management_target = (raw['id'], not raw['managed'])
            self.management_snapshot = self._management_snapshot(raw)
            detail = 'Ngừng bảo vệ tại app; không đóng vị thế.' if raw['managed'] else 'BOT ON có thể tự đóng theo E/M đã lưu.'
            self.confirm_note.configure(text=f"{'BỎ' if raw['managed'] else 'NHẬN'} QUẢN LÝ · {raw['side']} {raw['symbol']} · {raw['quantity']} HĐ\n{detail}")
            self.confirmation.grid()
        except ValueError as exc:
            self.status.configure(text=str(exc), text_color='#EF4444')

    def _check_saved_protection(self, raw):
        if self._exits() != self.app.settings.exit:
            raise ValueError('Lưu RULE chung trước khi nhận quản lý.')

    def _management_snapshot(self, raw):
        policy=self.app.settings.exit
        return deepcopy((raw['side'], raw['symbol'], raw['quantity'], raw['entry'],
            raw.get('margin_per_contract') if policy.get('distance_unit')=='PNL_PERCENT' else None,
            policy, bool(self.app.view.get('armed'))))

    def confirm_management(self):
        self.confirmation.grid_remove()
        try:
            raw = self._position()
            identity, enabled = self.management_target
            if identity != raw['id'] or enabled == raw['managed']:
                raise ValueError('Quyền vị thế đã thay đổi; kiểm tra và xác nhận lại.')
            if enabled:
                self._check_saved_protection(raw)
                if self.management_snapshot != self._management_snapshot(raw):
                    raise ValueError('Vị thế, E/M hoặc BOT đã thay đổi; xác nhận lại quyền quản lý.')
            self.app.send('set_managed', identity, enabled)
            self._page_changed()
            self.status.configure(text='Đã gửi thay đổi quyền quản lý vị thế.', text_color=self.GREEN)
        except ValueError as exc:
            self.status.configure(text=str(exc), text_color='#EF4444')

    def save(self):
        try:
            if self.tabs.get() == 'TÍN HIỆU':
                settings = self.signal_form.read(signal_settings(self.app))
                save_signal_settings(self.app, settings)
            else:
                if self.book != self._book() or self.app.mode_requested or self.app.switch_pending:
                    raise ValueError('Sổ giao dịch đã thay đổi; mở lại RULE để kiểm tra.')
                self.app.save_config(replace(self.app.settings, exit=self._exits()).validate())
            self.status.configure(text='Đã áp dụng vào mẫu trong phiên.' if getattr(self.app, 'preview_only', False) else 'Đã lưu cấu hình.', text_color=self.GREEN)
        except Exception as exc:
            self.status.configure(text=str(exc), text_color='#EF4444')
