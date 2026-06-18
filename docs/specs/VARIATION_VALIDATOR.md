# Variation Validator Reframe — Design Spec

**File targets:**
`C:\Users\詹天哲\Documents\greco\outputs.py` (the validator + its call site),
`C:\Users\詹天哲\Documents\greco\factcheck.py` (the `check_variations` wrapper + reusable `bind_span_to_ply`),
`C:\Users\詹天哲\Documents\greco\narrator.py` (the IRON-RULE prompt rule at line 218).

**Status:** design only — no code written.
**Date:** 2026-06-15.

---

## 1. The reframe in one sentence

Today's validator (`find_unverified_variation_moves`, `outputs.py:364-398`) treats a parenthetical
line as valid **only if every SAN token already appeared verbatim in some engine PV**. The new
default is the opposite: a parenthetical line — including a *counterfactual* the engine never
pre-analyzed ("if Black had not played ...f6, White would have had Qxg7#") — is **valid if it is a
legal move sequence from a plausible branch position**, whether or not Stockfish pre-computed it.
The validator fires **only** when *no* legal anchoring of the line exists anywhere, i.e. genuine
confabulation or a move that is illegal in every candidate position.

This moves from a **token-membership test** to a **legality-replay test**. The instructive
counterfactual is a feature Greco is supposed to have; it is currently suppressed by a validator
written for a narrower anti-hallucination goal.

---

## 2. Ground truth (verified against the live code)

There is **zero positional anchoring** in the current function. All SAN tokens are pooled flat.

- **The allowed-set is built ply-agnostically** (`outputs.py:377-383`): `for m in game.moves:
  allowed |= _san_tokens(...)` ORs every ply's tokens — played move, `best_line_san`,
  `refutation_line_san`, each alternative's `pv_numbered`/`pv_san` — into one flat `set` of bare
  SAN strings. No FEN is read in the function; `fen_before`/`fen_after` never appear. A `Nf3` from
  move 1 and a `Nf3` from move 30 are indistinguishable once pooled.
- **The decisive check is pure set membership** (`outputs.py:395`): `if tok not in allowed and tok
  not in seen`. `tok` is a bare SAN string tied to no board, ply, or position.
- **The move number inside the paren is a trigger gate, not an anchor** (`outputs.py:392`):
  `re.search(r"\d+\.(?:\.\.)?\s*[OKQRBNa-h]", paren)` only decides *whether to inspect the paren*.
  The captured number is discarded; the branch position is never reconstructed.

Consequence: the current check catches only **wholly-confabulated SAN strings**. It cannot catch a
real token in the wrong position, an illegal sequence assembled from individually-real tokens, or a
move illegal in the specific branch position — and, fatally for the feature James wants, it
**wrongly flags every legal instructive counterfactual the engine did not pre-analyze.**

The building blocks for the fix already exist and are currently ignored:
- per-ply `fen_before`/`fen_after` on every `MoveAnalysis` (`analyzer.py`);
- `chess` already imported in `factcheck.py:34`;
- `bind_span_to_ply` (`factcheck.py:113-133`), which binds a *prose* sentence to a ply via the
  **bold** move regex `_BOLD_MOVE_RE` — but is **not wired into the variation path**;
- `_HYPOTHETICAL_RE` (`factcheck.py:60`: `\b(if|would|could have|were to|instead|had )\b`,
  case-insensitive);
- the `chess.Move.null()` turn-pass idiom used by `factgate._mate_threat` (`factgate.py`).

### 2.1 Two integration facts the implementation MUST respect (do not skip)

These are easy to get wrong and would silently break the reframe:

1. **The variation path does NOT flow through the sentence-skip loop.** `verify_report`
   (`factcheck.py:301-321`) iterates sentences and `continue`s on any sentence matching
   `_HYPOTHETICAL_RE` or starting with `(` (line 311) — so hypothetical prose is never checked as a
   played-board claim. But `check_variations` (line 320) is called **separately on the whole
   `report_md`**, bypassing that skip. The new validator therefore receives the raw report text and
   must do its own span extraction and its own hypothetical detection — it cannot lean on the
   sentence loop having already filtered anything.

