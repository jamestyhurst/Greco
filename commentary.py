"""
Commentary style references — teach Greco's narrator GOOD COMMENTARY CRAFT by
showing it transcripts of real human commentators.

Why this is safe (and consistent with Greco's core principle):
    Greco's foundational rule is "data-back, never prompt-stuff" — every board
    fact comes from the engine, never from prose. These transcripts are about
    OTHER games, so they must influence VOICE ONLY (pacing, phrasing, how to
    build tension and explain a position), never facts. The loader below labels
    them explicitly as style-only and the narrator's system prompt repeats the
    rule, so the model learns the craft without importing any chess claims.

Folder layout (greco/commentary_refs/):
    <slug>/
        transcript.txt   (required)  — the commentator's words
        game.pgn         (optional)  — the game being commented (for context only)
        meta.json        (optional)  — {"title", "commentator", "source_url", "notes"}

Folders whose name starts with '_' or '.' are ignored (e.g. _example/), as are
transcripts shorter than ~200 characters (templates/stubs).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Tuple

REFS_DIR = Path(__file__).resolve().parent / "commentary_refs"

# Author-written house-voice spec (an explicit style guide, distinct from the
# transcript examples). This is the most reliable, tunable lever on the voice.
STYLE_GUIDE_PATH = REFS_DIR / "GRECO_STYLE.md"

_MIN_TRANSCRIPT_CHARS = 200


def load_style_guide(max_chars: int = 12000) -> str:
    """Return the Greco house-voice style guide (commentary_refs/GRECO_STYLE.md),
    wrapped for the system prompt, or '' if it is missing/empty.

    Unlike the transcript references (which the model must learn from indirectly),
    this is an explicit, author-controlled instruction set — so it is the most
    reliable and verifiable way to steer Greco's voice."""
    try:
        text = STYLE_GUIDE_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n…(style guide truncated)"
    return (
        "## Greco house voice — AUTHORITATIVE STYLE SPEC\n"
        "This is the definitive guide to how your commentary should sound; follow it "
        "closely. It governs VOICE ONLY — pacing, tone, structure, when to get excited. "
        "Every chess FACT (evaluations, best moves, threats, who is winning) still comes "
        "solely from the engine ground-truth in the user message; never take a claim from "
        "any style source.\n\n" + text
    )


def _pgn_label(pgn_path: Path) -> str:
    """A short 'White vs Black — Event' label from a PGN's tags (context only)."""
    try:
        text = pgn_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    def tag(name: str) -> str:
        m = re.search(rf'\[{name}\s+"([^"]*)"\]', text)
        return m.group(1) if m else ""

    white, black, event = tag("White"), tag("Black"), tag("Event")
    bits: List[str] = []
    if white or black:
        bits.append(f"{white or '?'} vs {black or '?'}")
    if event and event != "?":
        bits.append(event)
    return " — ".join(bits)


def _collect(max_refs: int, max_chars_each: int) -> List[Tuple[str, str, str, str]]:
    """Return [(title, commentator, game_label, transcript), ...] for valid refs."""
    if not REFS_DIR.is_dir():
        return []
    out: List[Tuple[str, str, str, str]] = []
    for sub in sorted(REFS_DIR.iterdir()):
        if not sub.is_dir() or sub.name.startswith(("_", ".")):
            continue
        tpath = sub / "transcript.txt"
        if not tpath.is_file():
            continue
        try:
            transcript = tpath.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            continue
        if len(transcript) < _MIN_TRANSCRIPT_CHARS:
            continue  # template / stub
        if transcript.upper().startswith("PLACEHOLDER"):
            continue  # unfilled scaffold (e.g. a fetch_transcript.py stub not yet filled)

        title, commentator = sub.name, ""
        meta = sub / "meta.json"
        if meta.is_file():
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
                title = m.get("title") or title
                commentator = m.get("commentator") or ""
            except Exception:
                pass

        # One subfolder per video; it may hold several PGNs named in the order
        # the games appear in the video (e.g. "01 White vs Black.pgn"). Sorted
        # by filename so the numeric prefixes preserve presentation order.
        pgn_paths = sorted(sub.glob("*.pgn"))
        labels = [lab for lab in (_pgn_label(p) for p in pgn_paths) if lab]
        if len(labels) == 1:
            game_label = labels[0]
        elif len(labels) > 1:
            game_label = "%d games, in presentation order: %s" % (
                len(labels), "; ".join(labels)
            )
        else:
            game_label = ""

        out.append((title, commentator, game_label, transcript[:max_chars_each]))
        if len(out) >= max_refs:
            break
    return out


def load_commentary_references(
    max_refs: int = 3, max_chars_each: int = 5000, max_total_chars: int = 12000
) -> str:
    """Build a system-prompt section of style exemplars, or '' if none exist.

    Returns a block that is safe to append to the narrator's system prompt: it
    frames the transcripts as STYLE-ONLY references for different games and
    forbids importing any facts from them.
    """
    entries = _collect(max_refs, max_chars_each)
    if not entries:
        return ""

    blocks: List[str] = []
    total = 0
    for title, commentator, game_label, transcript in entries:
        head_bits = [f'Reference: "{title}"']
        if commentator:
            head_bits.append(f"commentator: {commentator}")
        if game_label:
            head_bits.append(
                f"this is commentary on a DIFFERENT game ({game_label}) — not the one you are analyzing"
            )
        head = " — ".join(head_bits)
        block = f"{head}\n\"\"\"\n{transcript}\n\"\"\""
        if total + len(block) > max_total_chars:
            break
        blocks.append(block)
        total += len(block)

    if not blocks:
        return ""

    joined = "\n\n".join(blocks)
    return (
        "## Learning from real chess commentators (STYLE REFERENCE ONLY)\n"
        "Below are transcripts of human commentators narrating chess games. Study them to "
        "sharpen your *craft*: how a strong commentator builds tension, paces an explanation, "
        "varies sentence length, shifts between calm storytelling and excitement, addresses the "
        "viewer, and makes a position vivid and easy to follow. Absorb the rhythm and instincts, "
        "then apply them through whichever voice your voice-addendum specifies.\n\n"
        "**ABSOLUTE RULE — these transcripts are about DIFFERENT games, not the one you are "
        "analyzing.** Learn only their voice and technique. Take NO chess facts, moves, "
        "evaluations, player names, openings, or claims from them. Every fact about the current "
        "game comes solely from the engine ground-truth data in the user message. Never quote a "
        "commentator verbatim, and never reproduce any factual error one of them happens to make.\n\n"
        f"{joined}"
    )


if __name__ == "__main__":
    # Quick manual check: print what would be injected (or a note if empty).
    block = load_commentary_references()
    if block:
        print(block[:2000])
        print(f"\n... [total {len(block)} chars]")
    else:
        print(f"(No commentary references found in {REFS_DIR})")
