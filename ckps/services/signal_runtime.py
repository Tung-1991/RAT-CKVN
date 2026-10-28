"""Independent read-only market analysis and Telegram service. Cannot trade."""
from dataclasses import asdict
import os
import queue
import threading
import time
from types import SimpleNamespace

from ckps.connections.dnse.history import ReadOnlyHistory
from ckps.connections.dnse.paper_market import PaperMarket
from ckps.models import Quote, Settings, load_record, is_vn30
from ckps.storage import AccountLease, Store
from .signal_config import signal_folder, write_signal_settings
from .signal_worker import SignalWorker
from .signal_notifications import SignalNotifications
from .market_alerts import MarketAlerts
from .calendar import CalendarNotices


class SignalRuntime(SignalNotifications):
    def __init__(self,settings,credentials=None,*,market=None):
        self.settings=settings.validate()
        self.persist_settings=True
        credentials=credentials or {}
        folder=signal_folder()
        self.lease=AccountLease(folder/'session.lock')
        self.store=Store(folder/'ledger.sqlite3')
        key=credentials.get('key') or os.environ.get('CKPS_DNSE_API_KEY','')
        secret=credentials.get('secret') or os.environ.get('CKPS_DNSE_API_SECRET','')
        history_credentials={'key':key,'secret':secret} if key and secret else None
        try:
            self.market=market if market is not None else PaperMarket(ReadOnlyHistory(key,secret) if history_credentials else None,poll_seconds=settings.poll_seconds)
            self.analysis=SignalWorker(self.store.path,credentials=history_credentials)
        except Exception:
            if hasattr(self,'market'):self.market.close()
            self.store.close();self.lease.close()
            raise
        self.latest=None
        self.commands,self.events=queue.Queue(),queue.Queue()
        self.stop=threading.Event()
        self.owner_token=credentials.get('telegram_token',os.environ.get('CKPS_TELEGRAM_TOKEN',''))
        self.owner_chat,self.owner_enabled=settings.telegram_chat,settings.telegram_enabled
        self.owner_state,self.owner_contract,self.owner_last=None,None,0.
        self.owner_sent={}
        self.telegram_error=''
        self.market_alerts=MarketAlerts(self.store)
        self.calendar_notices=CalendarNotices(self.store)
        self.calendar_worker = None
        if history_credentials:
            from .calendar import CalendarWorker
            self.calendar_worker = CalendarWorker(key, secret)
        from .entry_notices import EntryNotices
        self.entry_notices=EntryNotices(self.store)
        # Never replay queued notifications from an earlier backend session.
        self.store.db.execute('UPDATE outbox SET sent=2 WHERE sent=0')
        self.telegram_thread=threading.Thread(target=self._telegram_worker,name='ckps-signals-telegram',daemon=True)
        self.thread=threading.Thread(target=self._run,name='ckps-signals',daemon=True)
        self.telegram_thread.start();self.thread.start()

    def command(self,name,*args):
        if name not in {'settings','refresh_signals'}:
            raise ValueError('Backend chỉ có phân tích và thông báo; không hỗ trợ giao dịch.')
        if not self.stop.is_set():self.commands.put((name,args))

    def _configure(self,raw,token):
        settings=load_record(Settings,raw).validate()
        with self.store.lock:
            if (settings.telegram_enabled,settings.telegram_chat,token)!=(self.owner_enabled,self.owner_chat,self.owner_token):
                self.store.db.execute('UPDATE outbox SET sent=2 WHERE sent=0')
            self.settings=settings
            self.owner_token=token
            self.owner_enabled,self.owner_chat=settings.telegram_enabled,settings.telegram_chat
            self._drop_disabled_owner()
            if getattr(self,'persist_settings',True):write_signal_settings(settings)

    def _run(self):
        next_poll=0.
        try:
            while not self.stop.is_set():
                try:name,args=self.commands.get(timeout=max(.05,min(.2,next_poll-time.monotonic())))
                except queue.Empty:name,args=None,()
                if self.stop.is_set():break
                if name:
                    try:
                        if name=='settings':self._configure(*args)
                        elif name=='refresh_signals':self.analysis.refresh_requested.set()
                        self.events.put(('success',name))
                    except Exception as exc:self.events.put(('error',str(exc)))
                    next_poll=0.
                if time.monotonic()>=next_poll:
                    try:self._publish()
                    except Exception as exc:self.events.put(('error',str(exc)))
                    next_poll=time.monotonic()+self.settings.poll_seconds
        finally:
            if self.calendar_worker:self.calendar_worker.close()
            self.market.close()
            self.analysis.close()
            self.telegram_thread.join()
            self.store.close();self.lease.close()
            self.events.put(('closed',None))

    def _publish(self):
        receipts=getattr(self,'entry_notices',None)
        if receipts:receipts.observe(enabled=self.owner_enabled and bool(self.owner_token) and self.settings.entry_notifications,chat=self.owner_chat)
        notices=getattr(self,'calendar_notices',None)
        if notices:notices.observe(enabled=self.owner_enabled and bool(self.owner_token),chat=self.owner_chat)
        data=self.market.snapshot()
        contract=data['contract']
        if not is_vn30(contract):raise ValueError('Backend chỉ phân tích hợp đồng VN30.')
        quotes={symbol:load_record(Quote,raw) for symbol,raw in data.get('quotes',{}).items() if raw.get('symbol')==symbol and is_vn30(symbol)}
        feed=getattr(self.market,'feed',None)
        if feed:
            quote=feed.latest(contract,self.settings.max_quote_age)
            if quote and quote.symbol==contract:quotes[contract]=quote
        self.latest=SimpleNamespace(contract=contract,quotes=quotes)
        raw_quotes={symbol:asdict(quote) for symbol,quote in quotes.items()}
        self.analysis.update({'contract':contract,'quotes':raw_quotes,'bars':data.get('bars',[])},asdict(self.settings))
        analysis=self.analysis.snapshot()
        self._owner_telemetry()
        with self.store.transaction():
            market=self.market_alerts.observe(contract,raw_quotes.get(contract,{}),analysis,self.settings.market_alerts,
                now=time.time(),max_age=self.settings.max_quote_age)
            for event in market.pop('events'):
                text=f'{contract} · {event["channel"]} · ALERT\n'+event['reason']
                if event.get('notify',True) and self.owner_enabled and self.owner_token and self.owner_chat and self._private_alert_allowed(text):
                    self.store.notify('owner:'+self.owner_chat,text,key=event['id'])
        from .market_context import publish_context, entry_context
        last_move=self.store.get('market','movement:'+contract,{})
        quote=raw_quotes.get(contract,{})
        if quote and -2<=time.time()-quote.get('at',0)<=self.settings.max_quote_age:
            movement=(f"BIẾN ĐỘNG {last_move.get('change_points',0):+g}đ" if 0<=time.time()-last_move.get('at',0)<=60 else 'ĐANG THEO DÕI')
            publish_context({'contract':contract,'observed_at':quote['at'],'movement':movement,
                'entry':entry_context(analysis,contract,max_age=self.settings.max_quote_age)})
        self.events.put(('snapshot',{'contract':contract,'quotes':raw_quotes,'connection':data,'analysis':analysis,
            'history':self.store.all('signal_history')[-200:],'events':self.store.events(),
            'market':market,'telegram_error':self.telegram_error}))

    def close(self):
        self.stop.set()
