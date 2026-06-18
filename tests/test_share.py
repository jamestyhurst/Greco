"""
Tests for the LAN share-link feature.

The share link lets James paste a URL into iMessage/WhatsApp and have
someone on the same WiFi open the report directly in their browser —
no file attachment, no QuickLook sandbox, JS runs normally.

Requires Greco Web to be running; does NOT work over the internet
(that's Phase 7 hosting).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from web.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Cycle 1 — /lan-url returns a url field
# ---------------------------------------------------------------------------

def test_lan_url_returns_json_with_url_field():
    """/lan-url must return JSON with a 'url' key."""
    r = client.get("/lan-url")
    assert r.status_code == 200
    assert "url" in r.json()


# ---------------------------------------------------------------------------
# Cycle 2 — url is http://…:5000, not loopback-only
# ---------------------------------------------------------------------------

def test_lan_url_is_http_on_port_5000():
    """The returned URL must be http:// and include port 5000."""
    r = client.get("/lan-url")
    url = r.json()["url"]
    assert url.startswith("http://"), f"Expected http://, got: {url}"
    assert ":5000" in url, f"Expected port 5000 in URL, got: {url}"


# ---------------------------------------------------------------------------
# Cycle 3 — result page contains a Copy link button
# ---------------------------------------------------------------------------

def test_result_page_contains_copy_link_button():
    """render_result() must include a copy-link element for the share feature."""
    from web.templates import render_result
    html = render_result("Alice vs Bob", rid=1, saved_dir="/tmp")
    assert "copy-link" in html.lower() or "copylink" in html.lower() or \
           "copy link" in html.lower() or "id=\"gv-copy\"" in html or \
           "gv-copy" in html, \
        "Result page must contain a copy-link button"


# ---------------------------------------------------------------------------
# Cycle 4 — copy button carries data-rid so JS can build the full report URL
# ---------------------------------------------------------------------------

def test_result_page_copy_button_has_report_rid():
    """The copy-link button must expose the report id (via data-rid or href)
    so the JS snippet can assemble http://<lan-ip>:5000/report/<rid>."""
    from web.templates import render_result
    html = render_result("Alice vs Bob", rid=42, saved_dir="/tmp")
    assert 'data-rid="42"' in html or "data-rid='42'" in html or \
           '"/report/42"' in html or "'/report/42'" in html, \
        "Copy-link button must reference report id 42"
