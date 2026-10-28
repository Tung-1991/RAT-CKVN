"""Compact connection pages built from MayinTien's original cards and fields."""
from dataclasses import replace
import os
import tkinter as tk
import customtkinter as ctk
from .forms import OriginalRuleForms
from .widgets import StableTabview, _StableToplevel, FONT_VALUE, size_popup
from ..theme import BG, GREEN, RED, MUTED, BLUE, WARN
from ckps.models import quantity
from ckps.rules.market_alerts import MarketAlertSettings
from ..settings_state import signal_settings, save_signal_settings, start_signal_backend


class ConnectionFields(OriginalRuleForms):
    def __init__(self, variables):
        self.variables = variables

    def card(self, parent, title, column=0):
        card = self._card(parent, title, '', 0, column, compact=True)
        for child in card._viking_header.winfo_children():
            if isinstance(child, ctk.CTkLabel):
                child.configure(font=('Segoe UI',14,'bold'))
        return card

    def field(self, card, key, label, value, choices=None, secret=False, width=180):
        hints={'connection.key':'API key DNSE dùng cho phiên kết nối; không lưu vào cấu hình.',
               'connection.secret':'API secret DNSE dùng cho phiên kết nối; không ghi vào log.',
               'connection.account':'Số tiểu khoản phái sinh DNSE dùng cho REAL.',
               'connection.loan':'Gói ký quỹ DNSE. Nếu chỉ có một gói, app tự chọn.',
               'capital.capital_limit':'0: không đặt trần riêng; sức mở vẫn do DNSE xác nhận.',
               'capital.max_contracts':'0: không giới hạn HĐ riêng. Tính cả vị thế và lệnh đang chờ.',
               'capital.risk_limit':'Trần rủi ro giá tới SL bằng tiền; 0 là không đặt riêng.',
               'capital.risk_nav_pct':'Trần rủi ro theo NAV phái sinh; thiếu NAV không tự tính.',
               'capital.estimated_fee_per_contract':'Phí ước tính cho một HĐ mỗi chiều; 0 hiện chờ phí.'}
        hint=hints.get(key,'')
        if isinstance(value, bool):
            variable = self._switch(card, label, value, hint)
            for widget in variable._viking_row.winfo_children():
                if isinstance(widget, ctk.CTkSwitch):
                    widget.configure(font=('Segoe UI',13), height=26)
            variable._viking_row.pack_configure(pady=2)
        else:
            variable = tk.StringVar(value=str(value))
            if choices:
                row = ctk.CTkFrame(card, fg_color='transparent')
                row.pack(fill='x', padx=8, pady=5)
                ctk.CTkLabel(row,text=label,font=('Segoe UI',13),text_color=self.TITLE).pack(side='left')
                ctk.CTkSegmentedButton(row,values=list(choices),variable=variable,
                    font=('Segoe UI',13,'bold'),height=32,selected_color=self.BLUE).pack(side='right')
            else:
                entry = self._field(card,label,value,hint,variable=variable)
                variable._viking_entry = entry
                entry.configure(width=width,height=32,font=FONT_VALUE,show='•' if secret else '',
                    justify='left' if secret or any(word in key for word in ('chat','account','loan')) else 'right')
                is_connection=key.startswith(('connection.','telegram.'))
                entry.master.grid_columnconfigure(0,weight=0 if is_connection else 1)
                entry.master.grid_columnconfigure(1,weight=1 if is_connection else 0)
                entry.grid_configure(sticky='ew')
                entry.configure(width=min(width,180))
                entry.master.pack_configure(pady=4)
                for widget in entry.master.winfo_children():
                    if isinstance(widget,ctk.CTkLabel) and widget is not entry._hint_icon and widget.cget('text'):
                        widget.configure(font=('Segoe UI',13))
                        if is_connection:widget.configure(width=90)
        self.variables[key] = variable
        return variable