2. **`_BOLD_MOVE_RE` matches BOLD references only** (`factcheck.py:59`: `\*\*\s*(\d+)(\.\.\.|\.)
   ...\*\*`). Move numbers **inside a parenthetical variation are never bold** (the prompt at
   `narrator.py:220` forbids bold inside variations). Therefore:
   - The **in-paren** anchor parse (Stage 3a primary) must use a **plain** number+SAN scan
     (`_SAN_RE` from `factcheck.py:58` plus a bare `(\d+)(\.\.\.|\.)` regex), **never**
     `_BOLD_MOVE_RE`.
   - `_BOLD_MOVE_RE` is correct **only** for the sentence-binding *fallback* (Stage 3a fallback),
     because the *game* move the surrounding sentence is about **is** bold.
   Conflating these two is the single most likely implementation bug; keep them separate.

---

## 3. The hard problem, stated honestly

A parenthetical branches from *some* board position, and that position is genuinely ambiguous in
free text:

1. **The branch ply is implicit.** A paren near move 24's prose need not name where it branches.
2. **Counterfactuals branch from a position the move number does not name.** "If Black had **not**
   played 24...f6, White would have had **Qxg7#**" branches from the position **before** 24...f6 —
   `fen_before` of that ply — and the first "move" of the line is *White* to move in a position
   where it was nominally Black's turn.
3. **Before-vs-after is ambiguous.** A continuation line ("25. g5 ...") branches *after* the move it
   comments on; an "instead of" / "if not" line branches *before* it. Prose does not reliably say
   which.
4. **Side-to-move ambiguity.** A counterfactual that removes a move leaves the *other* side to move,
   which may not match the printed move number's side.

No single deterministic parse resolves all four. The design is therefore **staged and tolerant**:
build a small ranked set of candidate branch positions and **accept the line if ANY candidate yields
a fully-legal replay.** Acceptance is generous by construction; rejection requires that *every*
reasonable anchoring fail. That asymmetry is what guarantees a legitimate counterfactual survives.

---

## 4. Design overview

```
parenthetical span
   │
   ├─ (1) move-bearing variation notation, OR a hypothetical-flagged paren?  ── no ─→ ignore
   │        yes
   ├─ (2) parse ORDERED (number?, side_hint?, san) tokens; note if any SAN is malformed
   │
   ├─ (3) build CANDIDATE BRANCH POSITIONS — a small ranked set of chess.Boards
   │
   ├─ (4) for each candidate (on a fresh .copy()): replay the SAN sequence via board.parse_san
   │        accept on FIRST candidate that replays the WHOLE sequence legally
   │
   └─ (5) decide:
            • any candidate fully legal                       → VALID  (counterfactual survives)
            • no candidate legal, but line == an engine PV     → VALID  (provenance fallback)
            • a token is MALFORMED / AMBIGUOUS (not parseable) → ABSTAIN → low-confidence note
            • no candidate legal, token is well-formed         → FLAG (illegal / confabulation)
```

The old token-membership function is **kept as a demoted, advisory provenance signal** — "this exact
line is the engine's PV" is still useful — but it **never gates validity**.

---

## 5. Mechanism, stage by stage

### Stage 1 — Span extraction & gate

Keep the span extractor `re.findall(r"\(([^)]*)\)", report_md)` and the existing trigger gate
`re.search(r"\d+\.(?:\.\.)?\s*[OKQRBNa-h]", paren)` (`outputs.py:387-392`). This still correctly
skips decimal evals and prose asides (precision over recall on *what counts as a line*).

**Augmentation for numberless counterfactuals.** Counterfactuals frequently carry no move number on
the first move ("...White would have had Qxg7#"). To catch these, ALSO accept a paren as inspectable
when the **sentence containing it** is hypothetical-flagged. Run `_HYPOTHETICAL_RE`
(`factcheck.py:60`) on the enclosing sentence; if it matches and the paren contains at least one
well-formed SAN token, treat the paren as a line even without a leading move number. This is the one
place we must look outside the parens, because the counterfactual's grammatical setup ("if Black had
not played X") lives in the prose. Use `split_sentences` (`factcheck.py:101`) to map paren→sentence
so the dotted move numbers do not split incorrectly.

