"""Tests for structured context fields in build_user_prompt and generate_narrative.

Covers the three new optional parameters added for fixes 4, 5, 6 from the
retrospective: audience_level, recipient, and white/black-context passthrough.
No Stockfish or API key needed — all tests exercise pure functions.
"""
from narrator import build_user_prompt


# --- audience_level --------------------------------------------------------

def test_audience_level_appears_in_prompt(make_move, make_game):
    g = make_game([make_move()], White="A", Black="B")
    prompt = build_user_prompt(g, [1], {}, audience_level="Beginner", with_knowledge=False)
    assert "Beginner" in prompt


def test_audience_level_absent_means_no_calibration_block(make_move, make_game):
    g = make_game([make_move()], White="A", Black="B")
    prompt = build_user_prompt(g, [1], {}, with_knowledge=False)
    assert "Audience calibration" not in prompt


def test_all_audience_levels_accepted(make_move, make_game):
    g = make_game([make_move()], White="A", Black="B")
    for level in ("Beginner", "Casual", "Club", "Advanced"):
        prompt = build_user_prompt(g, [1], {}, audience_level=level, with_knowledge=False)
        assert level in prompt


# --- recipient -------------------------------------------------------------

def test_recipient_appears_in_prompt(make_move, make_game):
    g = make_game([make_move()], White="A", Black="B")
    prompt = build_user_prompt(g, [1], {}, recipient="my dad", with_knowledge=False)
    assert "my dad" in prompt


def test_recipient_absent_means_no_recipient_block(make_move, make_game):
    g = make_game([make_move()], White="A", Black="B")
    prompt = build_user_prompt(g, [1], {}, with_knowledge=False)
    assert "Recipient" not in prompt


def test_recipient_and_audience_level_coexist(make_move, make_game):
    g = make_game([make_move()], White="A", Black="B")
    prompt = build_user_prompt(
        g, [1], {}, recipient="grandma", audience_level="Beginner", with_knowledge=False
    )
    assert "grandma" in prompt
    assert "Beginner" in prompt


# --- white/black context in user_context already works (regression guard) ---

def test_white_black_context_still_in_player_context_block(make_move, make_game):
    g = make_game([make_move()], White="Alice", Black="Bob")
    ctx = {"white_player": "an attacker", "black_player": "positional style"}
    prompt = build_user_prompt(g, [1], ctx, with_knowledge=False)
    assert "an attacker" in prompt
    assert "positional style" in prompt
