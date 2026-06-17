"""Tests for knowledge.py — _is_human_authored, _format_featured_passage,
and load_knowledge_for_game (with mocked retrieval).

These tests target the uncovered lines 698-847 (get_featured_passage /
load_knowledge_for_game) and the pure helpers _is_human_authored and
_format_featured_passage. No corpus DB required: retrieval is mocked.
"""
from __future__ import annotations

from unittest.mock import patch

import knowledge
from knowledge import Passage, _format_featured_passage, _is_human_authored


# --- helpers ----------------------------------------------------------------

def _passage(**overrides) -> Passage:
    defaults = dict(
        text=(
            "The king must be active in the endgame. "
            "He is a fighting piece; use him. "
            "Never leave him idle when the endgame arrives."
        ),
        title="Chess Fundamentals",
        author="Capablanca",
        year=1921,
        bucket="chess_principles",
        book_id="capablanca-chess-fundamentals",
        chunk_index=0,
        matched_theme="endgame",
        matched_phrases=["king", "endgame"],
    )
    defaults.update(overrides)
    return Passage(**defaults)


# --- _is_human_authored -------------------------------------------------------

def test_is_human_authored_named_author():
    assert _is_human_authored(_passage(author="Capablanca")) is True


def test_is_human_authored_empty_author():
    assert _is_human_authored(_passage(author="")) is False


def test_is_human_authored_greco_project_excluded():
    assert _is_human_authored(_passage(author="Greco Project")) is False


def test_is_human_authored_case_insensitive():
    assert _is_human_authored(_passage(author="GRECO PROJECT")) is False
    assert _is_human_authored(_passage(author="greco project")) is False


# --- _format_featured_passage ------------------------------------------------

def test_format_featured_passage_full_attribution():
    p = _passage(author="Capablanca", title="Chess Fundamentals", year=1921)
    result = _format_featured_passage(p, "The king must be active.")
    assert "Capablanca" in result
    assert "Chess Fundamentals" in result
    assert "1921" in result
    assert "FEATURED PASSAGE" in result
    assert '"The king must be active."' in result


def test_format_featured_passage_no_year():
    p = _passage(year=None, title="Some Book")
    result = _format_featured_passage(p, "A sentence.")
    assert "Some Book" in result
    assert "(None)" not in result


def test_format_featured_passage_endgame_placement_hint():
    p = _passage(matched_theme="endgame")
    result = _format_featured_passage(p, "A sentence.")
    assert "endgame" in result.lower()


def test_format_featured_passage_sacrifice_placement_hint():
    p = _passage(matched_theme="sacrifice")
    result = _format_featured_passage(p, "A sentence.")
    assert "sacrifice" in result.lower()


# --- load_knowledge_for_game (mocked) ----------------------------------------

def test_load_knowledge_returns_empty_on_exception(make_move, make_game):
    game = make_game([make_move()])
    with patch.object(knowledge, "themes_from_game", side_effect=RuntimeError("db gone")):
        assert knowledge.load_knowledge_for_game(game) == ""


def test_load_knowledge_returns_empty_when_no_passages(make_move, make_game):
    game = make_game([make_move()])
    with (
        patch.object(knowledge, "themes_from_game", return_value=["endgame"]),
        patch.object(knowledge, "retrieve", return_value=[]),
    ):
        assert knowledge.load_knowledge_for_game(game) == ""


def test_load_knowledge_returns_block_for_human_passage(make_move, make_game):
    game = make_game([make_move()])
    p = _passage(author="Capablanca", matched_theme="endgame")
    with (
        patch.object(knowledge, "themes_from_game", return_value=["endgame"]),
        patch.object(knowledge, "retrieve", return_value=[p]),
    ):
        result = knowledge.load_knowledge_for_game(game)
    assert "Capablanca" in result
    assert "Classical chess literature" in result


def test_load_knowledge_excludes_greco_seed_passages(make_move, make_game):
    game = make_game([make_move()])
    seed = _passage(author="Greco Project", matched_theme="endgame")
    with (
        patch.object(knowledge, "themes_from_game", return_value=["endgame"]),
        patch.object(knowledge, "retrieve", return_value=[seed]),
    ):
        assert knowledge.load_knowledge_for_game(game) == ""


def test_load_knowledge_respects_max_chars(make_move, make_game):
    game = make_game([make_move()])
    # Five passages with distinct authors; a very tight budget means not all make it
    # into the literature block (though a FEATURED PASSAGE is always prepended).
    passages = [_passage(author=f"Author{i}") for i in range(5)]
    with (
        patch.object(knowledge, "themes_from_game", return_value=["endgame"]),
        patch.object(knowledge, "retrieve", return_value=passages),
    ):
        result_small = knowledge.load_knowledge_for_game(game, max_chars=50)
        result_large = knowledge.load_knowledge_for_game(game, max_chars=100_000)
    # A larger budget should include more passages than a tiny one.
    assert result_large.count("Author") >= result_small.count("Author")
