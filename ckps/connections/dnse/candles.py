"""Independent GET worker; slow candles cannot hold the execution worker."""
from copy import deepcopy
import threading


class CandleWorker:
    def __init__(self, client, *, start=True):
        self.client = client
        self.stop = threading.Event()
        self.client.stopping = self.stop
        self.lock = threading.Lock()
        self.bars = []
        self.thread = None
        if start:
            self.thread = threading.Thread(target=self._run, name="ckps-real-candles", daemon=True)
            self.thread.start()

    def snapshot(self):
        with self.lock:
            return deepcopy(self.bars)

    def _run(self):
        while not self.stop.is_set():
            try:
                bars = self.client.daily_bars()
                with self.lock:
                    self.bars = bars
            except Exception:
                pass
            self.stop.wait(30)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join()
        self.client.close()
