"""Tests for the certified human-difficulty labels (Maia; spec §5.2).

Engine-free: each test constructs a MoveAnalysis with the Maia fact-block fields
set directly and checks factgate.human_labels / human_label — the threshold logic
and the obvious-recapture guard — plus that the labels flow through the gate
(certified_claims) only when a MoveAnalysis is supplied.
"""
from __future__ import annotations

import chess

from factgate import certified_claims, human_label, human_labels


# ---------------------------------------------------------------------------
# Abstention — the gate says nothing unless Maia ran AND the player erred
# ---------------------------------------------------------------------------

def test_no_label_when_maia_did_not_run(make_move):
    # maia_played_rank defaults to None -> Maia was skipped/unavailable on this ply.
    move = make_move(cp_loss=300, maia_best_move_p=0.01)
    assert human_labels(move) == set()
    assert human_label(move) is None


def test_no_label_when_not_a_real_miss(make_move):
    # Maia ran, but the move lost <=1 pawn: there is no miss to characterize.
    move = make_move(cp_loss=80, maia_played_rank=1, maia_best_move_p=0.01)
    assert human_labels(move) == set()


# ---------------------------------------------------------------------------
# Label A — engine_move
# ---------------------------------------------------------------------------

def test_engine_move_from_low_probability(make_move):
    move = make_move(cp_loss=150, maia_played_rank=5, maia_best_move_p=0.05)
    assert "engine_move" in human_labels(move)
    assert human_label(move) == "engine_move"


def test_engine_move_from_off_list(make_move):
    # SF's best move absent from a wide top-K (p≈0, meaningful) -> engine move.
    move = make_move(
        cp_loss=150, maia_played_rank=8,
        maia_best_move_p=None, maia_best_move_off_list=True,
    )
    assert "engine_move" in human_labels(move)


def test_obvious_recapture_is_not_an_engine_move(make_move):
    # The guard: an obvious recapture (high p_best) is never an "engine move",
    # even if other signals (here off_list) would otherwise fire it.
    move = make_move(
        cp_loss=150, maia_played_rank=2,
        maia_best_move_p=0.60, maia_best_move_off_list=True,
        best_is_recapture=True,
    )
    labels = human_labels(move)
    assert "engine_move" not in labels
    assert "humanly_findable" in labels        # p_best 0.60 -> clearly findable instead


# ---------------------------------------------------------------------------
# Label B — humanly_findable, and the dead zone between A and B
# ---------------------------------------------------------------------------

def test_humanly_findable(make_move):
    move = make_move(cp_loss=150, maia_played_rank=2, maia_best_move_p=0.40)
    assert human_labels(move) == {"humanly_findable"}
    assert human_label(move) == "humanly_findable"


def test_dead_zone_emits_no_miss_label(make_move):
    # p_best in [0.10, 0.25) is neither clearly engine-only nor clearly findable.
    move = make_move(cp_loss=150, maia_played_rank=2, maia_best_move_p=0.15)
    assert human_labels(move) == set()
    assert human_label(move) is None


# ---------------------------------------------------------------------------
# Label C — predictable_human_error, including co-occurrence with A
# ---------------------------------------------------------------------------

def test_predictable_human_error(make_move):
    move = make_move(
        cp_loss=150, maia_played_rank=2,
        maia_played_p=0.30, maia_best_move_p=0.15,   # A/B in the dead zone
    )
    assert human_labels(move) == {"predictable_human_error"}
    assert human_label(move) == "predictable_human_error"


def test_predictable_requires_top_three_rank(make_move):
    move = make_move(
        cp_loss=150, maia_played_rank=5,             # off the top-3
        maia_played_p=0.30, maia_best_move_p=0.40,   # -> humanly_findable only
    )
    labels = human_labels(move)
    assert "predictable_human_error" not in labels
    assert labels == {"humanly_findable"}


def test_engine_move_and_predictable_error_co_occur(make_move):
    # The best was an engine move AND the player's reply was a typical human error.
    move = make_move(
        cp_loss=200, maia_played_rank=2,
        maia_best_move_p=0.04,    # engine_move
        maia_played_p=0.35,       # predictable_human_error
    )
    assert human_labels(move) == {"engine_move", "predictable_human_error"}
    # The miss-characterization is the headline primary label.
    assert human_label(move) == "engine_move"


# ---------------------------------------------------------------------------
# Gate integration — labels reach certified_claims only with a MoveAnalysis
# ---------------------------------------------------------------------------

def test_labels_flow_through_certified_claims(make_move):
    board_before = chess.Board()
    mv = chess.Move.from_uci("e2e4")
    board_after = board_before.copy()
    board_after.push(mv)
    move = make_move(cp_loss=150, maia_played_rank=5, maia_best_move_p=0.05)

    with_maia = certified_claims(board_before, mv, board_after, True, "opening", move_analysis=move)
    assert "engine_move" in with_maia

    # The board-only callers (no move_analysis) never see a human-difficulty label.
    board_only = certified_claims(board_before, mv, board_after, True, "opening")
    assert "engine_move" not in board_only
