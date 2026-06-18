"""Tests for compute_pv_material_delta() — backlog #23.

All tests are engine-free: they construct a chess.Board, supply a list of
chess.Move objects (PV), and verify the computed delta.
"""
from __future__ import annotations

import chess
import pytest

from analyzer import compute_pv_material_delta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pv(board: chess.Board, ucis: list[str]) -> list[chess.Move]:
    """Convert UCI strings to legal chess.Move objects on a copy of board."""
    b = board.copy()
    moves: list[chess.Move] = []
    for uci in ucis:
        move = chess.Move.from_uci(uci)
        if not b.is_legal(move):
            raise ValueError(f"Illegal move {uci} in position {b.fen()}")
        moves.append(move)
        b.push(move)
    return moves


# ---------------------------------------------------------------------------
# Positive: mover gains material
# ---------------------------------------------------------------------------

def test_white_captures_free_piece():
    """White Rxe8 captures a rook, no recapture — net +5."""
    # Position: White rook on a8, Black rook on e8, it's White's turn.
    board = chess.Board("4r3/8/8/8/8/8/8/R7 w - - 0 1")
    pv = _pv(board, ["a1e1", "e8e1"])  # Rxe1? Let's construct a proper one.
    # Simpler: set up a position where White can win a rook cleanly.
    board = chess.Board("4r3/8/8/8/8/8/8/4R3 w - - 0 1")
    pv = _pv(board, ["e1e8"])  # Rxe8, no recapture possible (no Black piece to take back)
    delta = compute_pv_material_delta(board, pv)
    assert delta == pytest.approx(5.0)


def test_white_wins_knight_no_recapture():
    """White captures a loose Black knight — net +3."""
    # White queen on d1, Black knight on d5, it's White's turn, no recapture.
    board = chess.Board("8/8/8/3n4/8/8/8/3Q4 w - - 0 1")
    pv = _pv(board, ["d1d5"])  # Qxd5 wins the knight
    delta = compute_pv_material_delta(board, pv)
    assert delta == pytest.approx(3.0)


def test_exchange_even_trade():
    """Knight for bishop trade — net 0 (both worth 3)."""
    # White knight on c3, Black bishop on f6, White to move; Black recaptures.
    # Arrange: Nc3xf6, then Black gxf6
    board = chess.Board("8/8/5b2/8/8/2N5/8/8 w - - 0 1")
    # Check: can White's Nc3 reach f6? Knight from c3: possible targets are
    # b1, a2, a4, b5, d5, e4, e2, d1. f6 is NOT reachable from c3 in one move.
    # Use a closer setup: White Nd4, Black Be6 — Nd4xe6 then ...fxe6
    board = chess.Board("8/8/4b3/8/3N4/8/8/8 w - - 0 1")
    # Nd4xe6? Not reachable. Let's use Nf5xe7 then ...Kxe7
    board = chess.Board("4k3/4b3/8/5N2/8/8/8/4K3 w - - 0 1")
    pv = _pv(board, ["f5e7", "e8e7"])  # Nxe7 Kxe7 — knight for bishop, net 0
    delta = compute_pv_material_delta(board, pv)
    assert delta == pytest.approx(0.0)


def test_black_captures_free_queen():
    """Black captures a loose White queen — net +9 (from Black's POV)."""
    # White queen on d4, it's Black's turn, Black rook on d8.
    board = chess.Board("3r4/8/8/8/3Q4/8/8/8 b - - 0 1")
    pv = _pv(board, ["d8d4"])  # Rxd4 wins the queen
    delta = compute_pv_material_delta(board, pv)
    assert delta == pytest.approx(9.0)


def test_empty_pv_returns_zero():
    """An empty PV produces delta 0.0."""
    board = chess.Board()
    delta = compute_pv_material_delta(board, [])
    assert delta == pytest.approx(0.0)


def test_pawn_promotion_increases_delta():
    """A pawn promotion to queen is accounted for (+8 net from pawn → queen)."""
    # White pawn on e7, no Black pieces to capture, White to move.
    board = chess.Board("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1")
    move = chess.Move.from_uci("e7e8q")
    assert board.is_legal(move)
    pv = [move]
    delta = compute_pv_material_delta(board, pv)
    # Started with 1 pawn (1), ended with 1 queen (9) + 1 king each.
    # Mover is White; start material_balance (White) = 1; end = 9.
    # delta = 9 - 1 = +8
    assert delta == pytest.approx(8.0)
