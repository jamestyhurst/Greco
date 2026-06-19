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


# --- variation validator (legal-from-branch reframe) ------------------------
# Semantics changed (docs/specs/VARIATION_VALIDATOR.md): the validator now replays
# the line on REAL branch boards, so these fixtures carry real FENs. A line that is
# LEGAL from a plausible branch passes (engine-membership no longer required); only a
# line that is illegal from every candidate board is flagged. The fuller §8 matrix
# lives in test_variation_validator.py.
def test_validator_passes_clean_legal_line(make_move, make_game):
    # A legal line the engine did NOT pre-compute — passes purely on legality.
    m = make_move(
        side="White", move_number=28, san="Kh1", uci="g1h1",
        fen_before="3r2k1/5ppp/8/8/8/8/4QPPP/5RK1 w - - 0 28",
        fen_after="3r2k1/5ppp/8/8/8/8/4QPPP/5R1K b - - 1 28",
    )
    g = make_game([m])
    report = "Also possible was *(28. Rd1 Rxd1 29. Qxd1)*."
    assert find_unverified_variation_moves(report, g) == []


def test_validator_flags_illegal_move(make_move, make_game):
    # An illegal move (a knight move with no knight on the board) is flagged.
    m = make_move(
        side="White", move_number=25, san="Kf1", uci="e1f1",
        fen_before="4k3/8/8/8/8/8/4P3/4K3 w - - 0 25",
        fen_after="4k3/8/8/8/8/8/4P3/5K2 b - - 1 25",
    )
    g = make_game([m])
    report = "This runs into *(25. Nf3 and wins)*."
    flagged = find_unverified_variation_moves(report, g)
    assert "Nf3" in flagged


# --- header HTML escaping (#29) ---------------------------------------------
def test_build_header_escapes_untrusted_names(make_move, make_game):
    g = make_game([make_move()], White="<img src=x onerror=alert(1)>", Black="Bob")
    header = build_header(g)
    assert "<img" not in header
    assert "&lt;img" in header
