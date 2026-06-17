"""Tests for scripts/bump_version.py — read_version() file I/O.

Kept separate from test_bump_version.py (which tests the pure classify/
apply_bump/format_version logic) so each group can be reverted independently.
No git calls; VERSION_FILE is patched to point to a tmp_path file.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import scripts.bump_version as bv


def _write_version(path, ver_str: str) -> None:
    path.write_text(f'__version__ = "{ver_str}"\n', encoding="utf-8")


# --- read_version -----------------------------------------------------------

def test_read_version_parses_three_part(tmp_path):
    f = tmp_path / "version.py"
    _write_version(f, "0.10.0")
    with patch.object(bv, "VERSION_FILE", f):
        assert bv.read_version() == (0, 10, 0, 0)


def test_read_version_parses_four_part(tmp_path):
    f = tmp_path / "version.py"
    _write_version(f, "1.2.3.4")
    with patch.object(bv, "VERSION_FILE", f):
        assert bv.read_version() == (1, 2, 3, 4)


def test_read_version_parses_two_part(tmp_path):
    f = tmp_path / "version.py"
    _write_version(f, "2.0")
    with patch.object(bv, "VERSION_FILE", f):
        assert bv.read_version() == (2, 0, 0, 0)


def test_read_version_single_quotes(tmp_path):
    f = tmp_path / "version.py"
    f.write_text("__version__ = '0.5.1'\n", encoding="utf-8")
    with patch.object(bv, "VERSION_FILE", f):
        assert bv.read_version() == (0, 5, 1, 0)


def test_read_version_exits_when_no_version_found(tmp_path):
    f = tmp_path / "version.py"
    f.write_text("# no version here\n", encoding="utf-8")
    with patch.object(bv, "VERSION_FILE", f):
        with pytest.raises(SystemExit):
            bv.read_version()