### Stage 2 — Parse the line into an ordered token list

The current `_san_tokens` returns a **set** — order-destroying, fatal for replay. Add a sibling that
preserves order and records malformed tokens:

```
_san_sequence(text) -> Tuple[List[Tuple[Optional[int], Optional[str], str]], bool]
    # list of (move_number, side_hint, san) in textual order, plus a `had_unparseable` flag
    # side_hint: 'White' if "N." precedes the SAN, 'Black' if "N...", else None
    # had_unparseable: True if a SAN-shaped run was seen that the token regex could not
    #                  cleanly form (e.g. a typo like "exg5") — drives ABSTAIN, never FLAG
```

Reuse `_SAN_TOKEN_RE` (`outputs.py:354`) for SAN shapes and a bare `(\d+)(\.\.\.|\.)` regex for the
number+side prefix (NOT `_BOLD_MOVE_RE` — see §2.1). Strip `+`/`#` for replay but **retain** them as
a post-hoc check: a line ending in `#` should leave the board in checkmate; a line ending in `+`
should leave it in check. **`side_hint` is advisory only** — it is never used to accept or reject;
legality replay is the sole arbiter (a counterfactual legitimately inverts the printed side).
Promotions (`=Q`) and castling (`O-O`, `O-O-O`) are in the regex and handled natively by
`board.parse_san`.

### Stage 3 — Build candidate branch positions (the core of the fix)

For a parenthetical, produce a **small ranked list of `chess.Board` candidates**. Stage 4 tries them
in order and stops at the first full-legal replay.

**3a. Find the anchor ply.**
- **Primary (in-paren number present):** parse the first `(number, side)` inside the paren with the
  **plain** number regex + `_SAN_RE` (NOT `_BOLD_MOVE_RE`; see §2.1). Map to a ply:
  `ply = 2*(number-1) + (1 if side=='White' else 2)`, then locate the `MoveAnalysis` whose
  `move_no`/`side` match. (This mirrors the match `bind_span_to_ply` does at `factcheck.py:127-129`,
  **minus** the SAN-equality requirement — a variation's first move is not the played move.)
- **Fallback (no in-paren number — the counterfactual case):** bind the **enclosing sentence** to a
  ply via `bind_span_to_ply(sentence, fact_packets)` (`factcheck.py:113-133`), which keys off the
  sentence's **bold** game-move reference (`_BOLD_MOVE_RE` — correct here because the game move *is*
  bold). This is exactly the ply-binding that already exists for prose and is simply not wired to
  variations; wire it here. Note `bind_span_to_ply` needs `fact_packets`, so `check_variations` must
  be given (or build, via `build_fact_packets`) the packets — see §9.3.
- **Last resort (neither yields a ply):** scan **all** plies as candidate anchors. Bounded and only
  ever used to *grant* validity, never to deny it (see §6, asymmetry).

**3b. From anchor ply `p`, enumerate candidate boards.** Each on its own `chess.Board(fen).copy()`:

| # | Board (FEN source) | Covers |
|---|---|---|
| C1 | `game.moves[p].fen_after` | continuation line ("25. g5 ..."), branches *after* the move it follows |
| C2 | `game.moves[p].fen_before` | "instead of" / "better was" replacing move p; **and the "if X had NOT been played" counterfactual** (branch = the position before X) |
| C3 | `game.moves[p+1].fen_before` (== `fen_after` of p, when p+1 exists) | numbering-off-by-one (line labeled one move late) |
| C4 | `game.moves[p-1].fen_after` (== `fen_before` of p, when p-1 exists) | numbering-off-by-one the other way |

C1 and C2 carry almost all real cases; C3/C4 absorb common off-by-one narration. Guard `p±1` for
list bounds. (C3 may equal C1 and C4 may equal C2 by FEN — dedupe candidate boards by FEN string to
avoid redundant replays.)

**3c. Counterfactual turn-flip variant (for C2).** When the enclosing sentence is
hypothetical-flagged, ALSO offer a board with side-to-move flipped via a null move:

```
probe = chess.Board(fen_before_of_p)
try:
    probe.push(chess.Move.null())   # the side that would have played X passes → opponent to move
    candidates.append(probe)
except (ValueError, AssertionError):
    pass                            # a null move is illegal while in check; skip silently
```

This models "Black declines to play X, so White moves" — the position from which `Qxg7#` is legal.
Same idiom `factgate._mate_threat` uses to let the opponent pass. This single candidate is what makes
the canonical "if Black had not played ...f6, White would have had Qxg7#" replay cleanly. Only add it
under the hypothetical flag (a continuation line must not silently skip a tempo).

### Stage 4 — Replay against `legal_moves`

For each candidate board (a fresh `.copy()` per attempt):

```
board = candidate.copy()
for (_, _, san) in sequence:
    try:
        move = board.parse_san(san)        # validates against legal_moves AND resolves SAN
    except ValueError:                      # illegal in THIS position
        first_illegal = san
        break
    except (chess.AmbiguousMoveError, chess.IllegalMoveError, chess.InvalidMoveError):
        # AmbiguousMoveError → underspecified but plausibly legal: do NOT treat as confab.
        # Record as ABSTAIN (see §5 Stage 5) and stop trying to prove this candidate.
        ambiguous_or_malformed = True
        break
    board.push(move)
else:
    # whole sequence replayed legally on this candidate
    if san_seq_ends_with_hash and not board.is_checkmate():
        soft_fail = True        # claimed mate that isn't mate → low-confidence note, NOT a flag
    if san_seq_ends_with_plus and not board.is_check():
        soft_fail = True
    return LEGAL (with soft_fail noted)
```

Notes:
- `board.parse_san` is the right primitive — it validates against `board.legal_moves` *and* resolves
  disambiguation in that exact position, so a real-but-illegal-here token is rejected.
- python-chess raises `ValueError` for a flatly illegal move and the more specific
  `AmbiguousMoveError` / `IllegalMoveError` / `InvalidMoveError` (all `ValueError` subclasses) for
  ambiguity and malformed SAN. **Ambiguity and malformed-SAN are ABSTAIN, not FLAG** — an
  underspecified or mistyped move (e.g. the well-known `exg5` typo) is not proof of confabulation,
  and flagging it would risk the very false positive James forbids. Catch the broad `ValueError` for
  "illegal", but distinguish the ambiguous/invalid subclasses to route them to ABSTAIN.
- Every push is on a `.copy()`, never a shared board (the `analyzer.py` safety idiom).

Accept the line the instant **any** candidate replays fully and legally. Only if **all** candidates
fail does the line proceed to Stage 5.

### Stage 5 — Decide

```
VALID    if any candidate board replays the full sequence legally
VALID    else-if the line's tokens are verbatim-contained in an engine PV for the anchor ply
         (the OLD flat-set test, demoted to provenance fallback — covers a rare legal line our
         candidate set somehow did not anchor)
ABSTAIN  else-if the line contained a malformed or ambiguous SAN token (Stage 2 had_unparseable,
         or Stage 4 ambiguous_or_malformed) → emit a LOW-confidence note, never a strip-eligible flag
FLAG     else  (every token well-formed, no candidate legal, not an engine PV)
                → confabulation or an illegal move
```

Return richer records than a bare token list — a list of `UnverifiedVariation` (or reuse
`Contradiction` directly), each carrying: the offending **paren text**, the **anchor ply** tried, the
**first illegal SAN**, the candidate FENs tried, and a **confidence** (§6). This is the
position-anchored detail the current wrapper laments it cannot produce (`factcheck.py:292`:
`ply=None, move_ref=""`); now `ply` and `move_ref` can be filled.

---

## 6. Failure action: WARN + ANNOTATE, never strip — and never touch a legal line

**Recommendation: warn and annotate only. Do NOT mutate `body`. Stripping stays off.**

1. **A line that replays legally on any candidate → do nothing.** It is valid by James's definition.
   This is the case the old code wrongly flagged; the whole point of the reframe is that these now
   pass silently. Legitimate counterfactuals survive untouched.
