"""Adapt the original MayinTien widgets to the VN30 account and execution model.

Presentation lives in panels.py. This module never submits an order implicitly.
"""
from datetime import datetime
import time
import tkinter as tk
import customtkinter as ctk

from ckps.models import FINAL, ExitSettings, Position, Quote, load_record, quantity
from ..formatting import money, price, clock
from .panels import OriginalPanels, INFO_PANEL_HEIGHT
from .management_preview import position_milestones
from .widgets import fit_label_text
from .tokens import *


class MayinController(OriginalPanels):
    def _build(self):
        self.account_id=self.settings.account_no or 'LOCAL'
        self.configure(fg_color='#111318')
        self.grid_columnconfigure(0,weight=0,minsize=420)
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(0,weight=1)
        self.left=ctk.CTkScrollableFrame(self,width=405,corner_radius=0,fg_color='#15171B',
            scrollbar_fg_color='#15171B',scrollbar_button_color='#262B32',scrollbar_button_hover_color='#3A3F47')
        self.left.grid(row=0,column=0,sticky='nsew')
        self.right=ctk.CTkFrame(self,corner_radius=0,fg_color='transparent')
        self.right.grid(row=0,column=1,sticky='nsew',padx=12,pady=10)
        self.right.grid_columnconfigure(0,weight=1)
        self.right.grid_rowconfigure(1,weight=0,minsize=170)
        self.right.grid_rowconfigure(2,weight=1,minsize=INFO_PANEL_HEIGHT)
        self._left_panel()
        self.mode_choice,self.bot=self.mode,self.bot_button
        self.kind=self.order_type
        self.qty,self.limit=tk.StringVar(),tk.StringVar()
        self.ticket_tp,self.ticket_sl=tk.StringVar(value='RULE'),tk.StringVar(value='RULE')
        self.quantity_entry,self.price_entry,self.tp_entry,self.sl_entry=self.quantity,self.price,self.tp,self.sl
        for entry,variable in ((self.quantity,self.qty),(self.price,self.limit),(self.tp,self.ticket_tp),(self.sl,self.ticket_sl)):
            entry.configure(textvariable=variable)
            variable.trace_add('write',lambda *_:self._refresh_ticket_preview())
        self.open_buttons=[self.execute_button,self.short_button]
        self.capacity_label=ctk.CTkLabel(self.left,text='SỨC MỞ: --',font=('Segoe UI',13),text_color=COL_MUTED)
        self.capacity_label.pack(fill='x',padx=12,pady=(2,4))
        self._right_panel()
        # The stock loss-lock does not exist in CKPS. Use that original cell for
        # collateral; do not retain a nonfunctional unlock button.
        self.after_idle(self._sync_left_scrollbar)
        self.bind('<Configure>',self._on_dashboard_resize,add='+')

    def _on_dashboard_resize(self,event=None):
        if event is not None and event.widget not in (self,self.left,self.left._parent_canvas):
            return
        if self.running and getattr(self,'_dashboard_resize_after',None) is None:
            self._dashboard_resize_after=self.after(25,self._flush_dashboard_resize)

    def _flush_dashboard_resize(self):
        try:
            if self.running:
                self._sync_left_scrollbar()
                self._layout_preview()
        finally:
            self._dashboard_resize_after=None

    def _default_tp_text(self):
        return 'RULE'

    def _sync_default_sl(self,**_):
        # RULE is resolved by ticket_rules at preview and at explicit submission.
        return None

    def _update_order_preview(self):
        if hasattr(self,'ticket_sl'):
            self._refresh_ticket_preview()

    def _refresh_account_now(self):
        self.send('refresh')







    def _mode_changed(self,mode):
        self._mode_selected(mode)

    def _toggle_bot(self):
        self.toggle_bot()

    def _rule_settings(self):
        self.settings_dialog('RULE')

    def _advanced(self):
        self.connection()

    def _order_type_changed(self,kind):
        self.price.configure(state='normal' if kind=='LO' else 'disabled')
        self._refresh_ticket_preview()

    def _activate_lo_input(self,_=None):
        if self.order_type.get()!='LO':
            self.order_type.set('LO')
            self._order_type_changed('LO')

    def _sl_edited(self,_=None):
        self._refresh_ticket_preview()

    @staticmethod
    def _focus_widget(widget):
        widget.focus_set()
        return 'break'

    def _submit(self,_):
        self.open_order('LONG')




    def _refresh_ticket_preview(self):
        if not hasattr(self,'ticket_sl'):
            return
        try:
            account=self.view.get('account',{})
            quote=self.view.get('quotes',{}).get(self.view.get('contract','VN30F1M'),{})
            entry=float(self.limit.get()) if self.kind.get()=='LO' and self.limit.get() else quote.get('last',0)
            rules,_=self.ticket_rules(entry)
            long_capacity=self.ticket_capacity('LONG',entry,rules)
            qty=quantity(self.qty.get()) if self.qty.get().strip() else long_capacity.maximum
            qty_unknown=not self.qty.get().strip() and (account.get('qmax_long') is None or account.get('margin_per_contract') is None)
            sl=(money(-rules.points(rules.sl_distance,entry)*qty*100_000) if entry and not qty_unknown else '—') if rules.sl_enabled else 'OFF'
            tp=(money(rules.points(rules.tp_distance,entry)*qty*100_000) if entry and not qty_unknown else '—') if rules.tp_enabled else 'OFF'
            fee=self.settings.estimated_fee_per_contract*qty
            fees=money(fee) if self.settings.estimated_fee_per_contract else 'CHỜ PHÍ'
            self.lbl_order_value_title.configure(text='KÝ QUỸ + PHÍ' if self.settings.estimated_fee_per_contract else 'KÝ QUỸ · CHỜ PHÍ')
            margin=long_capacity.margin_per_contract
            cash=money(margin*qty+fee) if margin is not None else '—'
            for widget,text in ((self.lbl_tp_preview,tp),(self.lbl_sl_preview,sl),(self.lbl_fee_preview,fees),(self.lbl_order_value,cash)):
                widget.configure(text=text)
        except (ValueError,TypeError):
            pass
        finally:
            if hasattr(self,'preview_management'):
                self._render_signal_preview()
                self._render_selected_management()
                self._queue_preview_layout()

    def _render_signal_preview(self):
        from .signal_preview import signal_preview
        colors={'green':('#86EFAC','#397B57'),'red':('#FCA5A5','#8B4851'),
                'neutral':(COL_TEXT,'#435367')}
        result=signal_preview(self.view,self.settings.max_quote_age)
        for prefix,card,(value,detail,tone) in zip(('entry','trend'),self.preview_signal_cards,result):
            foreground,border=colors[tone]
            card.configure(fg_color='#1C242E',border_color=border)
            getattr(self,'preview_'+prefix+'_value').configure(text=value,text_color=foreground)
            getattr(self,'preview_'+prefix+'_detail').configure(text=detail)

    def _render_management_milestones(self, arm, dynamic):
        for value, detail, milestone in ((self.preview_normal_value,self.preview_normal_detail,arm),
                                         (self.preview_exit_value,self.preview_exit_detail,dynamic)):
            text=milestone.value.removeprefix('AUTO · ').replace('ALERT · ','BÁO · ',1)
            value.configure(text='Chưa bật' if milestone.value=='OFF' else text)
            detail.configure(text=milestone.detail)
            value.configure(text_color=COL_MUTED if milestone.value=='OFF' else COL_TEXT)

    def _render_management_config(self, rules):
        """Full configuration stays in a readable panel opened from each title."""
        unit='điểm' if rules.distance_unit=='POINTS' else '%'
        for prefix in ('arm','dynamic'):
            title='TSL / ARM · SAU ARM' if prefix=='arm' else 'DYNAMIC · TRƯỚC ARM'
            if not getattr(rules,prefix+'_enabled'):
                self._preview_help[prefix]=title+'\nChưa bật. Chỉnh tại RULE hoặc BẢO VỆ LỆNH.'
                continue
            policy=getattr(rules,prefix+'_policy')
            basis='gốc' if getattr(rules,prefix+'_basis')=='ORIGINAL' else 'còn lại'
            action=f"Đóng {getattr(rules,prefix+'_close_pct'):g}% {basis}" if policy=='AUTO' else 'Chỉ thông báo'
            repeat=f'Lặp {rules.repeat_gap:g} {unit}' if getattr(rules,prefix+'_repeat') else 'Không lặp'
            if prefix=='arm':
                parameters=f'ARM {rules.arm_gain:g} {unit} · Lùi {rules.trail_gap:g} {unit}'
                explanation='Đạt ARM rồi bám đỉnh Long / đáy Short. Giá lùi tới mốc thì xử lý.'
            else:
                parts=[]
                if rules.atr_start_enabled:parts.append(f'Bắt đầu {rules.atr_start_multiplier:g} ATR')
                if rules.atr_trail_enabled:parts.append(f'Lùi {rules.atr_trail_multiplier:g} ATR')
                if rules.retention_enabled:parts.append(f'Giữ {rules.retention_pct:g}% lãi')
                parameters=' · '.join(parts)
                explanation='Bảo vệ trước ARM. Khi đạt ARM, TSL tiếp quản.'
            self._preview_help[prefix]='\n'.join((title,explanation,parameters,action+' · '+repeat,
                'AUTO tự đóng khi đủ quyền; ALERT chỉ ghi LOG.'))

    def _render_selected_management(self):
        selected=self.positions_tree.selection()
        row=next((o for o in self.view.get('orders',[]) if selected and o['id']==selected[0]),None)
        position_id=row.get('position_id') if row else selected[0] if selected else None
        raw=next((p for p in self.view.get('positions',[]) if p['id']==position_id),None)
        if not raw:
            if self.preview_management.winfo_manager():self.preview_management.grid_remove()
            return
        if not self.preview_management.winfo_manager():self.preview_management.grid()
        position=load_record(Position,raw)
        rules=load_record(ExitSettings,position.exit_overrides or self.settings.exit)
        self.preview_order_title.configure(text='BẢO VỆ VỊ THẾ')
        source='RIÊNG' if position.exit_overrides is not None else 'RULE CHUNG'
        self.preview_rule_source.configure(text='RULE RIÊNG' if position.exit_overrides is not None else 'RULE CHUNG')
        self._render_management_config(rules)
        self._preview_position_context=f'{position.side} · {position.symbol}\nGiá vốn {price(position.entry)} · Giá {price(self.view.get("quotes",{}).get(position.symbol,{}).get("last"))}\nCòn {position.quantity}/{position.original_quantity} HĐ · {source}'
        quote=self.view.get('quotes',{}).get(position.symbol,{})
        atr=self.view.get('atr14_pct') if position.symbol==self.view.get('contract') else None
        ready=self.view.get('healthy') and self.view.get('consistent') and bool(quote) and load_record(Quote,quote).fresh(self.settings.max_quote_age)
        pending=[o for o in self.view.get('orders',[]) if o.get('position_id')==position.id and o['action']=='CLOSE' and o['status'] not in FINAL]
        self._render_management_milestones(*position_milestones(position,rules,quote.get('last'),atr,ready=ready,pending=pending))

    def render(self):
        view,account=self.view,self.view.get('account',{})
        mode=view.get('mode',self.settings.mode)
        requested=self.mode_requested or (self.switch_pending[0].mode if self.switch_pending else None)
        self.mode_choice.set(requested or mode)
        self.mode_selector.configure(selected_color=COL_WARN if requested else COL_GREEN,
            state='disabled' if self.switch_pending else 'normal')
        self.lbl_equity_title.configure(text='KÝ QUỸ ẢO · PAPER' if mode=='PAPER' else 'KÝ QUỸ · REAL')
        self.lbl_equity.configure(text=money(account.get('collateral_total')))
        self.lbl_account.configure(text='PAPER · Tiền ảo / giá DNSE' if mode=='PAPER' else f'Tài khoản {self.settings.account_no} · REAL')
        self.lbl_cash.configure(text='Tổng tiền: '+money(account.get('total_money')),text_color=COL_MUTED)
        self.lbl_session.configure(text=datetime.now().strftime('%d/%m · %H:%M:%S'))
        contract=view.get('contract','VN30F1M')
        quote=view.get('quotes',{}).get(contract,{})
        ready=bool(quote and load_record(Quote,quote).fresh(self.settings.max_quote_age))
        connection=view.get('market_connection',{})
        self.lbl_brain.configure(text=f'{requested} · CHƯA KẾT NỐI' if requested else 'DNSE: '+('ĐÃ CÓ GIÁ' if ready else 'CHỜ GIÁ' if connection.get('configured') else 'CHƯA KẾT NỐI'),text_color=COL_GREEN if ready and not requested else COL_WARN)
        self.lbl_quote_symbol.configure(text=contract)
        value=quote.get('last')
        self.lbl_price.configure(text=price(value),text_color=COL_TEXT)
        self.lbl_market.grid_remove()
        self.lbl_change.configure(text=('Ước ký quỹ/HĐ: ' if mode=='PAPER' else 'Ký quỹ/HĐ: ')+money(account.get('margin_per_contract')),font=('Segoe UI',13))
        self.market_context_label.configure(text='CHỈ THAM KHẢO · MẪU' if getattr(self,'preview_only',False) else 'CHỈ THAM KHẢO')
        if not self.limit.get() and value:
            self.limit.set(f'{value:.1f}')
        armed=view.get('armed',False)
        self.bot.configure(text='BOT · ON' if armed else 'ĐANG BẬT…' if self.bot_requested else 'BOT · OFF',fg_color='#15803D' if armed else COL_GRAY)
        self.capacity_label.configure(text=f"SỨC MỞ LONG {view.get('LONG',{}).get('maximum','—')} / SHORT {view.get('SHORT',{}).get('maximum','—')} HĐ" if ready else '')
        calendar_reason=view.get('calendar',{}).get('reason')
        if calendar_reason:self.capacity_label.configure(text=calendar_reason,text_color=COL_WARN,wraplength=380)
        else:self.capacity_label.configure(text_color=COL_MUTED)
        self._render_running()
        self._render_history()
        pnl_values=[load_record(Position,p).pnl(view['quotes'][p['symbol']]['last']) if view.get('quotes',{}).get(p['symbol'],{}).get('last') else None for p in view.get('positions',[])]
        pnl=sum(pnl_values) if all(value is not None for value in pnl_values) else None
        self.lbl_pnl.configure(text='PNL: '+money(pnl),text_color=COL_MUTED if pnl is None else COL_GREEN if pnl>=0 else COL_RED)
        events=sorted([*view.get('events',[]),*self.ui_events],key=lambda row:row[0])
        text='\n'.join(f'{clock(at)} [{kind}] {message}' for at,kind,message in events[-300:])
        if getattr(self.logs,'_last_text',None)!=text:
            self.logs.configure(state='normal')
            self.logs.delete('1.0','end')
            self.logs.insert('1.0',text)
            self.logs.see('end')
            self.logs.configure(state='disabled')
            self.logs._last_text=text
        status=view.get('error') or connection.get('error') or view.get('telegram_error') or ''
        if requested:
            status=f'Cấu hình {requested} · Sổ đang chạy: {mode}. Đóng KẾT NỐI để hủy.'
        if self.ui_status and self.ui_status[1]>time.monotonic():
            status=self.ui_status[0]
        self.status.configure(text=status,text_color=COL_RED if view.get('error') else COL_MUTED)
        self.status.grid() if status else self.status.grid_remove()
        for button in self.open_buttons:
            button.configure(state='normal' if ready and view.get('healthy') and view.get('consistent') and not self.order_busy and not requested and not calendar_reason else 'disabled')
        self._fit_account_stats()
        self._refresh_ticket_preview()
        self._fit_preview_text()
