"""ATR provenance and fixed DYNAMIC defaults agree with execution."""
from dataclasses import asdict
from datetime import datetime, timedelta

import pytest

from ckps.config import read_settings, write_settings
from ckps.dashboard.mayin.atr_preview import atr_preview
from ckps.dashboard.mayin.signal_preview import signal_preview
from ckps.models import ExitSettings, Settings
from ckps.services.technical_notifications import VN, completed_atr_snapshot


NOW = datetime(2026, 10, 30, 10, tzinfo=VN)


def candles():
    return [{'time': (NOW.date() - timedelta(days=20-i)).isoformat(),
             'high': 2010, 'low': 1990, 'close': 2000, 'closed': True} for i in range(20)]


def test_atr_snapshot_filters_current_future_unclosed_duplicates_and_invalid_ohlc():
    rows = candles()
    expected = completed_atr_snapshot(rows, NOW)
    assert expected == {'period': 14, 'pct': 1., 'count': 20, 'as_of': '2026-10-29'}
    extra = [dict(rows[-1]), None,
             {'date': '2026-10-30', 'high': 4000, 'low': 1000, 'close': 3000, 'closed': True},
             {'date': '2026-10-31', 'high': 4000, 'low': 1000, 'close': 3000, 'closed': True},
             {'date': '2026-10-28', 'high': 4000, 'low': 1000, 'close': 3000, 'closed': False},
             {'date': '2026-10-29', 'high': 1990, 'low': 2010, 'close': 2000},
             {'date': '2026-10-29', 'high': float('nan'), 'low': 1990, 'close': 2000}]
    assert completed_atr_snapshot(list(reversed(rows + extra)), NOW) == expected
    # Epoch milliseconds and timezone-offset ISO dates identify the same VN session.
    rows[-1]['time'] = datetime(2026, 10, 29, tzinfo=VN).timestamp() * 1000
    assert completed_atr_snapshot(rows, NOW) == expected
    rows[-1]['time'] = '2026-10-28T17:00:00Z'
    assert completed_atr_snapshot(rows, NOW) == expected


def test_missing_atr_is_unknown_and_last_session_does_not_imply_enough_candles():
    assert completed_atr_snapshot([], NOW) == {'period': 14, 'pct': None, 'count': 0, 'as_of': None}
    data = completed_atr_snapshot(candles()[-13:], NOW)
    assert data['pct'] is None and data['as_of'] == '2026-10-29'
    assert not atr_preview({'contract': 'VN30F1M', 'atr14': {'contract': 'VN30F1M', **data}})[2]


def test_completed_atr_preview_remains_read_only_when_live_quote_is_stale():
    view = {'contract': 'VN30F1M', 'atr14': {'contract': 'VN30F1M', **completed_atr_snapshot(candles(), NOW)},
            'quotes': {'VN30F1M': {'symbol': 'VN30F1M', 'last': 2000, 'at': NOW.timestamp()-60}}}
    before = repr(view)
    title, detail, ready = atr_preview(view)
    assert ready and title == 'ATR14 · 1,00% · phiên 29/10/2026'
    assert detail == 'Bắt đầu +0,50% · lùi ATR 0,80% · giữ 70% lãi'
    assert all(result[0] == 'CHỜ' for result in signal_preview(view, now=NOW.timestamp()))
    assert repr(view) == before


@pytest.mark.parametrize('changes', [dict(contract='OTHER'), dict(as_of=None), dict(period=20),
    dict(count=13), dict(count=float('nan')), dict(pct=None), dict(pct=float('inf')), dict(pct=0)])
def test_preview_requires_matching_contract_and_completed_candle_provenance(changes):
    data = {'contract': 'VN30F1M', **completed_atr_snapshot(candles(), NOW), **changes}
    assert not atr_preview({'contract': 'VN30F1M', 'atr14': data})[2]
    # A bare legacy percent must not be presented as a verified ATR snapshot.
    assert not atr_preview({'contract': 'VN30F1M', 'atr14_pct': 1.})[2]


def test_fixed_dynamic_internals_replace_old_controls_without_changing_user_thresholds(system):
    engine, _, store = system
    original = asdict(ExitSettings(sl_enabled=False, sl_distance=.35, arm_enabled=False,
        arm_gain=1.2, trail_gap=.2, repeat_gap=.3, arm_repeat=False, arm_repeat_below_arm=False,
        dynamic_enabled=False, dynamic_repeat=False, atr_start_enabled=False, atr_start_multiplier=2,
        atr_trail_enabled=False, atr_trail_multiplier=3, retention_enabled=False, retention_pct=30,
        retention_until_enabled=True, retention_until=.5))
    write_settings(Settings(exit=original))
    engine.settings = read_settings()
    actual = asdict(engine.exits(None))
    for key in ('sl_enabled', 'sl_distance', 'arm_enabled', 'arm_gain', 'trail_gap',
                'repeat_gap', 'arm_repeat', 'dynamic_enabled', 'dynamic_repeat'):
        assert actual[key] == original[key]
    fixed = {'tp_enabled': False, 'tp_distance': 0, 'atr_start_enabled': True,
             'atr_start_multiplier': .5, 'atr_trail_enabled': True, 'atr_trail_multiplier': .8,
             'retention_enabled': True, 'retention_pct': 70,
             'retention_until_enabled': False, 'retention_until': 0, 'arm_repeat_below_arm': True}
    assert {key: actual[key] for key in fixed} == fixed
    assert not engine.enabled.is_set() and not store.orders()


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_missing_atr_does_not_invent_dynamic_trigger_and_sl_still_works(system, side, sign):
    engine, broker, store = system
    engine.settings = Settings()  # Shipped preset, no completed candles available.
    engine.open_manual(side, 1, 'MOK'); engine.poll(); engine.arm(True)
    assert engine.atr_snapshot(engine.latest.contract)['pct'] is None
    broker.set_price(2000 + sign*12); engine.poll()
    broker.set_price(2000 + sign*8); engine.poll()
    assert store.positions()[0].quantity == 1 and len(store.orders()) == 1
    broker.set_price(2000 - sign*10); engine.poll(); engine.poll()
    assert not store.positions()
    assert store.orders()[-1].reason == 'SL'
