"""Tests for assemble_report() and markdown_to_html() in outputs.py.

Uses tmp_path and the conftest GameAnalysis fixtures. No engine, no API.
Targets the uncovered lines in outputs.py (420-489, 817-881).
"""
from __future__ import annotations

from outputs import assemble_report, markdown_to_html


# --- assemble_report -------------------------------------------------------

def test_assemble_report_creates_md_file(tmp_path, make_move, make_game):
    game = make_game(
        [make_move(ply=1, san="e4", uci="e2e4",
                   fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                   fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")],
        White="Kasparov", Black="Deep Blue",
    )
    out = tmp_path / "report.md"
    result = assemble_report(
        game, [1], "## Opening\n\nThe game opened with 1. e4.",
        output_md=out, boards_at="off", render_eval_graph=False,
    )
    assert result == out
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "Kasparov" in content
    assert "Deep Blue" in content


def test_assemble_report_strips_top_level_title(tmp_path, make_move, make_game):
    game = make_game([make_move()], White="A", Black="B")
    out = tmp_path / "report.md"
    assemble_report(
        game, [0], "# Unwanted Title Added By Model\n## Opening\n\nSome text.",
        output_md=out, boards_at="off", render_eval_graph=False,
    )
    content = out.read_text(encoding="utf-8")
    assert "# Unwanted Title Added By Model" not in content
    assert "## Opening" in content


def test_assemble_report_with_eval_graph(tmp_path, make_move, make_game):
    game = make_game(
        [make_move(ply=1, eval_after_cp=50, classification="best"),
         make_move(ply=2, eval_after_cp=-20, classification="good")],
        White="A", Black="B",
    )
    out = tmp_path / "report.md"
    assemble_report(
        game, [1, 0], "## Opening\n\nSome commentary.",
        output_md=out, boards_at="off", render_eval_graph=True,
    )
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "Evaluation" in content


def test_assemble_report_creates_parent_dirs(tmp_path, make_move, make_game):
    game = make_game([make_move()], White="A", Black="B")
    out = tmp_path / "nested" / "deep" / "report.md"
    assemble_report(
        game, [0], "## Opening\n\nText.",
        output_md=out, boards_at="off", render_eval_graph=False,
    )
    assert out.is_file()


# --- markdown_to_html -------------------------------------------------------

def test_markdown_to_html_creates_html_file(tmp_path):
    md = tmp_path / "report.md"
    md.write_text("# Test Report\n\nSome narrative text.", encoding="utf-8")
    result = markdown_to_html(md, embed_assets=False)
    assert result == md.with_suffix(".html")
    assert result.is_file()
    html = result.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    assert "<style>" in html
    assert "Test Report" in html


def test_markdown_to_html_custom_output_path(tmp_path):
    md = tmp_path / "report.md"
    md.write_text("# Hello\n\nWorld.", encoding="utf-8")
    out = tmp_path / "custom_output.html"
    result = markdown_to_html(md, html_path=out, embed_assets=False)
    assert result == out
    assert out.is_file()


def test_markdown_to_html_contains_greco_css(tmp_path):
    md = tmp_path / "report.md"
    md.write_text("# Report\n\nText.", encoding="utf-8")
    result = markdown_to_html(md, embed_assets=False)
    html = result.read_text(encoding="utf-8")
    # The Greco theme uses Palatino and the wine-dark colour.
    assert "Palatino" in html
    assert "#5E151D" in html or "#7A1C26" in html
