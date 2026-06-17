# -*- coding: utf-8 -*-
# FILE: bot_daemon.py
# V4.2.1: DECOUPLED THREADS & DYNAMIC TREND COMPASS (FIXED UI SYNC) (KAISER EDITION)

import time
import json
import os
import uuid
import logging
import threading

import config
from core.dnse_connector import DNSEConnector
from core.data_engine import data_engine
from core.market_hours import is_symbol_trade_window_open
from core.position_classifier import is_bot_position, is_manual_position
from signals.signal_generator import signal_generator
from core.storage_manager import get_brain_settings_for_symbol
from core.logger_setup import setup_logging  # [NEW V4.3] Import hệ thống Log

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [DAEMON] %(message)s")
logger = logging.getLogger("BotDaemon")

SIGNAL_FILE = "data/live_signals.json"
SIGNAL_FILE_TMP = SIGNAL_FILE + ".tmp"
BRAIN_SETTINGS_FILE = "data/brain_settings.json"
DEBUG_STATE_FILE = "data/current_signal_state.json"


def _is_telegram_auto_scale_position(pos, magics, trade_tactics):
    if not is_manual_position(pos, magics):
        return False
    comment = str(getattr(pos, "comment", "") or "")
    if "[USER]_TELEGRAM" not in comment:
        return False
    tactic = str((trade_tactics or {}).get(str(getattr(pos, "ticket", "")), "") or "")
    return "AUTO_DCA" in tactic or "AUTO_PCA" in tactic

def update_daemon_paths(account_id: str):
    global SIGNAL_FILE, SIGNAL_FILE_TMP, BRAIN_SETTINGS_FILE, DEBUG_STATE_FILE
    base_dir = os.path.join("data", str(account_id))
    os.makedirs(base_dir, exist_ok=True)
    SIGNAL_FILE = os.path.join(base_dir, "live_signals.json")
    SIGNAL_FILE_TMP = SIGNAL_FILE + ".tmp"
    BRAIN_SETTINGS_FILE = os.path.join(base_dir, "brain_settings.json")
    DEBUG_STATE_FILE = os.path.join(base_dir, "current_signal_state.json")


