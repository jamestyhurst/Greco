"""Prompt-content tests — guard the new doctrine against silent edits.

Pure string assertions on the prompt builders (no engine, no API). They lock in
the 2A variation iron-rule, the 2B wasted-tempo concept (and its over-trigger
guard), the feature-5 name-preference rule, and the feature-6 featured-passage
rule, so a future prompt refactor can't quietly drop them.
"""
from narrator import SYSTEM_PROMPT_BASE, _build_system_prompt


def _voice(use_case):
    return _build_system_prompt(use_case, with_style_guide=False, with_references=False)


# --- 2A: variations iron rule -----------------------------------------------
def test_2a_iron_rule_present():
    assert "IRON RULE" in SYSTEM_PROMPT_BASE
    assert "verbatim in that move's `variations` data" in SYSTEM_PROMPT_BASE


def test_2a_truncation_rule_present():
    assert "never extend one" in SYSTEM_PROMPT_BASE


# --- 2B: wasted-tempo concept -----------------------------------------------
def test_2b_primer_reaches_every_voice():
    for v in ("companion", "coaching", "commentary"):
        assert "induces a move the opponent already wanted" in _voice(v)


def test_2b_coaching_diagnostic_present():
    sp = _voice("coaching")
    assert "wasted (or self-defeating) tempo" in sp
    assert "the threat is a gift" in sp


def test_2b_guard_against_overtriggering():
    # The model must be told when NOT to apply it (a forced recapture is neutral).
    assert "only-legal recapture" in _voice("coaching")


# --- feature 5: name preference ---------------------------------------------
def test_name_preference_rule_present():
    assert "PREFER it over a bare" in SYSTEM_PROMPT_BASE


# --- feature 6: featured passage --------------------------------------------
def test_featured_passage_rule_present():
    assert "FEATURED PASSAGE is non-discretionary" in SYSTEM_PROMPT_BASE
