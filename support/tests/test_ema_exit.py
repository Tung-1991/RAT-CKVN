"""EMA E executes locally, independently of backend notification switches."""
from dataclasses import asdict
from datetime import datetime, timedelta

import pytest

from ckps.models import ExitSettings, Position, Quote, Settings, Snapshot
from ckps.rules.ema_exit import EMAExit
from ckps.rules.p2.market import VN_TZ
from ckps.rules.signal_settings import SignalSettings
from ckps.services.entry_notices import receipt_text


def bars(now, count=30):
    return [dict(time=(now-timedelta(days=offset)).timestamp(), close=2000, high=2010, low=1990)
            for offset in range(count, 0, -1) if (now-timedelta(days=offset)).weekday() < 5]


def market(now, price=2000, count=30):
    symbol = '41I1GB000'
    return Snapshot(symbol, [], [], {symbol: Quote(symbol, price, at=now.timestamp())},
                    100_000_000, 0, 40_000_000, 2, 2, bars=bars(now, count))


def policy(**params):
    return Settings(exit=asdict(ExitSettings(ema_exit_enabled=True,
                    ema_exit_mode=params.get('signal_mode','REALTIME'),
                    ema_exit_interval=params.get('realtime_indicator_interval','TICK'))),
                    signals=SignalSettings(**params).to_dict()).validate()


@pytest.mark.parametrize('side,price,hit', [('LONG', 1990, True), ('LONG', 2010, False),
    ('SHORT', 2010, True), ('SHORT', 1990, False), ('LONG', 2000, False), ('SHORT', 2000, False)])
def test_e_uses_opposite_ema_relationship_for_each_direction(side, price, hit):
    now = datetime(2026, 10, 27, 10, tzinfo=VN_TZ)
    snapshot = market(now, price)
    view = EMAExit().observe(snapshot, policy(), snapshot.contract, now=now)
    position = Position.create(snapshot.contract, side, 2, 2000)
    decision = EMAExit.decision(position, view)
    assert bool(decision) == hit
    if decision:
        assert decision.reason == 'E' and decision.quantity == 2


def test_legacy_closed_mode_is_normalized_to_live_daily_close():
    now = datetime(2026, 10, 27, 10, tzinfo=VN_TZ)
    snapshot = market(now, 1990)
    observer = EMAExit()
    closed = observer.observe(snapshot, policy(signal_mode='CLOSED'), snapshot.contract, now=now)
    assert closed['ready'] and closed['fast'] < closed['slow']
    realtime = observer.observe(snapshot, policy(), snapshot.contract, now=now)
    assert realtime['fast'] < realtime['slow']


@pytest.mark.parametrize('minutes', [1, 2, 5])
def test_legacy_interval_uses_each_fresh_price_immediately_even_after_gap(minutes):
    now = datetime(2026, 10, 27, 10, 0, 10, tzinfo=VN_TZ)
    settings = policy(realtime_indicator_interval=f'{minutes}M')
    observer = EMAExit()
    snapshot = market(now, 1990)
    assert observer.observe(snapshot, settings, snapshot.contract, now=now)['fast'] < 2000
    after = now + timedelta(minutes=minutes)
    snapshot.quotes[snapshot.contract] = Quote(snapshot.contract, 2010, at=after.timestamp())
    view = observer.observe(snapshot, settings, snapshot.contract, now=after)
    assert view['ready'] and view['fast'] > view['slow']
    gap = after + timedelta(minutes=minutes*3)
    snapshot.quotes[snapshot.contract] = Quote(snapshot.contract, 1990, at=gap.timestamp())
    assert observer.observe(snapshot, settings, snapshot.contract, now=gap)['fast'] < 2000


def test_e_waits_for_valid_quote_bars_and_matching_contract():
    now = datetime(2026, 10, 27, 10, tzinfo=VN_TZ)
    observer, settings = EMAExit(), policy()
    snapshot = market(now, 1990, count=5)
    assert not observer.observe(snapshot, settings, snapshot.contract, now=now)['ready']
    snapshot.bars = bars(now)
    snapshot.quotes[snapshot.contract].at -= 300
    assert not observer.observe(snapshot, settings, snapshot.contract, now=now)['ready']
    snapshot.quotes[snapshot.contract].at = now.timestamp()
    assert not observer.observe(snapshot, settings, '41I1GC000', now=now)['ready']
    snapshot.bars = bars(now-timedelta(days=10))
    assert not observer.observe(snapshot, settings, snapshot.contract, now=now)['ready']


def test_bad_calendar_keeps_e_waiting_without_crashing_sl(system):
    from ckps.config import runtime_root
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(ema_exit_enabled=True, sl_enabled=True, sl_distance=.5))
    engine.open_manual('LONG', 1, 'MOK')
    engine.poll()
    broker.set_bars(bars(datetime.now(VN_TZ)))
    engine.arm(True)
    runtime_root().mkdir(parents=True, exist_ok=True)
    (runtime_root()/'calendar.json').write_text('{broken', encoding='utf-8')
    engine.poll(manage=False)
    assert engine.ema_snapshot(engine.latest.contract)['state'] == 'WAIT_CALENDAR'
    broker.set_price(1989)
    engine.poll()
    assert not store.positions() and store.orders()[-1].reason == 'SL'


