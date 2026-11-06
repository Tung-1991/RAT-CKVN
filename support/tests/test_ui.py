from dataclasses import asdict
import inspect
from pathlib import Path
import subprocess
import sys

import pytest


def _layout_scenario(scale):
    import customtkinter as ctk
    from ckps.dashboard.window import App
    from ckps.dashboard.mayin.panels import OriginalPanels
    from ckps.dashboard.mayin.ui_compat import NativeFontMetrics
    from ckps.models import Settings
    from ckps.rules.signal_settings import SignalSettings
    ctk.deactivate_automatic_dpi_awareness()
    ctk.set_widget_scaling(scale)
    ctk.set_window_scaling(scale)
    app = App(settings=Settings(), start_runtime=False)
    app.update()
    errors=[]
    app.report_callback_exception=lambda *args:errors.append(args)
    def settle(ms=180):
        # A quit scheduled by another UI wait may end one loop early on Windows.
        # Give native geometry/DPI events the full settling period in either case.
        from tkinter import Misc
        from time import monotonic
        deadline=monotonic()+ms/1000
        while monotonic()<deadline:
            timer=app.after(max(1,round((deadline-monotonic())*1000)),app.quit)
            Misc.mainloop(app)
            app.after_cancel(timer)
        app.update()  # Flush native idle geometry before measuring rendered controls.
    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)
    try:
        settle(500)
        assert app.lbl_tp_preview.cget('text') == 'OFF'
        assert app.lbl_sl_preview.cget('text') == '—'
        assert all(label.cget('text') != 'NA' for label in (app.lbl_tp_preview, app.lbl_sl_preview, app.lbl_fee_preview, app.lbl_order_value))
        app.render()
        settle()
        assert isinstance(app,OriginalPanels)
        assert set(app.info_pages)=={'PREVIEW','LOG'}
        assert not hasattr(app,'preview_pages') and not hasattr(app,'preview_tab_selector')
        assert not hasattr(app,'phase_bar') and not hasattr(app,'bot_logs')
        assert app.preview_focus_panel.master is app.info_pages['PREVIEW']
        assert app.preview_focus_panel.winfo_rooty()>app.positions_tree.winfo_rooty()
        assert app.rule_button.winfo_ismapped() and app.connection_button.winfo_ismapped()
        assert not hasattr(app,'_em_buttons')
        assert not hasattr(app,'preview_metrics')
        assert not hasattr(app,'preview_wait') and app.preview_data.winfo_ismapped()
        assert not app.preview_management.winfo_ismapped()
        assert app.preview_entry_value.cget('text')=='CHỜ'
        assert app.preview_trend_value.cget('text')=='CHỜ'
        assert not hasattr(app,'preview_rule_ema') and not hasattr(app,'preview_rule_phase1_card') and not hasattr(app,'preview_rule_phase3_card')
        assert app.preview_atr.winfo_ismapped()
        assert 'CHỜ NẾN 1D' in app.preview_atr_value.cget('text')
        assert not app.view.get('quotes')  # Configuration Preview does not invent prices.
        assert not app.positions_tree.horizontal.winfo_ismapped()
        assert app.table_workspace.winfo_height()>=app.right.winfo_height()*.4
        assert abs(app.info_panel.winfo_rooty()+app.info_panel.winfo_height()-app.right.winfo_rooty()-app.right.winfo_height())<=2
        assert 300<=app.info_panel.winfo_height()/app.info_panel._get_widget_scaling()<=380
        assert app.preview_connection_status.cget('font')==('Segoe UI',11)
        assert app.preview_authentication.winfo_height()/app.preview_authentication._get_widget_scaling()<=28
        assert app.preview_entry_value.cget('font')[1]==22
        assert app.preview_entry_detail.cget('font')==('Segoe UI',14)
        assert not {'manage','adopt'} & set(app.action_buttons)
        assert not hasattr(app,'preview_state_panel')
        assert 'pnl' not in app.positions_tree._display
        for name in ('LOG','PREVIEW'):
            app._select_info(name);settle()
            assert app.info_choice.get()==name
        assert not hasattr(app,'preview_health_group')
        app._mode_selected('REAL');settle(600)
        assert app.settings.mode=='PAPER' and app.mode_choice.get()=='PAPER'
        assert app.mode_requested is None and 'connection' not in app.popups
        assert 'KẾT NỐI' in app.status.cget('text')
        connection=app.connection('REAL');settle(600)
        assert connection.tabs.get()=='DNSE / VỐN'
        assert connection.otp_card.winfo_ismapped()
        for widget in widgets(connection.pages['DNSE / VỐN']):
            if isinstance(widget,ctk.CTkEntry) and widget.winfo_ismapped():
                body=connection.connection_body
                canvas=body._parent_canvas
                canvas.yview_moveto(max(0,widget.winfo_rooty()-body.winfo_rooty()-4)/body.winfo_height())
                app.update()
                assert widget.winfo_rootx()+widget.winfo_width()<=connection.winfo_rootx()+connection.winfo_width()
                assert widget.winfo_rooty()+widget.winfo_height()<=connection.footer.winfo_rooty()
                assert widget.winfo_rooty()>=canvas.winfo_rooty()-2
        connection.connection_body._parent_canvas.yview_moveto(0)
        sent=[]
        app.send=lambda *args,**kwargs:sent.append((args,kwargs))
        app.open_order('LONG');app.toggle_bot()
        assert not sent and not app.confirmation.winfo_ismapped()
        connection.save()  # Missing account/key: must not switch or connect.
        assert app.settings.mode=='PAPER' and not app.switch_pending
        assert 'Nhập' in connection.note.cget('text')
        connection.destroy();settle()
        assert app.mode_choice.get()=='PAPER' and app.mode_requested is None
        from dataclasses import replace
        app.confirm('PAPER confirmation',lambda:sent.append('wrong-book'))
        old_confirm=app.confirm_primary.cget('command')
        old_settings=app.settings
        app.settings=replace(old_settings,mode='REAL')
        old_confirm()
        assert not sent and 'đã thay đổi' in app.status.cget('text')
        app.settings=old_settings
        assert not app.action_bar.winfo_ismapped()
        app.limit.set('2000.0');app.ticket_tp.set('0.5%')
        settle()
        for entry in (app.quantity_entry,app.price_entry,app.tp_entry,app.sl_entry):
            entry._viking_fit_text()
            assert NativeFontMetrics(entry,entry._entry.cget('font')).measure(entry.get())<=entry._entry.winfo_width()
        dialog=app.settings_dialog('RULE');settle()
        assert set(dialog.tabs._tab_dict)=={'E/M','TÍN HIỆU'}
        assert not hasattr(dialog,'phase_tabs') and not hasattr(dialog,'sell_alert_enabled')
        assert dialog._exits()==app.settings.exit
        connection=app.connection();settle(600)
        assert dialog is not connection
        assert set(connection.pages)=={'DNSE / VỐN','TELEGRAM / LỊCH'}
        assert {'telegram.token','telegram.chat'} <= set(connection.variables)
        assert connection.otp_card.winfo_ismapped()
        assert not hasattr(connection,'csv_button') and 'paper.price' not in connection.variables
        assert 'owner_chat' not in connection.variables and 'owner_token' not in connection.variables
        connection.select_page('VỐN');settle(600)
        assert connection.paper_capital_entry.winfo_ismapped()
        connection.variables['paper_balance'].set('250,000,000')
        connection.apply_capital()
        assert sent[-1][0]==('paper_capital',250_000_000)
        sent.clear()
        for page in ('E/M','TÍN HIỆU'):
            dialog.select(page);settle()
            host=dialog.protection_host if page=='E/M' else dialog.signal_form.body
            for w in widgets(host):
                if isinstance(w,ctk.CTkEntry) and w.winfo_ismapped():
                    assert w.winfo_rootx()+w.winfo_width()<=dialog.winfo_rootx()+dialog.winfo_width()
        saved,sent=[],[]
        app.save_config=saved.append
        app.send=lambda *a,**kw:sent.append((a,kw))
        dialog.select('E/M');settle()
        dialog.save()
        assert len(saved)==1 and saved[0].signals==SignalSettings().to_dict()
        assert not any(name[0] in {'open_manual','close_position'} for name,kw in sent)
        popup_size=(connection.winfo_width(),connection.winfo_height())
        assert popup_size==(dialog.winfo_width(),dialog.winfo_height())
        for name in connection.pages:
            connection.select_page(name);settle(600)
            assert (connection.winfo_width(),connection.winfo_height())==popup_size
            for widget in widgets(connection.pages[name]):
                if name == 'TELEGRAM / LỊCH':continue
                if widget is not connection.primary and isinstance(widget,(ctk.CTkEntry,ctk.CTkSwitch,ctk.CTkButton)) and widget.winfo_ismapped():
                    body=connection.connection_body
                    canvas=body._parent_canvas
                    # CTk reports off-viewport scroll children as mapped.
                    canvas.yview_moveto(max(0,widget.winfo_rooty()-body.winfo_rooty()-4)/body.winfo_height())
                    app.update()
                    bottom=connection.pages[name].winfo_rooty()+connection.pages[name].winfo_height()-4
                    assert widget.winfo_rooty()+widget.winfo_height()<=min(bottom,connection.footer.winfo_rooty()), (name,widget,widget.winfo_rooty(),widget.winfo_height(),bottom,connection.footer.winfo_rooty(),connection.winfo_height(),connection._get_window_scaling())
            connection.connection_body._parent_canvas.yview_moveto(0)
        connection.destroy();dialog.destroy();sent.clear()
        from dataclasses import asdict
        from ckps.models import Quote
        app.view.update(contract='VN30F1M', quotes={'VN30F1M':asdict(Quote('VN30F1M',2000))},
            account={'remaining_margin':100_000_000,'used_margin':0,'margin_per_contract':40_000_000,
                     'pending_margin':0,'qmax_long':1,'qmax_short':1,'total_money':100_000_000})
        app.open_order('LONG');settle()
        assert not sent and app.confirmation.winfo_ismapped()
        app.confirm_primary.invoke()
        assert sent[0][0][:3]==('open_manual','LONG',1)
        from dataclasses import asdict
        from ckps.models import ExitSettings, Position, Quote
        from ckps.rules.protection import evaluate
        rules=ExitSettings(distance_unit='PRICE_PERCENT', arm_enabled=True,arm_gain=1,trail_gap=.25,arm_repeat=True,repeat_gap=.25,
            dynamic_enabled=True,dynamic_policy='AUTO',dynamic_close_pct=50,dynamic_repeat=True,
            atr_start_multiplier=.5,retention_pct=70,retention_until_enabled=False)
        app.settings.exit=asdict(rules)
        position=Position.create('VN30F1M','LONG',2,2000,history_verified=True,margin_per_contract=40_000_000)
        evaluate(position,2012,rules,1)
        position.metrics['DYN:AUTO']={'count':1,'anchor':2008.4}
        app.view.update(positions=[asdict(position)],orders=[],healthy=True,consistent=True,
            contract='VN30F1M',atr14_pct=1,quotes={'VN30F1M':asdict(Quote('VN30F1M',2007))})
        app.render();app.positions_tree.selection_set(position.id)
        app._refresh_ticket_preview();settle()
        assert 'MỐC 2,008.4' in app.preview_exit_value.cget('text')
        from time import time
        from datetime import date,timedelta
        stamp=time()
        app.view.update(atr14={'contract':'VN30F1M','period':14,'count':20,'pct':1.,
            'as_of':(date.today()-timedelta(days=1)).isoformat()},
            market_context={'state':'BELOW','ma':2010,'observed_at':stamp,'entry':{'state':'WAIT'},
                'analysis':{'contract':'VN30F1M','observed_at':stamp,'quote_at':stamp,
                    'p2':{'status':'CHỜ CẮT LÊN','indicators':{'buy_ema_fast':1998,'buy_ema_slow':2000,'rsi':42.5}}}})
        app._refresh_ticket_preview();settle()
        assert 'EMA nhanh 1,998.0' in app.preview_entry_detail.cget('text')
        assert 'RSI 42.50' in app.preview_entry_detail.cget('text')
        assert '2,000,000 đ/2 HĐ' in app.preview_atr_detail.cget('text')
        assert 'điểm' in app.preview_atr_detail.cget('text')
        assert app.positions_tree.cell(position.id,'managed')['text']=='CHƯA NHẬN'
        assert app.positions_tree.cell(position.id,'side')['color']=='#22C55E'
        assert app.positions_tree.cell(position.id,'pnl')['color']=='#22C55E'
        assert not app.positions_tree.horizontal.winfo_ismapped()
        for widget,font in app._preview_fit_labels:
            if not widget.winfo_ismapped():continue
            assert widget.winfo_rootx()>=app.preview_content.winfo_rootx()
            assert widget.winfo_rootx()+widget.winfo_width()<=app.preview_content.winfo_rootx()+app.preview_content.winfo_width()+2
            assert widget.winfo_rooty()+widget.winfo_height()<=app.info_panel.winfo_rooty()+app.info_panel.winfo_height(), (widget.cget('text'),widget.winfo_rooty(),widget.winfo_height(),app.info_panel.winfo_rooty()+app.info_panel.winfo_height())
            assert widget.winfo_rooty()+widget.winfo_height()<=widget.master.winfo_rooty()+widget.master.winfo_height(), widget.cget('text')
            assert widget.cget('font')[1]==font[1], widget.cget('text')
        for label in (app.preview_normal_value,app.preview_normal_detail,app.preview_exit_value,app.preview_exit_detail):
            assert label.winfo_rooty()+label.winfo_height()<=label.master.winfo_rooty()+label.master.winfo_height()
            # Tk measures the rendered, wrapped label. Measuring the whole string
            # as one line rejects the intentional fixed-font wrapping at high DPI.
            assert label._label.winfo_reqwidth()<=label.winfo_width(), label.cget('text')
            assert label._label.winfo_reqheight()<=label.winfo_height(), label.cget('text')
        app.geometry('1080x700');settle(500)
        assert not app.positions_tree.horizontal.winfo_ismapped()
        assert app.preview_management.winfo_ismapped() and app.preview_exit_value.winfo_ismapped()
        assert app.table_workspace.winfo_height()>=170*app.table_workspace._get_widget_scaling()
        assert abs(app.info_panel.winfo_rooty()+app.info_panel.winfo_height()-app.right.winfo_rooty()-app.right.winfo_height())<=2
        for widget,font in app._preview_fit_labels:
            if not widget.winfo_ismapped():continue
            assert widget.winfo_rooty()+widget.winfo_height()<=app.info_panel.winfo_rooty()+app.info_panel.winfo_height(), (widget.cget('text'),widget.winfo_rooty(),widget.winfo_height(),app.info_panel.winfo_rooty()+app.info_panel.winfo_height(),app.info_panel.cget('height'),app.preview_data.winfo_reqheight())
            assert widget.winfo_rooty()+widget.winfo_height()<=widget.master.winfo_rooty()+widget.master.winfo_height(), widget.cget('text')
            assert widget._label.winfo_reqwidth()<=widget.winfo_width(), widget.cget('text')
            assert widget._label.winfo_reqheight()<=widget.winfo_height(), widget.cget('text')
            ancestor=widget.master
            while ancestor is not app.info_panel:
                assert widget.winfo_rooty()+widget.winfo_height()<=ancestor.winfo_rooty()+ancestor.winfo_height(), (widget.cget('text'),ancestor)
                ancestor=ancestor.master
        assert not errors,errors
    finally:
        app.close()


