"""Shared MayinTien palette, fonts and input sizing."""
from __future__ import annotations
from .mayin.widgets import (PALETTE, FONT_KEY, FONT_VALUE, FONT_MONO_VALUE, FONT_TABLE_HEADING, FONT_TABLE_VALUE, fit_entry_text)

BG, PANEL, SURFACE, SURFACE_2 = (PALETTE[k] for k in ('BG','PANEL','SURFACE','SURFACE_2'))
BORDER, TEXT, MUTED, TITLE = (PALETTE[k] for k in ('BORDER','TEXT','MUTED','TITLE'))
GREEN, RED, BLUE, WARN = (PALETTE[k] for k in ('GREEN','RED','BLUE','WARN'))
SLATE, SLATE_HOVER = PALETTE['SLATE'], PALETTE['SLATE_HOVER']
COL_SURFACE_2, COL_BORDER, COL_TITLE, COL_MUTED, COL_TEXT = SURFACE_2, BORDER, TITLE, MUTED, TEXT
FONT_BOLD = ("Segoe UI", 14, "bold")
