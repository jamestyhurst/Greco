# Detection Spec: `discovered_attack` — Discovered Attack (incl. Discovered Check)

> Corrected, adversarially-reviewed spec. Tag: `discovered_attack`.
> Models on `detect_double_attack` / `detect_royal_alignment` in `analyzer.py`; wired through
> `factgate.certified_claims` exactly like `creates_fork` / `sets_up_royal_pin`.
> All board truth is computed in code (data-back doctrine); the narrator only speaks the
> evidence string this predicate returns.

---

## 1. Expert definition

A **discovered attack** occurs when a piece (the **front piece**, A) moves off a line — file,
rank, or diagonal — thereby **unblocking a friendly long-range sliding piece** behind it (the
**rear piece**, B: a queen, rook, or bishop), so that B now bears on an enemy target it could
not reach before A moved. The defining quality is that the new attack is delivered **by a piece
that did not move**: A vacated the line, B does the attacking. A strong coach certifies every
one of these variants under the umbrella term:

- **Plain discovered attack** — B's newly-revealed line hits an enemy piece (queen, rook,
  minor, or even a pawn / a defended piece). The thematic "double" case is when A *itself* also
  makes a threat, but a bare revealed attack with no second threat still *is* a discovered
  attack and is certified.
- **Discovered check** — the revealed line from B hits the enemy **king**. Highest-value
  sub-case: the opponent must answer the check, so A is freed to do almost anything (the
  windmill / desperado engine).
- **Double check** — the strongest sub-case of discovered check: **both** the rear piece B
  (via discovery) *and* the moving piece A (directly) give check at once. The only legal reply
  is a king move.
- **Discovered attack by castling** — on a castling move the rook can be "revealed" onto a file
  while the king (front piece) vacates. Real but rare; **vetoed in v1** (§2 VETO 2, §6) as a
  precision choice, because both royal pieces move and the "front piece vacated a slider's ray"
  framing does not cleanly hold.

The term is fundamentally a **before/after geometry** claim: *a specific friendly slider's
attack reaches a new enemy target because a friendly piece got out of its way* — **not** a
claim that the tactic wins material (that is a separate evaluation question). The inclusive
standard: certify whenever a real newly-revealed attack on a namable enemy target exists —
**including relative-value targets** (a rook revealed onto a defended enemy queen counts) and
**including a pinned rear piece** (the geometry is real; a `can_capture` flag, not a veto,
handles legality) — and including the check / double-check sub-cases — **without** ever
certifying a plain attack that the *moved* piece created by itself.

