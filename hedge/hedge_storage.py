# -*- coding: utf-8 -*-
"""Per-account HEDGE storage helpers."""

import copy
import json
import os
import tempfile
import threading
import time
from typing import Any, Dict

from .hedge_config import (
    DEFAULT_HEDGE_SETTINGS,
    DEFAULT_HEDGE_STATE,
    HEDGE_SETTINGS_FILE,
    HEDGE_STATE_FILE,
)

_write_lock = threading.RLock()


def _account_dir() -> str:
    try:
        import core.storage_manager as storage_manager

        return storage_manager._active_account_dir
    except Exception:
        return "data"


def _path(filename: str) -> str:
    return os.path.join(_account_dir(), filename)


def hedge_settings_path() -> str:
    return _path(HEDGE_SETTINGS_FILE)


def hedge_state_path() -> str:
    return _path(HEDGE_STATE_FILE)


def _merge_defaults(defaults: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(defaults)
    if isinstance(data, dict):
        merged.update(data)
    return merged


def _load_json(path: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
    if not os.path.exists(path):
        return copy.deepcopy(defaults)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _merge_defaults(defaults, data if isinstance(data, dict) else {})
    except Exception:
        return copy.deepcopy(defaults)


def _save_json(path: str, data: Dict[str, Any]) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    with _write_lock:
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            dir=directory,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            last_error = None
            for attempt in range(5):
                try:
                    os.replace(tmp_path, path)
                    return
                except PermissionError as e:
                    last_error = e
                    time.sleep(0.05 * (attempt + 1))
            raise last_error
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass


def load_hedge_settings() -> Dict[str, Any]:
    return _load_json(hedge_settings_path(), DEFAULT_HEDGE_SETTINGS)


def save_hedge_settings(data: Dict[str, Any]) -> None:
    merged = _merge_defaults(DEFAULT_HEDGE_SETTINGS, data)
    _save_json(hedge_settings_path(), merged)
    try:
        from ai_advisor.history import ensure_config_snapshot, record_event

        snapshot_id = ensure_config_snapshot(reason="save_hedge_settings")
        record_event(
            "config_saved",
            "hedge_settings.json saved",
            payload={"source": hedge_settings_path(), "config_snapshot_id": snapshot_id},
        )
    except Exception:
        pass


def load_hedge_state() -> Dict[str, Any]:
    return _load_json(hedge_state_path(), DEFAULT_HEDGE_STATE)


def save_hedge_state(data: Dict[str, Any]) -> None:
    merged = _merge_defaults(DEFAULT_HEDGE_STATE, data)
    _save_json(hedge_state_path(), merged)
