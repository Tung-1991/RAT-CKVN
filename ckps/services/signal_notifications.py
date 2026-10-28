"""Signal-only Telegram delivery; no account, engine or trading dependency."""
import time
import requests
from ckps.rules.signal_settings import SignalSettings
from ckps.rules.market_alerts import MarketAlertSettings


class SignalNotifications:
    def _owner_telemetry(self):
        with self.store.transaction():
            self._observe_signal_conditions()

    def _observe_signal_conditions(self):
        if not self.latest:
            return
        signals = SignalSettings.from_dict(self.settings.signals)
        latest = self.latest
        quote = latest.quotes.get(latest.contract)
        if not quote or not quote.fresh(self.settings.max_quote_age):
            return
        analysis = self.analysis.snapshot()
        if analysis.get("contract") != latest.contract:
            return
        if 'observed_at' in analysis and not -2<=time.time()-float(analysis['observed_at'])<=self.settings.max_quote_age:
            return
        phase = analysis.get("p2", {})
        if getattr(self,'owner_contract',None)!=latest.contract:
            self.owner_contract = latest.contract
            saved=self.store.get('notification','condition:'+latest.contract,{})
            self.owner_state = tuple(saved['state']) if 'state' in saved else None
            self.owner_sent = saved.get('sent',{})
        state = (bool(phase.get("buy_alert")),bool(phase.get("exit_alert")))
        value = phase.get("indicators", {})
        if not value:
            return
        previous = self.owner_state or (False, False)
        self.owner_state = state
        self.store.put('notification','condition:'+latest.contract,{'state':state,'sent':getattr(self,'owner_sent',{})})
        if not self.owner_enabled or not self.owner_token or not self.owner_chat or not signals.enabled:
            return
        sent = getattr(self,'owner_sent',{})
        enabled = (signals.buy_alert_enabled,signals.sell_alert_enabled)
        for index, (label, prefix) in enumerate((("TÍN HIỆU", "buy"), ("E", "sell"))):
            if state[index] and not previous[index] and enabled[index] and time.time()-sent.get(label,0)>=60:
                self.store.notify("owner:" + self.owner_chat,
                    f"{latest.contract} · {label} · ALERT\n"
                    f"EMA {value[prefix + '_ema_fast']:.3f}/{value[prefix + '_ema_slow']:.3f} · RSI {value['rsi']}")
                sent[label] = time.time()
        self.owner_sent = sent
        self.store.put('notification','condition:'+latest.contract,{'state':state,'sent':sent})
        self.owner_state, self.owner_last = state, time.time()

    def _private_alert_allowed(self, text):
        if ' · ENTRY · ' in text:
            return self.settings.entry_notifications
        if ' · CALENDAR · ALERT' in text:
            from .calendar import read_settings
            return read_settings().notify_enabled
        market = MarketAlertSettings.from_dict(self.settings.market_alerts)
        if ' · TREND · ALERT' in text:
            return market.trend_enabled
        if ' · VOLATILITY · ALERT' in text:
            return market.movement_enabled
        signals = SignalSettings.from_dict(self.settings.signals)
        return signals.enabled and (signals.sell_alert_enabled if ' · E · ALERT' in text else
                                    signals.buy_alert_enabled if ' · TÍN HIỆU · ALERT' in text else False)

    def _drop_disabled_owner(self):
        with self.store.lock:
            rows = self.store.db.execute("SELECT id,text FROM outbox WHERE sent=0 AND target LIKE 'owner:%'").fetchall()
            for key,text in rows:
                if not self._private_alert_allowed(text):
                    self.store.db.execute('UPDATE outbox SET sent=2 WHERE id=?',(key,))

    def _telegram_worker(self):
        while not self.stop.wait(1):
            try:
                self._flush_telegram()
            except Exception:
                self.telegram_error = 'Telegram đang chờ gửi; phân tích tín hiệu tiếp tục.'

    def _flush_telegram(self):
        with self.store.lock:
            pending=self.store.db.execute('SELECT id,target,text FROM outbox WHERE sent=0 ORDER BY rowid LIMIT 6').fetchall()
        for key, target, text in pending:
            if getattr(self,'stop',None) is not None and self.stop.is_set():break
            owner = target.startswith("owner:")
            enabled = owner and self.owner_enabled
            if not enabled:
                with self.store.lock:
                    self.store.db.execute('UPDATE outbox SET sent=2 WHERE id=?',(key,))
                continue
            if owner:
                enabled = enabled and self._private_alert_allowed(text)
                if not enabled:
                    with self.store.lock:
                        self.store.db.execute("UPDATE outbox SET sent=2 WHERE id=?", (key,))
                    continue
            token = self.owner_token
            chat = target.removeprefix("owner:")
            if owner and chat!=getattr(self,'owner_chat',''):
                with self.store.lock:
                    self.store.db.execute('UPDATE outbox SET sent=2 WHERE id=?',(key,))
                continue
            if not enabled or not token or (not owner and chat != self.settings.telegram_chat):
                continue
            try:
                response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": text[:4096]}, timeout=(3, 5))
                if not response.ok or not response.json().get("ok"):
                    self.telegram_error = f"Telegram chưa gửi được (HTTP {response.status_code})."
                    break
                with self.store.lock:
                    self.store.db.execute("UPDATE outbox SET sent=1 WHERE id=?", (key,))
                self.telegram_error = ""
            except (requests.RequestException, ValueError):
                self.telegram_error = "Telegram mất kết nối; đang giữ tin để thử lại."
                break
