"""Shared compact cards and directly visible choices."""
import tkinter as tk
import customtkinter as ctk
from .theme import BORDER, SURFACE, SURFACE_2, TITLE, TEXT, BLUE
from .mayin.widgets import StableTabview, choice_bar


LABELS = {"POINTS": "ĐIỂM", "PERCENT": "% GIÁ", "ORIGINAL": "GỐC", "REMAINING": "CÒN GIỮ",
          "SESSIONS": "X PHIÊN", "VA": "∞ VA"}


class CompactForm:
    def __init__(self, variables):
        self.variables = variables

    def card(self, parent, title, row=0, column=0, *, span=1):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, border_width=1, border_color=BORDER, corner_radius=8)
        card.grid(row=row, column=column, columnspan=span, sticky="new", padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, text_color=TITLE, font=("Segoe UI", 12, "bold"), height=23,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 3))
        card._next_row = 1
        return card

    def field(self, parent, key, label, value, *, choices=None, secret=False, width=100):
        index = parent._next_row
        parent._next_row += 1
        row = ctk.CTkFrame(parent, fg_color="transparent", height=30)
        row.grid(row=index, column=0, sticky="ew", padx=8, pady=2)
        row.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(row, text=label, anchor="w", height=25, font=("Segoe UI", 11), text_color=TEXT)
        title.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        variable = tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=str(value))
        self.variables[key] = variable
        if isinstance(value, bool):
            widget = ctk.CTkSwitch(row, text="", variable=variable, width=40, switch_width=30, switch_height=16)
        elif choices:
            display = tk.StringVar(value=LABELS.get(str(value), str(value)))
            values = {LABELS.get(v, v): v for v in choices}
            widget = choice_bar(row, values=list(values), variable=display, height=34,
                font=("Segoe UI", 13, "bold"),
                command=lambda selected: variable.set(values[selected]))
            variable.trace_add("write", lambda *_: display.set(LABELS.get(variable.get(), variable.get())))
        else:
            widget = ctk.CTkEntry(row, textvariable=variable, width=width, height=27, justify="right",
                font=("Segoe UI", 12), show="●" if secret else "")
        widget.grid(row=0, column=1, sticky="e", pady=1)
        widget._compact_control = True
        return widget


def columns(parent, count=2):
    parent.grid_columnconfigure(tuple(range(count)), weight=1, uniform="compact")


def tabs(parent):
    view = StableTabview(parent, fg_color=SURFACE, border_width=1, border_color='#34465A',
        anchor='nw', segmented_button_fg_color='#172330',
        segmented_button_selected_color='#286AA6', segmented_button_selected_hover_color='#337EBE',
        segmented_button_unselected_color='#222E3B', segmented_button_unselected_hover_color='#32475D',
        text_color='#E3EDF8')
    view._segmented_button.configure(font=('Segoe UI',14,'bold'),height=36,corner_radius=7)
    return view
