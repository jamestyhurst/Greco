# -*- coding: utf-8 -*-
"""Greco game finder — download chess game PGNs matching a description.

Two sources:
  chesscom   — a Chess.com player's own games (public API), filter by time class
  pgnmentor  — a master's games (PGN Mentor collection), filter by result/category

Examples:
  python tools/find_games.py chesscom JamesTortoise --time-class rapid --max 20
  python tools/find_games.py chesscom JamesTortoise --color white --result loss
  python tools/find_games.py pgnmentor Carlsen --category classical --result loss --max 10
  python tools/find_games.py pgnmentor Kasparov --eco C45 --max 15

SSL note: this machine's certifi bundle is missing a root the network presents, so
we load the Windows certificate store into the SSL context (same workaround as
narrator.py / fetch_transcript.py).
"""
import argparse
import io
import re
import ssl
import zipfile
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

UA = "Greco-game-finder/0.1 (personal chess analysis tool)"
DEFAULT_OUT = r"E:\Chess\PGNs\found"
DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}
FAST_KEYWORDS = ("blitz", "rapid", "bullet", "blindfold", "online", "internet", "armageddon", "speed")


# ---------------------------------------------------------------- net / helpers
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
    s.headers.update({"User-Agent": UA})
    return s


def _tag(pgn: str, name: str) -> str:
    m = re.search(r'\[' + name + r'\s+"([^"]*)"\]', pgn)
    return m.group(1) if m else ""


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".") or "game"


def _is_online(site: str) -> bool:
    s = site.lower()
    if any(k in s for k in ("chess.com", "lichess", "playchess", "online", "internet", "icc")):
        return True
    return bool(re.search(r"\bint\b", s))   # "...INT" suffix = internet (but not "Saint")


def _tc_category(tc: str) -> str:
    """Category from a TimeControl tag, or '' if unknown."""
    if not tc or tc in ("?", "-"):
        return ""
    if "/" in tc:
        # Move-based TC: "moves/seconds" — correspondence if time-per-move ≥ 1 day.
        try:
            moves_s, secs_s = tc.split("/", 1)[0].strip(), tc.split("/", 1)[1].split(":")[0].strip()
            if int(secs_s) / max(int(moves_s), 1) >= 86400:
                return ""   # correspondence — not a speed category
            return "classical"
        except (ValueError, IndexError):
            return "classical"
    try:
        if "+" in tc:
            base, inc = tc.split("+", 1)
            base, inc = int(base), int(inc)
        else:
            base, inc = int(tc), 0
    except (ValueError, TypeError):
        return ""
    est = base + 40 * inc
    if est >= 3600:
        return "classical"
    if est >= 600:
        return "rapid"
    if est >= 180:
        return "blitz"
    return "bullet"


def _classify_category(event: str, site: str, tc: str) -> str:
    ev = (event + " " + site).lower()
    if "bullet" in ev:
        return "bullet"
    if "blitz" in ev or "titled tue" in ev or "titled tuesday" in ev:
        return "blitz"
    if any(k in ev for k in ("rapid", "blindfold", "armageddon", "speed chess")):
        return "rapid"
    # Modern rapid/blitz events that read like classical tournaments but aren't,
    # and (in PGN Mentor data) usually carry no rapid/blitz keyword or TimeControl.
    if any(h in ev for h in (
        "esports world cup", "clutch", "champions chess tour", "world rapid", "world blitz",
        "freestyle", "meltwater", "aimchess", "chessable masters", "carlsen invitational",
        "skilling", "airthings", "julius baer", "lindores", "new in chess classic",
        "tour final", "play-in", "ftx crypto", "global chess league", "cct ", "cct final",
        " gcl ", " gcl", "gcl ", "speed chess", "speedchess", "titled", "rapidchess",
        # Additional rapid/online events that PGN Mentor indexes without a TC tag:
        "superunited", "grand chess tour", "chess.com rapid", "chess.com blitz",
        "pro chess league", "chess olympiad online", "fide online", "nations cup",
        "chess24", "chessify", "chess league", "pro league",
    )):
        return "rapid"
    by_tc = _tc_category(tc)
    if by_tc:
        return by_tc
    # No explicit signal: online games are essentially never classical.
    return "rapid" if _is_online(site) else "classical"


