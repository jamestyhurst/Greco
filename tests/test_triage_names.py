"""Triage tests for the v0.9 fixes — pure, no engine.

The player-named tier boost now derives from PGN headers (so GUI/web get it too,
#23/#28), and the turning-point detector is seeded from the real start eval (#4).
"""
from triage import _detect_turning_points, _has_named_players, annotate_with_tiers


def test_has_named_players():
    assert _has_named_players({"White": "Alice", "Black": "Bob"}) is True
    assert _has_named_players({"White": "?", "Black": "?"}) is False
    assert _has_named_players({"White": "White", "Black": "Black"}) is False
    assert _has_named_players({}) is False


def _game_ending_in(make_move, make_game, classification, **headers):
    moves = [make_move(ply=i, move_number=i) for i in range(1, 10)]
    moves.append(make_move(ply=10, move_number=10, classification=classification))
    return make_game(moves, **headers)


def test_named_players_boost_inaccuracy(make_move, make_game):
    # A real-named game (headers) boosts the named player's inaccuracy 2 -> 3,
    # even without explicit --white-context.
    g = _game_ending_in(make_move, make_game, "inaccuracy", White="Alice", Black="Bob")
    tiers = annotate_with_tiers(g, {"user_is": "white"})
    assert tiers[-1] == 3


def test_unnamed_game_no_boost(make_move, make_game):
    # Placeholder White/Black headers -> not "named" -> inaccuracy stays tier 2.
    g = _game_ending_in(make_move, make_game, "inaccuracy")  # default placeholder headers
    tiers = annotate_with_tiers(g, {"user_is": "white"})
    assert tiers[-1] == 2


def test_turning_points_seeded_from_start_eval(make_move, make_game):
    # A game that is already winning from move 1 must not flag ply 1 as a turning
    # point (seeded from eval_before, not a literal 0).
    m1 = make_move(ply=1, eval_before_cp=600, eval_after_cp=600)
    m2 = make_move(ply=2, eval_before_cp=600, eval_after_cp=600)
    assert 1 not in _detect_turning_points(make_game([m1, m2]))