@pytest.mark.parametrize("scale", [1., 1.25, 1.5, 2.])
def test_mayin_tien_layout_two_settings_sections_and_no_trade_popups(scale):
    code = inspect.getsource(_layout_scenario) + f"\n_layout_scenario({scale!r})"
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


def test_context_actions_inline_em_partial_close_and_unified_history(system):
    import customtkinter as ctk
    from ckps.models import Position
    from ckps.dashboard.window import App
    engine, broker, store = system
    engine.open_manual("LONG", 2, "MOK")
    engine.poll()
    position = store.positions()[0]
    pending = engine.close_position(position.id, 1, kind="LO", price=2020)
    app = App(settings=engine.settings, start_runtime=False)
    sent = []
    app.send = lambda *args, **kwargs: sent.append((args, kwargs))
    try:
        app.update()
        snapshot = engine.latest
        app.view = {"mode":"PAPER", "contract":snapshot.contract, "healthy":True, "consistent":True,"atr14_pct":1.25,
            "armed":False, "quotes":{k:asdict(v) for k,v in snapshot.quotes.items()},
            "account":{k:getattr(snapshot,k) for k in ("nav","remaining_margin","used_margin","margin_per_contract","pending_margin","observed_at","source")},
            "positions":[asdict(p) for p in store.positions()], "orders":[asdict(o) for o in store.orders()],
            "history":[], "events":[(1,"BOT","bot action"),(2,"MANUAL","manual action")],
            "analysis":{"signal_history":[{"id":"s1","at":1,"symbol":"VN30F1M","kind":"BUY","reason":"ALERT"}]},
            "LONG":{"maximum":2}, "SHORT":{"maximum":2}}
        app.render()
        assert app.preview_atr.winfo_ismapped()
        app.positions_tree.selection_set(position.id)
        app._refresh_ticket_preview()
        assert position.symbol in app._preview_position_context and '2/2 HĐ' in app._preview_position_context
        assert app.positions_tree.parent(pending.id) == position.id
        assert app.positions_tree.item(pending.id,"values")[0] == "CHỜ KHỚP"
        app.positions_tree.selection_set(pending.id)
        app._refresh_ticket_preview()
        assert position.symbol in app._preview_position_context and '2/2 HĐ' in app._preview_position_context
        app._sync_selection()
        assert app.action_buttons["edit"].winfo_manager() == "pack"
        assert not app.action_buttons["close"].winfo_manager()
        app.edit_order()
        assert app.detail_page.winfo_manager() == "grid" and not app.popups
        app.hide_editor()
        app.positions_tree.selection_set(position.id)
        app._sync_selection()
        assert app.action_buttons["close"].winfo_manager() == "pack"
        app.view["orders"][-1]["quantity"] = 2
        app._sync_selection()
        assert not app.action_buttons["close"].winfo_manager()
        app.view["orders"][-1]["quantity"] = 1
        app._sync_selection()
        rule = app.position_exit()
        app.update()
        assert app.info_panel.winfo_ismapped() and not hasattr(rule, 'scope_selector')
        assert not hasattr(rule, 'inherit_switch') and rule.primary.cget('text') == 'LƯU RULE'
        def controls(widget):
            for child in widget.winfo_children():
                if isinstance(child, (ctk.CTkEntry, ctk.CTkSwitch, ctk.CTkOptionMenu, ctk.CTkSegmentedButton)):
                    yield child
                else:
                    yield from controls(child)
        assert rule.initial_sl.cget('state') == 'normal'
        assert hasattr(rule,'take_profit')
        rule.sl_enabled.set(True)
        rule.initial_sl.delete(0, 'end')
        rule.initial_sl.insert(0, '10')
        rule.save()
        assert sent[-1][0][0] == 'settings' and sent[-1][0][1]['exit']['sl_distance'] == 10
        rule.destroy()
        app.update()
        app.close_position()
        assert app.editor_variables["qty"].get() == "1"
        before = len(sent)
        app.editor_save.invoke()
        assert len(sent) == before
        app.confirm_primary.invoke()
        assert sent[-1][0] == ("close_position", position.id, 1)
        assert sent[-1][1]["kind"] == "MOK"
        assert not any(window.winfo_exists() for window in app.popups.values())
        profit=Position.create('VN30F1M','LONG',1,2000,closed_at=1,realized=1_000_000,fees=25_000)
        loss=Position.create('VN30F1M','SHORT',1,2000,closed_at=2,realized=-500_000,fees=25_000)
        unknown=Position.create('VN30F1M','SHORT',1,2000,closed_at=3,pnl_verified=False)
        app.view['history']=[asdict(profit),asdict(loss),asdict(unknown)]
        window = app.history()
        app.update()
        assert set(window.pages) == {"GIAO DỊCH", "LỆNH"}
        assert len(app.order_history_tree.get_children()) == 2
        assert not hasattr(app,"signal_history_tree")
        assert app.history_tree.cell(profit.id,'pnl')['color']=='#22C55E'
        assert app.history_tree.cell(loss.id,'pnl')['color']=='#EF4444'
        assert app.history_tree.cell(loss.id,'side')['color']=='#EF4444'
        assert app.history_tree.cell(unknown.id,'pnl')['color']=='#F59E0B'
        assert app.order_history_tree.cell(pending.id,'status')['text']=='CHỜ KHỚP'
        app.history_tree.selection_set(loss.id)
        app.view['history'][0]['realized']=2_000_000
        app._render_history()
        assert app.history_tree.selection()==(loss.id,)
        assert app.history_tree.item(profit.id,'values')[5]=='1,975,000 đ'
        for tree in (app.history_tree,app.order_history_tree):
            tree._paint_rows()
            assert not tree.horizontal.winfo_manager()
        assert "bot action" in app.logs.get("1.0","end") and "manual action" in app.logs.get("1.0","end")
        app.view['quotes']={}
        app.render()
        assert app.lbl_pnl.cget('text')=='PNL: —'
        assert all(button.cget('state')=='disabled' for button in app.open_buttons)
    finally:
        app.close()


