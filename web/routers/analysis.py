"""Analysis routes: submit a game, view the report, download a shareable copy.

The route layer is deliberately thin — it validates the HTTP request, offloads
the slow pipeline to a threadpool (so the async event loop stays free), and
renders a page. All the chess work lives in `web.pipeline`.
"""
from __future__ import annotations

import logging
import os
import traceback
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse

from outputs import export_shareable_html
from web.config import MODELS, SPEED_LABELS, USE_CASES, resolve_settings
from web.pipeline import report_html_path, run_analysis
from web.templates import render_error, render_result

router = APIRouter()


@router.post("/analyze", response_class=HTMLResponse)
async def analyze(
    pgn_file: Optional[UploadFile] = File(None),
    pgn_text: str = Form(""),
    use_case: str = Form("companion"),
    side: str = Form("neither"),
    speed: str = Form("normal"),
    model: str = Form(""),
    note: str = Form(""),
) -> HTMLResponse:
    """Run the pipeline on an uploaded or pasted PGN and show the report."""
    s = resolve_settings()
    if not s.ready:
        return HTMLResponse(
            render_error(
                "Stockfish path or API key not set. Open the desktop app's "
                "settings once, then reload."
            ),
            status_code=400,
        )

    # Resolve the PGN from the file upload, else the pasted text.
    text = ""
    if pgn_file is not None and (pgn_file.filename or "").strip():
        raw = await pgn_file.read()
        text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        text = (pgn_text or "").strip()
    if not text:
        return HTMLResponse(
            render_error("Please upload a PGN file or paste PGN text."),
            status_code=400,
        )

    # Validate / normalise options (untrusted input from the form).
    use_case = use_case if use_case in USE_CASES else "companion"
    user_is = side.lower() if side.lower() in ("white", "black") else "neither"
    time_limit = SPEED_LABELS.get(speed, 0.8)
    model = model if model in MODELS else s.model
    note_val = (note or "").strip() or None

    try:
        # Offload the blocking Stockfish + Claude work to a worker thread so the
        # server can still answer other requests while it runs.
        result = await run_in_threadpool(
            run_analysis,
            pgn_text=text, engine=s.engine, time_limit=time_limit,
            user_is=user_is, use_case=use_case, model=model, note=note_val,
        )
    except Exception:
        # Never leak a server traceback to the browser — it can carry internal file
        # paths, request URLs, or config detail. Log the full trace server-side under
        # a short id and show the user only that id. The detail is rendered in the
        # page ONLY when GRECO_DEBUG is set (off by default). Matters once Greco Web
        # is hosted (Phase 7); harmless to fix now.
        error_id = os.urandom(4).hex()
        logging.getLogger("greco.web").exception("Analysis failed [%s]", error_id)
        detail = traceback.format_exc() if os.environ.get("GRECO_DEBUG") else ""
        return HTMLResponse(
            render_error(
                f"Analysis failed. If this keeps happening, note error id {error_id}.",
                detail,
            ),
            status_code=500,
        )

    return HTMLResponse(render_result(result.base, result.rid, result.out_dir))


@router.get("/report/{rid}", response_class=HTMLResponse)
def report(rid: int) -> FileResponse:
    """Serve a finished report's self-contained HTML (validated path only)."""
    p = report_html_path(rid)
    if p is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(str(p), media_type="text/html")


@router.get("/report/{rid}/shareable")
def report_shareable(rid: int) -> FileResponse:
    """Generate (if needed) and download the single-file '… (shareable).html'
    for emailing — the same export the desktop button produces."""
    p = report_html_path(rid)
    if p is None:
        raise HTTPException(status_code=404, detail="Report not found")
    out = export_shareable_html(p)
    return FileResponse(str(out), media_type="text/html", filename=out.name)
