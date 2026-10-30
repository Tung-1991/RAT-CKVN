"""Compact connection pages built from MayinTien's original cards and fields."""
from dataclasses import replace
import os
import time
import tkinter as tk
import customtkinter as ctk
from .forms import OriginalRuleForms
from .widgets import StableTabview, _StableToplevel, FONT_VALUE, size_popup, choice_bar
from ..theme import BG, GREEN, RED, MUTED, BLUE, WARN
from ckps.rules.market_alerts import MarketAlertSettings
from .connection_status import otp_status
from .connection_preview import ConnectionPreviewMixin
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
        hints={'connection.key':'API đọc giá cho PAPER; REAL dùng thêm tài khoản và OTP. Ghi nhớ tùy chọn bằng mã hóa Windows.',
               'connection.secret':'API secret DNSE dùng cho phiên kết nối; không ghi vào log.',
               'connection.account':'Số tiểu khoản phái sinh DNSE dùng cho REAL.',
               'connection.loan':'Gói ký quỹ DNSE. Nếu chỉ có một gói, app tự chọn.'}
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
                choice_bar(row,values=list(choices),variable=variable,
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


class ConnectionWindow(ConnectionPreviewMixin,_StableToplevel):
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
            segmented_button_selected_color=BLUE,segmented_button_unselected_color='#222E3B',command=self._page_changed)
        self.tabs.grid(row=0,column=0,sticky='nsew',padx=8,pady=(4,0))
        self.tabs._segmented_button.configure(font=('Segoe UI',14,'bold'),height=30)
        self.pages={name:self.tabs.add(name) for name in ('DNSE / VỐN','TELEGRAM / LỊCH')}
        for page in self.pages.values():page.grid_columnconfigure(0,weight=1)
        self.connection_body=self.form._content(self.pages['DNSE / VỐN'],columns=2)
        self._connection(self.connection_body)
        self._paper_capital(self.connection_body)
        self._telegram(self.pages['TELEGRAM / LỊCH'])
        self.footer=ctk.CTkFrame(self,fg_color='transparent')
        self.footer.grid(row=1,column=0,sticky='ew',padx=16,pady=(4,10))
        self.footer.grid_columnconfigure(0,weight=1)
        self.note=ctk.CTkLabel(self.footer,text='',width=1,text_color=MUTED,font=('Segoe UI',12),anchor='w',justify='left',wraplength=350)
        self.note.grid(row=0,column=0,sticky='ew',padx=(0,8))
        self.note.bind('<Configure>',lambda _:self.note.configure(wraplength=max(120,int(self.note.winfo_width()/self.note._get_widget_scaling())-4)),add='+')
        self.primary=ctk.CTkButton(self.footer,text='',height=34,width=165,font=('Segoe UI',13,'bold'),fg_color=GREEN,command=self.save)
        self.primary.grid(row=0,column=1)
        self.save_button=ctk.CTkButton(self.footer,text='LƯU',width=74,height=34,font=('Segoe UI',13,'bold'),
            fg_color=BLUE,command=self.save_connection)
        self.save_button.grid(row=0,column=1,padx=(0,8))
        self.primary.grid_configure(column=2)
        self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.bind('<Escape>',lambda _:self.destroy())
        self._update_after=None
        self.select_mode(requested_mode or app.settings.mode)
        self.after(80,self.lift)
        self._update_after=self.after(400,self._update_view)

    def _connection(self,page):
        page.grid_columnconfigure((0,1),weight=1,uniform='dnse')
        api=self.api_card=self.form.card(page,'API DNSE')
        self.read_api_button=ctk.CTkButton(api._viking_header,text='ĐỌC MẪU' if getattr(self.app,'preview_only',False) else 'ĐỌC API',
            width=88,height=27,font=('Segoe UI',12,'bold'),command=self.read_api)
        self.read_api_button.pack(side='right')
        self.key_visibility=ctk.CTkButton(api._viking_header,text='HIỆN',width=50,height=27,
            font=('Segoe UI',12),fg_color='#3A3F47',command=self.toggle_key_visibility)
        self.key_visibility.pack(side='right',padx=5)
        self.target_label=ctk.CTkLabel(api,text='',font=('Segoe UI',13,'bold'),text_color=MUTED,anchor='w')
        self.target_label.pack(fill='x',padx=9,pady=(0,4))
        for key,label in (('key','API key'),('secret','API secret')):
            value=getattr(self.app,'connection_profile',self.app.credentials).get(key,'') or os.environ.get('CKPS_DNSE_API_'+key.upper(),'')
            self.form.field(api,'connection.'+key,label,value,secret=True,width=350)
        self.remember=tk.BooleanVar(value=getattr(self.app,'remember_connection',False))
        self.form._hint_icon(api._viking_header,'Một cặp API dùng chung cho PAPER/REAL, dữ liệu và tín hiệu. Ghi nhớ sẽ mã hóa key/secret và phiên OTP còn hạn bằng Windows theo người dùng; bỏ ghi nhớ rồi LƯU để xóa.').pack(side='left',padx=5)
        ctk.CTkCheckBox(api,text='Ghi nhớ kết nối',variable=self.remember,
            font=('Segoe UI',12),checkbox_width=16,checkbox_height=16).pack(fill='x',padx=10,pady=(4,8))
        self._build_account_preview(page)
        self.otp_card=self.form.card(page,'XÁC THỰC GIAO DỊCH REAL')
        self.otp_card.grid_configure(row=1,column=0,columnspan=2)
        otp_row=ctk.CTkFrame(self.otp_card,fg_color='transparent')
        otp_row.pack(fill='x',padx=9,pady=4)
        otp_row.grid_columnconfigure(1,weight=1)
        self.variables['connection.otp_type']=tk.StringVar(value='EMAIL')
        self.variables['connection.otp']=tk.StringVar()
        choice_bar(otp_row,values=['EMAIL','SMART'],variable=self.variables['connection.otp_type'],
            font=('Segoe UI',12,'bold'),height=30,width=150).grid(row=0,column=0,padx=(0,10))
        self.otp_entry=ctk.CTkEntry(otp_row,textvariable=self.variables['connection.otp'],show='•',height=30,
            font=FONT_VALUE,placeholder_text='Mã OTP')
        self.otp_entry.grid(row=0,column=1,sticky='ew')
        self.otp_status=ctk.CTkLabel(self.otp_card,text='',font=('Segoe UI',12),text_color=WARN,
            anchor='w',justify='left',wraplength=315)
        self.otp_status.pack(fill='x',padx=10,pady=3)
        self.form._hint_icon(self.otp_card._viking_header,'PAPER không cần OTP. REAL chọn EMAIL để nhận mã qua email hoặc SMART lấy mã từ app DNSE. Chỉ lưu phiên xác thực khi bật Ghi nhớ kết nối, không lưu mã OTP dùng một lần.').pack(side='left',padx=5)
        buttons=ctk.CTkFrame(self.otp_card,fg_color='transparent')
        buttons.pack(fill='x',padx=9,pady=4)
        self.otp_buttons=[ctk.CTkButton(buttons,text='GỬI EMAIL',width=120,height=30,command=self.send_otp),
            ctk.CTkButton(buttons,text='XÁC THỰC',width=120,height=30,command=self.verify_otp)]
        for button in self.otp_buttons:button.pack(side='left',padx=(0,8))

    def _paper_capital(self,page):
        self.paper_card=self.form.card(page,'TIỀN ẢO PAPER')
        self.paper_card.grid_configure(row=2,columnspan=2)
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
        self.form._hint_icon(card._viking_header,'Dùng chung API DNSE ở DNSE / VỐN; Telegram cần Bot token/Chat ID riêng. Tín hiệu / Lệnh gồm gợi ý P1/P2/E và trạng thái gửi/khớp/hủy/lỗi của lệnh mở, đóng/giảm, SL/TP/TSL/DYNAMIC. Chỉ thông báo, không nhận lệnh từ Telegram. Tắt nhóm vẫn phân tích, không gửi bù tin cũ.').pack(side='left',padx=5)
        self.backend_state=ctk.CTkLabel(card,text='CHƯA CHẠY',font=('Segoe UI',12),text_color=MUTED,anchor='w')
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
        for key,title in (('movement','Biến động VN30'),('expiry','Nhắc đáo hạn'),('entry','Tín hiệu / Lệnh')):
            ctk.CTkCheckBox(row,text=title,variable=self.options[key],width=1,
                checkbox_width=16,checkbox_height=16,font=('Segoe UI',12)).pack(side='left',padx=(0,20))

    def notification_values(self):
        settings=signal_settings(self.app)
        market=replace(MarketAlertSettings.from_dict(settings.market_alerts),
            movement_enabled=self.options['movement'].get(),trend_enabled=self.options['entry'].get())
        settings=replace(settings,telegram_chat=self.variables['telegram.chat'].get().strip(),
            telegram_enabled=any(option.get() for option in self.options.values()),
            entry_notifications=self.options['entry'].get(),market_alerts=market.to_dict()).validate()
        credentials=self.api_credentials()
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

    def remember_values(self, credentials):
        if getattr(self.app,'preview_only',False):
            return
        from ckps.connections.secure_session import remember_connection, forget_connection
        if self.remember.get():remember_connection(credentials)
        else:forget_connection()
        self.app.remember_connection=self.remember.get()

    def save_connection(self):
        try:
            if self.app.mode_requested or self.app.switch_pending:
                raise ValueError('Hoàn tất kết nối sổ đang chọn trước khi lưu.')
            settings=replace(self.app.settings,
                account_no=self.variables['connection.account'].get().strip() if self.app.settings.mode=='REAL' else self.app.settings.account_no,
                loan_package_id=self.variables['connection.loan'].get().strip() if self.app.settings.mode=='REAL' else self.app.settings.loan_package_id).validate()
            if self.app.runtime and (settings.account_no!=self.app.settings.account_no or settings.loan_package_id!=self.app.settings.loan_package_id):
                raise ValueError('Tài khoản/gói đã đổi: bấm KẾT NỐI DNSE để đối soát sổ mới.')
            credentials=self.api_credentials()
            self.remember_values(credentials)
            self.app.save_config(settings)
            self.app.connection_profile=credentials
            if self.remember.get():self.app.send('remember_session')
            self.note.configure(text='Đã áp dụng vào mẫu trong phiên.' if getattr(self.app,'preview_only',False)
                else 'Đã lưu cấu hình và ghi nhớ kết nối bằng Windows.' if self.remember.get()
                else 'Đã lưu cấu hình · Kết nối chỉ dùng trong phiên.',text_color=GREEN)
        except Exception as exc:self.note.configure(text=str(exc),text_color=RED)

    def send_otp(self):
        if not self.otp_ready():return
        if self.variables['connection.otp_type'].get()!='EMAIL':
            self.note.configure(text='SMART: lấy mã trong ứng dụng DNSE rồi bấm XÁC THỰC.',text_color=MUTED)
            return
        self.app.send('send_otp')
        self.note.configure(text='Đang yêu cầu DNSE gửi email OTP…',text_color=MUTED)

    def otp_ready(self):
        if getattr(self.app,'preview_only',False) or self.variables['connection.mode'].get()!='REAL' or self.app.settings.mode!='REAL' or not self.app.runtime or self.app.mode_requested or self.app.switch_pending:
            self.note.configure(text='Kết nối sổ REAL trước khi xác thực OTP.',text_color=RED)
            return False
        if not self.otp_matches_active():
            self.note.configure(text='Thông số kết nối đã đổi; KẾT NỐI DNSE trước khi xác thực OTP.',text_color=RED)
            return False
        return True

    def otp_matches_active(self):
        if any(self.variables['connection.'+key].get().strip()!=getattr(self.app.settings,setting)
            for key,setting in (('account','account_no'),('loan','loan_package_id'))):return False
        return all((self.variables['connection.'+key].get().strip() or os.environ.get('CKPS_DNSE_API_'+key.upper(),''))
            == (self.app.credentials.get(key,'') or os.environ.get('CKPS_DNSE_API_'+key.upper(),'')) for key in ('key','secret'))

    def verify_otp(self):
        if not self.otp_ready():return
        code=self.variables['connection.otp'].get().strip()
        if not code:
            self.note.configure(text='Nhập mã OTP từ email hoặc ứng dụng DNSE.',text_color=RED)
            return
        self.app.send('verify_otp',code,{'EMAIL':'email_otp','SMART':'smart_otp'}[self.variables['connection.otp_type'].get()])
        self.variables['connection.otp'].set('')
        self.note.configure(text='Đang xác thực OTP…',text_color=MUTED)

    def otp_result(self, name):
        self.note.configure(text='Đã yêu cầu gửi OTP qua email.' if name=='send_otp'
            else 'OTP đã xác thực · BOT vẫn OFF.' if not self.app.view.get('armed')
            else 'OTP đã xác thực · BOT đang ON.',text_color=GREEN)

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
        self.paper_card.grid() if mode=='PAPER' else self.paper_card.grid_remove()
        self.select_page('DNSE')

    def select_page(self,page):
        if page in {'Telegram','LỊCH'}:page='TELEGRAM / LỊCH'
        if page in {'DNSE','VỐN'}:page='DNSE / VỐN'
        self.tabs.set(page if page in self.pages else 'DNSE / VỐN')
        self._page_changed()

    def _page_changed(self):
        if not hasattr(self,'primary'):return
        page,mode=self.tabs.get(),self.variables['connection.mode'].get()
        self.primary.configure(text='KẾT NỐI DNSE' if page=='DNSE / VỐN' else 'LƯU THAY ĐỔI')
        self.save_button.grid() if page=='DNSE / VỐN' else self.save_button.grid_remove()
        text='MẪU OFFLINE' if getattr(self.app,'preview_only',False) else ''
        self.note.configure(text=text,text_color=MUTED)
    def connect(self):
        try:
            if getattr(self.app,'preview_only',False):
                raise ValueError('Bản mẫu chỉ rà DNSE/API; mở app giao dịch để kết nối thật.')
            if self.app.switch_pending:raise ValueError('Đang kết nối; chờ hoàn tất.')
            values={key:self.variables['connection.'+key].get().strip() for key in ('mode','key','secret','account','loan')}
            if not all(values[key] or os.environ.get('CKPS_DNSE_API_'+key.upper()) for key in ('key','secret')):
                raise ValueError('Nhập API key và API secret DNSE.')
            credentials=self.api_credentials()
            if self._profile_signature!=self._signature(credentials) or time.time()-self.preview_profile.get('observed_at',0)>300:
                self.read_api(connect_after=True)
                return
            if values['mode']=='REAL' and not values['account']:raise ValueError('Chọn tài khoản CKPS từ kết quả ĐỌC API.')
            if values['mode']=='REAL' and not values['loan']:raise ValueError('Chọn gói ký quỹ từ kết quả ĐỌC API.')
            settings=replace(self.app.settings,mode=values['mode'],
                account_no=values['account'] if values['mode']=='REAL' else self.app.settings.account_no,
                loan_package_id=values['loan'] if values['mode']=='REAL' else self.app.settings.loan_package_id).validate()
            self.remember_values(credentials)
            session=getattr(self.app,'signal_session',None)
            signal_credentials=getattr(self.app,'signal_credentials',{})
            if session and session.running and any(signal_credentials.get(key)!=credentials[key] for key in ('key','secret')):
                session.close()
                self.app.report('Đã dừng tín hiệu theo API cũ; bấm CHẠY để dùng API DNSE mới.')
            self.app.clear_confirmation()
            self.app._cancel_mode_probe()
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
        if self.tabs.get()=='TELEGRAM / LỊCH':
            try:
                self.save_notifications()
            except Exception as exc:self.note.configure(text=str(exc),text_color=RED)
        else:self.connect()

    def _update_view(self):
        self._update_after=None
        self._drain_profile()
        session=getattr(self.app,'signal_session',None)
        self.backend_button.configure(text='DỪNG' if session and session.running else 'CHẠY')
        if session:self.backend_state.configure(text=session.status)
        otp_enabled=(not getattr(self.app,'preview_only',False) and self.variables['connection.mode'].get()=='REAL'
            and self.app.settings.mode=='REAL' and self.app.runtime and not self.app.mode_requested and not self.app.switch_pending
            and self.otp_matches_active())
        for button in self.otp_buttons:button.configure(state='normal' if otp_enabled else 'disabled')
        self.otp_buttons[0].configure(state='normal' if otp_enabled and self.variables['connection.otp_type'].get()=='EMAIL' else 'disabled')
        self.otp_entry.configure(state='normal' if otp_enabled else 'disabled')
        text,tone=otp_status(self.app.view,self.variables['connection.mode'].get())
        if self.variables['connection.mode'].get()=='REAL' and self.app.settings.mode!='REAL':text='OTP · Kết nối sổ REAL trước khi xác thực'
        elif self.app.settings.mode=='REAL' and not self.otp_matches_active():text='OTP · Thông số đã đổi; cần kết nối lại'
        self.otp_status.configure(text=text,text_color=GREEN if tone=='green' else WARN if tone=='amber' else MUTED)
        self.primary.configure(state='disabled' if self.app.switch_pending else 'normal')
        self.save_button.configure(state='disabled' if self.app.switch_pending or self.app.mode_requested else 'normal')
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
        if self._probe:self._probe.close()
        if not self.app.switch_pending:
            self.app._cancel_mode_probe()
            self.app.mode_requested=None
            self.app.ui_status=None
            self.app.mode_choice.set(self.app.settings.mode)
        super().destroy()
        if not self.app.closing:self.app.render()
