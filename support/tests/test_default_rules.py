"""The built-in VN30 preset loads without a picker and never starts trading."""
from dataclasses import asdict
import json

import pytest

from ckps.config import read_settings, runtime_root, write_settings
from ckps.models import ExitSettings, Position, Settings, load_record
from ckps.rules.defaults import default_exit_settings, shared_exit_settings
from ckps.rules.protection import evaluate, levels
from ckps.trading.execution import Engine


def use_defaults(system):
    engine, broker, store = system
    engine.settings = broker.settings = read_settings()
    return engine, broker, store


def test_first_launch_loads_one_complete_preset_without_creating_runtime_or_a_picker():
    assert not runtime_root().exists()
    settings = read_settings()
    rules = load_record(ExitSettings, settings.exit).validate()
    assert settings.exit == default_exit_settings() == Settings().exit
    assert rules.distance_unit == 'PRICE_PERCENT'
    assert rules.sl_enabled and rules.sl_distance == .5
    assert not rules.tp_enabled and rules.tp_distance == 0
    assert rules.arm_enabled and rules.arm_gain == 1 and rules.trail_gap == .25
    assert rules.arm_policy == 'AUTO' and rules.arm_close_pct == 50 and rules.arm_basis == 'REMAINING'
    assert rules.arm_repeat and rules.arm_repeat_below_arm and rules.repeat_gap == .25
    assert rules.dynamic_enabled and rules.dynamic_policy == 'AUTO' and rules.dynamic_repeat
    assert rules.dynamic_close_pct == 50 and rules.dynamic_basis == 'REMAINING'
    assert rules.atr_start_multiplier == .5 and rules.atr_trail_multiplier == .8
    assert rules.retention_pct == 70 and not rules.retention_until_enabled
    assert not settings.telegram_enabled and not settings.entry_notifications
    assert not runtime_root().exists()
    settings.exit['sl_distance'] = 99
    assert read_settings().exit['sl_distance'] == .5  # Independent copies.


@pytest.mark.parametrize('with_empty_exit', [False, True])
def test_saved_connection_without_a_strategy_loads_the_preset(with_empty_exit):
    folder = runtime_root()
    folder.mkdir(parents=True)
    raw = {'mode': 'PAPER', 'account_no': '123', 'loan_package_id': '7', 'paper_balance': 230_000_000}
    if with_empty_exit:
        raw['exit'] = {}
    path = folder / 'settings.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    settings = read_settings()
    assert settings.exit == default_exit_settings()
    assert settings.account_no == '123' and settings.loan_package_id == '7'
    assert settings.paper_balance == 230_000_000
    assert json.loads(path.read_text(encoding='utf-8')) == raw


@pytest.mark.parametrize('disabled', [False, True])
def test_saved_user_rules_including_explicit_off_survive_restart(disabled):
    policy = asdict(ExitSettings()) if disabled else {**default_exit_settings(), 'sl_distance': .35,
        'arm_gain': .8, 'trail_gap': .2, 'repeat_gap': .15, 'arm_close_pct': 33}
    custom = Settings(exit=policy, paper_balance=180_000_000)
    write_settings(custom)
    for _ in range(2):
        loaded = read_settings()
        assert loaded.exit == shared_exit_settings(policy) and loaded.paper_balance == 180_000_000
        write_settings(loaded)


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_default_stop_and_trail_are_price_based_and_tp_never_caps_a_profitable_run(side,sign):
    rules = load_record(ExitSettings, read_settings().exit)
    position = Position.create('VN30F1M', side, 4, 2000, history_verified=True)
    assert levels(position, rules)['sl'] == 2000 - sign * 10
    assert levels(position, rules)['arm'] == 2000 + sign * 20
    assert levels(position, rules)['tp'] == 0
    assert evaluate(position, 2000 + sign * 100, rules) is None
    assert levels(position, rules)['protect'] == pytest.approx(2000 + sign * 95)
    decision = evaluate(position, 2000 + sign * 95, rules)
    assert decision.reason == 'ARM' and decision.policy == 'AUTO' and decision.quantity == 2
    stopped = Position.create('VN30F1M', side, 4, 2000, history_verified=True)
    assert evaluate(stopped, 2000 - sign * 10, rules).reason == 'SL'
    assert stopped.pnl(2000 - sign * 10) == -4_000_000


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_default_dynamic_protects_before_arm_and_the_floor_never_loosens(side,sign):
    rules = load_record(ExitSettings, read_settings().exit)
    position = Position.create('VN30F1M', side, 4, 2000, history_verified=True)
    assert evaluate(position, 2000 + sign * 12, rules, 1) is None
    floor = 2000 + sign * 8.4
    assert levels(position, rules, 1)['stage'] == 'DYN'
    assert position.floor == pytest.approx(floor)
    evaluate(position, 2000 + sign * 11, rules, 2)
    assert sign * (position.floor - floor) >= -1e-8
    decision = evaluate(position, floor, rules, 1)
    assert decision.reason == 'DYN' and decision.policy == 'AUTO' and decision.quantity == 2


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_loaded_preset_does_not_open_or_close_until_user_arms_it(system,side,sign):
    engine, broker, store = use_defaults(system)
    for _ in range(3):
        engine.poll()
    assert not store.orders() and not engine.enabled.is_set()
    engine.open_manual(side, 1, 'MOK')
    broker.set_price(2000 - sign * 10)
    engine.poll()
    assert len(store.orders()) == 1 and len(store.positions()) == 1
    engine.arm(True)
    engine.poll(); engine.poll()
    assert not store.positions() and len(store.orders()) == 2
    assert store.orders()[-1].reason == 'SL'


@pytest.mark.parametrize('side,sign', [('LONG', 1), ('SHORT', -1)])
def test_default_repeat_reduces_four_contracts_two_one_one_below_arm_without_tick_spam(system,side,sign):
    engine, broker, store = use_defaults(system)
    engine.paper_capital(200_000_000)
    engine.open_manual(side, 4, 'MOK'); engine.poll()
    engine.arm(True)
    broker.set_price(2000 + sign * 28); engine.poll()
    assert len(store.orders()) == 1
    for gain, remaining in ((23, 2), (18, 1), (13, 0)):
        broker.set_price(2000 + sign * gain)
        engine.poll(); engine.poll()
        position = store.positions()[0] if remaining else store.positions(closed=True)[0]
        assert position.quantity == remaining
        expected_count = {2: 1, 1: 2, 0: 3}[remaining]
        assert position.metrics['ARM:AUTO']['count'] == expected_count
        for _ in range(3):
            engine.poll()
        assert len(store.orders()) == expected_count + 1
        if remaining == 2:
            engine = Engine(store, broker, engine.settings)
            engine.poll()
            assert not engine.enabled.is_set()
            engine.arm(True)
    closed = store.positions(closed=True)[0]
    assert closed.realized == 7_700_000  # (2*23 + 18 + 13) * 100,000.
    assert all(o.reason == 'ARM' for o in store.orders() if o.action == 'CLOSE')


def test_builtin_preset_never_adopts_a_dnse_position_by_itself(system):
    engine, broker, store = use_defaults(system)
    store.put('paper_position', 'VN30F1M', {'symbol': 'VN30F1M', 'side': 'LONG', 'quantity': 1, 'entry': 2000})
    engine.poll()
    engine.arm(True)
    broker.set_price(1985); engine.poll()
    assert not store.positions()[0].managed and not store.orders()


def test_offline_sample_uses_exactly_the_shipped_policy():
    from ckps.dashboard.demo import demo_rules
    assert asdict(demo_rules()) == read_settings().exit
