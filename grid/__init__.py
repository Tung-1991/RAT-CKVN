# -*- coding: utf-8 -*-
"""GRID module scaffold.

This package intentionally contains only the isolated GRID foundation for now.
Trade entry, spacing, basket TP, and hedge logic will be added after the GRID
trade rules are finalized.
"""

from .grid_config import GRID_COMMENT_PREFIX, GRID_ENTRY_COMMENT, GRID_CHILD_COMMENT

__all__ = ["GRID_COMMENT_PREFIX", "GRID_ENTRY_COMMENT", "GRID_CHILD_COMMENT"]
