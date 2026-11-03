"""The existing order ticket can confirm a local LO for a later session."""
from dataclasses import asdict
from math import isfinite

from ckps.models import is_vn30,quantity
from .formatting import price


def scheduled_ticket(view):
    session=view.get('entry_queue') or {}
    if not session.get('date'):return None
    symbol=view.get('contract')
    quote=view.get('quotes',{}).get(symbol,{})
    cache=view.get('market_cache') or {}
    if not quote and symbol=='VN30F1M':symbol=cache.get('contract',symbol)
    if not is_vn30(symbol) or symbol=='VN30F1M':return None
    if quote and quote.get('symbol')!=symbol:return None
    return {'symbol':symbol,'date':session['date']}


def request_scheduled(app,side,ticket):
    try:
        if app.kind.get()!='LO':raise ValueError('Ngoài phiên chỉ lưu lệnh LO; chọn giá và số HĐ cụ thể.')
        px=float(app.limit.get())
        if not isfinite(px) or px<=0 or abs(px*10-round(px*10))>1e-6:
            raise ValueError('Giá LO phải dương và đúng bước 0,1 điểm.')
        rules,_=app.ticket_rules(px)
        qty=quantity(app.qty.get()) if app.qty.get().strip() else app.ticket_capacity(side,px,rules).maximum
        if not qty or qty<=0:raise ValueError('Nhập số HĐ cụ thể; chưa có cơ sở cho AUTO ngoài phiên.')
        original=(app.qty.get(),app.limit.get(),app.kind.get(),ticket,asdict(rules))
        def submit():
            current=(app.qty.get(),app.limit.get(),app.kind.get(),scheduled_ticket(app.view),asdict(app.ticket_rules(px)[0]))
            if current!=original or app.mode_requested or app.switch_pending:
                raise ValueError('Vé/phiên/RULE đã đổi; xem và xác nhận lại.')
            app.order_busy=True
            app.send('schedule_manual',side,qty,px,ticket['symbol'],ticket['date'])
        app.confirm(f"{app.settings.mode} · LƯU LO CHỜ PHIÊN {ticket['date']}\n"
            f"{side} {ticket['symbol']} · {qty} HĐ @ {price(px)}\n"
            'Chưa gửi broker. App phải mở/kết nối; đến phiên kiểm tra lại giá mới, sức mở và OTP REAL. '
            'Giữ nguyên mã/giá/HĐ; khớp theo thị trường. Chưa gửi hết phiên hẹn thì hết hiệu lực.',submit)
    except (ValueError,TypeError) as exc:app.report(str(exc),error=True)
