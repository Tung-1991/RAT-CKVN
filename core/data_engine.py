# -*- coding: utf-8 -*-
# FILE: core/data_engine.py
# V4.2.1: DYNAMIC TA OPTIMIZATION & MULTI-TIMEFRAME (KAISER EDITION)

import pandas as pd
import numpy as np
import json
import os
import logging
import time
import config
import pandas_ta as ta 
from core.storage_manager import get_brain_settings_for_symbol
from core.market_structure import analyze_market_structure, write_structure_context
from core.dnse_connector import DNSEConnector
from core.dnse_ws import market_ws

logger = logging.getLogger("DataEngine")

# Throttle cảnh báo OHLC lỗi lặp lại (cùng symbol+lý do): chỉ log lại sau N giây,
# tránh phình log khi 1 mã hỏng dữ liệu theo từng nhịp quét.
_OHLC_WARN_TS = {}
_OHLC_WARN_COOLDOWN = 300.0  # 5 phút


def _warn_ohlc_throttled(key, msg, *args):
    now = time.time()
    if (now - _OHLC_WARN_TS.get(key, 0.0)) >= _OHLC_WARN_COOLDOWN:
        logger.warning(msg, *args)
        _OHLC_WARN_TS[key] = now

# Khởi tạo DNSE API trực tiếp từ .env
dnse_api = DNSEConnector(
    api_key=os.getenv("DNSE_API_KEY", ""),
    api_secret=os.getenv("DNSE_API_SECRET", ""),
    account_no=os.getenv("DNSE_ACCOUNT_NO", "")
)

