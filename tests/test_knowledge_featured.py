"""Featured-passage tests (feature 6) — pure, no corpus DB needed.

We build Passage objects directly, so these run even when knowledge.db is absent
(the CI condition). Covers sentence selection, specific-theme preference, the
human-authored filter, the cleanliness guard, and the formatted block.
"""
from knowledge import (
    Passage,
    _best_quotable_sentence,
    _format_featured_passage,
    select_featured_passage,
)


def _passage(text, **kw):
    base = dict(
        title="Chess Fundamentals", author="Capablanca", year=1921,
        bucket="chess_principles", book_id="capa", chunk_index=0,
        matched_theme="endgame", matched_phrases=["endgame", "king"],
    )
    base.update(kw)
    return Passage(text=text, **base)


GOOD = (
    "The endgame is the phase where the king becomes a strong attacking piece. "
    "But it is hard. In a rook ending the active king and an outside passed pawn "
    "decide most games between otherwise equal sides."
)


def test_best_quotable_sentence_is_clean_and_in_window():
    s = _best_quotable_sentence(GOOD, ["endgame", "king", "rook"])
    assert s in GOOD
    assert 8 <= len(s.split()) <= 32
    assert not s.lower().startswith("but")  # dangling connector rejected


def test_best_quotable_sentence_rejects_notation_and_returns_empty():
    # Notation embedded with no space after the dot stays in one sentence and is
    # rejected (a move list is not a quotable maxim).
    bad = "White should improve the rook with 12.Rf1 and then push the passed pawn home soon."
    assert _best_quotable_sentence(bad, ["rook"]) == ""


def test_select_prefers_specific_theme_over_generic():
    specific = _passage(GOOD, matched_theme="endgame")
    generic = _passage(
        "Develop your pieces quickly toward the centre and castle early for safety.",
        author="Lasker", title="Common Sense in Chess", year=1896,
        matched_theme="development", matched_phrases=["development"],
    )
    sel = select_featured_passage([generic, specific])
    assert sel is not None
    passage, sentence = sel
    assert passage.author == "Capablanca"
    assert sentence in GOOD


def test_select_excludes_seed_authored():
    seed = _passage(GOOD, author="Greco Project", matched_theme="endgame")
    assert select_featured_passage([seed]) is None


def test_select_returns_none_when_no_clean_sentence():
    # Only short / notation-laden text -> nothing quotable.
    p = _passage("Then 1. e4 e5 2. Nf3.", matched_theme="opening", matched_phrases=["opening"])
    assert select_featured_passage([p]) is None


def test_format_featured_passage_shape():
    sel = select_featured_passage([_passage(GOOD)])
    passage, sentence = sel
    block = _format_featured_passage(passage, sentence)
    assert "## FEATURED PASSAGE" in block
    assert 'As Capablanca writes in Chess Fundamentals (1921):' in block
    assert sentence in block  # exact, verbatim