@pytest.mark.parametrize('side,hit', [('LONG', 1990), ('SHORT', 2010)])
def test_e_closes_all_only_with_bot_permission_and_ignores_alert_switches(system, side, hit):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(ema_exit_enabled=True))
    engine.settings.signals = SignalSettings(enabled=False, sell_alert_enabled=False).to_dict()
    engine.settings.telegram_enabled = False
    engine.open_manual(side, 2, 'MOK')
    engine.poll()
    position = store.positions()[0]
    broker.set_bars(bars(datetime.now(VN_TZ)))
    broker.set_price(hit)
    engine.poll()
    assert store.positions() and len(store.orders()) == 1
    engine.set_managed(position.id, False)
    engine.arm(True)
    engine.poll()
    assert store.positions() and len(store.orders()) == 1
    engine.set_managed(position.id, True)
    engine.poll()
    assert not store.positions()
    closed = store.orders()[-1]
    assert closed.source == 'AUTO' and closed.reason == 'E' and closed.applied == 2
    notice = next(row for row in store.all('entry_notice') if row['reason'] == 'E')
    text, kind = receipt_text(notice, notice['at'])
    assert 'E / EMA' in text and kind == 'ĐÓNG / GIẢM'
    assert not store.db.execute('SELECT id FROM outbox').fetchall()


def test_new_e_branch_defaults_off_and_cannot_create_an_entry(system):
    engine, _, store = system
    assert not engine.exits().ema_exit_enabled
    engine.settings.exit = asdict(ExitSettings(ema_exit_enabled=True))
    engine.arm(True)
    engine.poll()
    assert not store.orders()


def test_disabling_e_during_broker_preflight_prevents_submission(system, monkeypatch):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(ema_exit_enabled=True))
    engine.open_manual('LONG', 1, 'MOK')
    engine.poll()
    broker.set_bars(bars(datetime.now(VN_TZ)))
    broker.set_price(1990)
    engine.poll(manage=False)
    engine.arm(True)
    submit = broker.submit
    def revoke(order, can_submit=None):
        engine.settings.exit['ema_exit_enabled'] = False
        return submit(order, can_submit)
    monkeypatch.setattr(broker, 'submit', revoke)
    engine._manage()
    assert store.positions()[0].quantity == 1
    assert store.orders()[-1].status == 'CANCELLED'
    assert not store.get('paper_order', store.orders()[-1].id)


def _rule_form_scenario():
    from ckps.models import Settings
    from ckps.rules.signal_settings import SignalSettings
    from ckps.dashboard.window import App
    from ckps.services.signal_config import write_signal_settings
    write_signal_settings(Settings(signals=SignalSettings(signal_mode='CLOSED', realtime_indicator_interval='2M').to_dict()))
    app = App(start_runtime=False)
    app.withdraw()
    try:
        assert app.settings.exit['ema_exit_mode'] == 'REALTIME'
        assert app.settings.exit['ema_exit_interval'] == 'TICK'
        rule = app.settings_dialog('E/M')
        app.update()
        assert not rule.ema_exit_enabled.get()
        rule.ema_exit_enabled.set(True)
        rule.save()
        assert app.settings.exit['ema_exit_enabled']
        rule.destroy()
        reopened = app.settings_dialog('E/M')
        app.update()
        assert reopened.ema_exit_enabled.get() and reopened._exits()['ema_exit_enabled']
    finally:
        app.close()


def test_rule_form_requires_explicit_e_opt_in_and_saves_it():
    import inspect
    import subprocess
    import sys
    code="import requests, socket\ndef forbidden(*a,**k): raise AssertionError('Offline UI only')\nrequests.Session.request=socket.socket.connect=forbidden\n"
    code+=inspect.getsource(_rule_form_scenario)+'\n_rule_form_scenario()'
    result=subprocess.run([sys.executable,'-X','utf8','-c',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_saving_signal_clock_does_not_change_independent_local_e_settings():
    from types import SimpleNamespace
    from ckps.dashboard.settings_state import save_signal_settings
    sent = []
    app = SimpleNamespace(settings=policy(), preview_only=True,
                          send=lambda *args: sent.append(args))
    original = dict(app.settings.exit)
    save_signal_settings(app, policy(signal_mode='CLOSED', realtime_indicator_interval='5M',
                                     sell_ema_fast=7, sell_ema_slow=21))
    assert app.settings.exit == original and app.settings.paper_balance == 100_000_000
    assert not sent
    assert app.settings.exit['ema_exit_mode']=='REALTIME'
    assert app.settings.exit['ema_exit_interval']=='TICK'


def test_sl_has_priority_when_sl_and_e_trigger_together(system):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(ema_exit_enabled=True, sl_enabled=True, sl_distance=.5))
    engine.open_manual('LONG', 2, 'MOK')
    engine.poll()
    broker.set_bars(bars(datetime.now(VN_TZ)))
    engine.arm(True)
    broker.set_price(1989)
    engine.poll()
    assert store.orders()[-1].reason == 'SL' and store.orders()[-1].applied == 2


def test_e_has_priority_over_partial_trailing_exit(system):
    engine, broker, store = system
    engine.settings.exit = asdict(ExitSettings(ema_exit_enabled=True, arm_enabled=True, arm_gain=1, trail_gap=.25))
    engine.open_manual('LONG', 2, 'MOK')
    engine.poll()
    history = bars(datetime.now(VN_TZ))
    for index, row in enumerate(history):
        row['close'] = 2200-index*8
    broker.set_bars(history)
    position = store.positions()[0]
    position.best = 2025
    store.save_position(position)
    broker.set_price(2014)
    engine.poll(manage=False)
    assert engine.ema_snapshot(position.symbol)['fast'] < engine.ema_snapshot(position.symbol)['slow']
    engine.arm(True)
    engine.poll()
    assert store.orders()[-1].reason == 'E' and store.orders()[-1].applied == 2
