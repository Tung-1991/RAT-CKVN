"""Consolidated settings never cross the trading/backend permission boundary."""
from dataclasses import asdict
from io import StringIO
import inspect
import json
from pathlib import Path
import queue
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ckps.models import Settings
from ckps.services.signal_process import SignalProcess, public_settings, serve


def test_headless_signal_pipe_has_only_signal_settings_and_no_trading_commands():
    seen, commands = [], []
    class Runtime:
        def __init__(self, settings, credentials):
            seen.append((settings, credentials))
            self.events = queue.Queue()
        def command(self, *args):
            commands.append(args)
        def close(self):
            self.events.put(('closed', None))
    raw = {**asdict(Settings(account_no='123', mode='REAL')), 'unknown': 'ignored'}
    source = StringIO('\n'.join(json.dumps(row) for row in (
        {'command': 'start', 'settings': raw, 'credentials': {'key': 'k', 'secret': 's', 'telegram_token': 't', 'otp': 'private'}},
        {'command': 'open_manual', 'side': 'LONG'},
        {'command': 'settings', 'settings': raw, 'token': 'new-token'},
        {'command': 'stop'})))
    output = StringIO()
    assert serve(source, output, runtime_factory=Runtime) == 0
    assert len(seen) == 1 and seen[0][0].mode == 'PAPER' and seen[0][0].account_no == ''
    assert seen[0][1] == {'key': 'k', 'secret': 's', 'telegram_token': 't'}
    assert len(commands) == 1 and commands[0][0] == 'settings'
    assert 'account_no' not in commands[0][1] and 'exit' not in commands[0][1]
    assert 'chỉ nhận cấu hình' in output.getvalue() and 'Đã dừng' in output.getvalue()
    assert 'private' not in output.getvalue() and 'new-token' not in output.getvalue()


def test_pipe_controlled_runtime_updates_memory_without_rewriting_ui_settings(system, monkeypatch):
    from ckps.rules.signal_settings import SignalSettings
    from ckps.services.signal_runtime import SignalRuntime
    def forbidden(*args, **kwargs):
        raise AssertionError('Only the main settings UI may persist this file.')
    monkeypatch.setattr('ckps.services.signal_runtime.write_signal_settings', forbidden)
    runtime = SignalRuntime.__new__(SignalRuntime)
    runtime.store = system[2]
    runtime.persist_settings = False
    runtime.owner_enabled, runtime.owner_chat, runtime.owner_token = False, '', ''
    settings = Settings(signals=SignalSettings(buy_ema_fast=5, buy_ema_slow=13).to_dict())
    runtime._configure(asdict(settings), '')
    assert runtime.settings.signals['buy_ema_fast'] == 5


def test_signal_process_keeps_credentials_out_of_argv_and_sends_stop_without_blocking(monkeypatch):
    class Pipe(StringIO):
        def close(self):
            pass
    calls = []
    process = SimpleNamespace(stdin=Pipe(), stdout=Pipe('{"status":"Ready"}\n'), poll=lambda: None)
    def launch(command, **kwargs):
        calls.append((command, kwargs))
        return process
    monkeypatch.setattr('ckps.services.signal_process.subprocess.Popen', launch)
    session = SignalProcess(Settings(account_no='123'), {'key': 'api-key', 'secret': 'api-secret', 'telegram_token': 'tg-token', 'otp': 'private'})
    session.configure(Settings(), 'replacement')
    session.close()
    session.writer.join(2)
    session.reader.join(2)
    assert not session.writer.is_alive() and not session.reader.is_alive()
    assert calls[0][0][-3:] == ['-m', 'ckps.signal_app', '--headless']
    assert not any(secret in str(calls) for secret in ('api-key', 'api-secret', 'tg-token', 'private'))
    messages = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert [m['command'] for m in messages] == ['start', 'settings', 'stop']
    assert 'otp' not in messages[0]['credentials'] and 'account_no' not in messages[0]['settings']
    assert set(messages[0]['settings']) == set(public_settings(Settings()))


def test_entry_channel_off_keeps_signal_tracking_and_does_not_replay_when_enabled(system):
    from ckps.rules.signal_settings import SignalSettings
    from ckps.services.signal_runtime import SignalRuntime
    engine, broker, store = system
    engine.settings.signals = SignalSettings(buy_alert_enabled=True, sell_alert_enabled=True).to_dict()
    engine.settings.entry_notifications = False
    state = {'buy_alert': True, 'exit_alert': True, 'indicators': {
        'buy_ema_fast': 2001, 'buy_ema_slow': 2000, 'sell_ema_fast': 1999, 'sell_ema_slow': 2000, 'rsi': 51}}
    runtime = SignalRuntime.__new__(SignalRuntime)
    runtime.settings, runtime.latest, runtime.store = engine.settings, engine.latest, store
    runtime.owner_enabled, runtime.owner_token, runtime.owner_chat = True, 'offline-token', 'offline-chat'
    runtime.owner_state, runtime.owner_last = None, 0
    runtime.analysis = SimpleNamespace(snapshot=lambda: {'contract': engine.latest.contract, 'p2': state})
    runtime._owner_telemetry()
    assert not store.db.execute('SELECT id FROM outbox').fetchall()
    assert store.get('notification', 'condition:'+engine.latest.contract)['state'] == [True, True]
    engine.settings.entry_notifications = True
    runtime._owner_telemetry()
    assert not store.db.execute('SELECT id FROM outbox').fetchall()
    state.update(buy_alert=False, exit_alert=False)
    runtime._owner_telemetry()
    state.update(buy_alert=True, exit_alert=True)
    runtime._owner_telemetry()
    assert store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0] == 2
    assert not store.orders() and not engine.enabled.is_set()


