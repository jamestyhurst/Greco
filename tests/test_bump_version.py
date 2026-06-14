"""The release-automation logic (scripts/bump_version.py).

Pure functions — no git needed. Pins the rules that decide every version bump.
"""
from __future__ import annotations

from scripts.bump_version import (
    MAJOR, MINOR, PATCH, MICRO, NONE,
    apply_bump, classify, format_version,
)


def test_classify_conventional_types():
    assert classify("feat: add adapter", "") == MINOR
    assert classify("fix: wrong square", "") == PATCH
    assert classify("micro: tweak colour", "") == MICRO
    assert classify("docs: update readme", "") == NONE
    assert classify("chore: bump deps", "") == NONE
    assert classify("refactor: extract gate", "") == NONE
    assert classify("not a conventional subject", "") == NONE
    assert classify("feat(web): scoped", "") == MINOR


def test_classify_breaking_changes():
    assert classify("feat!: drop old api", "") == MAJOR
    assert classify("fix: x", "body\n\nBREAKING CHANGE: removed Y") == MAJOR


def test_apply_bump_resets_lower_digits():
    assert apply_bump((0, 3, 1, 0), PATCH) == (0, 3, 2, 0)
    assert apply_bump((0, 3, 1, 4), MINOR) == (0, 4, 0, 0)
    assert apply_bump((0, 3, 1, 2), MICRO) == (0, 3, 1, 3)
    assert apply_bump((0, 4, 5, 6), MAJOR) == (1, 0, 0, 0)
    assert apply_bump((0, 3, 1, 0), NONE) == (0, 3, 1, 0)


def test_format_version_omits_trailing_zero_micro():
    assert format_version((0, 3, 1, 0)) == "0.3.1"
    assert format_version((0, 3, 1, 2)) == "0.3.1.2"
    assert format_version((1, 0, 0, 0)) == "1.0.0"
