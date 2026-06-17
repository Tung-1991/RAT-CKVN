# -*- coding: utf-8 -*-
# FILE: core/trade_manager.py
# V4.4 (FINAL): UNIFIED TRADE MANAGER - DYNAMIC MACRO, REVERSE CLOSE & CASH TSL (KAISER EDITION)

import logging
import time
import math
import threading
from types import SimpleNamespace
import config
from core import settlement
from core.data_engine import data_engine
from core.storage_manager import (
    load_state,
    save_state,
    append_trade_log,
    get_brain_settings_for_symbol,
    apply_state_defaults,
    rollover_daily_session,
    release_expired_safeguard_brakes,
    get_active_safeguard_brake,
    mark_safeguard_brake,
)
from core.market_hours import is_symbol_trade_window_open
from core.position_classifier import is_bot_position, is_manual_position
from core.entry_exit_engine import evaluate_entry_exit, format_decision


class TradeManager:
    def __init__(self, connector, checklist_manager, log_callback=None):
        self.connector = connector
        self.checklist = checklist_manager
        self.log_callback = log_callback
        self.state = load_state()

        if "active_trades" not in self.state:
            self.state["active_trades"] = []
        if "trade_tactics" not in self.state:
            self.state["trade_tactics"] = {}
        if "parent_baskets" not in self.state:
            self.state["parent_baskets"] = {}
        if "child_to_parent" not in self.state:
            self.state["child_to_parent"] = {}
        if "initial_r_dist" not in self.state:
            self.state["initial_r_dist"] = {}
        if "initial_r_usd" not in self.state:
            self.state["initial_r_usd"] = {}
        if "trade_excursions" not in self.state:
            self.state["trade_excursions"] = {}
        if "anti_cash_locks" not in self.state:
            self.state["anti_cash_locks"] = {}
        if "be_sl_locks" not in self.state:
            self.state["be_sl_locks"] = {}
        if "be_sl_arms" not in self.state:
            self.state["be_sl_arms"] = {}
        if "rev_confirmations" not in self.state:
            self.state["rev_confirmations"] = {}
        if "last_entry_exit_logs" not in self.state:
            self.state["last_entry_exit_logs"] = {}

        # [NEW V4.4] Tracking chuyên sâu cho Cooldown và Log
        if "exit_reasons" not in self.state:
            self.state["exit_reasons"] = {}
        if "last_close_times" not in self.state:
            self.state["last_close_times"] = {}

    def _get_tick(self, symbol):
        if hasattr(self.connector, "get_tick"):
            tick = self.connector.get_tick(symbol)
            if tick:
                return tick
        tick_data = getattr(data_engine, "_last_tick", {}).get(symbol)
        if tick_data:
            last = float(tick_data.get("last") or tick_data.get("bid") or tick_data.get("ask") or 0.0)
            bid = float(tick_data.get("bid") or last)
            ask = float(tick_data.get("ask") or last)
            return SimpleNamespace(
                symbol=symbol,
                bid=bid,
                ask=ask,
                last=last,
                spread=float(tick_data.get("spread") or max(0.0, ask - bid)),
            )
        tick_data = data_engine.fetch_realtime_tick(symbol)
        if tick_data:
            last = float(tick_data.get("last") or tick_data.get("bid") or tick_data.get("ask") or 0.0)
            bid = float(tick_data.get("bid") or last)
            ask = float(tick_data.get("ask") or last)
            return SimpleNamespace(
                symbol=symbol,
                bid=bid,
                ask=ask,
                last=last,
                spread=float(tick_data.get("spread") or max(0.0, ask - bid)),
            )
        return None

    def _get_symbol_info(self, symbol):
        if hasattr(self.connector, "get_symbol_info"):
            return self.connector.get_symbol_info(symbol)
        return SimpleNamespace(
            symbol=symbol,
            point=float(getattr(config, "DNSE_PRICE_POINT", 0.1)),
            trade_contract_size=float(getattr(config, "DNSE_POINT_VALUE", 100000.0)),
            volume_min=float(getattr(config, "MIN_LOT_SIZE", 1.0) or 1.0),
            volume_max=float(getattr(config, "MAX_LOT_SIZE", 200.0) or 200.0),
            volume_step=float(getattr(config, "LOT_STEP", 1.0) or 1.0),
            trade_stops_level=0.0,
            spread=0.0,
        )

    def _order_ok(self, result):
        return bool(result and getattr(result, "ok", False))

    def _order_ticket(self, result):
        return str(
            getattr(result, "order_id", None)
            or getattr(result, "position_id", None)
            or getattr(result, "order", None)
            or getattr(result, "ticket", "")
        )

    def _position_settlement_dict(self, pos):
        raw = getattr(pos, "raw", {}) or {}
        return {
            "symbol": str(getattr(pos, "symbol", "") or "").upper(),
            "type": int(getattr(pos, "type", 0) or 0),
            "volume": float(getattr(pos, "volume", 0.0) or 0.0),
            "settle_date": raw.get("settle_date", ""),
        }

    def _stock_settled_long_volume(self, symbol, positions=None):
        if not settlement.is_cash_stock(symbol):
            return 0.0
        if positions is None:
            positions = self.connector.get_all_open_positions()
        rows = [self._position_settlement_dict(p) for p in positions or []]
        return settlement.available_to_sell(rows, symbol)

    def _stock_long_only_guard(self, symbol, direction):
        if str(direction or "").upper() != "SELL" or not settlement.is_cash_stock(symbol):
            return None
        available = self._stock_settled_long_volume(symbol)
        if available <= 0:
            return f"SAFEGUARD_FAIL|NO_SETTLED_LONG|{symbol} không có cổ phiếu đã về để bán/đóng; không mở short CKCS."
        return None

    def _close_with_t2_log(self, pos, reason=""):
        result = self.connector.close_position(pos)
        if result and getattr(result, "error", "") == "STOCK_NOT_SETTLED_T2":
            ticket = str(getattr(pos, "ticket", "") or getattr(pos, "position_id", "") or "")
            raw = getattr(pos, "raw", {}) or {}
            settle = raw.get("settle_date", "")
            key = f"{ticket}|T2"
            now = time.time()
            logs = self.state.setdefault("last_t2_close_logs", {})
            if now - float(logs.get(key, 0.0) or 0.0) > 900:
                suffix = f" chờ về {str(settle)[:10]}" if settle else ""
                reason_text = f" ({reason})" if reason else ""
                self.log(f"[T+2] treo {getattr(pos, 'symbol', '')}{suffix}{reason_text}", target="bot")
                logs[key] = now
                save_state(self.state)
        return result

    def _record_open_trade(self, ticket, symbol, direction, volume, entry_price, sl=0.0, tp=0.0, result=None):
        if not ticket:
            return
        s_ticket = str(ticket)
        self.state.setdefault("trade_symbols", {})[s_ticket] = symbol
        self.state.setdefault("trade_directions", {})[s_ticket] = direction
        self.state.setdefault("trade_volumes", {})[s_ticket] = float(volume or 0.0)
        self.state.setdefault("trade_prices", {})[s_ticket] = float(entry_price or 0.0)
        self.state.setdefault("trade_sl", {})[s_ticket] = float(sl or 0.0)
        self.state.setdefault("trade_tp", {})[s_ticket] = float(tp or 0.0)
        if result:
            self.state.setdefault("trade_order_ids", {})[s_ticket] = str(getattr(result, "order_id", "") or "")
            self.state.setdefault("trade_position_ids", {})[s_ticket] = str(getattr(result, "position_id", "") or "")

    def _should_log_entry_exit_decision(self, symbol, direction, decision, safeguard_cfg):
        status = decision.get("status")
        if status in ("READY", "ERROR"):
            return True

        try:
            cooldown_sec = float(safeguard_cfg.get("LOG_COOLDOWN_MINUTES", 60.0)) * 60.0
        except Exception:
            cooldown_sec = 3600.0

        zone = decision.get("entry_zone") or ()
        current_price = float(decision.get("current_price", 0) or 0)
        wait_side = "IN"
        if zone and current_price < float(zone[0]):
            wait_side = "BELOW"
        elif zone and current_price > float(zone[1]):
            wait_side = "ABOVE"
        signature = {
            "status": status,
            "wait_side": wait_side,
            "entry_tactic": decision.get("entry_tactic", ""),
            "exit_tactic": decision.get("exit_tactic", ""),
        }
        key = f"{symbol}|{direction}|{decision.get('entry_tactic', '')}"
        now = time.time()
        logs = self.state.setdefault("last_entry_exit_logs", {})
        last = logs.get(key, {})
        if last.get("signature") != signature or now - float(last.get("time", 0) or 0) >= max(0.0, cooldown_sec):
            logs[key] = {"time": now, "signature": signature}
            return True
        return False

    def _position_profit_usd(self, pos):
        return pos.profit + pos.swap + getattr(pos, "commission", 0.0)

    def _calc_risk_usd(self, symbol, order_type, volume, entry_price, sl_price):
        if not sl_price or sl_price <= 0:
            return 0.0
        side = "LONG" if order_type == 0 else "SHORT"
        risk = self.connector.calculate_profit(symbol, side, volume, entry_price, sl_price)
        broker_risk = abs(float(risk or 0.0))
        formula_risk = 0.0
        try:
            sym_info = self._get_symbol_info(symbol)
            contract_size = float(getattr(sym_info, "trade_contract_size", 1.0) or 1.0)
            formula_risk = abs(float(entry_price) - float(sl_price)) * float(volume) * contract_size
        except Exception:
            formula_risk = 0.0
        return max(broker_risk, formula_risk)

    def _get_ticket_risk_usd(self, pos):
        s_ticket = str(pos.ticket)
        risk_usd = float(self.state.get("initial_r_usd", {}).get(s_ticket, 0.0) or 0.0)
        current_sl_risk = 0.0
        if getattr(pos, "sl", 0.0) and pos.sl > 0:
            is_buy = pos.type == 0
            sl_is_loss_side = (is_buy and pos.sl < pos.price_open) or (
                not is_buy and pos.sl > pos.price_open
            )
            if sl_is_loss_side:
                current_sl_risk = self._calc_risk_usd(
                    pos.symbol, pos.type, pos.volume, pos.price_open, pos.sl
                )
        if risk_usd > 0:
            if current_sl_risk > risk_usd:
                self.state.setdefault("initial_r_usd", {})[s_ticket] = current_sl_risk
                return current_sl_risk
            return risk_usd

        one_r_dist = float(self.state.get("initial_r_dist", {}).get(s_ticket, 0.0) or 0.0)
        if one_r_dist <= 0:
            if current_sl_risk > 0:
                self.state.setdefault("initial_r_usd", {})[s_ticket] = current_sl_risk
            return current_sl_risk
        is_buy = pos.type == 0
        initial_sl = pos.price_open - one_r_dist if is_buy else pos.price_open + one_r_dist
        risk_usd = self._calc_risk_usd(pos.symbol, pos.type, pos.volume, pos.price_open, initial_sl)
        if risk_usd > 0:
            self.state.setdefault("initial_r_usd", {})[s_ticket] = risk_usd
        return risk_usd

    def _get_ticket_r_dist(self, pos):
        s_ticket = str(pos.ticket)
        one_r_dist = float(self.state.get("initial_r_dist", {}).get(s_ticket, 0.0) or 0.0)
        current_sl_dist = 0.0
        if getattr(pos, "sl", 0.0) and pos.sl > 0:
            is_buy = pos.type == 0
            sl_is_loss_side = (is_buy and pos.sl < pos.price_open) or (
                not is_buy and pos.sl > pos.price_open
            )
            if sl_is_loss_side:
                current_sl_dist = abs(pos.price_open - pos.sl)
        if current_sl_dist > one_r_dist:
            self.state.setdefault("initial_r_dist", {})[s_ticket] = current_sl_dist
            return current_sl_dist
        return one_r_dist

    def _resolve_money_value(self, value, unit, pos=None, equity=None):
        raw = float(value or 0.0)
        unit = (unit or "USD").upper().replace(" ", "")
        if unit == "R":
            risk_usd = self._get_ticket_risk_usd(pos) if pos else 0.0
            if risk_usd <= 0:
                return raw
            return risk_usd * raw
        if unit in ["%R", "PERCENT_R"]:
            # Legacy config support: old UI used percent-of-R, e.g. 50 = 0.5R.
            risk_usd = self._get_ticket_risk_usd(pos) if pos else 0.0
            if risk_usd <= 0:
                return raw / 100.0
            return risk_usd * raw / 100.0
        if unit in ["%EQUITY", "EQUITY", "PERCENT_EQUITY"]:
            if equity is None:
                acc = self.connector.get_account_info()
                equity = acc.get("equity", 0.0) if acc else 0.0
            if not equity or equity <= 0:
                return raw
            return float(equity or 0.0) * raw / 100.0
        return raw

    def _update_trade_excursion(self, pos):
        s_ticket = str(pos.ticket)
        profit_usd = self._position_profit_usd(pos)
        excursions = self.state.setdefault("trade_excursions", {})
        cur = excursions.get(s_ticket, {})
        mae = min(float(cur.get("mae_usd", profit_usd)), profit_usd)
        mfe = max(float(cur.get("mfe_usd", profit_usd)), profit_usd)
        excursions[s_ticket] = {"mae_usd": mae, "mfe_usd": mfe}
        return excursions[s_ticket]

    def _anti_cash_lock_key(self, symbol, direction):
        return f"{symbol}|{direction}"

    def _set_anti_cash_lock(self, pos, ttl_sec):
        if ttl_sec <= 0:
            return
        direction = "BUY" if pos.type == 0 else "SELL"
        key = self._anti_cash_lock_key(pos.symbol, direction)
        self.state.setdefault("anti_cash_locks", {})[key] = time.time() + ttl_sec

    def _check_anti_cash_reentry_lock(self, symbol, direction):
        locks = self.state.setdefault("anti_cash_locks", {})
        key = self._anti_cash_lock_key(symbol, direction)
        until = float(locks.get(key, 0.0) or 0.0)
        if until <= 0:
            return None
        now = time.time()
        if until <= now:
            locks.pop(key, None)
            return None
        return until

    def _set_be_sl_lock(self, symbol, direction, ttl_sec):
        if ttl_sec <= 0 or not symbol or not direction:
            return
        key = self._anti_cash_lock_key(symbol, direction)
        self.state.setdefault("be_sl_locks", {})[key] = time.time() + ttl_sec
        self.log(
            f"[BE_SL] Re-entry lock {symbol} {direction} trong {ttl_sec}s.",
            target="bot",
        )

    def _check_be_sl_reentry_lock(self, symbol, direction):
        locks = self.state.setdefault("be_sl_locks", {})
        key = self._anti_cash_lock_key(symbol, direction)
        until = float(locks.get(key, 0.0) or 0.0)
        if until <= 0:
            return None
        now = time.time()
        if until <= now:
            locks.pop(key, None)
            return None
        return until

    def log(self, msg, error=False, target=None):
        if self.log_callback:
            try:
                self.log_callback(msg, error=error, target=target)
            except TypeError:
                self.log_callback(msg, error=error)
        else:
            logger = logging.getLogger("TradeManager")
            if error:
                logger.error(msg)
            else:
                logger.info(msg)

    def set_exit_reason(self, ticket, reason):
        self.state["exit_reasons"][str(ticket)] = reason
        save_state(self.state)

    def _get_brain_settings(self, symbol=None):
        return get_brain_settings_for_symbol(symbol)

    def _sync_state_lifecycle(self):
        apply_state_defaults(self.state)
        changed = rollover_daily_session(self.state)
        changed = release_expired_safeguard_brakes(self.state) or changed
        if changed:
            save_state(self.state)
        return changed

    def check_and_trigger_cooldown(self, symbol=None):
        self._sync_state_lifecycle()
        brain = self._get_brain_settings()
        safeguard_cfg = brain.get("bot_safeguard", {})

        max_loss_pct = float(safeguard_cfg.get("MAX_DAILY_LOSS_PERCENT", 2.5))
        max_trades = int(safeguard_cfg.get("MAX_TRADES_PER_DAY", 30))
        max_streak = int(safeguard_cfg.get("MAX_LOSING_STREAK", 3))
        loss_mode = str(safeguard_cfg.get("LOSS_COUNT_MODE", "TOTAL")).upper()
        cooldown_hours = float(safeguard_cfg.get("GLOBAL_COOLDOWN_HOURS", 4.0))

        start_bal = self.state.get("starting_balance", 0)
        pnl = self.state.get("bot_pnl_today", 0.0)
        loss_pct = (pnl / start_bal * 100) if start_bal > 0 else 0

        trades = self.state.get("bot_trades_today", 0)
        losses = (
            self.state.get("bot_symbol_losing_streak", {}).get(symbol, 0)
            if loss_mode == "STREAK"
            else self.state.get("bot_daily_loss_count", 0)
        )

        triggered = False
        reason = ""

        if loss_pct <= -max_loss_pct:
            triggered = True
            reason = f"Chạm Max Loss ({loss_pct:.2f}% / {max_loss_pct}%)"
        elif trades >= max_trades:
            triggered = True
            reason = f"Chạm Max Trades ({trades}/{max_trades})"
        elif losses >= max_streak:
            triggered = True
            scope = symbol if loss_mode == "STREAK" and symbol else "BOT"
            reason = f"Chạm Max {loss_mode} Loss {scope} ({losses}/{max_streak})"

        if triggered:
            # [NEW V5.2] Xử lý theo GLOBAL_BRAKE_MODE
            brake_mode = safeguard_cfg.get("GLOBAL_BRAKE_MODE", "Mode 1: Total Freeze")
            is_symbol_brake_mode = "Mode 2" in str(brake_mode)
            if get_active_safeguard_brake(self.state, "GLOBAL"):
                return
            if is_symbol_brake_mode and symbol and get_active_safeguard_brake(
                self.state, "SYMBOL", symbol=symbol
            ):
                return

            cooldown_time = time.time() + (cooldown_hours * 3600)
            trigger_snapshot = {
                "loss_pct": loss_pct,
                "trades": trades,
                "losses": losses,
                "loss_mode": loss_mode,
                "max_loss_pct": max_loss_pct,
                "max_trades": max_trades,
                "max_streak": max_streak,
            }

            if is_symbol_brake_mode and symbol:
                # Mode 2: Symbol Isolation (Chỉ phạt mã này)
                item, created = mark_safeguard_brake(
                    self.state,
                    "SYMBOL",
                    reason,
                    cooldown_time,
                    symbol=symbol,
                    trigger=trigger_snapshot,
                )
                self.state.setdefault("bot_last_fail_times", {})[symbol] = float(
                    item.get("until", cooldown_time)
                )
                if created:
                    self.log(f"🛑 [SAFEGUARD] {reason}. Bot Phạt Cooldown CÁCH LY {symbol} (Mode 2) trong {cooldown_hours} giờ.", target="bot")
            else:
                # Mode 1: Total Freeze (Phạt toàn hệ thống)
                item, created = mark_safeguard_brake(
                    self.state,
                    "GLOBAL",
                    reason,
                    cooldown_time,
                    trigger=trigger_snapshot,
                )
                self.state["cooldown_until"] = float(item.get("until", cooldown_time))
                if created:
                    self.log(f"🛑 [SAFEGUARD] {reason}. Bot Phạt TOÀN HỆ THỐNG (Mode 1) trong {cooldown_hours} giờ.", target="bot")

            save_state(self.state)

    # ====================================================================================
    # [NEW V4.4] HÀM CẮT LỆNH KHI CÓ TÍN HIỆU ĐẢO CHIỀU (REVERSE SIGNAL)
    # ====================================================================================
    def close_opposite_positions(self, symbol, new_direction, min_hold_time=180):
        import core.storage_manager as storage_manager

        magics = storage_manager.get_magic_numbers()
        safe_cfg = self._get_brain_settings(symbol).get("bot_safeguard", {})

        positions = [
            p
            for p in self.connector.get_all_open_positions()
            if p.symbol == symbol and is_bot_position(p, magics)
        ]
        opposite_type = (
            1 if new_direction == "BUY" else 0
        )

        closed_count = 0
        now = time.time()

        for p in positions:
            if p.type == opposite_type:
                hold_time = now - p.time
                profit_usd = p.profit + p.swap + getattr(p, "commission", 0.0)

                # [NEW V4.4] REFINED PNL CHECK
                pnl_ok = True
                if safe_cfg.get("CLOSE_ON_REVERSE_USE_PNL", True):
                    acc = self.connector.get_account_info()
                    equity = acc.get("equity", 0.0) if acc else 0.0
                    min_profit = self._resolve_money_value(
                        safe_cfg.get("REV_CLOSE_MIN_PROFIT", 0.0),
                        safe_cfg.get("REV_CLOSE_MIN_PROFIT_UNIT", "USD"),
                        pos=p,
                        equity=equity,
                    )
                    max_loss = -abs(
                        self._resolve_money_value(
                            safe_cfg.get("REV_CLOSE_MAX_LOSS", 0.0),
                            safe_cfg.get("REV_CLOSE_MAX_LOSS_UNIT", "USD"),
                            pos=p,
                            equity=equity,
                        )
                    )

                    if profit_usd >= 0:
                        if min_profit > 0 and profit_usd < min_profit:
                            pnl_ok = False
                    else:
                        if (
                            max_loss != 0 and profit_usd > max_loss
                        ):  # Example: -15 > -20 -> hold, -20 <= -20 -> close
                            pnl_ok = False

                if hold_time >= min_hold_time and pnl_ok:
                    self.log(
                        f"  [REVERSE] Tín hiệu đảo chiều ({new_direction}) | PnL: ${profit_usd:.2f}! Cắt lệnh #{p.ticket} (Hold: {hold_time:.0f}s)",
                        target="bot",
                    )
                    self.state["exit_reasons"][str(p.ticket)] = (
                        f"Reverse_to_{new_direction}"
                    )

                    # Chạy luồng ẩn để cắt lệnh không làm kẹt
                    def _safe_close(pos, ticket_str=str(p.ticket)):
                        try:
                            result = self._close_with_t2_log(pos, "Reverse")
                            if result and not self._order_ok(result) and getattr(result, "error", "") != "STOCK_NOT_SETTLED_T2":
                                self.log(f"⚠️ [REVERSE] Đóng lệnh #{ticket_str} THẤT BẠI: {getattr(result, 'comment', 'Unknown')}", target="bot")
                        except Exception as e:
                            self.log(f"⚠️ [REVERSE] Lỗi đóng lệnh #{ticket_str}: {e}", target="bot")
                    threading.Thread(
                        target=_safe_close,
                        args=(p,),
                        daemon=True,
                    ).start()
                    closed_count += 1
                else:
                    # [NEW V5] Chống spam log đảo chiều (15 phút / lần)
                    s_ticket = str(p.ticket)
                    last_log = self.state.get("last_rev_log_time", {}).get(s_ticket, 0)
                    log_cooldown = float(safe_cfg.get("LOG_COOLDOWN_MINUTES", 60.0)) * 60.0
                    if time.time() - last_log > log_cooldown:
                        reason = "HoldTime" if hold_time < min_hold_time else "PnL_Filter"
                        self.log(f"⏳ [REVERSE] Tín hiệu ngược nhưng chưa đủ điều kiện cắt #{p.ticket} ({reason}). Đang theo dõi ngầm...", target="bot")
                        if "last_rev_log_time" not in self.state: self.state["last_rev_log_time"] = {}
                        self.state["last_rev_log_time"][s_ticket] = time.time()

        return closed_count

    # ====================================================================================
    # 1. HÀM THỰC THI LỆNH CHO BOT (HỖ TRỢ ENTRY, DCA, PCA, DYNAMIC SL & STRICT RISK)
    # ====================================================================================
    def execute_bot_trade(
        self, direction, symbol, context, market_mode="ANY", signal_class="ENTRY", tactic_override=None
    ):
        config.SYMBOL = symbol
        self._sync_state_lifecycle()
        acc_info = self.connector.get_account_info()
        brain = self._get_brain_settings(symbol)
        safeguard_cfg = brain.get("bot_safeguard", {})

        is_open, closed_reason = is_symbol_trade_window_open(symbol)
        if not is_open:
            return f"SAFEGUARD_FAIL|Market Hours|{closed_reason}"

        # [NEW V4.4] KIỂM TRA ĐẢO CHIỀU TRƯỚC KHI VÀO LỆNH (Cắt lệnh ngược chiều giải phóng Margin)
        lock_until = self._check_anti_cash_reentry_lock(symbol, direction)
        if lock_until:
            wait_s = max(1, int(lock_until - time.time()))
            return f"SAFEGUARD_FAIL|AntiCash_Reentry_Lock|{symbol} {direction} bị khóa vào lại sau ANTI CASH, còn {wait_s}s."

        be_lock_until = self._check_be_sl_reentry_lock(symbol, direction)
        if be_lock_until:
            wait_s = max(1, int(be_lock_until - time.time()))
            return f"SAFEGUARD_FAIL|BE_SL_Reentry_Lock|{symbol} {direction} bị khóa vào lại sau BE_SL, còn {wait_s}s."

        close_on_reverse = safeguard_cfg.get("CLOSE_ON_REVERSE", False)
        closed_on_reverse = 0
        if close_on_reverse and signal_class == "ENTRY":
            min_hold = safeguard_cfg.get("CLOSE_ON_REVERSE_MIN_TIME", 180)
            closed_on_reverse = self.close_opposite_positions(symbol, direction, min_hold)
            if closed_on_reverse and settlement.is_cash_stock(symbol) and str(direction or "").upper() == "SELL":
                return f"SAFEGUARD_FAIL|REV_CLOSE_ONLY|{symbol} đã phát đóng long CKCS; không mở short."

        stock_guard = self._stock_long_only_guard(symbol, direction)
        if stock_guard:
            return stock_guard

        # Gọi Checklist độc lập của Bot
        res = self.checklist.run_bot_safeguard_checks(
            acc_info, self.state, symbol, safeguard_cfg, signal_class, direction
        )

        if not res["passed"]:
            fail_names = [c["name"] for c in res["checks"] if c["status"] == "FAIL"]
            fail_reasons = [c["msg"] for c in res["checks"] if c["status"] == "FAIL"]
            name_str = ",".join(fail_names) if fail_names else "UNK"
            reason_str = (
                " | ".join(fail_reasons)
                if fail_reasons
                else "Lỗi Safeguard không xác định"
            )
            return f"SAFEGUARD_FAIL|{name_str}|{reason_str}"

        tick = self._get_tick(symbol)
        sym_info = self._get_symbol_info(symbol)
        if not tick or not sym_info:
            return "ERR_NO_TICK"

        current_price = tick.ask if direction == "BUY" else tick.bid
        risk_tsl = brain.get("risk_tsl", {})
        order_type = 0 if direction == "BUY" else 1
        ee_decision = None
        ee_sl_override = None
        ee_tp_override = None
        entry_exit_cfg = brain.get("entry_exit", {})
        if signal_class == "ENTRY":
            pending_key = f"{symbol}|{direction}"
            pending_map = self.state.setdefault("pending_entry_exit", {})
            for side in ("BUY", "SELL"):
                if side != direction:
                    pending_map.pop(f"{symbol}|{side}", None)
            pending = pending_map.get(pending_key)
            if pending:
                if pending.get("direction") != direction or float(pending.get("expires_at", 0) or 0) < time.time():
                    pending_map.pop(pending_key, None)
                    pending = None
            ee_decision = evaluate_entry_exit(
                symbol,
                direction,
                current_price,
                context,
                entry_exit_cfg,
                pending=pending,
            )
            if ee_decision.get("status") != "OFF" and self._should_log_entry_exit_decision(symbol, direction, ee_decision, safeguard_cfg):
                self.log(f"[E/E] {format_decision(ee_decision)}", target="bot-log")
            if entry_exit_cfg.get("enabled") and not entry_exit_cfg.get("preview_only", True):
                if ee_decision.get("status") == "READY":
                    pending_map.pop(pending_key, None)
                    ee_sl_override = ee_decision.get("sl")
                    ee_tp_override = ee_decision.get("tp")
                elif ee_decision.get("status") == "WAIT":
                    pending_map[pending_key] = ee_decision
                    save_state(self.state)
                    return f"SAFEGUARD_FAIL|EntryExit_WAIT|{format_decision(ee_decision)}"
                else:
                    pending_map.pop(pending_key, None)
                    save_state(self.state)
                    return f"SAFEGUARD_FAIL|EntryExit_{ee_decision.get('status')}|{ee_decision.get('reason', 'Entry/Exit blocked')}"

        # TÍNH TOÁN SMART SL TỪ CẤU HÌNH BRAIN
        sl_group = risk_tsl.get("base_sl", "G2")
        if "DYNAMIC" in sl_group:
            sl_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"

        atr_key = f"atr_{sl_group}"
        swing_l_key = f"swing_low_{sl_group}"
        swing_h_key = f"swing_high_{sl_group}"

        atr_val = context.get(atr_key) or context.get("atr_entry") or 0.0
        swing_l = context.get(swing_l_key)
        swing_h = context.get(swing_h_key)

        # [KAISER FIX]: Sử dụng Multiplier từ Brain (Mặc định 0.2 nếu không có)
        sl_mult = float(
            risk_tsl.get("sl_atr_multiplier", getattr(config, "sl_atr_multiplier", 0.2))
        )
        buffer_atr = float(atr_val or 0.0) * sl_mult

        if ee_sl_override:
            sl_price = float(ee_sl_override)
            raw_swing_sl = sl_price
            sl_distance = abs(current_price - sl_price)
        else:
            # CHỐT CHẶN 1: Bẫy lỗi mất Data
            if (
                atr_key not in context
                or swing_l_key not in context
                or swing_h_key not in context
            ):
                return f"SAFEGUARD_FAIL|No_Data|Mất dữ liệu Swing/ATR của {sl_group}. Từ chối vào lệnh."

            raw_swing_sl = swing_l if direction == "BUY" else swing_h
            sl_price = swing_l - buffer_atr if direction == "BUY" else swing_h + buffer_atr
            sl_distance = abs(current_price - sl_price)

        # CHỐT CHẶN 2: Bẫy lỗi SL cực hẹp (Nhỏ hơn 0.05% giá trị tài sản)
        min_safe_dist = current_price * 0.0005
        if sl_distance < min_safe_dist:
            return f"SAFEGUARD_FAIL|SL_Too_Tight|Khoảng cách SL quá hẹp ({sl_distance:.5f}). Từ chối để chống nổ Lot."

        parent_pos = None
        import core.storage_manager as storage_manager

        magics = storage_manager.get_magic_numbers()
        bot_magic = magics.get("bot_magic", 9999)
        if signal_class in ["DCA", "PCA"]:
            positions = [
                p
                for p in self.connector.get_all_open_positions()
                if p.symbol == symbol and is_bot_position(p, magics)
            ]
            if positions:
                parent_pos = sorted(positions, key=lambda x: x.time)[0]

        strict_fee_per_lot = 0.0
        if risk_tsl.get("strict_risk", False):
            acc_type = getattr(config, "DEFAULT_ACCOUNT_TYPE", "STANDARD")
            if acc_type in ["PRO", "STANDARD"]:
                comm_rate = 0.0
            else:
                comm_rate = getattr(config, "COMMISSION_RATES", {}).get(
                    symbol,
                    getattr(config, "ACCOUNT_TYPES_CONFIG", {})
                    .get(acc_type, {})
                    .get("COMMISSION_PER_LOT", 7.0),
                )
            spread_cost = (
                sym_info.spread * sym_info.point * sym_info.trade_contract_size
                if sym_info
                else 0.0
            )
            strict_fee_per_lot = comm_rate + spread_cost

        # [NEW V4.4] TÍNH VOLUME - TÍCH HỢP FIXED LOT & STRICT MIN LOT
        sym_cfgs = brain.get("symbol_configs", {}).get(symbol, {})
        fixed_lot = float(sym_cfgs.get("fixed_lot", 0.0))
        strict_min_lot = safeguard_cfg.get("STRICT_MIN_LOT", False)

        vol_min = (
            sym_info.volume_min if sym_info else getattr(config, "MIN_LOT_SIZE", 0.01)
        )
        vol_max = (
            sym_info.volume_max if sym_info else getattr(config, "MAX_LOT_SIZE", 200.0)
        )
        vol_step = (
            sym_info.volume_step if sym_info else getattr(config, "LOT_STEP", 0.01)
        )

        if parent_pos and signal_class in ["DCA", "PCA"]:
            cfg_key = "dca_config" if signal_class == "DCA" else "pca_config"
            mult = brain.get(
                cfg_key, getattr(config, f"{signal_class}_CONFIG", {})
            ).get("STEP_MULTIPLIER", 1.5)
            raw_lot = parent_pos.volume * mult
            lot_size = round(raw_lot / vol_step) * vol_step
            lot_size = max(vol_min, min(lot_size, vol_max))

        elif fixed_lot > 0:
            lot_size = fixed_lot
            # Vẫn gọi qua connector để lấy safe_sl chống lỗi sàn
            _, safe_sl = self.connector.calculate_lot_size(
                symbol, 10.0, sl_price, order_type, 0
            )
            sl_price = safe_sl if safe_sl else sl_price

        else:
            base_risk = risk_tsl.get(
                "base_risk", getattr(config, "BOT_RISK_PERCENT", 0.3)
            )
            mode_multiplier = risk_tsl.get("mode_multipliers", {}).get(market_mode, 1.0)
            final_risk_percent = base_risk * mode_multiplier
            risk_usd = acc_info["equity"] * (final_risk_percent / 100.0)

            calc_lot, safe_sl = self.connector.calculate_lot_size(
                symbol, risk_usd, sl_price, order_type, strict_fee_per_lot
            )

            # Xử lý Strict Min Lot Rejection
            if calc_lot is None or calc_lot == 0:
                if strict_min_lot:
                    return "SAFEGUARD_FAIL|Strict Min Lot|Từ chối do Vol tính toán < Min Lot (Rủi ro cao)"
                else:
                    return "ERR_LOT_CALC_FAILED"

            lot_size = calc_lot
            sl_price = safe_sl

        # [NEW V4.4] Áp dụng Max Lot Cap (Tính cho từng lệnh riêng lẻ)
        max_lot_cap = float(sym_cfgs.get("max_lot_cap", 0.0))
        if max_lot_cap > 0:
            lot_size = min(lot_size, max_lot_cap)

        child_sl_source = "CALCULATED"
        child_uses_parent_sl = False

        # TÍNH TP
        if parent_pos and signal_class in ["DCA", "PCA"]:
            cfg_key = "dca_config" if signal_class == "DCA" else "pca_config"
            child_cfg = brain.get(cfg_key, getattr(config, f"{signal_class}_CONFIG", {}))
            use_parent_sl = child_cfg.get("USE_PARENT_SL", True)
            tp_price = parent_pos.tp
            if use_parent_sl:
                sl_price = parent_pos.sl
                child_sl_source = f"PARENT#{parent_pos.ticket}"
                child_uses_parent_sl = True
            else:
                sl_price = raw_swing_sl
                sl_distance = abs(current_price - sl_price)
                child_sl_source = f"SWINGPOINT_{sl_group}"
        else:
            use_swing_tp = safeguard_cfg.get("BOT_USE_SWING_TP", False)
            use_rr_tp = safeguard_cfg.get("BOT_USE_RR_TP", True)
            ee_exit_tactic = str(entry_exit_cfg.get("exit_tactic", "")).upper()
            ee_tp_disabled = ee_exit_tactic in ("NO_TP", "OFF") or (
                ee_decision and ee_decision.get("tp_disabled")
            )

            if ee_tp_disabled:
                tp_price = 0.0
            elif ee_tp_override is not None:
                tp_price = float(ee_tp_override)
            elif use_swing_tp and context and swing_h and swing_l and atr_val:
                tp_price = (
                    (swing_h - buffer_atr)
                    if direction == "BUY"
                    else (swing_l + buffer_atr)
                )
            elif use_rr_tp:
                # Đọc từ JSON (safeguard_cfg) → fallback config
                reward_ratio = float(
                    safeguard_cfg.get(
                        "BOT_TP_RR_RATIO", getattr(config, "BOT_TP_RR_RATIO", 1.5)
                    )
                )
                tp_price = (
                    current_price + (sl_distance * reward_ratio)
                    if direction == "BUY"
                    else current_price - (sl_distance * reward_ratio)
                )
            else:
                tp_price = 0.0

        comment = f"[BOT]_AUTO_{signal_class}"
        # AUTO: trong phiên ATO/ATC thì đặt orderType ATO/ATC, ngoài phiên -> None (LO/MOK).
        from core.market_hours import resolve_order_kind
        order_kind = resolve_order_kind(symbol, safeguard_cfg.get("BOT_ORDER_MODE", "NORMAL"))
        result = self.connector.place_order(
            symbol, order_type, lot_size, sl_price, tp_price, bot_magic, comment, order_kind=order_kind
        )

        if self._order_ok(result):
            ticket_id = self._order_ticket(result)
            self._record_open_trade(ticket_id, symbol, direction, lot_size, current_price, sl_price, tp_price, result)
            bot_tactic = tactic_override or risk_tsl.get(
                "bot_tsl", getattr(config, "BOT_DEFAULT_TSL", "BE+STEP_R+SWING")
            )
            dca_cfg = brain.get("dca_config", getattr(config, "DCA_CONFIG", {}))
            pca_cfg = brain.get("pca_config", getattr(config, "PCA_CONFIG", {}))

            if dca_cfg.get("ENABLED", False) and "AUTO_DCA" not in bot_tactic:
                bot_tactic += "+AUTO_DCA"
            if pca_cfg.get("ENABLED", False) and "AUTO_PCA" not in bot_tactic:
                bot_tactic += "+AUTO_PCA"

            # [FIX V4.4]: Tự động gán Reverse Close (REV_C) cho lệnh Bot nếu được bật
            if (
                safeguard_cfg.get("CLOSE_ON_REVERSE", False)
                and "REV_C" not in bot_tactic
            ):
                bot_tactic += "+REV_C"

            self.update_trade_tactic(ticket_id, bot_tactic)
            if (
                ee_decision
                and ee_decision.get("status") == "READY"
                and entry_exit_cfg.get("enabled")
                and not entry_exit_cfg.get("preview_only", True)
            ):
                ee_label = ee_decision.get("entry_tactic") or "OFF"
                exit_label = ee_decision.get("exit_tactic")
                if exit_label:
                    ee_label = f"{ee_label}->{exit_label}"
                self.update_trade_entry_exit_tactic(ticket_id, ee_label)
            self.state["initial_r_dist"][str(ticket_id)] = sl_distance
            self.state.setdefault("initial_r_usd", {})[str(ticket_id)] = self._calc_risk_usd(
                symbol, order_type, lot_size, current_price, sl_price
            )
            try:
                from ai_advisor.history import record_trade_opened_data

                record_trade_opened_data(
                    ticket_id,
                    symbol=symbol,
                    open_time=time.time(),
                    source=f"bot_order_success:{signal_class}",
                    payload={
                        "direction": direction,
                        "volume": lot_size,
                        "entry_price": current_price,
                        "sl": sl_price,
                        "tp": tp_price,
                        "signal_class": signal_class,
                        "market_mode": market_mode,
                        "tactic": bot_tactic,
                        "entry_exit_tactic": self.get_trade_entry_exit_tactic(ticket_id),
                        "market_context": context or {},
                    },
                )
            except Exception:
                pass

            if parent_pos and signal_class in ["DCA", "PCA"]:
                s_parent = str(parent_pos.ticket)
                s_child = str(ticket_id)
                if s_parent not in self.state["parent_baskets"]:
                    self.state["parent_baskets"][s_parent] = []
                self.state["parent_baskets"][s_parent].append(s_child)
                self.state["child_to_parent"][s_child] = s_parent
                if child_uses_parent_sl:
                    self.state["initial_r_dist"][s_child] = self.state[
                        "initial_r_dist"
                    ].get(s_parent, sl_distance)
                else:
                    self.state["initial_r_dist"][s_child] = sl_distance
                save_state(self.state)

                self.log(
                    f"🔥 [{signal_class}] Mẹ #{s_parent} đẻ Con #{s_child} | Vol: {lot_size:.2f} | Entry: {current_price:.5f} | SL: {sl_price:.5f} ({child_sl_source}) | TP: {tp_price:.5f}",
                    target="bot",
                )
                if signal_class == "DCA":
                    threading.Thread(
                        target=self._adjust_basket_tp,
                        args=(parent_pos.ticket,),
                        daemon=True,
                    ).start()
            else:
                self.log(
                    f"🚀 [BOT EXEC] {direction} {symbol} #{ticket_id} | Lot: {lot_size:.2f} | Entry: {current_price:.5f} | SL: {sl_price:.5f} | TP: {tp_price:.5f} | TSL: {bot_tactic} | E/E: {self.get_trade_entry_exit_tactic(ticket_id)}",
                    target="bot",
                )
                if signal_class == "ENTRY":
                    self.state["bot_last_entry_times"][symbol] = time.time()

                self.state["bot_trades_today"] = (
                    self.state.get("bot_trades_today", 0) + 1
                )
                self.state["trades_today_count"] = (
                    self.state.get("trades_today_count", 0) + 1
                )
                save_state(self.state)
                self.check_and_trigger_cooldown(symbol)

            return "SUCCESS"

        err = getattr(result, "error", "") or "API_ERROR"
        msg = getattr(result, "message", "") or ""
        if msg or err != "API_ERROR":
            self.log(f"⛔ [BOT] Đặt lệnh {symbol} thất bại: {err} {msg}".strip(), target="bot")
        return "API_ERROR"

    def _adjust_basket_tp(self, parent_ticket):
        time.sleep(2)
        s_parent = str(parent_ticket)
        children = self.state.get("parent_baskets", {}).get(s_parent, [])
        if not children:
            return

        tickets = {str(parent_ticket), *[str(t) for t in children]}
        positions = [
            p for p in self.connector.get_all_open_positions() if str(p.ticket) in tickets
        ]
        if not positions:
            return

        total_lot = sum(p.volume for p in positions)
        total_value = sum(p.volume * p.price_open for p in positions)
        avg_price = total_value / total_lot

        sym_info = self._get_symbol_info(positions[0].symbol)
        is_buy = positions[0].type == 0

        tp_offset = 50 * sym_info.point
        new_tp = avg_price + tp_offset if is_buy else avg_price - tp_offset
        new_tp = round(new_tp / sym_info.point) * sym_info.point

        for p in positions:
            if abs(p.tp - new_tp) > sym_info.point * 2:
                self.connector.modify_position(p, p.sl, new_tp)

        self.log(
            f"🔄 [BASKET RESCUE] Kéo TP Rổ #{parent_ticket} về: {new_tp:.5f}",
            target="bot",
        )

    # ====================================================================================
    # 2. HÀM THỰC THI LỆNH TAY (MANUAL)
    # ====================================================================================
    def execute_manual_trade(
        self,
        direction,
        preset_name,
        symbol,
        strict_mode,
        context,  # <--- Thêm biến context vào khai báo
        manual_lot=0.0,
        manual_tp=0.0,
        manual_sl=0.0,
        bypass_checklist=False,
        tactic_str="OFF",
        order_kind=None,
    ):
        config.SYMBOL = symbol
        acc_info = self.connector.get_account_info()
        res = self.checklist.run_pre_trade_checks(
            acc_info, self.state, symbol, strict_mode
        )

        if not res["passed"] and not bypass_checklist:
            return "CHECKLIST_FAIL"

        stock_guard = self._stock_long_only_guard(symbol, direction)
        if stock_guard:
            return stock_guard

        params = getattr(config, "PRESETS", {}).get(
            preset_name, {"SL_PERCENT": 0.4, "TP_RR_RATIO": 1.5, "RISK_PERCENT": 0.3}
        )
        sl_mode = str(params.get("MANUAL_SL_MODE") or ("SWING_REJECTION" if params.get("USE_SWING_SL", False) else "PERCENT")).upper()

        tick = self._get_tick(symbol)
        sym_info = self._get_symbol_info(symbol)
        if not tick or not sym_info:
            return "ERR_NO_TICK"

        price = tick.ask if direction == "BUY" else tick.bid
        equity = acc_info["equity"]
        order_type = 0 if direction == "BUY" else 1

        def resolve_manual_group(key):
            group = str(params.get(key, "G2") or "G2")
            if "DYNAMIC" in group:
                market_mode = (context or {}).get("market_mode", "ANY")
                return "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"
            return group

        # --- TÍNH TOÁN SL CHÍNH XÁC ---
        if manual_sl > 0:
            sl_price = manual_sl
            sl_distance = abs(price - manual_sl)
        elif sl_mode == "SANDBOX" and context:
            brain = self._get_brain_settings(symbol)
            risk_tsl = brain.get("risk_tsl", {}) or {}
            sl_group = resolve_manual_group("MANUAL_SL_GROUP")
            if not sl_group:
                sl_group = str(risk_tsl.get("base_sl", getattr(config, "BOT_BASE_SL", "G2")) or "G2")
            if "DYNAMIC" in sl_group:
                market_mode = (context or {}).get("market_mode", "ANY")
                sl_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"

            sh = context.get(f"swing_high_{sl_group}")
            sl_val = context.get(f"swing_low_{sl_group}")
            atr_val = context.get(f"atr_{sl_group}", context.get("atr_entry"))

            if sh and sl_val and atr_val:
                sl_mult = float(risk_tsl.get("sl_atr_multiplier", getattr(config, "sl_atr_multiplier", 0.2)) or 0.2)
                buffer = float(atr_val) * sl_mult
                sl_price = (float(sl_val) - buffer) if direction == "BUY" else (float(sh) + buffer)
                sl_distance = abs(price - sl_price)
            else:
                sl_distance = price * (params.get("SL_PERCENT", 0.5) / 100.0)
                sl_price = price - sl_distance if direction == "BUY" else price + sl_distance
        elif sl_mode in ("SWING", "SWING_REJECTION", "SWING_RETEST", "SWING_STRUCTURE", "SWING_STRUCT") and context:
            sl_group = resolve_manual_group("MANUAL_SWING_SL_GROUP")

            sh = context.get(f"swing_high_{sl_group}")
            sl_val = context.get(f"swing_low_{sl_group}")
            atr_val = context.get(f"atr_{sl_group}")

            if sh and sl_val and atr_val:
                sl_mult = float(params.get("MANUAL_SWING_SL_ATR_MULT", getattr(config, "sl_atr_multiplier", 0.2)))
                buffer = atr_val * sl_mult
                sl_price = (sl_val - buffer) if direction == "BUY" else (sh + buffer)
                sl_distance = abs(price - sl_price)
            else:
                return "ERR_NO_SWING_DATA"
        else:
            sl_distance = price * (params.get("SL_PERCENT", 0.5) / 100.0)
            sl_price = (
                price - sl_distance if direction == "BUY" else price + sl_distance
            )

        if sl_distance <= 0:
            return "ERR_CALC_SL_ZERO"

        risk_pct = params.get("RISK_PERCENT", 0.3)

        auto_lot = manual_lot <= 0
        if manual_lot > 0:
            lot_size = manual_lot
        else:
            strict_fee_per_lot = 0.0
            if params.get("STRICT_RISK", False):
                acc_type = getattr(config, "DEFAULT_ACCOUNT_TYPE", "STANDARD")
                if acc_type in ["PRO", "STANDARD"]:
                    comm_rate = 0.0
                else:
                    comm_rate = getattr(config, "COMMISSION_RATES", {}).get(
                        symbol,
                        getattr(config, "ACCOUNT_TYPES_CONFIG", {})
                        .get(acc_type, {})
                        .get("COMMISSION_PER_LOT", 7.0),
                    )

                spread_cost = (
                    sym_info.spread * sym_info.point * sym_info.trade_contract_size
                    if sym_info
                    else 0.0
                )
                strict_fee_per_lot = comm_rate + spread_cost

            risk_usd = equity * (risk_pct / 100.0)

            calc_lot, safe_sl = self.connector.calculate_lot_size(
                symbol, risk_usd, sl_price, order_type, strict_fee_per_lot
            )
            if calc_lot is None:
                return "ERR_LOT_CALC_FAILED"
            lot_size = calc_lot
            sl_price = safe_sl

        # [NEW V4.4] Áp dụng Max Lot Cap (Tính cho từng lệnh riêng lẻ)
        brain = self._get_brain_settings(symbol)
        sym_cfgs = brain.get("symbol_configs", {}).get(symbol, {})
        max_lot_cap = float(sym_cfgs.get("max_lot_cap", 0.0))
        if max_lot_cap <= 0:
            max_lot_cap = float(getattr(config, "MAX_LOT_CAP", 0.0) or 0.0)
        if max_lot_cap > 0:
            lot_size = min(lot_size, max_lot_cap)

        use_swing_tp = params.get("USE_SWING_TP", False)

        if manual_tp > 0:
            tp_price = manual_tp
        elif use_swing_tp and context:
            tp_group = resolve_manual_group("MANUAL_SWING_TP_GROUP")

            sh = context.get(f"swing_high_{tp_group}")
            sl_val = context.get(f"swing_low_{tp_group}")
            atr_val = context.get(f"atr_{tp_group}")

            if sh and sl_val and atr_val:
                tp_mult = float(params.get("MANUAL_SWING_TP_ATR_MULT", params.get("MANUAL_SWING_SL_ATR_MULT", getattr(config, "sl_atr_multiplier", 0.2))))
                buffer = atr_val * tp_mult
                tp_price = (sh - buffer) if direction == "BUY" else (sl_val + buffer)
            else:
                tp_price = (
                    price + (abs(price - sl_price) * params.get("TP_RR_RATIO", 1.5))
                    if direction == "BUY"
                    else price
                    - (abs(price - sl_price) * params.get("TP_RR_RATIO", 1.5))
                )
        else:
            tp_price = (
                price + (abs(price - sl_price) * params.get("TP_RR_RATIO", 1.5))
                if direction == "BUY"
                else price - (abs(price - sl_price) * params.get("TP_RR_RATIO", 1.5))
            )

        import core.storage_manager as storage_manager

        magics = storage_manager.get_magic_numbers()
        manual_magic = magics.get("manual_magic", 8888)

        result = self.connector.place_order(
            symbol,
            order_type,
            lot_size,
            sl_price,
            tp_price,
            manual_magic,
            f"[USER]_{preset_name}",
            order_kind=order_kind,
        )

        if self._order_ok(result):
            ticket_id = self._order_ticket(result)
            self._record_open_trade(ticket_id, symbol, direction, lot_size, price, sl_price, tp_price, result)
            self.update_trade_tactic(ticket_id, tactic_str)
            self.state["initial_r_dist"][str(ticket_id)] = abs(price - sl_price)
            self.state.setdefault("initial_r_usd", {})[str(ticket_id)] = self._calc_risk_usd(
                symbol, order_type, lot_size, price, sl_price
            )

            self.state["manual_trades_today"] = (
                self.state.get("manual_trades_today", 0) + 1
            )
            self.state["trades_today_count"] = (
                self.state.get("trades_today_count", 0) + 1
            )

            save_state(self.state)
            try:
                from ai_advisor.history import record_trade_opened_data

                record_trade_opened_data(
                    ticket_id,
                    symbol=symbol,
                    open_time=time.time(),
                    source="manual_order_success",
                    payload={
                        "direction": direction,
                        "volume": lot_size,
                        "entry_price": price,
                        "sl": sl_price,
                        "tp": tp_price,
                        "tactic": tactic_str,
                        "preset": preset_name,
                        "market_context": context or {},
                    },
                )
            except Exception:
                pass
            self.log(
                f"🚀 [USER EXEC] {direction} {symbol} #{ticket_id} | Vol: {lot_size:.2f} | Entry: {price:.5f} | SL: {sl_price:.5f} | TP: {tp_price:.5f} | TSL: {tactic_str}"
            )
            return f"SUCCESS|{ticket_id}"

        err = getattr(result, "error", "") or "API_ERROR"
        msg = getattr(result, "message", "") or ""
        return f"API_ERROR|{err}|{msg}".rstrip("|")

    def execute_telegram_sandbox_order(self, symbol, side, lot, sl, tp, bypass_checklist=False):
        symbol = str(symbol or "").strip().upper()
        side = str(side or "").strip().upper()
        try:
            lot = float(lot)
            sl = float(sl)
            tp = float(tp)
        except Exception:
            return "TELEGRAM_FAIL|BAD_NUMERIC|lot/sl/tp không hợp lệ"

        if side not in ("BUY", "SELL"):
            return "TELEGRAM_FAIL|BAD_SIDE|side phải là BUY hoặc SELL"
        if lot <= 0 or sl <= 0 or tp < 0:
            return "TELEGRAM_FAIL|BAD_PRICE|lot/sl/tp không hợp lệ"

        config.SYMBOL = symbol
        self._sync_state_lifecycle()
        acc_info = self.connector.get_account_info()
        if not acc_info:
            return "TELEGRAM_FAIL|NO_ACCOUNT|Không lấy được tài khoản DNSE"

        is_open, closed_reason = is_symbol_trade_window_open(symbol)
        if not is_open:
            return f"TELEGRAM_FAIL|Market Hours|{closed_reason}"

        tick = self._get_tick(symbol)
        sym_info = self._get_symbol_info(symbol)
        if not tick or not sym_info:
            return "TELEGRAM_FAIL|NO_TICK|Không lấy được tick/symbol info"

        order_type = 0 if side == "BUY" else 1
        price = tick.ask if side == "BUY" else tick.bid
        if side == "BUY":
            if sl >= price:
                return "TELEGRAM_FAIL|BAD_SL|BUY cần SL thấp hơn giá hiện tại"
            if tp and tp <= price:
                return "TELEGRAM_FAIL|BAD_TP|BUY cần TP cao hơn giá hiện tại"
        else:
            if sl <= price:
                return "TELEGRAM_FAIL|BAD_SL|SELL cần SL cao hơn giá hiện tại"
            if tp and tp >= price:
                return "TELEGRAM_FAIL|BAD_TP|SELL cần TP thấp hơn giá hiện tại"

        vol_min = float(getattr(sym_info, "volume_min", getattr(config, "MIN_LOT_SIZE", 0.01)) or 0.01)
        vol_max = float(getattr(sym_info, "volume_max", getattr(config, "MAX_LOT_SIZE", 200.0)) or 200.0)
        vol_step = float(getattr(sym_info, "volume_step", getattr(config, "LOT_STEP", 0.01)) or 0.01)
        if lot < vol_min or lot > vol_max:
            return f"TELEGRAM_FAIL|BAD_LOT|Lot ngoài biên {vol_min}-{vol_max}"
        step_units = round((lot - vol_min) / vol_step) if vol_step > 0 else 0
        normalized = vol_min + (step_units * vol_step)
        if vol_step > 0 and abs(normalized - lot) > max(1e-8, vol_step / 1000.0):
            return f"TELEGRAM_FAIL|BAD_LOT_STEP|Lot phải theo step {vol_step}"

        res = self.checklist.run_pre_trade_checks(acc_info, self.state, symbol, strict_mode=True)
        if not res.get("passed"):
            fail_reasons = [c.get("msg", "") for c in res.get("checks", []) if c.get("status") == "FAIL"]
            if not bypass_checklist:
                return f"TELEGRAM_FAIL|CHECKLIST|{' | '.join(fail_reasons) or 'Checklist fail'}"

        import core.storage_manager as storage_manager

        magics = storage_manager.get_magic_numbers()
        manual_magic = magics.get("manual_magic", 8888)
        result = self.connector.place_order(
            symbol,
            order_type,
            lot,
            sl,
            tp,
            manual_magic,
            "[USER]_TELEGRAM",
        )
        if not self._order_ok(result):
            return "TELEGRAM_FAIL|API_ERROR|Đặt lệnh thất bại"

        ticket_id = self._order_ticket(result)
        self._record_open_trade(ticket_id, symbol, side, lot, price, sl, tp, result)
        brain = self._get_brain_settings(symbol)
        risk_tsl = brain.get("risk_tsl", {}) or {}
        safeguard_cfg = brain.get("bot_safeguard", {}) or {}
        tactic = risk_tsl.get("bot_tsl", getattr(config, "BOT_DEFAULT_TSL", "BE+STEP_R+SWING"))
        dca_cfg = brain.get("dca_config", getattr(config, "DCA_CONFIG", {}))
        pca_cfg = brain.get("pca_config", getattr(config, "PCA_CONFIG", {}))
        if dca_cfg.get("ENABLED", False) and "AUTO_DCA" not in tactic:
            tactic += "+AUTO_DCA"
        if pca_cfg.get("ENABLED", False) and "AUTO_PCA" not in tactic:
            tactic += "+AUTO_PCA"
        if safeguard_cfg.get("CLOSE_ON_REVERSE", False) and "REV_C" not in tactic:
            tactic += "+REV_C"

        self.update_trade_tactic(ticket_id, tactic)
        entry_exit_cfg = brain.get("entry_exit", {}) or {}
        if entry_exit_cfg.get("enabled"):
            active = entry_exit_cfg.get("active_tactics") or entry_exit_cfg.get("entry_tactics") or []
            if isinstance(active, str):
                active = [active]
            ee_label = "+".join(str(x) for x in active if x) or "SANDBOX"
            exit_label = entry_exit_cfg.get("exit_tactic")
            if exit_label:
                ee_label = f"{ee_label}->{exit_label}"
            self.update_trade_entry_exit_tactic(ticket_id, ee_label)

        self.state["initial_r_dist"][str(ticket_id)] = abs(price - sl)
        self.state.setdefault("initial_r_usd", {})[str(ticket_id)] = self._calc_risk_usd(
            symbol, order_type, lot, price, sl
        )
        self.state["manual_trades_today"] = self.state.get("manual_trades_today", 0) + 1
        self.state["trades_today_count"] = self.state.get("trades_today_count", 0) + 1
        save_state(self.state)
        try:
            from ai_advisor.history import record_trade_opened_data

            record_trade_opened_data(
                ticket_id,
                symbol=symbol,
                open_time=time.time(),
                source="telegram_order_success",
                payload={
                    "direction": side,
                    "volume": lot,
                    "entry_price": price,
                    "sl": sl,
                    "tp": tp,
                    "tactic": tactic,
                    "entry_exit_tactic": self.get_trade_entry_exit_tactic(ticket_id),
                },
            )
        except Exception:
            pass
        self.log(
            f"🚀 [TELEGRAM EXEC] {side} {symbol} #{ticket_id} | Lot: {lot:.2f} | Entry: {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | TSL: {tactic}",
            target="bot",
        )
        return f"SUCCESS|{ticket_id}"

    def build_telegram_signal_order(self, symbol, side, context=None, market_mode="ANY"):
        symbol = str(symbol or "").strip().upper()
        side = str(side or "").strip().upper()
        context = context or {}
        if side not in ("BUY", "SELL"):
            return {"ok": False, "error": "BAD_SIDE"}

        config.SYMBOL = symbol
        self._sync_state_lifecycle()
        acc_info = self.connector.get_account_info()
        if not acc_info:
            return {"ok": False, "error": "NO_ACCOUNT"}

        is_open, closed_reason = is_symbol_trade_window_open(symbol)
        if not is_open:
            return {"ok": False, "error": f"MARKET_CLOSED|{closed_reason}"}

        tick = self._get_tick(symbol)
        sym_info = self._get_symbol_info(symbol)
        if not tick or not sym_info:
            return {"ok": False, "error": "NO_TICK"}

        brain = self._get_brain_settings(symbol)
        risk_tsl = brain.get("risk_tsl", {}) or {}
        safeguard_cfg = brain.get("bot_safeguard", {}) or {}
        entry_exit_cfg = brain.get("entry_exit", {}) or {}
        price = tick.ask if side == "BUY" else tick.bid
        order_type = 0 if side == "BUY" else 1

        ee_sl_override = None
        ee_tp_override = None
        ee_decision = None
        try:
            pending_key = f"{symbol}|{side}"
            pending = (self.state.get("pending_entry_exit", {}) or {}).get(pending_key)
            ee_decision = evaluate_entry_exit(
                symbol,
                side,
                price,
                context,
                entry_exit_cfg,
                pending=pending,
            )
            if (
                entry_exit_cfg.get("enabled")
                and not entry_exit_cfg.get("preview_only", True)
                and ee_decision.get("status") == "READY"
            ):
                ee_sl_override = ee_decision.get("sl")
                ee_tp_override = ee_decision.get("tp")
        except Exception:
            ee_decision = None

        sl_group = risk_tsl.get("base_sl", "G2")
        if "DYNAMIC" in str(sl_group).upper():
            sl_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"
        atr_key = f"atr_{sl_group}"
        swing_l_key = f"swing_low_{sl_group}"
        swing_h_key = f"swing_high_{sl_group}"
        atr_val = context.get(atr_key) or context.get("atr_entry") or 0.0
        swing_l = context.get(swing_l_key)
        swing_h = context.get(swing_h_key)
        sl_mult = float(risk_tsl.get("sl_atr_multiplier", getattr(config, "sl_atr_multiplier", 0.2)))
        buffer_atr = float(atr_val or 0.0) * sl_mult

        if ee_sl_override:
            sl_price = float(ee_sl_override)
        else:
            if atr_key not in context or swing_l_key not in context or swing_h_key not in context:
                return {"ok": False, "error": f"NO_DATA|{sl_group}"}
            sl_price = float(swing_l) - buffer_atr if side == "BUY" else float(swing_h) + buffer_atr
        sl_distance = abs(price - sl_price)
        if sl_distance < price * 0.0005:
            return {"ok": False, "error": "SL_TOO_TIGHT"}

        strict_fee_per_lot = 0.0
        if risk_tsl.get("strict_risk", False):
            acc_type = getattr(config, "DEFAULT_ACCOUNT_TYPE", "STANDARD")
            comm_rate = 0.0 if acc_type in ["PRO", "STANDARD"] else getattr(
                config,
                "COMMISSION_RATES",
                {},
            ).get(
                symbol,
                getattr(config, "ACCOUNT_TYPES_CONFIG", {}).get(acc_type, {}).get("COMMISSION_PER_LOT", 7.0),
            )
            strict_fee_per_lot = comm_rate + (
                sym_info.spread * sym_info.point * sym_info.trade_contract_size if sym_info else 0.0
            )

        sym_cfgs = brain.get("symbol_configs", {}).get(symbol, {}) or {}
        fixed_lot = float(sym_cfgs.get("fixed_lot", 0.0) or 0.0)
        if fixed_lot > 0:
            lot = fixed_lot
            _, safe_sl = self.connector.calculate_lot_size(symbol, 10.0, sl_price, order_type, 0)
            sl_price = safe_sl if safe_sl else sl_price
        else:
            base_risk = float(risk_tsl.get("base_risk", getattr(config, "BOT_RISK_PERCENT", 0.3)) or 0.3)
            mode_multiplier = float((risk_tsl.get("mode_multipliers", {}) or {}).get(market_mode, 1.0) or 1.0)
            risk_usd = float(acc_info.get("equity", 0.0) or 0.0) * ((base_risk * mode_multiplier) / 100.0)
            lot, safe_sl = self.connector.calculate_lot_size(symbol, risk_usd, sl_price, order_type, strict_fee_per_lot)
            if not lot:
                return {"ok": False, "error": "LOT_CALC_FAILED"}
            sl_price = safe_sl if safe_sl else sl_price

        max_lot_cap = float(sym_cfgs.get("max_lot_cap", 0.0) or 0.0)
        if max_lot_cap > 0:
            lot = min(float(lot), max_lot_cap)

        use_swing_tp = safeguard_cfg.get("BOT_USE_SWING_TP", False)
        use_rr_tp = safeguard_cfg.get("BOT_USE_RR_TP", True)
        ee_exit_tactic = str(entry_exit_cfg.get("exit_tactic", "")).upper()
        ee_tp_disabled = ee_exit_tactic in ("NO_TP", "OFF") or (
            ee_decision and ee_decision.get("tp_disabled")
        )
        if ee_tp_disabled:
            tp_price = 0.0
        elif ee_tp_override is not None:
            tp_price = float(ee_tp_override)
        elif use_swing_tp and swing_h and swing_l and atr_val:
            tp_price = (float(swing_h) - buffer_atr) if side == "BUY" else (float(swing_l) + buffer_atr)
        elif use_rr_tp:
            reward_ratio = float(safeguard_cfg.get("BOT_TP_RR_RATIO", getattr(config, "BOT_TP_RR_RATIO", 1.5)) or 1.5)
            tp_price = price + (abs(price - sl_price) * reward_ratio) if side == "BUY" else price - (abs(price - sl_price) * reward_ratio)
        else:
            tp_price = 0.0

        digits = int(getattr(sym_info, "digits", 2) or 2)
        return {
            "ok": True,
            "symbol": symbol,
            "side": side,
            "lot": round(float(lot), 4),
            "sl": round(float(sl_price), digits),
            "tp": round(float(tp_price), digits) if tp_price else 0.0,
            "price": float(price),
            "market_mode": market_mode,
        }

    def update_trade_tactic(self, ticket, tactic_str):
        self.state["trade_tactics"][str(ticket)] = tactic_str
        save_state(self.state)

    def get_trade_tactic(self, ticket):
        return self.state.get("trade_tactics", {}).get(str(ticket), "OFF")

    def update_trade_entry_exit_tactic(self, ticket, tactic_str):
        self.state.setdefault("entry_exit_tactics", {})[str(ticket)] = tactic_str
        save_state(self.state)

    def get_trade_entry_exit_tactic(self, ticket):
        return self.state.get("entry_exit_tactics", {}).get(str(ticket), "OFF")

    # ====================================================================================
    # 3. QUẢN LÝ LỆNH CHẠY (TSL ĐỘC LẬP & DỌN RÁC RỔ LỆNH)
    # ====================================================================================
    def update_running_trades(self, account_type="STANDARD", all_market_contexts=None):
        tsl_status_map = {}
        try:
            self._sync_state_lifecycle()
            current_positions = self.connector.get_all_open_positions()
            current_tickets = [str(p.ticket) for p in current_positions]
            tracked_tickets = list(self.state.get("active_trades", []))

            # XỬ LÝ ĐÓNG LỆNH & CHỐT RỔ BẢO VỆ MẸ-CON
            closed_tickets = [t for t in tracked_tickets if str(t) not in current_tickets]
            if closed_tickets:
                for ticket in closed_tickets:
                    s_ticket = str(ticket)

                    sym = self.state.get("trade_symbols", {}).get(s_ticket, "VN30F1M")
                    dir_str = self.state.get("trade_directions", {}).get(s_ticket, "BUY")
                    vol = float(self.state.get("trade_volumes", {}).get(s_ticket, 1.0))
                    open_p = float(self.state.get("trade_prices", {}).get(s_ticket, 0.0))
                    
                    close_p = open_p
                    if isinstance(all_market_contexts, dict) and sym in all_market_contexts:
                        close_p = float(all_market_contexts[sym].get("current_price", open_p))
                    
                    # Mô phỏng tính PnL cho VN30 (1 giá = 100,000 VND)
                    diff = (close_p - open_p) if dir_str == "BUY" else (open_p - close_p)
                    real_pnl = diff * getattr(config, "DNSE_POINT_VALUE", 100000.0) * vol
                    
                    # [FIX] Phân loại lệnh dựa trên magic number thay vì gán cứng
                    _magic = int(self.state.get("trade_magics", {}).get(s_ticket, 0))
                    is_bot = is_bot_position(type("P", (), {"magic": _magic, "comment": "", "ticket": ticket})())
                    
                    self.state["pnl_today"] += real_pnl
                    
                    if real_pnl < 0:
                        self.state["daily_loss_count"] += 1

                    if is_bot:
                        self.state["bot_pnl_today"] = self.state.get("bot_pnl_today", 0) + real_pnl
                        symbol_streaks = self.state.setdefault("bot_symbol_losing_streak", {})
                        if real_pnl < 0:
                            self.state["bot_daily_loss_count"] = self.state.get("bot_daily_loss_count", 0) + 1
                            self.state["bot_losing_streak"] = self.state.get("bot_losing_streak", 0) + 1
                            symbol_streaks[sym] = symbol_streaks.get(sym, 0) + 1
                        else:
                            self.state["bot_losing_streak"] = 0
                            symbol_streaks[sym] = 0
                            
                    exit_reason = self.state.get("exit_reasons", {}).get(s_ticket, "Closed")
                    self.state.setdefault("last_close_times", {})[sym] = time.time()
                    
                    pnl_sign = "+" if real_pnl >= 0 else ""
                    self.log(
                        f"[DNSE] Đóng lệnh {dir_str} {sym} #{ticket} ({exit_reason}) | PnL tạm tính: {pnl_sign}{real_pnl:,.0f} VND",
                        target="bot",
                    )

                    # Cập nhật last_dca_pca_close_time nếu lệnh này là con (DCA/PCA)
                    from core.storage_manager import update_last_dca_pca_close_time

                    bot_tactic = self.get_trade_tactic(ticket)
                    if "AUTO_DCA" in bot_tactic or "AUTO_PCA" in bot_tactic:
                        update_last_dca_pca_close_time(
                            sym, time.time()
                        )

                    if is_bot:
                        self.check_and_trigger_cooldown(sym)

                    self.state["active_trades"] = [
                        t for t in self.state.get("active_trades", []) if str(t) != s_ticket
                    ]
                    for key in [
                        "trade_tactics",
                        "initial_r_dist",
                        "initial_r_usd",
                        "exit_reasons",
                        "initial_costs",
                        "last_tsl_rules",
                        "trade_excursions",
                        "be_sl_arms",
                        "rev_confirmations",
                    ]:
                        if s_ticket in self.state.get(key, {}):
                            del self.state[key][s_ticket]

                    # Basket Logic
                    if s_ticket in self.state.get("parent_baskets", {}):
                        child_tickets = self.state["parent_baskets"][s_ticket]
                        for child_t in child_tickets:
                            child_pos = next(
                                (
                                    p
                                    for p in current_positions
                                    if str(p.ticket) == str(child_t)
                                ),
                                None,
                            )
                            if child_pos:
                                self.log(
                                    f"⚠️ [BASKET CLOSE] Đóng lệnh Con #{child_t} do Mẹ #{ticket} đã chốt!",
                                    target="bot",
                                )
                                self.state["exit_reasons"][str(child_t)] = (
                                    "Parent_Closed"
                                )
                                threading.Thread(
                                    target=self._close_with_t2_log,
                                    args=(child_pos,),
                                    daemon=True,
                                ).start()
                        del self.state["parent_baskets"][s_ticket]

                    if s_ticket in self.state.get("child_to_parent", {}):
                        parent_t = self.state["child_to_parent"][s_ticket]
                        if (
                            parent_t in self.state.get("parent_baskets", {})
                            and s_ticket in self.state["parent_baskets"][parent_t]
                        ):
                            self.state["parent_baskets"][parent_t].remove(s_ticket)
                        del self.state["child_to_parent"][s_ticket]

                save_state(self.state)

            import core.storage_manager as storage_manager

            magics = storage_manager.get_magic_numbers()
            bot_magic = magics.get("bot_magic", 9999)
            tracked_positions = [
                p
                for p in current_positions
                if is_bot_position(p, magics) or is_manual_position(p, magics)
            ]

            needs_save = False

            # ATC-exit: đóng vị thế BOT ở phiên ATC cuối ngày (nếu bật BOT_ATC_EXIT). 1 lần/ngày/ticket.
            try:
                from core.market_hours import market_session_phase
                from datetime import datetime as _dt
                _today = _dt.now().strftime("%Y-%m-%d")
                atc_done = self.state.setdefault("atc_exit_done", {})
                for pos in tracked_positions:
                    if not is_bot_position(pos, magics):
                        continue
                    sg = self._get_brain_settings(pos.symbol).get("bot_safeguard", {})
                    if not sg.get("BOT_ATC_EXIT"):
                        continue
                    if market_session_phase(pos.symbol)[0] != "ATC":
                        continue
                    done_key = f"{pos.ticket}|{_today}"
                    if atc_done.get(done_key):
                        continue
                    res = self._close_with_t2_log(pos, "ATC_Exit")
                    if res and getattr(res, "error", "") != "STOCK_NOT_SETTLED_T2":
                        atc_done[done_key] = True
                        needs_save = True
            except Exception:
                pass

            for pos in tracked_positions:
                s_ticket = str(pos.ticket)
                is_newly_tracked = s_ticket not in [str(t) for t in self.state.get("active_trades", [])]
                if is_newly_tracked:
                    self.state["active_trades"].append(s_ticket)
                    direction = "BUY" if getattr(pos, "type", 0) == 0 else "SELL"
                    self._record_open_trade(
                        s_ticket,
                        pos.symbol,
                        direction,
                        pos.volume,
                        pos.price_open,
                        getattr(pos, "sl", 0.0),
                        getattr(pos, "tp", 0.0),
                    )
                    needs_save = True

                if pos.magic == bot_magic and self.get_trade_tactic(pos.ticket) == "OFF":
                    brain = self._get_brain_settings(pos.symbol)
                    risk_tsl = brain.get("risk_tsl", {})
                    restored_tactic = risk_tsl.get(
                        "bot_tsl", getattr(config, "BOT_DEFAULT_TSL", "BE+STEP_R+SWING")
                    )
                    if restored_tactic and restored_tactic != "OFF":
                        self.state.setdefault("trade_tactics", {})[str(pos.ticket)] = restored_tactic
                        needs_save = True
                        self.log(
                            f"♻️ [TSL] Khôi phục tactic cho lệnh bot #{pos.ticket}: {restored_tactic}",
                            target="bot",
                        )

                before_excursion = self.state.get("trade_excursions", {}).get(
                    str(pos.ticket), {}
                ).copy()
                excursion = self._update_trade_excursion(pos)
                if excursion != before_excursion:
                    needs_save = True

                sym_ctx = (
                    all_market_contexts.get(pos.symbol, {})
                    if all_market_contexts
                    else {}
                )
                if is_newly_tracked:
                    try:
                        from ai_advisor.history import record_trade_opened

                        record_trade_opened(
                            pos,
                            state=self.state,
                            market_context=sym_ctx,
                            source="running_trade_discovery",
                        )
                    except Exception:
                        pass
                tsl_status_map[pos.ticket] = self._apply_independent_tsl(pos, sym_ctx)

                if "ANTI_CASH" in self.get_trade_tactic(pos.ticket):
                    self._check_anti_cash(pos)

                if "REV_C" in self.get_trade_tactic(pos.ticket):
                    self._check_recovery(pos, sym_ctx)

            # --- [NEW V5] WATERMARK DYNAMIC PNL ---
            if tracked_positions:
                symbol_pnl = {}
                symbol_tickets = {}
                for p in tracked_positions:
                    profit = p.profit + p.swap + getattr(p, "commission", 0.0)
                    symbol_pnl[p.symbol] = symbol_pnl.get(p.symbol, 0.0) + profit
                    symbol_tickets.setdefault(p.symbol, []).append(str(p.ticket))

                self.state.setdefault("highest_pnl_recorded", {})
                self.state.setdefault("highest_pnl_tickets", {})
                active_symbols = set(symbol_pnl)
                for stale_sym in list(self.state["highest_pnl_recorded"].keys()):
                    if stale_sym not in active_symbols:
                        self.state["highest_pnl_recorded"].pop(stale_sym, None)
                        self.state["highest_pnl_tickets"].pop(stale_sym, None)
                        needs_save = True

                for sym, current_pnl in symbol_pnl.items():
                    brain = self._get_brain_settings(sym)
                    sym_cfg = brain.get("symbol_configs", {}).get(sym, {})
                    sg_cfg = brain.get("bot_safeguard", getattr(config, "BOT_SAFEGUARD", {}))
                    
                    acc = self.connector.get_account_info()
                    equity = acc.get("equity", 0.0) if acc else 0.0
                    wm_trigger = self._resolve_money_value(
                        sym_cfg.get("watermark_trigger", 0.0),
                        sym_cfg.get("watermark_trigger_unit", sg_cfg.get("WATERMARK_TRIGGER_UNIT", "USD")),
                        equity=equity,
                    )
                    if wm_trigger <= 0:
                        wm_trigger = self._resolve_money_value(
                            sg_cfg.get("WATERMARK_TRIGGER", 0.0),
                            sg_cfg.get("WATERMARK_TRIGGER_UNIT", "USD"),
                            equity=equity,
                        )
                        
                    wm_dd = self._resolve_money_value(
                        sym_cfg.get("watermark_drawdown", 0.0),
                        sym_cfg.get("watermark_drawdown_unit", sg_cfg.get("WATERMARK_DRAWDOWN_UNIT", "USD")),
                        equity=equity,
                    )
                    if wm_dd <= 0:
                        wm_dd = self._resolve_money_value(
                            sg_cfg.get("WATERMARK_DRAWDOWN", 0.0),
                            sg_cfg.get("WATERMARK_DRAWDOWN_UNIT", "USD"),
                            equity=equity,
                        )

                    if wm_trigger > 0 and wm_dd > 0:
                        ticket_key = "|".join(sorted(symbol_tickets.get(sym, [])))
                        prev_ticket_key = self.state["highest_pnl_tickets"].get(sym)

                        if prev_ticket_key != ticket_key:
                            self.state["highest_pnl_tickets"][sym] = ticket_key
                            self.state["highest_pnl_recorded"][sym] = max(current_pnl, 0.0)
                            highest = self.state["highest_pnl_recorded"][sym]
                            needs_save = True
                        else:
                            highest = self.state["highest_pnl_recorded"].get(sym, 0.0)
                        
                        if current_pnl > highest:
                            self.state["highest_pnl_recorded"][sym] = current_pnl
                            highest = current_pnl
                            needs_save = True
                            
                        # Kích hoạt Watermark
                        if highest >= wm_trigger and current_pnl > 0 and current_pnl <= (highest - wm_dd):
                            self.log(f"💧 [WATERMARK] {sym} Sụt giảm từ đỉnh (+${highest:.2f}) xuống (+${current_pnl:.2f})! Đạt giới hạn Drawdown (${wm_dd:.2f}). KÍCH HOẠT ĐÓNG TOÀN BỘ!", target="bot")
                            
                            def _close_watermark_seq(positions, symbol):
                                for p in positions:
                                    if p.symbol == symbol:
                                        self.state["exit_reasons"][str(p.ticket)] = "Watermark_Hit"
                                        self._close_with_t2_log(p, "Watermark")
                                        time.sleep(0.2)
                                        
                            threading.Thread(target=_close_watermark_seq, args=(tracked_positions, sym), daemon=True).start()
                            
                            # [V5.2] Kích hoạt Phanh theo Mode (Watermark)
                            if sg_cfg.get("APPLY_GLOBAL_COOLDOWN_ON_SAFEGUARD", False):
                                brake_mode = sg_cfg.get("GLOBAL_BRAKE_MODE", "Mode 1: Total Freeze")
                                hours = float(sg_cfg.get("GLOBAL_COOLDOWN_HOURS", 4.0))
                                cooldown_time = time.time() + (hours * 3600)
                                if not get_active_safeguard_brake(self.state, "GLOBAL"):
                                    if "Mode 2" in str(brake_mode):
                                        if not get_active_safeguard_brake(self.state, "SYMBOL", symbol=sym):
                                            item, created = mark_safeguard_brake(
                                                self.state,
                                                "SYMBOL",
                                                f"Watermark {sym}",
                                                cooldown_time,
                                                symbol=sym,
                                                trigger={"source": "WATERMARK", "symbol": sym, "pnl": current_pnl},
                                            )
                                            self.state.setdefault("bot_last_fail_times", {})[sym] = float(item.get("until", cooldown_time))
                                            if created:
                                                self.log(f"🛑 [SYMBOL BRAKE] Cách ly {sym} trong {hours} giờ do dính Watermark!", target="bot")
                                    else:
                                        item, created = mark_safeguard_brake(
                                            self.state,
                                            "GLOBAL",
                                            f"Watermark {sym}",
                                            cooldown_time,
                                            trigger={"source": "WATERMARK", "symbol": sym, "pnl": current_pnl},
                                        )
                                        self.state["cooldown_until"] = float(item.get("until", cooldown_time))
                                        if created:
                                            self.log(f"🛑 [GLOBAL BRAKE] Phanh Toàn Hệ Thống trong {hours} giờ do dính Watermark {sym}!", target="bot")

                            # Xóa mốc để chu kỳ mới làm lại
                            self.state["highest_pnl_recorded"][sym] = 0.0
                            self.state["highest_pnl_tickets"].pop(sym, None)
                            needs_save = True
            elif self.state.get("highest_pnl_recorded") or self.state.get("highest_pnl_tickets"):
                self.state["highest_pnl_recorded"] = {}
                self.state["highest_pnl_tickets"] = {}
                needs_save = True
            # ---------------------------------------

            # --- [NEW V5.1] MAX BASKET DRAWDOWN (PHANH KHẨN CẤP RỔ LỆNH) ---
            if tracked_positions and self.state.get("parent_baskets"):
                # Dùng list() để tránh lỗi RuntimeError: dictionary changed size during iteration
                for parent_str, children_list in list(self.state["parent_baskets"].items()):
                    basket_tickets = [int(parent_str)] + [int(t) for t in children_list]
                    basket_pos = [p for p in tracked_positions if p.ticket in basket_tickets]
                    
                    if not basket_pos:
                        continue
                        
                    # Lấy cấu hình Drawdown (Ưu tiên Symbol Config -> Fallback Global)
                    sym = basket_pos[0].symbol
                    brain = self._get_brain_settings(sym)
                    sym_cfg = brain.get("symbol_configs", {}).get(sym, {})
                    sg_cfg = brain.get("bot_safeguard", getattr(config, "BOT_SAFEGUARD", {}))
                    
                    acc = self.connector.get_account_info()
                    equity = acc.get("equity", 0.0) if acc else 0.0
                    max_basket_loss = self._resolve_money_value(
                        sym_cfg.get("max_basket_drawdown", 0.0),
                        sym_cfg.get("max_basket_drawdown_unit", sg_cfg.get("MAX_BASKET_DRAWDOWN_UNIT", "USD")),
                        equity=equity,
                    )
                    if max_basket_loss <= 0:
                        max_basket_loss = self._resolve_money_value(
                            sg_cfg.get("MAX_BASKET_DRAWDOWN_USD", 0.0),
                            sg_cfg.get("MAX_BASKET_DRAWDOWN_UNIT", "USD"),
                            equity=equity,
                        )
                        
                    if max_basket_loss > 0:
                        total_basket_pnl = sum((p.profit + p.swap + getattr(p, "commission", 0.0)) for p in basket_pos)
                        
                        if total_basket_pnl <= -max_basket_loss:
                            self.log(f"🔥 [BASKET DRAWDOWN] Rổ {sym} (Mẹ #{parent_str}) âm vượt ngưỡng (-${max_basket_loss:.2f})! PnL hiện tại: ${total_basket_pnl:.2f}. CẮT SẠCH CẢ RỔ!", target="bot")
                            
                            def _close_basket_seq(b_pos):
                                for p in b_pos:
                                    self.state["exit_reasons"][str(p.ticket)] = "Basket_Drawdown_Hit"
                                    self._close_with_t2_log(p, "Basket_Drawdown")
                                    time.sleep(0.2)
                                    
                            threading.Thread(target=_close_basket_seq, args=(basket_pos,), daemon=True).start()
                            
                            # [V5.2] Kích hoạt Phanh theo Mode (Basket)
                            if sg_cfg.get("APPLY_GLOBAL_COOLDOWN_ON_SAFEGUARD", False):
                                brake_mode = sg_cfg.get("GLOBAL_BRAKE_MODE", "Mode 1: Total Freeze")
                                hours = float(sg_cfg.get("GLOBAL_COOLDOWN_HOURS", 4.0))
                                cooldown_time = time.time() + (hours * 3600)
                                if not get_active_safeguard_brake(self.state, "GLOBAL"):
                                    if "Mode 2" in str(brake_mode):
                                        if not get_active_safeguard_brake(self.state, "SYMBOL", symbol=sym):
                                            item, created = mark_safeguard_brake(
                                                self.state,
                                                "SYMBOL",
                                                f"Basket Loss {sym}",
                                                cooldown_time,
                                                symbol=sym,
                                                trigger={"source": "BASKET_LOSS", "symbol": sym, "pnl": total_basket_pnl},
                                            )
                                            self.state.setdefault("bot_last_fail_times", {})[sym] = float(item.get("until", cooldown_time))
                                            if created:
                                                self.log(f"🛑 [SYMBOL BRAKE] Cách ly {sym} trong {hours} giờ do dính Basket Loss!", target="bot")
                                    else:
                                        item, created = mark_safeguard_brake(
                                            self.state,
                                            "GLOBAL",
                                            f"Basket Loss {sym}",
                                            cooldown_time,
                                            trigger={"source": "BASKET_LOSS", "symbol": sym, "pnl": total_basket_pnl},
                                        )
                                        self.state["cooldown_until"] = float(item.get("until", cooldown_time))
                                        if created:
                                            self.log(f"🛑 [GLOBAL BRAKE] Phanh Toàn Hệ Thống trong {hours} giờ do dính Basket Loss {sym}!", target="bot")

                            needs_save = True
            # ---------------------------------------------------------------
            
            if needs_save:
                save_state(self.state)

        except Exception as e:
            self.log(f"❌ Lỗi update loop: {e}", error=True)
        return tsl_status_map

    def _check_anti_cash_legacy(self, pos):
        tsl_cfg = self._get_brain_settings(pos.symbol).get(
            "TSL_CONFIG", getattr(config, "TSL_CONFIG", {})
        )
        hard_stop_usd = float(tsl_cfg.get("ANTI_CASH_USD", 10.0))
        time_cut_s = int(tsl_cfg.get("ANTI_CASH_TIME", 60))

        profit_usd = pos.profit + pos.swap + getattr(pos, "commission", 0.0)

        # [NEW V4.4] Tự động cộng phí sàn ban đầu vào ngưỡng cắt lỗ
        s_ticket = str(pos.ticket)
        if "initial_costs" not in self.state:
            self.state["initial_costs"] = {}
        if s_ticket not in self.state["initial_costs"]:
            # Phí ban đầu = |Profit âm lúc mới mở + Commission + Swap|
            init_cost = abs(
                min(0, pos.profit) + pos.swap + getattr(pos, "commission", 0.0)
            )
            self.state["initial_costs"][s_ticket] = init_cost
            save_state(self.state)

        initial_cost = self.state["initial_costs"].get(s_ticket, 0.0)
        dynamic_threshold = hard_stop_usd + initial_cost

        # Option 1: Hard Cash Stop (Dynamic Threshold)
        if profit_usd <= -dynamic_threshold:
            self.log(
                f"🔥 [ANTI CASH] Đạt ngưỡng Hard Stop (-${hard_stop_usd} + Phí ${initial_cost:.2f})! Cắt lỗ lệnh #{pos.ticket}",
                target="bot",
            )
            self.state["exit_reasons"][str(pos.ticket)] = "Anti_Cash_Hard_Stop"
            threading.Thread(
                target=self._close_with_t2_log, args=(pos, "Anti_Cash_Hard_Stop"), daemon=True
            ).start()
            return

        # Option 2: Time & Drawdown Cut (Chỉ chạy nếu Enable)
        time_enable = tsl_cfg.get("ANTI_CASH_TIME_ENABLE", True)
        if time_enable:
            hold_time = time.time() - pos.time
            if hold_time > time_cut_s and profit_usd < 0:
                self.log(
                    f"  [ANTI CASH] Quá Min Hold Time ({time_cut_s}s) và đang âm! Cắt lệnh #{pos.ticket}",
                    target="bot",
                )
                self.state["exit_reasons"][str(pos.ticket)] = "Anti_Cash_Time_Cut"
                threading.Thread(
                    target=self._close_with_t2_log, args=(pos, "Anti_Cash_Time_Cut"), daemon=True
                ).start()

    def _check_anti_cash(self, pos):
        tsl_cfg = self._get_brain_settings(pos.symbol).get(
            "TSL_CONFIG", getattr(config, "TSL_CONFIG", {})
        )
        hard_stop_usd = float(tsl_cfg.get("ANTI_CASH_USD", 10.0))
        time_cut_s = int(tsl_cfg.get("ANTI_CASH_TIME", 60))
        reentry_lock_s = int(tsl_cfg.get("ANTI_CASH_REENTRY_LOCK_SEC", 0))
        acc_info = self.connector.get_account_info()
        equity = acc_info.get("equity", 0.0) if acc_info else 0.0

        profit_usd = self._position_profit_usd(pos)
        s_ticket = str(pos.ticket)
        current_reason = self.state.get("exit_reasons", {}).get(s_ticket, "")
        if current_reason.startswith("Anti_Cash_"):
            return

        if "initial_costs" not in self.state:
            self.state["initial_costs"] = {}
        if s_ticket not in self.state["initial_costs"]:
            init_cost = abs(
                min(0, pos.profit) + pos.swap + getattr(pos, "commission", 0.0)
            )
            self.state["initial_costs"][s_ticket] = init_cost
            save_state(self.state)

        initial_cost = self.state["initial_costs"].get(s_ticket, 0.0)
        hard_stop_limit = self._resolve_money_value(
            hard_stop_usd,
            tsl_cfg.get("ANTI_CASH_HARD_STOP_UNIT", "USD"),
            pos=pos,
            equity=equity,
        )
        dynamic_threshold = hard_stop_limit + initial_cost
        hold_time = time.time() - pos.time
        excursion = self.state.get("trade_excursions", {}).get(s_ticket)
        if not excursion:
            excursion = self._update_trade_excursion(pos)
        mae_usd = float(excursion.get("mae_usd", profit_usd))
        mfe_usd = float(excursion.get("mfe_usd", profit_usd))

        def close_by_anti_cash(reason, message):
            self.log(message, target="bot")
            self.state["exit_reasons"][s_ticket] = reason
            self._set_anti_cash_lock(pos, reentry_lock_s)
            save_state(self.state)
            threading.Thread(
                target=self._close_with_t2_log, args=(pos, reason), daemon=True
            ).start()

        if profit_usd <= -dynamic_threshold:
            close_by_anti_cash(
                "Anti_Cash_Hard_Stop",
                f"🔥 [ANTI CASH] Hard Stop #{pos.ticket}: PnL ${profit_usd:.2f} <= -${dynamic_threshold:.2f} (-${hard_stop_limit:.2f} + phí ${initial_cost:.2f}).",
            )
            return

        if tsl_cfg.get("ANTI_CASH_MFE_ENABLE", True):
            mfe_trigger = self._resolve_money_value(
                tsl_cfg.get("ANTI_CASH_MFE_TRIGGER_USD", 30.0),
                tsl_cfg.get("ANTI_CASH_MFE_TRIGGER_UNIT", "USD"),
                pos=pos,
                equity=equity,
            )
            mfe_giveback = self._resolve_money_value(
                tsl_cfg.get("ANTI_CASH_MFE_GIVEBACK_USD", 20.0),
                tsl_cfg.get("ANTI_CASH_MFE_GIVEBACK_UNIT", "USD"),
                pos=pos,
                equity=equity,
            )
            mfe_floor = self._resolve_money_value(
                tsl_cfg.get("ANTI_CASH_MFE_FLOOR_USD", 0.0),
                tsl_cfg.get("ANTI_CASH_MFE_FLOOR_UNIT", "USD"),
                pos=pos,
                equity=equity,
            )
            giveback = mfe_usd - profit_usd
            if mfe_trigger > 0 and mfe_usd >= mfe_trigger:
                if mfe_giveback > 0 and giveback >= mfe_giveback:
                    close_by_anti_cash(
                        "Anti_Cash_MFE_Giveback",
                        f"💰 [ANTI CASH] MFE Giveback #{pos.ticket}: MFE ${mfe_usd:.2f}, PnL ${profit_usd:.2f}, trả lại ${giveback:.2f}.",
                    )
                    return
                if profit_usd <= mfe_floor:
                    close_by_anti_cash(
                        "Anti_Cash_MFE_Floor",
                        f"💰 [ANTI CASH] MFE Floor #{pos.ticket}: MFE ${mfe_usd:.2f}, PnL ${profit_usd:.2f} <= floor ${mfe_floor:.2f}.",
                    )
                    return

        if tsl_cfg.get("ANTI_CASH_MAE_ENABLE", True):
            mae_max_loss = self._resolve_money_value(
                tsl_cfg.get("ANTI_CASH_MAE_MAX_LOSS_USD", 25.0),
                tsl_cfg.get("ANTI_CASH_MAE_MAX_LOSS_UNIT", "USD"),
                pos=pos,
                equity=equity,
            )
            mae_min_hold = int(tsl_cfg.get("ANTI_CASH_MAE_MIN_HOLD_SEC", 300))
            low_mfe = self._resolve_money_value(
                tsl_cfg.get("ANTI_CASH_MAE_LOW_MFE_USD", 5.0),
                tsl_cfg.get("ANTI_CASH_MAE_LOW_MFE_UNIT", "USD"),
                pos=pos,
                equity=equity,
            )
            if (
                mae_max_loss > 0
                and profit_usd <= -mae_max_loss
                and hold_time >= mae_min_hold
                and mfe_usd < low_mfe
            ):
                close_by_anti_cash(
                    "Anti_Cash_MAE_Stop",
                    f"🔥 [ANTI CASH] MAE Stop #{pos.ticket}: PnL ${profit_usd:.2f}, MAE ${mae_usd:.2f}, MFE ${mfe_usd:.2f} < ${low_mfe:.2f}.",
                )
                return

        if tsl_cfg.get("ANTI_CASH_TIME_ENABLE", True):
            if hold_time > time_cut_s and profit_usd < 0:
                close_by_anti_cash(
                    "Anti_Cash_Time_Cut",
                    f"⏱ [ANTI CASH] Time Cut #{pos.ticket}: giữ {hold_time:.0f}s > {time_cut_s}s và PnL ${profit_usd:.2f}.",
                )

    def _check_recovery(self, pos, context):
        """[NEW V4.4] Close on Reverse (REV_C) logic"""
        # 1. Lấy signal hiện tại từ context (đã được Daemon ghi vào latest_signal)
        current_signal = context.get("latest_signal", 0)

        is_buy = pos.type == 0
        is_reversed = False
        reverse_signal = 0
        safe_cfg = self._get_brain_settings(pos.symbol).get("bot_safeguard", {})

        # Logic: Nếu đang BUY mà signal là -1 (SELL) hoặc ngược lại
        if is_buy and current_signal == -1:
            is_reversed = True
            reverse_signal = -1
        elif not is_buy and current_signal == 1:
            is_reversed = True
            reverse_signal = 1
        elif current_signal == 0 and safe_cfg.get("REV_CLOSE_ON_NONE", False):
            is_reversed = True
            reverse_signal = 0

        s_ticket = str(pos.ticket)
        rev_state = self.state.setdefault("rev_confirmations", {})
        if not is_reversed:
            if s_ticket in rev_state:
                rev_state.pop(s_ticket, None)
                save_state(self.state)
            return

        if is_reversed:
            current_reason = self.state.get("exit_reasons", {}).get(s_ticket, "")
            if current_reason in ("Recovery_Close", "Recovery_None"):
                return

            min_hold = float(safe_cfg.get("CLOSE_ON_REVERSE_MIN_TIME", 180))
            confirm_seconds = float(safe_cfg.get("REV_CONFIRM_SECONDS", 300) or 0)
            confirm_scans = int(safe_cfg.get("REV_CONFIRM_SCANS", 2) or 0)

            hold_time = time.time() - pos.time
            profit_usd = pos.profit + pos.swap + getattr(pos, "commission", 0.0)
            now = time.time()
            ctx_ts = context.get("timestamp", now)
            try:
                ctx_ts = float(ctx_ts)
            except (TypeError, ValueError):
                ctx_ts = now

            confirm = rev_state.get(s_ticket)
            if not confirm or int(confirm.get("signal", 999)) != reverse_signal:
                confirm = {
                    "signal": reverse_signal,
                    "first_seen": now,
                    "last_context_ts": ctx_ts,
                    "scans": 1,
                }
                rev_state[s_ticket] = confirm
                save_state(self.state)
            elif ctx_ts > float(confirm.get("last_context_ts", 0.0) or 0.0):
                confirm["last_context_ts"] = ctx_ts
                confirm["scans"] = int(confirm.get("scans", 1) or 1) + 1
                save_state(self.state)

            confirm_age = now - float(confirm.get("first_seen", now) or now)
            confirm_count = int(confirm.get("scans", 1) or 1)
            confirm_ok = (
                (confirm_seconds <= 0 or confirm_age >= confirm_seconds)
                and (confirm_scans <= 0 or confirm_count >= confirm_scans)
            )

            pnl_ok = True
            min_profit = 0.0
            max_loss = 0.0
            if safe_cfg.get("CLOSE_ON_REVERSE_USE_PNL", True):
                acc = self.connector.get_account_info()
                equity = acc.get("equity", 0.0) if acc else 0.0
                min_profit = self._resolve_money_value(
                    safe_cfg.get("REV_CLOSE_MIN_PROFIT", 0.0),
                    safe_cfg.get("REV_CLOSE_MIN_PROFIT_UNIT", "USD"),
                    pos=pos,
                    equity=equity,
                )
                max_loss = -abs(
                    self._resolve_money_value(
                        safe_cfg.get("REV_CLOSE_MAX_LOSS", 0.0),
                        safe_cfg.get("REV_CLOSE_MAX_LOSS_UNIT", "USD"),
                        pos=pos,
                        equity=equity,
                    )
                )

                if profit_usd >= 0:
                    pnl_ok = profit_usd >= min_profit if min_profit > 0 else True
                else:
                    pnl_ok = profit_usd <= max_loss if max_loss != 0 else True

            if hold_time >= min_hold and pnl_ok and confirm_ok:
                reverse_label = "NONE" if current_signal == 0 else ("SELL" if is_buy else "BUY")
                self.log(
                    f"  [RECOVERY] Đảo chiều Signal ({reverse_label}) | Confirm {confirm_age:.0f}/{confirm_seconds:.0f}s, {confirm_count}/{confirm_scans} scan | PnL: ${profit_usd:.2f} | Hold {hold_time:.0f}/{min_hold:.0f}s | MaxLoss ${abs(max_loss):.2f}. Đóng lệnh #{pos.ticket}",
                    target="bot",
                )
                self.state["exit_reasons"][s_ticket] = (
                    "Recovery_None" if current_signal == 0 else "Recovery_Close"
                )
                rev_state.pop(s_ticket, None)
                save_state(self.state)
                threading.Thread(
                    target=self._close_with_t2_log, args=(pos, "Reverse_Close"), daemon=True
                ).start()
            else:
                last_log = self.state.get("last_rev_log_time", {}).get(s_ticket, 0)
                log_cooldown = float(safe_cfg.get("LOG_COOLDOWN_MINUTES", 60.0)) * 60.0
                if time.time() - last_log > log_cooldown:
                    reverse_label = "NONE" if current_signal == 0 else ("SELL" if is_buy else "BUY")
                    if hold_time < min_hold:
                        reason = "HoldTime"
                    elif not confirm_ok:
                        reason = "RevConfirm"
                    else:
                        reason = "PnL_Filter"
                    self.log(
                        f"⏳ [RECOVERY] Giữ #{pos.ticket}: Signal {reverse_label} | {reason} | Confirm {confirm_age:.0f}/{confirm_seconds:.0f}s, {confirm_count}/{confirm_scans} scan | PnL ${profit_usd:.2f} | Hold {hold_time:.0f}/{min_hold:.0f}s | MaxLoss ${abs(max_loss):.2f}",
                        target="bot",
                    )
                    self.state.setdefault("last_rev_log_time", {})[s_ticket] = time.time()
                    save_state(self.state)

    def _apply_independent_tsl(self, pos, context):
        tactic_str = self.get_trade_tactic(pos.ticket)
        if tactic_str == "OFF" or not tactic_str:
            return "TSL OFF"

        active_modes = tactic_str.split("+")
        is_buy = pos.type == 0
        current_price = pos.price_current
        current_sl = pos.sl

        sym_info = self._get_symbol_info(pos.symbol)
        point = sym_info.point if sym_info else 0.00001

        one_r_dist = self._get_ticket_r_dist(pos)
        if one_r_dist <= 0:
            if pos.sl > 0:
                one_r_dist = abs(pos.price_open - pos.sl)
            else:
                return "Thiếu R-Dist"

        curr_dist = (
            current_price - pos.price_open if is_buy else pos.price_open - current_price
        )
        curr_r = curr_dist / one_r_dist
        profit_usd = self._position_profit_usd(pos)
        risk_usd = self._get_ticket_risk_usd(pos)
        curr_cash_r = profit_usd / risk_usd if risk_usd > 0 else curr_r

        candidates = []
        milestones = []
        tracking_modes = []

        brain = self._get_brain_settings(pos.symbol)
        tsl_cfg = brain.get("TSL_CONFIG", getattr(config, "TSL_CONFIG", {}))

        if "ANTI_CASH" in active_modes or "ANTI" in active_modes:
            acc = self.connector.get_account_info()
            equity = acc.get("equity", 0.0) if acc else 0.0
            s_ticket = str(pos.ticket)
            initial_cost = float(self.state.get("initial_costs", {}).get(s_ticket, 0.0) or 0.0)
            hard_stop_limit = self._resolve_money_value(
                tsl_cfg.get("ANTI_CASH_USD", 10.0),
                tsl_cfg.get("ANTI_CASH_HARD_STOP_UNIT", "USD"),
                pos=pos,
                equity=equity,
            )
            hard_threshold = hard_stop_limit + initial_cost
            if hard_threshold > 0 and profit_usd > -hard_threshold:
                milestones.append(
                    (
                        profit_usd + hard_threshold,
                        f"ANTI Hard đợi -${hard_threshold:.2f}",
                    )
                )

            if tsl_cfg.get("ANTI_CASH_MFE_ENABLE", True):
                excursion = self.state.get("trade_excursions", {}).get(s_ticket, {})
                mfe_usd = float(excursion.get("mfe_usd", profit_usd))
                mfe_trigger = self._resolve_money_value(
                    tsl_cfg.get("ANTI_CASH_MFE_TRIGGER_USD", 30.0),
                    tsl_cfg.get("ANTI_CASH_MFE_TRIGGER_UNIT", "USD"),
                    pos=pos,
                    equity=equity,
                )
                mfe_giveback = self._resolve_money_value(
                    tsl_cfg.get("ANTI_CASH_MFE_GIVEBACK_USD", 20.0),
                    tsl_cfg.get("ANTI_CASH_MFE_GIVEBACK_UNIT", "USD"),
                    pos=pos,
                    equity=equity,
                )
                mfe_floor = self._resolve_money_value(
                    tsl_cfg.get("ANTI_CASH_MFE_FLOOR_USD", 0.0),
                    tsl_cfg.get("ANTI_CASH_MFE_FLOOR_UNIT", "USD"),
                    pos=pos,
                    equity=equity,
                )
                if mfe_trigger > 0:
                    if mfe_usd < mfe_trigger:
                        milestones.append(
                            (
                                mfe_trigger - mfe_usd,
                                f"ANTI MFE đợi +${mfe_trigger:.2f}",
                            )
                        )
                    else:
                        cut_levels = []
                        if mfe_giveback > 0:
                            cut_levels.append(mfe_usd - mfe_giveback)
                        cut_levels.append(mfe_floor)
                        cut_level = max(cut_levels)
                        if profit_usd > cut_level:
                            milestones.append(
                                (
                                    profit_usd - cut_level,
                                    f"ANTI MFE guard ${cut_level:.2f}",
                                )
                            )
                        else:
                            milestones.append(
                                (
                                    0.0,
                                    f"ANTI MFE ready <= ${cut_level:.2f}",
                                )
                            )

        # [NEW V4.4] ONE-TIME BE: Bỏ qua BE/BE_CASH nếu SL đã được khoá an toàn
        one_time_be = tsl_cfg.get("ONE_TIME_BE", False)
        sl_better_than_entry = (is_buy and pos.sl >= pos.price_open) or (
            not is_buy and pos.sl > 0 and pos.sl <= pos.price_open
        )
        if one_time_be and sl_better_than_entry:
            if "BE" in active_modes:
                active_modes.remove("BE")
            if "BE_CASH" in active_modes:
                active_modes.remove("BE_CASH")

        if "BE" in active_modes:
            acc = self.connector.get_account_info()
            balance = acc.get("balance", 0.0) if acc else 0.0

            def resolve_be_sl_loss(value, unit):
                raw = float(value or 0.0)
                unit = str(unit or "R").upper().replace(" ", "")
                contract_size = getattr(sym_info, "trade_contract_size", 0.0) or 0.0
                if unit == "R":
                    cash = risk_usd * raw if risk_usd > 0 else abs(raw)
                    price_dist = one_r_dist * raw
                elif unit in ["%R", "PERCENT_R"]:
                    r_mult = raw / 100.0
                    cash = risk_usd * r_mult if risk_usd > 0 else abs(r_mult)
                    price_dist = one_r_dist * r_mult
                elif unit in ["PERCENT", "%", "PERCENT_BALANCE"]:
                    cash = balance * (raw / 100.0) if balance > 0 else abs(raw)
                    price_dist = cash / (pos.volume * contract_size) if pos.volume > 0 and contract_size > 0 else point
                elif unit == "POINT":
                    price_dist = raw * point
                    cash = price_dist * pos.volume * contract_size
                else:
                    cash = abs(raw)
                    price_dist = cash / (pos.volume * contract_size) if pos.volume > 0 and contract_size > 0 else point
                return abs(cash), abs(price_dist)

            loss_unit = tsl_cfg.get("BE_SL_LOSS_UNIT", "R")
            loss_trigger_usd, _ = resolve_be_sl_loss(
                tsl_cfg.get("BE_SL_LOSS_TRIGGER", 0.5), loss_unit
            )
            step_usd, _ = resolve_be_sl_loss(
                tsl_cfg.get("BE_SL_LOSS_STEP", 0.15), loss_unit
            )
            guard_buffer_usd, _ = resolve_be_sl_loss(
                tsl_cfg.get("BE_SL_GUARD_BUFFER", 0.0), loss_unit
            )
            if guard_buffer_usd <= 0 and step_usd > 0:
                guard_buffer_usd = step_usd / 2.0

            if loss_trigger_usd > 0 and step_usd > 0 and guard_buffer_usd > 0:
                s_ticket = str(pos.ticket)
                arms = self.state.setdefault("be_sl_arms", {})
                arm = arms.get(s_ticket)
                loss_usd = max(-profit_usd, 0.0)

                if not arm and loss_usd >= loss_trigger_usd:
                    arm = {
                        "armed_at": time.time(),
                        "trigger_pnl": profit_usd,
                        "worst_pnl": profit_usd,
                        "best_recovery_pnl": None,
                        "guard_pnl": None,
                    }
                    arms[s_ticket] = arm
                    save_state(self.state)
                    self.log(
                        f"[BE_SL] Arm recovery guard #{pos.ticket}: PnL ${profit_usd:.2f} <= -${loss_trigger_usd:.2f}",
                        target="bot",
                    )

                if arm:
                    worst_pnl = min(float(arm.get("worst_pnl", profit_usd)), profit_usd)
                    arm["worst_pnl"] = worst_pnl

                    if profit_usd >= 0:
                        arms.pop(s_ticket, None)
                        save_state(self.state)
                        self.log(
                            f"[BE_SL] Clear #{pos.ticket}: PnL hồi về ${profit_usd:.2f} >= $0.00",
                            target="bot",
                        )
                    else:
                        best_recovery = arm.get("best_recovery_pnl")
                        guard_pnl = arm.get("guard_pnl")
                        recovery_pnl = worst_pnl + step_usd

                        if best_recovery is None:
                            if profit_usd >= recovery_pnl:
                                best_recovery = profit_usd
                                guard_pnl = best_recovery - guard_buffer_usd
                                arm["best_recovery_pnl"] = best_recovery
                                arm["guard_pnl"] = guard_pnl
                                save_state(self.state)
                                self.log(
                                    f"[BE_SL] Recovery #{pos.ticket}: best ${best_recovery:.2f}, guard ${guard_pnl:.2f}",
                                    target="bot",
                                )
                            else:
                                milestones.append(
                                    (
                                        abs(recovery_pnl - profit_usd),
                                        f"BE_SL armed: chờ hồi ${recovery_pnl:.2f}",
                                    )
                                )
                        else:
                            best_recovery = float(best_recovery)
                            guard_pnl = float(guard_pnl)
                            if profit_usd > best_recovery:
                                best_recovery = profit_usd
                                guard_pnl = max(guard_pnl, best_recovery - guard_buffer_usd)
                                arm["best_recovery_pnl"] = best_recovery
                                arm["guard_pnl"] = guard_pnl
                                save_state(self.state)

                            if profit_usd <= guard_pnl:
                                self.log(
                                    f"[BE_SL] Recovery guard cut #{pos.ticket}: PnL ${profit_usd:.2f} <= guard ${guard_pnl:.2f}",
                                    target="bot",
                                )
                                self.state["exit_reasons"][s_ticket] = "BE_SL_Recovery_Guard"
                                arms.pop(s_ticket, None)
                                save_state(self.state)
                                threading.Thread(
                                    target=self._close_with_t2_log, args=(pos, "BE_SL_Recovery_Guard"), daemon=True
                                ).start()
                                return f"BE_SL Recovery Guard ${profit_usd:.2f}"

                            milestones.append(
                                (
                                    abs(profit_usd - guard_pnl),
                                    f"BE_SL guard ${guard_pnl:.2f} / best ${best_recovery:.2f}",
                                )
                            )
                elif loss_usd < loss_trigger_usd:
                    milestones.append(
                        (
                            max(loss_trigger_usd - loss_usd, 0.0),
                            f"BE_SL đợi loss -${loss_trigger_usd:.2f}",
                        )
                    )

        # [NEW V4.4] 1. BE_HARD_CASH (2 Giai đoạn: Trigger BE -> Trailing Step)
        if "BE_CASH" in active_modes:
            be_type = str(tsl_cfg.get("BE_CASH_TYPE", "USD")).upper()  # USD, PERCENT, POINT, R
            trigger_val = float(tsl_cfg.get("BE_TRIGGER", 10.0))
            step_val = float(tsl_cfg.get("BE_VALUE", 20.0))

            profit_usd = pos.profit + pos.swap + getattr(pos, "commission", 0.0)
            acc = self.connector.get_account_info()
            bal = acc["balance"] if acc else 1000

            # Quy đổi Trigger và Step ra USD
            trigger_usd, step_usd = 0, 0
            if be_type == "USD":
                trigger_usd, step_usd = trigger_val, step_val
            elif be_type == "PERCENT":
                trigger_usd, step_usd = (
                    bal * (trigger_val / 100.0),
                    bal * (step_val / 100.0),
                )
            elif be_type == "POINT":
                mult = point * pos.volume * sym_info.trade_contract_size
                trigger_usd, step_usd = trigger_val * mult, step_val * mult
            elif be_type == "R":
                trigger_usd = risk_usd * trigger_val if risk_usd > 0 else trigger_val
                step_usd = risk_usd * step_val if risk_usd > 0 else step_val
            elif be_type in ["%R", "PERCENT_R"]:
                trigger_mult = trigger_val / 100.0
                step_mult = step_val / 100.0
                trigger_usd = risk_usd * trigger_mult if risk_usd > 0 else trigger_mult
                step_usd = risk_usd * step_mult if risk_usd > 0 else step_mult

            if trigger_usd > 0:
                # Tính tổng phí hao hụt (Commission + Spread) để cắt hòa vốn không bị âm
                fee_protect = bool(tsl_cfg.get("BE_CASH_FEE_PROTECT", True))
                total_fee = 0.0
                if fee_protect:
                    total_fee = abs(getattr(pos, "commission", 0.0)) + (
                        sym_info.spread * point * pos.volume * sym_info.trade_contract_size
                    )

                if profit_usd >= trigger_usd:
                    locked_profit_usd = (
                        0  # Giai đoạn 1: Mới đạt Trigger -> Khóa BE ($0)
                    )

                    # Giai đoạn 2: Tính thêm các bước Trailing (Step)
                    extra_profit = profit_usd - trigger_usd
                    steps = math.floor(extra_profit / step_usd) if step_usd > 0 else 0

                    cash_strat = tsl_cfg.get("BE_CASH_STRAT", "TRAILING (Gap)")
                    cash_lock_label = f"CASH Step {steps}"
                    if steps >= 1:
                        if cash_strat == "LOCK (Tight)":
                            locked_profit_usd = trigger_usd + (steps * step_usd)
                            cash_lock_label = f"CASH Lock ${locked_profit_usd:.2f}"
                        elif cash_strat == "SOFT LOCK (Buffer)":
                            target_profit_usd = trigger_usd + (steps * step_usd)
                            buffer_type = tsl_cfg.get("BE_CASH_SOFT_BUFFER_TYPE", "USD")
                            buffer_val = float(tsl_cfg.get("BE_CASH_SOFT_BUFFER", 3.0))
                            if buffer_type == "PERCENT":
                                buffer_usd = bal * (buffer_val / 100.0)
                            elif buffer_type == "POINT":
                                buffer_usd = (
                                    buffer_val
                                    * point
                                    * pos.volume
                                    * sym_info.trade_contract_size
                                )
                            elif buffer_type == "ATR":
                                atr_group = tsl_cfg.get("SWING_GROUP", "G2")
                                if "DYNAMIC" in atr_group:
                                    market_mode = context.get("market_mode", "ANY")
                                    atr_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"
                                atr_val = float(context.get(f"atr_{atr_group}", 0.0) or 0.0)
                                buffer_usd = (
                                    buffer_val
                                    * atr_val
                                    * pos.volume
                                    * sym_info.trade_contract_size
                                )
                            elif buffer_type == "R":
                                buffer_usd = risk_usd * buffer_val if risk_usd > 0 else buffer_val
                            else:
                                buffer_usd = buffer_val

                            min_lock_usd = float(tsl_cfg.get("BE_CASH_MIN_LOCK", 0.0))
                            raw_lock_usd = target_profit_usd - buffer_usd
                            locked_profit_usd = (
                                max(raw_lock_usd, min_lock_usd)
                                if raw_lock_usd > 0
                                else 0.0
                            )
                            cash_lock_label = (
                                f"CASH SoftLock ${locked_profit_usd:.2f}"
                                f" (Target ${target_profit_usd:.2f} - Buffer ${buffer_usd:.2f})"
                            )
                        else:
                            locked_profit_usd = trigger_usd + ((steps - 1) * step_usd)
                            cash_lock_label = f"CASH Trail ${locked_profit_usd:.2f}"
                    elif cash_strat == "LOCK (Tight)":
                        locked_profit_usd = trigger_usd
                        cash_lock_label = f"CASH Lock ${locked_profit_usd:.2f}"
                    elif cash_strat == "SOFT LOCK (Buffer)":
                        buffer_type = tsl_cfg.get("BE_CASH_SOFT_BUFFER_TYPE", "USD")
                        buffer_val = float(tsl_cfg.get("BE_CASH_SOFT_BUFFER", 3.0))
                        if buffer_type == "PERCENT":
                            buffer_usd = bal * (buffer_val / 100.0)
                        elif buffer_type == "POINT":
                            buffer_usd = (
                                buffer_val
                                * point
                                * pos.volume
                                * sym_info.trade_contract_size
                            )
                        elif buffer_type == "ATR":
                            atr_group = tsl_cfg.get("SWING_GROUP", "G2")
                            if "DYNAMIC" in atr_group:
                                market_mode = context.get("market_mode", "ANY")
                                atr_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"
                            atr_val = float(context.get(f"atr_{atr_group}", 0.0) or 0.0)
                            buffer_usd = (
                                buffer_val
                                * atr_val
                                * pos.volume
                                * sym_info.trade_contract_size
                            )
                        elif buffer_type == "R":
                            buffer_usd = risk_usd * buffer_val if risk_usd > 0 else buffer_val
                        else:
                            buffer_usd = buffer_val

                        min_lock_usd = float(tsl_cfg.get("BE_CASH_MIN_LOCK", 0.0))
                        raw_lock_usd = trigger_usd - buffer_usd
                        locked_profit_usd = (
                            max(raw_lock_usd, min_lock_usd)
                            if raw_lock_usd > 0
                            else 0.0
                        )
                        cash_lock_label = (
                            f"CASH SoftLock ${locked_profit_usd:.2f}"
                            f" (Trig ${trigger_usd:.2f} - Buffer ${buffer_usd:.2f})"
                        )

                    # Quy đổi lợi nhuận USD muốn khóa ra khoảng cách giá (Price Distance)
                    lock_dist_price = locked_profit_usd / (
                        pos.volume * sym_info.trade_contract_size
                    )

                    # Mốc hòa vốn cơ sở (Đã cộng phí)
                    breakeven_dist = total_fee / (
                        pos.volume * sym_info.trade_contract_size
                    )

                    if is_buy:
                        base_be_price = pos.price_open + breakeven_dist
                        lock_price = base_be_price + lock_dist_price
                    else:
                        base_be_price = pos.price_open - breakeven_dist
                        lock_price = base_be_price - lock_dist_price

                    candidates.append((lock_price, cash_lock_label))

                # Tính Milestone hiển thị lên UI
                if profit_usd < trigger_usd:
                    milestones.append(
                        (
                            trigger_usd - profit_usd,
                            f"CASH Đợi Trig (${trigger_usd:.2f})",
                        )
                    )
                else:
                    extra_profit = profit_usd - trigger_usd
                    steps = math.floor(extra_profit / step_usd) if step_usd > 0 else 0
                    next_target_usd = trigger_usd + (steps + 1) * step_usd
                    milestone_label = f"CASH Đợi Step {steps + 1} (${next_target_usd:.2f})"
                    if tsl_cfg.get("BE_CASH_STRAT", "TRAILING (Gap)") == "SOFT LOCK (Buffer)":
                        buffer_type = tsl_cfg.get("BE_CASH_SOFT_BUFFER_TYPE", "USD")
                        buffer_val = float(tsl_cfg.get("BE_CASH_SOFT_BUFFER", 3.0))
                        if buffer_type == "PERCENT":
                            buffer_usd = bal * (buffer_val / 100.0)
                        elif buffer_type == "POINT":
                            buffer_usd = (
                                buffer_val
                                * point
                                * pos.volume
                                * sym_info.trade_contract_size
                            )
                        elif buffer_type == "ATR":
                            atr_group = tsl_cfg.get("SWING_GROUP", "G2")
                            if "DYNAMIC" in atr_group:
                                market_mode = context.get("market_mode", "ANY")
                                atr_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"
                            atr_val = float(context.get(f"atr_{atr_group}", 0.0) or 0.0)
                            buffer_usd = (
                                buffer_val
                                * atr_val
                                * pos.volume
                                * sym_info.trade_contract_size
                            )
                        elif buffer_type == "R":
                            buffer_usd = risk_usd * buffer_val if risk_usd > 0 else buffer_val
                        else:
                            buffer_usd = buffer_val
                        target_usd = trigger_usd + (steps * step_usd)
                        min_lock_usd = float(tsl_cfg.get("BE_CASH_MIN_LOCK", 0.0))
                        locked_usd = max(target_usd - buffer_usd, min_lock_usd)
                        if target_usd - buffer_usd <= 0:
                            locked_usd = 0.0
                        milestone_label = (
                            f"CASH SoftLock ${locked_usd:.2f}; "
                            f"đợi Step {steps + 1} (${next_target_usd:.2f})"
                        )
                    milestones.append(
                        (
                            next_target_usd - profit_usd,
                            milestone_label,
                        )
                    )

        # [NEW V4.4] 2. PSAR TRAILING
        if "PSAR_TRAIL" in active_modes and context:
            psar_min_rr = float(tsl_cfg.get("PSAR_MIN_RR", 0.0))
            psar_trigger_r = curr_cash_r
            if psar_min_rr > 0 and psar_trigger_r < psar_min_rr:
                milestones.append(
                    (abs(psar_min_rr - psar_trigger_r), f"PSAR Đợi Đủ {psar_min_rr}R")
                )
            else:
                trail_group = tsl_cfg.get("PSAR_GROUP", "G2")
                if "DYNAMIC" in trail_group:
                    market_mode = context.get("market_mode", "ANY")
                    trail_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"

                psar_val = context.get(f"psar_{trail_group}")
                if psar_val:
                    profit_only = bool(tsl_cfg.get("PSAR_PROFIT_ONLY", True))
                    buffer_points = float(tsl_cfg.get("PSAR_PROFIT_BUFFER_POINTS", 0))
                    profit_floor = (
                        pos.price_open + (buffer_points * point)
                        if is_buy
                        else pos.price_open - (buffer_points * point)
                    )
                    psar_locks_profit = (
                        psar_val >= profit_floor if is_buy else psar_val <= profit_floor
                    )

                    if not profit_only or psar_locks_profit:
                        candidates.append((psar_val, f"PSAR ➔ {psar_val:.2f}"))
                        tracking_modes.append("PSAR")
                    else:
                        milestones.append(
                            (
                                abs(psar_val - profit_floor),
                                f"PSAR Đợi BE ➔ {profit_floor:.2f}",
                            )
                        )

        if "BE_LEGACY" in active_modes:
            trig_r = tsl_cfg.get("BE_OFFSET_RR", 0.8)
            base = pos.price_open
            be_sl = (
                base + (tsl_cfg.get("BE_OFFSET_POINTS", 0) * point)
                if is_buy
                else base - (tsl_cfg.get("BE_OFFSET_POINTS", 0) * point)
            )
            trig_p = (
                base + (trig_r * one_r_dist) if is_buy else base - (trig_r * one_r_dist)
            )

            if curr_r >= trig_r:
                candidates.append((be_sl, "BE_SL"))
            else:
                milestones.append(
                    (abs(curr_r - trig_r), f"BE_SL Đợi {trig_p:.2f} ➔ {be_sl:.2f}")
                )

        if "STEP_R" in active_modes:
            sz, rt = tsl_cfg.get("STEP_R_SIZE", 1.0), tsl_cfg.get("STEP_R_RATIO", 0.8)
            steps = math.floor(curr_r / sz)

            if steps >= 1:
                step_sl = (
                    pos.price_open + (steps * one_r_dist * rt)
                    if is_buy
                    else pos.price_open - (steps * one_r_dist * rt)
                )
                candidates.append((step_sl, f"STEP {steps}"))

            next_step = steps + 1
            next_trig_p = (
                pos.price_open + (next_step * sz * one_r_dist)
                if is_buy
                else pos.price_open - (next_step * sz * one_r_dist)
            )
            next_sl = (
                pos.price_open + (next_step * sz * one_r_dist * rt)
                if is_buy
                else pos.price_open - (next_step * sz * one_r_dist * rt)
            )
            milestones.append(
                (
                    abs(curr_r - next_step * sz),
                    f"Step {next_step} Đợi {next_trig_p:.2f} ➔ {next_sl:.2f}",
                )
            )

        if "PNL" in active_modes:
            acc = self.connector.get_account_info()
            if acc:
                profit_usd = pos.profit + pos.swap + getattr(pos, "commission", 0.0)
                pnl_pct = (profit_usd / acc["balance"]) * 100
                levels = sorted(tsl_cfg.get("PNL_LEVELS", []), key=lambda x: x[0])

                for lvl in levels:
                    req_profit_usd = acc["balance"] * (lvl[0] / 100.0)
                    lock_dist = (acc["balance"] * (lvl[1] / 100.0)) / (
                        pos.volume * sym_info.trade_contract_size
                    )
                    pnl_sl = (
                        pos.price_open + lock_dist
                        if is_buy
                        else pos.price_open - lock_dist
                    )
                    trig_p = (
                        pos.price_open
                        + (req_profit_usd / (pos.volume * sym_info.trade_contract_size))
                        if is_buy
                        else pos.price_open
                        - (req_profit_usd / (pos.volume * sym_info.trade_contract_size))
                    )

                    if pnl_pct >= lvl[0]:
                        candidates.append((pnl_sl, f"PNL {lvl[1]}%"))
                    else:
                        milestones.append(
                            (
                                abs(pnl_pct - lvl[0]),
                                f"PnL {lvl[0]}% Đợi {trig_p:.2f} ➔ {pnl_sl:.2f}",
                            )
                        )
                        break

        if "SWING" in active_modes and context:
            trail_group = tsl_cfg.get("SWING_GROUP", "G2")
            market_mode = context.get("market_mode", "ANY")
            is_trending = market_mode in ["TREND", "BREAKOUT"]
            if "DYNAMIC" in trail_group:
                trail_group = "G1" if is_trending else "G2"

            sh = context.get(f"swing_high_{trail_group}")
            sl = context.get(f"swing_low_{trail_group}")
            atr = context.get(f"atr_{trail_group}", 0)

            if sh is not None and sl is not None and atr:
                brain = self._get_brain_settings(pos.symbol)
                risk_tsl = brain.get("risk_tsl", {})
                trail_buf = float(
                    risk_tsl.get(
                        "sl_atr_multiplier", getattr(config, "sl_atr_multiplier", 0.2)
                    )
                )

                tsl_mode = brain.get(
                    "TSL_LOGIC_MODE",
                    risk_tsl.get("tsl_mode", tsl_cfg.get("TSL_LOGIC_MODE", "STATIC")),
                )
                is_trending = context.get("market_mode", "TREND") in [
                    "TREND",
                    "BREAKOUT",
                ]

                swing_sl = 0.0
                if is_buy:
                    if tsl_mode == "STATIC":
                        swing_sl = sl - (trail_buf * atr)
                    elif tsl_mode == "AGGRESSIVE":
                        swing_sl = sh - (trail_buf * atr)
                    elif tsl_mode == "DYNAMIC":
                        swing_sl = (
                            sl - (trail_buf * atr)
                            if is_trending
                            else sh - (trail_buf * atr)
                        )
                else:
                    if tsl_mode == "STATIC":
                        swing_sl = sh + (trail_buf * atr)
                    elif tsl_mode == "AGGRESSIVE":
                        swing_sl = sl + (trail_buf * atr)
                    elif tsl_mode == "DYNAMIC":
                        swing_sl = (
                            sh + (trail_buf * atr)
                            if is_trending
                            else sl + (trail_buf * atr)
                        )

                candidates.append((swing_sl, f"SWING ➔ {swing_sl:.2f}"))
                tracking_modes.append("SWING")

        valid_moves = []
        min_stop_dist = getattr(sym_info, "trade_stops_level", 0) * point
        for price, rule in candidates:
            if not price:
                continue
            price = round(price / point) * point
            if is_buy:
                if (
                    price > current_sl + (point / 2)
                    and price <= current_price - min_stop_dist
                ):
                    valid_moves.append((price, rule))
            else:
                if (
                    current_sl == 0 or price < current_sl - (point / 2)
                ) and price >= current_price + min_stop_dist:
                    valid_moves.append((price, rule))

        if valid_moves:
            target_sl, action_rule = (
                max(valid_moves, key=lambda x: x[0])
                if is_buy
                else min(valid_moves, key=lambda x: x[0])
            )
            if abs(target_sl - current_sl) > (point / 2):
                self.connector.modify_position(pos, target_sl, pos.tp)
                # [NEW] Lưu quy tắc dời SL để tracking lý do đóng lệnh sau này
                if "last_tsl_rules" not in self.state:
                    self.state["last_tsl_rules"] = {}
                self.state["last_tsl_rules"][str(pos.ticket)] = action_rule
                save_state(self.state)
                return f"{action_rule} Đã kéo ➔ {target_sl:.2f}"

        if milestones:
            return sorted(milestones, key=lambda x: x[0])[0][1]

        if tracking_modes:
            return "Theo dõi: " + "/".join(tracking_modes)

        return "Tracking..."
