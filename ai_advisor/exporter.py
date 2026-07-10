# -*- coding: utf-8 -*-
import json
import hashlib
import os
import shutil
from datetime import datetime

from . import config_snapshot, history, paths


USER_CONTEXT_TEMPLATE = """# RAT-CKVN AI Advisor Context

## Bot overview
RAT-CKVN is a DNSE OpenAPI trading bot/workstation for CKPS (VN30F) and CKCS cash stocks. It supports manual orders, bot signals, DCA/PCA, TSL, BE, BE_CASH, REV_C, safeguards, Entry/Exit tactics, T+2 settlement, and multi-timeframe context.

## Current operating goal

## Acceptable drawdown

## Priority symbols

## Suspected rule

## Market context notes

## Things AI should not suggest

## Test notes
Examples: testing REV_C, BE_CASH, TSL, DCA/PCA, Entry/Exit, T+2 settlement.
"""
ADVISOR_FLOW_TEMPLATE = """# RAT-CKVN AI Advisor Flow

This document is the business-flow map for RAT-CKVN. It describes the DNSE OpenAPI bot without requiring the full source code.

## Advisor mission
Review trading performance, risk controls, signal behavior, T+2 settlement, config drift, and missed/poor exits. Do not propose direct automatic order placement and do not ask the bot to edit config by itself.

## Package reading order
For manual upload, use only the generated `external_package` folder; it contains sanitized copies and a manifest. Never upload `.env`, trading-token cache, or account workspace files.
1. Read advisor_flow.md first.
2. Read user_context.md for the operator goal and focus symbols.
3. Read technical_settings.json for current config/runtime snapshots.
4. Read advisor_export.xlsx for trade evidence.
5. Treat previous_advisor_response.md as prior advice only, not fact.

## Markets
- CKPS: VN30F aliases such as VN30F1M. No T+2 restriction; orders/trades/quotes use the resolved contract code, while OHLC uses the alias.
- CKCS: cash stocks such as FPT, SSI, VCB. Long-only; T+2 settlement applies before selling/closing.

## Core trading surfaces
- Manual: operator-triggered orders from UI/Telegram, using manual magic/comment classification.
- Bot: signal-driven orders from daemon context, checklist/safeguard, lot, SL/TP, TSL, DCA/PCA, REV_C, and Entry/Exit tactics.

## Signal/data flow
1. bot_daemon scans active symbols.
2. data_engine.fetch_data_v4 builds OHLC, indicators, ATR/swing, market-structure context.
3. signal_generator.generate_signal_v4 evaluates G0/G1/G2/G3, market mode, trend, votes, and final signal.
4. signal_listener routes pending signals to trade_manager.
5. trade_manager checks safeguards, T+2/long-only rules, Entry/Exit, lot, SL/TP, and sends DNSE orders.
6. Runtime scans apply TSL, BE, BE_CASH, REV_C, DCA/PCA, and settlement-aware closes.

## T+2 settlement
- CKCS BUY records buy_date and settle_date.
- CKCS SELL/close is allowed only for long volume that has settled.
- Unsettled CKCS close attempts should stay pending and retry after settlement instead of opening shorts.
- CKPS ignores T+2.

## Timeframe groups
- G0: macro/base timeframe.
- G1: trend/context timeframe.
- G2: execution/swing timeframe.
- G3: fast confirmation timeframe.

## Safeguards and gates
Common block reasons include market hours, re-entry locks, daily loss, max open positions, max trades, losing streak, ping/spread, cooldown, Entry/Exit WAIT/BLOCK, missing ATR/swing, SL too tight, strict min lot, NO_SETTLED_LONG, and STOCK_NOT_SETTLED_T2.

## Workbook sheets
Use closed_trades, open_trades, config_snapshots, config_changes, events, summary_daily, summary_symbol, summary_timeframe, summary_signal_group, summary_close_reason, summary_module, and trade_config_map as evidence.

## Advice rules
- Ground claims in internal evidence first.
- Separate internal bot evidence from web/market context.
- Diagnose by symbol, direction, close reason, signal group, market mode, tactic, MAE/MFE, fee, and T+2 state.
- Never recommend bypassing T+2 or opening shorts on CKCS.
"""
ADVISOR_RESPONSE_TEMPLATE = """# RAT-CKVN AI Advisor Response

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


def _template_state_path():
    return os.path.join(paths.advisor_root(), ".template_versions.json")


def _text_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sync_versioned_template(filename, target_path, default_text):
    """Update pristine templates; preserve unknown/custom files as *.latest.md."""
    paths.ensure_advisor_dirs()
    latest = _read_template_or_default(filename, default_text)
    latest_hash = _text_hash(latest)
    try:
        with open(_template_state_path(), "r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}
    previous_hash = str((state.get(filename) or {}).get("deployed_hash") or "")
    current = ""
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            current = f.read()
    current_hash = _text_hash(current) if current else ""
    if not current or current_hash == previous_hash:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(latest)
        state[filename] = {"deployed_hash": latest_hash, "version": 2}
    elif current_hash == latest_hash:
        state[filename] = {"deployed_hash": latest_hash, "version": 2}
    else:
        latest_path = os.path.splitext(target_path)[0] + ".latest.md"
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(latest)
        state[filename] = {"custom_hash": current_hash, "latest_hash": latest_hash, "version": 2}
    tmp = _template_state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _template_state_path())
    return target_path


def ensure_user_context():
    return _ensure_editable_file(
        "user_context.md",
        paths.user_context_path(),
        USER_CONTEXT_TEMPLATE,
    )


def ensure_advisor_flow():
    return _sync_versioned_template(
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

    _sync_versioned_template("advisor_prompt.md", paths.advisor_prompt_path(), api_client.DEFAULT_PROMPT)
    if not os.path.exists(paths.advisor_api_settings_path()):
        api_client.save_api_settings(api_client.DEFAULT_API_SETTINGS)
    return paths.advisor_api_settings_path()


def write_technical_settings(reason="manual_export"):
    snapshot = config_snapshot.build_technical_settings(reason=reason)
    path = paths.technical_settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    return path, snapshot.get("config_snapshot_id")


def write_external_package():
    """Build the only folder intended for manual upload to third-party AI."""
    from . import api_client

    root = paths.external_package_root()
    os.makedirs(root, exist_ok=True)
    text_sources = [
        ("advisor_prompt.md", paths.advisor_prompt_path()),
        ("advisor_flow.md", paths.advisor_flow_path()),
        ("technical_settings.json", paths.technical_settings_path()),
        ("user_context.md", paths.user_context_path()),
        ("scan_summary.md", paths.scan_summary_path()),
    ]
    files = []
    for name, source in text_sources:
        if not os.path.isfile(source):
            continue
        with open(source, "r", encoding="utf-8", errors="replace") as f:
            clean = api_client._sanitize_external_text(f.read())
        target = os.path.join(root, name)
        with open(target, "w", encoding="utf-8") as f:
            f.write(clean)
        files.append({"name": name, "bytes": os.path.getsize(target)})
    if os.path.isfile(paths.export_path()):
        target = os.path.join(root, "advisor_export.xlsx")
        shutil.copy2(paths.export_path(), target)
        files.append({"name": "advisor_export.xlsx", "bytes": os.path.getsize(target)})
    estimate = api_client.estimate_api_payload()
    manifest = {
        "version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": estimate.get("model"),
        "reasoning_effort": (estimate.get("settings") or {}).get("reasoning_effort"),
        "estimated_input_tokens": estimate.get("tokens"),
        "privacy": "known secrets, account identifiers and absolute paths redacted",
        "files": files,
    }
    manifest_path = os.path.join(root, "package_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return {"root": root, "manifest": manifest_path, "files": files}


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
        # [SCAN SNAPSHOT] Render kho quét watchlist thành summary/report (nếu có dữ liệu)
        try:
            from ai_advisor import scan_report
            scan_files = scan_report.export_scan_files()
            if scan_files:
                result["scan_summary"] = scan_files["summary"]
                result["scan_report"] = scan_files["report"]
                result["scan_symbols"] = scan_files["symbols"]
        except Exception as scan_exc:
            result["warnings"].append(f"scan report failed: {scan_exc}")
        history.ensure_config_snapshot(reason=reason)
        synced = history.sync_from_master_csv()
        open_count = history.refresh_open_trades(connector=connector, state=state, market_contexts=market_contexts)
        history.rebuild_summaries()
        export_result = history.build_export_workbook(export_days=export_days)
        from .api_client import validate_advisor_package
        package_validation = validate_advisor_package()
        external_package = write_external_package()
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
                "package_validation": package_validation,
                "external_package": external_package,
            }
        )
        history.record_event("advisor_package_exported", "Advisor package generated", payload=result)
    except Exception as exc:
        result["error"] = str(exc)
        history.record_event("advisor_package_export_error", str(exc), severity="ERROR", payload=result)
    return result
