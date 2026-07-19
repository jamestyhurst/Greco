"""
Assemble the final Greco report.

The narrator produces a Markdown narrative. This module:
  1. Prepends a header (game metadata + full move list for reference).
  2. Generates board images for selected moves and inserts them under the
     corresponding `### N. SAN` headers.
  3. Generates an eval-graph image and inserts it under the header.
  4. Optionally converts the assembled Markdown to a simple HTML file.

Designed so each piece (boards, eval graph, HTML wrap) is independently
toggleable.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote

import chess

from analyzer import GameAnalysis, MoveAnalysis
from narrator import _humanize_time_control
from renderers import render_eval_graph_png, save_board_svg


# Levels at which board diagrams may be rendered.
BOARD_TIERS = {
    "off": set(),
    "tier3": {3},
    "tier2": {2, 3},
    "all": {1, 2, 3},
}


def select_diagram_plies(game, tiers, boards_at: str = "tier3", periodic_every: int = 6) -> set:
    """Decide which plies get a board diagram — and therefore a `### N. SAN` header.

    This is the SINGLE source of truth shared by the narrator (which is told these
    moves, via `_move_to_dict`'s `diagram` flag, so it writes one header section per
    diagrammed move) and by `assemble_report` (which renders the boards and anchors
    them to those headers). Tying headers to this set is what stops both the
    header/bold duplication and the out-of-order board clumping: a header exists iff
    a board does. Diagrammed plies = the tier-selected moves PLUS periodic snapshots,
    so the opening and quiet stretches are depicted too, not only Tier-2/3 moments.

    Note: callers must use the same `boards_at`/`periodic_every` here as at assemble
    time, or the two sets would drift; `generate_narrative` now threads both through
    to its narrator call so the narrator's header set always matches the boards
    `assemble_report` renders.
    """
    tiers_to_render = BOARD_TIERS.get(boards_at, BOARD_TIERS["tier3"])
    plies = {move.ply for move, tier in zip(game.moves, tiers) if tier in tiers_to_render}
    # 'off' means genuinely no diagrams — don't OR in the periodic snapshots then.
    if boards_at != "off" and periodic_every and periodic_every > 0:
        plies |= {move.ply for move in game.moves if move.ply % periodic_every == 0}
    return plies


# --------------------------------------------------------------------------
# Report naming + output location
# --------------------------------------------------------------------------
def time_control_category(tc: str) -> str:
    """Map a PGN TimeControl tag to a general category for the filename.

    Returns "Bullet", "Blitz", "Rapid", "Classical", "Daily", or "" (unknown).
    Uses a lichess-style estimate (base + 40*increment) so that, e.g., 180+2
    reads as Blitz rather than Bullet.
    """
    if not tc or tc in ("?", "-"):
        return ""
    if "/" in tc:  # correspondence, e.g. "1/259200"
        return "Daily"
    try:
        if "+" in tc:
            base_s, inc_s = tc.split("+", 1)
            base, inc = int(base_s), int(inc_s)
        else:
            base, inc = int(tc), 0
    except (ValueError, TypeError):
        return ""
    if base >= 86400:
        return "Daily"
    estimate = base + 40 * inc
    if estimate < 180:
        return "Bullet"
    if estimate < 600:
        return "Blitz"
    if estimate < 3600:
        return "Rapid"
    return "Classical"


def is_daily_game(headers: dict) -> bool:
    """True for daily / correspondence games (a day or more per move).

    Reuses the tested `time_control_category` for the TimeControl tag, with an
    Event/Site keyword backstop for PGNs whose TimeControl is missing or garbled.
    This is the single source of truth for "is this daily?", shared by the narrator
    (which injects the daily voice protocol) and the report filename category.
    """
    if time_control_category(headers.get("TimeControl", "")) == "Daily":
        return True
    text = f"{headers.get('Event', '')} {headers.get('Site', '')}".lower()
    return bool(re.search(r"\b(daily|correspondence)\b", text))


def _year_from_headers(headers: dict) -> str:
    """Pull a 4-digit year from Date / UTCDate / EventDate, or '' if unknown."""
    for key in ("Date", "UTCDate", "EventDate"):
        value = headers.get(key) or ""
        m = re.match(r"(\d{4})", value)
        if m and m.group(1) != "0000":
            return m.group(1)
    return ""


def _safe_filename(name: str) -> str:
    """Make a string safe as a Windows filename (keeps spaces, commas, '.')."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(".")
    return name or "game"


def report_basename(game: GameAnalysis) -> str:
    """Build an informational report filename stem:
    'White vs. Black, Category, Year' (category/year omitted if unknown)."""
    h = game.headers
    white = (h.get("White") or "White").strip() or "White"
    black = (h.get("Black") or "Black").strip() or "Black"
    parts = [f"{white} vs. {black}"]
    category = time_control_category(h.get("TimeControl", ""))
    if category:
        parts.append(category)
    year = _year_from_headers(h)
    if year:
        parts.append(year)
    return _safe_filename(", ".join(parts))


def default_reports_dir() -> Path:
    r"""Where reports are saved. Default: the user's Documents\Greco Reports (on
    C:) — this is the shareable-product default. An in-house setup can redirect
    reports anywhere (e.g. an external drive) by setting the GRECO_REPORTS_DIR
    environment variable."""
    override = os.environ.get("GRECO_REPORTS_DIR")
    base = Path(override) if override else (Path.home() / "Documents" / "Greco Reports")
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except Exception:
        fallback = Path.home() / "Greco Reports"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


# Sub-folder of the PGN library where games that already have a report are filed.
REPORTED_GAMES_DIRNAME = "Games with Reports"


def pgn_library_dir() -> Path:
    r"""The user's canonical PGN library: Documents\Chess Game Files. This is the
    C: source that sync_pgns.bat mirrors to E:. Auto-filing (below) only ever acts
    on files sitting directly in this folder."""
    return Path.home() / "Documents" / "Chess Game Files"


def archive_reported_pgn(pgn_path, library_dir: Optional[Path] = None) -> Optional[Path]:
    r"""File a PGN into '<library>\Games with Reports' after a report was generated.

    Best-effort and deliberately conservative — never raises, so a filing problem
    can never sink a finished report:
      * acts only on a file sitting DIRECTLY in the library root (never touches
        PGNs elsewhere on disk, and never re-files one already in a sub-folder);
      * on a name collision with an identical archived copy, drops the duplicate;
      * on a collision with different content, moves under a numbered name.

    Returns the file's new path if it was moved (or already archived as an
    identical copy), else None.
    """
    try:
        src = Path(pgn_path)
        root = Path(library_dir) if library_dir else pgn_library_dir()
        if not src.is_file() or src.parent.resolve() != root.resolve():
            return None
        dest_dir = root / REPORTED_GAMES_DIRNAME
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            if dest.read_bytes() == src.read_bytes():
                src.unlink()  # exact duplicate of the archived copy
                return dest
            stem, suffix = src.stem, src.suffix
            n = 2
            while dest.exists():
                dest = dest_dir / f"{stem} ({n}){suffix}"
                n += 1
        src.rename(dest)
        return dest
    except OSError:
        return None


# How a game ended, as a short human label. Keyed on substrings of the PGN
# `Termination` tag (Chess.com writes "X won by resignation" / "won on time" /
# "game abandoned"; Lichess writes "Normal" / "Time forfeit").
_TERMINATION_PATTERNS = [
    ("resign", "resignation"),
    ("time", "on time"),
    ("abandon", "abandonment"),
    ("stalemate", "stalemate"),
    ("agree", "agreement"),
    ("repetition", "repetition"),
    ("insufficient", "insufficient material"),
    ("50", "fifty-move rule"),
]


def termination_reason(headers: dict, final_san: str = "") -> str:
    """Short, data-backed reason the game ended: 'checkmate', 'resignation',
    'on time', 'draw', … or '' when unknowable.

    A '#' on the final move proves mate; otherwise the Termination tag decides;
    a decisive result with no usable tag defaults to 'resignation' (the same
    rule the narrator follows); a bare draw is just 'draw'. This is what lets
    the move list and PGN viewer mark non-checkmate endings visibly (James's
    2026-07-18 critique, item 3)."""
    if (final_san or "").endswith("#"):
        return "checkmate"
    term = (headers.get("Termination") or "").lower()
    for needle, label in _TERMINATION_PATTERNS:
        if needle in term:
            return label
    result = headers.get("Result", "")
    if result in ("1-0", "0-1"):
        return "resignation"
    if result == "1/2-1/2":
        return "draw"
    return ""


def format_move_list(game: GameAnalysis) -> str:
    """Return the game's mainline as '1. e4 e5 2. Nf3 Nc6 ...' wrapped to ~70 cols.
    Ends with the result plus, for non-checkmate finishes, the reason in
    parentheses — '44. Kf5 1-0 (resignation)' — so a reader scanning the moves
    sees at once that the game did not end in mate."""
    tokens: List[str] = []
    for move in game.moves:
        if move.side == "White":
            tokens.append(f"{move.move_number}.")
            tokens.append(move.san)
        else:
            tokens.append(move.san)
    if game.result and game.result != "*":
        tokens.append(game.result)
        reason = termination_reason(
            game.headers, game.moves[-1].san if game.moves else ""
        )
        if reason and reason != "checkmate":
            tokens.append(f"({reason})")

    # Word-wrap to ~70 columns.
    lines: List[str] = []
    current = ""
    for tok in tokens:
        if not current:
            current = tok
        elif len(current) + 1 + len(tok) > 70:
            lines.append(current)
            current = tok
        else:
            current += " " + tok
    if current:
        lines.append(current)
    return "\n".join(lines)


