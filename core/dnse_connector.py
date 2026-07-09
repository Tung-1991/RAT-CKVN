# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from dotenv import load_dotenv

import config
from core import settlement, settlement_ledger, stock_rules
from core.dnse_signature import generate_signature_header


logger = logging.getLogger(__name__)

ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
DNSE_POINT_VALUE = 100000.0


@dataclass
class BrokerTick:
    symbol: str
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    spread: float = 0.0
    ceiling: float = 0.0
    floor: float = 0.0
    reference: float = 0.0
    timestamp: float = field(default_factory=time.time)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerSymbolInfo:
    symbol: str
    point: float = 0.1
    trade_contract_size: float = DNSE_POINT_VALUE
    volume_min: float = 1.0
    volume_max: float = 200.0
    volume_step: float = 1.0
    trade_stops_level: float = 0.0
    spread: float = 0.0
    market_type: str = "DERIVATIVE"
    quantity_label: str = "Hợp đồng"
    quantity_unit: str = "HĐ"
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerPosition:
    ticket: str
    position_id: str
    order_id: str
    symbol: str
    type: int
    volume: float
    price_open: float
    price_current: float = 0.0
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    comment: str = ""
    magic: int = 0
    time: float = field(default_factory=time.time)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerOrderResult:
    ok: bool
    order_id: str = ""
    position_id: str = ""
    status: str = ""
    message: str = ""
    error: str = ""
    status_code: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def order(self) -> str:
        return self.order_id or self.position_id

    @property
    def ticket(self) -> str:
        return self.order

    @property
    def retcode(self) -> int:
        """Mã trạng thái lệnh. 200=OK (DNSE), 0=Failed."""
        return 200 if self.ok else 0


@dataclass
class BrokerFeeProfile:
    broker_fee_per_contract: float = 0.0
    exchange_fee_per_contract: float = 2700.0
    clearing_fee_per_contract: float = 2550.0
    broker_fee_rate: float = 0.0
    tax_rate: float = 0.0
    point_value: float = DNSE_POINT_VALUE
    market_type: str = "DERIVATIVE"
    quantity_unit: str = "HĐ"
    fee_available: bool = True
    source: str = "fallback"
    raw: Dict[str, Any] = field(default_factory=dict)

    def fixed_per_contract(self) -> float:
        return (
            float(self.broker_fee_per_contract or 0.0)
            + float(self.exchange_fee_per_contract or 0.0)
            + float(self.clearing_fee_per_contract or 0.0)
        )

    def estimate_fee(self, price: float, contracts: float) -> float:
        qty = max(0.0, float(contracts or 0.0))
        fixed = self.fixed_per_contract() * qty
        notional = max(0.0, float(price or 0.0)) * qty * float(self.point_value or DNSE_POINT_VALUE)
        rate_fee = notional * float(self.broker_fee_rate or 0.0)
        tax = notional * float(self.tax_rate or 0.0)
        return fixed + rate_fee + tax

    def as_dict(self) -> Dict[str, Any]:
        return {
            "broker_fee_per_contract": float(self.broker_fee_per_contract or 0.0),
            "exchange_fee_per_contract": float(self.exchange_fee_per_contract or 0.0),
            "clearing_fee_per_contract": float(self.clearing_fee_per_contract or 0.0),
            "broker_fee_rate": float(self.broker_fee_rate or 0.0),
            "tax_rate": float(self.tax_rate or 0.0),
            "point_value": float(self.point_value or DNSE_POINT_VALUE),
            "market_type": self.market_type,
            "quantity_unit": self.quantity_unit,
            "fee_available": bool(self.fee_available),
            "source": self.source,
            "raw": dict(self.raw or {}),
        }


