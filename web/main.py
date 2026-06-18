"""Greco Web — FastAPI application entry point (Greco Online, Phase 1–3).

Phase 3 adds: user accounts (register/login/logout), session-based auth, and
per-user report scoping. The SessionMiddleware signs the session cookie with the
secret key from config.json (or an ephemeral random key if not set). Init the
SQLite DB on startup (idempotent).

Run:   run_greco_web.bat        (or:  venv\\Scripts\\python -m web.main)
Open:  http://127.0.0.1:5000    (API docs: http://127.0.0.1:5000/docs)
Stop:  Ctrl+C
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from version import __version__
from web.auth import NotAuthenticated, get_current_user
from web.config import resolve_settings
from web.db import init_db
from web.routers import analysis
from web.routers import auth as auth_router
from web import ngrok_tunnel
from web.templates import render_form


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = resolve_settings()
    # Ensure DB tables exist before serving any request.
    init_db()
    if s.ngrok_ready:
        tunnel_url = ngrok_tunnel.start_tunnel(s.ngrok_auth_token)
        if tunnel_url:
            print(f"  ngrok tunnel active — share reports anywhere: {tunnel_url}/report/<id>")
    yield


app = FastAPI(
    title="Greco Web",
    version=__version__,
    description="Engine-backed, AI-narrated chess reports over the shared Greco pipeline.",
    lifespan=lifespan,
)

# Session middleware must be added before the routers so the session is available
# in all request handlers. The secret key signs the cookie (tamper-evident).
_s = resolve_settings()
app.add_middleware(SessionMiddleware, secret_key=_s.secret_key, https_only=False)

app.include_router(analysis.router)
app.include_router(auth_router.router)


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    """Redirect unauthenticated users to the login page."""
    return RedirectResponse("/auth/login", status_code=303)


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Liveness + readiness probe."""
    s = resolve_settings()
    return {
        "status": "ok",
        "version": __version__,
        "engine_ok": s.engine_ok,
        "key_ok": s.key_ok,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """The upload form (requires login)."""
    user = await get_current_user(request)
    if user is None:
        return RedirectResponse("/auth/login", status_code=303)
    return HTMLResponse(render_form(resolve_settings(), user=user))


if __name__ == "__main__":
    import uvicorn

    s = resolve_settings()
    from web.routers.analysis import _lan_base_url
    _base = _lan_base_url()
    print(f"Greco Web {__version__} — open http://127.0.0.1:5000 in your browser.")
    print(f"  Share reports with devices on your WiFi via {_base}/report/<id>")
    print("  Interactive API docs at http://127.0.0.1:5000/docs")
    if not s.ready:
        print("  Heads up: Stockfish path or API key not set — open the desktop app's settings once.")
    print("  Press Ctrl+C to stop.")
    uvicorn.run(app, host="0.0.0.0", port=5000)