def _rule_adapter_scenario(clock):
    """Renamed MayinTien fields must preserve CKPS exit policies and units."""
    import socket
    import requests
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline UI scenarios must never contact DNSE/Telegram.')
    requests.Session.request=socket.socket.connect=forbidden
    from ckps.dashboard.window import App
    from dataclasses import asdict
    from ckps.models import Settings, ExitSettings
    from ckps.rules.signal_settings import SignalSettings
    exits=ExitSettings(distance_unit='POINTS', sl_enabled=True,sl_distance=8.5,tp_enabled=True,tp_distance=19,
        arm_enabled=True,arm_gain=12,trail_gap=4,arm_policy='ALERT',arm_close_pct=33,
        arm_basis='ORIGINAL',arm_repeat=True,repeat_gap=2.5,dynamic_enabled=True,
        dynamic_policy='AUTO',dynamic_close_pct=67,dynamic_basis='ORIGINAL',dynamic_repeat=True,
        atr_start_enabled=False,atr_start_multiplier=.7,atr_trail_enabled=True,atr_trail_multiplier=1.2,
        retention_enabled=True,retention_pct=81,retention_until_enabled=False,retention_until=22)
    signals=SignalSettings(enabled=False,buy_alert_enabled=True,sell_alert_enabled=False,
        buy_ema_fast=5,buy_ema_slow=13,sell_ema_fast=7,sell_ema_slow=21,
        rsi_period=17,buy_ema_cross_mode='SESSIONS',buy_ema_cross_sessions=6,
        buy_ema_va_lookback_enabled=True,buy_confirmation_enabled=True,buy_confirmation_minutes=8,
        buy_confirmation_require_ema=False,buy_window_enabled=True,buy_window_start='13:20',
        buy_volume_enabled=True,buy_volume_average_sessions=12,buy_volume_min_ratio=1.45,
        sell_signal_use_rsi=True,sell_signal_require_ema_cross=True,realtime_indicator_interval='2M',
        whipsaw_enabled=True,whipsaw_n=5,whipsaw_x=9)
    settings=Settings(exit=asdict(exits),signals=signals.to_dict(),estimated_fee_per_contract=25000).validate()
    app=App(settings=settings,start_runtime=False)
    try:
        app.update()
        window=app.settings_dialog('E/M')
        app.update()
        assert not hasattr(window,'indicator_exit_policy') and not hasattr(window,'rsi_period')
        assert not hasattr(window,'price_units')
        assert window._migration_error and window.primary.cget('state')=='normal'
        assert window.initial_sl.get()=='' and window.initial_sl.cget('state')=='disabled'
        assert window._exits()['sl_distance']==8.5 and window._exits()['distance_unit']=='POINTS'
        from ckps.models import Quote
        app.view.update(contract='VN30F1M',quotes={'VN30F1M':asdict(Quote('VN30F1M',2000))},
            account={'margin_per_contract':40_000_000,'margin_reference_price':2000})
        app.render()
        window.destroy()
        window=app.settings_dialog('E/M');app.update()
        from ckps.rules.defaults import shared_exit_settings
        expected={**shared_exit_settings(asdict(exits)),'distance_unit':'PRICE_PERCENT','trailing_unit':'PRICE_PERCENT'}
        for key in ('sl_distance','tp_distance','repeat_gap','arm_gain','trail_gap','retention_until'):
            expected[key]=getattr(exits,key)/2000*100
        assert window._exits()==expected
        for signed in ('-.25','-0,25%'):
            window.initial_sl.delete(0,'end');window.initial_sl.insert(0,signed)
            assert window._exits()['sl_distance']==.25
        window.initial_sl.delete(0,'end');window.initial_sl.insert(0,str(expected['sl_distance']))
        saved,sent=[],[]
        app.save_config=saved.append
        app.send=lambda *a,**kw:sent.append((a,kw))
        window.save()
        assert len(saved)==1 and saved[0].exit==expected
        assert saved[0].paper_balance==settings.paper_balance
        assert saved[0].signals==signals.validate().to_dict()
        assert not sent
        # A legacy PNL policy still needs its actual margin basis, even though
        # modern price rules can be edited and used without that basis.
        from dataclasses import replace
        legacy=asdict(ExitSettings(distance_unit='PNL_PERCENT',sl_enabled=True,sl_distance=2.5))
        app.settings=replace(settings,exit=legacy)
        app.view['account']={}
        window.destroy();window=app.settings_dialog('E/M');app.update()
        assert 'ký quỹ cơ sở' in window._migration_error
        assert window.primary.cget('state')=='normal' and app.settings.exit==legacy
        assert window.initial_sl.get()==''
        app.view['account']={'margin_per_contract':40_000_000,'margin_reference_price':2000}
        window.render_atr();app.update()
        assert not window._migration_error and window._exits()['sl_distance']==.5
        assert window._exits()['distance_unit']=='PRICE_PERCENT' and app.settings.exit==legacy
        # Price-based SL remains usable while only the old trailing group waits.
        legacy=asdict(ExitSettings(distance_unit='PRICE_PERCENT',trailing_unit='PNL_PERCENT',sl_enabled=True,sl_distance=.5,
            arm_enabled=True,arm_gain=5,trail_gap=1.25,repeat_gap=1.25))
        app.settings=replace(settings,exit=legacy);app.view['account']={}
        window.destroy();window=app.settings_dialog('E/M');app.update()
        assert window.initial_sl.get()=='0.5' and window.initial_sl.cget('state')=='normal'
        assert window.normal_arm.get()=='' and window.normal_arm.cget('state')=='disabled'
        window.initial_sl.delete(0,'end');window.initial_sl.insert(0,'.75')
        pending=window._exits()
        assert pending['sl_distance']==.75 and pending['arm_gain']==5 and pending['trailing_unit']=='PNL_PERCENT'
        window.save()
        assert saved[-1].exit==pending and not sent and app.settings.exit==legacy
        # A slow VPS can spend longer than max_quote_age opening the forms.
        # Verified margin alone must not unlock a draft against an old quote.
        clock.return_value+=settings.max_quote_age+1
        app.view['account']={'margin_per_contract':40_000_000,'margin_reference_price':2000}
        window.render_atr();app.update()
        assert window._migration_error and window.normal_arm.cget('state')=='disabled'
        assert window._exits()==pending and app.settings.exit==legacy
        # A genuinely new feed observation resolves only the pending group,
        # retaining the edited SL and leaving the saved/live RULE untouched.
        app.view['quotes']['VN30F1M']=asdict(Quote('VN30F1M',2000,at=clock()))
        window.render_atr();app.update()
        assert not window._migration_error and window.normal_arm.cget('state')=='normal'
        assert window._exits()['sl_distance']==.75 and window._exits()['arm_gain']==1
        assert saved[-1].exit==pending and app.settings.exit==legacy and not sent
    finally:
        app.close()


