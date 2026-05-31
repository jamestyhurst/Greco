"""
Opening identification from the lichess `chess-openings` database (CC0).

The TSV files in openings/data/ map exact SAN move sequences to an ECO code and
an official opening/variation name. Because the match is on the exact move order,
the opening is named by what the player ACTUALLY played (e.g. 1...Nf6 = Alekhine's
Defence), never by a structure it later transposes into.
"""

from __future__ import annotations

import glob
import os
import re
from typing import Dict, List, Optional, Tuple

_MOVE_NUM = re.compile(r"^\d+\.+$")
_OPENINGS: Optional[List[Tuple[int, str, str, Tuple[str, ...]]]] = None


def _sans_from_pgn(pgn: str) -> Tuple[str, ...]:
    return tuple(tok for tok in pgn.split() if not _MOVE_NUM.match(tok))


def _load() -> List[Tuple[int, str, str, Tuple[str, ...]]]:
    """Return list of (num_plies, eco, name, san_tuple), sorted longest-first."""
    global _OPENINGS
    if _OPENINGS is not None:
        return _OPENINGS
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openings", "data")
    rows: List[Tuple[int, str, str, Tuple[str, ...]]] = []
    for path in sorted(glob.glob(os.path.join(base, "*.tsv"))):
        try:
            with open(path, encoding="utf-8") as fh:
                header = fh.readline()  # eco\tname\tpgn
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        continue
                    eco, name, pgn = parts[0], parts[1], parts[2]
                    sans = _sans_from_pgn(pgn)
                    if sans:
                        rows.append((len(sans), eco, name, sans))
        except OSError:
            continue
    rows.sort(key=lambda r: r[0], reverse=True)  # longest lines first
    _OPENINGS = rows
    return rows


def identify_opening(game_sans: List[str]) -> Optional[Dict[str, object]]:
    """
    Find the deepest known opening line that is an exact prefix of the game.
    Returns {eco, name, book_plies} or None. `book_plies` = how many half-moves
    the players stayed in this known line (treat those as book/theory).
    """
    if not game_sans:
        return None
    openings = _load()
    game_tuple = tuple(game_sans)
    glen = len(game_tuple)
    for n, eco, name, sans in openings:  # already longest-first
        if n <= glen and game_tuple[:n] == sans:
            return {"eco": eco, "name": name, "book_plies": n}
    return None
