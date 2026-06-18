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
    detect_pin,
    detect_royal_alignment,
    detect_skewer,
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


def is_isolated_pawn(board: chess.Board, square: int, color: bool) -> Tuple[bool, dict]:
    """Certifies an 'isolated pawn': a pawn of `color` with no friendly pawn on either
    in-range adjacent file. Pure pawn-structure arithmetic — enemy pawns, the pawn's rank,
    pin status, and side-to-move are all irrelevant. Edge-file (a/h) pawns need only their
    one in-range neighbour file empty. Recognised sub-attributes in evidence: IQP (d-file),
    isolated doubled, isolated passed.
    """
    piece = board.piece_at(square)
    if piece is None or piece.piece_type != chess.PAWN or piece.color != color:
        return (False, {})

    # One O(≤8) pass: file→count map for friendly pawns only.
    friendly_file_counts: dict = {}
    for sq in board.pieces(chess.PAWN, color):
        f = chess.square_file(sq)
        friendly_file_counts[f] = friendly_file_counts.get(f, 0) + 1
    friendly_files = set(friendly_file_counts)

    file_idx = chess.square_file(square)
    adj = {f for f in (file_idx - 1, file_idx + 1) if 0 <= f <= 7}
    if not adj.isdisjoint(friendly_files):
        return (False, {})

    is_isolani = (file_idx == 3)
    is_passed = is_passed_pawn(board, square, color)
    count = friendly_file_counts.get(file_idx, 1)
    is_doubled = count >= 2
    doubled_squares: list = []
    if is_doubled:
        doubled_squares = sorted(
            chess.square_name(sq)
            for sq in board.pieces(chess.PAWN, color)
            if chess.square_file(sq) == file_idx
        )

    color_str = "White" if color == chess.WHITE else "Black"
    file_letter = chess.FILE_NAMES[file_idx]
    adj_letters = sorted(chess.FILE_NAMES[f] for f in adj)
    adj_str = f"{adj_letters[0]}-file" if len(adj_letters) == 1 else f"{adj_letters[0]}- or {adj_letters[1]}-file"

    evidence_str = (
        f"the {color_str} pawn on {chess.square_name(square)} is isolated — "
        f"no {color_str} pawn stands on the {adj_str} to support it"
    )
    if is_isolani:
        evidence_str += " — an isolated queen-pawn (isolani)"
    if is_doubled:
        evidence_str += (
            f" — isolated doubled pawns on the {file_letter}-file"
            f" ({' and '.join(doubled_squares)})"
        )
    if is_passed:
        evidence_str += " — an isolated passed pawn"

    return (True, {
        "square": chess.square_name(square),
        "color": color_str,
        "file": file_letter,
        "adjacent_files": adj_letters,
        "is_isolani": is_isolani,
        "is_doubled": is_doubled,
        "doubled_squares": doubled_squares,
        "is_passed": is_passed,
        "evidence_str": evidence_str,
    })


def is_doubled_pawn(board: chess.Board, square: int, color: bool) -> Tuple[bool, dict]:
    """Certifies a 'doubled pawn' STATE: the pawn of `color` on `square` shares its file
    with ≥1 other friendly pawn. Pure file-count arithmetic; pin status, side-to-move, and
    enemy pawns are all irrelevant. Evidence carries 'doubled'/'tripled'/'quadrupled' and a
    present-tense STATE sentence (contrast the EVENT field `doubled_pawns_created`).
    """
    piece = board.piece_at(square)
    if piece is None or piece.piece_type != chess.PAWN or piece.color != color:
        return (False, {})
    if len(board.pieces(chess.PAWN, color)) < 2:
        return (False, {})

    file_idx = chess.square_file(square)
    same_file = sorted(
        sq for sq in board.pieces(chess.PAWN, color) if chess.square_file(sq) == file_idx
    )
    count = len(same_file)
    if count < 2:
        return (False, {})

    descriptor = {2: "doubled", 3: "tripled"}.get(count, "quadrupled")
    color_str = "White" if color == chess.WHITE else "Black"
    file_letter = chess.FILE_NAMES[file_idx]
    square_names = [chess.square_name(sq) for sq in same_file]

    if count == 2:
        evidence_str = (
            f"{color_str} has doubled pawns on the {file_letter}-file"
            f" ({square_names[0]} and {square_names[1]})"
        )
    else:
        evidence_str = (
            f"{color_str} has {descriptor} pawns on the {file_letter}-file"
            f" ({', '.join(square_names)})"
        )

    return (True, {
        "color": color_str,
        "square": chess.square_name(square),
        "file": file_letter,
        "file_index": file_idx,
        "pawn_squares": same_file,
        "square_names": square_names,
        "count": count,
        "descriptor": descriptor,
        "evidence_str": evidence_str,
    })


