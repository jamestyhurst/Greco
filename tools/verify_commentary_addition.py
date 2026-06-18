#!/usr/bin/env python
"""Post-deposit verification tool for a single commentary_refs addition.

Run this after adding a new commentary folder (transcript + meta.json) to get
immediate feedback before committing.

Usage:
    python tools/verify_commentary_addition.py <folder-slug>
    python tools/verify_commentary_addition.py --all     # check every folder

The automated test suite (tests/test_commentary.py) runs these checks on
every pytest run — this script gives per-folder output faster.

What constitutes a complete commentary folder:
  commentary_refs/<slug>/
    transcript.txt       required — the real, fetched words (not a placeholder)
    meta.json            required — title, commentator, video_id, channel_verified,
                                    source_url, games_in_order (list), notes (str)
    NN White vs Black (Event Year).pgn  optional, one per game in video order

How to add a new commentary folder in an automated session:
  1. Identify the video ID and confirm the channel (@SammyChess1 or @agadmator).
  2. In Claude-in-Chrome: navigate to
         https://youtubetotranscript.com/transcript?v=<VIDEO_ID>
     Wait ~6 s for Cloudflare to auto-clear, then call get_page_text.
     Verify: the 'Author' header on the page matches the expected channel.
  3. Clean the transcript (remove site chrome, stitch any split sentences).
  4. Run this script with --scaffold to create the folder and stub files:
         python tools/verify_commentary_addition.py --scaffold \\
             --slug <slug> --video-id <ID> --commentator "Agadmator" \\
             --title "Kasparov vs Topalov 1999"
  5. Write the cleaned transcript to commentary_refs/<slug>/transcript.txt.
  6. For each game in the video: fetch the verified PGN from chessgames.com
     at https://www.chessgames.com/njs/api/game/viewPGN/<GID> and save it
     as commentary_refs/<slug>/NN White vs Black (Event Year).pgn.
  7. Update meta.json with games_in_order and any caption-garble notes.
  8. Run: python tools/verify_commentary_addition.py <slug>
  9. Run: pytest tests/test_commentary.py -v
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFS_DIR = ROOT / "commentary_refs"

PASS = "  [PASS]"
FAIL = "  [FAIL]"
WARN = "  [WARN]"

REQUIRED_META_FIELDS = {"title", "commentator", "video_id", "channel_verified"}
APPROVED_COMMENTATORS = {"sammychess", "agadmator"}


def _check_folder(slug: str) -> int:
    """Check one commentary folder. Returns number of failures."""
    folder = REFS_DIR / slug
    print(f"\n── {slug} ──")
    failures = 0

    if not folder.exists():
        print(f"{FAIL} Folder not found: {folder}")
        return 1

    # 1. transcript.txt
    transcript_path = folder / "transcript.txt"
    if not transcript_path.exists():
        print(f"{FAIL} transcript.txt missing")
        failures += 1
    else:
        text = transcript_path.read_text(encoding="utf-8").strip()
        if text.upper().startswith("PLACEHOLDER"):
            print(f"{FAIL} transcript.txt is a PLACEHOLDER — fetch the real transcript")
            failures += 1
        elif len(text) < 200:
            print(f"{FAIL} transcript.txt is only {len(text)} chars — looks like a stub")
            failures += 1
        else:
            words = len(text.split())
            print(f"{PASS} transcript.txt  ({words:,} words)")

    # 2. meta.json
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        print(f"{FAIL} meta.json missing")
        failures += 1
    else:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"{FAIL} meta.json parse error: {exc}")
            return failures + 1
        missing = REQUIRED_META_FIELDS - meta.keys()
        if missing:
            print(f"{FAIL} meta.json missing required fields: {missing}")
            failures += 1
        else:
            print(f"{PASS} meta.json  (commentator: {meta.get('commentator')!r})")

        # 3. Commentator must be approved
        commentator = meta.get("commentator", "").lower()
        if not any(a in commentator for a in APPROVED_COMMENTATORS):
            print(f"{FAIL} Commentator '{meta.get('commentator')}' is not in the approved "
                  "pool. Per WORKFLOW.md: only SammyChess and Agadmator are used for "
                  "style references. Prefix folder with '_' if experimenting.")
            failures += 1

        # 4. channel_verified should be True
        if not meta.get("channel_verified"):
            print(f"{WARN} channel_verified is falsy — confirm the transcript Author "
                  "header matches the expected channel before committing.")

        # 5. games_in_order (optional but encouraged)
        games = meta.get("games_in_order", [])
        pgns = sorted(folder.glob("*.pgn"))
        if games:
            print(f"{PASS} games_in_order  ({len(games)} game(s) listed)")
        else:
            print(f"  [NOTE] No games_in_order in meta.json. "
                  "Add a list of games once PGNs are verified.")

        # 6. PGN count should match games list
        if games and pgns:
            expected = len(games)
            actual = len(pgns)
            if actual < expected:
                print(f"{WARN} {actual} PGN file(s) but {expected} game(s) listed — "
                      f"{expected - actual} PGN(s) still needed.")
            else:
                print(f"{PASS} PGN files  ({actual} file(s) match games list)")

    return failures


def _scaffold(slug: str, video_id: str, commentator: str, title: str) -> None:
    """Create the folder scaffold for a new commentary addition."""
    folder = REFS_DIR / slug
    folder.mkdir(parents=True, exist_ok=True)

    transcript_path = folder / "transcript.txt"
    if not transcript_path.exists():
        transcript_path.write_text("PLACEHOLDER — paste the cleaned transcript here.\n",
                                   encoding="utf-8")
        print(f"  Created: {transcript_path.relative_to(ROOT)}")

    meta_path = folder / "meta.json"
    if not meta_path.exists():
        meta = {
            "title": title,
            "commentator": commentator,
            "video_id": video_id,
            "source_url": f"https://www.youtube.com/watch?v={video_id}",
            "channel_verified": False,
            "games_in_order": [],
            "notes": ""
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        print(f"  Created: {meta_path.relative_to(ROOT)}")

    print(f"\nScaffold created at commentary_refs/{slug}/")
    print("Next steps:")
    print(f"  1. In Claude-in-Chrome: navigate to "
          f"https://youtubetotranscript.com/transcript?v={video_id}")
    print("     Wait ~6 s for Cloudflare, then call get_page_text.")
    print(f"     Verify 'Author' header matches the channel for {commentator!r}.")
    print(f"  2. Write the cleaned transcript to {transcript_path.relative_to(ROOT)}")
    print("  3. Add verified PGNs (see WORKFLOW.md §C for chessgames.com method).")
    print("  4. Update meta.json: set channel_verified=true and fill games_in_order.")
    print(f"  5. python tools/verify_commentary_addition.py {slug}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify a commentary_refs addition.")
    ap.add_argument("slug", nargs="?", help="Folder slug to check")
    ap.add_argument("--all", action="store_true", help="Check every folder")
    ap.add_argument("--scaffold", action="store_true",
                    help="Create a new scaffold instead of checking")
    ap.add_argument("--video-id", help="YouTube video ID (for --scaffold)")
    ap.add_argument("--commentator", help="Commentator name (for --scaffold)")
    ap.add_argument("--title", help="Video title (for --scaffold)")
    args = ap.parse_args()

    if args.scaffold:
        if not all([args.slug, args.video_id, args.commentator, args.title]):
            print("--scaffold requires --slug, --video-id, --commentator, and --title")
            sys.exit(1)
        _scaffold(args.slug, args.video_id, args.commentator, args.title)
        return

    if not args.slug and not args.all:
        ap.print_help()
        sys.exit(1)

    if args.all:
        if not REFS_DIR.is_dir():
            print(f"commentary_refs/ not found at {REFS_DIR}")
            sys.exit(1)
        slugs = [
            sub.name for sub in sorted(REFS_DIR.iterdir())
            if sub.is_dir() and not sub.name.startswith(("_", "."))
        ]
    else:
        slugs = [args.slug]

    total = 0
    for slug in slugs:
        total += _check_folder(slug)

    print()
    if total == 0:
        print(f"All checks passed for {len(slugs)} folder(s).")
    else:
        print(f"{total} check(s) FAILED across {len(slugs)} folder(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
