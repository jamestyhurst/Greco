"""
Stockfish-driven analysis of a PGN game.

For every move we record what the engine thought the best continuation was,
how much (in centipawns) the played move lost relative to that, top
alternatives, mate scores, and a phase label (opening/middlegame/endgame).
"""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import chess
import chess.engine
import chess.pgn


def open_engine(engine_path: str, retries: int = 3, timeout: float = 20.0):
    """
    Launch Stockfish with a generous handshake timeout and a couple of retries.
    On a busy machine the UCI handshake can exceed python-chess's default 10s and
    raise TimeoutError; retrying clears the occasional transient failure.
    """
    last_exc = None
    for attempt in range(retries):
        try:
            return chess.engine.SimpleEngine.popen_uci(engine_path, timeout=timeout)
        except Exception as exc:  # TimeoutError, EngineTerminatedError, etc.
            last_exc = exc
            time.sleep(1.0)
    raise RuntimeError(
        f"Could not start the chess engine after {retries} attempts: {last_exc}"
    )

MATE_SCORE = 100_000


@dataclass
class MoveAnalysis:
    ply: int
    move_number: int
    side: str  # 'White' or 'Black'
    san: str
    uci: str
    fen_before: str
    fen_after: str
    eval_before_cp: Optional[int]   # from White's POV; None when a mate score applies
    mate_before: Optional[int]
    eval_after_cp: Optional[int]
    mate_after: Optional[int]
    best_move_san: str
    best_move_uci: str
    best_pv_san: str                # principal variation in SAN, up to 5 plies
    cp_loss: int                    # centipawns lost relative to the engine's best, from the mover's POV
    top_alternatives: List[Dict[str, Any]] = field(default_factory=list)
    legal_move_count: int = 0
    is_forced: bool = False
    is_only_good_move: bool = False  # large gap between best and 2nd best
    is_capture: bool = False
    is_check: bool = False
    is_castle: bool = False
    is_promotion: bool = False
    phase: str = "middlegame"
    classification: str = "good"    # 'best' | 'good' | 'inaccuracy' | 'mistake' | 'blunder' | 'forced'
    # --- Material & board-truth facts (so the narrator never has to guess) ---
    captured_piece: Optional[str] = None   # e.g. 'knight' if this move captured one, else None
    is_recapture: bool = False             # True only if this captures on the square the opponent just captured on
    best_is_recapture: bool = False        # whether the ENGINE'S best move would be a recapture (for accurate alt commentary)
    material_balance: float = 0.0          # pawns, White-positive, AFTER this move
    open_files: List[str] = field(default_factory=list)        # files with no pawns of either color
    half_open_white: List[str] = field(default_factory=list)   # files where White has no pawn but Black does
    half_open_black: List[str] = field(default_factory=list)   # files where Black has no pawn but White does
    double_attack: Optional[str] = None        # ground-truth fork/double-attack created by the move played
    best_move_double_attack: Optional[str] = None  # same, for the engine's preferred move
    is_sacrifice: bool = False                 # a SOUND sacrifice: invests material via a good move, eval still favors the mover
    is_brilliant: bool = False                 # a substantial sound sacrifice played as the best/near-best move (Chess.com "!!"-style)
    sacrifice_invested: float = 0.0            # pawns of material given up, from the mover's POV
    mobility_notes: List[str] = field(default_factory=list)  # escape-square / trappable-piece facts
    allows_fork: Optional[str] = None          # this move lets the opponent play a pawn-fork against the mover's pieces
    is_unsound_sacrifice: bool = False         # gave up material (>=2) with NO compensation — a speculative/intimidation sac
    least_active_piece: Optional[str] = None   # the mover's most passive minor piece, if stuck
    tactic_setup: Optional[str] = None         # a pin/skewer the mover has lined up (king+queen on a rook's line)
    attacks_pieces: List[str] = field(default_factory=list)  # enemy pieces the moved piece actually attacks (so the model can't invent "kicks the knight")
    doubled_pawns_created: Optional[str] = None  # this move newly doubled someone's pawns
    overloaded_defender: Optional[str] = None    # an overworked sole-defender on the board after this move
    still_winning: bool = False                # mover was decisively winning both before and after (so a slow move isn't a "mistake")


