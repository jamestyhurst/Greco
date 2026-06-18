#!/usr/bin/env python
"""Post-deposit verification tool for a single knowledge corpus addition.

Run this immediately after depositing a new book to get fast feedback before
committing. It validates the files, rebuilds the FTS5 index, and confirms the
book is retrievable.

Usage:
    python tools/verify_corpus_addition.py <slug>
    python tools/verify_corpus_addition.py --all        # check every manifest entry

The automated test suite (tests/test_knowledge_corpus_health.py) runs the same
checks on every pytest run — this script just gives you faster, per-book output
without running the full suite.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import knowledge
from knowledge import KNOWLEDGE_DIR, BUCKETS, DB_PATH

MANIFEST_PATH = KNOWLEDGE_DIR / "MANIFEST.md"

PASS = "  [PASS]"
FAIL = "  [FAIL]"
SKIP = "  [SKIP]"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _locate(slug: str, filename: str) -> Path | None:
    for bucket in BUCKETS:
        p = KNOWLEDGE_DIR / bucket / "texts" / slug / filename
        if p.exists():
            return p
    return None


def _manifest_slugs() -> list[str]:
    if not MANIFEST_PATH.exists():
        return []
    return re.findall(r"\|\s*`([^`]+)`\s*\|",
                      MANIFEST_PATH.read_text(encoding="utf-8"))


def _check_slug(slug: str) -> int:
    """Run all checks for one slug. Returns number of failures."""
    print(f"\n── {slug} ──")
    failures = 0

    # 1. text.txt exists
    text_path = _locate(slug, "text.txt")
    if text_path:
        text = text_path.read_text(encoding="utf-8").strip()
        size = len(text)
        if size >= 500:
            print(f"{PASS} text.txt  ({size:,} chars, at {text_path.relative_to(ROOT)})")
        else:
            print(f"{FAIL} text.txt has only {size} chars — looks like a stub")
            failures += 1
    else:
        print(f"{FAIL} text.txt not found in any bucket under knowledge/*/texts/{slug}/")
        failures += 1

    # 2. meta.json exists and is valid
    meta_path = _locate(slug, "meta.json")
    if meta_path:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"{FAIL} meta.json parse error: {exc}")
            failures += 1
            meta = {}
        required = {"title", "author", "year", "bucket", "pd_basis"}
        missing = required - meta.keys()
        if missing:
            print(f"{FAIL} meta.json missing fields: {missing}")
            failures += 1
        else:
            year = meta.get("year", "?")
            print(f"{PASS} meta.json  (title: {meta.get('title')!r}, year: {year})")
        # PD year check (skip Greco seeds)
        if not slug.startswith("greco-seed"):
            y = meta.get("year")
            if y and int(y) > 1930:
                print(f"{FAIL} year {y} > 1930 — may not be in the public domain!")
                failures += 1
    else:
        print(f"{FAIL} meta.json not found under knowledge/*/texts/{slug}/")
        failures += 1

    # 3. FTS5 index check
    if not DB_PATH.exists():
        print(f"{SKIP} FTS5 index — knowledge.db not found, rebuilding...")
        try:
            knowledge.build_index()
        except Exception as exc:
            print(f"{FAIL} Could not build index: {exc}")
            return failures + 1

    try:
        conn = knowledge._connect()
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM chunks WHERE book_id = ?", (slug,)
        ).fetchone()["c"]
        conn.close()
    except Exception as exc:
        print(f"{FAIL} DB query failed: {exc}")
        return failures + 1

    if n >= 1:
        print(f"{PASS} FTS5 index  ({n} chunks for this book)")
    else:
        print(f"{FAIL} 0 chunks for '{slug}' in the FTS5 index")
        print(f"       → Run `python knowledge.py` to rebuild, then re-check.")
        failures += 1

    # 4. Retrieval smoke test
    if n >= 1:
        sample_phrases = ["chess", "king", "pawn"]
        passages = knowledge.retrieve(sample_phrases, top_k=10)
        from_this_book = [p for p in passages if p.book_id == slug]
        if from_this_book:
            p0 = from_this_book[0]
            snippet = p0.text[:80].replace("\n", " ")
            print(f"{PASS} Retrieval  ('{snippet}…')")
        else:
            # Retrieval not finding this book with generic terms is OK if it's
            # highly specialised — just note it, don't count as a hard failure.
            print(f"  [NOTE] This book did not appear in a generic 'chess/king/pawn' retrieval.")
            print(f"         That may be normal for highly specialised texts.")

    return failures


def _rebuild_index() -> bool:
    print("\nRebuilding FTS5 index…")
    try:
        n = knowledge.build_index()
        print(f"  Done: {n} chunks total.")
        return True
    except Exception as exc:
        print(f"  Build failed: {exc}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify a knowledge corpus deposit.")
    ap.add_argument("slug", nargs="?", help="Book slug to check (folder name under texts/)")
    ap.add_argument("--all", action="store_true", help="Check every manifest entry")
    ap.add_argument("--rebuild", action="store_true",
                    help="Force a full index rebuild before checking")
    args = ap.parse_args()

    if not args.slug and not args.all:
        ap.print_help()
        sys.exit(1)

    if args.rebuild or not DB_PATH.exists():
        if not _rebuild_index():
            sys.exit(1)

    slugs = _manifest_slugs() if args.all else [args.slug]
    if not slugs:
        print("No slugs found. Is MANIFEST.md present?")
        sys.exit(1)

    total_failures = 0
    for slug in slugs:
        total_failures += _check_slug(slug)

    print()
    if total_failures == 0:
        print(f"All checks passed for {len(slugs)} slug(s).")
    else:
        print(f"{total_failures} check(s) FAILED across {len(slugs)} slug(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
