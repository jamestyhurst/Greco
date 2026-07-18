"""
maia.py — Maia (human-vs-engine) integration for Greco.

Stockfish tells Greco the *objectively best* move. Maia is a different kind of
engine: a set of neural-network weights for lc0 (Leela Chess Zero) trained on
millions of real human games, filtered by rating band. Its policy head answers a
different question — "what would a human of rating R actually play here?" — which
is exactly what a strong human commentator weighs when deciding whether a missed
best move was a forgivable "engine move" or a genuine, findable miss.

This module is built in phases (see docs/specs/MAIA_INTEGRATION.md). What lives
here today is the part that needs **no engine binary at all**:

  * `select_band` / `band_for_mover` — rating-band selection (pure arithmetic);
  * `find_weight_bands` / `maia_available` — the availability gate.

The availability gate is the keystone of the feature's safety: lc0 and the Maia
weight files are a manual download (Phase 0), so until they are present
`maia_available()` returns False and the analyzer leaves every Maia field empty —
Greco runs precisely as it does today. The live lc0 wrapper (`query`) and the
analyzer second-pass wiring land in later phases behind this same gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

# --- Rating bands -----------------------------------------------------------
# The publicly trained "Maia-1" nets cover 1100–1900 in 100-point steps; one
# weight file per band (maia-1100.pb.gz … maia-1900.pb.gz). Ratings outside that
# range are clamped to the nearest available band (and the clamp is recorded, so
# the report can stay honest about it — a 2400 is served by the 1900 net, which
# is the strongest human model we have, not a model of a 2400).
DEFAULT_RATING = 1500          # "average club player" — used when the PGN has no usable Elo
MIN_BAND = 1100
MAX_BAND = 1900
BAND_STEP = 100
TRAINED_BANDS = tuple(range(MIN_BAND, MAX_BAND + 1, BAND_STEP))

# --- Engine/weight locations (the manual Phase-0 download lands here) --------
# Kept under the repo so they are reachable by an ASCII-relative path even though
# the absolute path contains the non-ASCII username (C:\Users\詹天哲\...). These
# files are gitignored — binaries/weights never belong in the public repo.
_REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_LC0_PATH = _REPO_ROOT / "engines" / "lc0" / "lc0.exe"
DEFAULT_WEIGHTS_DIR = _REPO_ROOT / "engines" / "maia"

# Maia weight filenames look like "maia-1500.pb.gz" (lc0's gzipped protobuf format).
_BAND_FILE_RE = re.compile(r"^maia-(\d{3,4})\.pb\.gz$", re.IGNORECASE)


@dataclass
class BandSelection:
    """The Maia rating band chosen for one mover, plus the honesty flags the
    narrator needs to hedge correctly."""
    band: int                       # the trained band actually used (always in TRAINED_BANDS)
    clamped: bool                   # True iff the player's level fell outside the trained range
    defaulted: bool                 # True iff there was no usable Elo and DEFAULT_RATING was used
    raw_elo: Optional[int]          # the parsed PGN Elo, or None when defaulted


def _round_to_band(elo: int) -> int:
    """Round an Elo to the nearest 100, with halves going UP, deterministically.

    Why not ``round(elo, -2)``? Python's ``round`` uses banker's rounding
    (round-half-to-even): ``round(1450, -2) == 1400`` but ``round(1550, -2) == 1600``
    — the .5 boundary behaves inconsistently. The ``(elo + 50) // 100`` form sends
    every half up (1450→1500, 1550→1600), which is the predictable behavior we want
    for a band selector. Returns an UNCLAMPED multiple of 100 (caller clamps).
    """
    return int((int(elo) + BAND_STEP // 2) // BAND_STEP) * BAND_STEP


def select_band(elo: int) -> int:
    """Map any Elo to the nearest trained Maia band, clamped to 1100–1900."""
    return max(MIN_BAND, min(MAX_BAND, _round_to_band(elo)))


def _parse_elo(value: Optional[str]) -> Optional[int]:
    """Parse a PGN Elo header defensively. Returns None for absent/malformed
    values ("?", "", whitespace, non-integer) — every untrusted input is parsed
    in a try/except, the project's standing posture."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def band_for_mover(
    headers: Dict[str, str],
    side: str,
    default_rating: int = DEFAULT_RATING,
) -> BandSelection:
    """Choose the Maia band for the player who made a move.

    The *mover's* Elo selects the band: White's moves read ``WhiteElo``, Black's
    read ``BlackElo`` (the two can differ, so each side is served by its own band).
    Missing or malformed Elo falls back to ``default_rating`` with ``defaulted=True``.
    """
    key = "WhiteElo" if side == "White" else "BlackElo"
    raw = _parse_elo(headers.get(key))
    defaulted = raw is None
    elo = default_rating if defaulted else raw
    nearest = _round_to_band(elo)
    band = max(MIN_BAND, min(MAX_BAND, nearest))
    return BandSelection(
        band=band,
        clamped=(band != nearest),   # the rounding wanted to leave the trained range
        defaulted=defaulted,
        raw_elo=(None if defaulted else raw),
    )


