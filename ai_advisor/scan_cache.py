# -*- coding: utf-8 -*-
"""Kho lưu snapshot kết quả quét của daemon (phục vụ AI Advisor).

LEGO: module độc lập, daemon chỉ gọi maybe_record()/flush() bọc try/except.
Không đụng logic signal — chỉ ĐỌC dfs/context/signal đã tính sẵn rồi lưu lại.
Logic tính toán là hàm thuần để test không cần API/network.
"""
import json
import logging
import os
import time
from datetime import datetime

import pandas as pd

import config
from ai_advisor import paths

logger = logging.getLogger("BotDaemon")

SCHEMA_VERSION = 1
SIGNAL_DEDUP_MINUTES = 30
WEEK_BARS = 5  # 1 tuần giao dịch VN = 5 phiên

# Phiên khớp lệnh liên tục HOSE/HNX (xấp xỉ, đủ dùng để pro-rate volume)
_SESSION_WINDOWS = ((9 * 60, 11 * 60 + 30), (13 * 60, 14 * 60 + 45))


# =============================================================================
# Hàm thuần — tính toán snapshot
# =============================================================================
def _f(value, nd=4):
    """float an toàn: NaN/None/lỗi -> None, còn lại round nd chữ số."""
    try:
        v = float(value)
        if pd.isna(v):
            return None
        return round(v, nd)
    except Exception:
        return None


def session_elapsed_fraction(now):
    """Tỷ lệ phiên đã trôi (0..1) theo giờ VN — để pro-rate volume nến ngày."""
    minute = now.hour * 60 + now.minute
    total = sum(end - start for start, end in _SESSION_WINDOWS)
    elapsed = 0
    for start, end in _SESSION_WINDOWS:
        if minute >= end:
            elapsed += end - start
        elif minute > start:
            elapsed += minute - start
    return round(elapsed / total, 4) if total else 1.0


def pick_daily_df(dfs):
    """Tìm df khung ngày trong dfs (G0..G3) theo khoảng cách thời gian giữa nến."""
    for grp in ("G0", "G1", "G2", "G3"):
        df = dfs.get(grp)
        if df is None or df.empty or "time" not in df.columns or len(df) < 2:
            continue
        try:
            delta = (df["time"].iloc[-1] - df["time"].iloc[-2]).total_seconds()
            if delta >= 80000:  # ~1 ngày (chấp nhận lệch cuối tuần)
                return grp, df
        except Exception:
            continue
    return None, None


def _compute_price_block(daily_df, current_price, now):
    if daily_df is None or daily_df.empty:
        return {"close": None, "current": _f(current_price), "pct_1d": None,
                "pct_1w": None, "high_1w": None, "low_1w": None, "daily_bar_is_today": False}
    closes = daily_df["close"]
    last_bar_is_today = False
    try:
        last_bar_is_today = daily_df["time"].iloc[-1].date() == now.date()
    except Exception:
        pass
    # Nến cuối là hôm nay -> nến trước là phiên hôm qua; nếu không, nến cuối chính là phiên gần nhất
    prev_idx = -2 if (last_bar_is_today and len(closes) >= 2) else -1
    prev_close = _f(closes.iloc[prev_idx])
    ref_price = _f(current_price) or _f(closes.iloc[-1])

    pct_1d = None
    if ref_price is not None and prev_close:
        pct_1d = round((ref_price - prev_close) / prev_close * 100, 2)

    pct_1w = None
    week_idx = prev_idx - WEEK_BARS + 1
    if len(closes) >= abs(week_idx):
        week_close = _f(closes.iloc[week_idx])
        if ref_price is not None and week_close:
            pct_1w = round((ref_price - week_close) / week_close * 100, 2)

    tail = daily_df.tail(WEEK_BARS)
    return {
        "close": _f(closes.iloc[-1]),
        "current": ref_price,
        "pct_1d": pct_1d,
        "pct_1w": pct_1w,
        "high_1w": _f(tail["high"].max()),
        "low_1w": _f(tail["low"].min()),
        "daily_bar_is_today": bool(last_bar_is_today),
    }


def _compute_volume_block(daily_df, market_open, now):
    if daily_df is None or daily_df.empty or "volume" not in daily_df.columns:
        return {"today": None, "avg20": None, "ratio": None, "projected_ratio": None,
                "trend_5d": None, "is_partial_bar": bool(market_open)}
    vols = daily_df["volume"]
    last_bar_is_today = False
    try:
        last_bar_is_today = daily_df["time"].iloc[-1].date() == now.date()
    except Exception:
        pass
    today_vol = _f(vols.iloc[-1], 0) if last_bar_is_today else None
    closed = vols.iloc[:-1] if last_bar_is_today else vols

    avg20 = _f(closed.tail(20).mean(), 0) if len(closed) else None
    ratio = None
    projected = None
    is_partial = bool(market_open and last_bar_is_today)
    if today_vol and avg20:
        ratio = round(today_vol / avg20, 2)
        if is_partial:
            frac = max(session_elapsed_fraction(now), 0.1)
            projected = round((today_vol / frac) / avg20, 2)

    trend_5d = None
    if len(closed) >= 10:
        recent = closed.tail(WEEK_BARS).mean()
        older = closed.tail(WEEK_BARS * 2).head(WEEK_BARS).mean()
        if older and not pd.isna(older) and older > 0:
            chg = (recent - older) / older
            trend_5d = "tăng" if chg > 0.1 else ("giảm" if chg < -0.1 else "đi ngang")

    return {"today": today_vol, "avg20": avg20, "ratio": ratio,
            "projected_ratio": projected, "trend_5d": trend_5d, "is_partial_bar": is_partial}


