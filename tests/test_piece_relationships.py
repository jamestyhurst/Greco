"""Tests for the defense/hanging relationship geometry (analyzer.compute_piece_relationships)
and its wiring into the narrator fact packet.

This closes the geometry gap behind a real report-critique bug: Greco once claimed a rook
defended a bishop on the same rank when a pawn sat between them. python-chess's attacker
bitboards already account for blockers on the line/rank/diagonal — the bug was that nothing
in Greco computed or exposed that fact, so the narrator free-wrote a defense claim with no
ground truth to check it against. These tests lock in that the geometry is correct (blocked
vs. open lines) and that the narrator only ever receives what genuinely exists on the board.
"""
import chess

from analyzer import GameAnalysis, MoveAnalysis, compute_piece_relationships
from narrator import SYSTEM_PROMPT_BASE, _move_to_dict

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


# ----------------------------------------------------------------------------
# compute_piece_relationships — pure geometry, engine-free
# ----------------------------------------------------------------------------

def test_blocked_rook_does_not_defend_through_pawn():
    # The exact reported shape: rook and bishop on the same rank with a pawn
    # sitting between them. The rook must NOT be credited with defending the
    # bishop — python-chess's attacker geometry already knows the pawn blocks it.
    board = chess.Board("4k3/8/8/8/8/R3P2B/8/4K3 w - - 0 1")
    defends, hanging = compute_piece_relationships(board)
    assert not any("a3" in d and "h3" in d for d in defends)


def test_open_rank_rook_defends_bishop():
    # Same rank, no blocker: the rook genuinely does defend the bishop.
    board = chess.Board("4k3/8/8/8/8/R6B/8/4K3 w - - 0 1")
    defends, _ = compute_piece_relationships(board)
    assert any("Rook on a3 defends bishop on h3" == d for d in defends)


def test_pawn_can_be_a_defender():
    # A pawn defending a piece is a common, important claim ("the pawn holds the bishop").
    board = chess.Board("4k3/8/8/8/3P4/4b3/8/4K3 w - - 0 1")
    # White pawn d4 defends nothing of White's here; flip to a real pawn-defends-piece shape:
    board = chess.Board("4k3/8/8/8/4B3/3P4/8/4K3 w - - 0 1")
    defends, _ = compute_piece_relationships(board)
    assert any("Pawn on d3 defends bishop on e4" == d for d in defends)


def test_pawn_defended_pawn_is_excluded():
    # Pawn-chain internals are covered by the doubled/isolated/backward-pawn fields,
    # not this one — a pawn defending another pawn should not appear in `defends`.
    board = chess.Board("4k3/8/8/8/3P4/2P5/8/4K3 w - - 0 1")
    defends, _ = compute_piece_relationships(board)
    assert not any("defends pawn" in d for d in defends)


def test_king_can_be_a_defender():
    board = chess.Board("4k3/8/8/8/8/8/3KN3/8 w - - 0 1")
    defends, _ = compute_piece_relationships(board)
    assert any("King on d2 defends knight on e2" == d for d in defends)


def test_hanging_piece_detected():
    # Black bishop on e4 attacked by the d3-pawn with no Black defender.
    board = chess.Board("4k3/8/8/8/4b3/3P4/8/4K3 w - - 0 1")
    _, hanging = compute_piece_relationships(board)
    assert "Black bishop on e4" in hanging


def test_defended_piece_is_not_hanging():
    # Same attacked bishop, but now Black has a defender for it (pawn on d5).
    board = chess.Board("4k3/8/8/3p4/4b3/3P4/8/4K3 b - - 0 1")
    _, hanging = compute_piece_relationships(board)
    assert "Black bishop on e4" not in hanging


def test_king_never_listed_as_hanging():
    # A king in check is not "hanging" in the piece sense — it is out of scope by design.
    board = chess.Board("4k3/8/8/8/8/8/4R3/4K3 b - - 0 1")
    assert board.is_check()
    _, hanging = compute_piece_relationships(board)
    assert not any("king" in h.lower() for h in hanging)


def test_both_colors_computed_in_one_pass():
    # White pawn d3 defends White knight c4; White king c1 attacks the undefended
    # Black knight on d2. One call surfaces both a White defense fact and a Black
    # hanging fact.
    board = chess.Board("4k3/8/8/8/2N5/3P4/3n4/2K3R1 w - - 0 1")
    defends, hanging = compute_piece_relationships(board)
    assert any(d.startswith("Pawn on d3 defends") for d in defends)
    assert "Black knight on d2" in hanging


# ----------------------------------------------------------------------------
# Narrator serialization — the fact packet the model actually receives
# ----------------------------------------------------------------------------

def _mv(tier=2, **overrides):
    kwargs = dict(
        ply=1, move_number=1, side="White",
        san="e4", uci="e2e4",
        fen_before=START_FEN, fen_after=AFTER_E4,
        eval_before_cp=20, mate_before=None,
        eval_after_cp=25, mate_after=None,
        best_move_san="d4", best_move_uci="d2d4",
        best_pv_san="1. d4", cp_loss=15,
    )
    kwargs.update(overrides)
    return _move_to_dict(MoveAnalysis(**kwargs), tier)


def test_narrator_defends_present_when_nonempty():
    d = _mv(tier=1, defends=["Rook on a3 defends bishop on h3"])
    assert d["defends"] == ["Rook on a3 defends bishop on h3"]


def test_narrator_defends_absent_when_empty():
    # No relationship at all: omit the key rather than send an empty list (matches
    # the existing `attacks`/`overloaded_defender` convention elsewhere in this function).
    d = _mv(tier=1, defends=[])
    assert "defends" not in d


def test_narrator_hanging_emitted_even_when_empty():
    # An empty `hanging` list is still affirmative evidence (nothing is loose right
    # now), so it is always present at tier >= 1 — mirroring the `best_attacks` rule.
    d = _mv(tier=1, hanging=[])
    assert d["hanging"] == []


def test_narrator_hanging_lists_real_targets():
    d = _mv(tier=2, hanging=["Black bishop on e4"])
    assert d["hanging"] == ["Black bishop on e4"]


def test_narrator_defends_and_hanging_absent_below_tier_one():
    # Tier 0 is acknowledge-only — no prose is generated, so the ground-truth
    # payload is skipped entirely, same as `pieces` and `eval_before`.
    d = _mv(tier=0, defends=["Rook on a3 defends bishop on h3"], hanging=["Black bishop on e4"])
    assert "defends" not in d
    assert "hanging" not in d


# ----------------------------------------------------------------------------
# Prompt content — the new whitelist rule must actually ship
# ----------------------------------------------------------------------------

def test_prompt_defends_hanging_rule_present():
    assert "Do NOT assert that one piece defends, guards, or protects another" in SYSTEM_PROMPT_BASE
    assert "`defends` field" in SYSTEM_PROMPT_BASE
    assert "`hanging`" in SYSTEM_PROMPT_BASE


def test_prompt_does_not_leak_internal_constant_name():
    assert "_DEFENDS_HANGING_RULE" not in SYSTEM_PROMPT_BASE
