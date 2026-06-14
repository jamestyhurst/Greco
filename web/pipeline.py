"""The blocking analysis chokepoint for Greco Web.

One function — `run_analysis` — runs the exact same pipeline as `gui.py` and the
CLI (Stockfish + Claude), writes the report folder, and registers the result.
Keeping it in a single place (not inside a route handler) is the "thin
front-ends over a shared core" rule: the FastAPI route stays about HTTP, this
stays about chess. It is synchronous and slow on purpose — the route offloads it
to a threadpool so the event loop stays responsive (Phase 2 replaces this with a
real job queue + status page).
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from importers import load_pgn
from analyzer import analyze_pgn
from triage import annotate_with_tiers
from narrator import generate_narrative
from outputs import (
    assemble_report,
    markdown_to_html,
    report_basename,
    default_reports_dir,
)

# In-memory registry: report id -> absolute .html path. Integer ids keep report
# URLs pure-ASCII (the reports folder path contains non-ASCII characters). It is
# cleared on restart — fine for a single-user localhost tool; Phase 2 (database)
# is what makes reports durably addressable.
_REPORTS: dict[int, str] = {}
_LOCK = threading.Lock()
_NEXT_ID = [1]


class AnalysisResult(BaseModel):
    rid: int
    base: str
    out_dir: str
    html_path: str


def run_analysis(
    *,
    pgn_text: str,
    engine: str,
    time_limit: float,
    user_is: str,
    use_case: str,
    model: str,
    note: Optional[str],
) -> AnalysisResult:
    """Run the full pipeline on a PGN string and return the registered result.

    Identical to gui.py's worker: load_pgn -> analyze_pgn -> annotate_with_tiers
    -> generate_narrative -> assemble_report -> markdown_to_html. No analysis
    logic lives here.
    """
    flipped = user_is == "black"

    # load_pgn expects a path; write the (already-validated-by-upload) text to a
    # temp .pgn, then always clean it up.
    fd, tmp = tempfile.mkstemp(suffix=".pgn")
    os.close(fd)
    Path(tmp).write_text(pgn_text, encoding="utf-8")
    try:
        text, _src = load_pgn(tmp)
        game = analyze_pgn(text, engine_path=engine, time_limit=time_limit)
        user_context = {
            "white_player": None,
            "black_player": None,
            "user_is": user_is,
            "player_named": False,
        }
        tiers = annotate_with_tiers(game, user_context)
        narrative = generate_narrative(
            game, tiers, user_context, use_case=use_case,
            user_note=note, model=model, live_stream_to=None,
        )
        base = report_basename(game)
        out_dir = default_reports_dir() / base
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{base}.md"
        assemble_report(
            game, tiers, narrative, output_md=md_path,
            boards_at="tier3", render_eval_graph=True, flipped_for_black=flipped,
        )
        html_path = markdown_to_html(md_path, game=game, flipped=flipped)
    finally:
        try:
            Path(tmp).unlink()
        except Exception:
            pass

    with _LOCK:
        rid = _NEXT_ID[0]
        _NEXT_ID[0] += 1
        _REPORTS[rid] = str(Path(html_path).resolve())

    return AnalysisResult(rid=rid, base=base, out_dir=str(out_dir), html_path=str(html_path))


def report_html_path(rid: int) -> Optional[Path]:
    """Return the validated `.html` path for a report id, or None.

    Trust-boundary guard (same instinct as the old Flask handler): only ever
    return a `.html` file that actually lives inside the reports root, so a
    crafted id can never coax the server into serving an arbitrary file.
    """
    path = _REPORTS.get(rid)
    if not path:
        return None
    p = Path(path).resolve()
    root = default_reports_dir().resolve()
    if p.suffix.lower() != ".html" or root not in p.parents or not p.is_file():
        return None
    return p
