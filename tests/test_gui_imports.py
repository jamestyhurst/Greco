"""Smoke test: the desktop GUI module imports cleanly.

Importing builds no window (Tk() is only created in main()), so this is safe and
fast — it just catches a syntax error or a bad import in gui.py before it ships,
since the GUI is otherwise not exercised by the suite.
"""
from __future__ import annotations


def test_gui_module_imports():
    import gui
    assert hasattr(gui, "GrecoGUI")


def test_default_pgn_dir_is_an_existing_folder():
    import gui
    from pathlib import Path
    d = gui.default_pgn_dir()
    assert isinstance(d, str) and Path(d).is_dir()
