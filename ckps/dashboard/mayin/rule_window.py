"""MayinTien's RULE presentation with a CKPS settings adapter."""
from dataclasses import replace
import customtkinter as ctk

from .protection_form import ProtectionFormMixin
from .widgets import StableTabview, _StableToplevel, size_popup


class RuleWindow(ProtectionFormMixin, _StableToplevel):
    def __init__(self, app, page='E/M'):
        super().__init__(app)
        self.app, self.top = app, self
        self.title('RAT VN30 · RULE')
        size_popup(self)
        self.configure(fg_color='#111318')
        self.transient(app)
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(0,weight=1)
        self.tabs = StableTabview(self,fg_color=self.BG,border_width=1,border_color=self.BORDER,
            segmented_button_selected_color=self.BLUE,segmented_button_selected_hover_color='#245C92',
            segmented_button_unselected_color='#3A3F47',segmented_button_unselected_hover_color='#4B515B')
        self.tabs.grid(row=0,column=0,sticky='nsew',padx=10,pady=(8,3))
        self._tab_font(self.tabs,12)
        em = self.tabs.add('E/M')
        self._init_protection(em,app.settings.exit)
        self.footer = ctk.CTkFrame(self,fg_color='transparent')
        self.footer.grid(row=1,column=0,sticky='ew',padx=12,pady=(3,8))
        self.status = ctk.CTkLabel(self.footer,text='AUTO: tự đóng · ALERT: chỉ LOG trong app',font=('Segoe UI',11),text_color=self.TEXT,
            anchor='w',justify='left',wraplength=350)
        self.status.pack(side='left')
        ctk.CTkButton(self.footer,text='LƯU THAY ĐỔI',width=145,height=34,font=('Segoe UI',12,'bold'),
            fg_color=self.GREEN,hover_color='#16A34A',command=self.save).pack(side='right')
        self.select(page)
        self.bind('<Escape>',lambda _:self.destroy())
        self.after(100,self.lift)

    def select(self,page):
        self.tabs.set('E/M')
        self.lift()

    def save(self):
        try:
            settings=replace(self.app.settings,exit=self._exits()).validate()
            self.app.save_config(settings)
            self.status.configure(text='Đã áp dụng RULE vào mẫu trong phiên.' if getattr(self.app,'preview_only',False) else 'Đã lưu RULE CKPS.',text_color=self.GREEN)
        except Exception as exc:
            self.status.configure(text=str(exc),text_color='#EF4444')
