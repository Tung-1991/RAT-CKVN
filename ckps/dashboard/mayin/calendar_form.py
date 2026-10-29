"""Shared compact calendar controls for MAIN connection and signal backend."""
import tkinter as tk
import customtkinter as ctk

from ckps.rules.calendar import CalendarSettings
from ckps.services import calendar
from .connection_window import ConnectionFields
from .widgets import _StableToplevel
from .tokens import *


class CalendarForm(ctk.CTkFrame):
    def __init__(self,parent,*,settings=None,notice_toggle=True):
        super().__init__(parent,fg_color='transparent',height=1,width=1)
        self.settings=settings or calendar.read_settings()
        self.variables={}
        self.grid_columnconfigure(0,weight=1)
        form=ConnectionFields(self.variables)
        card=form.card(self,'LỊCH')
        self.variables['use_dnse_working_dates']=tk.BooleanVar(value=True)
        form._hint_icon(card._viking_header,'Tự cập nhật ngày nghỉ DNSE. Các lựa chọn né chỉ chặn mở mới/vào thêm; không chặn đóng/giảm và E/M. Đáo hạn chỉ gửi nhắc, không cấm giao dịch. Ngày bổ sung dùng YYYY-MM-DD, cách nhau bằng dấu phẩy.').pack(side='left',padx=7)
        flags=ctk.CTkFrame(card,fg_color='transparent')
        flags.pack(fill='x',padx=10,pady=(3,6))
        for key,label in (('block_entry_ato','Né ATO'),('block_entry_atc','Né ATC'),('avoid_vn30_rebalance_entry','Né đổi rổ')):
            variable=tk.BooleanVar(value=getattr(self.settings,key));self.variables[key]=variable
            ctk.CTkCheckBox(flags,text=label,variable=variable,width=105,font=('Segoe UI',12),
                checkbox_width=16,checkbox_height=16).pack(side='left',padx=(0,12))
        self.schedule_button=ctk.CTkButton(card._viking_header,text='NGÀY RIÊNG',width=110,height=26,
            font=('Segoe UI',12),command=self.toggle_dates)
        self.schedule_button.pack(side='right')
        self.custom_dates=ctk.CTkFrame(card,fg_color='transparent')
        self.custom_dates.grid_columnconfigure((0,1),weight=1,uniform='dates')
        for column,(key,label) in enumerate((('manual_closed_dates','Ngày nghỉ riêng'),('vn30_rebalance_dates','Ngày đổi rổ'))):
            cell=ctk.CTkFrame(self.custom_dates,fg_color='transparent')
            cell.grid(row=0,column=column,sticky='ew',padx=4)
            ctk.CTkLabel(cell,text=label,font=('Segoe UI',12),text_color=COL_MUTED,anchor='w').pack(fill='x')
            variable=tk.StringVar(value=', '.join(getattr(self.settings,key)));self.variables[key]=variable
            ctk.CTkEntry(cell,textvariable=variable,height=29,font=('Segoe UI',12),placeholder_text='YYYY-MM-DD').pack(fill='x')
        if self.settings.manual_closed_dates or self.settings.vn30_rebalance_dates:self.toggle_dates()
        notices=ctk.CTkFrame(card,fg_color='transparent')
        notices.pack(fill='x',padx=10,pady=6)
        self.variables['notify_enabled']=tk.BooleanVar(value=self.settings.notify_enabled)
        self.variables['expiry_notice_enabled']=tk.BooleanVar(value=self.settings.expiry_notice_enabled)
        if notice_toggle:
            ctk.CTkCheckBox(notices,text='Nhắc đáo hạn',variable=self.variables['expiry_notice_enabled'],font=('Segoe UI',12),
                checkbox_width=16,checkbox_height=16).pack(side='left',padx=(0,8))
        else:ctk.CTkLabel(notices,text='Báo trước',font=('Segoe UI',12)).pack(side='left',padx=(0,8))
        for key,value,width in (('notice_days',self.settings.notice_days,45),('notice_time',self.settings.notice_time,70)):
            variable=tk.StringVar(value=str(value));self.variables[key]=variable
            if key=='notice_time':ctk.CTkLabel(notices,text='ngày · lúc',font=('Segoe UI',12)).pack(side='left',padx=6)
            ctk.CTkEntry(notices,textvariable=variable,width=width,height=28,justify='center',font=('Segoe UI',12)).pack(side='left')
        info=calendar.summary()
        text=('Đáo hạn ' if info['expiry_confirmed'] else 'Dự kiến ')+info['next_expiry']
        self.calendar_status=ctk.CTkLabel(card,text=text,font=('Segoe UI',12),text_color=COL_MUTED,anchor='w')
        self.calendar_status.pack(fill='x',padx=10,pady=(0,6))

    def toggle_dates(self):
        if self.custom_dates.winfo_manager():
            self.custom_dates.pack_forget()
            self.schedule_button.configure(text='NGÀY RIÊNG')
        else:
            self.custom_dates.pack(fill='x',padx=6,pady=4)
            self.schedule_button.configure(text='THU GỌN')

    def values(self):
        values={key:variable.get() for key,variable in self.variables.items()}
        values['notify_enabled']=values['expiry_notice_enabled']
        values['notice_days']=int(values['notice_days'])
        return CalendarSettings.from_dict(values)


class CalendarWindow(_StableToplevel):
    def __init__(self,app):
        super().__init__(app)
        self.title('RAT VN30 · LỊCH / NGÀY NÉ')
        width=min(620,self.winfo_screenwidth()-60);height=min(370,self.winfo_screenheight()-80)
        x=max(0,(self.winfo_screenwidth()-width)//2)
        y=max(0,(self.winfo_screenheight()-height-32)//2)
        self.geometry(f'{width}x{height}+{x}+{y}');self.minsize(width,height)
        self.configure(fg_color='#111318');self.transient(app)
        self.grid_columnconfigure(0,weight=1);self.grid_rowconfigure(0,weight=1)
        self.form=CalendarForm(self);self.form.grid(row=0,column=0,sticky='nsew',padx=8,pady=8)
        footer=ctk.CTkFrame(self,fg_color='transparent',height=1);footer.grid(row=1,column=0,sticky='ew',padx=12,pady=8)
        footer.grid_columnconfigure(0,weight=1)
        self.note=ctk.CTkLabel(footer,text='Đáo hạn chỉ nhắc trước; Ngài tự quyết định giao dịch.',font=('Segoe UI',11),anchor='w')
        self.note.grid(row=0,column=0,sticky='ew')
        ctk.CTkButton(footer,text='LƯU LỊCH',width=110,height=32,command=self.save).grid(row=0,column=1,padx=(8,0))
        self.bind('<Escape>',lambda _:self.destroy())

    def save(self):
        try:
            calendar.write_settings(self.form.values())
            self.note.configure(text='Đã lưu lịch dùng chung cho hai app.',text_color=COL_GREEN)
        except Exception as exc:self.note.configure(text=str(exc),text_color=COL_RED)
