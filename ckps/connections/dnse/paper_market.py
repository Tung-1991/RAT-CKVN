"""Read-only DNSE market data for PAPER; HTTP never runs on its E/M worker."""
from copy import deepcopy
import threading


class PaperMarket:
    def __init__(self, client=None, *, poll_seconds=2, start=True):
        self.client = client
        self.feed = client.feed if client else None
        self.poll_seconds = poll_seconds
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.symbols = set()
        self.data = {"contract":"VN30F1M", "quotes":{}, "bars":[], "connected":False,
                     "configured":bool(client), "error":"" if client else "Chưa kết nối dữ liệu DNSE."}
        self.thread = None
        if client and start:
            client.stopping = self.stop
            self.thread = threading.Thread(target=self._run,name="ckps-paper-market",daemon=True)
            self.thread.start()

    def snapshot(self, symbols=()):
        with self.lock:
            self.symbols = set(symbols)
            return deepcopy(self.data)

    def _poll(self):
        if not self.client:
            return
        try:
            contract = self.client.resolve()
            with self.lock:
                symbols = {contract, *self.symbols}
            self.feed.start(symbols)
            quotes = {symbol:self.client.get_quote(symbol) for symbol in symbols}
            with self.lock:
                self.data.update(contract=contract,quotes=quotes,connected=True,error="")
            try:
                bars = self.client.daily_bars()
                with self.lock:
                    self.data.update(bars=bars,bars_error="")
            except Exception:
                with self.lock:
                    self.data["bars_error"] = "Đang chờ nến ngày từ DNSE."
        except Exception as exc:
            with self.lock:
                self.data.update(connected=False,error=str(exc))

    def _run(self):
        while not self.stop.is_set():
            self._poll()
            self.stop.wait(self.poll_seconds)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join()
        if self.client:
            self.client.close()
