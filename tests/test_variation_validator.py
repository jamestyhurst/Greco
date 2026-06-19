"""Tests for the variation-validator reframe — legality-replay, not engine-membership.

Spec: docs/specs/VARIATION_VALIDATOR.md. The policy moved from "a parenthetical is
valid only if every SAN token is verbatim in some engine PV" to "a parenthetical is
valid if it replays legally from ANY plausible branch board reconstructed from the
per-ply FENs." This un-suppresses legitimate instructive counterfactuals.

These fixtures use REAL FENs (verified with python-chess) because the validator now
replays moves on actual boards — the conftest dummy FENs ("startpos"/"afterpos") would
make every replay illegal. Each case mirrors a row of the spec's §8 worked-examples.

Pure: no engine, no API key.
"""
from outputs import (
    UnverifiedVariation,
    assemble_report,
    find_unverified_variation_moves,
    validate_parenthetical_variations,
)


def _game(make_move, make_game, **over):
    """A one-move game with REAL fen_before/fen_after so legality-replay can run."""
    return make_game([make_move(**over)])


# ---------------------------------------------------------------------------
# §8 row 2 + regression — the canonical counterfactual that the reframe exists to fix:
# "if Black had NOT played 24...f6, White would have had Qxg7#". It branches from the
# position BEFORE ...f6 with the side flipped (null move), where Qxg7 is mate.
# ---------------------------------------------------------------------------
def _qxg7_counterfactual_game(make_move, make_game):
    return _game(
        make_move, make_game,
        ply=48, move_number=24, side="Black", san="f6", uci="f7f6",
        fen_before="7k/5pp1/8/6Q1/8/8/1B6/6K1 b - - 0 24",
        fen_after="7k/6p1/5p2/6Q1/8/8/1B6/6K1 w - - 0 25",
    )


def test_counterfactual_qxg7_mate_survives(make_move, make_game):
    """The canonical 'if X had not been played, Qxg7#' counterfactual must SURVIVE
    (this is the exact false-positive the reframe removes — old code flagged Qxg7)."""
    g = _qxg7_counterfactual_game(make_move, make_game)
    report = ("If Black had not played **24...f6**, White would have had "
              "*(Qxg7#)* — the bishop on b2 covers g7.")
    assert find_unverified_variation_moves(report, g) == []
    assert validate_parenthetical_variations(report, g) == []


def test_counterfactual_survives_full_assemble(make_move, make_game, tmp_path):
    """Law-1 / output-level check: the counterfactual text is still present in the
    ASSEMBLED report body — the pipeline warns but never strips a legal line."""
    g = _qxg7_counterfactual_game(make_move, make_game)
    narrative = (
        "## Walkthrough\n\n"
        "**24...f6** blocks the long diagonal. If Black had not played **24...f6**, "
        "White would have had *(Qxg7#)*, since the b2-bishop still covered g7.\n"
    )
    out = assemble_report(
        g, [2], narrative, tmp_path / "r.md",
        boards_at="off", render_eval_graph=False,
    )
    text = out.read_text(encoding="utf-8")
    assert "Qxg7#" in text          # the counterfactual line was NOT stripped
    assert "(Qxg7#)" in text


# ---------------------------------------------------------------------------
# §8 row 1 — a legal continuation counterfactual ("better was 24...Rf8, when
# 25. g5 hxg5 26. fxg5 holds"), numbered from 24. Branches from fen_before of move 24.
# ---------------------------------------------------------------------------
def test_legal_continuation_counterfactual_passes(make_move, make_game):
    g = _game(
        make_move, make_game,
        ply=48, move_number=24, side="Black", san="Kf8", uci="g8f8",  # actual move differs from Rf8
        fen_before="4r1k1/5pp1/7p/8/5PP1/8/8/6K1 b - - 0 24",
        # Only fen_before (candidate C2) is needed to validate this counterfactual line.
        fen_after="4r1k1/5pp1/7p/8/5PP1/8/8/6K1 b - - 0 24",
    )
    report = "Better was *(24...Rf8, when 25. g5 hxg5 26. fxg5 holds)*."
    assert find_unverified_variation_moves(report, g) == []
    assert validate_parenthetical_variations(report, g) == []


# ---------------------------------------------------------------------------
# §8 row 5 — a clean legal line the engine simply did not pre-compute. The whole point
# of the reframe: legality (not engine-membership) is the bar, so this SURVIVES.
# ---------------------------------------------------------------------------
def test_engine_absent_but_legal_line_survives(make_move, make_game):
    g = _game(
        make_move, make_game,
        ply=55, move_number=28, side="White", san="Kh1", uci="g1h1",
        fen_before="3r2k1/5ppp/8/8/8/8/4QPPP/5RK1 w - - 0 28",
        fen_after="3r2k1/5ppp/8/8/8/8/4QPPP/5R1K b - - 1 28",
        best_line_san="", refutation_line_san="",   # NOT in any engine line
    )
    report = "Also possible was *(28. Rd1 Rxd1 29. Qxd1)*, holding the file."
    # Engine-absent, but legal from fen_before -> must NOT be flagged and NOT returned.
    assert find_unverified_variation_moves(report, g) == []
    assert validate_parenthetical_variations(report, g) == []


