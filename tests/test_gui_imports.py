"""Smoke test: the desktop GUI module imports cleanly.

Importing builds no window (Tk() is only created in main()), so this is safe and
fast — it just catches a syntax error or a bad import in gui.py before it ships,
since the GUI is otherwise not exercised by the suite.
"""
from __future__ import annotations


def test_gui_module_imports():
    import gui
    assert hasattr(gui, "GrecoGUI")
