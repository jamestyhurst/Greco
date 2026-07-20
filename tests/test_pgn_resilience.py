"""Mud-proof ingestion tests — pure, no engine, no network.

Regression suite for the 2026-07-19 resilience work. Every case here started
life as a failing row in the empirical characterization matrix
(Developer Tools (Greco)\\pgn-resilience\\): encoding crashes, silent
truncation on bad movetext, and silent header ("frontmatter") data loss —
the failure that produced the real-world "_ vs. _" report.
"""
import pytest

from analyzer import parse_pgn_game
from importers import load_from_file, sanitize_pgn
from outputs import time_control_category

HDR = (
    '[Event "Test"]\n[Site "Home"]\n[Date "2026.06.18"]\n[Round "1"]\n'
    '[White "Rafay"]\n[Black "James"]\n[Result "1-0"]\n\n'
)
MOVES = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 1-0\n"


# --- encoding ladder (load_from_file) ---------------------------------------

def _roundtrip(tmp_path, raw: bytes) -> str:
    p = tmp_path / "g.pgn"
    p.write_bytes(raw)
    text, _ = load_from_file(p)
    return text

def test_loads_utf16_notepad_unicode(tmp_path):
    assert "Rafay" in _roundtrip(tmp_path, (HDR + MOVES).encode("utf-16"))

def test_loads_cp1252_accented_name(tmp_path):
    text = _roundtrip(tmp_path, (HDR.replace("Rafay", "René") + MOVES).encode("cp1252"))
    assert "René" in text

def test_loads_utf8_bom(tmp_path):
    text = _roundtrip(tmp_path, ("﻿" + HDR + MOVES).encode("utf-8"))
    assert not text.startswith("﻿")


# --- sanitize_pgn: frontmatter repair + word-processor grit ------------------

def test_repairs_tag_missing_space():
    assert '[White "Rafay"]' in sanitize_pgn('[White"Rafay"]\n\n1. e4 e5 *\n')

def test_repairs_unquoted_and_unclosed_tags():
    out = sanitize_pgn('[White Rafay]\n[Black "James]\n\n1. e4 e5 *\n')
    assert '[White "Rafay"]' in out and '[Black "James"]' in out

def test_repairs_indented_tags():
    # Indented tags previously made the WHOLE game invisible: 0 moves, 0 errors.
    out = sanitize_pgn('   [White "Rafay"]\n\t[Black "James"]\n\n' + MOVES)
    game = parse_pgn_game(out)
    assert game.headers["White"] == "Rafay"
    assert len(list(game.mainline_moves())) == 10

def test_fixes_endash_castling_and_curly_quotes():
    dirty = HDR.replace('"James"', "“James”") + MOVES.replace("O-O", "O–O")
    game = parse_pgn_game(dirty)
    assert game.headers["Black"] == "James"
    assert len(list(game.mainline_moves())) == 10

def test_sanitize_is_idempotent_on_clean_pgn():
    clean = HDR + MOVES
    assert sanitize_pgn(clean) == clean


# --- parse_pgn_game: no more silent fragments --------------------------------

def test_clean_game_parses():
    assert len(list(parse_pgn_game(HDR + MOVES).mainline_moves())) == 10

def test_illegal_move_raises_instead_of_truncating():
    bad = HDR + "1. e4 e5 2. Nf3 Nf3 3. Bb5 a6 1-0\n"
    with pytest.raises(ValueError, match="not a legal move"):
        parse_pgn_game(bad)

def test_ambiguous_move_names_the_candidates():
    # Knights on b1 and e2 can both reach c3 — the scoresheet classic.
    bad = HDR + "1. e4 e5 2. Ne2 Nf6 3. Nc3 d5 1-0\n"
    with pytest.raises(ValueError, match="Nbc3, Nec3"):
        parse_pgn_game(bad)

def test_variant_game_refused():
    with pytest.raises(ValueError, match="Chess960"):
        parse_pgn_game(HDR.replace("[Result", '[Variant "Chess960"]\n[Result') + MOVES)

def test_lichess_from_position_allowed():
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    pgn = (f'[Variant "From Position"]\n[SetUp "1"]\n[FEN "{fen}"]\n\n'
           f"3. Bb5 a6 4. Ba4 Nf6 *\n")
    assert len(list(parse_pgn_game(pgn).mainline_moves())) == 4


# --- result reconciliation: the board outranks the tag ------------------------

def test_mate_on_board_corrects_wrong_result_tag():
    pgn = '[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n1. f3 e5 2. g4 Qh4# 1-0\n'
    assert parse_pgn_game(pgn).headers["Result"] == "0-1"

def test_mate_on_board_fills_in_unknown_result():
    pgn = '[White "A"]\n[Black "B"]\n[Result "*"]\n\n1. f3 e5 2. g4 Qh4# *\n'
    assert parse_pgn_game(pgn).headers["Result"] == "0-1"

def test_non_mate_result_tag_left_alone():
    # No mate on the board → a resignation is unknowable; trust the tag.
    assert parse_pgn_game(HDR + MOVES).headers["Result"] == "1-0"


# --- TimeControl: correspondence vs FIDE classical ----------------------------

def test_correspondence_is_daily():
    assert time_control_category("1/86400") == "Daily"

def test_fide_moves_per_session_is_classical_not_daily():
    assert time_control_category("40/7200:3600") == "Classical"
