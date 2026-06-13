"""
Greco's knowledge corpus — a retrieval layer over public-domain chess books.

WHAT THIS IS
    A searchable library of openly-licensed chess texts (Capablanca, Lasker, …)
    that the narrator can draw on — and quote verbatim — when a game exhibits a
    theme the classical literature speaks to (an isolated pawn, a rook endgame,
    a sacrifice). The books are NOT used to train anything; they are looked up at
    runtime and the *actual passage* is handed to Claude as source material.

WHY RETRIEVAL, NOT TRAINING (the concept worth learning here)
    This is "RAG" — Retrieval-Augmented Generation. A language model paraphrases
    and approximates; asking it to reproduce a book word-for-word is a failure
    mode, not a feature. So instead of hoping the model "knows" Capablanca, we
    store the real text on disk, search it for the relevant passage, and give the
    model that exact text to weave in. The quote is correct because it was
    retrieved, not generated. This mirrors Greco's core rule — *data-back, never
    prompt-stuff*: python-chess supplies geometry, Stockfish supplies evaluation,
    and now this corpus supplies the verbatim words of the masters. The model
    only ever narrates from supplied facts.

HOW IT FITS THE PIPELINE
    analyzer.py detects ground-truth themes per move (forks, sacrifices, doubled
    pawns, the endgame phase, …). Before narration, `load_knowledge_for_game()`
    turns those themes — plus the identified opening — into search queries, pulls
    the best-matching passages, and returns a block the narrator injects into the
    user message. One lookup per game (cheap), not one per move.

FOLDER LAYOUT (see knowledge/README.md for the deposit protocol)
    knowledge/
      opening_theory/texts/<book>/{text.txt, meta.json}   # opening-specific works
      opening_theory/games/*.pgn                           # annotated master PGN
      chess_principles/texts/<book>/{text.txt, meta.json}  # strategy / endgame works
      MANIFEST.md                                          # the legal registry
      knowledge.db                                         # generated FTS index (gitignored)

LEGAL BOUNDARY
    Only works first published in 1930 or earlier (US 95-year rule, as of 2026).
    English originals are safe for verbatim quoting; a modern translation of a
    public-domain foreign work carries its own copyright. The MANIFEST records
    the basis for every text. This module does not enforce the rule — acquisition
    does — but it surfaces author/title/year so attribution is always possible.

The whole module is fail-safe: if the corpus is empty or anything goes wrong,
every public function degrades to "no passages" and Greco narrates exactly as it
did before the corpus existed.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
DB_PATH = KNOWLEDGE_DIR / "knowledge.db"
BUCKETS = ("opening_theory", "chess_principles")

# Chunking: passages of roughly this many words, so a retrieved excerpt is big
# enough to carry a real idea but small enough to quote. A little overlap keeps a
# thought from being sliced in half at a boundary.
TARGET_WORDS = 380
OVERLAP_WORDS = 60
_MIN_TEXT_CHARS = 200  # ignore stub/placeholder text files


# --------------------------------------------------------------------------- #
# Theme vocabulary: a canonical theme (emitted only when the analyzer actually
# detected it) maps to the search phrases that find it in the literature.
# Multi-word entries are matched as phrases. Stemming (see the FTS tokenizer)
# means "sacrifice" already matches "sacrificed"/"sacrifices", so we stay terse.
# --------------------------------------------------------------------------- #
THEME_QUERIES: Dict[str, List[str]] = {
    "sacrifice": ["sacrifice", "combination", "give up material"],
    "fork": ["fork", "double attack", "knight fork"],
    "pin": ["pin", "skewer", "pinned"],
    "endgame": ["endgame", "ending", "king and pawn", "rook ending"],
    "doubled_pawns": ["doubled pawns", "pawn structure", "weak pawn"],
    "open_file": ["open file", "seventh rank", "rook on the"],
    "king_safety": ["king safety", "castle", "attack on the king"],
    "development": ["development", "develop", "mobilize the pieces"],
    "center": ["centre", "center", "central pawns"],
    # In the vocabulary for future detectors, even though nothing emits them yet
    # (kept here so adding a detector is a one-line change, not a redesign):
    "passed_pawn": ["passed pawn", "passed pawns"],
    "isolated_pawn": ["isolated pawn", "isolated queen's pawn"],
    "bishop_pair": ["two bishops", "bishop pair"],
}


@dataclass
class Passage:
    """One retrieved excerpt, with everything needed to attribute it."""
    text: str
    title: str
    author: str
    year: Optional[int]
    bucket: str
    book_id: str
    chunk_index: int

    def attribution(self) -> str:
        bits = [b for b in (self.author, self.title) if b]
        head = " — ".join(bits) if bits else (self.book_id or "unknown source")
        if self.year:
            head += f" ({self.year})"
        return head


# --------------------------------------------------------------------------- #
# Reading the corpus off disk
# --------------------------------------------------------------------------- #
def _iter_book_dirs():
    """Yield (bucket, book_dir Path) for every book folder holding a text.txt."""
    if not KNOWLEDGE_DIR.is_dir():
        return
    for bucket in BUCKETS:
        texts_root = KNOWLEDGE_DIR / bucket / "texts"
        if not texts_root.is_dir():
            continue
        for book_dir in sorted(texts_root.iterdir()):
            if not book_dir.is_dir() or book_dir.name.startswith((".", "_")):
                continue
            if (book_dir / "text.txt").is_file():
                yield bucket, book_dir


def _read_meta(book_dir: Path, bucket: str) -> Dict[str, object]:
    """Per-book metadata from meta.json, with sensible fallbacks."""
    meta: Dict[str, object] = {}
    mpath = book_dir / "meta.json"
    if mpath.is_file():
        try:
            meta = json.loads(mpath.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    title = str(meta.get("title") or book_dir.name.replace("-", " ").title())
    author = str(meta.get("author") or "")
    year_raw = meta.get("year")
    try:
        year = int(year_raw) if year_raw is not None else None
    except (ValueError, TypeError):
        year = None
    return {
        "book_id": book_dir.name,
        "title": title,
        "author": author,
        "year": year,
        "bucket": bucket,
    }


def chunk_text(text: str, target_words: int = TARGET_WORDS,
               overlap_words: int = OVERLAP_WORDS) -> List[str]:
    """
    Split a book into passage-sized chunks on paragraph boundaries, never cutting
    mid-paragraph. When a chunk is closed, the last paragraph is carried into the
    next chunk as overlap so an idea that straddles the boundary is still findable
    in one piece.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    current: List[str] = []
    words = 0
    for para in paragraphs:
        pw = len(para.split())
        if words + pw > target_words and current:
            chunks.append("\n\n".join(current))
            # Carry the tail paragraph forward as overlap, if it's small enough.
            tail = current[-1]
            if len(tail.split()) <= overlap_words:
                current = [tail]
                words = len(tail.split())
            else:
                current = []
                words = 0
        current.append(para)
        words += pw
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _corpus_fingerprint() -> str:
    """A string that changes whenever any text.txt is added, edited, or removed —
    used to decide when the index must be rebuilt."""
    parts: List[str] = []
    for bucket, book_dir in _iter_book_dirs():
        tpath = book_dir / "text.txt"
        try:
            st = tpath.stat()
            parts.append(f"{bucket}/{book_dir.name}:{st.st_size}:{int(st.st_mtime)}")
        except OSError:
            continue
    return "|".join(sorted(parts))


