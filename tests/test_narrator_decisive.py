"""Tests for the computed decisive-moments block (backlog #24).

_decisive_moments() summarises the biggest turning points and the first
decisive ply from engine data, so the narrator has ground-truth anchors
for its closing summary. Tests drive the logic through the public
build_user_prompt interface and the private helper.
"""
from narrator import _decisive_moments, build_user_prompt


# --- _decisive_moments: biggest turning points --------------------------------

def test_decisive_moments_includes_biggest_blunder(make_move, make_game):
    blunder = make_move(ply=3, move_number=2, side="White", san="Qxd8",
                        cp_loss=300, classification="blunder",
                        eval_after_cp=50, mate_after=None)
    good = make_move(ply=1, move_number=1, side="White", san="e4",
                     cp_loss=0, classification="best",
                     eval_after_cp=20, mate_after=None)
    g = make_game([good, blunder])
    block = _decisive_moments(g, [1, 3])
    assert "Qxd8" in block
    assert "300" in block
    assert "blunder" in block


def test_decisive_moments_includes_first_decisive_ply(make_move, make_game):
    normal = make_move(ply=1, move_number=1, side="White", san="e4",
                       cp_loss=0, eval_after_cp=20, mate_after=None)
    decisive = make_move(ply=3, move_number=2, side="White", san="Rxf7",
                         cp_loss=10, eval_after_cp=250, mate_after=None)
    g = make_game([normal, decisive])
    block = _decisive_moments(g, [1, 1])
    assert "Rxf7" in block
    assert "decisive" in block.lower()


def test_decisive_moments_mate_score_is_decisive(make_move, make_game):
    m = make_move(ply=5, move_number=3, side="Black", san="Qh4",
                  cp_loss=0, eval_after_cp=None, mate_after=-3)
    g = make_game([m])
    block = _decisive_moments(g, [3])
    assert "Qh4" in block
    assert "mate" in block.lower()


def test_decisive_moments_empty_when_all_moves_are_good(make_move, make_game):
    moves = [
        make_move(ply=i, move_number=(i+1)//2, cp_loss=5, eval_after_cp=20, mate_after=None)
        for i in range(1, 5)
    ]
    g = make_game(moves)
    block = _decisive_moments(g, [1, 1, 1, 1])
    assert block == ""


def test_decisive_moments_top_three_not_more(make_move, make_game):
    moves = [
        make_move(ply=i, move_number=i, side="White", san=f"m{i}",
                  cp_loss=100 + i * 10, classification="mistake",
                  eval_after_cp=20, mate_after=None)
        for i in range(1, 6)  # 5 mistakes
    ]
    g = make_game(moves)
    block = _decisive_moments(g, [2] * 5)
    # Only the top 3 should appear
    assert block.count("cp loss") <= 3


# --- decisive moments surface in build_user_prompt ---------------------------

def test_decisive_moments_block_in_build_user_prompt(make_move, make_game):
    blunder = make_move(ply=3, move_number=2, side="Black", san="Bxh2",
                        cp_loss=280, classification="blunder",
                        eval_after_cp=-50, mate_after=None)
    g = make_game([make_move(), blunder], White="A", Black="B")
    prompt = build_user_prompt(g, [1, 3], {}, with_knowledge=False)
    assert "Decisive moments" in prompt
    assert "Bxh2" in prompt


def test_no_decisive_moments_block_when_game_is_clean(make_move, make_game):
    moves = [
        make_move(ply=i, move_number=i, cp_loss=5, eval_after_cp=10, mate_after=None)
        for i in range(1, 4)
    ]
    g = make_game(moves, White="A", Black="B")
    prompt = build_user_prompt(g, [1, 1, 1], {}, with_knowledge=False)
    assert "Decisive moments" not in prompt
