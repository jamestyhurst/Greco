#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ship.py — one command to publish completed, tested work to GitHub.

Run this when a feature or fix is FINISHED and you have VERIFIED it works. It does
the whole safe release in order and stops at the first problem:

  1. Clean tree    — your tested changes must already be committed (Conventional
                     Commits). ship.py never commits your edits for you; it only
                     releases what is already committed.
  2. Tests         — runs the pytest suite (or, if pytest/tests are absent, an
                     import smoke test of the core modules) so broken code never
                     reaches GitHub (--skip-tests to bypass).
  3. Secret scan   — refuses to push if config.json is tracked or a real API-key
                     pattern appears in the commits about to be pushed.
  4. Version bump  — runs scripts/bump_version.py --apply (computes the next
                     4-digit version from the commits since the last tag, writes
                     version.py, commits the release, tags it). No-ops cleanly if
                     there were only docs/chore commits.
  5. Push          — git push + git push --tags.

It does NOT touch Notion: after ship.py succeeds, add a Greco Dev Log entry
(that step needs the Notion tool, not a local script — see CLAUDE.md).

Deliberately pure standard library — no pip installs, and nothing scheduled or
backgrounded (those trip this machine's antivirus). You run it, on demand, when
the work is proven functional.

Usage:
    python scripts/ship.py            # full release + push
    python scripts/ship.py --dry-run  # show what would happen; no commit/tag/push
    python scripts/ship.py --skip-tests
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENV_PY = REPO / "venv" / "Scripts" / "python.exe"
BUMP = REPO / "scripts" / "bump_version.py"
# Core modules that must import cleanly before anything ships.
SMOKE_MODULES = ["version", "importers", "analyzer", "triage", "narrator", "outputs", "gui", "web.main"]
# A real Anthropic key; placeholders ("sk-ant-REPLACE-...") do not match.
KEY_RE = re.compile(r"sk-ant-api03-[A-Za-z0-9_-]{20,}")


def py() -> str:
    """The interpreter to run Greco code with — the venv if present, else this one."""
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _has_module(mod: str) -> bool:
    return subprocess.run([py(), "-c", f"import {mod}"], cwd=REPO, capture_output=True).returncode == 0


def git(*args: str, check: bool = True, capture: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, text=True, encoding="utf-8", capture_output=capture)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr or r.stdout}")
    return (r.stdout or "").strip()


def fail(msg: str) -> None:
    sys.exit(f"\nSHIP ABORTED: {msg}")


def step(n: int, msg: str) -> None:
    print(f"[{n}/5] {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish completed, tested work to GitHub.")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen; no release/push")
    ap.add_argument("--skip-tests", action="store_true", help="skip the import smoke test")
    args = ap.parse_args()
    # Flush each line immediately so our step lines stay in order with the
    # output of the git/bump subprocesses we shell out to.
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        fail("detached HEAD — check out a branch first.")

    # 1) Clean tree.
    step(1, "Checking the working tree is clean...")
    if git("status", "--porcelain"):
        fail("uncommitted changes. Commit your tested work (Conventional Commits) first, then ship.")
    print("      clean.")

    # 2) Prove it works: run the pytest suite if present, else fall back to an
    #    import smoke test (catches a broken import at minimum).
    if args.skip_tests:
        step(2, "Tests SKIPPED (--skip-tests).")
    elif (REPO / "tests").is_dir() and _has_module("pytest"):
        step(2, "Running the test suite (pytest)...")
        if subprocess.run([py(), "-m", "pytest", "-q"], cwd=REPO,
                          env={**os.environ, "PYTHONUTF8": "1"}).returncode != 0:
            fail("tests failed — fix before shipping.")
    else:
        step(2, "Smoke-importing core modules...")
        code = "import importlib,sys;[importlib.import_module(m) for m in sys.argv[1:]];print('imports OK')"
        r = subprocess.run([py(), "-c", code, *SMOKE_MODULES], cwd=REPO, text=True,
                           capture_output=True, env={**os.environ, "PYTHONUTF8": "1"})
        if r.returncode != 0:
            fail("core modules do not import — fix before shipping:\n" + (r.stderr or r.stdout))
        print("      " + (r.stdout.strip() or "imports OK"))

    # 2b) Optional verify gate: deterministic contradiction check against saved
    #     fixture files (no API key or Stockfish needed). If the fixtures aren't
    #     present this is a no-op; when they are, a deterministic contradiction
    #     blocks the ship just like a failing test.
    if not args.skip_tests:
        _fx_analysis = REPO / "tests" / "fixtures" / "sample_analysis.json"
        _fx_report = REPO / "tests" / "fixtures" / "sample_report.md"
        if _fx_analysis.is_file() and _fx_report.is_file():
            print("      verify gate: checking saved fixtures for contradictions...")
            _vr = subprocess.run(
                [py(), str(REPO / "tools" / "verify_report.py"),
                 "--analysis", str(_fx_analysis),
                 "--report", str(_fx_report),
                 "--no-llm"],
                cwd=REPO,
                env={**os.environ, "PYTHONUTF8": "1"},
            )
            if _vr.returncode != 0:
                fail("verify_report found deterministic contradictions in the saved fixtures — "
                     "fix the narrator, then re-run ship.py.")
            print("      verify gate: OK — no contradictions in saved fixtures.")

    # 3) Secret scan — ironclad; the repo is public.
    step(3, "Scanning for secrets...")
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "config.json"],
                             cwd=REPO, capture_output=True, text=True)
    if tracked.returncode == 0:
        fail("config.json is TRACKED — it must stay gitignored. Run: git rm --cached config.json")
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    diff_range = f"{upstream}..HEAD" if upstream else "HEAD"
    if KEY_RE.search(git("diff", diff_range, check=False)):
        fail("a real API-key pattern appears in the commits about to be pushed. STOP and rotate the key.")
    print("      config.json untracked; no key in the outgoing diff.")

    if args.dry_run:
        print("\n--- DRY RUN: would bump the version, then push main + tags. Computed bump: ---")
        subprocess.run([py(), str(BUMP)], cwd=REPO)
        return

    # 4) Version bump + tag.
    step(4, "Computing + applying the version bump...")
    before = git("describe", "--tags", "--abbrev=0", check=False)
    subprocess.run([py(), str(BUMP), "--apply"], cwd=REPO, check=True)
    after = git("describe", "--tags", "--abbrev=0", check=False)

    # 5) Push.
    step(5, "Pushing to GitHub...")
    git("push", "origin", branch, capture=False)
    git("push", "origin", "--tags", capture=False)

    print("\nShipped.")
    if after and after != before:
        print(f"  New release: {after}")
    else:
        print("  Pushed commits (no version-affecting changes since the last tag — no new tag).")
    print("  Next: add a Greco Dev Log entry in Notion (see CLAUDE.md §Versioning, commits & GitHub sync).")


if __name__ == "__main__":
    main()
