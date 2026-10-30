"""Local configurable daily EMA observations, independent of signal alerts."""
from datetime import datetime, timedelta

from ckps.models import Decision, ExitSettings, load_record
from ckps.rules.calculations import ema
from ckps.rules.p2.market import VN_TZ
from ckps.services.signals import daily_rows
from ckps.services.calendar import read_cache, read_settings
from ckps.rules.calendar import date_status


class EMAExit:
    def observe(self, snapshot, settings, symbol, *, now=None):
        now = now or datetime.now(VN_TZ)
        waiting = {'ready': False, 'contract': symbol, 'fast': None, 'slow': None}
        if not settings.exit.get('ema_exit_enabled', False):
            return dict(waiting, state='OFF')
        if not snapshot or snapshot.contract != symbol:
            return dict(waiting, state='WAIT_CONTRACT')
        quote = snapshot.quotes.get(symbol)
        if not quote or quote.symbol != symbol or not quote.fresh(settings.max_quote_age, now.timestamp()):
            return dict(waiting, state='WAIT_PRICE')
        params = load_record(ExitSettings, settings.exit).validate()
        rows = daily_rows(snapshot.bars, now)
        previous_session = now.date() - timedelta(days=1)
        try:
            calendar, cache = read_settings(), read_cache()
        except (OSError, ValueError, TypeError):
            return dict(waiting, state='WAIT_CALENDAR')
        for _ in range(31):
            if date_status(previous_session, calendar, cache) not in {'HOLIDAY', 'WEEKEND'}:
                break
            previous_session -= timedelta(days=1)
        prior = [row for row in rows if datetime.fromtimestamp(row['time'], VN_TZ).date() < now.date()]
        if not prior or datetime.fromtimestamp(prior[-1]['time'], VN_TZ).date() != previous_session:
            return dict(waiting, state='WAIT_BARS')
        rows = prior
        at = quote.at
        rows.append({'close': quote.last})
        if len(rows) < params.ema_exit_slow + 1:
            return dict(waiting, state='WAIT_BARS')
        closes = [row['close'] for row in rows]
        return dict(ready=True, state='READY', contract=symbol, fast=ema(closes, params.ema_exit_fast)[-1],
                    slow=ema(closes, params.ema_exit_slow)[-1], sample_at=at, quote_at=quote.at,
                    fast_period=params.ema_exit_fast, slow_period=params.ema_exit_slow,
                    mode=params.ema_exit_mode, interval=params.ema_exit_interval)

    @staticmethod
    def decision(position, view):
        if not view.get('ready') or view.get('contract') != position.symbol:
            return None
        if position.sign * (view['fast'] - view['slow']) < -1e-9:
            return Decision('E', view['fast'], position.quantity)
        return None
