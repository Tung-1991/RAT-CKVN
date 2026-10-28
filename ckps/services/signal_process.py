"""Private pipe to a separate read-only signal process; no trading commands."""
from dataclasses import asdict
import json
import queue
import subprocess
import sys
import threading

from ckps.config import ROOT
from ckps.models import Quote, Settings, load_record
from .signal_config import FIELDS


def public_settings(settings):
    raw = asdict(settings.validate())
    return {key: raw[key] for key in FIELDS}


class SignalProcess:
    def __init__(self, settings, credentials):
        self.status = 'Đang kết nối dữ liệu…'
        self.process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'ckps.signal_app', '--headless'],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.pending = queue.Queue()
        self.writer = threading.Thread(target=self._write, daemon=True, name='signal-settings-pipe')
        self.reader = threading.Thread(target=self._read, daemon=True, name='signal-status-pipe')
        self.writer.start()
        self.reader.start()
        self.pending.put({'command': 'start', 'settings': public_settings(settings),
            'credentials': {key: credentials.get(key, '') for key in ('key', 'secret', 'telegram_token')}})

    @property
    def running(self):
        return self.process.poll() is None

    def configure(self, settings, token):
        if self.running:
            self.pending.put({'command': 'settings', 'settings': public_settings(settings), 'token': token})

    def close(self):
        if self.running:
            self.pending.put({'command': 'stop'})
        self.pending.put(None)

    def _write(self):
        try:
            while True:
                value = self.pending.get()
                if value is None:
                    break
                self.process.stdin.write(json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n')
                self.process.stdin.flush()
        except (OSError, ValueError):
            self.status = 'Backend đã dừng; kết nối lại tại đây.'
        finally:
            self.process.stdin.close()

    def _read(self):
        try:
            for line in self.process.stdout:
                value = json.loads(line)
                self.status = str(value.get('status', 'Chờ dữ liệu'))
        except (OSError, ValueError):
            self.status = 'Chưa nhận được trạng thái backend.'
        finally:
            self.process.stdout.close()


def serve(source, target, *, runtime_factory=None):
    """Only settings and stop cross this pipe. Credentials never reach disk/argv."""
    if runtime_factory is None:
        from .signal_runtime import SignalRuntime
        runtime_factory = SignalRuntime
    incoming = queue.Queue()
    def read():
        try:
            for line in source:
                try:
                    incoming.put(json.loads(line))
                except ValueError:
                    incoming.put({'command': 'invalid'})
        finally:
            incoming.put({'command': 'stop'})
    threading.Thread(target=read, daemon=True, name='signal-control').start()
    runtime, closing = None, False
    def emit(status):
        target.write(json.dumps({'status': status}, ensure_ascii=False)+'\n')
        target.flush()
    try:
        while True:
            try:
                request = incoming.get(timeout=.1)
            except queue.Empty:
                request = None
            if request:
                name = request.get('command')
                if name == 'stop':
                    if runtime:
                        runtime.close()
                        closing = True
                    else:
                        break
                elif name in {'start', 'settings'} and not closing:
                    raw = request.get('settings', {})
                    settings = load_record(Settings, {key: raw[key] for key in FIELDS if key in raw}).validate()
                    if name == 'start' and runtime is None:
                        credentials = {key: str(request.get('credentials', {}).get(key, ''))
                                       for key in ('key', 'secret', 'telegram_token')}
                        runtime = runtime_factory(settings, credentials)
                        runtime.persist_settings = False
                        emit('Đang phân tích · Chờ giá DNSE')
                    elif name == 'settings' and runtime:
                        runtime.command('settings', public_settings(settings), str(request.get('token', '')))
                else:
                    emit('Backend chỉ nhận cấu hình tín hiệu hoặc yêu cầu dừng.')
            if runtime:
                while True:
                    try:
                        kind, value = runtime.events.get_nowait()
                    except queue.Empty:
                        break
                    if kind == 'closed':
                        emit('Đã dừng backend')
                        return 0
                    if kind == 'snapshot':
                        error = value.get('telegram_error') or value.get('connection', {}).get('error')
                        quote = value.get('quotes', {}).get(value.get('contract'), {})
                        if not quote or not load_record(Quote, quote).fresh(runtime.settings.max_quote_age):
                            emit('Chờ giá DNSE')
                        elif not value.get('analysis', {}).get('p2', {}).get('indicators'):
                            emit('Đã có giá · Chờ nến 1D')
                        else:
                            emit('Đang phân tích · Telegram chờ kết nối' if error else
                                 'Đang phân tích · Telegram '+('ON' if runtime.settings.telegram_enabled else 'OFF'))
                    elif kind == 'error':
                        emit('Backend chờ dữ liệu; kiểm tra API hoặc phiên đang chạy.')
    except Exception:
        emit('Chưa khởi động được backend; kiểm tra API hoặc phiên đang chạy.')
        return 1
    finally:
        if runtime:
            runtime.close()
    return 0


def standalone():
    """Optional console runner; settings are edited only in the main app."""
    import os
    from .signal_config import read_signal_settings, signal_folder
    from .signal_runtime import SignalRuntime
    if not (os.environ.get('CKPS_DNSE_API_KEY') and os.environ.get('CKPS_DNSE_API_SECRET')):
        print('Mở app → KẾT NỐI → TELEGRAM / LỊCH để cấu hình và chạy backend.')
        return 1
    runtime = SignalRuntime(read_signal_settings())
    runtime.persist_settings = False
    path, modified = signal_folder()/'settings.json', None
    print('Backend VN30 chỉ phân tích/thông báo. Chỉnh tại RULE và KẾT NỐI; Ctrl+C để dừng.')
    try:
        while runtime.thread.is_alive():
            try:
                stamp = path.stat().st_mtime_ns
                if stamp != modified:
                    modified = stamp
                    runtime.command('settings', public_settings(read_signal_settings()), os.environ.get('CKPS_TELEGRAM_TOKEN', ''))
            except (OSError, ValueError):
                pass
            try:
                kind, _value = runtime.events.get(timeout=.2)
                if kind == 'closed':
                    break
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
        runtime.thread.join(10)
    return 0
