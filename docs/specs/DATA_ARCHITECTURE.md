# Evidence-Bundle Upgrade for the Certified-Claims Allow-Set

**Data-architecture spec — backward-compatible enrichment of `factgate.certified_claims`**
Date: 2026-06-15
Scope: `factgate.py`, `narrator.py`, `tests/test_factgate.py`; informational touch on `factcheck.py`.
Doctrine: *data-back, never prompt-stuff* — the engine supplies the geometry; the model only narrates it.

> **Relationship to `PREDICATE_SPECS.md`.** This document is the *data-architecture* layer:
> the return type of `certified_claims`, the canonical evidence-bundle shape, and the packet
> serialization. The *per-predicate* detection rules, FEN examples, and each detector's
> evidence fields live in `docs/specs/PREDICATE_SPECS.md` (the predicate-spec library). The two
> agree by construction: every bundle this doc serializes is the dict a predicate's spec in
> `PREDICATE_SPECS.md` defines. Where this doc says "the bundle," `PREDICATE_SPECS.md` says
> "the evidence dict the predicate returns." This doc decides *how the container is shaped and
> shipped*; that doc decides *what each predicate proves and what its bundle contains*.

---

## 1. Problem & goal

Today `certified_claims()` returns a flat `Set[str]` (e.g. `{"fork", "rook_lift"}`). The narrator
gates six claim types on `tag in certified` (narrator.py:202), and that membership test is the
single source of truth for the output fact-gate. But the *evidence* the predicates already
compute is discarded:

- `is_rook_lift` returns `(True, "rook lift to the open d-file")` — the reason string is dropped.
- `is_outpost` returns `(True, [supporter_squares])` — the supporter squares are dropped.
- `creates_fork` / `sets_up_royal_pin` return rich descriptions
  (`"knight on e6 attacks the king on g7 and the queen on c7 (royal fork)"`) — dropped.

`certified_claims` boils each predicate down to a bare boolean and a string tag. The narrator is
then told a fork *exists* but must **compose its own geometry** ("the knight on e6 forks…"),
re-deriving from the `pieces` field facts the engine already proved. That is exactly the
prompt-stuffing the architecture forbids: any geometry the model writes is unverified generation,
even though the engine had the verified string in hand.

**Goal:** surface each certified tag's evidence bundle (a ready-to-quote string plus structured
squares) to the narrator and the LLM judge, **without changing the `tag in certified` contract**.

---

## 2. The evidence bundle — canonical shape

One bundle per certified tag. A plain JSON-native `dict` (no new class at the predicate layer):

```python
# Canonical shape of one evidence bundle.
{
    "tag": "fork",                       # the GATED_TAGS member (self-describing in JSON)
    "evidence": "knight on e6 attacks the king on g7 and the queen on c7 (royal fork)",
    "squares": ["e6"],                   # primary actor square(s); may be []
    # ...any further structured keys the predicate's PREDICATE_SPECS entry defines
    #    (e.g. outpost adds "supporters"; pin/skewer add attacker/pinned/behind squares).
}
```

**Contract for every bundle (the only hard rules):**

- **`tag`** — required; equals the `GATED_TAGS` member and the dict key under which the bundle is
  stored. Redundant with the key by design, so a bundle copied out of context stays identifiable.
- **`evidence`** — required, always present: the ready-to-quote string. For predicates that
  already return a description string (rook lift, fork, royal pin), this *is* that string verbatim.
  For predicates that return a bare `bool` (`mate_in_one_threat`, `passed_pawn`) or structured
  detail instead of a string (`outpost` → supporter squares), `certified_claims` **synthesizes** a
  short string (see §4) — these are the only synthesized strings, and they are intentionally
  conservative.
- **Structured square keys** (`squares`, and predicate-specific keys like `supporters`,
  `attacker_square`, `pinned_square`, …) — optional. Absent keys simply do not serialize, mirroring
  the existing "guard emission on truthiness" convention in `_move_to_dict`. Their exact set per tag
  is whatever that tag's `PREDICATE_SPECS.md` entry specifies; this doc does not constrain it beyond
  "all squares are `chess.square_name` strings, all piece names from `PIECE_NAMES`."