class DataEngine:
    def __init__(self):
        self.tf_map = {
            "1m": "1", "5m": "5", "15m": "15",
            "30m": "30", "1h": "1H", "4h": "1H",
            "1d": "1D"
        }
        self._last_tick = {}  # Cache tick real-time: {symbol: {bid, ask, last, ...}}
        self._bars_cache = {}
        self._ws_started = False
        self.cache_stats = {
            "tick_hits": 0,
            "tick_misses": 0,
            "ohlc_hits": 0,
            "ohlc_misses": 0,
            "ws_hits": 0,
        }


    def _get_brain_settings(self, symbol=None):
        return get_brain_settings_for_symbol(symbol)

    def _ensure_ws_symbol(self, symbol):
        """Khởi động WS (1 lần) và subscribe symbol khi streaming được bật."""
        if not getattr(config, "DNSE_WS_ENABLED", False) or not market_ws.available:
            return
        if not self._ws_started:
            self._ws_started = market_ws.start()
        market_ws.subscribe([symbol])

    def set_stream_symbols(self, symbols):
        """Đồng bộ danh sách mã đang stream với watchlist hiện tại (gọi từ UI/daemon)."""
        if not getattr(config, "DNSE_WS_ENABLED", False) or not market_ws.available:
            return
        if not self._ws_started:
            self._ws_started = market_ws.start()
        market_ws.set_symbols(symbols)

    # =========================================================================
    # [TỐI ƯU CPU] CHỈ TÍNH TOÁN CÁC INDICATOR ĐƯỢC BẬT (ON)
    # =========================================================================
    def _apply_ta(self, df, inds_config, tsl_config=None):
        if df is None or df.empty: 
            return df
        try:
            def needs(name):
                cfg = inds_config.get(name, {}) or {}
                return bool(cfg.get("active") or cfg.get("is_trend"))

            # ADX
            if needs("adx"):
                p = int(inds_config["adx"].get("params", {}).get("period", 14))
                df.ta.adx(length=p, append=True)
            
            # EMA Cơ bản
            if needs("ema"):
                p = int(inds_config["ema"].get("params", {}).get("period", 50))
                df.ta.ema(length=p, append=True)
            
            # EMA Cross (Cần 2 đường EMA)
            if needs("ema_cross"):
                f = int(inds_config["ema_cross"].get("params", {}).get("fast", 9))
                s = int(inds_config["ema_cross"].get("params", {}).get("slow", 21))
                df.ta.ema(length=f, append=True)
                df.ta.ema(length=s, append=True)
            
            # RSI
            if needs("rsi"):
                p = int(inds_config["rsi"].get("params", {}).get("period", 14))
                df.ta.rsi(length=p, append=True)
            
            # MACD
            if needs("macd"):
                f = int(inds_config["macd"].get("params", {}).get("fast", 12))
                s = int(inds_config["macd"].get("params", {}).get("slow", 26))
                sig = int(inds_config["macd"].get("params", {}).get("signal", 9))
                df.ta.macd(fast=f, slow=s, signal=sig, append=True)
            
            # Bollinger Bands
            if needs("bollinger_bands"):
                p = int(inds_config["bollinger_bands"].get("params", {}).get("period", 20))
                std = float(inds_config["bollinger_bands"].get("params", {}).get("std_dev", 2.0))
                df.ta.bbands(length=p, std=std, append=True)
            
            # Supertrend
            if needs("supertrend"):
                p = int(inds_config["supertrend"].get("params", {}).get("period", 10))
                m = float(inds_config["supertrend"].get("params", {}).get("multiplier", 3.0))
                df.ta.supertrend(length=p, multiplier=m, append=True)
            
            # Stochastic
            if needs("stochastic"):
                k = int(inds_config["stochastic"].get("params", {}).get("k", 14))
                d = int(inds_config["stochastic"].get("params", {}).get("d", 3))
                sm = int(inds_config["stochastic"].get("params", {}).get("smooth", 3))
                df.ta.stoch(k=k, d=d, smooth_k=sm, append=True)
            
            # Parabolic SAR
            if needs("psar") or (tsl_config and "PSAR_STEP" in tsl_config):
                # Ưu tiên thông số từ TSL Config nếu có
                step = 0.02
                max_step = 0.2
                if tsl_config and "PSAR_STEP" in tsl_config:
                    step = float(tsl_config["PSAR_STEP"])
                    max_step = float(tsl_config["PSAR_MAX"])
                elif inds_config.get("psar"):
                    step = float(inds_config["psar"].get("params", {}).get("step", 0.02))
                    max_step = float(inds_config["psar"].get("params", {}).get("max_step", 0.2))
                
                df.ta.psar(af0=step, af=step, max_af=max_step, append=True)

            # Pivot Points (Standard Floor)
            if needs("pivot_points"):
                prev_h = df['high'].shift(1)
                prev_l = df['low'].shift(1)
                prev_c = df['close'].shift(1)
                df['PP'] = (prev_h + prev_l + prev_c) / 3
                df['R1'] = (2 * df['PP']) - prev_l
                df['S1'] = (2 * df['PP']) - prev_h

            # ATR
            if needs("atr"):
                p = int(inds_config["atr"].get("params", {}).get("period", 14))
                df.ta.atr(length=p, append=True)
            
            # Nến Nhật
            is_candle_active = needs("candle")
            is_mc_active = needs("multi_candle")
            if is_candle_active or is_mc_active:
                O, H, L, C = df['open'], df['high'], df['low'], df['close']
                body = (C - O).abs()
                upper_shadow = H - df[['open', 'close']].max(axis=1)
                lower_shadow = df[['open', 'close']].min(axis=1) - L
                df["CDL_ENGULFING"] = np.where((C > O) & (C.shift(1) < O.shift(1)) & (C > O.shift(1)) & (O < C.shift(1)), 100,
                                      np.where((C < O) & (C.shift(1) > O.shift(1)) & (C < O.shift(1)) & (O > C.shift(1)), -100, 0))
                df["CDL_HAMMER"] = np.where((lower_shadow > 2 * body) & (upper_shadow < 0.2 * body) & (C > O), 100, 0)
                df["CDL_SHOOTINGSTAR"] = np.where((upper_shadow > 2 * body) & (lower_shadow < 0.2 * body) & (C < O), -100, 0)
                df["CDL_MORNINGSTAR"] = np.where((C.shift(2) < O.shift(2)) & (body.shift(1) < body.shift(2)*0.3) & (C > O) & (C > O.shift(2) + body.shift(2)/2), 100, 0)
                df["CDL_EVENINGSTAR"] = np.where((C.shift(2) > O.shift(2)) & (body.shift(1) < body.shift(2)*0.3) & (C < O) & (C < O.shift(2) - body.shift(2)/2), -100, 0)
                
        except Exception as e:
            logger.error(f"Lỗi tính toán thư viện pandas-ta: {e}")
            
        return df

    def _fetch_bars(self, symbol, timeframe_val, num_bars, inds_config, tsl_config=None):
        res = self.tf_map.get(str(timeframe_val).lower(), "15")
        
        # Tính toán thời gian (from, to)
        # Giả sử lấy nến quá khứ, 1 cây nến 15 phút = 900 giây
        multiplier_map = {"1": 60, "5": 300, "15": 900, "30": 1800, "1h": 3600, "1d": 86400}
        seconds_per_bar = multiplier_map.get(str(res).lower(), 900)
        
        to_ts = int(time.time())
        # [FIX CKVN - Audit F1] Cửa sổ thời gian phải nhân hệ số phủ phiên: TT VN chỉ mở ~5h/ngày
        # (công thức gốc Exness giả định 24h) — không nhân thì khung intraday nhận thiếu nến trầm trọng
        # (100 nến 1H = 100 giờ lịch ≈ chỉ ~22 nến giao dịch thật) -> EMA/SMA period dài ra NaN im lặng.
        if str(res).lower() == "1d":
            window_factor = float(getattr(config, "DNSE_OHLC_WINDOW_FACTOR_DAILY", 1.6) or 1.0)
        else:
            window_factor = float(getattr(config, "DNSE_OHLC_WINDOW_FACTOR_INTRADAY", 8.0) or 1.0)
        from_ts = to_ts - int(num_bars * seconds_per_bar * max(window_factor, 1.0))

        cache_ttl = float(getattr(config, "DNSE_OHLC_CACHE_TTL_SECONDS", 30.0) or 0.0)
        effective_cache_ttl = max(cache_ttl, float(seconds_per_bar))
        # [24/7] Ngoài giờ giao dịch OHLC không đổi -> đóng băng cache để khỏi gọi API liên tục.
        market_open = True
        try:
            from core.market_hours import is_symbol_trade_window_open
            market_open = bool(is_symbol_trade_window_open(symbol)[0])
        except Exception:
            market_open = True
        if not market_open:
            closed_ttl = float(getattr(config, "DNSE_OHLC_CACHE_TTL_CLOSED_SECONDS", 1800.0) or 0.0)
            if closed_ttl > 0:
                effective_cache_ttl = max(effective_cache_ttl, closed_ttl)
        inds_key = tuple(sorted(
            (
                str(k),
                bool((v or {}).get("active")),
                bool((v or {}).get("is_trend")),
                json.dumps((v or {}).get("params", {}), sort_keys=True, default=str),
            )
            for k, v in (inds_config or {}).items()
            if isinstance(v, dict)
        ))
        # Ngoài giờ: bucket đóng băng NHƯNG xoay theo khối 6h. Bucket -1 cố định cũ có bug:
        # app chạy 24/7 cache nến 1d TRƯỚC PHIÊN (data chốt hôm qua) -> SAU PHIÊN vẫn trúng
        # key đó -> lượt quét EOD nhận nến cũ, không bao giờ thấy nến chốt hôm nay.
        # Khối 6h (mốc ~07h/13h/19h/01h VN) tách sáng-trước-phiên khỏi chiều-sau-phiên.
        cache_bucket = (-int(to_ts // 21600) - 1) if not market_open else int(to_ts / max(1, seconds_per_bar))
        try:
            market_type = dnse_api.market_type_for_symbol(symbol)
        except Exception:
            market_type = "DERIVATIVE"
        cache_key = (str(symbol).upper(), market_type, res, int(num_bars), cache_bucket, inds_key)
        if effective_cache_ttl > 0:
            cached = self._bars_cache.get(cache_key)
            if cached and (time.time() - cached["ts"]) < effective_cache_ttl:
                self.cache_stats["ohlc_hits"] += 1
                return cached["df"].copy()
        self.cache_stats["ohlc_misses"] += 1
        
        data = dnse_api.get_ohlc(symbol, res, from_ts, to_ts)

        required_keys = ("t", "o", "h", "l", "c", "v")
        if not isinstance(data, dict):
            _warn_ohlc_throttled(f"{symbol}|{res}|empty", "OHLC invalid for %s tf=%s res=%s: empty response", symbol, timeframe_val, res)
            return pd.DataFrame()
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            _warn_ohlc_throttled(f"{symbol}|{res}|missing", "OHLC invalid for %s tf=%s res=%s: missing %s", symbol, timeframe_val, res, missing_keys)
            return pd.DataFrame()
        invalid_keys = [key for key in required_keys if not hasattr(data.get(key), "__len__") or data.get(key) is None]
        if invalid_keys:
            _warn_ohlc_throttled(f"{symbol}|{res}|null", "OHLC invalid for %s tf=%s res=%s: null/non-list %s", symbol, timeframe_val, res, invalid_keys)
            return pd.DataFrame()
        lengths = {key: len(data.get(key)) for key in required_keys}
        if not lengths["t"]:
            return pd.DataFrame()
        if len(set(lengths.values())) != 1:
            _warn_ohlc_throttled(f"{symbol}|{res}|mismatch", "OHLC invalid for %s tf=%s res=%s: length mismatch %s", symbol, timeframe_val, res, lengths)
            return pd.DataFrame()
            
        df = pd.DataFrame({
            'time': data['t'],
            'open': data['o'],
            'high': data['h'],
            'low': data['l'],
            'close': data['c'],
            'volume': data['v']
        })
        df['time'] = pd.to_datetime(df['time'], unit='s')

        # [Audit F1] Chẩn đoán thiếu nến: nhận < 60% số nến yêu cầu -> indicator period dài có nguy cơ NaN
        if len(df) < int(num_bars * 0.6):
            _warn_ohlc_throttled(
                f"{symbol}|{res}|short",
                "OHLC %s tf=%s res=%s: nhận %s/%s nến — indicator period dài (EMA50, SMA20...) có thể NaN",
                symbol, timeframe_val, res, len(df), num_bars,
            )

        # Chỉ tính những Indicator đang bật
        df = self._apply_ta(df, inds_config, tsl_config)
        if effective_cache_ttl > 0:
            self._bars_cache[cache_key] = {"ts": time.time(), "df": df.copy()}
            # [Audit F1 follow-up] Cap cũ 128 chỉ đủ ~42 mã × 3 khung — watchlist lớn sẽ thrash
            # (mỗi vòng đá văng cache mã đầu -> gọi API lại vô ích). Nâng mặc định 512, chỉnh qua env.
            max_entries = int(getattr(config, "DNSE_OHLC_CACHE_MAX_ENTRIES", 512) or 512)
            if len(self._bars_cache) > max_entries:
                evict = max(32, max_entries // 8)
                oldest = sorted(self._bars_cache.items(), key=lambda item: item[1]["ts"])[:evict]
                for old_key, _ in oldest:
                    self._bars_cache.pop(old_key, None)
        
        return df

    def _calc_atr(self, df, period=14):
        if df.empty: return 0.0001
        current_price = float(df['close'].iloc[-1])
        safe_fallback = current_price * 0.0005 

        if len(df) < period + 1:
            try:
                mean_range = (df['high'] - df['low']).mean()
                return float(mean_range) if mean_range > 0 else safe_fallback
            except:
                return safe_fallback
        try:
            high, low, close_prev = df['high'], df['low'], df['close'].shift(1)
            tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean().iloc[-1]
            return safe_fallback if pd.isna(atr) or atr <= 0 else float(atr)
        except:
            return safe_fallback

    def _calc_swings(self, df, lookback=10):
        if df.empty: return 0.0, 0.0
        try:
            if len(df) < lookback: return float(df['high'].max()), float(df['low'].min())
            recent_df = df.tail(lookback)
            sh, sl = float(recent_df['high'].max()), float(recent_df['low'].min())
            if pd.isna(sh) or pd.isna(sl): return float(df['high'].iloc[-1]), float(df['low'].iloc[-1])
            return sh, sl
        except:
            current_close = float(df['close'].iloc[-1])
            return current_close * 1.001, current_close * 0.999 

    def fetch_data_v4(self, symbol):
        """Kéo độc lập 4 chuỗi dữ liệu cho G0, G1, G2, G3 và tính Cản/ATR cho tất cả"""
        settings = self._get_brain_settings(symbol)
        inds_config = settings.get("indicators", {})
        tsl_config = settings.get("TSL_CONFIG", getattr(config, "TSL_CONFIG", {}))
        
        tfs = {
            "G0": settings.get("G0_TIMEFRAME", getattr(config, "G0_TIMEFRAME", "1d")),
            "G1": settings.get("G1_TIMEFRAME", getattr(config, "G1_TIMEFRAME", "1h")),
            "G2": settings.get("G2_TIMEFRAME", getattr(config, "G2_TIMEFRAME", "15m")),
            "G3": settings.get("G3_TIMEFRAME", getattr(config, "G3_TIMEFRAME", "15m"))
        }
        
        num_bars = settings.get("NUM_H1_BARS", 100)
        
        # Truyền cấu hình Indicator và TSL vào để lọc
        dfs = {grp: self._fetch_bars(symbol, tf, num_bars, inds_config, tsl_config) for grp, tf in tfs.items()}
        
        if any(df.empty for df in dfs.values()):
            return None, None

        current_price = float(dfs["G2"]['close'].iloc[-1])
        
        context = {
            "symbol": symbol,
            "current_price": current_price
        }

        # [NEW V4.4 FINAL] Lấy giá trị PSAR hiện tại cho TSL PSAR_TRAIL
        try:
            tsl_cfg = settings.get("TSL_CONFIG", getattr(config, "TSL_CONFIG", {}))
            psar_grp = tsl_cfg.get("PSAR_GROUP", "G2")
            if "DYNAMIC" in psar_grp:
                psar_grp = "G2"
            elif psar_grp not in dfs:
                psar_grp = None
            context["psar_group_resolved"] = psar_grp

            for grp, df_psar in dfs.items():
                psar_cols = [c for c in df_psar.columns if c.startswith("PSARl_") or c.startswith("PSARs_")]
                for col in psar_cols:
                    val = df_psar[col].iloc[-1]
                    if not pd.isna(val):
                        context[f"psar_{grp}"] = float(val)
                        break

            if f"psar_{psar_grp}" in context:
                context["psar"] = context[f"psar_{psar_grp}"]
        except Exception:
            pass

        # [FIX V4.4] Đồng bộ thông số Lookback/Period với cấu hình Indicator thay vì hardcode
        swing_lookback = int(inds_config.get("swing_point", {}).get("params", {}).get("lookback", 50))
        swing_strength = int(inds_config.get("swing_point", {}).get("params", {}).get("strength", 2))
        atr_period = int(inds_config.get("atr", {}).get("params", {}).get("period", 14))

        for grp in ["G0", "G1", "G2", "G3"]:
            df_grp = dfs[grp]
            sh, sl = self._calc_swings(df_grp, lookback=swing_lookback)
            atr = self._calc_atr(df_grp, period=atr_period)
            
            context[f"swing_high_{grp}"] = float(sh)
            context[f"swing_low_{grp}"] = float(sl)
            context[f"atr_{grp}"] = float(atr)
            try:
                ema20 = df_grp["close"].ewm(span=20, adjust=False).mean().iloc[-1]
                context[f"ema20_{grp}"] = float(ema20)
                context[f"EMA_20_{grp}"] = float(ema20)
            except Exception:
                pass
            try:
                bb_mid = df_grp["close"].rolling(window=20).mean().iloc[-1]
                if not pd.isna(bb_mid):
                    context[f"bb_mid_{grp}"] = float(bb_mid)
            except Exception:
                pass
            write_structure_context(
                context,
                grp,
                analyze_market_structure(df_grp, lookback=swing_lookback, strength=swing_strength),
            )
            try:
                candle = df_grp.iloc[-1]
                context[f"open_{grp}"] = float(candle["open"])
                context[f"high_{grp}"] = float(candle["high"])
                context[f"low_{grp}"] = float(candle["low"])
                context[f"close_{grp}"] = float(candle["close"])
            except Exception:
                pass

        context["atr_entry"] = context["atr_G2"]
        context["atr_trend"] = context["atr_G1"]
        context["swing_high_entry"] = context["swing_high_G2"]
        context["swing_low_entry"] = context["swing_low_G2"]
        context["swing_high_trend"] = context["swing_high_G1"]
        context["swing_low_trend"] = context["swing_low_G1"]

        return dfs, context

    def fetch_and_prepare(self, symbol):
        """HÀM CŨ: Phục vụ chạy Bot Daemon bản cũ tránh crash"""
        settings = self._get_brain_settings(symbol)
        inds_config = settings.get("indicators", {})
        tsl_config = settings.get("TSL_CONFIG", getattr(config, "TSL_CONFIG", {}))
        
        tf_entry = settings.get("entry_timeframe", "15m")
        tf_trend = settings.get("trend_timeframe", "1h")
        num_entry = settings.get("NUM_M15_BARS", 100)
        num_trend = settings.get("NUM_H1_BARS", 100)

        df_entry = self._fetch_bars(symbol, tf_entry, num_entry, inds_config, tsl_config)
        df_trend = self._fetch_bars(symbol, tf_trend, num_trend, inds_config, tsl_config)

        if df_entry.empty or df_trend.empty:
            return None, None, None

        current_price = float(df_entry['close'].iloc[-1])
        swing_lookback = int(inds_config.get("swing_point", {}).get("params", {}).get("lookback", 50))
        atr_period = int(inds_config.get("atr", {}).get("params", {}).get("period", 14))

        atr_entry = self._calc_atr(df_entry, period=atr_period)
        atr_trend = self._calc_atr(df_trend, period=atr_period)
        swing_h_entry, swing_l_entry = self._calc_swings(df_entry, lookback=swing_lookback)
        swing_h_trend, swing_l_trend = self._calc_swings(df_trend, lookback=swing_lookback)
        
        wave_up_dist = swing_h_trend - swing_l_trend
        fibo_618_support = swing_h_trend - (wave_up_dist * 0.618)
        fibo_618_resistance = swing_l_trend + (wave_up_dist * 0.618)

        try:
            ema50 = float(df_trend['close'].ewm(span=50, adjust=False).mean().iloc[-1])
            trend_status = "UP" if current_price > ema50 else "DOWN"
        except:
            trend_status = "NONE"

        context = {
            "symbol": symbol, "current_price": float(current_price),
            "entry_timeframe": tf_entry, "trend_timeframe": tf_trend,
            "trend": trend_status, "atr_entry": float(atr_entry), "atr_trend": float(atr_trend),
            "swing_high_entry": float(swing_h_entry), "swing_low_entry": float(swing_l_entry),
            "swing_high_trend": float(swing_h_trend), "swing_low_trend": float(swing_l_trend),
            "fibo_618_support": float(fibo_618_support), "fibo_618_resistance": float(fibo_618_resistance)
        }

        return df_entry, df_trend, context

    def fetch_realtime_tick(self, symbol):
        """Lấy giá real-time từ DNSE: trades/latest (giá khớp) + quotes/latest (bid/ask).
        Trả về dict {bid, ask, last, high, low, spread, timestamp} hoặc None.
        Cache kết quả vào self._last_tick[symbol].
        """
        # 0. Ưu tiên dữ liệu WebSocket streaming nếu được bật và còn tươi.
        if getattr(config, "DNSE_WS_ENABLED", False) and market_ws.available:
            self._ensure_ws_symbol(symbol)
            ws_tick = market_ws.latest_tick(symbol)
            if ws_tick:
                stale = float(getattr(config, "DNSE_WS_STALE_SECONDS", 5.0) or 0.0)
                age = time.time() - float(ws_tick.get("timestamp", 0.0) or 0.0)
                if stale <= 0 or age < stale:
                    self._last_tick[symbol] = ws_tick
                    self.cache_stats["ws_hits"] += 1
                    return ws_tick

        cache_ttl = float(getattr(config, "DNSE_TICK_CACHE_TTL_SECONDS", 2.0) or 0.0)
        cached = self._last_tick.get(symbol)
        if cached and cache_ttl > 0 and (time.time() - float(cached.get("timestamp", 0.0) or 0.0)) < cache_ttl:
            self.cache_stats["tick_hits"] += 1
            return cached
        self.cache_stats["tick_misses"] += 1
        tick_data = {"symbol": symbol}
        try:
            # 1. Giá khớp lệnh gần nhất
            trade = dnse_api.get_latest_trade(symbol)
            if trade:
                tick_data["last"] = float(trade.get("matchPrice", 0))
                tick_data["high"] = float(trade.get("highestPrice", 0))
                tick_data["low"] = float(trade.get("lowestPrice", 0))
                tick_data["open"] = float(trade.get("openPrice", 0))
                tick_data["trade_time"] = trade.get("time", "")
            
            # 2. Bid/Ask sổ lệnh gần nhất
            quote = dnse_api.get_latest_quote(symbol)
            if quote:
                bids = quote.get("bid", [])
                offers = quote.get("offer", [])
                if bids:
                    tick_data["bid"] = float(bids[0].get("price", 0))
                if offers:
                    tick_data["ask"] = float(offers[0].get("price", 0))
                tick_data["quote_time"] = quote.get("time", "")
            
            # 3. Fallback: nếu thiếu bid/ask thì dùng last price.
            # Đánh dấu synthetic_quote để UI biết spread=0 là giả (ngoài giờ/nghỉ trưa),
            # tránh hiển thị "Spread: 0.00" như thể sổ lệnh đang khớp sát.
            if "last" in tick_data:
                if "bid" not in tick_data:
                    tick_data["bid"] = tick_data["last"]
                    tick_data["synthetic_quote"] = True
                if "ask" not in tick_data:
                    tick_data["ask"] = tick_data["last"]
                    tick_data["synthetic_quote"] = True
            
            # 4. Tính spread
            if "bid" in tick_data and "ask" in tick_data:
                tick_data["spread"] = round(tick_data["ask"] - tick_data["bid"], 2)
            
            tick_data["timestamp"] = time.time()
            
            if "last" in tick_data or "bid" in tick_data:
                self._last_tick[symbol] = tick_data
                return tick_data
                
        except Exception as e:
            logger.error(f"fetch_realtime_tick({symbol}) error: {e}")
        
        return self._last_tick.get(symbol)

    def get_api_health_snapshot(self):
        stats = {}
        try:
            stats = dnse_api.get_api_health_snapshot()
        except Exception:
            stats = {}
        try:
            ws_info = market_ws.snapshot()
        except Exception:
            ws_info = {}
        return {
            "connector": stats,
            "cache": dict(self.cache_stats),
            "cache_sizes": {
                "ticks": len(self._last_tick),
                "ohlc": len(self._bars_cache),
            },
            "ws": ws_info,
        }

data_engine = DataEngine()
