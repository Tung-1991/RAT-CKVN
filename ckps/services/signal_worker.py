"""Bounded analysis worker; history reads cannot delay position protection."""
from copy import deepcopy
import queue
import threading
import time

from ckps.connections.dnse.history import NoHistory, ReadOnlyHistory
from ckps.models import Settings, load_record
from ckps.storage import Store
from .signals import SignalAnalysis


class SignalWorker:
    def __init__(self, path, *, credentials=None):
        self.path, self.credentials = path, credentials
        self.pending = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.refresh_requested = threading.Event()
        self.view = {}
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True, name="ckps-analysis")
        self.thread.start()

    def update(self, data, settings):
        value = deepcopy((data, settings))
        try:
            self.pending.put_nowait(value)
        except queue.Full:
            try:
                self.pending.get_nowait()
            except queue.Empty:
                pass
            try:
                self.pending.put_nowait(value)
            except queue.Full:
                pass

    def snapshot(self):
        with self.lock:
            return deepcopy(self.view)

    def _run(self):
        store = Store(self.path)
        history = ReadOnlyHistory(**self.credentials) if self.credentials else NoHistory()
        history.stopping = self.stop
        analysis = SignalAnalysis(store, history)
        calendar, calendar_at = None, 0
        try:
            while not self.stop.is_set():
                try:
                    data, raw = self.pending.get(timeout=.2)
                except queue.Empty:
                    continue
                try:
                    if self.refresh_requested.is_set():
                        analysis.refresh()
                        self.refresh_requested.clear()
                    settings = load_record(Settings, raw)
                    if self.credentials and time.monotonic() - calendar_at > 3600:
                        try:
                            from ckps.services.calendar import refresh
                            calendar = refresh(history.working_dates).get('working_dates') or []
                        except Exception:
                            calendar = []  # An unknown exchange calendar cannot grant evidence.
                        calendar_at = time.monotonic()
                    value = analysis.observe(data, settings, working_dates=calendar)
                except Exception as exc:
                    value = {"contract": data.get("contract"), "p1": {"text": "CHỜ DỮ LIỆU", "state": "WAIT"},
                             "p2": {"status": "CHỜ PHÂN TÍCH", "badge": "WAIT"}, "error": str(exc)}
                value["signal_history"] = analysis.signal_history()
                with self.lock:
                    self.view = value
        finally:
            history.close()
            store.close()

    def close(self):
        self.stop.set()
        # Runtime is already a background worker. Keep the account lease until
        # analysis has stopped writing its derived memory to this ledger.
        self.thread.join()
