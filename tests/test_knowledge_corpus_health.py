"""Knowledge corpus health checks — the testing protocol for corpus additions.

This file is "the test that automatically runs when a new book is deposited."
It is part of the standard pytest suite, so ship.py's test gate catches any
deposit that leaves the corpus broken before a version bump is allowed.

Structure:
  1. File-system checks (no DB needed) — every manifest slug must have a valid
     text.txt and meta.json on disk before the index is even built.
  2. FTS5 index checks (skips when DB is absent, e.g. fresh checkout) — every
     book must contribute at least one chunk and standard themes must be retrievable.

When to re-run manually: after `python knowledge.py` to rebuild the index,
or via `tools/verify_corpus_addition.py <slug>` for a single-book spot-check.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import knowledge
from knowledge import KNOWLEDGE_DIR, BUCKETS

MANIFEST_PATH = KNOWLEDGE_DIR / "MANIFEST.md"

# ── Manifest slug extraction (pure, no DB) ────────────────────────────────────

def _parse_manifest_slugs() -> list[str]:
    """Return book-directory slugs from the manifest (backtick-quoted column values).

    Excludes PGN-file entries (paths ending in .pgn) which are game files,
    not text directories.
    """
    if not MANIFEST_PATH.exists():
        return []
    raw = re.findall(r"\|\s*`([^`]+)`\s*\|",
                     MANIFEST_PATH.read_text(encoding="utf-8"))
    return [s for s in raw if not s.endswith(".pgn")]

MANIFEST_SLUGS = _parse_manifest_slugs()

def _locate(slug: str, filename: str) -> Path | None:
    for bucket in BUCKETS:
        p = KNOWLEDGE_DIR / bucket / "texts" / slug / filename
        if p.exists():
            return p
    return None


# ── Part 1: file-system health ────────────────────────────────────────────────

class TestCorpusFileSystem:
    """Every manifest slug must have valid text.txt and meta.json on disk."""

    @pytest.mark.parametrize("slug", MANIFEST_SLUGS)
    def test_text_file_exists(self, slug):
        assert _locate(slug, "text.txt") is not None, (
            f"{slug}: text.txt not found under knowledge/*/texts/ — "
            "deposit the file or remove the manifest row"
        )

    @pytest.mark.parametrize("slug", MANIFEST_SLUGS)
    def test_text_file_is_not_a_stub(self, slug):
        path = _locate(slug, "text.txt")
        if path is None:
            pytest.skip(f"{slug}: no text.txt (caught by test_text_file_exists)")
        text = path.read_text(encoding="utf-8").strip()
        assert len(text) >= 500, (
            f"{slug}: text.txt has only {len(text)} chars — "
            "looks like a stub or empty placeholder"
        )

    @pytest.mark.parametrize("slug", MANIFEST_SLUGS)
    def test_meta_json_exists_and_is_valid(self, slug):
        path = _locate(slug, "meta.json")
        assert path is not None, (
            f"{slug}: meta.json not found — run fetch_gutenberg.py or create it manually"
        )
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            pytest.fail(f"{slug}: meta.json parse error: {exc}")
        required = {"title", "author", "year", "bucket", "pd_basis"}
        missing = required - meta.keys()
        assert not missing, f"{slug}: meta.json missing required fields: {missing}"

    @pytest.mark.parametrize("slug", MANIFEST_SLUGS)
    def test_meta_json_year_is_pre_1931(self, slug):
        """Public-domain boundary: only works first published 1930 or earlier."""
        path = _locate(slug, "meta.json")
        if path is None:
            pytest.skip("no meta.json")
        meta = json.loads(path.read_text(encoding="utf-8"))
        # Greco seed content is CC0 and exempt from the PD year rule.
        if slug.startswith("greco-seed"):
            return
        year = meta.get("year")
        assert year is not None, f"{slug}: meta.json has no 'year' field"
        assert int(year) <= 1930, (
            f"{slug}: year {year} is after 1930 — "
            "this work may not be in the public domain; remove it from the corpus"
        )


# ── Part 2: FTS5 index health (skips when DB absent) ─────────────────────────

@pytest.fixture(scope="module")
def corpus_db():
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


def test_corpus_has_minimum_chunk_count(corpus_db):
    """The index must have at least 100 chunks — catches a silent build failure."""
    n = corpus_db.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"]
    assert n >= 100, (
        f"Only {n} chunks in the FTS5 index — "
        "rebuild with `python knowledge.py` and check that text files are non-empty"
    )


# Only test non-seed slugs (seeds are tiny and may legitimately have few chunks).
_REAL_SLUGS = [s for s in MANIFEST_SLUGS if not s.startswith("greco-seed")]

@pytest.mark.parametrize("slug", _REAL_SLUGS)
def test_each_book_contributes_at_least_one_chunk(corpus_db, slug):
    """Every deposited book must appear in the FTS5 index after a rebuild."""
    n = corpus_db.execute(
        "SELECT COUNT(*) AS c FROM chunks WHERE book_id = ?", (slug,)
    ).fetchone()["c"]
    assert n >= 1, (
        f"{slug}: 0 chunks in the FTS5 index. "
        "Run `python knowledge.py` to rebuild; if the count stays 0 the text may be "
        "notation-only or below the minimum prose density threshold."
    )


@pytest.mark.parametrize("theme,phrases", [
    ("endgame",     ["endgame", "king"]),
    ("sacrifice",   ["sacrifice"]),
    ("opening",     ["opening"]),
    ("development", ["develop"]),
])
def test_theme_retrieval_finds_passages(corpus_db, theme, phrases):
    """Standard game themes must surface passages — catches a dead corpus."""
    rows = knowledge._search(corpus_db, phrases, 5)
    assert len(rows) >= 1, (
        f"Theme '{theme}' (phrases: {phrases}) returned 0 results. "
        "The corpus may be empty or the FTS5 index needs rebuilding."
    )
    # Each result must have real text content.
    assert rows[0]["text"].strip(), "First result has empty text"
