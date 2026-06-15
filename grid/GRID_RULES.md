# GRID V1 Business Rules

GRID V1 is an isolated strategy module. It may reuse shared connector,
market data, signal context, magic registry, hard safety checks, and trade
history, but it must not write BOT/manual runtime counters or cooldowns.

## Ownership

- Orders use `grid_magic`.
- Order comments start with `[GRID]`.
- Runtime data lives in `grid_state.json`.
- Settings live in `grid_settings.json`.
- GRID cooldown is per symbol + level via `last_grid_action_times`.
- GRID does not use `bot_last_entry_times`, `bot_last_fail_times`,
  `bot_trades_today`, or `manual_trades_today`.

## Entry Flow

1. Auto GRID requires `ENABLED=true`; Manual GRID can start even when Auto
   GRID is off.
2. Symbol must be in the GRID watchlist for Auto GRID, or be passed by the caller when
   the watchlist is empty.
3. GRID prepares market context and optional GRID signal.
4. Gate decides mode:
   - BUY signal -> `LONG`
   - SELL signal -> `SHORT`
   - NONE -> `NEUTRAL` or blocked by `NONE_POLICY`
   - `TREND`/`BREAKOUT` can block new orders when `STOP_ON_BREAKOUT` is true.
5. Boundary is manual upper/lower first, otherwise swing high/low from the
   configured timeframe group.
6. Spacing depends on `GRID_TYPE`:
   - `ATR_DYNAMIC`: `ATR * SPACING_ATR_MULTIPLIER`
   - `ARITHMETIC`: `(upper - lower) / GRID_COUNT`
   - `GEOMETRIC`: `current_price * GEOMETRIC_STEP_PERCENT / 100`
7. Direction:
   - `LONG`: BUY only below/equal midpoint.
   - `SHORT`: SELL only above/equal midpoint.
   - `NEUTRAL`: BUY below midpoint, SELL above midpoint.
8. GRID checks hard safety and GRID safeguard before opening.
9. GRID opens market orders with TP only. Per-order SL is not part of V1.

## Safeguard

- `MAX_GRID_ORDERS`: maximum open GRID positions for the symbol.
- `MAX_TOTAL_LOT`: maximum open GRID gross lot for the symbol.
- `MAX_BASKET_DRAWDOWN`: floating PnL stop-new threshold for the symbol.
- `GRID_MAX_DAILY_LOSS`: closed daily PnL stop-new threshold for GRID.
- `GRID_MAX_TRADES_PER_DAY`: closed trade count stop-new threshold for GRID.
- `BASKET_TP_USD`: close all current GRID positions when basket profit reaches this value.
- `BASKET_SL_USD`: close all current GRID positions when basket loss reaches this value.
- `CHECK_PING` and `CHECK_SPREAD` remain GRID-local settings.

## Signal Source

- `OFF`: GRID does not read signal. Manual uses the selected mode; Auto uses
  `DEFAULT_MANUAL_MODE`.
- `CONTEXT`: GRID uses `latest_signal` already present in daemon context.
- `IMPORTED`: GRID evaluates its own `GRID_SIGNAL_CONFIG` with the shared
  QUANT/BOT signal engine.

Signal only chooses the GRID bias mode. It does not place orders by itself.

## Launch Modes

- Auto GRID: daemon calls `GridManager.scan()` for the GRID watchlist when
  `ENABLED` is true, using `GRID_SCAN_INTERVAL_SECONDS`.
- Manual GRID: UI trade button starts a GRID session when manual trade mode is
  `GRID`, then immediately scans that symbol. Manual START does not require
  Auto GRID to be enabled.
- Both paths share the same GRID settings, state, magic, safeguard, and entry
  rules.

## Future Rule

Long term deployment should be one RAT process per MT5 portable terminal,
one terminal per account, and one account per strategy. This file only
defines the single-account GRID module boundary for the current phase.
