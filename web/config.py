"""Settings resolution for Greco Web.

Reads the SAME `config.json` the desktop settings panel writes (Stockfish path,
API key, model, reports folder), falls back to environment variables, and applies
the env vars the pipeline expects — so a browser analysis lands in the same
"Greco Reports" folder as the desktop app. This mirrors the old Flask resolver
exactly; the only change is returning a typed Pydantic model instead of a dict
(validation + editor autocomplete, the contract-grade habit FastAPI rewards).
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from pydantic import BaseModel

GRECO_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = GRECO_DIR / "config.json"

# Option lists shared with the form and request validation (mirror gui.py).
MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-fable-5"]
USE_CASES = ["companion", "coaching", "commentary"]
SPEED_LABELS = {"fast": 0.5, "normal": 0.8, "deep": 1.5}


class Settings(BaseModel):
    """Resolved runtime settings + readiness flags for the web layer."""

    engine: str = ""
    model: str = "claude-sonnet-4-6"
    reports_dir: str = ""
    engine_ok: bool = False
    key_ok: bool = False

    # ngrok — "Share now" ephemeral public tunnel
    ngrok_auth_token: str = ""

    # Session signing secret (Phase 3 — accounts + roles)
    # Set "web_secret_key" in config.json for persistent sessions across restarts.
    # If absent, a random key is generated at startup (sessions die on restart).
    secret_key: str = ""

    # Cloudflare R2 — "Publish permanently" cloud storage
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_public_url: str = ""   # e.g. https://pub-xxx.r2.dev or custom domain

    # SMTP — "report ready" email notification (Phase 6)
    # If smtp_host is empty, email sending is silently skipped.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    app_base_url: str = "http://localhost:5000"

    @property
    def ready(self) -> bool:
        return self.engine_ok and self.key_ok

    @property
    def ngrok_ready(self) -> bool:
        return bool(self.ngrok_auth_token)

    @property
    def r2_ready(self) -> bool:
        return all([self.r2_account_id, self.r2_access_key_id,
                    self.r2_secret_access_key, self.r2_bucket_name,
                    self.r2_public_url])

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)


_EPHEMERAL_SECRET: str = ""   # module-level cache so it's stable within a process


def _ephemeral_secret() -> str:
    """Return a process-stable random key when no persistent secret is configured.
    Logs a one-time warning because logged-in sessions won't survive a server restart.
    Add 'web_secret_key' to config.json (or GRECO_SECRET_KEY env var) to fix this."""
    global _EPHEMERAL_SECRET
    if not _EPHEMERAL_SECRET:
        _EPHEMERAL_SECRET = secrets.token_hex(32)
        import sys as _sys
        print(
            "  [auth] no web_secret_key in config.json — using a random session key.\n"
            "  Sessions will not survive a server restart. Add 'web_secret_key' to config.json to fix.",
            file=_sys.stderr,
        )
    return _EPHEMERAL_SECRET


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_settings() -> Settings:
    """Read config.json (+ env fallbacks), apply env vars for the pipeline, and
    report readiness. Calling it is cheap and idempotent; routes call it per
    request so a settings change in the desktop app is picked up without a
    server restart."""
    cfg = _load_config()
    engine = cfg.get("stockfish_path") or os.environ.get("STOCKFISH_PATH") or ""
    api_key = cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or ""
    model = cfg.get("model") or "claude-sonnet-4-6"
    reports_dir = cfg.get("reports_dir") or os.environ.get("GRECO_REPORTS_DIR") or ""
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    if reports_dir:
        # so outputs.default_reports_dir() writes where the desktop app does
        os.environ["GRECO_REPORTS_DIR"] = reports_dir
    secret_key = (cfg.get("web_secret_key") or os.environ.get("GRECO_SECRET_KEY") or "")
    if not secret_key:
        secret_key = _ephemeral_secret()

    return Settings(
        engine=engine,
        model=model if model in MODELS else "claude-sonnet-4-6",
        reports_dir=reports_dir,
        engine_ok=bool(engine) and os.path.isfile(engine),
        key_ok=bool(api_key),
        secret_key=secret_key,
        ngrok_auth_token=cfg.get("ngrok_auth_token") or os.environ.get("NGROK_AUTH_TOKEN") or "",
        r2_account_id=cfg.get("r2_account_id") or os.environ.get("R2_ACCOUNT_ID") or "",
        r2_access_key_id=cfg.get("r2_access_key_id") or os.environ.get("R2_ACCESS_KEY_ID") or "",
        r2_secret_access_key=cfg.get("r2_secret_access_key") or os.environ.get("R2_SECRET_ACCESS_KEY") or "",
        r2_bucket_name=cfg.get("r2_bucket_name") or os.environ.get("R2_BUCKET_NAME") or "",
        r2_public_url=cfg.get("r2_public_url") or os.environ.get("R2_PUBLIC_URL") or "",
        smtp_host=cfg.get("smtp_host") or os.environ.get("GRECO_SMTP_HOST") or "",
        smtp_port=int(cfg.get("smtp_port") or os.environ.get("GRECO_SMTP_PORT") or 587),
        smtp_user=cfg.get("smtp_user") or os.environ.get("GRECO_SMTP_USER") or "",
        smtp_password=cfg.get("smtp_password") or os.environ.get("GRECO_SMTP_PASSWORD") or "",
        smtp_from=cfg.get("smtp_from") or os.environ.get("GRECO_SMTP_FROM") or "",
        app_base_url=cfg.get("app_base_url") or os.environ.get("GRECO_APP_BASE_URL") or "http://localhost:5000",
    )
