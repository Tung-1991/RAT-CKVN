"""Non-secret OTP status shared by the connection page and main Preview."""
from datetime import datetime
import time


def market_status(view, max_age=10, *, now=None):
    from ckps.models import Quote, load_record
    from ckps.services.session_preview import closing_quote
    now=time.time() if now is None else now
    connection=view.get('market_connection',{})
    quote=view.get('quotes',{}).get(view.get('contract'),{})
    if connection.get('error'):return 'DNSE · LỖI KẾT NỐI','red'
    if quote and closing_quote(view.get('contract'),quote,now=now):return 'DNSE · ĐÓNG PHIÊN','blue'
    try:
        if quote and quote.get('symbol')==view.get('contract') and load_record(Quote,quote).fresh(max_age,now):
            return 'DNSE · REALTIME','green'
    except (ValueError,TypeError):pass
    if quote:return 'DNSE · GIÁ CŨ','amber'
    return ('DNSE · CHỜ GIÁ' if connection.get('configured') else 'DNSE · CHƯA KẾT NỐI'),'amber'


def order_block_reason(view, max_age=10, *, now=None, busy=False, requested=False):
    """Explain the existing entry gates; cached prices never supply trading data."""
    if requested:return 'Đang đổi kết nối · Chờ xác minh sổ'
    if busy:return 'Đang gửi lệnh · Chờ kết quả'
    from ..scheduled_orders import scheduled_ticket
    if scheduled_ticket(view):return ''
    from ckps.models import Quote,load_record
    from ckps.services.session_preview import closing_quote
    now=time.time() if now is None else now
    quote=view.get('quotes',{}).get(view.get('contract'),{})
    if quote and closing_quote(view.get('contract'),quote,now=now):
        return 'ĐÓNG PHIÊN · Chờ giá mới để đặt lệnh'
    if not quote or quote.get('symbol')!=view.get('contract'):
        return 'CHỜ GIÁ DNSE · Chưa thể đặt lệnh'
    try:fresh=load_record(Quote,quote).fresh(max_age,now)
    except (ValueError,TypeError):fresh=False
    if not fresh:return 'GIÁ CŨ · Chờ DNSE cập nhật để đặt lệnh'
    if not view.get('healthy') or not view.get('consistent'):
        return 'Chờ đối soát tài khoản / lệnh'
    return view.get('calendar',{}).get('reason') or ''


def otp_status(view, mode, *, now=None):
    if mode != 'REAL':
        return 'OTP · PAPER không cần xác thực', 'neutral'
    now = time.time() if now is None else now
    auth = view.get('trading_auth', {})
    until = auth.get('until', 0.)
    if auth.get('valid') and isinstance(until, (int, float)) and until > now:
        remaining = max(1, int((until-now)/60))
        return f'OTP · Còn {remaining//60}h{remaining%60:02d} · hết hạn {datetime.fromtimestamp(until).strftime("%H:%M")}', 'green'
    if until:
        return 'OTP · HẾT HẠN · xác thực lại', 'amber'
    return 'OTP · CHƯA XÁC THỰC', 'amber'
