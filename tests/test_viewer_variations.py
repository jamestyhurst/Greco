"""Tests for the clickable-variation feature in the PGN replay viewer (#22).

Pure, no engine. Tests _pv_to_fen_plies() correctness and verifies that
build_pgn_viewer() embeds per-ply FEN data in the JSON payload.
"""
import json
import re

import pytest

from outputs import _pv_to_fen_plies, build_pgn_viewer

_START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
_AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


# --- _pv_to_fen_plies --------------------------------------------------------

def test_pv_three_plies_produces_correct_sans_and_fens():
    plies = _pv_to_fen_plies(_START, "1. e4 e5 2. Nf3")
    assert len(plies) == 3
    assert [p["san"] for p in plies] == ["e4", "e5", "Nf3"]
    assert all("fen" in p and "uci" in p for p in plies)
    # FEN after e4 should have the pawn on e4
    assert "/4P3/" in plies[0]["fen"]


def test_pv_black_first_strips_ellipsis():
    # Black moves first: "1...e5 2. Nf3"
    plies = _pv_to_fen_plies(_AFTER_E4, "1...e5 2. Nf3")
    assert len(plies) == 2
    assert plies[0]["san"] == "e5"
    assert plies[1]["san"] == "Nf3"


def test_pv_empty_string_returns_empty():
    assert _pv_to_fen_plies(_START, "") == []
    assert _pv_to_fen_plies(_START, None) == []


def test_pv_bad_fen_returns_empty():
    assert _pv_to_fen_plies("this is not a fen", "1. e4") == []


def test_pv_illegal_san_truncates_gracefully():
    # "1. e9" is not a valid square — should return [] rather than crash.
    result = _pv_to_fen_plies(_START, "1. e9")
    assert result == []


# --- build_pgn_viewer payload ------------------------------------------------

def _extract_payload(html: str) -> dict:
    """Pull the JSON payload from the viewer HTML."""
    m = re.search(r'greco-viewer-data">(.*?)</script>', html, re.DOTALL)
    assert m, "viewer payload not found in HTML"
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_viewer_payload_includes_vars_for_blunder(make_move, make_game):
    m = make_move(
        fen_before=_START,
        fen_after=_AFTER_E4,
        classification="blunder",
        best_line_san="1. d4 d5 2. c4",
        refutation_line_san="",
    )
    g = make_game([m])
    data = _extract_payload(build_pgn_viewer(g))
    ply1 = data["plies"][1]
    assert "vars" in ply1
    var = ply1["vars"][0]
    assert var["tp"] == "best"
    assert [p["san"] for p in var["plies"]] == ["d4", "d5", "c4"]
    assert all("fen" in p and "uci" in p for p in var["plies"])


def test_viewer_payload_includes_refutation(make_move, make_game):
    m = make_move(
        fen_before=_START,
        fen_after=_AFTER_E4,
        classification="blunder",
        best_line_san="",
        refutation_line_san="1...e5 2. Nf3",
    )
    g = make_game([m])
    data = _extract_payload(build_pgn_viewer(g))
    ply1 = data["plies"][1]
    assert "vars" in ply1
    var = ply1["vars"][0]
    assert var["tp"] == "ref"
    assert var["plies"][0]["san"] == "e5"


def test_viewer_payload_no_vars_for_good_move(make_move, make_game):
    m = make_move(
        fen_before=_START, fen_after=_AFTER_E4, classification="best",
        best_line_san="", refutation_line_san="",
    )
    g = make_game([m])
    data = _extract_payload(build_pgn_viewer(g))
    ply1 = data["plies"][1]
    assert "vars" not in ply1


def test_viewer_payload_both_best_and_refutation(make_move, make_game):
    m = make_move(
        fen_before=_START,
        fen_after=_AFTER_E4,
        classification="mistake",
        best_line_san="1. d4",
        refutation_line_san="1...e5",
    )
    g = make_game([m])
    data = _extract_payload(build_pgn_viewer(g))
    ply1 = data["plies"][1]
    assert "vars" in ply1
    types = [v["tp"] for v in ply1["vars"]]
    assert "best" in types
    assert "ref" in types
