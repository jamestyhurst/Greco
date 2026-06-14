"""
factcheck.py — Layer-2 claim-verification self-test for Greco reports.

THE PROBLEM IT SOLVES
    Greco's whole architecture is "the engine supplies facts, the LLM only narrates
    them." But nothing CHECKS that the finished prose actually obeys that — the
    narrator can still slip in a derived-and-wrong board fact ("the king moved onto
    the g-file" when it was already there). This module is the output-side audit: it
    takes the generated report + the per-ply FACT PACKET the narrator was given and
    finds prose claims that CONTRADICT the facts.

TWO LAYERS (James's "let it cook" testing doctrine)
    1. DETERMINISTIC checks (this module's core) — pure, engine-free, no API key, so
       they run in CI and gate a build. They are written PRECISION-OVER-RECALL: a
       detector fires ONLY when it can bind a claim to one specific move AND that
       move's facts unambiguously refute the literal claim. Every ambiguous parse is
       dropped, never flagged — a false alarm in a gate is worse than a missed catch
       (the same posture as outputs.find_unverified_variation_moves).
    2. LLM-JUDGE (optional, key-gated, ADVISORY) — shows a checker model the fact
       packet + the prose and asks "does the prose contradict these facts?" Catches
       the long tail the deterministic checks deliberately can't. Never fails CI.

    The fact packet is exactly what narrator._move_to_dict emits, so the checker sees
    byte-for-byte the same truth the writer saw. tools/verify_report.py drives this
    over a saved analysis JSON (main.py --save-analysis) so it needs no engine at
    check time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List, Optional

import chess

# Field-shape dependency: detectors read the keys narrator._move_to_dict emits
# (from/to/pieces/material/played/move_no/side/...). If that schema changes, update here.


@dataclass
class Contradiction:
    """One detected prose-vs-facts disagreement. Detect-and-report only; nothing here
    ever mutates the report."""
    check: str            # 'geometry' | 'piece_square' | 'material' | 'variation' | 'llm-judge'
    move_ref: str         # e.g. '24...Kg7' or '' when not move-bound
    claim: str            # the asserted thing we read in the prose
    contradicted_fact: str  # the ground truth that refutes it
    snippet: str          # the verbatim sentence/phrase, so a human can eyeball it
    ply: Optional[int] = None
    confidence: str = "high"   # deterministic = high; llm-judge carries its own


# --------------------------------------------------------------------------- #
# Report parsing + ply binding (the shared precision gate)
# --------------------------------------------------------------------------- #
_PIECE_WORDS = {"king": chess.KING, "queen": chess.QUEEN, "rook": chess.ROOK,
                "bishop": chess.BISHOP, "knight": chess.KNIGHT, "pawn": chess.PAWN}
_SAN_RE = re.compile(r"(O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)")
_BOLD_MOVE_RE = re.compile(r"\*\*\s*(\d+)(\.\.\.|\.)\s*([^*]+?)\*\*")
_HYPOTHETICAL_RE = re.compile(r"\b(if|would|could have|were to|instead|had )\b", re.IGNORECASE)
_PAST_TENSE_RE = re.compile(
    # Past / displacement / trade phrasings that legitimately name a piece's PRE-move
    # square (the narrator describes the very move that evicted it). Abstain on these.
    r"\b(former|formerly|had been|has been|used to|earlier|previously|no longer|once on|"
    r"was on|undermined|dislodged|driven|kicked|chased|evicted|displaced|ousted|"
    r"forced to|retreats? to|retreated|traded|exchanged|swapped)\b",
    re.IGNORECASE,
)
_PIECE_NOUN_RE = re.compile(r"\b(king|queen|rook|bishop|knight|pawn)\b", re.IGNORECASE)


def _moved_piece_type(packet: dict):
    """The piece TYPE that actually moved this ply, from the SAN ('Kg7'->king, 'Rc7'->
    rook, 'e4'->pawn, 'O-O'->king)."""
    played = str(packet.get("played", "")).strip()
    if not played:
        return None
    if played.startswith("O-O"):
        return chess.KING
    return {"K": chess.KING, "Q": chess.QUEEN, "R": chess.ROOK,
            "B": chess.BISHOP, "N": chess.KNIGHT}.get(played[0], chess.PAWN)


def _subject_piece_before(sentence: str, pos: int):
    """The piece type named just before `pos` (the clause's grammatical subject), or
    None. Used to require that an 'onto the X-file' clause is about the piece that
    actually moved — not a different piece mentioned in the same sentence."""
    last = None
    for mm in _PIECE_NOUN_RE.finditer(sentence[:pos]):
        last = mm.group(1).lower()
    return _PIECE_WORDS[last] if last else None


def report_body(report_md: str) -> str:
    """The narrative only — drop the auto-prepended header/eval matter above the
    first '---' divider (the exact contract outputs.assemble_report builds)."""
    idx = report_md.find("\n---\n")
    return report_md[idx + 5:] if idx != -1 else report_md


def split_sentences(text: str) -> List[str]:
    """Sentence split that does NOT break on the dots inside a move number ('24.',
    '24...') or a decimal eval ('1.5'). We mask digit-dot runs, split on .!?, unmask."""
    masked = re.sub(r"(\d)(\.{1,3})", lambda m: m.group(1) + "\x00" * len(m.group(2)), text)
    parts = re.split(r"(?<=[.!?])\s+", masked)
    return [p.replace("\x00", ".").strip() for p in parts if p.strip()]


def _norm_san(san: str) -> str:
    return re.sub(r"[+#!?]+$", "", san.strip())


def bind_span_to_ply(sentence: str, fact_packets: List[dict]) -> Optional[dict]:
    """Return the single ply packet a sentence refers to, or None if zero / multiple /
    unresolvable references. This is the precision gate: a claim is attributed to a ply
    only when exactly one bold move reference resolves unambiguously."""
    refs = set()
    resolved = None
    for m in _BOLD_MOVE_RE.finditer(sentence):
        num = int(m.group(1))
        side = "Black" if m.group(2) == "..." else "White"
        san_m = _SAN_RE.match(m.group(3).strip())
        if not san_m:
            continue
        san = _norm_san(san_m.group(1))
        refs.add((num, side))
        for pk in fact_packets:
            if pk.get("move_no") == num and pk.get("side") == side and _norm_san(str(pk.get("played", ""))) == san:
                resolved = pk
                break
    if len(refs) != 1:
        return None  # zero or multiple distinct move references -> never bind
    return resolved


# --------------------------------------------------------------------------- #
# Deterministic detectors — each abstains by default, fires only on a sure thing
# --------------------------------------------------------------------------- #
_ONTO_FILE_RE = re.compile(r"\bonto the ([a-h])-file", re.IGNORECASE)
_ONTO_RANK_RE = re.compile(r"\bonto the (\d)(?:st|nd|rd|th) rank", re.IGNORECASE)


def check_geometry(packet: dict, sentence: str) -> Iterator[Contradiction]:
    """The king-on-g-file class: prose says the move went 'onto the X-file/Nth rank'
    when the moved piece was ALREADY on that file/rank (from and to share it). Only
    fires on the literal 'onto' motion verb — never on 'controls/opens/seizes the file'."""
    frm, to = str(packet.get("from", "")), str(packet.get("to", ""))
    if len(frm) != 2 or len(to) != 2:
        return
    moved = _moved_piece_type(packet)
    ref = f"{packet.get('move_no')}{'...' if packet.get('side')=='Black' else '.'}{packet.get('played')}"
    for m in _ONTO_FILE_RE.finditer(sentence):
        f = m.group(1).lower()
        if not (frm[0] == f and to[0] == f):  # piece DID change file -> 'onto' is fine
            continue
        # Only fire if the clause's subject is the piece that actually moved — otherwise
        # the 'onto' is about a different piece that legitimately reached that file.
        if moved is None or _subject_piece_before(sentence, m.start()) != moved:
            continue
        yield Contradiction(
            check="geometry", ply=packet.get("ply"), move_ref=ref,
            claim=f"moved onto the {f}-file",
            contradicted_fact=f"from={frm} to={to}: the piece was already on the {f}-file",
            snippet=sentence,
        )
    for m in _ONTO_RANK_RE.finditer(sentence):
        r = m.group(1)
        if not (frm[1] == r and to[1] == r):
            continue
        if moved is None or _subject_piece_before(sentence, m.start()) != moved:
            continue
        yield Contradiction(
            check="geometry", ply=packet.get("ply"), move_ref=ref,
            claim=f"moved onto the {r}th rank",
            contradicted_fact=f"from={frm} to={to}: the piece was already on rank {r}",
            snippet=sentence,
        )


def _parse_pieces(pieces: str) -> dict:
    """Parse the _piece_placement string into {square_name: (color, piece_type)}."""
    out = {}
    if not pieces:
        return out
    for half in pieces.split(" | "):
        toks = half.split()
        if not toks:
            continue
        color = chess.WHITE if toks[0] == "White" else chess.BLACK
        for tok in toks[1:]:
            if ":" not in tok:
                continue
            sym, squares = tok.split(":", 1)
            ptype = {"K": chess.KING, "Q": chess.QUEEN, "R": chess.ROOK,
                     "B": chess.BISHOP, "N": chess.KNIGHT, "P": chess.PAWN}.get(sym.upper())
            if ptype is None:
                continue
            for sq in squares.split(","):
                if sq:
                    out[sq] = (color, ptype)
    return out


_PIECE_ON_RE = re.compile(
    r"\b(?:the|his|her|its|their|white's|black's)\s+(king|queen|rook|bishop|knight|pawn)\s+on\s+([a-h][1-8])",
    re.IGNORECASE,
)


def check_piece_square(packet: dict, sentence: str) -> Iterator[Contradiction]:
    """'the <piece> on <square>' vs the move's `pieces` placement. Fires only when no
    piece of that type sits on the claimed square AND that piece type still exists on
    the board (a mislocation, not a since-captured piece)."""
    pieces = packet.get("pieces")
    if not pieces or _PAST_TENSE_RE.search(sentence):
        return
    placement = _parse_pieces(pieces)
    types_present = {pt for (_c, pt) in placement.values()}
    for m in _PIECE_ON_RE.finditer(sentence):
        word, sq = m.group(1).lower(), m.group(2).lower()
        if sq == str(packet.get("to", "")):
            continue  # the move's own destination is authoritative
        ptype = _PIECE_WORDS[word]
        here = placement.get(sq)
        if here and here[1] == ptype:
            continue  # correctly located
        if ptype not in types_present:
            continue  # the piece is gone (captured) — a legit past reference, not a mislocation
        yield Contradiction(
            check="piece_square", ply=packet.get("ply"),
            move_ref=f"{packet.get('move_no')}{'...' if packet.get('side')=='Black' else '.'}{packet.get('played')}",
            claim=f"the {word} on {sq}",
            contradicted_fact=f"no {word} on {sq} after this move (pieces: {pieces})",
            snippet=sentence,
        )


_MATERIAL_AHEAD_RE = re.compile(
    r"\b(?:is |are |you(?:'re| are)? |stands? )?(?:up|ahead|won|wins)\b[^.]{0,30}?\b(a (?:clean )?(?:pawn|piece|knight|bishop|rook|queen)|\d+\s*(?:points?|pawns?))\b",
    re.IGNORECASE,
)


def check_material(packet: dict, sentence: str) -> Iterator[Contradiction]:
    """'up a pawn / ahead / wins a piece' vs the SETTLED `material` field, from the
    right POV. Very conservative: fires only on a clear sign disagreement (prose says
    a side is materially ahead while that side is actually a full pawn+ behind)."""
    mat = packet.get("material")
    if mat is None:
        return
    low = sentence.lower()
    if not _MATERIAL_AHEAD_RE.search(low):
        return
    # Abstain on framings the settled-material field cannot fairly contradict: the
    # exchange nuance; a sound-sacrifice ("down a piece but winning"); a FUTURE/coming
    # tactic ("wins a piece next move"); or recovering material toward EQUALITY
    # ("wins a pawn back to reach equality"). Precision over recall.
    _abstain = ("the exchange", "sacrific", "down ", "gave up", " back",
                "next move", "will ", "is going to", "threatens to",
                "equal", "level", "regain", "win it back")
    if any(c in low for c in _abstain):
        return
    # POV: an explicit White/Black subject wins; else the bound mover.
    if re.search(r"\bwhite (?:is|are|stands)\b", low):
        pov_white = True
    elif re.search(r"\bblack (?:is|are|stands)\b", low):
        pov_white = False
    else:
        pov_white = packet.get("side") == "White"
    pov_material = float(mat) if pov_white else -float(mat)
    if pov_material <= -1.0:  # claims ahead, but is actually a pawn or more DOWN
        side = "White" if pov_white else "Black"
        yield Contradiction(
            check="material", ply=packet.get("ply"),
            move_ref=f"{packet.get('move_no')}{'...' if packet.get('side')=='Black' else '.'}{packet.get('played')}",
            claim="a side is materially ahead / winning material",
            contradicted_fact=f"settled material={mat} (White-positive): {side} is behind, not ahead",
            snippet=sentence,
        )


def check_variations(report_md: str, game) -> List[Contradiction]:
    """Wrap the existing, already-reviewed outputs.find_unverified_variation_moves:
    any move written in a parenthetical variation that is not in this game's engine
    lines is a confabulated move."""
    try:
        from outputs import find_unverified_variation_moves
        tokens = find_unverified_variation_moves(report_md, game)
    except Exception:
        return []
    return [
        Contradiction(check="variation", ply=None, move_ref="", claim=f"variation move {t}",
                      contradicted_fact="not present in any engine line for this game", snippet=t)
        for t in tokens
    ]


# --------------------------------------------------------------------------- #
# Deterministic harness (CI-safe entry point)
# --------------------------------------------------------------------------- #
def verify_report(report_md: str, fact_packets: List[dict], *, game=None) -> List[Contradiction]:
    """Run the deterministic contradiction detectors. Pure: no engine, no API key.
    `fact_packets` is the list of per-ply dicts from narrator._move_to_dict (or the
    saved-analysis JSON re-serialised through it). Returns a flat list of high-precision
    Contradictions; an empty list means the prose did not contradict the facts."""
    if "**" not in report_md and "(" not in report_md:
        return []
    body = report_body(report_md)
    found: List[Contradiction] = []
    for sentence in split_sentences(body):
        if _HYPOTHETICAL_RE.search(sentence) or sentence.strip().startswith("("):
            continue  # hypothetical/variation prose is not a claim about the played board
        packet = bind_span_to_ply(sentence, fact_packets)
        if packet is None:
            continue
        found.extend(check_geometry(packet, sentence))
        found.extend(check_piece_square(packet, sentence))
        found.extend(check_material(packet, sentence))
    if game is not None:
        found.extend(check_variations(report_md, game))
    return found


def build_fact_packets(game, tiers: List[int]) -> List[dict]:
    """The per-ply fact packets exactly as the narrator built them (so the checker sees
    the same truth the writer saw)."""
    from narrator import _move_to_dict
    return [_move_to_dict(m, t) for m, t in zip(game.moves, tiers)]


def run_deterministic_checks(game, tiers: List[int], report_md: str) -> List[Contradiction]:
    """Convenience wrapper for callers holding a GameAnalysis: build the fact packets
    and run the deterministic verifier (variations included)."""
    return verify_report(report_md, build_fact_packets(game, tiers), game=game)


# --------------------------------------------------------------------------- #
# LLM-judge (OPTIONAL, key-gated, ADVISORY — never gates CI)
# --------------------------------------------------------------------------- #
_JUDGE_SYSTEM = (
    "You are a fact-checker for chess game annotations. For each move you are given a "
    "STRUCTURED FACT PACKET computed by a chess engine (the ground truth) and the PROSE "
    "an annotator wrote about that move. Your ONLY job is to find statements in the prose "
    "that CONTRADICT the fact packet — a checkable, objective disagreement with the "
    "supplied facts. Examples of contradictions: the prose places a piece on a square the "
    "`pieces` list does not show; says a move 'attacks/kicks' a piece not in `attacks`; "
    "says a move went 'onto' a file/rank the `from` square already occupied; calls a file "
    "open that is not in `open_files`; states a material count disagreeing with `material`; "
    "cites a wrong `move_no`; calls a 'still-decisively-winning' move a blunder; asserts a "
    "fork/pin not in `double_attack`/`tactic_setup`/`certified`; says checkmate when the "
    "data shows resignation; or quotes a variation move not in this ply's `variations`. "
    "Use ONLY the supplied facts as truth. Do NOT use your own chess judgement to second-"
    "guess the engine, and do NOT invent facts. NEVER flag style, tone, word choice, "
    "emphasis, teaching quality, a 'prepares a break' (vs 'attacks') distinction, quoted "
    "master aphorisms, player names/pronouns, or vague-but-true descriptions — those are "
    "out of scope. When the facts are silent on a claim, it is NOT a contradiction. Prefer "
    "precision over recall: if unsure, do not flag. "
    'Reply with ONLY a JSON object: {"contradictions":[{"move_no":int,"side":"White|Black",'
    '"claim_text":str,"contradicted_fact":str,"confidence":float}]} and nothing else.'
)


def build_judge_items(game, tiers: List[int], report_md: str) -> List[dict]:
    """Pair each move's fact packet with the prose written about it (the sentences that
    bind to that ply). Key-free; reused by the judge and unit-testable on its own."""
    packets = build_fact_packets(game, tiers)
    items = []
    body = report_body(report_md)
    sentences = split_sentences(body)
    for pk in packets:
        if pk.get("tier", 0) < 1:
            continue  # acknowledge-only moves carry no checkable claim
        prose = [s for s in sentences if bind_span_to_ply(s, packets) is pk]
        if prose:
            items.append({"move_no": pk.get("move_no"), "side": pk.get("side"),
                          "played": pk.get("played"), "facts": pk, "prose": " ".join(prose)})
    return items


def _parse_judge_response(text: str) -> List[Contradiction]:
    """Extract the JSON contradictions array from a judge reply (defensive)."""
    import json
    data = None
    try:
        data = json.loads(text.strip())
    except Exception:
        # Tolerate leading/trailing prose: scan for the first BALANCED {...} so a brace
        # in trailing commentary can't swallow the real object (a recall hole otherwise).
        start = text.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(text[start:i + 1])
                        except Exception:
                            data = None
                        break
    if not isinstance(data, dict):
        return []
    out = []
    for c in data.get("contradictions", []):
        try:
            conf = float(c.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        out.append(Contradiction(
            check="llm-judge", ply=None,
            move_ref=f"{c.get('move_no')}{'...' if c.get('side')=='Black' else '.'}",
            claim=str(c.get("claim_text", "")),
            contradicted_fact=str(c.get("contradicted_fact", "")),
            snippet=str(c.get("claim_text", "")),
            confidence=f"{conf:.2f}",
        ))
    return out


def run_llm_judge(game, tiers: List[int], report_md: str, *,
                  model: str = "claude-opus-4-8", api_key: Optional[str] = None,
                  plies_per_chunk: int = 12) -> List[Contradiction]:
    """ADVISORY LLM judge: ask a checker model whether the prose contradicts the facts.
    Key-gated (returns [] with no key). Reuses narrator's truststore HTTP client for the
    TLS situation on this machine. Findings are advisory — the CLI never lets them fail CI."""
    import os
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return []
    # Setup is wrapped so the advisory judge can NEVER raise into the CLI exit code
    # (mirrors check_variations' fail-safe posture).
    try:
        items = build_judge_items(game, tiers, report_md)
        if not items:
            return []
        import json as _json
        from anthropic import Anthropic
        from narrator import _make_http_client

        client = Anthropic(api_key=key, http_client=_make_http_client())
    except Exception:
        return []
    findings: List[Contradiction] = []
    for i in range(0, len(items), plies_per_chunk):
        chunk = items[i:i + plies_per_chunk]
        payload = [{"move_no": it["move_no"], "side": it["side"],
                    "facts": it["facts"], "prose": it["prose"]} for it in chunk]
        user = ("Game: " + str(game.headers.get("White", "?")) + " vs " +
                str(game.headers.get("Black", "?")) + "\n\nMoves to check (JSON):\n" +
                _json.dumps(payload, indent=2))
        try:
            msg = client.messages.create(
                model=model, max_tokens=2000, system=_JUDGE_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(getattr(b, "text", "") for b in msg.content)
            findings.extend(_parse_judge_response(text))
        except Exception:
            continue  # advisory: a judge failure never breaks verification
    return findings
