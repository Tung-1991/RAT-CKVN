"""Blackbox edits signal rules only; it never connects, runs a bot or trades."""
import customtkinter as ctk

from ckps.config import runtime_root
from ckps.services.signal_config import read_signal_settings, write_signal_settings
from ckps.storage import AccountLease
from .mayin.signal_form import SignalForm
from .mayin.tokens import COL_TEXT, COL_GREEN, COL_RED, COL_MUTED


class SignalApp(ctk.CTk):
    def __init__(self, *, settings=None):
        super().__init__()
        self.lease=AccountLease(runtime_root()/'blackbox'/'session.lock')
        self.title('RAT VN30 · BLACKBOX')
        width=min(780,self.winfo_screenwidth()-50)
        height=min(600,self.winfo_screenheight()-80)
        self.geometry(f'{width}x{height}')
        self.minsize(min(650,width),min(480,height))
        self.configure(fg_color='#111318')
        self.settings=settings or read_signal_settings()
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(1,weight=1)
        header=ctk.CTkFrame(self,fg_color='transparent')
        header.grid(row=0,column=0,sticky='ew',padx=16,pady=(10,4))
        ctk.CTkLabel(header,text='BLACKBOX',font=('Segoe UI',19,'bold'),text_color=COL_TEXT).pack(side='left')
        ctk.CTkLabel(header,text='RULE TÍN HIỆU',font=('Segoe UI',12),text_color=COL_MUTED).pack(side='right')
        self.signal_form=SignalForm(self,self.settings)
        self.signal_form.grid(row=1,column=0,sticky='nsew',padx=8)
        self.footer=ctk.CTkFrame(self,fg_color='transparent')
        self.footer.grid(row=2,column=0,sticky='ew',padx=16,pady=(5,10))
        self.footer.grid_columnconfigure(0,weight=1)
        self.note=ctk.CTkLabel(self.footer,text='',width=1,font=('Segoe UI',12),anchor='w',justify='left')
        self.note.grid(row=0,column=0,sticky='ew',padx=(0,10))
        self.note.bind('<Configure>',lambda _:self.note.configure(wraplength=max(120,int(self.note.winfo_width()/self.note._get_widget_scaling())-4)))
        self.primary=ctk.CTkButton(self.footer,text='LƯU TÍN HIỆU',width=145,height=34,command=self.save_settings)
        self.primary.grid(row=0,column=1)
        self.protocol('WM_DELETE_WINDOW',self.close)

    def save_settings(self):
        try:
            # Preserve notification gates saved in the main app while changing
            # indicator rules; no API, token, calendar or E/M settings enter here.
            draft=self.signal_form.read(read_signal_settings())
            write_signal_settings(draft)
            self.settings=draft
            self.note.configure(text='Đã lưu RULE tín hiệu.',text_color=COL_GREEN)
        except Exception as exc:
            self.note.configure(text=str(exc),text_color=COL_RED)

    def close(self):
        self.lease.close()
        self.destroy()
