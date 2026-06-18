"""Narrator pure-function tests — no Stockfish, no API key.

The narrator decides which engine facts become the JSON the model may use, so a
regression here silently corrupts every report. Covers eval formatting (incl. the
terminal-checkmate sign fix), the time-control humaniser (incl. daily), name
resolution (feature 5), and the _move_to_dict serialization (tier gating + the 2A
variations array), plus the daily-protocol injection in build_user_prompt.
"""
from analyzer import MATE_SCORE
from narrator import (
    _format_eval,
    _humanize_time_control,
    _move_to_dict,
    build_user_prompt,
    resolve_player_names,
)


# --- _format_eval -----------------------------------------------------------
def test_format_eval_basic():
    assert _format_eval(150, None) == "+1.50"
    assert _format_eval(-30, None) == "-0.30"
    assert _format_eval(None, None) == "0.00"
    assert _format_eval(None, 3) == "#3 for White"
    assert _format_eval(None, -2) == "#2 for Black"


def test_format_eval_terminal_checkmate_keeps_sign():
    assert "White wins" in _format_eval(MATE_SCORE, None)
    assert "Black wins" in _format_eval(-MATE_SCORE, None)


# --- _humanize_time_control (feature 7) -------------------------------------
def test_humanize_time_control():
    assert "Daily" in _humanize_time_control("1/259200")
    assert "Daily" in _humanize_time_control("86400")
    assert "rapid" in _humanize_time_control("600")
    assert "classical" in _humanize_time_control("5400")
    assert "blitz" in _humanize_time_control("300")
    assert "increment" in _humanize_time_control("600+5")
    assert _humanize_time_control("?") == "?"
    assert _humanize_time_control("") == ""
    # OTB classical controls (backlog #12): increment must include category label.
    assert "classical" in _humanize_time_control("5400+30")   # 90+30 — standard FIDE classical
    assert "classical" in _humanize_time_control("3600+30")   # 60+30
    assert "rapid" in _humanize_time_control("600+5")         # 10+5 — online rapid
    assert "blitz" in _humanize_time_control("180+2")         # 3+2 — FIDE blitz
    assert "bullet" in _humanize_time_control("60+1")         # 1+1 — bullet


# --- resolve_player_names (feature 5) ---------------------------------------
def test_resolve_player_names_header_wins():
    assert resolve_player_names({"White": "Alice", "Black": "Bob"}) == ("Alice", "Bob")


def test_resolve_player_names_filename_fallback():
    names = resolve_player_names({"White": "?", "Black": ""}, "x/Carl vs Dana.pgn")
    assert names == ("Carl", "Dana")


def test_resolve_player_names_colour_fallback():
    assert resolve_player_names({}) == ("White", "Black")
    assert resolve_player_names({"White": "White", "Black": "Black"}) == ("White", "Black")


# --- _move_to_dict ----------------------------------------------------------
def test_move_to_dict_from_to(make_move):
    d = _move_to_dict(make_move(uci="e2e4"), tier=1)
    assert d["from"] == "e2" and d["to"] == "e4"
    assert _move_to_dict(make_move(uci=""), tier=1)["from"] == ""


def test_move_to_dict_tier_gating(make_move):
    # Tier 0 is acknowledge-only — no board-truth anchors.
    d0 = _move_to_dict(make_move(), tier=0)
    assert "pieces" not in d0 and "eval_before" not in d0 and "variations" not in d0
    # Tier 1 gets pieces + eval_before (anti-hallucination anchors) but not variations.
    d1 = _move_to_dict(make_move(), tier=1)
    assert "pieces" in d1 and "eval_before" in d1 and "variations" not in d1


def test_move_to_dict_variations_at_tier2(make_move):
    m = make_move(
        best_line_san="24...Rf8 25. g5",
        refutation_line_san="25. g5 Kxf6 26. gxf6",
        top_alternatives=[{"san": "h6", "cp": -40, "mate": None,
                           "pv_san": "h6 g5", "pv_numbered": "24...h6 25. g5"}],
    )
    d = _move_to_dict(m, tier=3)
    assert "variations" in d
    types = {v["type"] for v in d["variations"]}
    assert {"best", "refutation", "alternative"} <= types
    # numbered lines are ready to quote
    assert any("25. g5" in v["line"] for v in d["variations"])


# --- build_user_prompt: daily injection + names -----------------------------
def test_build_user_prompt_injects_daily_block(make_move, make_game):
    g = make_game([make_move()], White="A", Black="B", TimeControl="1/259200")
    prompt = build_user_prompt(g, [1], {}, with_knowledge=False)
    assert "DAILY / CORRESPONDENCE" in prompt
    assert "time trouble" in prompt


def test_build_user_prompt_no_daily_for_rapid(make_move, make_game):
    g = make_game([make_move()], White="A", Black="B", TimeControl="600")
    prompt = build_user_prompt(g, [1], {}, with_knowledge=False)
    assert "DAILY / CORRESPONDENCE" not in prompt


def test_build_user_prompt_uses_real_names(make_move, make_game):
    g = make_game([make_move()], White="Magnus", Black="Hikaru")
    prompt = build_user_prompt(g, [1], {}, with_knowledge=False)
    assert "Magnus" in prompt and "Hikaru" in prompt
