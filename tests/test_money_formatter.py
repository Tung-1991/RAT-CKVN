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


def test_unit_display_round_trip():
    # UI hien "VND", config luu "USD" (di san MT5) — map 2 chieu khong duoc lech
    from core.money import unit_from_display, unit_to_display

    assert unit_to_display("USD") == "VND"
    assert unit_from_display("VND") == "USD"
    # Cac unit khac giu nguyen ca 2 chieu
    for u in ("R", "%Equity", "PERCENT", "POINT", "ATR", "%R"):
        assert unit_to_display(u) == u
        assert unit_from_display(u) == u
    # Round-trip: gia tri cu tu settings -> display -> save lai van la "USD"
    assert unit_from_display(unit_to_display("USD")) == "USD"
    # None/rong: to_display mac dinh VND, from_display mac dinh USD
    assert unit_to_display(None) == "VND"
    assert unit_from_display(None) == "USD"


def test_money_input_scale_round_trip():
    # O nhap tien theo NGHIN VND, file luu dong nguyen con; chi scale khi unit la tien
    from core.money import money_input_from_display, money_input_to_display

    # Luu 500000 dong -> hien "500" (nghin); nhap "500" -> luu 500000
    assert money_input_to_display(500000, "USD") == "500"
    assert money_input_to_display(500000, "VND") == "500"
    assert money_input_from_display("500", "VND") == 500000.0
    # So le: 5787 dong -> "5.787" nghin va nguoc lai
    assert money_input_to_display(5787, "USD") == "5.787"
    assert abs(money_input_from_display("5.787", "VND") - 5787.0) < 1e-6
    # Unit khong phai tien -> giu nguyen so
    for u in ("R", "%Equity", "PERCENT", "POINT", "ATR"):
        assert money_input_to_display(0.5, u) == "0.5"
        assert money_input_from_display("0.5", u) == 0.5
    # Round-trip settings cu (dong) qua UI khong doi gia tri
    v = money_input_from_display(money_input_to_display(25000, "USD"), "VND")
    assert v == 25000.0
    # Input rac -> 0
    assert money_input_from_display("", "VND") == 0.0
    assert money_input_to_display(None, "VND") == "0"