def build_header(game: GameAnalysis) -> str:
    h = game.headers
    # PGN tag values are untrusted (uploaded / pasted) and flow into Markdown that is
    # rendered with inline-HTML passthrough, so escape them — a crafted tag like
    # [White "<img src=x onerror=...>"] must not inject HTML into the report (a
    # stored-XSS guard that matters for the Phase 3+ multi-user web milestone).
    def esc(value) -> str:
        return html.escape(str(value))

    title = f"{esc(h.get('White', '?'))} vs. {esc(h.get('Black', '?'))}"
    if h.get("Event") and h["Event"] != "?":
        title += f" — {esc(h['Event'])}"
    if h.get("Date") and h["Date"] not in ("?", ""):
        title += f" ({esc(h['Date'])})"

    metadata_rows = []
    for key in ("White", "Black", "Result", "ECO", "Opening"):
        if h.get(key) and h[key] != "?":
            value = str(h[key])
            if key == "Result":
                # Show HOW it ended next to the score ("1-0 (resignation)") so a
                # non-checkmate finish is visible at a glance.
                reason = termination_reason(h, game.moves[-1].san if game.moves else "")
                if reason:
                    value = f"{value} ({reason})"
            metadata_rows.append(f"- **{key}:** {esc(value)}")
    if h.get("TimeControl") and h["TimeControl"] != "?":
        metadata_rows.append(f"- **TimeControl:** {esc(_humanize_time_control(h['TimeControl']))}")
    if h.get("WhiteElo"):
        metadata_rows.append(f"- **White ELO:** {esc(h['WhiteElo'])}")
    if h.get("BlackElo"):
        metadata_rows.append(f"- **Black ELO:** {esc(h['BlackElo'])}")

    move_list = format_move_list(game)

    return f"""# {title}

{chr(10).join(metadata_rows)}

## Moves (for reference)

```
{move_list}
```
"""


def _move_san_to_filename_part(san: str) -> str:
    """Make a SAN move filesystem-safe ('O-O+', 'Nxe6+', 'd8=Q#') → 'O-O+ would have / in it? no, but # is fine on Windows)."""
    return re.sub(r"[^A-Za-z0-9_=\-]", "_", san)


def _board_filename(move: MoveAnalysis) -> str:
    side_marker = "w" if move.side == "White" else "b"
    # ply prefix (zero-padded) guarantees natural filesystem sort order matches game order.
    return f"ply{move.ply:03d}_m{move.move_number:02d}{side_marker}_{_move_san_to_filename_part(move.san)}.svg"


def _insert_image_after_move_header(
    markdown: str, move: MoveAnalysis, image_rel_path: str
) -> str:
    """
    Find a Markdown header for `move` (e.g. `### 14. Rd1` or `### 14...Qe6`)
    and insert an image reference right after it. If no header is found,
    no change is made (the narrative grouped this move into running prose).
    """
    move_number = move.move_number
    san_escaped = re.escape(move.san)
    # `(?!\w)` not `\b`: a SAN can end in a non-word char (`+`, `#`, `=Q`), and `\b`
    # AFTER such a char fails to match — which used to drop check/mate moves like
    # "17. Nf6+", sending them down the unanchored path and misplacing their board.
    if move.side == "White":
        patterns = [
            rf"^(#{{2,4}}\s*{move_number}\.\s*{san_escaped}(?!\w).*)$",
        ]
    else:
        patterns = [
            rf"^(#{{2,4}}\s*{move_number}\.{{1,3}}\s*{san_escaped}(?!\w).*)$",
            rf"^(#{{2,4}}\s*{move_number}\.\.\.\s*{san_escaped}(?!\w).*)$",
        ]
    alt_text = (
        f"Position after {move_number}{'.' if move.side == 'White' else '...'} {move.san}"
    )
    replacement = rf"\1\n\n![{alt_text}]({image_rel_path})\n"
    for pattern in patterns:
        new_md, n = re.subn(pattern, replacement, markdown, count=1, flags=re.MULTILINE)
        if n:
            return new_md, True

    # No `### N. SAN` header exists for this move. The caller (_place_board) handles
    # that by creating a header at the move's bold mention, so a diagrammed move
    # always gets a proper section — boards are never left dangling in prose.
    return markdown, False


def _place_board(body: str, move: MoveAnalysis, image_rel_path: str) -> str:
    """Put `move`'s board diagram into the report, keeping diagrams in ply order.

    1. If the narrator gave the move its own `### N. SAN` header, insert the image
       right after it.
    2. Otherwise CREATE the header ourselves, just before the move's first bold
       mention in the prose, so the diagrammed move still gets a clean section.
    3. As a last resort, append it at the end.

    The caller iterates moves in game order, so diagrams land chronologically and
    can never clump out of order the way the old unanchored-pile approach did.
    """
    body, anchored = _insert_image_after_move_header(body, move, image_rel_path)
    if anchored:
        return body
    num = move.move_number
    dots = ". " if move.side == "White" else "..."
    header = f"### {num}{dots}{move.san}"
    alt = f"Position after {num}{'.' if move.side == 'White' else '...'} {move.san}"
    block = f"{header}\n\n![{alt}]({image_rel_path})\n\n"
    san_escaped = re.escape(move.san)
    # First bold mention of this move in the prose, e.g. **24...Kg7** or **24. e3?!**.
    bold_line = re.compile(rf"(?m)^.*\*\*[^*\n]*\b{num}\b[^*\n]*{san_escaped}[^*\n]*\*\*.*$")
    m = bold_line.search(body)
    if m:
        line_start = body.rfind("\n", 0, m.start()) + 1
        return body[:line_start] + block + body[line_start:]
    return body.rstrip("\n") + "\n\n" + block


def _collapse_duplicate_headers(md: str) -> str:
    """Collapse an immediately-repeated move header down to a single one.

    The narrator occasionally emits the same `### N. SAN` anchor header twice in a
    row — most often on the dramatic Tier-3 moves that also get a board diagram —
    which then renders as the move name appearing two or three times around the
    board. Runs of identical `##`–`####` header lines (blank lines between them are
    fine) are reduced to the first occurrence. Non-consecutive repeats and ordinary
    text are left untouched.
    """
    out: List[str] = []
    last_header: Optional[str] = None
    for line in md.split("\n"):
        stripped = line.strip()
        if re.match(r"^#{2,4}\s+\S", stripped):
            if stripped == last_header:
                continue  # drop the immediate duplicate header
            last_header = stripped
        elif stripped:
            last_header = None  # real content ends the run; blank lines keep it open
        out.append(line)
    return "\n".join(out)


def _strip_orphan_move_headers(md: str) -> str:
    """Drop any `### N. SAN` move header that has no board diagram right after it.

    A `### ` header is purely a diagram anchor. The narrator still occasionally
    headlines a dramatic *non*-diagrammed move with its own header anyway; this
    removes those, so the move just reads as bolded prose (with its chess symbol)
    and there is no header/bold duplication. Section headers (`#`, `##`) and headers
    that DO anchor a board are kept. Run after boards are placed.
    """
    lines = md.split("\n")
    keep = [True] * len(lines)
    for i, line in enumerate(lines):
        if re.match(r"^###\s+\S", line.strip()):
            if not any("![" in w for w in lines[i + 1 : i + 5]):
                keep[i] = False
                if i + 1 < len(lines) and not lines[i + 1].strip():
                    keep[i + 1] = False  # swallow one trailing blank, avoid a double gap
    return "\n".join(l for l, k in zip(lines, keep) if k)


# A SAN move token: castles, or an optional piece letter + optional disambiguation
# + optional capture + destination square + optional promotion, with an optional
# check/mate suffix. Used to police the data-back boundary on written variations.
_SAN_TOKEN_RE = re.compile(
    r"\b(?:O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?"
)


def _san_tokens(text: str) -> set:
    """Set of normalised SAN move tokens in `text` (trailing +/# stripped)."""
    return {tok.rstrip("+#") for tok in _SAN_TOKEN_RE.findall(text or "")}


# ===========================================================================
# Variation legality validator — the "legal-from-branch" reframe
# (docs/specs/VARIATION_VALIDATOR.md).
#
# OLD policy (find_unverified_variation_moves, pre-v0.42): a parenthetical was valid
# only if every SAN token appeared verbatim in some engine PV. That wrongly deleted
# legitimate instructive counterfactuals the engine never pre-analysed ("if Black had
# NOT played ...f6, White would have had Qxg7#").
#
# NEW policy: reconstruct a small ranked set of candidate BRANCH BOARDS from the per-ply
# FENs (incl. a fen_before + null-move turn-flip variant for "if X had NOT been played"),
# replay the line via board.parse_san, and ACCEPT if ANY anchoring is fully legal.
# Malformed/ambiguous SAN -> ABSTAIN; only a well-formed line with no legal anchoring
# anywhere (and not a verbatim engine line) -> FLAG. Failure action is WARN-AND-ANNOTATE,
# never strip — a legitimate instructive line always survives.
# ===========================================================================