@dataclass
class GameAnalysis:
    headers: Dict[str, str]
    moves: List[MoveAnalysis]
    result: str
    final_eval_cp: Optional[int]
    final_mate: Optional[int]


def score_to_cp_mate(score) -> Tuple[Optional[int], Optional[int]]:
    """Return (centipawns, mate). Exactly one will be non-None."""
    if score.is_mate():
        return None, score.mate()
    return score.score(), None


def normalize_cp(cp: Optional[int], mate: Optional[int]) -> int:
    """Collapse (cp, mate) to a single signed integer suitable for comparison."""
    if mate is not None:
        if mate == 0:
            # The side to move is already checkmated.
            return -MATE_SCORE
        return MATE_SCORE - mate if mate > 0 else -MATE_SCORE - mate
    return cp if cp is not None else 0


def detect_phase(board: chess.Board, ply: int) -> str:
    values = {chess.QUEEN: 9, chess.ROOK: 5, chess.BISHOP: 3, chess.KNIGHT: 3}
    total = 0
    for piece_type, value in values.items():
        total += len(board.pieces(piece_type, chess.WHITE)) * value
        total += len(board.pieces(piece_type, chess.BLACK)) * value
    queens = (
        len(board.pieces(chess.QUEEN, chess.WHITE))
        + len(board.pieces(chess.QUEEN, chess.BLACK))
    )
    if ply <= 20 and total >= 50:
        return "opening"
    if total <= 16 or (queens == 0 and total <= 24):
        return "endgame"
    return "middlegame"


def classify_move(cp_loss: int, is_forced: bool) -> str:
    if is_forced:
        return "forced"
    if cp_loss <= 10:
        return "best"
    if cp_loss <= 30:
        return "good"
    if cp_loss <= 90:
        return "inaccuracy"
    if cp_loss <= 250:
        return "mistake"
    return "blunder"


def pv_to_san(board: chess.Board, pv: List[chess.Move], max_moves: int = 5) -> str:
    b = board.copy()
    sans: List[str] = []
    for move in pv[:max_moves]:
        try:
            sans.append(b.san(move))
            b.push(move)
        except Exception:
            break
    return " ".join(sans)


# Standard material values, in pawns.
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
# Pieces worth naming as fork targets (a pawn fork rarely matters for narration).
FORK_TARGET_TYPES = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING)


def material_balance(board: chess.Board) -> float:
    """Material in pawns, positive = White ahead."""
    total = 0
    for piece_type, value in PIECE_VALUES.items():
        total += len(board.pieces(piece_type, chess.WHITE)) * value
        total -= len(board.pieces(piece_type, chess.BLACK)) * value
    return float(total)


def captured_piece_name(board: chess.Board, move: chess.Move) -> Optional[str]:
    """Name of the piece this move captures (en-passant aware), or None."""
    if board.is_en_passant(move):
        return "pawn"
    target = board.piece_at(move.to_square)
    if target is not None:
        return PIECE_NAMES.get(target.piece_type)
    return None


def file_structure(board: chess.Board) -> Dict[str, List[str]]:
    """Open and half-open files, derived from actual pawn placement."""
    open_files: List[str] = []
    half_open_white: List[str] = []
    half_open_black: List[str] = []
    for file_index in range(8):
        letter = chess.FILE_NAMES[file_index]
        white_pawn = any(
            chess.square_file(sq) == file_index
            for sq in board.pieces(chess.PAWN, chess.WHITE)
        )
        black_pawn = any(
            chess.square_file(sq) == file_index
            for sq in board.pieces(chess.PAWN, chess.BLACK)
        )
        if not white_pawn and not black_pawn:
            open_files.append(letter)
        elif not white_pawn and black_pawn:
            half_open_white.append(letter)
        elif white_pawn and not black_pawn:
            half_open_black.append(letter)
    return {
        "open": open_files,
        "half_open_white": half_open_white,
        "half_open_black": half_open_black,
    }


