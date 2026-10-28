"""Two black-box results; no indicator controls or execution callbacks."""
from math import isfinite
import time
from ckps.models import Quote, load_record
from ..formatting import price, clock


def signal_preview(view, max_age=10, *, now=None):
    now=time.time() if now is None else now
    context=view.get('market_context',{})
    quote=view.get('quotes',{}).get(view.get('contract'),{})
    quote_fresh=False
    try:
        quote_fresh=bool(quote and quote.get('symbol')==view.get('contract') and load_record(Quote,quote).fresh(max_age,now))
        fresh=quote_fresh and -2<=now-float(context.get('observed_at',0))<=max_age
    except (ValueError,TypeError):fresh=False
    if not fresh:
        if quote:
            try:
                stamp=float(quote.get('at',0))
                if not isfinite(stamp) or not 0<stamp<=now+2:raise ValueError('Invalid quote time')
                detail='Giá cũ · '+clock(stamp)
            except (ValueError,TypeError,OSError,OverflowError):detail='Chờ giá có thời gian hợp lệ'
            if quote.get('symbol')!=view.get('contract'):detail='Chờ giá đúng mã hợp đồng'
        elif view.get('market_cache',{}).get('quote'):
            detail='Đang hiển thị giá lưu · chờ giá mới'
        else:
            detail='Chưa kết nối DNSE' if not view.get('market_connection',{}).get('configured') else 'DNSE chưa có giá mới'
        if quote_fresh:detail='Chờ dữ liệu thị trường 1D'
        waiting=('CHỜ',detail,'neutral')
        return waiting,waiting
    state=context.get('state')
    ma=context.get('ma')
    if state in {'ABOVE','BELOW','EQUAL'} and isinstance(ma,(int,float)) and isfinite(ma) and ma>0:
        trend=({'ABOVE':'UP','BELOW':'DOWN','EQUAL':'ĐI NGANG'}[state],
            'MA200 · '+price(ma),{'ABOVE':'green','BELOW':'red','EQUAL':'neutral'}[state])
    else:trend=('CHỜ','Chưa đủ nến ngày','neutral')
    entry=context.get('entry',{})
    result=('CHỜ','Backend chưa chạy · KẾT NỐI → TELEGRAM / LỊCH' if not view.get('analysis_running') else 'Backend đang chờ đủ dữ liệu 1D','neutral')
    if entry.get('state')=='WAIT':result=('CHƯA CÓ ĐIỂM','Đang theo dõi','neutral')
    elif entry.get('state')=='OFF':result=('TẠM DỪNG','Chưa bật phân tích','neutral')
    elif entry.get('state')=='READY':
        try:
            value=float(entry['price'])
            if isfinite(value) and value>0 and -2<=now-float(entry['observed_at'])<=max_age:
                result=('LONG · '+price(value),'Phân tích lúc '+clock(entry['observed_at']),'green')
        except (ValueError,TypeError,KeyError):pass
    return result,trend
