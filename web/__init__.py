"""Greco Web — the FastAPI web layer (Greco Online, Phase 1).

A thin web front-end over the SAME pipeline the desktop GUI and CLI use
(importers -> analyzer -> triage -> narrator -> outputs). It adds no analysis
logic; it only collects inputs, calls the shared core, and serves the report.
Replaces the earlier Flask `webapp.py`. Run it with `run_greco_web.bat`.
"""
