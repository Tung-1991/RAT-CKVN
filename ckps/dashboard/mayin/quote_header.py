"""Read-only quote comparison and compact margin presentation."""
from datetime import date
from math import isfinite

from ckps.services.previous_close import quote_key
from ..formatting import money,clock


def _amount(value):
    return value if isinstance(value,(float,int)) and not isinstance(value,bool) and isfinite(value) and value>=0 else None


def quote_header(view,mode):
    contract=view.get('contract','VN30F1M')
    quote=view.get('quotes',{}).get(contract) or (view.get('market_cache') or {}).get('quote') or {}
    symbol=quote.get('symbol') or contract
    trading_symbol=symbol if contract=='VN30F1M' else contract
    margin=_amount(view.get('account',{}).get('margin_per_contract'))
    compact=(f'{margin/1_000_000:.2f}'.replace('.',',')+'tr' if margin is not None and margin>=1_000_000 else money(margin))
    caption=('~ ' if mode=='PAPER' else '')+'KQ/HĐ '+compact
    hint=f'Hợp đồng tương lai VN30\nMã giao dịch: {trading_symbol}\nKý quỹ/HĐ: {money(margin)}'
    if symbol!=trading_symbol:hint+=f'\nGiá lưu thuộc mã: {symbol}'
    if mode=='PAPER':hint+='\nPAPER · ký quỹ ước tính mô phỏng'
    value,tone='—','neutral'
    reference=view.get('previous_close') or {}
    key=quote_key(quote)
    try:
        ref_price=_amount(reference.get('price'))
        session=date.fromisoformat(reference['session'])
        if (key and key[0]==trading_symbol and reference.get('contract')==key[0] and reference.get('quote_session')==key[1]
                and session<date.fromisoformat(key[1]) and ref_price and reference.get('source','').startswith('DNSE')):
            delta=float(quote['last'])-ref_price
            if abs(delta)<1e-9:delta=0.
            value=f'{delta:+.1f} ({delta/ref_price*100:+.2f}%)'.replace('.',',')
            tone='green' if delta>0 else 'red' if delta<0 else 'amber'
            hint+=f'\nĐóng phiên trước {session:%d/%m/%Y}: {ref_price:,.1f}\nGiá so sánh: {float(quote["last"]):,.1f} · {clock(quote.get("at"))}'
        else:hint+='\nChờ giá đóng phiên trước đúng hợp đồng'
    except (KeyError,TypeError,ValueError,OverflowError):hint+='\nChờ giá đóng phiên trước đúng hợp đồng'
    return value,tone,caption,hint