def find_weight_bands(weights_dir) -> Dict[int, Path]:
    """Scan a directory for Maia weight files, returning ``{band: path}``.

    Anything not matching ``maia-<digits>.pb.gz`` is ignored. A non-existent
    directory yields an empty mapping (never raises) — the safe default that
    keeps the availability gate fail-closed.
    """
    weights_dir = Path(weights_dir)
    found: Dict[int, Path] = {}
    if not weights_dir.is_dir():
        return found
    for entry in sorted(weights_dir.iterdir()):
        match = _BAND_FILE_RE.match(entry.name)
        if match and entry.is_file():
            found[int(match.group(1))] = entry
    return found


def maia_available(lc0_path=None, weights_dir=None) -> bool:
    """The master gate (``maia_ok``): True only when the lc0 binary AND at least
    one Maia weight file are present. When False, the analyzer skips Maia entirely
    and the report is byte-for-byte what today's Greco produces."""
    lc0_path = Path(lc0_path) if lc0_path is not None else DEFAULT_LC0_PATH
    weights_dir = weights_dir if weights_dir is not None else DEFAULT_WEIGHTS_DIR
    return lc0_path.is_file() and bool(find_weight_bands(weights_dir))


# --- Adaptive node budget (spec §2.1) ---------------------------------------
# Running a deep Maia search on all ~80 plies would roughly double a game's cost,
# so spend lc0 nodes where the human-vs-engine contrast is informative (mistakes,
# only-moves, sacrifices, mate shots) and stay ~free where it isn't (forced
# replies, dead-quiet decided positions). Budgets are deliberately round; tune in
# Phase 6 from the logged `maia_nodes_used`.
NODES_FORCED = 0           # one legal move — nothing to compare
NODES_QUIET_DECIDED = 1    # human and engine agree; record the top human move, no line
NODES_NORMAL_QUIET = 10    # a stable top-3 human distribution, no continuation
NODES_INACCURACY = 100     # was the better move humanly obvious? + a short human line
NODES_MISTAKE = 400        # the core engine_move vs humanly_findable use case
NODES_MATE_RELEVANT = 400  # did a human have a realistic shot at the mate?
NODES_CRITICAL = 800       # only-moves and sacrifices: where humans and engines diverge most

_QUIET_DECIDED_MAX_CPLOSS = 30   # |cp_loss| under which a still-winning move needs no human line
_BIG_SWING_CP = 200              # eval delta across a move that marks a sharp/critical moment


def maia_node_budget(move, tier: int, nodes_override: Optional[int] = None) -> int:
    """How many lc0 nodes to spend on Maia for this ply (the §2.1 adaptive table).

    Reads only facts Greco already computes on ``move`` plus the ``tier`` assigned
    by triage. Duck-typed (``getattr`` with safe defaults) so a partial or odd
    object degrades to "skip / cheap", never raises — a Maia glitch must never
    crash a report.
    """
    # Row 1 — forced: one legal move, no human/engine contrast possible. This wins
    # even over an explicit override (there is genuinely nothing to compare).
    if getattr(move, "is_forced", False):
        return NODES_FORCED

    # A positive override replaces the whole table for every non-forced position
    # (for users who want uniform deep human lines and accept the cost).
    if nodes_override is not None and nodes_override > 0:
        return int(nodes_override)

    classification = getattr(move, "classification", "good")
    cp_loss = getattr(move, "cp_loss", 0) or 0
    eval_before = getattr(move, "eval_before_cp", None)
    eval_after = getattr(move, "eval_after_cp", None)
    mate_relevant = (
        getattr(move, "mate_before", None) is not None
        or getattr(move, "mate_after", None) is not None
    )
    big_swing = (
        eval_before is not None
        and eval_after is not None
        and abs(eval_after - eval_before) >= _BIG_SWING_CP
    )

    # Row 6 — critical / sharp: only-moves, sound sacrifices, a big eval swing, or
    # a tier-3 deep-analysis ply. Spend the most here.
    if (
        getattr(move, "is_only_good_move", False)
        or getattr(move, "is_sacrifice", False)
        or getattr(move, "is_brilliant", False)
        or tier >= 3
        or big_swing
    ):
        return NODES_CRITICAL

    # Row 7 — mate-relevant: a mate score on either side of the move.
    if mate_relevant:
        return NODES_MATE_RELEVANT

    # Row 5 — mistake / blunder: the core labeling use case.
    if classification in ("mistake", "blunder"):
        return NODES_MISTAKE

    # Row 4 — inaccuracy.
    if classification == "inaccuracy":
        return NODES_INACCURACY

    # Row 2 — quiet & already decided: still winning, near-best move, low tier.
    if (
        getattr(move, "still_winning", False)
        and abs(cp_loss) <= _QUIET_DECIDED_MAX_CPLOSS
        and tier <= 1
    ):
        return NODES_QUIET_DECIDED

    # Row 3 — normal quiet: the default.
    return NODES_NORMAL_QUIET
