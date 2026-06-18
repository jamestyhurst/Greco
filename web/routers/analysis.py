"""Analysis routes: submit a game, poll job status, view a report.

Phase 2 behaviour: POST /analyze accepts the form, validates it, and returns a
waiting page immediately. The pipeline runs in a FastAPI BackgroundTask; the
browser polls GET /job/{id} every two seconds until the job reaches 'done' or
'failed', then follows the /result/{id} redirect to the finished report.

The route layer is deliberately thin — validation, job bookkeeping, and page
rendering only. All chess work lives in web.pipeline.
"""
from __future__ import annotations

import io
import logging
import socket
from typing import Optional

import chess.pgn

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from outputs import export_shareable_html
from web.auth import get_current_user, require_login
from web.config import MODELS, SPEED_LABELS, USE_CASES, resolve_settings
from web.db import User, create_report_ownership, get_user_by_id
from web.email_utils import send_report_ready
from web.jobs import JobStatus, _registry
from web import ngrok_tunnel, publish as pub
from web.pipeline import report_html_path, run_analysis, run_essay
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


def _run_background(job_id: str, owner_id: Optional[int] = None, **kwargs) -> None:
    """Execute the analysis pipeline and update the job status when done."""
    _registry.update(job_id, status=JobStatus.RUNNING)
    _registry.append_log(job_id, "Starting Stockfish analysis...")
    try:
        result = run_analysis(
            **kwargs,
            progress_cb=lambda msg: _registry.append_log(job_id, msg),
            move_cb=lambda done, total: _registry.update(
                job_id, current_move=done, total_moves=total
            ),
        )
        _registry.append_log(job_id, "Saving report...")
        if owner_id is not None:
            create_report_ownership(result.rid, owner_id, base=result.base)
        _registry.update(job_id, status=JobStatus.DONE, report_id=result.rid)
        _registry.append_log(job_id, "Done!")
        if owner_id is not None:
            _send_completion_email(owner_id, result.rid, result.base)
    except Exception as exc:
        _log.exception("Background job %s failed", job_id)
        _registry.update(job_id, status=JobStatus.FAILED, error=_friendly_error(exc))
        _registry.append_log(job_id, f"Failed: {exc}")


def _run_essay_background(
    job_id: str,
    owner_id: Optional[int] = None,
    **kwargs,
) -> None:
    """Execute the Essay Mode pipeline and update the job status when done."""
    _registry.update(job_id, status=JobStatus.RUNNING)
    _registry.append_log(job_id, "Searching the classical corpus…")
    try:
        result = run_essay(
            **kwargs,
            progress_cb=lambda msg: _registry.append_log(job_id, msg),
        )
        _registry.append_log(job_id, "Saving essay…")
        if owner_id is not None:
            create_report_ownership(result.rid, owner_id, base=result.base)
        _registry.update(job_id, status=JobStatus.DONE, report_id=result.rid)
        _registry.append_log(job_id, "Done!")
    except Exception as exc:
        _log.exception("Essay job %s failed", job_id)
        _registry.update(job_id, status=JobStatus.FAILED, error=_friendly_error(exc))
        _registry.append_log(job_id, f"Failed: {exc}")


def _send_completion_email(owner_id: int, report_id: int, base: Optional[str]) -> None:
    """Send a report-ready email if SMTP is configured. Never raises."""
    try:
        s = resolve_settings()
        if not s.smtp_ready:
            return
        user = get_user_by_id(owner_id)
        if user and user.email:
            send_report_ready(s, user.email, user.username, report_id, base)
    except Exception:
        _log.warning("Could not send report-ready email for report %d", report_id, exc_info=True)


def _validate_pgn(text: str) -> Optional[str]:
    """Return a user-facing error string if the PGN is invalid, else None."""
    try:
        game = chess.pgn.read_game(io.StringIO(text))
    except Exception as exc:
        return f"PGN parse error: {exc}"
    if game is None:
        return (
            "The text you entered could not be parsed as a chess game. "
            "Make sure it is valid PGN format."
        )
    moves = list(game.mainline_moves())
    if not moves:
        return (
            "The PGN was read successfully but contains no moves. "
            "Greco needs at least one move to generate a report."
        )
    return None


def _pgn_hint(text: str) -> str:
    """Return a diagnostic hint to help the user fix their PGN input."""
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped.startswith("http"):
        return (
            "It looks like you pasted a URL. Put URLs in the 'Lichess game URL' field above "
            "the form, or use the 'Paste PGN text' area for the actual move text."
        )
    if not any(c.isdigit() for c in stripped[:60]):
        return (
            "Valid PGN starts with header tags like [Event \"...\"] or directly with "
            "numbered moves like '1. e4 e5 2. Nf3 Nc6'. "
            "If you copied from a website, try copying the raw PGN instead."
        )
    return (
        "Try copying the PGN from Lichess (Game → Share & Export → Copy PGN) "
        "or from your chess software's export option."
    )


