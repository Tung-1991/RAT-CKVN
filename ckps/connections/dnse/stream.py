"""VN30-only DNSE stream, adapted from RAT's authenticated market feed."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import hmac
import json
import threading
import time
import uuid

import msgpack
import websocket

from ckps.models import Quote, is_vn30, market_time, number


class MarketFeed:
    def __init__(self, key, secret, *, max_quote_age=10):
        self.key, self.secret = key, secret
        self.max_quote_age = max_quote_age
        self.stop_event = threading.Event()
        self.changed = threading.Event()
        self.lock = threading.Lock()
        self.symbols = set()
        self.ticks = {}
        self.extremes = {}
        self.socket = None
        self.authenticated = False
        self.thread = None

    def start(self, symbols):
        symbols = {s for s in symbols if is_vn30(s)}
        with self.lock:
            new = symbols - self.symbols
            self.symbols = symbols
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name="ckps-price-ws", daemon=True)
            self.thread.start()
            threading.Thread(target=self._heartbeat, name="ckps-price-heartbeat", daemon=True).start()
        elif new and self.authenticated:
            self._subscribe()

    def _subscribe(self):
        channels = [f"tick.{board}.msgpack" for board in ("G1", "G3", "G7")]
        self.socket.send(json.dumps({"action": "subscribe", "channels": [
            {"name": name, "symbols": sorted(self.symbols)} for name in channels]}))

    def _open(self, ws):
        stamp, nonce = int(time.time()), uuid.uuid4().hex
        value = f"{self.key}:{stamp}:{nonce}"
        signature = hmac.new(self.secret.encode(), value.encode(), hashlib.sha256).hexdigest()
        ws.send(json.dumps({"action": "auth", "api_key": self.key, "signature": signature,
                            "timestamp": stamp, "nonce": nonce}))

    def _message(self, ws, message):
        try:
            payload = msgpack.unpackb(message, raw=False) if isinstance(message, bytes) else json.loads(message)
            if not isinstance(payload, dict):
                return
            action = payload.get("action", payload.get("a"))
            if action == "auth_success":
                self.authenticated = True
                self._subscribe()
                return
            if action == "ping":
                ws.send(json.dumps({"action": "pong"}))
                return
            data = payload.get("data", payload)
            if not isinstance(data, dict):
                return
            symbol = str(data.get("symbol", "")).upper()
            px = number(data.get("matchPrice"))
            # Expected auction prices and heartbeats must not masquerade as trades.
            if symbol not in self.symbols or px <= 0:
                return
            stamp = next((data[key] for key in ("time", "timestamp", "matchTime", "tradingTime") if data.get(key) is not None), None)
            quote = Quote(symbol, px, at=market_time(stamp), source="DNSE WS")
            if not quote.fresh(self.max_quote_age):
                return
            with self.lock:
                previous = self.ticks.get(symbol)
                if previous and quote.at < previous.at:
                    return
                # Validate every event before accumulating its extreme. A later
                # fresh tick must never make an old or undated event actionable.
                self.ticks[symbol] = quote
                low, high = self.extremes.get(symbol, (px, px))
                self.extremes[symbol] = min(low, px), max(high, px)
                self.changed.set()
        except (ValueError, TypeError, msgpack.UnpackException, websocket.WebSocketException):
            return

    def _run(self):
        while not self.stop_event.is_set():
            self.authenticated = False
            self.socket = websocket.WebSocketApp("wss://ws-openapi.dnse.com.vn/v1/stream?encoding=json",
                on_open=self._open, on_message=self._message,
                on_close=lambda *args: setattr(self, "authenticated", False), on_error=lambda *args: None)
            try:
                self.socket.run_forever(ping_interval=25, ping_timeout=10)
            except Exception:
                pass
            self.authenticated = False
            if self.stop_event.wait(5):
                break

    def _heartbeat(self):
        while not self.stop_event.wait(15):
            if self.authenticated and self.socket:
                try:
                    self.socket.send(json.dumps({"action": "ping"}))
                except websocket.WebSocketException:
                    self.socket.close()

    def latest(self, symbol, max_age=None):
        with self.lock:
            value = self.ticks.get(symbol)
            max_age = self.max_quote_age if max_age is None else max_age
            return replace(value) if value and value.fresh(max_age) and self.authenticated else None

    def drain(self):
        with self.lock:
            values = ({symbol: replace(value) for symbol, value in self.ticks.items()}, dict(self.extremes))
            self.extremes.clear()
            self.changed.clear()
            return values

    def reset_extremes(self, symbol):
        with self.lock:
            self.extremes.pop(symbol, None)

    def close(self):
        self.stop_event.set()
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=3)
