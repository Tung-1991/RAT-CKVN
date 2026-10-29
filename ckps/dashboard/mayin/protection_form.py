"""Native MayinTien controls for the one shared protection rule."""
from dataclasses import asdict
from types import SimpleNamespace
import tkinter as tk
import customtkinter as ctk

from ckps.models import ExitSettings, Quote, load_record
from ckps.rules.distances import price_percent_rules, reference_margin
from .forms import OriginalRuleForms


class ProtectionFormMixin(OriginalRuleForms):
    @staticmethod
    def set_protection_enabled(parent, enabled):
        for widget in parent.winfo_children():
            if isinstance(widget, (ctk.CTkEntry, ctk.CTkSwitch, ctk.CTkOptionMenu, ctk.CTkSegmentedButton)):
                widget.configure(state='normal' if enabled else 'disabled')
            else:
                ProtectionFormMixin.set_protection_enabled(widget, enabled)

    def _init_protection(self, parent, values):
        values={**values,'tp_enabled':False,'tp_distance':0.0}
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
        self._exit_manager_tab(parent,include_signals=False)
        self.arm_repeat_below_arm=tk.BooleanVar(value=exits.arm_repeat_below_arm)
        below_row=ctk.CTkFrame(self.protect_trail_card,fg_color='transparent')
        below_row.pack(fill='x',padx=8,pady=2)
        self.below_arm_switch=ctk.CTkSwitch(below_row,text='LẶP DƯỚI ARM',
            variable=self.arm_repeat_below_arm,font=('Segoe UI',11),progress_color=self.GREEN)
        self.below_arm_switch.pack(side='left')
        self._hint_icon(below_row, 'OFF: chỉ lặp khi mức lãi còn đạt ARM. ON: cho lặp dưới ARM nhưng vẫn phải còn lãi trước phí.').pack(side='right')
        self._execution_controls(self.exit_body,exits)
        self._update_units()
        if self._migration_error:
            for entry in (self.initial_sl,self.reentry_sl,self.take_profit,self.normal_arm,self.normal_giveback,self.normal_retention_until_pct):
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
        bar=ctk.CTkFrame(body,fg_color='transparent')
        bar.grid(row=0,column=0,columnspan=2,sticky='ew',padx=8,pady=3)
        row=ctk.CTkFrame(bar,fg_color='transparent')
        row.pack(fill='x')
        self.tp_enabled=tk.BooleanVar(value=False)
        self.take_profit.configure(state='disabled')
        for key,label in (('sl_enabled','SL'),('arm_enabled','TSL / ARM')):
            variable=tk.BooleanVar(value=getattr(exits,key))
            setattr(self,key,variable)
            ctk.CTkSwitch(row,text=label,variable=variable,width=105,font=('Segoe UI',12),progress_color=self.GREEN).pack(side='left',padx=(0,12))
        ctk.CTkLabel(row,text='TP · OFF',font=('Segoe UI',12),text_color=self.TEXT).pack(side='left',padx=8)
        self._hint_icon(row,'Một RULE chung áp dụng cho toàn bộ hợp đồng đang giữ, lệnh chờ và lệnh mới. TP OFF. SL/ARM/Lùi/LẶP tính trên giá vốn bình quân của từng hợp đồng. Giá vốn 2.000, SL 0,25% là khoảng giá 5: mua cắt tại 1.995, bán cắt tại 2.005. TSL bám đỉnh/đáy với khoảng lùi theo % giá vốn. Giữ lãi (%) tính trên lãi đỉnh; Đóng (%) tính trên HĐ, ATR là hệ số riêng. LƯU áp dụng cùng bộ thông số cho tất cả; nhận/bỏ quản lý chỉ thay quyền BOT, không tạo RULE riêng.').pack(side='right',padx=3)
        ctk.CTkLabel(row,text='% GIÁ VỐN',font=('Segoe UI',12,'bold'),text_color=self.TITLE).pack(side='right',padx=5)

    def _update_units(self):
        suffix='% GIÁ'
        for entry,title in ((self.initial_sl,'SL'),(self.reentry_sl,'LẶP'),(self.take_profit,'TP'),
                (self.normal_arm,'ARM'),(self.normal_giveback,'Lùi'),(self.normal_retention_until_pct,'Tới MFE')):
            label=next((w for w in entry.master.winfo_children() if isinstance(w,ctk.CTkLabel) and w.cget('text')),None)
            if label:
                label.configure(text=f'{title} ({suffix})')

    def _exits(self):
        if self._migration_error:raise ValueError(self._migration_error)
        values=asdict(self.values)
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
            values[key]=bool(raw) if isinstance(old,bool) else str(raw) if isinstance(old,str) else float(str(raw).strip().removesuffix('%').replace(',','.'))
        values['sl_distance']=abs(values['sl_distance'])
        values['tp_enabled']=False
        values['tp_distance']=0.0
        values['distance_unit']='PRICE_PERCENT'
        values['arm_basis']='ORIGINAL' if self.normal_sell_basis.get()=='GỐC' else 'REMAINING'
        values['dynamic_basis']='ORIGINAL' if self.dynamic_sell_basis.get()=='GỐC' else 'REMAINING'
        return asdict(load_record(ExitSettings,values).validate())