def detect_double_attack(
    board_after: chess.Board, piece_square: int, mover_color: bool
) -> Optional[str]:
    """
    Ground-truth double-attack / fork detection. Looks at what the piece now on
    `piece_square` actually attacks. Returns a human string like
    'knight on e6 attacks the king on g7 and the queen on c7 (royal fork)' or None.

    Only reports when 2+ enemy pieces are attacked AND at least one is a king,
    queen, or rook — so we don't narrate trivial minor-piece overlaps. This is a
    factual description of attacked squares, not a claim that the tactic wins.
    """
    attacker = board_after.piece_at(piece_square)
    if attacker is None:
        return None

    targets: List[tuple] = []  # (piece_type, square)
    for sq in board_after.attacks(piece_square):
        piece = board_after.piece_at(sq)
        if piece is not None and piece.color != mover_color and piece.piece_type in FORK_TARGET_TYPES:
            targets.append((piece.piece_type, sq))

    if len(targets) < 2:
        return None
    if not any(t[0] in (chess.KING, chess.QUEEN, chess.ROOK) for t in targets):
        return None

    # Sort by value descending so the headline pieces come first.
    targets.sort(key=lambda t: PIECE_VALUES[t[0]], reverse=True)
    has_king = any(t[0] == chess.KING for t in targets)
    has_queen = any(t[0] == chess.QUEEN for t in targets)

    desc_parts = [
        f"the {PIECE_NAMES[pt]} on {chess.square_name(sq)}" for pt, sq in targets
    ]
    if len(desc_parts) == 2:
        joined = f"{desc_parts[0]} and {desc_parts[1]}"
    else:
        joined = ", ".join(desc_parts[:-1]) + f", and {desc_parts[-1]}"

    attacker_name = PIECE_NAMES[attacker.piece_type]
    square = chess.square_name(piece_square)
    label = f"{attacker_name} on {square} attacks {joined}"

    if has_king and has_queen:
        label += " (royal fork)"
    elif has_king:
        label += " (fork involving the king)"
    else:
        label += " (double attack)"

    # Note whether the forking piece can simply be captured (fork may be illusory).
    enemy = not mover_color
    if board_after.is_attacked_by(enemy, piece_square):
        defended = board_after.is_attacked_by(mover_color, piece_square)
        if not defended:
            label += " — but the attacking piece is itself hanging"
    return label


def least_active_piece(board: chess.Board, color: bool) -> Optional[str]:
    """
    The side's most passive piece (fewest controlled squares) — across knights,
    bishops, ROOKS, and the QUEEN, not just minors. Flags it when genuinely stuck:
    a minor with <=3 squares, or a rook/queen with <=4 (heavy pieces are expected
    to be more active, so a low count means it's really doing nothing — e.g. a
    queen tied to passive defense, the case worth calling out). Cues 'activate
    your worst piece / redeploy that idle heavy piece' commentary.
    """
    candidates = []
    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        for sq in board.pieces(pt, color):
            mob = sum(
                1
                for d in board.attacks(sq)
                if board.piece_at(d) is None or board.piece_at(d).color != color
            )
            candidates.append((mob, pt, sq))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    mob, pt, sq = candidates[0]
    threshold = 4 if pt in (chess.ROOK, chess.QUEEN) else 3
    if mob <= threshold:
        side = "white" if color == chess.WHITE else "black"
        return (
            f"the {side} {PIECE_NAMES[pt]} on {chess.square_name(sq)} is the most passive piece "
            f"(controls only {mob} squares) and is the one to activate or redeploy"
        )
    return None


def detect_royal_alignment(board: chess.Board, mover_color: bool) -> Optional[str]:
    """
    Detect that the opponent's king and queen share a file or rank AND the mover
    has a rook or queen on that line — i.e. a pin/skewer the mover has set up that
    wins the queen. Credits the kind of tactical vision a player shows by lining a
    rook up against king+queen (e.g. both enemy royals on the g-file vs a rook).
    """
    opp = not mover_color
    king_sq = board.king(opp)
    if king_sq is None:
        return None
    kf, kr = chess.square_file(king_sq), chess.square_rank(king_sq)
    side = "white" if opp == chess.WHITE else "black"

    for qsq in board.pieces(chess.QUEEN, opp):
        qf, qr = chess.square_file(qsq), chess.square_rank(qsq)
        if qf == kf:
            line, coord = "file", chess.FILE_NAMES[qf]
        elif qr == kr:
            line, coord = "rank", chess.RANK_NAMES[qr]
        else:
            continue
        for ptm in (chess.ROOK, chess.QUEEN):
            for msq in board.pieces(ptm, mover_color):
                on_line = (
                    (line == "file" and chess.square_file(msq) == qf)
                    or (line == "rank" and chess.square_rank(msq) == qr)
                )
                if not on_line:
                    continue
                # The pinning piece must not be hanging — if the opponent can just
                # capture it for free (attacked and undefended), it's no real pin
                # (e.g. a rook that lands on the back rank only to be taken).
                if board.is_attacked_by(opp, msq) and not board.is_attacked_by(mover_color, msq):
                    continue
                return (
                    f"the {side} king on {chess.square_name(king_sq)} and queen on "
                    f"{chess.square_name(qsq)} share the {coord}-{line} with your "
                    f"{PIECE_NAMES[ptm]} on {chess.square_name(msq)} — a pin/skewer that wins the queen"
                )
    return None


