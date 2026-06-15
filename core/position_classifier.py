# -*- coding: utf-8 -*-
"""Shared helpers for classifying trade ownership by magic/comment."""

from typing import Any, Dict, Optional


BOT_COMMENT_PREFIX = "[BOT]"
MANUAL_COMMENT_PREFIX = "[USER]"
GRID_COMMENT_PREFIX = "[GRID]"
GRID_SAFE_COMMENT_PREFIX = "GRID_"
HEDGE_COMMENT_PREFIX = "[HEDGE]"
HEDGE_SAFE_COMMENT_PREFIX = "HEDGE_"


def _comment(obj: Any) -> str:
    return str(getattr(obj, "comment", "") or "")


def _magic(obj: Any) -> Optional[int]:
    try:
        return int(getattr(obj, "magic", None))
    except (TypeError, ValueError):
        return None


def is_grid_position(pos: Any, magics: Optional[Dict[str, int]] = None) -> bool:
    if pos is None:
        return False
    grid_magic = (magics or {}).get("grid_magic")
    comment = _comment(pos)
    return (
        (grid_magic is not None and _magic(pos) == int(grid_magic))
        or GRID_COMMENT_PREFIX in comment
        or comment.startswith(GRID_SAFE_COMMENT_PREFIX)
    )


def is_hedge_position(pos: Any, magics: Optional[Dict[str, int]] = None) -> bool:
    if pos is None:
        return False
    hedge_magic = (magics or {}).get("hedge_magic")
    comment = _comment(pos)
    return (
        (hedge_magic is not None and _magic(pos) == int(hedge_magic))
        or HEDGE_COMMENT_PREFIX in comment
        or comment.startswith(HEDGE_SAFE_COMMENT_PREFIX)
    )


def is_bot_position(pos: Any, magics: Optional[Dict[str, int]] = None) -> bool:
    if pos is None or is_grid_position(pos, magics) or is_hedge_position(pos, magics):
        return False
    bot_magic = (magics or {}).get("bot_magic")
    comment = _comment(pos)
    return (bot_magic is not None and _magic(pos) == int(bot_magic)) or BOT_COMMENT_PREFIX in comment


def is_manual_position(pos: Any, magics: Optional[Dict[str, int]] = None) -> bool:
    if pos is None or is_grid_position(pos, magics) or is_hedge_position(pos, magics):
        return False
    manual_magic = (magics or {}).get("manual_magic")
    comment = _comment(pos)
    return (manual_magic is not None and _magic(pos) == int(manual_magic)) or MANUAL_COMMENT_PREFIX in comment
