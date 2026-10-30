"""Saved DYNAMIC coefficients and repeat permission change actual exits."""
import pytest

from ckps.config import read_settings, write_settings
from ckps.models import Settings


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
def test_custom_dynamic_start_and_retention_drive_real_decisions(system,side,sign):
    engine,broker,store=system
    values={**Settings().exit,'arm_gain':2,'atr_start_multiplier':.9,
            'atr_trail_multiplier':1.2,'retention_pct':50,'dynamic_repeat':False}
    write_settings(Settings(exit=values))
    engine.settings=read_settings()
    engine._atr=lambda _:1.
    engine.paper_capital(200_000_000)
    engine.open_manual(side,4,'MOK');engine.poll();engine.arm(True)
    broker.set_price(2000+sign*12);engine.poll()
    assert store.positions()[0].floor==0  # Default START .5 would already protect.
    broker.set_price(2000+sign*20);engine.poll()
    assert store.positions()[0].floor==pytest.approx(2000+sign*10)
    broker.set_price(2000+sign*14);engine.poll()
    assert len(store.orders())==1  # Default 70% retention would close here.
    broker.set_price(2000+sign*10);engine.poll();engine.poll()
    assert store.positions()[0].quantity==2 and store.orders()[-1].reason=='DYN'


@pytest.mark.parametrize('side,sign',[('LONG',1),('SHORT',-1)])
@pytest.mark.parametrize('repeat_below',[False,True])
def test_repeat_below_arm_setting_controls_followup_reductions(system,side,sign,repeat_below):
    engine,broker,store=system
    write_settings(Settings(exit={**Settings().exit,'dynamic_enabled':False,
                                  'arm_repeat_below_arm':repeat_below}))
    engine.settings=read_settings()
    engine.paper_capital(200_000_000)
    engine.open_manual(side,4,'MOK');engine.poll();engine.arm(True)
    for gain in (28,23):broker.set_price(2000+sign*gain);engine.poll();engine.poll()
    assert store.positions()[0].quantity==2
    broker.set_price(2000+sign*18);engine.poll();engine.poll()
    assert store.positions()[0].quantity==(1 if repeat_below else 2)
    for _ in range(3):engine.poll()
    assert len(store.orders())==(3 if repeat_below else 2)
