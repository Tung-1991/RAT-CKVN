from math import ceil
from time import monotonic
from typing import Any, Callable
import customtkinter as ctk
from .hint_box import HINT_FONT, HOVER_DELAY_MS, release_hint


class _HoverHint:
    def __init__(self, widget: Any, text: str | Callable[[], str], placement: str = "side", *,
                 font: tuple | None = None, max_width: int = 440, padding: tuple[int, int] = (10, 6),
                 fixed_size: bool = False, click_to_toggle: bool = False, hover: bool = True):
        self.widget, self.text, self.popup = widget, text, None
        self.placement = placement
        self.font, self.max_width, self.padding = font or HINT_FONT, max_width, padding
        self.fixed_size, self.leave_timer, self.dpi_timer = fixed_size, None, None
        self.show_timer = None
        self._hover_deadline, self._pointer = 0.0, None
        if hover:
            widget.bind("<Enter>", self._enter, add="+")
            widget.bind("<Motion>", self._motion, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<Destroy>", self._hide, add="+")
        widget.bind('<Button-1>', self._toggle if click_to_toggle else self._hide, add='+')
        for sequence in ("<Button-3>", "<MouseWheel>"):
            widget.bind(sequence, self._hide, add="+")

    def _toggle(self, event=None):
        self._hide() if self.popup else self._show(event)

    def _enter(self, _event: Any = None) -> None:
        if self.leave_timer is not None:
            self.widget.after_cancel(self.leave_timer)
            self.leave_timer = None
        self._pointer = self._pointer_position(_event)
        if self.popup is None:
            self._queue_hover()

    @staticmethod
    def _pointer_position(event):
        if event is None:
            return None
        return (getattr(event, "x_root", getattr(event, "x", 0)),
                getattr(event, "y_root", getattr(event, "y", 0)))

    def _motion(self, event: Any) -> None:
        if getattr(event, "state", 0) & 0x0100:
            self._hide()
            return
        point = self._pointer_position(event)
        if point != self._pointer:
            self._pointer = point
            if self.popup is None:
                self._queue_hover()

    def _queue_hover(self) -> None:
        self._hover_deadline = monotonic() + HOVER_DELAY_MS / 1000
        if self.show_timer is None:
            self.show_timer = self.widget.after(HOVER_DELAY_MS, self._show_when_idle)

    def _show_when_idle(self) -> None:
        remaining = ceil((self._hover_deadline - monotonic()) * 1000)
        if remaining > 0:
            self.show_timer = self.widget.after(remaining, self._show_when_idle)
        else:
            self._show()

    def _cancel_show(self) -> None:
        if self.show_timer is not None:
            self.widget.after_cancel(self.show_timer)
            self.show_timer = None
        self._hover_deadline = 0.0

    def _show(self, _event: Any = None) -> None:
        scheduled = self.show_timer is not None
        self._cancel_show()
        if self.popup or not self.widget.winfo_exists() or (scheduled and not self.widget.winfo_ismapped()):
            return
        text = self.text() if callable(self.text) else self.text
        if not text:
            return
        # Keep the hint inside the same Tk window. On Windows with DPI scaling,
        # mixing winfo_root* coordinates with a new Toplevel can place the hint
        # hundreds of pixels away from its icon.
        host = self.widget.winfo_toplevel()
        from .hint_box import bind_hint_leave, fixed_hint
        self.popup = fixed_hint(host, text, compact=not self.fixed_size,
                                font=self.font, max_width=self.max_width, padding=self.padding)
        bind_hint_leave(self.popup, self._leave)
        # fixed_hint sets its requested dimensions synchronously. Let Tk
        # handle its child layout normally; draining idle here also runs every
        # pending table/popup layout inside this hover callback.
        width, height = self.popup.winfo_reqwidth(), self.popup.winfo_reqheight()
        host_width = max(1, host.winfo_width())
        host_height = max(1, host.winfo_height())
        widget_x = self.widget.winfo_rootx() - host.winfo_rootx()
        widget_y = self.widget.winfo_rooty() - host.winfo_rooty()
        widget_width = self.widget.winfo_width()
        widget_height = self.widget.winfo_height()

        if self.placement in {"below", "inside"}:
            x = widget_x
            y = widget_y + widget_height + 8
            if y + height > host_height - 12:
                y = widget_y - height - 8
        else:
            x = widget_x + widget_width + 8
            if x + width > host_width - 12:
                # Keep the tooltip edge next to the icon instead of pinning the
                # tooltip to a distant screen corner.
                x = widget_x - width - 8
            y = widget_y - 4
            if y + height > host_height - 12:
                y = widget_y - height - 8

        x = min(max(8, x), max(8, host_width - width - 12))
        y = min(max(8, y), max(8, host_height - height - 12))
        self.popup.place(x=x, y=y)
        self.popup.lift()
        ctk.ScalingTracker.add_widget(self._dpi_changed, self.widget)

    def _dpi_changed(self, *_scaling: Any) -> None:
        # Do not remove a callback while CTk is iterating its callback list.
        # Recreate on next hover using the new font, bounds and position.
        if self.popup and self.dpi_timer is None:
            self.dpi_timer = self.widget.after_idle(self._hide)

    def _leave(self, _event: Any = None) -> None:
        self._cancel_show()
        self._pointer = None
        if self.popup is None:
            return
        if self.leave_timer is not None:
            self.widget.after_cancel(self.leave_timer)
        def check():
            from .hint_box import contains_pointer
            self.leave_timer = None
            if not contains_pointer(self.popup) and not contains_pointer(self.widget):
                self._hide()
        self.leave_timer = self.widget.after(120, check)

    def _hide(self, _event: Any = None) -> None:
        self._cancel_show()
        self._pointer = None
        if self.dpi_timer is not None:
            self.widget.after_cancel(self.dpi_timer)
            self.dpi_timer = None
        if self.leave_timer is not None:
            self.widget.after_cancel(self.leave_timer)
            self.leave_timer = None
        if self.popup:
            ctk.ScalingTracker.remove_widget(self._dpi_changed, self.widget)
            release_hint(self.popup)
            self.popup = None

