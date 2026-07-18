"""Tests for the Maia narrator fact-packet serialization (spec §3.3).

Engine-free: build a MoveAnalysis with the Maia fact block populated and check
narrator._move_to_dict emits the `human` sub-dict (tier 1+) and `human_line`
(tier 2+), that both are skip-safe when Maia is absent, and that the line is
tier-gated. Real FENs are used so the rest of _move_to_dict runs normally.
"""
from __future__ import annotations

import narrator

_FEN_BEFORE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
_FEN_AFTER = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

_TOP = [
    {"san": "e4", "uci": "e2e4", "p_maia": 0.42, "p_estimated": False, "cp_maia": 20},
    {"san": "d4", "uci": "d2d4", "p_maia": 0.25, "p_estimated": False, "cp_maia": 18},
    {"san": "Nf3", "uci": "g1f3", "p_maia": 0.15, "p_estimated": False, "cp_maia": 15},
    {"san": "c4", "uci": "c2c4", "p_maia": 0.10, "p_estimated": False, "cp_maia": 12},
]


def _maia_move(make_move, **overrides):
    base = dict(
        fen_before=_FEN_BEFORE, fen_after=_FEN_AFTER, san="e4", uci="e2e4",
        cp_loss=150,
        maia_rating_band=1500,
        maia_top_moves=_TOP,
        maia_best_move_p=0.42, maia_played_p=0.30, maia_played_rank=2,
        human_label="humanly_findable",
    )
    base.update(overrides)
    return make_move(**base)


# ---------------------------------------------------------------------------
# The `human` sub-dict (tier 1+)
# ---------------------------------------------------------------------------

def test_human_block_emitted_at_tier_1(make_move):
    d = narrator._move_to_dict(_maia_move(make_move), tier=1)
    assert "human" in d
    h = d["human"]
    assert h["band"] == 1500
    assert len(h["top"]) == 3                       # capped to top-3
    assert h["top"][0] == {"san": "e4", "p": 0.42}
    assert h["best_move_p"] == 0.42
    assert h["played_p"] == 0.30
    assert h["played_rank"] == 2
    assert h["label"] == "humanly_findable"


def test_human_block_skipped_when_maia_absent(make_move):
    move = make_move(fen_before=_FEN_BEFORE, fen_after=_FEN_AFTER)  # no maia_top_moves
    d = narrator._move_to_dict(move, tier=1)
    assert "human" not in d


def test_human_block_skipped_at_tier_0(make_move):
    d = narrator._move_to_dict(_maia_move(make_move), tier=0)
    assert "human" not in d


def test_clamped_and_defaulted_flags_surface(make_move):
    move = _maia_move(make_move, maia_rating_clamped=True, maia_rating_defaulted=True)
    h = narrator._move_to_dict(move, tier=1)["human"]
    assert h["band_clamped"] is True
    assert h["band_defaulted"] is True


def test_label_falls_back_to_computed_when_field_blank(make_move):
    # human_label field left as default None -> serialization computes it from the
    # Maia probabilities (p_best 0.42 -> humanly_findable).
    move = _maia_move(make_move, human_label=None)
    assert narrator._move_to_dict(move, tier=1)["human"]["label"] == "humanly_findable"


# ---------------------------------------------------------------------------
# The `human_line` (tier 2+ only)
# ---------------------------------------------------------------------------

def test_human_line_emitted_at_tier_2(make_move):
    move = _maia_move(make_move, maia_line_san="1. e4 e5 2. Nf3", maia_line_eval_cp=40)
    d = narrator._move_to_dict(move, tier=2)
    assert d["human_line"]["line"] == "1. e4 e5 2. Nf3"
    assert "eval" in d["human_line"]


def test_human_line_not_emitted_at_tier_1(make_move):
    move = _maia_move(make_move, maia_line_san="1. e4 e5 2. Nf3", maia_line_eval_cp=40)
    d = narrator._move_to_dict(move, tier=1)
    assert "human_line" not in d


def test_human_line_skipped_without_a_line(make_move):
    move = _maia_move(make_move)  # maia_line_san defaults to ""
    d = narrator._move_to_dict(move, tier=2)
    assert "human_line" not in d
    assert "human" in d           # the tier-1 block still fires