def test_headless_backend_starts_and_stops_offline_in_a_real_child_process():
    from ckps.config import runtime_root
    code = '''
import socket
import sys
import requests
def forbidden(*args, **kwargs):
    raise AssertionError('Offline child must not contact DNSE or Telegram.')
socket.socket.connect = requests.Session.request = forbidden
from ckps.services.signal_process import serve
raise SystemExit(serve(sys.stdin, sys.stdout))
'''
    messages = '\n'.join(json.dumps(value) for value in (
        {'command': 'start', 'settings': public_settings(Settings()), 'credentials': {}},
        {'command': 'stop'}))+'\n'
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], input=messages,
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, encoding='utf-8', timeout=12)
    assert result.returncode == 0, result.stdout+result.stderr
    statuses = [json.loads(line)['status'] for line in result.stdout.splitlines()]
    assert statuses[0].startswith('Đang phân tích') and statuses[-1] == 'Đã dừng backend'
    assert not (runtime_root()/'accounts').exists()


def _consolidated_scenario(scale):
    import socket
    import requests
    import customtkinter as ctk
    from tkinter import Misc
    from ckps.config import runtime_root
    from ckps.dashboard.demo import DemoApp
    from ckps.dashboard.settings_state import signal_settings
    def forbidden(*args, **kwargs):
        raise AssertionError('UI verification cannot connect or trade.')
    socket.socket.connect = requests.Session.request = forbidden
    ctk.deactivate_automatic_dpi_awareness()
    ctk.set_widget_scaling(scale)
    ctk.set_window_scaling(scale)
    app = DemoApp()
    errors = []
    app.report_callback_exception = lambda *args: errors.append(args)
    def settle():
        app.update()
        app.after(100, app.quit)
        Misc.mainloop(app)
        app.update()
    def controls(parent):
        for child in parent.winfo_children():
            if isinstance(child, (ctk.CTkEntry, ctk.CTkCheckBox, ctk.CTkSwitch, ctk.CTkButton, ctk.CTkSegmentedButton, ctk.CTkOptionMenu)):
                yield child
            else:
                yield from controls(child)
    def reachable(body, footer):
        canvas = body._parent_canvas
        for widget in controls(body):
            if not widget.winfo_ismapped():continue
            offset = widget.winfo_rooty()-body.winfo_rooty()
            canvas.yview_moveto(max(0, offset-4)/body.winfo_height())
            settle()
            assert canvas.winfo_rootx()-2 <= widget.winfo_rootx()
            assert widget.winfo_rootx()+widget.winfo_width() <= canvas.winfo_rootx()+canvas.winfo_width()+2, str(widget)
            assert canvas.winfo_rooty()-2 <= widget.winfo_rooty()
            assert widget.winfo_rooty()+widget.winfo_height() <= min(footer.winfo_rooty(), canvas.winfo_rooty()+canvas.winfo_height()+2), str(widget)
        canvas.yview_moveto(0)
    try:
        settle()
        assert not {'adopt', 'manage'} & set(app.action_buttons)
        rule = app.settings_dialog()
        settle()
        assert set(rule.tabs._tab_dict) == {'E/M', 'TÍN HIỆU'}
        if scale == 1.:
            canvas = rule.exit_body._parent_canvas
            assert rule.below_arm_switch.winfo_rooty()+rule.below_arm_switch.winfo_height() <= canvas.winfo_rooty()+canvas.winfo_height()
        common = dict(app.settings.exit)
        rule.select_scope('VỊ THẾ')
        settle()
        if scale == 1.:
            canvas = rule.exit_body._parent_canvas
            assert rule.below_arm_switch.winfo_rooty()+rule.below_arm_switch.winfo_height() <= canvas.winfo_rooty()+canvas.winfo_height()
        rule.request_management()
        assert rule.confirmation.winfo_manager() == 'grid' and app.view['positions'][0]['managed']
        rule.confirm_management()
        assert not app.view['positions'][0]['managed'] and app.runtime is None
        rule.inherit_exit.set(False)
        rule._inherit_changed()
        rule.initial_sl.delete(0, 'end')
        rule.initial_sl.insert(0, '12')
        rule.request_management()
        assert not rule.confirmation.winfo_manager() and 'Lưu E/M' in rule.status.cget('text')
        rule.save()
        rule.request_management()
        app.view['armed'] = True
        rule.confirm_management()
        assert not app.view['positions'][0]['managed'] and 'xác nhận lại' in rule.status.cget('text')
        app.view['armed'] = False
        rule.request_management()
        rule.confirm_management()
        assert app.view['positions'][0]['managed']
        rule.inherit_exit.set(True)
        rule._inherit_changed()
        assert float(rule.initial_sl.get()) == common['sl_distance']
        assert rule.initial_sl.cget('state') == 'disabled'
        rule.save()
        rule.select('TÍN HIỆU')
        settle()
        reachable(rule.signal_form.body, rule.footer)
        variables = rule.signal_form.variables
        variables['buy_ema_fast'].set('5')
        variables['buy_ema_slow'].set('13')
        variables['sell_ema_fast'].set('7')
        variables['sell_ema_slow'].set('21')
        variables['rsi_period'].set('17')
        variables['buy_confirmation_enabled'].set(True)
        variables['buy_confirmation_minutes'].set('8')
        variables['buy_ema_cross_mode'].set('SESSIONS')
        variables['buy_alert_enabled'].set(True)
        variables['sell_alert_enabled'].set(False)
        variables['market.fast_points'].set('6')
        rule.save()
        saved = signal_settings(app)
        assert saved.signals['buy_ema_fast'] == 5 and saved.signals['sell_ema_slow'] == 21
        assert saved.signals['rsi_period'] == 17 and saved.signals['buy_confirmation_minutes'] == 8
        assert saved.signals['buy_alert_enabled'] and not saved.signals['sell_alert_enabled']
        assert saved.market_alerts['fast_points'] == 6 and app.settings.exit == common
        variables['buy_ema_fast'].set('30')
        rule.save()
        assert signal_settings(app).signals['buy_ema_fast'] == 5
        connection = app.connection()
        settle()
        size = (rule.winfo_width(), rule.winfo_height())
        assert size == (connection.winfo_width(), connection.winfo_height())
        assert set(connection.pages) == {'DNSE / VỐN', 'TELEGRAM / LỊCH'}
        for page in connection.pages:
            connection.select_page(page)
            settle()
            assert size == (connection.winfo_width(), connection.winfo_height())
        reachable(connection.notification_body, connection.footer)
        connection.calendar_form.schedule_button.invoke();settle()
        reachable(connection.notification_body, connection.footer)
        connection.select_page('DNSE');settle()
        reachable(connection.connection_body, connection.footer)
        assert connection.otp_card.winfo_ismapped()
        assert connection.otp_entry.cget('state') == 'disabled'
        assert 'capital.estimated_fee_per_contract' not in connection.variables
        assert not hasattr(connection.variables['connection.account'],'_viking_entry')
        connection.variables['connection.key'].set('offline-key')
        connection.variables['connection.secret'].set('offline-secret')
        connection.key_visibility.invoke()
        assert connection.variables['connection.secret']._viking_entry.cget('show') == ''
        connection.key_visibility.invoke()
        assert connection.variables['connection.secret']._viking_entry.cget('show') == '•'
        connection.read_api_button.invoke();settle()
        assert connection.variables['connection.account'].get() == '1234567890'
        assert connection.variables['connection.loan'].get() == '2279'
        assert '2,000' in connection.profile_fee.cget('text')
        assert connection.account_menu.cget('state') == 'disabled'
        connection.variables['capital.max_contracts'].set('3')
        connection.save_connection()
        assert app.settings.max_contracts == 3 and app.settings.account_no == ''
        assert app.runtime is None and not runtime_root().exists()
        connection.select_page('TELEGRAM / LỊCH');settle()
        connection.variables['telegram.token'].set('offline-token')
        connection.variables['telegram.chat'].set('offline-chat')
        connection.options['entry'].set(True)
        connection.options['movement'].set(True)
        connection.calendar_form.variables['manual_closed_dates'].set('2026-11-19')
        connection.save()
        saved = signal_settings(app)
        assert saved.entry_notifications and saved.market_alerts['movement_enabled']
        assert saved.signals['buy_ema_fast'] == 5 and saved.signals['sell_ema_slow'] == 21
        assert app._demo_calendar.manual_closed_dates == ['2026-11-19']
        connection.toggle_backend()
        assert 'Mẫu offline' in connection.note.cget('text') and not getattr(app, 'signal_session', None)
        connection.destroy()
        rule.select('E/M')
        rule.select_scope('VỊ THẾ')
        rule.request_management()
        app.view['positions'] = []
        rule.confirm_management()
        assert 'Vị thế đã thay đổi' in rule.status.cget('text')
        assert app.settings.exit == common and not runtime_root().exists()
        assert not errors, errors
    finally:
        app.close()


@pytest.mark.parametrize('scale', [1., 1.5, 2.])
def test_two_settings_windows_scopes_signal_roundtrip_and_reachable_controls(scale):
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c',
        inspect.getsource(_consolidated_scenario)+f'\n_consolidated_scenario({scale!r})'],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout+result.stderr
