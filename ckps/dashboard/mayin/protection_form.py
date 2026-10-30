"""Native MayinTien controls for the one shared protection rule."""
from dataclasses import asdict
from types import SimpleNamespace
import tkinter as tk
import customtkinter as ctk

from ckps.models import ExitSettings, Quote, load_record
from ckps.rules.distances import price_percent_rules, reference_margin
from ckps.rules.defaults import shared_exit_settings
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
        mapping = {'initial_sl_pct':'sl_distance','reentry_sl_pct':'repeat_gap',
            'normal_arm_pct':'arm_gain','normal_giveback_pct':'trail_gap','normal_repeat_enabled':'arm_repeat',
            'normal_dynamic_enabled':'dynamic_enabled','dynamic_repeat_enabled':'dynamic_repeat'}
        values.update({name:getattr(exits,key) for name,key in mapping.items()})
        self.params = SimpleNamespace(**values)
        self._exit_manager_tab(parent,include_signals=False)
        self._execution_controls(self.exit_body,exits)
        self._update_units()
        self.render_atr()
        if self._migration_error:
            for entry in (self.initial_sl,self.reentry_sl,self.normal_arm,self.normal_giveback):
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
        for key,label in (('sl_enabled','SL'),('arm_enabled','TSL / ARM')):
            variable=tk.BooleanVar(value=getattr(exits,key))
            setattr(self,key,variable)
            ctk.CTkSwitch(row,text=label,variable=variable,width=105,font=('Segoe UI',12),progress_color=self.GREEN).pack(side='left',padx=(0,12))
        ctk.CTkLabel(row,text='TP · OFF',font=('Segoe UI',12),text_color=self.TEXT).pack(side='left',padx=8)
        self._hint_icon(row,'Một RULE chung áp dụng cho toàn bộ hợp đồng đang giữ, lệnh chờ và lệnh mới. TP OFF. Chỉ chỉnh SL/ARM/Lùi/LẶP theo % giá vốn bình quân. Giá vốn 2.000, SL 0,25% là khoảng giá 5: mua cắt tại 1.995, bán cắt tại 2.005. DYNAMIC dùng sẵn bắt đầu 0,5 ATR, lùi 0,8 ATR, giữ 70% lãi đỉnh và đóng 50% HĐ còn lại mỗi lượt. LƯU áp dụng cùng bộ thông số cho tất cả; nhận/bỏ quản lý chỉ thay quyền BOT, không tạo RULE riêng.').pack(side='right',padx=3)
        ctk.CTkLabel(row,text='% GIÁ VỐN',font=('Segoe UI',12,'bold'),text_color=self.TITLE).pack(side='right',padx=5)

    def _update_units(self):
        suffix='% GIÁ'
        for entry,title in ((self.initial_sl,'SL'),(self.reentry_sl,'LẶP'),
                (self.normal_arm,'ARM'),(self.normal_giveback,'Lùi')):
            label=next((w for w in entry.master.winfo_children() if isinstance(w,ctk.CTkLabel) and w.cget('text')),None)
            if label:
                label.configure(text=f'{title} ({suffix})')

    def _exits(self):
        if self._migration_error:raise ValueError(self._migration_error)
        values=asdict(self.values)
        mapping={'sl_distance':'initial_sl','repeat_gap':'reentry_sl','arm_gain':'normal_arm',
            'trail_gap':'normal_giveback','arm_repeat':'normal_repeat',
            'dynamic_enabled':'normal_dynamic','dynamic_repeat':'dynamic_repeat',
            'sl_enabled':'sl_enabled','arm_enabled':'arm_enabled'}
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
