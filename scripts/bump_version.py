#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bump_version.py — compute Greco's next version number from the Git history.

Greco uses 4-digit versioning  MAJOR.MINOR.PATCH.MICRO  (trailing zeros omitted,
so 0.3.1.0 is written "0.3.1"). This script reads the Conventional-Commit messages
since the last version tag, decides which digit to bump, and — with --apply —
writes the new number into version.py, commits that one-line change, and creates a
matching git tag.

Which digit gets bumped (the highest-priority commit since the last tag wins):

    commit subject / marker        ->  digit bumped
    ---------------------------------------------------------
    "type!:"  or  "BREAKING CHANGE" in the body   ->  MAJOR   (resets the rest to 0)
    release:                                       ->  MINOR   (resets PATCH, MICRO)
    feat:                                          ->  PATCH   (resets MICRO)
    fix:                                           ->  PATCH   (resets MICRO)
    micro:                                         ->  MICRO   (+1)
    docs / refactor / test / chore / anything else ->  no change

Use "release:" deliberately when a batch of recent "feat:" commits adds up to a
meaningful product milestone (completing a phase, shipping a named feature set).
Individual features and fixes use "feat:" / "fix:" and produce PATCH bumps.

Usage:
    python scripts/bump_version.py            # DRY RUN — just shows what it would do
    python scripts/bump_version.py --apply    # writes version.py, commits, and tags

--apply refuses to run on a dirty working tree, so the release commit it creates
contains nothing but the version bump itself. After it runs, push with:
    git push && git push --tags

Why pure standard library (no pip installs, no git-cliff): this machine's antivirus
flags tools that download/install software, so the version automation deliberately
needs nothing beyond Python and git, both already present.

LEARNING NOTE (for James): this is a tiny "parser + state machine." It turns each
commit message into a number (classify), takes the maximum (the biggest change in
the batch decides the release), then applies a rule table to compute the next
version. Same shape as the triage tiers in triage.py — derive a decision from facts
via explicit rules, never guesswork.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO / "version.py"

# Bump levels, ordered. Higher number = bigger change.
NONE, MICRO, PATCH, MINOR, MAJOR = 0, 1, 2, 3, 4
LEVEL_NAME = {NONE: "none", MICRO: "MICRO", PATCH: "PATCH", MINOR: "MINOR", MAJOR: "MAJOR"}
TYPE_LEVEL = {"release": MINOR, "feat": PATCH, "fix": PATCH, "micro": MICRO}

# Matches a Conventional-Commit prefix: "type:", "type(scope):", or "type!:".
_TYPE_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<bang>!)?:")


def git(*args: str) -> str:
    """Run a git command in the repo and return its stripped stdout."""
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip()


def read_version() -> tuple[int, int, int, int]:
    text = VERSION_FILE.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*["\']([0-9.]+)["\']', text)
    if not m:
        sys.exit("Could not find __version__ in version.py")
    parts = [int(p) for p in m.group(1).split(".")] + [0, 0, 0, 0]
    return tuple(parts[:4])  # type: ignore[return-value]


def format_version(v: tuple[int, int, int, int]) -> str:
    major, minor, patch, micro = v
    return f"{major}.{minor}.{patch}.{micro}" if micro else f"{major}.{minor}.{patch}"


def commits_since_last_tag() -> tuple[str | None, list[tuple[str, str]]]:
    last_tag = git("describe", "--tags", "--abbrev=0")  # "" when there are no tags
    rng = f"{last_tag}..HEAD" if last_tag else "HEAD"
    # \x1f separates subject from body; \x1e separates commits.
    raw = git("log", rng, "--format=%s%x1f%b%x1e")
    commits: list[tuple[str, str]] = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        subject, _, body = record.partition("\x1f")
        commits.append((subject.strip(), body.strip()))
    return (last_tag or None), commits


def classify(subject: str, body: str) -> int:
    if "BREAKING CHANGE" in subject or "BREAKING CHANGE" in body:
        return MAJOR
    m = _TYPE_RE.match(subject)
    if not m:
        return NONE
    if m.group("bang"):
        return MAJOR
    return TYPE_LEVEL.get(m.group("type").lower(), NONE)


def apply_bump(v: tuple[int, int, int, int], level: int) -> tuple[int, int, int, int]:
    major, minor, patch, micro = v
    if level == MAJOR:
        return (major + 1, 0, 0, 0)
    if level == MINOR:
        return (major, minor + 1, 0, 0)
    if level == PATCH:
        return (major, minor, patch + 1, 0)
    if level == MICRO:
        return (major, minor, patch, micro + 1)
    return v


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    ap = argparse.ArgumentParser(description="Bump Greco's version from Conventional Commits.")
    ap.add_argument("--apply", action="store_true", help="write version.py, commit, and tag")
    args = ap.parse_args()

    current = read_version()
    last_tag, commits = commits_since_last_tag()

    if not commits:
        print(f"No commits since {last_tag or 'the start of history'} — nothing to bump.")
        print(f"Current version: {format_version(current)}")
        return

    level = max((classify(s, b) for s, b in commits), default=NONE)
    new = apply_bump(current, level)

    print(f"Since tag:          {last_tag or '(none — scanning all history)'}")
    print(f"Commits considered: {len(commits)}")
    for s, b in commits:
        print(f"  [{LEVEL_NAME[classify(s, b)]:>5}] {s}")
    print(f"\nHighest bump:    {LEVEL_NAME[level]}")
    print(f"Current version: {format_version(current)}")

    if level == NONE:
        print("No version-affecting commits (only docs/refactor/test/chore). Version unchanged.")
        return

    new_str = format_version(new)
    print(f"Next version:    {new_str}")

    if not args.apply:
        print("\n(DRY RUN — re-run with --apply to write version.py, commit, and tag.)")
        return

    # --apply: insist on a clean tree so the release commit is ONLY the version bump.
    if git("status", "--porcelain"):
        sys.exit("Working tree is not clean. Commit or stash your changes first, then re-run --apply.")

    # Edit in place via bytes so the file's existing line endings are preserved.
    # (read_text/write_text would rewrite LF as CRLF on Windows and churn the whole file.)
    src = VERSION_FILE.read_bytes().decode("utf-8")
    src = re.sub(r'(__version__\s*=\s*["\'])[0-9.]+(["\'])', rf"\g<1>{new_str}\g<2>", src)
    VERSION_FILE.write_bytes(src.encode("utf-8"))
    git("add", "version.py")
    subprocess.run(["git", "commit", "-m", f"chore: release v{new_str}"], cwd=REPO, check=True)
    subprocess.run(["git", "tag", f"v{new_str}"], cwd=REPO, check=True)
    print(f"\nReleased v{new_str}: version.py updated, committed, and tagged.")
    print("Now push it:  git push && git push --tags")


if __name__ == "__main__":
    main()
