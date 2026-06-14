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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
DB_PATH = KNOWLEDGE_DIR / "knowledge.db"
BUCKETS = ("opening_theory", "chess_principles")

# Bump when the indexing/cleaning logic changes (not just the texts), so the
# staleness check forces a rebuild even when the source files are untouched.
INDEX_VERSION = "2"

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
    matched_theme: str = ""
    matched_phrases: List[str] = field(default_factory=list)

    def attribution(self) -> str:
        bits = [b for b in (self.author, self.title) if b]
        head = " — ".join(bits) if bits else (self.book_id or "unknown source")
        if self.year:
            head += f" ({self.year})"
        return head


def _extract_key_sentences(text: str, query_words: List[str],
                           max_sentences: int = 2, max_words: int = 55) -> str:
    """
    Return the 1-2 sentences from `text` most likely to be quotable — scored by
    how many query vocabulary words they contain. Falls back to the first sentence.
    Keeps the output short enough (~55 words) for the narrator to quote cleanly
    rather than having to cut a 380-word block mid-thought.
    """
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in raw if s.strip()]
    if not sentences:
        return text.strip()

    query_set = {w.lower() for w in query_words if len(w) > 3}
    scored = []
    for s in sentences:
        words = re.findall(r"[a-z']+", s.lower())
        score = sum(1 for w in words if w in query_set)
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])

    picked: List[str] = []
    total_words = 0
    for _, sent in scored[:max_sentences]:
        wc = len(sent.split())
        if total_words + wc > max_words and picked:
            break
        picked.append(sent)
        total_words += wc
    return " ".join(picked) if picked else sentences[0]


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


# Old chess books interleave teaching PROSE with game scores (move lists) and
# diagram markers. Only the prose is quotable; a chunk that is mostly notation
# matches theme queries on incidental words and pollutes retrieval (e.g. a chunk
# of "1. K-R1! P-N5 2. ..." matching "king"). These helpers strip editorial
# markers and keep only prose-dense chunks at index time.
_ARTIFACT_RE = re.compile(r"\[[^\]]{0,80}\]")   # [Illustration: ...], [123], etc.
_PROSE_WORD_RE = re.compile(r"[a-z]{4,}")       # a 4+ letter lowercase run ~ a real word
_MOVE_NUM_RE = re.compile(r"\b\d{1,3}\.")        # "12." — a numbered move
# A sentence opening with one of these reads oddly when quoted out of context
# (a dangling connector or a pronoun with no antecedent) — reject it as a feature.
_DANGLING_START_RE = re.compile(
    r"^(but|then|thus|this|therefore|hence|however|so|it|he|she|they|such|these|"
    r"those|that|yet|and|or|for|nor)\b",
    re.IGNORECASE,
)


def _clean_chunk(text: str) -> str:
    """Strip editorial/diagram markers and tidy whitespace in a chunk."""
    text = _ARTIFACT_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_quotable_prose(text: str) -> bool:
    """True if a chunk is mostly teaching prose (worth quoting), not a game score
    or a diagram fragment."""
    prose_words = len(_PROSE_WORD_RE.findall(text.lower()))
    move_nums = len(_MOVE_NUM_RE.findall(text))
    if prose_words < 40:        # too short/sparse to be a useful quotation
        return False
    if move_nums >= 8:          # a paragraph dense with numbered moves = a game score
        return False
    if move_nums > prose_words / 8:  # notation outweighs prose
        return False
    return True


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
    return f"v{INDEX_VERSION}|" + "|".join(sorted(parts))


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
            kept = 0
            for chunk in chunk_text(raw):
                cleaned = _clean_chunk(chunk)
                if not _is_quotable_prose(cleaned):
                    continue  # skip game scores, diagrams, sparse fragments
                conn.execute(
                    "INSERT INTO chunks (text, book_id, title, author, year, bucket, chunk_index)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (cleaned, meta["book_id"], meta["title"], meta["author"],
                     meta["year"], meta["bucket"], kept),
                )
                kept += 1
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

    # Each entry is (theme_label, phrases) so retrieved passages can be tagged
    # with the theme that caused them to be retrieved — used later for phase-gating.
    tagged_queries: List[tuple] = []
    if opening_name:
        tagged_queries.append(
            ("opening", [opening_name] + _WORD_RE.findall(opening_name))
        )
    for theme in themes:
        phrases = THEME_QUERIES.get(theme)
        if phrases:
            tagged_queries.append((theme, list(phrases)))
    if not tagged_queries:
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
        for theme_label, phrases in tagged_queries:
            if len(results) >= top_k:
                break
            for row in _search(conn, phrases, per_query):
                key = (row["book_id"], row["chunk_index"])
                if key in seen:
                    continue
                seen.add(key)
                p = _row_to_passage(row)
                p.matched_theme = theme_label
                p.matched_phrases = phrases
                results.append(p)
                break
        # Pass 2: fill remaining slots, allowing more from each query.
        if len(results) < top_k:
            for theme_label, phrases in tagged_queries:
                if len(results) >= top_k:
                    break
                for row in _search(conn, phrases, per_query + 3):
                    key = (row["book_id"], row["chunk_index"])
                    if key in seen:
                        continue
                    seen.add(key)
                    p = _row_to_passage(row)
                    p.matched_theme = theme_label
                    p.matched_phrases = phrases
                    results.append(p)
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
def _is_human_authored(p: "Passage") -> bool:
    """True only for passages from a named human author — not Greco seed texts."""
    author = (p.author or "").strip().lower()
    if not author:
        return False
    if author == "greco project":
        return False
    return True


