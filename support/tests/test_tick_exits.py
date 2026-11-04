"""Every evidenced tick can latch SL/TP/E; submission uses the latest price."""
from dataclasses import asdict
from datetime import datetime, timedelta
import json
import time

import pytest

from ckps.connections.dnse.protocol import UnknownOutcome
from ckps.connections.dnse.stream import MarketFeed
from ckps.models import ExitSettings, Quote
from ckps.rules.p2.market import VN_TZ
from ckps.trading.execution import Engine


def protected(system, reason='SL', side='LONG', quantity=2):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(sl_enabled=reason == 'SL', sl_distance=.5,
        tp_enabled=reason == 'TP', tp_distance=.5, ema_exit_enabled=reason == 'E'))
    engine.open_manual(side, quantity, 'MOK')
    engine.poll()
    now = datetime.now(VN_TZ)
    broker.set_bars([dict(time=(now-timedelta(days=n)).timestamp(), close=2000)
                    for n in range(30, 0, -1) if (now-timedelta(days=n)).weekday() < 5])
    engine.poll(manage=False)
    engine.arm(True)
    return engine, broker, store


def batch(symbol, prices, *, equal_times=False):
    feed = MarketFeed('offline', 'offline')
    feed.symbols = {symbol}
    feed.authenticated = True
    now = time.time()
    for index, price in enumerate(prices):
        feed._message(None, json.dumps({'symbol': symbol, 'matchPrice': price,
            'timestamp': now if equal_times else now + index * .001}))
    return feed.drain()


@pytest.mark.parametrize('reason', ['SL', 'TP', 'E'])
@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
@pytest.mark.parametrize('equal_times', [False, True])
def test_full_exit_survives_intr_batch_rebound(system, reason, side, sign, equal_times):
    engine, broker, store = protected(system, reason, side)
    hit = 2000 + sign * (11 if reason == 'TP' else -11)
    engine.on_prices(*batch(broker.contract, (hit, 2000), equal_times=equal_times))
    exits = [o for o in store.orders() if o.action == 'CLOSE']
    assert len(exits) == 1 and exits[0].reason == reason and exits[0].applied == 2
    assert exits[0].avg_fill == 2000  # The trigger price cannot manufacture a fill.
    assert not store.positions()


@pytest.mark.parametrize('permission', ['bot_off', 'unmanaged', 'suspended', 'rule_off'])
def test_a_batch_cannot_bypass_exit_permissions(system, permission):
    engine, broker, store = protected(system)
    position = store.positions()[0]
    if permission == 'bot_off':
        engine.disarm()
    elif permission == 'unmanaged':
        engine.set_managed(position.id, False)
    elif permission == 'suspended':
        engine.suspend_position(position.id)
    else:
        engine.settings.exit['sl_enabled'] = False
    engine.on_prices(*batch(broker.contract, (1989, 2000)))
    assert len(store.orders()) == 1 and store.position(position.id).quantity == 2
    assert not store.position(position.id).metrics.get('full_exit')


def test_newer_account_quote_does_not_hide_unprocessed_stream_ticks(system):
    engine, broker, store = protected(system)
    data = batch(broker.contract, (1989, 2000))
    final = data[0][broker.contract]
    engine.latest.quotes[broker.contract] = Quote(broker.contract, 2000, at=final.at + .001)
    engine.on_prices(*data)
    assert not store.positions() and store.orders()[-1].reason == 'SL'
    assert engine.latest.quotes[broker.contract].at == final.at + .001


def test_batch_intent_survives_reservation_restart_and_rebound(system):
    engine, broker, store = protected(system)
    position = store.positions()[0]
    waiting = engine.close_position(position.id, 2, kind='LO', price=2010)
    engine.poll(manage=False)
    engine.on_prices(*batch(broker.contract, (1989, 2000)))
    assert store.order(waiting.id).status == 'CANCEL_PENDING'
    assert store.position(position.id).metrics['full_exit']['reason'] == 'SL'
    restarted = Engine(store, broker, engine.settings)
    restarted.poll()
    assert not restarted.enabled.is_set() and store.positions()[0].quantity == 2
    restarted.arm(True)
    restarted.poll()
    assert not store.positions() and store.orders()[-1].reason == 'SL'


def test_unknown_batch_exit_is_never_submitted_twice(system, monkeypatch):
    engine, broker, store = protected(system)
    calls = []
    def timeout(order, **kwargs):
        calls.append(order.id)
        raise UnknownOutcome('offline unknown')
    monkeypatch.setattr(broker, 'submit', timeout)
    engine.on_prices(*batch(broker.contract, (1989, 2000)))
    engine.on_prices(*batch(broker.contract, (1988, 2000)))
    engine.poll()
    assert len(calls) == 1 and store.order(calls[0]).status == 'UNKNOWN'
    assert store.positions()[0].quantity == 2


def test_stale_sample_is_not_revalidated_by_a_newer_tick(system):
    engine, broker, store = protected(system)
    now = time.time()
    samples = (Quote(broker.contract, 1989, at=now - 30), Quote(broker.contract, 2000, at=now))
    engine.on_prices({broker.contract: samples[-1]}, {broker.contract: (1989, 2000)}, samples)
    assert len(store.orders()) == 1 and store.positions()[0].worst == 2000


def test_reset_at_adoption_discards_unobserved_ticks_for_that_symbol():
    feed = MarketFeed('offline', 'offline')
    feed.symbols = {'VN30F1M', '41I1GB000'}
    for symbol in feed.symbols:
        feed._message(None, json.dumps({'symbol': symbol, 'matchPrice': 1989, 'timestamp': time.time()}))
    feed.reset_extremes('VN30F1M')
    _, extremes, samples = feed.drain()
    assert 'VN30F1M' not in extremes
    assert [quote.symbol for quote in samples] == ['41I1GB000']


@pytest.mark.parametrize('permission', ['bot', 'position'])
def test_enabling_permission_cannot_replay_a_buffered_off_period_crossing(system, permission):
    engine, broker, store = protected(system)
    position = store.positions()[0]
    if permission == 'bot':
        engine.disarm()
    else:
        engine.set_managed(position.id, False)
    feed = MarketFeed('offline', 'offline')
    feed.symbols = {broker.contract}
    feed.authenticated = True
    now = time.time()
    for index, price in enumerate((1989, 2000)):
        feed._message(None, json.dumps({'symbol': broker.contract, 'matchPrice': price,
            'timestamp': now + index * .001}))
    broker.feed = feed
    if permission == 'bot':
        engine.arm(True)
    else:
        engine.set_managed(position.id, True)
    engine.on_prices(*feed.drain())
    assert len(store.orders()) == 1 and store.position(position.id).quantity == 2
    assert not store.position(position.id).metrics.get('full_exit')