def _doubled_files(board: chess.Board, color: bool):
    counts: Dict[int, int] = {}
    for sq in board.pieces(chess.PAWN, color):
        f = chess.square_file(sq)
        counts[f] = counts.get(f, 0) + 1
    return {f for f, c in counts.items() if c >= 2}


def detect_doubled_pawns_created(
    board_before: chess.Board, board_after: chess.Board
) -> Optional[str]:
    """If this move newly doubled either side's pawns, describe it (e.g. a
    recapture like hxg5 that leaves White with pawns on g3 and g5)."""
    notes = []
    for color in (chess.WHITE, chess.BLACK):
        new_files = _doubled_files(board_after, color) - _doubled_files(board_before, color)
        for f in sorted(new_files):
            letter = chess.FILE_NAMES[f]
            sqs = [
                chess.square_name(s)
                for s in sorted(board_after.pieces(chess.PAWN, color))
                if chess.square_file(s) == f
            ]
            side = "White" if color == chess.WHITE else "Black"
            notes.append(f"doubles {side}'s pawns on the {letter}-file ({', '.join(sqs)})")
    return "; ".join(notes) if notes else None


def detect_overloaded_defender(board: chess.Board) -> Optional[str]:
    """
    Find a piece or pawn that is the SOLE defender of two or more friendly pieces
    that are each attacked by the enemy — i.e. an overworked defender that cannot
    save both (e.g. a d5-pawn holding both an e4-knight and a c4-bishop while a
    knight on d2 attacks both). Returns a description or None.
    """
    for sq, piece in board.piece_map().items():
        color = piece.color
        enemy = not color
        defended_attacked = []  # (piece_type, square, is_sole_defender)
        for tsq in board.attacks(sq):
            tp = board.piece_at(tsq)
            if tp is None or tp.color != color:
                continue
            if tp.piece_type in (chess.KING, chess.PAWN):
                continue  # focus on overloaded defence of real pieces
            if not board.is_attacked_by(enemy, tsq):
                continue
            defenders = board.attackers(color, tsq)
            is_sole = len(defenders) == 1 and sq in defenders
            defended_attacked.append((tp.piece_type, tsq, is_sole))
        # Overloaded: defends 2+ attacked pieces AND is the sole defender of at
        # least one of them (so it cannot leave without something falling).
        if len(defended_attacked) >= 2 and any(t[2] for t in defended_attacked):
            side = "White" if color == chess.WHITE else "Black"
            dname = PIECE_NAMES[piece.piece_type]
            items = " and ".join(
                f"the {PIECE_NAMES[pt]} on {chess.square_name(s)}" for pt, s, _ in defended_attacked
            )
            return (
                f"{side}'s {dname} on {chess.square_name(sq)} is overloaded — it defends "
                f"{items} (both under attack) and cannot hold both"
            )
    return None