2. **A line where NO candidate replays legally AND every token is well-formed → WARN only.** Keep the
   existing non-fatal `stderr` path (`outputs.py:473-485`), upgraded to name the anchor ply and the
   first illegal move, and emit a position-anchored
   `Contradiction(check="variation", ply=<anchor>, move_ref=<first illegal SAN>, confidence="high",
   ...)` through `check_variations`. **Do not mutate `body`.**
3. **A line with a malformed/ambiguous token → ABSTAIN:** emit a `confidence="low"` note and nothing
   else. Never strip-eligible.
4. **Stripping stays off by default.** If ever enabled, it must be gated to **only** category 2
   (well-formed, illegal in every candidate, not an engine PV) — never to a line that merely was not
   in an engine PV, and never to an ABSTAIN. The old docstring's musing that "auto-stripping is a
   possible future hardening" (`outputs.py:375`) is hereby re-scoped to that single category.

**Why warn, not strip, even for the illegal case.** The anchoring layer (Stage 3) is heuristic; a
false "no legal anchoring" is possible if the candidate set missed the true branch (a deeply nested
or oddly-numbered line). Stripping on a heuristic risks deleting correct content — the exact harm
James forbids. Warning surfaces the suspect line to the developer console without touching the
report; a human (or a later, higher-confidence pass) decides. This preserves the codebase's
**precision-over-recall, detect-don't-mutate** posture (`outputs.py:374-376`, `factcheck.py` header)
while flipping the *default* from "engine-membership required" to "legality required."

**Confidence tiering on the flag** (uses the existing `Contradiction.confidence` field,
`factcheck.py:50`):
- `high` — the first SAN is well-formed and illegal on **every** candidate including the all-plies
  sweep, **and** the token appears in no engine PV. Strong confabulation.
- `low` — the line is internally legal but could not be anchored (ambiguous branch), OR a token was
  malformed/ambiguous, OR only the optional mate/check post-check failed. A `low` flag never
  escalates to a strip even if stripping is later enabled.

**Over-acceptance is the deliberate safe direction.** The all-plies sweep (§5 last resort) can accept
a confabulated line that happens to be legal from some unrelated position. Under warn-not-strip this
is harmless: at worst a real confabulation is *not warned about*. We accept that miss in exchange for
**never** deleting or flagging a legitimate instructive line. The asymmetry — generous acceptance,
conservative flagging — is the whole safety guarantee.

---

## 7. Prompt-side change (required, or the feature stays bottled)

The validator is the output gate; the narrator's **IRON RULE** (`narrator.py:218`) is the input gate,
and it currently forbids exactly the feature James wants:

> "THE IRON RULE: every move you write inside a parenthetical variation MUST appear verbatim in that
> move's `variations` data. … If the line you want to show is not in the data, do not write a line."

Loosen it in lockstep with the validator (the matching language at `narrator.py:214-222`):

- **Preferred (unchanged):** when an engine `variations` line makes the point, quote it verbatim —
  still the gold path with the strongest provenance.
- **Newly allowed:** a **legal counterfactual or instructive sideline** may be written even if absent
  from `variations`, **provided every move is legal from the position it branches from.** Spell out
  the branch convention for the model: a continuation branches from the position *after* the named
  move; an "instead of" / "if not" counterfactual branches from the position *before* it.
- **Keep the guardrails:** the **VAGUE-BUT-TRUE** rule (`narrator.py:195`, `:219`) for anything past
  where legality is certain; the **geometry bar** (`narrator.py:222`) — named-square forks still
  require a `double_attack`/`allows_fork` field; the formatting rule (`narrator.py:220`) — variations
  stay *italic, in parentheses*, never bold, never a `### ` header. The freedom is to *write a legal
  line*, not to *invent tactical claims about it.*
- **Correctness note for the spec author:** the in-prompt example at `narrator.py:220` contains the
  string `exg5`, which is malformed SAN. When editing that rule, fix the example to a legal token
  (e.g. `hxg5`/`fxg5` as the position dictates) so the documentation does not model a token that the
  validator will (correctly) abstain on.

