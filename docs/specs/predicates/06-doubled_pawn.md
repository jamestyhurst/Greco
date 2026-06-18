# Detection Spec: Doubled Pawns (`doubled_pawn`)

> Status: corrected after adversarial review. Companion to `01-pin.md`, `02-skewer.md`,
> `03-discovered_attack.md`, `05-isolated_pawn.md`. Helper ground truth verified against
> `factgate.py` (`is_passed_pawn` 157–176, `certified_claims` 235–292, `_safe` closure
> 253–257, `GATED_TAGS` 222–229) and `analyzer.py` (`_doubled_files` 420–425,
> `detect_doubled_pawns_created` 428–445). Gating pattern mirrors `passed_pawn` /
> `isolated_pawn`: evaluated at **`move.to_square` for `mover_color`** in `certified_claims`,
> NOT both-colors-whole-board (that was the draft's central error — see §2).

## 1. Expert definition

A **doubled-pawn** condition exists for a side when **two or more of that side's pawns occupy
the same file** (e.g. White pawns on f2 and f4, or after `hxg5` a White pawn ends up on g3
and g5). It is a **structural STATE of the current position**, not an event: it is true for as
long as ≥2 friendly pawns share a file, regardless of which move produced them or how long ago.

A strong coach treats several facets as still "doubled," all of which must be caught:

- **Plain doubled pawns** — exactly two friendly pawns on one file. The canonical case.
- **Tripled (or quadrupled) pawns** — three (theoretically four) friendly pawns on one file.
  A *stronger* form of the same state: tripled IS doubled (≥2 on the file), but the narrator
  must be told it is tripled so the descriptor is accurate.
- **Isolated doubled, supported/connected doubled, doubled passed, hanging-pawn variants** —
  doubling can coexist with isolation, with friendly neighbours, or with passedness. All are
  still "doubled." Those extra features are **additional descriptors**, never preconditions;
  this predicate certifies the doubling claim **alone** and does not assert isolation,
  passedness, connectedness, or weakness.

**Pin independence (anti-false-negative).** A doubled pawn that is **pinned** — absolutely or
relatively — is still doubled. Pin status is a piece-interaction fact, not a pawn-structure
fact, and must never suppress the verdict. (`_doubled_files` already never consults pins; this
is restated so no implementer "guards against" a pinned pawn.)

**Side-to-move independence.** Doubling is a static count over pawn placement in the FEN.
Whose turn it is does not change whether a file is doubled. `board.turn` must **not** be read
— the verdict is byte-for-byte identical for either side to move. (This contrasts with
`mate_in_one_threat`, which is genuinely turn-dependent.)

**Color symmetry / color-by-file independence.** White and Black are assessed by the same
file-count rule (no color- or castling-side asymmetry; file index `f` means the same file for
both colors). A given file can be doubled for White, for Black, for both, or for neither.

**Relation to the existing EVENT field.** `MoveAnalysis.doubled_pawns_created` (populated by
`detect_doubled_pawns_created`, `analyzer.py:428`) tracks the **EVENT** — the move that
*newly* created doubling, via a before/after diff of `_doubled_files`. This predicate
certifies the **STATE** — that doubling exists *now*, irrespective of when it arose. The two
are complementary, not redundant: a position can be doubled with no creation event this ply
(the pawns doubled five moves ago), and a creation event also leaves the state true. Never
gate the STATE predicate on the EVENT field.

## 2. Detection rules (veto-then-confirm)

**Signature — mirror `is_passed_pawn` / `is_isolated_pawn`, NOT a free `(board, color)` form.**

```python
def is_doubled_pawn(board: chess.Board, square: int, color: bool) -> Tuple[bool, dict]:
```

Returns `(False, {})` on any veto and `(True, evidence)` on confirmation (evidence shape in
§5). The `square`/`color` form is mandatory: it is what `certified_claims` already passes to
every per-pawn predicate, lets the evidence name the exact pawn the mover just placed, and
keeps the gating identical to `passed_pawn` (`factgate.py` step 6) and `isolated_pawn`.

**Why `move.to_square` + `mover_color`, NOT "both colors over the whole board"** *(the draft's
core defect)*: `certified_claims` gates `passed_pawn`/`outpost`/`isolated_pawn` at
`move.to_square` for the mover. Evaluating doubling for **both** colors over the entire board
would certify the *opponent's* months-old doubling on an unrelated knight move (a spurious,
un-anchored certification), would have no square to attach evidence to, and would diverge from
every sibling predicate. So this gate certifies only the file of the pawn the mover just
moved. The position-wide both-colors scan is a real and useful capability but is a **separate
field**, not this per-ply gate — see §6.