# A move-number prefix ("25." -> White, "24..." -> Black) OR a SAN token, scanned in
# textual order so the line can be replayed move by move (a set would destroy order).
_SEQ_SCAN_RE = re.compile(
    r"(?P<num>\d+)\s*(?P<dots>\.\.\.|\.)"
    r"|(?P<san>(?:O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?)"
)
# A pawn capture: a leading file, 'x', then the destination square (no piece letter).
_PAWN_CAPTURE_RE = re.compile(r"^([a-h])x([a-h])[1-8](?:=[QRBN])?$")


@dataclass
class UnverifiedVariation:
    """One parenthetical line the validator could not bless. Detect-and-report only;
    nothing here mutates the report. The position-anchored detail (anchor ply, first
    illegal SAN, the candidate FENs tried) is what the old flat-set check could not
    produce. `verdict` is 'FLAG' (well-formed, illegal from every branch, not an engine
    line) or 'ABSTAIN' (malformed/ambiguous SAN, or an unmet mate/check annotation)."""
    paren: str                                  # the parenthetical text inspected
    verdict: str                                # 'FLAG' | 'ABSTAIN'
    first_illegal_san: Optional[str] = None     # the SAN that first proved illegal
    anchor_ply: Optional[int] = None            # the ply the line was anchored to
    candidate_fens: List[str] = field(default_factory=list)  # branch boards tried
    confidence: str = "high"                    # 'high' for a FLAG; 'low' for ABSTAIN


def _is_malformed_pawn_capture(san: str) -> bool:
    """True for a pawn capture whose source and destination files are not adjacent
    (e.g. 'exg5'): well-shaped to the token regex but geometrically impossible in ANY
    position. We route these to ABSTAIN, never to a confabulation FLAG — a typo is not
    proof the model invented a move (the documented exg5 false-positive)."""
    m = _PAWN_CAPTURE_RE.match(san.rstrip("+#"))
    return bool(m) and abs(ord(m.group(1)) - ord(m.group(2))) != 1


def _san_sequence(text: str) -> Tuple[List[Tuple[Optional[int], Optional[str], str]], bool]:
    """Parse a parenthetical into an ORDERED list of (move_number, side_hint, san) plus
    a `had_unparseable` flag.

    side_hint is 'White' after 'N.' and 'Black' after 'N...', else None — it is ADVISORY
    only (legality replay is the sole arbiter; a counterfactual legitimately inverts the
    printed side). had_unparseable is True when a SAN-shaped run cannot be legal in any
    position (a non-adjacent pawn capture) -> drives ABSTAIN, never FLAG. The +/# suffix
    is retained on the token (stripped at replay, checked post-hoc for mate/check claims).
    """
    seq: List[Tuple[Optional[int], Optional[str], str]] = []
    had_unparseable = False
    pending_num: Optional[int] = None
    pending_side: Optional[str] = None
    for m in _SEQ_SCAN_RE.finditer(text or ""):
        if m.group("num") is not None:
            pending_num = int(m.group("num"))
            pending_side = "White" if m.group("dots") == "." else "Black"
            continue
        san = m.group("san")
        if not san:
            continue
        if _is_malformed_pawn_capture(san):
            had_unparseable = True
        seq.append((pending_num, pending_side, san))
        pending_num, pending_side = None, None
    return seq, had_unparseable


def replay_variation_legal(
    sequence: List[Tuple[Optional[int], Optional[str], str]],
    candidate_boards: List["chess.Board"],
) -> Tuple[bool, Optional[str], bool, bool]:
    """Replay the SAN sequence on each candidate board (a fresh .copy() per attempt).

    Returns (legal, first_illegal_san, ambiguous, soft_fail):
      legal     — True the instant SOME candidate replays the WHOLE sequence legally.
      first_illegal_san — on total failure, the SAN that first proved illegal on the
                  candidate that got FURTHEST (most informative); None if no candidates.
      ambiguous — a candidate hit an ambiguous / malformed SAN (not flatly illegal).
      soft_fail — a candidate replayed fully, but the trailing '#'/'+' annotation held on
                  NO fully-legal candidate (claimed mate/check unmet) — a low note, not a flag.

    board.parse_san validates against board.legal_moves AND resolves disambiguation in
    that exact position. python-chess raises IllegalMoveError for a well-formed-but-illegal
    move (-> FLAG candidate) and AmbiguousMoveError / InvalidMoveError for ambiguity /
    malformed SAN (-> ABSTAIN); all are ValueError subclasses, so order matters.
    """
    if not sequence:
        return (True, None, False, False)  # an empty line replays trivially
    last_san = sequence[-1][2]
    wants_mate = last_san.endswith("#")
    wants_check = last_san.endswith("+")
    best_illegal: Optional[Tuple[int, str]] = None
    saw_ambiguous = False
    soft_fail_seen = False
    for board0 in candidate_boards:
        board = board0.copy()
        illegal_san: Optional[str] = None
        ambiguous = False
        prefix = 0
        for (_num, _side, san) in sequence:
            core = san.rstrip("+#")
            try:
                move = board.parse_san(core)
            except chess.IllegalMoveError:
                illegal_san = core       # well-formed SAN, no legal move -> confab/illegal
                break
            except (chess.AmbiguousMoveError, chess.InvalidMoveError):
                ambiguous = True         # underspecified or malformed -> ABSTAIN
                illegal_san = core
                break
            except ValueError:
                illegal_san = core       # any other parse failure -> treat as illegal
                break
            board.push(move)
            prefix += 1
        else:
            # whole sequence replayed legally on this candidate
            ok = True
            if wants_mate and not board.is_checkmate():
                ok = False
            elif wants_check and not board.is_check():
                ok = False
            if ok:
                return (True, None, False, False)
            soft_fail_seen = True
            continue
        if ambiguous:
            saw_ambiguous = True
        if best_illegal is None or prefix > best_illegal[0]:
            best_illegal = (prefix, illegal_san)
    if soft_fail_seen:
        return (True, None, False, True)
    if best_illegal is not None:
        return (False, best_illegal[1], saw_ambiguous, False)
    return (False, None, saw_ambiguous, False)


def _board_or_none(fen: str):
    """A chess.Board from `fen`, or None if the FEN is unusable (e.g. the dummy FENs
    tests sometimes pass). Used so a bad FEN never raises mid-validation."""
    if not fen:
        return None
    try:
        return chess.Board(fen)
    except (ValueError, IndexError):
        return None


def _index_of_ply(game, ply: int) -> Optional[int]:
    for i, m in enumerate(game.moves):
        if m.ply == ply:
            return i
    return None


def _anchor_index_from_number(game, number: int, side: Optional[str]) -> Optional[int]:
    """Index of the game move with this move-number (and side, if given). Mirrors the
    match bind_span_to_ply does, MINUS the SAN-equality requirement — a variation's
    first move is not the played move."""
    for i, m in enumerate(game.moves):
        if m.move_number == number and (side is None or m.side == side):
            return i
    return None


def _anchor_candidate_boards(game, idx: Optional[int], hypothetical: bool) -> List["chess.Board"]:
    """Boards C1-C4 around anchor index `idx` (deduped by FEN), plus a counterfactual
    turn-flip variant of C2 when the line is hypothetical (spec §3b/§3c):

      C1 fen_after(p)            continuation ("25. g5 ..."), branches AFTER the move
      C2 fen_before(p)           "instead of" / "if X had NOT been played", branches BEFORE
      C3 fen_before(p+1)         numbering off-by-one one way
      C4 fen_after(p-1)          numbering off-by-one the other way
      turn-flip  null move on C2 the side that would have played X passes -> opponent to move
                                 (this is what makes "if Black had NOT played ...f6, Qxg7#" replay)
    """
    boards: List[chess.Board] = []
    seen: set = set()

    def add(board) -> None:
        if board is None:
            return
        key = board.fen()
        if key in seen:
            return
        seen.add(key)
        boards.append(board)

    if idx is None:
        return boards
    mv = game.moves[idx]
    add(_board_or_none(mv.fen_after))    # C1
    add(_board_or_none(mv.fen_before))   # C2
    if idx + 1 < len(game.moves):
        add(_board_or_none(game.moves[idx + 1].fen_before))  # C3
    if idx - 1 >= 0:
        add(_board_or_none(game.moves[idx - 1].fen_after))   # C4
    if hypothetical:
        probe = _board_or_none(mv.fen_before)
        if probe is not None and not probe.is_check():   # a null move is illegal in check
            probe.push(chess.Move.null())
            add(probe)
    return boards


def _all_plies_candidate_boards(game) -> List["chess.Board"]:
    """Every per-ply fen_before/fen_after as a branch board (deduped). The last-resort
    sweep — only ever consulted to GRANT validity (find some legal anchoring), never to
    deny it; a confab line legal from an unrelated position is harmlessly accepted under
    warn-don't-strip (spec §6 asymmetry)."""
    boards: List[chess.Board] = []
    seen: set = set()
    for m in game.moves:
        for fen in (m.fen_before, m.fen_after):
            b = _board_or_none(fen)
            if b is None:
                continue
            key = b.fen()
            if key in seen:
                continue
            seen.add(key)
            boards.append(b)
    return boards