# ------------------------------------------------------------------- Chess.com
def _classify_chesscom(game: dict, user: str):
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


def fetch_chesscom(username, time_class=None, color=None, result=None, eco=None,
                   since=None, max_games=20, out_dir=DEFAULT_OUT):
    s = _session()
    resp = s.get(f"https://api.chess.com/pub/player/{username}/games/archives", timeout=30)
    if resp.status_code == 404:
        print(f"No Chess.com player named '{username}'.")
        return []
    resp.raise_for_status()
    months = resp.json().get("archives", [])
    if since:
        months = [m for m in months if int(m.rsplit("/", 2)[-2]) >= int(since)]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for month_url in reversed(months):
        if len(saved) >= max_games:
            break
        r = s.get(month_url, timeout=60)
        if r.status_code != 200:
            continue
        for g in reversed(r.json().get("games", [])):
            if len(saved) >= max_games:
                break
            if time_class and g.get("time_class") != time_class:
                continue
            cls = _classify_chesscom(g, username)
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
            if eco and eco.lower() not in (_tag(pgn, "ECO") + " " + _tag(pgn, "ECOUrl")).lower():
                continue
            date = (_tag(pgn, "UTCDate") or _tag(pgn, "Date")).replace(".", "-")
            fname = _safe(f"{date} {_tag(pgn,'White')} vs {_tag(pgn,'Black')} "
                          f"({g.get('time_class','?')}, {username} {outcome})") + ".pgn"
            (out / fname).write_text(pgn, encoding="utf-8")
            saved.append(fname)
    return saved


# ------------------------------------------------------------------- PGN Mentor
def _otb_outcome(player, white, black, result):
    p = player.lower()
    if p in white.lower():
        is_white = True
    elif p in black.lower():
        is_white = False
    else:
        return None
    if result == "1/2-1/2":
        return "draw"
    if result == "1-0":
        return "win" if is_white else "loss"
    if result == "0-1":
        return "loss" if is_white else "win"
    return None


def fetch_pgnmentor(player, category=None, result=None, eco=None,
                    max_games=20, out_dir=DEFAULT_OUT):
    s = _session()
    url = f"https://www.pgnmentor.com/players/{player}.zip"
    r = s.get(url, timeout=120)
    if r.status_code == 404:
        print(f"No PGN Mentor collection for '{player}'. Use the name as it appears at "
              f"pgnmentor.com/files.html (often the surname, e.g. Carlsen, Kasparov, Nakamura).")
        return []
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    pgn_name = next((n for n in z.namelist() if n.lower().endswith(".pgn")), None)
    if not pgn_name:
        print("That collection had no .pgn inside.")
        return []
    text = z.read(pgn_name).decode("utf-8", "ignore")

    matches = []
    for gtext in re.split(r"(?=\[Event )", text):   # split into individual games
        if not gtext.strip():
            continue
        white, black, res = _tag(gtext, "White"), _tag(gtext, "Black"), _tag(gtext, "Result")
        outcome = _otb_outcome(player, white, black, res)
        if outcome is None or (result and outcome != result):
            continue
        cat = _classify_category(_tag(gtext, "Event"), _tag(gtext, "Site"), _tag(gtext, "TimeControl"))
        if category and cat != category:
            continue
        if eco and eco.lower() not in _tag(gtext, "ECO").lower():
            continue
        matches.append((_tag(gtext, "Date"), white, black, cat, outcome, gtext))

    matches.sort(key=lambda m: m[0], reverse=True)   # most recent first
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for date, white, black, cat, outcome, gtext in matches[:max_games]:
        fname = _safe(f"{date.replace('.', '-')} {white} vs {black} ({cat}, {player} {outcome})") + ".pgn"
        (out / fname).write_text(gtext.strip() + "\n", encoding="utf-8")
        saved.append(fname)
    print(f"(scanned the collection: {len(matches)} game(s) matched the filters)")
    return saved


