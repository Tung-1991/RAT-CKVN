"""Shared compact calendar controls for MAIN connection and signal backend."""
import tkinter as tk
import customtkinter as ctk

from ckps.rules.calendar import CalendarSettings
from ckps.services import calendar
from .connection_window import ConnectionFields
from .widgets import _StableToplevel
from .tokens import *


class CalendarForm(ctk.CTkFrame):
    def __init__(self,parent,*,settings=None):
        super().__init__(parent,fg_color='transparent',height=1,width=1)
        self.settings=settings or calendar.read_settings()
        self.variables={}
        self.grid_columnconfigure((0,1),weight=1,uniform='calendar')
        form=ConnectionFields(self.variables)
        flags=form.card(self,'CHẶN MỞ MỚI')
        for key,label in (('use_dnse_working_dates','Lịch ngày nghỉ DNSE'),
                ('avoid_vn30_rebalance_entry','Né ngày đổi rổ VN30')):
            form.field(flags,key,label,getattr(self.settings,key))
        row=ctk.CTkFrame(flags,fg_color='transparent',height=1)
        row.pack(fill='x',padx=8,pady=4)
        for key,label in (('block_entry_ato','Né ATO'),('block_entry_atc','Né ATC')):
            variable=tk.BooleanVar(value=getattr(self.settings,key));self.variables[key]=variable
            ctk.CTkCheckBox(row,text=label,variable=variable,width=105,font=('Segoe UI',12),
                checkbox_width=18,checkbox_height=18).pack(side='left',padx=(0,8))
        custom=form.card(self,'NGÀY BỔ SUNG',1)
        for key,label in (('manual_closed_dates','Ngày nghỉ bổ sung'),('vn30_rebalance_dates','Ngày đổi rổ VN30')):
            ctk.CTkLabel(custom,text=label,font=('Segoe UI',12),text_color=COL_MUTED,anchor='w',height=20).pack(fill='x',padx=8,pady=(3,0))
            variable=tk.StringVar(value=', '.join(getattr(self.settings,key)));self.variables[key]=variable
            ctk.CTkEntry(custom,textvariable=variable,height=29,font=('Segoe UI',12),
                placeholder_text='YYYY-MM-DD, YYYY-MM-DD').pack(fill='x',padx=8,pady=(1,4))
        notices=ctk.CTkFrame(self,fg_color=COL_SURFACE_2,corner_radius=5,height=1)
        notices.grid(row=1,column=0,columnspan=2,sticky='ew',padx=4,pady=(4,3))
        self.variables['notify_enabled']=tk.BooleanVar(value=self.settings.notify_enabled)
        self.variables['expiry_notice_enabled']=tk.BooleanVar(value=self.settings.expiry_notice_enabled)
        ctk.CTkSwitch(notices,text='Nhắc trước đáo hạn',variable=self.variables['expiry_notice_enabled'],font=('Segoe UI',12),
            progress_color=COL_GREEN).pack(side='left',padx=(10,8),pady=6)
        for key,value,width in (('notice_days',self.settings.notice_days,45),('notice_time',self.settings.notice_time,70)):
            variable=tk.StringVar(value=str(value));self.variables[key]=variable
            if key=='notice_time':ctk.CTkLabel(notices,text='ngày · lúc',font=('Segoe UI',12)).pack(side='left',padx=6)
            ctk.CTkEntry(notices,textvariable=variable,width=width,height=28,justify='center',font=('Segoe UI',12)).pack(side='left')
        info=calendar.summary()
        text=('Đáo hạn: ' if info['expiry_confirmed'] else 'Đáo hạn dự kiến: ')+info['next_expiry']+' · Chỉ nhắc, không chặn giao dịch'
        ctk.CTkLabel(self,text=text,font=('Segoe UI',11),text_color=COL_MUTED,anchor='w',height=22).grid(row=2,column=0,columnspan=2,sticky='ew',padx=8)

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
