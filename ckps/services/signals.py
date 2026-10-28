"""P1/P2 read-only analysis. No engine, order queue or submit callback."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from math import isfinite

from ckps.rules.signal_settings import SignalSettings
from ckps.rules.p2.business import (indicator_snapshot, crossover_signal_from_snapshots,
    advance_buy_confirmation, buy_confirmation_conditions, entry_volume_snapshot, whipsaw_snapshot)
from ckps.rules.p2.ema_memory import consume_cross, crossing_totals, va_scan_counts, recent_session_start
from ckps.rules.p2.market import VN_TZ, market_phase, exchange_sessions, history_working_dates
from ckps.rules.p2.session_cross import HistoryCache, SessionCrossService


class AnalysisState:
    def __init__(self, store):
        self.store = store

    def read(self):
        return self.store.get("analysis", "price_cache", {"symbols": {}})

    def write(self, values):
        self.store.put("analysis", "price_cache", values)

    def session_cross(self, symbol, stream):
        return self.store.get("analysis", f"cross:{symbol}:{stream}", {})

    def save_session_cross(self, symbol, stream, row):
        self.store.put("analysis", f"cross:{symbol}:{stream}", row)
        return row


def daily_rows(rows, now):
    """Normalize dates and deduplicate without filling missing candles."""
    output = {}
    for original in rows or []:
        try:
            raw = original.get("time", original.get("date", original.get("timestamp")))
            try:
                stamp = float(raw)
                stamp = stamp / 1000 if stamp > 1e12 else stamp
                day = datetime.fromtimestamp(stamp, VN_TZ).date()
            except (TypeError, ValueError):
                day = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
            if day > now.date():
                continue
            value = float(original["close"])
            if not isfinite(value) or value <= 0:
                continue
            row = dict(original, time=datetime.combine(day, datetime.min.time(), VN_TZ).timestamp(), close=value)
            row["closed"] = day < now.date() or (now.hour * 60 + now.minute >= 885 and original.get("closed", True))
            output[day] = row
        except (ValueError, TypeError, OverflowError, OSError, KeyError):
            continue
    return [output[day] for day in sorted(output)]


def p1_snapshot(rows, price, *, fresh=True):
    if len(rows) < 200:
        return {"state": "WAIT", "price": price, "ma": None, "samples": len(rows),
                "text": f"THIẾU {200 - len(rows)} / 200 NẾN 1D"}
    ma = sum(float(row["close"]) for row in rows[-200:]) / 200
    state = "ABOVE" if price > ma else "BELOW" if price < ma else "EQUAL"
    return {"state": state if fresh else "STALE", "price": price, "ma": ma, "samples": len(rows),
            "text": {"ABOVE": "TRÊN MA200", "BELOW": "DƯỚI MA200", "EQUAL": "BẰNG MA200"}[state] if fresh else "GIÁ CŨ"}


class SignalAnalysis:
    def __init__(self, store, history):
        self.store = store
        self.state = AnalysisState(store)
        self.cache = HistoryCache(self.state, history)
        self.crosses = SessionCrossService(self.cache, self.state)
        self.previous = {}
        self.admission = {}
        self.filter_signature = {}

    def refresh(self):
        self.crosses.recovered.clear()
        self.state.write({**self.state.read(), "cross_recovery": {}})
        with self.store.lock:
            keys = [row[0] for row in self.store.db.execute("SELECT id FROM records WHERE kind='analysis' AND id LIKE 'cross:%'").fetchall()]
        for key in keys:
            row = self.store.get("analysis", key, {})
            row.pop("lookback_key", None)
            self.store.put("analysis", key, row)

    def observe(self, data, settings, *, now=None, working_dates=None):
        now = now or datetime.now(VN_TZ)
        p = SignalSettings.from_dict(settings.signals)
        symbol = data["contract"]
        quote = data.get("quotes", {}).get(symbol, {})
        price = float(quote.get("last", 0))
        age = now.timestamp() - float(quote.get("at", 0))
        fresh = -2 <= age <= settings.max_quote_age and price > 0
        bars = daily_rows(data.get("bars"), now)
        if bars and fresh:
            today = datetime.combine(now.date(), datetime.min.time(), VN_TZ).timestamp()
            if bars[-1]["time"] < today and market_phase(now, working_dates, exchange="VN30")[0] in {"ATO", "OPEN", "ATC"}:
                bars.append({"time": today, "open": price, "high": price, "low": price, "close": price, "closed": False})
            elif bars[-1]["time"] == today:
                bars[-1] = dict(bars[-1], close=price)
        result = {"contract": symbol, "observed_at": now.timestamp(),
                  "market_phase": market_phase(now, working_dates, exchange="VN30")[0],
                  "p1": p1_snapshot(bars, price, fresh=fresh),
                  "p2": {"status": "CHỜ DỮ LIỆU", "badge": "WAIT", "mode": p.buy_ema_cross_mode,
                         "observation": p.signal_mode, "interval": p.realtime_indicator_interval, "policy": "ALERT"}}
        if not p.enabled:
            result["p2"].update(status="P2 OFF", badge="OFF")
            return result
        rows = bars if p.signal_mode == "REALTIME" else [b for b in bars if b["closed"]]
        if len(rows) < max(p.buy_ema_slow + 1, p.sell_ema_slow + 1, p.rsi_period + 2):
            result["p2"]["status"] = "THIẾU LỊCH SỬ 1D"
            return result
        working_dates = history_working_dates(working_dates, bars, now)
        # Notification switches do not restart signal confirmation or sampling.
        signature = repr({key: value for key, value in p.to_dict().items()
                          if key not in {"buy_alert_enabled", "sell_alert_enabled"}})
        if self.filter_signature.get(symbol) != signature:
            self.store.put("analysis", "filter:" + symbol, {})
            self.filter_signature[symbol] = signature
            self.admission.pop(symbol, None)
        sampled = rows
        interval = 0 if p.realtime_indicator_interval == "TICK" else int(p.realtime_indicator_interval[:-1]) * 60
        self.crosses.max_observation_gap = max(20, interval + 5)
        admitted = self.admission.get(symbol)
        if p.signal_mode == "REALTIME" and interval:
            bucket = int(quote.get("at", 0)) // interval
            pending = self.store.get("analysis", "bucket:" + symbol, {})
            if pending and (pending.get("interval") != interval or pending.get("pair") != signature):
                pending = {}
            if pending and bucket > pending["bucket"]:
                end = (pending["bucket"] + 1) * interval
                if now.timestamp() - end <= max(interval, settings.max_quote_age):
                    sampled = deepcopy(rows)
                    sampled[-1]["close"] = pending["price"]
                    admitted = {"marks": self._marks(sampled, p), "at": end - 0.001, "bucket": pending["bucket"], "price": pending["price"]}
            self.store.put("analysis", "bucket:" + symbol,
                {"bucket": bucket, "price": price, "interval": interval, "pair": signature})
        elif fresh or p.signal_mode == "CLOSED":
            stamp = now.timestamp() if p.signal_mode == "REALTIME" else rows[-1]["time"] + 885 * 60
            admitted = {"marks": self._marks(sampled, p), "at": stamp, "price": sampled[-1]["close"]}
        if admitted is None:
            result["p2"]["status"] = "CHỜ ĐÓNG NHỊP " + p.realtime_indicator_interval
            return result
        marks = admitted["marks"]
        if p.signal_mode == "REALTIME":
            sampled = deepcopy(rows)
            sampled[-1]["close"] = admitted["price"]
        previous = self.previous.get(symbol, self.store.get("analysis", "marks:" + symbol, {}))
        new_sample = admitted["at"] > self.admission.get(symbol, {}).get("at", 0)
        if new_sample:
            self.previous[symbol] = self.admission.get(symbol, {}).get("marks", previous)
            previous = self.previous[symbol]
            self.admission[symbol] = admitted
            self.store.put("analysis", "marks:" + symbol, marks)
        at = datetime.fromtimestamp(admitted["at"], VN_TZ)
        stream = settings.mode
        if p.signal_mode == "CLOSED":
            memory = self.crosses.observe_closed(symbol, stream, rows, p, now, "VN30", working_dates=working_dates)
        elif fresh:
            memory = self.crosses.observe(symbol, stream, sampled, marks, p, at, "VN30", working_dates=working_dates)
        else:
            memory = self.state.session_cross(symbol, stream)
        memory = self._consume_fills(symbol, stream, memory, data.get("orders", []), now)
        # The X-session display always scans history, without granting that
        # evidence to VA when VA QUÉT TRƯỚC is disabled.
        preview = self.store.get("analysis", "window:" + symbol, {})
        if fresh or p.signal_mode == "CLOSED":
            preview = self.crosses._lookback(deepcopy(memory), symbol, rows,
                replace(p, buy_ema_cross_mode="SESSIONS"), now,
                dict(pair=f"{p.buy_ema_fast}/{p.buy_ema_slow}", mode="SESSIONS", sessions=p.buy_ema_cross_sessions,
                     exchange="VN30", working_dates=working_dates, holidays=None, va_lookback_enabled=True),
                p.signal_mode, current=marks)
            self.store.put("analysis", "window:" + symbol, preview)
        xp = crossing_totals(dict(preview, mode="SESSIONS")) if preview.get("lookback_ready") else (None, None)
        va = va_scan_counts(memory)
        buy = crossover_signal_from_snapshots(marks, previous, buy_signal_require_ema_cross=False,
            buy_use_ema=p.buy_signal_use_ema, buy_use_rsi=p.buy_signal_use_rsi,
            sell_use_ema=False, sell_use_rsi=False) == "BUY"
        exit_signal = crossover_signal_from_snapshots(marks, previous, prefer="SELL", buy_use_ema=False, buy_use_rsi=False,
            sell_use_ema=p.sell_signal_use_ema, sell_use_rsi=p.sell_signal_use_rsi,
            sell_signal_require_ema_cross=p.sell_signal_require_ema_cross) == "SELL"
        cross_needed = p.buy_signal_use_ema and p.buy_signal_require_ema_cross
        gate = not cross_needed or bool(memory.get("ready") and memory.get("valid") and not memory.get("used"))
        volume = entry_volume_snapshot(rows, p.buy_volume_average_sessions)
        whip = whipsaw_snapshot(rows, p.buy_ema_fast, p.buy_ema_slow, p.whipsaw_x)
        volume_ok = not p.buy_volume_enabled or (volume["ready"] and volume["ratio"] >= p.buy_volume_min_ratio)
        whip_ok = not p.whipsaw_enabled or whip["whipsaw_crossovers"] < p.whipsaw_n
        if not fresh and p.signal_mode == "REALTIME":
            self.store.put("analysis", "filter:" + symbol, {})
            candidate, status, audit = False, "GIÁ CŨ · CHỜ MẪU MỚI", {}
        else:
            candidate, status, audit = self._filters(symbol, buy and gate and volume_ok and whip_ok, marks, p, now, working_dates)
        if not fresh and p.signal_mode == "REALTIME":
            candidate, status = False, "GIÁ CŨ · CHỜ MẪU MỚI"
        elif not gate:
            candidate = False
            status = {"SESSION_USED": "ĐÃ DÙNG LẦN CẮT", "WAIT_DOWN": "CHỜ XUỐNG RỒI LÊN",
                      "WAIT_UP": "CHỜ CẮT LÊN", "EXPIRED": "LẦN CẮT HẾT HẠN"}.get(memory.get("state"), "CHỜ GIAO CẮT XÁC MINH")
        elif not volume_ok:
            candidate = False
            status = "CHỜ VOLUME" if volume["ready"] else "THIẾU LỊCH SỬ VOLUME"
        elif not whip_ok:
            candidate = False
            status = "WHIPSAW · CHỜ"
        full = settings.max_contracts > 0 and sum(int(v["quantity"]) for v in data.get("positions", [])) >= settings.max_contracts
        pending = any(o.get("action") == "OPEN" and o.get("status") not in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED", "FAILED"}
                      for o in data.get("orders", []))
        ema_gate = gate if cross_needed else marks.get("buy_ema_fast", 0) > marks.get("buy_ema_slow", 0)
        badge = "USED" if full or pending or (cross_needed and memory.get("used")) else "READY" if ema_gate else "WAIT"
        if pending:
            candidate, status = False, "CÓ LỆNH MỞ ĐANG CHỜ"
        if full:
            candidate, status = False, "ĐỦ HẠN MỨC HĐ"
        phase = market_phase(now, working_dates, exchange="VN30")[0]
        if phase not in {"ATO", "OPEN", "ATC"}:
            candidate = False
        self._record_history(symbol, memory)
        result["p2"].update(status=status, badge=badge, indicators=marks, memory=memory,
            xp={"up": xp[0], "down": xp[1], "start": preview.get("lookback_started_at", ""), "end": now.date().isoformat(),
                "ready": bool(preview.get("lookback_ready"))}, va=va, volume=volume, whipsaw=whip,
            confirmation=audit, buy_alert=bool(candidate), exit_alert=bool(exit_signal and fresh and phase in {"ATO", "OPEN", "ATC"}),
            history=self.store.get("analysis", "history:" + symbol, []), price_fresh=fresh)
        self.record_signals(result, now)
        return result

    @staticmethod
    def _marks(rows, params):
        return indicator_snapshot(rows, params.buy_ema_fast, params.buy_ema_slow, params.rsi_period,
                                  sell_fast=params.sell_ema_fast, sell_slow=params.sell_ema_slow)

    def _filters(self, symbol, trigger, marks, p, now, working_dates):
        key = "filter:" + symbol
        state = self.store.get("analysis", key, {})
        phase = market_phase(now, working_dates, exchange="VN30")[0]
        if (p.buy_window_enabled or p.buy_confirmation_enabled) and p.signal_mode != "REALTIME":
            self.store.put("analysis", key, {})
            return False, "LỌC GIỜ/XÁC NHẬN CẦN REALTIME", {}
        checks = buy_confirmation_conditions(marks, p)
        if p.buy_window_enabled:
            minute = now.hour * 60 + now.minute
            hour, part = map(int, p.buy_window_start.split(":"))
            if state.get("day") != now.date().isoformat():
                state = {}
            pending = state.get("pending") or trigger
            if not (not p.buy_signal_use_ema or checks["ema"]) or not (not p.buy_signal_use_rsi or checks["rsi"]):
                pending = False
            if minute >= 885:
                self.store.put("analysis", key, {})
                return False, "HẾT KHUNG GIỜ", {}
            state.update(day=now.date().isoformat(), pending=pending)
            if minute < hour * 60 + part or phase not in {"ATO", "OPEN", "ATC"}:
                self.store.put("analysis", key, state)
                return False, "CHỜ " + p.buy_window_start if pending else "CHỜ TÍN HIỆU", {}
            trigger = pending
        confirmation, status, audit = advance_buy_confirmation(state.get("confirmation"), raw_trigger=trigger,
            indicators=marks, observed_at=now, exchange="VN30", params=p, working_dates=working_dates,
            max_observation_gap_seconds=max(20, 65 * (int(p.realtime_indicator_interval[:-1]) if p.realtime_indicator_interval != "TICK" else 0)))
        state["confirmation"] = confirmation
        self.store.put("analysis", key, state)
        if status == "WAITING":
            return False, f"XÁC NHẬN {audit['minutes_held']:.0f}/{audit['minutes_required']}P", audit
        if status in {"CANCELLED", "INVALID"}:
            return False, "HỦY XÁC NHẬN", audit
        ready = (trigger and not p.buy_confirmation_enabled) or status == "CONFIRMED"
        return ready, "ĐẠT TÍN HIỆU" if ready else "CHỜ TÍN HIỆU", audit

    def _consume_fills(self, symbol, stream, memory, orders, now):
        consumed = set(self.store.get("analysis", "fills:" + symbol, []))
        for order in orders:
            if order["id"] in consumed or order.get("symbol") != symbol or order.get("action") != "OPEN" or not order.get("filled"):
                continue
            if order.get("side") == "LONG" and memory.get("valid") and float(memory.get("cross_timestamp", 0)) <= order.get("updated_at", 0):
                memory = consume_cross(memory, now=now, order_id=order["id"])
            consumed.add(order["id"])
        self.store.put("analysis", "fills:" + symbol, sorted(consumed))
        return self.state.save_session_cross(symbol, stream, memory)

    def _record_history(self, symbol, memory):
        history = self.store.get("analysis", "history:" + symbol, [])
        for direction, stamp in (("UP", memory.get("cross_at")), ("DOWN", memory.get("last_down_at"))):
            if stamp:
                key = direction + ":" + stamp
                if not any(row["id"] == key for row in history):
                    history.append({"id": key, "direction": direction, "at": stamp})
                try:
                    at = datetime.fromisoformat(stamp).timestamp()
                    self.store.put("signal_history", symbol + ":" + key, {"id": symbol + ":" + key,
                        "symbol": symbol, "at": at, "kind": "CẮT ↑" if direction == "UP" else "CẮT ↓",
                        "reason": "EMA · " + memory.get("observation_mode", "REALTIME")})
                except (ValueError, OverflowError):
                    pass
        self.store.put("analysis", "history:" + symbol, sorted(history, key=lambda r: r["at"])[-300:])

    def record_signals(self, result, now):
        symbol, p2 = result["contract"], result["p2"]
        if not p2.get("indicators") or not p2.get("price_fresh", False):
            return
        previous = self.store.get("analysis", "signal_state:" + symbol, {})
        marks = p2["indicators"]
        current = {"BUY":bool(p2.get("buy_alert")), "E":bool(p2.get("exit_alert"))}
        for kind, active in current.items():
            if active and not previous.get(kind):
                key = f"{symbol}:{kind}:{now.timestamp()}"
                prefix = "buy" if kind == "BUY" else "sell"
                self.store.put("signal_history", key, {"id":key, "symbol":symbol, "kind":kind,
                    "at":now.timestamp(), "fast":marks.get(prefix + "_ema_fast"), "slow":marks.get(prefix + "_ema_slow"),
                    "rsi":marks.get("rsi"), "reason":"THEO DÕI · " + p2.get("status", "")})
        self.store.put("analysis", "signal_state:" + symbol, current)

    def signal_history(self):
        return sorted(self.store.all("signal_history"), key=lambda r:r["at"])[-500:]