def detect_allowed_pawn_fork(board_after: chess.Board, mover_color: bool) -> Optional[str]:
    """
    After the mover's move, can the OPPONENT play a pawn push that forks two of
    the mover's pieces? This catches the root-cause error of drifting your own
    pieces onto adjacent forkable squares (e.g. rook on f4 + bishop on h4 invite
    g3). Returns a description like "allows g3, a pawn fork hitting the rook on
    f4 and the bishop on h4" or None.
    """
    opp = not mover_color
    probe = board_after.copy()
    probe.turn = opp
    best_desc = None
    best_value = 0
    for mv in probe.pseudo_legal_moves:
        p = probe.piece_at(mv.from_square)
        if p is None or p.piece_type != chess.PAWN:
            continue
        if probe.is_capture(mv):
            continue  # a pure push fork; capture-forks are rarer and noisier
        after = probe.copy()
        try:
            after.push(mv)
        except Exception:
            continue
        targets = []
        for sq in after.attacks(mv.to_square):
            pc = after.piece_at(sq)
            if (
                pc is not None
                and pc.color == mover_color
                and pc.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING)
            ):
                targets.append((pc.piece_type, sq))
        # Need two real targets, each at least a minor piece.
        real = [t for t in targets if t[0] != chess.KING or True]
        if len(real) < 2:
            continue
        if not all(PIECE_VALUES[t[0]] >= 3 or t[0] == chess.KING for t in real):
            continue
        value = sum(PIECE_VALUES[t[0]] for t in real)
        if value > best_value:
            real.sort(key=lambda t: PIECE_VALUES[t[0]], reverse=True)
            names = [f"the {PIECE_NAMES[pt]} on {chess.square_name(sq)}" for pt, sq in real]
            joined = " and ".join(names) if len(names) == 2 else ", ".join(names[:-1]) + f", and {names[-1]}"
            best_desc = f"allows {chess.square_name(mv.to_square)}, a pawn fork hitting {joined}"
            best_value = value
    return best_desc


def detect_sacrifice(
    mat_before_white: float,
    board_after: chess.Board,
    opp_best_reply: Optional[chess.Move],
    mover_color: bool,
    eval_after_norm_white: int,
    cp_loss: int,
):
    """
    Detect a SOUND sacrifice. Three conditions:
      1. The mover nets material DOWN (>= 1.5 pawns) after the opponent's best
         reply — they genuinely gave something up.
      2. The engine still clearly favors the mover afterward (eval gate) — so it
         is sound, not a blunder.
      3. The move is also a GOOD move (low cp_loss) — so we don't mislabel a
         sloppy move that merely stayed winning (because the mover was already up
         a lot) as a "sacrifice." A true sac is a deliberate, correct choice.

    cp_loss is used only as a "not a mistake" gate, kept loose (<=90) so that a
    brilliancy that is the engine's top move (cp_loss ~0) always passes while a
    give-back like a 140cp inaccuracy is excluded.

    Returns (is_sacrifice, is_brilliant, invested_pawns).
    """
    sign = 1 if mover_color == chess.WHITE else -1

    if opp_best_reply is not None:
        probe = board_after.copy()
        try:
            probe.push(opp_best_reply)
            mat_after_reply_white = material_balance(probe)
        except Exception:
            mat_after_reply_white = material_balance(board_after)
    else:
        mat_after_reply_white = material_balance(board_after)

    invested = (mat_before_white * sign) - (mat_after_reply_white * sign)
    mover_eval = eval_after_norm_white * sign  # centipawns from the mover's POV

    is_sac = invested >= 1.5 and mover_eval >= 100 and cp_loss <= 90
    is_brilliant = (
        is_sac and invested >= 2.5 and mover_eval >= 250 and cp_loss <= 40
    )
    return is_sac, is_brilliant, round(invested, 1)


def _enemy_pawn_can_attack(board: chess.Board, target_sq: int, piece_color: bool) -> bool:
    """Can an enemy pawn, in one push, reach a square from which it attacks target_sq?"""
    enemy = not piece_color
    probe = board.copy()
    probe.turn = enemy
    for mv in probe.pseudo_legal_moves:
        p = probe.piece_at(mv.from_square)
        if p is not None and p.piece_type == chess.PAWN:
            after = probe.copy()
            after.push(mv)
            if target_sq in after.attacks(mv.to_square):
                return True
    return False


def _pawn_safe_retreats(board: chess.Board, piece_sq: int, color: bool) -> List[int]:
    """Empty squares the piece on piece_sq could move to that are not attacked by an enemy pawn."""
    enemy = not color
    retreats: List[int] = []
    for dest in board.attacks(piece_sq):
        if board.piece_at(dest) is not None:
            continue  # only count empty retreat squares
        attacked_by_pawn = any(
            board.piece_at(s) is not None and board.piece_at(s).piece_type == chess.PAWN
            for s in board.attackers(enemy, dest)
        )
        if not attacked_by_pawn:
            retreats.append(dest)
    return retreats


