"""Tests for essay_mode.py — pure, engine-free, no API key required.

These tests cover the prompt-construction helpers, the HTML renderer, and the
knowledge-retrieval glue. They do NOT call the Anthropic API or Stockfish — those
are integration tests that run only on a machine with valid credentials.
"""
from __future__ import annotations

import essay_mode as E
from knowledge import Passage


# --------------------------------------------------------------------------- #
# Helpers for making fake Passage objects
# --------------------------------------------------------------------------- #
def _passage(author, title, year, text):
    p = Passage(
        text=text,
        title=title,
        author=author,
        year=year,
        bucket="book",
        book_id="test",
        chunk_index=0,
    )
    return p


# --------------------------------------------------------------------------- #
# _derive_title
# --------------------------------------------------------------------------- #
def test_derive_title_short_question():
    assert E._derive_title("What is prophylaxis?") == "What is prophylaxis"


def test_derive_title_long_question():
    q = "Does the Scandinavian Defense naturally lean toward queenside castling in most variations?"
    result = E._derive_title(q)
    assert len(result) <= 60
    assert result.endswith("…")


def test_derive_title_strips_trailing_punctuation():
    assert E._derive_title("Why are bishops strong in open positions.") == "Why are bishops strong in open positions"


# --------------------------------------------------------------------------- #
# _extract_sources
# --------------------------------------------------------------------------- #
def test_extract_sources_deduplicates():
    passages = [
        _passage("Capablanca", "Chess Fundamentals", 1921, "text"),
        _passage("Capablanca", "Chess Fundamentals", 1921, "other text"),
        _passage("Nimzowitsch", "My System", 1925, "text"),
    ]
    sources = E._extract_sources(passages)
    assert len(sources) == 2
    assert any("Capablanca" in s for s in sources)
    assert any("Nimzowitsch" in s for s in sources)


def test_extract_sources_empty():
    assert E._extract_sources([]) == []


def test_extract_sources_missing_author_skipped():
    passages = [_passage("", "Unknown Book", 1900, "text")]
    assert E._extract_sources(passages) == []


def test_extract_sources_includes_year():
    passages = [_passage("Capablanca", "Chess Fundamentals", 1921, "text")]
    sources = E._extract_sources(passages)
    assert "1921" in sources[0]


# --------------------------------------------------------------------------- #
# _build_corpus_block
# --------------------------------------------------------------------------- #
def test_build_corpus_block_empty():
    block = E._build_corpus_block([])
    assert "<corpus>" in block
    assert "No relevant passages" in block


def test_build_corpus_block_with_passages():
    passages = [
        _passage("Capablanca", "Chess Fundamentals", 1921, "The rook belongs on open files."),
    ]
    block = E._build_corpus_block(passages)
    assert "Capablanca" in block
    assert "Chess Fundamentals" in block
    assert "1921" in block
    assert "The rook belongs on open files." in block
    assert block.startswith("<corpus>")
    assert block.endswith("</corpus>")


# --------------------------------------------------------------------------- #
# _build_essay_prompt
# --------------------------------------------------------------------------- #
def test_build_essay_prompt_contains_question():
    prompt = E._build_essay_prompt(
        question="Why is the rook on an open file good?",
        corpus_block="<corpus>(no passages)</corpus>",
        coverage="none",
        pgn_text=None,
        audience_level="club",
        note="",
    )
    assert "Why is the rook on an open file good?" in prompt


def test_build_essay_prompt_includes_pgn_when_given():
    prompt = E._build_essay_prompt(
        question="Test?",
        corpus_block="<corpus></corpus>",
        coverage="full",
        pgn_text="1. e4 e5",
        audience_level="club",
        note="",
    )
    assert "1. e4 e5" in prompt
    assert "Illustrative game" in prompt


def test_build_essay_prompt_no_pgn_section_when_absent():
    prompt = E._build_essay_prompt(
        question="Test?",
        corpus_block="<corpus></corpus>",
        coverage="full",
        pgn_text=None,
        audience_level="club",
        note="",
    )
    assert "Illustrative game" not in prompt


def test_build_essay_prompt_truncates_long_pgn():
    long_pgn = "1. e4 e5 " * 500  # ~4500 chars
    prompt = E._build_essay_prompt(
        question="Test?",
        corpus_block="<corpus></corpus>",
        coverage="full",
        pgn_text=long_pgn,
        audience_level="club",
        note="",
    )
    # The PGN should be truncated to 3000 chars in the prompt
    assert len(prompt) < 4000 + 500  # well under the untruncated size


# --------------------------------------------------------------------------- #
# essay_to_html
# --------------------------------------------------------------------------- #
def test_essay_to_html_produces_html():
    result = {
        "markdown": "# Test Essay\n\nThis is a test.",
        "title": "Test Essay",
        "corpus_coverage": "full",
        "sources": [],
    }
    html = E.essay_to_html(result)
    assert "<!DOCTYPE html>" in html
    assert "Test Essay" in html
    assert "<body>" in html


def test_essay_to_html_shows_coverage_note_for_none():
    result = {
        "markdown": "# Q\n\nAnswer.",
        "title": "Q",
        "corpus_coverage": "none",
        "sources": [],
    }
    html = E.essay_to_html(result)
    assert "coverage-note" in html
    assert "limited coverage" in html


def test_essay_to_html_no_coverage_note_for_full():
    result = {
        "markdown": "# Q\n\nAnswer.",
        "title": "Q",
        "corpus_coverage": "full",
        "sources": [],
    }
    html = E.essay_to_html(result)
    # The CSS class definition is always present; the <p> element should not be.
    assert '<p class="coverage-note">' not in html


def test_essay_to_html_uses_title():
    result = {
        "markdown": "# My Essay\n\nText.",
        "title": "My Custom Title",
        "corpus_coverage": "full",
        "sources": [],
    }
    html = E.essay_to_html(result)
    assert "My Custom Title" in html


# --------------------------------------------------------------------------- #
# ESSAY_SYSTEM_PROMPT
# --------------------------------------------------------------------------- #
def test_essay_system_prompt_exists_and_has_key_rules():
    prompt = E.ESSAY_SYSTEM_PROMPT
    assert "corpus first" in prompt.lower()
    assert "hallucinated" in prompt.lower() or "invented" in prompt.lower()
    assert "key takeaway" in prompt.lower()


# --------------------------------------------------------------------------- #
# knowledge.retrieve_for_question integration (corpus may be empty in CI)
# --------------------------------------------------------------------------- #
def test_retrieve_for_question_returns_list():
    import knowledge
    result = knowledge.retrieve_for_question("What is an outpost?", top_k=3)
    assert isinstance(result, list)
    # Each item should be a Passage-like object
    for p in result:
        assert hasattr(p, "text")
        assert hasattr(p, "author")
