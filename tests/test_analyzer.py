"""Pure-function analyzer tests — no Stockfish, no API key.

Covers the engine-free helpers and the geometry fixes from the v0.9 sweep:
numbered-SAN variation rendering (2A), the pawn-fork legality filter, the
pinned-piece fork suppression, and the royal-alignment path-clear check.
Also covers normalize_cp, detect_phase, and score_to_cp_mate.
"""
import chess
import chess.engine

from analyzer import (
    MATE_SCORE,
    classify_move,
    detect_allowed_pawn_fork,
    detect_double_attack,
    detect_royal_alignment,
    detect_phase,
    normalize_cp,
    pv_to_numbered_san,
    score_to_cp_mate,
)


def _mv(uci):
    return chess.Move.from_uci(uci)


# --- pv_to_numbered_san (2A) ------------------------------------------------
def test_pv_numbered_white_first():
    pv = [_mv("e2e4"), _mv("e7e5"), _mv("g1f3")]
    assert pv_to_numbered_san(chess.Board(), pv) == "1. e4 e5 2. Nf3"


def test_pv_numbered_black_first():
    b = chess.Board()
    b.push_uci("e2e4")
    assert pv_to_numbered_san(b, [_mv("c7c5"), _mv("g1f3")]) == "1...c5 2. Nf3"


def test_pv_numbered_stops_on_illegal_move():
    # The legality guard means a stray/foreign PV never renders an illegal move.
    pv = [_mv("e2e4"), _mv("a1a8")]
    assert pv_to_numbered_san(chess.Board(), pv) == "1. e4"


def test_pv_numbered_empty():
    assert pv_to_numbered_san(chess.Board(), []) == ""


# --- classify_move ----------------------------------------------------------
def test_classify_move_thresholds():
    assert classify_move(0, False) == "best"
    assert classify_move(20, False) == "good"
    assert classify_move(50, False) == "inaccuracy"
    assert classify_move(150, False) == "mistake"
    assert classify_move(400, False) == "blunder"
    assert classify_move(400, True) == "forced"


# --- detect_double_attack pin suppression (#2) ------------------------------
def test_double_attack_detected():
    b = chess.Board(None)
    b.set_piece_at(chess.E6, chess.Piece(chess.KNIGHT, chess.WHITE))
    b.set_piece_at(chess.G7, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.C7, chess.Piece(chess.QUEEN, chess.BLACK))
    b.set_piece_at(chess.A1, chess.Piece(chess.KING, chess.WHITE))
    desc = detect_double_attack(b, chess.E6, chess.WHITE)
    assert desc and "queen" in desc and "king" in desc


def test_double_attack_suppressed_when_forker_pinned():
    # The e6-knight is pinned to its own king (e1) by the black rook on e8, so it
    # cannot actually deliver the royal fork — must not be reported.
    b = chess.Board(None)
    b.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    b.set_piece_at(chess.E6, chess.Piece(chess.KNIGHT, chess.WHITE))
    b.set_piece_at(chess.E8, chess.Piece(chess.ROOK, chess.BLACK))
    b.set_piece_at(chess.G7, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.C7, chess.Piece(chess.QUEEN, chess.BLACK))
    assert detect_double_attack(b, chess.E6, chess.WHITE) is None


# --- detect_royal_alignment path-clear (#20) --------------------------------
def test_royal_alignment_clear_line_wins_queen():
    b = chess.Board(None)
    b.set_piece_at(chess.G1, chess.Piece(chess.ROOK, chess.WHITE))
    b.set_piece_at(chess.G4, chess.Piece(chess.QUEEN, chess.BLACK))
    b.set_piece_at(chess.G8, chess.Piece(chess.KING, chess.BLACK))
    # King on h1 defends the g1-rook, so the pre-existing hanging-piece guard
    # doesn't fire (the pinned queen geometrically "attacks" the rook).
    b.set_piece_at(chess.H1, chess.Piece(chess.KING, chess.WHITE))
    desc = detect_royal_alignment(b, chess.WHITE)
    assert desc and "wins the queen" in desc


def test_royal_alignment_blocked_line_returns_none():
    b = chess.Board(None)
    b.set_piece_at(chess.G1, chess.Piece(chess.ROOK, chess.WHITE))
    b.set_piece_at(chess.G4, chess.Piece(chess.QUEEN, chess.BLACK))
    b.set_piece_at(chess.G6, chess.Piece(chess.PAWN, chess.BLACK))  # blocker Q<->K
    b.set_piece_at(chess.G8, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.A1, chess.Piece(chess.KING, chess.WHITE))
    assert detect_royal_alignment(b, chess.WHITE) is None


