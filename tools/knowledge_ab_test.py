"""
Greco knowledge-corpus A/B test.

Generates commentary for ONE game with the public-domain book corpus OFF vs ON,
so you can read — side by side — whether the retrieved passages actually change
(and improve) the report. Everything else is held constant; only `with_knowledge`
is toggled.

It analyzes the game ONCE with Stockfish, then calls Claude twice. Engine path +
API key + model are read from greco's config.json (the same ones the GUI saves)
unless overridden on the command line.

Two signals are printed, but THE .md FILES ARE THE REAL EVIDENCE — read them:
  1. marker counts (mentions of masters, attribution phrases) — a rough nudge;
     note the model may name a master from its own training even with books OFF.
  2. verbatim corpus overlap — how many 8-word spans in the report appear
     word-for-word in the corpus text. This is the hard proof of real quotation:
     it should be ~0 with books OFF and clearly higher with books ON.

Usage:
    set PYTHONUTF8=1
    python tools\\knowledge_ab_test.py --pgn "path\\to\\game.pgn"
    python tools\\knowledge_ab_test.py --pgn game.pgn --use-case coaching --depth 16

To save tokens, run it on Sonnet (config.json defaults the model to whatever the GUI
saved — often Opus). Coaching is the voice where the corpus is most used:
    python tools\\knowledge_ab_test.py --pgn game.pgn --use-case coaching --model claude-sonnet-4-6

This script makes its OWN API calls with a self-contained prompt — it does NOT inherit
the Claude Code session's context, so it's cheap to run even from a fresh, small session.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

GRECO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GRECO_DIR))

from importers import load_pgn          # noqa: E402
from analyzer import analyze_pgn        # noqa: E402
from triage import annotate_with_tiers  # noqa: E402
from narrator import generate_narrative # noqa: E402

KNOWLEDGE_MARKERS = {
    "names a master":       ["capablanca", "lasker", "nimzowitsch", "réti", "reti",
                              "tarrasch", "steinitz", "morphy"],
    "explicit attribution": ["as capablanca", "capablanca wrote", "capablanca put",
                             "capablanca observed", "capablanca said", "as lasker",
                             "in the words of", "once wrote", "as the old", "the masters"],
    "principle language":   ["principle", "fundamental", "timeless", "classic", "maxim",
                             "the rule is", "golden rule"],
}

USER_CTX = {"white_player": None, "black_player": None, "user_is": "neither", "player_named": False}

_WORD = re.compile(r"[a-z0-9]+")


def _norm_words(text: str):
    return _WORD.findall(text.lower())


def _ngrams(words, n=8):
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def corpus_text() -> str:
    """Concatenate every text.txt in the corpus (for the verbatim-overlap check)."""
    parts = []
    for tp in sorted((GRECO_DIR / "knowledge").rglob("text.txt")):
        try:
            parts.append(tp.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
    return "\n".join(parts)


def count_markers(text: str) -> dict:
    low = text.lower()
    return {name: sum(low.count(p) for p in pats) for name, pats in KNOWLEDGE_MARKERS.items()}


def verbatim_overlap(report: str, corpus_ngrams: set, n=8) -> int:
    """How many n-word spans in the report appear verbatim in the corpus."""
    return len(_ngrams(_norm_words(report), n) & corpus_ngrams)


def main() -> int:
    ap = argparse.ArgumentParser(description="A/B test whether the knowledge corpus changes Greco's report.")
    ap.add_argument("--pgn", required=True)
    ap.add_argument("--engine", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--depth", type=int, default=14)
    ap.add_argument("--max-tokens", type=int, default=14000)
    ap.add_argument("--use-case", default="companion", choices=["commentary", "companion", "coaching"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = {}
    cfg_path = GRECO_DIR / "config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    engine = args.engine or cfg.get("stockfish_path") or os.environ.get("STOCKFISH_PATH")
    if not engine or not os.path.isfile(engine):
        print("ERROR: no valid Stockfish engine. Pass --engine or set it in the GUI.", file=sys.stderr)
        return 2
    api_key = cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: no ANTHROPIC_API_KEY (set it in the GUI or the env var).", file=sys.stderr)
        return 2
    os.environ["ANTHROPIC_API_KEY"] = api_key
    model = args.model or cfg.get("model") or "claude-sonnet-4-6"

    pgn_text, src = load_pgn(args.pgn)
    print(f"Loaded PGN from {src}", file=sys.stderr)
    print(f"Analyzing with Stockfish (depth {args.depth})... one analysis, reused for both arms.", file=sys.stderr)
    game = analyze_pgn(pgn_text, engine_path=engine, depth=args.depth, multipv=3)
    tiers = annotate_with_tiers(game, USER_CTX)
    print(f"Analyzed {len(game.moves)} moves. Model: {model}, voice: {args.use_case}.", file=sys.stderr)

    conditions = [
        ("A_no_books",   dict(with_knowledge=False), "baseline — knowledge corpus OFF"),
        ("B_with_books", dict(with_knowledge=True),  "knowledge corpus ON (public-domain books)"),
    ]
    out = Path(args.out) if args.out else (Path(args.pgn).resolve().parent / "knowledge_ab_out")
    out.mkdir(parents=True, exist_ok=True)

    results = []
    for name, flags, desc in conditions:
        print(f"\n=== generating {name}: {desc} ===", file=sys.stderr)
        text = generate_narrative(
            game, tiers, USER_CTX, model=model, max_tokens=args.max_tokens,
            use_case=args.use_case, live_stream_to=None, **flags,
        )
        (out / f"{name}.md").write_text(text, encoding="utf-8")
        results.append((name, desc, text))
        print(f"   wrote {out / (name + '.md')} ({len(text):,} chars)", file=sys.stderr)

    cn = _ngrams(_norm_words(corpus_text()), 8)
    names = [r[0] for r in results]
    counts = {name: count_markers(text) for name, _, text in results}
    print("\n" + "=" * 70)
    print("KNOWLEDGE-CORPUS A/B  (the .md files are the real evidence)")
    print("=" * 70)
    print("signal".ljust(26) + "".join(n.ljust(16) for n in names))
    print("-" * (26 + 16 * len(names)))
    for marker in KNOWLEDGE_MARKERS:
        print(marker.ljust(26) + "".join(str(counts[n][marker]).ljust(16) for n in names))
    print("verbatim corpus 8-grams".ljust(26) +
          "".join(str(verbatim_overlap(t, cn)).ljust(16) for _, _, t in results))
    print("word count".ljust(26) + "".join(str(len(t.split())).ljust(16) for _, _, t in results))
    print(f"\nOutputs in: {out}")
    print("Read A_no_books.md vs B_with_books.md side by side — that difference IS the corpus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
