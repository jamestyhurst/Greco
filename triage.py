"""
Decide how much commentary each move deserves.

Returns a list of integer tiers (0–3) parallel to game.moves:

  Tier 0 — minimal acknowledgement only (forced moves, deep opening theory).
  Tier 1 — one or two sentences (normal good moves, captures, castling).
  Tier 2 — paragraph-length strategic note (inaccuracies, eval swings,
           phase transitions, "only good move" finds).
  Tier 3 — deep dive (mistakes, blunders, brilliancies, near-mate moments).
"""

from __future__ import annotations

from typing import Dict, List

from analyzer import GameAnalysis, MoveAnalysis, normalize_cp


BASE_BY_CLASSIFICATION: Dict[str, int] = {
    "forced": 0,
    "best": 1,
    "good": 1,
    "inaccuracy": 2,
    "mistake": 3,
    "blunder": 3,
}


def _detect_turning_points(game: GameAnalysis, threshold_cp: int = 200) -> List[int]:
    """Plies after which the evaluation swung by at least `threshold_cp`."""
    turning_points: List[int] = []
    # Seed from the actual starting evaluation (eval_before of ply 1) rather than a
    # literal 0, so a game starting from a non-standard FEN (handicap / puzzle) does
    # not spuriously flag ply 1 as a turning point.
    prev = (
        normalize_cp(game.moves[0].eval_before_cp, game.moves[0].mate_before)
        if game.moves
        else 0
    )
    for move in game.moves:
        current = normalize_cp(move.eval_after_cp, move.mate_after)
        if abs(current - prev) >= threshold_cp:
            turning_points.append(move.ply)
        prev = current
    return turning_points


def _tier_for_move(
    move: MoveAnalysis,
    user_context: Dict[str, object],
) -> int:
    if move.is_forced:
        return 0

    tier = BASE_BY_CLASSIFICATION.get(move.classification, 1)

    # Deep opening theory: the first several moves of a normal-looking opening
    # usually don't reward verbose commentary even when the engine prefers something else.
    if (
        move.phase == "opening"
        and move.cp_loss < 20
        and not move.is_capture
        and move.ply <= 12
    ):
        tier = min(tier, 1)

    # Castling and meaningful captures usually deserve at least a mention.
    if move.is_castle:
        tier = max(tier, 1)
    if move.is_capture and move.ply > 8:
        tier = max(tier, 1)

    # A check that wasn't the engine's pick is an interesting choice.
    if move.is_check and move.classification not in ("best", "forced"):
        tier = max(tier, 2)

    # "Only good move" finds (large gap to second best) are notable when the player found them.
    if move.is_only_good_move and move.classification in ("best", "good"):
        tier = max(tier, 2)

    # Sacrifices are the heart of human chess interest — a sound sacrifice is a
    # skill indicator and always deserves real commentary; a brilliancy gets the
    # deepest treatment.
    if move.is_brilliant:
        tier = 3
    elif move.is_sacrifice:
        tier = max(tier, 2)
    # A move that creates a real fork / double attack is worth a close look too.
    if move.double_attack:
        tier = max(tier, 2)

    # Player context boost — if a real player is named, lean into psychology
    # around their errors and surprising decisions.
    if user_context.get("player_named") and move.classification in (
        "inaccuracy",
        "mistake",
        "blunder",
    ):
        tier = min(3, tier + 1)

    # Promotions are dramatic.
    if move.is_promotion:
        tier = max(tier, 2)

    return tier


def _has_named_players(headers: Dict[str, str]) -> bool:
    """True when the PGN carries real player names (not blank, '?', or the
    placeholder 'White'/'Black' strings)."""
    for key in ("White", "Black"):
        name = (headers.get(key) or "").strip()
        if name and name not in ("?", "White", "Black"):
            return True
    return False


def annotate_with_tiers(
    game: GameAnalysis,
    user_context: Dict[str, object],
) -> List[int]:
    # Decouple "a real human name is present" from "free-text bio context was
    # supplied". The psychology tier-boost should fire for the user's own named
    # games (run from the GUI/web), not only CLI runs that passed --white-context.
    # The GUI and web front-ends hardcode player_named=False, so upgrade it here
    # from the PGN headers — one place that fixes all three front-ends consistently.
    if not user_context.get("player_named") and _has_named_players(game.headers):
        user_context = {**user_context, "player_named": True}

    turning_plies = set(_detect_turning_points(game))
    tiers: List[int] = []
    prev_phase = None
    total = len(game.moves)

    for move in game.moves:
        tier = _tier_for_move(move, user_context)

        # Phase transition: bump tier so the narrator can mark the moment.
        if prev_phase is not None and prev_phase != move.phase:
            tier = max(tier, 2)

        # Turning points override low tiers.
        if move.ply in turning_plies:
            tier = max(tier, 2)

        # The very first move (opening choice) and the very last move (result) always get at least Tier 1.
        if move.ply == 1 or move.ply == total:
            tier = max(tier, 1)

        # Approaching mate is dramatic.
        if move.mate_after is not None and abs(move.mate_after) <= 3:
            tier = max(tier, 2)
        if move.mate_after is not None and abs(move.mate_after) <= 1:
            tier = max(tier, 3)

        tiers.append(tier)
        prev_phase = move.phase

    return tiers


def tier_distribution(tiers: List[int]) -> Dict[int, int]:
    dist = {0: 0, 1: 0, 2: 0, 3: 0}
    for t in tiers:
        dist[t] = dist.get(t, 0) + 1
    return dist
