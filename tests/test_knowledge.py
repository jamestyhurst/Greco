"""Knowledge corpus — FTS5 retrieval and theme extraction.

Theme extraction is pure and always runs. The FTS5 search tests run against the
real (small) corpus DB and skip cleanly if it is absent or empty, so the suite
still passes on a fresh checkout that hasn't built the index yet.
"""
from __future__ import annotations

import pytest

import knowledge


@pytest.fixture(scope="module")
def corpus_conn():
    try:
        knowledge.ensure_index()
    except Exception:
        pytest.skip("knowledge index could not be built")
    if not knowledge.DB_PATH.exists():
        pytest.skip("knowledge corpus DB is not present")
    conn = knowledge._connect()
    if not knowledge._has_rows(conn):
        conn.close()
        pytest.skip("knowledge corpus is empty")
    yield conn
    conn.close()


def test_fts_search_finds_a_common_word(corpus_conn):
    rows = knowledge._search(corpus_conn, ["king"], 5)
    assert len(rows) >= 1          # "king" appears in any chess text
    assert rows[0]["text"].strip()


def test_retrieve_returns_passage_objects(corpus_conn):
    passages = knowledge.retrieve(["endgame", "king_safety"], top_k=4)
    assert isinstance(passages, list)
    for p in passages:
        assert isinstance(p, knowledge.Passage)
        assert p.text.strip()


def test_retrieve_with_no_themes_is_empty():
    assert knowledge.retrieve([]) == []


def test_themes_from_game_only_emits_detected_features(make_move, make_game):
    moves = [
        make_move(is_sacrifice=True),
        make_move(ply=2, double_attack="knight forks queen and rook"),
    ]
    themes = knowledge.themes_from_game(make_game(moves))
    assert "sacrifice" in themes
    assert "fork" in themes
    # A feature the board never showed must NOT be emitted.
    assert "pin" not in themes
