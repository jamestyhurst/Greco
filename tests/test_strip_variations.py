"""Tests for strip_unverified_variations — backlog #26.

The function must remove parentheticals whose variation notation contains moves
the engine never provided, while leaving all other text (including parentheticals
without variation notation, and parentheticals with only verified moves) intact.
"""
from outputs import strip_unverified_variations


# --- helper ------------------------------------------------------------------

def _game(make_move, make_game, *, best_line="", refutation="", san="e4"):
    """Game with one move; engine lines control the allowed-move set."""
    m = make_move(san=san, best_line_san=best_line, refutation_line_san=refutation)
    return make_game([m])


# --- clean prose: nothing stripped -------------------------------------------

def test_no_parentheticals_unchanged(make_move, make_game):
    game = _game(make_move, make_game)
    md = "**1. e4** is the King's Pawn opening.\n\nWhite takes central space."
    assert strip_unverified_variations(md, game) == md


def test_prose_parenthetical_not_variation_is_kept(make_move, make_game):
    game = _game(make_move, make_game)
    md = "White played e4 (a classic choice) and Black responded."
    assert strip_unverified_variations(md, game) == md


def test_verified_variation_is_kept(make_move, make_game):
    """A parenthetical whose moves are all in the engine lines survives."""
    game = _game(make_move, make_game, best_line="1. Nf3 d5 2. g3")
    md = "White could have played (1. Nf3 d5 2. g3) instead."
    assert strip_unverified_variations(md, game) == md


# --- confabulated variations: stripped ---------------------------------------

def test_unverified_variation_is_stripped(make_move, make_game):
    """A parenthetical with an invented move is removed."""
    game = _game(make_move, make_game, san="e4")  # only 'e4' allowed
    md = "But (1. Qxh7 Kg8) was possible."
    result = strip_unverified_variations(md, game)
    assert "Qxh7" not in result
    assert "Kg8" not in result


def test_surrounding_prose_preserved_after_strip(make_move, make_game):
    """The prose before and after a stripped parenthetical must survive."""
    game = _game(make_move, make_game, san="e4")
    md = "White threatened mate (1. Qxh7+ Kf8) which Black could not meet."
    result = strip_unverified_variations(md, game)
    assert "White threatened mate" in result
    assert "which Black could not meet" in result


def test_only_bad_paren_stripped_good_paren_kept(make_move, make_game):
    """Two parentheticals: the verified one stays, the confabulated one goes."""
    game = _game(make_move, make_game, best_line="1. Nf3")
    md = "After e4 (1. Nf3 is the engine line) White attacks (1. Qh5 Nc6 Bc4)."
    result = strip_unverified_variations(md, game)
    assert "1. Nf3" in result
    assert "Qh5" not in result


def test_empty_string_unchanged(make_move, make_game):
    game = _game(make_move, make_game)
    assert strip_unverified_variations("", game) == ""


def test_no_game_moves_strips_all_variation_parens(make_move, make_game):
    """With an empty allowed-move set every variation parenthetical is stripped."""
    game = make_game([])
    md = "The refutation was (1. Rxf7 Kxf7 2. Qh5+)."
    result = strip_unverified_variations(md, game)
    assert "Rxf7" not in result