Without this edit the reframe is invisible to users — the model never emits the lines, so the
validator never gets to bless them. Ship both changes together with a CHANGELOG note that the
variation policy moved from "engine-membership" to "legal-from-branch."

---

## 8. Worked examples

| Parenthetical (in prose) | Anchor | Winning candidate | Verdict |
|---|---|---|---|
| `*(better was 24...Rf8, when 25. g5 hxg5 26. fxg5 holds)*`, numbered from 24… | ply for 24…Rf8 | C2 (`fen_before` of move 24): play `Rf8`, continue | **VALID** (was valid; still passes) |
| "If Black had **not** played 24...f6, White would have had **Qxg7#**" | sentence binds to ply 24 (f6) | C2 + turn-flip (null move on `fen_before` of 24 → White to move): `Qxg7` legal, mates | **VALID** — counterfactual survives (old code **wrongly flagged** `Qxg7`) |
| `*(25. Nf3?? Qxf3 and Black wins)*`, `Nf3` illegal there (knight pinned) | ply 25 | none — `parse_san("Nf3")` raises `ValueError` on C1–C4 | **FLAG**, `confidence=high`, `move_ref="Nf3"` |
| `*(26. Bxh7+ Kxh7 27. Ng5+)*` — each move appears in *some* engine line, but the *sequence* is illegal here | ply 26 | none replays the ordered sequence | **FLAG** — caught now; invisible to old flat-set test |
| `*(28. Rd1 Rxd1 29. Qxd1)*` — a clean legal line the engine simply did not pre-compute | ply 28 | C1 (`fen_after`): all three legal | **VALID** — old code **wrongly flagged**; central feature win |
| `*(24...exg5 holds)*` — well-intentioned line with a SAN typo | ply 24 | none parses `exg5` | **ABSTAIN**, `confidence=low` — not deleted, not a high confab flag |

The four "old code wrongly flagged" / "ABSTAIN" rows are the legitimate or innocent lines James wants
protected; the two FLAG rows are real confabulation/illegality the old code could not catch. The
reframe stops the false positives and gains true positives.

---

## 9. Implementation plan (files & functions)

### 9.1 `outputs.py`
- Add `_san_sequence(text) -> (List[Tuple[Optional[int], Optional[str], str]], bool)` (ordered parse
  + `had_unparseable` flag) beside `_san_tokens` (~line 359). Keep `_san_tokens` for the provenance
  fallback.
- Add `replay_variation_legal(sequence, candidate_boards) -> (legal: bool, first_illegal_san:
  Optional[str], ambiguous: bool)` implementing Stage 4 on `.copy()` boards.
- Add `validate_parenthetical_variations(report_md, game, fact_packets=None) ->
  List[UnverifiedVariation]` implementing Stages 1–5. Anchor lookup uses
  `game.moves[*].fen_before/fen_after`; the sentence-binding fallback uses `bind_span_to_ply`
  (imported from `factcheck`) and therefore needs `fact_packets` (passed in, or built lazily).
- Keep a thin `find_unverified_variation_moves(report_md, game) -> List[str]` shim **sourced from the
  new legality result**, returning only the first-illegal SAN of each **category-2 (well-formed,
  no legal anchoring, not an engine PV)** line.
  **Breaking-change note:** this changes the function's meaning from "engine-absent" to "illegal".
  Existing tests that assert engine-absent-but-legal tokens are returned **will and must change** —
  that is the bug being fixed, not a regression. Update those tests (see §9.4); do not preserve the
  old semantics under the same name.

### 9.2 `outputs.py:473-485` (call site)
- Update the warning text to print anchor ply + first illegal move; keep it non-fatal
  (`try/except Exception: pass`). **Do not add stripping.**

### 9.3 `factcheck.py:282-295` (`check_variations`)
- Rewrite to consume the new records and fill `ply=<anchor>`, `move_ref=<first illegal SAN>`,
  `confidence=<high|low>` instead of `ply=None, move_ref=""`.
