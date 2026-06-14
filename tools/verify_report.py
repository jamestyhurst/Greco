#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_report.py — the Layer-2 self-test gate for a finished Greco report.

Given a SAVED ANALYSIS JSON (produced by `main.py --save-analysis`) and the report's
Markdown, it runs the DETERMINISTIC contradiction checks (engine-free, no API key) and,
when an API key is present and --no-llm is not set, the ADVISORY LLM judge.

Exit-code contract (the CI gate):
  * a DETERMINISTIC contradiction  -> exit 1   (fails a build / "let it cook" loop)
  * the LLM judge                  -> ADVISORY  (printed, never changes the exit code)
So the gate is fully functional in CI with no key; the judge is purely additive.

Usage:
  python tools/verify_report.py --analysis run.json --report "report.md"
  python tools/verify_report.py --analysis run.json --report report.md --no-llm
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running as `python tools/verify_report.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer import GameAnalysis, MoveAnalysis  # noqa: E402
import factcheck  # noqa: E402


def _load_analysis(path: Path):
    """Reconstruct (GameAnalysis, tiers) from a --save-analysis JSON payload."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        moves = [MoveAnalysis(**m) for m in payload["moves"]]
    except TypeError as exc:
        sys.exit(
            f"Saved-analysis JSON does not match the current MoveAnalysis schema "
            f"({exc}). Regenerate it with `main.py --save-analysis` on this version."
        )
    game = GameAnalysis(
        headers=payload.get("headers", {}),
        moves=moves,
        result=payload.get("result", "*"),
        final_eval_cp=payload.get("final_eval_cp"),
        final_mate=payload.get("final_mate"),
    )
    return game, payload.get("tiers", [1] * len(moves))


def _print(findings, label):
    if not findings:
        print(f"  {label}: none")
        return
    print(f"  {label}: {len(findings)} finding(s)")
    for f in findings:
        ref = f.move_ref or "(unbound)"
        conf = f" conf={f.confidence}" if f.check == "llm-judge" else ""
        print(f"    - [{f.check}{conf}] {ref}: {f.claim}")
        print(f"        contradicts: {f.contradicted_fact}")
        if f.snippet and f.snippet != f.claim:
            print(f"        in: \"{f.snippet.strip()[:160]}\"")


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify a Greco report against its engine facts.")
    ap.add_argument("--analysis", required=True, type=Path, help="saved-analysis JSON (main.py --save-analysis)")
    ap.add_argument("--report", required=True, type=Path, help="the report .md to check")
    ap.add_argument("--no-llm", action="store_true", help="skip the advisory LLM judge")
    ap.add_argument("--judge-model", default="claude-opus-4-8", help="model for the LLM judge")
    ap.add_argument("--json", type=Path, help="also write all findings to this JSON file")
    args = ap.parse_args()

    game, tiers = _load_analysis(args.analysis)
    report_md = args.report.read_text(encoding="utf-8")

    print(f"Verifying {args.report.name} ({len(game.moves)} moves)...")
    deterministic = factcheck.run_deterministic_checks(game, tiers, report_md)
    _print(deterministic, "deterministic checks")

    key = None
    advisory = []
    if not args.no_llm:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            # Fall back to the gitignored local config (never printed).
            cfg = Path(__file__).resolve().parent.parent / "config.json"
            if cfg.is_file():
                try:
                    key = json.loads(cfg.read_text(encoding="utf-8")).get("api_key")
                except Exception:
                    key = None
        if key:
            print("  running advisory LLM judge...")
            try:
                advisory = factcheck.run_llm_judge(game, tiers, report_md, model=args.judge_model, api_key=key)
                _print(advisory, "LLM judge (advisory)")
            except Exception:
                # Advisory only: never let a judge failure change the exit code.
                advisory = []
                print("  LLM judge: unavailable (advisory, skipped)")
        else:
            print("  LLM judge: skipped (no API key)")

    if args.json:
        args.json.write_text(json.dumps(
            {"deterministic": [vars(f) for f in deterministic],
             "advisory": [vars(f) for f in advisory]}, indent=2), encoding="utf-8")

    # Only deterministic contradictions gate the build; the judge is advisory.
    if deterministic:
        print(f"\nFAIL: {len(deterministic)} deterministic contradiction(s).")
        sys.exit(1)
    print("\nOK: no deterministic contradictions." +
          ("" if args.no_llm or not key else f" ({len(advisory)} advisory judge note(s).)"))


if __name__ == "__main__":
    main()
