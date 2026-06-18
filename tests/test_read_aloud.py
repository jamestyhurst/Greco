"""Tests for the 'Read aloud' button in generated HTML reports — backlog #9.

All tests are file-system only (tmp_path); no engine or API key needed.
"""
from pathlib import Path

from outputs import markdown_to_html


_MINIMAL_MD = """\
# Alice vs Bob

*Bullet · 2026-01-01 · **1-0***

---

## Opening

**1. e4** opens the game. Black responded with **1...e5**.

## Middlegame

**2. Nf3** develops the knight, eyeing the e5-pawn.
"""


def test_read_aloud_button_present(tmp_path):
    """The generated HTML must contain the read-aloud toggle button."""
    md = tmp_path / "report.md"
    md.write_text(_MINIMAL_MD, encoding="utf-8")
    html_path = markdown_to_html(md)
    html = html_path.read_text(encoding="utf-8")
    assert "Read aloud" in html or "read-aloud" in html.lower()


def test_speech_synthesis_api_used(tmp_path):
    """The inline script must reference speechSynthesis (Web Speech API)."""
    md = tmp_path / "report.md"
    md.write_text(_MINIMAL_MD, encoding="utf-8")
    html_path = markdown_to_html(md)
    html = html_path.read_text(encoding="utf-8")
    assert "speechSynthesis" in html


def test_read_aloud_absent_when_disabled(tmp_path):
    """When read_aloud=False is passed, the button must not appear."""
    md = tmp_path / "report.md"
    md.write_text(_MINIMAL_MD, encoding="utf-8")
    html_path = markdown_to_html(md, read_aloud=False)
    html = html_path.read_text(encoding="utf-8")
    assert "speechSynthesis" not in html
