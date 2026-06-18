# Detection Spec: Isolated Pawn (`isolated_pawn`)

> Status: corrected after adversarial review. Companion to `01-pin.md`, `02-skewer.md`,
> `03-discovered_attack.md`. Helper ground truth verified against
> `factgate.py` (`is_passed_pawn` lines 157–176, `certified_claims` 235–292, `GATED_TAGS`
> 222–229) and `analyzer.py` (`_doubled_files` 420–425).

## 1. Expert definition

An **isolated pawn** is a pawn that has **no friendly pawn on either of its two adjacent
files** — anywhere on those files, on any rank. Because no friendly pawn can ever stand
beside it, no friendly pawn can ever defend it: it must be guarded by pieces, and the square
in front of it is a permanent hole the enemy can blockade. This is the structural feature a
coach calls "isolated," independent of whether it is currently weak — it can equally be a
dynamic, space-giving asset (the IQP attacking complex).

The verdict is **pure pawn-structure arithmetic — friendly-file occupancy only.** It does
**not** depend on:

- enemy pawns (they never enter the boolean),
- whose move it is (`board.turn` is never read — the result is byte-for-byte identical
  regardless of side to move),
- the pawn's rank,
- whether the pawn is currently attacked, defended, **pinned** (absolutely or relatively),
  blockaded, or on an open/half-open file.

A **pinned** pawn (relative or absolute pin) is still isolated if its adjacent files are
empty — pin status is a piece-interaction fact, not a pawn-structure fact, and must not
suppress the verdict. (This is an explicit anti-false-negative requirement.)

Recognized variants — all qualify as isolated and are surfaced as evidence sub-attributes:

