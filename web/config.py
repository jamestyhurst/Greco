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

    @property
    def ready(self) -> bool:
        return self.engine_ok and self.key_ok


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
    return Settings(
        engine=engine,
        model=model if model in MODELS else "claude-sonnet-4-6",
        reports_dir=reports_dir,
        engine_ok=bool(engine) and os.path.isfile(engine),
        key_ok=bool(api_key),
    )