# --------------------------------------------------------------------------- #
# Index build (SQLite FTS5 when available; a LIKE-based table as a fallback)
# --------------------------------------------------------------------------- #
def _fts5_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_index() -> int:
    """(Re)build the search index from the text files on disk. Returns the number
    of chunks indexed. Safe to call repeatedly."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except OSError:
            pass

    conn = _connect()
    try:
        use_fts = _fts5_available(conn)
        if use_fts:
            # Only `text` is searched; the rest is stored metadata (UNINDEXED).
            # `porter` stemming + `unicode61` folding give robust keyword matching.
            conn.execute(
                "CREATE VIRTUAL TABLE chunks USING fts5("
                "  text, book_id UNINDEXED, title UNINDEXED, author UNINDEXED,"
                "  year UNINDEXED, bucket UNINDEXED, chunk_index UNINDEXED,"
                "  tokenize='porter unicode61')"
            )
        else:
            conn.execute(
                "CREATE TABLE chunks ("
                "  text TEXT, book_id TEXT, title TEXT, author TEXT,"
                "  year INTEGER, bucket TEXT, chunk_index INTEGER)"
            )
        conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")

        total = 0
        for bucket, book_dir in _iter_book_dirs():
            try:
                raw = (book_dir / "text.txt").read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                continue
            if len(raw) < _MIN_TEXT_CHARS:
                continue  # stub / placeholder
            meta = _read_meta(book_dir, bucket)
            for idx, chunk in enumerate(chunk_text(raw)):
                conn.execute(
                    "INSERT INTO chunks (text, book_id, title, author, year, bucket, chunk_index)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (chunk, meta["book_id"], meta["title"], meta["author"],
                     meta["year"], meta["bucket"], idx),
                )
                total += 1

        conn.execute(
            "INSERT INTO _meta (key, value) VALUES ('fingerprint', ?)",
            (_corpus_fingerprint(),),
        )
        conn.execute(
            "INSERT INTO _meta (key, value) VALUES ('engine', ?)",
            ("fts5" if use_fts else "like",),
        )
        conn.commit()
        return total
    finally:
        conn.close()


def ensure_index(force: bool = False) -> None:
    """Build the index if it is missing or stale (the corpus changed on disk)."""
    if not KNOWLEDGE_DIR.is_dir():
        return
    if force or not DB_PATH.exists():
        build_index()
        return
    try:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT value FROM _meta WHERE key='fingerprint'"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        build_index()
        return
    if row is None or row["value"] != _corpus_fingerprint():
        build_index()


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
_WORD_RE = re.compile(r"[A-Za-z]+")


def _safe_fts_query(phrases: Sequence[str]) -> str:
    """Turn desired phrases/words into a safe FTS5 MATCH expression: each phrase
    is stripped to letters, multi-word phrases are double-quoted, and the lot is
    OR-ed together. Returns '' if nothing usable remains."""
    parts: List[str] = []
    for phrase in phrases:
        words = _WORD_RE.findall(phrase.lower())
        if not words:
            continue
        if len(words) == 1:
            parts.append(words[0])
        else:
            parts.append('"' + " ".join(words) + '"')
    # De-dupe while preserving order.
    seen = set()
    uniq = [p for p in parts if not (p in seen or seen.add(p))]
    return " OR ".join(uniq)


def _engine_kind(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute("SELECT value FROM _meta WHERE key='engine'").fetchone()
        return row["value"] if row else "fts5"
    except sqlite3.DatabaseError:
        return "fts5"


def _search(conn: sqlite3.Connection, phrases: Sequence[str], limit: int) -> List[sqlite3.Row]:
    """Return up to `limit` best-matching chunk rows for the given phrases."""
    if _engine_kind(conn) == "fts5":
        match = _safe_fts_query(phrases)
        if not match:
            return []
        try:
            return list(conn.execute(
                "SELECT text, book_id, title, author, year, bucket, chunk_index, "
                "bm25(chunks) AS rank FROM chunks WHERE chunks MATCH ? "
                "ORDER BY rank LIMIT ?",
                (match, limit),
            ))
        except sqlite3.OperationalError:
            return []
    # LIKE fallback: score by how many distinct query words appear in the chunk.
    words = []
    for phrase in phrases:
        words.extend(_WORD_RE.findall(phrase.lower()))
    words = list(dict.fromkeys(words))
    if not words:
        return []
    score = " + ".join(["(CASE WHEN lower(text) LIKE ? THEN 1 ELSE 0 END)"] * len(words))
    params = [f"%{w}%" for w in words]
    sql = (
        f"SELECT text, book_id, title, author, year, bucket, chunk_index, "
        f"({score}) AS hits FROM chunks WHERE hits > 0 ORDER BY hits DESC LIMIT ?"
    )
    try:
        return list(conn.execute(sql, params + [limit]))
    except sqlite3.OperationalError:
        return []


def _row_to_passage(row: sqlite3.Row) -> Passage:
    return Passage(
        text=row["text"],
        title=row["title"] or "",
        author=row["author"] or "",
        year=row["year"],
        bucket=row["bucket"] or "",
        book_id=row["book_id"] or "",
        chunk_index=row["chunk_index"] if row["chunk_index"] is not None else 0,
    )


def _has_rows(conn: sqlite3.Connection) -> bool:
    try:
        return conn.execute("SELECT 1 FROM chunks LIMIT 1").fetchone() is not None
    except sqlite3.DatabaseError:
        return False


def retrieve(themes: Sequence[str], opening_name: Optional[str] = None,
             top_k: int = 4, per_query: int = 2) -> List[Passage]:
    """
    Retrieve up to `top_k` passages relevant to a game. The opening name (if any)
    is queried first, then each theme in priority order. A first pass takes the
    single best passage per query for balanced coverage; a second pass fills any
    remaining slots. Passages are de-duplicated across queries.

    Returns [] on any problem or empty corpus — callers need no error handling.
    """
    try:
        ensure_index()
    except Exception:
        return []
    if not DB_PATH.exists():
        return []

    queries: List[List[str]] = []
    if opening_name:
        # Query the full name and its component words (drops commas/accents safely).
        queries.append([opening_name] + _WORD_RE.findall(opening_name))
    for theme in themes:
        phrases = THEME_QUERIES.get(theme)
        if phrases:
            queries.append(phrases)
    if not queries:
        return []

    results: List[Passage] = []
    seen = set()
    try:
        conn = _connect()
    except sqlite3.DatabaseError:
        return []
    try:
        if not _has_rows(conn):
            return []
        # Pass 1: one passage per query, in priority order.
        for phrases in queries:
            if len(results) >= top_k:
                break
            for row in _search(conn, phrases, per_query):
                key = (row["book_id"], row["chunk_index"])
                if key in seen:
                    continue
                seen.add(key)
                results.append(_row_to_passage(row))
                break
        # Pass 2: fill remaining slots, allowing more from each query.
        if len(results) < top_k:
            for phrases in queries:
                if len(results) >= top_k:
                    break
                for row in _search(conn, phrases, per_query + 3):
                    key = (row["book_id"], row["chunk_index"])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(_row_to_passage(row))
                    if len(results) >= top_k:
                        break
    finally:
        conn.close()
    return results[:top_k]


# --------------------------------------------------------------------------- #
# Theme extraction from the engine analysis (data-back: emit a theme ONLY when
# the analyzer actually detected the corresponding ground-truth feature)
# --------------------------------------------------------------------------- #
def themes_from_game(game) -> List[str]:
    """
    Read a GameAnalysis and return the canonical themes present, ordered from most
    specific/noteworthy to most general. Only themes the analyzer truly detected
    are emitted — we never guess a theme the board didn't show.
    """
    moves = getattr(game, "moves", []) or []
    has = {
        "sacrifice": False, "fork": False, "pin": False, "doubled_pawns": False,
        "open_file": False, "king_safety": False, "endgame": False,
    }
    for m in moves:
        if getattr(m, "is_sacrifice", False) or getattr(m, "is_brilliant", False):
            has["sacrifice"] = True
        if getattr(m, "double_attack", None) or getattr(m, "best_move_double_attack", None):
            has["fork"] = True
        if getattr(m, "tactic_setup", None):
            has["pin"] = True
        if getattr(m, "doubled_pawns_created", None):
            has["doubled_pawns"] = True
        if getattr(m, "open_files", None):
            has["open_file"] = True
        if getattr(m, "is_castle", False):
            has["king_safety"] = True
        if getattr(m, "phase", "") == "endgame":
            has["endgame"] = True

    # Priority order: sharp tactics first, then structure, then the endgame, then
    # the always-relevant opening principles as a general backstop.
    ordered = ["sacrifice", "fork", "pin", "doubled_pawns", "open_file",
               "endgame", "king_safety"]
    themes = [t for t in ordered if has[t]]
    themes.append("development")  # every game has an opening; keep a principle query
    return themes


# --------------------------------------------------------------------------- #
# The narrator-facing entry point
# --------------------------------------------------------------------------- #
def load_knowledge_for_game(game, opening_name: Optional[str] = None,
                            max_passages: int = 4, max_chars: int = 6000) -> str:
    """
    Build the system/user-message block of classical-literature passages relevant
    to this game, ready to inject into the narrator prompt. Returns '' when the
    corpus is empty or nothing matches — in which case the narrator behaves
    exactly as it did before the corpus existed.

    This is the ONLY function the narrator needs to call. It is fully fail-safe.
    """
    try:
        themes = themes_from_game(game)
        passages = retrieve(themes, opening_name=opening_name, top_k=max_passages)
    except Exception:
        return ""
    if not passages:
        return ""

    blocks: List[str] = []
    total = 0
    for p in passages:
        excerpt = p.text.strip()
        block = f'[{p.attribution()}]\n"{excerpt}"'
        if total + len(block) > max_chars and blocks:
            break
        blocks.append(block)
        total += len(block)
    if not blocks:
        return ""

    joined = "\n\n".join(blocks)
    return (
        "## Classical chess literature (VERBATIM public-domain passages)\n"
        "These are exact excerpts from public-domain chess books, retrieved because "
        "they speak to themes present in THIS game (the opening, or a tactic/structure "
        "the engine detected). Unlike the style transcripts, you MAY quote or "
        "paraphrase these **with attribution** when one genuinely illuminates a move "
        "or position — e.g. \"As Capablanca put it, …\". They teach *principles*, not "
        "facts about this game: never use a passage to assert a board fact (the engine "
        "data above remains the sole source of board truth), never fabricate or extend "
        "a quote, and do not force a citation where it doesn't fit. Use at most one or "
        "two across the whole report, only where they add real insight.\n\n"
        f"{joined}"
    )


# --------------------------------------------------------------------------- #
# CLI: build the index and report what is in the corpus (so you can confirm a
# Cowork deposit was picked up). Usage:
#   python knowledge.py              build/refresh the index, print a summary
#   python knowledge.py --status     just print what is indexed
#   python knowledge.py --query foo  build, then show passages matching a query
# --------------------------------------------------------------------------- #
def _print_status() -> None:
    books = list(_iter_book_dirs())
    print(f"knowledge corpus at: {KNOWLEDGE_DIR}")
    if not books:
        print("  (no books yet — deposit texts per knowledge/README.md)")
    for bucket, book_dir in books:
        meta = _read_meta(book_dir, bucket)
        yr = f", {meta['year']}" if meta["year"] else ""
        print(f"  [{bucket}] {meta['title']}{yr}  <{book_dir.name}>")
    if DB_PATH.exists():
        try:
            conn = _connect()
            n = conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"]
            engine = _engine_kind(conn)
            conn.close()
            print(f"  index: {n} chunks ({engine}) -> {DB_PATH.name}")
        except sqlite3.DatabaseError:
            print("  index: present but unreadable (will rebuild on next run)")
    else:
        print("  index: not built yet")


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if "--status" in args:
        ensure_index()
        _print_status()
    elif "--query" in args:
        i = args.index("--query")
        query = " ".join(args[i + 1:]) or "endgame"
        n = build_index()
        print(f"Rebuilt index: {n} chunks.\n")
        conn = _connect()
        rows = _search(conn, [query], limit=3)
        conn.close()
        if not rows:
            print(f"No passages matched '{query}'.")
        for r in rows:
            p = _row_to_passage(r)
            print(f"--- {p.attribution()} [{p.bucket}] ---")
            print(p.text[:500].strip())
            print()
    else:
        n = build_index()
        print(f"Built index: {n} chunks.\n")
        _print_status()
