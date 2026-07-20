"""Regression tests: the Analyze action bar must always be visible.

The 2026-06-18 paste-PGN box pushed the form past the fixed 760x700 window, and
Tk's packer silently unmaps whatever no longer fits — which was everything below
the Setup section: the Analyze button, status line, report buttons, and log. The
fix pins the action bar to the bottom of the window with pack(side="bottom")
*before* the content sections, so when vertical space runs short the log and
sections give way, never the buttons.

These tests need a real display (they build actual Tk windows); they skip
automatically on headless CI where Tk cannot connect to a screen.
"""
from __future__ import annotations

import pytest
import tkinter as tk


def _make_root() -> tk.Tk:
    try:
        return tk.Tk()
    except tk.TclError:
        pytest.skip("no display available (headless environment)")


def _visible_in_window(root: tk.Tk, widget) -> bool:
    """Mapped by the packer AND fully inside the window's client area."""
    if not widget.winfo_ismapped():
        return False
    y = widget.winfo_rooty() - root.winfo_rooty()
    return 0 <= y and (y + widget.winfo_height()) <= root.winfo_height()


def _build(root: tk.Tk):
    import gui
    app = gui.GrecoGUI(root)
    root.update_idletasks()
    root.update()
    return app


def test_analyze_button_visible_at_launch_size():
    root = _make_root()
    try:
        app = _build(root)
        assert _visible_in_window(root, app.analyze_btn), (
            "Analyze button is not visible at the launch window size — "
            "the packer clipped the action bar (the 2026-07 regression)"
        )
    finally:
        root.destroy()


def test_action_bar_survives_a_squeeze_to_minsize():
    """Even at the smallest allowed window, the action bar must not clip."""
    root = _make_root()
    try:
        app = _build(root)
        root.geometry("640x600")  # the declared minsize
        root.update_idletasks()
        root.update()
        for name in ("analyze_btn", "open_report_btn", "open_folder_btn", "export_btn"):
            widget = getattr(app, name)
            assert _visible_in_window(root, widget), (
                f"{name} clipped at the 640x600 minimum window size — "
                "the action bar must be pinned with higher pack priority than "
                "the content sections and log"
            )
    finally:
        root.destroy()


def test_window_height_fits_on_this_screen():
    """The launch geometry must never exceed the screen (no off-screen rows)."""
    root = _make_root()
    try:
        _build(root)
        assert root.winfo_height() <= root.winfo_screenheight(), (
            "launch window is taller than the screen"
        )
    finally:
        root.destroy()