**Side-to-move independence:** `board.turn` is never read. **Color handling:** only
`board.pieces(chess.PAWN, color)` (friendly pawns of `color`) is counted; enemy pawns never
enter the boolean.

1. **VETO — not a friendly pawn on `square`.** Let `piece = board.piece_at(square)`. Return
   `(False, {})` if **any** of (checked in this order so the `None` test short-circuits before
   attribute access): `piece is None`, `piece.piece_type != chess.PAWN`,
   `piece.color != color`. This single veto disposes of:
   - every empty square and every non-pawn move (the gate simply does not fire),
   - every enemy pawn (wrong `color`),
   - **every promotion landing square** — after promotion the piece on `move.to_square` is a
     Q/N/R/B, not a pawn, so the type check fires and the move is never certified (correct:
     the promoting pawn left the file, possibly un-doubling it; there is no pawn there to be
     doubled),
   - **every castling move** — `move.to_square` holds the king, not a pawn → veto,
   - a null move / missing UCI — `move.to_square` is then meaningless; the piece-at check
     fails closed.

2. **VETO — fewer than two friendly pawns on the board.** If
   `len(board.pieces(chess.PAWN, color)) < 2`, a file count can never reach 2 → return
   `(False, {})`. The cheapest kill; disposes of most late endgames before any per-file work.
   (Strictly subsumed by step 3, but kept explicit per the cheap-first doctrine.)

3. **CONFIRM — the moved pawn's own file holds ≥2 friendly pawns.** Let
   `file_idx = chess.square_file(square)` and count friendly pawns on that file:

   ```python
   same_file = sorted(
       sq for sq in board.pieces(chess.PAWN, color)
       if chess.square_file(sq) == file_idx
   )
   count = len(same_file)            # ≥1 here, since `square` itself holds a friendly pawn
   ```

   Certify **iff `count >= 2`** — i.e. the moved pawn is part of a doubled (or tripled) stack
   on `file_idx`. Equivalent to `file_idx in analyzer._doubled_files(board, color)`; reuse
   `_doubled_files`'s counting idiom rather than re-deriving it, but key on the **moved pawn's
   file** so the certification is anchored to `move.to_square`. If `count < 2`, return
   `(False, {})`.

   - This is correct even when the mover doubled file X while *un-doubling* file Y in the same
     ply (a pawn-trade reshuffle): the static post-move board is authoritative and we only
     assert about the file the moved pawn now sits on. Transient mid-sequence states are never
     consulted.
   - The pawn need not be the one that *created* the doubling — a quiet push of one pawn onto
     a file that already had a friendly pawn, or a recapture landing on such a file, both
     confirm. Long-standing doubling that the mover's pawn merely *joins* or *sits within* is
     still the doubled STATE.

4. **CONFIRM — classify doubled vs. tripled (evidence only, never the boolean).**
   `count == 2 → "doubled"`; `count == 3 → "tripled"`; `count == 4 → "quadrupled"`. The
   boolean is `True` for all `count >= 2`; `count` only shapes the descriptor wording.

**The boolean (`doubled_pawn`) depends ONLY on steps 1–3.** Step 4 enriches evidence and never
changes the verdict.

**Wiring into the fact-gate** (`certified_claims`, `factgate.py:235–292`), under the existing
`_safe` closure so any exception drops the tag rather than crashing the report:

```python
dp = _safe(lambda: is_doubled_pawn(board_after, move.to_square, mover_color))
if dp and dp[0]:
    tags.add("doubled_pawn")
```

Tuple-returning → guard via `dp and dp[0]`, exactly as `is_outpost`/`creates_fork` are guarded
(`factgate.py:274,278`); `_safe` returning `None` falls through harmlessly. Then:

