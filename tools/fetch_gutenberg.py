"""
tools/fetch_gutenberg.py — acquire a public-domain chess book from Project
Gutenberg and deposit it into Greco's knowledge corpus, cleaned and ready.

This automates the mechanical half of the deposit protocol in
`knowledge/README.md`: download the plain-text edition, strip Project
Gutenberg's header / footer / license boilerplate, collapse the worst of the
whitespace, and write
    knowledge/<bucket>/texts/<slug>/text.txt
    knowledge/<bucket>/texts/<slug>/meta.json

You (or the acquiring agent) still do the JUDGEMENT half: confirm the work is
genuinely public domain (first published 1930 or earlier; a modern translation
of an old original is NOT public domain), pick the right bucket, and add the row
to `knowledge/MANIFEST.md`. See the README for the rules.

Usage:
    set PYTHONUTF8=1
    python tools\\fetch_gutenberg.py --id 33870 --bucket chess_principles ^
        --slug capablanca-chess-fundamentals ^
        --title "Chess Fundamentals" --author "Jose Raul Capablanca" --year 1921 ^
        --pd-basis "First published 1921; US copyright expired (pre-1931)."

    # Clean an already-downloaded raw .txt instead of downloading:
    python tools\\fetch_gutenberg.py --raw-file raw.txt --bucket chess_principles ^
        --slug capablanca-chess-fundamentals --title "..." --author "..." --year 1921

After it runs:  python knowledge.py --status   (confirm the new book + chunk count)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

GRECO_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = GRECO_DIR / "knowledge"
BUCKETS = ("opening_theory", "chess_principles")


def download_gutenberg(book_id: int) -> str:
    """Fetch the plain-text edition, trying the standard Gutenberg URL shapes."""
    urls = [
        f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}.txt",
    ]
    last = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Greco corpus builder"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            # Gutenberg text is UTF-8 for modern files; fall back leniently.
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")
        except Exception as exc:  # try the next URL shape
            last = exc
            continue
    raise RuntimeError(f"Could not download Gutenberg #{book_id}: {last}")


def strip_gutenberg(text: str) -> str:
    """Remove Gutenberg's header, footer, license, and producer lines, leaving
    just the book body. Conservative: if a marker is missing, keep more rather
    than risk cutting real content."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Slice to the body between the START and END markers when present.
    start = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG.*?\*\*\*",
                      text, re.IGNORECASE)
    if start:
        text = text[start.end():]
    end = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG.*?\*\*\*",
                    text, re.IGNORECASE)
    if end:
        text = text[:end.start()]

    # Drop the leading producer/proofreader credit block. These wrap across
    # several lines ("Produced by X, Y,\nZ and the Online Distributed\nProofreading
    # Team at pgdp.net"), so within the first ~15 lines we drop any line that looks
    # like part of that credit.
    credit = re.compile(
        r"(Produced by|E-text prepared by|Transcrib|Distributed Proofread|"
        r"Online Distributed|pgdp\.net|produced from images|page images)",
        re.IGNORECASE,
    )
    lines = text.split("\n")
    cleaned = []
    for i, line in enumerate(lines):
        if i < 15 and credit.search(line):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)

    # Remove Gutenberg "[Illustration ...]" markers, with or without a colon
    # (and other short bracketed editorial markers), which are not prose.
    text = re.sub(r"\[Illustration[^\]]*\]", "", text)

    # Collapse 3+ blank lines to a paragraph break; trim edges.
    text = re.sub(r"\n[ \t]*\n[ \t]*(\n[ \t]*)+", "\n\n", text)
    return text.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch + deposit a public-domain chess book into Greco's corpus.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--id", type=int, help="Project Gutenberg book ID (downloads the plain text)")
    src.add_argument("--raw-file", type=str, help="Path to an already-downloaded raw .txt to clean instead")
    ap.add_argument("--bucket", required=True, choices=BUCKETS)
    ap.add_argument("--slug", required=True, help="ASCII folder name, e.g. capablanca-chess-fundamentals")
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", default="")
    ap.add_argument("--year", type=int, required=True, help="ORIGINAL publication year (drives the legal check)")
    ap.add_argument("--language", default="en")
    ap.add_argument("--pd-basis", default="")
    ap.add_argument("--translation-status", default="Original language — verify before quoting a translation.")
    args = ap.parse_args()

    if args.year > 1930:
        print(f"REFUSING: year {args.year} is after 1930 — not public domain under the US 95-year rule "
              f"(as of 2026). See knowledge/README.md.", file=sys.stderr)
        return 2

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.slug):
        print(f"REFUSING: slug '{args.slug}' must be lowercase ASCII letters/digits/hyphens.", file=sys.stderr)
        return 2

    if args.raw_file:
        raw = Path(args.raw_file).read_text(encoding="utf-8", errors="ignore")
        source_url = ""
    else:
        print(f"Downloading Gutenberg #{args.id} ...", file=sys.stderr)
        raw = download_gutenberg(args.id)
        source_url = f"https://www.gutenberg.org/ebooks/{args.id}"

    body = strip_gutenberg(raw)
    if len(body) < 1000:
        print(f"WARNING: cleaned text is only {len(body)} chars — check the source.", file=sys.stderr)

    book_dir = KNOWLEDGE_DIR / args.bucket / "texts" / args.slug
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "text.txt").write_text(body, encoding="utf-8")
    meta = {
        "title": args.title,
        "author": args.author,
        "year": args.year,
        "language": args.language,
        "source_url": source_url,
        "pd_basis": args.pd_basis or f"First published {args.year}; pre-1931, US copyright expired.",
        "translation_status": args.translation_status,
        "bucket": args.bucket,
    }
    (book_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    words = len(body.split())
    print(f"Deposited: {args.title} -> {book_dir}")
    print(f"  text.txt: {len(body):,} chars (~{words:,} words)")
    print(f"  meta.json written.")
    print(f"\nNEXT STEPS:")
    print(f"  1. Add a row to knowledge/MANIFEST.md for '{args.slug}'.")
    print(f"  2. Run:  python knowledge.py --status   (confirm it indexed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
