"""Read-only, contract-specific last trade of a completed session."""
from datetime import datetime,timedelta
from math import isfinite
import threading
import time

from ckps.models import is_vn30,market_time
from ckps.rules.p2.market import VN_TZ
from ckps.connections.dnse.protocol import unwrap


def quote_key(quote):
    try:
        if isinstance(quote['at'],bool) or isinstance(quote['last'],bool):return None
        symbol=quote['symbol'];stamp=float(quote['at']);price=float(quote['last'])
        if (not is_vn30(symbol) or symbol=='VN30F1M' or not quote.get('source','').startswith('DNSE')
                or not isfinite(price) or price<=0 or not 0<stamp<=time.time()+2):return None
        return symbol,datetime.fromtimestamp(stamp,VN_TZ).date().isoformat()
    except (KeyError,TypeError,ValueError,OverflowError,OSError):return None


def read_previous_close(client,key):
    symbol,session=key
    end=datetime.fromisoformat(session).replace(tzinfo=VN_TZ)
    # Query one day at a time, skipping weekends and empty holiday sessions.
    for _ in range(21):
        start=end-timedelta(days=1)
        if start.weekday()<5:
            body=unwrap(client.request('GET',f'/price/{symbol}/trades',params={
                'boardId':'G1','from':str(int(start.timestamp())),'to':str(int(end.timestamp())),
                'limit':1,'order':'desc'}))
            rows=body.get('trades') if isinstance(body,dict) else None
            if not isinstance(rows,list):return {}
            if rows:
                if len(rows)!=1 or not isinstance(rows[0],dict):return {}
                row=rows[0]
                try:
                    if isinstance(row.get('matchPrice'),bool):return {}
                    stamp=market_time(row.get('time'));price=float(row['matchPrice'])
                    if (row.get('symbol')!=symbol or row.get('boardId')!='G1' or not isfinite(price) or price<=0
                            or not start.timestamp()<=stamp<end.timestamp()):return {}
                    return {'contract':symbol,'quote_session':session,'session':datetime.fromtimestamp(stamp,VN_TZ).date().isoformat(),
                        'price':price,'at':stamp,'source':'DNSE · KHỚP CUỐI PHIÊN'}
                except (KeyError,TypeError,ValueError,OverflowError,OSError):return {}
        end=start
    return {}


class PreviousCloseWorker:
    """No account/OTP, no execution-worker HTTP, obsolete replies are discarded."""
    def __init__(self,client):
        self.client=client
        self.stop=threading.Event();client.stopping=self.stop
        self.wake=threading.Event();self.lock=threading.Lock()
        self.key=None;self.value={};self.retry_at=0.
        self.thread=threading.Thread(target=self._run,name='ckps-previous-close',daemon=True)
        self.thread.start()

    def observe(self,quote):
        key=quote_key(quote or {})
        with self.lock:
            if key!=self.key:
                self.key=key;self.value={};self.retry_at=0.
            if key and not self.value and time.monotonic()>=self.retry_at:self.wake.set()
            return dict(self.value)

    def _run(self):
        while not self.stop.is_set():
            self.wake.wait(.25)
            if self.stop.is_set():break
            self.wake.clear()
            with self.lock:
                key=self.key
                if not key or self.value or time.monotonic()<self.retry_at:continue
                self.retry_at=time.monotonic()+30
            try:value=read_previous_close(self.client,key)
            except Exception:value={}
            with self.lock:
                if key==self.key:self.value=value

    def close(self):
        self.stop.set();self.wake.set();self.thread.join()
        self.client.close()