def _engine_pv_token_lists(game) -> List[List[str]]:
    """Each engine line (best / refutation / alternative) as an ordered SAN-token list,
    for the demoted provenance fallback."""
    lists: List[List[str]] = []
    for m in game.moves:
        candidates = [getattr(m, "best_line_san", "") or "",
                      getattr(m, "refutation_line_san", "") or ""]
        for alt in (m.top_alternatives or []):
            candidates.append(alt.get("pv_numbered", "") or alt.get("pv_san", "") or "")
        for line in candidates:
            seq, _ = _san_sequence(line)
            sans = [s.rstrip("+#") for (_n, _s, s) in seq]
            if sans:
                lists.append(sans)
    return lists


def _line_is_engine_pv(seq, pv_lists) -> bool:
    """True if the line's SAN tokens appear as a verbatim CONTIGUOUS subsequence of some
    engine PV — the demoted provenance signal (strongest trust). Deliberately stricter
    than the old flat per-token pooling, so an illegal SEQUENCE recombined from
    individually-real tokens is NOT rescued here."""
    target = [s.rstrip("+#") for (_n, _s, s) in seq]
    if not target:
        return False
    n = len(target)
    for pv in pv_lists:
        for i in range(len(pv) - n + 1):
            if pv[i:i + n] == target:
                return True
    return False


def _resolve_anchor_index(seq, sentence, game, fact_packets) -> Optional[int]:
    """Find the game-move index the parenthetical branches from (spec §3a): primary =
    the first (number, side) inside the paren; fallback = bind the enclosing sentence to
    a ply via its BOLD game-move reference (the counterfactual case, where the paren
    itself carries no move number)."""
    first_num, first_side = None, None
    for (num, side, _san) in seq:
        if num is not None:
            first_num, first_side = num, side
            break
    if first_num is not None:
        idx = _anchor_index_from_number(game, first_num, first_side)
        if idx is None and first_side is not None:
            idx = _anchor_index_from_number(game, first_num, None)  # try either side
        if idx is not None:
            return idx
    from factcheck import bind_span_to_ply  # lazy: avoid a load-time import cycle
    pk = bind_span_to_ply(sentence, fact_packets)
    if pk is not None and pk.get("ply") is not None:
        j = _index_of_ply(game, pk["ply"])
        if j is not None:
            return j
    return None


def validate_parenthetical_variations(
    report_md: str, game: GameAnalysis, fact_packets: Optional[List[dict]] = None
) -> List["UnverifiedVariation"]:
    """Legality-replay validator for written parenthetical variations (the reframe).

    Returns a record for each line that FLAGs (well-formed, illegal from every candidate
    branch board, not a verbatim engine line) or ABSTAINs (malformed/ambiguous SAN, or an
    unmet mate/check annotation). A VALID line — including a legal counterfactual the
    engine never pre-analysed — produces NO record. Never mutates the report.

    fact_packets (optional) feed the sentence->ply binding fallback; built minimally from
    `game` when omitted (only move_no/side/played/ply are read, so no tiers are needed).
    See docs/specs/VARIATION_VALIDATOR.md.
    """
    if not report_md or not getattr(game, "moves", None):
        return []
    # Lazy import: factcheck imports outputs lazily too, so module-level would cycle.
    from factcheck import split_sentences, _HYPOTHETICAL_RE

    if fact_packets is None:
        fact_packets = [
            {"ply": m.ply, "move_no": m.move_number, "side": m.side, "played": m.san}
            for m in game.moves
        ]

    pv_lists = _engine_pv_token_lists(game)
    all_plies: Optional[List["chess.Board"]] = None  # built lazily — the expensive path
    results: List[UnverifiedVariation] = []
    seen_parens: set = set()

    for sentence in split_sentences(report_md):
        for pm in re.finditer(r"\(([^)]*)\)", sentence):
            paren = pm.group(1)
            if paren in seen_parens:
                continue
            seq, had_unparseable = _san_sequence(paren)
            if not seq:
                continue
            hypothetical = bool(_HYPOTHETICAL_RE.search(sentence))
            has_move_notation = bool(_VARIATION_INTRO_RE.search(paren))
            # Inspect a paren only if it is move-bearing notation, OR its enclosing
            # sentence is hypothetical (the numberless-counterfactual case, where the
            # grammatical setup "if X had not played ..." lives in the prose).
            if not (has_move_notation or hypothetical):
                continue
            seen_parens.add(paren)

            idx = _resolve_anchor_index(seq, sentence, game, fact_packets)
            anchor_ply = game.moves[idx].ply if idx is not None else None
            cands = _anchor_candidate_boards(game, idx, hypothetical)
            legal, first_illegal, ambiguous, soft_fail = replay_variation_legal(seq, cands)

            if not legal:
                if all_plies is None:
                    all_plies = _all_plies_candidate_boards(game)
                s_legal, s_illegal, s_amb, s_soft = replay_variation_legal(seq, all_plies)
                if s_legal:
                    legal, first_illegal, ambiguous, soft_fail = True, None, s_amb, s_soft
                else:
                    ambiguous = ambiguous or s_amb
                    if first_illegal is None:
                        first_illegal = s_illegal

            cand_fens = [b.fen() for b in cands]

            if legal:
                if soft_fail:  # legal but the claimed mate/check held on no candidate
                    results.append(UnverifiedVariation(
                        paren=paren, verdict="ABSTAIN", confidence="low",
                        anchor_ply=anchor_ply, first_illegal_san=None,
                        candidate_fens=cand_fens))
                continue  # VALID — the counterfactual / sideline survives

            if _line_is_engine_pv(seq, pv_lists):
                continue  # VALID via provenance (verbatim engine line)
            if had_unparseable or ambiguous:
                results.append(UnverifiedVariation(
                    paren=paren, verdict="ABSTAIN", confidence="low",
                    anchor_ply=anchor_ply, first_illegal_san=first_illegal,
                    candidate_fens=cand_fens))
                continue
            if not cands and not all_plies:
                continue  # no usable branch board anywhere -> can't prove illegality
            results.append(UnverifiedVariation(
                paren=paren, verdict="FLAG", confidence="high",
                anchor_ply=anchor_ply, first_illegal_san=first_illegal,
                candidate_fens=cand_fens))
    return results


def find_unverified_variation_moves(report_md: str, game: GameAnalysis) -> List[str]:
    """Back-compat shim over `validate_parenthetical_variations`: the first illegal SAN
    of each FLAGGED line — a well-formed move illegal from every candidate branch board
    AND absent from the engine's lines.

    BREAKING CHANGE (v0.42 reframe): the meaning moved from 'engine-absent' to
    'illegal-from-branch'. A legal counterfactual the engine never pre-analysed is no
    longer returned — only genuine confabulation/illegality is. ABSTAIN lines (malformed
    SAN) are NOT returned. See docs/specs/VARIATION_VALIDATOR.md.
    """
    return [
        v.first_illegal_san
        for v in validate_parenthetical_variations(report_md, game)
        if v.verdict == "FLAG" and v.first_illegal_san
    ]


_VARIATION_INTRO_RE = re.compile(r"\d+\.(?:\.\.)?\s*[OKQRBNa-h]")


def strip_unverified_variations(report_md: str, game: GameAnalysis) -> str:
    """Remove parenthetical variation spans whose moves are not all in the engine lines.

    DISABLED BY DEFAULT (v0.42 reframe): this implements the OLD engine-membership
    policy and is NO LONGER called by the pipeline. `assemble_report` now WARNS and never
    strips, because deleting on a heuristic risks removing a legitimate instructive
    counterfactual — the exact harm the reframe forbids (docs/specs/VARIATION_VALIDATOR.md
    §6). Kept only so its behaviour stays test-covered. If stripping is ever re-enabled it
    must be gated to category-2 lines only (well-formed, illegal from every branch, not an
    engine line) — never to a line that was merely engine-absent. Do not re-wire as-is.
    """
    if not report_md:
        return report_md

    # Build the complete allowed-move set (same logic as find_unverified…).
    allowed: set = set()
    for m in game.moves:
        allowed |= _san_tokens(m.san)
        allowed |= _san_tokens(getattr(m, "best_line_san", "") or "")
        allowed |= _san_tokens(getattr(m, "refutation_line_san", "") or "")
        for alt in (m.top_alternatives or []):
            allowed |= _san_tokens(alt.get("pv_numbered", "") or alt.get("pv_san", ""))

    def _should_strip(paren_content: str) -> bool:
        if not _VARIATION_INTRO_RE.search(paren_content):
            return False  # not variation notation — leave it alone
        for tok in _san_tokens(paren_content):
            if tok not in allowed:
                return True
        return False

    return re.sub(
        r"\(([^)]*)\)",
        lambda m: "" if _should_strip(m.group(1)) else m.group(0),
        report_md,
    )


