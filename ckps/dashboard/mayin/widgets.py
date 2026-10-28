from __future__ import annotations
import tkinter as tk
from tkinter import font as tkfont
from typing import Any
import customtkinter as ctk
from .ui_compat import NativeFontMetrics, install_dpi_resize_guard
install_dpi_resize_guard()

PALETTE = {
    "BG": "#111318",        # window background
    "PANEL": "#15181D",     # tab body
    "SURFACE": "#22262D",   # cards and table rows
    "SURFACE_2": "#1B1F25", # inputs, headers, striped rows
    "BORDER": "#343A43",    # every border and chip
    "SLATE": "#3A3F47",     # neutral buttons
    "SLATE_HOVER": "#4B515B",
    "TEXT": "#E8EBEF",
    "TITLE": "#BABEC5",     # neutral headings/keys; readable without white glare
    "MUTED": "#C5CBD4",
    "DIM": "#98A2B3",
    "BLUE": "#2B6CB0",
    "BLUE_HOVER": "#245C92",
    "GREEN": "#22C55E",
    "GREEN_HOVER": "#16A34A",
    "RED": "#EF4444",
    "WARN": "#F59E0B",
}


FONT_KEY = ("Segoe UI", 14, "bold", "italic")


FONT_VALUE = ("Segoe UI", 14)


FONT_MONO_VALUE = ("Cascadia Mono", 14)


FONT_TABLE_HEADING = ("Segoe UI", 16, "bold", "italic")


FONT_TABLE_VALUE = ("Segoe UI", 14)


class StatusLabel(ctk.CTkLabel):
    """Avoid redrawing unchanged text and colours on periodic UI refreshes."""

    _stable_options = frozenset({"text", "text_color", "text_color_disabled", "fg_color"})

    def configure(self, require_redraw=False, **kwargs):
        changed = {key: value for key, value in kwargs.items()
                   if key not in self._stable_options or self.cget(key) != value}
        if changed or require_redraw:
            super().configure(require_redraw=require_redraw, **changed)

    def set_status_icon(self, mark: str, color: str, *, size: int = 14) -> None:
        """Draw status badges or bold crossing arrows at native DPI."""
        key = (mark, color) if mark else None
        if (getattr(self, "_viking_status_icon", None) == key
                and getattr(self, "_viking_icon_size", size) == size):
            return
        self._viking_status_icon = key
        self._viking_icon_size = size
        if key is None:
            self.configure(image=None)
            return
        from PIL import Image, ImageDraw
        cache = getattr(self, "_viking_icon_images", {})
        cache_key = (*key, size)
        if cache_key not in cache:
            bitmap = Image.new("RGBA", (64, 64))
            draw = ImageDraw.Draw(bitmap)
            if mark in {"↑", "↓"}:
                points = ((24, 8), (40, 8), (40, 34), (56, 34), (32, 58), (8, 34), (24, 34))
                draw.polygon(points if mark == "↓" else tuple((x, 64-y) for x, y in points), fill=color)
            else:
                draw.rounded_rectangle((2, 2, 61, 61), radius=14, fill=color)
            if mark == "✓":
                draw.line(((16, 33), (27, 44), (48, 21)), fill=PALETTE["BG"], width=6)
            elif mark == "×":
                draw.line(((20, 20), (44, 44)), fill=PALETTE["BG"], width=6)
                draw.line(((44, 20), (20, 44)), fill=PALETTE["BG"], width=6)
            elif mark not in {"↑", "↓"}:
                draw.line(((18, 26), (46, 26)), fill=PALETTE["BG"], width=6)
                draw.line(((18, 38), (46, 38)), fill=PALETTE["BG"], width=6)
            cache[cache_key] = ctk.CTkImage(light_image=bitmap, dark_image=bitmap, size=(size, size))
            self._viking_icon_images = cache
        self.configure(image=cache[cache_key], compound="left", padx=3)