def _extract_indicators(df, grp, context):
    """Đọc giá trị indicator thô từ các cột pandas-ta (None nếu indicator tắt)."""
    if df is None or df.empty:
        return {}
    out = {}
    last = df.iloc[-1]
    close = _f(last.get("close"))

    def first_col(prefix):
        for c in df.columns:
            if c.startswith(prefix):
                return c
        return None

    for key, prefix in (("rsi", "RSI_"), ("macd", "MACD_"), ("macd_hist", "MACDh_"),
                        ("macd_signal", "MACDs_"), ("atr", "ATRr_"), ("adx", "ADX_"),
                        ("stoch_k", "STOCHk_"), ("stoch_d", "STOCHd_"),
                        ("supertrend_dir", "SUPERTd_")):
        col = first_col(prefix)
        if col is not None:
            out[key] = _f(last[col])

    emas = {}
    for c in df.columns:
        if c.startswith("EMA_"):
            emas[c] = _f(last[c])
    if emas:
        out["ema"] = emas

    bbl, bbu = first_col("BBL_"), first_col("BBU_")
    if bbl and bbu and close is not None:
        lo, hi = _f(last[bbl]), _f(last[bbu])
        if lo is not None and hi is not None and hi > lo:
            out["bb_pos_pct"] = round((close - lo) / (hi - lo) * 100, 1)

    ema20 = context.get(f"ema20_{grp}")
    if ema20 and close is not None:
        out["close_vs_ema20_pct"] = round((close - float(ema20)) / float(ema20) * 100, 2)
    return out


def compute_snapshot(dfs, context, signal, now=None):
    """Chụp 1 mẫu từ kết quả fetch_data_v4 + generate_signal_v4 (hàm thuần)."""
    now = now or datetime.now()
    market_open = bool(context.get("market_open", True))
    daily_grp, daily_df = pick_daily_df(dfs)

    indicators = {}
    for grp in ("G0", "G1", "G2", "G3"):
        vals = _extract_indicators(dfs.get(grp), grp, context)
        if vals:
            indicators[grp] = vals

    return {
        "price": _compute_price_block(daily_df, context.get("current_price"), now),
        "volume": _compute_volume_block(daily_df, market_open, now),
        "indicators": indicators,
        "daily_group": daily_grp,
        "bot": {
            "trend_G0": context.get("trend_G0"),
            "trend_G1": context.get("trend_G1"),
            "trend_G2": context.get("trend_G2"),
            "trend_G3": context.get("trend_G3"),
            "market_mode": context.get("market_mode"),
            "mode_source": context.get("mode_source"),
            "block_reason": context.get("block_reason"),
            "latest_signal": signal,
            "group_signals": context.get("group_signals"),
        },
    }


# =============================================================================
# Hàm thuần — merge/prune/derive trên dict cache
# =============================================================================
def empty_cache():
    return {"schema_version": SCHEMA_VERSION, "updated_at": None, "symbols": {}}


def _day_entry(cache, sym, day):
    sym_node = cache["symbols"].setdefault(sym, {"days": {}})
    return sym_node["days"].setdefault(day, {
        "samples": 0, "first_scan": None, "last_scan": None, "eod_final": False, "signals": [],
    })


