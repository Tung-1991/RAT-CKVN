"""Native MayinTien controls for the one shared protection rule."""
from dataclasses import asdict
from types import SimpleNamespace
from math import isfinite
import tkinter as tk
import customtkinter as ctk

from ckps.models import ExitSettings, load_record, quantity
from ckps.rules.distances import price_rule_draft
from ckps.rules.defaults import shared_exit_settings
from .forms import OriginalRuleForms
from .hover_hint import _HoverHint
from .widgets import configure_changed
from .pnl_preview import ProtectionReference, protection_reference, pnl_preview, dynamic_pnl_preview


class ProtectionFormMixin(OriginalRuleForms):
    _distance_fields={'sl_distance':'initial_sl','tp_distance':'take_profit','repeat_gap':'reentry_sl',
        'arm_gain':'normal_arm','trail_gap':'normal_giveback','retention_until':'retention_until'}
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
        self._converted_legacy=values.get('distance_unit','POINTS')!='PRICE_PERCENT' or values.get('trailing_unit',values.get('distance_unit','POINTS'))!='PRICE_PERCENT'
        entry,margin=self._price_reference()
        values,self._pending_fields=price_rule_draft(values,entry,margin)
        exits = load_record(ExitSettings, values)
        self.values = exits
        values = {}
        mapping = {'initial_sl_pct':'sl_distance','take_profit_pct':'tp_distance','reentry_sl_pct':'repeat_gap',
            'normal_arm_pct':'arm_gain','normal_giveback_pct':'trail_gap','normal_repeat_enabled':'arm_repeat',
            'normal_dynamic_enabled':'dynamic_enabled','dynamic_repeat_enabled':'dynamic_repeat'}
        for key in ('arm_repeat_below_arm','atr_start_enabled','atr_start_multiplier','atr_trail_enabled',
                    'atr_trail_multiplier','retention_enabled','retention_pct','retention_until_enabled','retention_until'):
            mapping[key]=key
        values.update({name:getattr(exits,key) for name,key in mapping.items()})
        self.params = SimpleNamespace(**values)
        self._exit_manager_tab(parent,include_signals=False)
        self.dynamic_atr_detail.configure(font=('Segoe UI',12),cursor='hand2')
        self.dynamic_atr_detail._hover_hint=_HoverHint(self.dynamic_atr_detail,
            lambda:getattr(self,'_dynamic_pnl_help',''),click_to_toggle=True,hover=False)
        self._execution_controls(self.exit_body,exits)
        self._set_pending_fields()
        self.pnl_distances_preview.configure(cursor='hand2')
        self.pnl_distances_preview._hover_hint=_HoverHint(self.pnl_distances_preview,
            lambda:getattr(self,'_pnl_help',''),click_to_toggle=True,hover=False)
        self._update_units()
        self.render_atr()
        for widget in (self.normal_arm,self.normal_giveback,self.reentry_sl):
            widget.bind('<KeyRelease>',lambda _:self.render_atr(),add='+')

    def _set_pending_fields(self):
        self._migration_error=('Chờ giá vốn/ký quỹ cơ sở để đổi các ô CHỜ; giá trị đã lưu vẫn giữ nguyên.'
            if self._pending_fields else '')
        for key in self._pending_fields:
            widget=getattr(self,self._distance_fields[key])
            widget.delete(0,'end')
            widget.configure(placeholder_text='CHỜ',state='disabled')

    def _resolve_pending_fields(self,reference):
        if not self._pending_fields:return
        try:
            values,pending=price_rule_draft(self._exits(),reference.entry,reference.margin)
        except ValueError:return
        for key in self._pending_fields-pending:
            widget=getattr(self,self._distance_fields[key])
            widget.configure(state='normal',placeholder_text='')
            widget.delete(0,'end');widget.insert(0,str(values[key]))
        self.values=load_record(ExitSettings,values)
        self._pending_fields=pending
        self._migration_error=('Chờ giá vốn/ký quỹ cơ sở để đổi các ô CHỜ; giá trị đã lưu vẫn giữ nguyên.' if pending else '')
        if hasattr(self,'status'):
            configure_changed(self.status,text=self._migration_error,text_color='#FBBF24' if pending else self.TEXT)

    def _price_reference(self):
        ref=self._pnl_reference()
        return ref.entry,ref.margin

    def _pnl_reference(self):
        ref=protection_reference(self.app.view,self.app.settings.max_quote_age)
        if ref.source=='VỊ THẾ':return ref
        try:
            qty_text=self.app.qty.get().strip()
            qty=quantity(qty_text) if qty_text else None
        except (AttributeError,ValueError):qty=-1
        try:
            entry=float(self.app.limit.get()) if self.app.kind.get()=='LO' else None
            if entry is not None and (not isfinite(entry) or entry<=0):return ProtectionReference()
        except (AttributeError,ValueError):return ProtectionReference()
        return protection_reference(self.app.view,self.app.settings.max_quote_age,entry=entry,quantity=qty)

    def _execution_controls(self,body,exits):
        bar=ctk.CTkFrame(body,fg_color='#1C2B3B',border_width=1,border_color='#344D66',corner_radius=7)
        bar.grid(row=0,column=0,columnspan=2,sticky='ew',padx=4,pady=(2,5))
        ctk.CTkLabel(bar,text='RULE CHUNG',height=22,font=('Segoe UI',12,'bold'),text_color='#B9D9FA').pack(side='left',padx=8,pady=3)
        ctk.CTkLabel(bar,text='CÁC MỐC: % GIÁ VÀO',height=22,font=('Segoe UI',12),text_color=self.TEXT).pack(side='right',padx=8)
        for index,key,label,color in ((0,'sl_enabled','BẬT SL','#EF6B73'),(1,'tp_enabled','BẬT TP','#36C997')):
            entry=(self.initial_sl,self.take_profit)[index]
            row=entry.master
            variable=tk.BooleanVar(value=getattr(exits,key));setattr(self,key,variable)
            caption=next(w for w in row.winfo_children() if isinstance(w,ctk.CTkLabel) and w.cget('text'))
            caption.destroy()
            switch=ctk.CTkSwitch(row,text=('SL' if index==0 else 'TP')+' (% GIÁ)',width=1,variable=variable,font=('Segoe UI',12,'bold'),progress_color=color,
                button_color='#E0E8F1',fg_color='#3A4553')
            switch.grid(row=0,column=0,sticky='w')
        self.arm_enabled=tk.BooleanVar(value=exits.arm_enabled)
        header=self.protect_trail_card._viking_header
        ctk.CTkSwitch(header,text='',width=36,variable=self.arm_enabled,progress_color='#4A9FE8',button_color='#E0E8F1',command=self.render_atr).pack(side='left',before=header.winfo_children()[0],padx=(0,5))
        self._ema_controls(body,exits)

    def _ema_controls(self,body,exits):
        card=self._card(body,'E · THOÁT THEO EMA',
            'Long đóng toàn bộ khi EMA nhanh < EMA chậm; Short khi EMA nhanh > EMA chậm. EMA nến 1D cập nhật theo từng giá mới hợp lệ. E độc lập tín hiệu/RSI/Telegram, chỉ thực thi khi E + BOT + quyền vị thế ON.',3,0,span=2,compact=True)
        card.configure(fg_color='#202938',border_color='#415876')
        self.ema_exit_enabled=tk.BooleanVar(value=exits.ema_exit_enabled)
        header=card._viking_header
        ctk.CTkSwitch(header,text='',width=36,variable=self.ema_exit_enabled,progress_color='#9B8AFB',button_color='#E0E8F1').pack(side='left',before=header.winfo_children()[0],padx=(0,5))
        content=ctk.CTkFrame(card,fg_color='transparent');content.pack(fill='x',padx=6,pady=3)
        content.grid_columnconfigure((0,1),weight=1,uniform='ema-controls')
        ctk.CTkLabel(header,text='1D · REALTIME',height=20,font=('Segoe UI',11),text_color='#B9D9FA').pack(side='right')
        for column,name,label,value,hint in ((0,'ema_exit_fast','EMA nhanh',exits.ema_exit_fast,'Số phiên của EMA nhanh; phải nhỏ hơn EMA chậm.'),
                (1,'ema_exit_slow','EMA chậm',exits.ema_exit_slow,'Số phiên của EMA chậm. Thiếu ít nhất EMA chậm + 1 mẫu hợp lệ thì CHỜ.')):
            cell=ctk.CTkFrame(content,fg_color='transparent');cell.grid(row=0,column=column,sticky='ew');cell._viking_compact=True
            setattr(self,name,self._field(cell,label,value,hint))
        self.ema_exit_value=ctk.CTkLabel(card,text='',height=1,font=('Segoe UI',12),anchor='w',justify='left')
        self.ema_exit_value.bind('<Configure>',lambda _:self.ema_exit_value.configure(wraplength=max(120,int(self.ema_exit_value.winfo_width()/self.ema_exit_value._get_widget_scaling())-4)),add='+')

    def _update_units(self):
        for entry,title,suffix in ((self.initial_sl,'SL','% GIÁ'),(self.take_profit,'TP','% GIÁ'),
                (self.normal_arm,'Bắt đầu','% GIÁ'),(self.normal_giveback,'Lùi','% GIÁ')):
            label=next((w for w in entry.master.winfo_children() if isinstance(w,ctk.CTkLabel) and w is not entry._hint_icon and w.cget('text')),None)
            if label:
                label.configure(text=f'{title} ({suffix})')

    def _exits(self):
        values=asdict(self.values)
        mapping={'sl_distance':'initial_sl','tp_distance':'take_profit','repeat_gap':'reentry_sl','arm_gain':'normal_arm',
            'trail_gap':'normal_giveback','arm_repeat':'normal_repeat',
            'dynamic_enabled':'normal_dynamic','dynamic_repeat':'dynamic_repeat',
            'sl_enabled':'sl_enabled','tp_enabled':'tp_enabled','arm_enabled':'arm_enabled','ema_exit_enabled':'ema_exit_enabled',
            'ema_exit_fast':'ema_exit_fast','ema_exit_slow':'ema_exit_slow','arm_repeat_below_arm':'below_arm'}
        for key in ('atr_start_enabled','atr_start_multiplier','atr_trail_enabled','atr_trail_multiplier',
                    'retention_enabled','retention_pct','retention_until_enabled','retention_until'):
            mapping[key]=key
        for key,name in mapping.items():
            if key in self._pending_fields:continue
            raw=getattr(self,name).get()
            old=values[key]
            values[key]=bool(raw) if isinstance(old,bool) else str(raw) if isinstance(old,str) else float(str(raw).strip().removesuffix('%').replace(',','.'))
        values['sl_distance']=abs(values['sl_distance'])
        return asdict(load_record(ExitSettings,shared_exit_settings(values)).validate())

    def render_atr(self):
        from .atr_preview import atr_preview
        ref=self._pnl_reference()
        self._resolve_pending_fields(ref)
        try:rules=self._exits()
        except (ValueError,AttributeError):rules=asdict(self.values)
        value,detail,ready=atr_preview(self.app.view,rules)
        self._dynamic_pnl_help=value+'\n'+detail
        if ready:
            converted=dynamic_pnl_preview(self.app.view,rules,ref,self.app.view['atr14']['pct'])
            if converted:
                detail,self._dynamic_pnl_help=converted
        configure_changed(self.dynamic_atr_value,text=value,text_color='#60A5FA' if ready else '#FBBF24')
        configure_changed(self.dynamic_atr_detail,text=detail)
        view=self.app.view.get('ema_exit',{})
        enabled=self.app.settings.exit.get('ema_exit_enabled',False)
        text=''
        if enabled:
            text=(f"E · EMA{view.get('fast_period',3)} {view['fast']:,.2f} / EMA{view.get('slow_period',6)} {view['slow']:,.2f} · 1D {view['mode']} / {view['interval']}"
                  if view.get('ready') else 'E · CHỜ GIÁ / NẾN 1D')
        configure_changed(self.ema_exit_value,text=text)
        if text and not self.ema_exit_value.winfo_manager():self.ema_exit_value.pack(fill='x',padx=12,pady=(2,4))
        elif not text and self.ema_exit_value.winfo_manager():self.ema_exit_value.pack_forget()
        self._pnl_help='\n'.join(pnl_preview(rules,ref))
        base,detail=pnl_preview(rules,ref,compact=True)
        if self._pending_fields:base,detail='CHỜ CƠ SỞ QUY ĐỔI', 'Chỉ các ô CHỜ giữ nguyên cấu hình cũ.'
        configure_changed(self.pnl_basis_preview,text=base)
        configure_changed(self.pnl_distances_preview,text=detail)
