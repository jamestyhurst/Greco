"""Narrator helper tests — _piece_placement, _format_eval edge cases,
and _move_to_dict flag serialisation.

No API calls, no Stockfish. Complements test_narrator.py with edge cases
that were not covered there (lines 29-37, 349, 377-433 of narrator.py).
"""
from __future__ import annotations

from narrator import _format_eval, _move_to_dict, _piece_placement


# --- _piece_placement -------------------------------------------------------

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def test_piece_placement_starting_position():
    result = _piece_placement(STARTING_FEN)
    assert "White" in result and "Black" in result
    assert "K:" in result
    assert "Q:" in result
    assert "P:" in result


def test_piece_placement_correct_square_after_e4():
    result = _piece_placement(AFTER_E4_FEN)
    assert "e4" in result


def test_piece_placement_bad_fen_returns_empty():
    assert _piece_placement("not_a_fen") == ""


def test_piece_placement_pipe_separator():
    result = _piece_placement(STARTING_FEN)
    assert "|" in result  # White ... | Black ...


# --- _format_eval edge case: mate=0 means already checkmated ----------------

def test_format_eval_mate_zero():
    assert _format_eval(None, 0) == "checkmate"


# --- _move_to_dict flag serialisation ---------------------------------------

def test_move_to_dict_no_flags_by_default(make_move):
    d = _move_to_dict(make_move(), tier=1)
    assert "flags" not in d


def test_move_to_dict_check_flag(make_move):
    d = _move_to_dict(make_move(is_check=True), tier=1)
    assert "check" in d["flags"]


def test_move_to_dict_capture_and_captured_piece(make_move):
    d = _move_to_dict(make_move(is_capture=True, captured_piece="knight"), tier=1)
    assert "capture" in d["flags"]
    assert d["captured"] == "knight"


def test_move_to_dict_castle_flag(make_move):
    d = _move_to_dict(make_move(is_castle=True), tier=1)
    assert "castle" in d["flags"]


def test_move_to_dict_brilliant_and_sacrifice_flags(make_move):
    d = _move_to_dict(make_move(is_brilliant=True, is_sacrifice=True), tier=1)
    assert "brilliant" in d["flags"]
    assert "sound-sacrifice" in d["flags"]


def test_move_to_dict_unsound_sacrifice_flag(make_move):
    d = _move_to_dict(make_move(is_unsound_sacrifice=True), tier=1)
    assert "unsound-sacrifice" in d["flags"]


def test_move_to_dict_forced_and_only_good(make_move):
    d = _move_to_dict(make_move(is_forced=True, is_only_good_move=True), tier=1)
    assert "forced" in d["flags"]
    assert "only-good-move" in d["flags"]


def test_move_to_dict_still_winning_flag(make_move):
    d = _move_to_dict(make_move(still_winning=True), tier=1)
    assert "still-decisively-winning" in d["flags"]
