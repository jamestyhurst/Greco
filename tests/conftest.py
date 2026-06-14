"""Shared test fixtures.

`make_move` / `make_game` build the analyzer dataclasses with sensible defaults so
each test overrides only the fields it cares about. The FEN strings are dummies —
triage and theme extraction read the typed fields (classification, flags, eval),
never the board text — so tests stay fast and need no engine.
"""
from __future__ import annotations

import pytest

from analyzer import GameAnalysis, MoveAnalysis


def _make_move(**overrides) -> MoveAnalysis:
    defaults = dict(
        ply=1, move_number=1, side="White", san="e4", uci="e2e4",
        fen_before="startpos", fen_after="afterpos",
        eval_before_cp=20, mate_before=None, eval_after_cp=20, mate_after=None,
        best_move_san="e4", best_move_uci="e2e4", best_pv_san="e4 e5", cp_loss=0,
    )
    defaults.update(overrides)
    return MoveAnalysis(**defaults)


def _make_game(moves, **headers) -> GameAnalysis:
    return GameAnalysis(
        headers=headers or {"White": "White", "Black": "Black"},
        moves=list(moves),
        result="1-0",
        final_eval_cp=20,
        final_mate=None,
    )


@pytest.fixture
def make_move():
    return _make_move


@pytest.fixture
def make_game():
    return _make_game
