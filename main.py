"""
Greco — chess analysis with engine evaluation and AI narration.

Pipeline:
  PGN source (file / URL / inline) → importers.py
       → analyzer.py     (Stockfish per-position evaluation)
       → triage.py       (commentary tier assignment)
       → narrator.py     (Claude narrative + psychology)
       → outputs.py      (assemble Markdown with move list + boards + eval graph)
       → optional HTML via outputs.markdown_to_html
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from analyzer import analyze_pgn
from importers import load_pgn
from narrator import generate_narrative
from outputs import assemble_report, markdown_to_html
from triage import annotate_with_tiers, tier_distribution


BANNER = r"""
   _____
  / ____|
 | |  __  _ __  ___  ___  ___
 | | |_ || '__|/ _ \/ __|/ _ \
 | |__| || |  |  __/ (__| (_) |
  \_____||_|   \___|\___|\___/
                       chess engine + AI narrator
"""


USE_CASE_DESCRIPTIONS = {
    "companion": "warm friend sharing the game with you",
    "coaching":  "diagnostic focus on your decision-making; ends with 'patterns to work on'",
    "commentary": "YouTube-style video script with [SCENE BREAK] markers",
}


def _progress_printer(done: int, total: int) -> None:
    bar_width = 30
    filled = int(bar_width * done / total)
    bar = "#" * filled + "-" * (bar_width - filled)
    sys.stderr.write(f"\r  engine [{bar}] {done}/{total}")
    sys.stderr.flush()
    if done == total:
        sys.stderr.write("\n")


def _prompt_use_case() -> str:
    sys.stderr.write("\nWhat is this analysis for?\n")
    options = list(USE_CASE_DESCRIPTIONS.items())
    for i, (key, desc) in enumerate(options, start=1):
        sys.stderr.write(f"  {i}. {key} — {desc}\n")
    sys.stderr.write("Pick 1, 2, or 3 [default 1]: ")
    sys.stderr.flush()
    try:
        choice = input().strip()
    except EOFError:
        return "companion"
    if not choice:
        return "companion"
    if choice in ("1", "2", "3"):
        return options[int(choice) - 1][0]
    if choice in USE_CASE_DESCRIPTIONS:
        return choice
    sys.stderr.write(f"Didn't understand '{choice}', defaulting to companion.\n")
    return "companion"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="greco",
        description=(
            "Greco — analyze a chess game by combining Stockfish engine evaluation "
            "with Claude's narrative writing and psychological commentary."
        ),
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--pgn-file", type=str, help="Path to a PGN file")
    src.add_argument("--pgn", type=str, help="PGN text passed directly")
    src.add_argument("--pgn-url", type=str, help="Lichess URL or game ID (chess.com not yet supported)")
    src.add_argument("--source", type=str, help="Auto-detected source: file path, Lichess URL/ID, or raw PGN text")

    parser.add_argument(
        "--white-context",
        type=str,
        default=None,
        help="Free-form context about the White player (e.g. 'world #1 known for endgame technique')",
    )
    parser.add_argument(
        "--black-context",
        type=str,
        default=None,
        help="Free-form context about the Black player",
    )
    parser.add_argument(
        "--user-is",
        choices=["white", "black", "neither"],
        default="neither",
        help="If the user themselves played as one side, name it for first-person commentary",
    )
    parser.add_argument(
        "--use-case",
        choices=["companion", "coaching", "commentary"],
        default=None,
        help=(
            "Voice of the report. If not given, Greco will ask interactively. "
            "companion = friend sharing the game; coaching = diagnostic; commentary = video script."
        ),
    )
    parser.add_argument(
        "--user-note",
        type=str,
        default=None,
        help="A personal note about the game (e.g. 'I'm proud of the queen sacrifice'). Greco will respond to it directly.",
    )

    # Engine settings.
    parser.add_argument(
        "--engine",
        type=str,
        default=os.environ.get("STOCKFISH_PATH"),
        help="Path to the Stockfish binary (or set STOCKFISH_PATH)",
    )
    parser.add_argument("--depth", type=int, default=18, help="Engine search depth (default 18)")
    parser.add_argument(
        "--time-per-move",
        type=float,
        default=None,
        help="Seconds of engine time per position (overrides --depth)",
    )
    parser.add_argument("--multipv", type=int, default=3, help="Top N moves to consider (default 3)")

    # Claude settings.
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-6",
        help="Claude model to use (default claude-sonnet-4-6; try claude-opus-4-7 for richer prose)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16000,
        help="Max output tokens for the narrative (default 16000 — long games with many notable moves need the headroom)",
    )

    # Output settings.
    parser.add_argument("--output", type=Path, default=None, help="Write Markdown to this file (also creates a sibling _assets/ folder)")
    parser.add_argument(
        "--format",
        choices=["md", "html", "both"],
        default="both",
        help=(
            "Output format (default both). 'html' is self-contained: every board "
            "and the eval graph is embedded directly in the file — no links to "
            "open, and you can print it to PDF from your browser (Ctrl+P)."
        ),
    )
    parser.add_argument(
        "--boards-at",
        choices=["off", "tier3", "tier2", "all"],
        default="tier3",
        help="Insert board diagrams for moves at the chosen tier and above (default tier3)",
    )
    parser.add_argument(
        "--no-eval-graph",
        action="store_true",
        help="Skip the eval-graph PNG",
    )
    parser.add_argument(
        "--save-analysis",
        type=Path,
        default=None,
        help="Optional path to dump the raw engine analysis as JSON (useful for debugging)",
    )

    # Text-to-speech (Windows built-in voice; no extra install).
    parser.add_argument(
        "--speak",
        action="store_true",
        help="Read the narrative aloud when finished (Windows voice).",
    )
    parser.add_argument(
        "--audio",
        type=Path,
        default=None,
        help="Save the spoken narrative to a .wav file at this path.",
    )
    parser.add_argument(
        "--voice-rate",
        type=int,
        default=0,
        help="Speech rate from -10 (slow) to 10 (fast). Default 0.",
    )

    args = parser.parse_args()

    # Choose a source.
    source_string = args.source or args.pgn_file or args.pgn_url or args.pgn
    if not source_string:
        parser.error("Provide --pgn-file, --pgn-url, --pgn, or --source")
    if not args.engine:
        parser.error("Stockfish path required: pass --engine or set STOCKFISH_PATH")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("ANTHROPIC_API_KEY environment variable is not set")

    print(BANNER, file=sys.stderr)

    pgn_text, source_desc = load_pgn(source_string)
    print(f"Loaded PGN from {source_desc}", file=sys.stderr)

    # Resolve use_case (interactive prompt if not given).
    use_case = args.use_case
    if use_case is None:
        if sys.stdin.isatty():
            use_case = _prompt_use_case()
        else:
            use_case = "companion"

    flipped_for_black = args.user_is == "black"

    user_context = {
        "white_player": args.white_context,
        "black_player": args.black_context,
        "user_is": args.user_is,
        "player_named": bool(args.white_context or args.black_context),
    }

    print("Analyzing positions with Stockfish...", file=sys.stderr)
    game = analyze_pgn(
        pgn_text,
        engine_path=args.engine,
        depth=args.depth,
        multipv=args.multipv,
        time_limit=args.time_per_move,
        progress_cb=_progress_printer,
    )
    print(f"Analyzed {len(game.moves)} moves.", file=sys.stderr)

    print("Assigning commentary tiers...", file=sys.stderr)
    tiers = annotate_with_tiers(game, user_context)
    dist = tier_distribution(tiers)
    print(
        f"  tier distribution: 0={dist[0]}  1={dist[1]}  2={dist[2]}  3={dist[3]}",
        file=sys.stderr,
    )

    if args.save_analysis:
        import dataclasses
        import json
        payload = {
            "headers": game.headers,
            "result": game.result,
            "final_eval_cp": game.final_eval_cp,
            "final_mate": game.final_mate,
            "moves": [dataclasses.asdict(m) for m in game.moves],
            "tiers": tiers,
        }
        args.save_analysis.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  wrote raw analysis to {args.save_analysis}", file=sys.stderr)

    print(
        f"Generating narrative with {args.model} in '{use_case}' voice... (streaming live)\n",
        file=sys.stderr,
    )
    # If the source was a local file, pass its path so the narrator can recover
    # player names from the filename when the PGN headers lack them (feature 5).
    from pathlib import Path as _Path
    try:
        source_path = source_string if _Path(source_string).is_file() else None
    except OSError:
        source_path = None
    narrative = generate_narrative(
        game,
        tiers,
        user_context,
        model=args.model,
        max_tokens=args.max_tokens,
        live_stream_to=sys.stderr,
        use_case=use_case,
        user_note=args.user_note,
        source_path=source_path,
        boards_at=args.boards_at,
    )

    # Text-to-speech (works whether or not a report file is written).
    if args.speak or args.audio:
        try:
            from tts import save_audio, speak_text, to_speakable_text

            spoken = to_speakable_text(narrative)
            if args.audio:
                wav = save_audio(spoken, args.audio, rate=args.voice_rate)
                size_mb = wav.stat().st_size / (1024 * 1024)
                print(f"Wrote audio narration to {wav} ({size_mb:.1f} MB)", file=sys.stderr)
            if args.speak:
                print("Reading the narrative aloud...", file=sys.stderr)
                speak_text(spoken, rate=args.voice_rate)
        except Exception as exc:  # never let TTS failure sink the whole run
            print(f"(Text-to-speech failed: {exc})", file=sys.stderr)

    if not args.output:
        # No output path: just print the narrative to stdout.
        print(narrative)
        return 0

    md_path = assemble_report(
        game,
        tiers,
        narrative,
        output_md=args.output,
        boards_at=args.boards_at,
        render_eval_graph=not args.no_eval_graph,
        flipped_for_black=flipped_for_black,
    )
    print(f"Wrote Markdown report to {md_path}", file=sys.stderr)

    if args.format in ("html", "both"):
        html_path = markdown_to_html(md_path, game=game, flipped=flipped_for_black)
        print(f"Wrote HTML report to {html_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
