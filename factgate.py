"""
factgate.py — the Output Fact-Gate predicate library.

WHY THIS EXISTS (the core engineering problem of Greco)
    Greco's narrator is an LLM. Left to itself it will *derive* board facts and get
    them wrong ("the king moved onto the g-file" when it was already there), or
    confabulate a reason a move is bad to fit the engine's verdict. Greco's whole
    architecture exists to stop that: a deterministic layer supplies ground truth and
    the model only narrates from supplied facts. The INPUT side already has a hard
    gate (python-chess legal-move replay). This module is the start of the symmetric
    OUTPUT gate James designed: compute, for each move, the SET of claims the engine
    can actually PROVE — the "allow-set" — and let the narrator assert only those.

HOW IT WORKS (James's doctrine, made literal)
    Each claim the narrator might make becomes a CODE PREDICATE that CERTIFIES it from
    the board alone, in two stages: a cheap necessary-condition VETO (bail the instant
    the claim is impossible), then a fuller CONFIRM. `certified_claims()` runs every
    predicate for one move and returns the set of proven claim TAGS — the per-ply
    allow-set, serialised into the fact packet (`narrator._move_to_dict` -> d["certified"])
    and enforced by one rule in the system prompt.

    Predicates for tactics the analyzer ALREADY detects (fork, royal pin/skewer, open
    file) are THIN WRAPPERS over the analyzer's detectors, so the allow-set can never
    drift from the facts the analyzer already serialises. Geometric claims the analyzer
    doesn't expose as booleans (rook lift, outpost, passed pawn, mate-in-one threat)
    are implemented here.

    The library is PURE and ENGINE-FREE: every function takes a python-chess Board /
    FEN, never Stockfish or the network — so the whole module and its tests run in CI
    with no engine binary and no API key (the L1 half of the testing doctrine). It is
    also a WHITELIST, not a blacklist: the absence of a tag means "not machine-proven",
    NOT "false" — so the system-prompt rule is scoped to exactly the claim types here.
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

import chess

from analyzer import (  # pure board helpers — none touch Stockfish or the API key
    detect_double_attack,
    detect_royal_alignment,
    file_structure,
)


# --------------------------------------------------------------------------- #
# Position predicates (board + square/colour). Pure, freely composable.
# --------------------------------------------------------------------------- #
def threatens_mate_in_one(board: chess.Board) -> bool:
    """True if the SIDE TO MOVE has a legal move that delivers checkmate.

    Cheap veto: a move that does not give check can never be mate, and `gives_check`
    is far cheaper than pushing — so we only push the checking moves.
    """
    if board.is_game_over():
        return False
    for move in board.legal_moves:
        if not board.gives_check(move):
            continue
        board.push(move)
        mated = board.is_checkmate()
        board.pop()
        if mated:
            return True
    return False


def is_rook_lift(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board
) -> Tuple[bool, Optional[str]]:
    """The doctrine's worked example. Certifies a 'rook lift': a rook moved quietly
    OFF a home rank UP the board (Rd1-d3 style) toward an open/half-open file or the
    enemy king. The from/to forward-rank-change check is what kills the "already on
    the file/rank" hallucination class — a piece that didn't change rank is not lifting.
    """
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK:
        return (False, None)
    color = piece.color
    if board_before.is_capture(move):
        return (False, None)  # a lift is a quiet repositioning, not a capture
    from_rank = chess.square_rank(move.from_square)
    to_rank = chess.square_rank(move.to_square)
    if color == chess.WHITE:
        if to_rank <= from_rank:
            return (False, None)  # must move forward (up the board)
        if from_rank not in (0, 1):
            return (False, None)  # must start on a home rank (1st/2nd)
    else:
        if to_rank >= from_rank:
            return (False, None)
        if from_rank not in (6, 7):
            return (False, None)
    # Confirm purpose via the analyzer's own file definition (single source of truth).
    files = file_structure(board_after)
    to_file = chess.square_file(move.to_square)
    letter = chess.FILE_NAMES[to_file]
    half_key = "half_open_white" if color == chess.WHITE else "half_open_black"
    if letter in files["open"]:
        return (True, f"rook lift to the open {letter}-file")
    if letter in files[half_key]:
        return (True, f"rook lift to the half-open {letter}-file")
    opp = not color
    king_sq = board_after.king(opp)
    if king_sq is not None and (
        chess.square_file(king_sq) == to_file
        or chess.square_rank(king_sq) == to_rank
    ):
        return (True, "rook lift aiming at the enemy king")
    return (False, None)


def is_outpost(
    board: chess.Board, square: int, color: bool
) -> Tuple[bool, List[int]]:
    """Certifies an 'outpost': a friendly KNIGHT/BISHOP on an advanced square that is
    defended by a friendly pawn AND can never be challenged by an enemy pawn. Returns
    the supporting pawn square(s) as evidence. The 'unchallengeable' half is what
    separates a real outpost from a merely advanced minor.
    """
    piece = board.piece_at(square)
    if piece is None or piece.color != color or piece.piece_type not in (chess.KNIGHT, chess.BISHOP):
        return (False, [])
    rank = chess.square_rank(square)
    if color == chess.WHITE:
        if rank not in (3, 4, 5):  # ranks 4-6
            return (False, [])
    else:
        if rank not in (2, 3, 4):  # ranks 5-3
            return (False, [])
    supporters = [
        s for s in board.attackers(color, square)
        if (board.piece_at(s) and board.piece_at(s).piece_type == chess.PAWN)
    ]
    if not supporters:
        return (False, [])
    # Unchallengeable: no enemy pawn on an adjacent file can ever advance to attack it.
    file_idx = chess.square_file(square)
    enemy = not color
    for adj in (file_idx - 1, file_idx + 1):
        if not (0 <= adj <= 7):
            continue
        for sq in board.pieces(chess.PAWN, enemy):
            if chess.square_file(sq) != adj:
                continue
            r = chess.square_rank(sq)
            # An enemy pawn can challenge only if it is still BEHIND the outpost from
            # its own advancing direction (so it can reach a square attacking it).
            if color == chess.WHITE and r >= rank + 1:
                return (False, [])
            if color == chess.BLACK and r <= rank - 1:
                return (False, [])
    return (True, supporters)


def is_passed_pawn(board: chess.Board, square: int, color: bool) -> bool:
    """Certifies a 'passed pawn': a pawn of `color` with no enemy pawn ahead of it on
    its own file or either adjacent file (the standard definition). Pure square
    arithmetic; a same-file blocker ahead disqualifies it (it cannot promote)."""
    piece = board.piece_at(square)
    if piece is None or piece.color != color or piece.piece_type != chess.PAWN:
        return False
    file_idx = chess.square_file(square)
    rank = chess.square_rank(square)
    enemy = not color
    files = {f for f in (file_idx - 1, file_idx, file_idx + 1) if 0 <= f <= 7}
    for sq in board.pieces(chess.PAWN, enemy):
        if chess.square_file(sq) not in files:
            continue
        r = chess.square_rank(sq)
        if color == chess.WHITE and r > rank:
            return False
        if color == chess.BLACK and r < rank:
            return False
    return True


def file_state(board: chess.Board, file_index: int, color: bool) -> str:
    """'open_file' / 'half_open_file' / '' for a file, delegating to the analyzer's
    file_structure so 'open'/'half-open' mean EXACTLY what the fact packet already says."""
    if not (0 <= file_index <= 7):
        return ""
    files = file_structure(board)
    letter = chess.FILE_NAMES[file_index]
    if letter in files["open"]:
        return "open_file"
    half_key = "half_open_white" if color == chess.WHITE else "half_open_black"
    if letter in files[half_key]:
        return "half_open_file"
    return ""


# --------------------------------------------------------------------------- #
# Thin wrappers over analyzer detectors — so the allow-set never drifts from the
# fact packet's own double_attack / tactic_setup fields.
# --------------------------------------------------------------------------- #
def creates_fork(
    board_after: chess.Board, landing_square: int, mover_color: bool
) -> Tuple[bool, Optional[str]]:
    """Certifies a 'fork'/double attack from the piece on `landing_square`. Wraps
    analyzer.detect_double_attack (which already rejects pinned/hanging forkers)."""
    result = detect_double_attack(board_after, landing_square, mover_color)
    return (result is not None, result)


def sets_up_royal_pin(
    board: chess.Board, mover_color: bool
) -> Tuple[bool, Optional[str]]:
    """Certifies a 'pin/skewer that wins the queen'. Wraps analyzer.detect_royal_alignment
    (which already requires a clear line and a non-hanging pinner)."""
    result = detect_royal_alignment(board, mover_color)
    return (result is not None, result)


# --------------------------------------------------------------------------- #
# The allow-set builder — THE per-ply gate.
# --------------------------------------------------------------------------- #
# Exactly the claim types this gate covers. The system-prompt rule is scoped to
# these tags so it never suppresses legitimate prose about facts that have their own
# packet fields (doubled pawns, overloaded defenders, etc.).
GATED_TAGS = (
    "fork",
    "royal_pin_setup",
    "rook_lift",
    "outpost",
    "passed_pawn",
    "mate_in_one_threat",
)
# (Open / half-open files are NOT gated here: they already have their own ground-truth
# packet fields — open_files / half_open_for_white / half_open_for_black — and a
# dedicated system-prompt rule. Adding them to the allow-set would be dead payload.)


def certified_claims(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Set[str]:
    """Run every predicate for one ply and return the set of proven claim TAGS — the
    per-ply allow-set. Each predicate self-vetoes cheaply, so a quiet move costs only
    the vetoes and returns the empty set. Every call is wrapped so the gate can never
    crash the report (same fail-safe posture as outputs.find_unverified_variation_moves).

    `mate_in_one_threat` semantics: certified when, from the position AFTER the move
    (opponent to move), the MOVER would have a mate-in-one if the opponent did nothing
    — i.e. the mover threatens immediate mate. Evaluated via a null move so it is the
    mover's threat, not the opponent's.
    """
    tags: Set[str] = set()

    def _safe(fn):
        try:
            return fn()
        except Exception:
            return None

    def _mate_threat() -> bool:
        # The mover-threatens-mate framing (opponent "passes") is only well-defined
        # when the opponent is FREE to make a non-forced move. If the move gave check,
        # the opponent is forced to respond and the null-move probe would certify a
        # standing threat the forced reply actually refutes — so abstain under check.
        if board_after.is_game_over() or board_after.is_check():
            return False
        probe = board_after.copy()
        probe.push(chess.Move.null())  # opponent "passes" -> now it is the mover's turn
        return threatens_mate_in_one(probe)

    if _safe(_mate_threat):
        tags.add("mate_in_one_threat")

    rl = _safe(lambda: is_rook_lift(board_before, move, board_after))
    if rl and rl[0]:
        tags.add("rook_lift")

    fk = _safe(lambda: creates_fork(board_after, move.to_square, mover_color))
    if fk and fk[0]:
        tags.add("fork")

    rp = _safe(lambda: sets_up_royal_pin(board_after, mover_color))
    if rp and rp[0]:
        tags.add("royal_pin_setup")

    op = _safe(lambda: is_outpost(board_after, move.to_square, mover_color))
    if op and op[0]:
        tags.add("outpost")

    if _safe(lambda: is_passed_pawn(board_after, move.to_square, mover_color)):
        tags.add("passed_pawn")

    return tags
