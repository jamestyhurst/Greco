#!/usr/bin/env python
"""Spot-check: show what each corpus book actually contributes to commentary.

Answers: "Are these books net-positively influencing Greco's reports?"

For each book the script:
  1. Pulls a random sample of 3 chunks directly from that book's rows (no FTS
     competition from other books — every book gets examined on its own terms).
  2. Checks each chunk for prose quality (minimum length, symbol ratio, chess
     vocabulary, no OCR garbage runs).
  3. Prints or summarises the results.

This is different from test_knowledge_corpus_health.py, which tests that the
FTS5 index is built correctly.  This script tests that the actual TEXT CONTENT
is readable, relevant chess prose.

Usage:
    python tools/spot_check_corpus.py              # check all books, show passages
    python tools/spot_check_corpus.py <slug>       # check one book
    python tools/spot_check_corpus.py --brief      # one-line per book (no text)
    PYTHONUTF8=1 python tools/spot_check_corpus.py # needed on Windows for unicode output
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import knowledge
from knowledge import DB_PATH

# Chess vocabulary — uses stem matching so "pieces" matches "piece", etc.
CHESS_STEMS = [
    "king", "queen", "rook", "bishop", "knight", "pawn",
    "castl", "check", "stalemat",
    "move", "piece", "position", "file", "rank", "diagonal", "board",
    "open", "endgame", "middlegame", "attack", "defens", "sacrific",
    "exchang", "material", "centr", "center",
    "develop", "tempo", "initiativ", "advantag",
    "squar", "captur", "retreat", "advanc", "promot",
    "pass", "isolat", "backward", "doubl", "outpost",
    "chess", "game", "play", "player", "master", "grandmaster",
    "tactic", "strateg", "combination", "maneuver",
]


def _has_chess_vocab(text: str) -> bool:
    low = text.lower()
    return any(stem in low for stem in CHESS_STEMS)


def _symbol_ratio(text: str) -> float:
    if not text:
        return 1.0
    weird = sum(1 for c in text if not (c.isalpha() or c.isdigit() or c.isspace()
                                         or c in ".,;:!?-'\"()[]"))
    return weird / len(text)


def _has_ocr_garbage(text: str) -> bool:
    # Only flag non-whitespace repeated runs; OCR books often have many
    # spaces/newlines from column layout, which is harmless.
    return bool(re.search(r'([^\s])\1{6,}', text))


def _grade(text: str) -> tuple[str, list[str]]:
    """Return ('good'|'warn'|'bad', issues)."""
    issues = []
    stripped = text.strip()
    if len(stripped) < 80:
        issues.append(f"very short ({len(stripped)} chars)")
    if _symbol_ratio(text) > 0.20:
        issues.append(f"high symbol ratio ({_symbol_ratio(text):.0%})")
    if _has_ocr_garbage(text):
        issues.append("repeated-char runs (OCR garbage)")
    if not _has_chess_vocab(text):
        issues.append("no recognisable chess vocabulary")

    if not issues:
        return "good", []
    # One structural issue (short) is warn; vocabulary miss or 2+ issues = bad
    if len(issues) >= 2 or any("no recognisable" in i for i in issues):
        return "bad", issues
    return "warn", issues


# ── Per-book check ────────────────────────────────────────────────────────────

def _check_book(slug: str, conn, brief: bool = False) -> dict:
    rows = conn.execute(
        "SELECT text FROM chunks WHERE book_id = ? ORDER BY chunk_index",
        (slug,)
    ).fetchall()
    n_chunks = len(rows)

    if n_chunks == 0:
        if not brief:
            print(f"\n{'-'*60}")
            print(f"  {slug}")
            print("  [BAD] 0 chunks in the index.")
        return {"slug": slug, "chunks": 0, "good": 0, "warn": 0, "bad": 0}

    # Sample up to 5 chunks evenly spread through the book
    step = max(1, n_chunks // 5)
    sample = [rows[i]["text"] for i in range(0, min(n_chunks, step * 5), step)]
    random.shuffle(sample)
    sample = sample[:3]

    good = warn = bad = 0
    graded = []
    for text in sample:
        g, issues = _grade(text)
        if g == "good":
            good += 1
        elif g == "warn":
            warn += 1
        else:
            bad += 1
        graded.append((g, issues, text))

    if brief:
        if bad > 0:
            flag = "[BAD ]"
        elif warn > 0:
            flag = "[WARN]"
        else:
            flag = "[GOOD]"
        print(f"  {flag}  {slug:<50}  {n_chunks:>4} chunks  {good}ok {warn}warn {bad}bad")
    else:
        print(f"\n{'-'*60}")
        print(f"  {slug}  ({n_chunks} chunks, sample of {len(graded)})")
        for g, issues, text in graded:
            icon = "ok" if g == "good" else ("!!" if g == "warn" else "XX")
            print(f"\n  [{icon}]", end="")
            if issues:
                print(f"  issues: {'; '.join(issues)}")
            else:
                print()
            snippet = text.strip()[:280].replace("\n", " | ")
            print(f"       {snippet!r}")

    return {"slug": slug, "chunks": n_chunks, "good": good, "warn": warn, "bad": bad}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Spot-check corpus book text quality.")
    ap.add_argument("slug", nargs="?", help="Slug to check (default: all books)")
    ap.add_argument("--brief", action="store_true",
                    help="One-line summary per book, no passage text")
    ap.add_argument("--seed", type=int, default=42,
                    help="Random seed for reproducible sampling (default 42)")
    args = ap.parse_args()
    random.seed(args.seed)

    if not DB_PATH.exists():
        print("knowledge.db not found. Run: python knowledge.py")
        sys.exit(1)

    conn = knowledge._connect()
    if not knowledge._has_rows(conn):
        print("knowledge.db is empty. Run: python knowledge.py")
        conn.close()
        sys.exit(1)

    if args.slug:
        slugs = [args.slug]
    else:
        rows = conn.execute(
            "SELECT DISTINCT book_id FROM chunks ORDER BY book_id"
        ).fetchall()
        slugs = [r["book_id"] for r in rows]

    print(f"\nSpot-checking {len(slugs)} book(s)  (seed={args.seed})\n")
    if args.brief:
        print(f"  {'Status':<6}  {'Slug':<50}  {'Chunks':>6}  Grades")
        print(f"  {'-'*6}  {'-'*50}  {'-'*6}  {'-'*18}")

    results = [_check_book(s, conn, brief=args.brief) for s in slugs]
    conn.close()

    total_bad  = sum(r["bad"]  for r in results)
    total_warn = sum(r["warn"] for r in results)
    total_good = sum(r["good"] for r in results)
    zero_chunk = sum(1 for r in results if r["chunks"] == 0)

    print(f"\n{'-'*60}")
    print(f"Summary: {len(slugs)} books | passages: "
          f"{total_good} ok  {total_warn} warn  {total_bad} bad"
          f"  | {zero_chunk} book(s) with 0 chunks")
    if total_bad > 0 or zero_chunk > 0:
        print("Action needed: review the [BAD]/0-chunk books listed above.")
    elif total_warn > 0:
        print("Minor issues found. Review [WARN] passages manually.")
    else:
        print("All sampled passages look like usable chess prose.")


if __name__ == "__main__":
    main()