def piece_mobility_notes(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> List[str]:
    """
    Ground-truth notes about knights/bishops that a pawn can kick and where they
    can (or can't) flee — so the narrator can reason about escape squares instead
    of guessing. Covers two human ideas:
      - This move OPENS a retreat square for the mover's own kickable minor piece
        (e.g. Qe2 vacates f3, giving a g5-knight a flight square — blunting ...h6).
      - An enemy kickable minor piece is short of safe squares (trappable) — a
        target the mover (or the side to move) can chase with a pawn.
    """
    notes: List[str] = []
    from_sq = move.from_square
    moved_from = board_before.piece_at(from_sq)

    for color in (chess.WHITE, chess.BLACK):
        side = "white" if color == chess.WHITE else "black"
        minors = list(board_after.pieces(chess.KNIGHT, color)) + list(
            board_after.pieces(chess.BISHOP, color)
        )
        for sq in minors:
            if sq == move.to_square:
                continue  # the piece that just moved
            if not _enemy_pawn_can_attack(board_after, sq, color):
                continue
            retreats = _pawn_safe_retreats(board_after, sq, color)
            name = PIECE_NAMES[board_after.piece_at(sq).piece_type]
            where = chess.square_name(sq)

            if color == mover_color:
                # Did this move just open from_sq as a flight square for my own piece?
                if (
                    from_sq in retreats
                    and moved_from is not None
                    and moved_from.color == mover_color
                ):
                    notes.append(
                        f"this move opens {chess.square_name(from_sq)} as a retreat for the "
                        f"{side} {name} on {where}, which a pawn could otherwise trap"
                    )
            else:
                # Enemy kickable minor short of squares = a piece the mover can hunt.
                if len(retreats) == 0:
                    notes.append(
                        f"the {side} {name} on {where} can be kicked by a pawn and has NO "
                        f"safe retreat square (trappable)"
                    )
                elif len(retreats) == 1:
                    notes.append(
                        f"the {side} {name} on {where} can be kicked by a pawn and has only "
                        f"one safe retreat ({chess.square_name(retreats[0])})"
                    )

    return notes[:3]  # keep it focused


def analyze_pgn(
    pgn_text: str,
    engine_path: str,
    depth: int = 18,
    multipv: int = 3,
    time_limit: Optional[float] = None,
    threads: Optional[int] = None,
    hash_mb: int = 256,
    progress_cb=None,
) -> GameAnalysis:
    """Run Stockfish over every position in the PGN and return a structured analysis."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Could not parse PGN")

    headers = dict(game.headers)
    moves_list: List[chess.Move] = list(game.mainline_moves())
    if not moves_list:
        raise ValueError("PGN contains no moves")

    if threads is None:
        threads = max(1, (os.cpu_count() or 2) - 1)

    engine = open_engine(engine_path)
    try:
        try:
            engine.configure({"Threads": threads, "Hash": hash_mb})
        except chess.engine.EngineError:
            pass  # some engines reject options; not fatal
        limit = (
            chess.engine.Limit(time=time_limit)
            if time_limit is not None
            else chess.engine.Limit(depth=depth)
        )

        # First pass: analyze every position (including the one after the last move),
        # so eval_after for move N reuses the eval_before of move N+1 (one engine call per ply).
        positions: List[Dict[str, Any]] = []
        board = game.board()
        total_positions = len(moves_list) + 1
        for i in range(total_positions):
            info = engine.analyse(board, limit, multipv=multipv)
            if not isinstance(info, list):
                info = [info]
            positions.append(
                {
                    "fen": board.fen(),
                    "turn_white": board.turn == chess.WHITE,
                    "analyses": info,
                    "legal_moves": list(board.legal_moves),
                }
            )
            if progress_cb:
                progress_cb(i + 1, total_positions)
            if i < len(moves_list):
                board.push(moves_list[i])

        # Second pass: build MoveAnalysis objects.
        moves_analysis: List[MoveAnalysis] = []
        board = game.board()
        prev_capture_square: Optional[int] = None  # square the previous ply captured on, for recapture detection
        for i, move in enumerate(moves_list):
            ply = i + 1
            move_number = (ply + 1) // 2
            side = "White" if board.turn == chess.WHITE else "Black"

            pre = positions[i]
            post = positions[i + 1]

            fen_before = board.fen()
            san = board.san(move)
            uci = move.uci()
            is_capture = board.is_capture(move)
            is_castle = board.is_castling(move)
            is_promotion = move.promotion is not None
            legal_moves = pre["legal_moves"]
            legal_move_count = len(legal_moves)
            is_forced = legal_move_count == 1

            # Material facts (computed from the actual board, not guessed).
            captured = captured_piece_name(board, move) if is_capture else None
            is_recapture = bool(
                is_capture
                and prev_capture_square is not None
                and move.to_square == prev_capture_square
            )
            side_color = chess.WHITE if side == "White" else chess.BLACK

            # Eval before (from White's POV).
            best_info = pre["analyses"][0]
            best_score = best_info["score"].white()
            eval_before_cp, mate_before = score_to_cp_mate(best_score)

            best_move = best_info["pv"][0] if best_info.get("pv") else move
            best_move_san = board.san(best_move)
            best_move_uci = best_move.uci()
            best_pv_san = pv_to_san(board, best_info.get("pv", []))

            # Ground-truth double attack the engine's preferred move would create.
            best_move_double_attack = None
            try:
                probe = board.copy()
                probe.push(best_move)
                best_move_double_attack = detect_double_attack(
                    probe, best_move.to_square, side_color
                )
            except Exception:
                best_move_double_attack = None

            # Whether the engine's best move is itself a recapture (so the narrator
            # describes alternatives like dxe4 accurately — capture vs. recapture).
            best_is_recapture = bool(
                board.is_capture(best_move)
                and prev_capture_square is not None
                and best_move.to_square == prev_capture_square
            )

            # Top alternatives.
            alternatives: List[Dict[str, Any]] = []
            for variant in pre["analyses"]:
                pv = variant.get("pv") or []
                if not pv:
                    continue
                v_move = pv[0]
                v_score = variant["score"].white()
                v_cp, v_mate = score_to_cp_mate(v_score)
                alternatives.append(
                    {
                        "san": board.san(v_move),
                        "uci": v_move.uci(),
                        "cp": v_cp,
                        "mate": v_mate,
                        "pv_san": pv_to_san(board, pv),
                    }
                )

            # "Only good move" heuristic: large gap between best and second best.
            is_only_good_move = False
            if len(pre["analyses"]) >= 2:
                second_score = pre["analyses"][1]["score"].white()
                s2_cp, s2_mate = score_to_cp_mate(second_score)
                gap = abs(
                    normalize_cp(eval_before_cp, mate_before)
                    - normalize_cp(s2_cp, s2_mate)
                )
                if gap > 200:
                    is_only_good_move = True

            # Eval after (from White's POV) = best eval of the position after the move.
            after_best = post["analyses"][0]
            after_score = after_best["score"].white()
            eval_after_cp, mate_after = score_to_cp_mate(after_score)

            best_norm = normalize_cp(eval_before_cp, mate_before)
            actual_norm = normalize_cp(eval_after_cp, mate_after)
            if side == "White":
                cp_loss = max(0, best_norm - actual_norm)
            else:
                cp_loss = max(0, actual_norm - best_norm)

            # Cap cp_loss for sanity (mate score noise).
            if cp_loss > MATE_SCORE:
                cp_loss = MATE_SCORE

            classification = classify_move(cp_loss, is_forced)
            # Winning-clamp: a move that keeps a decisive advantage (winning by ~3+
            # both before and after) is NOT a "mistake/blunder" just because it
            # isn't the fastest win — don't mislabel it (e.g. ...Kf6 defending a pawn
            # while up a rook). Demote the severity.
            _sign = 1 if side == "White" else -1
            mover_before_eval = best_norm * _sign
            mover_after_eval = actual_norm * _sign
            still_winning = mover_before_eval >= 300 and mover_after_eval >= 300
            if still_winning and classification in ("inaccuracy", "mistake", "blunder"):
                classification = "good"
            phase = detect_phase(board, ply)

            mat_before_white = material_balance(board)  # before the move is played
            opp_best_reply = None
            if post["analyses"] and post["analyses"][0].get("pv"):
                opp_best_reply = post["analyses"][0]["pv"][0]
            # If the engine PV is empty (can happen on forced-mate positions),
            # fall back to the actual move the opponent played in the game so the
            # material-investment estimate stays correct.
            if opp_best_reply is None and (i + 1) < len(moves_list):
                opp_best_reply = moves_list[i + 1]

            board_before_snapshot = board.copy()  # position before the move, for mobility analysis
            board.push(move)
            fen_after = board.fen()
            is_check = board.is_check()

            # Ground-truth facts about the resulting position.
            double_attack = detect_double_attack(board, move.to_square, side_color)
            mat_balance = material_balance(board)
            files = file_structure(board)
            is_sacrifice, is_brilliant, sac_invested = detect_sacrifice(
                mat_before_white,
                board,
                opp_best_reply,
                side_color,
                actual_norm,
                cp_loss,
            )
            mobility_notes = piece_mobility_notes(
                board_before_snapshot, move, board, side_color
            )
            allows_fork = detect_allowed_pawn_fork(board, side_color)
            # Skip "passive piece" nagging in the opening (undeveloped pieces are normal there).
            least_active = least_active_piece(board, side_color) if phase != "opening" else None
            tactic_setup = detect_royal_alignment(board, side_color)
            # What enemy pieces does the moved piece ACTUALLY attack now? (Stops the
            # narrator inventing "this pawn kicks the knight" when nothing is there.)
            attacks_pieces = []
            moved_now = board.piece_at(move.to_square)
            if moved_now is not None:
                for asq in board.attacks(move.to_square):
                    pc = board.piece_at(asq)
                    if (
                        pc is not None
                        and pc.color != side_color
                        and pc.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
                    ):
                        attacks_pieces.append(
                            f"{PIECE_NAMES[pc.piece_type]} on {chess.square_name(asq)}"
                        )
            doubled_created = detect_doubled_pawns_created(board_before_snapshot, board)
            overloaded = detect_overloaded_defender(board)
            # Unsound / "intimidation" sacrifice: gave up >=2 points via a capture or
            # check, but the engine does NOT favor the mover afterward.
            is_unsound_sacrifice = (
                sac_invested >= 2
                and (actual_norm * (1 if side_color == chess.WHITE else -1)) <= 50
                and (is_capture or is_check)
            )

            # Remember where this move captured, for the next ply's recapture check.
            prev_capture_square = move.to_square if is_capture else None

            moves_analysis.append(
                MoveAnalysis(
                    ply=ply,
                    move_number=move_number,
                    side=side,
                    san=san,
                    uci=uci,
                    fen_before=fen_before,
                    fen_after=fen_after,
                    eval_before_cp=eval_before_cp,
                    mate_before=mate_before,
                    eval_after_cp=eval_after_cp,
                    mate_after=mate_after,
                    best_move_san=best_move_san,
                    best_move_uci=best_move_uci,
                    best_pv_san=best_pv_san,
                    cp_loss=cp_loss,
                    top_alternatives=alternatives,
                    legal_move_count=legal_move_count,
                    is_forced=is_forced,
                    is_only_good_move=is_only_good_move,
                    is_capture=is_capture,
                    is_check=is_check,
                    is_castle=is_castle,
                    is_promotion=is_promotion,
                    phase=phase,
                    classification=classification,
                    captured_piece=captured,
                    is_recapture=is_recapture,
                    best_is_recapture=best_is_recapture,
                    material_balance=mat_balance,
                    open_files=files["open"],
                    half_open_white=files["half_open_white"],
                    half_open_black=files["half_open_black"],
                    double_attack=double_attack,
                    best_move_double_attack=best_move_double_attack,
                    is_sacrifice=is_sacrifice,
                    is_brilliant=is_brilliant,
                    sacrifice_invested=sac_invested,
                    mobility_notes=mobility_notes,
                    allows_fork=allows_fork,
                    is_unsound_sacrifice=is_unsound_sacrifice,
                    least_active_piece=least_active,
                    tactic_setup=tactic_setup,
                    attacks_pieces=attacks_pieces,
                    doubled_pawns_created=doubled_created,
                    overloaded_defender=overloaded,
                    still_winning=still_winning,
                )
            )

        final_score = positions[-1]["analyses"][0]["score"].white()
        final_eval_cp, final_mate = score_to_cp_mate(final_score)

        return GameAnalysis(
            headers=headers,
            moves=moves_analysis,
            result=headers.get("Result", "*"),
            final_eval_cp=final_eval_cp,
            final_mate=final_mate,
        )
    finally:
        engine.quit()
