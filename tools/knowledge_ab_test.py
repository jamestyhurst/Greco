"""
DEVELOPER TOOL — not part of the shipped Greco product.

Greco knowledge-corpus A/B test.

Generates commentary for ONE game with the public-domain book corpus OFF vs ON,
so you can read — side by side — whether the retrieved passages actually change
(and improve) the report. Everything else is held constant; only `with_knowledge`
is toggled.

It analyzes the game ONCE with Stockfish, then calls Claude twice. Engine path +
API key + model are read from greco's config.json (the same ones the GUI saves)
unless overridden on the command line.

THREE outputs are produced, but THE .md FILES ARE THE REAL EVIDENCE — read them:

  1. CONSOLE: summary table (marker counts, verbatim hit count) + a quick-scan
     list of the EXACT 8-word phrases matched verbatim in the corpus-ON arm, so
     you can see at a glance WHAT the model quoted (not just that it quoted).

  2. A_no_books.md / B_with_books.md — the full reports for each arm.

  3. C_spotlight.md — the fast diff: verbatim hit contexts, attribution sentences
     from each arm side by side, and the closing section from each arm. Read this
     instead of both full reports when you only need to check whether the corpus
     is being used correctly.

Signals in the table:
  - marker counts (mentions of masters, attribution phrases) — rough nudge; the
    model may cite a master from its own training even with books OFF.
  - verbatim corpus 8-grams — hard proof of real quotation: ~0 when books OFF,
    clearly higher when books ON and the narrator voice instructs verbatim quoting.

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


# ---------------------------------------------------------------------------
# Spotlight helpers — quick diff without reading full reports
# ---------------------------------------------------------------------------

def _verbatim_contexts(report: str, corpus_ngrams: set, n: int = 8,
                       window: int = 15) -> list[dict]:
    """Return each verbatim n-gram match with surrounding normalised-word context."""
    words = _norm_words(report)
    hits, covered = [], -1
    for i in range(len(words) - n + 1):
        if i <= covered:
            continue
        gram = " ".join(words[i:i + n])
        if gram in corpus_ngrams:
            s, e = max(0, i - window), min(len(words), i + n + window)
            hits.append({
                "before": " ".join(words[s:i]),
                "match":  " ".join(words[i:i + n]),
                "after":  " ".join(words[i + n:e]),
            })
            covered = i + n - 1
    return hits


_ATTR_PAT = re.compile(
    r"As [A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)? (?:writes?|wrote|said|observed|noted|puts? it)"
    r"|[A-Z][a-zA-Z]+ (?:writes?|wrote|said|observed|noted)"
    r"|[Ii]n the words of"
    r"|\bthe (?:old )?masters?\b",
    re.IGNORECASE,
)


def _attr_sentences(text: str) -> list[str]:
    """Sentences containing an explicit attribution to a named chess master."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if _ATTR_PAT.search(s)]


def _nearest_move_header(text: str, sentence: str) -> str:
    """Find the nearest ### move header above this sentence in the report."""
    needle = sentence[:50] if len(sentence) >= 50 else sentence
    pos = text.find(needle)
    if pos == -1:
        # case-insensitive fallback (for normalized/lowercased match strings)
        pos = text.lower().find(needle.lower())
    if pos == -1:
        # word-only fallback: first 3 words, tolerates punctuation differences
        words = needle.lower().split()[:3]
        if words:
            pos = text.lower().find(" ".join(words))
    if pos == -1:
        return "(position unknown)"
    headers = re.findall(r"^###\s+(.+)$", text[:pos], re.MULTILINE)
    return headers[-1].strip() if headers else "(opening/narrative)"


def _attr_sentences_with_context(text: str) -> list[tuple[str, str]]:
    """Return (sentence, nearest_move_header) pairs for sentences with master attribution."""
    return [
        (s.strip(), _nearest_move_header(text, s.strip()))
        for s in re.split(r"(?<=[.!?])\s+", text)
        if _ATTR_PAT.search(s)
    ]


def _ply_matched_attr_rows(results: list) -> list:
    """
    Group attribution sentences from all arms by nearest move header (ply-matched).
    Returns [(move_key, {arm_name: sentence})] sorted by move number.
    A move appears once even if only one arm has an attribution there — the other
    arm's cell will be "—", making the non-equivalence visible.
    """
    by_move: dict = {}
    for name, _, text in results:
        for sent, move in _attr_sentences_with_context(text):
            if move not in by_move:
                by_move[move] = {}
            by_move[move][name] = sent

    def _sort_key(item: tuple) -> int:
        m = re.match(r"(\d+)", item[0])
        return int(m.group(1)) if m else 9999

    return sorted(by_move.items(), key=_sort_key)


def _generate_ply_packet(game, tiers: list, out: Path) -> Path:
    """
    Write D_ply_packet.json: per-ply engine analysis for every significant move
    (tier >= 1) in the game. Provides a stable positional reference for anchoring
    report comparisons — both arms were generated from this same analysis data.
    """
    significant = []
    for move, tier in zip(game.moves, tiers):
        if tier < 1:
            continue
        sep = "." if move.side == "White" else "..."
        notation = f"{move.move_number}{sep}{move.san}"
        significant.append({
            "ply": move.ply,
            "notation": notation,
            "full_move": move.move_number,
            "color": move.side.lower(),
            "san": move.san,
            "tier": tier,
            "classification": move.classification,
            "phase": move.phase,
            "cp_loss": move.cp_loss,
            "eval_after_cp": move.eval_after_cp,
            "mate_after": move.mate_after,
        })
    packet = {
        "white": game.headers.get("White", ""),
        "black": game.headers.get("Black", ""),
        "event": game.headers.get("Event", ""),
        "date": game.headers.get("Date", ""),
        "result": game.result,
        "significant_plies": significant,
    }
    path = out / "D_ply_packet.json"
    path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _extract_section(text: str, keyword_re: str) -> str:
    """Extract the first ## section whose heading matches keyword_re."""
    parts = re.split(r"(?m)^(?=##\s)", text)
    for part in parts:
        if part and re.search(keyword_re, part.split("\n")[0], re.IGNORECASE):
            return part.strip()
    return ""


