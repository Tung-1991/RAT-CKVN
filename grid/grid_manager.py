# -*- coding: utf-8 -*-
"""GRID V1 manager.

Runs isolated GRID symbol-sessions using market orders. It reuses existing
market context, connector, market-hours and signal output, but never writes to
BOT tactic/basket state.
"""

import time
from datetime import datetime

import MetaTrader5 as mt5

from core.market_hours import is_symbol_trade_window_open
from core.position_classifier import is_grid_position
from core.storage_manager import append_trade_log, get_magic_numbers

from .grid_config import GRID_COMMENT_PREFIX
from .grid_executor import GridExecutor
from .grid_storage import load_grid_settings, load_grid_state, save_grid_settings, save_grid_state


class GridManager:
    def __init__(self, connector=None, data_engine=None, signal_generator=None, log_callback=None):
        self.connector = connector
        self.data_engine = data_engine
        self.signal_generator = signal_generator
        self.log_callback = log_callback
        self.executor = GridExecutor(connector=connector, log_callback=log_callback)
        self._decision_log_cache = {}

    def log(self, message, error=False):
        if self.log_callback:
            self.log_callback(f"[GRID] {message}", error=error, target="grid")

    def reload(self):
        return {"settings": load_grid_settings(), "state": load_grid_state()}

    def _ensure_grid_state(self, state):
        today = datetime.now().strftime("%Y-%m-%d")
        if state.get("date") != today:
            state["date"] = today
            state["grid_pnl_today"] = 0.0
            state["grid_trades_today"] = 0
            state["grid_daily_loss_count"] = 0
        state.setdefault("grid_pnl_today", 0.0)
        state.setdefault("grid_trades_today", 0)
        state.setdefault("grid_daily_loss_count", 0)
        state.setdefault("last_decision", {})
        state.setdefault("last_decision_log_keys", {})
        state.pop("cooldown_until", None)

    def clear_session_block(self, symbol=None):
        state = load_grid_state()
        self._ensure_grid_state(state)
        sessions = state.setdefault("active_sessions", {})
        for sym, session in list(sessions.items()):
            if symbol and sym != symbol:
                continue
            if isinstance(session, dict):
                if session.get("status") == "STOP_NEW":
                    session["status"] = "ACTIVE"
                session.pop("stop_reason", None)
                session.pop("last_block_reason", None)
                session["updated_at"] = time.time()
        if symbol:
            state.get("last_decision", {}).pop(symbol, None)
        else:
            state["last_decision"] = {}
        save_grid_state(state)
        return "SUCCESS"

    def stop_session(self, symbol=None):
        state = load_grid_state()
        self._ensure_grid_state(state)
        changed = 0
        for sym, session in list(state.setdefault("active_sessions", {}).items()):
            if symbol and sym != symbol:
                continue
            if isinstance(session, dict):
                session["status"] = "STOP_NEW"
                session["stop_reason"] = "USER_STOP_SESSION"
                session["last_block_reason"] = "USER_STOP_SESSION"
                session["updated_at"] = time.time()
                changed += 1
        save_grid_state(state)
        return f"SUCCESS|{changed}"

    def rebuild_session_range(self, symbol, context=None):
        settings = load_grid_settings()
        state = load_grid_state()
        self._ensure_grid_state(state)
        context = context or {}
        if not context and self.data_engine:
            try:
                _, context = self.data_engine.fetch_data_v4(symbol)
            except Exception:
                context = {}
        context = self._prepare_grid_context(symbol, context or {}, settings)
        price = float((context or {}).get("current_price", 0.0) or 0.0)
        boundary = self._resolve_rebuilt_boundary(symbol, context or {}, settings, price)
        spacing = self._resolve_spacing(context or {}, settings, boundary)
        if not boundary or not spacing or price <= 0:
            state.setdefault("last_decision", {})[symbol] = {
                "status": "BLOCK",
                "reason": "REBUILD_FAILED",
                "symbol": symbol,
                "mode": settings.get("DEFAULT_MANUAL_MODE", "NEUTRAL"),
                "source": "GRID_CONTROL",
                "time": time.time(),
            }
            save_grid_state(state)
            return "FAILED|REBUILD_FAILED"

        session = self._ensure_session(
            state,
            symbol,
            settings,
            settings.get("DEFAULT_MANUAL_MODE", "NEUTRAL"),
            "AUTO",
            False,
            context or {},
        )
        session["boundary"] = boundary
        session["spacing"] = spacing
        session["status"] = "ACTIVE"
        session.pop("stop_reason", None)
        session.pop("last_block_reason", None)
        session["updated_at"] = time.time()
        state.setdefault("last_preview", {})[symbol] = {
            "permission": True,
            "mode": session.get("mode", "NEUTRAL"),
            "reason": "REBUILD_RANGE",
            "boundary": boundary,
            "spacing": spacing,
            "price": price,
        }
        self._record_decision(state, symbol, session, "WAIT", "REBUILD_RANGE", settings=settings, price=price, boundary=boundary, spacing=spacing)
        save_grid_state(state)
        return "SUCCESS|REBUILD_RANGE"

    def start_manual_session(self, symbol, mode="NEUTRAL", bypass_signal=False, context=None):
        settings = load_grid_settings()

        mode = str(mode or "NEUTRAL").upper()
        if mode not in {"NEUTRAL", "LONG", "SHORT"}:
            mode = settings.get("DEFAULT_MANUAL_MODE", "NEUTRAL")

        state = load_grid_state()
        self._ensure_grid_state(state)
        session = self._ensure_session(state, symbol, settings, mode, "MANUAL", bypass_signal, context or {})
        save_grid_state(state)
        self.log(f"Manual session {symbol} mode={session['mode']} bypass_signal={bool(bypass_signal)}")
        return f"SUCCESS|{session['session_id']}"

    def scan(self, symbols=None, contexts=None):
        settings = load_grid_settings()
        state = load_grid_state()
        self._ensure_grid_state(state)

        contexts = contexts or {}
        watchlist = settings.get("WATCHLIST") or symbols or []
        actions = []

        if settings.get("ENABLED", False) and settings.get("DYNAMIC_MODE_ENABLED", True):
            for symbol in watchlist:
                ctx = contexts.get(symbol, {})
                if not ctx and self.data_engine:
                    try:
                        _, ctx = self.data_engine.fetch_data_v4(symbol)
                        contexts[symbol] = ctx or {}
                    except Exception:
                        ctx = {}
                ctx = self._prepare_grid_context(symbol, ctx, settings)
                contexts[symbol] = ctx
                gate = self._evaluate_gate(symbol, ctx, settings, bypass_signal=False)
                if gate["permission"]:
                    self._ensure_session(state, symbol, settings, gate["mode"], "AUTO", False, ctx)
                else:
                    self._mark_stop_new(state, symbol, gate["reason"])

        active = state.get("active_sessions", {})
        for symbol, session in list(active.items()):
            ctx = contexts.get(symbol, {})
            if not ctx and self.data_engine:
                try:
                    _, ctx = self.data_engine.fetch_data_v4(symbol)
                except Exception:
                    ctx = {}
            ctx = self._prepare_grid_context(symbol, ctx or {}, settings)
            result = self._scan_session(symbol, session, ctx or {}, settings, state)
            if result:
                actions.extend(result)

        self._sync_grid_history(state)
        save_grid_state(state)
        return {"status": "OK", "actions": actions}

    def _ensure_session(self, state, symbol, settings, mode, source, bypass_signal, context):
        sessions = state.setdefault("active_sessions", {})
        session = sessions.get(symbol)
        now = time.time()
        if not isinstance(session, dict):
            session = {
                "session_id": f"GRID_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "symbol": symbol,
                "mode": mode,
                "source": source,
                "status": "ACTIVE",
                "created_at": now,
                "updated_at": now,
                "bypass_signal": bool(bypass_signal),
                "opened_orders": [],
            }
            sessions[symbol] = session
        else:
            session.update({
                "mode": mode,
                "source": source,
                "updated_at": now,
                "bypass_signal": bool(bypass_signal),
            })
            if source == "MANUAL" or session.get("status") != "STOP_NEW":
                session["status"] = "ACTIVE"

        boundary = self._resolve_boundary(symbol, context, settings)
        spacing = self._resolve_spacing(context, settings, boundary)
        session["boundary"] = boundary
        session["spacing"] = spacing
        return session

    def _mark_stop_new(self, state, symbol, reason):
        session = state.get("active_sessions", {}).get(symbol)
        if isinstance(session, dict) and session.get("status") == "ACTIVE":
            session["status"] = "STOP_NEW"
            session["stop_reason"] = reason
            session["updated_at"] = time.time()

    def _evaluate_gate(self, symbol, context, settings, bypass_signal=False):
        if bypass_signal:
            mode = settings.get("DEFAULT_MANUAL_MODE", "NEUTRAL")
            return {"permission": True, "mode": mode, "reason": "BYPASS_SIGNAL"}

        signal_source = str(settings.get("GRID_SIGNAL_SOURCE", "OFF") or "OFF").upper()
        market_mode = context.get("grid_market_mode", context.get("market_mode", "ANY"))
        if settings.get("STOP_ON_BREAKOUT", True) and market_mode in settings.get("STOP_NEW_MARKET_MODES", ["TREND", "BREAKOUT"]):
            return {"permission": False, "mode": "BLOCK", "reason": f"MARKET_MODE_{market_mode}"}

        if signal_source == "OFF":
            mode = str(settings.get("DEFAULT_MANUAL_MODE", "NEUTRAL") or "NEUTRAL").upper()
        else:
            signal_key = "grid_latest_signal" if signal_source == "IMPORTED" else "latest_signal"
            signal = int(context.get(signal_key, 0) or 0)
            if signal == 1:
                mode = "LONG"
            elif signal == -1:
                mode = "SHORT"
            else:
                none_policy = settings.get("NONE_POLICY", "NEUTRAL")
                if none_policy == "BLOCK":
                    return {"permission": False, "mode": "BLOCK", "reason": "SIGNAL_NONE"}
                mode = "NEUTRAL"

        boundary = self._resolve_boundary(symbol, context, settings)
        spacing = self._resolve_spacing(context, settings, boundary)
        price = float(context.get("current_price", 0.0) or 0.0)
        if not boundary or not spacing or price <= 0:
            return {"permission": False, "mode": "BLOCK", "reason": "NO_BOUNDARY_OR_SPACING"}
        if not (boundary["lower"] < price < boundary["upper"]):
            if str(settings.get("OUT_OF_RANGE_POLICY", "STOP") or "STOP").upper() == "AUTO_REBUILD":
                rebuilt = self._resolve_rebuilt_boundary(symbol, context, settings, price, spacing)
                rebuilt_spacing = self._resolve_spacing(context, settings, rebuilt)
                if rebuilt and rebuilt_spacing and rebuilt["lower"] < price < rebuilt["upper"]:
                    return {
                        "permission": True,
                        "mode": mode,
                        "reason": "AUTO_REBUILD_RANGE",
                        "boundary": rebuilt,
                        "spacing": rebuilt_spacing,
                    }
            return {"permission": False, "mode": "BLOCK", "reason": "PRICE_OUT_OF_BOUNDARY"}
        return {"permission": True, "mode": mode, "reason": "OK"}

    def _prepare_grid_context(self, symbol, context, settings):
        signal_source = str(settings.get("GRID_SIGNAL_SOURCE", "OFF") or "OFF").upper()
        if signal_source != "IMPORTED":
            return context
        cfg = settings.get("GRID_SIGNAL_CONFIG") or {}
        if not cfg or not self.data_engine or not self.signal_generator:
            return context
        try:
            dfs, fresh_context = self.data_engine.fetch_data_v4(symbol)
            if dfs is None or fresh_context is None:
                return context
            grid_context = dict(fresh_context)
            inds_config = cfg.get("indicators", {})
            voting_rules = cfg.get("voting_rules", {})
            eval_mode = cfg.get("MASTER_EVAL_MODE", "VETO") or "VETO"
            min_votes = int(cfg.get("MIN_MATCHING_VOTES", 3) or 3)

            current_mode, mode_src, macro_dir = self.signal_generator._detect_market_mode(
                dfs, grid_context, inds_config, voting_rules, symbol
            )
            grid_context["grid_market_mode"] = current_mode
            grid_context["grid_mode_source"] = mode_src
            grid_context["grid_macro_direction"] = macro_dir

            active_inds_by_group = {"G0": {}, "G1": {}, "G2": {}, "G3": {}}
            for name, ind_cfg in inds_config.items():
                if ind_cfg.get("active", False):
                    modes = ind_cfg.get("active_modes", ["ANY"])
                    if "ANY" in modes or current_mode in modes:
                        for grp in ind_cfg.get("groups", [ind_cfg.get("group", "G2")]):
                            if grp in active_inds_by_group:
                                active_inds_by_group[grp][name] = ind_cfg

            grid_context["grid_latest_signal"] = self.signal_generator._evaluate_pipeline_v4(
                dfs,
                grid_context,
                current_mode,
                voting_rules,
                active_inds_by_group,
                eval_mode,
                min_votes,
            )
            context.update(grid_context)
        except Exception as e:
            self.log(f"GRID signal eval fallback for {symbol}: {e}", error=True)
        return context

    def _resolve_boundary(self, symbol, context, settings):
        mode = settings.get("BOUNDARY_MODE", "HYBRID")
        manual_upper = float(settings.get("MANUAL_UPPER_BOUNDARY", 0.0) or 0.0)
        manual_lower = float(settings.get("MANUAL_LOWER_BOUNDARY", 0.0) or 0.0)
        if mode in {"MANUAL", "HYBRID"} and manual_upper > manual_lower > 0:
            return {"upper": manual_upper, "lower": manual_lower, "source": "MANUAL"}

        group = settings.get("GRID_TIMEFRAME_GROUP", "G2")
        upper = context.get(f"swing_high_{group}", context.get("swing_high"))
        lower = context.get(f"swing_low_{group}", context.get("swing_low"))
        try:
            upper = float(upper)
            lower = float(lower)
        except (TypeError, ValueError):
            return None
        if upper <= lower:
            return None
        return {"upper": upper, "lower": lower, "source": f"SWING_{group}"}

    def _resolve_spacing(self, context, settings, boundary=None):
        grid_type = str(settings.get("GRID_TYPE", "ATR_DYNAMIC") or "ATR_DYNAMIC").upper()
        if grid_type == "ARITHMETIC":
            if not boundary:
                return 0.0
            grid_count = int(settings.get("GRID_COUNT", 10) or 10)
            price_range = float(boundary["upper"]) - float(boundary["lower"])
            return price_range / grid_count if price_range > 0 and grid_count > 0 else 0.0

        if grid_type == "GEOMETRIC":
            price = float(context.get("current_price", 0.0) or 0.0)
            step_pct = float(settings.get("GEOMETRIC_STEP_PERCENT", 1.0) or 1.0)
            return price * (step_pct / 100.0) if price > 0 and step_pct > 0 else 0.0

        group = settings.get("GRID_TIMEFRAME_GROUP", "G2")
        atr = context.get(f"atr_{group}", context.get("atr"))
        try:
            atr = float(atr)
        except (TypeError, ValueError):
            return 0.0
        mult = float(settings.get("SPACING_ATR_MULTIPLIER", 1.0) or 1.0)
        return atr * mult if atr > 0 and mult > 0 else 0.0

    def _resolve_rebuilt_boundary(self, symbol, context, settings, price, spacing=None):
        price = float(price or 0.0)
        if price <= 0:
            return None
        spacing = float(spacing or 0.0)
        if spacing <= 0:
            spacing = self._resolve_spacing(context, settings, self._resolve_boundary(symbol, context, settings))
        if spacing <= 0:
            group = settings.get("GRID_TIMEFRAME_GROUP", "G2")
            try:
                atr = float(context.get(f"atr_{group}", context.get("atr")) or 0.0)
            except (TypeError, ValueError):
                atr = 0.0
            if atr > 0:
                spacing = atr * float(settings.get("SPACING_ATR_MULTIPLIER", 1.0) or 1.0)
        if spacing <= 0:
            return None
        grid_count = max(2, int(settings.get("GRID_COUNT", 10) or 10))
        half_range = spacing * grid_count / 2.0
        return {"upper": price + half_range, "lower": price - half_range, "source": "AUTO_REBUILD"}

    def _resolve_lot_size(self, symbol, settings):
        overrides = settings.get("SYMBOL_LOT_OVERRIDES") or {}
        lot = None
        if isinstance(overrides, dict):
            lot = overrides.get(symbol)
        if lot in ("", None):
            lot = settings.get("FIXED_LOT", 0.01)
        return float(lot or 0.01)

    def _hard_safety(self, symbol, settings, state):
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
            if ping_ms > int(settings.get("MAX_PING_MS", 150)):
                return False, f"PING:{ping_ms:.0f}"

        if settings.get("CHECK_SPREAD", True):
            tick = mt5.symbol_info_tick(symbol)
            info = mt5.symbol_info(symbol)
            if tick and info and info.point > 0:
                spread_points = (tick.ask - tick.bid) / info.point
                if spread_points > int(settings.get("MAX_SPREAD_POINTS", 150)):
                    return False, f"SPREAD:{spread_points:.0f}"
        return True, "OK"

    def _grid_positions(self, symbol=None):
        magics = get_magic_numbers()
        positions = self.connector.get_all_open_positions() if self.connector else []
        out = []
        for pos in positions:
            if is_grid_position(pos, magics) and (symbol is None or pos.symbol == symbol):
                out.append(pos)
        return out

    def _close_grid_positions(self, positions, reason):
        closed = 0
        if not self.connector:
            return closed
        for pos in positions:
            try:
                self.connector.close_position(pos)
                closed += 1
            except Exception as e:
                self.log(f"Close grid position #{getattr(pos, 'ticket', '?')} failed: {e}", error=True)
        if closed:
            self.log(f"CLOSE_GRID reason={reason} positions={closed}")
        return closed

    def _grid_safeguard(self, state, settings):
        max_daily_loss = float(settings.get("GRID_MAX_DAILY_LOSS", 0.0) or 0.0)
        if max_daily_loss > 0 and float(state.get("grid_pnl_today", 0.0) or 0.0) <= -abs(max_daily_loss):
            return False, "GRID_DAILY_LOSS"

        max_trades = int(settings.get("GRID_MAX_TRADES_PER_DAY", 0) or 0)
        if max_trades > 0 and int(state.get("grid_trades_today", 0) or 0) >= max_trades:
            return False, "GRID_MAX_TRADES_DAY"
        return True, "OK"

    def _record_decision(self, state, symbol, session, status, reason, settings=None, **extra):
        decision = {
            "status": status,
            "reason": reason,
            "symbol": symbol,
            "mode": session.get("mode", "NEUTRAL") if isinstance(session, dict) else "NEUTRAL",
            "source": session.get("source", "UNKNOWN") if isinstance(session, dict) else "UNKNOWN",
            "time": time.time(),
        }
        decision.update(extra)
        state.setdefault("last_decision", {})[symbol] = decision
        log_key = f"{symbol}|{status}|{reason}|{decision.get('mode')}|{decision.get('source')}|{extra.get('direction', '')}|{extra.get('level', '')}"
        last_logs = state.setdefault("last_decision_log_keys", {})
        prev = self._decision_log_cache.get(symbol) or last_logs.get(symbol, {})
        now = time.time()
        cfg = settings or {}
        repeat_cooldown = float(cfg.get("REOPEN_COOLDOWN_SECONDS", cfg.get("COOLDOWN_SECONDS", 60)) or 60)
        repeat_cooldown = max(5.0, repeat_cooldown)
        if status not in {"BLOCK", "WAIT"}:
            repeat_cooldown = 60.0
        should_log = (
            prev.get("key") != log_key
            or now - float(prev.get("time", 0) or 0) >= repeat_cooldown
            or status in {"OPEN", "CLOSE"}
        )
        if should_log:
            parts = [
                f"{symbol}",
                f"status={status}",
                f"reason={reason}",
                f"mode={decision.get('mode')}",
                f"source={decision.get('source')}",
            ]
            if "price" in extra:
                parts.append(f"price={float(extra['price']):.5f}")
            if "direction" in extra:
                parts.append(f"direction={extra['direction']}")
            if "level" in extra:
                parts.append(f"level={extra['level']}")
            if "boundary" in extra and isinstance(extra["boundary"], dict):
                parts.append(
                    f"range={float(extra['boundary'].get('lower', 0.0)):.5f}->{float(extra['boundary'].get('upper', 0.0)):.5f}"
                )
            self.log("DECISION " + " ".join(parts))
            cache_item = {"key": log_key, "time": now}
            self._decision_log_cache[symbol] = cache_item
            last_logs[symbol] = cache_item

    def _scan_session(self, symbol, session, context, settings, state):
        actions = []
        bypass = bool(session.get("bypass_signal", False))
        gate = self._evaluate_gate(symbol, context, settings, bypass_signal=bypass)
        if not gate["permission"]:
            session["status"] = "STOP_NEW"
            session["stop_reason"] = gate["reason"]
            state.setdefault("last_preview", {})[symbol] = gate
            self._record_decision(state, symbol, session, "BLOCK", gate["reason"], settings=settings)
            return actions
        if session.get("status") == "STOP_NEW" and not bypass:
            state.setdefault("last_preview", {})[symbol] = gate
            self._record_decision(state, symbol, session, "BLOCK", session.get("stop_reason", "STOP_NEW"), settings=settings)
            return actions

        safety_ok, safety_reason = self._hard_safety(symbol, settings, state)
        if not safety_ok:
            session["last_block_reason"] = safety_reason
            self._record_decision(state, symbol, session, "BLOCK", safety_reason, settings=settings)
            return actions

        guard_ok, guard_reason = self._grid_safeguard(state, settings)
        if not guard_ok:
            session["status"] = "STOP_NEW"
            session["last_block_reason"] = guard_reason
            self._record_decision(state, symbol, session, "BLOCK", guard_reason, settings=settings)
            return actions

        boundary = gate.get("boundary") or self._resolve_boundary(symbol, context, settings)
        spacing = gate.get("spacing") or self._resolve_spacing(context, settings, boundary)
        price = float(context.get("current_price", 0.0) or 0.0)
        if not boundary or not spacing or price <= 0:
            self._record_decision(state, symbol, session, "BLOCK", "NO_BOUNDARY_SPACING_OR_PRICE", settings=settings)
            return actions
        session["boundary"] = boundary
        session["spacing"] = spacing
        session["mode"] = gate["mode"] if session.get("source") == "AUTO" else session.get("mode", gate["mode"])
        state.setdefault("last_preview", {})[symbol] = {
            **gate,
            "boundary": boundary,
            "spacing": spacing,
            "price": price,
        }

        grid_positions = self._grid_positions(symbol)
        basket_pnl = sum(p.profit + p.swap + getattr(p, "commission", 0.0) for p in grid_positions)
        basket_tp = float(settings.get("BASKET_TP_USD", 0.0) or 0.0)
        basket_sl = float(settings.get("BASKET_SL_USD", 0.0) or 0.0)
        stop_price = float(settings.get("GRID_STOP_LOSS_PRICE", 0.0) or 0.0)
        take_price = float(settings.get("GRID_TAKE_PROFIT_PRICE", 0.0) or 0.0)
        close_reason = None
        if basket_tp > 0 and basket_pnl >= abs(basket_tp):
            close_reason = "BASKET_TP"
        elif basket_sl > 0 and basket_pnl <= -abs(basket_sl):
            close_reason = "BASKET_SL"
        elif stop_price > 0 and price <= stop_price:
            close_reason = "GRID_STOP_PRICE"
        elif take_price > 0 and price >= take_price:
            close_reason = "GRID_TAKE_PRICE"
        if close_reason:
            closed = self._close_grid_positions(grid_positions, close_reason)
            session["status"] = "STOP_NEW"
            session["last_block_reason"] = close_reason
            self._record_decision(state, symbol, session, "CLOSE", close_reason, settings=settings, price=price, pnl=basket_pnl, closed=closed)
            return actions

        max_orders = int(settings.get("MAX_GRID_ORDERS", 0) or 0)
        if max_orders > 0 and len(grid_positions) >= max_orders:
            session["last_block_reason"] = "MAX_GRID_ORDERS"
            self._record_decision(state, symbol, session, "BLOCK", "MAX_GRID_ORDERS", settings=settings, price=price, boundary=boundary, spacing=spacing)
            return actions

        gross_lot = sum(float(p.volume) for p in grid_positions)
        fixed_lot = self._resolve_lot_size(symbol, settings)
        max_total_lot = float(settings.get("MAX_TOTAL_LOT", 0.0) or 0.0)
        if max_total_lot > 0 and gross_lot + fixed_lot > max_total_lot:
            session["last_block_reason"] = "MAX_GROSS_LOT"
            self._record_decision(state, symbol, session, "BLOCK", "MAX_GROSS_LOT", settings=settings, price=price, boundary=boundary, spacing=spacing)
            return actions

        max_dd = float(settings.get("MAX_BASKET_DRAWDOWN", 0.0) or 0.0)
        if max_dd > 0:
            if basket_pnl <= -abs(max_dd):
                session["status"] = "STOP_NEW"
                session["last_block_reason"] = "MAX_SESSION_DD"
                self._record_decision(state, symbol, session, "BLOCK", "MAX_SESSION_DD", settings=settings, price=price, boundary=boundary, spacing=spacing, pnl=basket_pnl)
                return actions

        level = self._level_for_price(price, boundary, spacing)
        direction = self._direction_for_level(price, boundary, session.get("mode", "NEUTRAL"))
        if not direction:
            self._record_decision(state, symbol, session, "WAIT", "NO_DIRECTION_FOR_MODE", settings=settings, price=price, boundary=boundary, spacing=spacing, level=level)
            return actions

        level_id = f"{direction}_{level}"
        key = f"{symbol}|{level_id}"
        now = time.time()
        last_action = state.setdefault("last_grid_action_times", {}).get(key, 0)
        cooldown = float(settings.get("REOPEN_COOLDOWN_SECONDS", settings.get("COOLDOWN_SECONDS", 60)) or 0)
        if now - float(last_action or 0) < cooldown:
            self._record_decision(state, symbol, session, "WAIT", "LEVEL_COOLDOWN", settings=settings, price=price, direction=direction, level=level, cooldown=cooldown)
            return actions

        # Reserve the level before sending the order so fast daemon/manual scans
        # cannot submit the same level twice while MT5 is still responding.
        state["last_grid_action_times"][key] = now

        if self._has_open_level(grid_positions, level_id):
            self._record_decision(state, symbol, session, "WAIT", "LEVEL_ALREADY_OPEN", settings=settings, price=price, direction=direction, level=level)
            return actions

        tp_mult = float(settings.get("TAKE_PROFIT_SPACING_MULTIPLIER", 0.8) or 0.8)
        tp_distance = spacing * tp_mult
        tp_price = price + tp_distance if direction == "BUY" else price - tp_distance
        info = mt5.symbol_info(symbol)
        if info and info.point > 0:
            tp_price = round(tp_price / info.point) * info.point

        self._record_decision(state, symbol, session, "READY", "ORDER_READY", settings=settings, price=price, direction=direction, level=level, tp=tp_price)
        grid_magic = get_magic_numbers().get("grid_magic", 99999)
        result = self.executor.place_grid_order(
            symbol=symbol,
            direction=direction,
            lot_size=fixed_lot,
            tp_price=tp_price,
            grid_magic=grid_magic,
            level_id=level_id,
            session_id=session["session_id"],
        )
        if "SUCCESS" in result:
            state.setdefault("level_reopen_counts", {})[key] = int(state.setdefault("level_reopen_counts", {}).get(key, 0)) + 1
            session.setdefault("opened_orders", []).append({"time": now, "level": level_id, "direction": direction, "result": result})
            self._record_decision(state, symbol, session, "OPEN", result, settings=settings, price=price, direction=direction, level=level, tp=tp_price)
            actions.append(result)
        else:
            state["last_grid_action_times"].pop(key, None)
            session["last_block_reason"] = result
            if "VALIDATION" in str(result) or "ORDER_REJECTED" in str(result):
                session["status"] = "STOP_NEW"
                session["stop_reason"] = result
                settings["ENABLED"] = False
                save_grid_settings(settings)
                self.log(f"AUTO GRID disabled after order failure: {result}", error=True)
            self._record_decision(state, symbol, session, "BLOCK", result, settings=settings, price=price, direction=direction, level=level)
        return actions

    def _level_for_price(self, price, boundary, spacing):
        return int((price - boundary["lower"]) / spacing) if spacing > 0 else 0

    def _direction_for_level(self, price, boundary, mode):
        mode = str(mode or "NEUTRAL").upper()
        midpoint = (boundary["upper"] + boundary["lower"]) / 2.0
        if mode == "LONG":
            return "BUY" if price <= midpoint else None
        if mode == "SHORT":
            return "SELL" if price >= midpoint else None
        if price < midpoint:
            return "BUY"
        if price > midpoint:
            return "SELL"
        return None

    def _has_open_level(self, positions, level_id):
        safe_level = "".join(ch for ch in str(level_id) if ch.isalnum() or ch == "_")[:12]
        markers = (f"L:{level_id}", f"GRID_{safe_level}", str(level_id))
        return any(
            any(marker and marker in str(getattr(p, "comment", "")) for marker in markers)
            for p in positions
        )

    def _sync_grid_history(self, state):
        current_positions = self._grid_positions()
        current_tickets = {int(p.ticket) for p in current_positions}
        previous_tickets = {int(t) for t in state.get("grid_active_tickets", []) if str(t).isdigit()}
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
                pos_type = "BUY" if d_out.type == mt5.DEAL_TYPE_SELL else "SELL"
                open_time_str = datetime.fromtimestamp(d_in.time).strftime("%Y-%m-%d %H:%M:%S") if d_in else ""
                trigger = d_in.comment if d_in else GRID_COMMENT_PREFIX
                session_id = "GRID"
                parts = str(trigger).split("|")
                if len(parts) > 1 and parts[1]:
                    session_id = parts[1]
                orders = mt5.history_orders_get(position=ticket)
                last_sl, last_tp = 0.0, 0.0
                if orders:
                    for order in reversed(orders):
                        if order.sl > 0:
                            last_sl = order.sl
                        if order.tp > 0:
                            last_tp = order.tp
                        if last_sl > 0 and last_tp > 0:
                            break
                fee = -(abs(d_out.commission) + abs(d_out.swap))
                append_trade_log(
                    ticket,
                    d_out.symbol,
                    pos_type,
                    d_out.volume,
                    d_in.price if d_in else 0.0,
                    last_sl,
                    last_tp,
                    fee,
                    real_pnl,
                    "GRID_TP_or_Close",
                    market_mode="GRID",
                    trigger_signal=trigger,
                    session_id=session_id,
                    open_time_str=open_time_str,
                    mae_usd=min(real_pnl, 0.0),
                    mfe_usd=max(real_pnl, 0.0),
                )
                state["grid_pnl_today"] = float(state.get("grid_pnl_today", 0.0) or 0.0) + real_pnl
                state["grid_trades_today"] = int(state.get("grid_trades_today", 0) or 0) + 1
                if real_pnl < 0:
                    state["grid_daily_loss_count"] = int(state.get("grid_daily_loss_count", 0) or 0) + 1
                self.log(f"Closed {pos_type} {d_out.symbol} #{ticket} PnL={real_pnl:+.2f}")
            except Exception as e:
                self.log(f"History sync failed for #{ticket}: {e}", error=True)

        state["grid_active_tickets"] = sorted(current_tickets)
