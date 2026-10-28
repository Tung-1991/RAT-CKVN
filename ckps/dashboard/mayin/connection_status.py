"""Non-secret OTP status shared by the connection page and main Preview."""
from datetime import datetime
import time


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
