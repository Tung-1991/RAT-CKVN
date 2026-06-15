# -*- coding: utf-8 -*-
"""Per-account GRID storage helpers."""

import copy
import json
import os
from typing import Any, Dict

from .grid_config import (
    DEFAULT_GRID_SETTINGS,
    DEFAULT_GRID_STATE,
    GRID_SETTINGS_FILE,
    GRID_STATE_FILE,
)


def _account_dir() -> str:
    try:
        import core.storage_manager as storage_manager

        return storage_manager._active_account_dir
    except Exception:
        return "data"


def _path(filename: str) -> str:
    return os.path.join(_account_dir(), filename)


def grid_settings_path() -> str:
    return _path(GRID_SETTINGS_FILE)


def grid_state_path() -> str:
    return _path(GRID_STATE_FILE)


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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp_path, path)


def load_grid_settings() -> Dict[str, Any]:
    return _load_json(grid_settings_path(), DEFAULT_GRID_SETTINGS)


def save_grid_settings(data: Dict[str, Any]) -> None:
    merged = _merge_defaults(DEFAULT_GRID_SETTINGS, data)
    _save_json(grid_settings_path(), merged)
    try:
        from ai_advisor.history import ensure_config_snapshot, record_event

        snapshot_id = ensure_config_snapshot(reason="save_grid_settings")
        record_event(
            "config_saved",
            "grid_settings.json saved",
            payload={"source": grid_settings_path(), "config_snapshot_id": snapshot_id},
        )
    except Exception:
        pass


def load_grid_state() -> Dict[str, Any]:
    return _load_json(grid_state_path(), DEFAULT_GRID_STATE)


def save_grid_state(data: Dict[str, Any]) -> None:
    merged = _merge_defaults(DEFAULT_GRID_STATE, data)
    _save_json(grid_state_path(), merged)
