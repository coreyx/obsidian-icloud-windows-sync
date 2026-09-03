"""
A minimal hover tooltip for tkinter widgets. Stdlib tkinter has no built-in
tooltip widget, so this fills that gap: a small borderless popup that
appears near the widget after a short hover delay and disappears on
mouse-leave or click.
"""

import tkinter as tk


class Tooltip:
    DELAY_MS = 500

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._after_id = None
        self._popup = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._unschedule()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _on_leave(self, event=None):
        self._unschedule()
        self._hide()

    def _unschedule(self):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self._popup is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._popup = tk.Toplevel(self.widget)
        self._popup.wm_overrideredirect(True)
        self._popup.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._popup, text=self.text, justify="left", background="#ffffe0",
            relief="solid", borderwidth=1, padx=6, pady=3, wraplength=320,
            font=("Segoe UI", 8),
        ).pack()

    def _hide(self):
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
