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
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

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
    r"""Where the GUI saves reports: E:\Chess\Reports if the E: drive is
    connected, otherwise ~/Documents/Greco Reports. Creates the folder."""
    candidates = [Path("E:/Chess/Reports"), Path.home() / "Documents" / "Greco Reports"]
    for path in candidates:
        try:
            if path.drive and not Path(path.drive + "/").exists():
                continue  # drive (e.g. E:) not mounted right now
            path.mkdir(parents=True, exist_ok=True)
            return path
        except Exception:
            continue
    fallback = Path.home() / "Greco Reports"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def format_move_list(game: GameAnalysis) -> str:
    """Return the game's mainline as '1. e4 e5 2. Nf3 Nc6 ...' wrapped to ~70 cols."""
    tokens: List[str] = []
    for move in game.moves:
        if move.side == "White":
            tokens.append(f"{move.move_number}.")
            tokens.append(move.san)
        else:
            tokens.append(move.san)
    if game.result and game.result != "*":
        tokens.append(game.result)

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
    title = f"{h.get('White', '?')} vs. {h.get('Black', '?')}"
    if h.get("Event") and h["Event"] != "?":
        title += f" — {h['Event']}"
    if h.get("Date") and h["Date"] not in ("?", ""):
        title += f" ({h['Date']})"

    metadata_rows = []
    for key in ("White", "Black", "Result", "ECO", "Opening"):
        if h.get(key) and h[key] != "?":
            metadata_rows.append(f"- **{key}:** {h[key]}")
    if h.get("TimeControl") and h["TimeControl"] != "?":
        metadata_rows.append(f"- **TimeControl:** {_humanize_time_control(h['TimeControl'])}")
    if h.get("WhiteElo"):
        metadata_rows.append(f"- **White ELO:** {h['WhiteElo']}")
    if h.get("BlackElo"):
        metadata_rows.append(f"- **Black ELO:** {h['BlackElo']}")

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
    return f"move_{move.move_number:03d}{side_marker}_{_move_san_to_filename_part(move.san)}.svg"


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
    if move.side == "White":
        patterns = [
            rf"^(#{{2,4}}\s*{move_number}\.\s*{san_escaped}\b.*)$",
        ]
    else:
        patterns = [
            rf"^(#{{2,4}}\s*{move_number}\.{{1,3}}\s*{san_escaped}\b.*)$",
            rf"^(#{{2,4}}\s*{move_number}\.\.\.\s*{san_escaped}\b.*)$",
        ]
    alt_text = (
        f"Position after {move_number}{'.' if move.side == 'White' else '...'} {move.san}"
    )
    replacement = rf"\1\n\n![{alt_text}]({image_rel_path})\n"
    for pattern in patterns:
        new_md, n = re.subn(pattern, replacement, markdown, count=1, flags=re.MULTILINE)
        if n:
            return new_md, True

    # Fallback (for opening/prose moves with no dedicated header): anchor to a
    # BOLDED inline reference of the move, e.g. `**5. d4**` or `**6. g3 6...Qd8**`.
    # Insert the image after the whole line that contains that bold run.
    bold_move = rf"\*\*[^*\n]*\b{move_number}\b[^*\n]*{san_escaped}[^*\n]*\*\*"
    line_pattern = rf"^(.*{bold_move}.*)$"
    new_md, n = re.subn(
        line_pattern,
        rf"\1\n\n![{alt_text}]({image_rel_path})\n",
        markdown,
        count=1,
        flags=re.MULTILINE,
    )
    if n:
        return new_md, True
    return markdown, False


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

    # Decide which moves get a board: tier-selected moves PLUS periodic snapshots
    # (every `periodic_every` plies) so the opening and quiet stretches are also
    # depicted, not just the tactical Tier-2/3 moments.
    tiers_to_render = BOARD_TIERS.get(boards_at, BOARD_TIERS["tier3"])
    render_plies = set()
    for move, tier in zip(game.moves, tiers):
        if tier in tiers_to_render:
            render_plies.add(move.ply)
    if periodic_every and periodic_every > 0:
        for move in game.moves:
            if move.ply % periodic_every == 0:
                render_plies.add(move.ply)

    unanchored: List[tuple] = []  # (move, rel_path) for boards with no matching anchor
    if render_plies:
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
            body, inserted = _insert_image_after_move_header(body, move, rel)
            if not inserted:
                unanchored.append((move, rel))

    # Safety net: any board that couldn't be anchored to a move header is
    # collected into a "Key positions" section so it's never silently dropped.
    if unanchored:
        lines = ["\n\n---\n\n## Other key positions\n"]
        for move, rel in unanchored:
            dots = "." if move.side == "White" else "..."
            label = f"{move.move_number}{dots} {move.san}"
            lines.append(f"\n**{label}** ({move.classification})\n")
            lines.append(f"\n![Position after {label}]({rel})\n")
        body = body + "".join(lines)

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
            return f'<figure class="board">{svg}{caption}</figure>'

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


def markdown_to_html(
    md_path: Path, html_path: Optional[Path] = None, embed_assets: bool = True
) -> Path:
    """
    Convert an assembled Markdown report to a single self-contained HTML file
    using the `markdown` library, with light CSS so it reads well in a browser.

    When `embed_assets` is True (default), all SVG boards and the eval-graph PNG
    are inlined directly into the HTML, so the file stands alone — no links to
    open, no sibling folder required. You can email it, move it, or print it to
    PDF (Ctrl+P -> Save as PDF) and every image travels with it.
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

    if html_path is None:
        html_path = md_path.with_suffix(".html")

    css = """
    body { font-family: Georgia, 'Times New Roman', serif; max-width: 820px;
           margin: 2rem auto; padding: 0 1rem; line-height: 1.55; color: #222; }
    h1, h2, h3, h4 { font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.25; }
    h1 { border-bottom: 2px solid #2b6cb0; padding-bottom: 0.3rem; }
    h3 { color: #2b6cb0; margin-top: 1.6rem; }
    code, pre { font-family: 'Consolas', 'Menlo', monospace; }
    pre { background: #f5f7fa; padding: 0.75rem 1rem; border-radius: 4px; overflow-x: auto; }
    blockquote { border-left: 3px solid #2b6cb0; padding-left: 1rem; color: #444; }
    img { max-width: 100%; display: block; margin: 1rem auto; }
    figure { margin: 1.2rem auto; text-align: center; }
    figure.board svg { width: 360px; max-width: 90%; height: auto; }
    figcaption { font-size: 0.85rem; color: #666; font-style: italic; margin-top: 0.3rem; }
    """

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{md_path.stem}</title>
<style>{css}</style>
</head>
<body>
{html_body}
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    return html_path
