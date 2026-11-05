"""Read-only results and public analysis detail; no execution callbacks."""
from math import isfinite
import time
from ckps.models import Quote, load_record
from ..formatting import price, clock


def signal_preview(view, max_age=10, *, now=None):
    now=time.time() if now is None else now
    context=view.get('market_context',{})
    quote=view.get('quotes',{}).get(view.get('contract'),{})
    from ckps.services.session_preview import closing_quote
    closed = (context.get('mode')=='CLOSE' and quote and closing_quote(view.get('contract'),quote,now=now)
              and context.get('quote_at')==quote.get('at'))
    quote_fresh=False
    try:
        quote_fresh=bool(quote and quote.get('symbol')==view.get('contract') and load_record(Quote,quote).fresh(max_age,now))
        context_fresh=-2<=now-float(context.get('observed_at',0))<=max_age
        fresh=quote_fresh and context_fresh
        closed=closed and context_fresh
    except (ValueError,TypeError):fresh=closed=False
    if closed:
        stamp=clock(quote['at'])
        entry=('ĐÓNG PHIÊN',('Đã tính EMA/RSI' if context.get('entry',{}).get('calculated') else 'Chờ tính EMA/RSI')+' · '+stamp,'amber')
        state,ma=context.get('state'),context.get('ma')
        if state in {'ABOVE','BELOW','EQUAL'} and isinstance(ma,(int,float)) and isfinite(ma) and ma>0:
            return entry,({'ABOVE':'UP','BELOW':'DOWN','EQUAL':'ĐI NGANG'}[state],
                'Đóng phiên '+price(quote['last'])+' · MA200 '+price(ma)+' · '+stamp,
                {'ABOVE':'green','BELOW':'red','EQUAL':'neutral'}[state])
        return entry,('CHỜ','Chưa đủ 200 nến ngày','amber')
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
        waiting=('CHỜ',detail,'amber')
        return waiting,waiting
    state=context.get('state')
    ma=context.get('ma')
    if state in {'ABOVE','BELOW','EQUAL'} and isinstance(ma,(int,float)) and isfinite(ma) and ma>0:
        trend=({'ABOVE':'UP','BELOW':'DOWN','EQUAL':'ĐI NGANG'}[state],
            'Giá HĐ '+price(quote['last'])+' · MA200 '+price(ma)+'\nGiờ giá '+clock(quote['at']),
            {'ABOVE':'green','BELOW':'red','EQUAL':'neutral'}[state])
    else:trend=('CHỜ','Chưa đủ nến ngày','amber')
    entry=context.get('entry',{})
    detail={
        'HISTORY':'Chưa đủ nến 1D cho tín hiệu',
        'ANALYSIS_ERROR':'Phân tích lỗi · kiểm tra dữ liệu DNSE',
        'ANALYSIS_STALE':'Chờ kết quả phân tích mới',
        'PRICE_STALE':'Phân tích chờ giá mới',
        'ANALYSIS_PENDING':'Chờ kết quả phân tích',
    }.get(entry.get('reason'))
    if detail is None:
        detail='Chờ kết quả phân tích' if view.get('analysis_running') else 'Đang khởi tạo phân tích'
    result=('CHỜ',detail,'amber')
    if entry.get('state')=='WAIT':result=('CHƯA CÓ ĐIỂM','Đang theo dõi','neutral')
    elif entry.get('state')=='OFF':result=('TẠM DỪNG','Chưa bật phân tích','neutral')
    elif entry.get('state')=='READY':
        try:
            value=float(entry['price'])
            if isfinite(value) and value>0 and -2<=now-float(entry['observed_at'])<=max_age:
                result=('LONG · '+price(value),'Phân tích lúc '+clock(entry['observed_at']),'green')
        except (ValueError,TypeError,KeyError):pass
    from ckps.services.market_context import analysis_context
    public=analysis_context(context.get('analysis',{}),view.get('contract'),max_age=max_age,now=now)
    if public:
        p2=public['p2'];marks=p2['indicators'];lines=[]
        if p2['status']:lines.append(p2['status'])
        if 'buy_ema_fast' in marks and 'buy_ema_slow' in marks:
            lines.append('EMA nhanh '+price(marks['buy_ema_fast'])+' · chậm '+price(marks['buy_ema_slow']))
        if 'rsi' in marks:lines.append(f"RSI {marks['rsi']:.2f} · Phân tích "+clock(public['observed_at']))
        if lines:result=(result[0], '\n'.join(lines), result[2])
    return result,trend
