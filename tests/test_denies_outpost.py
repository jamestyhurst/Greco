"""Tests for the "denies an outpost" geometry (analyzer.compute_denied_outposts) and the
tier/truth decoupling in narrator._move_to_dict.

Motivation: a quiet prophylactic move like ...a6 (denying White's c3-knight the b5
outpost) used to get triaged to Tier 1, where the engine's justifying line was withheld
(gated to Tier 2+) even though the verdict ("best": "a6") was sent at every tier
unconditionally. The model was told an alternative was better with no evidence for why,
and invented a reason ("a6 develops the rook"). This closes two gaps at once: a cheap,
engine-free geometric fact for exactly this pattern, and the removal of the tier gate on
ground-truth fields that isn't about "extra depth" but "is this claim true."
"""
import chess

from analyzer import GameAnalysis, MoveAnalysis, compute_denied_outposts
from narrator import SYSTEM_PROMPT_BASE, _move_to_dict

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


# ----------------------------------------------------------------------------
# compute_denied_outposts — pure geometry, engine-free
# ----------------------------------------------------------------------------

def test_a6_denies_the_c3_knight_b5():
    board_before = chess.Board("4k3/p7/8/8/8/2N5/8/4K3 b - - 0 1")
    move = board_before.parse_san("a6")
    board_after = board_before.copy()
    board_after.push(move)
    denied = compute_denied_outposts(board_before, move, board_after, chess.BLACK)
    assert any("c3" in d and "b5" in d for d in denied)


def test_square_already_covered_is_not_newly_denied():
    # b5 is already covered by a black knight on c7 before ...a6 is played.
    board_before = chess.Board("4k3/p1n5/8/8/8/2N5/8/4K3 b - - 0 1")
    move = board_before.parse_san("a6")
    board_after = board_before.copy()
    board_after.push(move)
    denied = compute_denied_outposts(board_before, move, board_after, chess.BLACK)
    assert denied == []


def test_no_enemy_minor_reaches_the_square():
    board_before = chess.Board("4k3/p7/8/8/8/8/8/4K3 b - - 0 1")
    move = board_before.parse_san("a6")
    board_after = board_before.copy()
    board_after.push(move)
    denied = compute_denied_outposts(board_before, move, board_after, chess.BLACK)
    assert denied == []


def test_non_pawn_move_never_triggers_it():
    board_before = chess.Board("4k3/8/8/8/8/2N5/8/4K3 b - - 0 1")
    move = board_before.parse_san("Kd8")
    board_after = board_before.copy()
    board_after.push(move)
    denied = compute_denied_outposts(board_before, move, board_after, chess.BLACK)
    assert denied == []


def test_white_pawn_can_deny_a_black_minor_too():
    # Symmetric case: White pawn e4-e5 denies a black knight on h5 the f6 outpost.
    board_before = chess.Board("4k3/8/8/7n/4P3/8/8/4K3 w - - 0 1")
    move = board_before.parse_san("e5")
    board_after = board_before.copy()
    board_after.push(move)
    denied = compute_denied_outposts(board_before, move, board_after, chess.WHITE)
    assert denied == ["e5 newly controls f6, taking it away from the knight on h5"]


# ----------------------------------------------------------------------------
# Narrator serialization — tier must govern depth, never truth
# ----------------------------------------------------------------------------

def _mv(tier=1, **overrides):
    kwargs = dict(
        ply=1, move_number=1, side="Black",
        san="a6", uci="a7a6",
        fen_before=START_FEN, fen_after=AFTER_E4,
        eval_before_cp=20, mate_before=None,
        eval_after_cp=25, mate_after=None,
        best_move_san="a6", best_move_uci="a7a6",
        best_pv_san="1...a6", best_line_san="1...a6", cp_loss=0,
    )
    kwargs.update(overrides)
    return _move_to_dict(MoveAnalysis(**kwargs), tier)


def test_denies_outpost_present_for_played_move_any_tier():
    d = _mv(tier=0, denies_outpost=["a6 newly controls b5, taking it away from the knight on c3"])
    assert d["denies_outpost"] == ["a6 newly controls b5, taking it away from the knight on c3"]


def test_denies_outpost_absent_when_empty():
    d = _mv(tier=2, denies_outpost=[])
    assert "denies_outpost" not in d


def test_best_denies_outpost_present_at_tier_one_when_alternative_exists():
    # The exact motivating case: the played move (b6) was NOT the engine's a6, and
    # the engine's a6 denies the c3-knight — this must reach the model at Tier 1.
    d = _mv(
        tier=1, san="b6", uci="b7b6", best_move_san="a6", best_move_uci="a7a6",
        best_move_denies_outpost=["a6 newly controls b5, taking it away from the knight on c3"],
    )
    assert d["best_denies_outpost"] == ["a6 newly controls b5, taking it away from the knight on c3"]


def test_best_denies_outpost_absent_when_best_equals_played():
    d = _mv(tier=1, best_move_denies_outpost=["a6 newly controls b5, taking it away from the knight on c3"])
    assert "best_denies_outpost" not in d


def test_best_line_present_at_tier_one_when_alternative_exists():
    d = _mv(tier=1, san="b6", uci="b7b6", best_move_san="a6", best_move_uci="a7a6", best_line_san="1...a6")
    assert d["best_line"] == "1...a6"


def test_best_line_absent_when_best_equals_played():
    d = _mv(tier=1, best_line_san="1...a6")
    assert "best_line" not in d


# ----------------------------------------------------------------------------
# Prompt content — the revised prophylaxis rule must actually ship
# ----------------------------------------------------------------------------

def test_prompt_points_to_denies_outpost_field():
    assert "denies_outpost` / `best_denies_outpost` field is the authoritative source" in SYSTEM_PROMPT_BASE


def test_prompt_preserves_the_originally_approved_example():
    # The a6/Nb5/"does not activate the rook" example was already approved by James's
    # own critique — the revision must not lose it while adding the new field cite.
    assert "the engine's ...a6 is prophylaxis: it takes b5 away from the c3-knight" in SYSTEM_PROMPT_BASE
    assert 'a6 does not "activate the rook"' in SYSTEM_PROMPT_BASE


def test_prompt_does_not_leak_internal_rule_constant_names():
    assert "_PROPHYLAXIS_DENIES_RULE" not in SYSTEM_PROMPT_BASE
    assert "_SYSTEM_PROMPT_BASE_PRE" not in SYSTEM_PROMPT_BASE