This corrected spec deliberately differs from the draft on three expert points:
1. **Pinned rear piece is NOT vetoed for material targets.** A discovered attack is about
   geometry; B does not move, so an absolute pin on B does not erase the revealed attack. We
   certify and expose a `rear_can_capture_target` flag instead of dropping the claim (the
   draft's borrowed `detect_double_attack` pin-skip was the dominant **false negative**).
2. **The "was-blocked-before" proof is made explicit and direction-correct**, so we never
   certify a `revealed` set that grew for an unrelated reason (the dominant **false positive**).
3. **King-first ranking is special-cased** because `PIECE_VALUES[KING] == 0` would otherwise
   sort the king *last* (a real ranking bug in the draft's "sort by value, king first").

---

## 2. Detection rules (VETO-THEN-CONFIRM order)

Signature (matches `certified_claims`):
`detect_discovered_attack(board_before, move, board_after, mover_color) -> Optional[str]`.

Handle **both colors uniformly** via `mover_color` (python-chess bool). The rear-piece scan is
over `board_after.pieces(t, mover_color)` for `t in (BISHOP, ROOK, QUEEN)`; targets are enemy
pieces (`color != mover_color`). Side-to-move note: `board_after` already has the turn flipped
to the opponent, so `board_after.is_check()` reports the mover's delivered check — correct for
the discovered-check cross-check. All hypothetical reads are on the supplied boards (no pushes
needed); the whole predicate runs under `certified_claims`'s `_safe` wrapper, so any raise
silently drops the tag.

**VETO 1 — null / no real move.** If `move == chess.Move.null()` **or**
`move.from_square == move.to_square`, return `None`. A discovery requires a piece to vacate a
square.

**VETO 2 — castling routing.** If `board_before.is_castling(move)`, return `None` (v1). Both
royal pieces move; treating the king as a slider-line "front piece" mislabels normal rook
development as a discovery. Known gap (§6). *(Do not rely only on `move` shape — use
`board_before.is_castling(move)`, which is robust to king-takes-own-rook castling encodings.)*

**VETO 3 — collect the vacated squares.** Build the set `vacated`:
- always add `from_sq = move.from_square`;
- if `board_before.is_en_passant(move)`, also add the **captured pawn's square** — the square
  behind `move.to_square` from the mover's perspective:
  `cap_sq = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))`.
  (En passant removes a pawn from a square that is neither `from_sq` nor `to_sq`; a line can be
  opened *solely* by that removal. The draft's colinearity veto on `from_sq` alone would miss
  this — a **false negative**.)

Do **not** add `to_sq` to `vacated`: the mover's piece now occupies it, so it cannot have
opened a line *through* `to_sq` (it is the new blocker, if anything).

**VETO 4 — enumerate candidate rear pieces cheaply.** For each `v_sq in vacated`, build the set
of friendly sliders B in `board_after` colinear with `v_sq`:
- bishop ⇔ `abs(file(b)-file(v)) == abs(rank(b)-rank(v))` and ≠ 0;
- rook ⇔ `file(b)==file(v)` or `rank(b)==rank(v)` (exactly one);
- queen ⇔ either of the above.

Exclude `b_sq == move.to_square` (the moved/promoted piece is never the rear piece) and exclude
`b_sq == v_sq`. If no candidate B exists for any `v_sq`, return `None` — nothing could have been
unblocked.

**VETO 5 — the line from B must actually pass through the vacated square, and B must have been
blocked there *before*.** For each candidate `(b_sq, v_sq)`:
- `v_sq` must lie strictly between `b_sq` and the board edge along B's ray, i.e. on the open ray
  from `b_sq` in the direction of `v_sq`. Verify the squares **strictly between `b_sq` and
  `v_sq` were empty in `board_before`** (so B genuinely bore on `v_sq`):
  `all(board_before.piece_at(s) is None for s in chess.SquareSet(chess.between(b_sq, v_sq)))`.
- In `board_before`, the square `v_sq` itself was **occupied** (by the front piece, or by the
  en-passant-captured pawn) — confirm `board_before.piece_at(v_sq) is not None`. This is what
  makes B's line *blocked before*; without this check a B whose ray was already open would be
  falsely credited (**false positive**).

If either fails, skip this `(b_sq, v_sq)` pairing.

**CONFIRM — B's revealed attack must reach an enemy target *because* `v_sq` was vacated (the
core test).** For each surviving candidate B at `b_sq`:
1. **Existence guard.** B must occupy `b_sq` in *both* boards with the **same color and type**
   (`board_before.piece_at(b_sq)` and `board_after.piece_at(b_sq)` equal in color+type). If B
   was itself just created or moved, skip — `after - before` would be meaningless.
2. Compute `before = board_before.attacks(b_sq)` and `after = board_after.attacks(b_sq)`
   (`SquareSet`). The newly-reachable squares are `revealed = after - before`. If empty, skip.
3. **Causation guard (kills the residual false positive).** A target only counts if it is
   reached *along the ray through `v_sq`*. For each enemy-occupied `t_sq in revealed`, require
   that `v_sq` lies on the segment between `b_sq` and `t_sq`:
   `v_sq in chess.SquareSet(chess.between(b_sq, t_sq))` **or** `v_sq == t_sq` is impossible
   (v_sq was vacated, t_sq is enemy-occupied — they differ), so require
   `v_sq in chess.SquareSet(chess.between(b_sq, t_sq))`. Also require the squares strictly
   between `v_sq` and `t_sq` are empty in `board_after`
   (`all(board_after.piece_at(s) is None for s in chess.SquareSet(chess.between(v_sq, t_sq)))`),
   so the target is the *first* piece B now sees past the vacated square — not something behind
   a different new blocker. This binds the revealed attack to *this* discovery and excludes a
   `revealed` set that grew because of an unrelated board change elsewhere on B's lines.
4. **Target typing.** For each surviving enemy `t_sq`, read `target = board_after.piece_at(t_sq)`
   (`target.color != mover_color`). An enemy **king** → **discovered check**; an enemy
   queen / rook / bishop / knight → discovered attack; an enemy **pawn** → discovered attack
   (inclusive — see §4, ranked last). Record `(b_sq, target.piece_type, t_sq)`.
5. **Moved-piece exclusion (the primary false-positive guard).** The revealed attacker is B, a
   *non-moving* piece. By construction `revealed` is computed from B's own `attacks(b_sq)` and
   we already excluded `b_sq == move.to_square`; assert that exclusion here so a refactor cannot
   reintroduce "the piece that moved now attacks the queen" as a discovery (that is a plain
   attack, §4.1 — `creates_fork` already covers it).
6. **Pin handling — flag, do NOT veto (corrected).** If `board_after.is_pinned(mover_color, b_sq)`:
   - the discovered attack **still exists geometrically** → keep the claim;
   - set `rear_can_capture_target = (target is the enemy king) or (t_sq is on the pin ray, i.e.
     the king, B, and `t_sq` are colinear)`; otherwise `rear_can_capture_target = False`.
   - For a discovered **check** (target = king) the pin is wholly irrelevant — giving check is
     always real. Never let a pin suppress a discovered check.
   This is the key divergence from `detect_double_attack` (which *moves* its forker and so must
   skip pins). A discovery's rear piece does not move; an absolute pin does not erase its
   revealed attack. (`board.is_pinned` only detects king pins, so a *relative* pin to a higher
   piece is invisible to it and never blocks certification — correct for our inclusive standard.)

**CONFIRM-CHECK — discovered check & double check.** If any surviving revealed target is the
enemy king (`enemy_king_sq = board_after.king(not mover_color)`):
- It is a **discovered check**. Cross-validate with `board_after.is_check()` — this must be
  `True`. If for any reason it is `False`, treat the king-target as not-a-check (defensive;
  do not abstain on the *whole* predicate — a non-king target may still certify a plain
  discovered attack).
- **Double check** iff the king is *also* directly attacked by the piece now on `to_sq`:
  `enemy_king_sq is not None` **and**
  `move.to_square in board_after.attackers(mover_color, enemy_king_sq)` **and**
  `b_sq in board_after.attackers(mover_color, enemy_king_sq)` **and** `b_sq != move.to_square`.
  (Two *distinct* mover attackers of the king, one being the moved piece, one being the rear
  slider. Equivalent to `len(board_after.attackers(mover_color, enemy_king_sq)) >= 2` with those
  two members — but test membership explicitly so an unrelated third attacker can't spoof it.)

**RESULT.** Certify `discovered_attack` if at least one rear piece B yields a surviving enemy
target. For the headline, rank targets **king first, then by `PIECE_VALUES` descending**
(`sort key = (0 if pt == chess.KING else 1, -PIECE_VALUES[pt])`) — note `PIECE_VALUES[KING] == 0`,
so a naive value-descending sort would bury the king; the explicit king-first key fixes the
draft's ranking bug. Prefer a discovered **check** over a plain attack, and a **double check**
over a single discovered check. Return the evidence string for the chosen headline (§5); the
thin wrapper returns `(evidence_str is not None, evidence_str)`.

**Helpers to reuse (do not duplicate):** `board.attacks(sq)` + `SquareSet` set-difference for
the before/after diff; `chess.between` + `chess.SquareSet(...)` for ray / clear-line checks
(exact idiom of `detect_royal_alignment`, `analyzer.py:406-411`); `board.is_pinned`,
`board.attackers`, `board.is_check`, `board.is_attacked_by`, `board.king`; `board.is_castling`,
`board.is_en_passant`; `PIECE_NAMES`, `PIECE_VALUES`, `chess.square_name`, `chess.square_file`,
`chess.square_rank`, `chess.square` for evidence strings (same as `detect_double_attack`).

---

## 3. Positive examples

1. **Discovered check (knight reveals rook down a file).**
   A white knight sits on e-file in front of a white rook also on the e-file, the rook aimed at
   the black king on `e8`; the knight jumps to `c4`. `vacated = {e-knight square}`, B = the
   rook, `v_sq` was occupied and the between-squares were empty in `board_before`; in
   `board_after`, `e8 ∈ after - before`, `v_sq` lies between the rook and `e8`, the path
   `v_sq..e8` is clear → discovered check. `board_after.is_check()` is `True`. ✔

2. **Discovered attack winning a defended queen (relative-value target, certify anyway).**
   A knight vacates the `a2–g8` diagonal that a white bishop bears on, revealing the bishop onto
   the black queen on `g8`. Even if the queen is defended, the revealed attack is real:
   `g8 ∈ after - before`, causation guard passes, target = queen → certify. `target_is_defended`
   is set so the narrator can hedge "wins/attacks". ✔ (The draft already accepts this; we keep
   it and add the defended flag.)

3. **Double check.**
   A knight in front of a rook aimed at the enemy king jumps to a square that *also* checks the
   king (e.g. a knight-check from the landing square) while the rook reveals check down the file.
   `board_after.attackers(mover, king)` contains both `to_sq` (knight) and `b_sq` (rook), and
   `b_sq != to_sq` → `is_double_check = True`; headline upgraded to double check. ✔

4. **Discovered attack onto a rook, no check, pinned rear piece (corrected — still certified).**
   A bishop sits in front of a white rook on the f-file; the bishop moves off the f-file,
   revealing the rook onto a black rook on `f8`. Suppose the white rook is *pinned* to its own
   king along a different line. The draft would **veto** this (pin skip) — a false negative.
   Corrected: certify the discovered attack (geometry is real), set
   `rear_can_capture_target = False` (the pinned rook cannot legally leave the pin line to take
   on `f8`), and let the narrator say "reveals an attack on the rook" without claiming it wins
   material. ✔

5. **En-passant-opened discovery.**
   A white pawn captures en passant; the *captured* black pawn vacates a square that lay on a
   white bishop's diagonal, opening the bishop onto an enemy piece. `vacated` includes `cap_sq`
   (the captured-pawn square, computed from `to_sq` file + `from_sq` rank), so VETO 4/5 find the
   bishop and the causation guard binds the revealed attack to `cap_sq`. ✔ (Attribution caveat
   in §6.)

*(FENs are schematic; the predicate certifies from the live `board_before`/`board_after` diff
plus the causation guard, never from SAN.)*

---

## 4. Negative / edge cases

1. **Plain attack created by the moved piece itself.** A knight hops to a square and now attacks
   the enemy queen. The attacker is the *moved* piece (`to_sq`), not a revealed rear piece.
   **Excluded** — the diff is on B's `attacks(b_sq)` for B ≠ moved piece, and `b_sq == to_sq`
   is asserted-out (CONFIRM step 5). This is the dominant thing the term must NOT swallow; it is
   already covered by `fork` / `double_attack` for multi-target cases.

2. **Line already open — no real discovery.** B already attacked the target before A moved.
   **Excluded** — `t_sq ∈ before`, so `t_sq ∉ revealed = after - before`. Reinforced by VETO 5
   (`v_sq` had to be *occupied before*) and the causation guard.

3. **Front piece slides along the same ray (stays blocking).** A rook in front of a queen on a
   file moves *along* that file. **Excluded** — VETO 5: `from_sq` is vacated but the moved rook
   now re-occupies the ray, so for any target beyond it the between-`v_sq`-and-`t_sq` clearance
   check (CONFIRM step 3) fails; `revealed` gains nothing past the new blocker.

4. **Reveal onto an empty square or a friendly piece.** **Excluded** — `revealed` is scanned for
   squares holding an enemy piece (`color != mover_color`); empty squares and own pieces are
   ignored.

5. **Second blocker still on the line.** A vacates the near blocker but a *second* friendly or
   enemy piece sits between `v_sq` and the would-be target. **Excluded** — CONFIRM step 3
   requires the squares between `v_sq` and `t_sq` to be empty in `board_after`; the target never
   becomes B's first-seen piece.

6. **Spurious `after - before` growth elsewhere.** B's attack set can change for reasons
   unrelated to `v_sq` (e.g. the moved piece *removed* a blocker on a *different* one of B's
   rays by capture). **Excluded for this discovery** — the causation guard (CONFIRM step 3)
   admits a target only if `v_sq` lies between `b_sq` and `t_sq`. A genuinely separate discovery
   on another ray, opened by the *same* move, is still caught when iterated as its own
   `(b_sq, v_sq)` pairing with the correct `v_sq`.

7. **Pinned rear piece, material target (corrected).** **NOT excluded.** The discovered attack
   is certified; `rear_can_capture_target` is `False` when the target is off the pin ray so the
   narrator does not claim material is won. (Draft excluded this — fixed.) For a discovered
   **check**, the pin is irrelevant and the check is always certified.

8. **En-passant capture as the front move.** **Handled** — both `from_sq` and the captured-pawn
   square enter `vacated`; the attack-set diff plus causation guard catch a line opened by
   either removal.

9. **Castling "discovered attack."** **Excluded in v1** (VETO 2) — both royal pieces move; a
   rook arriving on a new file is normal development, not a front-piece vacating a slider's ray.
   Known gap (§6).

10. **Promotion that opens a line.** **Handled** — `from_sq` is the pawn's origin; the rear-
    slider diff and causation guard work normally. The new piece on `to_sq` is the moved piece
    and is excluded as a rear piece (`b_sq != to_sq`). An underpromotion that *also* gives a
    direct check while a rear slider reveals check is correctly reported as a double check.

11. **Board-edge ray.** `chess.between` and `SquareSet` are edge-safe (empty set when squares
    are adjacent or off-line); no manual file/rank arithmetic crosses a board edge because all
    ray walking is delegated to python-chess. A rear piece on the a-/h-file or 1st/8th rank is
    handled identically.

12. **Self-exposure (out of scope).** A move that reveals an *enemy* slider onto the *mover's*
    own king is **not** this tag — `discovered_attack` is about the mover attacking, not being
    attacked. **Excluded** — the rear-piece scan is over `mover_color` sliders and enemy targets
    only.

---

## 5. Evidence bundle

The predicate computes a structured payload so the narrator speaks verbatim without re-deriving
geometry (anti-hallucination). The public contract mirrors
`creates_fork` / `sets_up_royal_pin`: `detect_discovered_attack(...) -> Optional[str]`, wrapped
to `(bool, Optional[str])`. The richer internal record (chosen headline target):

- `rear_piece_type` (int) and `rear_piece_square` (int) — the slider that delivers the revealed
  attack, e.g. `"rook on d1"`.
- `front_piece_type` (int), `front_from_square` (int), `front_to_square` (int) — the piece that
  moved out of the way, e.g. `"knight from d3 to f4"`.
- `target_piece_type` (int) and `target_square` (int) — the enemy piece now attacked.
- `opened_by` (int) — the vacated square that actually opened the line (`from_sq` **or** the
  en-passant `cap_sq`); lets the narrator attribute correctly in the en-passant case.
- `is_discovered_check` (bool) — target is the enemy king (and `board_after.is_check()`).
- `is_double_check` (bool) — `enemy_king_sq is not None` and both `front_to_square` and
  `rear_piece_square` are in `board_after.attackers(mover_color, enemy_king_sq)` with
  `front_to_square != rear_piece_square`.
- `target_is_defended` (bool) — `board_after.is_attacked_by(not mover_color, target_square)`
  (lets the narrator avoid over-claiming won material).
- `rear_can_capture_target` (bool) — `True` if the target is the king, or the rear piece is not
  pinned, or the target lies on the rear piece's pin ray; `False` for a pinned rear piece whose
  target is off the pin line (geometry real, capture illegal).
- `rear_piece_hanging` (bool) —
  `board_after.is_attacked_by(not mover_color, rear_piece_square) and not
  board_after.is_attacked_by(mover_color, rear_piece_square)` (same caveat
  `detect_double_attack` appends).
- **`evidence_str`** (ready to quote, built from `PIECE_NAMES` + `chess.square_name`), selected
  by sub-case:
  - discovered attack:
    `f"the {PIECE_NAMES[front]} moves from {sq(from)} to {sq(to)}, uncovering the
    {PIECE_NAMES[rear]} on {sq(rear)} which now attacks the {PIECE_NAMES[target]} on
    {sq(target)} (discovered attack)"`
  - discovered check: same opening, then
    `f"... which now gives check to the king on {sq(king)} (discovered check)"`
  - double check: append
    `f" — double check (both the {PIECE_NAMES[front]} and the {PIECE_NAMES[rear]} give check)"`
  - append `" — but the {PIECE_NAMES[rear]} is itself hanging"` when `rear_piece_hanging`
    (mirrors `detect_double_attack`, `factgate`/`analyzer.py:331`);
  - append `" (though the {PIECE_NAMES[rear]} is pinned and cannot capture)"` when not
    `rear_can_capture_target` and not a check, so the narrator never claims won material from a
    pinned discovery.

**Wiring.** Add the tag string `"discovered_attack"` to `factgate.GATED_TAGS`
(`factgate.py:222`) and name it in the fact-gate prompt rule (`narrator.py:202`) so the narrator
is licensed to assert it. In `certified_claims`, add a `_safe`-guarded call mirroring
`creates_fork`:
`da = _safe(lambda: detect_discovered_attack(board_before, move, board_after, mover_color))`;
`if da and da[0]: tags.add("discovered_attack")` — using the `(bool, str)` thin-wrapper shape.
Serialize the richer `evidence_str` under a parallel evidence key when the Tier-1
`certified_evidence()` slot is built (per the narrator brief), with the same try/except
fail-safe as `certified`.

---

## 6. Known limitations

- **Castling-revealed attacks are not detected** (VETO 2) — a deliberate precision choice; a
  discovered attack delivered by a castling rook is missed. Revisit if a real game surfaces one.
- **En-passant attribution.** A line opened *solely* by the disappearance of the
  en-passant-captured pawn is detected (its square is in `vacated` and `opened_by` records it),
  but the headline still names the moving pawn as the front piece; `opened_by` lets the narrator
  phrase it precisely if it chooses.
- **Only friendly sliders behind the front piece** are considered. Self-inflicted exposure of an
  *enemy* slider against the mover's own king is out of scope (this tag is about the mover
  attacking).
- **No tactical-soundness judgment.** Like `detect_double_attack`, this certifies the *geometry*
  of a revealed attack, not that it wins material. Defended / hanging / pinned-cannot-capture
  flags are provided so the narrator can hedge; the inclusive standard certifies even a
  well-defended or pinned-rear-piece discovery.
- **Pinned rear piece is certified (corrected), with a `rear_can_capture_target` flag** rather
  than vetoed — broader than `detect_double_attack`, intentional for this term.
- **Pawn-only targets are certified** (inclusive) but ranked last, broader than
  `detect_double_attack` (which ignores pawns). Intentional inclusivity difference.
- **Single front piece only.** Standard discovery semantics; no exotic multi-piece line-clearing
  in one move (other than the en-passant two-square-removal case, which is handled).
- **One discovery per move is reported in the headline**, but the scan iterates all
  `(b_sq, v_sq)` pairings so the *best* discovery (king-first, then highest value, double-check
  preferred) is the one surfaced; additional simultaneous discoveries are not separately listed.

---

## 7. Complexity

**Medium.** The core is a deterministic before/after set-difference on a single slider's attack
set (`board.attacks(b_sq)` diff), cheap and built entirely from existing python-chess primitives
and the exact ray idioms in `detect_double_attack` / `detect_royal_alignment` — no new geometry
math beyond a colinearity test for candidate rear pieces. What lifts it above "low":

- **Enumerating candidate rear pieces** behind each vacated square (file/rank/diagonal
  colinearity + the `board_before` clear-line/occupancy proof in VETO 5);
- the **moved-piece-vs-revealed-piece distinction** that prevents the dominant false positive;
- the **causation guard** (CONFIRM step 3) that binds a revealed target to *this* vacated square
  and rejects unrelated `after - before` growth — the subtle correctness core;
- the **sub-case logic** (discovered check vs double check) needing `attackers()` membership and
  `is_check()` cross-validation, plus the **king-first ranking** fix
  (`PIECE_VALUES[KING] == 0`);
- the **pin handling** (flag, don't veto) and the **en-passant two-square `vacated`** edge.

None of these is individually hard, but together they make it more involved than a single-square
positional predicate like `is_passed_pawn`.