The bundle is **string-first**: the narrator's job is to *quote* `evidence`, not to interpret the
square arrays. The structured arrays exist for the LLM judge and for future deterministic checks,
not for prose composition.

---

## 3. Return type of `certified_claims` — decision

**Decision: return a plain `Dict[str, Dict[str, object]]` mapping `tag -> bundle`.**

This is the simplest viable container that carries the evidence while preserving the membership
contract, for five concrete reasons:

1. **`in` works for free.** `"fork" in some_dict` tests keys — exactly the behavior the narrator
   relies on. No `__contains__` to write, no dataclass to import, no delegation bug to introduce.
2. **`sorted(...)` works for free.** `sorted(some_dict)` returns sorted keys, so the serialization
   line `d["certified"] = sorted(claims)` produces the **identical** sorted tag-string list it
   produced over the old `Set[str]` — byte-for-byte (§6).
3. **JSON-native.** Bundles are dicts; the container is a dict; `json.dumps` handles it directly.
   A dataclass would need `asdict()` or a custom encoder at every serialization site.
4. **One concept, not two.** The key-set *is* the tag-set — they cannot drift apart. A dataclass
   holding `tags: Set[str]` + `evidence: dict` would force every reader to know which field carries
   membership and risks the two falling out of sync.
5. **Gradual, honest typing.** `from __future__ import annotations` is already in `factgate.py`, so
   the new return annotation is a string at runtime: no import cost, no runtime type enforcement to
   break old callers.

**Rejected alternative — a `CertifiedClaims` dataclass** with a custom `__contains__`/`__iter__`
delegating to a `tags` field: it re-implements by hand the membership and iteration a `dict` gives
natively, adds a class and an import, and needs `asdict()` to serialize. Over-engineered for this
need.

**Rejected alternative — keep `Set[str]` and ship evidence in a separate parallel structure**
(the shape an early reading of `PREDICATE_SPECS.md` might suggest): two structures keyed by the
same tags that can diverge, and a second function/return value threaded through the same call site.
The single-dict return collapses both into one object whose keys *are* the allow-set.

**Backward-compat guarantee, stated precisely.** `certified_claims(...)` returns a dict whose
**keys are exactly the strings the old `Set[str]` contained**. Therefore:

- `"fork" in certified_claims(...)` → unchanged.
- `for t in certified_claims(...)` → iterates the same tag strings.
- `sorted(certified_claims(...))` → the same sorted tag list.
- `len(...)`, `set(...)`, `bool(...)` → all unchanged (an empty dict is falsy, like the empty set).

**The one place this is NOT free: direct equality to a set.** `{} == set()` is `False`. Any caller
that compares the *whole return value* to a set (rather than testing membership / iterating /
`bool`-checking) must change. Exactly one such caller exists today — a unit test — and §7 fixes it.
This is the only behavioral edit the return-type change forces outside `factgate`/`narrator`.

---

## 4. `factgate.py` changes

### 4.1 Imports

- Add `Dict` to the typing import (today it is `from typing import List, Optional, Set, Tuple`;
  `Set` stays — `GATED_TAGS` consumers and the synthesized-string code still use set semantics).
- Add `PIECE_NAMES` to the existing `from analyzer import (...)` block (used to name the outpost
  piece in the synthesized string). It is already exported by `analyzer.py:211`.

### 4.2 `certified_claims` — build a bundle from each predicate's existing return

The function keeps its `_safe(...)` + `... and ...[0]` guard structure verbatim; the only change is
that each branch that fires now also reads the predicate's `[1]` (or synthesizes a string) and
stashes a bundle under the tag key instead of `tags.add(tag)`.