# ---------------------------------------------------------------------------
# §8 row 3 — a flatly illegal move (a knight move with no knight on the board). FLAG high.
# ---------------------------------------------------------------------------
def _no_knight_game(make_move, make_game):
    return _game(
        make_move, make_game,
        ply=49, move_number=25, side="White", san="Kf1", uci="e1f1",
        fen_before="4k3/8/8/8/8/8/4P3/4K3 w - - 0 25",
        fen_after="4k3/8/8/8/8/8/4P3/5K2 b - - 1 25",
    )


def test_illegal_move_flags_high(make_move, make_game):
    g = _no_knight_game(make_move, make_game)
    report = "This runs into *(25. Nf3 and wins)*."
    records = validate_parenthetical_variations(report, g)
    flags = [r for r in records if r.verdict == "FLAG"]
    assert len(flags) == 1
    assert flags[0].first_illegal_san == "Nf3"
    assert flags[0].confidence == "high"
    assert flags[0].anchor_ply == 49
    assert "Nf3" in find_unverified_variation_moves(report, g)


# ---------------------------------------------------------------------------
# §8 row 4 — an illegal SEQUENCE: Bxh7+ and Kxh7 are legal here, but the follow-up
# Ng5+ is illegal (no knight). The old flat-set test could not catch this; we do. FLAG.
# ---------------------------------------------------------------------------
def test_illegal_sequence_flags(make_move, make_game):
    g = _game(
        make_move, make_game,
        ply=51, move_number=26, side="White", san="Kh1", uci="g1h1",
        fen_before="6k1/7p/8/8/8/3B4/8/6K1 w - - 0 26",
        fen_after="6k1/7p/8/8/8/3B4/8/7K b - - 1 26",
    )
    report = "White lunged with *(26. Bxh7+ Kxh7 27. Ng5+)* but it does not exist."
    records = validate_parenthetical_variations(report, g)
    flags = [r for r in records if r.verdict == "FLAG"]
    assert len(flags) == 1
    # The first two moves are legal; the sequence first breaks at Ng5.
    assert flags[0].first_illegal_san == "Ng5"
    assert "Ng5" in find_unverified_variation_moves(report, g)


# ---------------------------------------------------------------------------
# §8 row 6 — a well-intentioned line with a SAN typo ('exg5' is a non-adjacent pawn
# capture, impossible in any position). ABSTAIN low — never a high-confidence FLAG,
# never stripped. This is the false positive James explicitly forbids.
# ---------------------------------------------------------------------------
def test_malformed_san_abstains_low(make_move, make_game):
    g = _game(
        make_move, make_game,
        ply=48, move_number=24, side="Black", san="Kf8", uci="g8f8",
        fen_before="6k1/4p1pp/8/6P1/8/8/8/6K1 b - - 0 24",
        fen_after="5k2/4p1pp/8/6P1/8/8/8/6K1 w - - 1 25",
    )
    report = "He could try *(24...exg5 holds)* but the move is mis-written."
    records = validate_parenthetical_variations(report, g)
    assert len(records) == 1
    assert records[0].verdict == "ABSTAIN"
    assert records[0].confidence == "low"
    # ABSTAIN must NOT surface as a strip-eligible / high-confidence flag.
    assert find_unverified_variation_moves(report, g) == []


# ---------------------------------------------------------------------------
# Shim contract — find_unverified_variation_moves returns ONLY category-2 (FLAG) SANs.
# ---------------------------------------------------------------------------
def test_shim_returns_only_flags_not_abstains(make_move, make_game):
    # A FLAG (illegal Nf3) and an ABSTAIN (malformed exg5) in one report.
    g = _no_knight_game(make_move, make_game)
    report = "Bad: *(25. Nf3 wins)*. Mis-typed: *(25. exg5 holds)*."
    shim = find_unverified_variation_moves(report, g)
    assert "Nf3" in shim          # the illegal move is returned
    assert "exg5" not in shim     # the malformed move is not (it ABSTAINs)


def test_record_type_is_unverifiedvariation(make_move, make_game):
    g = _no_knight_game(make_move, make_game)
    records = validate_parenthetical_variations("*(25. Nf3)*", g)
    assert records and isinstance(records[0], UnverifiedVariation)
    assert records[0].candidate_fens  # the boards tried are recorded for the human
