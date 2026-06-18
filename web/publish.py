"""Upload a finished Greco report to Cloudflare R2 for permanent public hosting.

Cloudflare R2 is S3-compatible, so we use boto3 with a custom endpoint URL.
The report gets a UUID-based key so the URL is unguessable (no sequential IDs
leaking how many reports have been published).

Setup (James fills in config.json once he creates the account):
  r2_account_id      — Cloudflare account ID (from dash.cloudflare.com → R2)
  r2_access_key_id   — R2 API token "Access Key ID"
  r2_secret_access_key — R2 API token "Secret Access Key"
  r2_bucket_name     — the R2 bucket name (create it in the dashboard)
  r2_public_url      — public bucket URL, e.g. https://pub-xxx.r2.dev
                       (enable "Public access" on the bucket first)
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from web.config import Settings


def publish_to_r2(html_path: Path, settings: "Settings") -> str:
    """Upload *html_path* to R2 and return the permanent public URL.

    Raises RuntimeError if credentials are missing (caller should 503).
    Raises any boto3/botocore exception on upload failure (caller 500s).
    """
    if not settings.r2_ready:
        raise RuntimeError("R2 credentials not configured")

    import boto3

    endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )

    key = f"reports/{uuid.uuid4().hex}.html"
    s3.upload_file(
        str(html_path),
        settings.r2_bucket_name,
        key,
        ExtraArgs={
            "ContentType": "text/html; charset=utf-8",
            # Reports are immutable once published — aggressive cache is safe.
            "CacheControl": "public, max-age=31536000, immutable",
        },
    )

    base = settings.r2_public_url.rstrip("/")
    return f"{base}/{key}"
