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
    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)
    try:
        settle(500)
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
        assert not hasattr(app,'preview_atr')
        assert not app.view.get('quotes')  # Configuration Preview does not invent prices.
        assert not app.positions_tree.horizontal.winfo_ismapped()
        assert app.table_workspace.winfo_height()>=app.right.winfo_height()*.4
        assert abs(app.info_panel.winfo_rooty()+app.info_panel.winfo_height()-app.right.winfo_rooty()-app.right.winfo_height())<=2
        assert app.info_panel.winfo_height()/app.info_panel._get_widget_scaling()<=340
        assert app.action_buttons['manage'].cget('text')=='BẢO VỆ LỆNH'
        assert not hasattr(app,'preview_state_panel')
        assert 'pnl' not in app.positions_tree._display
        for name in ('LOG','PREVIEW'):
            app._select_info(name);settle()
            assert app.info_choice.get()==name
        assert not hasattr(app,'preview_health_group')
        app._mode_selected('REAL');settle(600)
        connection=app.popups['connection']
        assert app.settings.mode=='PAPER' and app.mode_choice.get()=='REAL'
        assert app.mode_requested=='REAL' and connection.tabs.get()=='DNSE'
        assert connection.otp_card.winfo_ismapped()
        for widget in widgets(connection):
            if isinstance(widget,ctk.CTkEntry) and widget.winfo_ismapped():
                assert widget.winfo_rootx()+widget.winfo_width()<=connection.winfo_rootx()+connection.winfo_width()
                assert widget.winfo_rooty()+widget.winfo_height()<=connection.footer.winfo_rooty()
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
        assert set(dialog.tabs._tab_dict)=={'E/M'}
        assert not hasattr(dialog,'phase_tabs') and not hasattr(dialog,'sell_alert_enabled')
        assert dialog._exits()==app.settings.exit
        connection=app.connection();settle(600)
        assert dialog is not connection
        assert set(connection.pages)=={'DNSE','VỐN','Telegram','LỊCH'}
        assert not any('telegram' in key for key in connection.variables)
        assert not connection.otp_card.winfo_ismapped()
        assert not hasattr(connection,'csv_button') and 'paper.price' not in connection.variables
        assert 'owner_chat' not in connection.variables and 'owner_token' not in connection.variables
        connection.select_page('VỐN');settle(600)
        assert connection.paper_capital_entry.winfo_ismapped()
        connection.variables['paper_balance'].set('250,000,000')
        connection.apply_capital()
        assert sent[-1][0]==('paper_capital',250_000_000)
        sent.clear()
        for page in ('E/M','VỐN'):
            dialog.select(page);settle()
            for w in widgets(dialog):
                if isinstance(w,ctk.CTkEntry) and w.winfo_ismapped():
                    assert w.winfo_rootx()+w.winfo_width()<=dialog.winfo_rootx()+dialog.winfo_width()
        saved,sent=[],[]
        app.save_config=saved.append
        app.send=lambda *a,**kw:sent.append((a,kw))
        dialog.save()
        assert len(saved)==1 and saved[0].signals==SignalSettings().to_dict()
        assert not any(name[0] in {'open_manual','close_position'} for name,kw in sent)
        popup_size=(connection.winfo_width(),connection.winfo_height())
        assert popup_size==(dialog.winfo_width(),dialog.winfo_height())
        for name in connection.pages:
            connection.select_page(name);settle(600)
            assert (connection.winfo_width(),connection.winfo_height())==popup_size
            for widget in widgets(connection):
                if widget is not connection.primary and isinstance(widget,(ctk.CTkEntry,ctk.CTkSwitch,ctk.CTkButton)) and widget.winfo_ismapped():
                    bottom=connection.pages[name].winfo_rooty()+connection.pages[name].winfo_height()-4
                    assert widget.winfo_rooty()+widget.winfo_height()<=min(bottom,connection.footer.winfo_rooty()), (name,widget,widget.winfo_rooty(),widget.winfo_height(),bottom,connection.footer.winfo_rooty(),connection.winfo_height(),connection._get_window_scaling())
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
        rules=ExitSettings(arm_enabled=True,arm_gain=20,trail_gap=5,arm_repeat=True,repeat_gap=5,
            dynamic_enabled=True,dynamic_policy='AUTO',dynamic_close_pct=50,dynamic_repeat=True,
            atr_start_multiplier=.5,retention_pct=70,retention_until_enabled=False)
        position=Position.create('VN30F1M','LONG',2,2000,history_verified=True,exit_overrides=asdict(rules))
        evaluate(position,2012,rules,1)
        position.metrics['DYN:AUTO']={'count':1,'anchor':2008.4}
        app.view.update(positions=[asdict(position)],orders=[],healthy=True,consistent=True,
            contract='VN30F1M',atr14_pct=1,quotes={'VN30F1M':asdict(Quote('VN30F1M',2007))})
        app.render();app.positions_tree.selection_set(position.id)
        app._refresh_ticket_preview();settle()
        assert 'LẶP 2,003.4' in app.preview_exit_value.cget('text')
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
            assert getattr(widget,'_viking_fit_font_size',font[1])>=14, widget.cget('text')
        for label in (app.preview_normal_value,app.preview_normal_detail,app.preview_exit_value,app.preview_exit_detail):
            assert label.winfo_rooty()+label.winfo_height()<=label.master.winfo_rooty()+label.master.winfo_height()
            assert NativeFontMetrics(label,label._label.cget('font')).measure(label.cget('text'))<=label.winfo_width(), (label.cget('text'),label.winfo_width(),label._label.cget('font'))
        app.geometry('1080x700');settle(500)
        assert not app.positions_tree.horizontal.winfo_ismapped()
        assert app.preview_management.winfo_ismapped() and app.preview_exit_value.winfo_ismapped()
        assert app.table_workspace.winfo_height()>=app.right.winfo_height()*.35
        assert abs(app.info_panel.winfo_rooty()+app.info_panel.winfo_height()-app.right.winfo_rooty()-app.right.winfo_height())<=2
        for widget,font in app._preview_fit_labels:
            if not widget.winfo_ismapped():continue
            assert widget.winfo_rooty()+widget.winfo_height()<=app.info_panel.winfo_rooty()+app.info_panel.winfo_height(), (widget.cget('text'),widget.winfo_rooty(),widget.winfo_height(),app.info_panel.winfo_rooty()+app.info_panel.winfo_height(),app.info_panel.cget('height'),app.preview_data.winfo_reqheight())
            assert widget.winfo_rooty()+widget.winfo_height()<=widget.master.winfo_rooty()+widget.master.winfo_height(), widget.cget('text')
            assert NativeFontMetrics(widget,widget._label.cget('font')).measure(widget.cget('text'))<=widget.winfo_width(), widget.cget('text')
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
        assert not hasattr(app,'preview_atr')
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
        app.position_exit()
        app.update()
        assert not app.info_panel.winfo_ismapped()
        for page in ("SL / TP", "ARM", "DYNAMIC"):
            app.position_editor.tabs.set(page)
            app.after(150, app.quit)
            app.mainloop()
            def controls(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from controls(child)
            for widget in controls(app.position_editor):
                if getattr(widget, "_compact_control", False):
                    if isinstance(widget, ctk.CTkSegmentedButton):
                        assert all(child.cget("state") == "disabled" for child in widget.winfo_children() if isinstance(child, ctk.CTkButton))
                    else:
                        assert widget.cget("state") == "disabled"
                if getattr(widget, "_compact_control", False) and widget.winfo_ismapped():
                    assert widget.winfo_rooty() + widget.winfo_height() < app.editor_footer.winfo_rooty()
        app.inherit_exit.set(False)
        app.position_editor.variables["sl_enabled"].set(True)
        app.position_editor.variables["sl_distance"].set("10")
        app.editor_save.invoke()
        app.update()
        assert app.info_panel.winfo_ismapped()
        assert sent[-1][0][0] == "configure_position" and sent[-1][0][2]["sl_distance"] == 10
        app.close_position()
        assert app.editor_variables["qty"].get() == "1"
        before = len(sent)
        app.editor_save.invoke()
        assert len(sent) == before
        app.confirm_primary.invoke()
        assert sent[-1][0] == ("close_position", position.id, 1)
        assert sent[-1][1]["kind"] == "MOK"
        assert not app.popups
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


def _rule_adapter_scenario():
    """Renamed MayinTien fields must preserve CKPS exit policies and units."""
    from ckps.dashboard.window import App
    from dataclasses import asdict
    from ckps.models import Settings, ExitSettings
    from ckps.rules.signal_settings import SignalSettings
    exits=ExitSettings(sl_enabled=True,sl_distance=8.5,tp_enabled=True,tp_distance=19,
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
    settings=Settings(exit=asdict(exits),signals=signals.to_dict(),capital_limit=80_000_000,
        max_contracts=3,risk_limit=5_000_000,risk_nav_pct=4,estimated_fee_per_contract=25000).validate()
    app=App(settings=settings,start_runtime=False)
    try:
        app.update()
        window=app.settings_dialog('E/M')
        app.update()
        assert not hasattr(window,'indicator_exit_policy') and not hasattr(window,'rsi_period')
        assert window._exits()==asdict(exits)
        saved,sent=[],[]
        app.save_config=saved.append
        app.send=lambda *a,**kw:sent.append((a,kw))
        window.price_units.set('% GIÁ')
        window._units_changed('% GIÁ')
        assert window.price_units.get()=='ĐIỂM' and 'Cần giá' in window.status.cget('text')
        from ckps.models import Quote
        app.view.update(contract='VN30F1M',quotes={'VN30F1M':asdict(Quote('VN30F1M',2000))})
        window.price_units.set('% GIÁ')
        window._units_changed('% GIÁ')
        window.save()
        assert len(saved)==1
        expected={**asdict(exits),'distance_unit':'PERCENT'}
        for key in ('sl_distance','tp_distance','repeat_gap','arm_gain','trail_gap','retention_until'):
            expected[key]=getattr(exits,key)/20
        assert saved[0].exit==expected
        assert saved[0].capital_limit==settings.capital_limit and saved[0].max_contracts==3
        assert saved[0].signals==signals.to_dict()  # Hidden backend settings are not overwritten by MAIN.
        assert not sent  # Rule/indicator controls cannot submit or close a trade.
        window.price_units.set('ĐIỂM');window._units_changed('ĐIỂM')
        assert window._exits()==asdict(exits)
        app.view['quotes']['VN30F1M']['at']=0
        window.price_units.set('% GIÁ');window._units_changed('% GIÁ')
        assert window.price_units.get()=='ĐIỂM' and window._exits()==asdict(exits)
    finally:
        app.close()


def test_original_rule_forms_roundtrip_ckps_protection_and_private_signals():
    # Windows Store Python cannot reliably create a second Tk interpreter after
    # destroying the first; isolate GUI sessions, like the DPI scenarios above.
    result=subprocess.run([sys.executable,'-X','utf8','-c',
        inspect.getsource(_rule_adapter_scenario)+'\n_rule_adapter_scenario()'],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


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
    rules=ExitSettings(arm_enabled=True,arm_gain=20,trail_gap=5,repeat_gap=5,
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
        assert touched.detail=='Đã chạm mốc · đóng 1 HĐ'
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
    rules=ExitSettings(sl_enabled=True,sl_distance=10,tp_enabled=True,tp_distance=40,
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


def _split_app_scenario(kind,scale):
    import socket
    import requests
    import customtkinter as ctk
    from pathlib import Path
    from tkinter import Misc
    from ckps.config import runtime_root
    def forbidden(*args,**kwargs):raise AssertionError('UI review cannot use a network or start trading.')
    requests.Session.request=forbidden
    socket.socket.connect=forbidden
    if scale is not None:
        ctk.deactivate_automatic_dpi_awareness()
        ctk.set_widget_scaling(scale);ctk.set_window_scaling(scale)
    from ckps.dashboard.mayin.ui_compat import NativeFontMetrics
    errors=[]
    if kind=='demo':
        import ckps.dashboard.window as window
        window.Runtime=forbidden
        from ckps.dashboard.demo import DemoApp
        app=DemoApp()
    else:
        from ckps.dashboard.signal_app import SignalApp
        from ckps.models import Settings
        app=SignalApp(settings=Settings())
    app.report_callback_exception=lambda *args:errors.append(args)
    def settle():
        app.update();app.after(250,app.quit);Misc.mainloop(app)
    try:
        settle()
        if kind=='demo':
            for stage in ('DYNAMIC','LẶP','TSL / ARM'):
                app.show_sample(stage);settle()
                assert app.lbl_equity_title.cget('text').startswith('KÝ QUỸ')
                assert app.lbl_equity.cget('text')=='100,000,000 đ'
                assert app.lbl_cash.cget('text')=='Tổng tiền: 100,000,000 đ'
                assert app.lbl_cash.winfo_rooty()>app.lbl_equity.winfo_rooty()
                assert app.runtime is None and not app.view['armed']
                assert not hasattr(app,'demo_selector')
                assert len(app.view['positions'])==1 and not app.view['orders']
                assert not hasattr(app,'preview_rule_ema')
                for button in app.open_buttons:assert button.cget('state')=='disabled'
                assert app.bot.cget('state')=='normal'
                for button in (app.rule_button,app.connection_button):assert button.cget('state')=='normal'
                assert app.positions_tree.cell('DEMO-LONG','sl')['text']=='1,990.0'
                assert app.positions_tree.cell('DEMO-LONG','tp')['text']=='2,040.0'
                assert ('NHƯỜNG ARM' in app.preview_exit_value.cget('text'))==(stage=='TSL / ARM')
            app.show_sample('LẶP');settle()
            app.bot.invoke();settle()
            assert app.view['armed'] and app.positions_tree.cell('DEMO-LONG','managed')['text']=='QUẢN LÝ ON'
            assert app.preview_entry_value.cget('text')=='LONG · 2,007.0'
            assert app.preview_trend_value.cget('text')=='UP'
            assert app.market_context_label.cget('text')=='CHỈ THAM KHẢO · MẪU'
            app.bot.invoke();settle()
            assert not app.view['armed'] and app.runtime is None
            assert app.positions_tree.cell('DEMO-LONG','managed')['text']=='TẠM DỪNG'
            app.positions_tree.selection_set(());settle()
            assert app.positions_tree.selection()==('DEMO-LONG',)
            assert 'Còn 1/2 HĐ' in app._preview_position_context
            assert not hasattr(app,'preview_status_badge') and not hasattr(app,'preview_sl_value')
            assert app.info_panel.winfo_height()/app.info_panel._get_widget_scaling()<=340
            assert app.action_buttons['manage'].cget('text')=='BẢO VỆ LỆNH'
            app.preview_em_exit._label.event_generate('<Button-1>');settle()
            detail=app.preview_em_exit._hover_hint.popup
            assert detail and detail.winfo_ismapped()
            assert 'Giữ 70% lãi' in detail.body.get('1.0','end')
            assert detail.cget('highlightbackground')=='#60A5FA'
            app.preview_em_exit._label.event_generate('<Button-1>');settle()
            assert app.preview_em_exit._hover_hint.popup is None
            # Click the actual MAIN buttons, not just the popup constructors.
            app.rule_button.invoke();settle()
            rule=app.popups['rule']
            assert rule.winfo_width()/rule._get_window_scaling()<=781
            assert rule.winfo_height()/rule._get_window_scaling()<=621
            assert rule.winfo_ismapped() and rule.tabs.get()=='E/M'
            assert set(rule.tabs._tab_dict)=={'E/M'}
            if scale is None:
                assert abs(rule.winfo_rootx()+rule.winfo_width()/2-app.winfo_rootx()-app.winfo_width()/2)<100
                assert abs(rule.winfo_rooty()+rule.winfo_height()/2-app.winfo_rooty()-app.winfo_height()/2)<100
            def visible_entries(parent):
                for child in parent.winfo_children():
                    if isinstance(child,ctk.CTkEntry) and child.winfo_ismapped():yield child
                    yield from visible_entries(child)
            canvas=rule.exit_body._parent_canvas
            entries=list(visible_entries(rule))
            for entry in entries:
                # At high DPI the full native E/M form needs scrolling. Every
                # control must be reachable inside the viewport and footer.
                offset=entry.winfo_rooty()-rule.exit_body.winfo_rooty()
                canvas.yview_moveto(max(0,offset-4)/rule.exit_body.winfo_height())
                settle()
                assert entry.winfo_rooty()>=canvas.winfo_rooty()-2,entry.get()
                assert entry.winfo_rooty()+entry.winfo_height()<=rule.footer.winfo_rooty(),entry.get()
                assert entry.winfo_rooty()+entry.winfo_height()<=canvas.winfo_rooty()+canvas.winfo_height()+2,entry.get()
            canvas.yview_moveto(0);settle()
            assert rule.dynamic_settings_card.winfo_ismapped()
            assert rule.below_arm_switch.winfo_ismapped()
            assert rule.initial_sl._hint_icon.cget('text')=='?'
            icon=rule.initial_sl._hint_icon
            icon._label.event_generate('<Enter>')
            app.after(650,app.quit);Misc.mainloop(app);settle()
            hint=icon._hover_hint.popup
            assert hint and hint.winfo_ismapped()
            assert 'cắt lỗ' in hint.body.get('1.0','end')
            assert hint.winfo_rootx()>=rule.winfo_rootx()
            assert hint.winfo_rootx()+hint.winfo_width()<=rule.winfo_rootx()+rule.winfo_width()
            assert hint.winfo_rooty()+hint.winfo_height()<=rule.winfo_rooty()+rule.winfo_height()
            icon._hover_hint._hide()
            rule.initial_sl.delete(0,'end');rule.initial_sl.insert(0,'12')
            rule.save();settle()
            assert app.settings.exit['sl_distance']==12
            assert app.positions_tree.cell('DEMO-LONG','sl')['text']=='1,988.0'
            assert 'mẫu' in rule.status.cget('text')
            rule.destroy();settle()
            app.connection_button.invoke();settle()
            connection=app.popups['connection']
            assert connection.winfo_ismapped()
            connection.select_page('VỐN');settle()
            assert connection.variables['capital.max_contracts']._viking_entry.winfo_ismapped()
            connection.variables['capital.max_contracts'].set('3')
            connection.save();assert app.settings.max_contracts==3
            assert app.settings.exit['sl_distance']==12
            connection.variables['capital.risk_limit'].set('-1')
            connection.save();assert app.settings.risk_limit==0
            connection.variables['capital.risk_limit'].set('0')
            opened=[];app.open_signal_backend=lambda:opened.append(True)
            connection.select_page('Telegram');settle()
            connection.primary.invoke();assert opened==[True]
            connection.select_page('DNSE');settle()
            connection.select_page('LỊCH');settle()
            connection.calendar_form.variables['manual_closed_dates'].set('2026-11-19')
            connection.save()
            assert app._demo_calendar.manual_closed_dates==['2026-11-19']
            assert not runtime_root().exists()
            connection.select_page('DNSE');settle()
            assert {'connection.key','connection.secret','connection.account','connection.loan'}<=set(connection.variables)
            connection.variables['connection.key'].set('offline-key')
            connection.variables['connection.secret'].set('offline-secret')
            connection.connect();assert 'Bản mẫu' in connection.note.cget('text')
            assert app.runtime is None and not app.switch_pending
            connection.destroy();settle()
            app._mode_selected('REAL');settle()
            connection=app.popups['connection']
            assert connection.otp_card.winfo_ismapped() and app.mode_requested=='REAL'
            connection.variables['connection.account'].set('123')
            connection.connect();assert app.runtime is None and not app.switch_pending
            connection.destroy();settle()
            assert app.mode_requested is None and app.settings.mode=='PAPER'
            assert not runtime_root().exists()  # No settings, credentials or ledger was saved.
            app.geometry('1080x700');settle()
            for widget,font in app._preview_fit_labels:
                if not widget.winfo_ismapped() or not widget.cget('text'):continue
                assert widget.winfo_rooty()+widget.winfo_height()<=app.info_panel.winfo_rooty()+app.info_panel.winfo_height(),widget.cget('text')
                assert NativeFontMetrics(widget,widget._label.cget('font')).measure(widget.cget('text'))<=widget.winfo_width(),widget.cget('text')
        else:
            assert set(app.options)=={'movement','expiry','entry'}
            assert app.options['expiry'].get() and not app.options['entry'].get() and not app.options['movement'].get()
            assert set(app.variables)=={'key','secret','telegram_token','telegram_chat'}
            assert not hasattr(app,'bot') and not hasattr(app,'positions_tree')
            app.start();assert app.runtime is None and 'API' in app.note.cget('text')
            app.calendar();settle()
            calendar_window=app.calendar_window
            assert calendar_window.form.variables['notice_time'].get()=='15:00'
            assert calendar_window.form.variables['notice_days'].get()=='1'
            calendar_window.destroy();settle()
            app.geometry('820x560');settle()
            for variable in app.variables.values():
                entry=variable._viking_entry
                assert entry.winfo_rootx()+entry.winfo_width()<=app.winfo_rootx()+app.winfo_width()
                assert entry.winfo_rooty()+entry.winfo_height()<app.primary.winfo_rooty()
        assert not errors,errors
    finally:app.close()


@pytest.mark.parametrize('kind,scale',[('demo',None),('demo',1.),('demo',1.5),('demo',2.),('backend',1.),('backend',1.5)])
def test_separate_signal_console_and_long_demo_have_no_trade_or_network_path(kind,scale):
    code=inspect.getsource(_split_app_scenario)+f'\n_split_app_scenario({kind!r},{scale!r})'
    result=subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=Path(__file__).resolve().parents[2],
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