def _best_quotable_sentence(text: str, query_words: Sequence[str]) -> str:
    """Pick ONE clean, self-contained sentence to feature as a guaranteed verbatim
    quote: highest query-overlap within an ~8-32 word window, rejecting sentences
    that open with a dangling connector/pronoun or contain move notation/artifacts.
    Returns '' when nothing clean qualifies — better no featured quote than an
    awkward one (the design's "avoid awkward forced quotes" guard)."""
    raw = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    query_set = {w.lower() for w in query_words if len(w) > 3}
    best, best_score = "", -1
    for sentence in raw:
        s = sentence.strip().strip('"').strip()
        wc = len(s.split())
        if wc < 8 or wc > 32:
            continue
        if _DANGLING_START_RE.match(s):
            continue
        if _MOVE_NUM_RE.search(s) or "[" in s or "]" in s or '"' in s:
            continue  # skip notation, artifacts, and interior quotes (malformed when re-quoted)
        words = re.findall(r"[a-z']+", s.lower())
        score = sum(1 for w in words if w in query_set)
        if score > best_score:
            best, best_score = s, score
    return best


def select_featured_passage(passages: Sequence["Passage"]):
    """From already-retrieved human-authored passages, choose the single best one
    whose best sentence passes the cleanliness guard — preferring a specific-theme
    passage over the generic 'development' backstop, then better retrieval rank
    (passages already arrive best-first). Returns (Passage, sentence) or None."""
    specific_themes = (
        "opening", "sacrifice", "fork", "pin", "doubled_pawns",
        "open_file", "endgame", "king_safety", "isolated_pawn", "passed_pawn",
    )
    candidates = []
    for p in passages:
        if not _is_human_authored(p):
            continue
        sentence = _best_quotable_sentence(
            p.text, p.matched_phrases or p.text.split()[:8]
        )
        if not sentence:
            continue
        # 0 sorts before 1 → specific-theme passages are preferred; retrieval order
        # (best-first) is preserved within each group by the stable sort.
        specificity = 0 if p.matched_theme in specific_themes else 1
        candidates.append((specificity, p, sentence))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    _, passage, sentence = candidates[0]
    return (passage, sentence)


def _format_featured_passage(p: "Passage", sentence: str) -> str:
    """Build the deterministic, pre-attributed FEATURED PASSAGE block. The quote is
    assembled in code from the real text, so it is correct-by-construction; the
    model only chooses where it fits and writes the surrounding analysis."""
    author = p.author or "a master"
    if p.title and p.year:
        attribution = f"As {author} writes in {p.title} ({p.year}):"
    elif p.title:
        attribution = f"As {author} writes in {p.title}:"
    else:
        attribution = f"As {author} writes:"

    theme = p.matched_theme or "general"
    placement = {
        "endgame": "a move in the endgame phase",
        "opening": "a move in the opening",
        "sacrifice": "a move where a sacrifice or combination was played",
    }.get(theme, "the move it best illustrates")

    return (
        "## FEATURED PASSAGE (include this quotation)\n"
        "Below is ONE verbatim quotation, already attributed and assembled from the "
        "source text. Reproduce it word-for-word, in quotation marks, at the single "
        "move it best illustrates; you choose where it fits and write the surrounding "
        "analysis. Do NOT paraphrase, trim, or re-attribute it. If — and only if — no "
        "move in this game genuinely fits the idea, you may omit it.\n\n"
        f'{attribution} "{sentence}"\n\n'
        f"(Place this near {placement}.)"
    )


