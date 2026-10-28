"""Small, selectable hints, bounded independently of Tk's point scaling."""
import tkinter as tk

import customtkinter as ctk

HINT_FONT = ("Segoe UI", 12)
HOVER_DELAY_MS = 500
HINT_SIZE = (440, 220)
COMPACT_HINT_SIZE = (340, 180)


def copy_text(widget, text):
    """Write only after an explicit copy action; preserve Unicode and newlines."""
    if text:
        widget.clipboard_clear()
        widget.clipboard_append(text)
    return "break"


def bind_hint_leave(box, callback):
    """Include nested controls so leaving a copy button also dismisses the hint."""
    box._hint_leave = callback
    if getattr(box, "_hint_leave_bound", False):
        return
    def bind(widget):
        widget.bind("<Leave>", lambda event: box._hint_leave(event) if box._hint_leave else None, add="+")
        for child in widget.winfo_children():
            bind(child)
    bind(box)
    box._hint_leave_bound = True


def release_hint(box):
    """Keep at most one hidden panel per window, ready for the next hover."""
    if box is None or not box.winfo_exists():
        return
    host = box.master
    focus = host.focus_get()
    while focus is not None:
        if focus is box:
            host.focus_set()
            break
        focus = getattr(focus, "master", None)
    box.place_forget()
    box._hint_leave = None
    if getattr(host, "_viking_hint_spare", None) is None:
        host._viking_hint_spare = box
    else:
        box.destroy()


def fixed_hint(host, text, *, compact=False, font=None, max_width=None, padding=(10, 6)):
    scale = ctk.ScalingTracker.get_widget_scaling(host)
    limit = COMPACT_HINT_SIZE if compact else HINT_SIZE
    width = min(round(min(limit[0], max_width or limit[0]) * scale), max(1, host.winfo_width() - 24))
    max_height = min(round(limit[1] * scale), max(1, host.winfo_height() - 24))
    padx, pady = (round(value * scale) for value in padding)
    logical_font = font or HINT_FONT
    font = (logical_font[0], -max(1, round(abs(logical_font[1]) * scale)), *logical_font[2:])
    footer_height = round(27 * scale)
    # Measure wrapped text before constructing the viewport. Short hints fit
    # their content; only long details need the bounded, scrollable panel.
    # Reserve scrollbar space so adding it cannot introduce clipped lines.
    measure = getattr(host, "_viking_hint_measure", None)
    if measure is None or not measure.winfo_exists():
        measure = host._viking_hint_measure = tk.Label(host, justify="left", borderwidth=0, highlightthickness=0)
    measure_key = (text, font, padx, pady, max(1, width - 2 * padx - round(18 * scale)))
    if getattr(measure, "_hint_measure_key", None) != measure_key:
        measure.configure(text=text, font=font, padx=padx, pady=pady, wraplength=measure_key[-1])
        measure._hint_measure_key = measure_key
    if compact:
        width = min(width, max(round(100 * scale), measure.winfo_reqwidth() + round(18 * scale) + 2))
    height = min(max_height, measure.winfo_reqheight() + footer_height + 2)
    box = getattr(host, "_viking_hint_spare", None)
    host._viking_hint_spare = None
    layout = (width, height, font, padx, pady, footer_height, scale)
    if box is not None and box.winfo_exists():
        if box._hint_layout != layout:
            box.configure(width=width, height=height)
            box.body.configure(font=font, padx=padx, pady=pady)
            box.footer.configure(height=footer_height)
            box.copy_button.configure(font=font, padx=round(8 * scale))
            box.copy_button.grid_configure(padx=round(6 * scale), pady=(0, round(4 * scale)))
            box._hint_layout = layout
        if box._hint_text != text:
            box.body.configure(state="normal")
            box.body.delete("1.0", "end")
            box.body.insert("1.0", text)
            box.body.configure(state="disabled")
            box._hint_text = text
        box.body.tag_remove("sel", "1.0", "end")
        box.body.yview_moveto(0)
        return box
    box = tk.Frame(host, width=width, height=height, bg="#252A31", highlightthickness=1,
                   highlightbackground="#59616E")
    box.grid_propagate(False)
    box.grid_rowconfigure(0, weight=1)
    box.grid_columnconfigure(0, weight=1)
    body = tk.Text(box, wrap="word", font=font,
                   bg="#252A31", fg="#F5F7FA", relief="flat", borderwidth=0,
                   highlightthickness=0, cursor="xterm", padx=padx,
                   pady=pady, spacing1=0, spacing3=0,
                   exportselection=False)
    body.grid(row=0, column=0, sticky="nsew")
    scroll = tk.Scrollbar(box, orient="vertical", command=body.yview)
    scroll.grid(row=0, column=1, sticky="ns", padx=(0, 3), pady=3)
    def viewport(first, last):
        scroll.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            scroll.grid_remove()
        else:
            scroll.grid()
    body.configure(yscrollcommand=viewport)
    body.insert("1.0", text)
    body.configure(state="disabled")
    # A disabled Text still supports selection. Hover never steals keyboard
    # focus; clicking the text enables Ctrl+A / Ctrl+C without editing it.
    body.bind("<Button-1>", lambda _event: body.focus_set(), add="+")
    def select_all(_event=None):
        body.tag_add("sel", "1.0", "end-1c")
        return "break"
    def copy_selection(_event=None):
        selection = body.tag_ranges("sel")
        return copy_text(body, body.get(*selection) if selection else body.get("1.0", "end-1c"))
    body.bind("<Control-a>", select_all)
    body.bind("<Control-A>", select_all)
    body.bind("<<Copy>>", copy_selection)
    body.bind("<Control-c>", copy_selection)
    body.bind("<Control-C>", copy_selection)
    footer = tk.Frame(box, height=footer_height, bg="#252A31")
    footer.grid(row=1, column=0, columnspan=2, sticky="ew")
    footer.grid_propagate(False)
    footer.grid_columnconfigure(0, weight=1)
    button = tk.Button(footer, text="Sao chép", command=lambda: copy_text(body, body.get("1.0", "end-1c")),
                       font=font, bg="#343B45", fg="#F5F7FA", activebackground="#445063",
                       activeforeground="#FFFFFF", relief="flat", borderwidth=0,
                       padx=round(8 * scale), pady=0, cursor="hand2")
    button.grid(row=0, column=0, sticky="e", padx=round(6 * scale), pady=(0, round(4 * scale)))
    box.body = body
    box.footer = footer
    box.copy_button = button
    box._hint_layout, box._hint_text = layout, text
    return box


def contains_pointer(widget):
    if widget is None or not widget.winfo_exists():
        return False
    x, y = widget.winfo_pointerxy()
    return (widget.winfo_rootx() <= x < widget.winfo_rootx() + widget.winfo_width()
            and widget.winfo_rooty() <= y < widget.winfo_rooty() + widget.winfo_height())
