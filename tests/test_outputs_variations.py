"""Outputs tests for the v0.9 changes — pure, no engine/API.

Daily detection (feature 7), the 'off' diagram gate (#8), the variation
confabulation validator (2A safety net), and HTML escaping of untrusted PGN
header values (#29).
"""
from outputs import (
    build_header,
    find_unverified_variation_moves,
    is_daily_game,
    select_diagram_plies,
)


# --- is_daily_game (feature 7) ----------------------------------------------
def test_is_daily_game():
    assert is_daily_game({"TimeControl": "1/259200"}) is True
    assert is_daily_game({"TimeControl": "86400"}) is True
    assert is_daily_game({"TimeControl": "604800"}) is True
    assert is_daily_game({"TimeControl": "600"}) is False
    assert is_daily_game({"TimeControl": "180+2"}) is False
    assert is_daily_game({"TimeControl": "?", "Event": "Daily Chess game"}) is True
    assert is_daily_game({"TimeControl": "-", "Event": "Correspondence"}) is True
    assert is_daily_game({"TimeControl": "?", "Event": "Rated Rapid game"}) is False
    assert is_daily_game({}) is False


# --- select_diagram_plies 'off' (#8) ----------------------------------------
def test_boards_off_renders_no_diagrams(make_move, make_game):
    moves = [make_move(ply=i, move_number=i) for i in range(1, 13)]
    g = make_game(moves)
    assert select_diagram_plies(g, [3] * 12, "off", 6) == set()


def test_boards_tier3_includes_periodic(make_move, make_game):
    moves = [make_move(ply=i, move_number=i) for i in range(1, 13)]
    g = make_game(moves)
    plies = select_diagram_plies(g, [1] * 12, "tier3", 6)
    assert 6 in plies and 12 in plies  # periodic snapshots survive


# --- variation validator (2A) -----------------------------------------------
def test_validator_passes_clean_quoted_line(make_move, make_game):
    m = make_move(
        side="Black", move_number=24, san="Kg7",
        best_line_san="24...Rf8 25. g5",
        refutation_line_san="25. g5 Kxf6 26. gxf6",
    )
    g = make_game([m])
    report = "Better was *(24...Rf8 25. g5)*, and *(25. g5 Kxf6 26. gxf6)* punishes it."
    assert find_unverified_variation_moves(report, g) == []


def test_validator_flags_invented_move(make_move, make_game):
    m = make_move(
        side="Black", move_number=24, san="Kg7",
        refutation_line_san="25. g5 Kxf6 26. gxf6",
    )
    g = make_game([m])
    report = "This runs into *(25. g5 Kxf6 26. Qh8 winning)*."
    flagged = find_unverified_variation_moves(report, g)
    assert "Qh8" in flagged


# --- header HTML escaping (#29) ---------------------------------------------
def test_build_header_escapes_untrusted_names(make_move, make_game):
    g = make_game([make_move()], White="<img src=x onerror=alert(1)>", Black="Bob")
    header = build_header(g)
    assert "<img" not in header
    assert "&lt;img" in header
