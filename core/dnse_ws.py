# -*- coding: utf-8 -*-
"""DNSE Market-Data WebSocket client.

Streams real-time ticks/quotes from DNSE into an in-memory cache so the bot can
watch many symbols without polling REST endpoints (which are rate-limited per
LIMIT.txt). DataEngine reads this cache first and falls back to REST when
streaming has no fresh value.

Protocol (matched to the official SDK, github.com/dnse-tech/openapi-sdk):
  * URL:        {DNSE_WS_URL}/v1/stream?encoding=json   (wss://ws-openapi.dnse.com.vn)
  * Auth:       send {"action":"auth","api_key":..,"signature":HEX_HMAC,"timestamp":..,"nonce":..}
                where signature = HMAC-SHA256(secret, f"{api_key}:{timestamp}:{nonce}").hexdigest()
                wait for {"action":"auth_success"}.
  * Subscribe:  {"action":"subscribe","channels":[{"name":"tick.G1.json","symbols":[...]},
                                                   {"name":"top_price.G1.json","symbols":[...]}]}
  * Data msgs:  flat payload dict with `symbol` + channel fields (matchPrice / bid / offer ...).
  * Keepalive:  server PINGs ~every 3 min; client must PONG within 1 min. websocket-client
                auto-replies to ping; we also send a proactive pong every DNSE_WS_PONG_INTERVAL.
  * A connection lives at most 8h (server closes); the reconnect loop handles it.

Transport uses the synchronous ``websocket-client`` package so it fits the bot's
threaded model without an asyncio loop. If the package is missing the client stays
disabled and the app uses the REST fallback.
"""

import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Dict, Iterable, List, Optional

import config

logger = logging.getLogger("DNSE_WS")

try:
    import websocket  # provided by the `websocket-client` package
    _WS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    websocket = None
    _WS_AVAILABLE = False


def _env(key, default=""):
    try:
        from core.env_utils import get_env_value
        return get_env_value(key, default) or default
    except Exception:
        import os
        return os.getenv(key, default) or default


