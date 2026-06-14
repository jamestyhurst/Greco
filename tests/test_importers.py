"""Importer tests — pure, no network.

Covers filename name recovery (feature 5) and the chess.com mis-route fix (#33:
a pasted PGN whose [Site] mentions chess.com must load as raw PGN, not raise).
"""
from pathlib import Path

import pytest

from importers import load_pgn, parse_players_from_filename


def test_parse_vs_patterns():
    assert parse_players_from_filename(Path("Magnus vs Hikaru.pgn")) == ("Magnus", "Hikaru")
    assert parse_players_from_filename(Path("A_vs_B.pgn")) == ("A", "B")
    assert parse_players_from_filename(Path("A_vs_B, Blitz, 2024.pgn")) == ("A", "B")


def test_parse_requires_vs_not_bare_hyphen():
    # A bare " - " is deliberately not a separator (avoids false names from
    # ordinary filenames like "My Game - Draft Copy.pgn").
    assert parse_players_from_filename(Path("A - B.pgn")) == (None, None)
    assert parse_players_from_filename(Path("My Game - Draft Copy.pgn")) == (None, None)


def test_parse_handles_none():
    assert parse_players_from_filename(None) == (None, None)
    assert parse_players_from_filename(
        Path("2026-05-19 JamesTortoise vs NinaTitova (Rapid, 1-0).pgn")
    ) == ("JamesTortoise", "NinaTitova")
    assert parse_players_from_filename(
        Path("redwood1978_vs_JamesTortoise_2025.10.05.pgn")
    ) == ("redwood1978", "JamesTortoise")


def test_parse_no_confident_match():
    assert parse_players_from_filename(Path("randomgame.pgn")) == (None, None)
    assert parse_players_from_filename(Path("12345.pgn")) == (None, None)


def test_pasted_pgn_mentioning_chesscom_loads_as_raw():
    pgn = (
        '[Event "Live Chess"]\n'
        '[Site "https://www.chess.com/game/live/123"]\n\n'
        "1. e4 e5 2. Nf3 Nc6 *"
    )
    text, src = load_pgn(pgn)
    assert "inline PGN" in src and "Nf3" in text


def test_bare_chesscom_url_still_not_implemented():
    with pytest.raises(NotImplementedError):
        load_pgn("https://www.chess.com/game/live/123")