def assemble_report(
    game: GameAnalysis,
    tiers: List[int],
    narrative: str,
    output_md: Path,
    boards_at: str = "tier3",
    render_eval_graph: bool = True,
    flipped_for_black: bool = False,
    periodic_every: int = 6,
) -> Path:
    """
    Write the assembled Markdown report and any side-car images to disk.
    Returns the path of the written .md file.

    Side files go next to the .md:
      <stem>_assets/
        eval.png
        boards/move_NNN.svg
    """
    output_md = Path(output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    assets_dir = output_md.parent / f"{output_md.stem}_assets"
    boards_dir = assets_dir / "boards"

    header = build_header(game)
    body = narrative.lstrip()
    # Safety net: strip any top-level `# Title` Claude added despite the system prompt.
    body = re.sub(r"^#\s+[^\n]+\n+", "", body, count=1)
    # Safety net: collapse any move header the model emitted twice in a row, before
    # boards are anchored to those headers.
    body = _collapse_duplicate_headers(body)

    # Eval graph.
    eval_section = ""
    if render_eval_graph:
        eval_path = assets_dir / "eval.png"
        try:
            render_eval_graph_png(game, eval_path)
            rel = eval_path.relative_to(output_md.parent).as_posix()
            eval_section = f"\n## Evaluation across the game\n\n![Engine evaluation chart]({rel})\n"
        except Exception as exc:
            eval_section = f"\n> (Eval graph could not be rendered: {exc})\n"

    # Which moves get a board (= which get a `### N. SAN` header). The narrator was
    # told this exact set via select_diagram_plies, so each board anchors to its own
    # header. We iterate in GAME ORDER and _place_board inserts each diagram at its
    # move's spot (creating the header if the narrator didn't) — so diagrams stay in
    # chronological order and never clump.
    render_plies = select_diagram_plies(game, tiers, boards_at, periodic_every)
    for move in game.moves:
        if move.ply not in render_plies:
            continue
        board_path = boards_dir / _board_filename(move)
        try:
            save_board_svg(
                move.fen_after,
                board_path,
                last_move_uci=move.uci,
                flipped=flipped_for_black,
            )
        except Exception:
            continue
        rel = board_path.relative_to(output_md.parent).as_posix()
        body = _place_board(body, move, rel)

    # Headers anchor diagrams only: drop any the narrator put on a non-diagrammed
    # move so there's no header/bold duplication for dramatic-but-undiagrammed moves.
    body = _strip_orphan_move_headers(body)

    # Data-back trust boundary (legality reframe): WARN about any parenthetical line with
    # no legal anchoring in this game, but NEVER mutate `body`. The old engine-membership
    # strip wrongly deleted legitimate instructive counterfactuals the engine had not
    # pre-analysed; under the reframe a line is valid if it replays legally from a
    # plausible branch board, and the failure action is warn-and-annotate, never strip
    # (docs/specs/VARIATION_VALIDATOR.md §6).
    try:
        flagged = [v for v in validate_parenthetical_variations(body, game)
                   if v.verdict == "FLAG"]
        if flagged:
            import sys
            for v in flagged[:12]:
                print(
                    f"  [variation check] illegal-from-branch: {v.first_illegal_san!r} "
                    f"(anchor ply {v.anchor_ply}) in ({v.paren[:70]})",
                    file=sys.stderr,
                )
    except Exception:
        pass

    assembled = f"{header}\n{eval_section}\n---\n\n{body}\n"
    output_md.write_text(assembled, encoding="utf-8")
    return output_md


def _inline_image_assets(html_body: str, base_dir: Path) -> str:
    """
    Replace every <img src="..."> in the HTML with self-contained content so the
    file needs no external assets and no links to open:
      - SVG files are inlined directly as <svg> elements (wrapped in <figure>).
      - Raster files (PNG/JPG) become base64 data URIs.
    Paths are resolved relative to `base_dir` (the report's folder).
    """
    img_re = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*?>', re.IGNORECASE)

    def _alt_of(tag: str) -> str:
        m = re.search(r'alt="([^"]*)"', tag)
        return m.group(1) if m else ""

    def _replace(match: "re.Match[str]") -> str:
        tag = match.group(0)
        src = unquote(match.group(1))
        alt = _alt_of(tag)

        # Leave already-embedded data URIs and remote URLs untouched.
        if src.startswith(("data:", "http://", "https://")):
            return tag

        asset_path = (base_dir / src).resolve()
        if not asset_path.exists():
            return tag  # nothing to inline; leave the original tag

        suffix = asset_path.suffix.lower()
        if suffix == ".svg":
            svg = asset_path.read_text(encoding="utf-8")
            # Strip XML prolog / DOCTYPE so it embeds cleanly inside HTML.
            svg = re.sub(r"<\?xml.*?\?>", "", svg, flags=re.DOTALL)
            svg = re.sub(r"<!DOCTYPE.*?>", "", svg, flags=re.DOTALL)
            svg = svg.strip()
            caption = f"<figcaption>{alt}</figcaption>" if alt else ""
            # data-ply encodes the move's half-move index so tools/CSS can verify
            # or re-sort board figures by game order.
            ply_m = re.search(r"ply(\d+)_", asset_path.name)
            ply_attr = f' data-ply="{int(ply_m.group(1))}"' if ply_m else ""
            return f'<figure class="board"{ply_attr}>{svg}{caption}</figure>'

        # Raster image -> base64 data URI.
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
        }.get(suffix, "application/octet-stream")
        data = base64.b64encode(asset_path.read_bytes()).decode("ascii")
        caption = f"<figcaption>{alt}</figcaption>" if alt else ""
        return f'<figure><img alt="{alt}" src="data:{mime};base64,{data}">{caption}</figure>'

    return img_re.sub(_replace, html_body)


# --------------------------------------------------------------------------
# Interactive PGN viewer (click-through replay board)
# --------------------------------------------------------------------------
# The replay board is rendered client-side from a small per-ply data array
# (FENs are precomputed by the analyzer, so no chess logic is needed in JS).
# The 12 piece graphics are reused from python-chess's own SVG set so the
# replay board is visually identical to the inline static boards. Everything
# is inlined — the HTML stays self-contained (no CDN, works offline/emailed).

def _piece_defs_inline() -> str:
    """Return a <defs> block (no outer SVG wrapper) holding the 12 piece
    symbols.  Intended to be embedded directly inside <svg id="gv-board"> so
    that <use href="#gv-P"> elements injected via innerHTML always reference an
    id in the *same* SVG — cross-SVG innerHTML references don't resolve in
    Firefox."""
    import chess.svg  # lazy: only needed when a viewer is built

    parts = []
    for key, group in chess.svg.PIECES.items():
        inner = re.sub(r'id="(white|black)-', r'id="gvp-\1-', group)
        parts.append(f'<g id="gv-{key}">{inner}</g>')
    return f'<defs>{"".join(parts)}</defs>'


def _viewer_eval_text(cp: Optional[int], mate: Optional[int]) -> str:
    """Compact, White-positive eval badge (lichess style): '+1.24', '-0.50',
    'M5' (White mates), '-M3' (Black mates), '' at checkmate."""
    if mate is not None:
        if mate == 0:
            return ""
        return f"M{mate}" if mate > 0 else f"-M{abs(mate)}"
    if cp is None:
        return "0.00"
    pawns = cp / 100.0
    return f"+{pawns:.2f}" if pawns >= 0 else f"{pawns:.2f}"


