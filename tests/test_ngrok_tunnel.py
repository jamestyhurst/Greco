"""
Tests for the ngrok "Share now" tunnel feature.

GET /ngrok-url returns the current public tunnel URL (or null when ngrok
isn't configured / no tunnel is running). The tunnel is started at server
boot if an auth token is present in config.json; otherwise the route
returns null and the UI shows a setup hint instead of a URL.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from web.main import app

client = TestClient(app)


def test_ngrok_url_route_exists():
    """/ngrok-url must return 200 even when no tunnel is running."""
    r = client.get("/ngrok-url")
    assert r.status_code == 200


def test_ngrok_url_returns_null_when_no_tunnel():
    """/ngrok-url returns {"url": null} when ngrok hasn't been started
    (e.g. no auth token in config)."""
    r = client.get("/ngrok-url")
    assert r.json()["url"] is None


def test_ngrok_url_returns_tunnel_url_when_active(monkeypatch):
    """/ngrok-url returns the live public URL when a tunnel is running."""
    import web.ngrok_tunnel as nt
    monkeypatch.setattr(nt, "get_tunnel_url", lambda: "https://abc123.ngrok-free.app")
    r = client.get("/ngrok-url")
    assert r.json()["url"] == "https://abc123.ngrok-free.app"


def test_result_page_has_ngrok_copy_button():
    """The result page must include a 'copy ngrok link' element."""
    from web.templates import render_result
    html = render_result("Alice vs Bob", rid=1, saved_dir="/tmp")
    assert 'id="gv-ngrok"' in html, "Result page must have #gv-ngrok copy button"
