"""Compact connection pages built from MayinTien's original cards and fields."""
from dataclasses import replace
import os
from math import ceil
import tkinter as tk
import customtkinter as ctk
from .forms import OriginalRuleForms
from .widgets import StableTabview, _StableToplevel, FONT_VALUE
from ..theme import BG, GREEN, RED, MUTED, BLUE, WARN
from ckps.models import quantity


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
        if isinstance(value, bool):
            variable = self._switch(card, label, value, '')
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
                entry = self._field(card,label,value,'',variable=variable)
                variable._viking_entry = entry
                entry.configure(width=width,height=32,font=FONT_VALUE,show='•' if secret else '',
                    justify='left' if secret or any(word in key for word in ('chat','account','loan')) else 'right')
                entry.master.pack_configure(pady=4)
                for widget in entry.master.winfo_children():
                    if isinstance(widget,ctk.CTkLabel) and widget.cget('text'):
                        widget.configure(font=('Segoe UI',13))
        self.variables[key] = variable
        return variable


class ConnectionWindow(_StableToplevel):
    def __init__(self, app, requested_mode=None):
        super().__init__(app)
        self.app=app
        self.title('RAT VN30 · KẾT NỐI')
        self.configure(fg_color=BG)
        self._window_width=min(620,self.winfo_screenwidth()-60)
        self.geometry(f'{self._window_width}x320')
        self.minsize(min(560,self._window_width),260)
        self.transient(app)
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(0,weight=1)
        self.variables={'connection.mode':tk.StringVar(value=requested_mode or app.settings.mode)}
        self.form=ConnectionFields(self.variables)
        self.tabs=StableTabview(self,fg_color='transparent',border_width=0,
            segmented_button_selected_color=BLUE,segmented_button_unselected_color='#3A3F47',command=self._page_changed)
        self.tabs.grid(row=0,column=0,sticky='nsew',padx=8,pady=(4,0))
        self.tabs._segmented_button.configure(font=('Segoe UI',14,'bold'),height=30)
        self.pages={name:self.tabs.add(name) for name in ('DNSE','VỐN','Telegram','LỊCH')}
        for page in self.pages.values():page.grid_columnconfigure(0,weight=1)
        self._connection(self.pages['DNSE'])
        self._capital(self.pages['VỐN'])
        self._telegram(self.pages['Telegram'])
        from .calendar_form import CalendarForm
        self.calendar_form=CalendarForm(self.pages['LỊCH'],settings=getattr(app,'_demo_calendar',None))
        self.calendar_form.grid(row=0,column=0,sticky='nsew')
        self.footer=ctk.CTkFrame(self,fg_color='transparent')
        self.footer.grid(row=1,column=0,sticky='ew',padx=16,pady=(4,10))
        self.footer.grid_columnconfigure(0,weight=1)
        self.note=ctk.CTkLabel(self.footer,text='',text_color=MUTED,font=('Segoe UI',12),anchor='w',justify='left',wraplength=350)
        self.note.grid(row=0,column=0,sticky='ew',padx=(0,8))
        self.primary=ctk.CTkButton(self.footer,text='',height=34,width=165,font=('Segoe UI',13,'bold'),fg_color=GREEN,command=self.save)
        self.primary.grid(row=0,column=1)
        self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.bind('<Escape>',lambda _:self.destroy())
        self._fit_after=self._update_after=None
        self.select_mode(requested_mode or app.settings.mode)
        self.after(80,self.lift)
        self._update_after=self.after(400,self._update_view)

    def _connection(self,page):
        api=self.form.card(page,'API DNSE')
        self.target_label=ctk.CTkLabel(api,text='',font=('Segoe UI',13,'bold'),text_color=MUTED,anchor='w')
        self.target_label.pack(fill='x',padx=9,pady=(0,4))
        for key,label in (('key','API key'),('secret','API secret')):
            self.form.field(api,'connection.'+key,label,self.app.credentials.get(key,''),secret=True,width=350)
        self.real_rows=[]
        for key,label,value in (('account','Tài khoản CKPS',self.app.settings.account_no),('loan','Gói ký quỹ',self.app.settings.loan_package_id)):
            variable=self.form.field(api,'connection.'+key,label,value,width=350)
            self.real_rows.append(variable._viking_entry.master)
            if key=='loan':variable._viking_entry.configure(placeholder_text='Tự chọn nếu DNSE có một gói')
        self.otp_card=self.form.card(page,'XÁC THỰC GIAO DỊCH REAL')
        self.otp_card.grid_configure(row=1)
        otp_row=ctk.CTkFrame(self.otp_card,fg_color='transparent')
        otp_row.pack(fill='x',padx=9,pady=4)
        otp_row.grid_columnconfigure(1,weight=1)
        self.variables['connection.otp_type']=tk.StringVar(value='EMAIL')
        self.variables['connection.otp']=tk.StringVar()
        ctk.CTkSegmentedButton(otp_row,values=['EMAIL','SMART'],variable=self.variables['connection.otp_type'],
            font=('Segoe UI',12,'bold'),height=30,width=150).grid(row=0,column=0,padx=(0,10))
        ctk.CTkEntry(otp_row,textvariable=self.variables['connection.otp'],show='•',height=30,
            font=FONT_VALUE,placeholder_text='Mã OTP').grid(row=0,column=1,sticky='ew')
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
                ('risk_limit','Rủi ro tới SL (đ)'),('risk_nav_pct','Rủi ro / NAV (%)'),('estimated_fee_per_contract','Phí / HĐ / chiều (đ)')):
            self.form.field(limits if key in {'capital_limit','max_contracts'} else risk,'capital.'+key,label,getattr(self.app.settings,key),width=130)
        self.capital_advanced = tk.BooleanVar(value=any(getattr(self.app.settings,key) for key in self.capital_keys))
        self.capital_advanced_switch = ctk.CTkSwitch(page,text='HẠN MỨC NÂNG CAO',variable=self.capital_advanced,
            command=lambda: self._show_capital_advanced(limits,risk),font=('Segoe UI',12),progress_color=GREEN)
        self.capital_advanced_switch.grid(row=2,column=0,columnspan=2,sticky='w',padx=8,pady=5)
        self._capital_cards=(limits,risk)
        self._show_capital_advanced(limits,risk)
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

    def _show_capital_advanced(self, limits, risk):
        for card in (limits, risk):
            card.grid() if self.capital_advanced.get() else card.grid_remove()
        if hasattr(self,'primary'):
            self._page_changed()

    def _telegram(self,page):
        card=self.form.card(page,'TELEGRAM · TÍN HIỆU')
        ctk.CTkLabel(card,text='Biến động VN30 · Nhắc đáo hạn · Thông báo vào lệnh.',
            font=('Segoe UI',13),text_color=MUTED,anchor='w',justify='left',wraplength=550).pack(fill='x',padx=10,pady=8)
        ctk.CTkLabel(card,text='Mở backend để cấu hình và chạy thông báo.',font=('Segoe UI',13),
            text_color=MUTED,anchor='w').pack(fill='x',padx=10,pady=(0,10))

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
        for row in self.real_rows:
            row.pack(fill='x',padx=8,pady=4) if mode=='REAL' else row.pack_forget()
        self.otp_card.grid() if mode=='REAL' else self.otp_card.grid_remove()
        self.paper_card.grid() if mode=='PAPER' else self.paper_card.grid_remove()
        self.select_page('DNSE')

    def select_page(self,page):
        self.tabs.set(page if page in self.pages else 'DNSE')
        self._page_changed()

    def _page_changed(self):
        if not hasattr(self,'primary'):return
        page,mode=self.tabs.get(),self.variables['connection.mode'].get()
        self.primary.configure(text={'DNSE':'KẾT NỐI DNSE','VỐN':'LƯU HẠN MỨC','Telegram':'MỞ TELEGRAM','LỊCH':'LƯU LỊCH'}[page])
        text='Mẫu: rà cấu hình DNSE/API; không kết nối thật.' if getattr(self.app,'preview_only',False) else ('PAPER chỉ đọc dữ liệu DNSE.' if mode=='PAPER' else 'Kết nối trước, xác thực OTP sau.')
        if page=='VỐN':text='0 = không đặt trần riêng; không thay đổi E/M.'
        elif page=='Telegram':text='Một kênh thông báo; bot quản lý vị thế tại app.'
        elif page=='LỊCH':text='Đáo hạn chỉ nhắc; ngày nghỉ và phiên giữ kiểm tra.'
        self.note.configure(text=text,text_color=MUTED)
        if self._fit_after:self.after_cancel(self._fit_after)
        self._fit_rounds=0
        self._fit_after=self.after(30,self._fit_page)

    def _fit_page(self):
        self._fit_after=None
        page=self.pages[self.tabs.get()]
        if page.winfo_height()<=1:
            self._fit_after=self.after(50,self._fit_page)
            return
        scale=self._get_window_scaling()
        cards=[child for child in page.winfo_children() if isinstance(child,ctk.CTkFrame) and child.winfo_manager()]
        rows={}
        for child in cards:
            row=child.grid_info()['row']
            rows[row]=max(rows.get(row,0),child.winfo_reqheight()+12*scale)
        content=sum(rows.values())
        controls=self.tabs._segmented_button.winfo_reqheight()+self.footer.winfo_reqheight()
        height=min(self.winfo_screenheight()-90,max(270,ceil((content+controls)/scale)+48))
        x=max(0,(self.winfo_screenwidth()-self._window_width)//2)
        y=max(0,(self.winfo_screenheight()-height)//2)
        self.geometry(f'{self._window_width}x{height}+{x}+{y}')
        if self._fit_rounds<2:
            self._fit_rounds+=1
            self._fit_after=self.after(35,self._fit_page)

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
        elif self.tabs.get()=='Telegram':self.app.open_signal_backend()
        elif self.tabs.get()=='LỊCH':
            try:
                from ckps.services import calendar
                settings=self.calendar_form.values()
                if getattr(self.app,'preview_only',False):self.app._demo_calendar=settings
                else:calendar.write_settings(settings)
                self.note.configure(text='Đã áp dụng lịch vào mẫu trong phiên.' if getattr(self.app,'preview_only',False) else 'Đã lưu lịch cho app và backend.',text_color=GREEN)
            except Exception as exc:self.note.configure(text=str(exc),text_color=RED)
        else:self.connect()

    def _update_view(self):
        self._update_after=None
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
        for timer in (self._fit_after,self._update_after):
            if timer:self.after_cancel(timer)
        if not self.app.switch_pending:
            self.app.mode_requested=None
            self.app.ui_status=None
            self.app.mode_choice.set(self.app.settings.mode)
        super().destroy()
        if not self.app.closing:self.app.render()