```python
def certified_claims(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    mover_color: bool,
) -> Dict[str, Dict[str, object]]:
    """Run every predicate for one ply and return a mapping of proven claim TAG ->
    evidence bundle. The KEY SET is the old allow-set: `tag in certified_claims(...)`
    and `sorted(certified_claims(...))` behave exactly as when this returned Set[str].
    Each bundle is {'tag', 'evidence', + optional 'squares'/predicate-specific keys} —
    the ready-to-quote string the predicate computed plus its structured detail. A quiet
    move returns the empty dict {} (falsy, like the old empty set). Same fail-safe posture
    as before: any predicate exception yields None, drops the tag, and never crashes the report.
    """
    claims: Dict[str, Dict[str, object]] = {}

    def _safe(fn):
        try:
            return fn()
        except Exception:
            return None

    def _mate_threat() -> bool:
        if board_after.is_game_over() or board_after.is_check():
            return False
        probe = board_after.copy()
        probe.push(chess.Move.null())  # opponent "passes" -> mover to move
        return threatens_mate_in_one(probe)

    to_name = chess.square_name(move.to_square) if move else ""

    if _safe(_mate_threat):
        claims["mate_in_one_threat"] = {
            "tag": "mate_in_one_threat",
            "evidence": "threatens mate in one if the opponent does nothing",  # synthesized: bool predicate
            "squares": [],
        }

    rl = _safe(lambda: is_rook_lift(board_before, move, board_after))
    if rl and rl[0]:
        claims["rook_lift"] = {
            "tag": "rook_lift",
            "evidence": rl[1] or "rook lift",          # predicate's reason string
            "squares": [to_name],                       # the lifted rook's destination
        }

    fk = _safe(lambda: creates_fork(board_after, move.to_square, mover_color))
    if fk and fk[0]:
        claims["fork"] = {
            "tag": "fork",
            "evidence": fk[1] or "fork / double attack",   # predicate's description
            "squares": [to_name],                          # the forking piece's square
        }

    rp = _safe(lambda: sets_up_royal_pin(board_after, mover_color))
    if rp and rp[0]:
        claims["royal_pin_setup"] = {
            "tag": "royal_pin_setup",
            "evidence": rp[1] or "pin/skewer winning the queen",  # predicate's description
            "squares": [],
        }

    op = _safe(lambda: is_outpost(board_after, move.to_square, mover_color))
    if op and op[0]:
        supporters = [chess.square_name(s) for s in (op[1] or [])]
        piece = board_after.piece_at(move.to_square)
        kind = PIECE_NAMES.get(piece.piece_type, "piece") if piece else "piece"
        ev = f"{kind} outpost on {to_name}"                # synthesized from squares
        if supporters:
            ev += " supported by the pawn(s) on " + ", ".join(supporters)
        claims["outpost"] = {
            "tag": "outpost",
            "evidence": ev,
            "squares": [to_name],
            "supporters": supporters,
        }

    if _safe(lambda: is_passed_pawn(board_after, move.to_square, mover_color)):
        claims["passed_pawn"] = {
            "tag": "passed_pawn",
            "evidence": f"passed pawn on {to_name}",        # synthesized: bool predicate
            "squares": [to_name],
        }

    return claims
```

Notes:

- **Evidence provenance.** `rook_lift`, `fork`, `royal_pin_setup` quote the predicate's own
  `[1]` string. `mate_in_one_threat` and `passed_pawn` are bare-`bool` predicates with no string,
  so a fixed conservative phrase is synthesized. `outpost` returns supporter *squares*, not a
  string, so its string is synthesized from those squares. These three synthesized strings are the
  only ones a reader will not find inside a predicate.
- **Fail-safe preserved verbatim.** `_safe` still swallows any predicate exception to `None`; the
  `... and ...[0]` guards are untouched; a raising predicate still silently drops its tag. The only
  change inside a firing branch is reading `[1]` and writing a bundle instead of adding to a set.
- **`GATED_TAGS` unchanged.** Still the same 6-tuple; the returned dict's keys are still a subset of
  it. No new tag is introduced here, so no prompt-rule edit is forced by this change.

### 4.3 No compatibility accessor

A `certified_tags() -> Set[str]` helper is **not** added: every caller already works on the dict
directly (§7), and `set(certified_claims(...))` recovers the old view in one call if ever needed.
Adding a second public function for a one-liner would be surface for no benefit.

