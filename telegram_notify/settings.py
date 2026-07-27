# -*- coding: utf-8 -*-
import json
import os


DEFAULT_SETTINGS = {
    "enabled": False,
    "system_alerts_enabled": True,
    "control_enabled": False,
    "signal_proposals_enabled": False,
    "opportunity_alerts_enabled": False,
    "opportunity_daily_digest_enabled": False,
    "bot_token_env": "TELE_BOT_KEY",
    "report_chat_id": "1003772881044",
    "opportunity_chat_id": "",
    "control_chat_id": "1003941549878",
    "owner_user_id": "",
    "operator_user_ids": "",
    "chunk_size": 3500,
    "control_poll_interval_seconds": 2.0,
    "signal_proposal_cooldown_minutes": 15.0,
    "opportunity_duplicate_cooldown_minutes": 0.0,
    "opportunity_batch_minutes": 0.5,
    "opportunity_mode_filter": "ALL",
    "opportunity_ckps_enabled": True,
    "opportunity_ckcs_enabled": True,
}


def account_dir():
    try:
        import core.storage_manager as storage_manager

        return storage_manager._active_account_dir
    except Exception:
        return "data"


def settings_path():
    return os.path.join(account_dir(), "telegram_settings.json")


def _safe_int(value, default, min_value=500, max_value=3900):
    try:
        parsed = int(float(value))
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def _safe_float(value, default, min_value=0.5, max_value=30.0):
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def _is_exact_number(value, expected):
    try:
        return float(value) == float(expected)
    except (TypeError, ValueError):
        return False


def normalize_settings(data):
    clean = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        clean.update(data)
        # Migrate only the two legacy defaults. Custom values are preserved.
        if _is_exact_number(data.get("opportunity_duplicate_cooldown_minutes"), 60.0):
            clean["opportunity_duplicate_cooldown_minutes"] = 0.0
        if _is_exact_number(data.get("opportunity_batch_minutes"), 5.0):
            clean["opportunity_batch_minutes"] = 0.5
    clean["enabled"] = bool(clean.get("enabled"))
    clean["system_alerts_enabled"] = bool(clean.get("system_alerts_enabled", True))
    clean["control_enabled"] = bool(clean.get("control_enabled"))
    clean["signal_proposals_enabled"] = bool(clean.get("signal_proposals_enabled"))
    clean["opportunity_alerts_enabled"] = bool(clean.get("opportunity_alerts_enabled"))
    clean["opportunity_daily_digest_enabled"] = bool(
        clean.get("opportunity_daily_digest_enabled", False)
    )
    clean["bot_token_env"] = str(clean.get("bot_token_env") or DEFAULT_SETTINGS["bot_token_env"]).strip()
    clean["report_chat_id"] = str(clean.get("report_chat_id") or "").strip()
    clean["opportunity_chat_id"] = str(clean.get("opportunity_chat_id") or "").strip()
    clean["control_chat_id"] = str(clean.get("control_chat_id") or "").strip()
    clean["owner_user_id"] = str(clean.get("owner_user_id") or "").strip()
    clean["operator_user_ids"] = str(clean.get("operator_user_ids") or "").strip()
    clean["chunk_size"] = _safe_int(clean.get("chunk_size"), DEFAULT_SETTINGS["chunk_size"])
    clean["control_poll_interval_seconds"] = _safe_float(
        clean.get("control_poll_interval_seconds"),
        DEFAULT_SETTINGS["control_poll_interval_seconds"],
    )
    clean["signal_proposal_cooldown_minutes"] = _safe_float(
        clean.get("signal_proposal_cooldown_minutes"),
        DEFAULT_SETTINGS["signal_proposal_cooldown_minutes"],
        min_value=0.5,
        max_value=1440.0,
    )
    clean["opportunity_duplicate_cooldown_minutes"] = _safe_float(
        clean.get("opportunity_duplicate_cooldown_minutes"),
        DEFAULT_SETTINGS["opportunity_duplicate_cooldown_minutes"],
        min_value=0.0,
        max_value=1440.0,
    )
    clean["opportunity_batch_minutes"] = _safe_float(
        clean.get("opportunity_batch_minutes"),
        DEFAULT_SETTINGS["opportunity_batch_minutes"],
        min_value=0.1,
        max_value=60.0,
    )
    mode_filter = str(clean.get("opportunity_mode_filter") or "ALL").strip().upper()
    clean["opportunity_mode_filter"] = (
        mode_filter if mode_filter in {"PAPER", "REAL", "ALL"} else "ALL"
    )
    clean["opportunity_ckps_enabled"] = bool(clean.get("opportunity_ckps_enabled", True))
    clean["opportunity_ckcs_enabled"] = bool(clean.get("opportunity_ckcs_enabled", True))
    return clean


def parse_user_ids(value):
    ids = set()
    for part in str(value or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except Exception:
            pass
    return ids


def allowed_user_ids(settings=None):
    settings = normalize_settings(settings or load_settings())
    ids = parse_user_ids(settings.get("operator_user_ids"))
    ids.update(parse_user_ids(settings.get("owner_user_id")))
    return ids


def load_settings():
    path = settings_path()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    return normalize_settings(data)


def save_settings(data):
    clean = normalize_settings(data)
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)
    return clean
