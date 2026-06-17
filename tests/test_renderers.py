"""Tests for renderers.py — SVG board diagrams and PNG eval chart.

No Stockfish or API calls. render_board_svg uses python-chess directly;
render_eval_graph_png uses matplotlib in Agg (headless) mode.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from renderers import render_board_svg, save_board_svg, render_eval_graph_png


STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


# ---------------------------------------------------------------------------
# render_board_svg
# ---------------------------------------------------------------------------

def test_render_board_svg_returns_svg_string():
    svg = render_board_svg(STARTING_FEN)
    assert isinstance(svg, str)
    assert "<svg" in svg


def test_render_board_svg_with_last_move():
    svg = render_board_svg(AFTER_E4_FEN, last_move_uci="e2e4")
    assert "<svg" in svg


def test_render_board_svg_flipped():
    svg_white = render_board_svg(STARTING_FEN, flipped=False)
    svg_black = render_board_svg(STARTING_FEN, flipped=True)
    # The SVG content differs when the board is flipped.
    assert svg_white != svg_black


def test_render_board_svg_custom_size():
    svg = render_board_svg(STARTING_FEN, size=200)
    assert "200" in svg


# ---------------------------------------------------------------------------
# save_board_svg
# ---------------------------------------------------------------------------

def test_save_board_svg_creates_file(tmp_path):
    out = tmp_path / "board.svg"
    result = save_board_svg(STARTING_FEN, out)
    assert result == out
    assert out.is_file()
    assert "<svg" in out.read_text(encoding="utf-8")


def test_save_board_svg_creates_parent_dirs(tmp_path):
    out = tmp_path / "nested" / "deep" / "board.svg"
    save_board_svg(STARTING_FEN, out)
    assert out.is_file()


# ---------------------------------------------------------------------------
# render_eval_graph_png  (uses conftest make_move / make_game)
# ---------------------------------------------------------------------------

def test_render_eval_graph_png_creates_file(tmp_path, make_move, make_game):
    moves = [
        make_move(ply=1, eval_after_cp=20, classification="best"),
        make_move(ply=2, eval_after_cp=-10, classification="good"),
        make_move(ply=3, eval_after_cp=200, classification="blunder"),
        make_move(ply=4, eval_after_cp=150, classification="mistake"),
    ]
    game = make_game(moves, White="Kasparov", Black="Topalov")
    out = tmp_path / "eval.png"
    result = render_eval_graph_png(game, out)
    assert result == out
    assert out.is_file()
    assert out.stat().st_size > 0


def test_render_eval_graph_png_handles_mate_score(tmp_path, make_move, make_game):
    moves = [
        make_move(ply=1, eval_after_cp=None, mate_after=3, classification="best"),
        make_move(ply=2, eval_after_cp=None, mate_after=-2, classification="best"),
    ]
    game = make_game(moves)
    out = tmp_path / "mate_eval.png"
    render_eval_graph_png(game, out)
    assert out.is_file()