def load_knowledge_for_game(game, opening_name: Optional[str] = None,
                            max_passages: int = 4, max_chars: int = 6000) -> str:
    """
    Build the system/user-message block of classical-literature passages relevant
    to this game, ready to inject into the narrator prompt. Returns '' when the
    corpus is empty or nothing matches — in which case the narrator behaves
    exactly as it did before the corpus existed.

    Only passages from named human authors (e.g. Capablanca) are injected.
    Greco seed texts are excluded so the narrator is never tempted to attribute
    quotes to "Greco" or unnamed internal notes.

    This is the ONLY function the narrator needs to call. It is fully fail-safe.
    """
    try:
        themes = themes_from_game(game)
        all_passages = retrieve(themes, opening_name=opening_name, top_k=max_passages)
        passages = [p for p in all_passages if _is_human_authored(p)]
    except Exception:
        return ""
    if not passages:
        return ""

    blocks: List[str] = []
    total = 0
    for p in passages:
        theme = p.matched_theme or "general"

        # Short, quotable excerpt — the 1-2 most relevant sentences (≤55 words).
        key_sentence = _extract_key_sentences(
            p.text,
            p.matched_phrases if p.matched_phrases else p.text.split()[:8],
            max_sentences=2,
            max_words=55,
        )

        # Phase/tactic gate: tells the narrator when it is and isn't appropriate
        # to apply this passage.
        if theme == "endgame":
            gate = (
                "• PHASE GATE: cite this only at moves in the endgame phase — "
                "not in the opening or middlegame.\n"
            )
        elif theme == "opening":
            gate = (
                "• PHASE GATE: cite this only during the opening — "
                "not in the middlegame or endgame.\n"
            )
        elif theme == "sacrifice":
            gate = (
                "• TACTIC GATE: cite this only at a move where a sacrifice or "
                "combination was played — not at quiet positional moves.\n"
            )
        else:
            gate = ""

        block = (
            f"[{p.attribution()} | retrieved-for: {theme}]\n\n"
            f"QUOTABLE EXCERPT (≤55 words — use these exact words if you quote):\n"
            f'"{key_sentence}"\n\n'
            f"POSITION VALIDATION — read before citing:\n"
            f'• This passage was retrieved on the "{theme}" theme. Before quoting, '
            f"confirm the specific move you are annotating genuinely exhibits this theme.\n"
            f"• If the passage's concrete claim does not match the position details "
            f"(e.g. the quote says 'defend pawns' but the position involves defending "
            f"pieces, not pawns), skip this passage entirely — do not cite or paraphrase it.\n"
            f"{gate}"
            f"\nFULL PASSAGE (background context only — do not quote from this section; "
            f"quote only from QUOTABLE EXCERPT above):\n"
            f'"{p.text.strip()}"'
        )
        if total + len(block) > max_chars and blocks:
            break
        blocks.append(block)
        total += len(block)
    if not blocks:
        return ""

    joined = "\n\n---\n\n".join(blocks)
    literature = (
        "## Classical chess literature (public-domain passages)\n"
        "Each entry below has three parts:\n"
        "  1. QUOTABLE EXCERPT — 1-2 sentences (≤55 words). "
        "If you quote, use these exact words.\n"
        "  2. POSITION VALIDATION — a gate you MUST check before citing. "
        "If the position's specifics do not match the passage's claim, skip it.\n"
        "  3. FULL PASSAGE — background only; do not quote directly from it.\n\n"
        "Attribution rule: cite only named historical masters (Capablanca, Lasker, "
        "Nimzowitsch, etc.). Aim for 1-3 quotations per report, where they "
        "genuinely sharpen a lesson. Silence is correct when no passage fits cleanly.\n\n"
        f"{joined}"
    )

    # Deterministic featured passage: pick the single best chunk and hand the model
    # ONE finished, attributed, verbatim quotation it is told to include — so a quote
    # reliably reaches the page instead of being smoothed into paraphrase (the A/B
    # finding). Fail-safe: no clean sentence → no featured section, behaves as before.
    featured = ""
    try:
        selection = select_featured_passage(passages)
        if selection:
            fp, sentence = selection
            featured = _format_featured_passage(fp, sentence) + "\n\n"
    except Exception:
        featured = ""

    return featured + literature


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