def test_original_rule_forms_roundtrip_ckps_protection_and_private_signals():
    # Windows Store Python cannot reliably create a second Tk interpreter after
    # destroying the first; isolate GUI sessions, like the DPI scenarios above.
    # Quote creation and freshness checks use one controlled clock, independent
    # of machine speed. Advance it explicitly to exercise stale-price gating.
    code=inspect.getsource(_rule_adapter_scenario)+"\nfrom time import time\nfrom unittest.mock import patch\nwith patch('time.time', return_value=time()) as clock:\n    _rule_adapter_scenario(clock)"
    result=subprocess.run([sys.executable,'-X','utf8','-c',code],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def _position_protection_scenario(scale):
    import socket
    import requests
    import customtkinter as ctk
    from dataclasses import asdict
    from tkinter import Misc
    from ckps.dashboard.window import App
    from ckps.dashboard.mayin.forms import OriginalRuleForms
    from ckps.models import ExitSettings, Position, Quote, Settings

    def forbidden(*args, **kwargs):
        raise AssertionError('UI verification must remain offline.')
    socket.socket.connect = requests.Session.request = forbidden
    ctk.deactivate_automatic_dpi_awareness()
    ctk.set_widget_scaling(scale)
    ctk.set_window_scaling(scale)
    app = App(settings=Settings(), start_runtime=False)
    app.geometry('1080x700')
    app.update()
    errors, sent = [], []
    app.report_callback_exception = lambda *args: errors.append(args)
    app.send = lambda *args, **kwargs: sent.append((args, kwargs))
    def settle(ms=180):
        from time import monotonic
        deadline = monotonic()+ms/1000
        while monotonic() < deadline:
            timer = app.after(max(1, round((deadline-monotonic())*1000)), app.quit)
            Misc.mainloop(app)
            app.after_cancel(timer)
        app.update()  # Flush native idle geometry before measuring rendered controls.
    def controls(parent):
        for child in parent.winfo_children():
            if isinstance(child, (ctk.CTkEntry, ctk.CTkSwitch, ctk.CTkOptionMenu, ctk.CTkSegmentedButton)):
                yield child
            else:
                yield from controls(child)
    try:
        settle(500)
        original = asdict(ExitSettings(distance_unit='POINTS', sl_enabled=True, sl_distance=12, tp_enabled=True, tp_distance=42,
            arm_enabled=True, arm_gain=20, trail_gap=5, arm_policy='ALERT', arm_close_pct=33,
            arm_basis='ORIGINAL', arm_repeat=True, repeat_gap=4, arm_repeat_below_arm=True,
            dynamic_enabled=True, dynamic_policy='AUTO', dynamic_close_pct=67,
            dynamic_basis='ORIGINAL', dynamic_repeat=True, atr_start_multiplier=.6,
            atr_trail_multiplier=.9, retention_pct=81, retention_until=18))
        from ckps.rules.defaults import shared_exit_settings
        common = shared_exit_settings(original)
        saved=[]
        app.save_config=saved.append
        # Opening RULE from either direction always edits the same global form.
        for side in ('LONG', 'SHORT'):
            app.settings=Settings(exit=dict(common)).validate()
            position = Position.create('VN30F2611', side, 3, 1980, history_verified=True,
                                       exit_overrides=original,margin_per_contract=40_000_000)
            app.view = {'contract': 'VN30F2612', 'positions': [asdict(position)], 'orders': [],
                'account': {'margin_per_contract':48_000_000,'margin_reference_price':2400},
                'quotes': {'VN30F2611': asdict(Quote('VN30F2611', 2000)),
                           'VN30F2612': asdict(Quote('VN30F2612', 2400))}}
            app.render()
            app.positions_tree.selection_set(position.id)
            editor = app.position_exit()
            app.update()
            settle()
            assert isinstance(editor, OriginalRuleForms) and not hasattr(editor,'scope_selector')
            assert not hasattr(editor,'inherit_switch') and editor.primary.cget('text')=='LƯU RULE'
            expected={**common,'distance_unit':'PRICE_PERCENT','trailing_unit':'PRICE_PERCENT'}
            for key in ('sl_distance','tp_distance','repeat_gap','arm_gain','trail_gap','retention_until'):
                expected[key]=expected[key]/2400*100
            actual=editor._exits()
            from math import isclose
            assert actual.keys()==expected.keys()
            for key,value in expected.items():
                if isinstance(value,(int,float)) and not isinstance(value,bool):
                    assert isclose(actual[key],value,rel_tol=1e-12,abs_tol=1e-12), (key,actual[key],value)
                else:assert actual[key]==value, (key,actual[key],value)
            expected=actual
            assert not hasattr(editor,'price_units')
            assert editor.initial_sl._hint_icon.cget('text') == '?'
            assert editor.dynamic_settings_card.winfo_ismapped() and editor.dynamic_atr_value.winfo_ismapped()
            assert hasattr(editor,'below_arm')
            assert not editor.reentry_sl.master.winfo_ismapped()
            assert not editor.normal_repeat._viking_row.winfo_ismapped()
            assert not editor.below_arm._viking_row.winfo_ismapped()
            assert not editor.dynamic_repeat._viking_row.winfo_ismapped()
            canvas = editor.exit_body._parent_canvas
            for widget in controls(editor.protection_host):
                if not widget.winfo_ismapped():continue  # Obsolete repeat controls are deliberately hidden.
                offset = widget.winfo_rooty() - editor.exit_body.winfo_rooty()
                canvas.yview_moveto(max(0, offset-4) / editor.exit_body.winfo_height())
                settle()
                assert widget.winfo_rootx() >= canvas.winfo_rootx()-2
                assert widget.winfo_rootx()+widget.winfo_width() <= canvas.winfo_rootx()+canvas.winfo_width()+2
                assert widget.winfo_rooty() >= canvas.winfo_rooty()-2
                assert widget.winfo_rooty()+widget.winfo_height() <= canvas.winfo_rooty()+canvas.winfo_height()+2
                assert widget.winfo_rooty()+widget.winfo_height() <= editor.footer.winfo_rooty()
            canvas.yview_moveto(0)
            assert app.settings.exit == common and not sent and not saved
            # Invalid distances stay in the editor and never reach execution.
            valid_sl = editor.initial_sl.get()
            for invalid in ('0', 'nan', 'inf'):
                editor.initial_sl.delete(0, 'end')
                editor.initial_sl.insert(0, invalid)
                editor.primary.invoke()
                assert not sent and not saved and not hasattr(editor,'scope_selector')
                assert editor.initial_sl.get() == invalid
            editor.initial_sl.delete(0, 'end')
            editor.initial_sl.insert(0, valid_sl)
            # Old, absent or mismatched quotes cannot reinterpret the saved thresholds.
            for quote in ({}, asdict(Quote('VN30F2611', 2000, at=0)), asdict(Quote('VN30F2612', 2400))):
                app.view['quotes']['VN30F2611'] = quote
                assert editor._exits() == expected
            settle()
            assert editor.primary.winfo_rootx()+editor.primary.winfo_width() <= editor.winfo_rootx()+editor.winfo_width()
            editor.primary.invoke()
            assert saved[-1].exit == expected and not sent
            app.settings=saved[-1]
            # Legacy private fields cannot select a second configuration.
            app.view['positions'][0]['exit_overrides'] = {'sl_enabled':True,'sl_distance':999}
            app.position_exit()
            assert editor._exits() == expected and editor.initial_sl.cget('state')=='normal'
            assert hasattr(editor,'take_profit')
            editor.destroy();app.update()
            saved.clear()
        assert not errors, errors
    finally:
        app.close()


@pytest.mark.parametrize('scale', [1., 1.25, 1.5, 2.])
def test_shared_protection_native_form_and_legacy_global_unit_conversion(scale):
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c',
        inspect.getsource(_position_protection_scenario)+f'\n_position_protection_scenario({scale!r})'],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout+result.stderr


