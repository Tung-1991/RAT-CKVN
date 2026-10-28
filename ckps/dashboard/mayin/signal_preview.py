"""Two black-box results; no indicator controls or execution callbacks."""
from math import isfinite
import time
from ckps.models import Quote, load_record
from ..formatting import price


def signal_preview(view, max_age=10, *, now=None):
    now=time.time() if now is None else now
    context=view.get('market_context',{})
    quote=view.get('quotes',{}).get(view.get('contract'),{})
    waiting=('CHỜ','Chờ dữ liệu','neutral')
    try:
        fresh=bool(quote and quote.get('symbol')==view.get('contract') and load_record(Quote,quote).fresh(max_age,now))
        fresh=fresh and -2<=now-float(context.get('observed_at',0))<=max_age
    except (ValueError,TypeError):fresh=False
    if not fresh:return waiting,waiting
    state=context.get('state')
    ma=context.get('ma')
    if state in {'ABOVE','BELOW','EQUAL'} and isinstance(ma,(int,float)) and isfinite(ma) and ma>0:
        trend=({'ABOVE':'UP','BELOW':'DOWN','EQUAL':'ĐI NGANG'}[state],
            'MA200 · '+price(ma),{'ABOVE':'green','BELOW':'red','EQUAL':'neutral'}[state])
    else:trend=('CHỜ','Chưa đủ nến ngày','neutral')
    entry=context.get('entry',{})
    result=('CHỜ','Chờ phân tích','neutral')
    if entry.get('state')=='WAIT':result=('CHƯA CÓ ĐIỂM','Đang theo dõi','neutral')
    elif entry.get('state')=='OFF':result=('TẠM DỪNG','Chưa bật phân tích','neutral')
    elif entry.get('state')=='READY':
        try:
            value=float(entry['price'])
            if isfinite(value) and value>0 and -2<=now-float(entry['observed_at'])<=max_age:
                result=('LONG · '+price(value),'Có tín hiệu','green')
        except (ValueError,TypeError,KeyError):pass
    return result,trend
