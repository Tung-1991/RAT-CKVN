# -*- coding: utf-8 -*-
import pandas as pd

from signals.signal_generator import SignalGenerator


def _ohlcv(rows=250):
    close = [100.0 + i * 0.05 for i in range(rows)]
    return pd.DataFrame(
        {
            "open": [value - 0.1 for value in close],
            "high": [value + 0.3 for value in close],
            "low": [value - 0.3 for value in close],
            "close": close,
            "volume": [1000.0 + i for i in range(rows)],
        }
    )


def test_all_registered_indicators_accept_standard_ohlcv():
    generator = SignalGenerator()
    expected = {
        "rsi", "macd", "bollinger_bands", "ema", "ema_cross", "stochastic",
        "atr", "adx", "supertrend", "psar", "volume", "multi_candle", "candle",
        "swing_point", "fibonacci", "pivot_points", "simple_breakout",
    }
    assert set(generator.indicator_map) == expected

    frame = _ohlcv()
    context_indicators = {"fibonacci", "pivot_points", "swing_point", "simple_breakout"}
    for name, func in generator.indicator_map.items():
        if name in context_indicators:
            result = func(frame.copy(), {}, {"atr_G2": 1.0, "symbol": "FPT"})
        else:
            result = func(frame.copy(), {})
        assert result in (-1, 0, 1), name


def test_group_evaluation_uses_closed_bar_and_group_params():
    generator = SignalGenerator()
    observed = {}

    def indicator(frame, params):
        observed["rows"] = len(frame)
        observed["params"] = params
        return 1

    generator.indicator_map = {"probe": indicator}
    context = {}
    result = generator._evaluate_group(
        "G2",
        {
            "probe": {
                "params": {"period": 10},
                "group_params": {"G2": {"period": 21}},
                "trigger_mode": "STRICT_CLOSE",
            }
        },
        _ohlcv(5),
        context,
        "ANY",
        {"max_opposite": 0, "max_none": 0},
    )

    assert result == 1
    assert observed == {"rows": 4, "params": {"period": 21}}
    assert context["group_details"]["G2"]["status"] == 1


def test_generate_signal_veto_pipeline(monkeypatch):
    generator = SignalGenerator()
    generator.indicator_map = {"probe": lambda _frame, _params: 1}
    settings = {
        "FORCE_ANY_MODE": True,
        "MASTER_EVAL_MODE": "VETO",
        "MIN_MATCHING_VOTES": 1,
        "indicators": {
            "probe": {"active": True, "groups": ["G2"], "active_modes": ["ANY"], "params": {}}
        },
        "voting_rules": {
            "G0": {"master_rule": "IGNORE"},
            "G1": {"master_rule": "IGNORE"},
            "G2": {"master_rule": "FIX", "max_opposite": 0, "max_none": 0},
            "G3": {"master_rule": "IGNORE"},
        },
    }
    monkeypatch.setattr(generator, "_get_brain_settings", lambda _symbol=None: settings)
    context = {}

    result = generator.generate_signal_v4({"G2": _ohlcv(20)}, context, symbol="FPT")

    assert result == 1
    assert context["market_mode"] == "ANY"
    assert context["group_signals"]["G2"] == 1
    assert context["block_reason"] == "OK / Ready"


def test_generate_signal_voting_requires_configured_group_count(monkeypatch):
    generator = SignalGenerator()
    generator.indicator_map = {"probe": lambda _frame, _params: 1}
    rules = {
        group: {"master_rule": "PASS", "max_opposite": 0, "max_none": 0}
        for group in ("G0", "G1", "G2", "G3")
    }
    settings = {
        "FORCE_ANY_MODE": True,
        "MASTER_EVAL_MODE": "VOTING",
        "MIN_MATCHING_VOTES": 3,
        "indicators": {
            "probe": {
                "active": True,
                "groups": ["G1", "G2", "G3"],
                "active_modes": ["ANY"],
                "params": {},
            }
        },
        "voting_rules": rules,
    }
    monkeypatch.setattr(generator, "_get_brain_settings", lambda _symbol=None: settings)
    frames = {group: _ohlcv(20) for group in ("G1", "G2", "G3")}

    assert generator.generate_signal_v4(frames, {}, symbol="FPT") == 1