def fit_entry_text(
    entry: ctk.CTkEntry,
    text: str,
    *,
    base_font: tuple[Any, ...] = FONT_MONO_VALUE,
    minimum_size: int = 11,
    horizontal_padding: int = 22,
) -> int:
    """Keep a dynamic entry value readable without letting it be clipped.

    Normal values stay at the standard 14-point size.  Only values wider than
    the actual input area are reduced, and never below the UI minimum of 11.
    """
    family = str(base_font[0])
    base_size = max(minimum_size, int(base_font[1]))
    styles = tuple(str(item) for item in base_font[2:])
    inner = getattr(entry, "_entry", None)
    inner_width = int(inner.winfo_width()) if inner is not None else 0
    available = max(
        0,
        inner_width - 8 if inner_width > 1
        else int(entry.winfo_width()) - horizontal_padding,
    )
    selected = base_size
    if available > 0 and text:
        top = entry.winfo_toplevel()
        for size in range(base_size, minimum_size - 1, -1):
            options: dict[str, Any] = {"root": top, "family": family, "size": size}
            if "bold" in styles:
                options["weight"] = "bold"
            if "italic" in styles:
                options["slant"] = "italic"
            if tkfont.Font(**options).measure(text) <= available:
                selected = size
                break
        else:
            selected = minimum_size
    if getattr(entry, "_viking_fit_font_size", None) != selected:
        entry.configure(font=(family, selected, *styles))
        entry._viking_fit_font_size = selected
    return selected


def fit_label_text(
    label: ctk.CTkLabel,
    *,
    base_font: tuple[Any, ...],
    minimum_size: int = 10,
) -> None:
    """Fit a compact, single-line value using its actual scaled Tk font."""
    if not isinstance(label, ctk.CTkLabel) or label.winfo_width() <= 1:
        return
    text = str(label.cget("text") or "")
    # CTk reserves the corner radius on both sides of its native text label.
    # Measuring only the outer frame let rounded health/status pills clip.
    padding = max(4, 2 * min(float(label.cget("corner_radius")),
                            label.winfo_height() / label._get_widget_scaling() / 2))
    available = max(0, label.winfo_width() - padding * label._get_widget_scaling())
    icon = label.cget("image")
    if isinstance(icon, ctk.CTkImage):
        available = max(0, available - (icon.cget("size")[0] + 6) * label._get_widget_scaling())
    signature = (text, available, base_font, minimum_size, label._get_widget_scaling())
    if getattr(label, "_viking_fit_label_signature", None) == signature:
        return
    label._viking_fit_label_signature = signature
    family, base_size, *styles = base_font
    selected = minimum_size
    for size in range(int(base_size), minimum_size - 1, -1):
        font = NativeFontMetrics(label, label._apply_font_scaling((family, size, *styles)))
        if font.measure(text) <= available:
            selected = size
            break
    if getattr(label, "_viking_fit_font_size", None) != selected:
        label.configure(font=(family, selected, *styles))
        label._viking_fit_font_size = selected


class _StableToplevel(ctk.CTkToplevel):
    # CustomTkinter redraws the Windows title bar by withdrawing the window.
    # That conflicts with the app's own hide/show popup behaviour.
    _deactivate_windows_window_header_manipulation = True

    def __init__(self, *args, **kwargs):
        self._viking_after_ids = set()
        super().__init__(*args, **kwargs)

    def after(self, ms, func=None, *args):
        if func is None:
            return super().after(ms)
        def run():
            self._viking_after_ids.discard(identifier)
            return func(*args)
        identifier = super().after(ms, run)
        self._viking_after_ids.add(identifier)
        return identifier

    def after_cancel(self, identifier):
        self._viking_after_ids.discard(identifier)
        return super().after_cancel(identifier)

    def destroy(self):
        # CTk schedules title-bar/icon work at construction. Tcl timers survive
        # widget destruction unless cancelled, and can hit a recycled command
        # name when another dialog opens quickly.
        for identifier in tuple(self._viking_after_ids):
            self.after_cancel(identifier)
        super().destroy()


class StableTabview(ctk.CTkTabview):
    def _grid_forget_all_tabs(self, exclude_name=None):
        # CTk queues this 100 ms after set(). A stale callback must not hide
        # the new current tab if the user switches again before it executes.
        if exclude_name is not None and exclude_name != self.get():
            return
        super()._grid_forget_all_tabs(exclude_name)
