"""FastAPI routes (Greco Online, Phase 1 + Phase 2).

The expensive Stockfish + Claude pipeline is mocked out, so these exercise the
HTTP layer — routing, request validation, the background-task flow, the job
status endpoint, and rendering — without an engine or an API key.

Phase 2 behaviour: POST /analyze now returns a waiting page immediately and
runs the pipeline in a BackgroundTask. The TestClient runs background tasks
synchronously before returning, so tests can poll /job/{id} right after the
POST and find the job already in a terminal state.

Phase 3: all analysis routes now require login. The bypass_auth autouse
fixture injects a fake user so these tests stay focused on pipeline/HTTP
behaviour. Auth-specific coverage lives in test_auth.py.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import web.routers.analysis as analysis
import web.main as web_main
from web.auth import require_login
from web.config import Settings
from web.db import User as DbUser
from web.main import app
from web.pipeline import AnalysisResult

client = TestClient(app)

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

_FAKE_USER = DbUser(id=1, username="testuser", email="test@example.com", role="user")


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    """Bypass auth for all tests in this module.

    - Replaces get_current_user (used in GET /) with a function returning the fake user.
    - Overrides the require_login dependency (used in POST /analyze).
    - No-ops create_report_ownership so tests don't need a real DB with a user row.
    """
    async def _fake_current_user(request):
        return _FAKE_USER

    monkeypatch.setattr(web_main, "get_current_user", _fake_current_user)
    monkeypatch.setattr(analysis, "create_report_ownership", lambda rid, uid: None)
    app.dependency_overrides[require_login] = lambda: _FAKE_USER
    yield
    app.dependency_overrides.pop(require_login, None)


def _ready(monkeypatch):
    """Force settings to look 'ready' so a route gets past the readiness gate
    regardless of this machine's config.json."""
    monkeypatch.setattr(
        analysis, "resolve_settings",
        lambda: Settings(engine="stockfish", model="claude-sonnet-4-6",
                         engine_ok=True, key_ok=True),
    )


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_index_serves_form():
    r = client.get("/")
    assert r.status_code == 200
    assert "Greco Web" in r.text


def test_unknown_report_is_404():
    assert client.get("/report/999999").status_code == 404


def test_analyze_without_pgn_is_400(monkeypatch):
    _ready(monkeypatch)
    r = client.post("/analyze", data={"pgn_text": ""})
    assert r.status_code == 400
    assert "PGN" in r.text


def test_analyze_returns_waiting_page_immediately(monkeypatch, tmp_path):
    """POST /analyze returns the waiting page (not the result) right away."""
    _ready(monkeypatch)
    fake = AnalysisResult(rid=1, base="Alice vs Bob",
                          out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"))
    monkeypatch.setattr(analysis, "run_analysis", lambda **kw: fake)

    r = client.post("/analyze", data={"pgn_text": "1. e4 e5", "use_case": "companion"})
    assert r.status_code == 200
    # Waiting page — not the final result page
    assert "Alice vs Bob" not in r.text
    # A UUID job id is embedded in the page
    assert _UUID_RE.search(r.text), "Expected a job UUID in the waiting page"


def test_analyze_job_reaches_done_with_report_id(monkeypatch, tmp_path):
    """After the background task completes the job status is 'done' with the report id."""
    _ready(monkeypatch)
    fake = AnalysisResult(rid=5, base="X vs Y",
                          out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"))
    monkeypatch.setattr(analysis, "run_analysis", lambda **kw: fake)

    post_resp = client.post("/analyze", data={"pgn_text": "1. e4", "use_case": "coaching"})
    job_id = _UUID_RE.search(post_resp.text).group(0)

    status_resp = client.get(f"/job/{job_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "done"
    assert body["report_id"] == 5


def test_job_status_unknown_is_404():
    r = client.get("/job/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_analyze_job_is_failed_when_pipeline_raises(monkeypatch):
    """If run_analysis raises, the job transitions to 'failed'."""
    _ready(monkeypatch)
    monkeypatch.setattr(analysis, "run_analysis", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))

    post_resp = client.post("/analyze", data={"pgn_text": "1. e4"})
    assert post_resp.status_code == 200          # waiting page always returned
    job_id = _UUID_RE.search(post_resp.text).group(0)

    status_resp = client.get(f"/job/{job_id}")
    body = status_resp.json()
    assert body["status"] == "failed"
    assert "boom" in (body.get("error") or "")


def test_analyze_passes_context_fields_to_pipeline(monkeypatch, tmp_path):
    """audience_level, recipient, white_context, black_context reach run_analysis."""
    _ready(monkeypatch)
    captured = {}

    def fake_run(**kw):
        captured.update(kw)
        return AnalysisResult(
            rid=2, base="X vs Y",
            out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"),
        )

    monkeypatch.setattr(analysis, "run_analysis", fake_run)
    client.post("/analyze", data={
        "pgn_text": "1. e4",
        "audience_level": "Club",
        "recipient": "my friend",
        "white_context": "an attacker",
        "black_context": "positional style",
    })
    assert captured.get("audience_level") == "Club"
    assert captured.get("recipient") == "my friend"
    assert captured.get("white_context") == "an attacker"
    assert captured.get("black_context") == "positional style"
