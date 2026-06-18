"""Analysis routes: submit a game, poll job status, view a report.

Phase 2 behaviour: POST /analyze accepts the form, validates it, and returns a
waiting page immediately. The pipeline runs in a FastAPI BackgroundTask; the
browser polls GET /job/{id} every two seconds until the job reaches 'done' or
'failed', then follows the /result/{id} redirect to the finished report.

The route layer is deliberately thin — validation, job bookkeeping, and page
rendering only. All chess work lives in web.pipeline.
"""
from __future__ import annotations

import logging
import socket
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from outputs import export_shareable_html
from web.config import MODELS, SPEED_LABELS, USE_CASES, resolve_settings
from web.jobs import JobStatus, _registry
from web import ngrok_tunnel, publish as pub
from web.pipeline import report_html_path, run_analysis
from web.templates import render_error, render_result, render_waiting

router = APIRouter()


def _lan_base_url(port: int = 5000) -> str:
    """Return the machine's LAN base URL (e.g. http://192.168.1.42:5000).

    Uses a connect-without-send trick to find which local interface routes
    to the outside world, which is the same IP other devices on the LAN use
    to reach this machine. Falls back to 127.0.0.1 if detection fails."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return f"http://{ip}:{port}"


@router.get("/lan-url")
def lan_url() -> dict:
    """Return the server's LAN base URL so the result page can build a
    shareable link that works from any device on the same WiFi network."""
    return {"url": _lan_base_url()}

_log = logging.getLogger("greco.web")


def _run_background(job_id: str, **kwargs) -> None:
    """Execute the analysis pipeline and update the job status when done."""
    _registry.update(job_id, status=JobStatus.RUNNING)
    try:
        result = run_analysis(**kwargs)
        _registry.update(job_id, status=JobStatus.DONE, report_id=result.rid)
    except Exception as exc:
        _log.exception("Background job %s failed", job_id)
        _registry.update(job_id, status=JobStatus.FAILED, error=str(exc))


@router.post("/analyze", response_class=HTMLResponse)
async def analyze(
    background_tasks: BackgroundTasks,
    pgn_file: Optional[UploadFile] = File(None),
    pgn_text: str = Form(""),
    use_case: str = Form("companion"),
    side: str = Form("neither"),
    speed: str = Form("normal"),
    model: str = Form(""),
    note: str = Form(""),
    audience_level: str = Form(""),
    recipient: str = Form(""),
    white_context: str = Form(""),
    black_context: str = Form(""),
) -> HTMLResponse:
    """Accept a PGN, register a background job, and return the waiting page."""
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

    # Validate / normalise options (untrusted form input).
    use_case = use_case if use_case in USE_CASES else "companion"
    user_is = side.lower() if side.lower() in ("white", "black") else "neither"
    time_limit = SPEED_LABELS.get(speed, 0.8)
    model = model if model in MODELS else s.model
    note_val = (note or "").strip() or None

    job = _registry.create()
    background_tasks.add_task(
        _run_background,
        job.id,
        pgn_text=text, engine=s.engine, time_limit=time_limit,
        user_is=user_is, use_case=use_case, model=model, note=note_val,
        audience_level=(audience_level or "").strip() or None,
        recipient=(recipient or "").strip() or None,
        white_context=(white_context or "").strip() or None,
        black_context=(black_context or "").strip() or None,
    )
    return HTMLResponse(render_waiting(job.id))


@router.get("/job/{job_id}")
def job_status(job_id: str) -> dict:
    """Return the current status of a background analysis job as JSON."""
    job = _registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "report_id": job.report_id,
        "error": job.error,
    }


@router.get("/result/{job_id}", response_class=HTMLResponse)
def result_page(job_id: str) -> HTMLResponse:
    """Show the finished-report page for a completed job (replaces the old
    blocking result page). Redirects to the report if done; shows an error
    if failed; shows the waiting page if still running."""
    job = _registry.get(job_id)
    if job is None:
        return HTMLResponse(render_error("Job not found."), status_code=404)
    if job.status == JobStatus.DONE and job.report_id is not None:
        p = report_html_path(job.report_id)
        if p is None:
            return HTMLResponse(render_error("Report file not found."), status_code=404)
        return HTMLResponse(render_result("Report", job.report_id, str(p.parent)))
    if job.status == JobStatus.FAILED:
        return HTMLResponse(render_error(job.error or "Analysis failed."), status_code=500)
    return HTMLResponse(render_waiting(job_id))


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


@router.get("/ngrok-url")
def ngrok_url() -> dict:
    """Return the active ngrok public URL, or null if no tunnel is running.
    The result page JS calls this to build a share link that works anywhere."""
    return {"url": ngrok_tunnel.get_tunnel_url()}


@router.post("/report/{rid}/publish")
def report_publish(rid: int) -> dict:
    """Upload the report to Cloudflare R2 and return the permanent public URL.
    Returns 503 when R2 credentials are not yet configured in config.json."""
    s = resolve_settings()
    if not s.r2_ready:
        raise HTTPException(
            status_code=503,
            detail="R2 not configured — add r2_* keys to config.json to enable permanent publishing.",
        )
    p = report_html_path(rid)
    if p is None:
        raise HTTPException(status_code=404, detail="Report not found")
    # Use the fully-inlined shareable HTML so the published page has no
    # dependencies on the local server.
    shareable = export_shareable_html(p)
    url = pub.publish_to_r2(shareable, s)
    return {"url": url}