def test_failed_mode_start_clears_previous_snapshot_and_cannot_leave_trading_ready(monkeypatch):
    from types import SimpleNamespace
    import ckps.dashboard.window as module
    from ckps.models import Settings
    saved,rendered,reported=[],[],[]
    def unavailable(*args,**kwargs):
        raise ValueError('offline connection unavailable')
    monkeypatch.setattr(module,'Runtime',unavailable)
    monkeypatch.setattr(module,'write_settings',saved.append)
    chosen=[]
    app=SimpleNamespace(runtime=None,settings=Settings(),view={'healthy':True,'consistent':True},
        mode_requested='REAL',bot_requested=True,mode_choice=SimpleNamespace(set=chosen.append),
        status=SimpleNamespace(configure=lambda **kwargs:None),render=lambda:rendered.append(True),
        report=lambda *args,**kwargs:reported.append(args))
    module.App._start_runtime(app,Settings(mode='REAL'),{})
    assert app.settings.mode=='PAPER' and app.runtime is None and app.view=={}
    assert not app.bot_requested and app.mode_requested is None and chosen==['PAPER']
    assert rendered and reported and not saved


def test_read_only_em_milestones_follow_dynamic_arm_repeat_and_missing_data():
    from copy import deepcopy
    from ckps.dashboard.mayin.management_preview import position_milestones, ticket_milestones
    from ckps.models import ExitSettings, Position
    from ckps.rules.protection import evaluate
    rules=ExitSettings(distance_unit='POINTS', arm_enabled=True,arm_gain=20,trail_gap=5,repeat_gap=5,
        arm_close_pct=50,dynamic_enabled=True,dynamic_policy='AUTO',dynamic_close_pct=50,
        dynamic_repeat=True,atr_start_multiplier=.5,retention_pct=70,retention_until_enabled=False)
    draft_arm,draft_dyn=ticket_milestones(2000,rules,1)
    assert draft_arm.detail=='ARM L 2,020.0 / S 1,980.0'
    assert draft_dyn.detail=='START L 2,010.0 / S 1,990.0'
    assert 'CHỜ ATR' in ticket_milestones(2000,rules)[1].value
    for side,sign in [('LONG',1),('SHORT',-1)]:
        p=Position.create('VN30F1M',side,2,2000,history_verified=True)
        evaluate(p,2000+sign*12,rules,1)
        original=deepcopy(asdict(p))
        arm,dyn=position_milestones(p,rules,2000+sign*10,1)
        assert arm.value=='AUTO · CHỜ ARM'
        assert dyn.value==f'AUTO · MỐC {2000+sign*8.4:,.1f}'
        assert 'đóng 1 HĐ' in dyn.detail
        assert asdict(p)==original  # Rendering must not advance MFE or consume a repeat.
        assert 'CHỜ KHỚP' in position_milestones(p,rules,2000+sign*10,1,pending=[{'reason':'MANUAL'}])[1].value
        touched=position_milestones(p,rules,2000+sign*8,1)[1]
        assert touched.detail.startswith('Đã chạm mốc · đóng 1 HĐ')
        assert '% giá vào' in touched.detail and '1,680,000 đ/2 HĐ' in touched.detail
        assert asdict(p)==original
        p.metrics['DYN:AUTO']={'count':1,'anchor':2000+sign*8.4}
        p.quantity=1
        _,dyn=position_milestones(p,rules,2000+sign*7,1)
        assert dyn.value==f'AUTO · LẶP {2000+sign*3.4:,.1f}'
        evaluate(p,2000+sign*20,rules,1)
        arm,dyn=position_milestones(p,rules,2000+sign*17,1)
        assert arm.value==f'AUTO · MỐC {2000+sign*15:,.1f}'
        assert 'NHƯỜNG ARM' in dyn.value
        p.metrics['ARM:AUTO']={'count':1,'anchor':2000+sign*15}
        assert 'XONG' in position_milestones(p,rules,2000+sign*14,1)[0].value
        assert 'CHỜ GIÁ' in position_milestones(p,rules,None,1,ready=False)[0].value
        p.history_verified=False
        assert 'XÁC MINH' in position_milestones(p,rules,2000+sign*14,1)[0].value
    fresh=Position.create('VN30F1M','LONG',1,2000,history_verified=True)
    assert 'CHỜ ATR' in position_milestones(fresh,rules,2001,None)[1].value


