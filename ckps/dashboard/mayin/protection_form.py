"""Native MayinTien controls for the one shared protection rule."""
from dataclasses import asdict
from types import SimpleNamespace
import tkinter as tk
import customtkinter as ctk

from ckps.models import ExitSettings, Quote, load_record
from ckps.rules.distances import price_percent_rules, reference_margin
from ckps.rules.defaults import shared_exit_settings
from .forms import OriginalRuleForms
from .widgets import choice_bar


class ProtectionFormMixin(OriginalRuleForms):
    @staticmethod
    def set_protection_enabled(parent, enabled):
        for widget in parent.winfo_children():
            if isinstance(widget, (ctk.CTkEntry, ctk.CTkSwitch, ctk.CTkOptionMenu, ctk.CTkSegmentedButton)):
                widget.configure(state='normal' if enabled else 'disabled')
            else:
                ProtectionFormMixin.set_protection_enabled(widget, enabled)

    def _init_protection(self, parent, values):
        values=shared_exit_settings(values)
        self._migration_error=''
        self._converted_legacy=values.get('distance_unit','POINTS')!='PRICE_PERCENT'
        try:
            entry,margin=self._price_reference()
            values=price_percent_rules(values,entry,margin)
        except ValueError as exc:
            self._migration_error=str(exc)
            values={**values,'distance_unit':'PRICE_PERCENT'}
        exits = load_record(ExitSettings, values)
        self.values = exits
        values = {}
        mapping = {'initial_sl_pct':'sl_distance','take_profit_pct':'tp_distance','reentry_sl_pct':'repeat_gap',
            'normal_arm_pct':'arm_gain','normal_giveback_pct':'trail_gap','normal_repeat_enabled':'arm_repeat',
            'normal_dynamic_enabled':'dynamic_enabled','dynamic_repeat_enabled':'dynamic_repeat'}
        values.update({name:getattr(exits,key) for name,key in mapping.items()})
        self.params = SimpleNamespace(**values)
        self._exit_manager_tab(parent,include_signals=False)
        self._execution_controls(self.exit_body,exits)
        self._update_units()
        self.render_atr()
        if self._migration_error:
            for entry in (self.initial_sl,self.take_profit,self.reentry_sl,self.normal_arm,self.normal_giveback):
                entry.delete(0,'end')
                entry.configure(placeholder_text='CHỜ')
            self.set_protection_enabled(parent,False)

    def _price_reference(self):
        symbol=self.app.view.get('contract','VN30F1M')
        quote=self.app.view.get('quotes',{}).get(symbol,{})
        if not quote or quote.get('symbol')!=symbol or not load_record(Quote,quote).fresh(self.app.settings.max_quote_age):return None,None
        account=self.app.view.get('account',{})
        entry=quote.get('last')
        return entry,reference_margin(account.get('margin_per_contract'),account.get('margin_reference_price') or entry,entry)

    def _execution_controls(self,body,exits):
        bar=ctk.CTkFrame(body,fg_color='#1C2B3B',border_width=1,border_color='#344D66',corner_radius=7)
        bar.grid(row=0,column=0,columnspan=2,sticky='ew',padx=4,pady=(2,5))
        ctk.CTkLabel(bar,text='RULE CHUNG',font=('Segoe UI',14,'bold'),text_color='#B9D9FA').pack(side='left',padx=12,pady=7)
        ctk.CTkLabel(bar,text='% GIÁ VỐN',font=('Segoe UI',14,'bold'),text_color=self.TEXT).pack(side='right',padx=12)
        for index,key,label,color in ((0,'sl_enabled','BẬT SL','#EF6B73'),(1,'tp_enabled','BẬT TP','#36C997')):
            cell=self.exit_limit_cells[index]
            variable=tk.BooleanVar(value=getattr(exits,key));setattr(self,key,variable)
            switch=ctk.CTkSwitch(cell,text=label,variable=variable,font=('Segoe UI',13,'bold'),progress_color=color,
                button_color='#E0E8F1',fg_color='#3A4553')
            switch.pack(fill='x',padx=8,pady=(4,5),before=cell.winfo_children()[0])
        spacer=ctk.CTkLabel(self.exit_limit_cells[2],text='BƯỚC ĐÓNG TIẾP',font=('Segoe UI',13,'bold'),text_color='#B5C4D5')
        spacer.pack(fill='x',padx=8,pady=(4,5),before=self.exit_limit_cells[2].winfo_children()[0])
        self.arm_enabled=tk.BooleanVar(value=exits.arm_enabled)
        header=self.protect_trail_card._viking_header
        ctk.CTkSwitch(header,text='',width=36,variable=self.arm_enabled,progress_color='#4A9FE8',button_color='#E0E8F1').pack(side='left',before=header.winfo_children()[0],padx=(0,5))
        self._ema_controls(body,exits)

    def _ema_controls(self,body,exits):
        card=self._card(body,'E · THOÁT THEO EMA',
            'Long đóng toàn bộ khi EMA nhanh < EMA chậm; Short khi EMA nhanh > EMA chậm. Khung nến 1D; REALTIME dùng giá đang chạy, CLOSED dùng nến đã đóng. Nhịp phút dùng mẫu cuối nhịp hoàn thành. E độc lập tín hiệu/RSI/Telegram, chỉ thực thi khi E + BOT + quyền vị thế ON.',3,0,span=2,compact=True)
        card.configure(fg_color='#202938',border_color='#415876')
        self.ema_exit_enabled=tk.BooleanVar(value=exits.ema_exit_enabled)
        header=card._viking_header
        ctk.CTkSwitch(header,text='',width=36,variable=self.ema_exit_enabled,progress_color='#9B8AFB',button_color='#E0E8F1').pack(side='left',before=header.winfo_children()[0],padx=(0,5))
        content=ctk.CTkFrame(card,fg_color='transparent');content.pack(fill='x',padx=6,pady=3)
        content.grid_columnconfigure((0,1),weight=1,uniform='ema-controls')
        numbers=ctk.CTkFrame(content,fg_color='transparent');numbers.grid(row=0,column=0,sticky='nsew',padx=(0,8));numbers._viking_compact=True
        self.ema_exit_fast=self._field(numbers,'EMA nhanh',exits.ema_exit_fast,'Số phiên của EMA nhanh; phải nhỏ hơn EMA chậm.')
        self.ema_exit_slow=self._field(numbers,'EMA chậm',exits.ema_exit_slow,'Số phiên của EMA chậm. Thiếu ít nhất EMA chậm + 1 mẫu hợp lệ thì CHỜ.')
        clock=ctk.CTkFrame(content,fg_color='transparent');clock.grid(row=0,column=1,sticky='nsew',padx=4)
        ctk.CTkLabel(clock,text='NẾN 1D · QUAN SÁT',font=('Segoe UI',13,'bold'),anchor='w',text_color='#C5D5E9').pack(fill='x')
        self.ema_exit_mode=tk.StringVar(value=exits.ema_exit_mode)
        self.ema_mode_control=choice_bar(clock,values=['REALTIME','CLOSED'],variable=self.ema_exit_mode,height=32,font=('Segoe UI',13,'bold'),selected_color='#6250A8')
        self.ema_mode_control.pack(fill='x',pady=(1,4))
        self.ema_exit_interval=tk.StringVar(value=exits.ema_exit_interval)
        self.ema_interval_control=choice_bar(clock,values=['TICK','1M','2M','5M'],variable=self.ema_exit_interval,height=32,font=('Segoe UI',13,'bold'),selected_color='#6250A8')
        self.ema_interval_control.pack(fill='x')
        self.ema_exit_value=ctk.CTkLabel(card,text='',font=('Segoe UI',14),anchor='w',justify='left')
        self.ema_exit_value.pack(fill='x',padx=12,pady=(4,8))
        self.ema_exit_value.bind('<Configure>',lambda _:self.ema_exit_value.configure(wraplength=max(120,int(self.ema_exit_value.winfo_width()/self.ema_exit_value._get_widget_scaling())-4)),add='+')

    def _update_units(self):
        suffix='% GIÁ'
        for entry,title in ((self.initial_sl,'SL'),(self.take_profit,'TP'),(self.reentry_sl,'LẶP'),
                (self.normal_arm,'ARM'),(self.normal_giveback,'Lùi')):
            label=next((w for w in entry.master.winfo_children() if isinstance(w,ctk.CTkLabel) and w.cget('text')),None)
            if label:
                label.configure(text=f'{title} ({suffix})')

    def _exits(self):
        if self._migration_error:raise ValueError(self._migration_error)
        values=asdict(self.values)
        mapping={'sl_distance':'initial_sl','tp_distance':'take_profit','repeat_gap':'reentry_sl','arm_gain':'normal_arm',
            'trail_gap':'normal_giveback','arm_repeat':'normal_repeat',
            'dynamic_enabled':'normal_dynamic','dynamic_repeat':'dynamic_repeat',
            'sl_enabled':'sl_enabled','tp_enabled':'tp_enabled','arm_enabled':'arm_enabled','ema_exit_enabled':'ema_exit_enabled',
            'ema_exit_fast':'ema_exit_fast','ema_exit_slow':'ema_exit_slow','ema_exit_mode':'ema_exit_mode','ema_exit_interval':'ema_exit_interval'}
        for key,name in mapping.items():
            raw=getattr(self,name).get()
            old=values[key]
            values[key]=bool(raw) if isinstance(old,bool) else str(raw) if isinstance(old,str) else float(str(raw).strip().removesuffix('%').replace(',','.'))
        values['sl_distance']=abs(values['sl_distance'])
        values['distance_unit']='PRICE_PERCENT'
        return asdict(load_record(ExitSettings,shared_exit_settings(values)).validate())

    def render_atr(self):
        from .atr_preview import atr_preview
        value,detail,ready=atr_preview(self.app.view)
        self.dynamic_atr_value.configure(text=value,text_color='#60A5FA' if ready else '#FBBF24')
        self.dynamic_atr_detail.configure(text=detail)
        view=self.app.view.get('ema_exit',{})
        enabled=self.app.settings.exit.get('ema_exit_enabled',False)
        text='E · OFF'
        if enabled:
            text=(f"E · EMA{view.get('fast_period',3)} {view['fast']:,.2f} / EMA{view.get('slow_period',6)} {view['slow']:,.2f} · 1D {view['mode']} / {view['interval']}"
                  if view.get('ready') else 'E · CHỜ GIÁ / NẾN 1D')
        self.ema_exit_value.configure(text=text)
