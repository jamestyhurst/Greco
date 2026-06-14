"""FastAPI routes (Greco Online, Phase 1).

The expensive Stockfish + Claude pipeline is mocked out, so these exercise the
HTTP layer — routing, request validation, the threadpool offload, and rendering —
without an engine or an API key.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.routers.analysis as analysis
from web.config import Settings
from web.main import app
from web.pipeline import AnalysisResult

client = TestClient(app)


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


def test_analyze_runs_pipeline_and_renders_result(monkeypatch, tmp_path):
    _ready(monkeypatch)
    fake = AnalysisResult(
        rid=1, base="Alice vs Bob",
        out_dir=str(tmp_path), html_path=str(tmp_path / "r.html"),
    )
    monkeypatch.setattr(analysis, "run_analysis", lambda **kw: fake)

    r = client.post("/analyze", data={"pgn_text": "1. e4 e5", "use_case": "companion"})
    assert r.status_code == 200
    assert "Alice vs Bob" in r.text          # the result page rendered
    assert "/report/1" in r.text             # links to the new report