def _first_value(data: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def _deep_first_value(data: Any, keys: Iterable[str], default: Any = None) -> Any:
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        for value in data.values():
            found = _deep_first_value(value, keys, None)
            if found not in (None, ""):
                return found
    elif isinstance(data, list):
        for value in data:
            found = _deep_first_value(value, keys, None)
            if found not in (None, ""):
                return found
    return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _unwrap_payload(data: Any, collection_keys: Tuple[str, ...] = ()) -> Any:
    if not isinstance(data, dict):
        return data
    for key in collection_keys:
        value = data.get(key)
        if value is not None:
            return value
    for key in ("data", "items", "content", "result"):
        value = data.get(key)
        if value is not None:
            return value
    return data


class DNSEConnector:
    _balances_403_muted = False
    _positions_403_muted = False

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        account_no: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        load_dotenv(encoding="utf-8-sig")
        def _clean_acc(value: str) -> str:
            # Số tiểu khoản là chuỗi số; loại các giá trị rác như "True"/"False"/"None".
            v = str(value or "").strip()
            return "" if v.lower() in ("true", "false", "none") else v

        explicit_account_no = _clean_acc(account_no)
        self.api_key = api_key or os.getenv("DNSE_API_KEY", "")
        self.api_secret = api_secret or os.getenv("DNSE_API_SECRET", "")
        self.stock_account_no = explicit_account_no or _clean_acc(os.getenv("DNSE_STOCK_ACCOUNT_NO", ""))
        self.derivative_account_no = explicit_account_no or _clean_acc(os.getenv("DNSE_DERIVATIVE_ACCOUNT_NO", ""))
        self.custody_code = os.getenv("DNSE_CUSTODY_CODE", "")
        self.account_no = (
            explicit_account_no
            or self.derivative_account_no
            or self.stock_account_no
            or _clean_acc(os.getenv("DNSE_ACCOUNT_NO", ""))
        )
        self.otp_type = os.getenv("DNSE_OTP_TYPE", "email_otp")
        self.base_url = (base_url or os.getenv("DNSE_BASE_URL", "https://openapi.dnse.com.vn")).rstrip("/")
        self.session = session or requests.Session()
        self.is_connected = False
        self.trading_token: Optional[str] = None
        self.trading_token_expires_at: float = 0.0
        self.trading_token_persistent: bool = False
        self.last_request_time = 0.0
        # [FREEZE FIX] Khóa để giãn nhịp rate-limit nhất quán giữa các thread (UI + nền).
        # Trước đây 2 thread đọc last_request_time cùng lúc -> cùng bỏ qua wait -> burst -> 429.
        self._rate_lock = threading.Lock()
        self.last_latency_ms = 0.0
        self.market_type = os.getenv("DNSE_MARKET_TYPE", "DERIVATIVE")
        self.order_category = os.getenv("DNSE_ORDER_CATEGORY", "NORMAL")
        self._paper_broker = None
        self._account_cache: Optional[Dict[str, Any]] = None
        self._account_cache_ts: float = 0.0
        self._positions_cache: List[BrokerPosition] = []
        self._positions_cache_ts: float = 0.0
        self._fee_profile_cache: Dict[str, BrokerFeeProfile] = {}
        self._fee_profile_cache_ts: Dict[str, float] = {}
        self._tick_cache: Dict[str, BrokerTick] = {}
        self._tick_cache_ts: Dict[str, float] = {}
        # Map alias phái sinh (symbolType: VN30F1M...) -> mã hợp đồng thật (41I1G6000...).
        # Mã thật ĐỔI theo tháng đáo hạn nên tra động từ /instruments rồi cache.
        self._symbol_map: Dict[str, str] = {}
        self._symbol_map_ts: float = 0.0
        self._derivative_real_symbols: set = set()
        self._working_dates: List[str] = []
        self._working_dates_ts: float = 0.0
        self.api_stats = {
            "started_at": time.time(),
            "total_requests": 0,
            "by_endpoint": {},
            "last_endpoint": "",
            "last_status": None,
            "last_error": "",
            "last_latency_ms": 0.0,
        }
        self._load_token_from_disk()  # opt-in: nạp token đã lưu (nếu còn hiệu lực) để khỏi OTP lại sau restart

    @property
    def _is_connected(self) -> bool:
        return self.is_connected

    @_is_connected.setter
    def _is_connected(self, value: bool):
        self.is_connected = bool(value)

    def connect(self) -> bool:
        if not self.api_key or not self.api_secret or not self.account_no:
            logger.error("DNSE_API_KEY, DNSE_API_SECRET and DNSE_ACCOUNT_NO are required.")
            self.is_connected = False
            return False
        self.is_connected = True
        logger.info("Connected to DNSE OpenAPI for account %s.", self.account_no)
        return True

    def shutdown(self):
        self.is_connected = False
        self.session.close()

    def _is_paper_mode(self) -> bool:
        return bool(getattr(config, "PAPER_TRADING", True))

    def _paper(self):
        if self._paper_broker is None:
            from core.paper_broker import PaperBroker
            self._paper_broker = PaperBroker(
                self.account_no or "PAPER",
                tick_provider=self.get_tick,
                fee_profile_provider=self.get_fee_profile,
                working_dates_provider=self.get_working_dates,
            )
        return self._paper_broker

    def reset_paper(self, balance: Optional[float] = None) -> Dict[str, Any]:
        return self._paper().reset(balance)

    def reset_session_caches(self):
        """Xoá cache tài khoản/vị thế — gọi khi đổi PAPER<->REAL để lần đọc sau lấy số liệu mới
        (không cần restart app). Token + market-data cache giữ nguyên."""
        self._account_cache = None
        self._account_cache_ts = 0.0
        self._positions_cache = []
        self._positions_cache_ts = 0.0

    # ---- Lưu/nạp trading-token qua restart (opt-in, PERSIST_TRADING_TOKEN) ----
    def _token_file(self) -> Optional[str]:
        acc = str(self.account_no or "").strip()
        return os.path.join("data", acc, "trading_token.json") if acc else None

    def _configured_token_ttl_seconds(self) -> float:
        ttl_map = getattr(config, "DNSE_TOKEN_TTL_HOURS", {}) or {}
        ttl_hours = float(ttl_map.get(self.otp_type, 8.0) or 0.0)
        return max(0.0, ttl_hours * 3600.0)

    def _clear_trading_token(self, remove_file: bool = False):
        self.trading_token = None
        self.trading_token_expires_at = 0.0
        self.trading_token_persistent = False
        if remove_file:
            path = self._token_file()
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as exc:
                    logger.warning("Xoa trading-token cache loi: %s", exc)

    def _save_token_to_disk(self):
        if not bool(getattr(config, "PERSIST_TRADING_TOKEN", False)):
            return
        path = self._token_file()
        if not path or not self.trading_token:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "trading_token": self.trading_token,
                    "otp_type": self.otp_type,
                    "saved_at": time.time(),
                    "expires_at": self.trading_token_expires_at,
                    "persistent": self.trading_token_persistent,
                }, f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lưu trading-token lỗi: %s", exc)

    def _load_token_from_disk(self):
        if not bool(getattr(config, "PERSIST_TRADING_TOKEN", False)):
            return
        path = self._token_file()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = str(data.get("trading_token") or "")
            exp = float(data.get("expires_at") or 0.0)
            ttl_seconds = self._configured_token_ttl_seconds()
            if ttl_seconds > 0 and exp > time.time() + ttl_seconds + 300.0:
                logger.info("Bo qua trading-token cache cu co han vuot TTL DNSE.")
                return
            if token and time.time() < exp:
                self.trading_token = token
                self.trading_token_expires_at = exp
                self.trading_token_persistent = bool(data.get("persistent", False)) and ttl_seconds <= 0
                logger.info("Đã nạp trading-token đã lưu (còn hiệu lực).")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Nạp trading-token lỗi: %s", exc)

    def _account_pending_info(self, reason: str = "") -> Dict[str, Any]:
        pending_balance = float(getattr(config, "PAPER_INITIAL_BALANCE", 100000000.0))
        return {
            "login": self.account_no,
            "server": "DNSE_API_REAL_PENDING",
            "status": "ACCOUNT_PENDING",
            "balance": pending_balance,
            "equity": pending_balance,
            "margin": 0.0,
            "free_margin": pending_balance,
            "margin_free": pending_balance,
            "margin_level": 0.0,
            "reason": reason,
        }

    def _rate_limit(self):
        with self._rate_lock:
            now = time.time()
            wait_s = 0.1 - (now - self.last_request_time)
            if wait_s > 0:
                time.sleep(wait_s)
            self.last_request_time = time.time()

    def _record_api_request(self, method: str, path: str, status_code: int, latency_ms: float, error: str = ""):
        endpoint = f"{method.upper()} {path}"
        self.api_stats["total_requests"] = int(self.api_stats.get("total_requests", 0) or 0) + 1
        by_endpoint = self.api_stats.setdefault("by_endpoint", {})
        by_endpoint[endpoint] = int(by_endpoint.get(endpoint, 0) or 0) + 1
        self.api_stats["last_endpoint"] = endpoint
        self.api_stats["last_status"] = status_code
        self.api_stats["last_error"] = error or ""
        self.api_stats["last_latency_ms"] = float(latency_ms or 0.0)

    def get_api_health_snapshot(self) -> Dict[str, Any]:
        return {
            **self.api_stats,
            "account_cache_age": max(0.0, time.time() - self._account_cache_ts) if self._account_cache else None,
            "positions_cache_age": max(0.0, time.time() - self._positions_cache_ts) if self._positions_cache_ts else None,
        }

    def _build_headers(self, method: str, path: str, *, require_trading_token: bool = False) -> Dict[str, str]:
        x_sig, date_str = generate_signature_header(self.api_key, self.api_secret, method, path)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "X-Signature": x_sig,
            "X-Aux-Date": date_str,
            "version": os.getenv("DNSE_API_VERSION", "2026-05-07"),
        }
        if self.trading_token:
            headers["trading-token"] = self.trading_token
        if require_trading_token and not self.has_trading_token():
            raise RuntimeError("DNSE trading token is missing or expired. Verify OTP first.")
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
        require_trading_token: bool = False,
        timeout: float = 15.0,
    ) -> Tuple[bool, Any, int, str]:
        if not self.is_connected and not self.connect():
            return False, None, 0, "NOT_CONNECTED"
        max_429_retries = int(getattr(config, "DNSE_RATE_LIMIT_RETRIES", 1) or 0)
        attempt = 0
        try:
            while True:
                self._rate_limit()
                headers = self._build_headers(method, path, require_trading_token=require_trading_token)
                started = time.perf_counter()
                response = self.session.request(
                    method.upper(),
                    f"{self.base_url}{path}",
                    params=params,
                    json=json_payload,
                    headers=headers,
                    timeout=timeout,
                )
                self.last_latency_ms = (time.perf_counter() - started) * 1000.0
                try:
                    data = response.json()
                except ValueError:
                    data = {"text": response.text}
                if 200 <= response.status_code < 300:
                    self._record_api_request(method, path, response.status_code, self.last_latency_ms)
                    return True, data, response.status_code, ""
                # [24/7] Dính rate-limit (429): chờ theo Retry-After rồi thử lại tối đa N lần.
                if response.status_code == 429 and attempt < max_429_retries:
                    attempt += 1
                    try:
                        wait_s = float(response.headers.get("Retry-After", "") or 0.0)
                    except (TypeError, ValueError):
                        wait_s = 0.0
                    wait_s = wait_s if wait_s > 0 else min(30.0, 2.0 ** attempt)
                    logger.warning("DNSE %s %s rate-limited (429). Backoff %.1fs (lần %d).", method.upper(), path, wait_s, attempt)
                    time.sleep(wait_s)
                    continue
                message = data.get("message") if isinstance(data, dict) else str(data)
                if response.status_code == 401 and "token is invalid" in str(message or data).lower():
                    self._clear_trading_token(remove_file=True)
                self._record_api_request(method, path, response.status_code, self.last_latency_ms, message or response.text)
                return False, data, response.status_code, message or response.text
        except Exception as exc:
            self._record_api_request(method, path, 0, 0.0, str(exc))
            logger.error("DNSE %s %s failed: %s", method.upper(), path, exc)
            return False, None, 0, str(exc)

    def has_trading_token(self) -> bool:
        return bool(self.trading_token and time.time() < self.trading_token_expires_at)

    def trading_token_seconds_left(self) -> float:
        """Số giây còn lại của trading-token (0 nếu chưa có/đã hết). Cho UI cảnh báo."""
        if not self.trading_token:
            return 0.0
        return max(0.0, float(self.trading_token_expires_at or 0.0) - time.time())

    def send_email_otp(self) -> bool:
        ok, data, status_code, message = self._request("POST", "/registration/send-email-otp")
        if not ok:
            logger.error("DNSE send email OTP failed [%s]: %s", status_code, message or data)
        return ok

    def verify_otp(self, otp_type: Optional[str], passcode: str) -> bool:
        payload = {"otpType": otp_type or self.otp_type, "passcode": str(passcode)}
        ok, data, status_code, message = self._request("POST", "/registration/trading-token", json_payload=payload)
        if not ok or not isinstance(data, dict):
            logger.error("DNSE OTP verification failed [%s]: %s", status_code, message or data)
            return False
        token = _first_value(data, ("tradingToken", "trading-token", "token", "data"))
        if isinstance(token, dict):
            token = _first_value(token, ("tradingToken", "trading-token", "token"))
        if not token:
            logger.error("DNSE OTP verification did not return trading token: %s", data)
            return False
        self.trading_token = str(token)
        # DNSE docs: trading-token is valid for about 8 hours.
        ttl_seconds = self._configured_token_ttl_seconds()
        ttl_hours = ttl_seconds / 3600.0
        self.trading_token_persistent = ttl_hours <= 0
        if self.trading_token_persistent:
            self.trading_token_expires_at = time.time() + (10 * 365 * 24 * 3600)
            logger.info("DNSE trading token ready (%s — không tự hết hạn).", self.otp_type)
        else:
            self.trading_token_expires_at = time.time() + ttl_seconds
            logger.info("DNSE trading token ready (~%.0fh, %s).", ttl_hours, self.otp_type)
        self._save_token_to_disk()  # opt-in: lưu để restart khỏi OTP lại
        return True

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        if self._is_paper_mode():
            return self._paper().get_account_info()
        cache_ttl = float(getattr(config, "DNSE_ACCOUNT_CACHE_TTL_SECONDS", 5.0) or 0.0)
        if self._account_cache is not None and cache_ttl > 0 and (time.time() - self._account_cache_ts) < cache_ttl:
            return dict(self._account_cache)
        ok, data, status_code, message = self._request("GET", f"/accounts/{self.account_no}/balances")
        if not ok:
            if status_code == 403:
                if not DNSEConnector._balances_403_muted:
                    logger.warning("DNSE balances failed [403]: %s. Muting further 403s.", message or data)
                    DNSEConnector._balances_403_muted = True
                info = self._account_pending_info(message or "DNSE account access pending.")
                self._account_cache = dict(info)
                self._account_cache_ts = time.time()
                return info
            if not getattr(self, "_balances_error_logged", False):
                logger.warning("DNSE balances failed [%s]: %s. Muting further 403s.", status_code, message or data)
                self._balances_error_logged = True
            info = self._account_pending_info(message or "DNSE account unavailable.")
            self._account_cache = dict(info)
            self._account_cache_ts = time.time()
            return info
        payload = _unwrap_payload(data)
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            payload = {}
        # [FIX] Response DNSE /balances có 2 khối: "stock" (totalCash/availableCash) và
        # "derivative" (remainSecure). KHÔNG có key top-level "balance"/"nav" -> trước đây ra 0.
        stock_blk = payload.get("stock") if isinstance(payload.get("stock"), dict) else {}
        deriv_blk = payload.get("derivative") if isinstance(payload.get("derivative"), dict) else {}
        stock_total = _to_float(stock_blk.get("totalCash"), 0.0)
        stock_avail = _to_float(stock_blk.get("availableCash"), stock_total)
        deriv_avail = _to_float(deriv_blk.get("remainSecure"), 0.0)
        legacy_bal = _to_float(_deep_first_value(payload, ("balance", "cashBalance", "totalAsset", "netAssetValue", "nav")), 0.0)
        balance = stock_total or deriv_avail or legacy_bal
        equity = _to_float(_deep_first_value(payload, ("equity", "netAssetValue", "nav", "totalAsset"), balance), balance)
        margin = _to_float(_deep_first_value(payload, ("margin", "marginValue", "derivativeMargin", "usedSecure")), 0.0)
        cash_available = _to_float(_deep_first_value(payload, ("cashAvailable", "cash_available", "cashBalanceAvailable", "availableCash")), 0.0) or stock_avail or deriv_avail
        buying_power = _to_float(_deep_first_value(payload, ("buyingPower", "buying_power", "purchasingPower")), 0.0) or stock_avail or deriv_avail
        available_balance = _to_float(_deep_first_value(payload, ("freeMargin", "availableBalance", "available_balance")), 0.0)
        free_margin = available_balance or cash_available or buying_power or (equity - margin)
        margin_debt = _to_float(_deep_first_value(payload, ("marginDebt", "margin_debt", "loan", "loanValue", "debt", "debtValue")), margin)
        rtt_raw = _deep_first_value(payload, ("rtt", "Rtt", "RTT", "marginRatio", "margin_ratio", "actualRatio"), None)
        rtt = None if rtt_raw in (None, "") else _to_float(rtt_raw, 0.0)
        margin_call_level = _to_float(_deep_first_value(payload, ("callRtt", "callMarginRatio", "marginCallLevel")), 87.0)
        margin_force_level = _to_float(_deep_first_value(payload, ("forceRtt", "forceSellRatio", "marginForceLevel")), 80.0)
        info = {
            "login": self.account_no,
            "server": "DNSE_API",
            "balance": balance,
            "equity": equity,
            "margin": margin,
            "free_margin": free_margin,
            "margin_free": free_margin,
            "margin_level": (equity / margin * 100.0) if margin else 0.0,
            "cash_available": cash_available,
            "buying_power": buying_power or free_margin,
            "margin_debt": margin_debt,
            "rtt": rtt,
            "margin_call_level": margin_call_level,
            "margin_force_level": margin_force_level,
            # Tách bạch 2 ví để UI hiện đúng (không gán nhầm tiền cơ sở thành ký quỹ phái sinh).
            "stock_cash": stock_avail or stock_total,
            "deriv_avail": deriv_avail,
            "raw": data,
        }
        self._account_cache = dict(info)
        self._account_cache_ts = time.time()
        return info

    def get_accounts(self) -> Dict[str, Any]:
        ok, data, status_code, message = self._request("GET", "/accounts")
        if not ok:
            logger.warning("DNSE get accounts failed [%s]: %s", status_code, message or data)
            return {"accounts": [], "error": message or data, "status_code": status_code}
        payload = _unwrap_payload(data)
        return payload if isinstance(payload, dict) else {"accounts": payload if isinstance(payload, list) else [], "raw": data}

    DERIVATIVE_TYPE_ALIASES = {"VN30F1M", "VN30F2M", "VN30F1Q", "VN30F2Q"}

    def _refresh_symbol_map(self) -> None:
        """Tra /instruments để map symbolType (VN30F1M) -> mã hợp đồng thật (41I1G6000). Cache 1h."""
        now = time.time()
        if self._symbol_map and (now - self._symbol_map_ts) < 3600.0:
            return
        try:
            ok, data, _status, _msg = self._request(
                "GET", "/instruments",
                params={"marketId": "DVX", "securityGroupId": "FU", "limit": 50},
            )
            if ok and isinstance(data, dict):
                m, real = {}, set()
                for it in data.get("data", []) or []:
                    st = str(it.get("symbolType", "") or "").upper()
                    sym = str(it.get("symbol", "") or "")
                    if st and sym:
                        m[st] = sym
                        real.add(sym.upper())
                if m:
                    self._symbol_map = m
                    self._derivative_real_symbols = real
                    self._symbol_map_ts = now
        except Exception:
            pass

    def resolve_symbol(self, symbol: str) -> str:
        """VN30F1M (alias) -> mã hợp đồng thật. Mã thường/đã thật thì giữ nguyên."""
        s = str(symbol or "").upper()
        if s not in self.DERIVATIVE_TYPE_ALIASES:
            return symbol
        self._refresh_symbol_map()
        return self._symbol_map.get(s, symbol)

    def market_type_for_symbol(self, symbol: str) -> str:
        sym = str(symbol or "").upper()
        derivatives = {str(s).upper() for s in getattr(config, "CKPS_SYMBOLS", []) or []}
        if (
            sym.startswith("VN30F")
            or sym in derivatives
            or sym in self.DERIVATIVE_TYPE_ALIASES
            or sym in self._derivative_real_symbols
        ):
            return "DERIVATIVE"
        return "STOCK"

    def account_no_for_symbol(self, symbol: Optional[str] = None) -> str:
        market_type = self.market_type_for_symbol(symbol or "")
        if market_type == "STOCK":
            return self.stock_account_no or self.account_no or self.derivative_account_no
        return self.derivative_account_no or self.account_no or self.stock_account_no

    def quantity_unit_for_symbol(self, symbol: Optional[str] = None) -> str:
        return "HĐ" if self.market_type_for_symbol(symbol or "") == "DERIVATIVE" else "CP"

    def quantity_label_for_symbol(self, symbol: Optional[str] = None) -> str:
        return "Hợp đồng" if self.market_type_for_symbol(symbol or "") == "DERIVATIVE" else "Cổ phiếu"

    def get_orders(self, **params) -> List[Dict[str, Any]]:
        if self._is_paper_mode():
            return []
        symbol = params.pop("symbol", None)
        market_type = self.market_type_for_symbol(symbol) if symbol else self.market_type
        account_no = self.account_no_for_symbol(symbol) if symbol else self.account_no
        query = {"marketType": market_type, **params}
        ok, data, status_code, message = self._request("GET", f"/accounts/{account_no}/orders", params=query)
        if not ok:
            logger.error("DNSE get orders failed [%s]: %s", status_code, message or data)
            return []
        payload = _unwrap_payload(data, ("orders",))
        return payload if isinstance(payload, list) else []

    def _fallback_fee_profile(self, source: str = "fallback", market_type: str = "DERIVATIVE") -> BrokerFeeProfile:
        if str(market_type).upper() == "STOCK":
            return BrokerFeeProfile(
                broker_fee_per_contract=0.0,
                exchange_fee_per_contract=0.0,
                clearing_fee_per_contract=0.0,
                broker_fee_rate=float(getattr(config, "DNSE_STOCK_BROKER_FEE_RATE", 0.0) or 0.0),
                tax_rate=float(getattr(config, "DNSE_STOCK_TAX_RATE", 0.0) or 0.0),
                point_value=float(getattr(config, "DNSE_STOCK_PRICE_VALUE", 1000.0) or 1000.0),
                market_type="STOCK",
                quantity_unit="CP",
                fee_available=source != "fallback_stock_fee_unavailable",
                source=source,
            )
        return BrokerFeeProfile(
            broker_fee_per_contract=float(getattr(config, "DNSE_BROKER_FEE_PER_CONTRACT", 0.0) or 0.0),
            exchange_fee_per_contract=float(getattr(config, "DNSE_EXCHANGE_FEE_PER_CONTRACT", 2700.0) or 0.0),
            clearing_fee_per_contract=float(getattr(config, "DNSE_CLEARING_FEE_PER_CONTRACT", 2550.0) or 0.0),
            tax_rate=float(getattr(config, "DNSE_TAX_RATE", 0.0) or 0.0),
            point_value=float(getattr(config, "DNSE_POINT_VALUE", DNSE_POINT_VALUE) or DNSE_POINT_VALUE),
            market_type="DERIVATIVE",
            quantity_unit="HĐ",
            source=source,
        )

    def _parse_fee_profile_from_loan_packages(self, data: Any, market_type: str = "DERIVATIVE") -> Optional[BrokerFeeProfile]:
        payload = _unwrap_payload(data, ("loanPackages",))
        if isinstance(payload, dict):
            payload = payload.get("loanPackages") or payload.get("items") or [payload]
        if not isinstance(payload, list) or not payload:
            return None
        if str(market_type).upper() == "STOCK":
            stock_pkgs = [item for item in payload if isinstance(item, dict)]
            if not stock_pkgs:
                return None

            def _pkg_rate(p):
                return max(
                    _to_float(p.get("brokerFirmBuyingFeeRate"), 0.0),
                    _to_float(p.get("brokerFirmSellingFeeRate"), 0.0),
                )

            # DNSE trả nhiều gói (có gói phí 0 khuyến mãi) -> lấy gói phí CAO NHẤT cho
            # ước tính an toàn, tránh hiện phí 0 sai.
            package = max(stock_pkgs, key=_pkg_rate)
            buy_rate = _to_float(package.get("brokerFirmBuyingFeeRate"), 0.0)
            sell_rate = _to_float(package.get("brokerFirmSellingFeeRate"), buy_rate)
            broker_rate = max(buy_rate, sell_rate)
            return BrokerFeeProfile(
                broker_fee_per_contract=0.0,
                exchange_fee_per_contract=0.0,
                clearing_fee_per_contract=0.0,
                broker_fee_rate=broker_rate,
                tax_rate=float(getattr(config, "DNSE_STOCK_TAX_RATE", 0.0) or 0.0),
                point_value=float(getattr(config, "DNSE_STOCK_PRICE_VALUE", 1000.0) or 1000.0),
                market_type="STOCK",
                quantity_unit="CP",
                fee_available=True,
                source="dnse_stock_loan_package",
                raw=package,
            )
        package = next((item for item in payload if isinstance(item, dict) and item.get("tradingFee")), None)
        if not isinstance(package, dict):
            return None
        fee = package.get("tradingFee") or {}
        if not isinstance(fee, dict):
            return None
        broker_fee = _to_float(_first_value(fee, ("fixedTradingFee", "fixedDailyCloseTradingFee")), 0.0)
        if not broker_fee:
            progress = fee.get("progressTradingFee") or []
            if isinstance(progress, list) and progress:
                first = progress[0] if isinstance(progress[0], dict) else {}
                broker_fee = _to_float(first.get("fee"), 0.0)
        return BrokerFeeProfile(
            broker_fee_per_contract=broker_fee,
            exchange_fee_per_contract=float(getattr(config, "DNSE_EXCHANGE_FEE_PER_CONTRACT", 2700.0) or 0.0),
            clearing_fee_per_contract=float(getattr(config, "DNSE_CLEARING_FEE_PER_CONTRACT", 2550.0) or 0.0),
            tax_rate=float(getattr(config, "DNSE_TAX_RATE", 0.0) or 0.0),
            point_value=float(getattr(config, "DNSE_POINT_VALUE", DNSE_POINT_VALUE) or DNSE_POINT_VALUE),
            market_type="DERIVATIVE",
            quantity_unit="HĐ",
            source="dnse_loan_package",
            raw=package,
        )

    def get_fee_profile(self, symbol: Optional[str] = None, *, force_refresh: bool = False) -> BrokerFeeProfile:
        symbol_key = str(symbol or getattr(config, "DEFAULT_SYMBOL", "VN30F1M")).upper()
        market_type = self.market_type_for_symbol(symbol_key)
        account_no = self.account_no_for_symbol(symbol_key)
        cache_ttl = float(getattr(config, "DNSE_FEE_CACHE_TTL_SECONDS", 3600.0) or 0.0)
        cached = self._fee_profile_cache.get(symbol_key)
        if cached and not force_refresh and cache_ttl > 0 and (time.time() - self._fee_profile_cache_ts.get(symbol_key, 0.0)) < cache_ttl:
            return cached

        ok, data, status_code, message = self._request(
            "GET",
            f"/accounts/{account_no}/loan-packages",
            params={"marketType": market_type, "symbol": symbol_key},
        )
        if ok:
            fallback_source = "fallback_stock_fee_unavailable" if market_type == "STOCK" else "fallback_no_fee_package"
            profile = self._parse_fee_profile_from_loan_packages(data, market_type) or self._fallback_fee_profile(fallback_source, market_type)
        else:
            if status_code == 403 and not getattr(self, "_fee_profile_403_logged", False):
                logger.warning("DNSE loan packages failed [403]: %s. Using fallback fee profile.", message or data)
                self._fee_profile_403_logged = True
            fallback_source = "fallback_stock_fee_unavailable" if market_type == "STOCK" else "fallback_account_pending"
            profile = self._fallback_fee_profile(fallback_source, market_type)
        self._fee_profile_cache[symbol_key] = profile
        self._fee_profile_cache_ts[symbol_key] = time.time()
        return profile

    def calculate_trade_fee(self, symbol: str, price: float, contracts: float) -> float:
        return self.get_fee_profile(symbol).estimate_fee(price, contracts)

    def get_order_detail(self, order_id: str) -> Optional[Dict[str, Any]]:
        if self._is_paper_mode():
            return None
        ok, data, status_code, message = self._request("GET", f"/accounts/{self.account_no}/orders/{order_id}")
        if not ok:
            logger.error("DNSE order detail failed [%s]: %s", status_code, message or data)
            return None
        payload = _unwrap_payload(data)
        return payload if isinstance(payload, dict) else {"raw": data}

    def _position_from_raw(self, item: Dict[str, Any]) -> BrokerPosition:
        side = str(_first_value(item, ("side", "positionSide", "type", "positionType"), "")).upper()
        position_type = ORDER_TYPE_BUY if side in ("NB", "LONG", "BUY", "B") else ORDER_TYPE_SELL
        volume = _to_float(_first_value(item, ("volume", "quantity", "openQuantity", "netQuantity", "qty")), 0.0)
        entry = _to_float(_first_value(item, ("priceOpen", "price_open", "avgPrice", "averagePrice", "costPrice")), 0.0)
        current = _to_float(_first_value(item, ("priceCurrent", "marketPrice", "currentPrice", "lastPrice")), entry)
        position_id = str(_first_value(item, ("positionId", "id", "positionID"), ""))
        order_id = str(_first_value(item, ("orderId", "openOrderId", "orderID"), ""))
        ticket = position_id or order_id or str(_first_value(item, ("ticket",), ""))
        return BrokerPosition(
            ticket=ticket,
            position_id=position_id or ticket,
            order_id=order_id,
            symbol=str(_first_value(item, ("symbol", "symbolCode", "code"), "")).upper(),
            type=position_type,
            volume=volume,
            price_open=entry,
            price_current=current,
            profit=_to_float(_first_value(item, ("profit", "unrealizedPnl", "unrealizedProfit", "pnl")), 0.0),
            swap=_to_float(item.get("swap"), 0.0),
            commission=_to_float(_first_value(item, ("commission", "fee")), 0.0),
            sl=_to_float(_first_value(item, ("sl", "stopLoss", "cutLossPrice")), 0.0),
            tp=_to_float(_first_value(item, ("tp", "takeProfit", "takeProfitPrice")), 0.0),
            comment=str(_first_value(item, ("comment", "remark", "source"), "")),
            magic=_to_int(_first_value(item, ("magic", "magicNumber")), 0),
            time=_to_float(_first_value(item, ("time", "createdAt", "openTime")), time.time()),
            raw=item,
        )

    def get_positions(self) -> List[BrokerPosition]:
        if self._is_paper_mode():
            return self._paper().get_positions()
        cache_ttl = float(getattr(config, "DNSE_POSITIONS_CACHE_TTL_SECONDS", 2.0) or 0.0)
        if cache_ttl > 0 and (time.time() - self._positions_cache_ts) < cache_ttl:
            return list(self._positions_cache)

        # Reset cờ "mute 403" theo NGÀY (đang mute vĩnh viễn cả session) — để ngày mới thấy lỗi lại.
        today = time.strftime("%Y-%m-%d")
        if getattr(self, "_mute_reset_date", None) != today:
            DNSEConnector._positions_403_muted = False
            DNSEConnector._balances_403_muted = False
            self._positions_error_logged = False
            self._balances_error_logged = False
            self._mute_reset_date = today

        query_targets: List[Tuple[str, str]] = []
        for market_type, account_no in (
            ("DERIVATIVE", self.derivative_account_no or self.account_no),
            ("STOCK", self.stock_account_no or self.account_no),
        ):
            if account_no and (market_type, account_no) not in query_targets:
                query_targets.append((market_type, account_no))

        positions: List[BrokerPosition] = []
        had_ok = False
        for market_type, account_no in query_targets:
            ok, data, status_code, message = self._request(
                "GET",
                f"/accounts/{account_no}/positions",
                params={"marketType": market_type},
            )
            if not ok:
                if status_code == 403:
                    if not DNSEConnector._positions_403_muted:
                        logger.warning("DNSE positions failed [403]: %s. Muting further 403s.", message or data)
                        DNSEConnector._positions_403_muted = True
                    continue
                if not getattr(self, "_positions_error_logged", False):
                    logger.warning("DNSE positions failed [%s]: %s. Muting further position errors.", status_code, message or data)
                    self._positions_error_logged = True
                continue
            had_ok = True
            payload = _unwrap_payload(data, ("positions",))
            if isinstance(payload, dict):
                payload = [payload]
            if isinstance(payload, list):
                positions.extend(self._position_from_raw(item) for item in payload if isinstance(item, dict))

        if not had_ok:
            # Cả 2 account đều fail -> bot/UI sẽ tưởng 0 vị thế. Cảnh báo (throttle 60s).
            now_ts = time.time()
            if (now_ts - getattr(self, "_positions_allfail_log_ts", 0.0)) > 60.0:
                logger.error("⚠️ KHÔNG tải được vị thế từ TẤT CẢ tài khoản — có thể tưởng 0 lệnh. Kiểm tra kết nối/token.")
                self._positions_allfail_log_ts = now_ts
            self._positions_cache = []
            self._positions_cache_ts = time.time()
            return []
        try:
            settlement_ledger.enrich_positions(self.account_no, positions)
        except Exception as exc:
            logger.warning("Settlement ledger enrich failed: %s", exc)
        self._positions_cache = list(positions)
        self._positions_cache_ts = time.time()
        return positions

    def get_all_open_positions(self) -> List[BrokerPosition]:
        return self.get_positions()

    def _order_result(self, ok: bool, data: Any, status_code: int, message: str = "") -> BrokerOrderResult:
        payload = _unwrap_payload(data) if isinstance(data, dict) else {}
        if not isinstance(payload, dict):
            payload = {}
        order_id = str(_first_value(payload, ("orderId", "id", "orderID"), ""))
        position_id = str(_first_value(payload, ("positionId", "positionID"), ""))
        status = str(_first_value(payload, ("status", "orderStatus"), ""))
        result_message = str(_first_value(payload, ("message", "description", "error"), message or ""))
        return BrokerOrderResult(
            ok=ok,
            order_id=order_id,
            position_id=position_id,
            status=status,
            message=result_message,
            error="" if ok else (message or result_message),
            status_code=status_code,
            raw=data if isinstance(data, dict) else {"raw": data},
        )

    def _normalize_side(self, order_type: Any) -> str:
        text = str(order_type).upper()
        return "NB" if text in ("0", "BUY", "LONG", "NB") else "NS"

    def _normalize_stock_order(self, symbol, order_type, volume, price, order_kind):
        """Chuẩn hoá khối lượng + kiểm luật cổ phiếu, dùng chung cho paper lẫn real.

        Trả (quantity:int, err:BrokerOrderResult|None).
        - Mọi mã: làm tròn số nguyên, tối thiểu 1.
        - Cổ phiếu (CKCS): lô chẵn 100 (làm tròn xuống, dưới 1 lô -> STOCK_ODD_LOT);
          lệnh LO (giá>0) phải nằm trong biên trần/sàn (-> PRICE_OUT_OF_BAND).
        - Phái sinh: không áp lô 100/biên ở đây.
        """
        quantity = max(1, int(round(float(volume or 0))))
        symbol_key = str(symbol or "").strip().upper()
        if not settlement.is_cash_stock(symbol_key):
            return quantity, None

        round_lot = int(getattr(config, "STOCK_ROUND_LOT", 100) or 100)
        quantity = stock_rules.round_lot_down(quantity, round_lot)
        if quantity < round_lot:
            return quantity, BrokerOrderResult(
                ok=False,
                error="STOCK_ODD_LOT",
                message=f"Cổ phiếu {symbol_key}: khối lượng phải là bội số {round_lot} (tối thiểu {round_lot} CP).",
            )

        order_type_name = order_kind or ("LO" if float(price or 0) > 0 else "MOK")
        if order_type_name == "LO" and float(price or 0) > 0:
            tick = self.get_tick(symbol_key)
            if tick is not None:
                band_pct = stock_rules.band_pct_for(symbol_key)
                fl, ce = stock_rules.resolve_band(tick.reference, tick.ceiling, tick.floor, band_pct)
                if not stock_rules.price_in_band(price, fl, ce):
                    return quantity, BrokerOrderResult(
                        ok=False,
                        error="PRICE_OUT_OF_BAND",
                        message=f"Cổ phiếu {symbol_key}: giá {float(price):g} ngoài biên [sàn {fl:g} .. trần {ce:g}].",
                    )
        return quantity, None

    def send_order(
        self,
        symbol: str,
        order_type: Any,
        volume: float,
        price: float = 0.0,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "",
        magic: int = 0,
        order_kind: Optional[str] = None,
    ) -> BrokerOrderResult:
        # Chuẩn hoá khối lượng + luật CK (lô 100 + biên trần/sàn) — áp cho CẢ paper lẫn real
        # để test paper sát thực tế. Phái sinh chỉ làm tròn số nguyên.
        quantity, norm_err = self._normalize_stock_order(symbol, order_type, volume, price, order_kind)
        if norm_err is not None:
            return norm_err
        if self._is_paper_mode():
            return self._paper().place_order(
                symbol,
                order_type,
                quantity,
                price=price,
                sl=sl,
                tp=tp,
                magic=magic,
                comment=comment,
            )
        if not bool(getattr(config, "AUTO_TRADE_ENABLED", False)):
            return BrokerOrderResult(
                ok=False,
                error="AUTO_TRADE_DISABLED",
                message="AUTO_TRADE_ENABLED is False; refusing to send a new live DNSE order.",
            )
        side = self._normalize_side(order_type)
        order_type_name = order_kind or ("LO" if float(price or 0) > 0 else "MOK")
        market_type = self.market_type_for_symbol(symbol)
        account_no = self.account_no_for_symbol(symbol)
        symbol_key = str(symbol or "").strip().upper()
        is_stock = settlement.is_cash_stock(symbol_key)
        if side == "NS" and is_stock:
            enriched = settlement_ledger.enrich_positions(self.account_no, self.get_positions())
            available = settlement.available_to_sell(enriched, symbol_key)
            pending = settlement.pending_to_settle(enriched, symbol_key)
            if available < quantity:
                msg = (
                    f"Cổ phiếu {symbol_key} chỉ có {available:g} đã về, cần bán {quantity:g}; "
                    f"đang chờ về {pending:g}. Không bán khống CKCS."
                )
                return BrokerOrderResult(ok=False, error="STOCK_NOT_SETTLED_T2", message=msg)
        symbol = self.resolve_symbol(symbol)  # gửi mã hợp đồng thật cho lệnh phái sinh
        payload = {
            "accountNo": account_no,
            "symbol": str(symbol).upper(),
            "side": side,
            "quantity": quantity,
            "orderType": order_type_name,
            "price": float(price or 0),
        }
        if comment:
            payload["remark"] = comment
        if magic:
            payload["magicNumber"] = int(magic)
        if sl:
            payload["stopLoss"] = float(sl)
        if tp:
            payload["takeProfit"] = float(tp)

        ok, data, status_code, message = self._request(
            "POST",
            "/accounts/orders",
            params={"marketType": market_type, "orderCategory": self.order_category},
            json_payload=payload,
            require_trading_token=True,
        )
        result = self._order_result(ok, data, status_code, message)
        if not result.ok:
            logger.error("DNSE order failed: %s", result.error or result.raw)
        elif side == "NB" and is_stock:
            ticket = result.position_id or result.order_id or result.ticket
            buy_date = datetime.now()
            try:
                settle = settlement.settle_date_str(buy_date, self.get_working_dates())
                settlement_ledger.record_buy(self.account_no, ticket, symbol_key, quantity, buy_date, settle)
            except Exception as exc:
                logger.warning("Settlement ledger record failed for %s %s: %s", symbol_key, ticket, exc)
        return result

    def place_order(self, symbol, order_type, lot, sl, tp, magic=0, comment="", order_kind=None, price=0.0) -> BrokerOrderResult:
        # order_kind: None -> tự LO/MOK; "ATO"/"ATC" -> lệnh phiên định kỳ mở/đóng cửa.
        return self.send_order(symbol, order_type, lot, price=price, sl=sl, tp=tp, comment=comment, magic=magic, order_kind=order_kind)

    def replace_order(self, order_id: str, *, price: Optional[float] = None, quantity: Optional[float] = None, account_no: Optional[str] = None, symbol: Optional[str] = None) -> BrokerOrderResult:
        if self._is_paper_mode():
            return BrokerOrderResult(ok=False, order_id=str(order_id), error="PAPER_REPLACE_UNSUPPORTED", message="Paper orders are filled immediately.")
        _account_no = account_no or (self.account_no_for_symbol(symbol) if symbol else self.account_no)
        _market_type = self.market_type_for_symbol(symbol) if symbol else self.market_type
        payload: Dict[str, Any] = {}
        if price is not None:
            payload["price"] = float(price)
        if quantity is not None:
            payload["quantity"] = max(1, int(round(float(quantity))))
        ok, data, status_code, message = self._request(
            "PUT",
            f"/accounts/{_account_no}/orders/{order_id}",
            params={"marketType": _market_type},
            json_payload=payload,
            require_trading_token=True,
        )
        return self._order_result(ok, data, status_code, message)

    def cancel_order(self, order_id: str, *, account_no: Optional[str] = None, symbol: Optional[str] = None) -> BrokerOrderResult:
        if self._is_paper_mode():
            return BrokerOrderResult(ok=False, order_id=str(order_id), error="PAPER_CANCEL_UNSUPPORTED", message="Paper orders are filled immediately.")
        _account_no = account_no or (self.account_no_for_symbol(symbol) if symbol else self.account_no)
        _market_type = self.market_type_for_symbol(symbol) if symbol else self.market_type
        ok, data, status_code, message = self._request(
            "DELETE",
            f"/accounts/{_account_no}/orders/{order_id}",
            params={"marketType": _market_type},
            require_trading_token=True,
        )
        return self._order_result(ok, data, status_code, message)

    def set_position_pnl_config(self, position_id: str, sl: float = 0.0, tp: float = 0.0) -> BrokerOrderResult:
        payload = {}
        if sl:
            payload["stopLoss"] = float(sl)
        if tp:
            payload["takeProfit"] = float(tp)
        if not payload:
            return BrokerOrderResult(ok=True, position_id=str(position_id), message="No PnL config change requested.")
        ok, data, status_code, message = self._request(
            "POST",
            f"/accounts/positions/{position_id}/pnl-configs",
            json_payload=payload,
            require_trading_token=True,
        )
        return self._order_result(ok, data, status_code, message)

    def modify_position(self, position_or_ticket: Any, sl: float = 0.0, tp: float = 0.0) -> BrokerOrderResult:
        if self._is_paper_mode():
            return self._paper().modify_position(position_or_ticket, sl, tp)
        position_id = getattr(position_or_ticket, "position_id", None) or getattr(position_or_ticket, "ticket", None) or position_or_ticket
        result = self.set_position_pnl_config(str(position_id), sl, tp)
        if not result.ok:
            logger.warning("DNSE PnL config update failed/not supported for %s: %s", position_id, result.error)
        return result

    def close_position(self, position_or_ticket: Any, comment: str = "") -> BrokerOrderResult:
        if self._is_paper_mode():
            return self._paper().close_position(position_or_ticket, comment)
        position_id = getattr(position_or_ticket, "position_id", None) or getattr(position_or_ticket, "ticket", None) or position_or_ticket
        pos_obj = position_or_ticket if hasattr(position_or_ticket, "symbol") else None
        if pos_obj is None and isinstance(position_or_ticket, (str, int)):
            pos_key = str(position_id or "")
            pos_obj = next(
                (
                    p
                    for p in self.get_positions()
                    if str(getattr(p, "position_id", "") or getattr(p, "ticket", "") or "") == pos_key
                    or str(getattr(p, "ticket", "") or "") == pos_key
                ),
                None,
            )
        if pos_obj is not None and settlement.is_cash_stock(getattr(pos_obj, "symbol", "")):
            enriched = settlement_ledger.enrich_positions(self.account_no, [pos_obj])
            settle = (enriched[0] or {}).get("settle_date") if enriched else ""
            if settle and not settlement.is_settled(settle):
                msg = f"Cổ phiếu {getattr(pos_obj, 'symbol', '')} chưa về T+2 (về {str(settle)[:10]}), chưa đóng được."
                return BrokerOrderResult(ok=False, position_id=str(position_id), error="STOCK_NOT_SETTLED_T2", message=msg)
        ok, data, status_code, message = self._request(
            "POST",
            f"/accounts/positions/{position_id}/close",
            json_payload={"comment": comment} if comment else None,
            require_trading_token=True,
        )
        result = self._order_result(ok, data, status_code, message)
        if not result.position_id:
            result.position_id = str(position_id)
        if result.ok and pos_obj is not None and settlement.is_cash_stock(getattr(pos_obj, "symbol", "")):
            settlement_ledger.drop(self.account_no, position_id)
        return result

    def close_all_positions(self) -> List[BrokerOrderResult]:
        return [self.close_position(pos) for pos in self.get_positions()]

    def get_ohlc(self, symbol: str, resolution: str, from_ts: int, to_ts: int) -> Optional[Dict[str, Any]]:
        market_type = self.market_type_for_symbol(symbol)
        # LƯU Ý: endpoint OHLC nhận symbolType alias (VN30F1M) cho phái sinh — KHÔNG resolve
        # sang mã hợp đồng thật (41I1G6000 trả về 0 nến). Chỉ trades/quotes mới cần mã thật.
        ok, data, status_code, message = self._request(
            "GET",
            "/price/ohlc",
            params={
                "symbol": str(symbol).upper(),
                "type": market_type,
                "resolution": resolution,
                "from": str(int(from_ts)),
                "to": str(int(to_ts)),
            },
        )
        if not ok:
            logger.error("DNSE OHLC failed [%s]: %s", status_code, message or data)
            return None
        return data if isinstance(data, dict) else None

    def get_latest_trade(self, symbol: str, board_id: str = "G1") -> Optional[Dict[str, Any]]:
        symbol = self.resolve_symbol(symbol)
        ok, data, _status_code, _message = self._request(
            "GET",
            f"/price/{str(symbol).upper()}/trades/latest",
            params={"boardId": board_id},
        )
        if not ok:
            return None
        payload = _unwrap_payload(data, ("trades",))
        if isinstance(payload, list):
            return payload[0] if payload else None
        return payload if isinstance(payload, dict) else None

    def get_latest_quote(self, symbol: str, board_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        symbol = self.resolve_symbol(symbol)
        params = {"boardId": board_id} if board_id else {}
        ok, data, _status_code, _message = self._request(
            "GET",
            f"/price/{str(symbol).upper()}/quotes/latest",
            params=params,
        )
        if not ok:
            return None
        payload = _unwrap_payload(data, ("quotes",))
        if isinstance(payload, list):
            return payload[0] if payload else None
        return payload if isinstance(payload, dict) else None

    def get_working_dates(self) -> List[str]:
        """Danh sách ngày làm việc (YYYY-MM-DD) từ DNSE — cache 1 ngày — để tính T+2."""
        now = time.time()
        if self._working_dates and (now - self._working_dates_ts) < 86400.0:
            return self._working_dates
        ok, data, _s, _m = self._request("GET", "/market/working-dates")
        if ok and isinstance(data, dict):
            dates = [str(d)[:10] for d in (data.get("workingDates") or []) if d]
            if dates:
                self._working_dates = sorted(dates)
                self._working_dates_ts = now
        return self._working_dates

    def get_tick(self, symbol: str) -> Optional[BrokerTick]:
        cache_ttl = float(getattr(config, "DNSE_TICK_CACHE_TTL_SECONDS", 2.0) or 0.0)
        sym_key = str(symbol).upper()
        if cache_ttl > 0 and sym_key in self._tick_cache and (time.time() - self._tick_cache_ts.get(sym_key, 0.0)) < cache_ttl:
            return self._tick_cache[sym_key]
        trade = self.get_latest_trade(symbol) or {}
        quote = self.get_latest_quote(symbol) or {}
        bid = ask = 0.0
        bids = quote.get("bid") or quote.get("bids") or []
        offers = quote.get("offer") or quote.get("ask") or quote.get("offers") or []
        if bids:
            bid = _to_float((bids[0] or {}).get("price") if isinstance(bids[0], dict) else bids[0])
        if offers:
            ask = _to_float((offers[0] or {}).get("price") if isinstance(offers[0], dict) else offers[0])
        last = _to_float(_first_value(trade, ("matchPrice", "price", "lastPrice")), 0.0)
        if not bid:
            bid = last
        if not ask:
            ask = last
        if not (last or bid or ask):
            return None
        # Giá trần/sàn/tham chiếu: DNSE có thể nằm ở trade hoặc quote -> gộp tìm.
        merged = {**(quote if isinstance(quote, dict) else {}), **(trade if isinstance(trade, dict) else {})}
        ceiling = _to_float(_first_value(merged, ("ceilingPrice", "ceiling", "maxPrice")), 0.0)
        floor = _to_float(_first_value(merged, ("floorPrice", "floor", "minPrice")), 0.0)
        reference = _to_float(_first_value(merged, ("referencePrice", "refPrice", "basicPrice", "priorClosePrice")), 0.0)
        tick = BrokerTick(
            symbol=sym_key,
            bid=bid,
            ask=ask,
            last=last or bid or ask,
            high=_to_float(_first_value(trade, ("highestPrice", "high")), 0.0),
            low=_to_float(_first_value(trade, ("lowestPrice", "low")), 0.0),
            open=_to_float(_first_value(trade, ("openPrice", "open")), 0.0),
            spread=round((ask - bid), 4) if ask and bid else 0.0,
            ceiling=ceiling,
            floor=floor,
            reference=reference,
            raw={"trade": trade, "quote": quote},
        )
        self._tick_cache[sym_key] = tick
        self._tick_cache_ts[sym_key] = time.time()
        return tick

    def get_symbol_info(self, symbol: str, poll_tick: bool = True) -> BrokerSymbolInfo:
        market_type = self.market_type_for_symbol(symbol)
        # [FIX 429] poll_tick=False: chỉ cần thông số hợp đồng (tĩnh theo loại thị trường),
        # không gọi /trades|quotes/latest -> tránh đập endpoint phái sinh nóng từ UI mỗi vòng.
        tick = self.get_tick(symbol) if poll_tick else None
        is_derivative = market_type == "DERIVATIVE"
        point_value = (
            float(getattr(config, "DNSE_POINT_VALUE", DNSE_POINT_VALUE) or DNSE_POINT_VALUE)
            if is_derivative
            else float(getattr(config, "DNSE_STOCK_PRICE_VALUE", 1000.0) or 1000.0)
        )
        # Cổ phiếu: lô chẵn 100 -> auto-lot tự làm tròn bội 100. Phái sinh giữ step=1.
        round_lot = float(getattr(config, "STOCK_ROUND_LOT", 100) or 100)
        volume_min = 1.0 if is_derivative else round_lot
        volume_step = float(getattr(config, "LOT_STEP", 1.0) or 1.0) if is_derivative else round_lot
        return BrokerSymbolInfo(
            symbol=str(symbol).upper(),
            point=float(getattr(config, "DNSE_PRICE_POINT", 0.1)),
            trade_contract_size=point_value,
            volume_min=volume_min,
            volume_max=float(getattr(config, "MAX_LOT_SIZE", 200.0) or 200.0) if is_derivative else 1000000.0,
            volume_step=volume_step,
            spread=float(tick.spread if tick else 0.0),
            market_type=market_type,
            quantity_label="Hợp đồng" if is_derivative else "Cổ phiếu",
            quantity_unit="HĐ" if is_derivative else "CP",
            raw=tick.raw if tick else {},
        )

    def calculate_profit(self, symbol: str, side: str, volume: float, entry_price: float, exit_price: float) -> float:
        direction = str(side).upper()
        diff = float(exit_price) - float(entry_price)
        if direction in ("SHORT", "SELL", "NS", "1"):
            diff = -diff
        point_value = float(self.get_symbol_info(symbol).trade_contract_size or 1.0)
        return diff * float(volume) * point_value

    def calculate_lot_size(
        self,
        symbol: str,
        risk_value: float,
        sl_price: float,
        order_type: Any,
        strict_fee_per_lot: float = 0.0,
        entry_price: Optional[float] = None,
    ) -> Tuple[Optional[float], float]:
        tick = self.get_tick(symbol)
        if entry_price is None:
            if tick:
                entry_price = tick.ask if self._normalize_side(order_type) == "NB" else tick.bid
            else:
                entry_price = 0.0
        distance = abs(float(entry_price or 0.0) - float(sl_price or 0.0))
        if distance <= 0:
            return None, sl_price
        point_value = float(self.get_symbol_info(symbol).trade_contract_size or 1.0)
        risk_per_contract = (distance * point_value) + float(strict_fee_per_lot or 0.0)
        if risk_per_contract <= 0:
            return None, sl_price
        raw_qty = float(risk_value) / risk_per_contract
        info = self.get_symbol_info(symbol)
        step = max(float(info.volume_step or 1.0), 1.0)
        qty = round(raw_qty / step) * step
        qty = max(float(info.volume_min), min(float(qty), float(info.volume_max)))
        return qty, float(sl_price)