- Add `"doubled_pawn"` to `factgate.GATED_TAGS` (`factgate.py:222`).
- Name it in the fact-gate prompt rule (`narrator.py:202`) — add "**doubled pawns**
  (`doubled_pawn`)" to the whitelist sentence — or the narrator stays forbidden from asserting
  it. **Migration note:** `doubled_pawns_created` is currently mentioned in the *separate*
  `doubles_pawns`-field rule (`narrator.py:196`) as a freely-usable EVENT field; that field is
  unchanged. Adding `doubled_pawn` to the whitelist gates the *new STATE claim* only; the two
  must be reconciled in the prompt so the narrator knows the EVENT field still licenses
  "this move doubled the pawns" and the new tag licenses "these pawns are (already) doubled."

## 3. Positive examples

Each is evaluated as `is_doubled_pawn(board_after, move.to_square, mover_color)` — `square` is
the pawn the mover just placed. (FENs show the post-move position; the mover is the side that
just landed the named pawn.)

1. **White doubled on the c-file after a recapture.** Post-move FEN
   `r1bqkbnr/pp1ppppp/2n5/8/8/2P5/PP1PPPPP/RNBQKBNR b KQkq - 0 1`; the mover (White) just
   played a `bxc3`/`dxc3`-style recapture landing a pawn on **c3**, joining the pawn on c2.
   `square = c3`, `color = WHITE`: c-file holds {c2, c3} → `count = 2` → certified "doubled."
   Classic recapture doubling.

2. **Black doubled on the f-file (Nimzo/Sämisch-type structure).** Post-move FEN
   `rnbqk2r/ppp2p1p/4pp2/8/8/2P2N2/PP1PPPPP/RNBQKB1R w KQkq - 0 1`; Black just played
   `...exf6`/`...gxf6`-style landing a pawn on **f6**, with a pawn already on f7. `square = f6`,
   `color = BLACK`: f-file holds {f6, f7} → certified "doubled" for Black. (Note: the gate
   fires because **Black is the mover** here; the certification is anchored to the moved pawn,
   not to "scan both colors regardless of who moved.")

3. **Tripled pawns (stronger form, still certified).** A side has pawns on c2, c3, c4 and just
   pushed/recaptured the pawn now on **c4** (or any of the three is `move.to_square`).
   `count = 3` → boolean `True`, `descriptor = "tripled"`. Proves tripled is a superset of
   doubled, not a separate exclusion.

4. **Doubled passed pawns in an endgame.** White pawns on g5 and g6, no Black pawn on f/g/h;
   White just played the pawn now on **g6**. `square = g6`, `color = WHITE`: g-file holds
   {g5, g6} → certified "doubled." The coexisting *passed* status is a **separate** claim
   (`passed_pawn`); this predicate certifies the doubling alone, regardless.

5. **Pinned doubled pawn (anti-false-negative).** White pawns on e2 and e4; the e4 pawn is
   relatively pinned to the white queen (or e2 absolutely pinned to the king) by a Black
   rook/bishop on the e-file or a diagonal. White just played the pawn now on **e4**.
   `square = e4`: e-file holds {e2, e4} → certified "doubled." The pin does **not** suppress
   the verdict — pin status is irrelevant to a static pawn-file count.

## 4. Negative / edge cases

1. **Two pawns on adjacent files (e4 and f4) — NOT doubled.** These are a connected
   phalanx/duo, not doubled. The moved pawn's file holds exactly one friendly pawn →
   `count = 1` → not certified. A naive "two pawns near each other" heuristic would wrongly
   fire; keying on same-file count excludes it.

2. **A lone advanced pawn / one pawn per file — NOT doubled.** One pawn on the moved pawn's
   file → `count = 1` → step-3 fails. Doubling needs ≥2 pawns on the *same file*, never pawns
   on the same rank or merely "near" a friendly piece.

3. **Long-standing doubling, no creation EVENT this ply.** The pawns doubled five moves ago
   and nothing changed the file this turn. `detect_doubled_pawns_created` correctly returns
   `None` (no diff), but the STATE predicate **still certifies** `doubled_pawn` if `count >= 2`
   on the moved pawn's file. Absence of a creation event ≠ absence of the doubled state. (The
   per-ply gate naturally fires only when the mover's pawn lands on the doubled file; the
   position-wide variant in §6 would catch doubling on files the mover did not touch.)

