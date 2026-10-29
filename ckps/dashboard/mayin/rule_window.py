"""Two compact RULE pages: native E/M scopes and backend signal parameters."""
from dataclasses import replace
from copy import deepcopy
import tkinter as tk
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
        em.grid_rowconfigure(1, weight=1)
        scope = ctk.CTkFrame(em, fg_color='transparent')
        scope.grid(row=0, column=0, sticky='ew', padx=8, pady=4)
        scope.grid_columnconfigure(1, weight=1)
        self.scope = tk.StringVar(value='CHUNG')
        self.scope_display=tk.StringVar(value='MẶC ĐỊNH')
        self.scope_selector = ctk.CTkSegmentedButton(scope, values=['MẶC ĐỊNH', 'VỊ THẾ'], variable=self.scope_display,
            font=('Segoe UI', 12, 'bold'), height=28, selected_color=self.BLUE,
            command=lambda value:self.select_scope('CHUNG' if value=='MẶC ĐỊNH' else 'VỊ THẾ'))
        self.scope_selector.grid(row=0, column=0, sticky='w')
        self._hint_icon(scope,'MẶC ĐỊNH là bộ E/M chung cho các vị thế kế thừa. VỊ THẾ chỉnh riêng dòng đang chọn; có thể dùng lại mặc định hoặc nhận/bỏ quyền quản lý tại đây. TÍN HIỆU chỉ cấu hình phân tích, không tự vào lệnh.').grid(row=0,column=3,padx=5)
        self.scope_note = ctk.CTkLabel(scope, text='', font=('Segoe UI', 12), anchor='w', width=1)
        self.scope_note.grid(row=0, column=1, sticky='ew', padx=10)
        self.inherit_exit = tk.BooleanVar(value=False)
        self.inherit_switch = ctk.CTkCheckBox(scope, text='Dùng RULE chung', variable=self.inherit_exit,
            checkbox_width=16, checkbox_height=16, font=('Segoe UI', 12), command=self._inherit_changed)
        self.inherit_switch.grid(row=0, column=2, sticky='e')
        self.protection_host = ctk.CTkFrame(em, fg_color='transparent')
        self.protection_host.grid(row=1, column=0, sticky='nsew')
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
        self.select_scope('CHUNG')
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

    def select_scope(self, scope):
        try:
            raw = None
            if scope == 'VỊ THẾ':
                selected = self.app.positions_tree.selection()
                raw = next((p for p in self.app.view.get('positions', []) if selected and p['id'] == selected[0]), None)
                if raw is None:
                    raise ValueError('Chọn vị thế tại bảng trước khi mở RULE riêng.')
            self.position_id = raw['id'] if raw else None
            self.protection_symbol = raw['symbol'] if raw else None
            self.scope.set(scope)
            self.scope_display.set('VỊ THẾ' if raw else 'MẶC ĐỊNH')
            self.inherit_exit.set(bool(raw and raw.get('exit_overrides') is None))
            self._inherit_displayed = self.inherit_exit.get()
            self._custom_protection = deepcopy((raw.get('exit_overrides') or self.app.settings.exit) if raw else self.app.settings.exit)
            for child in self.protection_host.winfo_children():
                child.destroy()
            self._init_protection(self.protection_host,
                (raw.get('exit_overrides') or self.app.settings.exit) if raw else self.app.settings.exit)
            self.scope_note.configure(text=f"{raw['side']} · {raw['symbol']} · {raw['quantity']} HĐ" if raw else '')
            self.inherit_switch.grid() if raw else self.inherit_switch.grid_remove()
            self._inherit_changed()
            self.confirmation.grid_remove()
            self._page_changed()
        except ValueError as exc:
            self.scope.set('VỊ THẾ' if self.position_id else 'CHUNG')
            self.scope_display.set('VỊ THẾ' if self.position_id else 'MẶC ĐỊNH')
            self.status.configure(text=str(exc), text_color='#EF4444')

    def _inherit_changed(self):
        inherited = bool(self.position_id and self.inherit_exit.get())
        if inherited != getattr(self, '_inherit_displayed', inherited):
            if inherited:
                try:
                    self._custom_protection = self._exits()
                except (ValueError, TypeError, OverflowError):
                    pass
            values = self.app.settings.exit if inherited else self._custom_protection
            for child in self.protection_host.winfo_children():
                child.destroy()
            self._init_protection(self.protection_host, values)
            self._inherit_displayed = inherited
        self.set_protection_enabled(self.protection_host, not self._migration_error and not (self.position_id and self.inherit_exit.get()))
        if hasattr(self,'primary'):self._page_changed()

    def _page_changed(self):
        if not hasattr(self, 'primary'):
            return
        signal = self.tabs.get() == 'TÍN HIỆU'
        self.status.configure(text='' if signal else self._migration_error,text_color='#EF4444' if self._migration_error else self.TEXT)
        self.primary.configure(state='normal' if signal or not self._migration_error else 'disabled')
        self.primary.configure(text='LƯU TÍN HIỆU' if signal else 'LƯU VỊ THẾ' if self.position_id else 'LƯU MẶC ĐỊNH')
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
        draft = None if self.inherit_exit.get() else self._exits()
        if draft != raw.get('exit_overrides'):
            raise ValueError('Lưu E/M và chờ cập nhật vị thế trước khi nhận quản lý.')

    def _management_snapshot(self, raw):
        return deepcopy((raw['side'], raw['symbol'], raw['quantity'], raw['entry'],
            raw.get('margin_per_contract'), raw.get('exit_overrides') or self.app.settings.exit, bool(self.app.view.get('armed'))))

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
            elif self.position_id:
                self._position()
                values = None if self.inherit_exit.get() else self._exits()
                self.app.send('configure_position', self.position_id, values)
            else:
                if self.book != self._book() or self.app.mode_requested or self.app.switch_pending:
                    raise ValueError('Sổ giao dịch đã thay đổi; mở lại RULE để kiểm tra.')
                self.app.save_config(replace(self.app.settings, exit=self._exits()).validate())
            self.status.configure(text='Đã áp dụng vào mẫu trong phiên.' if getattr(self.app, 'preview_only', False) else 'Đã lưu cấu hình.', text_color=self.GREEN)
        except Exception as exc:
            self.status.configure(text=str(exc), text_color='#EF4444')
