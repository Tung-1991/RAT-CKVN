"""Completed-candle ATR provenance and configured protection distances."""
from datetime import date
from math import isfinite

from ckps.rules.defaults import default_exit_settings, shared_exit_settings


def atr_preview(view, rules=None):
    data = view.get('atr14') or {}
    settings = shared_exit_settings({**default_exit_settings(), **(rules or {})})
    def description(value=None):
        parts=[]
        number=lambda n:f'{n:.2f}'.replace('.', ',')
        if settings['atr_start_enabled']:
            parts.append(f"Bắt đầu +{number(value*settings['atr_start_multiplier'])}%" if value is not None
                         else f"Bắt đầu {settings['atr_start_multiplier']:g} ATR".replace('.',','))
        else:parts.append('Bắt đầu khi có lãi')
        if settings['atr_trail_enabled']:
            parts.append(f"lùi ATR {number(value*settings['atr_trail_multiplier'])}%" if value is not None
                         else f"lùi {settings['atr_trail_multiplier']:g} ATR".replace('.',','))
        if settings['retention_enabled']:
            parts.append(f"giữ {settings['retention_pct']:g}% lãi")
            if settings['retention_until_enabled']:parts.append(f"tới MFE {settings['retention_until']:g}% giá vốn")
        return ' · '.join(parts)
    waiting = ('ATR14 · CHỜ NẾN 1D', description(), False)
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
        number = lambda n: f'{n:.2f}'.replace('.', ',')
        return (f'ATR14 · {number(value)}% · phiên {session}',
                description(value), True)
    except (ValueError, TypeError, KeyError):
        return waiting
