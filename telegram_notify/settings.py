# -*- coding: utf-8 -*-
import json
import os


DEFAULT_SETTINGS = {
    "enabled": False,
    "control_enabled": False,
    "signal_proposals_enabled": False,
    "bot_token_env": "TELE_BOT_KEY",
    "report_chat_id": "1003772881044",
    "control_chat_id": "1003941549878",
    "owner_user_id": "",
    "operator_user_ids": "",
    "chunk_size": 3500,
    "control_poll_interval_seconds": 2.0,
    "signal_proposal_cooldown_minutes": 15.0,
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


def normalize_settings(data):
    clean = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        clean.update(data)
    clean["enabled"] = bool(clean.get("enabled"))
    clean["control_enabled"] = bool(clean.get("control_enabled"))
    clean["signal_proposals_enabled"] = bool(clean.get("signal_proposals_enabled"))
    clean["bot_token_env"] = str(clean.get("bot_token_env") or DEFAULT_SETTINGS["bot_token_env"]).strip()
    clean["report_chat_id"] = str(clean.get("report_chat_id") or "").strip()
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