- It must supply `fact_packets` to the validator so the sentence-binding fallback works. Either
  accept `fact_packets` as a parameter (preferred — `verify_report` already has them and can pass
  them at the call site, `factcheck.py:320`) or build them via `build_fact_packets(game, tiers)`
  (`factcheck.py:324`). Passing them through from `verify_report` avoids recomputation.
- `chess` is already imported (`factcheck.py:34`).
- Skip any line routed to ABSTAIN unless emitting it as an explicit `confidence="low"` note.

### 9.4 `narrator.py:214-222` (IRON RULE)
- Loosen per §7. Prompt change — must ship with the validator change. Fix the malformed `exg5`
  example in the same edit. CHANGELOG: "variation policy moved from engine-membership to
  legal-from-branch."

### 9.5 Tests (`pytest`, contract-grade)
Fixtures for the six §8 cases:
- two counterfactuals that must **pass** (continuation `Rf8` line; the `Qxg7#` turn-flip);
- one illegal-move line and one illegal-*sequence* line that must **FLAG** (`confidence=high`);
- one engine-absent-but-legal line that must **pass** (assert it is **never** stripped and **not**
  returned by the `find_unverified_variation_moves` shim);
- one malformed-SAN line (`exg5`) that must **ABSTAIN** (`confidence=low`, not stripped, not a
  high-confidence flag).
- Regression: the canonical "if Black had not played ...f6 … Qxg7#" line passes — the bug this whole
  reframe fixes.
- Update the existing `find_unverified_variation_moves` tests to the new "illegal, not engine-absent"
  semantics (§9.1 breaking-change note).

---

## 10. Honest limitations

- **Anchoring is heuristic.** Stage 3's candidate set is best-effort; a bizarrely-numbered or
  doubly-nested variation could miss its true branch. Mitigation: the all-plies sweep, and —
  decisively — we only ever *warn* on failure, never strip, so a missed anchor degrades to a harmless
  console line, not lost content.
- **Nested parens are not parsed** (the span regex is single-level, unchanged). A line-within-a-line
  is treated as one span; acceptable under warn-don't-strip.
- **Over-acceptance by design.** The sweep can bless a confabulated-but-coincidentally-legal line; we
  accept that miss to guarantee no legitimate line is ever flagged or deleted (§6 asymmetry).
- **"Legal" ≠ "good".** This validator certifies *legality from a plausible branch*, not engine
  soundness. A legal-but-losing instructive line ("if he'd tried this, he loses to…") passes — which
  is correct. Soundness claims still ride the separate `double_attack`/`allows_fork` geometry gate
  (`narrator.py:222`), unchanged.
- **Provenance preserved, not discarded.** "This line is verbatim the engine's PV" remains computable
  (the demoted flat-set test) and is still the highest-trust path; the reframe simply stops treating
  its *absence* as a defect.

---

## Bottom line

Today's validator pools all SAN flat and has no idea where any variation branches — so it both
**wrongly flags** every legal counterfactual the engine did not pre-analyze (killing the feature
James wants) and **misses** truly illegal sequences built from individually-real tokens. The reframe
reconstructs a small ranked set of candidate **branch boards** from per-ply FENs (with a `fen_before`
+ null-move turn-flip variant that specifically captures "if X had *not* been played"
counterfactuals), **replays the line against `board.legal_moves` via `board.parse_san`**, and accepts
if **any** anchoring is fully legal. Malformed or ambiguous SAN **abstains** (never a high-confidence
flag); only a well-formed line with **no** legal anchoring anywhere is flagged. The failure action is
**warn-and-annotate, never strip** — a legitimate instructive line always survives. The companion
IRON-RULE loosening (§7, including fixing the malformed `exg5` example) must ship in the same change,
or the model never writes the lines the new validator was built to bless.

**Relevant files:** `C:\Users\詹天哲\Documents\greco\outputs.py` (validator + call site),
`C:\Users\詹天哲\Documents\greco\factcheck.py` (`check_variations` wrapper + reusable
`bind_span_to_ply`, `_HYPOTHETICAL_RE`, `Contradiction.confidence`),
`C:\Users\詹天哲\Documents\greco\narrator.py` (IRON RULE at line 218).