- **Isolani / isolated queen-pawn (IQP):** an isolated pawn on the **d-file** (the
  most-discussed case in opening theory — Queen's Gambit, Tarrasch, Panov structures). Named
  explicitly because the literature treats it as its own strategic topic. By convention the
  "isolani" label is the d-file only; an isolated e- or c-pawn is isolated but is **not** an
  isolani.
- **Isolated doubled pawns:** two (or more) friendly pawns on the *same* file with **no
  friendly pawn on either adjacent file**. Each pawn of the stack is isolated. A doubled pair
  on, say, c2+c3 with no b- or d-pawn is "isolated doubled pawns" — a notably weak structure.
  The isolation test is satisfied by the same adjacent-file-empty rule; doubling is an
  *additional* aggravating attribute, **never a disqualifier**, and a same-file friendly pawn
  does **not** rescue the pawn from isolation (the own file is not an adjacent file).
- **Isolated passed pawn:** an isolated pawn that is also passed (no enemy pawn ahead on its
  own or adjacent files). Isolation and passedness are independent; flag as a sub-attribute
  when both hold.
- **Edge-file isolani (a- or h-file):** a rook-pawn has only **one** adjacent file. It is
  isolated **iff that single in-range adjacent file** (b- for an a-pawn, g- for an h-pawn)
  has no friendly pawn. Fully valid — never require two adjacent files. (Some beginners
  believe a rook-pawn "can't be isolated"; it can, and this spec certifies it.)

The term applies **symmetrically to both colors** (no color- or castling-side asymmetry: the
file scan and the d-file isolani test are color-independent — file index 3 is the d-file for
White and Black alike). A single position can contain several isolated pawns at once; each is
its own instance.

## 2. Detection rules (veto-then-confirm)

Signature mirrors `is_passed_pawn` / `is_outpost`:

```python
def is_isolated_pawn(board: chess.Board, square: int, color: bool) -> Tuple[bool, dict]:
```

Returns `(False, {})` on any veto and `(True, evidence)` on confirmation (evidence shape in
§5). In `certified_claims` it is evaluated on **`board_after` at `move.to_square` with
`mover_color`** — the pawn the mover just placed/pushed — exactly mirroring how
`passed_pawn` is gated (`factgate.py` step 6).

**Side-to-move independence:** `board.turn` must **not** be read; the verdict is identical
whoever is to move. **Color handling:** the adjacent-file scan looks only at
`board.pieces(chess.PAWN, color)` (friendly pawns of the same `color`); enemy pawns are never
consulted for the boolean.

1. **VETO — not a friendly pawn on the square.** Let `piece = board.piece_at(square)`.
   Return `(False, {})` if **any** of: `piece is None`, `piece.piece_type != chess.PAWN`,
   `piece.color != color`. Evaluate in that order so the `None` check short-circuits before
   any attribute access (identical guard intent to `is_passed_pawn` lines 161–163; that
   helper happens to test color before type, but order is immaterial once `None` is excluded
   first — both attributes are always safe to read on a real `Piece`). This single veto kills:
   - every empty square,
   - every non-pawn piece,
   - every enemy pawn (wrong `color`),
   - **every promotion landing square** — after a promotion the piece on `move.to_square` is
     a queen/knight/rook/bishop, *not* a pawn, so the type check fires and the move is never
     certified `isolated_pawn` (correct: there is no pawn there to be isolated),
   - **every castling move** — `move.to_square` holds the king (or, for the rook component,
     is not where a pawn lands), so the veto fires,
   - **every non-pawn move generally** (the gate simply does not fire for, e.g., a knight
     move).

2. **VETO/SETUP — compute the friendly-pawn file multiset once.** Build, in a single pass
   over friendly pawns, the file→count map (reusing the `_doubled_files` idiom,
   `analyzer.py:420–425`):

   ```python
   friendly_file_counts: Dict[int, int] = {}
   for sq in board.pieces(chess.PAWN, color):
       f = chess.square_file(sq)
       friendly_file_counts[f] = friendly_file_counts.get(f, 0) + 1
   friendly_files = set(friendly_file_counts)   # files occupied by ≥1 friendly pawn
   ```

   This one O(#friendly-pawns ≤ 8) pass yields both the file set (step 3) and the doubling
   count (step 6). Do **not** re-scan the whole board; do **not** consult enemy pawns.

3. **CONFIRM — both in-range adjacent files empty of friendly pawns.** Let
   `file_idx = chess.square_file(square)` and

   ```python
   adj = {f for f in (file_idx - 1, file_idx + 1) if 0 <= f <= 7}
   ```

   `adj` naturally has **one** member for an a-/h-pawn and **two** otherwise — this *is* the
   edge-file rule, no special-casing. The pawn is isolated **iff `adj.isdisjoint(friendly_files)`**
   (no adjacent file carries a friendly pawn). If any adjacent file is occupied by a friendly
   pawn, return `(False, {})`. Otherwise build evidence (§5) and return `(True, evidence)`.

   - The pawn's **own** file (`file_idx`) is deliberately **excluded** from `adj`, so a
     friendly pawn doubled on the *same* file does **not** rescue it — that is precisely the
     isolated-doubled-pawns case.

4. **Sub-attribute — isolani (IQP).** `is_isolani = (file_idx == 3)` (the d-file). Pure file
   check; color-independent; no enemy or rank dependence.

5. **Sub-attribute — isolated passed pawn.** Call the existing
   `is_passed_pawn(board, square, color)` verbatim (`factgate.py:157`) on the **same board
   and same `color`** and record its boolean as `is_passed`. Do **not** duplicate its
   enemy-pawn-ahead logic. (`is_passed_pawn` is also side-to-move independent, so the
   composition stays static.)

6. **Sub-attribute — isolated doubled pawns.** From step 2,
   `count = friendly_file_counts.get(file_idx, 0)` (always ≥1 here, since the square holds a
   friendly pawn). If `count >= 2`, set `is_doubled = True` and collect the **sorted**
   square names of friendly pawns on `file_idx`:
   ```python
   doubled_squares = sorted(
       chess.square_name(sq)
       for sq in board.pieces(chess.PAWN, color)
       if chess.square_file(sq) == file_idx
   )
   ```
   (Equivalent to `file_idx in _doubled_files(board, color)`; prefer reusing the count from
   step 2 to avoid a second scan.)

**The boolean certification (`isolated_pawn`) depends ONLY on steps 1–3.** Steps 4–6 enrich
the evidence bundle and never change the True/False verdict.

## 3. Positive examples

1. **Classic IQP (isolani), White d4.** FEN
   `rnbqkb1r/pp3ppp/4pn2/8/3P4/2N2N2/PP3PPP/R1BQKB1R w KQkq - 0 7`.
   White pawns: a2, b2, d4, f2, g2, h2. The c- and e-files carry no White pawn →
   d4 is isolated; `file_idx == 3` → `is_isolani = True`. The textbook
   Queen's-Gambit-structure isolani. (Black's pawns a7,b7,e6,f7,g7,h7 are not under test.)

2. **Edge-file isolated a-pawn, Black, side-to-move = Black.** FEN
   `8/p7/8/8/8/5k2/5P2/6K1 b - - 0 1`. Black's a7: the only in-range adjacent file is b,
   which has no Black pawn → isolated. Demonstrates (a) the single-adjacent-file rule for
   rook-pawns and (b) side-to-move independence — the verdict would be the same with `w` to
   move.

3. **Isolated doubled pawns, White on the c-file.** FEN
   `6k1/8/8/8/2P5/2P5/6PP/6K1 w - - 0 1`. White pawns c3 and c4 (plus g2, h2): the b- and
   d-files are empty of White pawns → **both** c-pawns are isolated. For the c4 pawn,
   `is_doubled = True`, `doubled_squares = ["c3", "c4"]`. The c4 pawn being "supported" by c3
   does **not** count — same file is not an adjacent file. (Per the per-move limitation in §6,
   a single ply certifies only the c-pawn actually on `to_square`.)

4. **Isolated passed pawn, White e5.** FEN `8/6k1/8/4P3/8/8/6PP/6K1 w - - 0 1`.
   White pawns: e5, g2, h2. The d- and f-files are empty of White pawns → e5 is isolated; and
   no Black pawn exists anywhere → `is_passed_pawn` returns `True` → `is_passed = True`. An
   isolated passed pawn.

5. **Black isolani after a capture sequence.** FEN
   `r2q1rk1/pp3ppp/2n1pn2/8/3p4/2N2N2/PP2BPPP/R1BQ1RK1 w - - 0 11`. Black pawns:
   a7, b7, d4, e6, f7, g7, h7. The c- and e-files carry no Black pawn (e6 is on the e-file,
   so the e-file is NOT empty for Black — recheck): Black has a pawn on e6, so the e-file
   **is** occupied by a Black pawn. Therefore d4 has a friendly pawn on the adjacent e-file
   → **NOT isolated.** *(This corrects the draft, which wrongly listed this as a positive: the
   e6 pawn makes d4 not isolated. See negative example 7.)*

5'. **Black isolani (corrected positive).** FEN
   `r2q1rk1/pp3ppp/2n2n2/8/3p4/2N2N2/PP2BPPP/R1BQ1RK1 w - - 0 11` (the e6 pawn removed).
   Black pawns: a7, b7, d4, f7, g7, h7. The c- and e-files carry no Black pawn → Black's d4 is
   isolated; `is_isolani = True`, `color = BLACK`. Confirms color symmetry with example 1.

6. **Pinned pawn is still isolated.** FEN `4k3/8/8/8/1b6/8/3P4/4K3 w - - 0 1`.
   White's d2 is **absolutely pinned** by the Bb4 against Ke1 (it cannot move). Adjacent files
   c and e have no White pawn → d2 is isolated regardless of the pin. Confirms pin status is
   irrelevant to the structural verdict (anti-false-negative guard).

## 4. Negative / edge cases

1. **Backward pawn (looks weak, is NOT isolated).** FEN `8/8/8/8/1p6/1P6/P7/6K1 w - - 0 1`.
   White's b3 has a friendly a2 pawn on the adjacent a-file. Backward and weak, but **not
   isolated** — an adjacent file is occupied. Isolation is file occupancy, not
   "currently undefendable by a pawn."

2. **Doubled but NOT isolated.** FEN `6k1/8/8/8/8/1PP5/1P4PP/6K1 w - - 0 1`. White's c-pawns
   are doubled (c3 has no second c-pawn here, so re-state): White pawns b2, b3, c3, g2, h2.
   The b-file (adjacent to c) carries White pawns → the c3 pawn is **not** isolated. Doubled ≠
   isolated; only doubling *with both adjacent files empty* qualifies (contrast positive
   example 3).

3. **Pawn defended right now by a friendly pawn.** A pawn currently protected by a neighbor
   (e.g. d4 protected by c3) has a friendly pawn on an adjacent file → never isolated.
   Conversely, a pawn that *happens* to be undefended this instant is isolated **only if** the
   adjacent files are structurally empty. Transient defense is irrelevant; only file occupancy
   matters.

4. **Hanging pawns / half-isolated.** Hanging pawns (e.g. White c- and d-pawns abreast with no
   b- or e-pawn) are **each NOT isolated** — c has d on an adjacent file and d has c on an
   adjacent file, so they mutually satisfy "adjacent file occupied." A distinct structure; do
   **not** certify `isolated_pawn` for either. This is the most common false-positive trap and
   is correctly excluded by testing adjacent (not own) files.

5. **Empty square / enemy pawn / non-pawn piece / promotion / castling on the square.** The
   step-1 veto returns `(False, {})` for a square holding no pawn, an enemy pawn (wrong
   `color`), a non-pawn piece, a just-promoted piece (no longer a pawn), or a king/rook from a
   castling move. Guards `certified_claims` evaluating `move.to_square` after any non-pawn or
   promotion move — the gate simply does not fire.

6. **Edge pawn whose sole neighbor is occupied.** FEN `8/p7/1p6/8/8/8/8/6K1 b - - 0 1`.
   Black's a7 has a Black pawn on b6 (the only in-range adjacent file) → **not** isolated.
   Confirms the a/h-file rule rejects when the single neighbor file is occupied.

7. **Central pawn with one adjacent file occupied (the draft's mis-classified case).** FEN
   `r2q1rk1/pp3ppp/2n1pn2/8/3p4/2N2N2/PP2BPPP/R1BQ1RK1 w - - 0 11`. Black has a pawn on e6, so
   the e-file is occupied; Black's d4 therefore has a friendly pawn on an adjacent file →
   **NOT isolated.** A single occupied adjacent file is enough to disqualify — both directions
   need not be empty, but **every in-range adjacent file must be**.

8. **En-passant artifact.** Isolation is read from the static post-move board. After an
   en-passant capture, `move.to_square` holds the capturing pawn (still a pawn, on its new
   square) and the captured enemy pawn has been removed from a *different* square; the
   predicate simply reads the resulting `board.pieces(PAWN, color)`. The FEN's ep-square is
   never consulted. If the capturing pawn's adjacent files are empty of friendly pawns, it is
   isolated; otherwise not.

## 5. Evidence bundle

The predicate returns `(is_isolated: bool, evidence: dict)`. On `False`, `evidence == {}`. On
`True`:

| Key | Type | Value |
|---|---|---|
| `square` | str | pawn's square name, e.g. `"d4"` (`chess.square_name(square)`). |
| `color` | str | `"White"` or `"Black"` (the pawn's owner, derived from `color`). |
| `file` | str | file letter, e.g. `"d"` (`chess.FILE_NAMES[file_idx]`). |
| `adjacent_files` | list[str] | the in-range adjacent file letters proven empty of friendly pawns — `["c","e"]` for a d-pawn, `["b"]` for an a-pawn, `["g"]` for an h-pawn. Sorted, deterministic. |
| `is_isolani` | bool | `True` iff `file_idx == 3` (d-file). Licenses the word "isolani." |
| `is_doubled` | bool | `True` iff ≥2 friendly pawns share `file_idx`. |
| `doubled_squares` | list[str] | sorted square names of those pawns, e.g. `["c3","c4"]`; `[]` when `is_doubled` is `False`. |
| `is_passed` | bool | `True` iff `is_passed_pawn(board, square, color)` also holds. |
| `evidence_str` | str | a ready-to-quote, narrator-safe sentence built **deterministically** from the above (templates below). Never exposes a tag or JSON key name. |

**`adj_letters` joiner (deterministic):** join `adjacent_files` as
`"{a}-file"` for one file, or `"{a}- or {b}-file"` for two (the two letters in sorted order).
So `["c","e"] → "c- or e-file"`, `["b"] → "b-file"`.

**`evidence_str` templates** (compose by attribute; use `square_name` / `FILE_NAMES`
conventions; never emit a field name):

- **Base:** `"the {color} pawn on {square} is isolated — no {color} pawn stands on the
  {adj_letters} to support it"` → e.g. `"the White pawn on d4 is isolated — no White pawn
  stands on the c- or e-file to support it"`; for an a-pawn → `"... no Black pawn stands on
  the b-file to support it"`.
- **Isolani (when `is_isolani`):** append `" — an isolated queen-pawn (isolani)"`.
- **Doubled (when `is_doubled`):** append `" — isolated doubled pawns on the {file}-file
  ({doubled_squares joined by ' and '})"`, e.g. `"isolated doubled pawns on the c-file (c3 and
  c4)"`.
- **Passed (when `is_passed`):** append `" — an isolated passed pawn"`.

### Wiring into the fact-gate

1. Add a new `is_isolated_pawn(board, square, color) -> Tuple[bool, dict]` to `factgate.py`.
2. In `certified_claims` (`factgate.py:235–292`), add, after the `passed_pawn` block, wrapped
   in the existing `_safe` closure:
   ```python
   ip = _safe(lambda: is_isolated_pawn(board_after, move.to_square, mover_color))
   if ip and ip[0]:
       tags.add("isolated_pawn")
   ```
   (Tuple-returning → guard via `ip and ip[0]`, exactly as `is_outpost`/`creates_fork` are
   guarded; `_safe` returning `None` falls through harmlessly.)
3. Add `"isolated_pawn"` to `factgate.GATED_TAGS` (`factgate.py:222`).
4. Name it in the fact-gate system-prompt rule at `narrator.py:202` (add "an **isolated
   pawn** (`isolated_pawn`)" to the whitelist sentence), or the narrator stays forbidden from
   asserting it.
5. **Evidence payload (Tier 1+).** The `dict` is the anti-hallucination payload. Serialize it
   via a sibling evidence path in `_move_to_dict` (inside the `if tier >= 1:` block,
   `narrator.py:440–462`, alongside `certified`), under an `evidence`/`certified_evidence`
   key, wrapped in the same try/except fail-safe. The narrator may then state the isolated
   pawn, name the isolani, or note the doubled/passed character **verbatim from
   `evidence_str`** — but only because the tag certifies it. `certified` itself stays a sorted
   list of bare tags (`sorted(tags)`); the dict rides alongside.

## 6. Known limitations

- **Per-move, single-pawn evaluation only.** Wired like `passed_pawn`, `certified_claims`
  evaluates isolation only at `move.to_square`. A position may contain isolated pawns the
  mover did **not** just touch (an opponent's long-standing isolani; the *other* pawn of an
  isolated doubled pair). Those are not certified for *this* ply. A position-wide
  `detect_isolated_pawns(board) -> list[dict]` would catch them all but is a larger surface
  than the per-move gate; flagged as a future field, not built here.
- **Structure, not evaluation.** The detector certifies the *structural fact*, not its
  goodness. An IQP can be a strength (dynamic, attacking) or a weakness (endgame target); the
  boolean says nothing about which. "Weak" vs "strong" narration must come from the Stockfish
  eval / phase, never from this predicate.
- **No blockade / target-square / attacker-count analysis.** It does not check whether the
  square in front is blockaded by an enemy piece, nor whether the pawn is attacked more times
  than defended — the classic "why an isolani is weak" facts. Those are separate predicates.
- **Move-to-square assumption.** If one move both relieves one pawn's isolation and creates
  another's, only the just-moved pawn is assessed this ply; neighbors whose isolation status
  changed are not re-checked.
- **Promotion squares never certify.** A promotion replaces the pawn with a piece, so the
  promotion's `to_square` always vetoes at step 1 — by design, not a bug (there is no pawn
  there to be isolated). The *underlying* pawn structure change is read normally on subsequent
  plies.
- **Edge-pawn semantics are by-design, not a bug.** An a-/h-pawn needs only its single
  in-range neighbor file empty. Intentional inclusivity matching expert usage; do not "fix"
  it to require two files.

## 7. Complexity

**Low.** Pure pawn-structure arithmetic over `board.pieces(chess.PAWN, color)`: one
O(#friendly-pawns ≤ 8) pass to build the friendly file→count map, then a constant-time
disjointness check of one or two adjacent files. No enemy pawns, no attack maps, no engine, no
board copies or hypothetical pushes, no `board.turn` read, no side-to-move dependence. It
reuses established idioms (`_doubled_files`-style counting per `analyzer.py:420`, and
`is_passed_pawn` for the passed sub-attribute, `factgate.py:157`) and adds no new external
dependency. The only subtlety is conceptual, not computational — excluding the
doubled-but-adjacent and hanging-pawn look-alikes, and **not** letting pin/defense/blockade
status suppress the verdict — and that falls out of testing the *adjacent* files (not the own
file) against the friendly-file set. Comparable in cost to `is_passed_pawn`; cheaper than
`is_outpost` (no attacker enumeration).