_VIEWER_JS = r"""
(function(){
  var el = document.getElementById('greco-viewer-data');
  if(!el) return;
  var DATA = JSON.parse(el.textContent);
  var PLIES = DATA.plies, flip = !!DATA.flip, idx = 0;
  var M = 18, SZ = 45, BOARD = SZ * 8;
  var LIGHT = '#ffce9e', DARK = '#d18b47', HL = '#cdd16a';
  var boardSvg = document.getElementById('gv-board');
  var statusEl = document.getElementById('gv-status');
  var movesEl  = document.getElementById('gv-moves');
  var varsEl   = document.getElementById('gv-vars');

  /* --- Move sounds (lichess/chess.com-style feedback), synthesized via WebAudio
     so the HTML stays self-contained — no audio assets to ship or inline. The
     AudioContext is created lazily inside a user-gesture handler (click/keydown),
     which satisfies browser autoplay policies. Mute preference persists. --- */
  var audioCtx = null;
  var muted = false;
  try{ muted = localStorage.getItem('greco_viewer_muted') === '1'; }catch(e){}
  function beep(freq, dur, wave, vol){
    if(muted) return;
    try{
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      if(audioCtx.state === 'suspended') audioCtx.resume();
      var o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.type = wave || 'sine'; o.frequency.value = freq;
      g.gain.setValueAtTime(vol || 0.1, audioCtx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + dur);
      o.connect(g); g.connect(audioCtx.destination);
      o.start(); o.stop(audioCtx.currentTime + dur);
    }catch(e){}
  }
  function moveSound(pl){
    if(!pl){ beep(240, .05, 'sine', .05); return; }  /* back to the start position */
    var san = pl.san || '';
    if(san.indexOf('#') !== -1){ beep(660, .16, 'sine', .12); beep(880, .3, 'sine', .1); }
    else if(san.indexOf('+') !== -1){ beep(760, .12, 'triangle', .1); }
    else if(san.indexOf('x') !== -1){ beep(320, .09, 'square', .08); }
    else { beep(520, .06, 'sine', .09); }
  }

  function sqXY(file, rank){
    var col  = flip ? 7 - file : file;
    var srow = flip ? rank : 7 - rank;
    return [M + col * SZ, 2 + srow * SZ];
  }
  function parsePlacement(fen){
    var rows = fen.split(' ')[0].split('/'), pcs = [];
    for(var ri = 0; ri < 8; ri++){
      var rank = 7 - ri, file = 0, row = rows[ri] || '';
      for(var ci = 0; ci < row.length; ci++){
        var c = row[ci];
        if(c >= '1' && c <= '8'){ file += parseInt(c, 10); }
        else { pcs.push({ch: c, file: file, rank: rank}); file++; }
      }
    }
    return pcs;
  }
  function renderBoard(fen, uci){
    var defs = boardSvg.querySelector('defs');
    var p = [];
    for(var f = 0; f < 8; f++){
      for(var r = 0; r < 8; r++){
        var xy = sqXY(f, r), light = ((f + r) % 2) === 1;
        p.push('<rect x="'+xy[0]+'" y="'+xy[1]+'" width="'+SZ+'" height="'+SZ+'" fill="'+(light?LIGHT:DARK)+'"/>');
      }
    }
    if(uci && uci.length >= 4){
      var sqs = [uci.slice(0,2), uci.slice(2,4)];
      for(var s = 0; s < sqs.length; s++){
        var ff = sqs[s].charCodeAt(0) - 97, rr = parseInt(sqs[s][1], 10) - 1;
        if(ff >= 0 && ff < 8 && rr >= 0 && rr < 8){
          var h = sqXY(ff, rr);
          p.push('<rect x="'+h[0]+'" y="'+h[1]+'" width="'+SZ+'" height="'+SZ+'" fill="'+HL+'"/>');
        }
      }
    }
    var pcs = parsePlacement(fen);
    for(var i = 0; i < pcs.length; i++){
      var xy2 = sqXY(pcs[i].file, pcs[i].rank), ref = '#gv-' + pcs[i].ch;
      p.push('<use href="'+ref+'" xlink:href="'+ref+'" x="'+xy2[0]+'" y="'+xy2[1]+'"/>');
    }
    var files = 'abcdefgh', ranks = '12345678';
    for(var k = 0; k < 8; k++){
      var fc = flip ? files[7-k] : files[k];
      p.push('<text class="gv-coord" x="'+(M + k*SZ + SZ/2)+'" y="'+(2 + BOARD + 13)+'" text-anchor="middle">'+fc+'</text>');
      var rc = flip ? ranks[k] : ranks[7-k];
      p.push('<text class="gv-coord" x="9" y="'+(2 + k*SZ + SZ/2 + 4)+'" text-anchor="middle">'+rc+'</text>');
    }
    boardSvg.innerHTML = p.join('');
    if(defs) boardSvg.insertBefore(defs, boardSvg.firstChild);
  }

  function moveLabel(pl){ return pl.n + (pl.s === 'W' ? '.' : '…') + ' ' + pl.san; }
  function badge(pl){
    if(pl.br) return '<span class="gv-badge gv-brilliant">Brilliant !!</span>';
    if(pl.cls === 'blunder')    return '<span class="gv-badge gv-blunder">Blunder ??</span>';
    if(pl.cls === 'mistake')    return '<span class="gv-badge gv-mistake">Mistake ?</span>';
    if(pl.cls === 'inaccuracy') return '<span class="gv-badge gv-inaccuracy">Inaccuracy ?!</span>';
    return '';
  }
  function updateStatus(){
    var pl = PLIES[idx];
    if(idx === 0){ statusEl.innerHTML = '<span class="gv-movelabel">Start position</span>'; return; }
    var ev = pl.ev ? '<span class="gv-eval">'+pl.ev+'</span>' : '';
    var fin = '';
    if(idx === PLIES.length - 1 && DATA.result && DATA.result !== '*'){
      fin = ' <span class="gv-badge gv-result-badge">'+DATA.result+(DATA.term ? ' · '+DATA.term : '')+'</span>';
    }
    statusEl.innerHTML = '<span class="gv-movelabel">'+moveLabel(pl)+'</span> '+ev+' '+badge(pl)+fin;
  }
  function buildMoves(){
    var html = '';
    for(var i = 1; i < PLIES.length; i++){
      var pl = PLIES[i], cls = 'gv-move';
      if(pl.s === 'W') html += '<span class="gv-num">'+pl.n+'.</span>';
      if(pl.br) cls += ' gv-mv-brilliant';
      else if(pl.cls === 'blunder')    cls += ' gv-mv-blunder';
      else if(pl.cls === 'mistake')    cls += ' gv-mv-mistake';
      else if(pl.cls === 'inaccuracy') cls += ' gv-mv-inaccuracy';
      html += '<span class="'+cls+'" data-idx="'+i+'">'+pl.san+'</span> ';
    }
    /* Result marker: make a non-checkmate ending visible right in the move
       order — '1-0 · resignation' — the way printed game scores do. */
    if(DATA.result && DATA.result !== '*'){
      html += '<span class="gv-result" title="How the game ended">'+DATA.result+(DATA.term ? ' · '+DATA.term : '')+'</span>';
    }
    movesEl.innerHTML = html;
    movesEl.addEventListener('click', function(e){
      var t = e.target.closest ? e.target.closest('.gv-move') : null;
      if(t) go(parseInt(t.getAttribute('data-idx'), 10));
    });
  }
  function highlightMove(){
    var prev = movesEl.querySelector('.gv-move.active');
    if(prev) prev.classList.remove('active');
    if(idx > 0){
      var cur = movesEl.querySelector('.gv-move[data-idx="'+idx+'"]');
      if(cur){ cur.classList.add('active'); cur.scrollIntoView({block: 'nearest'}); }
    }
  }
  /* --- Variation stepping: clicking a move in an engine line focuses that line;
     arrow keys then walk ITS plies instead of the game's. Stepping left past the
     line's first move (or pressing Esc) returns to the game position. --- */
  var varMode = null;  /* {v: variation row index, p: ply index within it} */
  function currentVars(){ var pl = PLIES[idx]; return (pl && pl.vars) ? pl.vars : []; }
  function markVarActive(){
    var prev = varsEl.querySelector('.gv-var-peek');
    if(prev) prev.classList.remove('gv-var-peek');
    if(varMode){
      var sel = varsEl.querySelector('.gv-var-move[data-v="'+varMode.v+'"][data-p="'+varMode.p+'"]');
      if(sel) sel.classList.add('gv-var-peek');
    }
  }
  function enterVar(v, p){
    var vars = currentVars();
    if(!vars[v] || !vars[v].plies || !vars[v].plies[p]) return;
    varMode = {v: v, p: p};
    var vp = vars[v].plies[p];
    renderBoard(vp.fen, vp.uci);
    moveSound(vp);
    markVarActive();
  }
  function exitVar(){
    varMode = null;
    var pl = PLIES[idx];
    renderBoard(pl.fen, pl.uci);
    markVarActive();
  }
  function showVars(i){
    if(!varsEl) return;
    varsEl.innerHTML = '';
    varMode = null;
    var pl = PLIES[i];
    if(!pl || !pl.vars || !pl.vars.length) return;
    for(var v = 0; v < pl.vars.length; v++){
      var vr = pl.vars[v];
      if(!vr.plies || !vr.plies.length) continue;
      var row = document.createElement('div');
      row.className = 'gv-vars-row';
      var lbl = document.createElement('span');
      lbl.className = 'gv-vars-label';
      lbl.textContent = vr.tp === 'best' ? 'Better:' : 'Then:';
      row.appendChild(lbl);
      /* Parenthetical notation, like an annotated game score: (15. dxc6 Bxc6 16. Nbd4) */
      row.appendChild(document.createTextNode(' ('));
      for(var p = 0; p < vr.plies.length; p++){
        (function(v2, p2, vp){
          var sp = document.createElement('span');
          sp.className = 'gv-var-move';
          sp.textContent = (vp.lbl || '') + vp.san;
          sp.setAttribute('data-v', v2);
          sp.setAttribute('data-p', p2);
          sp.title = 'Step into this line — ←/→ walk it, Esc returns to the game';
          sp.addEventListener('click', function(){ enterVar(v2, p2); });
          row.appendChild(sp);
        })(v, p, vr.plies[p]);
      }
      row.appendChild(document.createTextNode(')'));
      varsEl.appendChild(row);
    }
  }
  function go(i){
    var prev = idx;
    idx = Math.max(0, Math.min(PLIES.length - 1, i));
    var pl = PLIES[idx];
    renderBoard(pl.fen, pl.uci);
    updateStatus();
    highlightMove();
    showVars(idx);
    if(idx !== prev){ moveSound(idx > 0 ? PLIES[idx] : null); }
  }
  document.getElementById('gv-start').onclick = function(){ go(0); };
  document.getElementById('gv-prev').onclick  = function(){ go(idx - 1); };
  document.getElementById('gv-next').onclick  = function(){ go(idx + 1); };
  document.getElementById('gv-end').onclick   = function(){ go(PLIES.length - 1); };
  document.getElementById('gv-flip').onclick  = function(){ flip = !flip; renderBoard(PLIES[idx].fen, PLIES[idx].uci); };
  var sndBtn = document.getElementById('gv-sound');
  function syncSoundBtn(){ if(sndBtn) sndBtn.textContent = muted ? '🔇' : '🔊'; }
  if(sndBtn){
    sndBtn.onclick = function(){
      muted = !muted;
      try{ localStorage.setItem('greco_viewer_muted', muted ? '1' : '0'); }catch(e){}
      syncSoundBtn();
      if(!muted) beep(520, .06, 'sine', .09);  /* audible confirmation */
    };
    syncSoundBtn();
  }
  document.addEventListener('keydown', function(e){
    if(/^(INPUT|TEXTAREA|SELECT)$/.test(e.target && e.target.tagName || '')) return;
    if(e.key === 'ArrowLeft'){
      if(varMode){ if(varMode.p > 0){ enterVar(varMode.v, varMode.p - 1); } else { exitVar(); } }
      else { go(idx - 1); }
      e.preventDefault();
    }
    else if(e.key === 'ArrowRight'){
      if(varMode){
        var vr = currentVars()[varMode.v];
        if(vr){ enterVar(varMode.v, Math.min(varMode.p + 1, vr.plies.length - 1)); }
      }
      else { go(idx + 1); }
      e.preventDefault();
    }
    else if(e.key === 'Escape'){ if(varMode){ exitVar(); e.preventDefault(); } }
    else if(e.key === 'Home'){ go(0); }
    else if(e.key === 'End'){ go(PLIES.length - 1); }
  });
  buildMoves();
  go(0);
})();
"""


