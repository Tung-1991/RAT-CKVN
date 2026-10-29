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
        def configure(self, **kwargs):
            self.text = kwargs['text']
    app = SimpleNamespace(settings=Settings(), ticket_sl=value('RULE'), qty=value('2'), limit=value('2000'), kind=value('LO'),
        view={'account': {'qmax_long': 2, 'margin_per_contract': 40_000_000, 'package_fees': {'open': 2000}}})
    app.ticket_rules = lambda entry: (ExitSettings(**app.settings.exit), None)
    app.ticket_capacity = lambda *args: SimpleNamespace(margin_per_contract=40_000_000, maximum=2)
    for name in ('lbl_tp_preview', 'lbl_sl_preview', 'lbl_fee_preview', 'lbl_order_value', 'lbl_fee_title', 'lbl_order_value_title'):
        setattr(app, name, Label())
    return app


@pytest.mark.parametrize('field,text', [('limit', ''), ('limit', 'x'), ('limit', 'nan'), ('limit', 'inf'),
                                     ('limit', '-2000'), ('limit', '0'), ('qty', 'x'), ('qty', '0'), ('qty', '-1')])
def test_invalid_ticket_clears_previous_money_estimates(field, text):
    app = ticket()
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_tp_preview.text == 'OFF' and app.lbl_sl_preview.text == '-2,000,000 đ'
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
    assert app.lbl_tp_preview.text == 'OFF' and app.lbl_sl_preview.text == '—'
    assert app.lbl_fee_preview.text == 'CHỜ HĐ' and app.lbl_order_value.text == '—'


def test_auto_preview_for_an_existing_short_uses_short_buying_power():
    app = ticket()
    app.qty.get = lambda: ''
    app.view.update(contract='VN30F1M', positions=[{'symbol':'VN30F1M','side':'SHORT'}])
    app.view['account'].update(qmax_long=0, qmax_short=2)
    app.ticket_capacity = lambda side, *args: SimpleNamespace(margin_per_contract=40_000_000, maximum=2 if side=='SHORT' else 0)
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_sl_preview.text == '-2,000,000 đ' and app.lbl_fee_preview.text == '4,000 đ'
    assert app.lbl_order_value.text == '80,004,000 đ'


def test_auto_preview_does_not_assume_long_when_long_and_short_buying_power_differ():
    app = ticket()
    app.qty.get = lambda: ''
    app.view['account'].update(qmax_long=1, qmax_short=2)
    MayinController._refresh_ticket_preview(app)
    assert app.lbl_sl_preview.text == '—' and app.lbl_order_value.text == '—'
    assert app.lbl_fee_preview.text == 'CHỜ HĐ'
    assert app.lbl_tp_preview.text == 'OFF'
