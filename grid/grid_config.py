# -*- coding: utf-8 -*-
"""Default GRID settings and identity constants."""

GRID_COMMENT_PREFIX = "[GRID]"
GRID_ENTRY_COMMENT = "[GRID]_ENTRY"
GRID_CHILD_COMMENT = "[GRID]_CHILD"
GRID_LOG_PREFIX = "[GRID]"

GRID_SETTINGS_FILE = "grid_settings.json"
GRID_STATE_FILE = "grid_state.json"

DEFAULT_GRID_SETTINGS = {
    "ENABLED": False,
    "WATCHLIST": [],
    "GRID_SCAN_INTERVAL_SECONDS": 5,
    "GRID_SIGNAL_SOURCE": "OFF",
    "DYNAMIC_MODE_ENABLED": True,
    "NONE_POLICY": "NEUTRAL",
    "DEFAULT_MANUAL_MODE": "NEUTRAL",
    "MANUAL_BYPASS_SIGNAL": False,
    "GRID_TIMEFRAME_GROUP": "G2",
    "TREND_FILTER_GROUP": "G1",
    "BOUNDARY_MODE": "HYBRID",
    "OUT_OF_RANGE_POLICY": "STOP",
    "MANUAL_UPPER_BOUNDARY": 0.0,
    "MANUAL_LOWER_BOUNDARY": 0.0,
    "GRID_TYPE": "ATR_DYNAMIC",
    "GRID_COUNT": 10,
    "GEOMETRIC_STEP_PERCENT": 1.0,
    "SPACING_ATR_MULTIPLIER": 1.0,
    "TAKE_PROFIT_SPACING_MULTIPLIER": 0.8,
    "FIXED_LOT": 0.01,
    "SYMBOL_LOT_OVERRIDES": {},
    "MAX_GRID_ORDERS": 5,
    "MAX_TOTAL_LOT": 0.05,
    "MAX_BASKET_DRAWDOWN": 20.0,
    "MAX_BASKET_DRAWDOWN_UNIT": "USD",
    "BASKET_TP_USD": 0.0,
    "BASKET_SL_USD": 0.0,
    "GRID_STOP_LOSS_PRICE": 0.0,
    "GRID_TAKE_PROFIT_PRICE": 0.0,
    "GRID_MAX_DAILY_LOSS": 0.0,
    "GRID_MAX_TRADES_PER_DAY": 0,
    "CHECK_PING": True,
    "MAX_PING_MS": 150,
    "CHECK_SPREAD": True,
    "MAX_SPREAD_POINTS": 150,
    "COOLDOWN_SECONDS": 900,
    "LEVEL_REUSE": True,
    "REOPEN_COOLDOWN_SECONDS": 900,
    "STOP_ON_BREAKOUT": True,
    "STOP_NEW_MARKET_MODES": ["TREND", "BREAKOUT"],
    "GRID_SIGNAL_CONFIG": {},
    "NOTES": "GRID V1 test execution. Market orders only.",
}

DEFAULT_GRID_STATE = {
    "active_sessions": {},
    "grid_baskets": {},
    "grid_child_to_parent": {},
    "last_grid_action_times": {},
    "level_reopen_counts": {},
    "last_preview": {},
    "last_decision": {},
    "last_decision_log_keys": {},
    "grid_active_tickets": [],
    "date": "",
    "grid_pnl_today": 0.0,
    "grid_trades_today": 0,
    "grid_daily_loss_count": 0,
}


def is_grid_comment(comment: str) -> bool:
    return GRID_COMMENT_PREFIX in str(comment or "")


def is_grid_position(pos, grid_magic=None) -> bool:
    if pos is None:
        return False
    if grid_magic is not None and getattr(pos, "magic", None) == grid_magic:
        return True
    return is_grid_comment(getattr(pos, "comment", ""))
