"""Invalid tickets must clear estimates from the previous valid ticket."""
from types import SimpleNamespace

import pytest

from ckps.dashboard.mayin.controller import MayinController
from ckps.models import Settings, ExitSettings


def ticket():
    def value(text):
        return SimpleNamespace(text=text, get=lambda: text)
    class Label:
        text = 'OLD ESTIMATE'
        def cget(self, key):
            return getattr(self, key, None)
        def configure(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    app = SimpleNamespace(settings=Settings(), ticket_sl=value('RULE'), qty=value('2'), limit=value('2000'), kind=value('LO'),
        view={'account': {'qmax_long': 2, 'margin_per_contract': 40_000_000, 'package_fees': {'open': 2000}}})
    app.ticket_rules = lambda entry: (ExitSettings(**app.settings.exit), None)
    app.ticket_capacity = lambda *args: SimpleNamespace(margin_per_contract=40_000_000, maximum=2)
    for name in ('lbl_tp_preview', 'lbl_sl_preview', 'lbl_fee_preview', 'lbl_order_value', 'lbl_fee_title', 'lbl_order_value_title','lbl_sl_title','lbl_tp_title'):
        setattr(app, name, Label())
    return app


@pytest.mark.parametrize('field,text', [('limit', ''), ('limit', 'x'), ('limit', 'nan'), ('limit', 'inf'),
                                     ('limit', '-2000'), ('limit', '0'), ('qty', 'x'), ('qty', '0'), ('qty', '-1')])
def test_invalid_ticket_clears_previous_money_estimates(field, text):
    app = ticket()
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_tp_preview.text == 'OFF' and app.lbl_sl_preview.text == '-2,000,000'
    getattr(app, field).get = lambda: text
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_tp_preview.text == 'OFF'
    assert all(getattr(app, name).text == '—' for name in ('lbl_sl_preview', 'lbl_fee_preview', 'lbl_order_value'))


def test_unknown_auto_quantity_does_not_show_free_fees_or_zero_sl():
    app = ticket()
    app.qty.get = lambda: ''
    app.ticket_capacity = lambda *args: SimpleNamespace(margin_per_contract=None, maximum=0)
    app.view['account'].update(qmax_long=None, margin_per_contract=None)
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_tp_preview.text == 'OFF' and app.lbl_sl_preview.text == '-1,000,000'
    assert app.lbl_sl_title.text=='SL · đ/HĐ'
    assert app.lbl_fee_preview.text == '2,000' and app.lbl_order_value.text == '—'
    assert app.lbl_fee_title.text=='PHÍ GÓI/HĐ'


def test_auto_preview_for_an_existing_short_uses_short_buying_power():
    app = ticket()
    app.qty.get = lambda: ''
    app.view.update(contract='VN30F1M', positions=[{'symbol':'VN30F1M','side':'SHORT'}])
    app.view['account'].update(qmax_long=0, qmax_short=2)
    app.ticket_capacity = lambda side, *args: SimpleNamespace(margin_per_contract=40_000_000, maximum=2 if side=='SHORT' else 0)
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_sl_preview.text == '-2,000,000' and app.lbl_fee_preview.text == '4,000'
    assert app.lbl_order_value.text == '80,004,000 đ'


def test_auto_preview_does_not_assume_long_when_long_and_short_buying_power_differ():
    app = ticket()
    app.qty.get = lambda: ''
    app.view['account'].update(qmax_long=1, qmax_short=2)
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_sl_preview.text == '-1,000,000' and app.lbl_order_value.text == '—'
    assert app.lbl_fee_preview.text == '2,000' and app.lbl_sl_title.text=='SL · đ/HĐ'
    assert app.lbl_tp_preview.text == 'OFF'


def test_closed_market_auto_zero_shows_one_contract_estimates_without_granting_buying_power():
    app=ticket();app.qty.get=lambda:''
    app.view['account'].update(qmax_long=0,qmax_short=0)
    app.ticket_capacity=lambda *args:SimpleNamespace(margin_per_contract=40_000_000,maximum=0)
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_sl_preview.text=='-1,000,000' and app.lbl_sl_title.text=='SL · đ/HĐ'
    assert app.lbl_order_value.text=='—' and app.lbl_order_value_title.text=='KÝ QUỸ · CHỜ HĐ'
    assert app.view['account']['qmax_long']==0 and app.qty.get()==''


def test_tier_estimate_is_labelled_and_missing_is_distinct_from_zero():
    app=ticket()
    app.view['account']['package_fees']={'open':None,'estimated_open':1000}
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_fee_preview.text=='≤ 2,000' and app.lbl_fee_title.text=='ƯỚC PHÍ GÓI · đ'
    assert app.lbl_order_value.text=='≤ 80,002,000 đ'
    app.view['account']['package_fees']={'open':None}
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_fee_preview.text=='CHỜ DNSE' and app.lbl_order_value.text=='—'
    app.view['account']['package_fees']={'open':0}
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_fee_preview.text=='0' and app.lbl_order_value.text=='80,000,000 đ'
