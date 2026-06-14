"""Report naming + the shareable single-file export."""
from __future__ import annotations

import re

import outputs
from analyzer import GameAnalysis


def test_time_control_category():
    assert outputs.time_control_category("60") == "Bullet"
    assert outputs.time_control_category("180+2") == "Blitz"
    assert outputs.time_control_category("600") == "Rapid"
    assert outputs.time_control_category("5400") == "Classical"
    assert outputs.time_control_category("1/259200") == "Daily"
    assert outputs.time_control_category("?") == ""
    assert outputs.time_control_category("") == ""


def test_safe_filename_strips_illegal_chars():
    cleaned = outputs._safe_filename('a/b:c*d?e')
    assert not re.search(r'[<>:"/\\|?*]', cleaned)
    assert outputs._safe_filename("") == "game"


def test_report_basename_includes_players_category_year():
    game = GameAnalysis(
        headers={"White": "Bobby Fischer", "Black": "Boris Spassky",
                 "TimeControl": "5400", "Date": "1972.07.11"},
        moves=[], result="1-0", final_eval_cp=0, final_mate=None,
    )
    base = outputs.report_basename(game)
    assert "Bobby Fischer vs. Boris Spassky" in base
    assert "Classical" in base
    assert "1972" in base


def test_export_shareable_html_inlines_and_preserves_original(tmp_path):
    folder = tmp_path / "Test vs Test"
    folder.mkdir()
    assets = folder / "Test vs Test_assets"
    assets.mkdir()
    (assets / "board.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><rect width="8" height="8"/></svg>',
        encoding="utf-8",
    )
    original_html = (
        '<!doctype html><html><body>'
        '<img alt="board" src="Test vs Test_assets/board.svg">'
        '<img alt="graph" src="data:image/png;base64,AAAA">'
        '</body></html>'
    )
    src = folder / "Test vs Test.html"
    src.write_text(original_html, encoding="utf-8")

    out = outputs.export_shareable_html(folder)

    # Clearly labelled export, written alongside the source.
    assert out.name == "Test vs Test (shareable).html"
    assert out.exists()

    text = out.read_text(encoding="utf-8")
    assert "Test vs Test_assets/board.svg" not in text   # external svg got inlined
    assert "<svg" in text                                  # ...as inline SVG
    assert "data:image/png;base64,AAAA" in text            # already-inline asset kept

    # The original report files are untouched (export, not replacement).
    assert "Test vs Test_assets/board.svg" in src.read_text(encoding="utf-8")
