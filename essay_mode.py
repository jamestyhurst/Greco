"""essay_mode.py — Essay Mode pipeline.

Unlike the game-analysis pipeline (PGN → Stockfish → Claude → report), Essay Mode
answers a free-text chess question using the knowledge corpus as its primary source.
PGN is optional; Stockfish is not required.

Architecture summary:
  Question [+ optional PGN] → retrieve_for_question() → ESSAY_SYSTEM_PROMPT
  → Claude API call → Markdown essay → essay_to_html()
"""
from __future__ import annotations

import os
from typing import List, Optional

import markdown as _md

import knowledge
from narrator import _make_http_client

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None  # type: ignore[assignment]


ESSAY_SYSTEM_PROMPT = """\
You are Greco — an AI chess narrator grounded in classical chess literature. In Essay Mode
your job is to answer a chess question analytically, drawing first from the classical corpus
supplied below, then from sound chess theory. You are a chess writer and historian, not a
database lookup.

## Core rules

1. **Answer from the corpus first.** When a supplied passage directly addresses the
   question, quote it verbatim and attribute it by author name and title. Prefer the
   master's own words over your paraphrase wherever the passage is relevant.

2. **Corpus over training knowledge.** When corpus passages and general chess knowledge
   diverge, prefer the corpus passage if it is more specific to the question.

3. **Do not assert specific board facts not in the corpus or the supplied game.** You may
   describe general truths of chess theory (e.g., "bishops are stronger in open positions").
   You may NOT claim that a specific move occurred in a specific historical game unless that
   game appears in the corpus passages provided. No invented game citations.

4. **No hallucinated sources.** Never invent a book title, game reference, or passage not
   in the `<corpus>` block. If you cannot find a classical source for a claim, state the
   idea without attribution or use "classical theory holds…" for widely-accepted principles.

5. **Length: 400–700 words** for a typical question. Shorter for simple questions; up to
   ~900 words only if the question is complex and the corpus provides substantial material.

6. **Close with a "Key takeaway:"** — a single crisp sentence the reader can carry away.

7. **Calibrate language** to the audience level if given: beginners need plain English and
   minimal jargon; advanced players can handle coordinates and technical terms.

## Format

Write in flowing prose paragraphs. Use a top-level `#` header for the essay title at the
very top. Use `**Key takeaway:**` in bold for the final line. End with a
`**Sources consulted from Greco's classical corpus:**` section listing (as bullet points)
only the books you actually cited. Do not list sources you did not use. Never invent
sources.
"""


def generate_essay(
    question: str,
    pgn_text: Optional[str] = None,
    audience_level: str = "club",
    note: str = "",
    model: str = "claude-sonnet-4-6",
    api_key: Optional[str] = None,
    corpus_k: int = 7,
) -> dict:
    """Generate an Essay Mode response.

    Returns:
        {
            "markdown":        str   — the essay in Markdown,
            "title":           str   — restated question as a short title,
            "corpus_coverage": str   — "full" | "partial" | "none",
            "sources":         list  — list of "Author, *Title* (year)" strings,
        }
    """
    passages = knowledge.retrieve_for_question(question, top_k=corpus_k)
    coverage = "full" if len(passages) >= 4 else ("partial" if passages else "none")

    corpus_block = _build_corpus_block(passages)
    user_prompt = _build_essay_prompt(
        question=question,
        corpus_block=corpus_block,
        coverage=coverage,
        pgn_text=pgn_text,
        audience_level=audience_level,
        note=note,
    )

    client = Anthropic(
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        http_client=_make_http_client(),
    )
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=ESSAY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    markdown_text = message.content[0].text

    return {
        "markdown": markdown_text,
        "title": _derive_title(question),
        "corpus_coverage": coverage,
        "sources": _extract_sources(passages),
    }


