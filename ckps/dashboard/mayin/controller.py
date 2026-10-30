"""Adapt the original MayinTien widgets to the VN30 account and execution model.

Presentation lives in panels.py. This module never submits an order implicitly.
"""
from datetime import datetime
from dataclasses import asdict
from math import isfinite
import time
import tkinter as tk
import customtkinter as ctk

from ckps.models import FINAL, ExitSettings, Position, Quote, load_record, quantity
from ckps.rules.distances import price_percent_rules
from ckps.rules.defaults import shared_exit_settings
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
        self.ticket_tp,self.ticket_sl=tk.StringVar(value='OFF'),tk.StringVar(value='RULE')
        self.quantity_entry,self.price_entry,self.tp_entry,self.sl_entry=self.quantity,self.price,self.tp,self.sl
        for entry,variable in ((self.quantity,self.qty),(self.price,self.limit),(self.tp,self.ticket_tp),(self.sl,self.ticket_sl)):
            entry.configure(textvariable=variable)
            if entry in (self.quantity,self.price):
                variable.trace_add('write',lambda *_:self._refresh_ticket_preview())
            else:
                entry.configure(state='disabled')
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
        rules=load_record(ExitSettings,shared_exit_settings(self.settings.exit))
        try:
            account=self.view.get('account',{})
            quote=self.view.get('quotes',{}).get(self.view.get('contract','VN30F1M'),{})
            entry=float(self.limit.get()) if self.kind.get()=='LO' else quote.get('last',0)
            if not isfinite(entry) or entry<=0:
                raise ValueError('Chờ giá hợp lệ.')
            rules,_=self.ticket_rules(entry)
            held_side=next((p['side'] for p in self.view.get('positions',[])
                            if p['symbol']==self.view.get('contract')),None)
            side=held_side if held_side in {'LONG','SHORT'} else 'LONG'
            available=self.ticket_capacity(side,entry,rules)
            margin=available.margin_per_contract
            qty=quantity(self.qty.get()) if self.qty.get().strip() else available.maximum
            if self.qty.get().strip() and qty<=0:
                raise ValueError('Chờ khối lượng hợp lệ.')
            qty_unknown=not self.qty.get().strip() and (account.get('qmax_'+side.lower()) is None
                or margin is None or (not held_side and account.get('qmax_long')!=account.get('qmax_short')))
            sl=(money(-rules.points(rules.sl_distance,entry,margin)*qty*100_000) if entry and not qty_unknown else '—') if rules.sl_enabled else 'OFF'
            tp=(money(rules.points(rules.tp_distance,entry,margin)*qty*100_000) if entry and not qty_unknown else '—') if rules.tp_enabled else 'OFF'
            package=account.get('package_fees',{})
            per_contract=package.get('open')
            if per_contract is None and self.settings.mode=='PAPER' and self.settings.estimated_fee_per_contract:
                per_contract=self.settings.estimated_fee_per_contract
            fee=per_contract*qty if per_contract is not None and not qty_unknown else None
            fees=money(fee) if fee is not None else 'CHỜ HĐ' if qty_unknown else 'CHỜ DNSE'
            self.lbl_fee_title.configure(text='PHÍ GÓI' if package.get('open') is not None else 'PHÍ MÔ PHỎNG' if per_contract is not None else 'PHÍ')
            self.lbl_order_value_title.configure(text='KÝ QUỸ + PHÍ GÓI' if package.get('open') is not None else 'KÝ QUỸ + PHÍ' if per_contract is not None else 'KÝ QUỸ · CHỜ PHÍ')
            cash=money(margin*qty+fee) if margin is not None and fee is not None and not qty_unknown else '—'
            for widget,text in ((self.lbl_tp_preview,tp),(self.lbl_sl_preview,sl),(self.lbl_fee_preview,fees),(self.lbl_order_value,cash)):
                widget.configure(text=text)
        except (ValueError,TypeError):
            for widget,text in ((self.lbl_tp_preview,'—' if rules.tp_enabled else 'OFF'),
                                (self.lbl_sl_preview,'—' if rules.sl_enabled else 'OFF'),
                                (self.lbl_fee_preview,'—'),(self.lbl_order_value,'—')):
                widget.configure(text=text)
        finally:
            if hasattr(self,'preview_management'):
                self._render_signal_preview()
                self._render_selected_management()
                self._queue_preview_layout()

    def _render_signal_preview(self):
        from .signal_preview import signal_preview
        colors={'green':('#86EFAC','#397B57'),'red':('#FCA5A5','#8B4851'),
                'neutral':(COL_TEXT,'#435367')}
        session=getattr(self,'signal_session',None)
        result=signal_preview({**self.view,'analysis_running':bool(session and session.running)},self.settings.max_quote_age)
        for prefix,card,(value,detail,tone) in zip(('entry','trend'),self.preview_signal_cards,result):
            foreground,border=colors[tone]
            card.configure(fg_color='#1C242E',border_color=border)
            getattr(self,'preview_'+prefix+'_value').configure(text=value,text_color=foreground)
            getattr(self,'preview_'+prefix+'_detail').configure(text=detail)
        from .connection_status import otp_status
        text,tone=otp_status(self.view,self.settings.mode)
        self.preview_connection_status.configure(text=text,text_color=COL_GREEN if tone=='green' else COL_WARN if tone=='amber' else COL_MUTED)
        from .atr_preview import atr_preview
        value,detail,ready=atr_preview(self.view)
        self.preview_atr_value.configure(text=value,text_color=COL_ACCENT_BLUE if ready else COL_WARN)
        self.preview_atr_detail.configure(text=detail)
        popup=self.popups.get('rule')
        if popup and popup.winfo_exists():popup.render_atr()

    def _render_management_milestones(self, arm, dynamic):
        for value, detail, milestone in ((self.preview_normal_value,self.preview_normal_detail,arm),
                                         (self.preview_exit_value,self.preview_exit_detail,dynamic)):
            text=milestone.value.removeprefix('AUTO · ').replace('ALERT · ','BÁO · ',1)
            value.configure(text='Chưa bật' if milestone.value=='OFF' else text)
            detail.configure(text=milestone.detail)
            value.configure(text_color=COL_MUTED if milestone.value=='OFF' else COL_TEXT)

    def _render_management_config(self, rules, entry=None, margin=None):
        """Full configuration stays in a readable panel opened from each title."""
        try:
            rules=load_record(ExitSettings,price_percent_rules(shared_exit_settings(asdict(rules)),entry,margin))
        except ValueError:
            for prefix in ('arm','dynamic'):
                self._preview_help[prefix]='Chờ dữ liệu xác minh để hiển thị % giá vốn. Các mốc đang chạy được giữ nguyên.'
            return
        unit='% giá vốn'
        for prefix in ('arm','dynamic'):
            title='TSL / ARM · SAU ARM' if prefix=='arm' else 'DYNAMIC · TRƯỚC ARM'
            if not getattr(rules,prefix+'_enabled'):
                self._preview_help[prefix]=title+'\nChưa bật. Chỉnh tại RULE → E/M, áp dụng chung tất cả hợp đồng.'
                continue
            action='Tự đóng 50% HĐ còn lại'
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
                'Cần BOT và quyền quản lý ON; 1 HĐ còn lại thì đóng 1.'))

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
        rules=load_record(ExitSettings,shared_exit_settings(self.settings.exit))
        self.preview_order_title.configure(text='BẢO VỆ VỊ THẾ')
        source='RULE CHUNG'
        self.preview_rule_source.configure(text=source)
        self._render_management_config(rules,position.entry,position.margin_per_contract)
        self._preview_position_context=f'{position.side} · {position.symbol}\nGiá vốn {price(position.entry)} · Giá {price(self.view.get("quotes",{}).get(position.symbol,{}).get("last"))}\nĐơn vị hiển thị: % giá vốn\nCòn {position.quantity}/{position.original_quantity} HĐ · {source}'
        quote=self.view.get('quotes',{}).get(position.symbol,{})
        atr=self.view.get('atr14_pct') if position.symbol==self.view.get('contract') else None
        ready=self.view.get('healthy') and self.view.get('consistent') and bool(quote) and load_record(Quote,quote).fresh(self.settings.max_quote_age)
        pending=[o for o in self.view.get('orders',[]) if o.get('position_id')==position.id and o['action']=='CLOSE' and o['status'] not in FINAL]
        self._render_management_milestones(*position_milestones(position,rules,quote.get('last'),atr,ready=ready,pending=pending))

    def render(self):
        view,account=self.view,self.view.get('account',{})
        self.ticket_tp.set('OFF')
        rules=load_record(ExitSettings,shared_exit_settings(self.settings.exit))
        try:
            quote=view.get('quotes',{}).get(view.get('contract'),{})
            if quote and (quote.get('symbol')!=view.get('contract') or not load_record(Quote,quote).fresh(self.settings.max_quote_age)):
                quote={}
            displayed=price_percent_rules(self.settings.exit,quote.get('last'),account.get('margin_per_contract'))
            self.ticket_sl.set(f"{displayed['sl_distance']:g}%" if rules.sl_enabled else 'OFF')
        except ValueError:
            self.ticket_sl.set('CHỜ' if rules.sl_enabled else 'OFF')
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
        cache=view.get('market_cache',{})
        display_quote=quote or cache.get('quote',{})
        value=quote.get('last')
        self.lbl_price.configure(text=price(display_quote.get('last')),text_color=COL_TEXT if ready else COL_WARN)
        if not quote and display_quote:self.lbl_quote_symbol.configure(text=cache.get('contract',contract))
        if display_quote:
            self.lbl_market.configure(text=('DNSE · ' if ready else 'GIÁ CŨ · ' if quote else 'GIÁ LƯU · ')+clock(display_quote.get('at')),
                text_color=COL_MUTED if ready else COL_WARN)
            self.lbl_market.grid()
        else:self.lbl_market.grid_remove()
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