def _king_flights(board: chess.Board, king_sq: int, mover_color: bool) -> set:
    """Survivable king-flight squares from king_sq, with the king removed from that square
    so it cannot shield its own destination from enemy sliders (sole-blocker bug fix)."""
    enemy = not mover_color
    probe = board.copy()
    probe.remove_piece_at(king_sq)
    flights: set = set()
    for s in board.attacks(king_sq):
        if board.piece_at(s) is not None:
            continue
        if probe.is_attacked_by(enemy, s):
            continue
        flights.add(s)
    return flights


def is_luft(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies 'luft': a quiet pawn push on the king's own or adjacent file that newly
    opens a survivable king-flight square. The core gate is the diff of king-flight sets
    before and after the push; the king-removed survivability probe prevents false-safety
    via the sole-blocker edge case (the king cannot shield its own destination from a slider).
    """
    # VETO 1: must be a pawn push, not a promotion
    if move.promotion is not None:
        return (False, None)
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN or piece.color != mover_color:
        return (False, None)

    # VETO 2: king exists
    king_sq = board_after.king(mover_color)
    if king_sq is None:
        return (False, None)
    king_sq_before = board_before.king(mover_color)
    if king_sq_before is None:
        return (False, None)

    # VETO 3: not a capture (covers en passant)
    if board_before.is_capture(move):
        return (False, None)

    # VETO 4: pawn file must be on the king's file or an adjacent file
    if abs(chess.square_file(king_sq) - chess.square_file(move.from_square)) > 1:
        return (False, None)

    # CONFIRM 1: the push newly opens a survivable flight square
    flights_before = _king_flights(board_before, king_sq_before, mover_color)
    flights_after = _king_flights(board_after, king_sq, mover_color)
    new = flights_after - flights_before
    if not new:
        return (False, None)

    # CONFIRM 2 is subsumed by VETO 4 + CONFIRM 1 for all practical positions: any new
    # survivable flight square is king-adjacent and the pawn was on the king's adjacent file.

    was_boxed_in = len(flights_before) == 0
    luft_squares = sorted(new)
    king_sq_name = chess.square_name(king_sq)
    to_name = chess.square_name(move.to_square)
    luft_names = [chess.square_name(s) for s in luft_squares]

    if was_boxed_in:
        evidence = (
            f"{to_name} makes luft for the king on {king_sq_name}, opening "
            f"{', '.join(luft_names)} as an escape square and easing the back-rank threat"
        )
    else:
        evidence = (
            f"{to_name} gives the king on {king_sq_name} a flight square on "
            f"{', '.join(luft_names)}"
        )

    return (True, {
        "king_square": king_sq,
        "king_color": mover_color,
        "pawn_from": move.from_square,
        "pawn_to": move.to_square,
        "luft_squares": luft_squares,
        "was_boxed_in": was_boxed_in,
        "flights_before_count": len(flights_before),
        "relative_pin_on_pawn": board_before.is_pinned(mover_color, move.from_square),
        "evidence": evidence,
    })


def is_back_rank_weak(
    board: chess.Board,
    defending_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies 'back_rank_weakness' for the defending side: king on its first rank with
    no genuine luft, and an enemy rook/queen bearing on or able to reach that rank. Run
    twice per ply (for both colors) in certified_claims. Turn-independent except for the
    in-check abstention guard which uses board.turn.

    The tag certifies the VULNERABILITY, never a forced mate — mate is the eval/mate gate's job.
    """
    D = defending_color
    E = not D
    back_rank = 0 if D == chess.WHITE else 7
    luft_rank = 1 if D == chess.WHITE else 6

    # VETO 1: king must be on its own back rank
    king_sq = board.king(D)
    if king_sq is None or chess.square_rank(king_sq) != back_rank:
        return (False, None)

    # VETO 2: abstain only when it is D's king that is currently in check (live tactical state)
    if board.is_check() and board.turn == D:
        return (False, None)

    # VETO 3: enemy must have at least one rook or queen
    enemy_heavy = board.pieces(chess.ROOK, E) | board.pieces(chess.QUEEN, E)
    if not enemy_heavy:
        return (False, None)

    # VETO 4: every forward escape square blocked or enemy-covered — one genuine escape vetoes
    king_file = chess.square_file(king_sq)
    blocked_escape: list = []
    for f in (f for f in (king_file - 1, king_file, king_file + 1) if 0 <= f <= 7):
        s = chess.square(f, luft_rank)
        occ = board.piece_at(s)
        if occ is not None:
            if occ.color == D and occ.piece_type == chess.PAWN:
                reason = "own pawn"
            elif occ.color == D:
                reason = "own piece"
            else:
                reason = "enemy piece"
        elif board.is_attacked_by(E, s):
            reason = "covered by the enemy"
        else:
            return (False, None)  # genuine luft: king is not back-rank-weak
        blocked_escape.append((s, reason))

    # CONFIRM 5 is implicit: surviving VETO 4 means every escape square is blocked.

    # CONFIRM 6: heavy piece already bearing or reachable via open/half-open file
    heavy_piece_bearing = False
    heavy_pieces: list = []

    for f in range(8):
        back_sq = chess.square(f, back_rank)
        for atk_sq in board.attackers(E, back_sq):
            p = board.piece_at(atk_sq)
            if p is not None and p.piece_type in (chess.ROOK, chess.QUEEN):
                heavy_piece_bearing = True
                if atk_sq not in heavy_pieces:
                    heavy_pieces.append(atk_sq)

    if not heavy_piece_bearing:
        files = file_structure(board)
        e_half_key = "half_open_white" if E == chess.WHITE else "half_open_black"
        for heavy_sq in enemy_heavy:
            fl = chess.FILE_NAMES[chess.square_file(heavy_sq)]
            if fl not in files["open"] and fl not in files[e_half_key]:
                continue
            back_sq = chess.square(chess.square_file(heavy_sq), back_rank)
            between_squares = chess.SquareSet(chess.between(heavy_sq, back_sq))
            if all(board.piece_at(t) is None for t in between_squares):
                if heavy_sq not in heavy_pieces:
                    heavy_pieces.append(heavy_sq)

    # Rule 3 guaranteed a heavy piece exists: certify even when heavy_pieces == []
    # (piece present but blocked path → latent weakness, narrated as "latent").

    # CONFIRM 7: back_rank_defended — flag only, never a veto
    d_heavy = board.pieces(chess.ROOK, D) | board.pieces(chess.QUEEN, D)
    king_attacks = board.attacks(king_sq)
    back_rank_defended = False
    for f in range(8):
        bs = chess.square(f, back_rank)
        if bs == king_sq:
            continue
        if bool(board.attackers(D, bs) & d_heavy):
            back_rank_defended = True
            break
        if bs in king_attacks:
            back_rank_defended = True
            break

    D_str = "White" if D == chess.WHITE else "Black"
    king_sq_name = chess.square_name(king_sq)
    rank_name = "first" if D == chess.WHITE else "eighth"
    blocked_names = [chess.square_name(s) for s, _ in blocked_escape]

    if heavy_piece_bearing and heavy_pieces:
        p0 = board.piece_at(heavy_pieces[0])
        piece_word = "rook" if p0 and p0.piece_type == chess.ROOK else "queen"
        evidence_str = (
            f"{D_str}'s king on {king_sq_name} has no luft — "
            f"{', '.join(blocked_names)} sealed — "
            f"and the enemy {piece_word} on {chess.square_name(heavy_pieces[0])} "
            f"bears on the back rank, a standing back-rank weakness."
        )
    elif back_rank_defended:
        evidence_str = (
            f"{D_str}'s back rank is weak — the king on {king_sq_name} has no flight square — "
            f"though it is currently held by a friendly piece."
        )
    else:
        evidence_str = (
            f"{D_str}'s king on {king_sq_name} is boxed in with no escape square; "
            f"the weakness is latent until a rook reaches the {rank_name} rank."
        )

    return (True, {
        "defending_color": D,
        "king_square": king_sq,
        "blocked_escape_squares": blocked_escape,
        "heavy_pieces": heavy_pieces,
        "heavy_piece_bearing": heavy_piece_bearing,
        "back_rank_defended": back_rank_defended,
        "evidence": evidence_str,
    })


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


def creates_battery(
    board_after: chess.Board, move: chess.Move, mover_color: bool
) -> Tuple[bool, Optional[str]]:
    """Certifies a 'battery': after the move, the moved rook or queen is aligned with
    another rook or queen of the same color on the same file or rank, with no pieces
    between them. Classic examples: doubled rooks on a file, R+Q aiming at the seventh rank.

    The 'nothing between them' check is what prevents certifying a pseudo-battery where a
    pawn or piece blocks the alignment and the pieces are not truly coordinated.
    """
    piece = board_after.piece_at(move.to_square)
    if piece is None or piece.piece_type not in (chess.ROOK, chess.QUEEN):
        return (False, None)

    to_file = chess.square_file(move.to_square)
    to_rank = chess.square_rank(move.to_square)
    _names = {chess.ROOK: "rook", chess.QUEEN: "queen"}
    p1 = _names[piece.piece_type]

    for sq in (board_after.pieces(chess.ROOK, mover_color)
               | board_after.pieces(chess.QUEEN, mover_color)):
        if sq == move.to_square:
            continue
        other = board_after.piece_at(sq)
        if other is None:
            continue
        p2 = _names[other.piece_type]
        sq_file = chess.square_file(sq)
        sq_rank = chess.square_rank(sq)

        if sq_file == to_file:  # same file
            min_r, max_r = sorted((to_rank, sq_rank))
            blocked = any(
                board_after.piece_at(chess.square(to_file, r))
                for r in range(min_r + 1, max_r)
            )
            if not blocked:
                return (True, f"{p1}–{p2} battery on the {chess.FILE_NAMES[to_file]}-file")

        if sq_rank == to_rank:  # same rank
            min_f, max_f = sorted((to_file, sq_file))
            blocked = any(
                board_after.piece_at(chess.square(f, to_rank))
                for f in range(min_f + 1, max_f)
            )
            if not blocked:
                return (True, f"{p1}–{p2} battery on rank {to_rank + 1}")

    return (False, None)


def threatens_promotion(
    board_after: chess.Board, mover_color: bool
) -> Tuple[bool, Optional[str]]:
    """Certifies a 'promotion threat': the mover has a pawn on its seventh rank that
    can advance or capture to promote on the very next move. Checks reachability directly
    (advance to empty square, or diagonal capture of an enemy piece) so a pawn that is
    physically blocked or has nothing to capture is NOT certified as a threat.
    """
    promo_rank = 6 if mover_color == chess.WHITE else 1
    fwd = +1 if mover_color == chess.WHITE else -1

    for sq in board_after.pieces(chess.PAWN, mover_color):
        if chess.square_rank(sq) != promo_rank:
            continue
        sq_file = chess.square_file(sq)
        sq_rank = chess.square_rank(sq)
        promo_sq = chess.square(sq_file, sq_rank + fwd)

        if board_after.piece_at(promo_sq) is None:
            return (True, f"pawn promotion threat on {chess.FILE_NAMES[sq_file]}-file")

        for adj_file in (sq_file - 1, sq_file + 1):
            if not (0 <= adj_file <= 7):
                continue
            cap_sq = chess.square(adj_file, sq_rank + fwd)
            cap = board_after.piece_at(cap_sq)
            if cap is not None and cap.color != mover_color and cap.piece_type != chess.KING:
                return (True, f"pawn promotion threat on {chess.FILE_NAMES[sq_file]}-file (capture)")

    return (False, None)


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


def creates_pin(
    board_after: chess.Board, mover_color: bool
) -> Tuple[bool, Optional[dict]]:
    """Certifies a 'pin': mover's sliding piece pins an enemy piece absolutely (king rear)
    or relatively (front piece less valuable than rear). Wraps analyzer.detect_pin which
    enforces: hanging guard, ray-type gate, clear line, edge-safe rear walk, and
    value/king classifier. Evidence dict is the full bundle from detect_pin."""
    result = detect_pin(board_after, mover_color)
    return (result is not None, result)


def creates_skewer(
    board_after: chess.Board, mover_color: bool
) -> Tuple[bool, Optional[dict]]:
    """Certifies a 'skewer': mover's sliding piece attacks an enemy piece (king or
    higher-value) with a lesser enemy piece directly behind it. Wraps analyzer.detect_skewer
    which enforces: pinned/hanging attacker guard, ray-type gate, edge-clamped rear walk,
    front>back value ordering, and check requirement for the absolute case."""
    result = detect_skewer(board_after, mover_color)
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
    "pin",
    "skewer",
    "rook_lift",
    "outpost",
    "passed_pawn",
    "isolated_pawn",
    "doubled_pawn",
    "luft",
    "back_rank_weakness",
    "mate_in_one_threat",
    "battery",
    "promotion_threat",
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

    pn = _safe(lambda: creates_pin(board_after, mover_color))
    if pn and pn[0]:
        tags.add("pin")

    sk = _safe(lambda: creates_skewer(board_after, mover_color))
    if sk and sk[0]:
        tags.add("skewer")

    op = _safe(lambda: is_outpost(board_after, move.to_square, mover_color))
    if op and op[0]:
        tags.add("outpost")

    if _safe(lambda: is_passed_pawn(board_after, move.to_square, mover_color)):
        tags.add("passed_pawn")

    ip = _safe(lambda: is_isolated_pawn(board_after, move.to_square, mover_color))
    if ip and ip[0]:
        tags.add("isolated_pawn")

    dp = _safe(lambda: is_doubled_pawn(board_after, move.to_square, mover_color))
    if dp and dp[0]:
        tags.add("doubled_pawn")

    lf = _safe(lambda: is_luft(board_before, move, board_after, mover_color))
    if lf and lf[0]:
        tags.add("luft")

    for D in (chess.WHITE, chess.BLACK):
        brw = _safe(lambda D=D: is_back_rank_weak(board_after, D))
        if brw and brw[0]:
            tags.add("back_rank_weakness")

    bt = _safe(lambda: creates_battery(board_after, move, mover_color))
    if bt and bt[0]:
        tags.add("battery")

    pt = _safe(lambda: threatens_promotion(board_after, mover_color))
    if pt and pt[0]:
        tags.add("promotion_threat")

    return tags