4. **A pawn move that DOUBLES one file while UN-doubling another (trade reshuffle).** Evaluate
   the static `board_after` at `move.to_square` only. Certification keys on the file the moved
   pawn now occupies. If that file has ≥2 friendly pawns, certify; transient mid-sequence
   states are irrelevant.

5. **En-passant capture.** After `exd6 e.p.`-style, the capturing pawn sits on its new square
   and the captured enemy pawn was removed from a *different* square. Read the static
   `board.pieces(PAWN, color)` on `board_after`; `board.ep_square` is **never** consulted. If
   the capturing pawn's file now holds ≥2 friendly pawns it is doubled; otherwise not. (No
   special en-passant handling — the FEN already resolved the capture.)

6. **Promotion off a doubled file.** When the back/front pawn of a doubled stack promotes,
   `move.to_square` holds a **piece**, not a pawn → step-1 veto returns `(False, {})`. Correct:
   the promoting pawn left the file (often un-doubling it), and there is no pawn on the landing
   square to be doubled. (Another file might still be doubled, but that is the position-wide
   variant's job, §6 — the per-ply gate at `to_square` does not certify it.)

7. **Zero or one pawn of `color` (deep endgame) — NOT doubled.** Step-2 veto returns
   immediately; avoids per-file work in K+P endings with a lone pawn. (Also caught by step 1
   if `to_square` is not a friendly pawn.)

8. **Empty square / enemy pawn / non-pawn piece / castling on `to_square`.** Step-1 veto fires
   for a square holding no friendly pawn — including the king of a castling move and a piece
   move's destination. The gate simply does not certify these.

9. **"Doubled rooks" / "doubled bishops on a diagonal" — out of scope.** `doubled_pawn` is
   strictly about `chess.PAWN` of `color`. A heavy-piece battery on a file, or two bishops on a
   diagonal, must NOT be certified — only pawns on the same file count.

## 5. Evidence bundle

The predicate returns `(is_doubled: bool, evidence: dict)`. On `False`, `evidence == {}`. On
`True`:

| Key | Type | Value |
|---|---|---|
| `color` | str | `"White"` / `"Black"` (the pawn's owner, derived from `color`). |
| `square` | str | the moved pawn's square name, e.g. `"c3"` (`chess.square_name(square)`). |
| `file` | str | the doubled file letter, e.g. `"c"` (`chess.FILE_NAMES[file_idx]`). |
| `file_index` | int | the doubled file index 0–7 (`file_idx`). |
| `pawn_squares` | list[int] | **sorted** square indices of *all* friendly pawns on `file_idx` (the `same_file` list from §2 step 3, e.g. `[parse_square("c2"), parse_square("c3")]`). The narrator never invents a square. |
| `square_names` | list[str] | human form, `[chess.square_name(s) for s in pawn_squares]`, e.g. `["c2","c3"]`. |
| `count` | int | `len(pawn_squares)` — 2, 3, or 4. |
| `descriptor` | str | `"doubled"` (2) / `"tripled"` (3) / `"quadrupled"` (4). |
| `evidence_str` | str | ready-to-quote, narrator-safe **present-tense STATE** sentence (templates below). Never exposes a tag or JSON key name. |

**`evidence_str` templates — present-tense STATE wording.** Do **NOT** reuse
`detect_doubled_pawns_created`'s string verbatim: that helper emits the EVENT phrasing
`"doubles {side}'s pawns on the {letter}-file ({squares})"` (note the possessive `{side}'s`
and the verb "doubles" — `analyzer.py:444`). The STATE predicate describes an existing
condition, so use the state verb "has":

- **Doubled (`count == 2`):**
  `f"{color} has doubled pawns on the {file}-file ({sq1} and {sq2})"`
  → `"White has doubled pawns on the c-file (c2 and c3)"`.
- **Tripled (`count == 3`):**
  `f"{color} has tripled pawns on the {file}-file ({', '.join(square_names)})"`
  → `"Black has tripled pawns on the f-file (f5, f6, f7)"`.
- **Quadrupled (`count == 4`):** same shape with "quadrupled".

`square_names` is always sorted, so `sq1`/`sq2` are deterministic. (A single per-ply
certification reports one file — the moved pawn's; the multi-file `"; ".join(...)`
join-convention from `detect_doubled_pawns_created`, `analyzer.py:445`, belongs to the
position-wide variant in §6, which can certify several files at once.)

### Serialization (Tier 1+)

The `dict` is the anti-hallucination payload. `certified` itself stays a sorted list of bare
tags (`sorted(tags)`, `narrator.py:450–462`); serialize the evidence dict via the sibling
evidence path inside the `if tier >= 1:` block, alongside `certified`, under an
`evidence`/`certified_evidence` key, wrapped in the same try/except fail-safe. The narrator may
then state the doubling and name the exact file and squares **verbatim from `evidence_str`** —
but only because the tag certifies it — with no derivation of its own.

## 6. Known limitations

- **Per-move, single-file evaluation only.** Wired like `passed_pawn`/`isolated_pawn`,
  `certified_claims` certifies only the file of the pawn on `move.to_square`, for the mover. A
  position may hold doubling the mover did not just touch — the **opponent's** long-standing
  doubling, or a *second* doubled file of the mover's. Those are not certified for *this* ply.
  A position-wide `detect_doubled_pawns(board) -> list[dict]` (both colors, every doubled file,
  multi-file `evidence_str` joined by `"; "`) would catch them all and is the natural sibling
  to `detect_doubled_pawns_created`; it is flagged as a **future field**, not built by this
  per-ply gate. This is the deliberate scope boundary that keeps the gate consistent with the
  other structural-pawn tags rather than the draft's both-colors-whole-board scan.
- **Structural value not assessed.** Certifies *that* pawns are doubled, never whether the
  doubling is a weakness, a strength (controlling key squares, a half-open file for the rook
  behind), or neutral. Any evaluative spin ("these doubled pawns are weak") must come from the
  Stockfish eval / principles corpus, never from this tag.
- **Does not flag isolation, passedness, or backwardness.** Independent features with their own
  detectors (`is_passed_pawn` exists; `is_isolated_pawn` is its own spec/predicate; backward
  has none yet). "Isolated doubled pawns" requires combining this tag with the isolation check
  — out of scope here.
- **No "functional doubling" nuance.** Two pawns on a file about to be un-doubled by a forced
  recapture are still reported as doubled — the predicate is purely static and cannot see one
  move ahead. Intentional (state, not prognosis).
- **Same-file count only — no diagonal/rank concepts.** By design it cannot detect "tripled" on
  a diagonal, heavy-piece batteries, or any non-file pawn relationship; those are different
  terms (see negative example 9).
- **State vs. event "old news."** Because it reports the STATE, it can fire on doubling that
  has existed for many moves. Pairing it with `doubled_pawns_created` (the EVENT) lets the
  narrator distinguish "just doubled" from "long-standing doubling"; this predicate alone
  cannot make that distinction.
- **Quadrupled pawns** are handled by the count logic but effectively never occur; the wording
  falls back to `"quadrupled"` with no special validation.

## 7. Complexity

**Low.** A static count of friendly pawns on a single file of one board — the moved pawn's
file. Reuses the `_doubled_files` counting idiom (`analyzer.py:420–425`) and the per-file
square-collection pattern of `detect_doubled_pawns_created` (`analyzer.py:438–442`), but keyed
on `move.to_square`'s file and wrapped exactly like `is_passed_pawn`/`is_isolated_pawn`
(`board, square, color → Tuple[bool, dict]`). One O(#friendly-pawns ≤ 8) pass; no engine, no
hypothetical pushes, no board copies, no `board.turn` read, no side-to-move dependence, no
line legality to verify (unlike `mate_in_one_threat` or variation re-validation). The only
real design decisions are (a) gating at `move.to_square` for the mover — matching every sibling
structural-pawn tag rather than scanning both colors over the whole board (the draft's error),
(b) present-tense STATE evidence wording distinct from the EVENT helper's possessive "doubles"
string, and (c) reconciling the new STATE tag with the unchanged `doubled_pawns_created` EVENT
field in the prompt. Reusing `_doubled_files`'s logic keeps the allow-set from ever drifting
from the analyzer's own doubled-pawn definition.
