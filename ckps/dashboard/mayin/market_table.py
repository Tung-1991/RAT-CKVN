"""Responsive, per-cell market tables using the MayinTien palette and fonts."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

import customtkinter as ctk

from .tokens import (COL_BORDER, COL_MUTED, COL_SURFACE, COL_SURFACE_2, COL_TEXT, COL_TITLE,
    COL_PANEL_HEADER, COL_PANEL_BODY, COL_GRID, COL_GRID_SOFT, COL_SELECTED_ROW, COL_ACCENT_BLUE)


class MarketTable(ctk.CTkFrame):
    """Small Treeview-compatible model with two-line cells and automatic sizing.

    Only visible rows are painted. Sorting/repainting never changes selection,
    row identity or the data returned to the order/position actions.
    """

    def __init__(self, master, columns, *, hierarchy=False, empty_text="Chưa có dữ liệu"):
        super().__init__(master, fg_color=COL_SURFACE, corner_radius=6, width=1, height=1)
        self._columns = {key: dict(text=label, width=width, minwidth=width * .78,
                                  anchor="w", weight=1) for key, label, width in columns}
        if hierarchy:
            self._columns = {"#0": dict(text="HỢP ĐỒNG", width=155, minwidth=128,
                                       anchor="w", weight=2), **self._columns}
        self._display = tuple(self._columns)
        self._rows, self._children, self._selection = {}, {"": []}, ()
        self._pending_draw = None
        self._empty_text = empty_text
        self._bounds = []
        self._visible_rows = []
        self._row_height = 56
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.header = tk.Canvas(self, width=1, height=38, bg=COL_PANEL_HEADER, bd=0, highlightthickness=0)
        self.body = tk.Canvas(self, width=1, height=1, bg=COL_SURFACE, bd=0, highlightthickness=0, takefocus=True)
        self.header.grid(row=0, column=0, sticky="ew")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.vertical = ctk.CTkScrollbar(self, command=self.yview, width=10,
            fg_color=COL_SURFACE, button_color="#3A424D", button_hover_color="#596777")
        self.horizontal = ctk.CTkScrollbar(self, command=self.xview, orientation="horizontal", height=10,
            fg_color=COL_SURFACE, button_color="#3A424D", button_hover_color="#596777")
        self.body.configure(yscrollcommand=self._vertical_changed, xscrollcommand=self._horizontal_changed)
        self.body.bind("<Configure>", self._queue_draw)
        self.header.bind("<Configure>", self._queue_draw)
        self.body.bind("<Button-1>", self._click)
        self.body.bind("<MouseWheel>", self._wheel)
        self.body.bind("<Up>", lambda event: self._step(-1))
        self.body.bind("<Down>", lambda event: self._step(1))
        self.body.bind("<Home>", lambda event: self._step(-len(self._rows)))
        self.body.bind("<End>", lambda event: self._step(len(self._rows)))
        self.body.bind("<Return>", lambda event: self.body.event_generate("<<RowActivate>>"))
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._queue_draw()

    def bind(self, sequence=None, command=None, add=True):
        if hasattr(self, "body"):
            return self.body.bind(sequence, command, add="+" if add else None)
        return super().bind(sequence, command, add=add)

    def _set_scaling(self, *args, **kwargs):
        super()._set_scaling(*args, **kwargs)
        if hasattr(self, "body"):
            self._queue_draw()

    def _on_destroy(self, event):
        if event.widget is self.body and self._pending_draw:
            self.after_cancel(self._pending_draw)
            self._pending_draw = None

    def configure(self, require_redraw=False, **kwargs):
        if "displaycolumns" in kwargs:
            displayed = tuple(kwargs.pop("displaycolumns"))
            self._display = (("#0",) if "#0" in self._columns else ()) + displayed
            self._queue_draw()
        return super().configure(require_redraw=require_redraw, **kwargs)

    config = configure

    def heading(self, key, **kwargs):
        self._columns[key].update(kwargs)
        self._queue_draw()

    def column(self, key, option=None, **kwargs):
        if kwargs:
            self._columns[key].update(kwargs)
            self._queue_draw()
        return self._columns[key].get(option) if option else dict(self._columns[key])

    def insert(self, parent, index, *, iid, text="", values=(), tags=(), open=True):
        self._rows[iid] = dict(parent=parent, text=text, values=tuple(values), tags=tuple(tags), open=open, cells={})
        siblings = self._children.setdefault(parent, [])
        siblings.append(iid) if index == "end" else siblings.insert(int(index), iid)
        self._children.setdefault(iid, [])
        self._queue_draw()
        return iid

    def item(self, iid, option=None, **kwargs):
        row = self._rows[iid]
        changed = False
        for key, value in kwargs.items():
            value = tuple(value) if key in {"values", "tags"} else value
            if row.get(key) != value:
                row[key], changed = value, True
        if changed:
            self._queue_draw()
        return row.get(option) if option else dict(row)

    def cell(self, iid, key, **kwargs):
        row = self._rows[iid]
        if kwargs and row["cells"].get(key) != kwargs:
            row["cells"][key] = kwargs
            self._queue_draw()
        return dict(row["cells"].get(key, {}))

    def exists(self, iid):
        return iid in self._rows

    def get_children(self, iid=""):
        return tuple(self._children.get(iid, ()))

    def parent(self, iid):
        return self._rows[iid]["parent"]

    def move(self, iid, parent, index):
        old = self._rows[iid]["parent"]
        siblings = self._children.setdefault(parent, [])
        if old == parent and index == "end" and siblings and siblings[-1] == iid:
            return
        self._children[old].remove(iid)
        siblings.append(iid) if index == "end" else siblings.insert(int(index), iid)
        self._rows[iid]["parent"] = parent
        self._queue_draw()

    def delete(self, *iids):
        for iid in iids:
            for child in tuple(self._children.get(iid, ())):
                self.delete(child)
            self._children[self.parent(iid)].remove(iid)
            self._children.pop(iid, None)
            self._rows.pop(iid)
            if iid in self._selection:
                self.selection_set(())
        self._queue_draw()

    def selection(self):
        return self._selection

    def selection_set(self, iid):
        selected = (iid,) if isinstance(iid, str) and iid else tuple(iid)
        if selected != self._selection:
            self._selection = selected
            self._queue_draw()
            self.body.event_generate("<<TreeviewSelect>>", when="tail")

    def identify_row(self, y):
        index = int(self.body.canvasy(y) // self._row_height)
        return self._visible_rows[index] if 0 <= index < len(self._visible_rows) else ""

    def _click(self, event):
        self.body.focus_set()
        self.selection_set(self.identify_row(event.y))

    def _step(self, delta):
        if self._visible_rows:
            current = self._visible_rows.index(self._selection[0]) if self._selection else (-1 if delta > 0 else 0)
            index = max(0, min(len(self._visible_rows) - 1, current + delta))
            self.selection_set(self._visible_rows[index])
            y = index * self._row_height
            top = self.body.canvasy(0)
            if y < top or y + self._row_height > top + self.body.winfo_height():
                self.body.yview_moveto(y / max(1, len(self._visible_rows) * self._row_height))
            self._queue_draw()
        return "break"

    def _wheel(self, event):
        self.yview("scroll", -int(event.delta / 120) * 2, "units")
        return "break"

    def yview(self, *args):
        result = self.body.yview(*args)
        self._queue_draw()
        return result

    def xview(self, *args):
        result = self.body.xview(*args)
        self.header.xview_moveto(self.body.xview()[0])
        return result

    def _vertical_changed(self, first, last):
        self.vertical.set(first, last)

    def _horizontal_changed(self, first, last):
        self.horizontal.set(first, last)
        self.header.xview_moveto(first)

    def _queue_draw(self, event=None):
        if self._pending_draw is None:
            self._pending_draw = self.after_idle(self._paint_rows)

    @staticmethod
    def _ellipsize(text, font, width):
        text = str(text)
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text.rstrip() + "…" if text else ""

    def _flatten(self, parent=""):
        for iid in self._children.get(parent, ()):
            yield iid
            if self._rows[iid]["open"]:
                yield from self._flatten(iid)

    def _paint_rows(self):
        self._pending_draw = None
        if not self.winfo_exists():
            return
        scale = self._get_widget_scaling()
        self._row_height = round(56 * scale)
        width, height = self.body.winfo_width(), self.body.winfo_height()
        if width < 2:
            return
        self.header.configure(height=round(36 * scale))
        minimum = sum(self._columns[key]["minwidth"] * scale for key in self._display)
        content_width = max(width, round(minimum))
        extra = max(0, content_width - minimum)
        total_weight = sum(self._columns[key]["weight"] for key in self._display)
        self._bounds, left = [], 0
        for key in self._display:
            col = self._columns[key]
            cell_width = col["minwidth"] * scale + extra * col["weight"] / total_weight
            self._bounds.append((key, left, left + cell_width))
            left += cell_width
        self._visible_rows = list(self._flatten())
        content_height = max(height, len(self._visible_rows) * self._row_height)
        self.body.configure(scrollregion=(0, 0, content_width, content_height), yscrollincrement=self._row_height)
        header_height=self.header.winfo_height()
        self.header.configure(scrollregion=(0, 0, content_width, header_height))
        self.header.yview_moveto(0)
        self.vertical.grid(row=1, column=1, sticky="ns") if content_height > height else self.vertical.grid_remove()
        self.horizontal.grid(row=2, column=0, sticky="ew") if content_width > width + 1 else self.horizontal.grid_remove()
        self.header.delete("all")
        self.body.delete("all")
        heading_font = tkfont.Font(root=self, family="Segoe UI", size=-round(14 * scale), weight="bold")
        value_font = tkfont.Font(root=self, family="Segoe UI", size=-round(16 * scale))
        number_font = tkfont.Font(root=self, family="Cascadia Mono", size=-round(16 * scale))
        detail_font = tkfont.Font(root=self, family="Segoe UI", size=-round(14 * scale))
        self._fonts = heading_font, value_font, number_font, detail_font
        for key, x1, x2 in self._bounds:
            col = self._columns[key]
            anchor = col["anchor"]
            pad=round((6 if anchor=='center' else 12)*scale)
            x = x2 - pad if anchor == "e" else (x1+x2)/2 if anchor == "center" else x1+pad
            self.header.create_text(x, header_height/2, text=self._ellipsize(col["text"], heading_font, x2-x1-2*pad),
                anchor=anchor, fill=COL_TITLE, font=heading_font)
        self.header.create_line(0, header_height-1, content_width, header_height-1, fill=COL_GRID)
        if not self._visible_rows:
            self.body.create_text(width / 2, min(height / 2, 90 * scale), text=self._empty_text,
                                  fill=COL_MUTED, font=value_font)
        top = max(0, int(self.body.canvasy(0) // self._row_height))
        bottom = min(len(self._visible_rows), top + int(height / self._row_height) + 2)
        keys = [key for key in self._columns if key != "#0"]
        for index in range(top, bottom):
            iid = self._visible_rows[index]
            row = self._rows[iid]
            y1, y2 = index*self._row_height, (index+1)*self._row_height
            selected = iid in self._selection
            bg = COL_SELECTED_ROW if selected else COL_PANEL_BODY if index % 2 == 0 else COL_SURFACE
            self.body.create_rectangle(0, y1, content_width, y2, fill=bg, outline="")
            if selected:
                self.body.create_rectangle(0, y1, 3*scale, y2, fill=COL_ACCENT_BLUE, outline="")
            self.body.create_line(0, y2-1, content_width, y2-1, fill=COL_GRID_SOFT)
            for key, x1, x2 in self._bounds:
                cell = row["cells"].get(key, {})
                raw = row["text"] if key == "#0" else row["values"][keys.index(key)] if keys.index(key) < len(row["values"]) else ""
                value, detail = str(cell.get("text", raw)), str(cell.get("detail", ""))
                anchor = self._columns[key]["anchor"]
                pad=round((6 if anchor=='center' else 12)*scale)
                indent = 12 * scale if key == "#0" and row["parent"] else 0
                x = x2-pad if anchor == "e" else (x1+x2)/2 if anchor == "center" else x1+pad+indent
                available = x2-x1-2*pad-indent
                font = number_font if cell.get("numeric") else value_font
                if key == "#0" and row["parent"]:
                    value = "↳ " + value
                self.body.create_text(x, y1+(21 if detail else 30)*scale,
                    text=self._ellipsize(value, font, available), anchor=anchor,
                    fill=cell.get("color", COL_TEXT), font=font)
                if detail:
                    self.body.create_text(x, y1+41*scale, text=self._ellipsize(detail, detail_font, available),
                        anchor=anchor, fill=cell.get("detail_color", COL_MUTED), font=detail_font)
        # One continuous guide per visible column, aligned between header and
        # body even when the table is empty or scrolled. Rows remain neutral.
        for _key,_left,right in self._bounds[:-1]:
            self.header.create_line(right,0,right,header_height,fill=COL_GRID,tags='column-guide')
            self.body.create_line(right,0,right,content_height,fill=COL_GRID_SOFT,tags='column-guide')