---

## 5. `narrator._move_to_dict` — serialization & tier

### 5.1 Tier placement (unchanged)

The evidence bundles stay co-located with `certified`, **inside the existing `if tier >= 1:` block**
(narrator.py:440-462). `certified` is already Tier 1+ (Tier 0 is acknowledge-only and skipped);
evidence is pointless without the tag, so it shares the same gate and the same try/except fail-safe.
This respects the tier system exactly — no new field crosses a tier boundary, and Tier 0 payloads
are unchanged.

### 5.2 The edit (drop-in replacement for narrator.py:450-462)

```python
        try:
            from factgate import certified_claims

            claims = certified_claims(
                chess.Board(move.fen_before),
                chess.Move.from_uci(move.uci) if move.uci else chess.Move.null(),
                chess.Board(move.fen_after),
                move.side == "White",
            )
            if claims:
                # Back-compat: the allow-set is still a sorted list of tag strings
                # (claims.keys()), so any consumer testing `tag in certified` is unaffected.
                d["certified"] = sorted(claims)
                # NEW: evidence bundles, tag -> {evidence, squares, ...}. The narrator
                # QUOTES the evidence string instead of composing geometry itself.
                d["certified_evidence"] = {tag: claims[tag] for tag in sorted(claims)}
        except Exception:
            pass
```

Properties:

- **`d["certified"]` is byte-for-byte identical** to today: `sorted(claims)` over the dict yields
  the same sorted key list `sorted(tags)` yielded over the set. Every existing reader (the prompt
  rule, the LLM judge's `certified` reference, the deterministic checkers) is unaffected.
- **`d["certified_evidence"]` is the only new key** — additive, omitted when there are no claims,
  inside the same try/except so a gate error drops *both* keys and never crashes the report.
- The `certified_evidence` value is a `dict[str, dict]`; all leaf values are JSON-native
  (`str` / `list[str]`), so `json.dumps` of the packet stays clean and ASCII (square names and
  piece names are ASCII).

### 5.3 Prompt change (`SYSTEM_PROMPT_BASE`, the fact-gate rule at narrator.py:202)

**Append** to the existing certified-claims rule — do not rewrite it; the whitelist semantics must
stay intact:

> *Addition:* "When you assert one of these certified claim types, a parallel `certified_evidence`
> object gives you the engine's own description of it (an `evidence` string, plus the squares
> involved). **Quote or lightly paraphrase that `evidence` string for the geometry and
> justification — do NOT invent your own squares, piece names, or 'because' for a certified claim;
> the engine has already computed the correct ones.** If `certified_evidence` is present for a tag,
> its `evidence` text is the authoritative description of that tactic. As always, never write a
> field name in the prose."

This converts the gate from "you *may* assert a fork" into "you may assert a fork **and here is
exactly how to describe it**," removing the model's freedom to confabulate the supporting geometry.
It changes no other rule and introduces no new gated tag.

---

## 6. `factcheck.py` — how the LLM judge benefits (no required change)

The LLM judge already receives **the entire fact packet** per move: `build_judge_items` packs
`"facts": pk` (factcheck.py:376) where `pk` is `_move_to_dict`'s output, and `run_llm_judge`
forwards `it["facts"]` verbatim (factcheck.py:449). The judge system prompt already names
`certified` as a truth source (`_JUDGE_SYSTEM`, factcheck.py:350). Therefore:

1. The judge now sees `certified_evidence` **automatically** (it is in `pk`). It can catch a finer
   class of contradiction: prose that asserts a certified fork **on the wrong squares** —
   previously invisible, because the old packet proved only "a fork exists," not "the fork is
   knight-e6 on king-g7." `evidence: "knight on e6 …"` lets the judge flag prose that says "the
   bishop forks."
2. The re-serialization path is also covered: `factcheck.build_fact_packets` (factcheck.py:327-328)
   rebuilds packets by calling the same `_move_to_dict`, so saved-analysis re-checks pick up
   `certified` + `certified_evidence` with no edit.

