"""Triage tiers — the rules engine that decides how much commentary each move gets.

This is the StayPlus analogue of "derive a record/decision from data via explicit
rules", so it is worth pinning down with tests.
"""
from __future__ import annotations

from triage import _tier_for_move, annotate_with_tiers, tier_distribution


def test_forced_move_is_tier_0(make_move):
    assert _tier_for_move(make_move(is_forced=True, classification="best"), {}) == 0


def test_blunder_is_tier_3(make_move):
    assert _tier_for_move(make_move(classification="blunder"), {}) == 3


def test_brilliancy_is_tier_3(make_move):
    assert _tier_for_move(make_move(classification="good", is_brilliant=True), {}) == 3


def test_quiet_opening_move_stays_low(make_move):
    m = make_move(ply=4, phase="opening", cp_loss=5, is_capture=False, classification="good")
    assert _tier_for_move(m, {}) <= 1


def test_sacrifice_gets_real_commentary(make_move):
    assert _tier_for_move(make_move(classification="good", is_sacrifice=True), {}) >= 2


def test_player_named_boosts_errors(make_move):
    plain = _tier_for_move(make_move(classification="inaccuracy"), {})
    named = _tier_for_move(make_move(classification="inaccuracy"), {"player_named": True})
    assert named == min(3, plain + 1)


def test_annotate_returns_one_tier_per_move(make_move, make_game):
    moves = [make_move(ply=i + 1, move_number=i // 2 + 1) for i in range(6)]
    tiers = annotate_with_tiers(make_game(moves), {})
    assert len(tiers) == len(moves)
    assert all(0 <= t <= 3 for t in tiers)


def test_mate_in_one_is_tier_3(make_move, make_game):
    moves = [make_move(ply=1), make_move(ply=2, mate_after=1)]
    tiers = annotate_with_tiers(make_game(moves), {})
    assert tiers[1] == 3


def test_tier_distribution_counts():
    assert tier_distribution([0, 1, 1, 2, 3, 3]) == {0: 1, 1: 2, 2: 1, 3: 2}