def _move_sections(text: str) -> dict[str, str]:
    """Return {move_key: section_text} for every ### move header in the report."""
    sections: dict[str, str] = {}
    parts = re.split(r"(?m)^(?=###\s+\d)", text)
    for part in parts:
        first_line = part.split("\n")[0]
        m = re.match(r"###\s+(\d+[.…]+\S*)", first_line)
        if m:
            sections[m.group(1)] = part.strip()
    return sections


def _write_spotlight(results: list, corpus_ngrams: set, out: Path, n: int = 8) -> Path:
    """
    Write C_spotlight.md: verbatim hits in context, attribution sentences labelled
    with their move, and closing-section side-by-side.

    Equivalence principle: every comparison row in this file is anchored to the
    same move number or the same named section across all arms. Attribution
    sentences are labelled with their nearest move header so reviewers can verify
    both arms are commenting on the same position.
    """
    lines: list[str] = [
        "# A/B Spotlight\n\n",
        "> **DEVELOPER TOOL** — evaluates the knowledge corpus. "
        "Not part of the shipped Greco product.\n\n",
        "> **Equivalence protocol:** every comparison row is anchored to the same "
        "move number or section heading across all arms. Attribution sentences "
        "are labelled with their move so you can verify both arms cover the same "
        "position before drawing conclusions.\n\n",
    ]

    # 1. Verbatim hits (corpus-ON arm only — baseline arm has none by definition)
    b_name, _, b_text = next(
        (r for r in results if r[0].startswith("B_")), results[-1]
    )
    hits = _verbatim_contexts(b_text, corpus_ngrams, n=n)
    lines.append(f"## Verbatim corpus hits in `{b_name}` ({len(hits)} × {n}-gram)\n\n")
    if hits:
        lines.append(
            "_Each entry: context …**[EXACT MATCH]**… context "
            "(normalised — lowercased, punctuation stripped). "
            "Move header shows which position the match appears in._\n\n"
        )
        for i, h in enumerate(hits, 1):
            move = _nearest_move_header(b_text, h["match"])
            lines.append(
                f"{i}. **[{move}]** …{h['before']} **[{h['match']}]** {h['after']}…\n"
            )
    else:
        lines.append("_(no verbatim matches detected)_\n")

    # 2. Attribution sentences — ply-matched table
    lines.append("\n## Attribution sentences (ply-matched)\n\n")
    lines.append(
        "_Each row is a single move. A dash means that arm added no master "
        "attribution at that position. Both arms were generated from identical "
        "engine analysis, so a dash is a genuine absence, not a different position._\n\n"
    )
    arm_names = [r[0] for r in results]
    col_labels = " | ".join(n.replace("_", " ") for n in arm_names)
    lines.append(f"| Move | {col_labels} |\n")
    lines.append("|---|" + "".join("---|" for _ in arm_names) + "\n")
    attr_rows = _ply_matched_attr_rows(results)
    for move_key, arm_sents in attr_rows:
        cells = []
        for name in arm_names:
            sent = arm_sents.get(name, "—")
            if sent != "—" and len(sent) > 200:
                sent = sent[:197] + "…"
            cells.append(sent.replace("|", "\\|"))
        lines.append("| **" + move_key + "** | " + " | ".join(cells) + " |\n")
    if not attr_rows:
        lines.append("_(no attribution sentences found in either arm)_\n")

    # 3. Closing section — full section from each arm (not cherry-picked bullets)
    closing_kw = r"patterns?|reflection|outro|closing"
    lines.append(
        "## Closing section (full — both arms, same section heading)\n\n"
        "_Showing both sections in full to prevent cherry-picking. Compare bullet "
        "themes across the same numbered position in each arm's list._\n\n"
    )
    for arm_name, _, arm_text in results:
        section = _extract_section(arm_text, closing_kw)
        label = arm_name.replace("_", " ")
        lines.append(f"### {label}\n\n")
        lines.append((section or "_(section not found)_") + "\n\n")

    path = out / "C_spotlight.md"
    path.write_text("".join(lines), encoding="utf-8")
    return path


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

    packet_path = _generate_ply_packet(game, tiers, out)
    print(f"   wrote ply packet: {packet_path}", file=sys.stderr)

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

    # Quick-scan: show WHAT was quoted verbatim and WHERE (which move)
    b_text = next((t for name, _, t in results if name.startswith("B_")), results[-1][2])
    b_hits = _verbatim_contexts(b_text, cn)
    if b_hits:
        print(f"\n--- VERBATIM HITS in corpus-ON arm ({len(b_hits)} × 8-word match) ---")
        for i, h in enumerate(b_hits, 1):
            move = _nearest_move_header(b_text, h["match"])
            print(f"  {i:2d}. [{move}] {h['match']}")
    else:
        print("\n--- VERBATIM HITS: none (model drew from training data only) ---")

    spotlight_path = _write_spotlight(results, cn, out)
    print(f"\nSpotlight (quick diff): {spotlight_path}")
    print("Read C_spotlight.md for a fast comparison; A/B .md files for full evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
