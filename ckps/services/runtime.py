from __future__ import annotations

from dataclasses import asdict
import os
import queue
import threading
import time


from ckps.connections.dnse.client import DNSEBroker
from ckps.connections.dnse.paper import PaperBroker
from ckps.connections.dnse.paper_market import PaperMarket
from ckps.connections.dnse.history import ReadOnlyHistory
from ckps.config import book_path, write_settings
from ckps.models import load_record, Settings
from ckps.trading.execution import Engine
from ckps.storage import AccountLease, Store
from ckps.services.calendar import CalendarWorker, summary as calendar_summary


class Runtime:
    """One I/O worker; Tk receives immutable snapshots and never waits on HTTP."""

    def __init__(self, settings, credentials=None, *, offline=False, market_profile=None):
        self.settings = settings
        from ckps.services.quote_cache import QuoteCache
        self.quote_cache = QuoteCache()
        folder = book_path(settings)
        self.lease = AccountLease(folder / "session.lock")
        self.store = Store(folder / "ledger.sqlite3")
        credentials = credentials or {}
        key=credentials.get("key") or os.environ.get("CKPS_DNSE_API_KEY","")
        secret=credentials.get("secret") or os.environ.get("CKPS_DNSE_API_SECRET","")
        try:
            if settings.mode=="PAPER":
                from ckps.connections.dnse.discovery import AccountReader
                reader=AccountReader(key,secret) if key and secret and not offline else None
                profile=market_profile or {}
                market=None if offline else PaperMarket(ReadOnlyHistory(key,secret) if key and secret else None,
                    poll_seconds=settings.poll_seconds,account_reader=reader,account=profile.get('account_no',settings.account_no),
                    package=profile.get('loan_package_id',settings.loan_package_id))
                broker=PaperBroker(self.store,settings,market=market,offline=offline)
            else:
                broker=DNSEBroker(key,secret,settings.account_no,settings.loan_package_id)
                from ckps.connections.secure_session import trading_session
                broker.token, broker.token_until = trading_session(settings.account_no, {'key': key, 'secret': secret})
                if not offline:
                    from ckps.connections.dnse.candles import CandleWorker
                    broker.history_worker = CandleWorker(ReadOnlyHistory(key, secret))
        except Exception:
            self.store.close()
            self.lease.close()
            raise
        self.engine = Engine(self.store, broker, settings)
        from ckps.services.entry_notices import EntryRelay
        self.entry_relay = EntryRelay(self.store)
        self.calendar_worker=CalendarWorker(key,secret) if key and secret and not offline else None
        self.commands, self.events = queue.Queue(), queue.Queue()
        self.stop = threading.Event()
        # Old combined-app messages must never be sent by the trading app.
        with self.store.lock:
            self.store.db.execute('UPDATE outbox SET sent=2 WHERE sent=0')
        self.desired_arm = False
        self.health_error = ""
        self.thread = threading.Thread(target=self._run, name="ckps-io", daemon=True)
        self.thread.start()

    def command(self, name, *args, **kwargs):
        if self.stop.is_set():
            return
        if name == "arm":
            self.desired_arm = bool(args[0])
            if not self.desired_arm:
                self.engine.disarm()
        if name == "set_managed" and args[1] is False:
            self.engine.suspend_position(args[0])
        self.commands.put((name, args, kwargs))

    def _run(self):
        next_poll = 0.0
        while not self.stop.is_set():
            try:
                command = self.commands.get(timeout=max(0.05, min(0.2, next_poll - time.monotonic())))
            except queue.Empty:
                command = None
            if self.stop.is_set():
                break
            if command:
                name, args, kwargs = command
                try:
                    if name == "settings":
                        settings = load_record(Settings, args[0]).validate()
                        self.settings = self.engine.settings = settings
                        feed = getattr(self.engine.broker, 'feed', None)
                        if feed:
                            feed.max_quote_age = settings.max_quote_age
                        if isinstance(self.engine.broker, PaperBroker):
                            self.engine.broker.settings = settings
                    elif name == "paper_capital":
                        self.engine.paper_capital(*args)
                        write_settings(self.settings)
                        self.events.put(('paper_capital_result',{'capital':self.settings.paper_balance}))
                    elif name == 'remember_session':
                        broker = self.engine.broker
                        if self.settings.mode == 'REAL':
                            from ckps.connections.secure_session import save_trading_session
                            save_trading_session(self.settings.account_no, {'key': broker.key, 'secret': broker.secret}, broker.token, broker.token_until)
                    elif name in {"set_price", "set_bars", "send_otp", "verify_otp"}:
                        getattr(self.engine.broker, name)(*args, **kwargs)
                        if name == 'verify_otp' and self.settings.mode == 'REAL':
                            broker = self.engine.broker
                            from ckps.connections.secure_session import save_trading_session
                            try:
                                save_trading_session(self.settings.account_no, {'key': broker.key, 'secret': broker.secret}, broker.token, broker.token_until)
                            except (OSError, ValueError):
                                self.events.put(('session_warning', 'OTP đã xác thực trong phiên; Windows chưa lưu được phiên xác thực.'))
                    elif name == "refresh":
                        pass
                    else:
                        allowed = {"arm", "open_manual", "close_position", "set_managed", "cancel", "replace", "bind_unknown"}
                        if name not in allowed:
                            raise ValueError("Thao tác không hỗ trợ.")
                        if name != "arm" or not args[0] or self.desired_arm:
                            getattr(self.engine, name)(*args, **kwargs)
                    self.events.put(("success", name))
                except Exception as exc:
                    self.store.event("ERROR", str(exc))
                    self.events.put(("error", str(exc)))
                    if name=='paper_capital':self.events.put(('paper_capital_result',{'error':str(exc)}))
                    if name in {'send_otp', 'verify_otp'}:self.events.put(('auth_error', str(exc)))
                next_poll = 0.0
            feed = getattr(self.engine.broker, "feed", None)
            if feed and feed.authenticated and feed.changed.is_set():
                try:
                    self.engine.on_prices(*feed.drain())
                    self._publish()
                except Exception as exc:
                    self.engine.healthy = False
                    self.engine.error = str(exc)
            if time.monotonic() >= next_poll:
                try:
                    self.engine.poll()
                    if self.health_error:
                        self.store.event("HEALTH", "Kết nối tài khoản đã phục hồi.")
                        self.engine._notify("HỆ THỐNG · ĐÃ PHỤC HỒI\nĐã đồng bộ tài khoản/lệnh/vị thế.")
                        self.health_error = ""
                except Exception as exc:
                    if str(exc) != self.health_error:
                        self.health_error = str(exc)
                        self.store.event("HEALTH", str(exc))
                        self.engine._notify("HỆ THỐNG · CHỜ ĐỐI SOÁT\n" + str(exc))
                self._publish()
                next_poll = time.monotonic() + self.settings.poll_seconds
        self.engine.disarm()
        self.entry_relay.close()
        if self.calendar_worker:self.calendar_worker.close()
        self.engine.broker.close()
        self.store.close()
        self.lease.close()
        self.events.put(("closed", None))

    def _publish(self):
        snapshot = self.engine.latest
        self.quote_cache.observe(snapshot)
        quotes = {symbol: asdict(quote) for symbol, quote in snapshot.quotes.items()} if snapshot else {}
        views = {"armed": self.engine.enabled.is_set(), "healthy": self.engine.healthy,
                 "consistent": self.engine.consistent, "error": self.engine.error,
                 "mode": self.settings.mode, "contract": snapshot.contract if snapshot else "VN30F1M",
                 "loan_packages": [{"id": p.get("id"), "name": p.get("name"), "rate": p.get("initialRate"), 'tradingFee': p.get('tradingFee')}
                                   for p in getattr(self.engine.broker, "packages", [])],
                 "quotes": quotes, "positions": [asdict(p) for p in self.store.positions()],
                 "orders": [asdict(o) for o in self.store.orders()][-300:],
                 "history": [asdict(p) for p in self.store.positions(closed=True)][-300:],
                 "events": self.store.events()}
        views['market_cache'] = self.quote_cache.value
        broker = self.engine.broker
        until = getattr(broker, 'token_until', 0.)
        views['trading_auth'] = {'required': self.settings.mode == 'REAL', 'until': until,
            'valid': bool(getattr(broker, 'token', '') and until > time.time())}
        views['account_profile'] = getattr(broker, 'market_view', {}).get('account_profile', {})
        if snapshot:
            from ckps.services.market_context import context
            views['market_context'] = context(snapshot, max_age=self.settings.max_quote_age)
            quote=snapshot.quotes.get(snapshot.contract)
            views['market_ready']=bool(quote and quote.fresh(self.settings.max_quote_age))
            views['market_connection']=getattr(self.engine.broker,'market_view',{'configured':True,'connected':self.engine.healthy})
            # Expose the same completed-candle ATR used by protection; the UI
            # must not recompute it from realtime prices or placeholder bars.
            views['atr14'] = self.engine.atr_snapshot(snapshot.contract)
            views['ema_exit'] = self.engine.ema_snapshot(snapshot.contract)
            views["atr14_pct"] = views['atr14']['pct']
            views["account"] = {name: getattr(snapshot, name) for name in (
                "nav", "remaining_margin", "used_margin", "margin_per_contract", "pending_margin", "qmax_long", "qmax_short", "observed_at", "source", "paper_capital", "total_money", "collateral_total", "margin_reference_price", 'package_fees')}
        for side in ("LONG", "SHORT"):
            try:
                views[side] = asdict(self.engine.preview(side))
            except Exception as exc:
                views[side] = {"maximum": 0, "reason": str(exc)}
        try:views['calendar']=calendar_summary()
        except (ValueError,TypeError):views['calendar']={'reason':'Lịch không hợp lệ; không mở vị thế mới.'}
        self.events.put(("snapshot", views))

    def close(self):
        self.desired_arm = False
        self.engine.disarm()
        self.stop.set()
