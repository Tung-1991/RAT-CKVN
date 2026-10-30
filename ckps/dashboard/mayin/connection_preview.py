"""Account/package selection and API preview using the native MayinTien card."""
from copy import deepcopy
import hashlib
import json
import os
import queue
import time
import tkinter as tk

import customtkinter as ctk

from ckps.connections.dnse.fees import package_fees
from ..formatting import money, clock
from ..theme import MUTED, GREEN, RED
from .widgets import option_menu


class ConnectionPreviewMixin:
    def api_credentials(self):
        return {key:self.variables['connection.'+key].get().strip()
            or os.environ.get('CKPS_DNSE_API_'+key.upper(),'') for key in ('key','secret')}

    @staticmethod
    def _signature(credentials):
        return hashlib.sha256(json.dumps(credentials,sort_keys=True).encode()).hexdigest()

    def _build_account_preview(self,page):
        self.preview_profile={}
        self._profile_signature=''
        self._probe=None
        self._probe_revision=None
        self._connect_after_read=False
        self.real_account_card=self.form.card(page,'DNSE · PREVIEW',1)
        self.variables['connection.account']=tk.StringVar(value=self.app.settings.account_no)
        self.variables['connection.loan']=tk.StringVar(value=self.app.settings.loan_package_id)
        self.account_display=tk.StringVar(value='Đọc API để chọn')
        self.package_display=tk.StringVar(value='Đọc API để chọn')
        self._account_options={}
        self._package_options={}
        for title,variable,command,name in (('Tài khoản CKPS',self.account_display,self._select_account,'account_menu'),
                ('Gói ký quỹ',self.package_display,self._select_package,'package_menu')):
            row=ctk.CTkFrame(self.real_account_card,fg_color='transparent')
            row.pack(fill='x',padx=10,pady=4)
            row.grid_columnconfigure(1,weight=1)
            ctk.CTkLabel(row,text=title,font=('Segoe UI',13),width=100,anchor='w').grid(row=0,column=0,sticky='w')
            menu=option_menu(row,values=['Đọc API để chọn'],variable=variable,command=command,
                height=30,width=1,font=('Segoe UI',13),dynamic_resizing=False,state='disabled')
            menu.grid(row=0,column=1,sticky='ew',padx=(4,0))
            setattr(self,name,menu)
        self.profile_balance=ctk.CTkLabel(self.real_account_card,text='Ký quỹ còn / đã dùng: — / —',
            font=('Segoe UI',13),text_color=MUTED,anchor='w',justify='left',wraplength=320)
        self.profile_balance.pack(fill='x',padx=10,pady=(4,2))
        self.profile_fee=ctk.CTkLabel(self.real_account_card,text='Phí gói · CHỜ DNSE',font=('Segoe UI',13),
            text_color=MUTED,anchor='w',justify='left',wraplength=320)
        self.profile_fee.pack(fill='x',padx=10,pady=2)
        self.form._hint_icon(self.real_account_card._viking_header,
            'API DNSE dùng chung cho giá, PAPER/REAL và backend tín hiệu. Phí gói lấy từ loan-packages; chưa gồm thuế/phí Sở chưa được trả. Gói bậc thang cần mức áp dụng từ DNSE.').pack(side='left',padx=7)
        self.profile_state=ctk.CTkLabel(self.real_account_card,text='Chưa đọc API',font=('Segoe UI',12),
            text_color=MUTED,anchor='w',justify='left',wraplength=320)
        self.profile_state.pack(fill='x',padx=10,pady=(2,7))
        for widget in (self.profile_balance,self.profile_fee,self.profile_state):
            widget.bind('<Configure>',lambda _,w=widget:w.configure(wraplength=max(100,int(w.winfo_width()/w._get_widget_scaling())-4)),add='+')
        cached=getattr(self.app,'connection_preview',{})
        if cached.get('signature')==self._signature(self.api_credentials()):
            self._show_profile(cached['profile'])

    def toggle_key_visibility(self):
        shown=self.key_visibility.cget('text')=='HIỆN'
        for key in ('key','secret'):self.variables['connection.'+key]._viking_entry.configure(show='' if shown else '•')
        self.key_visibility.configure(text='ẨN' if shown else 'HIỆN')

    def read_api(self,connect_after=False):
        try:
            credentials=self.api_credentials()
            if getattr(self.app,'preview_only',False):
                package={'id':2279,'name':'Gói mẫu','tradingFee':{'schemaType':'FIXED','fixedTradingFee':2000,'fixedDailyCloseTradingFee':2000}}
                self._show_profile({'accounts':[{'id':'1234567890'}],'account_no':'1234567890',
                    'packages':[package],'loan_package_id':'2279','balance':{'remaining_margin':100_000_000,'used_margin':0},
                    'fees':package_fees(package),'observed_at':time.time()})
                self.profile_state.configure(text='MẪU OFFLINE · Không đọc tài khoản thật')
                return
            if not all(credentials.values()):raise ValueError('Nhập API key và API secret DNSE trước khi đọc.')
            if not self._probe:
                from ckps.services.connection_probe import ConnectionProbe
                self._probe=ConnectionProbe()
            same=self._profile_signature==self._signature(credentials)
            account=self.variables['connection.account'].get() if same else ''
            package=self.variables['connection.loan'].get() if same else ''
            self._probe_signature=self._signature(credentials)
            self._probe_revision=self._probe.request(credentials,account,package)
            self._connect_after_read=connect_after
            self.read_api_button.configure(state='disabled')
            self.profile_state.configure(text='Đang đọc tài khoản/gói/phí DNSE…',text_color=MUTED)
        except Exception as exc:self.note.configure(text=str(exc),text_color=RED)

    def _drain_profile(self):
        if not self._probe:return
        while True:
            try:revision,profile=self._probe.events.get_nowait()
            except queue.Empty:break
            if revision!=self._probe_revision:continue
            self.read_api_button.configure(state='normal')
            if self._probe_signature!=self._signature(self.api_credentials()):
                self._connect_after_read=False
                self.profile_state.configure(text='API đã đổi · Đọc lại dữ liệu',text_color=MUTED)
                continue
            if profile.get('error'):
                self._profile_signature=''
                self._connect_after_read=False
                self.profile_state.configure(text=profile['error'],text_color=RED)
                continue
            self._show_profile(profile)
            connect,self._connect_after_read=self._connect_after_read,False
            if connect and (self.variables['connection.mode'].get()=='PAPER' or profile.get('account_no') and profile.get('loan_package_id')):self.connect()

    def _show_profile(self,profile):
        self.preview_profile=deepcopy(profile)
        self._profile_signature=self._signature(self.api_credentials())
        self.variables['connection.account'].set(profile.get('account_no',''))
        self.variables['connection.loan'].set(profile.get('loan_package_id',''))
        self._account_options={row['id']:row['id'] for row in profile.get('accounts',[])}
        self._package_options={f"{row.get('name') or 'Gói'} · {row['id']}":str(row['id']) for row in profile.get('packages',[])}
        for menu,variable,options,selected,waiting in ((self.account_menu,self.account_display,self._account_options,profile.get('account_no'),'Chọn tài khoản'),
                (self.package_menu,self.package_display,self._package_options,profile.get('loan_package_id'),'Chọn gói ký quỹ')):
            values=list(options)
            menu.configure(values=values or [waiting],state='normal' if len(values)>1 else 'disabled')
            variable.set(next((label for label,key in options.items() if key==selected),values[0] if len(values)==1 else waiting))
        balance=profile.get('balance',{})
        self.profile_balance.configure(text='Ký quỹ còn / đã dùng: '+money(balance.get('remaining_margin'))+' / '+money(balance.get('used_margin')))
        self.profile_fee.configure(text=profile.get('fees',{}).get('text','Phí gói · CHỜ DNSE'))
        message='Không có tài khoản CKPS hoạt động' if not self._account_options else 'Chọn tài khoản CKPS' if not profile.get('account_no') else 'Chọn gói ký quỹ' if not profile.get('loan_package_id') else 'API · '+clock(profile.get('observed_at'))
        self.profile_state.configure(text=message,text_color=GREEN if profile.get('loan_package_id') else MUTED)
        self.app.connection_preview={'signature':self._profile_signature,'profile':deepcopy(profile)}

    def _select_account(self,label):
        self.variables['connection.account'].set(self._account_options[label])
        self.variables['connection.loan'].set('')
        self.read_api()

    def _select_package(self,label):
        profile=deepcopy(self.preview_profile)
        package=self._package_options[label]
        profile['loan_package_id']=package
        profile['fees']=package_fees(next(row for row in profile['packages'] if str(row['id'])==package))
        self._show_profile(profile)
