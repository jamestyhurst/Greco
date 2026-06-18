"""
Tests for the Cloudflare R2 "Publish permanently" feature.

POST /report/{rid}/publish uploads the finished report HTML to R2 and
returns a permanent public URL. When R2 credentials aren't configured the
route returns 503 with a setup hint — the feature degrades gracefully.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from fastapi.testclient import TestClient
from web.main import app

client = TestClient(app)


def test_publish_returns_503_when_r2_not_configured():
    """POST /report/1/publish returns 503 when R2 credentials are absent."""
    r = client.post("/report/1/publish")
    assert r.status_code == 503
    assert "r2" in r.json()["detail"].lower() or "not configured" in r.json()["detail"].lower()


def test_publish_returns_404_for_missing_report(monkeypatch, tmp_path):
    """POST /report/999/publish returns 404 when the report file doesn't exist,
    even if R2 is configured."""
    from web.config import Settings
    mock_settings = Settings(
        r2_account_id="acct", r2_access_key_id="key",
        r2_secret_access_key="secret", r2_bucket_name="bucket",
        r2_public_url="https://pub.r2.dev",
        engine_ok=False, key_ok=False,
    )
    # Patch at the point of use — the router imports resolve_settings by name.
    import web.routers.analysis as router_mod
    monkeypatch.setattr(router_mod, "resolve_settings", lambda: mock_settings)
    monkeypatch.setattr(router_mod, "report_html_path", lambda rid: None)
    r = client.post("/report/999/publish")
    assert r.status_code == 404


def test_publish_uploads_and_returns_url(monkeypatch, tmp_path):
    """POST /report/1/publish calls publish_to_r2 and returns the public URL."""
    html_path = tmp_path / "report.html"
    html_path.write_text("<html>test</html>", encoding="utf-8")

    from web.config import Settings
    mock_settings = Settings(
        r2_account_id="acct", r2_access_key_id="key",
        r2_secret_access_key="secret", r2_bucket_name="bucket",
        r2_public_url="https://pub.r2.dev",
        engine_ok=False, key_ok=False,
    )
    import web.routers.analysis as router_mod
    monkeypatch.setattr(router_mod, "resolve_settings", lambda: mock_settings)
    monkeypatch.setattr(router_mod, "report_html_path", lambda rid: html_path)
    # publish route calls export_shareable_html first, then pub.publish_to_r2.
    monkeypatch.setattr(router_mod, "export_shareable_html", lambda p: p)
    monkeypatch.setattr(router_mod.pub, "publish_to_r2",
                        lambda path, settings: "https://pub.r2.dev/reports/abc123.html")

    r = client.post("/report/1/publish")
    assert r.status_code == 200
    assert r.json()["url"] == "https://pub.r2.dev/reports/abc123.html"


def test_result_page_has_publish_button():
    """The result page must include a publish-permanently button."""
    from web.templates import render_result
    html = render_result("Alice vs Bob", rid=1, saved_dir="/tmp")
    assert 'id="gv-publish"' in html, "Result page must have #gv-publish button"
