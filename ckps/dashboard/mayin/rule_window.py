"""MayinTien's RULE presentation with a CKPS settings adapter."""
from dataclasses import asdict, replace
from types import SimpleNamespace
import tkinter as tk
import customtkinter as ctk

from ckps.models import ExitSettings, Quote, load_record
from .forms import OriginalRuleForms
from .widgets import StableTabview, _StableToplevel, size_popup


class RuleWindow(OriginalRuleForms, _StableToplevel):
    def __init__(self, app, page='E/M'):
        super().__init__(app)
        self.app, self.top = app, self
        self.title('RAT VN30 · RULE')
        size_popup(self)
        self.configure(fg_color='#111318')
        self.transient(app)
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(0,weight=1)
        exits = load_record(ExitSettings, app.settings.exit)
        values = {}
        mapping = {'initial_sl_pct':'sl_distance','reentry_sl_pct':'repeat_gap','take_profit_pct':'tp_distance',
            'normal_arm_pct':'arm_gain','normal_giveback_pct':'trail_gap','normal_sell_pct':'arm_close_pct',
            'normal_sell_basis':'arm_basis','normal_repeat_enabled':'arm_repeat','normal_policy':'arm_policy',
            'normal_dynamic_enabled':'dynamic_enabled','dynamic_policy':'dynamic_policy','dynamic_sell_pct':'dynamic_close_pct',
            'dynamic_sell_basis':'dynamic_basis','dynamic_repeat_enabled':'dynamic_repeat',
            'normal_atr_activation_multiplier':'atr_start_multiplier','normal_atr_activation_enabled':'atr_start_enabled',
            'normal_atr_multiplier':'atr_trail_multiplier','normal_atr_trail_enabled':'atr_trail_enabled',
            'normal_retention_pct':'retention_pct','normal_retention_enabled':'retention_enabled',
            'normal_retention_until_pct':'retention_until','normal_retention_until_enabled':'retention_until_enabled'}
        values.update({name:getattr(exits,key) for name,key in mapping.items()})
        self.params = SimpleNamespace(**values)
        self.tabs = StableTabview(self,fg_color=self.BG,border_width=1,border_color=self.BORDER,
            segmented_button_selected_color=self.BLUE,segmented_button_selected_hover_color='#245C92',
            segmented_button_unselected_color='#3A3F47',segmented_button_unselected_hover_color='#4B515B')
        self.tabs.grid(row=0,column=0,sticky='nsew',padx=10,pady=(8,3))
        self._tab_font(self.tabs,12)
        em = self.tabs.add('E/M')
        self._exit_manager_tab(em,include_signals=False)
        self.arm_repeat_below_arm=tk.BooleanVar(value=exits.arm_repeat_below_arm)
        below_row=ctk.CTkFrame(self.protect_trail_card,fg_color='transparent')
        below_row.pack(fill='x',padx=8,pady=2)
        self.below_arm_switch=ctk.CTkSwitch(below_row,text='LẶP DƯỚI ARM',
            variable=self.arm_repeat_below_arm,font=('Segoe UI',11),progress_color=self.GREEN)
        self.below_arm_switch.pack(side='left')
        self._hint_icon(below_row, 'OFF: chỉ lặp khi mức lãi còn đạt ARM. ON: cho lặp dưới ARM nhưng vẫn phải còn lãi trước phí.').pack(side='right')
        self._execution_controls(self.exit_body,exits)
        self._update_units()
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

    def _execution_controls(self,body,exits):
        bar=ctk.CTkFrame(body,fg_color='transparent')
        bar.grid(row=0,column=0,columnspan=2,sticky='ew',padx=8,pady=3)
        row=ctk.CTkFrame(bar,fg_color='transparent')
        row.pack(fill='x')
        for key,label in (('sl_enabled','SL'),('tp_enabled','TP'),('arm_enabled','TSL / ARM')):
            variable=tk.BooleanVar(value=getattr(exits,key))
            setattr(self,key,variable)
            ctk.CTkSwitch(row,text=label,variable=variable,width=105,font=('Segoe UI',12),progress_color=self.GREEN).pack(side='left',padx=(0,12))
        self.price_units=tk.StringVar(value='ĐIỂM' if exits.distance_unit=='POINTS' else '% GIÁ')
        self._current_unit=self.price_units.get()
        ctk.CTkSegmentedButton(row,values=['ĐIỂM','% GIÁ'],variable=self.price_units,selected_color=self.BLUE,
            font=('Segoe UI',12,'bold'),command=self._units_changed).pack(side='right')
        ctk.CTkLabel(row,text='ĐƠN VỊ',font=('Segoe UI',11,'bold'),text_color=self.TITLE).pack(side='right',padx=5)
        self._hint_icon(row, 'ĐIỂM: khoảng điểm VN30. % GIÁ: phần trăm so với giá vốn. Khi đổi, app quy đổi theo giá hợp đồng đang xem; kiểm tra lại trước khi lưu.').pack(side='right',padx=3)
        ctk.CTkLabel(bar,text='ĐIỂM: khoảng điểm VN30  ·  % GIÁ: tỷ lệ trên giá vốn',
            font=('Segoe UI',11),text_color=self.MUTED,anchor='w').pack(fill='x',pady=(2,0))

    def _units_changed(self, selected):
        previous=self._current_unit
        if selected==previous:return
        entries=(self.initial_sl,self.reentry_sl,self.take_profit,self.normal_arm,self.normal_giveback,self.normal_retention_until_pct)
        try:
            values=[float(entry.get()) for entry in entries]
            quote=self.app.view.get('quotes',{}).get(self.app.view.get('contract','VN30F1M'),{})
            fresh=bool(quote and load_record(Quote,quote).fresh(self.app.settings.max_quote_age))
            if any(values) and not fresh:
                raise ValueError('Cần giá hợp đồng mới để đổi đơn vị; các ngưỡng chưa thay đổi.')
            price=float(quote.get('last',0)) if fresh else 1.0
            factor=100/price if selected=='% GIÁ' else price/100
            converted=[f'{value*factor:.8g}' for value in values]
            for entry,value in zip(entries,converted):
                entry.delete(0,'end');entry.insert(0,value)
            self._current_unit=selected
            self._update_units()
            message=(f'Đã quy đổi theo giá {price:,.1f}; kiểm tra trước khi lưu.' if fresh
                     else 'Đã đổi đơn vị; các ngưỡng đều bằng 0.')
            self.status.configure(text=message,text_color=self.WARN)
        except (ValueError,TypeError,OverflowError) as exc:
            self.price_units.set(previous)
            self.status.configure(text=str(exc),text_color='#EF4444')

    def _update_units(self):
        suffix='điểm' if self.price_units.get()=='ĐIỂM' else '%'
        for entry,title in ((self.initial_sl,'SL'),(self.reentry_sl,'LẶP'),(self.take_profit,'TP'),
                (self.normal_arm,'ARM'),(self.normal_giveback,'Lùi'),(self.normal_retention_until_pct,'Tới MFE')):
            label=next((w for w in entry.master.winfo_children() if isinstance(w,ctk.CTkLabel) and w.cget('text')),None)
            if label:
                label.configure(text=f'{title} ({suffix})')

    def _exits(self):
        if self.price_units.get()!=self._current_unit:
            raise ValueError('Cần quy đổi các ngưỡng trước khi đổi đơn vị.')
        values=asdict(load_record(ExitSettings,self.app.settings.exit))
        mapping={'sl_distance':'initial_sl','tp_distance':'take_profit','repeat_gap':'reentry_sl','arm_gain':'normal_arm',
            'trail_gap':'normal_giveback','arm_close_pct':'normal_sell','arm_policy':'normal_policy','arm_repeat':'normal_repeat',
            'dynamic_enabled':'normal_dynamic','dynamic_policy':'dynamic_policy','dynamic_close_pct':'dynamic_sell','dynamic_repeat':'dynamic_repeat',
            'atr_start_enabled':'normal_atr_activation_enabled','atr_start_multiplier':'normal_atr_activation_multiplier',
            'atr_trail_enabled':'normal_atr_trail_enabled','atr_trail_multiplier':'normal_atr_multiplier',
            'retention_enabled':'normal_retention_enabled','retention_pct':'normal_retention_pct',
            'retention_until_enabled':'normal_retention_until_enabled','retention_until':'normal_retention_until_pct',
            'sl_enabled':'sl_enabled','tp_enabled':'tp_enabled','arm_enabled':'arm_enabled',
            'arm_repeat_below_arm':'arm_repeat_below_arm'}
        for key,name in mapping.items():
            raw=getattr(self,name).get()
            old=values[key]
            values[key]=bool(raw) if isinstance(old,bool) else str(raw) if isinstance(old,str) else abs(float(raw))
        values['distance_unit']='POINTS' if self.price_units.get()=='ĐIỂM' else 'PERCENT'
        values['arm_basis']='ORIGINAL' if self.normal_sell_basis.get()=='GỐC' else 'REMAINING'
        values['dynamic_basis']='ORIGINAL' if self.dynamic_sell_basis.get()=='GỐC' else 'REMAINING'
        return asdict(load_record(ExitSettings,values).validate())

    def save(self):
        try:
            settings=replace(self.app.settings,exit=self._exits()).validate()
            self.app.save_config(settings)
            self.status.configure(text='Đã áp dụng RULE vào mẫu trong phiên.' if getattr(self.app,'preview_only',False) else 'Đã lưu RULE CKPS.',text_color=self.GREEN)
        except Exception as exc:
            self.status.configure(text=str(exc),text_color='#EF4444')
