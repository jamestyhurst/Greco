# -*- coding: utf-8 -*-
"""Fetch a YouTube transcript as plain text — for building Greco commentary
references. Transcripts ONLY; no audio/video is ever downloaded (tiny files).

Usage:
    python fetch_transcript.py <VIDEO_ID_or_URL> [output.txt]

SSL note: this machine's certifi bundle is missing a root the network presents,
so we load the Windows certificate store into the SSL context (same workaround
as narrator.py / importers.py). The folder is named "_tools" so Greco's
commentary loader ignores it.
"""
import re
import ssl
import sys
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from youtube_transcript_api import YouTubeTranscriptApi


def _win_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.load_default_certs()
    if hasattr(ssl, "enum_certificates"):  # Windows
        for store in ("ROOT", "CA"):
            try:
                for cert, encoding, _trust in ssl.enum_certificates(store):
                    if encoding == "x509_asn":
                        try:
                            ctx.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(cert))
                        except ssl.SSLError:
                            pass
            except (OSError, FileNotFoundError):
                pass
    return ctx


class _WinCertAdapter(HTTPAdapter):
    def __init__(self, *a, **k):
        self._ctx = _win_ssl_context()
        super().__init__(*a, **k)

    def init_poolmanager(self, *a, **k):
        k["ssl_context"] = self._ctx
        return super().init_poolmanager(*a, **k)

    def proxy_manager_for(self, *a, **k):
        k["ssl_context"] = self._ctx
        return super().proxy_manager_for(*a, **k)


def to_video_id(s: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else s.strip()


def fetch_text(video_id: str, languages=("en", "en-US", "en-GB")) -> str:
    session = requests.Session()
    session.mount("https://", _WinCertAdapter())
    api = YouTubeTranscriptApi(http_client=session)
    fetched = api.fetch(video_id, languages=list(languages))
    parts = []
    for snippet in fetched:
        text = getattr(snippet, "text", None)
        if text is None and isinstance(snippet, dict):
            text = snippet.get("text", "")
        if text:
            parts.append(text)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python fetch_transcript.py <video_id_or_url> [out.txt]")
        sys.exit(2)
    vid = to_video_id(sys.argv[1])
    text = fetch_text(vid)
    print("VIDEO_ID:", vid)
    print("CHARS:", len(text))
    if len(sys.argv) >= 3:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
        print("WROTE:", sys.argv[2])
    else:
        print("PREVIEW:", text[:600])
