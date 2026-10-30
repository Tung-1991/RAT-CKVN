"""A fresh last tick must never legitimize stale extrema in the same batch."""
import json
import time
from dataclasses import asdict

import pytest

from ckps.connections.dnse.stream import MarketFeed
from ckps.models import ExitSettings


@pytest.mark.parametrize('bad_age', [300, None, -30])
def test_invalid_tick_cannot_pollute_extremes(bad_age):
    feed = MarketFeed('offline', 'offline')
    symbol = '41I1GB000'
    feed.symbols = {symbol}
    feed.authenticated = True
    now = time.time()
    bad = {'symbol': symbol, 'matchPrice': 2100}
    if bad_age is not None:
        bad['timestamp'] = now - bad_age
    feed._message(None, json.dumps(bad))
    feed._message(None, json.dumps({'symbol': symbol, 'matchPrice': 2001, 'timestamp': now}))
    ticks, extremes = feed.drain()
    assert ticks[symbol].last == 2001
    assert extremes[symbol] == (2001, 2001)


def test_older_tick_cannot_replace_newest_but_equal_timestamps_keep_trades():
    feed = MarketFeed('offline', 'offline')
    symbol = '41I1GB000'
    feed.symbols = {symbol}
    now = time.time()
    for price, at in [(2000, now), (2100, now - 1), (2002, now)]:
        feed._message(None, json.dumps({'symbol': symbol, 'matchPrice': price, 'timestamp': at}))
    ticks, extremes = feed.drain()
    assert ticks[symbol].last == 2002
    assert extremes[symbol] == (2000, 2002)


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_invalid_extreme_cannot_generate_an_automatic_trailing_close(system, side, sign):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(arm_enabled=True, arm_gain=1, trail_gap=.25))
    engine.open_manual(side, 2, 'MOK')
    engine.poll()
    engine.arm(True)
    feed = MarketFeed('offline', 'offline')
    feed.symbols = {'VN30F1M'}
    now = time.time()
    for price, stamp in [(2000+sign*100, now-300), (2000+sign, now)]:
        feed._message(None, json.dumps({'symbol': 'VN30F1M', 'matchPrice': price, 'timestamp': stamp}))
    broker.set_price(2000+sign)
    engine.on_prices(*feed.drain())
    assert store.positions()[0].best == 2000+sign
    assert len(store.orders()) == 1 and store.positions()[0].quantity == 2


def test_stream_uses_configured_price_age_instead_of_a_fixed_ttl():
    symbol = '41I1GB000'
    feed = MarketFeed('offline', 'offline', max_quote_age=30)
    feed.symbols = {symbol}
    feed._message(None, json.dumps({'symbol': symbol, 'matchPrice': 2000, 'timestamp': time.time()-20}))
    assert feed.drain()[1][symbol] == (2000, 2000)
    feed.max_quote_age = 2
    feed._message(None, json.dumps({'symbol': symbol, 'matchPrice': 2100, 'timestamp': time.time()-5}))
    assert not feed.drain()[1]
