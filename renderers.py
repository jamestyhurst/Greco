"""
Visual renderers for Greco reports:
  - render_board_svg / save_board_svg: chessboard images per position
  - render_eval_graph_png: matplotlib eval chart across the game

These are intentionally side-effect-free where possible so we can swap
backends later (e.g. a different chess rendering library, or PNG boards
via cairosvg) without disturbing the rest of Greco.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import chess
import chess.svg

from analyzer import GameAnalysis, normalize_cp


def render_board_svg(
    fen: str,
    last_move_uci: Optional[str] = None,
    check_square: Optional[int] = None,
    size: int = 360,
    flipped: bool = False,
) -> str:
    """Return an SVG string for the given FEN, highlighting the last move."""
    board = chess.Board(fen)
    last_move = (
        chess.Move.from_uci(last_move_uci) if last_move_uci else None
    )
    return chess.svg.board(
        board=board,
        lastmove=last_move,
        check=check_square,
        size=size,
        orientation=chess.BLACK if flipped else chess.WHITE,
    )


def save_board_svg(
    fen: str,
    output_path: Path,
    last_move_uci: Optional[str] = None,
    flipped: bool = False,
    size: int = 360,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    svg = render_board_svg(fen, last_move_uci=last_move_uci, size=size, flipped=flipped)
    output_path.write_text(svg, encoding="utf-8")
    return output_path


def render_eval_graph_png(
    game: GameAnalysis,
    output_path: Path,
    width: float = 10.0,
    height: float = 3.5,
    dpi: int = 120,
) -> Path:
    """
    Plot the engine evaluation across the game. Mate scores are clamped to
    +/-10 for display. Blunders and mistakes are marked.
    """
    # matplotlib is imported lazily — it's optional and heavy.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plies: List[float] = [0.0]
    evals: List[float] = [0.0]  # start at the initial position
    for move in game.moves:
        plies.append(float(move.ply))
        if move.mate_after is not None:
            evals.append(10.0 if move.mate_after > 0 else -10.0)
        elif move.eval_after_cp is not None:
            evals.append(max(-10.0, min(10.0, move.eval_after_cp / 100.0)))
        else:
            evals.append(0.0)

    fig, ax = plt.subplots(figsize=(width, height))
    ax.plot(plies, evals, linewidth=2, color="#2b6cb0")
    ax.fill_between(plies, 0, evals, where=[e >= 0 for e in evals], alpha=0.25, color="#2b6cb0", interpolate=True)
    ax.fill_between(plies, 0, evals, where=[e < 0 for e in evals], alpha=0.25, color="#b04a4a", interpolate=True)
    ax.axhline(y=0, color="#888", linewidth=0.6)

    # Mark blunders (red X) and mistakes (red dot).
    for i, move in enumerate(game.moves, start=1):
        if move.classification == "blunder":
            ax.plot(i, evals[i], "x", color="#c0392b", markersize=12, markeredgewidth=2)
        elif move.classification == "mistake":
            ax.plot(i, evals[i], "o", color="#c0392b", markersize=6)

    ax.set_xlabel("Ply (half-move)")
    ax.set_ylabel("Eval (pawns, White +)")
    ax.set_ylim(-10.5, 10.5)
    ax.set_xlim(0, max(plies) if plies else 1)
    white = game.headers.get("White", "White")
    black = game.headers.get("Black", "Black")
    ax.set_title(f"{white}  vs.  {black}  —  engine evaluation")
    ax.grid(True, alpha=0.3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path
