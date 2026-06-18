"""ngrok tunnel management for Greco Web.

Starts an optional public HTTPS tunnel at server boot when an auth token is
present in config.  The tunnel URL is stored in module-level state so any
route can return it without restarting the tunnel.

Usage:
  - Call start_tunnel(auth_token) once from the FastAPI lifespan.
  - Call get_tunnel_url() from routes to read the current URL (None if not running).
"""
from __future__ import annotations

import logging
from typing import Optional

_log = logging.getLogger("greco.ngrok")
_tunnel_url: Optional[str] = None


def start_tunnel(auth_token: str, port: int = 5000) -> Optional[str]:
    """Open an ngrok tunnel to *port* and cache the public URL.

    Returns the public URL on success, None if the token is empty or the
    tunnel fails (logged as a warning — not fatal, sharing just won't work).
    """
    global _tunnel_url
    if not auth_token:
        return None
    try:
        from pyngrok import conf, ngrok
        conf.get_default().auth_token = auth_token
        tunnel = ngrok.connect(port, "http")
        _tunnel_url = tunnel.public_url
        # ngrok gives http:// by default; upgrade to https:// (always available)
        if _tunnel_url and _tunnel_url.startswith("http://"):
            _tunnel_url = "https://" + _tunnel_url[len("http://"):]
        _log.info("ngrok tunnel active: %s", _tunnel_url)
        return _tunnel_url
    except Exception as exc:
        _log.warning("ngrok tunnel failed to start: %s", exc)
        return None


def get_tunnel_url() -> Optional[str]:
    """Return the current ngrok public URL, or None if no tunnel is running."""
    return _tunnel_url
