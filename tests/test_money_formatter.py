# -*- coding: utf-8 -*-

import config
from core.money import format_vnd, money_unit_note, parse_money_unit_label


def test_format_vnd_default_thousand_unit(monkeypatch):
    monkeypatch.setattr(config, "MONEY_DISPLAY_UNIT", "K_VND", raising=False)

    assert format_vnd(100000000, suffix=True) == "100,000 nghìn VND"
    assert format_vnd(2358240, signed=True) == "+2,358"
    assert money_unit_note() == "Đơn vị tiền: nghìn VND"


def test_format_vnd_full_and_million(monkeypatch):
    monkeypatch.setattr(config, "MONEY_DISPLAY_UNIT", "VND", raising=False)
    assert format_vnd(1000000, suffix=True) == "1,000,000 VND"

    monkeypatch.setattr(config, "MONEY_DISPLAY_UNIT", "M_VND", raising=False)
    assert format_vnd(1000000, suffix=True) == "1.00 triệu VND"
    assert parse_money_unit_label("triệu VND") == "M_VND"
