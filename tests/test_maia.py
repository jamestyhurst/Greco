"""Tests for maia.py — Maia (human-vs-engine) integration, Phase 2.

Engine-free by design: this phase is rating-band selection (pure arithmetic) and
the availability gate (a filesystem check). No lc0 binary or weight files are
needed — and that is exactly the point: when they are absent, Maia must stay OFF
and Greco behaves exactly as it does today (the hard fallback, spec §7 item 1).

Live lc0 querying (Phase 1/3) is verified separately once the binaries are
downloaded (Phase 0); it is not exercised here.
"""
from __future__ import annotations

import pytest

import maia


# ---------------------------------------------------------------------------
# select_band — the deterministic clamp (spec §5.4)
# ---------------------------------------------------------------------------

def test_exact_band_is_unchanged():
    assert maia.select_band(1500) == 1500
    assert maia.select_band(1100) == 1100
    assert maia.select_band(1900) == 1900


def test_rounds_to_nearest_hundred():
    assert maia.select_band(1549) == 1500
    assert maia.select_band(1551) == 1600
    assert maia.select_band(1149) == 1100
    assert maia.select_band(1849) == 1800


def test_half_boundary_rounds_up_not_bankers():
    # The .5 boundary must round UP deterministically. Python's round() uses
    # banker's rounding (round-half-to-even): round(1450, -2) == 1400 but
    # round(1550, -2) == 1600 — inconsistent. The +50//100 form rounds every
    # half up, so 1550 -> 1600 AND 1450 -> 1500.
    assert maia.select_band(1550) == 1600
    assert maia.select_band(1450) == 1500
    assert maia.select_band(1150) == 1200


def test_clamps_below_min_band():
    assert maia.select_band(700) == 1100
    assert maia.select_band(0) == 1100
    assert maia.select_band(1099) == 1100


def test_clamps_above_max_band():
    assert maia.select_band(2500) == 1900
    assert maia.select_band(3000) == 1900
    assert maia.select_band(1950) == 1900


def test_every_output_is_a_trained_band():
    # No matter the input Elo, the chosen band must be one lc0 actually has weights for.
    for elo in range(-200, 3200, 7):
        assert maia.select_band(elo) in maia.TRAINED_BANDS


# ---------------------------------------------------------------------------
# band_for_mover — read the mover's Elo from PGN headers, defend against junk
# ---------------------------------------------------------------------------

def test_white_mover_uses_white_elo():
    sel = maia.band_for_mover({"WhiteElo": "1700", "BlackElo": "1200"}, "White")
    assert sel.band == 1700
    assert sel.raw_elo == 1700
    assert sel.clamped is False
    assert sel.defaulted is False


def test_black_mover_uses_black_elo():
    sel = maia.band_for_mover({"WhiteElo": "1700", "BlackElo": "1200"}, "Black")
    assert sel.band == 1200
    assert sel.raw_elo == 1200


def test_strong_player_is_clamped_and_flagged():
    sel = maia.band_for_mover({"WhiteElo": "2400"}, "White")
    assert sel.band == 1900
    assert sel.clamped is True       # 1900 net materially under-represents a 2400
    assert sel.defaulted is False
    assert sel.raw_elo == 2400


def test_weak_player_is_clamped_low():
    sel = maia.band_for_mover({"WhiteElo": "800"}, "White")
    assert sel.band == 1100
    assert sel.clamped is True


def test_near_ceiling_is_not_clamped():
    # 1920 rounds to 1900, which is a real band — not a clamp distortion.
    sel = maia.band_for_mover({"WhiteElo": "1920"}, "White")
    assert sel.band == 1900
    assert sel.clamped is False


def test_missing_header_falls_back_to_default():
    sel = maia.band_for_mover({}, "White")
    assert sel.band == maia.select_band(maia.DEFAULT_RATING)
    assert sel.defaulted is True
    assert sel.raw_elo is None


@pytest.mark.parametrize("bad", ["?", "", "   ", "abc", "1850.5", "N/A", "-"])
def test_malformed_elo_falls_back_to_default(bad):
    sel = maia.band_for_mover({"WhiteElo": bad}, "White")
    assert sel.band == maia.select_band(maia.DEFAULT_RATING)
    assert sel.defaulted is True
    assert sel.raw_elo is None


def test_custom_default_rating_is_honored():
    sel = maia.band_for_mover({}, "White", default_rating=1300)
    assert sel.band == 1300
    assert sel.defaulted is True


