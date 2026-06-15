# -*- coding: utf-8 -*-
"""Default HEDGE Dual settings and identity constants."""

HEDGE_COMMENT_PREFIX = "[HEDGE]"
HEDGE_BUY_COMMENT = "HEDGE_BUY"
HEDGE_SELL_COMMENT = "HEDGE_SELL"

HEDGE_SETTINGS_FILE = "hedge_settings.json"
HEDGE_STATE_FILE = "hedge_state.json"

DEFAULT_HEDGE_SETTINGS = {
    "ENABLED": False,
    "HEDGE_SCAN_INTERVAL_SECONDS": 2,
    "HEDGE_LOG_COOLDOWN_SECONDS": 300,
    "WATCHLIST": [],
    "USE_SIGNAL_FILTER": False,
    "HEDGE_SIGNAL_RULE": "SANDBOX_SIGNAL",
    "USE_ENTRY_EXIT_FILTER": False,
    "HEDGE_ENTRY_RULE": "SWING_REJECTION",
    "HEDGE_EE_SL_RULE": "MATCH_ENTRY",
    "HEDGE_EE_TP_RULE": "MATCH_ENTRY",
    "USE_HEDGE_SLTP": True,
    "HEDGE_SL_RULE": "BASE_SL_ATR",
    "HEDGE_TP_RULE": "RR",
    "USE_TSL": True,
    "HEDGE_TSL_MODE": "BE+STEP_R+SWING",
    "SURVIVOR_PROTECT": "BE_FEE",
    "LOT_MODE": "FIXED",
    "FIXED_LOT": 0.1,
    "RISK_PERCENT_PER_PAIR": 0.5,
    "MAX_LOT_CAP": 1.0,
    "SYMBOL_OVERRIDES": {},
    "MAX_PAIRS_PER_SYMBOL": 1,
    "COOLDOWN_AFTER_CLOSE_SECONDS": 900,
    "COOLDOWN_AFTER_LOSS_SECONDS": 1800,
    "MAX_CONSECUTIVE_LOSSES": 3,
    "GLOBAL_COOLDOWN_SECONDS": 3600,
    "MAX_SESSIONS_PER_DAY": 0,
    "HEDGE_MAX_DAILY_LOSS": 0.0,
    "HEDGE_SESSION_TP_USD": 0.0,
    "HEDGE_SESSION_SL_USD": 0.0,
    "HEDGE_MAX_HOLD_MINUTES": 0,
    "CHECK_PING": True,
    "MAX_PING_MS": 150,
    "CHECK_SPREAD": True,
    "MAX_SPREAD_POINTS": 150,
}

DEFAULT_HEDGE_STATE = {
    "active_sessions": {},
    "last_decision": {},
    "last_decision_log_keys": {},
    "last_close_times": {},
    "last_loss_times": {},
    "global_cooldown_until": 0.0,
    "consecutive_losses": 0,
    "hedge_active_tickets": [],
    "date": "",
    "hedge_pnl_today": 0.0,
    "hedge_sessions_today": 0,
    "hedge_daily_loss_count": 0,
}


def is_hedge_comment(comment: str) -> bool:
    comment = str(comment or "")
    return HEDGE_COMMENT_PREFIX in comment or comment.startswith("HEDGE_")