# --- detect_allowed_pawn_fork legality filter (#2/#3) -----------------------
def test_allowed_pawn_fork_detected_when_legal():
    b = chess.Board(None)
    b.set_piece_at(chess.E4, chess.Piece(chess.PAWN, chess.BLACK))   # ...e3 forks
    b.set_piece_at(chess.D2, chess.Piece(chess.ROOK, chess.WHITE))   # mover target
    b.set_piece_at(chess.F2, chess.Piece(chess.BISHOP, chess.WHITE)) # mover target
    b.set_piece_at(chess.C6, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.H1, chess.Piece(chess.KING, chess.WHITE))
    b.turn = chess.BLACK
    desc = detect_allowed_pawn_fork(b, chess.WHITE)
    assert desc and "e3" in desc and "rook" in desc and "bishop" in desc


def test_allowed_pawn_fork_excludes_illegal_push():
    # Same fork geometry, but now the e4-pawn is pinned diagonally (bishop g2 ->
    # king c6), so ...e3 is ILLEGAL and must not be reported as a playable fork.
    b = chess.Board(None)
    b.set_piece_at(chess.E4, chess.Piece(chess.PAWN, chess.BLACK))
    b.set_piece_at(chess.D2, chess.Piece(chess.ROOK, chess.WHITE))
    b.set_piece_at(chess.F2, chess.Piece(chess.BISHOP, chess.WHITE))
    b.set_piece_at(chess.C6, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.G2, chess.Piece(chess.BISHOP, chess.WHITE))  # pins the e4-pawn
    b.set_piece_at(chess.H1, chess.Piece(chess.KING, chess.WHITE))
    b.turn = chess.BLACK
    assert detect_allowed_pawn_fork(b, chess.WHITE) is None


# --- normalize_cp -----------------------------------------------------------

def test_normalize_cp_centipawn():
    assert normalize_cp(50, None) == 50
    assert normalize_cp(-300, None) == -300
    assert normalize_cp(0, None) == 0


def test_normalize_cp_none_returns_zero():
    assert normalize_cp(None, None) == 0


def test_normalize_cp_mate_positive():
    result = normalize_cp(None, 3)
    assert result == MATE_SCORE - 3
    assert result > 0


def test_normalize_cp_mate_negative():
    result = normalize_cp(None, -2)
    assert result == -MATE_SCORE + 2
    assert result < 0


def test_normalize_cp_mate_in_zero():
    # mate=0 means already checkmated (the side to move lost).
    assert normalize_cp(None, 0) == -MATE_SCORE


# --- score_to_cp_mate -------------------------------------------------------

def test_score_to_cp_mate_centipawn():
    cp, mate = score_to_cp_mate(chess.engine.Cp(75))
    assert cp == 75
    assert mate is None


def test_score_to_cp_mate_mate():
    cp, mate = score_to_cp_mate(chess.engine.Mate(2))
    assert cp is None
    assert mate == 2


# --- detect_phase -----------------------------------------------------------

def _full_board_ply(ply: int) -> chess.Board:
    """A standard starting board (all pieces present) at the given ply."""
    b = chess.Board()
    b.fullmove_number = ply // 2 + 1
    return b


def test_detect_phase_opening():
    b = chess.Board()  # all pieces present, ply 1
    assert detect_phase(b, 1) == "opening"


def test_detect_phase_endgame_low_material():
    b = chess.Board(None)
    b.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    b.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.A1, chess.Piece(chess.ROOK, chess.WHITE))
    # total material: 5 — well below the endgame threshold
    assert detect_phase(b, 50) == "endgame"


def test_detect_phase_middlegame():
    b = chess.Board(None)
    # Add enough material to stay out of endgame but past opening ply threshold.
    for sq, piece in [
        (chess.E1, chess.Piece(chess.KING, chess.WHITE)),
        (chess.E8, chess.Piece(chess.KING, chess.BLACK)),
        (chess.D1, chess.Piece(chess.QUEEN, chess.WHITE)),
        (chess.D8, chess.Piece(chess.QUEEN, chess.BLACK)),
        (chess.A1, chess.Piece(chess.ROOK, chess.WHITE)),
        (chess.A8, chess.Piece(chess.ROOK, chess.BLACK)),
        (chess.C1, chess.Piece(chess.BISHOP, chess.WHITE)),
        (chess.C8, chess.Piece(chess.BISHOP, chess.BLACK)),
    ]:
        b.set_piece_at(sq, piece)
    assert detect_phase(b, 25) == "middlegame"