def _friendly_error(exc: Exception) -> str:
    """Convert a pipeline exception into a user-facing message."""
    msg = str(exc)
    t = type(exc).__name__
    if "Could not parse PGN" in msg or "PGN" in msg:
        return (
            "Greco could not read the chess game. "
            "Check that the PGN is valid and contains at least one move."
        )
    if "No such file" in msg or "FileNotFoundError" in t:
        return "The PGN file could not be found. Please try uploading it again."
    if "engine" in msg.lower() or "stockfish" in msg.lower() or "Engine" in t:
        return (
            "Stockfish (the chess engine) encountered a problem. "
            "Check that your Stockfish path in settings is correct and the file exists."
        )
    if "401" in msg or "403" in msg or "invalid_api_key" in msg or "AuthenticationError" in t:
        return (
            "The AI narration step failed: invalid API key. "
            "Open the Greco desktop app, go to Settings, and paste a valid Anthropic API key."
        )
    if "insufficient" in msg.lower() or "credit" in msg.lower() or "quota" in msg.lower():
        return (
            "Your Anthropic API account has insufficient credits. "
            "Add credits at console.anthropic.com, then try again."
        )
    if "timeout" in msg.lower() or "TimeoutError" in t:
        return (
            "The analysis timed out. Try a faster engine speed (Normal instead of Deep) "
            "or a shorter game."
        )
    if "connection" in msg.lower() or "ConnectionError" in t or "NetworkError" in t:
        return (
            "A network connection error occurred while contacting the Anthropic API. "
            "Check your internet connection and try again."
        )
    return f"Analysis failed: {msg}"


@router.post("/analyze", response_class=HTMLResponse)
async def analyze(
    background_tasks: BackgroundTasks,
    current_user: Optional[User] = Depends(get_current_user),
    pgn_file: Optional[UploadFile] = File(None),
    pgn_text: str = Form(""),
    lichess_url: str = Form(""),
    use_case: str = Form("companion"),
    side: str = Form("neither"),
    speed: str = Form("normal"),
    model: str = Form(""),
    note: str = Form(""),
    audience_level: str = Form(""),
    recipient: str = Form(""),
    white_context: str = Form(""),
    black_context: str = Form(""),
    essay_question: str = Form(""),
) -> HTMLResponse:
    """Accept a PGN or essay question, register a background job, and return the waiting page."""
    s = resolve_settings()
    if not s.key_ok:
        return HTMLResponse(
            render_error(
                "API key not set. Open the desktop app's settings once, then reload."
            ),
            status_code=400,
        )

    # Validate / normalise options (untrusted form input).
    use_case = use_case if use_case in USE_CASES else "companion"
    model = model if model in MODELS else s.model

    # --- Essay Mode branch (no Stockfish; PGN optional) ---
    if use_case == "essay":
        question = (essay_question or "").strip()
        if not question:
            return HTMLResponse(
                render_error("Please enter a chess question for Essay Mode."),
                status_code=400,
            )
        if len(question) < 10:
            return HTMLResponse(
                render_error("Your question is too short. Please be more specific."),
                status_code=400,
            )
        pgn_for_essay: Optional[str] = None
        if pgn_text.strip():
            pgn_for_essay = pgn_text.strip()

        job = _registry.create()
        background_tasks.add_task(
            _run_essay_background,
            job.id,
            owner_id=current_user.id if current_user else None,
            question=question,
            pgn_text=pgn_for_essay,
            model=model,
            audience_level=(audience_level or "").strip() or None,
            note=(note or "").strip() or None,
        )
        return HTMLResponse(render_waiting(job.id, essay_mode=True))

    # --- Standard analysis branch (PGN required) ---
    if not s.engine_ok:
        return HTMLResponse(
            render_error(
                "Stockfish path not set. Open the desktop app's settings once, then reload."
            ),
            status_code=400,
        )

    # Resolve the PGN: Lichess URL > file upload > pasted text.
    text = ""
    if (lichess_url or "").strip():
        try:
            from importers import load_from_lichess
            text, _src = load_from_lichess(lichess_url.strip())
        except Exception as exc:
            return HTMLResponse(
                render_error(f"Could not fetch Lichess game: {exc}"),
                status_code=400,
            )
    elif pgn_file is not None and (pgn_file.filename or "").strip():
        raw = await pgn_file.read()
        text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        text = (pgn_text or "").strip()
    if not text:
        return HTMLResponse(
            render_error("Please upload a PGN file, paste PGN text, or enter a Lichess URL."),
            status_code=400,
        )

    # Pre-validate PGN so errors surface immediately with clear messages
    # rather than silently failing in the background task.
    pgn_err = _validate_pgn(text)
    if pgn_err:
        return HTMLResponse(render_error(pgn_err, detail=_pgn_hint(text)), status_code=400)

    user_is = side.lower() if side.lower() in ("white", "black") else "neither"
    time_limit = SPEED_LABELS.get(speed, 0.8)
    note_val = (note or "").strip() or None

    job = _registry.create()
    background_tasks.add_task(
        _run_background,
        job.id,
        owner_id=current_user.id if current_user else None,
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
        "logs": job.logs,
        "current_move": job.current_move,
        "total_moves": job.total_moves,
    }


@router.get("/result/{job_id}", response_class=HTMLResponse)
async def result_page(request: Request, job_id: str) -> HTMLResponse:
    """Show the finished-report page for a completed job (replaces the old
    blocking result page). Redirects to the report if done; shows an error
    if failed; shows the waiting page if still running."""
    current_user = await get_current_user(request)
    job = _registry.get(job_id)
    if job is None:
        return HTMLResponse(render_error("Job not found.", user=current_user), status_code=404)
    if job.status == JobStatus.DONE and job.report_id is not None:
        p = report_html_path(job.report_id)
        if p is None:
            return HTMLResponse(render_error("Report file not found.", user=current_user), status_code=404)
        return HTMLResponse(render_result("Report", job.report_id, str(p.parent), user=current_user))
    if job.status == JobStatus.FAILED:
        return HTMLResponse(render_error(job.error or "Analysis failed.", user=current_user), status_code=500)
    return HTMLResponse(render_waiting(job_id, user=current_user))


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
