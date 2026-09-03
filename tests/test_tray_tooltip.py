import tkinter as tk

import pytest

from obsidian_sync_tray.tooltip import Tooltip


@pytest.fixture
def root(tk_root):
    # See test_tray_options_window.py for why this is the shared session root.
    return tk_root


class TestTooltip:
    def test_show_creates_a_popup_with_the_given_text(self, root):
        widget = tk.Label(root, text="a field")
        widget.pack()
        root.update()
        tip = Tooltip(widget, "helpful explanation")
        try:
            assert tip._popup is None
            tip._show()
            assert tip._popup is not None
            assert tip._popup.winfo_exists()
        finally:
            tip._hide()
            widget.destroy()

    def test_leave_hides_the_popup(self, root):
        widget = tk.Label(root, text="a field")
        widget.pack()
        root.update()
        tip = Tooltip(widget, "helpful explanation")
        try:
            tip._show()
            popup = tip._popup
            tip._on_leave()
            assert tip._popup is None
            assert not popup.winfo_exists()
        finally:
            widget.destroy()

    def test_enter_schedules_a_show_after_a_delay_without_showing_immediately(self, root):
        widget = tk.Label(root, text="a field")
        widget.pack()
        root.update()
        tip = Tooltip(widget, "helpful explanation")
        try:
            tip._on_enter()
            assert tip._popup is None  # not shown yet -- only scheduled
            assert tip._after_id is not None
        finally:
            tip._on_leave()
            widget.destroy()

    def test_empty_text_never_shows_a_popup(self, root):
        widget = tk.Label(root, text="a field")
        widget.pack()
        root.update()
        tip = Tooltip(widget, "")
        try:
            tip._show()
            assert tip._popup is None
        finally:
            widget.destroy()

    def test_show_is_idempotent_while_already_visible(self, root):
        widget = tk.Label(root, text="a field")
        widget.pack()
        root.update()
        tip = Tooltip(widget, "helpful explanation")
        try:
            tip._show()
            first_popup = tip._popup
            tip._show()
            assert tip._popup is first_popup
        finally:
            tip._hide()
            widget.destroy()