_READ_ALOUD_SNIPPET = """<style>
#ra-btn{position:fixed;bottom:24px;right:24px;background:#C9A23A;color:#5E151D;
  border:none;border-radius:8px;padding:10px 16px;font-size:.88rem;font-weight:700;
  font-family:inherit;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.28);
  z-index:9999;transition:background .2s;}
#ra-btn:hover{background:#d9b658;}
.ra-hl{background:rgba(201,162,58,.18);border-radius:3px;transition:background .4s;}
</style>
<script>(function(){
  if(!window.speechSynthesis)return;
  var btn=document.createElement('button');
  btn.id='ra-btn';btn.textContent='♪ Read aloud';
  document.body.appendChild(btn);
  var speaking=false,paras=[],idx=0,cur=null;
  function hl(el){if(cur)cur.classList.remove('ra-hl');cur=el;if(el){el.classList.add('ra-hl');el.scrollIntoView({behavior:'smooth',block:'nearest'});}}
  function readNext(){
    if(!speaking||idx>=paras.length){stop();return;}
    var p=paras[idx++];hl(p);
    var u=new SpeechSynthesisUtterance(p.textContent);
    u.onend=u.onerror=function(){if(speaking)readNext();};
    speechSynthesis.speak(u);
  }
  function start(){
    speaking=true;idx=0;
    paras=Array.from(document.querySelectorAll('p')).filter(function(p){
      return p.textContent.trim().length>30&&!p.closest('.gv-wrap');
    });
    btn.textContent='■ Stop';readNext();
  }
  function stop(){speaking=false;speechSynthesis.cancel();hl(null);btn.textContent='♪ Read aloud';}
  btn.addEventListener('click',function(){speaking?stop():start();});
})();</script>"""

_VIEWER_CSS = """
    .greco-viewer { margin: 1.5rem 0 2rem; }
    .greco-viewer h2 { margin-bottom: 0.6rem; }
    .gv-wrap { display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-start; }
    .gv-board-col { flex: 0 0 auto; }
    .gv-board { width: 360px; max-width: 92vw; height: auto; display: block;
                border: 1px solid #cbb89a; border-radius: 4px; }
    .gv-coord { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 11px; fill: #6b5942; }
    .gv-controls { display: flex; gap: 0.3rem; margin: 0.5rem 0; flex-wrap: wrap; }
    .gv-controls button { font-size: 1rem; line-height: 1; padding: 0.35rem 0.6rem; cursor: pointer;
        border: 1px solid #c9b78f; border-radius: 4px; background: #f3e9cf; color: #5E151D; }
    .gv-controls button:hover { background: #e8dcb8; }
    .gv-status { min-height: 1.7em; font-family: 'Helvetica Neue', Arial, sans-serif; }
    .gv-movelabel { font-weight: 600; }
    .gv-eval { font-family: 'Consolas','Menlo',monospace; background: #f3e9cf; color: #7A1C26;
        padding: 0.05rem 0.35rem; border-radius: 3px; margin-left: 0.3rem; }
    .gv-badge { font-size: 0.78rem; padding: 0.05rem 0.4rem; border-radius: 3px; margin-left: 0.3rem; color: #fff; }
    .gv-brilliant { background: #1abc9c; } .gv-blunder { background: #c0392b; }
    .gv-mistake { background: #e67e22; } .gv-inaccuracy { background: #c9a227; }
    .gv-moves { flex: 1 1 240px; min-width: 220px; max-height: 372px; overflow-y: auto;
        font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.95; padding: 0.3rem 0.5rem;
        border: 1px solid #e3d2a6; border-radius: 4px; background: #fbf6e7; }
    .gv-num { color: #999; margin-right: 0.15rem; }
    .gv-move { cursor: pointer; padding: 0.02rem 0.2rem; border-radius: 3px; }
    .gv-move:hover { background: #efe6c8; }
    .gv-move.active { background: #7A1C26; color: #fff; }
    .gv-mv-blunder { color: #c0392b; } .gv-mv-mistake { color: #e67e22; }
    .gv-mv-inaccuracy { color: #b8901f; } .gv-mv-brilliant { color: #129e83; font-weight: 600; }
    .gv-move.active.gv-mv-blunder, .gv-move.active.gv-mv-mistake,
    .gv-move.active.gv-mv-inaccuracy, .gv-move.active.gv-mv-brilliant { color: #fff; }
    .gv-hint { font-size: 0.82rem; color: #777; margin-top: 0.4rem; }
    .gv-vars { min-height: 0; margin-top: 0.45rem; line-height: 1.55; }
    .gv-vars-row { margin: 0.1rem 0; font-family: 'Helvetica Neue', Arial, sans-serif; }
    .gv-vars-label { font-size: 0.78rem; color: #8a7a5c; font-style: italic; margin-right: 0.25rem; }
    .gv-var-move { display: inline-block; padding: 1px 5px; margin: 1px 2px;
        border-radius: 3px; background: #f3e9cf; border: 1px solid #d9c7a0;
        cursor: pointer; color: #5E151D; font-size: 0.85rem;
        font-family: 'Helvetica Neue', Arial, sans-serif; }
    .gv-var-move:hover { background: #e8dcb8; }
    .gv-var-peek { background: #cdd16a !important; border-color: #b8bc4a !important; }
    .gv-result { display: inline-block; margin-left: 0.3rem; padding: 0.02rem 0.45rem;
        border-radius: 3px; background: #efe6c8; border: 1px solid #d9c7a0;
        color: #5E151D; font-weight: 600; white-space: nowrap; }
    .gv-result-badge { background: #7A1C26; }
    @media print { .gv-controls, .gv-hint, .gv-vars { display: none; } .gv-moves { max-height: none; } }
"""


def _pv_to_fen_plies(fen_start: str, pv_san_numbered: str) -> list:
    """Parse a numbered-SAN variation string into per-ply {san, fen, uci, lbl} dicts.

    The input format is what pv_to_numbered_san() produces: '25. g5 exg5 26. fxg5'
    or '24...Kg7 25. g5'. Move numbers are stripped, then each SAN is applied to a
    copy of the board starting at fen_start. `lbl` is the display move-number
    prefix rebuilt from the replay board ('25. ' for White, '24... ' for a line's
    first Black move, '' otherwise) so the viewer can render variations in proper
    parenthetical notation. Returns [] on any parse error so the viewer degrades
    gracefully when a variation can't be decoded.
    """
    clean = re.sub(r'\d+\.{1,3}\s*', '', pv_san_numbered or '').strip()
    sans = clean.split() if clean else []
    if not sans:
        return []
    try:
        board = chess.Board(fen_start)
        result = []
        first = True
        for san in sans:
            num = board.fullmove_number
            white_to_move = board.turn == chess.WHITE
            move = board.parse_san(san)
            uci = move.uci()
            board.push(move)
            if white_to_move:
                lbl = f"{num}. "
            elif first:
                lbl = f"{num}... "
            else:
                lbl = ""
            result.append({"san": san, "fen": board.fen(), "uci": uci, "lbl": lbl})
            first = False
        return result
    except Exception:
        return []


