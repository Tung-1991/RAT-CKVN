"""End-of-session calculations for display only; never a live entry signal."""
from datetime import datetime
from math import isfinite

from ckps.models import Quote, load_record, is_vn30
from ckps.rules.p2.market import VN_TZ, exchange_close_minute, market_phase
from ckps.rules.signal_settings import SignalSettings
from .signals import SignalAnalysis, daily_rows, p1_snapshot
from .technical_notifications import completed_bars


def closing_quote(contract, quote, *, now):
    """Only a DNSE closing print from today qualifies, never a saved cache."""
    try:
        quote = quote if isinstance(quote, Quote) else load_record(Quote, quote)
        local = datetime.fromtimestamp(now, VN_TZ)
        at = datetime.fromtimestamp(quote.at, VN_TZ)
        return bool(is_vn30(contract) and quote.symbol == contract and quote.source == 'DNSE'
            and isfinite(quote.last) and quote.last > 0 and quote.at <= now + 2
            and at.date() == local.date() and market_phase(local, exchange='VN30')[0] == 'CLOSED'
            and at.hour * 60 + at.minute >= exchange_close_minute('VN30')
            and local.hour * 60 + local.minute >= exchange_close_minute('VN30'))
    except (TypeError, ValueError, OverflowError, OSError):
        return False


def closing_analysis(data, settings, *, now):
    contract = data['contract']
    quote = data.get('quotes', {}).get(contract, {})
    if not closing_quote(contract, quote, now=now):return None
    local = datetime.fromtimestamp(now, VN_TZ)
    params = SignalSettings.from_dict(settings.signals)
    rows = daily_rows(data.get('bars'), local)
    previous = completed_bars(rows, local)
    rows = [row for row in rows if datetime.fromtimestamp(row['time'], VN_TZ).date() < local.date()]
    rows.append({'time': datetime.combine(local.date(), datetime.min.time(), VN_TZ).timestamp(),
                 'close': quote['last'], 'closed': True})
    enough = len(rows) >= max(params.buy_ema_slow + 1, params.sell_ema_slow + 1, params.rsi_period + 2)
    marks = SignalAnalysis._marks(rows, params) if enough else {}
    ready = enough and all(isinstance(marks.get(key), (float, int)) and isfinite(marks[key])
                          for key in ('buy_ema_fast', 'buy_ema_slow', 'rsi'))
    return {'contract': contract, 'observed_at': now, 'quote_at': quote['at'], 'price': quote['last'],
            'ready': ready, 'indicators': marks, 'p1': p1_snapshot(previous, quote['last'])}
