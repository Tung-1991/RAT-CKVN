from dataclasses import asdict, replace

import pytest

from ckps.models import ExitSettings, Position
from ckps.rules.calculations import protect_level
from ckps.rules.protection import close_quantity, evaluate, levels


@pytest.mark.parametrize("side,stop,hit", [("LONG", 1990, 1989), ("SHORT", 2010, 2011)])
def test_stop_loss_symmetric(side, stop, hit):
    p = Position.create("VN30F1M", side, 3, 2000, history_verified=True)
    rule = ExitSettings(distance_unit='POINTS', sl_enabled=True, sl_distance=10)
    assert levels(p, rule)["sl"] == stop
    decision = evaluate(p, hit, rule)
    assert (decision.reason, decision.quantity) == ("SL", 3)


@pytest.mark.parametrize("side,target", [("LONG", 2020), ("SHORT", 1980)])
def test_take_profit_symmetric(side, target):
    p = Position.create("VN30F1M", side, 2, 2000, history_verified=True)
    rule = ExitSettings(distance_unit='POINTS', tp_enabled=True, tp_distance=20)
    assert evaluate(p, target, rule).reason == "TP"


@pytest.mark.parametrize("side,best,hit,expected", [("LONG", 2020, 2015, 2015), ("SHORT", 1980, 1985, 1985)])
def test_point_trailing_and_monotonic_floor(side, best, hit, expected):
    p = Position.create("VN30F1M", side, 3, 2000, history_verified=True)
    rule = ExitSettings(distance_unit='POINTS', arm_enabled=True, arm_gain=10, trail_gap=5)
    assert evaluate(p, best, rule) is None
    assert p.floor == pytest.approx(expected)
    decision = evaluate(p, hit, rule)
    assert decision.reason == "ARM"
    assert p.floor == pytest.approx(expected)


@pytest.mark.parametrize("mfe", [1.5, 3, 6, 9, 12])
def test_long_percent_adapter_matches_original_mayintien(mfe):
    p = Position.create("VN30F1M", "LONG", 2, 100, history_verified=True)
    p.best = 100 + mfe
    rule = ExitSettings(distance_unit="PERCENT", sl_enabled=True, sl_distance=3,
        arm_enabled=True, arm_gain=7, trail_gap=2.8, dynamic_enabled=True,
        retention_until=4.5)
    actual = levels(p, rule, 2.4)
    original = protect_level(100, mfe, 7, 2.8, dynamic_enabled=True, sl_price=97,
        atr_pct=2.4, atr_multiplier=.8, atr_activation_multiplier=.55,
        retention_pct=72, retention_until_pct=4.5)
    assert actual["protect"] == pytest.approx(original.trigger_price if original.active else 0)


def test_short_percent_trail_uses_entry_cost():
    p = Position.create("VN30F1M", "SHORT", 2, 2000, history_verified=True)
    p.best = 1900
    rule = ExitSettings(distance_unit="PERCENT", arm_enabled=True, arm_gain=3, trail_gap=1)
    assert levels(p, rule)["protect"] == pytest.approx(1920)


@pytest.mark.parametrize("side,best,loss", [("LONG", 2020, 1990), ("SHORT", 1980, 2010)])
def test_protect_never_closes_at_price_loss(side, best, loss):
    p = Position.create("VN30F1M", side, 2, 2000, history_verified=True)
    rule = ExitSettings(distance_unit='POINTS', arm_enabled=True, arm_gain=10, trail_gap=5)
    evaluate(p, best, rule)
    assert evaluate(p, loss, rule) is None


@pytest.mark.parametrize("side,best,hit,second", [("LONG", 2020, 2015, 2010), ("SHORT", 1980, 1985, 1990)])
def test_repeat_requires_full_adverse_step(side, best, hit, second):
    p = Position.create("VN30F1M", side, 5, 2000, history_verified=True)
    rule = ExitSettings(distance_unit='POINTS', arm_enabled=True, arm_gain=10, trail_gap=5, arm_repeat=True, repeat_gap=5)
    evaluate(p, best, rule)
    assert evaluate(p, hit, rule)
    p.metrics["ARM:AUTO"] = {"count": 1, "anchor": hit}
    assert evaluate(p, hit, rule) is None
    assert evaluate(p, second, rule)


@pytest.mark.parametrize("qty,pct,basis,expected", [(1, 33, "REMAINING", 1), (3, 33, "REMAINING", 1),
    (10, 33, "REMAINING", 3), (6, 33, "ORIGINAL", 3), (2, 100, "ORIGINAL", 2)])
def test_integer_contract_fraction(qty, pct, basis, expected):
    assert close_quantity(qty, 10, pct, basis) == expected


def test_dynamic_no_atr_does_not_invent_start():
    p = Position.create("VN30F1M", "LONG", 1, 2000, history_verified=True)
    rule = ExitSettings(distance_unit='POINTS', dynamic_enabled=True)
    evaluate(p, 2020, rule, 0)
    assert p.floor == 0


def test_dynamic_retention_without_atr_start_is_supported():
    p = Position.create("VN30F1M", "LONG", 1, 2000, history_verified=True)
    rule = ExitSettings(distance_unit='POINTS', dynamic_enabled=True, atr_start_enabled=False,
                        atr_trail_enabled=False, retention_until_enabled=False)
    evaluate(p, 2020, rule)
    assert p.floor == pytest.approx(2014.4)
    assert evaluate(p, 2014, rule).policy == "ALERT"


def test_unverified_history_disables_trailing_but_not_sl():
    p = Position.create("VN30F1M", "LONG", 1, 2000)
    rule = ExitSettings(distance_unit='POINTS', sl_enabled=True, sl_distance=10, arm_enabled=True, arm_gain=10, trail_gap=5)
    evaluate(p, 2020, rule)
    assert evaluate(p, 2015, rule) is None
    assert evaluate(p, 1990, rule).reason == "SL"


@pytest.mark.parametrize("side,best,hit", [("LONG", 2020, 2015), ("SHORT", 1980, 1985)])
@pytest.mark.parametrize("anchor", [0, float("nan"), float("inf")])
def test_repeat_without_finite_anchor_never_unblocks(side, best, hit, anchor):
    p = Position.create("VN30F1M", side, 3, 2000, history_verified=True)
    rule = ExitSettings(distance_unit='POINTS', arm_enabled=True, arm_gain=10, trail_gap=5, arm_repeat=True, repeat_gap=5)
    evaluate(p, best, rule)
    p.metrics["ARM:AUTO"] = {"count": 1, "anchor": anchor}
    assert evaluate(p, hit, rule) is None