def build_pgn_viewer(game: GameAnalysis, flipped: bool = False) -> str:
    """Return a self-contained <section> with the click-through replay board.
    Returns '' when there are no moves to show."""
    if not game.moves:
        return ""

    start_fen = game.moves[0].fen_before
    plies = [{"san": "", "fen": start_fen, "uci": "", "n": 0, "s": "", "ev": "", "cls": "", "br": False}]
    for m in game.moves:
        d = {
            "san": m.san,
            "fen": m.fen_after,
            "uci": m.uci or "",
            "n": m.move_number,
            "s": "W" if m.side == "White" else "B",
            "ev": _viewer_eval_text(m.eval_after_cp, m.mate_after),
            "cls": m.classification,
            "br": bool(getattr(m, "is_brilliant", False)),
        }
        # Variation data: per-ply FENs so the viewer can play out engine lines.
        # best_line starts from fen_before ("what to play instead").
        # refutation_line starts from fen_after ("what your move runs into").
        move_vars = []
        if getattr(m, "best_line_san", ""):
            best_plies = _pv_to_fen_plies(m.fen_before, m.best_line_san)
            if best_plies:
                move_vars.append({"tp": "best", "plies": best_plies})
        if getattr(m, "refutation_line_san", ""):
            ref_plies = _pv_to_fen_plies(m.fen_after, m.refutation_line_san)
            if ref_plies:
                move_vars.append({"tp": "ref", "plies": ref_plies})
        if move_vars:
            d["vars"] = move_vars
        plies.append(d)

    # Result + termination reason so the viewer can mark how the game ended
    # ('1-0 · resignation') right in the move list and on the final ply.
    headers = getattr(game, "headers", {}) or {}
    result = (getattr(game, "result", "") or headers.get("Result", "") or "").strip()
    term = termination_reason(headers, game.moves[-1].san if game.moves else "")
    payload = json.dumps(
        {"flip": bool(flipped), "plies": plies, "result": result, "term": term},
        ensure_ascii=True,
    )
    # Defensive: never let a value end the <script> block early.
    payload = payload.replace("</", "<\\/")

    return f"""<section class="greco-viewer">
<h2>Replay the game</h2>
<div class="gv-wrap">
<div class="gv-board-col">
<svg id="gv-board" class="gv-board" viewBox="0 0 380 380" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">{_piece_defs_inline()}</svg>
<div class="gv-controls">
<button id="gv-start" type="button" title="Start (Home)">&#9198;</button>
<button id="gv-prev" type="button" title="Previous (Left arrow)">&#9664;</button>
<button id="gv-next" type="button" title="Next (Right arrow)">&#9654;</button>
<button id="gv-end" type="button" title="End (End)">&#9197;</button>
<button id="gv-flip" type="button" title="Flip board">&#8645; Flip</button>
<button id="gv-sound" type="button" title="Toggle move sounds">&#128266;</button>
</div>
<div id="gv-status" class="gv-status"></div>
<div id="gv-vars" class="gv-vars"></div>
</div>
<div id="gv-moves" class="gv-moves"></div>
</div>
<p class="gv-hint">Click any move, use the buttons, or press &larr; / &rarr; (Home / End to jump).
Click a move in an engine line (&ldquo;Better:&rdquo; / &ldquo;Then:&rdquo;) to step into it &mdash; &larr; / &rarr; then walk that line, and Esc (or &larr; past its first move) returns to the game.</p>
<script type="application/json" id="greco-viewer-data">{payload}</script>
<script>{_VIEWER_JS}</script>
</section>
"""


def markdown_to_html(
    md_path: Path,
    html_path: Optional[Path] = None,
    embed_assets: bool = True,
    game: Optional[GameAnalysis] = None,
    flipped: bool = False,
    read_aloud: bool = True,
) -> Path:
    """
    Convert an assembled Markdown report to a single self-contained HTML file
    using the `markdown` library, with light CSS so it reads well in a browser.

    When `embed_assets` is True (default), all SVG boards and the eval-graph PNG
    are inlined directly into the HTML, so the file stands alone — no links to
    open, no sibling folder required. You can email it, move it, or print it to
    PDF (Ctrl+P -> Save as PDF) and every image travels with it.

    When `game` is provided, an interactive click-through replay board is
    embedded near the top (after the eval graph). `flipped` orients it for
    Black. The viewer is also fully self-contained.
    """
    import markdown as md_lib  # lazy import

    md_text = md_path.read_text(encoding="utf-8")
    html_body = md_lib.markdown(
        md_text,
        extensions=["fenced_code", "tables", "toc", "sane_lists"],
        output_format="html5",
    )

    if embed_assets:
        html_body = _inline_image_assets(html_body, md_path.parent)

    # Interactive replay board: insert just before the first <hr> (the divider
    # between the header/eval-graph matter and the narrative). Falls back to
    # prepending if no divider is present.
    viewer_css = ""
    if game is not None and game.moves:
        viewer_html = build_pgn_viewer(game, flipped=flipped)
        if viewer_html:
            viewer_css = _VIEWER_CSS
            hr_at = html_body.find("<hr")
            if hr_at != -1:
                html_body = html_body[:hr_at] + viewer_html + "\n" + html_body[hr_at:]
            else:
                html_body = viewer_html + "\n" + html_body

    if html_path is None:
        html_path = md_path.with_suffix(".html")

    css = """
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=EB+Garamond:ital,wght@0,400;0,700;1,400;1,700&display=swap');
    body { font-family: 'EB Garamond', 'Palatino Linotype', Palatino, Georgia, 'Times New Roman', serif;
           max-width: 820px; margin: 2rem auto; padding: 0 1.2rem; line-height: 1.65;
           color: #2e2117; background: #fbf6e7; }
    h1, h2, h3, h4 { line-height: 1.25; color: #5E151D; }
    h1 { font-family: 'Cinzel', 'Palatino Linotype', Palatino, Georgia, serif;
         border-bottom: 3px double #C9A23A; padding-bottom: 0.3rem; color: #7A1C26; }
    h2, h3, h4 { font-family: 'EB Garamond', 'Palatino Linotype', Palatino, Georgia, serif;
                 font-weight: 700; }
    h2 { border-bottom: 1px solid #e3d2a6; padding-bottom: 0.2rem; }
    h3 { color: #7A1C26; margin-top: 1.6rem; }
    a { color: #7A1C26; }
    code, pre { font-family: 'Consolas', 'Menlo', monospace; }
    pre { background: #f3e9cf; padding: 0.75rem 1rem; border-radius: 4px; overflow-x: auto;
          border: 1px solid #e3d2a6; }
    blockquote { border-left: 3px solid #C9A23A; padding: 0.4rem 1rem; color: #4a3826;
                 background: #f3e9cf; border-radius: 0 4px 4px 0; }
    img { max-width: 100%; display: block; margin: 1rem auto; }
    figure { margin: 1.2rem auto; text-align: center; }
    figure.board svg { width: 360px; max-width: 90%; height: auto;
                       border: 1px solid #cbb89a; border-radius: 4px; background: #fff; }
    figcaption { font-size: 0.85rem; color: #6b5942; font-style: italic; margin-top: 0.3rem; }
    """ + viewer_css

    read_aloud_html = _READ_ALOUD_SNIPPET if read_aloud else ""
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(md_path.stem)}</title>
<style>{css}</style>
</head>
<body>
{html_body}
{read_aloud_html}
</body>
</html>
"""
    html_path.write_text(page, encoding="utf-8")
    return html_path


# --------------------------------------------------------------------------
# Shareable export — bundle a finished report into ONE emailable HTML file
# --------------------------------------------------------------------------
# A finished report is a *folder*: the self-contained `<name>.html`, the source
# `<name>.md`, and a `<name>_assets/` folder of board SVGs + the eval PNG. That
# multi-file folder is the right internal working format, but it is confusing to
# share — a non-technical recipient can't tell which file to open. This export
# produces a single, clearly-labelled `<name> (shareable).html` with everything
# inlined, so it can be attached to an email as one file. It never touches the
# originals (an export product, not a replacement).

def _resolve_report_html(report) -> Path:
    """Find the main report `.html` from a report folder, an `.html`, or an `.md`.

    Skips any previously-generated `(shareable)` export so re-running is safe.
    """
    report = Path(report)
    if report.is_dir():
        candidates = sorted(
            p for p in report.glob("*.html") if "(shareable)" not in p.stem
        )
        if not candidates:
            raise FileNotFoundError(f"No report .html found in folder: {report}")
        named = report / f"{report.name}.html"  # prefer '<folder>.html'
        return named if named.exists() else candidates[0]
    suffix = report.suffix.lower()
    if suffix == ".html":
        return report
    if suffix == ".md":
        sibling = report.with_suffix(".html")
        if sibling.exists():
            return sibling
        raise FileNotFoundError(
            f"No .html next to {report.name}; generate the report's HTML first."
        )
    raise ValueError(f"Unsupported report path (need a folder, .html, or .md): {report}")


def export_shareable_html(report, dest_dir: Optional[Path] = None) -> Path:
    """Bundle a finished Greco report into ONE self-contained, emailable HTML file.

    `report` may be the report folder, its `.html`, or its `.md`. Writes
    ``<stem> (shareable).html`` next to the source (or in `dest_dir`) — a clearly
    labelled EXPORT that never overwrites the working files. Every board SVG, the
    eval-graph PNG, the page CSS and the interactive replay viewer are inlined, so
    the single file opens correctly on any machine and survives being emailed.

    Returns the path to the written export file.

    Implementation note: this reuses ``_inline_image_assets`` over the existing
    HTML. That pass is *idempotent* — already-embedded ``data:`` URIs and remote
    URLs are left untouched — so a report already built self-contained
    (``embed_assets=True``) passes through unchanged, while one that still points
    at sidecar files gets fixed here. The CSS is always emitted inline by
    ``markdown_to_html``, so there is no external stylesheet to chase.
    """
    src_html = _resolve_report_html(report)
    base_dir = src_html.parent
    html = src_html.read_text(encoding="utf-8")

    # Guarantee self-containment regardless of how the source HTML was produced.
    html = _inline_image_assets(html, base_dir)

    out_dir = Path(dest_dir) if dest_dir else base_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src_html.stem} (shareable).html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