class StandaloneBotDaemon:
    def __init__(self):
        self.running = False
        self.connector = DNSEConnector()
        if not self.connector.connect():
            logger.error("Không thể kết nối DNSE. Daemon sẽ dừng.")
            return

        acc_info = self.connector.get_account_info()
        if acc_info:
            import core.storage_manager as storage_manager
            storage_manager.set_active_account(acc_info['login'])
            update_daemon_paths(acc_info['login'])
            logger.info(f"✅ Daemon đã thiết lập Workspace cho tài khoản: {acc_info['login']}")

        self.dca_pca_interval = 2
        self.last_dca_pca_scan = 0
        self.pending_signals = []
        self.heartbeat_contexts = {}
        self.last_entry_signal_times = {}
        self._tick_thread = None
        self._active_symbols = []

    def _get_entry_signal_cooldown(self, symbol):
        try:
            brain = get_brain_settings_for_symbol(symbol)
            cooldown_min = float(brain.get("bot_safeguard", {}).get("COOLDOWN_MINUTES", 1.0))
            return max(0.0, cooldown_min * 60)
        except Exception:
            return 60.0

    def _entry_signal_on_cooldown(self, action, symbol):
        if action == "NONE":
            return False

        cooldown_sec = self._get_entry_signal_cooldown(symbol)
        if cooldown_sec <= 0:
            return False

        key = f"{symbol}_{action}"
        now = time.time()
        last_time = self.last_entry_signal_times.get(key, 0)
        if now - last_time < cooldown_sec:
            return True

        self.last_entry_signal_times[key] = now
        return False

    def _atomic_write_signals(self, active_symbols):
        payload = {
            "brain_heartbeat": {
                "status": "HEALTHY",
                "wakeup_time": time.time(),
                "active_symbols": active_symbols,
                "contexts": self.heartbeat_contexts,
            },
            "pending_signals": self.pending_signals[-10:],
        }
        os.makedirs(os.path.dirname(SIGNAL_FILE), exist_ok=True)

        # [FIX] WinError 5 Access is denied
        for attempt in range(5):
            try:
                with open(SIGNAL_FILE_TMP, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=4)
                os.replace(SIGNAL_FILE_TMP, SIGNAL_FILE)
                break
            except (PermissionError, OSError) as e:
                time.sleep(0.05)
                if attempt == 4:
                    logger.error(f"Lỗi ghi tín hiệu sau 5 lần thử: {e}")

    def _write_signal_debugger(self, debug_state):
        try:
            os.makedirs(os.path.dirname(DEBUG_STATE_FILE), exist_ok=True)
            with open(DEBUG_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "states": debug_state,
                    },
                    f,
                    indent=4,
                    ensure_ascii=False,
                )
        except Exception:
            pass

    def _add_signal(self, action, symbol, context, signal_class="ENTRY"):
        if signal_class == "ENTRY" and self._entry_signal_on_cooldown(action, symbol):
            logger.debug(f"Cooldown signal ENTRY {action} {symbol}: skip duplicate")
            return False

        sig_id = str(uuid.uuid4())
        self.pending_signals.append(
            {
                "signal_id": sig_id,
                "timestamp": time.time(),
                "valid_for": 300 if signal_class == "ENTRY" else 60,
                "action": action,
                "symbol": symbol,
                "signal_class": signal_class,
                "context": context,
                "market_mode": context.get("market_mode", "ANY"),
            }
        )
        logger.debug(f"Đã phát tín hiệu {action} cho {symbol} ({signal_class})")
        live_cfg = self._read_live_config()
        syms = live_cfg.get("BOT_ACTIVE_SYMBOLS", getattr(config, "SYMBOLS", []))
        self._atomic_write_signals(syms)
        return True

    def _read_live_config(self):
        try:
            if os.path.exists(BRAIN_SETTINGS_FILE):
                with open(BRAIN_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _tick_update_loop(self):
        """Luồng riêng: poll giá real-time mỗi 2 giây qua trades/latest + quotes/latest."""
        tick_interval = 2.0
        while self.running:
            try:
                # Chỉ lấy tick cho VN30F1M theo yêu cầu để tối ưu
                symbols = list(
                    self._active_symbols
                    or getattr(config, "BOT_ACTIVE_SYMBOLS", [])
                    or [getattr(config, "DEFAULT_SYMBOL", "VN30F1M")]
                )
                for sym in symbols:
                    if not self.running:
                        break
                    tick = data_engine.fetch_realtime_tick(sym)
                    if tick:
                        # Ghi tick vào heartbeat context để UI nhận
                        ctx = self.heartbeat_contexts.get(sym, {})
                        if "last" in tick:
                            ctx["current_price"] = tick["last"]
                        if "bid" in tick:
                            ctx["bid"] = tick["bid"]
                        if "ask" in tick:
                            ctx["ask"] = tick["ask"]
                        if "spread" in tick:
                            ctx["spread"] = tick["spread"]
                        if "high" in tick:
                            ctx["day_high"] = tick["high"]
                        if "low" in tick:
                            ctx["day_low"] = tick["low"]
                        ctx["tick_timestamp"] = tick.get("timestamp", time.time())
                        self.heartbeat_contexts[sym] = ctx
                        # Ghi tín hiệu ngay để UI cập nhật nhanh
                        self._atomic_write_signals(symbols)
            except Exception as e:
                logger.debug(f"Tick update error: {e}")
            time.sleep(tick_interval)

    def run(self):
        self.running = True
        logger.info(
            "RAT6.0 Daemon started."
        )
        last_signal_scan = 0
        last_acc_check = 0
        acc_info = None

        while self.running:
            try:
                now = time.time()
                if acc_info is None or (now - last_acc_check > 15.0):
                    acc_info = self.connector.get_account_info()
                    last_acc_check = now
                    if acc_info is None:
                        self.connector._is_connected = False
                        self.connector.connect()
                        acc_info = self.connector.get_account_info()
                    
                if acc_info:
                    import core.storage_manager as storage_manager
                    current_acc_id = str(acc_info['login'])
                    if current_acc_id and current_acc_id != storage_manager._active_account_id:
                        storage_manager.set_active_account(current_acc_id)
                        update_daemon_paths(current_acc_id)
                        logger.info(f"🔄 Daemon phát hiện đổi tài khoản DNSE sang {current_acc_id}. Đã cập nhật Workspace.")
                        
                live_cfg = self._read_live_config()
                bot_active = live_cfg.get(
                    "BOT_ACTIVE",
                    live_cfg.get(
                        "AUTO_TRADE_ENABLED",
                        getattr(config, "AUTO_TRADE_ENABLED", False),
                    ),
                )
                symbols = live_cfg.get(
                    "BOT_ACTIVE_SYMBOLS",
                    getattr(
                        config, "BOT_ACTIVE_SYMBOLS", getattr(config, "SYMBOLS", [])
                    ),
                )
                self._active_symbols = symbols

                # Khởi động luồng tick nếu chưa chạy
                if self._tick_thread is None or not self._tick_thread.is_alive():
                    self._tick_thread = threading.Thread(target=self._tick_update_loop, daemon=True)
                    self._tick_thread.start()
                    logger.info("🔥 Tick update thread started (2s interval).")

                # [NEW] Lấy thời gian quét động từ UI
                daemon_delay = live_cfg.get("bot_safeguard", {}).get(
                    "DAEMON_LOOP_DELAY", getattr(config, "DAEMON_LOOP_DELAY", 15)
                )
                self.dca_pca_interval = live_cfg.get("bot_safeguard", {}).get(
                    "DCA_PCA_SCAN_INTERVAL", 2
                )
                for _ttl_key in (
                    "DNSE_TICK_CACHE_TTL_SECONDS",
                    "DNSE_OHLC_CACHE_TTL_SECONDS",
                    "DNSE_ACCOUNT_CACHE_TTL_SECONDS",
                    "DNSE_POSITIONS_CACHE_TTL_SECONDS",
                ):
                    if _ttl_key in live_cfg:
                        try:
                            setattr(config, _ttl_key, float(live_cfg.get(_ttl_key)))
                        except Exception:
                            pass

                now = time.time()

                # 1. QUÉT TÍN HIỆU ENTRY (Chu kỳ động)
                if symbols and (now - last_signal_scan >= daemon_delay):
                    self._scan_signals(symbols, bot_active)
                    last_signal_scan = now
                    self._atomic_write_signals(symbols)

                # 2. QUÉT DCA/PCA (Chu kỳ động - Độc lập hoàn toàn)
                if (
                    bot_active
                    and symbols
                    and (now - self.last_dca_pca_scan >= self.dca_pca_interval)
                ):
                    self._scan_dca_pca()
                    self.last_dca_pca_scan = now

                # Luồng gốc ngủ rất ngắn để không gây kẹt tiến trình
                time.sleep(0.5)

            except Exception as e:
                logger.exception("Lỗi Loop trong Daemon")
                time.sleep(2)

    def _scan_signals(self, symbols, bot_active):
        signal_debug_state = {}

        for sym in symbols:
            if not self.running:
                break

            is_open, closed_reason = is_symbol_trade_window_open(sym)
            dfs, context = data_engine.fetch_data_v4(sym)
            if dfs is None or context is None:
                signal_debug_state[sym] = f"[PAUSE] {closed_reason}" if not is_open else "Đang tải dữ liệu..."
                continue

            # [FIX CORE]: Luôn chạy hàm generate_signal_v4 để tính toán và lưu Trend, Mode vào biến context
            # Đảm bảo UI luôn nhận được cấu trúc thị trường mới nhất ngay cả khi Bot đang tắt (Manual Mode)
            signal = signal_generator.generate_signal_v4(dfs, context, symbol=sym)
            context["latest_signal"] = signal # [NEW V4.4] Phục vụ logic REV_C
            context["market_open"] = bool(is_open)
            context["market_closed_reason"] = "" if is_open else closed_reason
            if not is_open:
                context["block_reason"] = f"MARKET_CLOSED: {closed_reason}"

            # --- [V4.2.1] Gói toàn bộ context vào Heartbeat ---
            self.heartbeat_contexts[sym] = context.copy()
            self.heartbeat_contexts[sym].update({"timestamp": time.time()})

            if not is_open:
                signal_debug_state[sym] = f"[PAUSE/PREVIEW] {closed_reason}"
                continue

            # [FIX] Luôn gửi tín hiệu vào hàng chờ (để SignalListener hiển thị Thinking Logs)
            if signal == 1:
                self._add_signal("BUY", sym, context, "ENTRY")
                signal_debug_state[sym] = (
                    "✅ ĐÃ BÓP CÒ BUY" if bot_active else "⏸️ (TEST) Tín hiệu BUY"
                )
            elif signal == -1:
                self._add_signal("SELL", sym, context, "ENTRY")
                signal_debug_state[sym] = (
                    "✅ ĐÃ BÓP CÒ SELL" if bot_active else "⏸️ (TEST) Tín hiệu SELL"
                )
            else:
                try:
                    from core.storage_manager import get_brain_settings_for_symbol
                    none_rev = get_brain_settings_for_symbol(sym).get("bot_safeguard", {}).get("REV_CLOSE_ON_NONE", False)
                except Exception:
                    none_rev = False
                if none_rev:
                    self._add_signal("NONE", sym, context, "ENTRY")
                signal_debug_state[sym] = (
                    "⏳ Đang chờ điều kiện bóp cò..."
                    if bot_active
                    else "⏸️ Đang theo dõi..."
                )

        self._write_signal_debugger(signal_debug_state)

    def _scan_dca_pca(self):
        # [NEW V4.4] Bỏ get brain global, dời xuống từng vòng lặp Symbol để lấy config riêng
        positions = self.connector.get_positions()
        if not positions:
            return

        import core.storage_manager as storage_manager
        magics = storage_manager.get_magic_numbers()
        state = storage_manager.load_state()
        trade_tactics = state.get("trade_tactics", {}) if isinstance(state, dict) else {}
        bot_positions = {}
        for pos in positions:
            if is_bot_position(pos, magics) or _is_telegram_auto_scale_position(pos, magics, trade_tactics):
                if pos.symbol not in bot_positions:
                    bot_positions[pos.symbol] = []
                bot_positions[pos.symbol].append(pos)

        from core.storage_manager import get_last_dca_pca_close_time

        for symbol, pos_list in bot_positions.items():
            # Lấy cấu hình riêng cho từng symbol
            brain = get_brain_settings_for_symbol(symbol)
            dca_cfg = brain.get("dca_config", getattr(config, "DCA_CONFIG", {}))
            pca_cfg = brain.get("pca_config", getattr(config, "PCA_CONFIG", {}))
            
            if not dca_cfg.get("ENABLED", False) and not pca_cfg.get("ENABLED", False):
                continue
            
            context = self.heartbeat_contexts.get(symbol)
            if not context:
                dfs, ctx = data_engine.fetch_data_v4(symbol)
                if not ctx:
                    continue
                context = ctx
            
            # [NEW V5] Check Cooldown DCA/PCA theo Signal Time (Chống xả lệnh liên thanh)
            from core.storage_manager import get_last_dca_pca_signal_time
            now = time.time()
            dca_cd_time = dca_cfg.get("COOLDOWN", 60)
            pca_cd_time = pca_cfg.get("COOLDOWN", dca_cd_time)

            current_price = context.get("current_price", 0)
            
            # [KAISER FIX] Lấy ATR theo đúng Group mà Ngài đã chọn ở Risk & TSL (Nguồn cắm SL)
            risk_tsl = brain.get("risk_tsl", {})
            sl_group = risk_tsl.get("base_sl", "G2")
            if "DYNAMIC" in sl_group:
                # Giả định DYNAMIC dùng G1 cho Trend, G2 cho Sideway (theo logic TradeManager)
                market_mode = context.get("market_mode", "ANY")
                sl_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"
            
            atr_val = context.get(f"atr_{sl_group}", 0)
            # NẾU MẤT DATA ATR -> BỎ QUA KHÔNG NHỒI LỆNH ĐỂ CHỐNG SPAM
            if not atr_val or atr_val <= 0:
                continue

            pos_list.sort(key=lambda x: x.time)
            first_pos = pos_list[0]
            is_buy = first_pos.type == 0
            expected_sig = 1 if is_buy else -1
            
            profit_points = (
                (current_price - first_pos.price_open)
                if is_buy
                else (first_pos.price_open - current_price)
            )

            # DCA LOGIC
            if (
                dca_cfg.get("ENABLED", False)
                and profit_points < 0
                and len(pos_list) < dca_cfg.get("MAX_STEPS", 3)
                and now - get_last_dca_pca_signal_time(symbol, "DCA") >= dca_cd_time
            ):
                if abs(profit_points) >= (dca_cfg.get("DISTANCE_ATR_R", 1.0) * atr_val):
                    # ==========================================
                    # [NEW V5.1] MINI-BRAIN EVALUATION (DCA)
                    # ==========================================
                    dca_signal = context.get("latest_signal", 0)
                    dca_mb = dca_cfg.get("MINI_BRAIN", {})
                    if dca_mb.get("active", False):
                        # [Way B] Tự động kế thừa thông số params từ Sandbox hiện tại
                        sandbox_inds = brain.get("indicators", {})
                        for k, v in dca_mb.get("indicators", {}).items():
                            if k in sandbox_inds:
                                v["params"] = sandbox_inds[k].get("params", {})
                        
                        tf = dca_mb.get("timeframe", "15m")
                        df_mb = data_engine._fetch_bars(symbol, tf, 50, dca_mb.get("indicators", {}))
                        dca_signal = signal_generator.evaluate_mini_brain(df_mb, context, dca_mb, context.get("market_mode", "ANY"))

                    if dca_signal == expected_sig:  # [V5.1] Cần Mini-Brain đồng thuận
                        self._add_signal(
                            "BUY" if is_buy else "SELL",
                            symbol,
                            context,
                            "DCA",
                        )
                        from core.storage_manager import update_last_dca_pca_signal_time
                        update_last_dca_pca_signal_time(symbol, time.time(), "DCA")
                        time.sleep(0.5)
                        continue
                    else:
                        mb_log_key = f"mb_dca_reject_{symbol}"
                        last_mb_log = self.heartbeat_contexts.get(mb_log_key, 0)
                        log_cooldown = float(brain.get("bot_safeguard", {}).get("LOG_COOLDOWN_MINUTES", 60.0)) * 60.0
                        if time.time() - last_mb_log > log_cooldown:
                            logger.info(f"🚫 [MINI-BRAIN] Tạm chặn DCA {symbol} (Chưa đồng thuận xu hướng).")
                            self.heartbeat_contexts[mb_log_key] = time.time()

            # PCA LOGIC
            if (
                pca_cfg.get("ENABLED", False)
                and profit_points > 0
                and len(pos_list) < pca_cfg.get("MAX_STEPS", 2)
                and now - get_last_dca_pca_signal_time(symbol, "PCA") >= pca_cd_time
            ):
                is_safe = (
                    is_buy and first_pos.sl > first_pos.price_open
                ) or (
                    not is_buy and (0 < first_pos.sl < first_pos.price_open)
                )
                if is_safe and profit_points >= (pca_cfg.get("DISTANCE_ATR_R", 1.5) * atr_val):
                    # ==========================================
                    # [NEW V5.1] MINI-BRAIN EVALUATION (PCA)
                    # ==========================================
                    pca_signal = context.get("latest_signal", 0)
                    pca_mb = pca_cfg.get("MINI_BRAIN", {})
                    if pca_mb.get("active", False):
                        # [Way B] Tự động kế thừa thông số params từ Sandbox hiện tại
                        sandbox_inds = brain.get("indicators", {})
                        for k, v in pca_mb.get("indicators", {}).items():
                            if k in sandbox_inds:
                                v["params"] = sandbox_inds[k].get("params", {})

                        tf = pca_mb.get("timeframe", "15m")
                        df_mb = data_engine._fetch_bars(symbol, tf, 50, pca_mb.get("indicators", {}))
                        pca_signal = signal_generator.evaluate_mini_brain(df_mb, context, pca_mb, context.get("market_mode", "ANY"))

                    if pca_signal == expected_sig:  # [V5.1] Cần Mini-Brain đồng thuận
                        self._add_signal(
                            "BUY" if is_buy else "SELL",
                            symbol,
                            context,
                            "PCA",
                        )
                        from core.storage_manager import update_last_dca_pca_signal_time
                        update_last_dca_pca_signal_time(symbol, time.time(), "PCA")
                        time.sleep(0.5)
                    else:
                        mb_log_key = f"mb_pca_reject_{symbol}"
                        last_mb_log = self.heartbeat_contexts.get(mb_log_key, 0)
                        log_cooldown = float(brain.get("bot_safeguard", {}).get("LOG_COOLDOWN_MINUTES", 60.0)) * 60.0
                        if time.time() - last_mb_log > log_cooldown:
                            logger.info(f"🚫 [MINI-BRAIN] Tạm chặn PCA {symbol} (Chưa đồng thuận xu hướng).")
                            self.heartbeat_contexts[mb_log_key] = time.time()


if __name__ == "__main__":
    # [FIX V5] Đổi tên tiến trình thành "daemon" để không đụng file log của UI (WinError 32)
    logger = setup_logging(debug_mode=getattr(config, "ENABLE_DEBUG_LOGGING", False), process_name="daemon")

    daemon = StandaloneBotDaemon()
    try:
        if daemon.connector._is_connected:
            daemon.run()
    except KeyboardInterrupt:
        import logging

        logger = logging.getLogger("BotDaemon")
        logger.info("Đang tắt tiến trình Daemon...")
