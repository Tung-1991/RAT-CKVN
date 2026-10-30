"""Compact signal settings using the native MayinTien cards, inputs and hints."""
from dataclasses import asdict, replace
import tkinter as tk
import customtkinter as ctk
from .widgets import choice_bar

from ckps.rules.signal_settings import SignalSettings
from ckps.rules.market_alerts import MarketAlertSettings
from .forms import OriginalRuleForms


class SignalForm(OriginalRuleForms, ctk.CTkFrame):
    def __init__(self, parent, settings):
        super().__init__(parent, fg_color='transparent')
        self.signals = SignalSettings.from_dict(settings.signals)
        self.market = MarketAlertSettings.from_dict(settings.market_alerts)
        self.variables = {}
        self.body = self._content(self, columns=2)
        mode = self._card(self.body, 'QUAN SÁT 1D', '', 0, 0, span=2, compact=True)
        row = self.row(mode)
        self.choice(row, 'signal_mode', ('REALTIME', 'CLOSED'))
        self.choice(row, 'realtime_indicator_interval', ('TICK', '1M', '2M', '5M'))
        self._hint_icon(row, 'EMA/RSI luôn tính trên nến ngày. REALTIME cập nhật nến hôm nay; CLOSED chỉ dùng nến đã đóng. TICK/1M/2M/5M là nhịp cập nhật, không phải khung nến phút. MA200 và ATR14 dùng nến ngày đã đóng.').pack(side='right')
        ema = self._card(self.body, 'EMA / RSI · CHỈ TÍN HIỆU', '', 1, 0, compact=True)
        for prefix, title in (('buy', 'ĐIỂM VÀO'), ('sell', 'E · CẢNH BÁO')):
            row = self.row(ema)
            ctk.CTkLabel(row, text=title, font=('Segoe UI', 12, 'bold'), width=110, anchor='w').pack(side='left')
            self.number(row, prefix+'_ema_fast', 'Nhanh', width=43)
            self.number(row, prefix+'_ema_slow', 'Chậm', width=43)
            row = self.row(ema)
            self.flag(row, prefix+'_signal_use_ema', 'EMA')
            self.flag(row, prefix+'_signal_use_rsi', 'RSI')
            self.flag(row, prefix+'_signal_require_ema_cross', 'CẮT')
            self.flag(row, prefix+'_alert_enabled', 'ALERT')
        row = self.row(ema)
        self.number(row, 'rsi_period', 'RSI', width=48)
        self._hint_icon(row, 'ALERT của điểm vào và E độc lập; OFF vẫn phân tích. Telegram chỉ gửi khi nhóm Tín hiệu / Lệnh được bật tại KẾT NỐI. CẮT: yêu cầu giao cắt; E không có quyền đóng vị thế.').pack(side='right')
        memory = self._card(self.body, 'GIAO CẮT / XÁC NHẬN', '', 2, 0, compact=True)
        row = self.row(memory)
        self.choice(row, 'buy_ema_cross_mode', ('VA', 'SESSIONS'), labels={'VA': '∞ VA', 'SESSIONS': 'X PHIÊN'})
        self.number(row, 'buy_ema_cross_sessions', 'Phiên', width=40)
        row = self.row(memory)
        self.flag(row, 'buy_ema_va_lookback_enabled', 'VA QUÉT TRƯỚC')
        self._hint_icon(row, 'VA theo dõi giao cắt cho tới khi được dùng. X PHIÊN giới hạn tuổi lần cắt. QUÉT TRƯỚC cho phép lấy bằng chứng lịch sử; thiếu dữ liệu không coi là 0.').pack(side='right')
        row = self.row(memory)
        self.flag(row, 'buy_confirmation_enabled', 'XÁC NHẬN')
        self.number(row, 'buy_confirmation_minutes', 'Phút', width=42)
        row = self.row(memory)
        self.flag(row, 'buy_confirmation_require_ema', 'Giữ EMA')
        self.flag(row, 'buy_confirmation_require_rsi', 'Giữ RSI')
        row = self.row(memory)
        self.flag(row, 'buy_window_enabled', 'GIỜ THEO DÕI')
        self.number(row, 'buy_window_start', '', width=65)
        filters = self._card(self.body, 'VOLUME / WHIPSAW', '', 1, 1, compact=True)
        row = self.row(filters)
        self.flag(row, 'buy_volume_enabled', 'VOLUME')
        self._hint_icon(row, 'Volume so trung bình số phiên đã chọn. Whipsaw đếm giao cắt EMA trong X nến ngày, chặn tín hiệu mới khi đạt N; không chặn E/M hay lệnh đóng.').pack(side='right')
        row = self.row(filters)
        self.number(row, 'buy_volume_average_sessions', 'Phiên', width=43)
        self.number(row, 'buy_volume_min_ratio', 'Tỷ lệ ≥', width=53)
        row = self.row(filters)
        self.flag(row, 'whipsaw_enabled', 'WHIPSAW')
        row = self.row(filters)
        self.number(row, 'whipsaw_n', 'N lần', width=43)
        self.number(row, 'whipsaw_x', 'X phiên', width=43)
        movement = self._card(self.body, 'BIẾN ĐỘNG VN30', '', 2, 1, compact=True)
        row = self.row(movement)
        self.number(row, 'market.fast_points', 'Điểm', width=50)
        self.number(row, 'market.window_seconds', 'Giây', width=50)
        row = self.row(movement)
        self.number(row, 'market.confirmations', 'Xác nhận', width=45)
        row = self.row(movement)
        self.flag(row, 'market.session_enabled', 'NHỊP PHIÊN')
        self.number(row, 'market.session_points', 'Điểm', width=48)
        row = self.row(movement)
        self.number(row, 'market.cooldown_minutes', 'Cách tin (phút)', width=53)
        self._hint_icon(row, 'Chỉ cấu hình ngưỡng quan sát. Bật/tắt gửi Biến động VN30 tại KẾT NỐI; tắt gửi vẫn phân tích.').pack(side='right')
        self.cards = (mode, ema, memory, filters, movement)
        self.body._parent_canvas.bind('<Configure>', self._reflow, add='+')

    def _reflow(self, _event=None):
        wide = self.body._parent_canvas.winfo_width()/self.body._get_widget_scaling() >= 660
        if getattr(self, '_wide', None) == wide:
            return
        self._wide = wide
        self.body.grid_columnconfigure(0, weight=1, uniform='signal' if wide else '')
        self.body.grid_columnconfigure(1, weight=1 if wide else 0, uniform='signal' if wide else '')
        places = ((0, 0, 2), (1, 0, 1), (2, 0, 1), (1, 1, 1), (2, 1, 1)) if wide else tuple((i, 0, 1) for i in range(5))
        for card, (row, column, span) in zip(self.cards, places):
            card.grid_configure(row=row, column=column, columnspan=span)

    def row(self, card):
        row = ctk.CTkFrame(card, fg_color='transparent')
        row.pack(fill='x', padx=8, pady=2)
        return row

    def variable(self, key):
        if key not in self.variables:
            value = getattr(self.market if key.startswith('market.') else self.signals, key.removeprefix('market.'))
            self.variables[key] = tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=str(value))
        return self.variables[key]

    def number(self, row, key, title, *, width):
        if title:
            ctk.CTkLabel(row, text=title, font=('Segoe UI', 12), text_color=self.TITLE).pack(side='left', padx=(0, 4))
        entry = ctk.CTkEntry(row, textvariable=self.variable(key), width=width, height=27,
            font=('Segoe UI', 12), justify='right', fg_color='#181B20', border_color='#444B55')
        entry.pack(side='left', padx=(0, 8))
        self.variables[key]._viking_entry = entry
        return entry

    def flag(self, row, key, title):
        switch = ctk.CTkCheckBox(row, text=title, variable=self.variable(key),
            width=1, checkbox_width=16, checkbox_height=16, font=('Segoe UI', 11))
        switch.pack(side='left', padx=(0, 8))
        return switch

    def choice(self, row, key, values, *, labels=None):
        labels = labels or {value: value for value in values}
        variable = self.variable(key)
        shown = tk.StringVar(value=labels[variable.get()])
        reverse = {label: value for value, label in labels.items()}
        choice_bar(row, values=list(labels.values()), variable=shown,
            font=('Segoe UI', 12, 'bold'), height=32,
            command=lambda selected: variable.set(reverse[selected])).pack(side='left', padx=(0, 8))
        variable.trace_add('write', lambda *_: shown.set(labels[variable.get()]))

    def read(self, settings):
        signals, market = asdict(self.signals), asdict(self.market)
        for key, variable in self.variables.items():
            target = market if key.startswith('market.') else signals
            name = key.removeprefix('market.')
            old, raw = target[name], variable.get()
            target[name] = bool(raw) if isinstance(old, bool) else str(raw).strip() if isinstance(old, str) else float(raw)
        signals['enabled'] = True
        # Notification gates belong to their own settings page, never reset them
        # from an older RULE window while saving indicator parameters.
        current = MarketAlertSettings.from_dict(settings.market_alerts)
        market.update(movement_enabled=current.movement_enabled, trend_enabled=current.trend_enabled)
        return replace(settings, signals=SignalSettings.from_dict(signals).to_dict(),
                       market_alerts=MarketAlertSettings.from_dict(market).to_dict()).validate()
