"""VN30 date exclusions adapted from RAT-CKVN core.market_calendar.

No legacy runtime imports. Dates come from the exchange calendar cache; only
the expiry weekday rule is calculated locally, with known holidays adjusted.
"""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
import calendar
import re

from .p2.market import VN_TZ, market_phase


def dates(values):
    if isinstance(values,str):values=re.split(r'[,;\s]+',values.strip())
    result=set()
    for value in values or []:
        text=str(value).strip()
        if not text:continue
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):raise ValueError('Ngày cần dạng YYYY-MM-DD.')
        result.add(date.fromisoformat(text).isoformat())
    return sorted(result)


@dataclass
class CalendarSettings:
    use_dnse_working_dates: bool = True
    block_entry_ato: bool = True
    block_entry_atc: bool = True
    avoid_vn30_expiry_entry: bool = False
    avoid_vn30_rebalance_entry: bool = False
    manual_closed_dates: list[str] = field(default_factory=list)
    vn30_rebalance_dates: list[str] = field(default_factory=list)
    notify_enabled: bool = True
    expiry_notice_enabled: bool = True
    notice_days: int = 1
    notice_time: str = '15:00'

    @classmethod
    def from_dict(cls,raw=None):
        result=cls(**{key:value for key,value in (raw or {}).items() if key in cls.__dataclass_fields__})
        for key in ('use_dnse_working_dates','block_entry_ato','block_entry_atc','avoid_vn30_expiry_entry',
                'avoid_vn30_rebalance_entry','notify_enabled','expiry_notice_enabled'):
            if not isinstance(getattr(result,key),bool):raise ValueError('Lịch cần công tắc bật/tắt hợp lệ.')
        result.manual_closed_dates=dates(result.manual_closed_dates)
        result.vn30_rebalance_dates=dates(result.vn30_rebalance_dates)
        if isinstance(result.notice_days,bool) or int(result.notice_days)!=float(result.notice_days) or not 1<=int(result.notice_days)<=31:
            raise ValueError('Báo trước từ 1 đến 31 ngày.')
        result.notice_days=int(result.notice_days)
        # Expiry is informational, including when migrating an older blocking setting.
        result.avoid_vn30_expiry_entry = False
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',result.notice_time):raise ValueError('Giờ báo cần dạng HH:MM.')
        return result

    def to_dict(self):return asdict(self)


def covered(day,cache):
    text=day.isoformat()
    return bool(cache.get('coverage_start') and cache.get('coverage_end') and cache['coverage_start']<=text<=cache['coverage_end'])


def date_status(day,settings,cache):
    if day.weekday()>=5:return 'WEEKEND'
    if day.isoformat() in settings.manual_closed_dates:return 'HOLIDAY'
    if settings.use_dnse_working_dates and cache.get('working_dates') and covered(day,cache):
        return 'TRADING' if day.isoformat() in cache.get('working_dates',[]) else 'HOLIDAY'
    return 'UNKNOWN'


def expiry_date(year,month,settings,cache):
    thursdays=[week[calendar.THURSDAY] for week in calendar.monthcalendar(year,month) if week[calendar.THURSDAY]]
    day=date(year,month,thursdays[2])
    for _ in range(31):
        if date_status(day,settings,cache) not in {'HOLIDAY','WEEKEND'}:return day
        day-=timedelta(days=1)
    raise ValueError('Lịch nghỉ không đủ một ngày giao dịch trước đáo hạn.')


def special_days(today,settings,cache):
    result={text:'NGÀY NGHỈ BỔ SUNG' for text in settings.manual_closed_dates}
    if settings.use_dnse_working_dates:
        for offset in range(settings.notice_days+1):
            day=today+timedelta(days=offset)
            if day.weekday()<5 and date_status(day,settings,cache)=='HOLIDAY':result.setdefault(day.isoformat(),'NGÀY NGHỈ DNSE')
    if settings.avoid_vn30_rebalance_entry:
        for text in settings.vn30_rebalance_dates:result[text]='NGÀY ĐỔI RỔ VN30'
    if settings.expiry_notice_enabled:
        for delta in (0,1):
            month=(today.month-1+delta)%12+1
            year=today.year+(today.month-1+delta)//12
            expiry=expiry_date(year,month,settings,cache)
            result[expiry.isoformat()]='NGÀY ĐÁO HẠN VN30F'+(' (DỰ KIẾN)' if date_status(expiry,settings,cache)=='UNKNOWN' else '')
    return result


def entry_block(now,settings,cache):
    now=now.astimezone(VN_TZ) if now.tzinfo else now.replace(tzinfo=VN_TZ)
    day=now.date()
    status=date_status(day,settings,cache)
    if status=='WEEKEND':return 'Nghỉ cuối tuần; không mở vị thế mới.'
    if status=='HOLIDAY':return f'Ngày nghỉ {day:%d/%m/%Y}; không mở vị thế mới.'
    label=special_days(day,settings,cache).get(day.isoformat())
    if label and not label.startswith('NGÀY ĐÁO HẠN'):
        return f'{label} {day:%d/%m/%Y}; không mở vị thế mới.'
    phase=market_phase(now,exchange='VN30')[0]
    if phase=='ATO' and settings.block_entry_ato:return 'ATO; chặn mở vị thế mới theo lịch.'
    if phase=='ATC' and settings.block_entry_atc:return 'ATC; chặn mở vị thế mới theo lịch.'
    return ''
