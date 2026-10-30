"""Read-only ATR provenance and the fixed early-protection distances."""
from datetime import date
from math import isfinite

from ckps.rules.defaults import shared_exit_settings


def atr_preview(view):
    data = view.get('atr14') or {}
    settings = shared_exit_settings({})
    waiting = ('ATR14 · CHỜ NẾN 1D', 'Bắt đầu 0,5 ATR · lùi 0,8 ATR · giữ 70% lãi', False)
    try:
        value = float(data['pct'])
        if (not view.get('contract') or data.get('contract') != view['contract']
                or data.get('period') != 14 or not 14 <= data.get('count', 0)
                or not isfinite(value) or value <= 0):
            return waiting
        if data.get('sample'):
            session = 'MẪU'
        else:
            session = date.fromisoformat(data['as_of']).strftime('%d/%m/%Y')
        start = value * settings['atr_start_multiplier']
        trail = value * settings['atr_trail_multiplier']
        number = lambda n: f'{n:.2f}'.replace('.', ',')
        return (f'ATR14 · {number(value)}% · phiên {session}',
                f'Bắt đầu +{number(start)}% · lùi ATR {number(trail)}% · giữ 70% lãi', True)
    except (ValueError, TypeError, KeyError):
        return waiting
