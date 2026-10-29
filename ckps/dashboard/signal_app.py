"""Small standalone signal console; no trading controls or account access."""
from dataclasses import asdict, replace
import queue
import tkinter as tk
import customtkinter as ctk

from ckps.models import Quote, load_record
from ckps.rules.signal_settings import SignalSettings
from ckps.rules.market_alerts import MarketAlertSettings
from ckps.services.signal_config import read_signal_settings, write_signal_settings
from ckps.services.signal_runtime import SignalRuntime
from .formatting import clock, price
from .mayin.connection_window import ConnectionFields
from .mayin.tokens import *


class SignalApp(ctk.CTk):
    def __init__(self,*,settings=None):
        super().__init__()
        self.title('RAT VN30 · TELEGRAM')
        width=min(940,self.winfo_screenwidth()-50)
        height=min(650,self.winfo_screenheight()-80)
        x=max(0,(self.winfo_screenwidth()-width)//2)
        y=max(0,(self.winfo_screenheight()-height-32)//2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        self.minsize(min(820,width),min(560,height))
        self.configure(fg_color='#111318')
        self.settings=settings or read_signal_settings()
        self.runtime=None
        self.closing=False
        self.credentials={}
        self.variables={}
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(3,weight=1)
        header=ctk.CTkFrame(self,fg_color='transparent')
        header.grid(row=0,column=0,sticky='ew',padx=18,pady=(12,6))
        ctk.CTkLabel(header,text='THÔNG BÁO VN30',font=('Segoe UI',19,'bold'),text_color=COL_TEXT).pack(side='left')
        self.status=ctk.CTkLabel(header,text='CHƯA CHẠY',font=('Segoe UI',13),text_color=COL_MUTED)
        self.status.pack(side='right')
        ctk.CTkButton(header,text='LỊCH',width=70,height=28,fg_color=COL_GRAY,command=self.calendar).pack(side='right',padx=12)
        connections=ctk.CTkFrame(self,fg_color='transparent')
        connections.grid(row=1,column=0,sticky='ew',padx=12)
        connections.grid_columnconfigure((0,1),weight=1,uniform='connections')
        form=ConnectionFields(self.variables)
        api=form.card(connections,'DNSE · CHỈ ĐỌC GIÁ / NẾN')
        form.field(api,'key','API key','',secret=True,width=260)
        form.field(api,'secret','API secret','',secret=True,width=260)
        tele=form.card(connections,'TELEGRAM · MỘT KÊNH',1)
        form.field(tele,'telegram_token','Bot token','',secret=True,width=260)
        form.field(tele,'telegram_chat','Chat ID',self.settings.telegram_chat,width=260)
        options=ctk.CTkFrame(self,fg_color=COL_SURFACE_2,corner_radius=6)
        options.grid(row=2,column=0,sticky='ew',padx=16,pady=10)
        options.grid_columnconfigure((0,1,2),weight=1)
        signals=SignalSettings.from_dict(self.settings.signals)
        market=MarketAlertSettings.from_dict(self.settings.market_alerts)
        self.options={}
        from ckps.services.calendar import read_settings as read_calendar
        schedule = read_calendar()
        for column,(key,label,value) in enumerate((('movement','Biến động VN30',market.movement_enabled),
                ('expiry','Nhắc đáo hạn',schedule.notify_enabled and schedule.expiry_notice_enabled),
                ('entry','Tín hiệu / Lệnh',self.settings.entry_notifications or signals.buy_alert_enabled or signals.sell_alert_enabled or market.trend_enabled))):
            variable=tk.BooleanVar(value=value)
            self.options[key]=variable
            ctk.CTkSwitch(options,text=label,variable=variable,font=('Segoe UI',14),progress_color=COL_GREEN,
                command=self.apply_options).grid(row=0,column=column,sticky='w',padx=14,pady=12)
        output=ctk.CTkFrame(self,fg_color=COL_SURFACE,corner_radius=6)
        output.grid(row=3,column=0,sticky='nsew',padx=16)
        output.grid_columnconfigure(0,weight=1)
        output.grid_rowconfigure(1,weight=1)
        self.market_summary=ctk.CTkLabel(output,text='VN30F1M · Chờ giá và nến DNSE',font=('Segoe UI',14),anchor='w')
        self.market_summary.grid(row=0,column=0,sticky='ew',padx=12,pady=8)
        self.logs=ctk.CTkTextbox(output,fg_color='transparent',font=('Segoe UI',13),wrap='word',state='disabled')
        self.logs.grid(row=1,column=0,sticky='nsew',padx=8,pady=(0,8))
        footer=ctk.CTkFrame(self,fg_color='transparent')
        footer.grid(row=4,column=0,sticky='ew',padx=16,pady=12)
        footer.grid_columnconfigure(0,weight=1)
        self.note=ctk.CTkLabel(footer,text='Cảnh báo / gợi ý / gửi và khớp lệnh · Vào lệnh bằng tay.',font=('Segoe UI',12),anchor='w',wraplength=570)
        self.note.grid(row=0,column=0,sticky='ew',padx=(0,10))
        self.primary=ctk.CTkButton(footer,text='KẾT NỐI & CHẠY',width=170,height=36,command=self.start)
        self.primary.grid(row=0,column=1)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self._drain)

    def option_settings(self):
        signals=replace(SignalSettings.from_dict(self.settings.signals),enabled=True,
            buy_alert_enabled=self.options['entry'].get(),sell_alert_enabled=self.options['entry'].get())
        market=replace(MarketAlertSettings.from_dict(self.settings.market_alerts),trend_enabled=self.options['entry'].get(),
            movement_enabled=self.options['movement'].get())
        return replace(self.settings,signals=signals.to_dict(),market_alerts=market.to_dict(),
            entry_notifications=self.options['entry'].get(),telegram_enabled=True,telegram_chat=self.variables['telegram_chat'].get().strip()).validate()

    def calendar(self):
        window=getattr(self,'calendar_window',None)
        if window and window.winfo_exists():window.lift();return
        from .mayin.calendar_form import CalendarWindow
        self.calendar_window=CalendarWindow(self)

    def apply_options(self):
        self.settings=self.option_settings()
        from ckps.services import calendar
        calendar.write_settings(replace(calendar.read_settings(),expiry_notice_enabled=self.options['expiry'].get(),
            notify_enabled=self.options['expiry'].get()))
        if self.runtime:self.runtime.command('settings',asdict(self.settings),self.credentials.get('telegram_token',''))
        else:write_signal_settings(self.settings)

    def start(self):
        if self.runtime:
            self.runtime.close()
            self.primary.configure(state='disabled')
            self.note.configure(text='Đang dừng backend…')
            return
        try:
            values={key:value.get().strip() for key,value in self.variables.items()}
            if not values['key'] or not values['secret']:raise ValueError('Nhập API key và API secret DNSE đọc dữ liệu.')
            from ckps.services.calendar import read_settings as read_calendar
            if any(variable.get() for variable in self.options.values()) and not (values['telegram_token'] and values['telegram_chat']):
                raise ValueError('Nhập Bot token và Chat ID để gửi tín hiệu.')
            self.apply_options()
            self.credentials=values
            self.runtime=SignalRuntime(self.settings,values)
            write_signal_settings(self.settings)
            for variable in self.variables.values():variable._viking_entry.configure(state='disabled')
            self.primary.configure(text='DỪNG BACKEND')
            self.note.configure(text='Biến động · Nhắc đáo hạn · Tín hiệu / Lệnh. Chỉ thông báo.',text_color=COL_MUTED)
        except Exception as exc:self.note.configure(text=str(exc),text_color=COL_RED)

    def _drain(self):
        if self.runtime:
            for _ in range(100):
                try:kind,data=self.runtime.events.get_nowait()
                except queue.Empty:break
                if kind=='snapshot':self.render(data)
                elif kind=='error':self.note.configure(text=data,text_color=COL_RED)
                elif kind=='closed':
                    self.runtime=None
                    if self.closing:self.destroy();return
                    for variable in self.variables.values():variable._viking_entry.configure(state='normal')
                    self.status.configure(text='ĐÃ DỪNG',text_color=COL_MUTED)
                    self.primary.configure(text='KẾT NỐI & CHẠY',state='normal')
                    self.note.configure(text='Backend đã dừng.',text_color=COL_MUTED)
        self.after(100,self._drain)

    def render(self,data):
        symbol=data['contract']
        quote=data.get('quotes',{}).get(symbol,{})
        p1=data.get('analysis',{}).get('p1',{})
        trend={'ABOVE':'UPTREND','BELOW':'DOWNTREND','STALE':'Giá cũ'}.get(p1.get('state'),'Chờ MA200')
        self.market_summary.configure(text=f'{symbol} · Giá {price(quote.get("last"))} · MA200 {price(p1.get("ma"))} · {trend}')
        error=data.get('telegram_error') or data.get('connection',{}).get('error')
        fresh=bool(quote and load_record(Quote,quote).fresh(self.settings.max_quote_age))
        self.status.configure(text='ĐANG CHẠY' if fresh and not error else 'CHỜ DỮ LIỆU',text_color=COL_GREEN if fresh and not error else COL_WARN)
        self.note.configure(text=error or 'Biến động · Nhắc trước đáo hạn · Gợi ý và thông báo vào lệnh.',text_color=COL_WARN if error else COL_MUTED)
        text='\n'.join(f'{clock(row.get("at"))} · {row.get("kind","")} · {row.get("reason","")}' for row in data.get('history',[])[-100:])
        if getattr(self,'_log_text',None)!=text:
            self.logs.configure(state='normal');self.logs.delete('1.0','end');self.logs.insert('1.0',text);self.logs.see('end');self.logs.configure(state='disabled')
            self._log_text=text

    def close(self):
        self.closing=True
        if self.runtime:self.runtime.close();self.primary.configure(state='disabled')
        else:self.destroy()