**Optional, deferred sharpenings (not part of this migration):**

- Extend the `_JUDGE_SYSTEM` example list (factcheck.py:350) to "…says a fork/pin is on squares
  other than those in `certified_evidence`." A prompt-only, fully backward-compatible tweak that
  makes the new evidence actionable for the judge.
- Give the deterministic `check_geometry` detector a structured anchor:
  `certified_evidence[tag]["squares"]` is a clean `list[str]` it could compare against square tokens
  in a sentence, instead of regex-scraping free-form text. Low-priority enhancement.

---

## 7. Migration — every call site

`certified_claims` and the `certified` key are consumed in exactly these places. Each is confirmed
against the source.

| # | Site | Today | Under the dict return | Change needed |
|---|---|---|---|---|
| 1 | `factgate.certified_claims` (factgate.py:235-292) | builds & returns `Set[str]` | builds & returns `Dict[str,dict]`; keys = old tags | **Yes — §4** (core edit) |
| 2 | `narrator._move_to_dict` (narrator.py:450-462) | `tags = certified_claims(...)`; `if tags: d["certified"] = sorted(tags)` | `sorted(claims)` over the dict = same sorted key list; adds `certified_evidence` | **Yes — §5.2** (additive; `certified` output identical) |
| 3 | narrator system prompt (narrator.py:202) | gates the 6 claim types on `tag in certified` | semantics unchanged; gains the evidence-quoting instruction | **Yes — §5.3** (append-only) |
| 4 | `tests/test_factgate.py:119-123` `..._collects_tags` | `tags = certified_claims(...)`; `assert "rook_lift" in tags` | `in` tests dict keys → still passes | **No** (passes unchanged) |
| 5 | `tests/test_factgate.py:126-129` `..._no_false_mate_threat...` | `assert "mate_in_one_threat" not in certified_claims(...)` | `not in` tests dict keys → still passes | **No** (passes unchanged) |
| 6 | `tests/test_factgate.py:132-134` `..._empty_on_quiet_move` | `assert certified_claims(...) == set()` | `{} == set()` is **False** → **fails** | **Yes** — change to `== {}` (or `assert not certified_claims(...)`) |
| 7 | `tests/test_factgate.py:137-141` `..._serialises_ascii` | `json.dumps(sorted(certified_claims(...)))` | `sorted(dict)` = sorted keys → identical JSON, still ASCII | **No** (passes unchanged) — optionally add a sibling test asserting `certified_evidence` is ASCII too |
| 8 | `tests/test_factgate.py:144-151` `..._never_raises...` | calls `certified_claims(...)` for its side effects | still cannot raise (fail-safe intact) | **No** (passes unchanged) |
| 9 | `factcheck.build_fact_packets` / `run_llm_judge` (factcheck.py:324-328, 363-377, 440-459) | forwards `pk` (incl. `certified`) to the judge | forwards `pk` (now incl. `certified_evidence`) verbatim | **No** — packet is opaque to it |
| 10 | `factcheck._JUDGE_SYSTEM` (factcheck.py:350) | references `certified` in prose | `certified` still present & identical | **No** (optional sharpening, §6) |
| 11 | `factcheck` deterministic checkers (`check_geometry` etc.) | read other packet keys; do not read `certified` structurally | unaffected | **No** |
| 12 | `GATED_TAGS` consumers / any `sorted()`/`in` on the collection | iterate/membership | dict supports both natively | **No** |

**Why nothing else breaks:**

- The `certified` JSON value is **identical** (same sorted tag-string list), so the whitelist gate,
  the deterministic checkers, and the judge's existing `certified` logic see exactly what they saw.
- The only behavioral *additions* are the new `certified_evidence` key and the appended prompt
  sentences — both additive, both fail-safe-wrapped, both omitted on a quiet move.
- No new gated tag is introduced, so the `GATED_TAGS`/prompt-rule invariant is untouched.
- An empty result is `{}` — falsy like the old `set()`, so the `if claims:` / `if tags:` guards
  behave identically. The **only** place falsiness is insufficient is `== set()`, fixed in row 6.

