"""Unchanged snapshots must not repaint cards or replay a UI update burst."""
import inspect
from pathlib import Path
import queue
import subprocess
import sys
from types import SimpleNamespace

from ckps.dashboard.window import App
from ckps.models import Settings


def test_snapshot_burst_renders_only_the_latest_view():
    events = queue.Queue()
    for capital in (100, 200, 300):
        events.put(('snapshot', {'mode': 'PAPER', 'account': {'paper_capital': capital}}))
    rendered = []
    app = SimpleNamespace(preview_analysis_enabled=False, closing=False,
        runtime=SimpleNamespace(events=events), settings=Settings(),
        _drain_mode_probe=lambda: None, after=lambda *args: None)
    app._drain = lambda: None
    app.render = lambda: rendered.append(app.view)
    App._drain(app)
    assert len(rendered) == 1
    assert rendered[0]['account']['paper_capital'] == app.settings.paper_balance == 300


def _stable_refresh_scenario():
    from dataclasses import asdict
    import socket
    import time
    import requests
    import customtkinter as ctk
    from tkinter import Misc
    from ckps.dashboard.window import App
    from ckps.models import Quote, Settings

    def forbidden(*args, **kwargs):
        raise AssertionError('Offline UI check must not connect or trade.')
    requests.Session.request = socket.socket.connect = forbidden
    ctk.deactivate_automatic_dpi_awareness()
    app = App(settings=Settings(), start_runtime=False)
    app.withdraw()

    def settle():
        app.update()
        app.after(100, app.quit)
        Misc.mainloop(app)
        app.update()

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    try:
        now = time.time()
        app.view = {'mode': 'PAPER', 'contract': 'VN30F1M', 'healthy': True, 'consistent': True,
            'quotes': {'VN30F1M': asdict(Quote('VN30F1M', 2007, at=now))},
            'market_context': {'state': 'ABOVE', 'ma': 2000, 'observed_at': now,
                               'entry': {'state': 'WAIT'}},
            'market_connection': {'configured': True},
            'account': {'collateral_total': 100_000_000, 'total_money': 100_000_000,
                'margin_per_contract': 40_000_000, 'remaining_margin': 100_000_000,
                'used_margin': 0, 'pending_margin': 0, 'qmax_long': 2, 'qmax_short': 2}}
        app.render()
        settle()
        draws = []
        for widget in widgets(app):
            if hasattr(widget, '_draw'):
                draw = widget._draw
                def tracked(*args, _draw=draw, _widget=widget, **kwargs):
                    draws.append(str(_widget))
                    return _draw(*args, **kwargs)
                widget._draw = tracked
        for _ in range(3):
            app.render()
            settle()
        assert not draws, f'Unchanged data triggered {len(draws)} widget redraws: {draws[:8]}'
        assert app.preview_trend_value.cget('text') == 'UP'
        assert app.preview_entry_value.cget('text') == 'CHƯA CÓ ĐIỂM'

        # Real changes must still update immediately, including stale-data gates.
        app.view['quotes']['VN30F1M']['last'] = 1990
        app.view['market_context']['state'] = 'BELOW'
        app.render()
        assert app.preview_trend_value.cget('text') == 'DOWN'
        assert app.lbl_price.cget('text') == '1,990.0'
        app.view['quotes']['VN30F1M']['at'] = now - 30
        app.render()
        assert app.preview_trend_value.cget('text') == 'CHỜ'
        assert 'Giá cũ' in app.preview_entry_detail.cget('text')
        assert app.execute_button.cget('state') == 'disabled'
        assert 'GIÁ CŨ' in app.order_gate_label.cget('text')
        assert app.order_gate_label.winfo_manager()=='pack'
        app.view['quotes']['VN30F1M']['at']=time.time()
        app.render()
        assert not app.order_gate_label.winfo_manager() and app.execute_button.cget('state')=='normal'
        assert draws
        # Outside-session intent uses the same confirmation and table, with no POST.
        from ckps.models import Order
        app.view['contract']='41I1GB000'
        app.view['quotes']={'41I1GB000':asdict(Quote('41I1GB000',1990,at=now-30,source='DNSE'))}
        app.view['entry_queue']={'date':'2026-11-03'}
        app.render()
        assert app.execute_button.cget('text')=='LƯU LONG' and app.execute_button.cget('state')=='normal'
        sent=[];app.send=lambda *args,**kwargs:sent.append(args)
        app.open_order('LONG')
        assert app.confirmation.winfo_manager()=='grid' and not sent
        app.confirm_primary.invoke()
        assert len(sent)==1 and sent[0][0]=='schedule_manual' and sent[0][-2:]==('41I1GB000','2026-11-03')
        order=Order.create('41I1GB000','LONG',2,price=2007,status='SCHEDULED',scheduled_for='2026-11-03')
        app.view['orders']=[asdict(order)]
        app.render();app.positions_tree.selection_set(order.id);app._sync_selection()
        assert app.positions_tree.cell(order.id,'managed')['text']=='CHỜ PHIÊN'
        assert app.action_buttons['cancel'].cget('state')=='normal'
    finally:
        app.close()


def test_stable_snapshot_does_not_redraw_but_price_and_stale_state_still_update():
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c',
        inspect.getsource(_stable_refresh_scenario)+'\n_stable_refresh_scenario()'],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
