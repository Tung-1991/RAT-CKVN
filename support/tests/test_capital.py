from dataclasses import asdict

import pytest

from ckps.models import ExitSettings, Order, Position


def test_paper_capital_can_be_changed_without_quotes_and_same_amount_is_not_added_twice(system):
    from ckps.connections.dnse.paper import PaperBroker
    from ckps.trading.execution import Engine
    engine,_,store=system
    disconnected=Engine(store,PaperBroker(store,engine.settings),engine.settings)
    for _ in range(2):disconnected.paper_capital(250_000_000)
    snapshot=disconnected.poll(manage=False)
    assert snapshot.nav==snapshot.paper_capital==250_000_000
    assert snapshot.quotes=={} and snapshot.qmax_long is None
    assert not store.orders() and not store.positions()
    assert len([row for row in store.events() if row[1]=='PAPER'])==1


def test_adjusting_paper_capital_preserves_realized_profit_fees_and_order_history(system):
    engine,broker,store=system
    engine.settings.estimated_fee_per_contract=25_000
    engine.open_manual('LONG',1,'MOK');engine.poll()
    broker.set_price(2010);engine.poll()
    engine.close_position(store.positions()[0].id,1)
    orders=[asdict(o) for o in store.orders()]
    closed=[asdict(p) for p in store.positions(closed=True)]
    engine.paper_capital(200_000_000)
    assert store.get('paper','account')['cash']==200_950_000
    assert store.get('paper','account')['capital']==200_000_000
    engine.paper_capital(50_000_000)
    assert store.get('paper','account')['cash']==50_950_000
    assert [asdict(o) for o in store.orders()]==orders
    assert [asdict(p) for p in store.positions(closed=True)]==closed


def test_reducing_paper_capital_cannot_underfund_positions_and_pending_orders(system):
    engine,broker,store=system
    engine.open_manual('LONG',1,'MOK');engine.poll()
    engine.open_manual('LONG',1,'LO',1990);engine.poll()
    before=store.get('paper','account').copy()
    with pytest.raises(ValueError,match='không đủ ký quỹ'):
        engine.paper_capital(60_000_000)
    assert store.get('paper','account')==before
    engine.paper_capital(80_000_000)
    snapshot=engine.poll(manage=False)
    assert snapshot.remaining_margin==0 and snapshot.paper_capital==80_000_000
    assert store.positions()[0].quantity==1 and len(store.orders())==2


@pytest.mark.parametrize('amount',[0,-1,float('nan'),float('inf')])
def test_invalid_paper_capital_never_changes_cash(system,amount):
    engine,broker,store=system
    before=store.get('paper','account').copy()
    with pytest.raises(ValueError):engine.paper_capital(amount)
    assert store.get('paper','account')==before and not store.orders()


def test_paper_funding_command_cannot_change_real_account(system,monkeypatch):
    engine,broker,store=system
    monkeypatch.setattr(broker,'mode','REAL')
    before=store.get('paper','account').copy()
    with pytest.raises(ValueError,match='Chỉ chỉnh vốn ảo'):
        engine.paper_capital(500_000_000)
    assert store.get('paper','account')==before


def test_risk_below_one_contract_returns_zero_not_forced_one(system):
    engine, broker, store = system
    engine.settings.risk_limit = 500_000
    engine.settings.exit = asdict(ExitSettings(sl_enabled=True, sl_distance=10))
    assert engine.preview("LONG").maximum == 0
    with pytest.raises(ValueError):
        engine.open_manual("LONG", None, "MOK")
    assert not store.orders()


def test_unmanaged_positions_consume_capital_and_contract_limit(system):
    engine, broker, store = system
    engine.settings.max_contracts = 2
    store.put("paper_position", "VN30F1M", {"symbol": "VN30F1M", "side": "LONG", "quantity": 1, "entry": 2000})
    engine.poll()
    assert not store.positions()[0].managed
    assert engine.preview("LONG").maximum == 1


def test_accepted_pending_margin_is_not_subtracted_twice(system):
    engine, broker, store = system
    engine.settings.capital_limit = 100_000_000
    engine.open_manual("LONG", 1, "LO", price=1990)
    engine.poll()
    limit = engine.preview("LONG")
    assert limit.available_budget == 60_000_000
    assert limit.maximum == 1


