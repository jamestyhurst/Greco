# -*- coding: utf-8 -*-
"""Greco game finder — download chess game PGNs matching a description.

Currently supports Chess.com via its public API (no login needed). Master/OTB
sources (PGN Mentor, lichess) can be added the same way.

Examples:
    python tools/find_games.py JamesTortoise --time-class rapid --max 20
    python tools/find_games.py JamesTortoise --result loss --color white --max 10
    python tools/find_games.py someUser --eco B02 --max 15        # Alekhine's Defense
    python tools/find_games.py someUser --since 2025 --out "E:\\Chess\\PGNs\\found"

SSL note: this machine's certifi bundle is missing a root the network presents,
so we load the Windows certificate store into the SSL context (same workaround as
narrator.py / fetch_transcript.py).
"""
import argparse
import re
import ssl
import sys
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

UA = "Greco-game-finder/0.1 (personal chess analysis tool)"
DEFAULT_OUT = r"E:\Chess\PGNs\found"
DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}


def _win_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.load_default_certs()
    if hasattr(ssl, "enum_certificates"):  # Windows
        for store in ("ROOT", "CA"):
            try:
                for cert, enc, _ in ssl.enum_certificates(store):
                    if enc == "x509_asn":
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


def _session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", _WinCertAdapter())
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    return s


def _tag(pgn: str, name: str) -> str:
    m = re.search(r'\[' + name + r'\s+"([^"]*)"\]', pgn)
    return m.group(1) if m else ""


def _classify(game: dict, user: str):
    """Return (color, outcome, opponent_name) for `user`, or None if not in game."""
    u = user.lower()
    white, black = game.get("white", {}), game.get("black", {})
    if white.get("username", "").lower() == u:
        me, opp, color = white, black, "white"
    elif black.get("username", "").lower() == u:
        me, opp, color = black, white, "black"
    else:
        return None
    r = me.get("result", "")
    outcome = "win" if r == "win" else ("draw" if r in DRAW_RESULTS else "loss")
    return color, outcome, opp.get("username", "?")


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".") or "game"


def fetch_chesscom(username, time_class=None, color=None, result=None, eco=None,
                   since=None, max_games=20, out_dir=DEFAULT_OUT):
    s = _session()
    arch_url = f"https://api.chess.com/pub/player/{username}/games/archives"
    resp = s.get(arch_url, timeout=30)
    if resp.status_code == 404:
        print(f"No Chess.com player named '{username}'.")
        return []
    resp.raise_for_status()
    months = resp.json().get("archives", [])  # oldest -> newest
    if since:
        months = [m for m in months if int(m.rsplit("/", 2)[-2]) >= int(since)]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for month_url in reversed(months):           # newest month first
        if len(saved) >= max_games:
            break
        r = s.get(month_url, timeout=60)
        if r.status_code != 200:
            continue
        for g in reversed(r.json().get("games", [])):   # newest game first
            if len(saved) >= max_games:
                break
            if time_class and g.get("time_class") != time_class:
                continue
            cls = _classify(g, username)
            if not cls:
                continue
            c, outcome, opp = cls
            if color and c != color:
                continue
            if result and outcome != result:
                continue
            pgn = g.get("pgn", "")
            if not pgn:
                continue
            if eco:
                hay = (_tag(pgn, "ECO") + " " + _tag(pgn, "ECOUrl")).lower()
                if eco.lower() not in hay:
                    continue
            date = (_tag(pgn, "UTCDate") or _tag(pgn, "Date")).replace(".", "-")
            white, black = _tag(pgn, "White"), _tag(pgn, "Black")
            tc = g.get("time_class", "?")
            fname = _safe(f"{date} {white} vs {black} ({tc}, {username} {outcome})") + ".pgn"
            path = out / fname
            path.write_text(pgn, encoding="utf-8")
            saved.append(fname)
    return saved


def main():
    ap = argparse.ArgumentParser(description="Find & download chess PGNs (Chess.com).")
    ap.add_argument("username", help="Chess.com username")
    ap.add_argument("--time-class", choices=["bullet", "blitz", "rapid", "daily"])
    ap.add_argument("--color", choices=["white", "black"])
    ap.add_argument("--result", choices=["win", "loss", "draw"])
    ap.add_argument("--eco", help="match ECO code or opening name (e.g. B02, Alekhine)")
    ap.add_argument("--since", type=int, help="only games from this year onward")
    ap.add_argument("--max", type=int, default=20, dest="max_games")
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"output folder (default {DEFAULT_OUT})")
    a = ap.parse_args()
    saved = fetch_chesscom(a.username, a.time_class, a.color, a.result, a.eco,
                           a.since, a.max_games, a.out)
    print(f"\nSaved {len(saved)} game(s) to {a.out}")
    for f in saved:
        print("  ", f)
    if not saved:
        print("(no games matched — try loosening the filters)")


if __name__ == "__main__":
    main()