# ------------------------------------------------------------------- Similar
def _time_class_from_tc(tc: str):
    if not tc or tc in ("?", "-"):
        return None
    if "/" in tc:
        return "daily"
    try:
        base = int(tc.split("+")[0])
    except ValueError:
        return None
    if base >= 86400:
        return "daily"
    if base >= 600:
        return "rapid"
    if base >= 180:
        return "blitz"
    return "bullet"


def _prune(out_dir, cap):
    """Keep only the newest `cap` .pgn files in out_dir (a rotating pool)."""
    if not cap or cap <= 0:
        return
    files = sorted(Path(out_dir).glob("*.pgn"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[cap:]:
        try:
            p.unlink()
        except OSError:
            pass


def fetch_similar(pgn_path, max_games=2, out_dir=DEFAULT_OUT):
    """Given a game's PGN, pull a few *similar* games — same Chess.com player and
    time class — so a developer's test pool keeps refilling itself."""
    text = Path(pgn_path).read_text(encoding="utf-8", errors="ignore")
    tclass = _time_class_from_tc(_tag(text, "TimeControl"))
    for player in (_tag(text, "White"), _tag(text, "Black")):
        if not player or player == "?":
            continue
        saved = fetch_chesscom(player, time_class=tclass, max_games=max_games, out_dir=out_dir)
        if saved:
            print(f"(similar: recent {tclass or 'any'}-time-class games by {player})")
            return saved
    print("Couldn't resolve a Chess.com player from this PGN to find a similar game.")
    return []


# --------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Find & download chess game PGNs for Greco.")
    sub = ap.add_subparsers(dest="source", required=True)

    cc = sub.add_parser("chesscom", help="a Chess.com player's own games")
    cc.add_argument("username")
    cc.add_argument("--time-class", choices=["bullet", "blitz", "rapid", "daily"])
    cc.add_argument("--color", choices=["white", "black"])
    cc.add_argument("--result", choices=["win", "loss", "draw"])
    cc.add_argument("--eco", help="match ECO code or opening name (e.g. B02, Alekhine)")
    cc.add_argument("--since", type=int, help="only games from this year onward")
    cc.add_argument("--max", type=int, default=20, dest="max_games")
    cc.add_argument("--out", default=DEFAULT_OUT)
    cc.add_argument("--cap", type=int, default=0, help="after saving, keep only the newest N .pgn in --out")

    pm = sub.add_parser("pgnmentor", help="a master's games (PGN Mentor collection)")
    pm.add_argument("player", help="collection name, e.g. Carlsen, Kasparov, Nakamura")
    pm.add_argument("--category", choices=["classical", "rapid", "blitz", "bullet"])
    pm.add_argument("--result", choices=["win", "loss", "draw"])
    pm.add_argument("--eco", help="match ECO code (e.g. C45, B02)")
    pm.add_argument("--max", type=int, default=20, dest="max_games")
    pm.add_argument("--out", default=DEFAULT_OUT)
    pm.add_argument("--cap", type=int, default=0, help="after saving, keep only the newest N .pgn in --out")

    sm = sub.add_parser("similar", help="pull games similar to a given PGN (same player + time class)")
    sm.add_argument("pgn_path", help="path to the .pgn of the game just analysed")
    sm.add_argument("--max", type=int, default=2, dest="max_games")
    sm.add_argument("--out", default=DEFAULT_OUT)
    sm.add_argument("--cap", type=int, default=40, help="keep only the newest N .pgn in --out (rotating test pool)")

    a = ap.parse_args()
    if a.source == "chesscom":
        saved = fetch_chesscom(a.username, a.time_class, a.color, a.result, a.eco,
                               a.since, a.max_games, a.out)
    elif a.source == "pgnmentor":
        saved = fetch_pgnmentor(a.player, a.category, a.result, a.eco, a.max_games, a.out)
    else:
        saved = fetch_similar(a.pgn_path, a.max_games, a.out)

    _prune(a.out, a.cap)
    print(f"\nSaved {len(saved)} game(s) to {a.out}" + (f"  (folder capped at {a.cap})" if a.cap else ""))
    for f in saved:
        print("  ", f)
    if not saved:
        print("(no games matched — try loosening the filters)")


if __name__ == "__main__":
    main()
