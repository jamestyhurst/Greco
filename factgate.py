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

import re
from typing import List, Optional, Set, Tuple

import chess

from analyzer import (  # pure board helpers — none touch Stockfish or the API key
    PIECE_NAMES,
    detect_discovered_attack,
    detect_double_attack,
    detect_overloaded_defender_full,
    detect_pin,
    detect_royal_alignment,
    detect_skewer,
    file_structure,
    normalize_cp,
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
    # Unchallengeable: no enemy pawn can ever advance to attack the outpost square.
    if not is_hole(board, square, not color):
        return (False, [])
    return (True, supporters)


def is_hole(board: chess.Board, square: int, defender_color: bool) -> bool:
    """True when `defender_color` has no pawn that can ever attack `square`.
    A square is a permanent 'hole' for a color when they cannot defend it with pawns.
    Extracted from is_outpost's unchallengeable check so both functions share one source.
    """
    file_idx = chess.square_file(square)
    rank = chess.square_rank(square)
    for adj in (file_idx - 1, file_idx + 1):
        if not (0 <= adj <= 7):
            continue
        for pawn_sq in board.pieces(chess.PAWN, defender_color):
            if chess.square_file(pawn_sq) != adj:
                continue
            pr = chess.square_rank(pawn_sq)
            # White pawn at pr attacks pr+1; can reach the square if pr <= rank-1
            if defender_color == chess.WHITE and pr <= rank - 1:
                return False
            # Black pawn at pr attacks pr-1; can reach the square if pr >= rank+1
            if defender_color == chess.BLACK and pr >= rank + 1:
                return False
    return True


def outpost_evidence(board: chess.Board, square: int, color: bool) -> Optional[dict]:
    """Companion to is_outpost: builds a ready-to-quote evidence bundle for narrator
    use when is_outpost certifies, or returns None. Does not change is_outpost's
    own return shape — certified_claims continues to call is_outpost directly.
    """
    ok, supporters = is_outpost(board, square, color)
    if not ok:
        return None
    piece = board.piece_at(square)
    if piece is None:
        return None
    square_nm = chess.square_name(square)
    piece_name = PIECE_NAMES[piece.piece_type]
    supporter_names = [chess.square_name(s) for s in supporters]
    color_name = "White" if color == chess.WHITE else "Black"
    if len(supporter_names) == 1:
        evidence = (
            f"the {color_name} {piece_name} on {square_nm} is an outpost — "
            f"defended by the pawn on {supporter_names[0]} "
            f"and immune to any enemy pawn challenge"
        )
    else:
        all_but_last = ", ".join(supporter_names[:-1])
        evidence = (
            f"the {color_name} {piece_name} on {square_nm} is an outpost — "
            f"defended by the pawns on {all_but_last} and {supporter_names[-1]} "
            f"and immune to any enemy pawn challenge"
        )
    return {
        "is_outpost": True,
        "supporters": supporters,
        "square": square,
        "square_name": square_nm,
        "piece_name": piece_name,
        "supporter_names": supporter_names,
        "color_name": color_name,
        "evidence": evidence,
    }


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


def is_backward_pawn(
    board: chess.Board, square: int, color: bool
) -> Tuple[bool, Optional[dict]]:
    """Certifies a 'backward pawn': the pawn on `square` of `color` is rear-most relative
    to its adjacent-file neighbors, its one-step advance (stop square) is enemy-pawn-controlled,
    and no friendly pawn can be brought up to defend that advance. Pure structural geometry;
    turn- and pin-independent. Returns (True, evidence_dict) on success, (False, None) on veto.
    """
    # VETO 1: must be a pawn of the correct color (also rejects promoted pieces)
    piece = board.piece_at(square)
    if piece is None or piece.piece_type != chess.PAWN or piece.color != color:
        return (False, None)

    enemy = not color
    f = chess.square_file(square)
    r = chess.square_rank(square)
    fwd = 1 if color == chess.WHITE else -1
    home_rank = 1 if color == chess.WHITE else 6

    # VETO 2: stop square must exist on-board (promotion rank → no stop square)
    if (color == chess.WHITE and r == 7) or (color == chess.BLACK and r == 0):
        return (False, None)
    stop_sq = chess.square(f, r + fwd)

    def _epc(sq: int) -> bool:
        """True if any enemy pawn geometrically attacks sq (turn/pin-independent)."""
        for a in board.attackers(enemy, sq):
            p = board.piece_at(a)
            if p is not None and p.piece_type == chess.PAWN:
                return True
        return False

    adj_files = [af for af in (f - 1, f + 1) if 0 <= af <= 7]
    adj_file_set = set(adj_files)

    # VETO 4a: not isolated — at least one adjacent file has a friendly pawn
    friendly_pawn_files = {chess.square_file(sq) for sq in board.pieces(chess.PAWN, color)}
    if not any(af in friendly_pawn_files for af in adj_files):
        return (False, None)

    # Classify each neighbor pawn as strictly-ahead or behind-or-level
    advanced: List[int] = []
    behind_or_level: List[Tuple[int, int, int]] = []  # (adj_f, rn, nb_sq)

    for nb_sq in board.pieces(chess.PAWN, color):
        af = chess.square_file(nb_sq)
        if af not in adj_file_set:
            continue
        rn = chess.square_rank(nb_sq)
        if (color == chess.WHITE and rn > r) or (color == chess.BLACK and rn < r):
            advanced.append(nb_sq)
        else:
            behind_or_level.append((af, rn, nb_sq))

    # VETO 4b: at least one neighbor must be strictly ahead (non-vacuous "fallen behind")
    if not advanced:
        return (False, None)

    # VETO 3: no behind-or-level neighbor can reach its support square.
    # The support square for file af is chess.square(af, r + fwd) — the square BESIDE
    # the stop square (adjacent file, same rank as the stop square), where a connected
    # pawn marching alongside the candidate would stand. Only TWO paths can reach it
    # in one "action": a single step by a LEVEL neighbor (rn == r, advances one square
    # to r+fwd), or a home-rank double-step when the candidate is exactly one forward
    # step ahead of the neighbor's home rank (r == home_rank + fwd), so the double
    # step from home_rank lands on r+fwd = support square.
    fixed_level_neighbors: List[int] = []

    for af, rn, nb_sq in behind_or_level:
        sup_sq = chess.square(af, r + fwd)
        can_support = False

        # Single step: only a level neighbor (rn == r) can reach sup_sq in one step
        if rn == r:
            if board.piece_at(sup_sq) is None and not _epc(sup_sq):
                can_support = True

        # Double step from home rank: leaps to sup_sq when r == home_rank + fwd
        if not can_support and rn == home_rank and r == home_rank + fwd:
            inter_sq = chess.square(af, rn + fwd)
            if (board.piece_at(inter_sq) is None
                    and board.piece_at(sup_sq) is None
                    and not _epc(sup_sq)):
                can_support = True

        if can_support:
            return (False, None)
        fixed_level_neighbors.append(nb_sq)

    # CONFIRM 1: stop square is attacked by an enemy pawn (the structural fixative)
    pawn_controllers = [
        a for a in board.attackers(enemy, stop_sq)
        if board.piece_at(a) is not None and board.piece_at(a).piece_type == chess.PAWN
    ]
    if not pawn_controllers:
        return (False, None)

    # CONFIRM 1b: home-rank escape via double-step (replaces the naive home-rank veto)
    if r == home_rank:
        leap_sq = chess.square(f, r + 2 * fwd)
        leap_controlled = any(
            board.piece_at(a) is not None and board.piece_at(a).piece_type == chess.PAWN
            for a in board.attackers(enemy, leap_sq)
        )
        if (board.piece_at(stop_sq) is None
                and board.piece_at(leap_sq) is None
                and not leap_controlled):
            return (False, None)

    # CONFIRM 3: not a passed pawn (anti-false-positive; provably unreachable after CONFIRM 1)
    if is_passed_pawn(board, square, color):
        return (False, None)

    # --- All checks passed — build the evidence bundle ---
    file_letter = chess.FILE_NAMES[f]

    # Subtype: blocked > half_open > closed
    stop_occ = board.piece_at(stop_sq)
    if stop_occ is not None and stop_occ.piece_type == chess.PAWN and stop_occ.color == enemy:
        subtype = "blocked"
    else:
        ahead_on_f = any(
            chess.square_file(sq) == f and (
                (color == chess.WHITE and chess.square_rank(sq) > r) or
                (color == chess.BLACK and chess.square_rank(sq) < r)
            )
            for sq in board.pieces(chess.PAWN, enemy)
        )
        subtype = "half_open" if not ahead_on_f else "closed"

    is_blocked = (subtype == "blocked")

    fb_occ = board.piece_at(stop_sq)
    if fb_occ is not None and fb_occ.piece_type == chess.PAWN and fb_occ.color == color:
        friendly_blocker: Optional[int] = stop_sq
    else:
        friendly_blocker = None

    is_doubled = (
        sum(1 for sq in board.pieces(chess.PAWN, color) if chess.square_file(sq) == f) >= 2
    )
    fs = file_state(board, f, color)
    is_half_open_target = (fs == "half_open_file")

    # Evidence string — names squares, never tag/field names
    pawn_name = chess.square_name(square)
    stop_name = chess.square_name(stop_sq)
    ev = (
        f"the pawn on {pawn_name} is backward: its advance square {stop_name} "
        f"is covered by the pawn on {chess.square_name(pawn_controllers[0])}"
    )
    if advanced:
        if len(advanced) == 1:
            adv_fl = chess.FILE_NAMES[chess.square_file(advanced[0])]
            ev += (
                f", and the {adv_fl}-pawn on {chess.square_name(advanced[0])} "
                f"has already advanced past it and cannot return to support a push"
            )
        else:
            adv_names = " and ".join(chess.square_name(s) for s in advanced)
            ev += (
                f", and the pawns on {adv_names} have already advanced past it "
                f"and cannot return to support a push"
            )
    for fl_sq in fixed_level_neighbors:
        fl_f = chess.square_file(fl_sq)
        fl_rn = chess.square_rank(fl_sq)
        if fl_rn == r:
            ev += (
                f"; although the {chess.FILE_NAMES[fl_f]}-pawn is level on "
                f"{chess.square_name(fl_sq)} it cannot reach "
                f"{chess.square_name(chess.square(fl_f, r + fwd))} to defend the push"
            )
    if subtype == "half_open":
        ev += f"; the half-open {file_letter}-file makes it a target"

    return (True, {
        "pawn_square": square,
        "color": color,
        "stop_square": stop_sq,
        "enemy_pawn_controllers": pawn_controllers,
        "advanced_neighbors": advanced,
        "fixed_level_neighbors": fixed_level_neighbors,
        "subtype": subtype,
        "is_blocked": is_blocked,
        "friendly_blocker": friendly_blocker,
        "is_doubled": is_doubled,
        "file_status": fs,
        "is_half_open_target": is_half_open_target,
        "evidence": ev,
    })


def is_infiltration(
    board_after: chess.Board, square: int, color: bool, phase: str
) -> Tuple[bool, Optional[dict]]:
    """Certifies 'infiltration': a rook, queen, or (endgame-only) king has landed on a deep
    rank inside enemy territory — the 7th/8th for heavy pieces, 6th/7th/8th for an endgame
    king — where it is not trivially hanging or pinned, and it is doing real damage (raking
    pawns, boxing the enemy king, or arriving on an open back-rank file).

    A move that arrives with check is NOT infiltration (veto 3) — the opponent is forced to
    respond and the move belongs to the tactics gates. Phase must be passed explicitly because
    chess.Move has no .phase attribute; see the wiring in certified_claims / narrator.py.
    """
    if color == chess.WHITE:
        heavy_deep_ranks = {6, 7}
        king_deep_ranks  = {5, 6, 7}
        back_rank = 7
    else:
        heavy_deep_ranks = {1, 0}
        king_deep_ranks  = {2, 1, 0}
        back_rank = 0
    enemy = not color

    # VETO 1: piece type — rook, queen, or king only
    piece = board_after.piece_at(square)
    if piece is None or piece.color != color:
        return (False, None)
    if piece.piece_type not in (chess.ROOK, chess.QUEEN, chess.KING):
        return (False, None)

    # VETO 2: endgame gate for the king
    if piece.piece_type == chess.KING and phase != "endgame":
        return (False, None)

    # VETO 3: no infiltration if the move arrived with check (tactic, not standing penetration)
    if board_after.is_check():
        return (False, None)

    # VETO 4: depth — must be on the relevant deep-rank set for this piece type
    rank = chess.square_rank(square)
    if piece.piece_type in (chess.ROOK, chess.QUEEN):
        if rank not in heavy_deep_ranks:
            return (False, None)
    else:  # KING
        if rank not in king_deep_ranks:
            return (False, None)

    # CONFIRM 5: operability — not absolutely pinned; not hanging-and-undefended
    attacked = board_after.is_attacked_by(enemy, square)
    defended = board_after.is_attacked_by(color, square)
    pinned   = board_after.is_pinned(color, square)

    if pinned:
        return (False, None)

    hanging = False
    if attacked and not defended:
        if piece.piece_type in (chess.QUEEN, chess.KING):
            return (False, None)
        else:  # rook — record caveat, don't auto-veto
            hanging = True

    # CONFIRM 6: purpose — at least one of (a) pawn-raking, (b) king confinement, (c) open back-rank
    targeted_pawns: List[str] = []
    confines_king: Optional[str] = None
    arrival_file_state: str = ""
    absolute_seventh: bool = False

    # (a) Attacks an enemy pawn (all piece types)
    for s in board_after.attacks(square):
        tp = board_after.piece_at(s)
        if tp is not None and tp.piece_type == chess.PAWN and tp.color == enemy:
            targeted_pawns.append(chess.square_name(s))

    # (b) King confinement — rook/queen only
    if piece.piece_type in (chess.ROOK, chess.QUEEN):
        ek = board_after.king(enemy)
        if ek is not None and chess.square_rank(ek) == back_rank:
            # escape_rank: one step toward centre from the back rank
            escape_rank = back_rank - 1 if color == chess.WHITE else back_rank + 1
            ek_file = chess.square_file(ek)
            cuts_escape = any(
                chess.square_rank(s) == escape_rank
                and abs(chess.square_file(s) - ek_file) <= 1
                for s in board_after.attacks(square)
            )
            shares_file = (chess.square_file(square) == ek_file)
            if cuts_escape or shares_file:
                confines_king = chess.square_name(ek)
                seventh_rank = 6 if color == chess.WHITE else 1
                # "absolute 7th": rook on the 7th, same file as the trapped king
                # (rook pins the king to the back rank by file — the strongest sub-case)
                if piece.piece_type == chess.ROOK and rank == seventh_rank and shares_file:
                    absolute_seventh = True

        # (c) Open-file back-rank arrival — rook/queen only
        if rank == back_rank:
            files = file_structure(board_after)
            file_idx = chess.square_file(square)
            letter = chess.FILE_NAMES[file_idx]
            half_key = "half_open_white" if color == chess.WHITE else "half_open_black"
            if letter in files["open"]:
                arrival_file_state = "open"
            elif letter in files[half_key]:
                arrival_file_state = "half-open"

    # Must have at least one purpose
    has_purpose = (
        bool(targeted_pawns)
        or confines_king is not None
        or arrival_file_state != ""
    )
    if not has_purpose:
        return (False, None)

    # --- Build evidence bundle ---
    piece_name = PIECE_NAMES[piece.piece_type]
    sq_name = chess.square_name(square)

    if color == chess.WHITE:
        rank_label_map = {6: "the seventh rank", 7: "the eighth (back) rank", 5: "the sixth rank"}
    else:
        rank_label_map = {1: "the second rank", 0: "the first (back) rank", 2: "the third rank"}
    rank_label = rank_label_map.get(rank, f"rank {rank + 1}")

    if confines_king is not None:
        prefix = "absolute seventh — " if absolute_seventh else ""
        evidence_str = (
            f"{prefix}the {piece_name} on {sq_name} has infiltrated to {rank_label}, "
            f"cutting off the enemy king on {confines_king}"
        )
    elif targeted_pawns:
        if piece.piece_type == chess.KING:
            evidence_str = (
                f"the king on {sq_name} has marched into enemy territory on {rank_label}, "
                f"attacking {', '.join(targeted_pawns)}"
            )
        else:
            evidence_str = (
                f"the {piece_name} on {sq_name} has infiltrated to {rank_label}, "
                f"attacking the pawn(s) on {', '.join(targeted_pawns)}"
            )
    else:  # (c) open-file back-rank
        file_letter = sq_name[0]
        evidence_str = (
            f"the {piece_name} on {sq_name} has infiltrated the enemy back rank "
            f"down the {arrival_file_state} {file_letter}-file"
        )

    if hanging:
        evidence_str += " — but the infiltrating rook is itself hanging"

    return (True, {
        "piece": piece_name,
        "square": sq_name,
        "rank_label": rank_label,
        "targeted_pawns": targeted_pawns,
        "confines_king": confines_king,
        "arrival_file_state": arrival_file_state,
        "absolute_seventh": absolute_seventh,
        "hanging": hanging,
        "evidence_str": evidence_str,
    })


def is_fianchetto(
    board: chess.Board, color: bool
) -> Tuple[bool, Optional[List[dict]]]:
    """Certifies a 'fianchetto' structural feature for `color`: the friendly bishop
    sits on its flank square (g2/b2 for White, g7/b7 for Black) and a friendly pawn
    occupies the opened knight-pawn square (g3/b3 for White, g6/b6 for Black).

    Pure standing structural predicate — side-to-move independent. Evaluated for BOTH
    colors in certified_claims (not just the mover). Returns (True, list_of_dicts) if
    at least one flank certifies, (False, None) otherwise; a double fianchetto produces
    a 2-element list. Pinned bishops still certify (pin is a piece-interaction fact,
    not a structural one).
    """
    side = "White" if color == chess.WHITE else "Black"

    # Per-flank constants (verified empirically against python-chess)
    if color == chess.WHITE:
        flanks = [
            {
                "flank": "kingside",
                "bishop_sq": chess.G2,
                "pawn_open_sq": chess.G3,
                "long_diagonal": "h1-a8",
                "aims_at": "a8",
                "king_behind_sqs": frozenset({chess.G1, chess.H1}),
            },
            {
                "flank": "queenside",
                "bishop_sq": chess.B2,
                "pawn_open_sq": chess.B3,
                "long_diagonal": "a1-h8",
                "aims_at": "h8",
                "king_behind_sqs": frozenset({chess.C1, chess.B1}),
            },
        ]
    else:
        flanks = [
            {
                "flank": "kingside",
                "bishop_sq": chess.G7,
                "pawn_open_sq": chess.G6,
                "long_diagonal": "a1-h8",
                "aims_at": "a1",
                "king_behind_sqs": frozenset({chess.G8, chess.H8}),
            },
            {
                "flank": "queenside",
                "bishop_sq": chess.B7,
                "pawn_open_sq": chess.B6,
                "long_diagonal": "h1-a8",
                "aims_at": "h1",
                "king_behind_sqs": frozenset({chess.C8, chess.B8}),
            },
        ]

    results: List[dict] = []

    for fl in flanks:
        # VETO 1: friendly bishop on the flank square
        bp = board.piece_at(fl["bishop_sq"])
        if bp is None or bp.piece_type != chess.BISHOP or bp.color != color:
            continue

        # VETO 2: friendly pawn on the opened knight-pawn square
        pp = board.piece_at(fl["pawn_open_sq"])
        if pp is None or pp.piece_type != chess.PAWN or pp.color != color:
            continue

        # CONFIRM: both O(1) vetoes passed — build evidence dict
        bishop_square = chess.square_name(fl["bishop_sq"])
        pawn_square = chess.square_name(fl["pawn_open_sq"])
        long_diagonal = fl["long_diagonal"]
        aims_at = fl["aims_at"]
        flank = fl["flank"]
        current_rake = sorted(chess.square_name(s) for s in board.attacks(fl["bishop_sq"]))

        king_sq = board.king(color)
        king_behind = king_sq is not None and king_sq in fl["king_behind_sqs"]

        base = (
            f"{side}'s bishop is fianchettoed on {bishop_square} ({flank}), "
            f"the knight-pawn on {pawn_square} opening the {long_diagonal} long diagonal "
            f"toward {aims_at}"
        )
        evidence = (
            f"{base}, behind the castled king on {chess.square_name(king_sq)}"
            if king_behind
            else base
        )

        results.append({
            "color": color,
            "side": side,
            "flank": flank,
            "bishop_square": bishop_square,
            "pawn_square": pawn_square,
            "long_diagonal": long_diagonal,
            "aims_at": aims_at,
            "current_rake": current_rake,
            "king_behind": king_behind,
            "evidence": evidence,
        })

    if not results:
        return (False, None)
    return (True, results)


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


def creates_discovered_attack(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[str]]:
    """Certifies a 'discovered_attack': a friendly slider was blocked before the move and
    now bears on an enemy target because the front piece vacated. Covers plain discovered
    attacks, discovered check, and double check. Wraps analyzer.detect_discovered_attack
    which enforces: castling/null-move veto, vacated-set + colinearity proof, before-clear
    + was-occupied VETO 5, causation guard, pin-as-flag (not veto), king-first ranking."""
    result = detect_discovered_attack(board_before, move, board_after, mover_color)
    return (result is not None, result)


def creates_overloaded(board_after: chess.Board) -> Optional[dict]:
    """Certifies an 'overloaded / overworked defender': a piece that simultaneously
    defends two or more attacked friendly pieces and is the sole defender of at
    least one — it physically cannot save both. Thin wrapper over
    detect_overloaded_defender_full; returns the evidence bundle when certified,
    None otherwise.
    """
    return detect_overloaded_defender_full(board_after)


# --------------------------------------------------------------------------- #
# Zugzwang (engine-dependent, pre-computed scores).
# --------------------------------------------------------------------------- #
ZUGZWANG_CP = 100  # minimum delta (pass - best) to certify; tune up to cut false positives


def is_zugzwang(
    board: chess.Board,
    cp_best: Optional[int],
    mate_best: Optional[int],
    cp_pass: Optional[int],
    mate_pass: Optional[int],
    phase: str,
    legal_move_count: int,
    best_move_san: str,
) -> dict:
    """Approximate zugzwang detector (engine-dependent, pre-computed scores).

    Takes Stockfish eval scores supplied by the caller — never calls the engine.
    cp_best / mate_best: best-legal-move eval for the side to move (White-POV).
    cp_pass / mate_pass: null-move pass-baseline (White-POV).
    Both are converted to side-to-move POV internally via the sign procedure
    specified in the detection spec §Rule 6.

    Returns a dict with is_zugzwang, strict, label, evidence, and diagnostic fields.
    The 'zugzwang' allow-set tag is in GATED_TAGS and is added to d['certified']
    in narrator._move_to_dict when is_zugzwang=True (not via certified_claims, which
    is engine-free by design).
    """
    side_to_move = "White" if board.turn == chess.WHITE else "Black"

    def _no_fire(veto_reason: str) -> dict:
        return {
            "is_zugzwang": False,
            "strict": False,
            "label": "near-zugzwang",
            "side_to_move": side_to_move,
            "eval_pass_cp": 0,
            "eval_best_cp": 0,
            "delta_cp": 0,
            "best_move_san": best_move_san,
            "legal_move_count": legal_move_count,
            "phase": phase,
            "threshold_cp": ZUGZWANG_CP,
            "veto_reason": veto_reason,
            "evidence": "",
        }

    # VETO 1: game already over (stalemate, checkmate, draw — not zugzwang)
    if board.is_game_over():
        return _no_fire("game_over")

    # VETO 2: side to move is in check (forced parry, not compulsion; null-move
    # baseline would also be meaningless — the king stays in check)
    if board.is_check():
        return _no_fire("in_check")

    # VETO 3: forced / single legal move (no choice to degrade)
    if legal_move_count <= 1:
        return _no_fire("forced")

    # VETO 4: phase / scope gate — endgame OR ≤6 non-king non-pawn pieces (both colors)
    non_kp = sum(
        len(board.pieces(pt, c))
        for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
        for c in (chess.WHITE, chess.BLACK)
    )
    if phase != "endgame" and non_kp > 6:
        return _no_fire("phase")

    # VETO 5: en-passant capture available (null-move baseline is polluted —
    # push(Move.null()) silently forfeits the ep right, corrupting the delta)
    if board.has_legal_en_passant():
        return _no_fire("en_passant")

    # Guard: null-move scores must be present (probe may have been skipped upstream)
    if cp_pass is None and mate_pass is None:
        return _no_fire("below_threshold")

    # CONFIRM — Rule 6: sign-correct side-to-move POV conversion
    # normalize_cp returns White-POV; sign flips to side-to-move POV for both values
    sign = 1 if board.turn == chess.WHITE else -1
    eval_best = sign * normalize_cp(cp_best, mate_best)
    eval_pass = sign * normalize_cp(cp_pass, mate_pass)
    delta_cp = eval_pass - eval_best

    if delta_cp < ZUGZWANG_CP:
        return _no_fire("below_threshold")

    # Rule 7: strictness ladder — strict requires pass to be non-losing for the mover
    strict = eval_pass >= -50
    label = "zugzwang" if strict else "near-zugzwang"

    move_name = best_move_san if best_move_san else "their best move"
    if strict:
        evidence = (
            f"{side_to_move} is in zugzwang: passing would hold "
            f"(about {eval_pass / 100:+.1f}), but every one of the "
            f"{legal_move_count} legal moves loses ground — "
            f"even the best, {move_name}, drops to about {eval_best / 100:+.1f}."
        )
    else:
        evidence = (
            f"{side_to_move} is in near-zugzwang: with no useful waiting move, "
            f"every legal reply worsens the position — the best available, "
            f"{move_name}, is about {delta_cp} centipawns worse than "
            f"simply passing would be."
        )

    return {
        "is_zugzwang": True,
        "strict": strict,
        "label": label,
        "side_to_move": side_to_move,
        "eval_pass_cp": eval_pass,
        "eval_best_cp": eval_best,
        "delta_cp": delta_cp,
        "best_move_san": best_move_san,
        "legal_move_count": legal_move_count,
        "phase": phase,
        "threshold_cp": ZUGZWANG_CP,
        "veto_reason": None,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- #
# Compensation (eval-dependent, pre-computed scores).
# --------------------------------------------------------------------------- #
COMPENSATION_MATERIAL_MIN = -1.5   # mover-POV pawns down (threshold: ≤ this to qualify)
COMPENSATION_EVAL_MIN = -50        # mover-POV cp (threshold: ≥ this = near-level or better)


def is_compensation(
    material_balance: float,
    eval_after_cp: Optional[int],
    mate_after: Optional[int],
    mover_color: bool,
) -> Optional[dict]:
    """Certifies 'compensation': the mover is down material (≥ ~1.5 pawns) yet the
    engine eval does not reflect that deficit (mover-POV ≥ −50cp). Both signals are
    pre-computed by the caller from MoveAnalysis fields.

    material_balance — White-POV pawns (+ = White ahead); sign-corrected internally.
    eval_after_cp   — White-POV centipawns after the move.
    mate_after      — White-POV mate score after the move (None when cp applies).
    mover_color     — True = White.

    Returns a dict evidence bundle or None.
    """
    # VETO 0: no eval data — cannot make the assessment
    if eval_after_cp is None and mate_after is None:
        return None

    # VETO 1: under a mate score — the cp comparison is undefined; abstain
    if eval_after_cp is None and mate_after is not None:
        return None

    sign = 1 if mover_color == chess.WHITE else -1
    mover_material = sign * material_balance   # mover-POV; negative = mover is down

    # VETO 2: mover is not materially down by enough (≤ -1.5 required)
    if mover_material > COMPENSATION_MATERIAL_MIN:
        return None

    mover_eval = sign * normalize_cp(eval_after_cp, mate_after)  # mover-POV cp

    # VETO 3: eval is bad for the mover — the material loss is not compensated
    if mover_eval < COMPENSATION_EVAL_MIN:
        return None

    # All checks passed — compensation is certified.
    side = "White" if mover_color == chess.WHITE else "Black"
    down_pawns = round(abs(mover_material), 1)
    plural = "s" if down_pawns >= 2.0 else ""

    if mover_eval >= 50:
        eval_desc = f"the position favors {side}"
    elif mover_eval >= -20:
        eval_desc = "the engine rates the position as roughly equal"
    else:
        eval_desc = "the engine rates the position as nearly level"

    evidence = (
        f"{side} is down about {down_pawns:.1f} pawn{plural} in material "
        f"but {eval_desc} — full compensation."
    )

    return {
        "tag": "compensation",
        "side": side,
        "down_pawns": down_pawns,
        "eval_cp": mover_eval,
        "mechanism": None,
        "approximate": False,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- #
# Tempo gain (pre-computed attack/refutation data).
# --------------------------------------------------------------------------- #
def is_tempo(
    attacks_pieces: List[str],
    refutation_line_san: str,
    fen_after: str,
    is_capture: bool,
) -> Optional[dict]:
    """Certifies a 'tempo gain': the move attacks an enemy piece (≥ minor value)
    that the opponent's best reply is forced to address — the opponent spends their
    move reacting rather than executing their own plan. No material is exchanged by
    the certifying move itself.

    attacks_pieces      — enemy pieces the moved piece attacks (from MoveAnalysis).
    refutation_line_san — numbered SAN of the engine's best line from fen_after.
    fen_after           — FEN of the position after the move (to parse the reply SAN).
    is_capture          — True if the move itself captured a piece.

    Returns a dict evidence bundle or None.
    """
    # VETO 1: move was a capture (material changed — this is a trade, not a pure tempo),
    #         or no non-pawn / non-king enemy pieces are attacked.
    non_trivial = [
        a for a in attacks_pieces
        if not a.startswith("pawn") and not a.startswith("king")
    ]
    if is_capture or not non_trivial:
        return None

    # VETO 2: no refutation line to check forcing-ness.
    if not refutation_line_san:
        return None

    # Extract the first SAN move token from the numbered move string.
    # Handles both "15. Nd7 ..." (White first) and "15... Nd7 ..." (Black first).
    tok = re.match(r"^\d+\.{1,3}\s*(\S+)", refutation_line_san.strip())
    if not tok:
        return None
    first_san = tok.group(1)

    # Parse the SAN token on the post-move board (opponent to move).
    try:
        board_aft = chess.Board(fen_after)
        opp_move = board_aft.parse_san(first_san)
    except Exception:
        return None

    # Build a square → description map for non-trivial attacked pieces.
    attacked: dict = {}
    for atk_str in non_trivial:
        parts = atk_str.rsplit(" on ", 1)
        if len(parts) == 2:
            try:
                sq = chess.parse_square(parts[1])
                attacked[sq] = atk_str
            except ValueError:
                pass

    if not attacked:
        return None

    # CONFIRM: the opponent's first reply addresses at least one attacked square
    # — either the attacked piece moves (from_square) or something comes to that
    # square to defend/recapture (to_square).
    addressed_sq = None
    for sq in attacked:
        if opp_move.from_square == sq or opp_move.to_square == sq:
            addressed_sq = sq
            break

    if addressed_sq is None:
        return None

    # All checks passed — tempo gain certified.
    attacked_desc = attacked[addressed_sq]
    sq_name = attacked_desc.rsplit(" on ", 1)[1]
    evidence = (
        f"attacks the {attacked_desc}, forcing the reply {first_san} — a gain of tempo."
    )

    return {
        "tag": "tempo_gain",
        "attacked": attacked_desc,
        "forced_reply": first_san,
        "square": sq_name,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- #
# Weak square / hole (board-only predicate — no engine required).
# --------------------------------------------------------------------------- #
def detect_weak_square(
    board_after: chess.Board, move: chess.Move, mover_color: bool
) -> Optional[dict]:
    """Certifies 'weak_square': the moved piece (minor piece, rook, or queen, not
    pawn/king) lands on a permanent hole in the opponent's pawn structure — a square
    the opponent's pawns can never attack. Restricted to the same advanced-territory
    rank bands used by is_outpost. Piece must not be trivially hanging.
    """
    sq = move.to_square
    piece = board_after.piece_at(sq)
    if piece is None or piece.color != mover_color:
        return None

    # VETO 1: only pieces that meaningfully benefit from a hole (not pawn or king)
    if piece.piece_type in (chess.PAWN, chess.KING):
        return None

    # VETO 2: advanced territory only — same rank gate as is_outpost
    rank = chess.square_rank(sq)
    if mover_color == chess.WHITE:
        if rank not in (3, 4, 5):
            return None
    else:
        if rank not in (2, 3, 4):
            return None

    defender = not mover_color

    # VETO 3: square must be a permanent hole for the opponent
    if not is_hole(board_after, sq, defender):
        return None

    # VETO 4: piece must not be trivially hanging (attacked and completely undefended)
    if board_after.is_attacked_by(defender, sq) and not board_after.is_attacked_by(mover_color, sq):
        return None

    sq_name = chess.square_name(sq)
    piece_name = PIECE_NAMES[piece.piece_type]
    side = "White" if mover_color == chess.WHITE else "Black"
    defender_side = "Black" if mover_color == chess.WHITE else "White"
    evidence = (
        f"{side}'s {piece_name} on {sq_name} occupies a permanent weak square — "
        f"{defender_side} has no pawn that can ever challenge it there"
    )
    return {
        "tag": "weak_square",
        "square": sq_name,
        "piece": piece_name,
        "side": side,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- #
# Zwischenzug / checking intermezzo (board-only predicate).
# --------------------------------------------------------------------------- #
_PIECE_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9,
}


def is_zwischenzug(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Optional[dict]:
    """Certifies the checking-zwischenzug (intermezzo) pattern: instead of taking an
    available free enemy piece, the mover plays a check first — changing the terms of
    the exchange before completing it. Only the checking variant is certified; non-checking
    intermezzos require eval comparison and are deferred to a future iteration.

    VETOs:
      1. Move does not give check.
      2. Move gives checkmate (the ultimate win, but not a tactical intermezzo).
      3. No undefended enemy piece (other than the king and what was just captured) exists
         in board_before that the mover could have taken instead.
    """
    # VETO 1: must give check
    if not board_after.is_check():
        return None

    # VETO 2: checkmate is not a zwischenzug
    if board_after.is_checkmate():
        return None

    enemy = not mover_color

    # CONFIRM: find the most valuable forgone free capture in board_before.
    # A "forgone" piece is undefended, attacked by the mover's side, not the king,
    # and NOT on the square the mover just moved to (not what was captured this turn).
    candidates: List[tuple] = []
    for enemy_sq, ep in board_before.piece_map().items():
        if ep.color != enemy:
            continue
        if ep.piece_type == chess.KING:
            continue
        if enemy_sq == move.to_square:
            continue
        if not board_before.is_attacked_by(mover_color, enemy_sq):
            continue
        if board_before.attackers(enemy, enemy_sq):
            continue  # defended — not a free capture
        candidates.append((_PIECE_VALUES.get(ep.piece_type, 0), enemy_sq, ep.piece_type))

    if not candidates:
        return None

    # Pick the most valuable forgone piece so the evidence names the clearest target
    candidates.sort(reverse=True)
    _, forgone_sq, forgone_type = candidates[0]

    forgone_name = chess.square_name(forgone_sq)
    forgone_piece_name = PIECE_NAMES[forgone_type]
    check_sq_name = chess.square_name(move.to_square)
    side = "White" if mover_color == chess.WHITE else "Black"
    evidence = (
        f"{side} ignores the free {forgone_piece_name} on {forgone_name} "
        f"and inserts a check — a zwischenzug that changes the terms of the exchange"
    )
    return {
        "tag": "zwischenzug",
        "check_square": check_sq_name,
        "forgone_capture": forgone_name,
        "forgone_piece": forgone_piece_name,
        "side": side,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- #
# Space advantage (board-only — goes in certified_claims).
# --------------------------------------------------------------------------- #
_SPACE_ADVANTAGE_THRESHOLD = 4   # minimum pawn-space lead to certify
_SPACE_ADVANTAGE_MIN_PAWNS = 4   # minimum total pawn count (barren positions excluded)


def _pawn_space_score(board: chess.Board, color: bool) -> int:
    """Sum of rank-advancement for every pawn of `color` beyond its starting rank.
    White pawn at rank-index r: max(0, r−1) [rank 2 = 0, rank 7 = 5].
    Black pawn at rank-index r: max(0, 6−r) [rank 7 = 0, rank 2 = 5].
    """
    total = 0
    for sq in board.pieces(chess.PAWN, color):
        r = chess.square_rank(sq)
        total += max(0, r - 1) if color == chess.WHITE else max(0, 6 - r)
    return total


def detect_space_advantage(
    board: chess.Board, mover_color: bool
) -> Optional[dict]:
    """Certifies 'space_advantage': the mover's pawn chain is more advanced than
    the opponent's — measured by a per-pawn rank-advancement score. Requires at
    least 4 total pawns and a lead of ≥ 4 score points to avoid false positives
    in barren endings or marginally unequal positions.
    """
    enemy = not mover_color

    # VETO 1: too few pawns — space is meaningless in near-pawnless positions
    mover_pawns = board.pieces(chess.PAWN, mover_color)
    enemy_pawns = board.pieces(chess.PAWN, enemy)
    if len(mover_pawns) + len(enemy_pawns) < _SPACE_ADVANTAGE_MIN_PAWNS:
        return None

    mover_score = _pawn_space_score(board, mover_color)
    enemy_score = _pawn_space_score(board, enemy)
    lead = mover_score - enemy_score

    # VETO 2: lead not significant enough
    if lead < _SPACE_ADVANTAGE_THRESHOLD:
        return None

    side = "White" if mover_color == chess.WHITE else "Black"
    enemy_side = "Black" if mover_color == chess.WHITE else "White"

    # Name the most advanced pawns (up to 3) for the evidence string
    pawn_sqs = sorted(
        mover_pawns,
        key=lambda s: chess.square_rank(s) if mover_color == chess.WHITE else -chess.square_rank(s),
        reverse=True,
    )
    adv_names = [chess.square_name(s) for s in pawn_sqs[:3]]
    if len(adv_names) == 1:
        pawn_desc = f"pawn on {adv_names[0]}"
    elif len(adv_names) == 2:
        pawn_desc = f"pawns on {adv_names[0]} and {adv_names[1]}"
    else:
        pawn_desc = f"pawns on {', '.join(adv_names[:-1])} and {adv_names[-1]}"

    evidence = (
        f"{side}'s {pawn_desc} give {side} a space advantage "
        f"(pawn-space score {mover_score} vs {enemy_side}'s {enemy_score})"
    )
    return {
        "tag": "space_advantage",
        "side": side,
        "mover_score": mover_score,
        "enemy_score": enemy_score,
        "lead": lead,
        "advanced_pawns": adv_names,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- #
# Prophylaxis / blockade (board-only — goes in certified_claims).
# --------------------------------------------------------------------------- #
def is_prophylaxis(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Optional[dict]:
    """Certifies 'prophylaxis': a quiet (non-checking, non-capturing) move in which
    the mover places a piece on the natural advance square of an advanced enemy pawn,
    blocking its further progress. The pawn must have crossed the centre:

      • Black pawn being blocked by White: pawn rank ≤ 4 (rank 1–4, r ≤ 3)
      • White pawn being blocked by Black: pawn rank ≥ 5 (rank 5–8, r ≥ 4)

    The blocking piece must not be trivially hanging (attacked and completely
    undefended). Passed-pawn blockades are flagged in the evidence bundle.
    """
    # VETO 1: giving check is a tactical reply, not prophylaxis
    if board_after.is_check():
        return None

    # VETO 2: a capture is not a prophylactic quiet move
    if board_before.is_capture(move):
        return None

    enemy = not mover_color
    to_sq = move.to_square
    to_file = chess.square_file(to_sq)
    to_rank = chess.square_rank(to_sq)

    # VETO 3: to-square must have been empty before the move (true blockade)
    if board_before.piece_at(to_sq) is not None:
        return None

    # Scan enemy pawns for one whose advance square matches to_sq
    blocked_pawn_sq: Optional[int] = None
    for pawn_sq in board_before.pieces(chess.PAWN, enemy):
        pr = chess.square_rank(pawn_sq)
        pf = chess.square_file(pawn_sq)
        if pf != to_file:
            continue
        if enemy == chess.WHITE:
            advance_rank = pr + 1    # White pawns advance up
            dangerous = (pr >= 4)    # past the centre: rank 5+ (r ≥ 4)
        else:
            advance_rank = pr - 1    # Black pawns advance down
            dangerous = (pr <= 3)    # past the centre: rank 4 or below (r ≤ 3)
        if advance_rank != to_rank:
            continue
        if not dangerous:
            continue
        blocked_pawn_sq = pawn_sq
        break

    if blocked_pawn_sq is None:
        return None

    # VETO 4: blocking piece is trivially hanging (attacked and completely undefended)
    if (board_after.is_attacked_by(enemy, to_sq)
            and not board_after.is_attacked_by(mover_color, to_sq)):
        return None

    piece = board_after.piece_at(to_sq)
    if piece is None:
        return None

    piece_name = PIECE_NAMES[piece.piece_type]
    side = "White" if mover_color == chess.WHITE else "Black"
    enemy_side = "Black" if mover_color == chess.WHITE else "White"
    to_name = chess.square_name(to_sq)
    pawn_name = chess.square_name(blocked_pawn_sq)
    pawn_rank_label = chess.square_name(blocked_pawn_sq)[1]   # digit only, e.g. "4"

    passed = is_passed_pawn(board_before, blocked_pawn_sq, enemy)

    if passed:
        evidence = (
            f"{side}'s {piece_name} on {to_name} blockades the passed {enemy_side} pawn "
            f"on {pawn_name}, preventing its advance — a prophylactic blockade"
        )
    else:
        evidence = (
            f"{side}'s {piece_name} on {to_name} blocks the {enemy_side} pawn "
            f"on {pawn_name} from pushing forward — a prophylactic move"
        )

    return {
        "tag": "prophylaxis",
        "blocked_pawn": pawn_name,
        "blocking_piece": piece_name,
        "blocking_square": to_name,
        "side": side,
        "is_passed_pawn_blockade": passed,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- #
# Initiative — checking sequence (PV-dependent, wired in narrator._move_to_dict).
# --------------------------------------------------------------------------- #
def is_initiative(
    fen_after: str,
    refutation_line_san: str,
    mover_color: bool,
) -> Optional[dict]:
    """Certifies 'initiative': the move gives check AND the mover's next move in the
    engine PV is also a check — two consecutive checks indicating sustained forcing
    pressure. The current check is confirmed from fen_after; the follow-up check is
    read from the second SAN token of refutation_line_san (opponent's reply is token 0,
    mover's continuation is token 1 — a '+' in token 1 is the confirm).

    fen_after           — FEN after the move (opponent to move, in check).
    refutation_line_san — numbered SAN of the engine's best line from fen_after
                          (starts with the opponent's reply, then mover's next move).
    mover_color         — True = White.
    """
    # VETO 1: current move must give check
    try:
        board_after = chess.Board(fen_after)
    except Exception:
        return None
    if not board_after.is_check():
        return None

    # VETO 2: checkmate is the ultimate win, not a sustained initiative pattern
    if board_after.is_checkmate():
        return None

    # VETO 3: no PV line to inspect
    if not refutation_line_san:
        return None

    # Strip move-number markers ("15.", "15...") and collect bare SAN tokens
    moves_only = [t for t in refutation_line_san.split() if not re.match(r'^\d+\.+$', t)]

    # VETO 4: need opponent's reply (index 0) plus mover's next (index 1)
    if len(moves_only) < 2:
        return None

    opp_reply = moves_only[0]
    mover_next = moves_only[1]

    # CONFIRM: mover's next move in the PV is a check ('+' in SAN token)
    if '+' not in mover_next:
        return None

    side = "White" if mover_color == chess.WHITE else "Black"
    evidence = (
        f"{side} maintains the initiative — after {opp_reply}, "
        f"{mover_next} delivers a second consecutive check, keeping {side} on the attack"
    )
    return {
        "tag": "initiative",
        "opp_reply": opp_reply,
        "second_check": mover_next,
        "side": side,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- #
# Bishop pair — structural material imbalance.
# --------------------------------------------------------------------------- #
def is_bishop_pair(board: chess.Board, color: bool) -> Tuple[bool, str]:
    """Certifies that `color` has both bishops while the opponent has at most one bishop.
    The bishop pair is a lasting structural edge: two complementary long-diagonal sliders
    cover all square colours. Engine-free — pure piece count.
    """
    friendly = len(board.pieces(chess.BISHOP, color))
    enemy = len(board.pieces(chess.BISHOP, not color))
    if friendly < 2 or enemy > 1:
        return (False, "")
    side = "White" if color == chess.WHITE else "Black"
    opp_desc = "no bishops" if enemy == 0 else "only one bishop"
    return (
        True,
        f"{side} has the bishop pair — two complementary long-diagonal sliders covering "
        f"both square colours; the opponent has {opp_desc}",
    )


# --------------------------------------------------------------------------- #
# Rook on open / half-open file — standing positional fact.
# --------------------------------------------------------------------------- #
def is_rook_on_open_file(
    board: chess.Board, square: int, color: bool
) -> Tuple[bool, str]:
    """Certifies that a rook of `color` on `square` occupies an open or half-open file.
    Open = no pawns of either colour on the file; half-open = no friendly pawns remain
    (enemy pawn(s) may still be present). Distinct from `rook_lift` (which certifies the
    *move* off a home rank) — this certifies the *standing* positional fact of a rook
    already posted on such a file. Uses file_structure() as the single source of truth.
    """
    piece = board.piece_at(square)
    if piece is None or piece.piece_type != chess.ROOK or piece.color != color:
        return (False, "")
    files = file_structure(board)
    letter = chess.FILE_NAMES[chess.square_file(square)]
    half_key = "half_open_white" if color == chess.WHITE else "half_open_black"
    if letter in files["open"]:
        return (True, f"rook on the open {letter}-file")
    if letter in files[half_key]:
        return (True, f"rook on the half-open {letter}-file")
    return (False, "")


# --------------------------------------------------------------------------- #
# Connected rooks — two rooks see each other on the same rank or file.
# --------------------------------------------------------------------------- #
def is_connected_rooks(board: chess.Board, color: bool) -> Tuple[bool, Optional[dict]]:
    """Certifies that `color` has at least two rooks connected — seeing each other on
    the same rank or file with no intervening pieces. Engine-free state predicate.
    """
    rook_squares = list(board.pieces(chess.ROOK, color))
    if len(rook_squares) < 2:
        return False, None

    for i in range(len(rook_squares)):
        for j in range(i + 1, len(rook_squares)):
            sq1, sq2 = rook_squares[i], rook_squares[j]
            r1, f1 = chess.square_rank(sq1), chess.square_file(sq1)
            r2, f2 = chess.square_rank(sq2), chess.square_file(sq2)

            # Rooks must share a rank or file; diagonal alignments are excluded.
            if r1 != r2 and f1 != f2:
                continue

            # Confirm no pieces occupy the squares between them.
            if not any(board.piece_at(sq) for sq in chess.SquareSet(chess.between(sq1, sq2))):
                side = "White" if color == chess.WHITE else "Black"
                axis = "rank" if r1 == r2 else "file"
                return True, {
                    "square1": chess.square_name(sq1),
                    "square2": chess.square_name(sq2),
                    "rank_or_file": axis,
                    "evidence": (
                        f"{side}'s rooks are connected on the {axis} "
                        f"({chess.square_name(sq1)} and {chess.square_name(sq2)})"
                    ),
                }

    return False, None


# --------------------------------------------------------------------------- #
# File opening — a move that creates a new fully-open file.
# --------------------------------------------------------------------------- #
def creates_open_file(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certify that the move opened a new fully-open file (no pawns of either colour
    remain on it). Most commonly a pawn capture that exchanges both colours' pawns off
    the same file, freeing it for rooks and queens. Engine-free — pure pawn counting.
    """
    open_before = set(file_structure(board_before)["open"])
    open_after = set(file_structure(board_after)["open"])
    new_open = sorted(open_after - open_before)
    if not new_open:
        return False, None

    side = "White" if mover_color == chess.WHITE else "Black"
    file_list = ", ".join(f"{f}-file" for f in new_open)
    return True, {
        "files": new_open,
        "evidence": f"{side}'s move opens the {file_list}",
    }


# --------------------------------------------------------------------------- #
# Half-open file created — the mover loses a pawn from a file but the opponent's
# pawn remains, giving the mover a half-open file to operate on.
# --------------------------------------------------------------------------- #
def creates_half_open_file(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certify that the move gave the mover a new half-open file — the mover no longer
    has a pawn on it, but the opponent still does. This is the common pattern of a pawn
    capture that clears one's own pawn from a file while the enemy pawn remains as a
    target for heavy pieces. Engine-free — pure pawn counting via file_structure().
    """
    half_key = "half_open_white" if mover_color == chess.WHITE else "half_open_black"
    half_before = set(file_structure(board_before)[half_key])
    half_after = set(file_structure(board_after)[half_key])
    new_half = sorted(half_after - half_before)
    if not new_half:
        return False, None

    side = "White" if mover_color == chess.WHITE else "Black"
    file_list = ", ".join(f"{f}-file" for f in new_half)
    return True, {
        "files": new_half,
        "evidence": (
            f"{side}'s move opens the {file_list} as a half-open file "
            f"— {side} has no pawns there but the opponent does"
        ),
    }


# --------------------------------------------------------------------------- #
# Desperado — a piece captures material while itself under attack.
# --------------------------------------------------------------------------- #
def is_desperado(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
) -> Tuple[bool, Optional[dict]]:
    """Certify a desperado: a piece makes a capture while itself under attack by an
    opponent piece of equal or lesser value (the piece is en prise and grabs material
    before being captured itself).

    Veto ladder:
      1. Move is not a capture.
      2. Moving piece has no recognized material value.
      3. No opponent piece attacks the from-square before the move.
      4. The cheapest opponent attacker is MORE valuable than the moving piece
         (piece is not en prise — the opponent would lose material by taking it).
      5. The captured piece has no material value.

    Returns (True, evidence_dict) or (False, None).
    evidence keys: piece, captured, cheapest_attacker, attacker_value,
                   piece_value, captured_value.
    """
    # VETO 1: must be a capture
    if not board_before.is_capture(move):
        return False, None

    from_sq = move.from_square
    to_sq = move.to_square

    # VETO 2: moving piece must have a recognized material value
    moving_piece = board_before.piece_at(from_sq)
    if moving_piece is None:
        return False, None
    moving_value = _PIECE_VALUES.get(moving_piece.piece_type, 0)
    if moving_value == 0:
        return False, None

    # VETO 3: moving piece must be attacked by at least one opponent piece
    opponent = not board_before.turn
    attacker_squares = list(board_before.attackers(opponent, from_sq))
    if not attacker_squares:
        return False, None

    attacker_pieces = [board_before.piece_at(sq) for sq in attacker_squares]
    attacker_values = [
        _PIECE_VALUES.get(p.piece_type, 0) for p in attacker_pieces if p is not None
    ]
    if not attacker_values:
        return False, None
    min_attacker_value = min(attacker_values)

    # VETO 4: cheapest attacker must be ≤ moving piece value (confirms en prise)
    if min_attacker_value > moving_value:
        return False, None

    # VETO 5: captured piece must have material value
    if board_before.is_en_passant(move):
        captured_type = chess.PAWN
        captured_value = 1
    else:
        captured_piece = board_before.piece_at(to_sq)
        if captured_piece is None:
            return False, None
        captured_type = captured_piece.piece_type
        captured_value = _PIECE_VALUES.get(captured_type, 0)
    if captured_value == 0:
        return False, None

    cheapest_idx = attacker_values.index(min_attacker_value)
    cheapest_attacker = attacker_pieces[cheapest_idx]

    return True, {
        "piece": chess.piece_name(moving_piece.piece_type),
        "captured": chess.piece_name(captured_type),
        "cheapest_attacker": chess.piece_name(cheapest_attacker.piece_type)
        if cheapest_attacker else "unknown",
        "attacker_value": min_attacker_value,
        "piece_value": moving_value,
        "captured_value": captured_value,
    }


# --------------------------------------------------------------------------- #
# Promotion — a pawn reaches the back rank and becomes a new piece.
# --------------------------------------------------------------------------- #
def is_promotion(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move is a pawn promotion.

    Returns (True, evidence_dict) when move.promotion is set and the piece
    moving was indeed a pawn. Returns (False, None) otherwise.
    evidence keys: promoted_to (piece name string), square (algebraic name).
    """
    if move.promotion is None:
        return False, None
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN:
        return False, None
    return True, {
        "promoted_to": chess.piece_name(move.promotion),
        "square": chess.square_name(move.to_square),
    }


# --------------------------------------------------------------------------- #
# En passant — the capturing pawn lands behind the captured pawn.
# --------------------------------------------------------------------------- #
def is_en_passant(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move is an en passant capture.

    The captured pawn sits on the same file as the destination square and the
    same rank as the origin square — it vanishes from that square, not from the
    destination.  Evidence keys: capture_square (where the capturing pawn lands),
    captured_square (where the captured pawn was).
    """
    if not board_before.is_en_passant(move):
        return False, None
    captured_sq = chess.square(
        chess.square_file(move.to_square),
        chess.square_rank(move.from_square),
    )
    side = "White" if board_before.turn == chess.WHITE else "Black"
    return True, {
        "capture_square": chess.square_name(move.to_square),
        "captured_square": chess.square_name(captured_sq),
        "evidence": (
            f"{side} captures en passant on {chess.square_name(move.to_square)}, "
            f"removing the pawn from {chess.square_name(captured_sq)}"
        ),
    }


# --------------------------------------------------------------------------- #
# Castling — the king moves two squares toward a rook.
# --------------------------------------------------------------------------- #
def is_castling(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move is a castling move (kingside or queenside).

    Uses python-chess's is_castling() which checks the move is a legal
    king-two-squares move with castling rights intact.
    Evidence keys: side ('kingside' or 'queenside'), color ('White' or 'Black').
    """
    if not board_before.is_castling(move):
        return False, None
    color = board_before.turn
    side = "kingside" if board_before.is_kingside_castling(move) else "queenside"
    color_name = "White" if color == chess.WHITE else "Black"
    return True, {
        "side": side,
        "color": color_name,
        "evidence": f"{color_name} castles {side}",
    }


# --------------------------------------------------------------------------- #
# Creates passer — a move that establishes a new passed pawn for the mover.
# --------------------------------------------------------------------------- #
def creates_passer(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move created at least one new passed pawn for the mover.

    "New" means the pawn is a passer after the move but was NOT a passer before.
    Advances of already-passed pawns do not qualify — the pawn at `move.from_square`
    is compared to the pawn at `move.to_square` so an advance doesn't double-count.
    """
    new_passers = []
    for sq in board_after.pieces(chess.PAWN, mover_color):
        if not is_passed_pawn(board_after, sq, mover_color):
            continue
        prev_sq = move.from_square if sq == move.to_square else sq
        if not is_passed_pawn(board_before, prev_sq, mover_color):
            new_passers.append(sq)

    if not new_passers:
        return False, None

    side = "White" if mover_color == chess.WHITE else "Black"
    passer_names = sorted([chess.square_name(sq) for sq in new_passers])
    return True, {
        "squares": passer_names,
        "evidence": f"{side}'s move creates a passed pawn on {', '.join(passer_names)}",
    }


# --------------------------------------------------------------------------- #
# Wins the exchange — a minor piece captures a rook.
# --------------------------------------------------------------------------- #
def wins_exchange(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move wins the exchange: a minor piece (bishop or knight)
    captures an enemy rook. The standard net material gain is approximately two pawns
    (rook ≈ 5, minor ≈ 3), regardless of whether the minor is immediately recaptured.
    Returns (True, evidence_dict) or (False, None).
    evidence keys: piece (minor piece name), rook_square, mover (White/Black), evidence.
    """
    if not board_before.is_capture(move) or board_before.is_en_passant(move):
        return False, None
    moving_piece = board_before.piece_at(move.from_square)
    if moving_piece is None or moving_piece.piece_type not in (chess.BISHOP, chess.KNIGHT):
        return False, None
    captured_piece = board_before.piece_at(move.to_square)
    if captured_piece is None or captured_piece.piece_type != chess.ROOK:
        return False, None
    side = "White" if moving_piece.color == chess.WHITE else "Black"
    piece_name = chess.piece_name(moving_piece.piece_type)
    return True, {
        "piece": piece_name,
        "rook_square": chess.square_name(move.to_square),
        "mover": side,
        "evidence": (
            f"{side}'s {piece_name} captures the rook on "
            f"{chess.square_name(move.to_square)}, winning the exchange"
        ),
    }


# --------------------------------------------------------------------------- #
# Opposite-colored bishops — each side has exactly one bishop on different
# colored squares (the structural draw tendency).
# --------------------------------------------------------------------------- #
def _sq_is_light(sq: int) -> bool:
    return (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1


def is_opposite_bishops(board: chess.Board) -> Tuple[bool, Optional[dict]]:
    """Certifies that each side has exactly one bishop and they are on different
    colored squares. Engine-free state predicate.
    evidence keys: white_bishop (square name), black_bishop (square name), evidence.
    """
    white_bishops = list(board.pieces(chess.BISHOP, chess.WHITE))
    black_bishops = list(board.pieces(chess.BISHOP, chess.BLACK))
    if len(white_bishops) != 1 or len(black_bishops) != 1:
        return False, None
    wb_sq, bb_sq = white_bishops[0], black_bishops[0]
    if _sq_is_light(wb_sq) == _sq_is_light(bb_sq):
        return False, None
    return True, {
        "white_bishop": chess.square_name(wb_sq),
        "black_bishop": chess.square_name(bb_sq),
        "evidence": (
            f"Opposite-colored bishops: White on {chess.square_name(wb_sq)}, "
            f"Black on {chess.square_name(bb_sq)}"
        ),
    }


def is_rook_on_seventh(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that this move places the mover's rook on the opponent's back rank
    (7th rank for White, 2nd rank for Black), the classic invasive-rook motif.
    evidence keys: square (landing square name), rank ('7th'/'2nd'), evidence.
    """
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK:
        return False, None
    seventh_rank = 6 if mover_color == chess.WHITE else 1
    if chess.square_rank(move.to_square) != seventh_rank:
        return False, None
    rank_label = "7th" if mover_color == chess.WHITE else "2nd"
    sq_name = chess.square_name(move.to_square)
    return True, {
        "square": sq_name,
        "rank": rank_label,
        "evidence": f"Rook invades the {rank_label} rank at {sq_name}",
    }


def captures_queen(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move captures the enemy queen. This tags the CAPTURE EVENT;
    whether it nets material depends on subsequent moves (use engine eval / material field).
    evidence keys: captured_at (square name), mover_piece (piece name), evidence.
    """
    captured = board_before.piece_at(move.to_square)
    if captured is None or captured.piece_type != chess.QUEEN or captured.color == mover_color:
        return False, None
    moving = board_before.piece_at(move.from_square)
    mover_name = PIECE_NAMES[moving.piece_type] if moving else "piece"
    sq_name = chess.square_name(move.to_square)
    return True, {
        "captured_at": sq_name,
        "mover_piece": mover_name,
        "evidence": f"{mover_name.capitalize()} captures the queen on {sq_name}",
    }


def pawn_on_seventh(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move advances a pawn to the mover's 7th rank (one step
    from promotion): rank 6 for White (a7-h7), rank 1 for Black (a2-h2).
    evidence keys: square, rank ('7th'/'2nd'), evidence.
    """
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN or piece.color != mover_color:
        return False, None
    seventh_rank = 6 if mover_color == chess.WHITE else 1
    if chess.square_rank(move.to_square) != seventh_rank:
        return False, None
    rank_label = "7th" if mover_color == chess.WHITE else "2nd"
    sq_name = chess.square_name(move.to_square)
    return True, {
        "square": sq_name,
        "rank": rank_label,
        "evidence": (
            f"Pawn advances to {sq_name} on the {rank_label} rank — "
            "promotion is one step away"
        ),
    }


def is_checkmate(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move delivers checkmate — the opponent's king is in check
    and has no legal moves. The game ends immediately.
    evidence keys: evidence (ready-to-quote string).
    """
    if not board_after.is_checkmate():
        return False, None
    return True, {
        "evidence": "Checkmate — the opponent's king is in check with no legal escape",
    }


_CORE_CENTER = frozenset({chess.D4, chess.D5, chess.E4, chess.E5})


def knight_centralized(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move places a knight on one of the four core central squares
    (d4, d5, e4, e5), the squares where a knight controls the maximum number of squares.
    Engine-free geometric fact; distinct from outpost (which requires pawn support).
    evidence keys: square (landing square name), evidence.
    """
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.KNIGHT:
        return False, None
    if move.to_square not in _CORE_CENTER:
        return False, None
    sq_name = chess.square_name(move.to_square)
    return True, {
        "square": sq_name,
        "evidence": f"Knight centralizes to {sq_name} — a core central square where it controls up to eight squares",
    }


def is_pawn_endgame(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that after the move, only kings and pawns remain on the board
    (the position has entered a pure pawn endgame). Requires at least one pawn.
    evidence keys: evidence (ready-to-quote string).
    """
    _MINOR_MAJOR = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    for color in (chess.WHITE, chess.BLACK):
        for piece_type in _MINOR_MAJOR:
            if board_after.pieces(piece_type, color):
                return False, None
    has_pawn = bool(
        board_after.pieces(chess.PAWN, chess.WHITE)
        or board_after.pieces(chess.PAWN, chess.BLACK)
    )
    if not has_pawn:
        return False, None
    return True, {
        "evidence": "Only kings and pawns remain — the position has entered a pawn endgame",
    }


def loses_exchange(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the mover's rook captures an enemy minor piece (bishop or knight)
    — the mover is giving up the exchange (~2-pawn material loss). Complement of wins_exchange.
    evidence keys: piece ('rook'), minor (piece name), minor_square, mover, evidence.
    """
    if board_before.is_en_passant(move):
        return False, None
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK or piece.color != mover_color:
        return False, None
    captured = board_before.piece_at(move.to_square)
    if captured is None or captured.piece_type not in (chess.BISHOP, chess.KNIGHT):
        return False, None
    if captured.color == mover_color:
        return False, None
    minor_name = PIECE_NAMES[captured.piece_type]
    sq_name = chess.square_name(move.to_square)
    mover_label = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "piece": "rook",
        "minor": minor_name,
        "minor_square": sq_name,
        "mover": mover_label,
        "evidence": (
            f"{mover_label} rook captures the {minor_name} on {sq_name} — "
            "giving up the exchange"
        ),
    }


def is_stalemate_move(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move results in stalemate — the opponent has no legal
    moves and is not in check, so the game is drawn immediately.
    evidence keys: evidence (ready-to-quote string).
    """
    if not board_after.is_stalemate():
        return False, None
    return True, {
        "evidence": (
            "Stalemate — the opponent has no legal moves and is not in check; "
            "the game is drawn"
        ),
    }


def is_double_check(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move gives a double check — two of the mover's pieces
    simultaneously attack the enemy king. Only a king move can escape double check.
    evidence keys: checking_squares (list of square names), evidence.
    """
    if not board_after.is_check():
        return False, None
    checkers = list(board_after.checkers())
    if len(checkers) < 2:
        return False, None
    sq_names = sorted([chess.square_name(sq) for sq in checkers])
    return True, {
        "checking_squares": sq_names,
        "evidence": (
            f"Double check from {sq_names[0]} and {sq_names[1]} — "
            "the king cannot block or interpose, only flee"
        ),
    }


def captures_hanging(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move captures an enemy piece that had zero defenders
    at the moment of capture. The capturing piece is removed from the board
    before counting defenders so that X-ray defenders are correctly revealed.
    Skips en passant (its own predicate handles that).
    evidence keys: captured (piece name), square, evidence.
    """
    if board_before.is_en_passant(move):
        return False, None
    captured = board_before.piece_at(move.to_square)
    if captured is None or captured.color == mover_color:
        return False, None
    defender_color = not mover_color
    probe = board_before.copy()
    probe.remove_piece_at(move.from_square)
    if probe.attackers(defender_color, move.to_square):
        return False, None
    piece_name = PIECE_NAMES[captured.piece_type]
    sq_name = chess.square_name(move.to_square)
    return True, {
        "captured": piece_name,
        "square": sq_name,
        "evidence": f"{piece_name.capitalize()} on {sq_name} was undefended — a free capture",
    }


def is_threefold_repetition(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that after this move the same position has occurred three times —
    the game is immediately drawn by threefold repetition. Uses python-chess's
    board.is_repetition(count=3) which checks the full move-stack history.
    evidence keys: evidence.
    """
    if not board_after.is_repetition(count=3):
        return False, None
    return True, {
        "evidence": (
            "This position has occurred three times — the game is drawn "
            "by threefold repetition"
        ),
    }


def is_rook_doubled(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move places a rook on a file already occupied by a
    friendly rook, creating doubled rooks — a classic coordination milestone.
    evidence keys: file (letter), mover ('White'/'Black'), evidence.
    """
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK:
        return False, None
    dest_file = chess.square_file(move.to_square)
    rooks_on_dest = [
        sq for sq in board_after.pieces(chess.ROOK, mover_color)
        if chess.square_file(sq) == dest_file
    ]
    if len(rooks_on_dest) < 2:
        return False, None
    file_letter = "abcdefgh"[dest_file]
    mover_label = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "file": file_letter,
        "mover": mover_label,
        "evidence": f"{mover_label} doubles the rooks on the {file_letter}-file",
    }


def captures_with_check(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies a move that captures an enemy piece AND gives check — the
    opponent must address the check before recovering material. En passant
    is excluded (covered by the en_passant tag).
    evidence keys: captured (piece name), square, piece (mover piece name), evidence.
    """
    if board_before.is_en_passant(move):
        return False, None
    captured = board_before.piece_at(move.to_square)
    if captured is None or captured.color == mover_color:
        return False, None
    if not board_after.is_check():
        return False, None
    moving = board_before.piece_at(move.from_square)
    mover_name = PIECE_NAMES[moving.piece_type] if moving else "piece"
    captured_name = PIECE_NAMES[captured.piece_type]
    sq_name = chess.square_name(move.to_square)
    return True, {
        "captured": captured_name,
        "square": sq_name,
        "piece": mover_name,
        "evidence": (
            f"{mover_name.capitalize()} captures the {captured_name} on {sq_name} "
            f"with check — the opponent must respond to the check before dealing "
            f"with the material loss"
        ),
    }


def is_royal_fork(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies the moved piece simultaneously gives check (attacks the enemy king)
    AND attacks the enemy queen from its landing square — a royal fork. The king must
    flee, leaving the queen to be taken next move.
    evidence keys: piece, piece_square, king_square, queen_square, evidence.
    """
    if not board_after.is_check():
        return False, None
    enemy_color = not mover_color
    enemy_queen_sqs = list(board_after.pieces(chess.QUEEN, enemy_color))
    if not enemy_queen_sqs:
        return False, None
    if move.to_square not in board_after.checkers():
        return False, None
    attacked = board_after.attacks(move.to_square)
    forked_queen_sqs = [sq for sq in enemy_queen_sqs if sq in attacked]
    if not forked_queen_sqs:
        return False, None
    piece = board_after.piece_at(move.to_square)
    piece_name = PIECE_NAMES[piece.piece_type] if piece else "piece"
    enemy_king_sq = board_after.king(enemy_color)
    king_sq_name = chess.square_name(enemy_king_sq) if enemy_king_sq is not None else "?"
    queen_sq_name = chess.square_name(forked_queen_sqs[0])
    dest_name = chess.square_name(move.to_square)
    return True, {
        "piece": piece_name,
        "piece_square": dest_name,
        "king_square": king_sq_name,
        "queen_square": queen_sq_name,
        "evidence": (
            f"{piece_name.capitalize()} on {dest_name} forks the king on "
            f"{king_sq_name} and the queen on {queen_sq_name} — "
            f"the king must move, leaving the queen to be taken"
        ),
    }


def is_queenless_position(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that this move removes the last queen from the board, creating
    a queenless position. Only fires on the move that causes the transition —
    returns False when the board was already queenless before.
    evidence keys: evidence.
    """
    queens_before = (
        board_before.pieces(chess.QUEEN, chess.WHITE)
        | board_before.pieces(chess.QUEEN, chess.BLACK)
    )
    if not queens_before:
        return False, None
    queens_after = (
        board_after.pieces(chess.QUEEN, chess.WHITE)
        | board_after.pieces(chess.QUEEN, chess.BLACK)
    )
    if queens_after:
        return False, None
    return True, {
        "evidence": (
            "The last queen has left the board — the position becomes queenless, "
            "where the king can become more active and endgame precision matters"
        ),
    }


def is_king_opposition(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the king move places the mover's king in direct opposition
    with the enemy king — same file or same rank with exactly one empty square
    between them (kings two squares apart). Diagonal opposition is not certified.
    Only fires when pawns exist, since opposition is strategically significant
    only in pawn endings.
    evidence keys: mover, mover_king, enemy_king, evidence.
    """
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.KING:
        return False, None
    wk = board_after.king(chess.WHITE)
    bk = board_after.king(chess.BLACK)
    if wk is None or bk is None:
        return False, None
    df = abs(chess.square_file(wk) - chess.square_file(bk))
    dr = abs(chess.square_rank(wk) - chess.square_rank(bk))
    if not ((df == 0 and dr == 2) or (dr == 0 and df == 2)):
        return False, None
    all_pawns = (
        board_after.pieces(chess.PAWN, chess.WHITE)
        | board_after.pieces(chess.PAWN, chess.BLACK)
    )
    if not all_pawns:
        return False, None
    enemy_color = not mover_color
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    mk_name = chess.square_name(board_after.king(mover_color))
    ek_name = chess.square_name(board_after.king(enemy_color))
    return True, {
        "mover": mover_name,
        "mover_king": mk_name,
        "enemy_king": ek_name,
        "evidence": (
            f"{mover_name} seizes the opposition — the kings stand face-to-face "
            f"on {mk_name} and {ek_name} with one square between them, forcing "
            f"the opponent's king to give way"
        ),
    }


def is_pawn_lever(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the move is a non-capturing pawn advance that sets up a
    pawn lever — after the move the pawn diagonally attacks an enemy pawn on an
    adjacent file. Levers drive pawn-structure changes and line-opening play.
    evidence keys: pawn, targets, mover, evidence.
    """
    if board_before.is_capture(move):
        return False, None
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN:
        return False, None
    dest_file = chess.square_file(move.to_square)
    dest_rank = chess.square_rank(move.to_square)
    enemy_color = not mover_color
    attack_rank = dest_rank + 1 if mover_color == chess.WHITE else dest_rank - 1
    if not 0 <= attack_rank <= 7:
        return False, None
    lever_sqs = []
    for df in (-1, 1):
        f = dest_file + df
        if 0 <= f <= 7:
            sq = chess.square(f, attack_rank)
            p = board_after.piece_at(sq)
            if p is not None and p.piece_type == chess.PAWN and p.color == enemy_color:
                lever_sqs.append(sq)
    if not lever_sqs:
        return False, None
    pawn_sq = chess.square_name(move.to_square)
    target_names = [chess.square_name(s) for s in lever_sqs]
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "pawn": pawn_sq,
        "targets": target_names,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s pawn on {pawn_sq} sets up a lever against "
            f"{' and '.join(target_names)} — "
            f"exchanging here would open lines for the major pieces"
        ),
    }


def has_connected_passers(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that this move creates a new connected-passer formation for the
    mover — two or more passed pawns on adjacent files that did not exist as a
    connected pair before the move. Only fires on the transition move.
    evidence keys: squares, mover, evidence.
    """
    def _passers(board: chess.Board, color: bool) -> List[int]:
        return [sq for sq in board.pieces(chess.PAWN, color) if is_passed_pawn(board, sq, color)]

    def _are_connected(sqs: List[int]) -> bool:
        if len(sqs) < 2:
            return False
        files = sorted({chess.square_file(sq) for sq in sqs})
        return any(files[i + 1] - files[i] == 1 for i in range(len(files) - 1))

    after_sqs = _passers(board_after, mover_color)
    if not _are_connected(after_sqs):
        return False, None

    before_sqs = _passers(board_before, mover_color)
    if _are_connected(before_sqs):
        return False, None  # already had connected passers; this move didn't create them

    files = sorted({chess.square_file(sq) for sq in after_sqs})
    conn_files: Set[int] = set()
    for i in range(len(files) - 1):
        if files[i + 1] - files[i] == 1:
            conn_files.update({files[i], files[i + 1]})
            break
    pair = [sq for sq in after_sqs if chess.square_file(sq) in conn_files][:2]
    pair_names = [chess.square_name(sq) for sq in pair]
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "squares": pair_names,
        "mover": mover_name,
        "evidence": (
            f"{mover_name} has connected passed pawns on "
            f"{pair_names[0]} and {pair_names[1]} — "
            f"two adjacent passers that advance together and are nearly unstoppable"
        ),
    }


def rook_behind_own_passer(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the rook just moved to a square directly behind one of
    the mover's own passed pawns on the same file — the Tarrasch rule, which
    maximises the passer's support while cutting off the enemy king.
    evidence keys: rook, pawn, file, mover, evidence.
    """
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK:
        return False, None
    dest_file = chess.square_file(move.to_square)
    dest_rank = chess.square_rank(move.to_square)
    for pawn_sq in board_after.pieces(chess.PAWN, mover_color):
        if chess.square_file(pawn_sq) != dest_file:
            continue
        pawn_rank = chess.square_rank(pawn_sq)
        # Rook must be BEHIND the pawn (lower rank for white, higher rank for black)
        if mover_color == chess.WHITE and dest_rank >= pawn_rank:
            continue
        if mover_color == chess.BLACK and dest_rank <= pawn_rank:
            continue
        if not is_passed_pawn(board_after, pawn_sq, mover_color):
            continue
        file_letter = "abcdefgh"[dest_file]
        mover_name = "White" if mover_color == chess.WHITE else "Black"
        return True, {
            "rook": chess.square_name(move.to_square),
            "pawn": chess.square_name(pawn_sq),
            "file": file_letter,
            "mover": mover_name,
            "evidence": (
                f"{mover_name}'s rook swings behind the passed pawn on "
                f"{chess.square_name(pawn_sq)} on the {file_letter}-file — "
                f"applying the Tarrasch rule: the rook drives the passer forward "
                f"while cutting off the enemy king"
            ),
        }
    return False, None


def is_opposite_side_castling(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    """Certifies that the mover just castled and the resulting position has
    both kings on opposite wings — one kingside (g-file + f-rook), one
    queenside (c-file + d-rook). Opposite-side castling sets the stage for
    mutual pawn storms and racing attacks.
    evidence keys: mover, mover_side, enemy_side, evidence.
    """
    if not board_before.is_castling(move):
        return False, None
    to_file = chess.square_file(move.to_square)
    if to_file == 6:
        mover_kingside = True
    elif to_file == 2:
        mover_kingside = False
    else:
        return False, None
    enemy_color = not mover_color
    enemy_king_sq = board_after.king(enemy_color)
    if enemy_king_sq is None:
        return False, None
    back_rank = 0 if enemy_color == chess.WHITE else 7
    if chess.square_rank(enemy_king_sq) != back_rank:
        return False, None
    enemy_file = chess.square_file(enemy_king_sq)
    if enemy_file == 6:
        # Check f-rook in place to confirm kingside castle
        f_sq = chess.square(5, back_rank)
        p = board_after.piece_at(f_sq)
        if p is None or p.piece_type != chess.ROOK or p.color != enemy_color:
            return False, None
        enemy_kingside = True
    elif enemy_file == 2:
        # Check d-rook in place to confirm queenside castle
        d_sq = chess.square(3, back_rank)
        p = board_after.piece_at(d_sq)
        if p is None or p.piece_type != chess.ROOK or p.color != enemy_color:
            return False, None
        enemy_kingside = False
    else:
        return False, None
    if mover_kingside == enemy_kingside:
        return False, None  # same-side castling
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    enemy_name = "Black" if mover_color == chess.WHITE else "White"
    mover_side = "kingside" if mover_kingside else "queenside"
    enemy_side = "kingside" if enemy_kingside else "queenside"
    return True, {
        "mover": mover_name,
        "mover_side": mover_side,
        "enemy_side": enemy_side,
        "evidence": (
            f"{mover_name} castles {mover_side} while {enemy_name} is on the "
            f"{enemy_side} — opposite-side castling sets the stage for mutual "
            f"pawn storms and a race between both attacks"
        ),
    }


def has_queen_centralization(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.QUEEN:
        return False, None
    _CENTRAL = frozenset({chess.D4, chess.D5, chess.E4, chess.E5})
    if move.to_square not in _CENTRAL:
        return False, None
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    queen_sq = chess.square_name(move.to_square)
    return True, {
        "queen_sq": queen_sq,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s queen centralises to {queen_sq} — "
            f"from the heart of the board the queen maximises its mobility "
            f"and bears simultaneously on all four flanks"
        ),
    }


def is_shelter_pawn_capture(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    if not board_before.is_capture(move):
        return False, None
    cap_sq = move.to_square
    captured = board_before.piece_at(cap_sq)
    if captured is None or captured.piece_type != chess.PAWN:
        return False, None
    enemy_color = not mover_color
    king_sq = board_after.king(enemy_color)
    if king_sq is None:
        return False, None
    k_file = chess.square_file(king_sq)
    k_rank = chess.square_rank(king_sq)
    p_file = chess.square_file(cap_sq)
    p_rank = chess.square_rank(cap_sq)
    if abs(p_file - k_file) > 1:
        return False, None
    if enemy_color == chess.WHITE:
        if not (k_rank <= p_rank <= k_rank + 2):
            return False, None
    else:
        if not (k_rank - 2 <= p_rank <= k_rank):
            return False, None
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    enemy_name = "Black" if mover_color == chess.WHITE else "White"
    pawn_sq_name = chess.square_name(cap_sq)
    king_sq_name = chess.square_name(king_sq)
    return True, {
        "mover": mover_name,
        "pawn_sq": pawn_sq_name,
        "king_sq": king_sq_name,
        "evidence": (
            f"{mover_name} captures the pawn on {pawn_sq_name} — "
            f"tearing open the shelter in front of {enemy_name}'s king on {king_sq_name}; "
            f"the king's cover is compromised and attacking lines may now be forced open"
        ),
    }


def has_diagonal_battery(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _queen_bishop_batteries(board: chess.Board, color: bool) -> Set[frozenset]:
        queens = list(board.pieces(chess.QUEEN, color))
        bishops = list(board.pieces(chess.BISHOP, color))
        result: Set[frozenset] = set()
        for q_sq in queens:
            qf, qr = chess.square_file(q_sq), chess.square_rank(q_sq)
            for b_sq in bishops:
                bf, br = chess.square_file(b_sq), chess.square_rank(b_sq)
                if abs(qf - bf) != abs(qr - br):
                    continue
                between = chess.SquareSet(chess.between(q_sq, b_sq))
                if any(board.piece_at(s) for s in between):
                    continue
                result.add(frozenset({q_sq, b_sq}))
        return result

    after_batteries = _queen_bishop_batteries(board_after, mover_color)
    if not after_batteries:
        return False, None
    before_batteries = _queen_bishop_batteries(board_before, mover_color)
    new_batteries = after_batteries - before_batteries
    if not new_batteries:
        return False, None

    pair = next(iter(new_batteries))
    sq1, sq2 = sorted(pair)
    p1 = board_after.piece_at(sq1)
    p2 = board_after.piece_at(sq2)
    if p1 is not None and p1.piece_type == chess.QUEEN:
        q_sq, b_sq = sq1, sq2
    else:
        q_sq, b_sq = sq2, sq1
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "queen_sq": chess.square_name(q_sq),
        "bishop_sq": chess.square_name(b_sq),
        "mover": mover_name,
        "evidence": (
            f"{mover_name} lines up a diagonal battery — "
            f"the queen on {chess.square_name(q_sq)} and bishop on {chess.square_name(b_sq)} "
            f"combine their firepower along the same diagonal"
        ),
    }


def is_rook_endgame(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    _MINOR_TYPES = (chess.QUEEN, chess.BISHOP, chess.KNIGHT)

    def _has_non_rook(board: chess.Board) -> bool:
        for color in (chess.WHITE, chess.BLACK):
            for pt in _MINOR_TYPES:
                if board.pieces(pt, color):
                    return True
        return False

    if _has_non_rook(board_after):
        return False, None
    if not _has_non_rook(board_before):
        return False, None  # Already in rook endgame; not a new transition
    # Must have at least one rook (else it's a pawn_endgame)
    if not (board_after.pieces(chess.ROOK, chess.WHITE) or board_after.pieces(chess.ROOK, chess.BLACK)):
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "evidence": (
            f"The position transitions to a rook endgame — "
            f"only kings, rooks, and pawns remain; "
            f"rook activity, king centralisation, and pawn structure now decide the outcome"
        ),
    }


def is_undermining(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    if not board_before.is_capture(move):
        return False, None
    cap_sq = move.to_square
    captured = board_before.piece_at(cap_sq)
    if captured is None:
        return False, None  # en passant guard: captured pawn is not at to_square
    enemy_color = not mover_color

    PIECE_VALUE = {
        chess.QUEEN: 9, chess.ROOK: 5, chess.BISHOP: 3,
        chess.KNIGHT: 3, chess.PAWN: 1, chess.KING: 0,
    }

    undermined: List[Tuple[int, chess.Piece]] = []
    for sq in board_before.attacks(cap_sq):
        target = board_before.piece_at(sq)
        if target is None or target.color != enemy_color or target.piece_type == chess.KING:
            continue
        if cap_sq not in board_before.attackers(enemy_color, sq):
            continue
        if not board_after.is_attacked_by(mover_color, sq):
            continue
        before_def = len(board_before.attackers(enemy_color, sq))
        after_def = len(board_after.attackers(enemy_color, sq))
        if after_def < before_def:
            undermined.append((sq, target))

    if not undermined:
        return False, None

    best_sq, best_piece = max(undermined, key=lambda x: PIECE_VALUE.get(x[1].piece_type, 0))
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    cap_piece_name = chess.piece_name(captured.piece_type)
    target_name = chess.piece_name(best_piece.piece_type)
    return True, {
        "mover": mover_name,
        "captured_sq": chess.square_name(cap_sq),
        "exposed_sq": chess.square_name(best_sq),
        "evidence": (
            f"{mover_name} takes the {cap_piece_name} on {chess.square_name(cap_sq)} — "
            f"removing the defender of the {target_name} on {chess.square_name(best_sq)} "
            f"and leaving it vulnerable to capture"
        ),
    }


def has_bishop_vs_knight(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _bvk_sides(board: chess.Board):
        wb = bool(board.pieces(chess.BISHOP, chess.WHITE))
        wn = bool(board.pieces(chess.KNIGHT, chess.WHITE))
        bb = bool(board.pieces(chess.BISHOP, chess.BLACK))
        bn = bool(board.pieces(chess.KNIGHT, chess.BLACK))
        if wb and not wn and bn and not bb:
            return (chess.WHITE, chess.BLACK)
        if bb and not bn and wn and not wb:
            return (chess.BLACK, chess.WHITE)
        return None

    after = _bvk_sides(board_after)
    if after is None:
        return False, None
    if _bvk_sides(board_before) is not None:
        return False, None

    bishop_side, knight_side = after
    b_name = "White" if bishop_side == chess.WHITE else "Black"
    n_name = "White" if knight_side == chess.WHITE else "Black"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "bishop_side": b_name,
        "knight_side": n_name,
        "mover": mover_name,
        "evidence": (
            f"{b_name} retains the bishop while {n_name} is left with the knight — "
            f"in open positions the bishop's long-range scope prevails; "
            f"in locked pawn structures the knight's agility shines"
        ),
    }


def is_king_active_endgame(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.KING:
        return False, None
    queens_after = (
        board_after.pieces(chess.QUEEN, chess.WHITE)
        | board_after.pieces(chess.QUEEN, chess.BLACK)
    )
    if queens_after:
        return False, None
    from_rank = chess.square_rank(move.from_square)
    to_rank = chess.square_rank(move.to_square)
    if mover_color == chess.WHITE:
        if to_rank <= from_rank:
            return False, None
    else:
        if to_rank >= from_rank:
            return False, None
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    king_sq = chess.square_name(move.to_square)
    return True, {
        "mover": mover_name,
        "king": king_sq,
        "evidence": (
            f"{mover_name}'s king marches forward to {king_sq} — "
            f"in the endgame the king is a fighting piece; "
            f"centralising it now creates threats and supports advancing pawns"
        ),
    }


def has_pawn_majority(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    QS_FILES = frozenset(range(4))    # a-d
    KS_FILES = frozenset(range(4, 8)) # e-h

    def _counts(board: chess.Board, color: bool):
        qs = sum(1 for sq in board.pieces(chess.PAWN, color) if chess.square_file(sq) in QS_FILES)
        ks = sum(1 for sq in board.pieces(chess.PAWN, color) if chess.square_file(sq) in KS_FILES)
        return qs, ks

    enemy_color = not mover_color
    m_qs_b, m_ks_b = _counts(board_before, mover_color)
    e_qs_b, e_ks_b = _counts(board_before, enemy_color)
    m_qs_a, m_ks_a = _counts(board_after, mover_color)
    e_qs_a, e_ks_a = _counts(board_after, enemy_color)

    new_qs = (m_qs_a > e_qs_a) and not (m_qs_b > e_qs_b)
    new_ks = (m_ks_a > e_ks_a) and not (m_ks_b > e_ks_b)

    if not (new_qs or new_ks):
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    if new_qs and new_ks:
        wing = "both wings"
        wing_detail = "queenside and kingside"
    elif new_qs:
        wing = "the queenside"
        wing_detail = "queenside (a–d files)"
    else:
        wing = "the kingside"
        wing_detail = "kingside (e–h files)"

    return True, {
        "mover": mover_name,
        "wing": wing_detail,
        "evidence": (
            f"{mover_name} has established a pawn majority on {wing} — "
            f"the extra pawn can be leveraged to create a passed pawn in the endgame"
        ),
    }


def has_passed_pawn_race(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _has_passer(board: chess.Board, color: bool) -> bool:
        enemy = not color
        for sq in board.pieces(chess.PAWN, color):
            f = chess.square_file(sq)
            r = chess.square_rank(sq)
            blocked = False
            for ep in board.pieces(chess.PAWN, enemy):
                ef = chess.square_file(ep)
                er = chess.square_rank(ep)
                if abs(ef - f) > 1:
                    continue
                if (color == chess.WHITE and er > r) or (color == chess.BLACK and er < r):
                    blocked = True
                    break
            if not blocked:
                return True
        return False

    after_w = _has_passer(board_after, chess.WHITE)
    after_b = _has_passer(board_after, chess.BLACK)
    if not (after_w and after_b):
        return False, None

    before_w = _has_passer(board_before, chess.WHITE)
    before_b = _has_passer(board_before, chess.BLACK)
    if before_w and before_b:
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "evidence": (
            f"Both sides now have a passed pawn — a mutual pawn race; "
            f"whoever queens first will seize a decisive material advantage"
        ),
    }


def has_castling_rights_forfeited(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    if board_before.is_castling(move):
        return False, None

    had_ks = board_before.has_kingside_castling_rights(mover_color)
    had_qs = board_before.has_queenside_castling_rights(mover_color)
    has_ks = board_after.has_kingside_castling_rights(mover_color)
    has_qs = board_after.has_queenside_castling_rights(mover_color)

    lost_ks = had_ks and not has_ks
    lost_qs = had_qs and not has_qs

    if not (lost_ks or lost_qs):
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    if lost_ks and lost_qs:
        lost_str = "kingside and queenside"
        side_str = "both sides"
    elif lost_ks:
        lost_str = "kingside"
        side_str = "the kingside"
    else:
        lost_str = "queenside"
        side_str = "the queenside"

    return True, {
        "mover": mover_name,
        "lost": lost_str,
        "evidence": (
            f"{mover_name} forfeits {side_str} castling rights — "
            f"the king can no longer find shelter via castling on the {lost_str}; "
            f"king safety now depends on the existing piece configuration"
        ),
    }


def is_bishop_on_long_diagonal(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.BISHOP:
        return False, None

    _A1H8 = frozenset({
        chess.A1, chess.B2, chess.C3, chess.D4,
        chess.E5, chess.F6, chess.G7, chess.H8,
    })
    _H1A8 = frozenset({
        chess.H1, chess.G2, chess.F3, chess.E4,
        chess.D5, chess.C6, chess.B7, chess.A8,
    })

    to_sq = move.to_square
    from_sq = move.from_square

    if to_sq in _A1H8:
        diag_name = "a1-h8"
    elif to_sq in _H1A8:
        diag_name = "h1-a8"
    else:
        return False, None

    if from_sq in _A1H8 or from_sq in _H1A8:
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {
        "square": sq_name,
        "diagonal": diag_name,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s bishop reaches {sq_name} on the {diag_name} long diagonal — "
            f"from this diagonal the bishop commands the full length of the board, "
            f"radiating pressure from corner to corner"
        ),
    }


def has_hanging_pawns(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _find_complexes(board: chess.Board, color: bool) -> Set[Tuple[int, int]]:
        pawns = list(board.pieces(chess.PAWN, color))
        all_pf = {chess.square_file(sq) for sq in pawns}
        result: Set[Tuple[int, int]] = set()
        for sq1 in pawns:
            f1, r1 = chess.square_file(sq1), chess.square_rank(sq1)
            for sq2 in pawns:
                f2, r2 = chess.square_file(sq2), chess.square_rank(sq2)
                if f2 != f1 + 1 or r1 != r2:
                    continue
                if (f1 - 1 >= 0 and (f1 - 1) in all_pf) or (f2 + 1 <= 7 and (f2 + 1) in all_pf):
                    continue
                result.add((f1, f2))
        return result

    after_cx = _find_complexes(board_after, mover_color)
    if not after_cx:
        return False, None
    before_cx = _find_complexes(board_before, mover_color)
    new_cx = after_cx - before_cx
    if not new_cx:
        return False, None

    f1, f2 = next(iter(new_cx))
    sq1 = next(
        sq for sq in board_after.pieces(chess.PAWN, mover_color)
        if chess.square_file(sq) == f1
    )
    sq2 = next(
        sq for sq in board_after.pieces(chess.PAWN, mover_color)
        if chess.square_file(sq) == f2
        and chess.square_rank(sq) == chess.square_rank(sq1)
    )
    n1, n2 = chess.square_name(sq1), chess.square_name(sq2)
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "squares": [n1, n2],
        "mover": mover_name,
        "evidence": (
            f"{mover_name} creates a hanging pawn complex on {n1} and {n2} — "
            f"the pair is isolated from all other friendly pawns, making them mobile and dynamic "
            f"but also a potential target if the position opens"
        ),
    }


def has_mobile_pawn_center(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    if mover_color == chess.WHITE:
        d_sq, e_sq = chess.D4, chess.E4
        center_desc = "d4 and e4"
    else:
        d_sq, e_sq = chess.D5, chess.E5
        center_desc = "d5 and e5"

    def _has_center(board: chess.Board) -> bool:
        pd = board.piece_at(d_sq)
        pe = board.piece_at(e_sq)
        return (
            pd is not None and pd.piece_type == chess.PAWN and pd.color == mover_color
            and pe is not None and pe.piece_type == chess.PAWN and pe.color == mover_color
        )

    if not _has_center(board_after):
        return False, None
    if _has_center(board_before):
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "evidence": (
            f"{mover_name} establishes a mobile pawn centre on {center_desc} — "
            f"two central pawns that claim the heart of the board, restrict the opponent's pieces, "
            f"and can advance to create space or open lines at the right moment"
        ),
    }


def has_rook_file_battery(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _file_batteries(board: chess.Board, color: bool) -> Set[int]:
        majors = (
            list(board.pieces(chess.ROOK, color))
            + list(board.pieces(chess.QUEEN, color))
        )
        batteries: Set[int] = set()
        for i, sq1 in enumerate(majors):
            for sq2 in majors[i + 1:]:
                if chess.square_file(sq1) != chess.square_file(sq2):
                    continue
                between = chess.SquareSet(chess.between(sq1, sq2))
                if not any(board.piece_at(s) for s in between):
                    batteries.add(chess.square_file(sq1))
        return batteries

    after_bats = _file_batteries(board_after, mover_color)
    if not after_bats:
        return False, None
    before_bats = _file_batteries(board_before, mover_color)
    new_bats = after_bats - before_bats
    if not new_bats:
        return False, None

    file_idx = next(iter(new_bats))
    file_letter = "abcdefgh"[file_idx]
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "file": file_letter,
        "mover": mover_name,
        "evidence": (
            f"{mover_name} lines up a battery of major pieces on the {file_letter}-file — "
            f"rooks or a rook and queen aligned without obstruction on the same file "
            f"concentrate their firepower and overwhelm any defence on that column"
        ),
    }


def has_pawn_duo(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _find_duos(board: chess.Board, color: bool) -> Set[frozenset]:
        pawn_squares = list(board.pieces(chess.PAWN, color))
        duos: Set[frozenset] = set()
        for sq1 in pawn_squares:
            f1, r1 = chess.square_file(sq1), chess.square_rank(sq1)
            for sq2 in pawn_squares:
                f2, r2 = chess.square_file(sq2), chess.square_rank(sq2)
                if r1 == r2 and abs(f1 - f2) == 1 and sq1 < sq2:
                    duos.add(frozenset({sq1, sq2}))
        return duos

    after_duos = _find_duos(board_after, mover_color)
    if not after_duos:
        return False, None
    before_duos = _find_duos(board_before, mover_color)
    new_duos = after_duos - before_duos
    if not new_duos:
        return False, None

    pair = next(iter(new_duos))
    sq1, sq2 = sorted(pair)
    names = [chess.square_name(sq1), chess.square_name(sq2)]
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "squares": names,
        "mover": mover_name,
        "evidence": (
            f"{mover_name} forms a pawn duo on {names[0]} and {names[1]} — "
            f"two connected pawns on the same rank that support each other "
            f"and control a broad front of squares"
        ),
    }


def has_knight_on_seventh(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.KNIGHT:
        return False, None
    to_sq = move.to_square
    target_rank = 6 if mover_color == chess.WHITE else 1
    if chess.square_rank(to_sq) != target_rank:
        return False, None
    if chess.square_rank(move.from_square) == target_rank:
        return False, None
    rank_name = "seventh" if mover_color == chess.WHITE else "second"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "rank": rank_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s knight leaps to the {rank_name} rank on {sq_name} — "
        f"deep in enemy territory, the knight threatens forks of rooks and king, "
        f"attacks pawns on the back rank, and is extremely difficult to dislodge "
        f"because the enemy king cannot safely approach without being forked"
    )}


def has_knight_on_fifth(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.KNIGHT:
        return False, None
    to_sq = move.to_square
    target_rank = 4 if mover_color == chess.WHITE else 3  # 0-indexed: rank 5=4, rank 4=3
    if chess.square_rank(to_sq) != target_rank:
        return False, None
    if chess.square_rank(move.from_square) == target_rank:
        return False, None
    rank_name = "fifth" if mover_color == chess.WHITE else "fourth"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "rank": rank_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s knight plants itself on the {rank_name} rank at {sq_name} — "
        f"an outpost in the heart of the board; from here the knight controls key squares "
        f"on both flanks, cannot easily be chased by enemy pawns, "
        f"and threatens to spring forward to even deeper penetration"
    )}


def has_two_rooks_vs_queen(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wr == 2 and wq == 0 and br == 0 and bq == 1:
            return "white_rooks"
        if br == 2 and bq == 0 and wr == 0 and wq == 1:
            return "black_rooks"
        return None

    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    rook_side = "White" if after == "white_rooks" else "Black"
    queen_side = "Black" if after == "white_rooks" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "rook_side": rook_side, "queen_side": queen_side, "mover": mover_name,
        "evidence": (
            f"The material crystallises into a classic two rooks vs. queen imbalance — "
            f"{rook_side} holds both rooks while {queen_side} relies on the lone queen; "
            f"in open positions with active rooks and open files this is roughly balanced, "
            f"but the coordinated rooks can dominate when they work together "
            f"or when the queen has no strong targets"
        ),
    }


def has_queen_vs_rook_and_minor(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        wm = wb + wn
        bm = bb + bn
        if wq == 1 and wr == 0 and wm == 0 and br == 1 and bm == 1 and bq == 0:
            return "white_queen"
        if bq == 1 and br == 0 and bm == 0 and wr == 1 and wm == 1 and wq == 0:
            return "black_queen"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    queen_side = "White" if after == "white_queen" else "Black"
    rook_side = "Black" if after == "white_queen" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "queen_side": queen_side, "rook_side": rook_side, "mover": mover_name,
        "evidence": (
            f"The material crystallises into a queen vs. rook-and-minor imbalance — "
            f"{queen_side} wields the queen while {rook_side} answers with rook and minor piece; "
            f"the queen typically outweighs this combination by a small margin, "
            f"though the rook-and-minor side gains practical chances in complex, tactical positions "
            f"or when the rook claims an open file and the minor piece finds a strong outpost"
        ),
    }


def has_rook_vs_two_minors(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        wm = wb + wn
        bm = bb + bn
        if wr == 1 and wq == 0 and wm == 0 and br == 0 and bq == 0 and bm == 2:
            return "white_rook"
        if br == 1 and bq == 0 and bm == 0 and wr == 0 and wq == 0 and wm == 2:
            return "black_rook"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    rook_side = "White" if after == "white_rook" else "Black"
    minor_side = "Black" if after == "white_rook" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "rook_side": rook_side, "minor_side": minor_side, "mover": mover_name,
        "evidence": (
            f"The position resolves into a rook vs. two minor pieces imbalance — "
            f"{rook_side} holds the lone rook while {minor_side} answers with two minor pieces; "
            f"theory gives two pieces a small edge over a single rook on average, "
            f"but the rook side earns real practical chances on open files, "
            f"and the outcome depends heavily on pawn structure and piece coordination"
        ),
    }


def has_queen_endgame(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _is_queen_endgame(board: chess.Board) -> bool:
        if not (board.pieces(chess.QUEEN, chess.WHITE) or board.pieces(chess.QUEEN, chess.BLACK)):
            return False
        if board.pieces(chess.ROOK, chess.WHITE) or board.pieces(chess.ROOK, chess.BLACK):
            return False
        if board.pieces(chess.BISHOP, chess.WHITE) or board.pieces(chess.BISHOP, chess.BLACK):
            return False
        if board.pieces(chess.KNIGHT, chess.WHITE) or board.pieces(chess.KNIGHT, chess.BLACK):
            return False
        return True
    if not _is_queen_endgame(board_after):
        return False, None
    if _is_queen_endgame(board_before):
        return False, None
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "evidence": (
            f"The game enters a queen endgame — only kings, queens, and pawns remain; "
            f"queen endgames are among the most technically demanding: "
            f"the queens' long-range power and checking ability give the defending side "
            f"persistent resources for a perpetual check, while the attacking queen must "
            f"coordinate with its king to convert a material or pawn advantage into a win; "
            f"precise calculation is essential, and many theoretically won positions "
            f"are saved by a timely perpetual"
        ),
    }


def has_rook_vs_bishop(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wr == 1 and wq == 0 and wb == 0 and wn == 0 and br == 0 and bq == 0 and bb == 1 and bn == 0:
            return "white_rook"
        if br == 1 and bq == 0 and bb == 0 and bn == 0 and wr == 0 and wq == 0 and wb == 1 and wn == 0:
            return "black_rook"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    rook_side = "White" if after == "white_rook" else "Black"
    bishop_side = "Black" if after == "white_rook" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "rook_side": rook_side, "bishop_side": bishop_side, "mover": mover_name,
        "evidence": (
            f"The material simplifies to a rook vs. bishop imbalance — "
            f"{rook_side} holds the rook while {bishop_side} relies on the lone bishop; "
            f"the rook is worth roughly two pawns more than a single bishop, "
            f"giving the rook side a tangible endgame advantage, "
            f"though the defending side can often draw by keeping the bishop active "
            f"and the position blocked against rook penetration"
        ),
    }


def has_rook_vs_knight(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wr == 1 and wq == 0 and wb == 0 and wn == 0 and br == 0 and bq == 0 and bb == 0 and bn == 1:
            return "white_rook"
        if br == 1 and bq == 0 and bb == 0 and bn == 0 and wr == 0 and wq == 0 and wb == 0 and wn == 1:
            return "black_rook"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    rook_side = "White" if after == "white_rook" else "Black"
    knight_side = "Black" if after == "white_rook" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "rook_side": rook_side, "knight_side": knight_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a rook vs. knight imbalance — "
            f"{rook_side} holds the rook while {knight_side} relies on the lone knight; "
            f"the rook carries a two-pawn material advantage on average, "
            f"but the knight's leaping ability makes it slippery to hunt down, "
            f"and in positions with fixed pawn chains the knight can frustrate the rook "
            f"by occupying strong outposts the rook cannot control"
        ),
    }


def has_two_bishops_vs_rook(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wb == 2 and wn == 0 and wq == 0 and wr == 0 and br == 1 and bn == 0 and bq == 0 and bb == 0:
            return "white_bishops"
        if bb == 2 and bn == 0 and bq == 0 and br == 0 and wr == 1 and wn == 0 and wq == 0 and wb == 0:
            return "black_bishops"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    bishop_side = "White" if after == "white_bishops" else "Black"
    rook_side = "Black" if after == "white_bishops" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "bishop_side": bishop_side, "rook_side": rook_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a two bishops vs. rook imbalance — "
            f"{bishop_side} wields the bishop pair while {rook_side} relies on the lone rook; "
            f"two bishops typically outweigh a rook by about half a pawn on average, "
            f"particularly in open positions where the bishops span both long diagonals; "
            f"the rook side earns practical compensation with active file control and "
            f"penetration, especially in positions where the bishops' diagonals are blocked"
        ),
    }


def has_two_knights_vs_rook(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wn == 2 and wb == 0 and wq == 0 and wr == 0 and br == 1 and bb == 0 and bq == 0 and bn == 0:
            return "white_knights"
        if bn == 2 and bb == 0 and bq == 0 and br == 0 and wr == 1 and wb == 0 and wq == 0 and wn == 0:
            return "black_knights"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    knight_side = "White" if after == "white_knights" else "Black"
    rook_side = "Black" if after == "white_knights" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "knight_side": knight_side, "rook_side": rook_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a two knights vs. rook imbalance — "
            f"{knight_side} wields the knight pair while {rook_side} relies on the lone rook; "
            f"two knights are typically worth slightly more than a rook but lack the rook's "
            f"long-range power and open-file dominance; the knight side excels in closed and "
            f"tactical positions where the knights can establish strong outposts, while the "
            f"rook side compensates with active play along open files and rank penetration"
        ),
    }


def has_queen_vs_rook(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wq == 1 and wr == 0 and wb == 0 and wn == 0 and bq == 0 and br == 1 and bb == 0 and bn == 0:
            return "white_queen"
        if bq == 1 and br == 0 and bb == 0 and bn == 0 and wq == 0 and wr == 1 and wb == 0 and wn == 0:
            return "black_queen"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    queen_side = "White" if after == "white_queen" else "Black"
    rook_side = "Black" if after == "white_queen" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "queen_side": queen_side, "rook_side": rook_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a queen vs. rook endgame — "
            f"{queen_side} holds the queen while {rook_side} relies on the lone rook; "
            f"the queen outvalues the rook by roughly two pawns in open positions, "
            f"but the rook side can exploit perpetual-check and fortress drawing resources "
            f"to neutralize the material edge; the queen side typically wins by centralizing "
            f"the king and advancing passed pawns while avoiding back-rank traps"
        ),
    }


def has_queen_vs_two_minors(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wq == 1 and wr == 0 and wb == 0 and wn == 0 and bq == 0 and br == 0 and (bb + bn) == 2:
            return "white_queen"
        if bq == 1 and br == 0 and bb == 0 and bn == 0 and wq == 0 and wr == 0 and (wb + wn) == 2:
            return "black_queen"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    queen_side = "White" if after == "white_queen" else "Black"
    minor_side = "Black" if after == "white_queen" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "queen_side": queen_side, "minor_side": minor_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a queen vs. two minor pieces imbalance — "
            f"{queen_side} wields the queen while {minor_side} relies on two minor pieces; "
            f"the queen typically edges out two minors by about half a pawn in open positions, "
            f"but two coordinated minors can be very difficult to fight in closed structures "
            f"where the queen's long-range power is limited; the queen side compensates with "
            f"tactical threats and passed-pawn support while the minor side seeks coordination"
        ),
    }


def has_rook_and_minor_vs_two_rooks(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wr == 1 and (wb + wn) == 1 and wq == 0 and br == 2 and bb == 0 and bn == 0 and bq == 0:
            return "white_rook_minor"
        if br == 1 and (bb + bn) == 1 and bq == 0 and wr == 2 and wb == 0 and wn == 0 and wq == 0:
            return "black_rook_minor"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    minor_rook_side = "White" if after == "white_rook_minor" else "Black"
    two_rook_side = "Black" if after == "white_rook_minor" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "minor_rook_side": minor_rook_side, "two_rook_side": two_rook_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a rook-and-minor vs. two rooks imbalance — "
            f"{minor_rook_side} holds a rook and a minor piece while {two_rook_side} "
            f"commands the rook pair; two rooks typically outweigh a rook-and-minor by about "
            f"one to two pawns, especially in open positions where rook coordination along "
            f"multiple files is decisive; the rook-and-minor side compensates through the "
            f"minor piece's outpost potential and tactical flexibility"
        ),
    }


def has_two_rooks_vs_minor_pair(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wr == 2 and wb == 0 and wn == 0 and wq == 0 and br == 0 and bq == 0 and (bb + bn) == 2:
            return "white_rooks"
        if br == 2 and bb == 0 and bn == 0 and bq == 0 and wr == 0 and wq == 0 and (wb + wn) == 2:
            return "black_rooks"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    two_rook_side = "White" if after == "white_rooks" else "Black"
    minor_pair_side = "Black" if after == "white_rooks" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "two_rook_side": two_rook_side, "minor_pair_side": minor_pair_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a two rooks vs. minor pair imbalance — "
            f"{two_rook_side} commands the rook pair while {minor_pair_side} relies on "
            f"two minor pieces; the rook pair typically outweighs two minors by one to two "
            f"pawns in open positions where dual file control is decisive, but the minor pair "
            f"compensates in closed structures through coordination and outpost control; "
            f"this tag fires specifically on the MOVE that created the clean 2R:2-minor imbalance"
        ),
    }


def has_queen_vs_bishop(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wq == 1 and wr == 0 and wb == 0 and wn == 0 and bq == 0 and br == 0 and bb == 1 and bn == 0:
            return "white_queen"
        if bq == 1 and br == 0 and bb == 0 and bn == 0 and wq == 0 and wr == 0 and wb == 1 and wn == 0:
            return "black_queen"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    queen_side = "White" if after == "white_queen" else "Black"
    bishop_side = "Black" if after == "white_queen" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "queen_side": queen_side, "bishop_side": bishop_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a queen vs. lone bishop endgame — "
            f"{queen_side} holds the queen while {bishop_side} relies on a single bishop; "
            f"the queen holds a commanding material advantage of roughly six pawns, but "
            f"the bishop side can use the bishop's diagonal control and the king's activity "
            f"to set up defensive fortresses or perpetual threats in certain pawn structures; "
            f"the queen side typically wins by coordinating king and queen to strip pawns"
        ),
    }


def has_queen_vs_knight(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        if wq == 1 and wr == 0 and wb == 0 and wn == 0 and bq == 0 and br == 0 and bb == 0 and bn == 1:
            return "white_queen"
        if bq == 1 and br == 0 and bb == 0 and bn == 0 and wq == 0 and wr == 0 and wb == 0 and wn == 1:
            return "black_queen"
        return None
    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    queen_side = "White" if after == "white_queen" else "Black"
    knight_side = "Black" if after == "white_queen" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "queen_side": queen_side, "knight_side": knight_side, "mover": mover_name,
        "evidence": (
            f"The material resolves into a queen vs. lone knight endgame — "
            f"{queen_side} holds the queen while {knight_side} relies on a single knight; "
            f"the queen holds a commanding material advantage of roughly six pawns, and "
            f"the knight's short-range leaping makes it particularly difficult to defend "
            f"against queen threats across all corners of the board; the queen side typically "
            f"converts by using king centralization and triangulation to trap the knight"
        ),
    }


def has_queen_and_minor_vs_two_rooks(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq=len(board.pieces(chess.QUEEN,chess.WHITE)); wr=len(board.pieces(chess.ROOK,chess.WHITE))
        wb=len(board.pieces(chess.BISHOP,chess.WHITE)); wn=len(board.pieces(chess.KNIGHT,chess.WHITE))
        bq=len(board.pieces(chess.QUEEN,chess.BLACK)); br=len(board.pieces(chess.ROOK,chess.BLACK))
        bb=len(board.pieces(chess.BISHOP,chess.BLACK)); bn=len(board.pieces(chess.KNIGHT,chess.BLACK))
        if wq==1 and wr==0 and (wb+wn)==1 and bq==0 and br==2 and bb==0 and bn==0: return "white_qm"
        if bq==1 and br==0 and (bb+bn)==1 and wq==0 and wr==2 and wb==0 and wn==0: return "black_qm"
        return None
    after=_state(board_after)
    if not after: return False, None
    before=_state(board_before)
    if before: return False, None
    queen_minor_side="White" if after=="white_qm" else "Black"
    two_rook_side="Black" if after=="white_qm" else "White"
    mover_name="White" if mover_color==chess.WHITE else "Black"
    return True, {
        "queen_minor_side": queen_minor_side,
        "two_rook_side": two_rook_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a queen-and-minor vs. two-rooks ending, "
            f"with {queen_minor_side} holding the queen and minor piece against "
            f"{two_rook_side}'s rook pair."
        ),
    }


def has_queen_and_rook_vs_two_rooks(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq=len(board.pieces(chess.QUEEN,chess.WHITE)); wr=len(board.pieces(chess.ROOK,chess.WHITE))
        wb=len(board.pieces(chess.BISHOP,chess.WHITE)); wn=len(board.pieces(chess.KNIGHT,chess.WHITE))
        bq=len(board.pieces(chess.QUEEN,chess.BLACK)); br=len(board.pieces(chess.ROOK,chess.BLACK))
        bb=len(board.pieces(chess.BISHOP,chess.BLACK)); bn=len(board.pieces(chess.KNIGHT,chess.BLACK))
        if wq==1 and wr==1 and wb==0 and wn==0 and bq==0 and br==2 and bb==0 and bn==0: return "white_qr"
        if bq==1 and br==1 and bb==0 and bn==0 and wq==0 and wr==2 and wb==0 and wn==0: return "black_qr"
        return None
    after=_state(board_after)
    if not after: return False, None
    before=_state(board_before)
    if before: return False, None
    queen_rook_side="White" if after=="white_qr" else "Black"
    two_rook_side="Black" if after=="white_qr" else "White"
    mover_name="White" if mover_color==chess.WHITE else "Black"
    return True, {
        "queen_rook_side": queen_rook_side,
        "two_rook_side": two_rook_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a queen-and-rook vs. two-rooks ending, "
            f"with {queen_rook_side} holding a decisive material advantage — "
            f"the queen dominates while the rook adds second-rank pressure against "
            f"{two_rook_side}'s rook pair."
        ),
    }


def has_rook_and_two_minors_vs_two_rooks(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq=len(board.pieces(chess.QUEEN,chess.WHITE)); wr=len(board.pieces(chess.ROOK,chess.WHITE))
        wb=len(board.pieces(chess.BISHOP,chess.WHITE)); wn=len(board.pieces(chess.KNIGHT,chess.WHITE))
        bq=len(board.pieces(chess.QUEEN,chess.BLACK)); br=len(board.pieces(chess.ROOK,chess.BLACK))
        bb=len(board.pieces(chess.BISHOP,chess.BLACK)); bn=len(board.pieces(chess.KNIGHT,chess.BLACK))
        if wr==1 and (wb+wn)==2 and wq==0 and br==2 and (bb+bn)==0 and bq==0: return "white_r2m"
        if br==1 and (bb+bn)==2 and bq==0 and wr==2 and (wb+wn)==0 and wq==0: return "black_r2m"
        return None
    after=_state(board_after)
    if not after: return False, None
    before=_state(board_before)
    if before: return False, None
    rook_minor_side="White" if after=="white_r2m" else "Black"
    two_rook_side="Black" if after=="white_r2m" else "White"
    mover_name="White" if mover_color==chess.WHITE else "Black"
    return True, {
        "rook_minor_side": rook_minor_side,
        "two_rook_side": two_rook_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a rook-and-two-minors vs. two-rooks ending, "
            f"with {rook_minor_side} holding a rook and minor-piece pair against "
            f"{two_rook_side}'s rook pair — a dynamic imbalance where the minor pieces "
            f"often compensate through outpost control and coordination."
        ),
    }


def has_queen_vs_three_minors(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq=len(board.pieces(chess.QUEEN,chess.WHITE)); wr=len(board.pieces(chess.ROOK,chess.WHITE))
        wb=len(board.pieces(chess.BISHOP,chess.WHITE)); wn=len(board.pieces(chess.KNIGHT,chess.WHITE))
        bq=len(board.pieces(chess.QUEEN,chess.BLACK)); br=len(board.pieces(chess.ROOK,chess.BLACK))
        bb=len(board.pieces(chess.BISHOP,chess.BLACK)); bn=len(board.pieces(chess.KNIGHT,chess.BLACK))
        if wq==1 and wr==0 and wb==0 and wn==0 and bq==0 and br==0 and (bb+bn)==3: return "white_queen"
        if bq==1 and br==0 and bb==0 and bn==0 and wq==0 and wr==0 and (wb+wn)==3: return "black_queen"
        return None
    after=_state(board_after)
    if not after: return False, None
    before=_state(board_before)
    if before: return False, None
    queen_side="White" if after=="white_queen" else "Black"
    three_minor_side="Black" if after=="white_queen" else "White"
    mover_name="White" if mover_color==chess.WHITE else "Black"
    return True, {
        "queen_side": queen_side,
        "three_minor_side": three_minor_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a queen vs. three-minor-pieces ending, "
            f"with {queen_side} relying on the queen's long-range power against "
            f"{three_minor_side}'s trio of minor pieces — a roughly balanced but complex "
            f"imbalance where the minor pieces often prevail in closed positions through "
            f"superior coordination and pawn-support."
        ),
    }


def has_two_rooks_vs_three_minors(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq=len(board.pieces(chess.QUEEN,chess.WHITE)); wr=len(board.pieces(chess.ROOK,chess.WHITE))
        wb=len(board.pieces(chess.BISHOP,chess.WHITE)); wn=len(board.pieces(chess.KNIGHT,chess.WHITE))
        bq=len(board.pieces(chess.QUEEN,chess.BLACK)); br=len(board.pieces(chess.ROOK,chess.BLACK))
        bb=len(board.pieces(chess.BISHOP,chess.BLACK)); bn=len(board.pieces(chess.KNIGHT,chess.BLACK))
        if wr==2 and wb==0 and wn==0 and wq==0 and bq==0 and br==0 and (bb+bn)==3: return "white_rooks"
        if br==2 and bb==0 and bn==0 and bq==0 and wq==0 and wr==0 and (wb+wn)==3: return "black_rooks"
        return None
    after=_state(board_after)
    if not after: return False, None
    before=_state(board_before)
    if before: return False, None
    two_rook_side="White" if after=="white_rooks" else "Black"
    three_minor_side="Black" if after=="white_rooks" else "White"
    mover_name="White" if mover_color==chess.WHITE else "Black"
    return True, {
        "two_rook_side": two_rook_side,
        "three_minor_side": three_minor_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a two-rooks vs. three-minor-pieces ending, "
            f"with {two_rook_side}'s rook pair facing {three_minor_side}'s trio of minor pieces — "
            f"the rooks typically prevail on open files while three coordinated minors "
            f"can outperform in closed, fortified positions."
        ),
    }


def has_queen_vs_two_rooks_and_minor(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq=len(board.pieces(chess.QUEEN,chess.WHITE)); wr=len(board.pieces(chess.ROOK,chess.WHITE))
        wb=len(board.pieces(chess.BISHOP,chess.WHITE)); wn=len(board.pieces(chess.KNIGHT,chess.WHITE))
        bq=len(board.pieces(chess.QUEEN,chess.BLACK)); br=len(board.pieces(chess.ROOK,chess.BLACK))
        bb=len(board.pieces(chess.BISHOP,chess.BLACK)); bn=len(board.pieces(chess.KNIGHT,chess.BLACK))
        if wq==1 and wr==0 and wb==0 and wn==0 and bq==0 and br==2 and (bb+bn)==1: return "white_queen"
        if bq==1 and br==0 and bb==0 and bn==0 and wq==0 and wr==2 and (wb+wn)==1: return "black_queen"
        return None
    after=_state(board_after)
    if not after: return False, None
    before=_state(board_before)
    if before: return False, None
    queen_side="White" if after=="white_queen" else "Black"
    two_rook_minor_side="Black" if after=="white_queen" else "White"
    mover_name="White" if mover_color==chess.WHITE else "Black"
    return True, {
        "queen_side": queen_side,
        "two_rook_minor_side": two_rook_minor_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a queen vs. two-rooks-and-minor ending, "
            f"with {queen_side} facing a material deficit — the rook pair plus minor piece "
            f"typically outweighs a lone queen, especially with active rooks and a supported "
            f"minor piece on {two_rook_minor_side}'s side."
        ),
    }


def has_three_minors_vs_rook(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq=len(board.pieces(chess.QUEEN,chess.WHITE)); wr=len(board.pieces(chess.ROOK,chess.WHITE))
        wb=len(board.pieces(chess.BISHOP,chess.WHITE)); wn=len(board.pieces(chess.KNIGHT,chess.WHITE))
        bq=len(board.pieces(chess.QUEEN,chess.BLACK)); br=len(board.pieces(chess.ROOK,chess.BLACK))
        bb=len(board.pieces(chess.BISHOP,chess.BLACK)); bn=len(board.pieces(chess.KNIGHT,chess.BLACK))
        if wr==0 and (wb+wn)==3 and wq==0 and bq==0 and br==1 and bb==0 and bn==0: return "white_minors"
        if br==0 and (bb+bn)==3 and bq==0 and wq==0 and wr==1 and wb==0 and wn==0: return "black_minors"
        return None
    after=_state(board_after)
    if not after: return False, None
    before=_state(board_before)
    if before: return False, None
    three_minor_side="White" if after=="white_minors" else "Black"
    rook_side="Black" if after=="white_minors" else "White"
    mover_name="White" if mover_color==chess.WHITE else "Black"
    return True, {
        "three_minor_side": three_minor_side,
        "rook_side": rook_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a three-minor-pieces vs. lone-rook ending, "
            f"with {three_minor_side}'s trio of minor pieces enjoying a significant material "
            f"advantage over {rook_side}'s single rook — three coordinated minor pieces "
            f"typically dominate a lone rook and should convert the advantage decisively."
        ),
    }


def has_queen_and_rook_vs_queen(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq=len(board.pieces(chess.QUEEN,chess.WHITE)); wr=len(board.pieces(chess.ROOK,chess.WHITE))
        wb=len(board.pieces(chess.BISHOP,chess.WHITE)); wn=len(board.pieces(chess.KNIGHT,chess.WHITE))
        bq=len(board.pieces(chess.QUEEN,chess.BLACK)); br=len(board.pieces(chess.ROOK,chess.BLACK))
        bb=len(board.pieces(chess.BISHOP,chess.BLACK)); bn=len(board.pieces(chess.KNIGHT,chess.BLACK))
        if wq==1 and wr==1 and wb==0 and wn==0 and bq==1 and br==0 and bb==0 and bn==0: return "white_qr"
        if bq==1 and br==1 and bb==0 and bn==0 and wq==1 and wr==0 and wb==0 and wn==0: return "black_qr"
        return None
    after=_state(board_after)
    if not after: return False, None
    before=_state(board_before)
    if before: return False, None
    queen_rook_side="White" if after=="white_qr" else "Black"
    lone_queen_side="Black" if after=="white_qr" else "White"
    mover_name="White" if mover_color==chess.WHITE else "Black"
    return True, {
        "queen_rook_side": queen_rook_side,
        "lone_queen_side": lone_queen_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a queen-and-rook vs. lone-queen ending, "
            f"with {queen_rook_side} holding a decisive material advantage — the extra rook "
            f"gives {queen_rook_side} a winning advantage that {lone_queen_side}'s queen alone "
            f"cannot match without perpetual check or immediate fortress resources."
        ),
    }


def has_queen_and_minor_vs_queen(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board):
        wq = len(board.pieces(chess.QUEEN, chess.WHITE))
        wr = len(board.pieces(chess.ROOK, chess.WHITE))
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        bq = len(board.pieces(chess.QUEEN, chess.BLACK))
        br = len(board.pieces(chess.ROOK, chess.BLACK))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        if wq == 1 and wr == 0 and (wb + wn) == 1 and bq == 1 and br == 0 and bb == 0 and bn == 0:
            return "white_qm"
        if bq == 1 and br == 0 and (bb + bn) == 1 and wq == 1 and wr == 0 and wb == 0 and wn == 0:
            return "black_qm"
        return None

    state_after = _state(board_after)
    if state_after is None:
        return False, None
    if _state(board_before) is not None:
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    if state_after == "white_qm":
        queen_minor_side = "White"
        lone_queen_side = "Black"
    else:
        queen_minor_side = "Black"
        lone_queen_side = "White"

    return True, {
        "queen_minor_side": queen_minor_side,
        "lone_queen_side": lone_queen_side,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s move creates a queen-and-minor vs. lone-queen ending, "
            f"with {queen_minor_side} holding queen plus a minor piece against {lone_queen_side}'s "
            f"lone queen — the extra piece gives {queen_minor_side} a lasting initiative that "
            f"{lone_queen_side} must neutralise with precise defence."
        ),
    }


def has_rook_on_fifth(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK:
        return False, None
    to_sq = move.to_square
    target_rank = 4 if mover_color == chess.WHITE else 3  # 0-indexed: rank 5=4, rank 4=3
    if chess.square_rank(to_sq) != target_rank:
        return False, None
    if chess.square_rank(move.from_square) == target_rank:
        return False, None
    rank_name = "fifth" if mover_color == chess.WHITE else "fourth"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "rank": rank_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s rook advances to the {rank_name} rank on {sq_name} — "
        f"a strong positional posting in the opponent's half of the board; "
        f"from here the rook controls the rank, supports passed-pawn advances, "
        f"and is well placed for a further push to the sixth or seventh rank"
    )}


def has_bishop_on_seventh(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.BISHOP:
        return False, None
    to_sq = move.to_square
    target_rank = 6 if mover_color == chess.WHITE else 1  # 0-indexed: rank 7=6, rank 2=1
    if chess.square_rank(to_sq) != target_rank:
        return False, None
    if chess.square_rank(move.from_square) == target_rank:
        return False, None
    rank_name = "seventh" if mover_color == chess.WHITE else "second"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "rank": rank_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s bishop sweeps deep to the {rank_name} rank on {sq_name} — "
        f"from this advanced post the bishop bears diagonally on the enemy back rank, "
        f"harasses pawns from behind, and joins the attack alongside rooks or queens "
        f"that may already be penetrating the position"
    )}


def has_pawn_on_fifth(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN:
        return False, None
    to_sq = move.to_square
    target_rank = 4 if mover_color == chess.WHITE else 3  # 0-indexed: rank 5=4, rank 4=3
    if chess.square_rank(to_sq) != target_rank:
        return False, None
    if chess.square_rank(move.from_square) == target_rank:
        return False, None
    rank_name = "fifth" if mover_color == chess.WHITE else "fourth"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "rank": rank_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s pawn crosses into the opponent's half of the board, "
        f"arriving on the {rank_name} rank at {sq_name} — "
        f"the pawn has now staked territory in enemy ground and begins to exert "
        f"concrete pressure, restricting the opponent's piece mobility and "
        f"setting the stage for a deeper advance toward promotion"
    )}


def has_bishop_centralized(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.BISHOP:
        return False, None
    if move.to_square not in _CORE_CENTER:
        return False, None
    sq_name = chess.square_name(move.to_square)
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {"square": sq_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s bishop centralises to {sq_name} — "
        f"from a core central square the bishop bears simultaneously on both long diagonals "
        f"spanning the board, maximising its reach and coordinating with pieces on either wing"
    )}


def has_two_bishops_vs_two_knights(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _state(board: chess.Board) -> Optional[str]:
        wb = len(board.pieces(chess.BISHOP, chess.WHITE))
        wn = len(board.pieces(chess.KNIGHT, chess.WHITE))
        bb = len(board.pieces(chess.BISHOP, chess.BLACK))
        bn = len(board.pieces(chess.KNIGHT, chess.BLACK))
        if wb == 2 and wn == 0 and bb == 0 and bn == 2:
            return "white_bishops"
        if bb == 2 and bn == 0 and wb == 0 and wn == 2:
            return "black_bishops"
        return None

    after = _state(board_after)
    if not after:
        return False, None
    before = _state(board_before)
    if before:
        return False, None
    bishop_side = "White" if after == "white_bishops" else "Black"
    knight_side = "Black" if after == "white_bishops" else "White"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "bishop_side": bishop_side, "knight_side": knight_side, "mover": mover_name,
        "evidence": (
            f"The position crystallises into a classic bishop-pair vs knight-pair imbalance — "
            f"{bishop_side} holds both bishops while {knight_side} has both knights; "
            f"in open positions the bishops' long diagonals dominate, "
            f"in closed positions the knights' leaping ability gives the edge"
        ),
    }


def has_pawn_on_sixth(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN:
        return False, None
    to_sq = move.to_square
    target_rank = 5 if mover_color == chess.WHITE else 2
    if chess.square_rank(to_sq) != target_rank:
        return False, None
    if chess.square_rank(move.from_square) == target_rank:
        return False, None
    rank_name = "sixth" if mover_color == chess.WHITE else "third"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "rank": rank_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s pawn storms to the {rank_name} rank on {sq_name} — "
        f"deep in enemy territory and only one step from the seventh, "
        f"the pawn creates concrete promotion threats and forces the opponent "
        f"to commit pieces to stopping it"
    )}


def has_king_centralized(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.KING:
        return False, None
    to_sq = move.to_square
    if chess.square_file(to_sq) not in (3, 4) or chess.square_rank(to_sq) not in (3, 4):
        return False, None
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s king reaches the heart of the board on {sq_name} — "
        f"from this central stronghold the king controls all four quadrants, "
        f"escorts passed pawns in any direction, and applies maximum pressure "
        f"on both wings simultaneously"
    )}


def has_queen_on_back_rank(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.QUEEN:
        return False, None
    to_sq = move.to_square
    target_rank = 7 if mover_color == chess.WHITE else 0
    if chess.square_rank(to_sq) != target_rank:
        return False, None
    if chess.square_rank(move.from_square) == target_rank:
        return False, None
    rank_name = "eighth" if mover_color == chess.WHITE else "first"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "rank": rank_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s queen storms all the way to the {rank_name} rank on {sq_name} — "
        f"the deepest possible invasion; from the back rank the queen controls both the "
        f"rank and its diagonals simultaneously, threatening back-rank mates, cutting off "
        f"the enemy king, and supporting promotion from behind"
    )}


def has_outside_passed_pawn(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _is_passed(board: chess.Board, sq: int, color: bool) -> bool:
        f = chess.square_file(sq)
        r = chess.square_rank(sq)
        opp = not color
        for osq in board.pieces(chess.PAWN, opp):
            of = chess.square_file(osq)
            if abs(of - f) <= 1:
                orr = chess.square_rank(osq)
                if color == chess.WHITE and orr > r:
                    return False
                if color == chess.BLACK and orr < r:
                    return False
        return True

    def _outside_passers(board: chess.Board, color: bool) -> List[int]:
        return [
            sq for sq in board.pieces(chess.PAWN, color)
            if chess.square_file(sq) in (0, 7) and _is_passed(board, sq, color)
        ]

    after = _outside_passers(board_after, mover_color)
    if not after:
        return False, None
    before = _outside_passers(board_before, mover_color)
    if before:
        return False, None
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(after[0])
    file_name = "a" if chess.square_file(after[0]) == 0 else "h"
    return True, {
        "square": sq_name, "file": file_name, "mover": mover_name,
        "evidence": (
            f"{mover_name} creates an outside passed pawn on the {file_name}-file at {sq_name} — "
            f"a wing passer that forces the opponent's king to the edge of the board, "
            f"freeing the mover's king and pieces to operate in the centre or on the other wing"
        ),
    }


def has_queen_on_sixth(
    board_before: chess.Board, move: chess.Move, board_after: chess.Board, mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.QUEEN:
        return False, None
    to_sq = move.to_square
    target_rank = 5 if mover_color == chess.WHITE else 2
    if chess.square_rank(to_sq) != target_rank:
        return False, None
    if chess.square_rank(move.from_square) == target_rank:
        return False, None
    rank_name = "sixth" if mover_color == chess.WHITE else "third"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {"square": sq_name, "rank": rank_name, "mover": mover_name, "evidence": (
        f"{mover_name}'s queen advances to the {rank_name} rank on {sq_name} — "
        f"deep in enemy territory, the queen commands both the rank and its diagonals, "
        f"creating threats that require immediate attention and setting up potential "
        f"invasions further into the opponent's position"
    )}


def has_rook_on_back_rank(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK:
        return False, None

    to_sq = move.to_square
    target_rank = 7 if mover_color == chess.WHITE else 0  # 8th rank idx=7; 1st rank idx=0

    if chess.square_rank(to_sq) != target_rank:
        return False, None

    if chess.square_rank(move.from_square) == target_rank:
        return False, None

    rank_name = "eighth" if mover_color == chess.WHITE else "first"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {
        "square": sq_name,
        "rank": rank_name,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s rook penetrates all the way to the {rank_name} rank on {sq_name} — "
            f"the ultimate invasion; from the back rank the rook can sweep the entire length "
            f"of the file, threaten back-rank mates, and support promotion of a passed pawn "
            f"from behind the enemy lines"
        ),
    }


def has_queen_on_seventh(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.QUEEN:
        return False, None

    to_sq = move.to_square
    target_rank = 6 if mover_color == chess.WHITE else 1  # 7th rank idx=6; 2nd rank idx=1

    if chess.square_rank(to_sq) != target_rank:
        return False, None

    if chess.square_rank(move.from_square) == target_rank:
        return False, None

    rank_name = "seventh" if mover_color == chess.WHITE else "second"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {
        "square": sq_name,
        "rank": rank_name,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s queen penetrates to the {rank_name} rank on {sq_name} — "
            f"commanding rank and diagonal simultaneously, the queen on the seventh "
            f"threatens enemy pawns, supports a back-rank invasion, "
            f"and is more resilient than a rook there since it cannot easily be traded away"
        ),
    }


def has_minor_piece_endgame(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _is_mixed_minor_endgame(board: chess.Board) -> bool:
        for color in [chess.WHITE, chess.BLACK]:
            for pt in [chess.ROOK, chess.QUEEN]:
                if board.pieces(pt, color):
                    return False
        has_knight = False
        has_bishop = False
        for color in [chess.WHITE, chess.BLACK]:
            if board.pieces(chess.KNIGHT, color):
                has_knight = True
            if board.pieces(chess.BISHOP, color):
                has_bishop = True
        return has_knight and has_bishop

    if not _is_mixed_minor_endgame(board_after):
        return False, None
    if _is_mixed_minor_endgame(board_before):
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "evidence": (
            f"The position enters a minor-piece endgame — no rooks or queens remain, "
            f"and both knights and bishops are still on the board; "
            f"the interplay between colour-bound bishops and colour-leaping knights "
            f"creates rich imbalances, and pawn structure (open diagonals for bishops, "
            f"fixed pawns for knights) will determine whose minor piece is the stronger"
        ),
    }


def has_knight_endgame(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _is_knight_endgame(board: chess.Board) -> bool:
        for color in [chess.WHITE, chess.BLACK]:
            for pt in [chess.ROOK, chess.QUEEN, chess.BISHOP]:
                if board.pieces(pt, color):
                    return False
        for color in [chess.WHITE, chess.BLACK]:
            if board.pieces(chess.KNIGHT, color):
                return True
        return False

    if not _is_knight_endgame(board_after):
        return False, None
    if _is_knight_endgame(board_before):
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "evidence": (
            f"The position enters a knight endgame — only kings, knights, and pawns remain; "
            f"knight endgames are notoriously tricky: the knight's leaping ability "
            f"lets it attack squares of both colours simultaneously, "
            f"king-knight coordination is essential for escorting passers to promotion, "
            f"and the knight's slow tempo makes it poor at gaining the opposition"
        ),
    }


def has_bishop_endgame(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _is_bishop_endgame(board: chess.Board) -> bool:
        for color in [chess.WHITE, chess.BLACK]:
            for pt in [chess.ROOK, chess.QUEEN, chess.KNIGHT]:
                if board.pieces(pt, color):
                    return False
        for color in [chess.WHITE, chess.BLACK]:
            if board.pieces(chess.BISHOP, color):
                return True
        return False

    if not _is_bishop_endgame(board_after):
        return False, None
    if _is_bishop_endgame(board_before):
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "evidence": (
            f"The position enters a bishop endgame — only kings, bishops, and pawns remain; "
            f"bishop endgames are sensitive to pawn colour (pawns on the same colour "
            f"as the bishop cramp its mobility), opposite-coloured bishops carry a "
            f"strong drawing tendency, and same-colour bishop endings hinge on "
            f"king activity and pawn breaks"
        ),
    }


def has_knight_on_sixth(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.KNIGHT:
        return False, None

    to_sq = move.to_square
    target_rank = 5 if mover_color == chess.WHITE else 2  # 0-indexed: rank 6=5, rank 3=2

    if chess.square_rank(to_sq) != target_rank:
        return False, None

    if chess.square_rank(move.from_square) == target_rank:
        return False, None

    rank_name = "sixth" if mover_color == chess.WHITE else "third"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)
    return True, {
        "square": sq_name,
        "rank": rank_name,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s knight leaps to the {rank_name} rank on {sq_name} — "
            f"deep in enemy territory, the knight attacks key squares and pieces "
            f"from a forward post and is often difficult to dislodge once established"
        ),
    }


def has_knight_on_rim(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.KNIGHT:
        return False, None

    to_file = chess.square_file(move.to_square)
    if to_file not in (0, 7):
        return False, None

    if chess.square_file(move.from_square) in (0, 7):
        return False, None

    file_letter = "a" if to_file == 0 else "h"
    sq_name = chess.square_name(move.to_square)
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "square": sq_name,
        "file": file_letter,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s knight lands on the rim at {sq_name} — "
            f"on the {file_letter}-file it controls at most four squares, "
            f"half its usual reach; a knight on the rim is typically passive "
            f"and may need several tempi to re-enter the game"
        ),
    }


def has_open_center(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _center_open(board: chess.Board) -> bool:
        for color in [chess.WHITE, chess.BLACK]:
            for sq in board.pieces(chess.PAWN, color):
                if chess.square_file(sq) in (3, 4):  # d=3, e=4
                    return False
        return True

    if not _center_open(board_after):
        return False, None
    if _center_open(board_before):
        return False, None

    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "evidence": (
            f"{mover_name} opens the centre — both the d and e files are now clear of all pawns; "
            f"with no central pawns to restrict them, pieces gain maximum mobility, "
            f"rooks can penetrate along open files, and king safety becomes urgent "
            f"in a position where the board has suddenly opened up"
        ),
    }


def has_rook_on_sixth(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK:
        return False, None

    to_sq = move.to_square
    target_rank = 5 if mover_color == chess.WHITE else 2  # 0-indexed: rank 6=idx5, rank 3=idx2

    if chess.square_rank(to_sq) != target_rank:
        return False, None

    if chess.square_rank(move.from_square) == target_rank:
        return False, None

    rank_name = "sixth" if mover_color == chess.WHITE else "third"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    sq_name = chess.square_name(to_sq)

    return True, {
        "square": sq_name,
        "rank": rank_name,
        "mover": mover_name,
        "evidence": (
            f"{mover_name}'s rook advances to the {rank_name} rank on {sq_name} — "
            f"deep in enemy territory, the rook attacks enemy pawns from the side, "
            f"restricts the opponent's king, and can swing along the rank "
            f"to wherever the position demands"
        ),
    }


def has_tripled_pawns(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _find_tripled(board: chess.Board, color: bool) -> Set[int]:
        file_counts: dict = {}
        for sq in board.pieces(chess.PAWN, color):
            f = chess.square_file(sq)
            file_counts[f] = file_counts.get(f, 0) + 1
        return {f for f, cnt in file_counts.items() if cnt >= 3}

    after_tripled = _find_tripled(board_after, mover_color)
    if not after_tripled:
        return False, None
    before_tripled = _find_tripled(board_before, mover_color)
    new_tripled = after_tripled - before_tripled
    if not new_tripled:
        return False, None

    file_idx = next(iter(new_tripled))
    file_letter = "abcdefgh"[file_idx]
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "file": file_letter,
        "mover": mover_name,
        "evidence": (
            f"{mover_name} creates tripled pawns on the {file_letter}-file — "
            f"three pawns stacked on the same file; a severe structural concession "
            f"since they cannot defend each other and the file yields no passed-pawn potential"
        ),
    }


def has_isolated_queen_pawn(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _is_iqp(board: chess.Board, color: bool) -> bool:
        d_sq = chess.D4 if color == chess.WHITE else chess.D5
        pd = board.piece_at(d_sq)
        if pd is None or pd.piece_type != chess.PAWN or pd.color != color:
            return False
        for sq in board.pieces(chess.PAWN, color):
            f = chess.square_file(sq)
            if f == 2 or f == 4:  # c-file=2, e-file=4
                return False
        return True

    if not _is_iqp(board_after, mover_color):
        return False, None
    if _is_iqp(board_before, mover_color):
        return False, None

    d_sq_name = "d4" if mover_color == chess.WHITE else "d5"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "square": d_sq_name,
        "mover": mover_name,
        "evidence": (
            f"{mover_name} acquires an isolated queen's pawn on {d_sq_name} — "
            f"a central pawn with no friendly pawns on the c or e files to support it; "
            f"a dynamic middlegame asset that radiates piece activity but becomes "
            f"a long-term endgame liability if it cannot advance"
        ),
    }


def has_seventh_rank_battery(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Tuple[bool, Optional[dict]]:
    def _seventh_rank_battery(board: chess.Board, color: bool) -> bool:
        rank = 6 if color == chess.WHITE else 1
        majors = (
            list(board.pieces(chess.ROOK, color))
            + list(board.pieces(chess.QUEEN, color))
        )
        on_rank = [sq for sq in majors if chess.square_rank(sq) == rank]
        if len(on_rank) < 2:
            return False
        for i, sq1 in enumerate(on_rank):
            for sq2 in on_rank[i + 1:]:
                between = chess.SquareSet(chess.between(sq1, sq2))
                if not any(board.piece_at(s) for s in between):
                    return True
        return False

    if not _seventh_rank_battery(board_after, mover_color):
        return False, None
    if _seventh_rank_battery(board_before, mover_color):
        return False, None

    rank_name = "seventh" if mover_color == chess.WHITE else "second"
    mover_name = "White" if mover_color == chess.WHITE else "Black"
    return True, {
        "mover": mover_name,
        "rank": rank_name,
        "evidence": (
            f"{mover_name} doubles major pieces on the {rank_name} rank — "
            f"the classic 'pigs on the seventh' — creating devastating pressure "
            f"on the enemy pawns and a constant back-rank mating threat"
        ),
    }


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
    "discovered_attack",
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
    "backward_pawn",
    "infiltration",
    "fianchetto",
    "zugzwang",
    "overloaded_piece",
    "compensation",
    "tempo_gain",
    "weak_square",
    "zwischenzug",
    "initiative",
    "space_advantage",
    "prophylaxis",
    "bishop_pair",
    "rook_on_open_file",
    "desperado",
    "connected_rooks",
    "file_opened",
    "half_open_file",
    "promotion",
    "en_passant",
    "castling",
    "passer_created",
    "wins_exchange",
    "opposite_colored_bishops",
    "rook_on_seventh",
    "captures_hanging",
    "double_check",
    "stalemate_move",
    "loses_exchange",
    "pawn_endgame",
    "knight_centralized",
    "checkmate",
    "pawn_on_seventh",
    "captures_queen",
    "royal_fork",
    "captures_with_check",
    "rook_doubled",
    "threefold_repetition",
    "queenless_position",
    "king_opposition",
    "pawn_lever",
    "connected_passers",
    "rook_behind_passer",
    "opposite_side_castling",
    "pawn_majority",
    "king_active_endgame",
    "bishop_vs_knight",
    "undermining",
    "rook_endgame",
    "diagonal_battery",
    "shelter_pawn_capture",
    "queen_centralization",
    "pawn_duo",
    "rook_file_battery",
    "mobile_pawn_center",
    "hanging_pawns",
    "bishop_long_diagonal",
    "castling_rights_forfeited",
    "passed_pawn_race",
    "seventh_rank_battery",
    "isolated_queen_pawn",
    "knight_on_seventh",
    "knight_on_fifth",
    "bishop_centralized",
    "pawn_on_fifth",
    "bishop_on_seventh",
    "rook_on_fifth",
    "two_rooks_vs_queen",
    "queen_vs_rook_and_minor",
    "rook_vs_two_minors",
    "queen_endgame",
    "rook_vs_bishop",
    "rook_vs_knight",
    "two_bishops_vs_rook",
    "two_knights_vs_rook",
    "queen_vs_rook",
    "queen_vs_two_minors",
    "rook_and_minor_vs_two_rooks",
    "two_rooks_vs_minor_pair",
    "queen_vs_bishop",
    "queen_vs_knight",
    "queen_and_minor_vs_two_rooks",
    "queen_and_rook_vs_two_rooks",
    "rook_and_two_minors_vs_two_rooks",
    "queen_vs_three_minors",
    "two_rooks_vs_three_minors",
    "queen_vs_two_rooks_and_minor",
    "three_minors_vs_rook",
    "queen_and_rook_vs_queen",
    "queen_and_minor_vs_queen",
    "two_bishops_vs_two_knights",
    "pawn_on_sixth",
    "king_centralized",
    "queen_on_back_rank",
    "outside_passed_pawn",
    "queen_on_sixth",
    "rook_on_back_rank",
    "queen_on_seventh",
    "minor_piece_endgame",
    "knight_endgame",
    "bishop_endgame",
    "knight_on_sixth",
    "knight_on_rim",
    "open_center",
    "rook_on_sixth",
    "tripled_pawns",
)
# (The `rook_on_open_file` tag certifies a specific rook's standing position — distinct
# from the packet-level open_files / half_open_for_white / half_open_for_black fields,
# which state which files are open. This tag gates the piece-level claim.)


def certified_claims(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
    phase: str = "middlegame",
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

    da = _safe(
        lambda: creates_discovered_attack(board_before, move, board_after, mover_color)
    )
    if da and da[0]:
        tags.add("discovered_attack")

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

    bp = _safe(lambda: is_backward_pawn(board_after, move.to_square, mover_color))
    if bp and bp[0]:
        tags.add("backward_pawn")

    inf = _safe(lambda: is_infiltration(board_after, move.to_square, mover_color, phase))
    if inf and inf[0]:
        tags.add("infiltration")

    for col in (chess.WHITE, chess.BLACK):
        fz = _safe(lambda c=col: is_fianchetto(board_after, c))
        if fz and fz[0]:
            tags.add("fianchetto")

    ov = _safe(lambda: creates_overloaded(board_after))
    if ov is not None:
        tags.add("overloaded_piece")

    ws = _safe(lambda: detect_weak_square(board_after, move, mover_color))
    if ws is not None:
        tags.add("weak_square")

    zw = _safe(lambda: is_zwischenzug(board_before, move, board_after, mover_color))
    if zw is not None:
        tags.add("zwischenzug")

    sa = _safe(lambda: detect_space_advantage(board_after, mover_color))
    if sa is not None:
        tags.add("space_advantage")

    ph = _safe(lambda: is_prophylaxis(board_before, move, board_after, mover_color))
    if ph is not None:
        tags.add("prophylaxis")

    bpair = _safe(lambda: is_bishop_pair(board_after, mover_color))
    if bpair and bpair[0]:
        tags.add("bishop_pair")

    for _rsq in board_after.pieces(chess.ROOK, mover_color):
        rof = _safe(lambda sq=_rsq: is_rook_on_open_file(board_after, sq, mover_color))
        if rof and rof[0]:
            tags.add("rook_on_open_file")
            break

    desp = _safe(lambda: is_desperado(board_before, move, board_after))
    if desp and desp[0]:
        tags.add("desperado")

    cr = _safe(lambda: is_connected_rooks(board_after, mover_color))
    if cr and cr[0]:
        tags.add("connected_rooks")

    fo = _safe(lambda: creates_open_file(board_before, move, board_after, mover_color))
    if fo and fo[0]:
        tags.add("file_opened")

    hof = _safe(lambda: creates_half_open_file(board_before, move, board_after, mover_color))
    if hof and hof[0]:
        tags.add("half_open_file")

    prm = _safe(lambda: is_promotion(board_before, move, board_after))
    if prm and prm[0]:
        tags.add("promotion")

    ep = _safe(lambda: is_en_passant(board_before, move, board_after))
    if ep and ep[0]:
        tags.add("en_passant")

    cst = _safe(lambda: is_castling(board_before, move, board_after))
    if cst and cst[0]:
        tags.add("castling")

    ps = _safe(lambda: creates_passer(board_before, move, board_after, mover_color))
    if ps and ps[0]:
        tags.add("passer_created")

    we = _safe(lambda: wins_exchange(board_before, move, board_after))
    if we and we[0]:
        tags.add("wins_exchange")

    ocb = _safe(lambda: is_opposite_bishops(board_after))
    if ocb and ocb[0]:
        tags.add("opposite_colored_bishops")

    r7 = _safe(lambda: is_rook_on_seventh(board_before, move, board_after, mover_color))
    if r7 and r7[0]:
        tags.add("rook_on_seventh")

    ch = _safe(lambda: captures_hanging(board_before, move, board_after, mover_color))
    if ch and ch[0]:
        tags.add("captures_hanging")

    dc = _safe(lambda: is_double_check(board_before, move, board_after, mover_color))
    if dc and dc[0]:
        tags.add("double_check")

    sm = _safe(lambda: is_stalemate_move(board_before, move, board_after, mover_color))
    if sm and sm[0]:
        tags.add("stalemate_move")

    le = _safe(lambda: loses_exchange(board_before, move, board_after, mover_color))
    if le and le[0]:
        tags.add("loses_exchange")

    peg = _safe(lambda: is_pawn_endgame(board_before, move, board_after, mover_color))
    if peg and peg[0]:
        tags.add("pawn_endgame")

    kc = _safe(lambda: knight_centralized(board_before, move, board_after, mover_color))
    if kc and kc[0]:
        tags.add("knight_centralized")

    cm = _safe(lambda: is_checkmate(board_before, move, board_after, mover_color))
    if cm and cm[0]:
        tags.add("checkmate")

    p7 = _safe(lambda: pawn_on_seventh(board_before, move, board_after, mover_color))
    if p7 and p7[0]:
        tags.add("pawn_on_seventh")

    cq = _safe(lambda: captures_queen(board_before, move, board_after, mover_color))
    if cq and cq[0]:
        tags.add("captures_queen")

    rf = _safe(lambda: is_royal_fork(board_before, move, board_after, mover_color))
    if rf and rf[0]:
        tags.add("royal_fork")

    cwc = _safe(lambda: captures_with_check(board_before, move, board_after, mover_color))
    if cwc and cwc[0]:
        tags.add("captures_with_check")

    rdbl = _safe(lambda: is_rook_doubled(board_before, move, board_after, mover_color))
    if rdbl and rdbl[0]:
        tags.add("rook_doubled")

    tfr = _safe(lambda: is_threefold_repetition(board_before, move, board_after, mover_color))
    if tfr and tfr[0]:
        tags.add("threefold_repetition")

    qls = _safe(lambda: is_queenless_position(board_before, move, board_after, mover_color))
    if qls and qls[0]:
        tags.add("queenless_position")

    ko = _safe(lambda: is_king_opposition(board_before, move, board_after, mover_color))
    if ko and ko[0]:
        tags.add("king_opposition")

    pl = _safe(lambda: is_pawn_lever(board_before, move, board_after, mover_color))
    if pl and pl[0]:
        tags.add("pawn_lever")

    cp = _safe(lambda: has_connected_passers(board_before, move, board_after, mover_color))
    if cp and cp[0]:
        tags.add("connected_passers")

    rbp = _safe(lambda: rook_behind_own_passer(board_before, move, board_after, mover_color))
    if rbp and rbp[0]:
        tags.add("rook_behind_passer")

    osc = _safe(lambda: is_opposite_side_castling(board_before, move, board_after, mover_color))
    if osc and osc[0]:
        tags.add("opposite_side_castling")

    pm = _safe(lambda: has_pawn_majority(board_before, move, board_after, mover_color))
    if pm and pm[0]:
        tags.add("pawn_majority")

    kae = _safe(lambda: is_king_active_endgame(board_before, move, board_after, mover_color))
    if kae and kae[0]:
        tags.add("king_active_endgame")

    bvk = _safe(lambda: has_bishop_vs_knight(board_before, move, board_after, mover_color))
    if bvk and bvk[0]:
        tags.add("bishop_vs_knight")

    und = _safe(lambda: is_undermining(board_before, move, board_after, mover_color))
    if und and und[0]:
        tags.add("undermining")

    re_ = _safe(lambda: is_rook_endgame(board_before, move, board_after, mover_color))
    if re_ and re_[0]:
        tags.add("rook_endgame")

    db = _safe(lambda: has_diagonal_battery(board_before, move, board_after, mover_color))
    if db and db[0]:
        tags.add("diagonal_battery")

    spc = _safe(lambda: is_shelter_pawn_capture(board_before, move, board_after, mover_color))
    if spc and spc[0]:
        tags.add("shelter_pawn_capture")

    qc = _safe(lambda: has_queen_centralization(board_before, move, board_after, mover_color))
    if qc and qc[0]:
        tags.add("queen_centralization")

    pd = _safe(lambda: has_pawn_duo(board_before, move, board_after, mover_color))
    if pd and pd[0]:
        tags.add("pawn_duo")

    rfb = _safe(lambda: has_rook_file_battery(board_before, move, board_after, mover_color))
    if rfb and rfb[0]:
        tags.add("rook_file_battery")

    mpc = _safe(lambda: has_mobile_pawn_center(board_before, move, board_after, mover_color))
    if mpc and mpc[0]:
        tags.add("mobile_pawn_center")

    hpw = _safe(lambda: has_hanging_pawns(board_before, move, board_after, mover_color))
    if hpw and hpw[0]:
        tags.add("hanging_pawns")

    bld = _safe(lambda: is_bishop_on_long_diagonal(board_before, move, board_after, mover_color))
    if bld and bld[0]:
        tags.add("bishop_long_diagonal")

    crf = _safe(lambda: has_castling_rights_forfeited(board_before, move, board_after, mover_color))
    if crf and crf[0]:
        tags.add("castling_rights_forfeited")

    ppr = _safe(lambda: has_passed_pawn_race(board_before, move, board_after, mover_color))
    if ppr and ppr[0]:
        tags.add("passed_pawn_race")

    s7b = _safe(lambda: has_seventh_rank_battery(board_before, move, board_after, mover_color))
    if s7b and s7b[0]:
        tags.add("seventh_rank_battery")

    iqp = _safe(lambda: has_isolated_queen_pawn(board_before, move, board_after, mover_color))
    if iqp and iqp[0]:
        tags.add("isolated_queen_pawn")

    kn7 = _safe(lambda: has_knight_on_seventh(board_before, move, board_after, mover_color))
    if kn7 and kn7[0]:
        tags.add("knight_on_seventh")

    kn5 = _safe(lambda: has_knight_on_fifth(board_before, move, board_after, mover_color))
    if kn5 and kn5[0]:
        tags.add("knight_on_fifth")

    bisc = _safe(lambda: has_bishop_centralized(board_before, move, board_after, mover_color))
    if bisc and bisc[0]:
        tags.add("bishop_centralized")

    pp5 = _safe(lambda: has_pawn_on_fifth(board_before, move, board_after, mover_color))
    if pp5 and pp5[0]:
        tags.add("pawn_on_fifth")

    bo7 = _safe(lambda: has_bishop_on_seventh(board_before, move, board_after, mover_color))
    if bo7 and bo7[0]:
        tags.add("bishop_on_seventh")

    ro5 = _safe(lambda: has_rook_on_fifth(board_before, move, board_after, mover_color))
    if ro5 and ro5[0]:
        tags.add("rook_on_fifth")

    trvq = _safe(lambda: has_two_rooks_vs_queen(board_before, move, board_after, mover_color))
    if trvq and trvq[0]:
        tags.add("two_rooks_vs_queen")

    qvrm = _safe(lambda: has_queen_vs_rook_and_minor(board_before, move, board_after, mover_color))
    if qvrm and qvrm[0]:
        tags.add("queen_vs_rook_and_minor")

    rvtm = _safe(lambda: has_rook_vs_two_minors(board_before, move, board_after, mover_color))
    if rvtm and rvtm[0]:
        tags.add("rook_vs_two_minors")

    qeg = _safe(lambda: has_queen_endgame(board_before, move, board_after, mover_color))
    if qeg and qeg[0]:
        tags.add("queen_endgame")

    rvb = _safe(lambda: has_rook_vs_bishop(board_before, move, board_after, mover_color))
    if rvb and rvb[0]:
        tags.add("rook_vs_bishop")

    rvk = _safe(lambda: has_rook_vs_knight(board_before, move, board_after, mover_color))
    if rvk and rvk[0]:
        tags.add("rook_vs_knight")

    tbvr = _safe(lambda: has_two_bishops_vs_rook(board_before, move, board_after, mover_color))
    if tbvr and tbvr[0]:
        tags.add("two_bishops_vs_rook")

    tkvr = _safe(lambda: has_two_knights_vs_rook(board_before, move, board_after, mover_color))
    if tkvr and tkvr[0]:
        tags.add("two_knights_vs_rook")

    qvr = _safe(lambda: has_queen_vs_rook(board_before, move, board_after, mover_color))
    if qvr and qvr[0]:
        tags.add("queen_vs_rook")

    qvtm = _safe(lambda: has_queen_vs_two_minors(board_before, move, board_after, mover_color))
    if qvtm and qvtm[0]:
        tags.add("queen_vs_two_minors")

    rmvtr = _safe(lambda: has_rook_and_minor_vs_two_rooks(board_before, move, board_after, mover_color))
    if rmvtr and rmvtr[0]:
        tags.add("rook_and_minor_vs_two_rooks")

    trvmp = _safe(lambda: has_two_rooks_vs_minor_pair(board_before, move, board_after, mover_color))
    if trvmp and trvmp[0]:
        tags.add("two_rooks_vs_minor_pair")

    qvb = _safe(lambda: has_queen_vs_bishop(board_before, move, board_after, mover_color))
    if qvb and qvb[0]:
        tags.add("queen_vs_bishop")

    qvk = _safe(lambda: has_queen_vs_knight(board_before, move, board_after, mover_color))
    if qvk and qvk[0]:
        tags.add("queen_vs_knight")

    qmvtr = _safe(lambda: has_queen_and_minor_vs_two_rooks(board_before, move, board_after, mover_color))
    if qmvtr and qmvtr[0]:
        tags.add("queen_and_minor_vs_two_rooks")

    qrv2r = _safe(lambda: has_queen_and_rook_vs_two_rooks(board_before, move, board_after, mover_color))
    if qrv2r and qrv2r[0]:
        tags.add("queen_and_rook_vs_two_rooks")

    r2mv2r = _safe(lambda: has_rook_and_two_minors_vs_two_rooks(board_before, move, board_after, mover_color))
    if r2mv2r and r2mv2r[0]:
        tags.add("rook_and_two_minors_vs_two_rooks")

    qv3m = _safe(lambda: has_queen_vs_three_minors(board_before, move, board_after, mover_color))
    if qv3m and qv3m[0]:
        tags.add("queen_vs_three_minors")

    trvtm = _safe(lambda: has_two_rooks_vs_three_minors(board_before, move, board_after, mover_color))
    if trvtm and trvtm[0]:
        tags.add("two_rooks_vs_three_minors")

    qv2rm = _safe(lambda: has_queen_vs_two_rooks_and_minor(board_before, move, board_after, mover_color))
    if qv2rm and qv2rm[0]:
        tags.add("queen_vs_two_rooks_and_minor")

    tmvr = _safe(lambda: has_three_minors_vs_rook(board_before, move, board_after, mover_color))
    if tmvr and tmvr[0]:
        tags.add("three_minors_vs_rook")

    qrvq = _safe(lambda: has_queen_and_rook_vs_queen(board_before, move, board_after, mover_color))
    if qrvq and qrvq[0]:
        tags.add("queen_and_rook_vs_queen")

    qmvq = _safe(lambda: has_queen_and_minor_vs_queen(board_before, move, board_after, mover_color))
    if qmvq and qmvq[0]:
        tags.add("queen_and_minor_vs_queen")

    tbvtk = _safe(lambda: has_two_bishops_vs_two_knights(board_before, move, board_after, mover_color))
    if tbvtk and tbvtk[0]:
        tags.add("two_bishops_vs_two_knights")

    po6 = _safe(lambda: has_pawn_on_sixth(board_before, move, board_after, mover_color))
    if po6 and po6[0]:
        tags.add("pawn_on_sixth")

    kingc = _safe(lambda: has_king_centralized(board_before, move, board_after, mover_color))
    if kingc and kingc[0]:
        tags.add("king_centralized")

    qbr = _safe(lambda: has_queen_on_back_rank(board_before, move, board_after, mover_color))
    if qbr and qbr[0]:
        tags.add("queen_on_back_rank")

    opp = _safe(lambda: has_outside_passed_pawn(board_before, move, board_after, mover_color))
    if opp and opp[0]:
        tags.add("outside_passed_pawn")

    qo6 = _safe(lambda: has_queen_on_sixth(board_before, move, board_after, mover_color))
    if qo6 and qo6[0]:
        tags.add("queen_on_sixth")

    rob = _safe(lambda: has_rook_on_back_rank(board_before, move, board_after, mover_color))
    if rob and rob[0]:
        tags.add("rook_on_back_rank")

    q7 = _safe(lambda: has_queen_on_seventh(board_before, move, board_after, mover_color))
    if q7 and q7[0]:
        tags.add("queen_on_seventh")

    mpe = _safe(lambda: has_minor_piece_endgame(board_before, move, board_after, mover_color))
    if mpe and mpe[0]:
        tags.add("minor_piece_endgame")

    keg = _safe(lambda: has_knight_endgame(board_before, move, board_after, mover_color))
    if keg and keg[0]:
        tags.add("knight_endgame")

    beg = _safe(lambda: has_bishop_endgame(board_before, move, board_after, mover_color))
    if beg and beg[0]:
        tags.add("bishop_endgame")

    kn6 = _safe(lambda: has_knight_on_sixth(board_before, move, board_after, mover_color))
    if kn6 and kn6[0]:
        tags.add("knight_on_sixth")

    knr = _safe(lambda: has_knight_on_rim(board_before, move, board_after, mover_color))
    if knr and knr[0]:
        tags.add("knight_on_rim")

    oc = _safe(lambda: has_open_center(board_before, move, board_after, mover_color))
    if oc and oc[0]:
        tags.add("open_center")

    ro6 = _safe(lambda: has_rook_on_sixth(board_before, move, board_after, mover_color))
    if ro6 and ro6[0]:
        tags.add("rook_on_sixth")

    tpw = _safe(lambda: has_tripled_pawns(board_before, move, board_after, mover_color))
    if tpw and tpw[0]:
        tags.add("tripled_pawns")

    return tags