class DNSEMarketWS:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self._api_key = api_key or _env("DNSE_API_KEY")
        self._api_secret = api_secret or _env("DNSE_API_SECRET")
        base = getattr(config, "DNSE_WS_URL", "wss://ws-openapi.dnse.com.vn").rstrip("/")
        self._encoding = getattr(config, "DNSE_WS_ENCODING", "json")
        self._url = f"{base}/v1/stream?encoding={self._encoding}"
        self._board_id = getattr(config, "DNSE_WS_BOARD_ID", "G1")
        self._reconnect_s = float(getattr(config, "DNSE_WS_RECONNECT_SECONDS", 5.0))
        self._pong_interval = float(getattr(config, "DNSE_WS_PONG_INTERVAL", 150.0))

        self._ticks: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._desired: set = set()
        self._subscribed: set = set()

        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        self._authenticated = False
        self._last_pong = 0.0

        self.stats = {
            "messages": 0,
            "reconnects": 0,
            "last_message_ts": 0.0,
            "last_error": "",
        }

    # ------------------------------------------------------------------ public
    @property
    def available(self) -> bool:
        return _WS_AVAILABLE

    def is_connected(self) -> bool:
        return self._connected and self._authenticated

    def latest_tick(self, symbol: str) -> Optional[Dict]:
        with self._lock:
            tick = self._ticks.get(str(symbol).upper())
            return dict(tick) if tick else None

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "available": _WS_AVAILABLE,
                "enabled": bool(getattr(config, "DNSE_WS_ENABLED", False)),
                "connected": self._connected and self._authenticated,
                "subscribed": sorted(self._subscribed),
                "desired": sorted(self._desired),
                "messages": self.stats["messages"],
                "reconnects": self.stats["reconnects"],
                "last_message_ts": self.stats["last_message_ts"],
                "last_error": self.stats["last_error"],
            }

    def start(self) -> bool:
        if not _WS_AVAILABLE:
            logger.warning("websocket-client chưa cài; WS market data tắt, dùng REST. (pip install websocket-client)")
            return False
        if not self._api_key or not self._api_secret:
            logger.warning("Thiếu DNSE_API_KEY/SECRET cho WS; dùng REST.")
            return False
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="DNSEMarketWS")
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        self._connected = False
        self._authenticated = False

    def subscribe(self, symbols: Iterable[str]):
        syms = {str(s).upper() for s in symbols if s}
        with self._lock:
            new = syms - self._desired
            self._desired |= syms
        if new and self.is_connected():
            self._send_subscribe(new)

    def unsubscribe(self, symbols: Iterable[str]):
        syms = {str(s).upper() for s in symbols if s}
        with self._lock:
            self._desired -= syms
            gone = syms & self._subscribed
            self._subscribed -= syms
        if gone and self.is_connected():
            self._send_unsubscribe(gone)

    def set_symbols(self, symbols: Iterable[str]):
        """Replace the desired set with exactly these symbols."""
        syms = {str(s).upper() for s in symbols if s}
        with self._lock:
            to_add = syms - self._desired
            to_remove = self._desired - syms
            self._desired = syms
        if self.is_connected():
            if to_remove:
                self._send_unsubscribe(to_remove)
            if to_add:
                self._send_subscribe(to_add)

    # --------------------------------------------------------------- handshake
    def _auth_message(self) -> str:
        timestamp = int(time.time())
        nonce = str(int(time.time() * 1_000_000))
        message = f"{self._api_key}:{timestamp}:{nonce}"
        signature = hmac.new(
            self._api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return json.dumps({
            "action": "auth",
            "api_key": self._api_key,
            "signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
        })

    def _channels(self) -> List[str]:
        enc = self._encoding
        bid = self._board_id
        return [f"tick.{bid}.{enc}", f"top_price.{bid}.{enc}"]

    def _send_subscribe(self, symbols: Iterable[str]):
        syms = sorted(symbols)
        try:
            channels = [{"name": ch, "symbols": syms} for ch in self._channels()]
            self._ws.send(json.dumps({"action": "subscribe", "channels": channels}))
            with self._lock:
                self._subscribed |= set(syms)
        except Exception as exc:  # noqa: BLE001
            logger.debug("subscribe error: %s", exc)

    def _send_unsubscribe(self, symbols: Iterable[str]):
        syms = sorted(symbols)
        try:
            channels = [{"name": ch, "symbols": syms} for ch in self._channels()]
            self._ws.send(json.dumps({"action": "unsubscribe", "channels": channels}))
        except Exception as exc:  # noqa: BLE001
            logger.debug("unsubscribe error: %s", exc)

    # --------------------------------------------------------------- transport
    def _run(self):
        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    self._url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_ping=self._on_ping,
                )
                self._ws.run_forever(ping_interval=0, ping_timeout=None)
            except Exception as exc:  # noqa: BLE001
                self.stats["last_error"] = str(exc)
                logger.debug("WS run error: %s", exc)
            self._connected = False
            self._authenticated = False
            with self._lock:
                self._subscribed.clear()
            if not self._running:
                break
            self.stats["reconnects"] += 1
            time.sleep(self._reconnect_s)

    # ------------------------------------------------------------------ events
    def _on_open(self, _ws):
        self._connected = True
        self._authenticated = False
        self._last_pong = time.time()
        logger.info("DNSE market WS connected: %s", self._url)
        try:
            self._ws.send(self._auth_message())
        except Exception as exc:  # noqa: BLE001
            logger.debug("auth send error: %s", exc)

    def _heartbeat_loop(self):
        while self._running and self._connected:
            time.sleep(min(30.0, self._pong_interval))
            if not self._connected:
                break
            if time.time() - self._last_pong >= self._pong_interval:
                try:
                    self._ws.pong("")
                    self._last_pong = time.time()
                except Exception:
                    break

    def _on_ping(self, _ws, _data):
        try:
            self._ws.pong("")
        except Exception:
            pass
        self._last_pong = time.time()

    def _on_error(self, _ws, error):
        self.stats["last_error"] = str(error)
        logger.debug("WS error: %s", error)

    def _on_close(self, _ws, code, msg):
        self._connected = False
        self._authenticated = False
        logger.info("DNSE market WS closed: %s %s", code, msg)

    def _on_message(self, _ws, message):
        self.stats["messages"] += 1
        self.stats["last_message_ts"] = time.time()
        try:
            payload = json.loads(message) if isinstance(message, (str, bytes, bytearray)) else message
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        action = payload.get("action") or payload.get("a")
        if action:
            self._handle_control(action, payload)
            return
        # Some servers wrap the payload as {"channel":.., "data":{...}}.
        data = payload.get("data", payload)
        if isinstance(data, dict):
            self._ingest(data)

    def _handle_control(self, action: str, payload: Dict):
        if action == "auth_success":
            self._authenticated = True
            logger.info("DNSE market WS authenticated.")
            with self._lock:
                desired = set(self._desired)
            if desired:
                self._send_subscribe(desired)
            threading.Thread(target=self._heartbeat_loop, daemon=True, name="DNSEMarketWS-HB").start()
        elif action in ("auth_error", "error"):
            self.stats["last_error"] = str(payload.get("message") or payload)
            logger.warning("DNSE market WS control error: %s", payload)

    # -------------------------------------------------------------- cache write
    def _ingest(self, data: Dict):
        symbol = str(data.get("symbol") or data.get("Symbol") or "").upper()
        if not symbol:
            return
        now = time.time()
        with self._lock:
            tick = self._ticks.get(symbol, {"symbol": symbol})
            if "matchPrice" in data:
                tick["last"] = _f(data.get("matchPrice"), tick.get("last"))
                tick["high"] = _f(data.get("highestPrice"), tick.get("high"))
                tick["low"] = _f(data.get("lowestPrice"), tick.get("low"))
                tick["open"] = _f(data.get("openPrice"), tick.get("open"))
            bid = _best_level(data.get("bid"))
            ask = _best_level(data.get("offer") if data.get("offer") is not None else data.get("ask"))
            if bid is not None:
                tick["bid"] = bid
            if ask is not None:
                tick["ask"] = ask
            if bid is not None and ask is not None:
                tick["synthetic_quote"] = False  # đã có sổ lệnh thật đủ 2 phía
            if "last" in tick:
                if "bid" not in tick:
                    tick["bid"] = tick["last"]
                    tick["synthetic_quote"] = True
                if "ask" not in tick:
                    tick["ask"] = tick["last"]
                    tick["synthetic_quote"] = True
            if "bid" in tick and "ask" in tick:
                tick["spread"] = round(float(tick["ask"]) - float(tick["bid"]), 2)
            tick["timestamp"] = now
            self._ticks[symbol] = tick


def _f(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _best_level(levels):
    """Return the best price from a DNSE bid/offer level list or scalar."""
    if levels is None:
        return None
    if isinstance(levels, (int, float)):
        return float(levels)
    if isinstance(levels, list) and levels:
        first = levels[0]
        if isinstance(first, dict):
            return _f(first.get("price"))
        return _f(first)
    if isinstance(levels, dict):
        return _f(levels.get("price"))
    return None


# Shared singleton used by DataEngine.
market_ws = DNSEMarketWS()
