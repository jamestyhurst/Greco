"""
PGN source loaders.

Each loader returns (pgn_text, human_readable_source_description).
`load_pgn` auto-detects which loader to use from the user's input string.
"""

from __future__ import annotations

import re
import ssl
from pathlib import Path
from typing import Tuple

import httpx


LICHESS_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?lichess\.org/(?:embed/game/|game/|)([a-zA-Z0-9]{8})",
    re.IGNORECASE,
)
CHESSCOM_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?chess\.com/", re.IGNORECASE)


def _make_http_client() -> httpx.Client:
    """Same Windows-cert-trusting client used elsewhere in Greco."""
    ctx = ssl.create_default_context()
    ctx.load_default_certs()
    if hasattr(ssl, "enum_certificates"):
        for store_name in ("ROOT", "CA"):
            try:
                for cert, encoding, _trust in ssl.enum_certificates(store_name):
                    if encoding == "x509_asn":
                        try:
                            ctx.load_verify_locations(
                                cadata=ssl.DER_cert_to_PEM_cert(cert)
                            )
                        except ssl.SSLError:
                            pass
            except (OSError, FileNotFoundError):
                pass
    return httpx.Client(verify=ctx, timeout=httpx.Timeout(30.0))


def load_from_file(path: Path) -> Tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    return text, f"file: {path}"


def load_from_lichess(url_or_id: str) -> Tuple[str, str]:
    match = LICHESS_URL_RE.search(url_or_id)
    game_id = match.group(1) if match else url_or_id.strip()[:8]
    if not re.fullmatch(r"[a-zA-Z0-9]{8}", game_id):
        raise ValueError(f"Could not extract a Lichess game ID from: {url_or_id}")

    url = f"https://lichess.org/game/export/{game_id}"
    with _make_http_client() as client:
        response = client.get(
            url,
            headers={"Accept": "application/x-chess-pgn"},
            params={"clocks": "false", "evals": "false"},
        )
        response.raise_for_status()
    return response.text, f"Lichess game {game_id}"


def load_from_chesscom(_url: str) -> Tuple[str, str]:
    """
    Placeholder. Chess.com does not offer a clean public per-game API by URL,
    only by player+date via api.chess.com/pub/player/{user}/games/{yyyy}/{mm}.
    For now, ask the user to download the PGN from chess.com directly.
    """
    raise NotImplementedError(
        "Chess.com URLs aren't yet supported. Use chess.com's 'Share' → "
        "'Download PGN' button on the game, then pass --pgn-file with the "
        "downloaded file."
    )


def load_pgn(source: str) -> Tuple[str, str]:
    """
    Auto-detect the source type:
    - existing file path  → load_from_file
    - lichess.org URL/ID  → load_from_lichess
    - chess.com URL       → load_from_chesscom (not yet implemented)
    - otherwise           → assume it's raw PGN text
    """
    if not source:
        raise ValueError("Empty source")

    # File path?
    candidate = Path(source)
    if candidate.exists() and candidate.is_file():
        return load_from_file(candidate)

    # Lichess?
    if LICHESS_URL_RE.search(source):
        return load_from_lichess(source)

    # Chess.com?
    if CHESSCOM_URL_RE.search(source):
        return load_from_chesscom(source)

    # Raw PGN text (must contain at least a header or a move).
    if "[" in source or re.search(r"\d+\.\s", source):
        return source, "inline PGN text"

    raise ValueError(
        f"Could not figure out what {source!r} is. Pass a file path, a "
        "Lichess URL/ID, or raw PGN text."
    )