def test_total_risk_counts_existing_positions(system):
    engine, broker, store = system
    engine.settings.risk_limit = 1_500_000
    engine.settings.exit = asdict(ExitSettings(sl_enabled=True, sl_distance=10))
    engine.open_manual("LONG", 1, "MOK")
    engine.poll()
    assert engine.preview("LONG").maximum == 0


def test_missing_nav_does_not_fabricate_risk_budget(system):
    engine, broker, store = system
    engine.settings.risk_nav_pct = 1
    engine.latest.nav = None
    assert engine.preview("LONG").maximum == 0
    assert "NAV" in engine.preview("LONG").reason


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("pending", [False, True])
def test_scale_in_uses_existing_policy_for_risk_and_rejects_conflicting_ticket(system, side, pending):
    engine, broker, store = system
    engine.settings.risk_limit = 1_500_000
    engine.settings.exit = asdict(ExitSettings(sl_enabled=True, sl_distance=1))
    wide = asdict(ExitSettings(sl_enabled=True, sl_distance=10))
    engine.open_manual(side, 1, "LO" if pending else "MOK", price=1990 if side == "LONG" else 2010,
                       exit_settings=wide)
    engine.poll()
    assert engine.preview(side).risk_per_contract == 1_000_000
    assert engine.preview(side).maximum == 0
    before = len(store.orders())
    with pytest.raises(ValueError, match="cùng E/M"):
        engine.open_manual(side, 1, "MOK", exit_settings=engine.settings.exit)
    with pytest.raises(ValueError):
        engine.open_manual(side, 1, "MOK")
    assert len(store.orders()) == before


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_scale_in_inherits_pinned_policy_and_keeps_pending_risk_on_rule_change(system, side):
    engine, broker, store = system
    engine.settings.risk_limit = 3_000_000
    wide = asdict(ExitSettings(sl_enabled=True, sl_distance=10))
    engine.open_manual(side, 1, "MOK", exit_settings=wide)
    engine.poll()
    order = engine.open_manual(side, 1, "LO", price=1990 if side == "LONG" else 2010)
    assert order.exit_settings == wide
    engine.settings.exit = asdict(ExitSettings(sl_enabled=True, sl_distance=1))
    assert engine.preview(side).risk_per_contract == 1_000_000
    engine.cancel(order.id)
    engine.poll()
    filled = engine.open_manual(side, 1, "MOK")
    engine.poll()
    position = store.positions()[0]
    assert filled.exit_settings == wide and position.exit_overrides == wide
    assert position.quantity == 2


def test_ticket_preview_inherits_existing_ckps_em_before_applying_override():
    from types import SimpleNamespace
    from ckps.dashboard.actions import DashboardActionsMixin
    class Value:
        def __init__(self, value): self.value = value
        def get(self): return self.value
    settings = SimpleNamespace(alias='VN30F1M', exit=asdict(ExitSettings(distance_unit='PNL_PERCENT',sl_enabled=True, sl_distance=1)))
    wide = asdict(ExitSettings(distance_unit='PNL_PERCENT',sl_enabled=True, sl_distance=10))
    app = SimpleNamespace(settings=settings, ticket_sl=Value('RULE'), ticket_tp=Value('RULE'),
        view={'contract':'VN30F1M', 'positions':[{'symbol':'VN30F1M','exit_overrides':wide}]})
    rules, override = DashboardActionsMixin.ticket_rules(app, 2000)
    assert asdict(rules) == wide and override is None
    app.ticket_tp = Value('20')
    rules, override = DashboardActionsMixin.ticket_rules(app, 2000)
    assert rules.sl_distance == 10 and override['tp_distance'] == 20
    app.ticket_tp = Value('RULE')
    app.view['positions'][0]['exit_overrides'] = None
    app.view['orders'] = [{'symbol':'VN30F1M','action':'OPEN','status':'WORKING','exit_settings':wide}]
    rules, _ = DashboardActionsMixin.ticket_rules(app, 2000)
    assert rules.sl_distance == 1  # The live position's policy is authoritative.