def merge_sample(cache, sym, snapshot, now=None, eod=False):
    now = now or datetime.now()
    day = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H:%M")
    entry = _day_entry(cache, sym, day)
    entry.update({k: snapshot[k] for k in ("price", "volume", "indicators", "bot", "daily_group")})
    entry["samples"] += 1
    entry["first_scan"] = entry["first_scan"] or hhmm
    entry["last_scan"] = hhmm
    if eod:
        entry["eod_final"] = True
    cache["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    return entry


def record_signal_event(cache, sym, side, context, now=None):
    """Ghi ngay tín hiệu BUY/SELL daemon bắn ra (dedup cùng chiều trong 30 phút)."""
    now = now or datetime.now()
    day = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H:%M")
    entry = _day_entry(cache, sym, day)
    for ev in reversed(entry["signals"]):
        if ev.get("side") == side:
            try:
                prev = datetime.strptime(f"{day} {ev['time']}", "%Y-%m-%d %H:%M")
                if (now - prev).total_seconds() < SIGNAL_DEDUP_MINUTES * 60:
                    return False
            except Exception:
                pass
            break
    entry["signals"].append({
        "time": hhmm,
        "side": side,
        "mode": context.get("market_mode"),
        "groups": context.get("group_signals"),
        "note": context.get("block_reason"),
    })
    cache["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    return True


def prune(cache, retention_days=None):
    keep = int(retention_days or getattr(config, "SCAN_SNAPSHOT_RETENTION_DAYS", 10))
    for sym in list(cache.get("symbols", {})):
        days = cache["symbols"][sym].get("days", {})
        for day in sorted(days)[:-keep] if len(days) > keep else []:
            days.pop(day, None)
        if not days:
            cache["symbols"].pop(sym, None)
    return cache


def derive_weekly(sym_node):
    """Đếm tín hiệu BUY/SELL trong các ngày đang giữ (≈ 2 tuần)."""
    buy = sell = 0
    for day_data in sym_node.get("days", {}).values():
        for ev in day_data.get("signals", []):
            if ev.get("side") == "BUY":
                buy += 1
            elif ev.get("side") == "SELL":
                sell += 1
    return {"buy": buy, "sell": sell}


# =============================================================================
# I/O — atomic write (pattern chống WinError 5 như bot_daemon)
# =============================================================================
def load_cache(path=None):
    path = path or paths.scan_cache_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("symbols"), dict):
                data.setdefault("schema_version", SCHEMA_VERSION)
                return data
    except Exception as e:
        logger.warning(f"scan_cache: file hỏng, khởi tạo lại ({e})")
    return empty_cache()


def save_cache(cache, path=None):
    path = path or paths.scan_cache_path()
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    for attempt in range(5):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        except (PermissionError, OSError) as e:
            time.sleep(0.05)
            if attempt == 4:
                logger.error(f"scan_cache: lỗi ghi sau 5 lần thử: {e}")
    return False


# =============================================================================
# Recorder — trạng thái cho daemon (1 instance/process)
# =============================================================================
class ScanSnapshotRecorder:
    def __init__(self):
        self._cache = None
        self._cache_path = None
        self._dirty = False
        self._last_sample_ts = {}

    def _ensure_loaded(self):
        current_path = paths.scan_cache_path()
        if self._cache is None or self._cache_path != current_path:
            self._cache = load_cache(current_path)
            self._cache_path = current_path
            self._dirty = False
            self._last_sample_ts = {}

    def maybe_record(self, sym, dfs, context, signal, now=None):
        """Gọi mỗi lần daemon quét xong 1 mã. Tự quyết định lưu hay bỏ qua."""
        now = now or datetime.now()
        self._ensure_loaded()
        market_open = bool(context.get("market_open", True))

        # 1. Tín hiệu BUY/SELL: ghi NGAY (chỉ trong phiên)
        if market_open and signal in (1, -1):
            side = "BUY" if signal == 1 else "SELL"
            if record_signal_event(self._cache, sym, side, context, now=now):
                self._dirty = True

        # 2. Mẫu định kỳ theo interval
        interval_s = float(getattr(config, "SCAN_SNAPSHOT_INTERVAL_MINUTES", 15)) * 60
        last_ts = self._last_sample_ts.get(sym, 0.0)
        due = (time.time() - last_ts) >= interval_s

        day = now.strftime("%Y-%m-%d")
        entry = self._cache["symbols"].get(sym, {}).get("days", {}).get(day)

        if market_open:
            if due:
                snapshot = compute_snapshot(dfs, context, signal, now=now)
                merge_sample(self._cache, sym, snapshot, now=now)
                self._last_sample_ts[sym] = time.time()
                self._dirty = True
        else:
            # Ngoài giờ: chốt EOD 1 lần nếu hôm nay LÀ ngày giao dịch
            # (nến ngày cuối = hôm nay — sau ATC cache bucket tự miss nên số liệu final)
            already_final = bool(entry and entry.get("eod_final"))
            if not already_final:
                snapshot = compute_snapshot(dfs, context, signal, now=now)
                if snapshot["price"].get("daily_bar_is_today"):
                    merge_sample(self._cache, sym, snapshot, now=now, eod=True)
                    self._last_sample_ts[sym] = time.time()
                    self._dirty = True

    def flush(self):
        """Gọi 1 lần cuối mỗi vòng quét — chỉ ghi đĩa khi có thay đổi."""
        if self._cache is not None and self._dirty:
            prune(self._cache)
            if save_cache(self._cache, self._cache_path):
                self._dirty = False

    def status(self):
        self._ensure_loaded()
        syms = self._cache.get("symbols", {})
        return {
            "updated_at": self._cache.get("updated_at"),
            "symbols": len(syms),
            "days": max((len(s.get("days", {})) for s in syms.values()), default=0),
        }


recorder = ScanSnapshotRecorder()
