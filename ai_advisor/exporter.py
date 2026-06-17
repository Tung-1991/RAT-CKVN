# -*- coding: utf-8 -*-
import json
import os

from . import config_snapshot, history, paths


USER_CONTEXT_TEMPLATE = """# RAT6 AI Advisor Context

## Bot overview
RAT6 is a trading bot/workstation with manual, bot, DCA/PCA, TSL, BE, BE_CASH, REV_C, safeguard, and multi-timeframe signal context.

## Current operating goal

## Acceptable drawdown

## Priority symbols

## Suspected module/rule

## Market context notes

## Things AI should not suggest

## Test notes
Examples: testing REV_C, BE_CASH, TSL, GRID, HEDGE, DCA/PCA.
"""

ADVISOR_FLOW_TEMPLATE = """# RAT6 AI Advisor Flow

This document is the business-flow map for the RAT6 advisor package. It is designed so an LLM can understand the bot without receiving the full source code. Treat this file as the interpretation guide, not as runtime config.

## Advisor mission
The advisor should review RAT6 as a trader/risk-manager assistant. It should diagnose performance, risk, module behavior, missed profit, bad exits, repeated blocks, config drift, suspicious settings, and external market context when web search is available. It must not propose direct automatic order placement and must not tell the bot to edit config by itself.

## Package reading order
1. Read advisor_flow.md first to understand the business flow and glossary.
2. Read user_context.md to understand the operator's current question, risk preference, market notes, and focus symbols.
3. Read technical_settings.json to inspect current configuration and runtime snapshots.
4. Read advisor_export.xlsx to inspect trade evidence, summaries, events, config snapshots, and config changes.
5. If the UI option "Send advisor_response.md with API" is enabled, read previous_advisor_response.md as prior advice only. Prior advice is not fact; verify it against current data.

## Web context rules
- Internal RAT6 data is the primary source for bot/config/trade diagnosis.
- When web search is available, use it for external market context such as news, macro, crypto, XAU, risk-on/risk-off, Fed, ETF, regulation, liquidation, funding, or fresh price drivers.
- Separate internal RAT6 evidence from web/market context.
- Do not claim a market/news cause without enough source evidence.

## Package files
- advisor_flow.md: Human-readable business-flow map and glossary.
- technical_settings.json: Machine-readable snapshot. It is not runtime config and must not be treated as an edit target.
- advisor_export.xlsx: Trade/event/config evidence for the selected export window.
- user_context.md: Human notes from the operator.
- advisor_response.md: Latest saved LLM answer after Send API succeeds.
- history/advisor_response_*.md: Historical copies of LLM answers.

## Technical settings JSON layers
technical_settings.json contains multiple layers because the bot has defaults, active global settings, per-symbol merges, and raw runtime files.

- settings.config_py: Static/default values imported from config.py. Use as background/default only.
- settings.active_global: Current global brain settings loaded from brain_settings.json.
- settings.active_by_symbol: Effective merged settings for each active symbol. Prefer this for symbol-specific review.
- settings.raw_sources: Raw snapshots of JSON/state files such as brain_settings.json, symbol_overrides.json, tsl_settings.json, presets_config.json, grid_settings.json, hedge_settings.json, bot_state.json, grid_state.json, hedge_state.json, live_signals.json, and system_meta.json.

Conflict rule:
- For symbol-specific advice, prefer active_by_symbol.
- For global risk/settings advice, prefer active_global.
- For module-local advice, inspect the matching raw source: grid_settings for GRID, hedge_settings for HEDGE, tsl_settings for TSL, bot_state/grid_state/hedge_state for runtime state.
- Use config_py only when an active value is missing or when comparing default vs active behavior.

## Advisor workbook sheets
advisor_export.xlsx is a compact evidence workbook, not a full source dump.

- closed_trades: Closed trade rows with ticket, symbol, direction, lot, entry/exit time, SL/TP, fee, profit, close reason, market mode, trigger, session id, signal group, tactic, entry/exit tactic, parent ticket, source type, MAE, MFE, module tags, and config snapshot id.
- open_trades: Current open trade rows with symbol, direction, lot, entry price, SL/TP, floating profit, tactic, market mode, MAE/MFE, and snapshot id.
- config_snapshots: Stored config snapshots by id.
- config_changes: Diffs between snapshots.
- events: Advisor/system events with payload JSON.
- summary_daily: Aggregate result by day.
- summary_symbol: Aggregate result by symbol.
- summary_timeframe: Aggregate result by market mode/timeframe context.
- summary_signal_group: Aggregate result by G0/G1/G2/G3.
- summary_close_reason: Aggregate result by close reason.
- summary_module: Aggregate result by module tag.
- trade_config_map: Links trade ticket to the config snapshot recorded near open time.

## Core trading modes
RAT6 has two major trading surfaces:

- Manual: Operator-triggered order from the UI. Uses manual magic/comment classification. Manual orders can still use configured SL/TP logic depending on selected mode and fields.
- Bot: Signal-driven automatic order flow. Uses active symbols, signal context, checklist/safeguard, lot, SL/TP, TSL, DCA/PCA, REV_C, and entry/exit tactic settings.

## Timeframe groups
The bot describes multi-timeframe signal context with groups:

- G0: Macro/base timeframe, usually the highest or broadest market context.
- G1: Trend/context timeframe.
- G2: Execution/swing timeframe. Often used for swing-based SL/TP references.
- G3: Fast confirmation timeframe.

When reviewing losses or missed trades, compare signal group, market mode, and trigger text. A trade opened from a weak fast signal against higher timeframe context should be flagged differently from a trade aligned across groups.

## High-level bot order flow
1. Market data and indicators produce symbol context.
2. Signal engine evaluates configured groups and produces BUY/SELL/NONE plus details.
3. Signal listener/router decides whether an entry, DCA, PCA, reverse-close, or manual action should be considered.
4. Safeguards/checklists can block order entry before lot/SL/TP are finalized.
5. Entry/Exit engine may run as preview-only or as a real entry gate depending on config.
6. SL, TP, lot, tactic labels, parent/child relation, session id, and comments are resolved.
7. DNSE order is sent.
8. Trade-open metadata and config snapshot are recorded for later advisor analysis.
9. Runtime managers scan open trades and apply TSL, BE, BE_CASH, REV_C, and DCA/PCA logic.
10. Closed trades are written into history and later exported into advisor_export.xlsx.

## Safeguards and gates
Safeguards are hard risk gates. If they block an order, the result often starts with SAFEGUARD_FAIL. Common reasons include:

- Market hours closed.
- Re-entry lock after ANTI_CASH or BE_SL.
- Max daily loss.
- Max open positions.
- Max trades per day.
- Max losing streak.
- Ping too high.
- Spread too high.
- Cooldown active.
- Entry/Exit WAIT/BLOCK when Entry/Exit is enabled as a real gate.
- Missing swing/ATR data for SL.
- SL too tight.
- Strict minimum lot rejection.

Advisor interpretation:
- Repeated SAFEGUARD_FAIL is not necessarily a bug; it can mean risk gates are doing their job.
- If good trades are missed, compare block reason frequency, market mode, spread/ping, cooldown, and Entry/Exit WAIT.
- If bad trades pass, inspect whether the relevant safeguard was disabled, too loose, or bypassed.

## Entry/Exit engine
Entry/Exit is a tactic layer. It can be preview-only or can block real entries depending on config.

Possible advisor focus:
- If Entry/Exit is preview-only, do not treat WAIT/BLOCK as a real reason an order was blocked.
- If Entry/Exit is enabled and not preview-only, WAIT/BLOCK can produce SAFEGUARD_FAIL and prevent entry.
- Entry/Exit tactic labels are recorded per trade when available.
- Compare entry_exit_tactic with close reason, MAE/MFE, and signal group to judge if the tactic improved or harmed entries.

## SL and TP concepts
SL/TP can come from multiple sources depending on mode:

- Manual direct fields: Operator can type lot, TP, SL.
- Swing-based logic: SL/TP can use group references such as G2 plus ATR buffer.
- RR/percent/cash logic: Some modes calculate TP/SL from risk, reward ratio, or cash targets.

Advisor interpretation:
- If MAE is tiny but SL hit occurs, inspect SL too tight, spread, volatility, and swing/ATR buffer.
- If MFE is large but profit is small or negative, inspect TSL, BE_CASH, REV_C, giveback, or TP placement.
- If many trades have no TP/SL, determine whether that is intended by mode or a safety gap.

## Lot and risk
Lot can be fixed, account-risk based, or module-specific. Risk settings may differ between Bot, Manual, GRID, and HEDGE.

Advisor interpretation:
- Compare lot size with symbol volatility, SL distance, account risk percent, max lot cap, and strict min lot.
- For DCA/PCA, compare child lot mode against parent lot and basket exposure.
- For GRID, inspect MAX_TOTAL_LOT and MAX_GRID_ORDERS.
- For HEDGE, inspect max pairs, pair lot, and daily loss.

## Runtime tactic tags
Trade tactics and module tags help identify what managed the trade.

- TSL: Trailing-stop layer in general.
- BE: Break-even stop behavior.
- BE_CASH: Cash/profit lock behavior.
- STEP_R: R-multiple step trailing.
- SWING: Swing-point based trailing or SL/TP reference.
- PSAR_TRAIL: Parabolic SAR trailing.
- REV_C: Reverse/recovery close logic.
- DCA: Adds/averages into a losing or adverse basket by rule.
- PCA: Adds into a winning/confirmed basket by rule.
- AUTO_DCA/AUTO_PCA: Automatic DCA/PCA tactic label attached to bot trade management.
- A.CUT or ANTI_CASH: Giveback/cash protection logic.
- GRID: Grid module.
- HEDGE: Hedge module.
- SANDBOX: Strategy sandbox/preview and bot strategy configuration surface.

## TSL, BE, and BE_CASH
TSL is the general trade-management layer after a trade is open.

- BE moves stop toward break-even after conditions are met.
- BE_CASH locks a cash/profit amount after a trigger. It may include fee protection, minimum lock, trailing gap, lock/tight behavior, or soft buffer.
- STEP_R trails by R-multiple steps using settings such as step size and ratio.
- SWING trailing can move stop based on swing structure.
- PSAR_TRAIL trails according to Parabolic SAR context.

Advisor interpretation:
- If MFE is high but final profit is low, inspect whether BE_CASH/STEP_R/SWING/PSAR was absent, too loose, or triggered too late.
- If trades close too early with small profit, inspect BE_CASH min lock, trigger, gap, soft buffer, and fee protection.
- If SL moves unexpectedly, inspect tactic label and event payloads before assuming a bug.

## REV_C reverse close
REV_C is reverse/recovery close logic. It can close a trade when signal context reverses or becomes NONE if configured.

Key concepts:
- REV_CLOSE_ON_NONE controls whether no-signal context can trigger close.
- REV_CONFIRM_SECONDS and REV_CONFIRM_SCANS can require persistence before closing.
- REV_CLOSE_MIN_PROFIT can avoid closing too early unless profit threshold is met.
- REV_CLOSE_MAX_LOSS can avoid accepting too much loss or can cap the allowed loss depending on unit settings.

Advisor interpretation:
- If trades close before TP despite favorable MFE, inspect REV_C settings and reverse signal timing.
- If losses persist through clear reverse signals, inspect whether REV_C was attached to tactic and whether confirm thresholds were too strict.
- Always compare close reason, trigger, market mode, and tactic before blaming REV_C.

## DCA and PCA
DCA/PCA are child-entry systems tied to parent/basket logic.

- DCA generally adds or averages when a position moves adversely according to configured rules.
- PCA generally adds when the direction is confirmed or winning according to configured rules.
- Parent/child mapping can appear in trade_config_map and closed_trades parent ticket fields.
- Child trades may inherit or calculate their own SL/TP depending on config.
- There are cooldowns to prevent repeated additions too quickly.

Advisor interpretation:
- If basket drawdown grows quickly, inspect DCA enablement, lot multiplier, max child count, cooldown, and parent SL.
- If PCA worsens performance, inspect whether it adds too late, near exhaustion, or against higher timeframe context.
- If child trades close differently from parent, inspect child tactic, parent ticket, and session id.

## Manual mode
Manual trades are operator-triggered but still part of advisor evidence.

Manual concepts:
- Manual orders use manual magic/comment classification.
- Manual trade mode can be NORMAL, GRID, or HEDGE depending on UI selection.
- Manual SL/TP can be direct typed fields or calculated using configured manual swing/RR/percent modes.
- Manual preview panels may show expected setup before order.

Advisor interpretation:
- Do not assume manual trade losses are bot signal failures.
- Separate source type MANUAL from BOT/GRID/HEDGE.
- If manual trades repeatedly lose due to SL placement, inspect manual SL group, ATR buffer, typed SL, and symbol volatility.

## GRID business rules
GRID is isolated from normal Bot/manual runtime counters.

Ownership:
- Orders use grid_magic.
- Order comments start with [GRID].
- Runtime data lives in grid_state.json.
- Settings live in grid_settings.json.
- GRID cooldown is per symbol and level.
- GRID does not write bot/manual runtime counters such as bot_trades_today or manual_trades_today.

GRID entry flow:
1. Auto GRID requires ENABLED=true. Manual GRID can start even when Auto GRID is off.
2. Symbol must be in GRID watchlist for Auto GRID, or passed by caller when watchlist is empty.
3. GRID prepares market context and optional GRID signal.
4. Gate decides bias mode: BUY signal means LONG, SELL signal means SHORT, NONE means NEUTRAL or blocked by NONE_POLICY. TREND/BREAKOUT can block new orders when STOP_ON_BREAKOUT is true.
5. Boundary uses manual upper/lower first, otherwise swing high/low from configured timeframe group.
6. Spacing depends on GRID_TYPE:
   - ATR_DYNAMIC: ATR * SPACING_ATR_MULTIPLIER.
   - ARITHMETIC: (upper - lower) / GRID_COUNT.
   - GEOMETRIC: current_price * GEOMETRIC_STEP_PERCENT / 100.
7. Direction:
   - LONG: BUY only below/equal midpoint.
   - SHORT: SELL only above/equal midpoint.
   - NEUTRAL: BUY below midpoint, SELL above midpoint.
8. GRID checks hard safety and GRID safeguard before opening.
9. GRID opens market orders with TP only. Per-order SL is not part of GRID V1.

GRID safeguards:
- MAX_GRID_ORDERS: Max open GRID positions per symbol.
- MAX_TOTAL_LOT: Max open GRID gross lot per symbol.
- MAX_BASKET_DRAWDOWN: Floating PnL stop-new threshold per symbol.
- GRID_MAX_DAILY_LOSS: Closed daily PnL stop-new threshold.
- GRID_MAX_TRADES_PER_DAY: Closed trade count stop-new threshold.
- BASKET_TP_USD: Close all current GRID positions at basket profit target.
- BASKET_SL_USD: Close all current GRID positions at basket loss threshold.
- CHECK_PING and CHECK_SPREAD remain GRID-local settings.

GRID signal source:
- OFF: GRID does not read signal.
- CONTEXT: GRID uses latest_signal already present in daemon context.
- IMPORTED: GRID evaluates its own GRID_SIGNAL_CONFIG with shared signal engine.

Advisor interpretation:
- Do not treat GRID orders as normal Bot trades.
- Use GRID settings/state and GRID summary/module rows for diagnosis.
- If GRID overtrades, inspect spacing, cooldown, level reserve, max orders, and watchlist.
- If GRID misses levels, inspect boundary source, spacing type, midpoint direction, and signal gate.
- If basket exits dominate results, inspect BASKET_TP_USD/BASKET_SL_USD and total lot.

## HEDGE business rules
HEDGE Dual owns its own state/log and reuses shared bot rules only where needed.

HEDGE entry:
- If USE_SIGNAL_FILTER is ON, latest_signal must be non-zero.
- If USE_ENTRY_EXIT_FILTER is ON, HEDGE runs Entry/Exit as an entry filter.
- If filters are OFF, HEDGE skips those filters.
- Every entry still must pass hard safety, max pairs, cooldown, daily loss, ping, and spread checks.

HEDGE orders:
- When allowed, HEDGE opens BUY and SELL at the same time with the same lot.
- Each leg can have its own SL/TP.
- If Entry/Exit does not provide SL and USE_HEDGE_SLTP is ON, HEDGE calculates SL/TP by its own rules.
- If USE_HEDGE_SLTP is OFF, HEDGE may open without SL/TP.

HEDGE exit:
- While both BUY and SELL are open, HEDGE does not run TSL on individual legs.
- Each leg may still close by its own SL/TP.
- After one leg closes, the remaining leg is armed for protection and TSL.
- SURVIVOR_PROTECT runs before TSL to protect against immediate reversal.
- If price keeps moving in the profitable direction, TSL manages the remaining leg.

HEDGE isolation:
- HEDGE writes hedge_state.json, hedge_settings.json, and hedge logs.
- HEDGE must not write BOT/GRID runtime state.

Advisor interpretation:
- Do not judge HEDGE by single-leg PnL alone; inspect pair/session behavior.
- If both legs lose or fees dominate, inspect spread, pair SL/TP, lot, and entry filter quality.
- If survivor leg gives back profit, inspect SURVIVOR_PROTECT and TSL settings.
- If HEDGE does not enter, inspect signal filter, Entry/Exit filter, max pairs, cooldown, daily loss, ping, and spread.

## Position classification
Source type matters when diagnosing:

- BOT positions are bot-managed and usually have bot magic/comment markers.
- MANUAL positions use manual magic/comment markers.
- GRID positions use grid_magic or [GRID] comments.
- HEDGE positions use hedge-specific magic/comment/session classification.

Always separate performance by Source Type and Module Tags before making conclusions.

## Close reasons
Close Reason is a high-value evidence field. It can show SL/TP, manual close, reverse close, trailing logic, basket close, safeguard-related close, or module-specific actions.

Advisor interpretation:
- Many SL closes with low MFE: entry quality or SL placement issue.
- Many SL closes after high MFE: trailing/BE/giveback issue.
- Many TP closes but net profit small: fee, lot, TP distance, or spread issue.
- Many manual closes: operator behavior dominates; avoid blaming bot automation.
- Many basket closes: analyze GRID/HEDGE/DCA/PCA basket settings instead of individual entries.

## MAE and MFE
- MAE: Maximum adverse excursion in USD. It shows how much a trade went against the position.
- MFE: Maximum favorable excursion in USD. It shows how much potential profit existed.

Advisor use:
- High MFE and low final profit suggests exit/trailing/giveback problem.
- High MAE before profit suggests entry timing, SL distance, or DCA/PCA stress.
- Low MAE and low MFE suggests choppy/no-edge entry or overly tight management.
- Compare MAE/MFE by symbol, close reason, signal group, and tactic.

## Config snapshot usage
Every trade can map to a config snapshot id. Use this to avoid judging old trades with current settings.

Advisor workflow:
1. Identify the losing or problematic trades.
2. Read their Config Snapshot ID.
3. Check config_snapshots and config_changes around that snapshot.
4. Determine whether a setting changed before/after the trade.
5. Avoid saying current config caused an old trade if snapshot evidence says otherwise.

## Event payloads
Events can contain system/advisor warnings, package generation records, API records, missing CSV warnings, config snapshot errors, and module payloads.

Advisor interpretation:
- Events are supporting evidence, not trade results.
- Repeated errors can indicate export/runtime data quality issues.
- Missing master CSV or snapshot warnings reduce confidence in historical diagnosis.

## Recommended advisor answer format
Always answer in Vietnamese. Return concise but evidence-based output:

1. Tóm tắt điều hành.
2. Bằng chứng nội bộ RAT6.
3. Bối cảnh web/thị trường.
4. Chẩn đoán.
5. Rủi ro chính.
6. Hành động đề xuất: safe config checks for the operator to consider, not automatic edits.
7. Độ tin cậy / Thiếu dữ liệu.

Important conclusions should include short evidence and confidence: Cao / Trung bình / Thấp.

## Strict response rules
- Separate facts from assumptions.
- Do not invent behavior for unknown keys.
- If a field is unclear, state which evidence was used instead.
- Do not recommend turning off safeguards casually.
- Do not recommend increasing risk after a loss streak without strong evidence.
- Do not give financial advice as certainty. Frame trading ideas as risk review and operator decisions.
- Do not ask RAT6 to place orders or modify files automatically.
"""

