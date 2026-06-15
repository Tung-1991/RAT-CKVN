# HEDGE Dual Rules

HEDGE Dual owns its own state/log and reuses existing bot rules only where needed.

## Entry
- If `USE_SIGNAL_FILTER = ON`, `latest_signal` must be non-zero.
- If `USE_ENTRY_EXIT_FILTER = ON`, HEDGE runs Entry/Exit as an entry filter.
- If filters are OFF, HEDGE skips those filters.
- Every entry still must pass hard safety, max pairs, cooldown, daily loss, ping, and spread checks.

## Orders
- When allowed, HEDGE opens BUY and SELL at the same time with the same lot.
- Each leg can have its own SL/TP.
- If Entry/Exit does not provide SL and `USE_HEDGE_SLTP = ON`, HEDGE calculates SL/TP by its own HEDGE rules.
- If `USE_HEDGE_SLTP = OFF`, HEDGE may open without SL/TP.

## Exit
- While both BUY and SELL are open, HEDGE does not run TSL on individual legs.
- Each leg may still close by its own SL/TP.
- After one leg closes, the remaining leg is armed for protection and TSL.
- `SURVIVOR_PROTECT` runs before TSL to protect against immediate reversal.
- If price keeps moving in the profitable direction, TSL manages the remaining leg.

## Isolation
- HEDGE writes `hedge_state.json`, `hedge_settings.json`, and hedge logs.
- HEDGE must not write BOT/GRID runtime state.