def essay_to_html(result: dict) -> str:
    """Convert an essay result dict to a standalone Greco-styled HTML page."""
    display_title = result.get("title") or "Greco Essay"
    body_html = _md.markdown(
        result["markdown"],
        extensions=["fenced_code", "tables"],
    )
    coverage = result.get("corpus_coverage", "unknown")
    coverage_note_html = {
        "none": (
            '<p class="coverage-note">Greco\'s classical corpus had limited coverage '
            "for this topic; the answer draws on general chess theory.</p>"
        ),
        "partial": (
            '<p class="coverage-note">Some relevant passages were found in '
            "Greco's classical corpus and are cited below.</p>"
        ),
    }.get(coverage, "")

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{display_title} — Greco Essay</title>\n"
        "<style>\n"
        "  :root { --bg:#fffdf6; --ink:#3A2A1A; --gold:#8a7a5c; --accent:#5a3e28; --border:#e2d9c8; }\n"
        "  body { font-family:'Georgia',serif; background:var(--bg); color:var(--ink);\n"
        "         max-width:780px; margin:0 auto; padding:2rem 1.5rem;\n"
        "         line-height:1.75; font-size:1.05rem; }\n"
        "  h1 { font-size:1.6rem; color:var(--accent); border-bottom:2px solid var(--gold);\n"
        "       padding-bottom:.4rem; margin-bottom:1.4rem; }\n"
        "  h2 { font-size:1.1rem; color:var(--accent); margin-top:1.6rem; }\n"
        "  blockquote { border-left:3px solid var(--gold); margin-left:0;\n"
        "               padding-left:1.2rem; color:var(--gold); font-style:italic; }\n"
        "  a { color:var(--accent); }\n"
        "  .coverage-note { font-size:.88rem; color:var(--gold); background:#f5f0e8;\n"
        "                   border:1px solid var(--border); border-radius:6px;\n"
        "                   padding:.6rem 1rem; margin-bottom:1.2rem; }\n"
        "  .essay-footer { margin-top:2.5rem; padding-top:1rem;\n"
        "                  border-top:1px solid var(--border);\n"
        "                  font-size:.85rem; color:var(--gold); }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{coverage_note_html}\n"
        f"{body_html}\n"
        '<div class="essay-footer">Generated by '
        '<a href="https://github.com/JamesTyhurst/Greco">Greco</a>'
        " — classical chess literature meets modern AI.</div>\n"
        "</body>\n"
        "</html>"
    )


# --------------------------------------------------------------------------- #
# Prompt construction helpers
# --------------------------------------------------------------------------- #
def _build_corpus_block(passages: list) -> str:
    if not passages:
        return "<corpus>\n(No relevant passages found in Greco's classical corpus.)\n</corpus>"
    lines = ["<corpus>"]
    for i, p in enumerate(passages, 1):
        header = f"[{i}] {p.author}, *{p.title}*"
        if p.year:
            header += f" ({p.year})"
        lines.append(f"\n{header}\n{p.text.strip()}")
    lines.append("</corpus>")
    return "\n".join(lines)


def _build_essay_prompt(
    question: str,
    corpus_block: str,
    coverage: str,
    pgn_text: Optional[str],
    audience_level: str,
    note: str,
) -> str:
    parts = [f"## Question\n{question}"]
    if audience_level and audience_level.lower() not in ("", "club", "not specified"):
        parts.append(f"## Audience level\n{audience_level}")
    if note:
        parts.append(f"## Additional context\n{note}")
    if coverage == "none":
        parts.append(
            "## Corpus coverage note\n"
            "Greco's classical corpus has limited coverage of this topic. "
            "Answer from sound chess theory; clearly flag where classical citations are absent."
        )
    parts.append(corpus_block)
    if pgn_text:
        trimmed = pgn_text[:3000]
        parts.append(
            "## Illustrative game (optional — reference specific moves only if directly relevant)\n"
            f"```\n{trimmed}\n```"
        )
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Result helpers
# --------------------------------------------------------------------------- #
def _extract_sources(passages: list) -> List[str]:
    seen: set = set()
    sources: List[str] = []
    for p in passages:
        key = (p.author, p.title, p.year)
        if key not in seen and p.author and p.title:
            seen.add(key)
            year_str = f" ({p.year})" if p.year else ""
            sources.append(f"{p.author}, *{p.title}*{year_str}")
    return sources


def _derive_title(question: str) -> str:
    q = question.strip().rstrip("?").rstrip(".")
    return (q[:57] + "…") if len(q) > 60 else q