ADVISOR_RESPONSE_TEMPLATE = """# RAT6 AI Advisor Response

No API response has been saved yet.

When Send API succeeds, this file will be replaced with the latest LLM response.
Historical copies are stored in the account history folder as advisor_response_*.md.
"""


def _read_template_or_default(filename, default_text):
    template_path = paths.advisor_template_path(filename)
    if os.path.exists(template_path):
        try:
            with open(template_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            pass
    return default_text


def _ensure_editable_file(filename, target_path, default_text):
    paths.ensure_advisor_dirs()
    if not os.path.exists(target_path):
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(_read_template_or_default(filename, default_text))
    return target_path


def ensure_user_context():
    return _ensure_editable_file(
        "user_context.md",
        paths.user_context_path(),
        USER_CONTEXT_TEMPLATE,
    )


def ensure_advisor_flow():
    return _ensure_editable_file(
        "advisor_flow.md",
        paths.advisor_flow_path(),
        ADVISOR_FLOW_TEMPLATE,
    )


def ensure_advisor_response_template():
    return _ensure_editable_file(
        "advisor_response.md",
        paths.advisor_response_path(),
        ADVISOR_RESPONSE_TEMPLATE,
    )


def ensure_advisor_api_files():
    from . import api_client

    api_client.ensure_advisor_prompt()
    if not os.path.exists(paths.advisor_api_settings_path()):
        api_client.save_api_settings(api_client.DEFAULT_API_SETTINGS)
    return paths.advisor_api_settings_path()


def write_technical_settings(reason="manual_export"):
    snapshot = config_snapshot.build_technical_settings(reason=reason)
    path = paths.technical_settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    return path, snapshot.get("config_snapshot_id")


def generate_advisor_package(
    export_days=7,
    save_archive=False,
    connector=None,
    state=None,
    market_contexts=None,
    reason="manual_export",
):
    result = {
        "ok": False,
        "root": paths.advisor_root(),
        "technical_settings": paths.technical_settings_path(),
        "advisor_history": paths.history_path(),
        "advisor_export": paths.export_path(),
        "advisor_flow": paths.advisor_flow_path(),
        "user_context": paths.user_context_path(),
        "archive": None,
        "warnings": [],
    }
    try:
        paths.ensure_advisor_dirs()
        ensure_user_context()
        ensure_advisor_flow()
        ensure_advisor_response_template()
        ensure_advisor_api_files()
        tech_path, snapshot_id = write_technical_settings(reason=reason)
        history.ensure_config_snapshot(reason=reason)
        synced = history.sync_from_master_csv()
        open_count = history.refresh_open_trades(connector=connector, state=state, market_contexts=market_contexts)
        history.rebuild_summaries()
        export_result = history.build_export_workbook(export_days=export_days)
        if not export_result.get("ok"):
            result["warnings"].append(export_result.get("error", "advisor export build failed"))
        result.update(
            {
                "ok": True,
                "technical_settings": tech_path,
                "advisor_export": export_result.get("path", paths.export_path()),
                "config_snapshot_id": snapshot_id,
                "synced_closed_trades": synced,
                "export_closed_trades": export_result.get("closed_trades", 0),
                "open_trades": open_count,
                "export_days": export_days,
            }
        )
        history.record_event("advisor_package_exported", "Advisor package generated", payload=result)
    except Exception as exc:
        result["error"] = str(exc)
        history.record_event("advisor_package_export_error", str(exc), severity="ERROR", payload=result)
    return result