def _table_review_scenario(interactive=False):
    """Populated UI fixture: no runtime, ledger, broker or notification worker."""
    from dataclasses import asdict
    import customtkinter as ctk
    from tkinter import Misc
    from ckps.dashboard.window import App
    from ckps.models import ExitSettings, Order, Position, Quote, Settings
    from ckps.rules.protection import evaluate
    ctk.set_appearance_mode('Dark')
    rules=ExitSettings(distance_unit='POINTS', sl_enabled=True,sl_distance=10,tp_enabled=True,tp_distance=40,
        arm_enabled=True,arm_gain=20,trail_gap=5,arm_close_pct=33,arm_repeat=True,repeat_gap=5,
        dynamic_enabled=True,dynamic_close_pct=50,atr_start_multiplier=.5,
        retention_pct=70,retention_until_enabled=False)
    app=App(settings=Settings(exit=asdict(rules)),start_runtime=False)
    app.title('RAT · VN30 · UI OFFLINE')
    calls,errors=[],[]
    app.send=lambda *a,**kw:calls.append((a,kw))
    app.report_callback_exception=lambda *a:errors.append(a)
    long=Position.create('VN30F1M','LONG',3,2000,managed=True,history_verified=True)
    short=Position.create('41I1GB000','SHORT',2,2000,managed=False,history_verified=True)
    evaluate(long,2020,rules,1.2);evaluate(short,1980,rules,1.2)
    pending=Order.create(long.symbol,'LONG',1,action='CLOSE',position_id=long.id,
        status='WORKING',broker_id='OFFLINE-ORDER',kind='LO',price=2025)
    profit=Position.create('VN30F1M','LONG',2,2000,closed_at=1,realized=2_000_000,fees=50_000)
    loss=Position.create('41I1GB000','SHORT',1,2000,closed_at=2,realized=-1_000_000,fees=25_000)
    app.view={'mode':'PAPER','contract':'VN30F1M','healthy':True,'consistent':True,'armed':False,
        'atr14_pct':1.2,'quotes':{p.symbol:asdict(Quote(p.symbol,2010)) for p in (long,short)},
        'account':{'nav':101_000_000,'remaining_margin':30_000_000,'margin_per_contract':40_000_000,'source':'OFFLINE · DỮ LIỆU KIỂM THỬ'},
        'positions':[asdict(long),asdict(short)],'orders':[asdict(pending)],
        'history':[asdict(profit),asdict(loss)],'events':[],
        'LONG':{'maximum':1},'SHORT':{'maximum':1},
        'analysis':{'p1':{'state':'ABOVE','text':'UPTREND','ma':1985,'price':2010},
            'p2':{'badge':'READY','price_fresh':True,'status':'EMA / RSI ĐẠT · CHỜ XÁC NHẬN',
                'xp':{'up':2,'down':1},'memory':{'cross_at':'2026-10-27T09:30:00+07:00'},
                'indicators':{'buy_ema_fast':2012.35,'buy_ema_slow':2008.12,'sell_ema_fast':2012.35,'sell_ema_slow':2008.12,'rsi':61.2,'rsi_previous':57.8}},
            'signal_history':[{'id':'signal-offline','at':1,'symbol':'VN30F1M','kind':'BUY','fast':2012.35,'slow':2008.12,'rsi':61.2,'reason':'EMA / RSI ĐẠT'}]}}
    def settle():
        app.update();app.after(180,app.quit);Misc.mainloop(app)
    try:
        settle();app.render();settle()
        app.positions_tree.selection_set(long.id);settle()
        if interactive:
            app.mainloop()
            return
        table=app.positions_tree
        assert table.parent(pending.id)==long.id
        assert table.cell(long.id,'pnl')['color']=='#22C55E'
        assert table.cell(short.id,'pnl')['color']=='#EF4444'
        assert table.cell(short.id,'side')['color']=='#EF4444'
        assert table.cell(long.id,'sl')['text']=='1,990.0'
        assert table.cell(long.id,'tp')['text']=='2,040.0'
        assert table.cell(long.id,'managed')['text']=='TẠM DỪNG'
        assert table._display==('#0','side','entry','sl','tp','managed')
        assert table._row_height==round(44*table._get_widget_scaling())
        assert table.cell(long.id,'#0')['detail']==''
        # A position enrolled for management is paused while the shared BOT is
        # off; never print ON merely because its per-position permission is set.
        app.view['armed']=True
        app.render();settle()
        assert table.cell(long.id,'managed')['text']=='CHỜ KHỚP'
        app.view['orders']=[]
        app.render();settle()
        assert table.cell(long.id,'managed')['text']=='QUẢN LÝ ON'
        app.view['consistent']=False
        app.render();settle()
        assert table.cell(long.id,'managed')['text']=='CHỜ DỮ LIỆU'
        app.view.update(armed=False,consistent=True,orders=[asdict(pending)])
        app.render();settle()
        table.body.event_generate('<Button-1>',x=30,y=round(66*table._get_widget_scaling()))
        settle()
        assert table.selection()==(pending.id,)
        assert app.action_buttons['cancel'].winfo_manager()=='pack'
        table.body.event_generate('<Down>');settle()
        assert table.selection()==(short.id,)
        app.render();settle()
        assert table.selection()==(short.id,) and short.symbol in app._preview_position_context
        history=app.history();settle()
        for page,tree in [('GIAO DỊCH',app.history_tree),('LỆNH',app.order_history_tree)]:
            history.tabs.set(page);settle()
            assert not tree.horizontal.winfo_ismapped()
            assert not tree.vertical.winfo_ismapped()
            header_values={tree.header.itemcget(item,'text') for item in tree.header.find_all() if tree.header.type(item)=='text'}
            assert 'CHIỀU' in header_values
        assert app.history_tree.cell(profit.id,'pnl')['color']=='#22C55E'
        assert app.history_tree.cell(loss.id,'pnl')['color']=='#EF4444'
        history.destroy()
        # Overflow uses the dark scrollbar, preserves identity and draws only visible rows.
        for i in range(40):
            table.insert('', 'end',iid=f'row-{i}',text=f'VN30F{i}',values=('THEO DÕI','LONG',1,'2,000','2,010','1,000,000','—','—','—','OFF','0','10'))
        settle();table.yview('moveto',1);settle()
        assert table.vertical.winfo_ismapped()
        assert table.selection()==(short.id,)
        assert len(table.body.find_all())<400
        assert not calls and not errors
    finally:
        if app.running:app.close()


