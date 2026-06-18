"""Tests for propagate_sacrifice_windows() — backlog #25.

Tests are engine-free: they construct MoveAnalysis lists directly and call
the second-pass function, verifying which downstream plies are tagged.
"""
from __future__ import annotations

import pytest

from analyzer import MoveAnalysis, propagate_sacrifice_windows

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_move(
    ply: int,
    side: str = "White",
    is_sacrifice: bool = False,
    sacrifice_invested: float = 0.0,
    material_balance: float = 0.0,
    eval_after_cp: int = 30,
) -> MoveAnalysis:
    """Build a minimal MoveAnalysis for sacrifice-window testing."""
    return MoveAnalysis(
        ply=ply,
        move_number=(ply + 1) // 2,
        side=side,
        san="e4",
        uci="e2e4",
        fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        eval_before_cp=30,
        mate_before=None,
        eval_after_cp=eval_after_cp,
        mate_after=None,
        best_move_san="e4",
        best_move_uci="e2e4",
        best_pv_san="e4 e5",
        cp_loss=0,
        is_sacrifice=is_sacrifice,
        sacrifice_invested=sacrifice_invested,
        material_balance=material_balance,
    )


# ---------------------------------------------------------------------------
# Positive: window is propagated
# ---------------------------------------------------------------------------

def test_white_sacrifice_window_propagates():
    """Plies after a White sound sacrifice are tagged in_sacrifice_window."""
    # White at ply 10: sacrificed a piece (invested=3.0), now down 3 pawns.
    # Plies 11-13: material still invested (balance at -3.0), eval holds.
    # Ply 14: material recovered (balance back to 0.0).
    moves = [
        _make_move(10, "White", is_sacrifice=True, sacrifice_invested=3.0, material_balance=-3.0),
        _make_move(11, "Black", material_balance=-3.0, eval_after_cp=120),
        _make_move(12, "White", material_balance=-3.0, eval_after_cp=150),
        _make_move(13, "Black", material_balance=-3.0, eval_after_cp=110),
        _make_move(14, "White", material_balance=0.0, eval_after_cp=60),  # recovered
    ]
    propagate_sacrifice_windows(moves)
    assert moves[0].in_sacrifice_window is False   # origin itself is not tagged
    assert moves[1].in_sacrifice_window is True
    assert moves[2].in_sacrifice_window is True
    assert moves[3].in_sacrifice_window is True
    assert moves[4].in_sacrifice_window is False   # material recovered → window closed


def test_black_sacrifice_window_propagates():
    """Black-side sacrifice window: material_balance goes UP (White gains) while Black invested."""
    # Black at ply 11: invested 3 pawns (White material_balance +3 = Black down 3).
    # post-sacrifice: material_balance = +3.0 (White ahead because Black sacrificed)
    # pre-sacrifice was 0.0; after Black sacrifice = +3.0
    moves = [
        _make_move(11, "Black", is_sacrifice=True, sacrifice_invested=3.0, material_balance=3.0,
                   eval_after_cp=-130),  # eval_after_cp from White's POV = Black is fine (-130 white = +130 black)
        _make_move(12, "White", material_balance=3.0, eval_after_cp=-120),
        _make_move(13, "Black", material_balance=3.0, eval_after_cp=-110),
        _make_move(14, "White", material_balance=0.0, eval_after_cp=20),  # recovered
    ]
    propagate_sacrifice_windows(moves)
    assert moves[0].in_sacrifice_window is False
    assert moves[1].in_sacrifice_window is True
    assert moves[2].in_sacrifice_window is True
    assert moves[3].in_sacrifice_window is False  # material recovered


def test_window_carries_origin_ply_and_invested():
    """Tagged plies carry the correct origin ply and invested amount."""
    moves = [
        _make_move(20, "White", is_sacrifice=True, sacrifice_invested=3.0, material_balance=-3.0),
        _make_move(21, "Black", material_balance=-3.0, eval_after_cp=150),
        _make_move(22, "White", material_balance=-3.0, eval_after_cp=140),
    ]
    propagate_sacrifice_windows(moves)
    assert moves[1].sacrifice_window_origin_ply == 20
    assert moves[1].sacrifice_window_invested == 3.0
    assert moves[2].sacrifice_window_origin_ply == 20


# ---------------------------------------------------------------------------
# Negative: window does not fire when it shouldn't
# ---------------------------------------------------------------------------

def test_no_sacrifice_no_window():
    """No is_sacrifice → no window propagation."""
    moves = [
        _make_move(1, material_balance=-3.0, eval_after_cp=100),
        _make_move(2, material_balance=-3.0, eval_after_cp=100),
    ]
    propagate_sacrifice_windows(moves)
    assert moves[0].in_sacrifice_window is False
    assert moves[1].in_sacrifice_window is False


def test_small_sacrifice_no_window():
    """sacrifice_invested < 1.5 → window not started (too small to certify)."""
    moves = [
        _make_move(1, "White", is_sacrifice=True, sacrifice_invested=1.0, material_balance=-1.0),
        _make_move(2, "Black", material_balance=-1.0, eval_after_cp=120),
    ]
    propagate_sacrifice_windows(moves)
    assert moves[1].in_sacrifice_window is False


def test_window_stops_on_eval_collapse():
    """Window ends when eval collapses below -150cp from the sacrificing side."""
    moves = [
        _make_move(10, "White", is_sacrifice=True, sacrifice_invested=3.0, material_balance=-3.0),
        _make_move(11, "Black", material_balance=-3.0, eval_after_cp=100),   # fine
        _make_move(12, "White", material_balance=-3.0, eval_after_cp=-200),  # collapsed
        _make_move(13, "Black", material_balance=-3.0, eval_after_cp=-200),
    ]
    propagate_sacrifice_windows(moves)
    assert moves[1].in_sacrifice_window is True
    assert moves[2].in_sacrifice_window is False   # eval collapse stops at this ply
    assert moves[3].in_sacrifice_window is False


def test_window_respects_max_plies():
    """Window never extends beyond _MAX_SACRIFICE_WINDOW_PLIES (8)."""
    from analyzer import _MAX_SACRIFICE_WINDOW_PLIES
    origin = _make_move(1, "White", is_sacrifice=True, sacrifice_invested=3.0, material_balance=-3.0)
    # 10 plies all with deficit still -3.0 and good eval
    later = [
        _make_move(1 + k, "White" if k % 2 == 0 else "Black",
                   material_balance=-3.0, eval_after_cp=100)
        for k in range(1, 11)
    ]
    moves = [origin] + later
    propagate_sacrifice_windows(moves)
    # Plies 1..8 after origin (indices 1..8) should be tagged
    for idx in range(1, _MAX_SACRIFICE_WINDOW_PLIES + 1):
        assert moves[idx].in_sacrifice_window is True, f"index {idx} should be in window"
    # Ply 9+ should NOT be tagged
    for idx in range(_MAX_SACRIFICE_WINDOW_PLIES + 1, len(moves)):
        assert moves[idx].in_sacrifice_window is False, f"index {idx} should be outside window"
