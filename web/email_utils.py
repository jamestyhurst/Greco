"""Email notification utilities for Greco Web (Phase 6).

Sends a "report ready" email when an analysis job completes. Uses Python's
stdlib smtplib (no extra dependencies). If smtp_host is not configured,
send_report_ready() is a silent no-op — most local installs skip email.

Configuration lives in config.json (or environment variables):
    smtp_host         — SMTP server hostname (e.g. smtp.gmail.com)
    smtp_port         — SMTP port, default 587 (STARTTLS)
    smtp_user         — SMTP auth username
    smtp_password     — SMTP auth password (or API key for SendGrid)
    smtp_from         — "From" address (defaults to smtp_user if empty)
    app_base_url      — base URL for report links (default: http://localhost:5000)

For Gmail: enable "App Passwords" and use an app-specific password.
For SendGrid: smtp_host=smtp.sendgrid.net, smtp_port=587,
              smtp_user=apikey, smtp_password=<your API key>.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from web.config import Settings

_log = logging.getLogger("greco.email")


def send_report_ready(
    settings: Settings,
    to_email: str,
    username: str,
    report_id: int,
    base: Optional[str] = None,
) -> None:
    """Send a "report ready" notification email.

    Silently skips (logs a debug line) when SMTP is not configured.
    Logs a warning on delivery failure without re-raising — a failed
    email must never crash the analysis job that succeeded.
    """
    if not settings.smtp_ready:
        _log.debug("SMTP not configured — skipping report-ready email for %s", to_email)
        return

    game_title = base or f"Report #{report_id}"
    report_url = f"{settings.app_base_url.rstrip('/')}/report/{report_id}"
    from_addr = settings.smtp_from or settings.smtp_user

    subject = f"Your Greco report is ready — {game_title}"

    text_body = (
        f"Hi {username},\n\n"
        f"Your Greco analysis of \"{game_title}\" is ready.\n\n"
        f"View your report: {report_url}\n\n"
        "— Greco"
    )

    html_body = f"""\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="font-family:Georgia,serif;color:#3A2A1A;max-width:520px;margin:0 auto;padding:24px;">
  <h2 style="color:#7A1C26;">&#9818; Greco</h2>
  <p>Hi <strong>{username}</strong>,</p>
  <p>Your analysis of <strong>&ldquo;{game_title}&rdquo;</strong> is ready.</p>
  <p style="margin:24px 0;">
    <a href="{report_url}"
       style="background:#C9A23A;color:#7A1C26;padding:12px 24px;border-radius:8px;
              text-decoration:none;font-weight:bold;">
      View Report
    </a>
  </p>
  <p style="color:#8a7a5c;font-size:.85rem;">
    Or copy this link: <a href="{report_url}">{report_url}</a>
  </p>
  <hr style="border:none;border-top:1px solid #d9c7a0;margin:24px 0;">
  <p style="color:#8a7a5c;font-size:.8rem;">Greco &mdash; engine-backed, AI-narrated chess reports.</p>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(from_addr, [to_email], msg.as_string())
        _log.info("Report-ready email sent to %s (report %d)", to_email, report_id)
    except Exception:
        _log.warning(
            "Failed to send report-ready email to %s (report %d)",
            to_email, report_id, exc_info=True,
        )
