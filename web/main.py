"""Greco Web — FastAPI application entry point (Greco Online, Phase 1).

Replaces the previous Flask `webapp.py`. Same behaviour from a user's point of
view — open http://127.0.0.1:5000, upload or paste a PGN, get the report — but
on FastAPI, so Greco now gets Pydantic request validation, async endpoints, and
auto-generated interactive API docs at /docs. It binds to 127.0.0.1 only, so the
API key stays server-side; the desktop GUI, CLI and Greco.exe are unaffected.

Run:   run_greco_web.bat        (or:  venv\\Scripts\\python -m web.main)
Open:  http://127.0.0.1:5000    (API docs: http://127.0.0.1:5000/docs)
Stop:  Ctrl+C
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from version import __version__
from web.config import resolve_settings
from web.routers import analysis
from web.templates import render_form


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply settings/env once at startup (mirrors the old Flask resolve at import).
    resolve_settings()
    yield


app = FastAPI(
    title="Greco Web",
    version=__version__,
    description="Engine-backed, AI-narrated chess reports over the shared Greco pipeline.",
    lifespan=lifespan,
)
app.include_router(analysis.router)


@app.get("/health")
def health() -> dict:
    """Liveness + readiness probe (also handy for the future status page)."""
    s = resolve_settings()
    return {
        "status": "ok",
        "version": __version__,
        "engine_ok": s.engine_ok,
        "key_ok": s.key_ok,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """The upload form."""
    return render_form(resolve_settings())


if __name__ == "__main__":
    import uvicorn

    s = resolve_settings()
    print(f"Greco Web {__version__} — open http://127.0.0.1:5000 in your browser.")
    print("  Interactive API docs at http://127.0.0.1:5000/docs")
    if not s.ready:
        print("  Heads up: Stockfish path or API key not set — open the desktop app's settings once.")
    print("  Press Ctrl+C to stop.")
    uvicorn.run(app, host="127.0.0.1", port=5000)