---

## 8. What to ship — minimal core

Four edits deliver the whole win, fully backward compatible:

1. **`factgate.py`** — add `Dict` to the typing import and `PIECE_NAMES` to the analyzer import;
   change `certified_claims`'s return from `Set[str]` to `Dict[str, dict]`, stashing each
   predicate's `[1]` (or a synthesized string) into a bundle (§4). The `sorted()`/`in`/`bool`
   contract is preserved because dict keys = the old tag set.
2. **`narrator._move_to_dict` (450-462)** — keep `d["certified"] = sorted(claims)` (unchanged
   output) and add `d["certified_evidence"] = {...}` (§5.2).
3. **`narrator` fact-gate prompt (202)** — append the "quote the `evidence` string, don't invent
   geometry" instruction (§5.3).
4. **`tests/test_factgate.py:134`** — change `== set()` to `== {}` (or `assert not ...`); the other
   four tests pass unchanged. Optionally add a test asserting `certified_evidence` serializes ASCII.

That delivers: certified claims carry the engine's verified geometry, the narrator quotes it instead
of composing it, and the LLM judge automatically sees the richer facts — with **zero** change to
membership semantics, `GATED_TAGS`, the deterministic checkers, or any other call site.

---

## 9. Deferred (separate, additive — specced in `PREDICATE_SPECS.md`)

These are **not** required for the evidence-bundle upgrade and **must not** be bundled into it:

- **New detectors and `MoveAnalysis` fields** (`detect_pin`, `detect_skewer`,
  `detect_discovered_attack`, `detect_back_rank_weakness`, `detect_battery`, structural-weakness
  scans). None exist in `analyzer.py` today (only `detect_double_attack` and
  `detect_royal_alignment`). Each is specced per-predicate in `PREDICATE_SPECS.md`. When added, they
  follow the existing convention: a typed `MoveAnalysis` field defaulting falsy, populated in
  `analyze_pgn`'s second pass, serialized in `_move_to_dict` guarded by `if move.<field>:`. **Shipped
  as informational fields first, they are NOT auto-gated** — exactly like `double_attack` and
  `tactic_setup`.
- **Promoting a new tag into the gate** (e.g. `pin`, `skewer`). A field becomes whitelist-gated only
  by a deliberate, synchronized three-part change: (a) add the tag to `GATED_TAGS`, (b) wire its
  detector into `certified_claims` with its own bundle (per its `PREDICATE_SPECS.md` entry — the
  thin `creates_pin` / `creates_skewer` wrappers returning `(bool, Optional[dict])`), and (c) name
  it in the fact-gate prompt rule at narrator.py:202. Omitting (c) forbids the narrator from
  asserting it. Do this only once a detector is as conservative as `detect_royal_alignment`.
- **Judge-prompt sharpening and `check_geometry` structured anchor** (§6) — both optional,
  prompt/detector-local, fully backward-compatible.

None of these touch the contract this document delivers.

---

## 10. Relevant files

- `C:\Users\詹天哲\Documents\greco\factgate.py` — return-type + bundle build (lines 235-292),
  imports (36, 40-44).
- `C:\Users\詹天哲\Documents\greco\narrator.py` — serialization (450-462), prompt rule (202).
- `C:\Users\詹天哲\Documents\greco\tests\test_factgate.py` — five `certified_claims` tests
  (118-151); line 134 requires the `== set()` → `== {}` edit.
- `C:\Users\詹天哲\Documents\greco\factcheck.py` — no required change; judge flow (327-328, 376,
  449), optional prompt sharpening (350), optional `check_geometry` anchor.
- `C:\Users\詹天哲\Documents\greco\analyzer.py` — `PIECE_NAMES` export (211); home of the deferred
  detectors (§9).
- `C:\Users\詹天哲\Documents\greco\docs\specs\PREDICATE_SPECS.md` — the per-predicate detection
  specs and evidence-dict definitions this doc's bundles conform to.
