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
    monkeypatch.setattr(analysis, "create_report_ownership", lambda rid, uid, **kw: None)
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
    assert "Greco" in r.text
    assert "analyze" in r.text.lower()


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


# ---------------------------------------------------------------------------
# Lichess URL input (R-IN1)
# ---------------------------------------------------------------------------

def test_lichess_url_fetches_pgn_and_runs_analysis(monkeypatch, tmp_path):
    """When lichess_url is provided, load_from_lichess is called and its PGN
    is forwarded to run_analysis."""
    _ready(monkeypatch)
    captured = {}
    FAKE_PGN = "[Event \"Lichess Game\"]\n1. d4 d5 *"

    import importers as _imp
    monkeypatch.setattr(_imp, "load_from_lichess", lambda url_or_id: (FAKE_PGN, "lichess"))

    def fake_run(**kw):
        captured.update(kw)
        return AnalysisResult(rid=10, base="LichessGame",
                              out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"))

    monkeypatch.setattr(analysis, "run_analysis", fake_run)

    r = client.post("/analyze", data={"lichess_url": "https://lichess.org/abcd1234"})
    assert r.status_code == 200
    assert _UUID_RE.search(r.text), "Expected a job UUID in the waiting page"
    assert captured.get("pgn_text") == FAKE_PGN


def test_lichess_url_error_returns_400(monkeypatch):
    """When load_from_lichess raises, the route returns 400 with an error page."""
    _ready(monkeypatch)

    import importers as _imp
    monkeypatch.setattr(
        _imp, "load_from_lichess",
        lambda url_or_id: (_ for _ in ()).throw(ValueError("Game not found"))
    )

    r = client.post("/analyze", data={"lichess_url": "https://lichess.org/notreal"})
    assert r.status_code == 400
    assert "Lichess" in r.text or "Game not found" in r.text


def test_waiting_page_shows_logged_in_nav(monkeypatch, tmp_path):
    """Regression: POST /analyze rendered the waiting page without the user,
    so a signed-in user saw 'Sign in' in the nav mid-analysis."""
    _ready(monkeypatch)
    from web.auth import get_current_user as gcu
    fake = AnalysisResult(rid=20, base="A vs B",
                          out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"))
    monkeypatch.setattr(analysis, "run_analysis", lambda **kw: fake)
    app.dependency_overrides[gcu] = lambda: _FAKE_USER
    try:
        r = client.post("/analyze", data={"pgn_text": "1. e4 e5"})
        assert r.status_code == 200
        assert "Sign&nbsp;out" in r.text
        assert "Sign&nbsp;in" not in r.text
    finally:
        app.dependency_overrides.pop(gcu, None)


def test_waiting_page_explains_vanished_job():
    """The waiting page must handle a 404 from /job/{id} (in-memory jobs die
    with the server) by telling the user instead of spinning forever."""
    from web.templates import render_waiting
    html = render_waiting("dead-job-id")
    assert "r.status===404" in html
    assert "no longer running" in html


def _extract_scripts(html: str):
    return re.findall(r"<script>(.*?)</script>", html, flags=re.S)


def test_rendered_js_has_no_newline_inside_string_literals():
    """Regression for the bug that froze every web analysis at 'Queued':
    the templates are NON-raw Python strings, so a '\\n' typed with a single
    backslash inside the embedded JS becomes a real newline in the served
    page — splitting a JS string literal across lines, a SyntaxError that
    silently kills the whole script (browsers don't run half a script).

    Python can't run JS, so this checks the failure's fingerprint: any line
    of rendered script whose single-quoted strings don't close by line end.
    """
    from types import SimpleNamespace
    from web.config import Settings
    from web.templates import render_home, render_waiting

    user = SimpleNamespace(username="u", lichess_username="u",
                           chesscom_username="u", is_admin=False, role="user")
    pages = {
        "waiting": render_waiting("jid", user=user),
        "home": render_home(
            Settings(engine="sf", model="m", engine_ok=True, key_ok=True),
            user=user,
        ),
    }
    for name, html in pages.items():
        for script in _extract_scripts(html):
            # Comments may legitimately contain apostrophes — drop them first.
            script = re.sub(r"/\*.*?\*/", "", script, flags=re.S)
            for lineno, line in enumerate(script.splitlines(), start=1):
                # Strip escaped quotes, then require an even number of bare
                # single quotes on the line (JS strings must close same-line).
                bare = line.replace("\\\\", "").replace("\\'", "")
                assert bare.count("'") % 2 == 0, (
                    f"{name} page, rendered script line {lineno}: a "
                    f"single-quoted JS string never closes on its own line "
                    f"(escaped newline leak?): {line!r}"
                )


# ---------------------------------------------------------------------------
# game_url input — Chess.com and Lichess auto-detection
# ---------------------------------------------------------------------------

def test_chesscom_game_url_fetches_pgn_and_runs_analysis(monkeypatch, tmp_path):
    """A chess.com URL in game_url routes to load_from_chesscom, passing the
    logged-in user's linked Chess.com username."""
    _ready(monkeypatch)
    captured, seen = {}, {}
    FAKE_PGN = "[Event \"Live Chess\"]\n1. c4 e5 *"

    import importers as _imp

    def fake_cc(url_or_id, username=None, months_to_scan=6):
        seen["url"], seen["username"] = url_or_id, username
        return FAKE_PGN, "chesscom"

    monkeypatch.setattr(_imp, "load_from_chesscom", fake_cc)

    def fake_run(**kw):
        captured.update(kw)
        return AnalysisResult(rid=12, base="CC",
                              out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"))

    monkeypatch.setattr(analysis, "run_analysis", fake_run)

    r = client.post("/analyze",
                    data={"game_url": "https://www.chess.com/game/live/123"})
    assert r.status_code == 200
    assert captured.get("pgn_text") == FAKE_PGN
    assert seen["url"].endswith("/123")


def test_game_url_accepts_lichess_too(monkeypatch, tmp_path):
    """A lichess URL in the unified game_url field routes to load_from_lichess."""
    _ready(monkeypatch)
    captured = {}
    FAKE_PGN = "[Event \"Lichess\"]\n1. Nf3 *"

    import importers as _imp
    monkeypatch.setattr(_imp, "load_from_lichess", lambda url_or_id: (FAKE_PGN, "lichess"))

    def fake_run(**kw):
        captured.update(kw)
        return AnalysisResult(rid=13, base="L",
                              out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"))

    monkeypatch.setattr(analysis, "run_analysis", fake_run)

    r = client.post("/analyze", data={"game_url": "https://lichess.org/abcd1234"})
    assert r.status_code == 200
    assert captured.get("pgn_text") == FAKE_PGN


def test_chesscom_url_without_linked_username_is_400(monkeypatch):
    """No chesscom_username on the account -> friendly 400, and no network:
    load_from_chesscom raises before it ever builds an HTTP client."""
    _ready(monkeypatch)
    r = client.post("/analyze",
                    data={"game_url": "https://www.chess.com/game/live/123"})
    assert r.status_code == 400
    assert "Chess.com" in r.text


def test_lichess_url_takes_priority_over_pgn_text(monkeypatch, tmp_path):
    """lichess_url is preferred over pasted pgn_text when both are submitted."""
    _ready(monkeypatch)
    captured = {}
    LICHESS_PGN = "[Event \"Lichess\"]\n1. e4 *"

    import importers as _imp
    monkeypatch.setattr(_imp, "load_from_lichess", lambda url_or_id: (LICHESS_PGN, "lichess"))

    def fake_run(**kw):
        captured.update(kw)
        return AnalysisResult(rid=11, base="X",
                              out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"))

    monkeypatch.setattr(analysis, "run_analysis", fake_run)

    client.post("/analyze", data={
        "lichess_url": "https://lichess.org/abcd1234",
        "pgn_text": "1. d4 Nf6 2. c4",
    })
    assert captured.get("pgn_text") == LICHESS_PGN