def test_surrounding_whitespace_is_tolerated():
    sel = maia.band_for_mover({"WhiteElo": "  1600 "}, "White")
    assert sel.band == 1600
    assert sel.defaulted is False


# ---------------------------------------------------------------------------
# Availability gate — the hard fallback (spec §7 item 1)
# ---------------------------------------------------------------------------

def test_maia_unavailable_with_no_engine_files():
    # The real repo has no engines/ directory yet (weights are a manual Phase-0
    # download). The gate MUST report unavailable so the analyzer skips Maia.
    assert maia.maia_available() is False


def test_find_weight_bands_empty_dir(tmp_path):
    assert maia.find_weight_bands(tmp_path) == {}


def test_find_weight_bands_discovers_and_keys_by_band(tmp_path):
    (tmp_path / "maia-1100.pb.gz").write_bytes(b"")
    (tmp_path / "maia-1500.pb.gz").write_bytes(b"")
    (tmp_path / "readme.txt").write_bytes(b"")          # ignored
    bands = maia.find_weight_bands(tmp_path)
    assert set(bands) == {1100, 1500}
    assert bands[1500].name == "maia-1500.pb.gz"


def test_available_requires_both_binary_and_weights(tmp_path):
    lc0 = tmp_path / "lc0.exe"
    weights = tmp_path / "weights"
    weights.mkdir()
    # Neither present yet.
    assert maia.maia_available(lc0, weights) is False
    # Binary only — still off.
    lc0.write_bytes(b"")
    assert maia.maia_available(lc0, weights) is False
    # Add a weight file — now available.
    (weights / "maia-1500.pb.gz").write_bytes(b"")
    assert maia.maia_available(lc0, weights) is True
    # Weights only (no binary) — off.
    lc0.unlink()
    assert maia.maia_available(lc0, weights) is False


# ---------------------------------------------------------------------------
# maia_node_budget — the adaptive table (spec §2.1)
# ---------------------------------------------------------------------------

def test_forced_move_skips_maia(make_move):
    move = make_move(is_forced=True, classification="forced")
    assert maia.maia_node_budget(move, tier=3) == 0


def test_forced_move_skips_even_under_override(make_move):
    move = make_move(is_forced=True)
    assert maia.maia_node_budget(move, tier=0, nodes_override=500) == 0


def test_override_replaces_table_for_non_forced(make_move):
    move = make_move(classification="good")          # would normally be cheap
    assert maia.maia_node_budget(move, tier=0, nodes_override=250) == 250


def test_only_good_move_is_critical(make_move):
    move = make_move(is_only_good_move=True, classification="good")
    assert maia.maia_node_budget(move, tier=2) == maia.NODES_CRITICAL


def test_sacrifice_is_critical(make_move):
    assert maia.maia_node_budget(make_move(is_sacrifice=True), tier=2) == maia.NODES_CRITICAL
    assert maia.maia_node_budget(make_move(is_brilliant=True), tier=2) == maia.NODES_CRITICAL


def test_tier_three_is_critical(make_move):
    move = make_move(classification="good")
    assert maia.maia_node_budget(move, tier=3) == maia.NODES_CRITICAL


def test_big_eval_swing_is_critical(make_move):
    move = make_move(eval_before_cp=20, eval_after_cp=300, classification="good")
    assert maia.maia_node_budget(move, tier=1) == maia.NODES_CRITICAL


def test_mate_relevant_without_other_flags(make_move):
    move = make_move(mate_after=3, classification="good")
    assert maia.maia_node_budget(move, tier=2) == maia.NODES_MATE_RELEVANT


def test_mistake_and_blunder_budget(make_move):
    assert maia.maia_node_budget(make_move(classification="mistake"), tier=2) == maia.NODES_MISTAKE
    assert maia.maia_node_budget(make_move(classification="blunder"), tier=2) == maia.NODES_MISTAKE


def test_inaccuracy_budget(make_move):
    move = make_move(classification="inaccuracy")
    assert maia.maia_node_budget(move, tier=2) == maia.NODES_INACCURACY


def test_quiet_decided_is_cheapest_nonzero(make_move):
    move = make_move(still_winning=True, cp_loss=10, classification="good")
    assert maia.maia_node_budget(move, tier=0) == maia.NODES_QUIET_DECIDED


def test_normal_quiet_is_the_default(make_move):
    move = make_move(classification="good", cp_loss=10)   # not winning, not tactical
    assert maia.maia_node_budget(move, tier=1) == maia.NODES_NORMAL_QUIET