def test_market_table_populated_actions_colors_history_and_virtual_scrolling():
    code=inspect.getsource(_table_review_scenario)+'\n_table_review_scenario()'
    result=subprocess.run([sys.executable,'-X','utf8','-c',code],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def _backend_app_scenario(scale):
    import socket
    import requests
    import customtkinter as ctk
    from tkinter import Misc
    from ckps.dashboard.signal_app import SignalApp
    from ckps.models import Settings
    def forbidden(*args, **kwargs):
        raise AssertionError('UI tests must not connect or trade.')
    socket.socket.connect = requests.Session.request = forbidden
    ctk.deactivate_automatic_dpi_awareness()
    ctk.set_widget_scaling(scale);ctk.set_window_scaling(scale)
    app=SignalApp(settings=Settings())
    errors=[]
    app.report_callback_exception=lambda *args:errors.append(args)
    def settle():
        app.update();app.after(100,app.quit);Misc.mainloop(app);app.update()
    try:
        settle()
        assert set(app.options)=={'movement','expiry','entry'}
        assert app.options['expiry'].get() and not app.options['entry'].get() and not app.options['movement'].get()
        assert set(app.variables)=={'key','secret','telegram_token','telegram_chat'}
        assert not hasattr(app,'bot') and not hasattr(app,'positions_tree')
        app.start();assert app.runtime is None and 'API' in app.note.cget('text')
        app.calendar();settle()
        assert app.calendar_window.form.variables['notice_time'].get()=='15:00'
        app.calendar_window.destroy();settle()
        app.geometry('820x560');settle()
        for variable in app.variables.values():
            entry=variable._viking_entry
            assert entry.winfo_rootx()+entry.winfo_width()<=app.winfo_rootx()+app.winfo_width()
            assert entry.winfo_rooty()+entry.winfo_height()<app.primary.winfo_rooty()
        assert not errors,errors
    finally:app.close()



@pytest.mark.parametrize('scale',[1.,1.5])
def test_separate_signal_console_has_no_trade_path(scale):
    code=inspect.getsource(_backend_app_scenario)+f'\n_backend_app_scenario({scale!r})'
    result=subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=Path(__file__).resolve().parents[2],
        capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