class ConnectionWindow(_StableToplevel):
    def __init__(self, app, requested_mode=None):
        super().__init__(app)
        self.app=app
        self.title('RAT VN30 · KẾT NỐI')
        self.configure(fg_color=BG)
        self._window_width,self._window_height=size_popup(self)
        self.transient(app)
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(0,weight=1)
        self.variables={'connection.mode':tk.StringVar(value=requested_mode or app.settings.mode)}
        self.form=ConnectionFields(self.variables)
        self.tabs=StableTabview(self,fg_color='transparent',border_width=0,
            segmented_button_selected_color=BLUE,segmented_button_unselected_color='#3A3F47',command=self._page_changed)
        self.tabs.grid(row=0,column=0,sticky='nsew',padx=8,pady=(4,0))
        self.tabs._segmented_button.configure(font=('Segoe UI',14,'bold'),height=30)
        self.pages={name:self.tabs.add(name) for name in ('DNSE','VỐN','TELEGRAM / LỊCH')}
        for page in self.pages.values():page.grid_columnconfigure(0,weight=1)
        self._connection(self.pages['DNSE'])
        self._capital(self.pages['VỐN'])
        self._telegram(self.pages['TELEGRAM / LỊCH'])
        self.footer=ctk.CTkFrame(self,fg_color='transparent')
        self.footer.grid(row=1,column=0,sticky='ew',padx=16,pady=(4,10))
        self.footer.grid_columnconfigure(0,weight=1)
        self.note=ctk.CTkLabel(self.footer,text='',width=1,text_color=MUTED,font=('Segoe UI',12),anchor='w',justify='left',wraplength=350)
        self.note.grid(row=0,column=0,sticky='ew',padx=(0,8))
        self.note.bind('<Configure>',lambda _:self.note.configure(wraplength=max(120,int(self.note.winfo_width()/self.note._get_widget_scaling())-4)),add='+')
        self.primary=ctk.CTkButton(self.footer,text='',height=34,width=165,font=('Segoe UI',13,'bold'),fg_color=GREEN,command=self.save)
        self.primary.grid(row=0,column=1)
        self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.bind('<Escape>',lambda _:self.destroy())
        self._update_after=None
        self.select_mode(requested_mode or app.settings.mode)
        self.after(80,self.lift)
        self._update_after=self.after(400,self._update_view)

    def _connection(self,page):
        page.grid_columnconfigure((0,1),weight=1,uniform='dnse')
        api=self.api_card=self.form.card(page,'API DNSE')
        self.target_label=ctk.CTkLabel(api,text='',font=('Segoe UI',13,'bold'),text_color=MUTED,anchor='w')
        self.target_label.pack(fill='x',padx=9,pady=(0,4))
        for key,label in (('key','API key'),('secret','API secret')):
            self.form.field(api,'connection.'+key,label,self.app.credentials.get(key,''),secret=True,width=350)
        self.real_account_card=self.form.card(page,'TÀI KHOẢN PHÁI SINH',1)
        for key,label,value in (('account','Tài khoản CKPS',self.app.settings.account_no),('loan','Gói ký quỹ',self.app.settings.loan_package_id)):
            variable=self.form.field(self.real_account_card,'connection.'+key,label,value,width=180)
            if key=='loan':variable._viking_entry.configure(placeholder_text='Tự chọn nếu DNSE có một gói')
        self.otp_card=self.form.card(page,'XÁC THỰC GIAO DỊCH REAL')
        self.otp_card.grid_configure(row=1,columnspan=2)
        otp_row=ctk.CTkFrame(self.otp_card,fg_color='transparent')
        otp_row.pack(fill='x',padx=9,pady=4)
        otp_row.grid_columnconfigure(1,weight=1)
        self.variables['connection.otp_type']=tk.StringVar(value='EMAIL')
        self.variables['connection.otp']=tk.StringVar()
        ctk.CTkSegmentedButton(otp_row,values=['EMAIL','SMART'],variable=self.variables['connection.otp_type'],
            font=('Segoe UI',12,'bold'),height=30,width=150).grid(row=0,column=0,padx=(0,10))
        ctk.CTkEntry(otp_row,textvariable=self.variables['connection.otp'],show='•',height=30,
            font=FONT_VALUE,placeholder_text='Mã OTP').grid(row=0,column=1,sticky='ew')
        ctk.CTkLabel(self.otp_card,text='EMAIL: mã qua email · SMART: mã từ ứng dụng DNSE',
            font=('Segoe UI',11),text_color=MUTED,anchor='w').pack(fill='x',padx=10)
        buttons=ctk.CTkFrame(self.otp_card,fg_color='transparent')
        buttons.pack(fill='x',padx=9,pady=4)
        self.otp_buttons=[ctk.CTkButton(buttons,text='GỬI OTP',width=120,height=30,command=lambda:self.app.send('send_otp')),
            ctk.CTkButton(buttons,text='XÁC THỰC',width=120,height=30,command=lambda:self.app.send('verify_otp',
                self.variables['connection.otp'].get(),{'EMAIL':'email_otp','SMART':'smart_otp'}[self.variables['connection.otp_type'].get()]))]
        for button in self.otp_buttons:button.pack(side='left',padx=(0,8))
        self.packages_label=ctk.CTkLabel(self.otp_card,text='',font=('Segoe UI',12),text_color=MUTED,anchor='w')

    def _capital(self,page):
        page.grid_columnconfigure((0,1),weight=1,uniform='capital')
        limits=self.form.card(page,'HẠN MỨC')
        risk=self.form.card(page,'RỦI RO / PHÍ',1)
        self.capital_keys=('capital_limit','max_contracts','risk_limit','risk_nav_pct','estimated_fee_per_contract')
        for key,label in (('capital_limit','Trần ký quỹ (đ)'),('max_contracts','Tổng HĐ tối đa'),
                ('risk_limit','Lỗ tới SL (đ)'),('risk_nav_pct','Lỗ / NAV (%)'),('estimated_fee_per_contract','Phí / HĐ (đ)')):
            self.form.field(limits if key in {'capital_limit','max_contracts'} else risk,'capital.'+key,label,getattr(self.app.settings,key),width=100)
        self._capital_cards=(limits,risk)
        self.paper_card=self.form.card(page,'TIỀN ẢO PAPER')
        self.paper_card.grid_configure(row=1,columnspan=2)
        self.paper_funds=ctk.CTkFrame(self.paper_card,fg_color='transparent')
        self.paper_funds.pack(fill='x',padx=9,pady=(4,6))
        self.paper_funds.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(self.paper_funds,text='Vốn PAPER (đ)',font=('Segoe UI',13),text_color=MUTED,anchor='w').grid(row=0,column=0,sticky='ew')
        self.variables['paper_balance']=tk.StringVar(value=f"{self.app.view.get('account',{}).get('paper_capital') or self.app.settings.paper_balance:,.0f}")
        self.paper_capital_entry=ctk.CTkEntry(self.paper_funds,textvariable=self.variables['paper_balance'],width=210,height=32,font=FONT_VALUE,justify='right')
        self.paper_capital_entry.grid(row=0,column=1,padx=8)
        self.paper_capital_button=ctk.CTkButton(self.paper_funds,text='ÁP DỤNG',width=120,height=32,font=('Segoe UI',12,'bold'),command=self.apply_capital)
        self.paper_capital_button.grid(row=0,column=2)

    def _telegram(self,page):
        self.notification_body=self.form._content(page,columns=1)
        card=self.form.card(self.notification_body,'TELEGRAM · MỘT KÊNH')
        settings=signal_settings(self.app)
        credentials=getattr(self.app,'signal_credentials',{})
        self.form.field(card,'telegram.token','Bot token',credentials.get('telegram_token',''),secret=True)
        self.form.field(card,'telegram.chat','Chat ID',settings.telegram_chat)
        self.backend_button=ctk.CTkButton(card._viking_header,text='CHẠY',width=100,height=26,
            font=('Segoe UI',12,'bold'),command=self.toggle_backend)
        self.backend_button.pack(side='right')
        self.backend_state=ctk.CTkLabel(card,text='Chưa chạy · Phân tích độc lập BOT giao dịch',font=('Segoe UI',12),text_color=MUTED,anchor='w')
        self.backend_state.pack(fill='x',padx=10,pady=(2,4))
        from .calendar_form import CalendarForm
        self.calendar_form=CalendarForm(self.notification_body,settings=getattr(self.app,'_demo_calendar',None),notice_toggle=False)
        self.calendar_form.grid(row=1,column=0,sticky='ew')
        market=MarketAlertSettings.from_dict(settings.market_alerts)
        self.options={'movement':tk.BooleanVar(value=market.movement_enabled),
            'expiry':self.calendar_form.variables['expiry_notice_enabled'],
            'entry':tk.BooleanVar(value=settings.entry_notifications)}
        row=ctk.CTkFrame(card,fg_color='transparent')
        row.pack(fill='x',padx=10,pady=5)
        for key,title in (('movement','Biến động VN30'),('expiry','Nhắc đáo hạn'),('entry','Vào lệnh')):
            ctk.CTkCheckBox(row,text=title,variable=self.options[key],width=1,
                checkbox_width=16,checkbox_height=16,font=('Segoe UI',12)).pack(side='left',padx=(0,20))

    def notification_values(self):
        settings=signal_settings(self.app)
        market=replace(MarketAlertSettings.from_dict(settings.market_alerts),
            movement_enabled=self.options['movement'].get(),trend_enabled=self.options['entry'].get())
        settings=replace(settings,telegram_chat=self.variables['telegram.chat'].get().strip(),
            telegram_enabled=any(option.get() for option in self.options.values()),
            entry_notifications=self.options['entry'].get(),market_alerts=market.to_dict()).validate()
        credentials={key:self.variables['connection.'+key].get().strip() or self.app.credentials.get(key,'')
                     or os.environ.get('CKPS_DNSE_API_'+key.upper(),'') for key in ('key','secret')}
        credentials['telegram_token']=self.variables['telegram.token'].get().strip()
        return settings,self.calendar_form.values(),credentials

    def save_notifications(self):
        settings,schedule,credentials=self.notification_values()
        from ckps.services import calendar
        if getattr(self.app,'preview_only',False):self.app._demo_calendar=schedule
        else:calendar.write_settings(schedule)
        self.app.signal_credentials=credentials
        save_signal_settings(self.app,settings)
        self.note.configure(text='Đã áp dụng thông báo/lịch vào mẫu trong phiên.' if getattr(self.app,'preview_only',False)
            else 'Đã lưu Telegram/lịch; tắt thông báo vẫn phân tích.',text_color=GREEN)

    def toggle_backend(self):
        try:
            if getattr(self.app,'preview_only',False):
                raise ValueError('Mẫu offline chỉ rà UI; không kết nối hoặc gửi Telegram.')
            session=getattr(self.app,'signal_session',None)
            if session and session.running:
                session.close()
                self.backend_state.configure(text='Đang dừng backend…')
                return
            settings,schedule,credentials=self.notification_values()
            if not credentials['key'] or not credentials['secret']:
                raise ValueError('Nhập API key/secret ở DNSE trước khi chạy tín hiệu.')
            if settings.telegram_enabled and not (credentials['telegram_token'] and settings.telegram_chat):
                raise ValueError('Nhập Bot token và Chat ID trước khi bật thông báo.')
            from ckps.services import calendar
            calendar.write_settings(schedule)
            start_signal_backend(self.app,settings,credentials)
            self.note.configure(text='Đã chạy backend riêng · Không có quyền giao dịch.',text_color=GREEN)
        except Exception as exc:self.note.configure(text=str(exc),text_color=RED)

    def save_limits(self):
        try:
            values={key:quantity(self.variables['capital.'+key].get()) if key=='max_contracts'
                else float(self.variables['capital.'+key].get().replace(',','').strip()) for key in self.capital_keys}
            self.app.save_config(replace(self.app.settings,**values).validate())
            self.note.configure(text='Đã áp dụng hạn mức/phí vào mẫu.' if getattr(self.app,'preview_only',False) else 'Đã lưu hạn mức/phí.',text_color=GREEN)
        except Exception as exc:self.note.configure(text=str(exc),text_color=RED)

    def apply_capital(self):
        try:
            if getattr(self.app,'preview_only',False):
                raise ValueError('Bản mẫu không thay vốn thật; chỉnh tại app giao dịch PAPER.')
            if self.app.settings.mode!='PAPER' or self.app.mode_requested or self.app.switch_pending:
                raise ValueError('Chọn sổ PAPER đang chạy trước khi chỉnh vốn.')
            value=float(self.variables['paper_balance'].get().replace(',','').replace(' ',''))
            from math import isfinite
            if not isfinite(value) or value<=0:raise ValueError('Vốn PAPER phải lớn hơn 0.')
            self.app.send('paper_capital',value)
            self.note.configure(text='Đang áp dụng vốn PAPER…',text_color=MUTED)
        except Exception as exc:self.note.configure(text=str(exc),text_color=RED)

    def capital_result(self,result):
        if result.get('error'):
            self.note.configure(text=result['error'],text_color=RED)
        else:
            self.variables['paper_balance'].set(f"{result['capital']:,.0f}")
            self.note.configure(text='Đã áp dụng vốn PAPER.',text_color=GREEN)

    def select_mode(self,mode):
        self.variables['connection.mode'].set(mode)
        self.target_label.configure(text='PAPER · Giá DNSE, tiền ảo' if mode=='PAPER' else 'REAL · Tài khoản và lệnh DNSE')
        self.real_account_card.grid() if mode=='REAL' else self.real_account_card.grid_remove()
        self.api_card.grid_configure(columnspan=1 if mode=='REAL' else 2)
        self.otp_card.grid() if mode=='REAL' else self.otp_card.grid_remove()
        self.paper_card.grid() if mode=='PAPER' else self.paper_card.grid_remove()
        self.select_page('DNSE')

    def select_page(self,page):
        if page in {'Telegram','LỊCH'}:page='TELEGRAM / LỊCH'
        self.tabs.set(page if page in self.pages else 'DNSE')
        self._page_changed()

    def _page_changed(self):
        if not hasattr(self,'primary'):return
        page,mode=self.tabs.get(),self.variables['connection.mode'].get()
        self.primary.configure(text={'DNSE':'KẾT NỐI DNSE','VỐN':'LƯU HẠN MỨC','TELEGRAM / LỊCH':'LƯU THAY ĐỔI'}[page])
        text='Mẫu: rà cấu hình DNSE/API; không kết nối thật.' if getattr(self.app,'preview_only',False) else ('PAPER chỉ đọc dữ liệu DNSE.' if mode=='PAPER' else 'Kết nối trước, xác thực OTP sau.')
        if page=='VỐN':text='0 = không đặt trần riêng; không thay đổi E/M.'
        elif page=='TELEGRAM / LỊCH':text='Đáo hạn chỉ nhắc · EMA/RSI chỉnh tại RULE.'
        self.note.configure(text=text,text_color=MUTED)
    def connect(self):
        try:
            if getattr(self.app,'preview_only',False):
                raise ValueError('Bản mẫu chỉ rà DNSE/API; mở app giao dịch để kết nối thật.')
            if self.app.switch_pending:raise ValueError('Đang kết nối; chờ hoàn tất.')
            values={key:self.variables['connection.'+key].get().strip() for key in ('mode','key','secret','account','loan')}
            if not all(values[key] or os.environ.get('CKPS_DNSE_API_'+key.upper()) for key in ('key','secret')):
                raise ValueError('Nhập API key và API secret DNSE.')
            if values['mode']=='REAL' and not values['account']:raise ValueError('Nhập tài khoản CKPS cho REAL.')
            settings=replace(self.app.settings,mode=values['mode'],
                account_no=values['account'] if values['mode']=='REAL' else self.app.settings.account_no,
                loan_package_id=values['loan'] if values['mode']=='REAL' else self.app.settings.loan_package_id).validate()
            credentials={key:values[key] for key in ('key','secret')}
            self.app.clear_confirmation()
            self._connecting=True
            self.app.mode_requested=settings.mode
            self.app.switch_pending=(settings,credentials)
            if self.app.runtime:self.app.runtime.close()
            else:
                self.app.switch_pending=None
                self.app._start_runtime(settings,credentials)
            self.app.render()
            self.note.configure(text='Đang kết nối DNSE…',text_color=WARN)
            self.variables['connection.otp'].set('')
        except Exception as exc:self.note.configure(text=str(exc),text_color=RED)

    def save(self):
        if self.tabs.get()=='VỐN':self.save_limits()
        elif self.tabs.get()=='TELEGRAM / LỊCH':
            try:
                self.save_notifications()
            except Exception as exc:self.note.configure(text=str(exc),text_color=RED)
        else:self.connect()

    def _update_view(self):
        self._update_after=None
        session=getattr(self.app,'signal_session',None)
        self.backend_button.configure(text='DỪNG' if session and session.running else 'CHẠY')
        if session:self.backend_state.configure(text=session.status)
        packages=self.app.view.get('loan_packages',[])
        self.packages_label.configure(text=' · '.join(f"{p['id']} {p['name']}" for p in packages[:2]))
        self.packages_label.pack(fill='x',padx=9,pady=(0,4)) if packages else self.packages_label.pack_forget()
        for button in self.otp_buttons:button.configure(state='normal' if self.app.settings.mode=='REAL' and self.app.runtime else 'disabled')
        self.primary.configure(state='disabled' if self.app.switch_pending else 'normal')
        self.paper_capital_button.configure(state='normal' if self.app.settings.mode=='PAPER' and not self.app.mode_requested and not self.app.switch_pending else 'disabled')
        if getattr(self,'_connecting',False) and not self.app.switch_pending:
            if self.app.view.get('market_ready'):
                self.note.configure(text='Đã nhận giá DNSE · BOT OFF',text_color=GREEN);self._connecting=False
            elif self.app.view.get('market_connection',{}).get('connected'):
                self.note.configure(text='Đã kết nối DNSE · Chờ giá mới',text_color=MUTED);self._connecting=False
            elif self.app.view.get('error') or self.app.view.get('market_connection',{}).get('error'):
                self.note.configure(text=self.app.view.get('error') or self.app.view['market_connection']['error'],text_color=RED);self._connecting=False
            elif not self.app.runtime:
                self.note.configure(text='Chưa kết nối được. Kiểm tra LOG.',text_color=RED);self._connecting=False
        self._update_after=self.after(400,self._update_view)

    def destroy(self):
        if self._update_after:self.after_cancel(self._update_after)
        if not self.app.switch_pending:
            self.app.mode_requested=None
            self.app.ui_status=None
            self.app.mode_choice.set(self.app.settings.mode)
        super().destroy()
        if not self.app.closing:self.app.render()
