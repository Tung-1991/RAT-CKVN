"""Shared non-secret calendar policy/cache, background GET and notice history."""
from datetime import datetime, date, timedelta
import json
import os
from pathlib import Path
import threading

from ckps.config import runtime_root
from ckps.rules.calendar import CalendarSettings, dates, date_status, entry_block, expiry_date, special_days
from ckps.rules.p2.market import VN_TZ
from ckps.storage import AccountLease


def local_now():return datetime.now(VN_TZ)


def read_settings():
    path=runtime_root()/'calendar.json'
    return CalendarSettings.from_dict(json.loads(path.read_text(encoding='utf-8')) if path.exists() else {})


def _write(name,values):
    folder=runtime_root();folder.mkdir(parents=True,exist_ok=True)
    path=folder/name
    temporary=folder/(name+f'.{os.getpid()}.{threading.get_ident()}.tmp')
    temporary.write_text(json.dumps(values,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(temporary,path)


def write_settings(settings):_write('calendar.json',CalendarSettings.from_dict(settings.to_dict()).to_dict())


def read_cache():
    try:
        values=json.loads((runtime_root()/'calendar_cache.json').read_text(encoding='utf-8'))
        if not isinstance(values,dict):return {}
        values['working_dates']=dates(values.get('working_dates',[]))
        if not values['working_dates']:
            values.pop('coverage_start',None);values.pop('coverage_end',None)
        return values
    except (OSError,ValueError,TypeError):return {}


def refresh(provider,*,now=None):
    now=now or local_now()
    today=now.date().isoformat()
    if not read_settings().use_dnse_working_dates:return read_cache()
    try:lease=AccountLease(runtime_root()/'calendar_refresh.lock')
    except RuntimeError:return read_cache()
    try:
        cache=read_cache()
        if cache.get('last_attempt_date')==today:return cache
        if date_status(now.date(),read_settings(),cache)=='HOLIDAY' and cache.get('coverage_start'):
            return cache
        cache['last_attempt_date']=today
        try:
            values=dates(provider() or [])
            if not values:raise ValueError('DNSE chưa trả lịch ngày giao dịch.')
            cache.update(working_dates=values,coverage_start=today,coverage_end=max(values),error='')
        except Exception:cache['error']='Chưa cập nhật lịch DNSE; giữ lịch đã có.'
        _write('calendar_cache.json',cache)
        return cache
    finally:lease.close()


def block_reason(now=None):return entry_block(now or local_now(),read_settings(),read_cache())


def summary(now=None):
    now=now or local_now();settings=read_settings();cache=read_cache()
    expiry=expiry_date(now.year,now.month,settings,cache)
    if expiry<now.date():
        month=now.month%12+1;year=now.year+(now.month//12)
        expiry=expiry_date(year,month,settings,cache)
    return {'reason':entry_block(now,settings,cache),'next_expiry':expiry.isoformat(),
        'expiry_confirmed':date_status(expiry,settings,cache)=='TRADING',
        'coverage_start':cache.get('coverage_start'),'coverage_end':cache.get('coverage_end'),'error':cache.get('error','')}


class CalendarWorker:
    def __init__(self,key,secret):
        from ckps.connections.dnse.history import ReadOnlyHistory
        self.client=ReadOnlyHistory(key,secret)
        self.stop=threading.Event();self.client.stopping=self.stop
        self.thread=threading.Thread(target=self._run,name='ckps-calendar',daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            try:refresh(self.client.working_dates)
            except Exception:pass
            self.stop.wait(60)

    def close(self):
        self.stop.set();self.thread.join();self.client.close()


class CalendarNotices:
    def __init__(self,store):self.store=store

    def observe(self,*,now=None,enabled=False,chat=''):
        now=(now or local_now()).astimezone(VN_TZ)
        settings=read_settings();cache=read_cache()
        today=now.date()
        with self.store.transaction():
            for text,label in special_days(today,settings,cache).items():
                distance=(date.fromisoformat(text)-today).days
                if not 0<=distance<=settings.notice_days:continue
                if distance>0 and now.strftime('%H:%M')<settings.notice_time:continue
                key=f'calendar:{text}:'+('today' if distance==0 else 'before')
                if self.store.get('calendar_notice',key):continue
                reason=(f'{label} {text} · Hạn chế giao dịch; tự cân nhắc vào lệnh. App không tự chặn hoặc đóng vị thế.'
                        if label.startswith('NGÀY ĐÁO HẠN') else
                        f'{label} {text} · Không mở vị thế mới; đóng/giảm và E/M vẫn được phép.')
                self.store.put('calendar_notice',key,{'at':now.timestamp()})
                self.store.put('signal_history',key,{'id':key,'at':now.timestamp(),'symbol':'VN30F1M','kind':'LỊCH','reason':reason})
                if enabled and chat and settings.notify_enabled:
                    self.store.notify('owner:'+chat,'VN30 · CALENDAR · ALERT\n'+reason,key=key)
