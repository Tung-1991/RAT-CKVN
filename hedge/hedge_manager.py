# -*- coding: utf-8 -*-
"""HEDGE Dual V1 manager.

This module owns HEDGE state only. It does not write BOT/manual/GRID state.
"""

import copy
import math
import time
from datetime import datetime

import MetaTrader5 as mt5

import config
from core.entry_exit_engine import evaluate_entry_exit, format_decision
from core.market_hours import is_symbol_trade_window_open
from core.position_classifier import is_hedge_position
from core.storage_manager import append_trade_log, get_brain_settings_for_symbol, get_magic_numbers, get_today_str

from .hedge_executor import HedgeExecutor
from .hedge_storage import load_hedge_settings, load_hedge_state, save_hedge_settings, save_hedge_state


class HedgeManager:
    def __init__(self, connector=None, data_engine=None, signal_generator=None, log_callback=None):
        self.connector = connector
        self.data_engine = data_engine
        self.signal_generator = signal_generator
        self.log_callback = log_callback
        self.executor = HedgeExecutor(connector=connector, log_callback=log_callback)
        self._decision_log_cache = {}

    def log(self, message, error=False):
        if self.log_callback:
            self.log_callback(f"[HEDGE] {message}", error=error, target="hedge")

    def reload(self):
        return {"settings": load_hedge_settings(), "state": load_hedge_state()}

    def _ensure_hedge_state(self, state):
        today = get_today_str()
        if state.get("date") != today:
            state["date"] = today
            state["hedge_pnl_today"] = 0.0
            state["hedge_sessions_today"] = 0
            state["hedge_daily_loss_count"] = 0
        state.setdefault("active_sessions", {})
        state.setdefault("last_decision", {})
        state.setdefault("last_decision_log_keys", {})
        state.setdefault("last_close_times", {})
        state.setdefault("last_loss_times", {})
        state.setdefault("global_cooldown_until", 0.0)
        state.setdefault("consecutive_losses", 0)
        state.setdefault("hedge_active_tickets", [])
        state.setdefault("hedge_pnl_today", 0.0)
        state.setdefault("hedge_sessions_today", 0)
        state.setdefault("hedge_daily_loss_count", 0)

    def _daily_safety(self, state, settings):
        max_daily_loss = float(settings.get("HEDGE_MAX_DAILY_LOSS", 0.0) or 0.0)
        if max_daily_loss > 0 and float(state.get("hedge_pnl_today", 0.0) or 0.0) <= -abs(max_daily_loss):
            return False, "HEDGE_DAILY_LOSS"
        max_day = int(settings.get("MAX_SESSIONS_PER_DAY", 0) or 0)
        if max_day > 0 and int(state.get("hedge_sessions_today", 0) or 0) >= max_day:
            return False, "MAX_SESSIONS_PER_DAY"
        return True, "OK"

    def settings_for_symbol(self, symbol, settings=None):
        base = copy.deepcopy(settings or load_hedge_settings())
        overrides = base.get("SYMBOL_OVERRIDES") or {}
        symbol_cfg = overrides.get(symbol, {}) if isinstance(overrides, dict) else {}
        if isinstance(symbol_cfg, dict):
            for key, value in symbol_cfg.items():
                if key != "SYMBOL_OVERRIDES":
                    base[key] = value
        return base

    def evaluate_entry_gate(self, symbol, context=None, settings=None):
        cfg = self.settings_for_symbol(symbol, settings)
        context = self._prepare_hedge_context(symbol, context or {}, cfg)
        reasons = []

        signal_on = bool(cfg.get("USE_SIGNAL_FILTER", False))
        latest_signal = int(context.get("latest_signal", 0) or 0)
        if signal_on and latest_signal == 0:
            reasons.append("SIGNAL_NONE")
        signal_status = "OFF" if not signal_on else ("PASS" if latest_signal != 0 else "WAIT")

        entry_on = bool(cfg.get("USE_ENTRY_EXIT_FILTER", False))
        entry_status = "OFF"
        entry_reason = "OFF"
        entry_decisions = {}
        signal_direction = "BUY" if latest_signal == 1 else "SELL" if latest_signal == -1 else None
        if entry_on:
            entry_decisions = self._entry_exit_decisions(symbol, context, cfg, signal_direction)
            ready = [side for side, decision in entry_decisions.items() if decision.get("status") == "READY"]
            if ready:
                entry_status = "PASS"
                entry_reason = ",".join(ready)
            else:
                entry_status = "WAIT"
                entry_reason = "; ".join(
                    f"{side}:{decision.get('status')}:{decision.get('reason', '')}"
                    for side, decision in entry_decisions.items()
                ) or "ENTRY_EXIT_NOT_READY"
                reasons.append("ENTRY_EXIT_NOT_READY")

        permission = not reasons
        return {
            "permission": permission,
            "status": "READY" if permission else "WAIT",
            "reason": "OK" if permission else "+".join(reasons),
            "signal": latest_signal,
            "signal_status": signal_status,
            "signal_direction": signal_direction,
            "entry_status": entry_status,
            "entry_reason": entry_reason,
            "entry_decisions": entry_decisions,
            "tactic": "DUAL",
        }

    def _prepare_hedge_context(self, symbol, context, settings):
        return context

    def clear_session_block(self, symbol=None):
        state = load_hedge_state()
        self._ensure_hedge_state(state)
        for sym, session in list(state.get("active_sessions", {}).items()):
            if symbol and sym != symbol:
                continue
            if isinstance(session, dict) and session.get("status") in {"STOP_NEW", "BLOCK"}:
                session["status"] = "PAIR_OPEN"
                session.pop("stop_reason", None)
                session.pop("last_block_reason", None)
                session["updated_at"] = time.time()
        if symbol:
            state.get("last_decision", {}).pop(symbol, None)
            state.setdefault("last_loss_times", {}).pop(symbol, None)
        else:
            state["last_decision"] = {}
            state["last_loss_times"] = {}
            state["global_cooldown_until"] = 0.0
            state["consecutive_losses"] = 0
        save_hedge_state(state)
        return "SUCCESS"

    def stop_session(self, symbol=None):
        state = load_hedge_state()
        self._ensure_hedge_state(state)
        changed = 0
        for sym, session in list(state.get("active_sessions", {}).items()):
            if symbol and sym != symbol:
                continue
            if isinstance(session, dict):
                session["status"] = "STOP_NEW"
                session["stop_reason"] = "USER_STOP_SESSION"
                session["updated_at"] = time.time()
                changed += 1
        save_hedge_state(state)
        return f"SUCCESS|{changed}"

    def start_manual_session(self, symbol, context=None):
        settings = load_hedge_settings()
        state = load_hedge_state()
        self._ensure_hedge_state(state)
        result = self._start_pair_session(symbol, context or {}, settings, state, source="MANUAL")
        save_hedge_state(state)
        return result

    def _start_pair_session(self, symbol, context, settings, state, source="MANUAL"):
        cfg = self.settings_for_symbol(symbol, settings)
        context = self._prepare_hedge_context(symbol, context or {}, cfg)
        ok_daily, daily_reason = self._daily_safety(state, cfg)
        if not ok_daily:
            self._record_decision(state, symbol, None, "BLOCK", daily_reason)
            return f"HEDGE_BLOCK|{daily_reason}"
        global_until = float(state.get("global_cooldown_until", 0.0) or 0.0)
        if global_until > time.time():
            self._record_decision(state, symbol, None, "WAIT", "GLOBAL_LOSS_COOLDOWN")
            return "HEDGE_BLOCK|GLOBAL_LOSS_COOLDOWN"
        gate = self.evaluate_entry_gate(symbol, context or {}, settings)
        if not gate["permission"]:
            self._record_decision(state, symbol, None, "WAIT", gate["reason"], gate=gate)
            return f"HEDGE_BLOCK|{gate['reason']}"

        ok, reason = self._hard_safety(symbol, cfg)
        if not ok:
            self._record_decision(state, symbol, None, "BLOCK", reason, gate=gate)
            return f"HEDGE_BLOCK|{reason}"

        existing = self._hedge_positions(symbol)
        max_pairs = int(cfg.get("MAX_PAIRS_PER_SYMBOL", 1) or 1)
        if len(existing) >= max_pairs * 2:
            self._record_decision(state, symbol, None, "BLOCK", "MAX_PAIRS_PER_SYMBOL", gate=gate)
            return "HEDGE_BLOCK|MAX_PAIRS_PER_SYMBOL"

        cooldown = float(cfg.get("COOLDOWN_AFTER_CLOSE_SECONDS", 900) or 0)
        last_close = float(state.get("last_close_times", {}).get(symbol, 0.0) or 0.0)
        if cooldown > 0 and time.time() - last_close < cooldown:
            self._record_decision(state, symbol, None, "WAIT", "COOLDOWN_AFTER_CLOSE", gate=gate)
            return "HEDGE_BLOCK|COOLDOWN_AFTER_CLOSE"

        loss_cooldown = float(cfg.get("COOLDOWN_AFTER_LOSS_SECONDS", 0) or 0)
        last_loss = float(state.get("last_loss_times", {}).get(symbol, 0.0) or 0.0)
        if loss_cooldown > 0 and time.time() - last_loss < loss_cooldown:
            self._record_decision(state, symbol, None, "WAIT", "COOLDOWN_AFTER_LOSS", gate=gate)
            return "HEDGE_BLOCK|COOLDOWN_AFTER_LOSS"

        context = dict(context or {})
        context["hedge_sl_rule"] = str(cfg.get("HEDGE_SL_RULE", "BASE_SL_ATR") or "BASE_SL_ATR").upper()
        context["hedge_tp_rule"] = str(cfg.get("HEDGE_TP_RULE", "RR") or "RR").upper()
        sltp = self._resolve_pair_sltp(symbol, cfg, context, gate.get("entry_decisions") or {})
        if not sltp.get("ready", False):
            self._record_decision(state, symbol, None, "BLOCK", sltp.get("reason", "SLTP_FAILED"), gate=gate)
            return f"HEDGE_BLOCK|{sltp.get('reason', 'SLTP_FAILED')}"

        lot, lot_meta = self._resolve_lot_size(symbol, cfg, context, sltp=sltp)
        if not lot or lot <= 0:
            reason = lot_meta.get("reason", "LOT_CALC_FAILED") if isinstance(lot_meta, dict) else "LOT_CALC_FAILED"
            self._record_decision(state, symbol, None, "BLOCK", reason, gate=gate)
            return f"HEDGE_BLOCK|{reason}"
        session_id = f"HEDGE_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        hedge_magic = get_magic_numbers().get("hedge_magic", 99888)

        buy_result = self.executor.place_hedge_leg(
            symbol,
            "BUY",
            lot,
            hedge_magic,
            session_id,
            sltp.get("BUY", {}).get("sl", 0.0),
            sltp.get("BUY", {}).get("tp", 0.0),
        )
        if "SUCCESS" not in buy_result:
            self._record_decision(state, symbol, None, "BLOCK", buy_result, gate=gate)
            return buy_result
        buy_ticket = int(buy_result.split("|", 1)[1])
        sell_result = self.executor.place_hedge_leg(
            symbol,
            "SELL",
            lot,
            hedge_magic,
            session_id,
            sltp.get("SELL", {}).get("sl", 0.0),
            sltp.get("SELL", {}).get("tp", 0.0),
        )
        if "SUCCESS" not in sell_result:
            buy_pos = self._position_by_ticket(buy_ticket)
            if buy_pos:
                self.executor.close_position(buy_pos, "PAIR_FAIL")
            self._record_decision(state, symbol, None, "BLOCK", "PAIR_OPEN_FAILED", gate=gate)
            return f"HEDGE_FAIL|PAIR_OPEN_FAILED|{sell_result}"
        sell_ticket = int(sell_result.split("|", 1)[1])

        session = {
            "session_id": session_id,
            "symbol": symbol,
            "source": source,
            "status": "PAIR_OPEN",
            "tactic": "DUAL",
            "buy_ticket": buy_ticket,
            "sell_ticket": sell_ticket,
            "created_at": time.time(),
            "updated_at": time.time(),
            "entry_gate": gate,
            "lot_mode": lot_meta.get("LOT_MODE", str(cfg.get("LOT_MODE", "FIXED")).upper()),
            "lot_per_leg": lot,
            "lot_sizing": lot_meta,
            "sltp": sltp,
            "use_tsl": bool(cfg.get("USE_TSL", True)),
            "survivor_protect": str(cfg.get("SURVIVOR_PROTECT", "BE_FEE") or "BE_FEE").upper(),
            "initial_r_dist": {
                str(buy_ticket): sltp.get("BUY", {}).get("risk_distance", 0.0),
                str(sell_ticket): sltp.get("SELL", {}).get("risk_distance", 0.0),
            },
            "initial_r_usd": {},
            "mfe": 0.0,
            "mae": 0.0,
            "closed_leg_pnl": 0.0,
        }
        session["initial_r_usd"][str(buy_ticket)] = self._calc_risk_usd_for_ticket(symbol, lot, sltp.get("BUY", {}).get("risk_distance", 0.0))
        session["initial_r_usd"][str(sell_ticket)] = self._calc_risk_usd_for_ticket(symbol, lot, sltp.get("SELL", {}).get("risk_distance", 0.0))
        state.setdefault("active_sessions", {})[symbol] = session
        state["hedge_sessions_today"] = int(state.get("hedge_sessions_today", 0) or 0) + 1
        self._record_decision(state, symbol, session, "OPEN", "PAIR_OPENED", gate=gate)
        return f"SUCCESS|{session_id}"

    def scan(self, symbols=None, contexts=None):
        settings = load_hedge_settings()
        state = load_hedge_state()
        self._ensure_hedge_state(state)
        actions = []
        if settings.get("ENABLED", False):
            scan_symbols = list(symbols or settings.get("WATCHLIST") or [])
            if not scan_symbols:
                self._record_decision(state, "---", None, "WAIT", "WATCHLIST_EMPTY")
            for symbol in scan_symbols:
                if symbol in (state.get("active_sessions") or {}):
                    continue
                context = (contexts or {}).get(symbol, {}) if isinstance(contexts, dict) else {}
                result = self._start_pair_session(symbol, context, settings, state, source="AUTO")
                if result.startswith("SUCCESS"):
                    actions.append(f"HEDGE_OPEN|{symbol}|AUTO")
        for symbol, session in list(state.get("active_sessions", {}).items()):
            context = (contexts or {}).get(symbol, {}) if isinstance(contexts, dict) else {}
            actions.extend(self._manage_session(symbol, session, self.settings_for_symbol(symbol, settings), state, context=context))
        self._sync_hedge_history(state)
        save_hedge_state(state)
        return {"status": "OK", "actions": actions}

    def _hard_safety(self, symbol, settings):
        if not self.connector or not getattr(self.connector, "_is_connected", False):
            return False, "NO_CONNECTION"
        is_open, reason = is_symbol_trade_window_open(symbol)
        if not is_open:
            return False, f"MARKET_CLOSED:{reason}"
        if settings.get("CHECK_PING", True):
            try:
                ping_ms = mt5.terminal_info().ping_last / 1000
            except Exception:
                ping_ms = 0
            if ping_ms > int(settings.get("MAX_PING_MS", 150) or 150):
                return False, f"PING:{ping_ms:.0f}"
        if settings.get("CHECK_SPREAD", True):
            tick = mt5.symbol_info_tick(symbol)
            info = mt5.symbol_info(symbol)
            if tick and info and getattr(info, "point", 0) > 0:
                spread_points = (tick.ask - tick.bid) / info.point
                if spread_points > int(settings.get("MAX_SPREAD_POINTS", 150) or 150):
                    return False, f"SPREAD:{spread_points:.0f}"
        return True, "OK"

    def _hedge_positions(self, symbol=None):
        magics = get_magic_numbers()
        positions = self.connector.get_all_open_positions() if self.connector else []
        return [p for p in positions if is_hedge_position(p, magics) and (symbol is None or getattr(p, "symbol", None) == symbol)]

    def _position_by_ticket(self, ticket):
        for pos in self._hedge_positions():
            try:
                if int(pos.ticket) == int(ticket):
                    return pos
            except Exception:
                pass
        return None

    def _pos_pnl(self, pos):
        return float(getattr(pos, "profit", 0.0) or 0.0) + float(getattr(pos, "swap", 0.0) or 0.0) + float(getattr(pos, "commission", 0.0) or 0.0)

    def _normalize_lot(self, symbol, lot, max_lot_cap=0.0):
        info = mt5.symbol_info(symbol)
        min_lot = float(getattr(info, "volume_min", 0.01) or 0.01) if info else 0.01
        max_lot = float(getattr(info, "volume_max", 100.0) or 100.0) if info else 100.0
        step = float(getattr(info, "volume_step", 0.01) or 0.01) if info else 0.01
        if max_lot_cap and max_lot_cap > 0:
            max_lot = min(max_lot, float(max_lot_cap))
        lot = max(min_lot, min(float(lot or min_lot), max_lot))
        if step > 0:
            lot = round(lot / step) * step
        return round(max(min_lot, min(lot, max_lot)), 2)

    def _account_base_value(self, cfg):
        if not self.connector:
            return 0.0
        try:
            acc = self.connector.get_account_info() or {}
        except Exception:
            return 0.0
        return float(acc.get("equity", acc.get("balance", 0.0)) or 0.0)

    def _brain_settings(self, symbol):
        try:
            return get_brain_settings_for_symbol(symbol)
        except Exception:
            return {}

    def _entry_exit_decisions(self, symbol, context, cfg, signal_direction=None):
        price = float(context.get("hedge_current_price", context.get("current_price", 0.0)) or 0.0)
        if price <= 0:
            return {}
        brain = self._brain_settings(symbol)
        entry_exit_cfg = self._hedge_entry_exit_cfg(brain.get("entry_exit", {}), cfg)
        directions = [signal_direction] if signal_direction in {"BUY", "SELL"} else ["BUY", "SELL"]
        decisions = {}
        for direction in directions:
            try:
                decisions[direction] = evaluate_entry_exit(symbol, direction, price, context or {}, entry_exit_cfg)
            except Exception as exc:
                decisions[direction] = {"status": "ERROR", "reason": str(exc), "direction": direction}
        return decisions

    def _hedge_entry_exit_cfg(self, base_cfg, cfg):
        ee_cfg = copy.deepcopy(base_cfg or {})
        entry_rule = str(cfg.get("HEDGE_ENTRY_RULE", "SWING_REJECTION") or "SWING_REJECTION").upper()
        sl_rule = str(cfg.get("HEDGE_EE_SL_RULE", "MATCH_ENTRY") or "MATCH_ENTRY").upper()
        tp_rule = str(cfg.get("HEDGE_EE_TP_RULE", "MATCH_ENTRY") or "MATCH_ENTRY").upper()
        if sl_rule == "MATCH_ENTRY":
            sl_rule = "AUTO"
        if tp_rule == "MATCH_ENTRY":
            tp_rule = "AUTO"
        ee_cfg["enabled"] = True
        ee_cfg["active_tactics"] = [entry_rule]
        ee_cfg["entry_tactics"] = [entry_rule]
        ee_cfg["sl_mode"] = sl_rule
        ee_cfg["exit_tactic"] = tp_rule
        return ee_cfg

    def _resolve_pair_sltp(self, symbol, cfg, context, entry_decisions=None):
        result = {"ready": True, "BUY": {}, "SELL": {}}
        for direction in ("BUY", "SELL"):
            side = self._resolve_leg_sltp(symbol, direction, cfg, context, (entry_decisions or {}).get(direction))
            if not side.get("ready", False):
                return {"ready": False, "reason": f"{direction}_{side.get('reason', 'SLTP_FAILED')}"}
            result[direction] = side
        return result

    def _resolve_leg_sltp(self, symbol, direction, cfg, context, ee_decision=None):
        sl = 0.0
        tp = 0.0
        source = "OFF"
        if ee_decision and ee_decision.get("status") == "READY":
            sl = float(ee_decision.get("sl") or 0.0)
            tp = float(ee_decision.get("tp") or 0.0)
            source = f"ENTRY_EXIT:{ee_decision.get('entry_tactic', 'AUTO')}"
        hedge_sltp_on = bool(cfg.get("USE_HEDGE_SLTP", cfg.get("USE_SANDBOX_SLTP", True)))
        if sl <= 0 and hedge_sltp_on:
            hedge_rule = self._hedge_rule_leg_sltp(symbol, direction, context, ee_decision)
            if not hedge_rule.get("ready", False):
                return hedge_rule
            sl = float(hedge_rule.get("sl") or 0.0)
            if tp <= 0:
                tp = float(hedge_rule.get("tp") or 0.0)
            source = hedge_rule.get("source", "HEDGE_RULE") if source == "OFF" else source
        if not hedge_sltp_on and not (ee_decision and ee_decision.get("status") == "READY"):
            source = "OFF"
        price = float(context.get("hedge_current_price", context.get("current_price", 0.0)) or 0.0)
        if (sl > 0 or tp > 0) and price <= 0:
            return {"ready": False, "reason": "NO_PRICE"}
        risk_distance = abs(price - sl) if sl > 0 else 0.0
        return {"ready": True, "sl": sl, "tp": tp, "source": source, "risk_distance": risk_distance}

    def _hedge_rule_leg_sltp(self, symbol, direction, context, ee_decision=None):
        sl_rule = str(context.get("hedge_sl_rule") or "BASE_SL_ATR").upper()
        tp_rule = str(context.get("hedge_tp_rule") or "RR").upper()
        if sl_rule != "BASE_SL_ATR":
            return self._hedge_entry_exit_sltp(symbol, direction, context, sl_rule, tp_rule)
        brain = self._brain_settings(symbol)
        risk_tsl = brain.get("risk_tsl", {})
        safeguard_cfg = brain.get("safeguard", getattr(config, "SAFEGUARD_CONFIG", {}))
        price = float(context.get("hedge_current_price", context.get("current_price", 0.0)) or 0.0)
        market_mode = context.get("market_mode", "ANY")
        sl_group = risk_tsl.get("base_sl", getattr(config, "BOT_BASE_SL", "G2"))
        if "DYNAMIC" in str(sl_group):
            sl_group = "G1" if market_mode in ["TREND", "BREAKOUT"] else "G2"
        atr = float(context.get(f"atr_{sl_group}", context.get("atr_entry", 0.0)) or 0.0)
        swing_l = context.get(f"swing_low_{sl_group}")
        swing_h = context.get(f"swing_high_{sl_group}")
        if not price or not atr or swing_l is None or swing_h is None:
            return {"ready": False, "reason": f"NO_HEDGE_SLTP_DATA_{sl_group}"}
        sl_mult = float(risk_tsl.get("sl_atr_multiplier", getattr(config, "sl_atr_multiplier", 0.2)) or 0.2)
        buffer_atr = atr * sl_mult
        sl = float(swing_l) - buffer_atr if direction == "BUY" else float(swing_h) + buffer_atr
        dist = abs(price - sl)
        if dist <= 0:
            return {"ready": False, "reason": "INVALID_HEDGE_SL"}
        min_safe_dist = price * 0.0005
        if dist < min_safe_dist:
            return {"ready": False, "reason": "HEDGE_SL_TOO_TIGHT"}
        if tp_rule in ("NO_TP", "OFF") or (ee_decision and ee_decision.get("tp_disabled")):
            tp = 0.0
        elif ee_decision and ee_decision.get("tp"):
            tp = float(ee_decision.get("tp"))
        elif tp_rule in ("SWING", "SWING_TP") or bool(safeguard_cfg.get("BOT_USE_SWING_TP", False)) and tp_rule == "AUTO":
            tp = float(swing_h) - buffer_atr if direction == "BUY" else float(swing_l) + buffer_atr
        elif tp_rule in ("RR", "R") or bool(safeguard_cfg.get("BOT_USE_RR_TP", True)) and tp_rule == "AUTO":
            rr = float(safeguard_cfg.get("BOT_TP_RR_RATIO", getattr(config, "BOT_TP_RR_RATIO", 1.5)) or 1.5)
            tp = price + dist * rr if direction == "BUY" else price - dist * rr
        else:
            tp = 0.0
        return {"ready": True, "sl": sl, "tp": tp, "source": f"HEDGE_RULE:{sl_group}", "risk_distance": dist}

    def _hedge_entry_exit_sltp(self, symbol, direction, context, sl_rule, tp_rule):
        brain = self._brain_settings(symbol)
        ee_cfg = copy.deepcopy(brain.get("entry_exit", {}) or {})
        exit_rule = {
            "RR": "RR",
            "R": "RR",
            "SWING": "SWING_STRUCTURE",
            "SWING_TP": "SWING_STRUCTURE",
            "NO_TP": "NO_TP",
            "OFF": "NO_TP",
        }.get(tp_rule, tp_rule)
        ee_cfg["enabled"] = True
        ee_cfg["active_tactics"] = ["FALLBACK_R"]
        ee_cfg["entry_tactics"] = ["FALLBACK_R"]
        ee_cfg["sl_mode"] = sl_rule
        ee_cfg["exit_tactic"] = exit_rule
        price = float(context.get("hedge_current_price", context.get("current_price", 0.0)) or 0.0)
        decision = evaluate_entry_exit(symbol, direction, price, context or {}, ee_cfg)
        sl = float(decision.get("sl") or 0.0)
        tp = float(decision.get("tp") or 0.0)
        if sl <= 0:
            return {"ready": False, "reason": f"NO_HEDGE_SL_{sl_rule}"}
        dist = abs(price - sl)
        if dist <= 0:
            return {"ready": False, "reason": "INVALID_HEDGE_SL"}
        return {"ready": True, "sl": sl, "tp": tp, "source": f"HEDGE_RULE:{sl_rule}/{tp_rule}", "risk_distance": dist}

    def _calc_risk_usd_for_ticket(self, symbol, lot, risk_distance):
        info = mt5.symbol_info(symbol)
        contract_size = float(getattr(info, "trade_contract_size", 1.0) or 1.0) if info else 1.0
        return abs(float(risk_distance or 0.0) * float(lot or 0.0) * contract_size)

    def _virtual_sl_prices_for_lot(self, symbol, cfg, context):
        group = str(cfg.get("SWING_GROUP", "G2") or "G2").upper()
        low = context.get("hedge_swing_low", context.get(f"swing_low_{group}", context.get("swing_low")))
        high = context.get("hedge_swing_high", context.get(f"swing_high_{group}", context.get("swing_high")))
        atr = context.get("hedge_atr", context.get(f"atr_{group}", context.get("atr")))
        try:
            low = float(low)
            high = float(high)
            atr = float(atr)
        except (TypeError, ValueError):
            return None, None, "NO_SWING_FOR_LOT"
        if low <= 0 or high <= 0 or atr <= 0:
            return None, None, "NO_SWING_FOR_LOT"
        sl_mult = float(getattr(config, "sl_atr_multiplier", 0.2) or 0.2)
        buffer_atr = atr * sl_mult
        return low - buffer_atr, high + buffer_atr, "OK"

    def _resolve_lot_size(self, symbol, cfg, context=None, sltp=None):
        base_lot = max(0.01, float(cfg.get("FIXED_LOT", 0.1) or 0.1))
        max_cap = float(cfg.get("MAX_LOT_CAP", 0.0) or 0.0)
        lot_mode = str(cfg.get("LOT_MODE", "FIXED") or "FIXED").upper()
        if lot_mode not in {"RISK_PERCENT", "ACCOUNT_RISK"}:
            return self._normalize_lot(symbol, base_lot, max_cap), {"LOT_MODE": "FIXED"}

        if not self.connector or not hasattr(self.connector, "calculate_lot_size"):
            return 0.0, {"LOT_MODE": "ACCOUNT_RISK", "reason": "NO_LOT_CONNECTOR"}
        price = float((context or {}).get("hedge_current_price", (context or {}).get("current_price", 0.0)) or 0.0)
        buy_sl = (sltp or {}).get("BUY", {}).get("sl", 0.0)
        sell_sl = (sltp or {}).get("SELL", {}).get("sl", 0.0)
        if not buy_sl or not sell_sl:
            buy_sl, sell_sl, reason = self._virtual_sl_prices_for_lot(symbol, cfg, context or {})
            if reason != "OK":
                return 0.0, {"LOT_MODE": "ACCOUNT_RISK", "reason": reason}
        if price > 0 and (abs(price - float(buy_sl)) <= 0 or abs(price - float(sell_sl)) <= 0):
            return 0.0, {"LOT_MODE": "ACCOUNT_RISK", "reason": "INVALID_RISK_SL"}
        account_value = self._account_base_value(cfg)
        risk_pct = max(0.0, float(cfg.get("RISK_PERCENT_PER_PAIR", 0.0) or 0.0))
        target_risk_usd = account_value * risk_pct / 100.0
        if account_value <= 0 or target_risk_usd <= 0:
            return 0.0, {"LOT_MODE": "ACCOUNT_RISK", "reason": "INVALID_ACCOUNT_RISK"}
        buy_order_type = getattr(mt5, "ORDER_TYPE_BUY", 0)
        sell_order_type = getattr(mt5, "ORDER_TYPE_SELL", 1)
        buy_lot, safe_buy_sl = self.connector.calculate_lot_size(
            symbol, target_risk_usd, buy_sl, buy_order_type, 0.0
        )
        sell_lot, safe_sell_sl = self.connector.calculate_lot_size(
            symbol, target_risk_usd, sell_sl, sell_order_type, 0.0
        )
        if not buy_lot or not sell_lot:
            return 0.0, {"LOT_MODE": "ACCOUNT_RISK", "reason": "LOT_CALC_FAILED"}
        raw_lot = min(float(buy_lot), float(sell_lot))
        lot = self._normalize_lot(symbol, raw_lot, max_cap)
        return lot, {
            "LOT_MODE": "ACCOUNT_RISK",
            "ACCOUNT_RISK_USD": target_risk_usd,
            "BUY_SIZE_SL": safe_buy_sl or buy_sl,
            "SELL_SIZE_SL": safe_sell_sl or sell_sl,
            "LOT_CAP_APPLIED": max_cap > 0 and raw_lot > lot + 1e-9,
        }

    def _manage_session(self, symbol, session, settings, state, context=None):
        if session.get("status") == "STOP_NEW":
            return []
        positions = {int(p.ticket): p for p in self._hedge_positions(symbol)}
        main_tickets = [int(t) for t in (session.get("buy_ticket"), session.get("sell_ticket")) if t]
        session_positions = [positions[t] for t in main_tickets if t in positions]
        if not session_positions:
            state.setdefault("last_close_times", {})[symbol] = time.time()
            state.get("active_sessions", {}).pop(symbol, None)
            self._record_decision(state, symbol, session, "CLOSE", "SESSION_DONE")
            return ["HEDGE_CLOSE|SESSION_DONE"]

        pnl = sum(self._pos_pnl(p) for p in session_positions) + float(session.get("closed_leg_pnl", 0.0) or 0.0)
        session["mfe"] = max(float(session.get("mfe", 0.0) or 0.0), pnl)
        session["mae"] = min(float(session.get("mae", 0.0) or 0.0), pnl)
        session["updated_at"] = time.time()

        actions = []
        session_tp = float(settings.get("HEDGE_SESSION_TP_USD", 0.0) or 0.0)
        session_sl = float(settings.get("HEDGE_SESSION_SL_USD", 0.0) or 0.0)
        max_hold_min = float(settings.get("HEDGE_MAX_HOLD_MINUTES", 0.0) or 0.0)
        age_min = (time.time() - float(session.get("created_at", time.time()) or time.time())) / 60.0
        close_reason = None
        if session_tp > 0 and pnl >= abs(session_tp):
            close_reason = "SESSION_TP"
        elif session_sl > 0 and pnl <= -abs(session_sl):
            close_reason = "SESSION_SL"
        elif max_hold_min > 0 and age_min >= max_hold_min:
            close_reason = "SESSION_TIMEOUT"
        if close_reason:
            actions.extend(self._close_session_positions(symbol, session, session_positions, close_reason, state, settings))
            return actions

        survivor_active = len(session_positions) == 1 and len(main_tickets) >= 2
        if survivor_active:
            survivor = session_positions[0]
            survivor_ticket = str(getattr(survivor, "ticket", ""))
            if session.get("survivor_armed_ticket") != survivor_ticket:
                session["survivor_armed_ticket"] = survivor_ticket
                session["survivor_armed_at"] = time.time()
                self.log(f"SURVIVOR_ARMED {symbol} #{survivor_ticket}")
            action = self._protect_survivor(symbol, session, survivor, settings)
            if action:
                actions.append(action)

        if survivor_active and bool(session.get("use_tsl", settings.get("USE_TSL", True))):
            for pos in session_positions:
                action = self._apply_hedge_tsl(symbol, session, pos, settings, state, context or {})
                if action:
                    actions.append(f"HEDGE_TSL|{action}")
                    self.log(f"TSL {symbol}: {action}")

        self._record_decision(state, symbol, session, "WAIT", "DUAL_HOLD", pnl=pnl)
        return actions

    def _protect_survivor(self, symbol, session, pos, settings):
        mode = str(session.get("survivor_protect", settings.get("SURVIVOR_PROTECT", "BE_FEE")) or "BE_FEE").upper()
        if mode in {"OFF", "NONE"} or session.setdefault("survivor_protected", {}).get(str(pos.ticket)):
            return None
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if not info or not tick or not self.connector:
            return None
        point = float(getattr(info, "point", 0.00001) or 0.00001)
        contract_size = float(getattr(info, "trade_contract_size", 1.0) or 1.0)
        stop_dist = float(getattr(info, "trade_stops_level", 0) or 0) * point
        is_buy = pos.type == mt5.ORDER_TYPE_BUY
        current_price = float(getattr(pos, "price_current", 0.0) or (tick.bid if is_buy else tick.ask) or 0.0)
        current_sl = float(getattr(pos, "sl", 0.0) or 0.0)
        fee_usd = 0.0
        if mode == "BE_FEE":
            fee_usd = abs(float(getattr(pos, "commission", 0.0) or 0.0)) + abs(float(getattr(pos, "swap", 0.0) or 0.0))
            fee_usd += float(getattr(info, "spread", 0.0) or 0.0) * point * float(pos.volume) * contract_size
        fee_dist = fee_usd / (float(pos.volume) * contract_size) if pos.volume and contract_size > 0 else 0.0
        target_sl = float(pos.price_open) + fee_dist if is_buy else float(pos.price_open) - fee_dist
        target_sl = round(target_sl / point) * point
        valid = (
            is_buy
            and target_sl > current_sl + point / 2
            and target_sl <= current_price - stop_dist
        ) or (
            not is_buy
            and (current_sl == 0 or target_sl < current_sl - point / 2)
            and target_sl >= current_price + stop_dist
        )
        if not valid:
            return None
        result = self.connector.modify_position(pos.ticket, target_sl, pos.tp)
        session.setdefault("survivor_protected", {})[str(pos.ticket)] = {
            "mode": mode,
            "sl": target_sl,
            "time": time.time(),
        }
        return f"HEDGE_SURVIVOR_{mode}|{getattr(pos, 'ticket', '')}|SL={target_sl:.5f}|ret={getattr(result, 'retcode', 'NA')}"

    def _apply_hedge_tsl(self, symbol, session, pos, settings, state, context):
        modes = str(settings.get("HEDGE_TSL_MODE", "BE+STEP_R+SWING") or "OFF").upper()
        if modes in {"", "OFF", "NONE"}:
            return None
        return self._apply_tsl_modes(symbol, session, pos, modes, state, context)

    def _apply_tsl_modes(self, symbol, session, pos, mode, state, context):
        mode = str(mode or "OFF").upper()
        if mode in {"", "OFF", "NONE"}:
            return None
        active_modes = [m.strip() for m in mode.replace(",", "+").split("+") if m.strip()]
        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            return None
        point = float(getattr(sym_info, "point", 0.00001) or 0.00001)
        contract_size = float(getattr(sym_info, "trade_contract_size", 1.0) or 1.0)
        is_buy = pos.type == mt5.ORDER_TYPE_BUY
        current_price = float(getattr(pos, "price_current", 0.0) or 0.0)
        current_sl = float(getattr(pos, "sl", 0.0) or 0.0)
        profit_usd = self._pos_pnl(pos)
        ticket_key = str(getattr(pos, "ticket", ""))
        one_r_dist = float((session.get("initial_r_dist") or {}).get(ticket_key, 0.0) or 0.0)
        if one_r_dist <= 0 and current_sl > 0:
            one_r_dist = abs(float(pos.price_open) - current_sl)
        if one_r_dist <= 0:
            one_r_dist = point
        risk_usd = float((session.get("initial_r_usd") or {}).get(ticket_key, 0.0) or 0.0)
        if risk_usd <= 0 and pos.volume and contract_size > 0:
            risk_usd = one_r_dist * float(pos.volume) * contract_size
        curr_dist = current_price - pos.price_open if is_buy else pos.price_open - current_price
        curr_r = curr_dist / one_r_dist
        curr_cash_r = profit_usd / risk_usd if risk_usd > 0 else curr_r
        brain = self._get_brain_settings_for_tsl(symbol)
        tsl_cfg = brain.get("TSL_CONFIG", getattr(config, "TSL_CONFIG", {}))
        candidates = []

        if "BE" in active_modes:
            trig_r = float(tsl_cfg.get("BE_OFFSET_RR", 0.8) or 0.8)
            if curr_r >= trig_r:
                offset = float(tsl_cfg.get("BE_OFFSET_POINTS", 0) or 0) * point
                candidates.append((pos.price_open + offset if is_buy else pos.price_open - offset, "BE"))

        if "BE_CASH" in active_modes:
            trigger_val = float(tsl_cfg.get("BE_TRIGGER", 10.0) or 10.0)
            step_val = float(tsl_cfg.get("BE_VALUE", 20.0) or 20.0)
            be_type = str(tsl_cfg.get("BE_CASH_TYPE", "USD") or "USD").upper()
            acc = self.connector.get_account_info() if self.connector else None
            bal = float(acc.get("balance", 1000.0) if acc else 1000.0)
            if be_type == "R":
                trigger_usd = risk_usd * trigger_val
                step_usd = risk_usd * step_val
            elif be_type == "PERCENT":
                trigger_usd = bal * trigger_val / 100.0
                step_usd = bal * step_val / 100.0
            elif be_type == "POINT":
                trigger_usd = trigger_val * point * pos.volume * contract_size
                step_usd = step_val * point * pos.volume * contract_size
            else:
                trigger_usd = trigger_val
                step_usd = step_val
            if trigger_usd > 0 and profit_usd >= trigger_usd:
                extra_profit = profit_usd - trigger_usd
                steps = math.floor(extra_profit / step_usd) if step_usd > 0 else 0
                locked_profit = 0.0 if steps <= 0 else trigger_usd + max(0, steps - 1) * step_usd
                if str(tsl_cfg.get("BE_CASH_STRAT", "")).startswith("LOCK"):
                    locked_profit = trigger_usd + steps * step_usd
                total_fee = 0.0
                if bool(tsl_cfg.get("BE_CASH_FEE_PROTECT", True)):
                    total_fee = abs(float(getattr(pos, "commission", 0.0) or 0.0)) + (
                        float(getattr(sym_info, "spread", 0.0) or 0.0) * point * pos.volume * contract_size
                    )
                lock_dist = (locked_profit + total_fee) / (pos.volume * contract_size)
                candidates.append((pos.price_open + lock_dist if is_buy else pos.price_open - lock_dist, "BE_CASH"))

        if "STEP_R" in active_modes:
            sz = float(tsl_cfg.get("STEP_R_SIZE", 1.0) or 1.0)
            rt = float(tsl_cfg.get("STEP_R_RATIO", 0.8) or 0.8)
            steps = math.floor(curr_r / sz) if sz > 0 else 0
            if steps >= 1:
                dist = steps * one_r_dist * rt
                candidates.append((pos.price_open + dist if is_buy else pos.price_open - dist, f"STEP_R:{steps}"))

        if "PNL" in active_modes:
            acc = self.connector.get_account_info() if self.connector else None
            if acc:
                pnl_pct = profit_usd / float(acc.get("balance", 1.0) or 1.0) * 100
                for lvl in sorted(tsl_cfg.get("PNL_LEVELS", []), key=lambda x: x[0]):
                    if pnl_pct >= float(lvl[0]):
                        lock_usd = float(acc.get("balance", 1.0) or 1.0) * float(lvl[1]) / 100.0
                        lock_dist = lock_usd / (pos.volume * contract_size)
                        candidates.append((pos.price_open + lock_dist if is_buy else pos.price_open - lock_dist, f"PNL:{lvl[1]}%"))

        if "SWING" in active_modes:
            group = str(tsl_cfg.get("SWING_GROUP", "G2") or "G2")
            if "DYNAMIC" in group:
                group = "G1" if context.get("market_mode") in ["TREND", "BREAKOUT"] else "G2"
            sh = context.get(f"swing_high_{group}")
            sl = context.get(f"swing_low_{group}")
            atr = context.get(f"atr_{group}", 0)
            if sh is not None and sl is not None and atr:
                trail_buf = float(brain.get("risk_tsl", {}).get("sl_atr_multiplier", getattr(config, "sl_atr_multiplier", 0.2)))
                tsl_mode = brain.get("TSL_LOGIC_MODE", tsl_cfg.get("TSL_LOGIC_MODE", "STATIC"))
                is_trending = context.get("market_mode", "TREND") in ["TREND", "BREAKOUT"]
                if is_buy:
                    price = float(sl) - trail_buf * float(atr) if tsl_mode == "STATIC" else float(sh) - trail_buf * float(atr)
                    if tsl_mode == "DYNAMIC":
                        price = (float(sl) if is_trending else float(sh)) - trail_buf * float(atr)
                else:
                    price = float(sh) + trail_buf * float(atr) if tsl_mode == "STATIC" else float(sl) + trail_buf * float(atr)
                    if tsl_mode == "DYNAMIC":
                        price = (float(sh) if is_trending else float(sl)) + trail_buf * float(atr)
                candidates.append((price, "SWING"))

        if "PSAR_TRAIL" in active_modes:
            min_rr = float(tsl_cfg.get("PSAR_MIN_RR", 0.0) or 0.0)
            if curr_cash_r >= min_rr:
                group = str(tsl_cfg.get("PSAR_GROUP", "G2") or "G2")
                if "DYNAMIC" in group:
                    group = "G1" if context.get("market_mode") in ["TREND", "BREAKOUT"] else "G2"
                psar_val = context.get(f"psar_{group}")
                if psar_val:
                    candidates.append((float(psar_val), "PSAR"))

        valid = []
        min_stop_dist = float(getattr(sym_info, "trade_stops_level", 0) or 0) * point
        for price, rule in candidates:
            if not price:
                continue
            price = round(float(price) / point) * point
            if is_buy and price > current_sl + point / 2 and price <= current_price - min_stop_dist:
                valid.append((price, rule))
            if not is_buy and (current_sl == 0 or price < current_sl - point / 2) and price >= current_price + min_stop_dist:
                valid.append((price, rule))
        if not valid:
            return None
        target_sl, rule = max(valid, key=lambda x: x[0]) if is_buy else min(valid, key=lambda x: x[0])
        result = self.connector.modify_position(pos.ticket, target_sl, pos.tp) if self.connector else None
        session.setdefault("hedge_tsl_rules", {})[str(pos.ticket)] = rule
        session["hedge_tsl_mode"] = mode
        return f"TSL_{rule}->{target_sl:.5f}"

    def _get_brain_settings_for_tsl(self, symbol):
        try:
            from core.storage_manager import get_brain_settings_for_symbol

            return get_brain_settings_for_symbol(symbol)
        except Exception:
            return {"TSL_CONFIG": getattr(config, "TSL_CONFIG", {}), "risk_tsl": {}}

    def _close_session_positions(self, symbol, session, positions, reason, state, settings=None):
        settings = settings or {}
        actions = []
        total_pnl = sum(self._pos_pnl(p) for p in positions) + float(session.get("closed_leg_pnl", 0.0) or 0.0)
        for pos in positions:
            actions.append(self.executor.close_position(pos, reason))
        state.setdefault("last_close_times", {})[symbol] = time.time()
        if total_pnl < 0:
            state.setdefault("last_loss_times", {})[symbol] = time.time()
            state["consecutive_losses"] = int(state.get("consecutive_losses", 0) or 0) + 1
            max_losses = int(settings.get("MAX_CONSECUTIVE_LOSSES", 0) or 0)
            if max_losses > 0 and state["consecutive_losses"] >= max_losses:
                state["global_cooldown_until"] = time.time() + float(settings.get("GLOBAL_COOLDOWN_SECONDS", 3600) or 3600)
        else:
            state["consecutive_losses"] = 0
        session["status"] = "CLOSED"
        state.get("active_sessions", {}).pop(symbol, None)
        self._record_decision(state, symbol, session, "CLOSE", reason, pnl=total_pnl)
        return actions

    def _record_decision(self, state, symbol, session, status, reason, gate=None, **extra):
        decision = {
            "status": status,
            "reason": reason,
            "symbol": symbol,
            "tactic": (session or {}).get("tactic", "DUAL") if isinstance(session, dict) else "DUAL",
            "source": (session or {}).get("source", "MANUAL") if isinstance(session, dict) else "MANUAL",
            "time": time.time(),
        }
        if gate:
            decision["gate"] = gate
        decision.update(extra)
        state.setdefault("last_decision", {})[symbol] = decision
        reason_key = str(reason or "").split(":", 1)[0]
        log_key = f"{symbol}|{status}|{reason_key}|{decision.get('tactic')}|{decision.get('source')}"
        last_logs = state.setdefault("last_decision_log_keys", {})
        prev = self._decision_log_cache.get(symbol) or last_logs.get(symbol, {})
        now = time.time()
        try:
            cfg = load_hedge_settings()
            repeat_cooldown = float(cfg.get("HEDGE_LOG_COOLDOWN_SECONDS", 300) or 300)
        except Exception:
            repeat_cooldown = 300.0
        if status in {"OPEN", "CLOSE"}:
            repeat_cooldown = 0.0
        if prev.get("key") != log_key or now - float(prev.get("time", 0) or 0) >= repeat_cooldown or status in {"OPEN", "CLOSE"}:
            parts = [symbol, f"status={status}", f"reason={reason}", f"tactic={decision.get('tactic')}", f"source={decision.get('source')}"]
            if "pnl" in extra:
                parts.append(f"pnl={float(extra['pnl']):+.2f}")
            self.log("DECISION " + " ".join(parts))
            cache_item = {"key": log_key, "time": now}
            self._decision_log_cache[symbol] = cache_item
            last_logs[symbol] = cache_item

    def _sync_hedge_history(self, state):
        current_tickets = {int(p.ticket) for p in self._hedge_positions()}
        previous_tickets = {int(t) for t in state.get("hedge_active_tickets", []) if str(t).isdigit()}
        closed_tickets = previous_tickets - current_tickets
        for ticket in closed_tickets:
            try:
                deals = mt5.history_deals_get(position=ticket)
                if not deals:
                    continue
                deal_out = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
                if not deal_out:
                    continue
                d_out = deal_out[0]
                deal_in = [d for d in deals if d.entry == mt5.DEAL_ENTRY_IN]
                d_in = deal_in[0] if deal_in else None
                real_pnl = d_out.profit + d_out.commission + d_out.swap
                for session in (state.get("active_sessions") or {}).values():
                    if not isinstance(session, dict):
                        continue
                    session_tickets = {
                        str(session.get("buy_ticket")),
                        str(session.get("sell_ticket")),
                    }
                    if str(ticket) in session_tickets and str(ticket) not in session.setdefault("closed_legs", {}):
                        session["closed_leg_pnl"] = float(session.get("closed_leg_pnl", 0.0) or 0.0) + real_pnl
                        session["closed_legs"][str(ticket)] = real_pnl
                        break
                pos_type = "BUY" if d_out.type == mt5.DEAL_TYPE_SELL else "SELL"
                open_time_str = datetime.fromtimestamp(d_in.time).strftime("%Y-%m-%d %H:%M:%S") if d_in else ""
                append_trade_log(
                    ticket,
                    d_out.symbol,
                    pos_type,
                    d_out.volume,
                    d_in.price if d_in else 0.0,
                    0.0,
                    0.0,
                    -(abs(d_out.commission) + abs(d_out.swap)),
                    real_pnl,
                    "HEDGE_Close",
                    market_mode="HEDGE",
                    trigger_signal=d_in.comment if d_in else "HEDGE",
                    session_id="HEDGE",
                    open_time_str=open_time_str,
                    mae_usd=min(real_pnl, 0.0),
                    mfe_usd=max(real_pnl, 0.0),
                )
                state["hedge_pnl_today"] = float(state.get("hedge_pnl_today", 0.0) or 0.0) + real_pnl
                if real_pnl < 0:
                    state["hedge_daily_loss_count"] = int(state.get("hedge_daily_loss_count", 0) or 0) + 1
                self.log(f"Closed {pos_type} {d_out.symbol} #{ticket} PnL={real_pnl:+.2f}")
            except Exception as e:
                self.log(f"History sync failed for #{ticket}: {e}", error=True)
        state["hedge_active_tickets"] = sorted(current_tickets)
