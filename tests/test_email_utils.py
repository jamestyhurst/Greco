"""Tests for web.email_utils — report-ready email notifications (Phase 6).

All tests mock smtplib.SMTP so no network connection is required.
"""
from __future__ import annotations

import email as _email_module
from unittest.mock import MagicMock, patch

from web.config import Settings
from web.email_utils import send_report_ready


def _parse_mime_body(raw: str) -> str:
    """Return all decoded text from a MIME multipart message as one string."""
    msg = _email_module.message_from_string(raw)
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "text":
                payload = part.get_payload(decode=True)
                if payload:
                    parts.append(payload.decode("utf-8", errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            parts.append(payload.decode("utf-8", errors="replace"))
    return "\n".join(parts)


def _smtp_settings(**overrides) -> Settings:
    base = dict(
        engine="stockfish", model="claude-sonnet-4-6",
        engine_ok=True, key_ok=True,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="secret",
        smtp_from="greco@example.com",
        app_base_url="http://localhost:5000",
    )
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# No-op when SMTP is not configured
# ---------------------------------------------------------------------------

def test_no_email_when_smtp_not_configured():
    s = Settings(engine="sf", model="claude-sonnet-4-6", engine_ok=True, key_ok=True)
    assert not s.smtp_ready
    with patch("smtplib.SMTP") as mock_smtp:
        send_report_ready(s, "user@example.com", "alice", 42, "Fischer vs Spassky")
        mock_smtp.assert_not_called()


def test_smtp_ready_requires_host_user_password():
    s_no_host = Settings(engine="sf", model="claude-sonnet-4-6",
                         smtp_user="u", smtp_password="p")
    assert not s_no_host.smtp_ready

    s_no_user = Settings(engine="sf", model="claude-sonnet-4-6",
                         smtp_host="smtp.example.com", smtp_password="p")
    assert not s_no_user.smtp_ready

    s_no_pass = Settings(engine="sf", model="claude-sonnet-4-6",
                         smtp_host="smtp.example.com", smtp_user="u")
    assert not s_no_pass.smtp_ready


# ---------------------------------------------------------------------------
# Happy path — email sent with correct content
# ---------------------------------------------------------------------------

def test_send_report_ready_connects_to_configured_smtp():
    s = _smtp_settings()
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda self_: mock_conn
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_report_ready(s, "alice@example.com", "alice", 7, "Fischer vs Spassky")

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)


def test_send_report_ready_calls_login_and_sendmail():
    s = _smtp_settings()
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda self_: mock_conn
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_report_ready(s, "alice@example.com", "alice", 7, "Fischer vs Spassky")

        mock_conn.login.assert_called_once_with("user@example.com", "secret")
        args = mock_conn.sendmail.call_args
        assert args[0][0] == "greco@example.com"      # from
        assert "alice@example.com" in args[0][1]       # to
        body = _parse_mime_body(args[0][2])
        assert "Fischer vs Spassky" in body
        assert "http://localhost:5000/report/7" in body


def test_send_report_ready_uses_smtp_user_as_from_when_smtp_from_empty():
    s = _smtp_settings(smtp_from="")
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda self_: mock_conn
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_report_ready(s, "bob@example.com", "bob", 1, None)

        args = mock_conn.sendmail.call_args
        assert args[0][0] == "user@example.com"   # smtp_user used as from


def test_send_report_ready_falls_back_to_report_id_when_no_game_title():
    s = _smtp_settings()
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda self_: mock_conn
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_report_ready(s, "x@y.com", "xuser", 99, None)

        body = _parse_mime_body(mock_conn.sendmail.call_args[0][2])
        assert "Report #99" in body


# ---------------------------------------------------------------------------
# SMTP failure — never raises
# ---------------------------------------------------------------------------

def test_send_report_ready_does_not_raise_on_smtp_error():
    s = _smtp_settings()
    with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("no server")):
        # Must not propagate the exception
        send_report_ready(s, "alice@example.com", "alice", 5, "My Game")
