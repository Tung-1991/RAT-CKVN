"""Local manual LO requests wait for an eligible session, never a cached fill."""
from datetime import datetime,timedelta

from ckps.rules.p2.market import VN_TZ,market_phase,exchange_close_minute
from . import calendar


def queue_session():
    now=calendar.local_now()
    settings,cache=calendar.read_settings(),calendar.read_cache()
    phase=market_phase(now,exchange='VN30')[0]
    reason=calendar.entry_block(now,settings,cache)
    if phase in {'OPEN','ATO','ATC'} and not reason:return None
    day=now.date()
    end=870 if settings.block_entry_atc else exchange_close_minute('VN30')
    if now.hour*60+now.minute>=end:day+=timedelta(days=1)
    for _ in range(370):
        candidate=datetime(day.year,day.month,day.day,9,0,tzinfo=VN_TZ)
        if not calendar.entry_block(candidate,settings,cache):
            return {'date':day.isoformat(),'reason':reason or 'Ngoài phiên giao dịch'}
        day+=timedelta(days=1)
    raise ValueError('Chưa xác định được phiên giao dịch cho lệnh chờ.')


def session_hold():
    now=calendar.local_now()
    if market_phase(now,exchange='VN30')[0] not in {'OPEN','ATO','ATC'}:
        return 'Chờ phiên giao dịch'
    return calendar.block_reason(now)
