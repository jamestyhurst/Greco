"""
Greco commentary STYLE A/B test.

Generates commentary for ONE game under different "style source" settings, so you
can read — side by side — how much the house style guide (GRECO_STYLE.md) and the
commentary_refs transcripts actually change Greco's voice. This is the honest way
to answer "is Greco really imitating these commentators?": compare the output with
the sources ON vs OFF and read the difference.

It analyzes the game ONCE with Stockfish, then calls Claude a few times with the
style sources toggled. Engine path + API key are read from greco's config.json
(the same ones the GUI saves) unless overridden on the command line.

Usage:
    set PYTHONUTF8=1
    python tools\\style_ab_test.py --pgn "examples\\morphy_opera.pgn"
    python tools\\style_ab_test.py --pgn game.pgn --full-matrix --depth 12

Outputs: writes A_none.md, B_full.md (etc.) to an output folder and prints a
style-marker table. The .md files are the real evidence — read them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make greco's modules importable no matter where this is run from.
GRECO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GRECO_DIR))

from importers import load_pgn          # noqa: E402
from analyzer import analyze_pgn        # noqa: E402
from triage import annotate_with_tiers  # noqa: E402
from narrator import generate_narrative # noqa: E402


# Signature voice/craft markers to count (lowercased substring match). These are
# delivery tells, NOT chess facts — a rough quantitative hint of whether the style
# sources are shaping the output. The .md files are the real proof; this is a nudge.
STYLE_MARKERS = {
    "scene-setting open":     ["welcome", "our story", "the year", "picture this", "the stage is set", "let me take you"],
    "invite the viewer":      ["can you find", "feel free to pause", "take a moment", "see if you can", "pause here", "what would you play"],
    "turning-point callout":  ["critical moment", "this is the moment", "here's where", "the turning point", "everything changes", "watch closely"],
    "purpose-per-move (why)":  ["so that", "the idea is", "the point is", "with the idea", "intending", "in order to", "eyeing"],
    "excitement spikes":      ["!", "stunning", "brilliant", "incredible", "wow", "boom", "ice-cold"],
    "video structure":        ["[scene break]", "cold open", "outro"],
}

USER_CTX = {"white_player": None, "black_player": None, "user_is": "neither", "player_named": False}


def count_markers(text: str) -> dict:
    low = text.lower()
    return {name: sum(low.count(p) for p in pats) for name, pats in STYLE_MARKERS.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="A/B test how much the style sources change Greco's commentary voice.")
    ap.add_argument("--pgn", required=True, help="PGN file (or Lichess URL / raw PGN text) to commentate")
    ap.add_argument("--engine", default=None, help="Stockfish path (default: config.json / STOCKFISH_PATH)")
    ap.add_argument("--model", default=None, help="Claude model (default: config.json 'model' or claude-sonnet-4-6)")
    ap.add_argument("--depth", type=int, default=12, help="Engine depth (default 12 — lower is faster and fine for a style test)")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--use-case", default="commentary", choices=["commentary", "companion", "coaching"])
    ap.add_argument("--full-matrix", action="store_true",
                    help="Run all 4 conditions (none / guide-only / refs-only / full) instead of just none vs full")
    ap.add_argument("--out", default=None, help="Output folder (default: style_ab_out next to the PGN)")
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
        print("ERROR: no valid Stockfish engine. Pass --engine, or set it once in the GUI (saved to config.json).", file=sys.stderr)
        return 2
    api_key = cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: no ANTHROPIC_API_KEY (enter it once in the GUI, or set the env var).", file=sys.stderr)
        return 2
    os.environ["ANTHROPIC_API_KEY"] = api_key
    model = args.model or cfg.get("model") or "claude-sonnet-4-6"

    pgn_text, src = load_pgn(args.pgn)
    print(f"Loaded PGN from {src}", file=sys.stderr)
    print(f"Analyzing with Stockfish (depth {args.depth})... one analysis, reused for every condition.", file=sys.stderr)
    game = analyze_pgn(pgn_text, engine_path=engine, depth=args.depth, multipv=3)
    tiers = annotate_with_tiers(game, USER_CTX)
    print(f"Analyzed {len(game.moves)} moves. Model: {model}, voice: {args.use_case}.", file=sys.stderr)

    conditions = [
        ("A_none", dict(with_style_guide=False, with_references=False), "voice DESCRIPTION only (no guide, no transcripts)"),
        ("B_full", dict(with_style_guide=True,  with_references=True),  "FULL: house guide + transcripts (your real setup)"),
    ]
    if args.full_matrix:
        conditions[1:1] = [
            ("C_guide_only", dict(with_style_guide=True,  with_references=False), "house GUIDE only"),
            ("D_refs_only",  dict(with_style_guide=False, with_references=True),  "TRANSCRIPTS only"),
        ]

    out = Path(args.out) if args.out else (Path(args.pgn).resolve().parent / "style_ab_out")
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

    # Quantitative nudge.
    names = [r[0] for r in results]
    counts = {name: count_markers(text) for name, _, text in results}
    print("\n" + "=" * 78)
    print("STYLE-MARKER COUNTS  (rough signal — the .md files are the real evidence)")
    print("=" * 78)
    print("marker".ljust(26) + "".join(n.ljust(14) for n in names))
    print("-" * (26 + 14 * len(names)))
    for marker in STYLE_MARKERS:
        print(marker.ljust(26) + "".join(str(counts[n][marker]).ljust(14) for n in names))
    print("word count".ljust(26) + "".join(str(len(t.split())).ljust(14) for _, _, t in results))
    print(f"\nOutputs in: {out}")
    print("Read A_none.md vs B_full.md side by side — that difference IS the influence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
