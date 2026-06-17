"""Tests for commentary.py — style-guide loader and transcript collector.

All tests use pytest's tmp_path fixture to build a temporary commentary_refs/
directory. No external services, no Stockfish, no API calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import commentary


def _make_ref(base: Path, slug: str, transcript: str,
              meta: dict | None = None, pgn: str | None = None) -> Path:
    """Create a commentary_refs/<slug>/ subfolder with the given content."""
    sub = base / slug
    sub.mkdir(parents=True)
    (sub / "transcript.txt").write_text(transcript, encoding="utf-8")
    if meta:
        (sub / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if pgn:
        (sub / "game.pgn").write_text(pgn, encoding="utf-8")
    return sub


LONG_TRANSCRIPT = "A" * 300  # 300 chars > the 200-char minimum


# ---------------------------------------------------------------------------
# load_style_guide
# ---------------------------------------------------------------------------

def test_load_style_guide_returns_empty_when_missing(tmp_path):
    fake_path = tmp_path / "nonexistent.md"
    with patch.object(commentary, "STYLE_GUIDE_PATH", fake_path):
        assert commentary.load_style_guide() == ""


def test_load_style_guide_wraps_content(tmp_path):
    guide = tmp_path / "style.md"
    guide.write_text("Be vivid. Vary sentence length.", encoding="utf-8")
    with patch.object(commentary, "STYLE_GUIDE_PATH", guide):
        result = commentary.load_style_guide()
    assert "## Greco house voice" in result
    assert "Be vivid." in result


def test_load_style_guide_truncates_at_max_chars(tmp_path):
    guide = tmp_path / "style.md"
    guide.write_text("X" * 5000, encoding="utf-8")
    with patch.object(commentary, "STYLE_GUIDE_PATH", guide):
        result = commentary.load_style_guide(max_chars=100)
    assert "…(style guide truncated)" in result
    assert len(result) < 5000


# ---------------------------------------------------------------------------
# load_commentary_references — filtering rules
# ---------------------------------------------------------------------------

def test_valid_ref_appears_in_output(tmp_path):
    refs = tmp_path / "commentary_refs"
    _make_ref(refs, "agadmator-test", LONG_TRANSCRIPT,
              meta={"title": "Kasparov Immortal", "commentator": "Agadmator"})
    with patch.object(commentary, "REFS_DIR", refs):
        result = commentary.load_commentary_references()
    assert "Kasparov Immortal" in result
    assert "Agadmator" in result
    assert "## Learning from real chess commentators" in result


def test_underscore_prefix_folder_is_skipped(tmp_path):
    refs = tmp_path / "commentary_refs"
    _make_ref(refs, "_example", LONG_TRANSCRIPT)
    with patch.object(commentary, "REFS_DIR", refs):
        result = commentary.load_commentary_references()
    assert result == ""


def test_dot_prefix_folder_is_skipped(tmp_path):
    refs = tmp_path / "commentary_refs"
    _make_ref(refs, ".hidden", LONG_TRANSCRIPT)
    with patch.object(commentary, "REFS_DIR", refs):
        result = commentary.load_commentary_references()
    assert result == ""


def test_short_transcript_is_skipped(tmp_path):
    refs = tmp_path / "commentary_refs"
    _make_ref(refs, "stub", "Too short.")  # well under 200 chars
    with patch.object(commentary, "REFS_DIR", refs):
        result = commentary.load_commentary_references()
    assert result == ""


def test_placeholder_transcript_is_skipped(tmp_path):
    refs = tmp_path / "commentary_refs"
    _make_ref(refs, "unfilled", "PLACEHOLDER — fill this in later " + "x" * 200)
    with patch.object(commentary, "REFS_DIR", refs):
        result = commentary.load_commentary_references()
    assert result == ""


def test_max_refs_is_respected(tmp_path):
    refs = tmp_path / "commentary_refs"
    for i in range(5):
        _make_ref(refs, f"ref-{i:02d}", LONG_TRANSCRIPT,
                  meta={"title": f"Title {i}", "commentator": "C"})
    with patch.object(commentary, "REFS_DIR", refs):
        result = commentary.load_commentary_references(max_refs=2)
    # Only 2 of the 5 refs should appear.
    assert result.count('Reference: "') == 2


def test_no_refs_dir_returns_empty(tmp_path):
    missing = tmp_path / "no_such_dir"
    with patch.object(commentary, "REFS_DIR", missing):
        assert commentary.load_commentary_references() == ""


def test_pgn_game_label_appears(tmp_path):
    refs = tmp_path / "commentary_refs"
    pgn_text = '[White "Kasparov"][Black "Topalov"][Event "Wijk aan Zee 1999"]\n1. e4'
    _make_ref(refs, "immortal", LONG_TRANSCRIPT, pgn=pgn_text)
    with patch.object(commentary, "REFS_DIR", refs):
        result = commentary.load_commentary_references()
    assert "Kasparov" in result
    assert "Topalov" in result
