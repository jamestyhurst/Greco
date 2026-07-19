"""Pure-function analyzer tests — no Stockfish, no API key.

Covers the engine-free helpers and the geometry fixes from the v0.9 sweep:
numbered-SAN variation rendering (2A), the pawn-fork legality filter, the
pinned-piece fork suppression, and the royal-alignment path-clear check.
"""
import chess

from analyzer import (
    classify_move,
    detect_allowed_pawn_fork,
    detect_double_attack,
    detect_royal_alignment,
    pv_to_numbered_san,
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
    # The f2-bishop guards e3, so the fork needs a supporter to be real (the
    # 2026-07-18 defended-square gate): the f4-pawn backs the push, making
    # Bxe3 a losing capture. Without it, ...e3 would just hang the pawn.
    b.set_piece_at(chess.F4, chess.Piece(chess.PAWN, chess.BLACK))
    b.set_piece_at(chess.C6, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.H1, chess.Piece(chess.KING, chess.WHITE))
    b.turn = chess.BLACK
    desc = detect_allowed_pawn_fork(b, chess.WHITE)
    assert desc and "e3" in desc and "rook" in desc and "bishop" in desc


def test_allowed_pawn_fork_suppressed_when_square_defended_unsupported():
    # Same geometry WITHOUT the supporter: the f2-bishop simply takes the pawn
    # on e3, so no fork threat exists (James's 2026-07-18 critique, item 16).
    b = chess.Board(None)
    b.set_piece_at(chess.E4, chess.Piece(chess.PAWN, chess.BLACK))
    b.set_piece_at(chess.D2, chess.Piece(chess.ROOK, chess.WHITE))
    b.set_piece_at(chess.F2, chess.Piece(chess.BISHOP, chess.WHITE))
    b.set_piece_at(chess.C6, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.H1, chess.Piece(chess.KING, chess.WHITE))
    b.turn = chess.BLACK
    assert detect_allowed_pawn_fork(b, chess.WHITE) is None


def test_allowed_pawn_fork_excludes_illegal_push():
    # Same fork geometry, but now the e4-pawn is pinned diagonally (bishop g2 ->
    # king c6), so ...e3 is ILLEGAL and must not be reported as a playable fork.
    b = chess.Board(None)
    b.set_piece_at(chess.E4, chess.Piece(chess.PAWN, chess.BLACK))
    b.set_piece_at(chess.D2, chess.Piece(chess.ROOK, chess.WHITE))
    b.set_piece_at(chess.F2, chess.Piece(chess.BISHOP, chess.WHITE))
    b.set_piece_at(chess.F4, chess.Piece(chess.PAWN, chess.BLACK))  # supporter, so only the pin suppresses
    b.set_piece_at(chess.C6, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.G2, chess.Piece(chess.BISHOP, chess.WHITE))  # pins the e4-pawn
    b.set_piece_at(chess.H1, chess.Piece(chess.KING, chess.WHITE))
    b.turn = chess.BLACK
    assert detect_allowed_pawn_fork(b, chess.WHITE) is None
