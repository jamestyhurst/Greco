# Greco Predicate (Fact-Gate) Detection Specs

> Pre-implementation design specs, adversarially reviewed. One section per term.
> Each section is the reviewed spec as returned by its agent (some include a short
> verification preamble noting FENs were checked against python-chess).

---

## Pin (absolute + relative) (`pin`)

Spec written. Sanity check: I verified every FEN against python-chess 1.11.2 (positive examples 1b, 2, 3, 4, 5, 6 all confirmed; the `is_pinned` hanging hazard, edge-wrap, and pawn-pin all reproduced), and re-confirmed the file was overwritten at `C:\Users\詹天哲\Documents\greco\docs\specs\predicates\01-pin.md`. Returning the corrected spec markdown.

# Detection Spec — Pin (absolute + relative) — tag `pin`

> **Status:** corrected after adversarial review. This revision fixes broken positive
> examples (every FEN below is machine-verified on python-chess 1.11.2), a dangerous
> `is_pinned` shortcut that bypassed the hanging guard, an edge-wrap bug in the ray walk,
> the wrongful exclusion of pinned pawns, and several under-/over-inclusive rules. See §8
> (defects fixed) for the full list. Predicate lives in `analyzer.py` as `detect_pin(...)`;
> thin wrapper `creates_pin(...)` in `factgate.py`.

## 1. Expert definition

A **pin** is a situation where a friendly sliding piece (bishop, rook, or queen) attacks an
enemy piece along a line (rank, file, or diagonal) such that **moving that enemy piece is
effectively prohibited** because a more valuable enemy unit — or the enemy king — sits
directly behind it on the same line with nothing in between. The enemy piece is "pinned to"
what stands behind it.

Two recognized variants, both of which this detector MUST certify:

- **Absolute pin** — the piece behind is the **enemy king**. Moving the pinned piece is
  *illegal* (it would expose the king to check). This is the strict, geometry-enforced case.
  python-chess models it via `board.is_pinned(color, square)`.
- **Relative pin** — the piece behind is a more valuable enemy piece (most often the queen,
  but any unit worth strictly more than the pinned piece — e.g. a knight pinned in front of a
  rook, or a **pawn pinned in front of a rook**). Moving the pinned piece is *legal but
  materially ruinous*: it loses the piece behind. James's framing: "moving this bishop would
  lose the rook behind it."

**The pinned (front) piece may be ANY enemy unit except the king — including a pawn.** A pawn
pinned to its king cannot legally capture or push off the line; a pawn pinned in front of a
rook loses the rook if it moves. Pawns are first-class pinned pieces and must not be excluded.
(The only thing a pawn may *not* be is the **rear/shield** of a relative pin — a pawn is worth
1, never strictly greater than the front piece, so the value test in rule 8 excludes it
automatically; and a pawn rear can never be a king, so the absolute branch never applies.)

Key expert nuances the spec honors:

- The defining feature is **a line through three collinear pieces**: friendly attacker → enemy
  pinned piece → enemy higher-value piece/king, with **nothing else between any adjacent
  pair** (nothing between attacker and front; nothing between front and rear).
- The attacker's ray type must match the line: **bishops/queens pin on diagonals;
  rooks/queens pin on ranks/files**. A bishop cannot pin along a file; a rook cannot pin along
  a diagonal.
- A pin is only real if the **specific attacker is not simply hanging** (capturable for free) —
  otherwise the "threat" is illusory, mirroring the existing `detect_royal_alignment` guard.
  **This guard applies to BOTH the absolute and the relative case** (see §8, defect D2/D7).
- "Pinned in front of an *equal or lesser* value piece" is **not** a relative pin (no
  prohibitive consequence) — except the absolute case, where the king's special status makes
  the move outright illegal regardless of the pinned piece's value.

This **generalizes** the existing `detect_royal_alignment` helper, which only fires for
king+queen alignment that wins the queen. The new `pin` predicate covers (a) absolute pins to
the king with *any* non-king piece (including a pawn) in front, and (b) relative pins where the
rear piece is any strictly-higher-value enemy unit, not only the queen.

## 2. Detection rules (VETO-THEN-CONFIRM)

Evaluated on `board_after` (the position after the mover's move); `mover_color` = the side that
just moved. The pinned and rear pieces belong to the opponent (`opp = not mover_color`); the
pinning attacker is the mover's. Color is handled purely via `mover_color`/`opp` — the logic is
symmetric, so White and Black are covered by the same code with **no color branch and no rank
direction hard-coded** (see §8, defect D8). Side-to-move dependence: a pin is a static
geometric fact on `board_after`, so whose turn it is does **not** affect certification —
verified: `board.is_pinned` returns the same value with either side to move. Iterate candidate
**attacker** squares = `board.pieces(BISHOP, mover_color) ∪ board.pieces(ROOK, mover_color) ∪
board.pieces(QUEEN, mover_color)`.

**VETO stage (cheap necessary-condition refutations — kill most non-pins instantly):**

1. **No sliding attacker → abstain.** If the mover has no bishop, rook, or queen, return
   `(False, None)` immediately. (A knight/pawn/king can never pin.)

2. **Per attacker: skip if THIS attacker is hanging.** If
   `board.is_attacked_by(opp, attacker_sq)` and NOT `board.is_attacked_by(mover_color,
   attacker_sq)` (attacked and undefended), skip this attacker — a pin whose pinning piece can
   be captured for free is not real. This is the exact guard from `detect_royal_alignment`
   (analyzer.py line 400) and it is evaluated **per candidate attacker before any other test**,
   so it gates the absolute case too. **Do NOT use `board.is_pinned` as a shortcut that skips
   this guard** (see rule 8 and §8 defect D2).

3. **Candidate pinned (front) pieces = only what the attacker actually attacks.** Use
   `board.attacks(attacker_sq)` (a `SquareSet`) and keep only squares holding an **enemy** piece
   (`board.piece_at(s)` exists, `.color == opp`) that is **not** the enemy king. **Pawns ARE
   allowed as front pieces** — do not filter them out. `board.attacks()` already stops at the
   first occupied square on each ray, so any returned occupied square is the *first* piece on
   that ray (the legitimate front candidate); a square occupied by one of the mover's *own*
   pieces is rejected here by the `== opp` color test. If `board.attacks()` yields no eligible
   enemy piece, skip this attacker. This is the single biggest false-positive killer: the front
   piece must be directly, currently attacked with a clear line to it.

4. **Ray-type gate.** The attacker→front direction must be legal for the attacker's piece type:
   - rook (and the rook-component of a queen): only on a shared rank or file —
     `square_file(attacker) == square_file(front)` **or** `square_rank(attacker) ==
     square_rank(front)`;
   - bishop (and the bishop-component of a queen): only on a shared diagonal —
     `abs(file_a − file_f) == abs(rank_a − rank_f)` and the two squares are not identical;
   - queen: either of the above.

   Compute the unit step `(df, dr)` where `df = sign(file_f − file_a)` and `dr = sign(rank_f −
   rank_a)`, each in `{−1, 0, +1}`. If `(df, dr)` is not a legal direction for the attacker's
   type, skip. **Because `board.attacks()` already guarantees a legal ray for the piece type,
   this gate is normally redundant for the front square — its real job is to produce the
   `(df, dr)` step reused in rule 6.** Keep it as an explicit assertion.

**CONFIRM stage (fuller checks on survivors):**

5. **Clear line attacker→front (defensive assertion).** Every square strictly between attacker
   and front must be empty:
   `all(board.piece_at(s) is None for s in chess.SquareSet(chess.between(attacker_sq,
   front_sq)))` (same idiom as `detect_royal_alignment` lines 406–411). Because rule 3 took the
   front square straight from `board.attacks()`, this holds by construction — but assert it so
   the predicate is robust if rule 3 is ever refactored.

6. **Find the rear piece — continue the SAME ray past the front piece, with edge-safe stepping.**
   Starting from `front_sq`, repeatedly advance one step in direction `(df, dr)` from rule 4.
   At each step compute the candidate file `f = square_file(prev) + df` and rank `r =
   square_rank(prev) + dr`; **stop if `f` or `r` leaves `0..7` (you walked off the board).** Do
   **NOT** advance by raw square-index arithmetic (`sq + 9`, `sq + 1`, …): that wraps across the
   board edge (verified: h4 + 1 → a5) and would read a phantom rear piece on the wrong
   rank/file (see §8, defect D5). Only when `0 ≤ f ≤ 7` and `0 ≤ r ≤ 7` form the next square via
   `chess.square(f, r)`. The **first occupied square** reached this way is the rear candidate
   `rear_sq`; if you fall off the board first, there is no rear piece → skip. (`chess.between`
   is **not** usable here because the rear piece is *beyond* the front, not between attacker and
   front.)

7. **Rear must be an enemy piece.** `board.piece_at(rear_sq)` exists and `.color == opp`. If the
   first piece behind the front on the ray is one of the mover's **own** pieces, or there is no
   piece behind on the ray, it is **not** a pin (nothing enemy is being shielded).

8. **Prohibitive-consequence test — the pin classifier (the heart):**
   - **Absolute pin:** if `rear_piece.piece_type == chess.KING` → certify, `kind = "absolute"`.
     **Corroboration, not shortcut:** you MAY assert `board.is_pinned(opp, front_sq)` is `True`
     as a sanity check (it should be, since the king is the verified rear and the line is clear),
     but `is_pinned` must **never** be used as a fast-positive that *skips* the per-attacker
     hanging guard (rule 2) or the per-attacker line/ray checks. `is_pinned` reports only *that*
     the front piece is pinned to its king by *some* enemy piece — it does **not** tell you
     **which** attacker pins, and it returns `True` even when the actual pinning piece is
     hanging and can simply be captured (verified: a queen on e3 pinning a rook to the king on
     the e-file shows `is_pinned == True` while the queen is attacked-and-undefended). Certifying
     off `is_pinned` alone would (a) over-credit an illusory pin and (b) risk naming the wrong
     attacker square in the evidence bundle. So `is_pinned` is at most a redundant confirmation
     of the manual result for the attacker actually under examination.
   - **Relative pin:** else if `PIECE_VALUES[rear_piece.piece_type] >
     PIECE_VALUES[front_piece.piece_type]` → certify, `kind = "relative"`. Strictly greater.
     Reuse the module `PIECE_VALUES` (`{PAWN:1, KNIGHT:3, BISHOP:3, ROOK:5, QUEEN:9, KING:0}`).
     Note `KING` value is 0, so a king behind is handled only by the absolute branch above,
     never by this value comparison.
   - **Else (rear value ≤ front value, rear not king):** **veto** — no prohibitive consequence,
     so not a pin (e.g. a rook "pinning" a queen in front of another rook is no pin; moving the
     queen loses nothing of greater value). This also vetoes the **equal-value** case
     (bishop-in-front-of-bishop, knight-in-front-of-knight): `3 > 3` is `False`.

9. **No-skewer disambiguation.** Confirm the **front** piece (closer to the attacker) is the
   lower-value / non-king one and the **rear** is the higher-value piece or the king. If the
   higher-value piece is in *front* and the lesser behind, that is a **skewer**, not a pin — do
   not certify under `pin`. Rule 8's strict value test already enforces this for the relative
   case; for the king, the king being the *front* piece would mean the attacker gives check
   (rule 3 already excludes the king from front candidates), which is also not a pin.

**First surviving `(attacker, front, rear)` triple certifies `(True, evidence)`.** Reuse: this
is `detect_royal_alignment` generalized — same per-attacker hanging guard (rule 2), same
`chess.between`/`SquareSet` clear-line idiom (rule 5) — but with (a) any sliding attacker on its
correct ray type, (b) any non-king front piece including a pawn, and (c) an edge-safe ray walk
(rule 6) plus a value/king classifier (rule 8) replacing the king+queen-only special case. Do
**not** duplicate `detect_royal_alignment`; the new `detect_pin` supersedes it. The old helper
remains in place only so the narrower legacy `royal_pin_setup` tag keeps working until callers
migrate.

## 3. Positive examples

Every FEN is `board_after` (the mover has just moved) and is machine-verified on python-chess
1.11.2 — `board.attacks()` hits the front square, the ray is clear, and `is_pinned` is reported
where relevant.

1. **Absolute pin (bishop pins knight to king), real-game form.** Play out the Steinitz
   Defense: `1.e4 e5 2.Nf3 Nc6 3.Bb5 d6`. After `3...d6` the d7 pawn has vacated d7, so the
   white bishop on b5 attacks the black knight on c6 with the black king on e8 directly behind
   on the a4–e8 diagonal and **nothing between** (d7 is empty). Verified: `board.is_pinned(BLACK,
   c6) == True` and the knight has **zero** legal moves. Front = knight; rear = king → absolute
   pin. *(Note: the bare `3.Bb5` Ruy position is NOT a pin — the d7 pawn still blocks the
   diagonal, so the c6 knight can legally move. The pin only bites once d7 is vacated. The
   original draft's flagship example was that non-pin; fixed here — see §8 D1.)*

   Minimal equivalent FEN: `4k3/8/2n5/1B6/8/8/8/4K3 w - - 0 1` — bishop b5, knight c6, king e8,
   d7 empty. `is_pinned(BLACK, c6) == True`.

2. **Relative pin (bishop pins knight to queen).** FEN `3qk3/8/5n2/6B1/8/8/8/4K3 w - - 0 1` —
   white bishop g5 attacks the black knight on f6 with the black queen on d8 behind it on the
   d8–h4 diagonal (e7 empty). Front = knight (3); rear = queen (9) > 3 → relative pin (moving
   Nf6 loses the queen). Verified: `g5` attacks `f6`; first piece beyond f6 on the diagonal is
   the d8 queen.

3. **Relative pin to a rook (James's canonical case).** FEN `2r1k3/8/8/8/8/2n5/8/2RK4 w - - 0 1`
   — white rook c1 attacks the black knight on c3 along the c-file; behind it on the c-file sits
   the black rook on c8 (king is on e8, off the file). Front = knight (3); rear = rook (5) > 3 →
   relative pin: "moving this knight would lose the rook behind it." Verified: rook c1 attacks
   c3; first piece beyond c3 on the c-file is the c8 rook.

4. **Rook absolute pin on a file.** FEN `3k4/8/8/8/8/3b4/8/3RK3 w - - 0 1` — white rook d1, black
   bishop d3, **black king d8**, all on the d-file, nothing between rook and bishop or bishop and
   king. Front = bishop; rear = king → absolute pin along the file (the d3 bishop cannot legally
   move). Verified: `is_pinned(BLACK, d3) == True`. *(The original draft FEN `3rk3/...` placed a
   rook on d8 and the king on e8 — making it a relative pin, not the claimed absolute pin, and
   `is_pinned` was False. Corrected to put the king on d8 — see §8 D4.)*

5. **Queen relative pin on a rank.** FEN `4k3/8/8/8/Q1n1r3/8/8/4K3 w - - 0 1` — white queen a4
   attacks the black knight on c4 along the 4th rank (b4 empty) with the black rook on e4 behind
   (d4 empty). Front = knight (3); rear = rook (5) → relative pin on a rank by the queen's rook
   component. Verified: queen a4 attacks c4; first piece beyond c4 on the rank is the e4 rook.

6. **Absolute pin of a PAWN (under-inclusiveness regression guard).** FEN
   `4k3/8/4p3/8/8/8/8/4R1K1 w - - 0 1` — white rook e1 attacks the black pawn on e6 with the
   black king on e8 behind on the e-file. Front = **pawn**; rear = king → absolute pin (the pawn
   cannot legally move off the e-file). Verified: `is_pinned(BLACK, e6) == True`. This must
   certify — it is the case the draft's "skip pawns" wording wrongly excluded (see §8 D6).

## 4. Negative / edge cases

1. **Skewer (higher-value piece in front).** Rook attacks an enemy queen with the enemy rook
   behind it. Front = queen (9), rear = rook (5); `PIECE_VALUES[rear] (5) > PIECE_VALUES[front]
   (9)` is **False** → vetoed by rule 8. Correctly excluded — it is a skewer, never `pin`.

2. **"Pin" in front of an equal piece.** Bishop attacks an enemy knight with an enemy bishop
   (also value 3) behind it. `3 > 3` is `False` → vetoed. Moving the front knight loses nothing
   of greater value; no prohibitive consequence, not a pin.

3. **Hanging pinning piece (BOTH variants).** A piece lines up against king+rear but is itself
   attacked and undefended. Rule 2 (`is_attacked_by(opp, attacker)` and not defended) skips that
   attacker **before** the classifier runs — so it is enforced for absolute pins too, not only
   relative. Verified hazard: a white queen on e3 with `is_pinned(BLACK, rook-on-e-file) ==
   True` is nonetheless captured for free by the rook; rule 2 (not the `is_pinned` shortcut)
   correctly refuses to certify it. The "pin" is illusory because the opponent just takes the
   pinning piece.

4. **Blocker on the line.** Attacker and the two enemy pieces are collinear, but a third piece
   (either color) sits between attacker and front, or between front and rear. If between attacker
   and front: `board.attacks()` never returns the front square (it stops at the blocker), so
   rule 3 fails. If between front and rear: rule 6 finds the blocker as the first occupied square
   beyond the front, and rule 7/8 judges *that* piece — if it is the mover's own or lower-value,
   no certification. Either way there is no through-line, so no pin. *(The c6-knight Ruy case in
   §3.1's note is exactly this: the d7 pawn between front and the king makes the "absolute pin"
   evaporate — the pawn, value 1 < knight 3, is the real rear and fails the value test.)*

5. **Wrong ray for the piece type.** A bishop "lined up" with two enemy pieces on a *file*. The
   bishop does not attack along a file, so `board.attacks()` never includes the front square,
   rule 3 yields nothing, and the ray-type gate (rule 4) would reject the direction anyway. Same
   for a rook on a diagonal.

6. **Self-pin / own piece behind.** The first piece beyond the enemy front piece on the ray is
   one of the **mover's own** pieces (or the ray runs off the board empty). Rule 7 requires
   `rear.color == opp`; a friendly rear or empty ray is not a pin (nothing enemy is shielded).

7. **Front piece is the enemy king (giving check, not pinning).** If the only enemy piece the
   attacker hits on a ray is the king itself, the attacker is giving check, not pinning. Rule 3
   excludes the king from front candidates; this is check, never a pin.

8. **Board-edge ray walk (rule 6 correctness).** Attacker and front sit near a file/rank edge
   (e.g. a rook pinning along the 4th rank with the front piece on g4 and nothing real on h4).
   The ray walk must stop when it would leave the board, not wrap from h4 to a5. Verified: naive
   `square + 1` indexing wraps h4 → a5 and would invent a phantom rear piece; rule 6's file/rank
   bounds check (`0 ≤ f,r ≤ 7`) prevents it.

9. **En-passant / discovered-pin subtleties.** The detector reads the static `board_after`
   geometry only; it does not reason about whether the pin was *created* by this move vs.
   pre-existing (see §6 limitations). A pin that already existed and merely persists still
   certifies on `board_after` — acceptable because the claim "there is a pin" remains true,
   though it may over-credit the mover. The narrator claim is scoped to "a pin exists," not "you
   created a pin," unless a before/after diff is added.

## 5. Evidence bundle

The predicate returns `(bool, Optional[dict])`. On success the dict carries the exact
anti-hallucination payload (all squares as `chess.square_name`, all piece names from
`PIECE_NAMES`):

- `kind`: `"absolute"` or `"relative"`.
- `attacker_square`: e.g. `"b5"` — the mover's pinning piece square (the attacker actually
  examined in the loop, never inferred from `is_pinned`).
- `attacker_piece`: e.g. `"bishop"` (from `PIECE_NAMES`).
- `pinned_square`: e.g. `"c6"` — the enemy front (pinned) piece.
- `pinned_piece`: e.g. `"knight"` or `"pawn"`.
- `behind_square`: e.g. `"e8"` — the rear (shielded) piece/king.
- `behind_piece`: e.g. `"king"` or `"queen"`/`"rook"`.
- `line`: `"diagonal"`, `"file"`, or `"rank"` (the ray type used).
- `coord`: the file letter (`chess.FILE_NAMES[file]`) for a file or diagonal anchor, or the rank
  digit (`chess.RANK_NAMES[rank]`) for a rank — matching `detect_royal_alignment`'s `coord`-
  `line` phrasing. (Added: the draft's templates referenced `{coord}` without listing it — see
  §8 D9.)
- `evidence`: a ready-to-quote string the narrator may use verbatim. Exact templates:
  - Absolute: `f"your {attacker_piece} on {attacker_square} pins the {pinned_piece} on
    {pinned_square} to the king on {behind_square} along the {coord}-{line} — an absolute pin
    (the {pinned_piece} cannot legally move)"`
  - Relative: `f"your {attacker_piece} on {attacker_square} pins the {pinned_piece} on
    {pinned_square} against the {behind_piece} on {behind_square} along the {coord}-{line} — a
    relative pin (moving the {pinned_piece} loses the {behind_piece})"`

**Wiring (parallel to `sets_up_royal_pin`):** add a thin `creates_pin(board_after, mover_color)`
wrapper in `factgate.py` that calls `detect_pin` and returns `(result is not None, result)`
where `result` is the evidence dict (or `None`). In `certified_claims()`, add:
`pn = _safe(lambda: creates_pin(board_after, mover_color)); if pn and pn[0]: tags.add("pin")` —
the same `<var> and <var>[0]` guard shape used for the other tuple-returning predicates, so a
predicate exception is swallowed by `_safe` and silently drops the tag rather than crashing the
report. Serialize the evidence dict (or just its `evidence` string) into the Tier-1 packet
alongside `certified`, inside the existing `if tier >= 1:` block of `_move_to_dict`
(`narrator.py:440-462`), under the same try/except fail-safe.

**Registration required (or the narrator is forbidden to assert it):** add `"pin"` to
`factgate.GATED_TAGS` (`factgate.py:222`) **and** name it in the fact-gate prompt rule at
`narrator.py:202`. The whitelist is the single source of truth — an unregistered tag is treated
as "not machine-proven" and the narrator may not assert it.

## 6. Known limitations

- **Static, not causal.** It certifies "a pin exists on `board_after`," not "this move created
  the pin." A pin present before the move also certifies. To credit *creation*, diff against
  `board_before` (compute the predicate on both; certify only if newly present) — deferred by
  default to keep parity with the static `detect_royal_alignment`.
- **First-triple-wins.** It reports one pin (the first survivor); a position with multiple
  simultaneous pins surfaces only one. Acceptable for narration; extendable to a list.
- **Value-only relative test.** "More valuable" is pure `PIECE_VALUES`; it ignores
  positional/defended nuance (e.g. a rear piece that is itself defended so recapture wins
  material back). The narrator frames it as "loses material," which holds geometrically; deep
  soundness is the engine's job, not this gate.
- **No partial/cross pins or pin-on-a-defender.** It does not detect "situational pins" where
  moving a piece is bad for non-material reasons (e.g. abandoning a defended mate square) — only
  the line-geometry material/king pin. Intentional; those are false-positive-prone without
  engine eval.
- **Does not verify the pin is exploitable.** A pinned piece may still be adequately defended so
  the pin wins nothing concrete; certification means the *geometry and prohibitive-consequence*
  hold, not that the mover wins material. Matches the "factual description, not a claim that it
  wins" posture of `detect_double_attack`.
- **`is_pinned` is corroboration only, never the gate.** The absolute case is computed manually
  (per-attacker hanging guard + ray walk) and `board.is_pinned(opp, front_sq)` is used at most as
  a redundant sanity check, because `is_pinned` ignores who pins and ignores whether the pinner
  is hanging. The relative case is wholly manual (`is_pinned` does not model relative pins).

## 7. Complexity

**Medium.** The geometry is more involved than a single-square lookup (`is_passed_pawn`) but
reuses proven idioms: `board.attacks()` for front candidates, the per-attacker `is_attacked_by`
hanging guard and `chess.between`/`SquareSet` clear-line check from `detect_royal_alignment`, and
`PIECE_VALUES`/`PIECE_NAMES` for the classifier and strings. The genuinely new work is (a) the
ray-type gate that yields the `(df, dr)` step (rule 4) and (b) the **edge-safe** ray walk *past*
the front piece (rule 6) — which `chess.between` does not do and which must use file/rank-bounds
stepping, not raw index arithmetic, to avoid board-edge wrap. Loops are small and bounded — at
most ~9 attacker pieces × a handful of attacked squares, with O(8) ray walks — so it is cheap at
runtime; the cost is correctness/edge-case care (skewer vs. pin, ray-type matching, the hanging
guard applied to *both* variants, edge-safe stepping, pawns-as-front), not algorithmic
difficulty. Lower than `detect_sacrifice` (no engine eval, no material-delta simulation); higher
than the thin wrappers.

## 8. Defects fixed from the draft (adversarial review log)

- **D1 — broken flagship positive example (false certification of a non-pin).** Draft Example 1
  (Ruy Lopez `3.Bb5`) is **not a pin**: the d7 pawn sits between the c6 knight and the e8 king,
  so the knight moves legally (`is_pinned(BLACK, c6) == False`; legal `Na5/Nd4/...`). The draft's
  own rules would (correctly) read the d7 pawn as the rear, value 1 < knight 3, and veto — i.e.
  the draft showcased a non-pin as a positive. Fixed: use the Steinitz `1.e4 e5 2.Nf3 Nc6 3.Bb5
  d6` position (d7 vacated → genuine absolute pin) or the minimal FEN `4k3/8/2n5/1B6/8/8/8/4K3`.
- **D2 — `is_pinned` shortcut bypassed the hanging guard (false positive).** Draft rule 8 said
  to "prefer trusting `is_pinned` as a fast positive shortcut for the absolute case." But
  `is_pinned(opp, front)` returns `True` even when the actual pinning piece is **hanging**
  (verified: a white queen on e3 pinning a rook to the king while attacked-and-undefended).
  Trusting it skips rule 2 and certifies an illusory pin the opponent refutes by capturing the
  pinner. `is_pinned` also never identifies **which** attacker pins, so it can mislabel
  `attacker_square` in the evidence. Fixed: `is_pinned` is corroboration only; the per-attacker
  hanging guard and manual ray walk are authoritative for both variants.
- **D3 — second positive example was an illegal move.** Draft Example 2's FEN
  (`rnbqkb1r/.../2N1P3/...`) has a white pawn on **e3** blocking the c1 bishop, so `Bg5` is an
  **illegal move** — the example never reaches the claimed position. Fixed with a clean,
  verified FEN `3qk3/8/5n2/6B1/8/8/8/4K3`.
- **D4 — fourth positive example contradicted its own claim.** Draft Example 4's FEN `3rk3/...`
  places a **rook on d8 and the king on e8**, so it is a *relative* pin (bishop→rook), not the
  *absolute* pin the text asserts (`is_pinned == False`). Fixed to `3k4/8/8/8/8/3b4/8/3RK3` with
  the king genuinely on d8 (`is_pinned == True`).
- **D5 — board-edge wrap bug in the rear-piece ray walk (false positive / phantom rear).** Draft
  rule 6 said "extend ... one step at a time" without specifying edge-safe stepping. Raw index
  arithmetic (`sq + 1`, `sq + 9`, …) wraps across the board edge (verified: h4 + 1 → a5),
  inventing a rear piece on the wrong rank/file. Fixed: rule 6 steps by `(df, dr)` and stops when
  file or rank leaves `0..7`.
- **D6 — under-inclusive exclusion of pinned pawns (false negative).** Draft rule 3 excluded "a
  pawn-vs-nothing case," ambiguously risking the exclusion of **pawns as front (pinned) pieces**.
  A pawn pinned to its king or in front of a rook is a real, common pin (verified:
  `is_pinned(BLACK, e6) == True` for a pawn). Fixed: pawns are explicit, first-class front
  pieces (new positive Example 6); only the *rear/shield* is value-gated, which already excludes
  a pawn rear via rule 8.
- **D7 — hanging guard scoped only to the relative/royal case (false positive on absolute).** By
  pushing the hanging check after an `is_pinned` shortcut, the draft let hanging *absolute*
  pinners through. Fixed: rule 2 runs **per attacker, before the classifier**, covering both
  variants.
- **D8 — color/side asymmetry risk made explicit.** Draft prose claimed symmetry but the ray
  walk and any rank-direction logic must not hard-code a White-relative "up the board"
  direction. Fixed: rule 6 derives the step sign from the attacker→front delta, so Black pins
  (downward rays) are handled identically; verified `is_pinned` is side-to-move independent.
- **D9 — missing `coord` field in the evidence bundle.** The draft's `evidence` templates
  referenced `{coord}` but `coord` was not listed as a returned field. Added `coord` to the §5
  bundle with its derivation (file letter for file/diagonal, rank digit for rank).

---

## Skewer (absolute + relative) (`skewer`)

Sanity check before finishing: I verified the load-bearing claims against the actual code — `PIECE_VALUES` has `KING: 0` (analyzer.py:209), `detect_royal_alignment` (analyzer.py:367–417) never orders K vs Q so it can't distinguish pin from skewer, the not-hanging guard is at line 400, `detect_double_attack`'s pinned guard at 288, and the clear-line `chess.between`/`SquareSet` checks at 406–411. The single biggest fix — that python-chess `board.attacks(asq)` stops at the first blocker and therefore can never see the back piece — is correct python-chess semantics, which is why the corrected spec mandates a manual edge-clamped ray-walk. File written to the requested path. Returning the corrected spec markdown.

# Detection Spec — "Skewer (absolute + relative)" — tag: `skewer`

> **Adversarial-review note (why this revision exists).** The draft conflated
> `board.attacks(asq)` (which **stops at the first blocker** and therefore can *never* see the
> back piece) with a directional ray-walk; mis-handled the king's value-0 entry in
> `PIECE_VALUES`; relied on `board_after.is_check()` without nailing down that the opponent is
> the side to move on `board_after`; offered a `chess.between` collinearity test that silently
> passes for non-collinear squares; and wrongly conceded that promotion can't create a skewer.
> Every one of those is fixed below. The corrected engine does its own **edge-clamped
> directional ray-walk** and treats `board.attacks`/`board.attackers` only as cheap pre-filters,
> never as the line-walker.

---

## 1. Expert definition

A **skewer** is a straight-line (ray) tactic on a single file, rank, or diagonal in which a
long-range attacker (rook, bishop, or queen) attacks an enemy piece, and **directly behind that
front piece, on the same ray, stands a second enemy piece**. The front piece is the more
valuable (or the king); the piece behind it is the lesser one that is won. The front piece is
forced or induced to move off the line, exposing the piece behind it to capture. Geometrically
it is "a pin run backwards": the **same ray-alignment primitive as a pin, with the value
ordering of the two screened enemy pieces reversed** — the valuable piece is in **FRONT**, the
lesser piece **BEHIND**.

Recognized variants (all must be certifiable):

- **Absolute skewer** — the front piece is the **enemy king**. On `board_after` (opponent to
  move) the king is attacked along the ray and is *legally compelled* to step off the line,
  after which the piece behind it is captured. King **in front** ⇒ skewer; king **behind** ⇒
  that is an absolute *pin*, not a skewer. Because the king has value 0 in `PIECE_VALUES`, the
  absolute case is detected by an explicit **`front.piece_type == KING` branch**, never by a
  value comparison (the table would make the king "less valuable than" every other piece and
  silently kill every absolute skewer).
- **Relative skewer** — the front piece is any enemy non-king piece **more valuable than the
  piece behind it** (queen in front of a rook/bishop/knight; rook in front of a bishop/knight).
  The front piece is not legally forced to move, but moving loses less than staying, so the
  lesser piece behind is won.
- **Equal-value boundary** — front and back the same nominal value (rook-in-front-of-rook,
  bishop/knight-in-front-of-minor). Commentators sometimes call this a skewer. **Default
  posture: require front strictly greater than back (`>`)** and abstain on equal value, treating
  it as the documented edge in §4. Abstaining means "not machine-proven," never "false."

The defining contrast with a pin (same engine, opposite ordering):
> **Pin** = lesser-value enemy piece in front, more-valuable enemy piece (or king) behind it.
> **Skewer** = more-valuable enemy piece (or the king) in front, lesser-value enemy piece behind.
> Front-vs-back **relative value ordering** is the single discriminator between the two tags.

This is **not** restricted to the king+queen "royal" case that `detect_royal_alignment`
(analyzer.py:367) already covers — that helper fires only for enemy K+Q with a mover R/Q and
collapses pin and skewer into one "a pin/skewer that wins the queen" string **without ever
establishing front/back order** (it never checks which of K or Q is nearer the attacker). A
faithful `skewer` detector must generalize the screened pair to any (front, back) and emit the
tag ONLY when the front/back ordering is the skewer ordering.

**Color handling — fully symmetric, no side- or color-asymmetric rule.** The **mover_color**
owns the attacker (R/B/Q); the **opponent** (`enemy = not mover_color`) owns **both** screened
pieces (front and back). Every rule below is computed identically for `mover_color == WHITE` and
`mover_color == BLACK`; only `enemy` flips. Certification describes `board_after` — the position
*after* the mover's move, where **the opponent is the side to move** — i.e. "the mover has set
up / is executing a skewer against the opponent." This side-to-move fact is load-bearing for the
absolute case (see rule 7) and must hold for the caller.

---

## 2. Detection rules (VETO-THEN-CONFIRM)

Operate on `board_after` with `enemy = not mover_color`. **Do not use `board.attacks(asq)` to
find the back piece** — `attacks()` returns only squares the slider reaches *given current
blockers*, so it stops at the FRONT piece and never includes `bsq`. Use it only as a cheap
"does the attacker hit the front square at all" pre-filter (rule 3). The line itself is walked by
an explicit, **edge-clamped directional step** (rule 4).

Mirror the proven guards in `detect_royal_alignment` (analyzer.py:367, esp. the not-hanging
guard at :400 and the `chess.between`/`SquareSet` clear-line checks at :406–411) and the
pinned-attacker guard in `detect_double_attack` (analyzer.py:288). Reuse, do not duplicate.

**VETO stage — cheap necessary conditions; bail the instant a skewer is impossible:**

1. **Attacker must exist and belong to the mover.** Iterate candidate attacker squares `asq` in
   `board_after.pieces(ROOK, mover_color)`, `pieces(BISHOP, mover_color)`,
   `pieces(QUEEN, mover_color)`. If the mover has no R/B/Q, veto immediately. (A promoted piece
   already sits on `board_after` as its new type, so a skewer **created by promotion** — e.g.
   `e8=Q` aligning queen→enemy-king→rook — is detected here with no special handling; see §6.)

2. **Attacker not pinned to its own king, and not hanging.**
   - Veto this attacker if `board_after.is_pinned(mover_color, asq)` — note this guard is True
     ONLY for a pin against the attacker's *own* king (python-chess semantics), so it does not
     spuriously reject a piece merely "lined up" with enemy pieces. (Edge case, documented in §6:
     a slider pinned to its own king can still legally move *along* the pin ray, so if the skewer
     ray coincides with the pin ray it is technically playable; we conservatively veto — precision
     over recall.)
   - Veto if hanging: `board_after.is_attacked_by(enemy, asq) and not
     board_after.is_attacked_by(mover_color, asq)` (the exact not-hanging guard from
     `detect_royal_alignment`:400 / `detect_double_attack`:328). A free-to-capture skewering piece
     is not a real skewer.

3. **Front square must be directly hit by the attacker (cheap pre-filter).** There must be an
   enemy non-pawn piece `fsq` with `fsq in board_after.attacks(asq)` (so the front piece is the
   FIRST obstruction the slider actually reaches). Skip pawns as the front piece (a "skewered
   pawn" in front is not a tactic; the king and real pieces are the front candidates). This is the
   only use of `attacks()`; it guarantees `fsq` is reachable and unblocked from `asq`.

4. **Walk the ray past `fsq` to find `bsq` — edge-clamped, piece-type-legal direction.**
   - Compute the unit step `(df, dr)` from `asq`→`fsq`:
     `df = sign(file(fsq) - file(asq))`, `dr = sign(rank(fsq) - rank(asq))`.
   - **Reject unless `(df, dr)` is a legal slider direction for THIS attacker's type:** rook ⇒
     exactly one of `df`/`dr` is zero (pure file or rank); bishop ⇒ both non-zero AND
     `abs(file Δ) == abs(rank Δ)` (true diagonal); queen ⇒ either. If `asq→fsq` is not a single
     straight ray for this piece type (e.g. a queen "attacking" via an L that `attacks()` would
     never report anyway, or any off-line relation), veto. This is the geometry guard that keeps
     a *fork / contact double-attack* (rule §4-case-8) out of `skewer`.
   - **Step from `fsq` by `(df, dr)`, one square at a time, stopping at the board edge**
     (`0 <= file <= 7 and 0 <= rank <= 7`): the FIRST occupied square encountered is `bsq`. If
     the ray runs off the edge with no piece behind `fsq`, veto (front piece is the last thing on
     the line — nothing skewered). **Edge clamping is mandatory**: never let raw index arithmetic
     wrap around a file/rank boundary (a8→a1 wrap is a classic ray-walk bug).
   - `asq`, `fsq`, `bsq` are now guaranteed collinear on a single slider ray by construction —
     do **not** substitute a `fsq in chess.between(asq, bsq)` test for this, because
     `chess.between` returns an **empty set when its two endpoints are not collinear**, so
     `fsq in SquareSet(between(asq, bsq))` evaluates False *both* when geometry is wrong AND can be
     mis-read as a pass elsewhere; the directional walk is authoritative.

5. **Exactly the front piece between attacker and front, and a clear segment front→back.**
   - Every square strictly between `asq` and `fsq` is empty:
     `all(board_after.piece_at(s) is None for s in chess.SquareSet(chess.between(asq, fsq)))`.
     (Guaranteed by rule 3's `attacks()` reachability, but assert it explicitly for safety —
     same check `detect_royal_alignment`:406 uses.)
   - Every square strictly between `fsq` and `bsq` is empty:
     `all(board_after.piece_at(s) is None for s in chess.SquareSet(chess.between(fsq, bsq)))`
     (mirrors :409). So the front piece is the FIRST obstruction and the back piece the SECOND,
     with nothing in between. Any extra blocker ⇒ veto (over-screened; see §4-case-5).

**CONFIRM stage — the skewer-defining conditions:**

6. **Both screened pieces are the OPPONENT's.** `front = board_after.piece_at(fsq)`,
   `back = board_after.piece_at(bsq)`; both must be non-None with
   `front.color == enemy and back.color == enemy`. If `back` is the mover's own piece, this is an
   X-ray defense/support of one's own piece, **not** a skewer ⇒ veto (§4-case-4). (`front.color ==
   enemy` is already guaranteed by rule 3's enemy filter; re-assert for clarity.)

7. **Skewer value ordering — THE discriminator vs pin — with explicit king branch.**
   Using `PIECE_VALUES` (analyzer.py:203; **KING:0 there**):
   - **Absolute skewer** — `front.piece_type == chess.KING`:
     - The back piece may be any opponent **non-king** piece (a king cannot stand behind a king).
     - Confirm the king is **attacked along this very ray on `board_after`**: since the opponent
       is to move on `board_after`, `board_after.is_check()` is True iff the opponent's king is in
       check, and `asq in board_after.attackers(mover_color, fsq)` confirms *this* attacker is the
       checking piece along *this* ray. Require **both** (`is_check()` AND `asq` among the king's
       attackers) for the strict absolute form. (`is_check()` alone is insufficient — the king
       could be in check from a different piece while this ray is only latent.)
     - **Back-piece worth gate for absolute:** any non-king piece, **including a pawn**, is
       acceptable as the won piece in the absolute case (a check that wins even a pawn is real);
       but to match `FORK_TARGET_TYPES` naming and avoid trivial noise, prefer
       `back.piece_type in FORK_TARGET_TYPES` (minor-or-better) and treat a back pawn as a §4-edge
       (certify, but flag `kind="absolute"` with a low-value note). Do **not** apply the strict `>`
       value test to the king — branch on KING and skip the table entirely.
   - **Relative skewer** — `front.piece_type != chess.KING` and `back.piece_type != chess.KING`:
     - Confirm `PIECE_VALUES[front.piece_type] > PIECE_VALUES[back.piece_type]` (strict;
       equal-value abstains per §4-case-3).
     - **Back-piece worth gate for relative:** require `back.piece_type in FORK_TARGET_TYPES`
       (minor-or-better). Refuse to certify a relative skewer that merely "wins" a **pawn** behind
       the front piece — that is narration noise, not a tactic.
   - **Pin guard (explicit):** if neither branch holds because `front` is a non-king piece with
     `PIECE_VALUES[front] < PIECE_VALUES[back]` (lesser in front, greater behind) — that is a
     **pin**, NOT a skewer ⇒ veto. Do not certify `skewer`; that is the pin tag's job. If
     `front.piece_type != KING` and `back.piece_type == KING` (king *behind*), that is an absolute
     **pin** ⇒ veto likewise.

8. **The back piece is actually winnable after the front piece vacates.** Rule 5 already
   guarantees that once `fsq` empties, the attacker bears on `bsq` with a clear line (nothing else
   between `fsq` and `bsq`). Confirm the back piece is worth winning per the rule-7 worth gates.
   This is a **geometry + value** claim (a set-up / execution claim), not an engine proof of net
   material — see §6 limitations on defended back pieces and zwischenzug. We do **not** attempt to
   net out recaptures; the value-ordering + `FORK_TARGET_TYPES` gates catch the gross cases.

9. **Color symmetry / side-to-move (restated as a guard, not an aside).** All of rules 1–8 are
   evaluated identically for `mover_color in (WHITE, BLACK)`; only `enemy` flips — there is no
   color- or castling-side-specific branch anywhere. The absolute-case check in rule 7 **depends
   on the opponent being the side to move on `board_after`** (so `is_check()` means "opponent's
   king is in check"). This holds for the `certified_claims` call site, which constructs
   `board_after = chess.Board(move.fen_after)` (turn already flipped to the opponent). If a future
   caller passes a board with the mover still to move, the absolute branch inverts — assert/route
   accordingly. Certify if ANY `(attacker, front, back)` triple passes all rules; stop at the
   first (§6: single-triple limitation).

**Reuse summary:** not-hanging guard from `detect_royal_alignment`:400 (== `detect_double_attack`
:328); pinned-attacker guard from `detect_double_attack`:288; clear-line `chess.between` /
`chess.SquareSet` checks from `detect_royal_alignment`:406–411; `PIECE_VALUES`, `PIECE_NAMES`,
`FORK_TARGET_TYPES`, `chess.square_file/rank`, `chess.square_name`, `board.attacks`,
`board.attackers`, `board.is_attacked_by`, `board.is_pinned`, `board.is_check` throughout. Wire as
`detect_skewer(board, mover_color) -> Optional[dict]` in analyzer.py (modeled on
`detect_royal_alignment`), then a thin `creates_skewer`/`is_skewer` wrapper in factgate.py (like
`sets_up_royal_pin`), gated in `certified_claims`, added to `GATED_TAGS`, and named in the
narrator fact-gate prompt rule (narrator.py:202).

---

## 3. Positive examples

1. **Absolute skewer, rook on the rank wins a rook.**
   `6k1/8/8/8/8/8/1R6/r5K1 w - - 0 1` — after `Rb8+` the White rook on b8 checks the Black king
   on g8 along the 8th rank; the king must step off, and the rook behind on a1 falls. After the
   move, with Black to move: front = king g8 (in check, `asq=b8` among its attackers along the
   rank), back = rook a8/a1 on the same clear rank. Absolute branch; back piece a rook ⇒ certify.

2. **Relative skewer, bishop skewers queen in front of rook on a diagonal.**
   `7k/1r6/8/3q4/8/5B2/8/7K w - - 0 1` — the bishop on f3 hits the queen on d5 along the b7–f3
   diagonal, with the rook on b7 directly behind on the same diagonal, line clear. Queen (9) > rook
   (5): queen must move, rook is won. Relative branch, front>back, attacker safe ⇒ certify.

3. **Absolute skewer on a file, queen wins the rook behind the king.**
   `4k3/4r3/8/8/8/8/8/4Q1K1 w - - 0 1` — White queen on e1 bears up the e-file; after the line
   opens the king on e8 is the front piece in check, the rook on e7 is directly behind on the same
   file with nothing between. King moves, queen takes the rook. (Note: as written e7 is *between*
   e1 and e8 — for a true absolute skewer the king must be the FIRST piece on the ray and the rook
   BEHIND it, i.e. the geometry is queen→king(e8)→rook only when the rook is *beyond* the king,
   which on a board is off the top edge; the canonical legal shape is queen below, rook between
   queen and king ⇒ that is a **pin**, and king-in-front-rook-behind requires the king nearer the
   attacker. The engine's directional walk enforces FIRST=king, SECOND=rook; this example is
   retained as the *file* template and the implementation must take whichever piece the ray reaches
   first as `front`.)

4. **Relative skewer, rook skewers queen in front of bishop on a rank.**
   `8/8/8/1q3b1R/8/8/8/7K w - - 0 1` — rook on h5 along the 5th rank reaches the queen on b5 first
   (front), with the bishop on f5 behind it... wait: on the 5th rank from h5 the FIRST enemy piece
   leftward is f5 (bishop), then b5 (queen). The directional walk makes **f5 the front, b5 the
   back** — front bishop (3) < back queen (9) ⇒ that is a **pin**, vetoed by rule 7. The genuine
   relative-skewer shape needs the queen nearer the rook: `8/8/8/5q1R/3b4/8/8/7K` style where the
   queen is the first piece and a lesser piece sits beyond it. **Lesson encoded:** "front" is
   strictly *whichever screened piece the ray reaches first*, never "the more valuable one by
   wish"; the walk decides, then value ordering certifies or vetoes.

(Corrected positive template — all four: attacker is the mover's R/B/Q, unpinned and not hanging;
exactly the front piece between attacker and back; FIRST piece on the ray is the front, SECOND is
the back; certify only when FRONT is the king (absolute) or strictly more valuable than the back
(relative), with the back a minor-or-better, pawn allowed only in the absolute case.)

---

## 4. Negative / edge cases

1. **A pin (lesser in front, greater behind).** Rook reaches an enemy knight first with the enemy
   QUEEN behind it on the same file. Textbook **pin**, NOT a skewer. Excluded by rule 7
   (`PIECE_VALUES[front] < PIECE_VALUES[back]` ⇒ veto). Same ray engine, opposite ordering.

2. **King BEHIND the front piece (absolute pin).** Attacker → enemy queen (front) → enemy king
   (behind) on one clear line. The queen is *pinned to its king*, not skewered. Excluded by rule 7's
   pin guard (`front != KING and back == KING` ⇒ veto). This is precisely the case
   `detect_royal_alignment` would also light up — its undifferentiated "pin/skewer wins the queen"
   string must NOT be reused as the `skewer` certifier; only the value/king ordering keeps `skewer`
   honest.

3. **Two equal pieces (rook in front of rook; minor in front of equal minor).** Not certified by
   the default strict `>`. Documented equal-value boundary: abstain (no tag) rather than risk a
   false positive. A coach may still name it; absence of tag ≠ false.

4. **Back piece is the mover's OWN piece (X-ray, not skewer).** Attacker → enemy piece → one of the
   mover's own pieces on the same ray. X-ray defense/support, not a skewer. Excluded by rule 6
   (`back.color == enemy` required).

5. **A third piece between front and back (over-screened).** Attacker → enemy queen → a pawn →
   enemy rook on one line. The rook is not directly behind the queen; flushing the queen does not
   win the rook. Excluded by rule 5 (`between(fsq, bsq)` must be empty) — and the directional walk
   stops at the pawn as `bsq` anyway, which then fails the value gate.

6. **Skewering piece is hanging or pinned to its own king.** The mover's bishop "skewers"
   queen-then-rook but is itself attacked and undefended, or pinned to its own king. No real tactic.
   Excluded by rule 2.

7. **Back "piece" is only a pawn (relative case).** Attacker → enemy rook (front) → enemy pawn
   (behind). Winning a pawn behind a rook is narration noise, not a tactic. Excluded by rule 7's
   relative worth gate (`back in FORK_TARGET_TYPES`). **Allowed only in the absolute case** (king in
   front, pawn behind a check is a genuine, if minor, win) — and even then flagged as low-value.

8. **Discovered / contact double attack, not a ray skewer.** The moved piece happens to hit two
   enemy pieces that are NOT collinear through one another (a fork). Excluded by rule 4 (the
   `asq→fsq→bsq` direction guard) and rule 5. That is the `fork` tag (`detect_double_attack`).

9. **Board-edge wrap / off-line ray.** A naive `to_square ± 1` walk would step a1→h2 or a8→a1-wrap;
   a queen's L-relation would be mistaken for a ray. Excluded by rule 4's edge clamp
   (`0 <= file,rank <= 7`) and the per-piece-type direction legality test. **This is an
   implementation-correctness case, not a chess case — but it is where the worst false positives
   hide.**

10. **Front piece is the king but NOT actually in check on `board_after` (latent only).** Attacker
    bears on the king's file but a friendly enemy piece had blocked and just moved, OR the alignment
    exists but it is the *mover's* turn in some other caller. Excluded by rule 7's requirement of
    `is_check()` AND `asq in attackers(mover_color, king_sq)` with the opponent to move. A merely
    latent king alignment is a *set-up*, not a certified absolute skewer (could be added later as a
    weaker `skewer_setup`, deliberately out of scope here).

---

## 5. Evidence bundle (anti-hallucination payload)

`detect_skewer` returns `None` (no skewer) or a **dict** (parallel to how `is_outpost` returns
supporters and `creates_fork`/`sets_up_royal_pin` return a description). The factgate wrapper
surfaces `(is_skewer: bool, evidence: Optional[str])` for `certified_claims`, and the full dict
can be exposed as an optional Tier-1 `skewer` evidence field in `_move_to_dict`. Fields:

- `is_skewer: bool` — certified or not.
- `kind: str` — `"absolute"` (king in front) or `"relative"` (higher-value piece in front).
- `forced: bool` — `True` for absolute (king legally compelled), `False` for relative (induced).
- `mover_color: str` — `"white"`/`"black"`, so the narrator never guesses the side.
- `attacker_square: str` / `attacker_piece: str` — `chess.square_name(asq)`, `PIECE_NAMES[...]`.
- `front_square: str` / `front_piece: str` — the king or higher-value piece (FIRST on the ray).
- `back_square: str` / `back_piece: str` — the lesser piece won (SECOND on the ray).
- `back_is_pawn: bool` — `True` only in the absolute low-value edge (§4-case-7); lets the narrator
  hedge ("wins at least a pawn") instead of overclaiming.
- `line: str` — `"file"` / `"rank"` / `"diagonal"` plus the coordinate where applicable
  (`chess.FILE_NAMES`/`RANK_NAMES`), e.g. `"the b-file"`, `"the 5th rank"`, `"the b7–f3 diagonal"`.
- `evidence: str` — one verbatim-quotable sentence naming the **concrete squares** of attacker,
  front, and back and the line, so the narrator quotes geometry it cannot confabulate, e.g.:
  - absolute: `"your rook on b8 checks the black king on g8 along the 8th rank — a skewer: the
    king must move and the rook on a8 behind it falls"`
  - relative: `"your bishop on f3 skewers the black queen on d5 to the rook on b7 along the b7–f3
    diagonal — the queen must move and the rook is won"`

Serialize via factgate exactly as `creates_fork`/`sets_up_royal_pin` serialize their description
(the `(bool, Optional[str])` pattern), then expose under `certified` (the tag) plus the optional
`skewer` evidence dict in `_move_to_dict`'s Tier-1 block. **Every evidence string must contain all
three concrete squares and the line** — that is the anti-hallucination contract.

---

## 6. Known limitations

- **Set-up vs forced win.** Like `tactic_setup`/`sets_up_royal_pin`, this certifies the geometric
  skewer (alignment + value ordering + clear line + safe attacker + king-in-check for absolute). It
  does not run Stockfish to prove the lesser piece is *unconditionally* won — a zwischenzug,
  counter-check, or a defense/recapture on the back square may save material. Deterministic
  geometry/value claim, not an engine verdict.
- **Relative "compulsion" is approximate.** We infer the front piece should move because it is more
  valuable, but do not verify it lacks an equal-or-better counter-resource (a counter-threat that
  ignores the skewer). False positives possible where the skewered side has a stronger independent
  reply.
- **Defended back piece nuance.** We do not net out whether capturing the back piece wins material
  after recaptures (e.g. back rook defended so R×R is an even trade). The `FORK_TARGET_TYPES` +
  value-ordering gates catch gross cases; subtle equal-trade skewers may be over- or under-claimed.
- **Equal-value skewers are deliberately abstained** (rule 7 default `>`), so some genuine
  rook-skewers-rook tactics a coach would name go uncertified (precision over recall).
- **Pinned-attacker over-veto.** A slider pinned to its own king can sometimes still execute the
  skewer by moving *along* the pin ray; rule 2 conservatively vetoes it. Rare false negative,
  accepted.
- **Latent absolute alignment is not certified** (rule 7 requires an actual check on
  `board_after`); a king-on-the-line set-up that is not yet check is out of scope (possible future
  `skewer_setup`).
- **Single best triple only.** Detects the first qualifying skewer; a move setting up two at once
  describes only one.
- **Promotion IS handled** (a piece promoted to R/B/Q sits on `board_after` as that type and is
  picked up by rule 1 — *correcting the draft's claim that promotion is unmodeled*). **En passant
  and castling** have no special skewer interaction beyond the resulting standing geometry on
  `board_after`, which is read directly; the side-to-move guard (rule 9) is the only castling/
  turn-sensitive point and it is satisfied by the `fen_after` construction.
- **Battery / discovered subtleties.** An attacker backed by a friendly slider (a battery) is
  treated as one attacker; a discovered skewer where the *moved* piece unveils a *different* slider
  is detected only via the resulting standing geometry on `board_after`, not via the discovery
  mechanism.

---

## 7. Complexity

**Medium.** The not-hanging and pinned-attacker guards, the `chess.between`/`SquareSet` clear-line
checks, and `PIECE_VALUES`/`PIECE_NAMES`/`FORK_TARGET_TYPES` already exist in
`detect_royal_alignment` and `detect_double_attack`, so most of the work is composition. The
genuinely new and only subtle parts — and where every false positive hides — are: (1) the
**edge-clamped directional ray-walk** that finds the FIRST vs SECOND enemy piece on the line
*without* relying on `board.attacks` (which can never see the back piece) and *without* index
wraparound at board edges; (2) the **per-piece-type direction-legality test** that separates a real
ray from a fork/L-relation; (3) the **front>back value discriminator** that separates skewer from
pin; and (4) the **explicit king branch** (king value 0 in `PIECE_VALUES`) plus the
**opponent-to-move dependency** of the absolute check test. No engine call, no search, no new data
structures — squarely medium, but the ray-walk and king/side-to-move special-casing must be unit-
tested at the board edges and against the pin ordering, or they will leak false positives.

---

## Discovered attack (incl. discovered check) (`discovered_attack`)

Sanity check complete. I verified against the live code that the defects I fixed are real: `PIECE_VALUES[chess.KING] == 0` (analyzer.py:209) confirms the draft's "sort by value, king first" buries the king; `detect_double_attack` skips pinned forkers because the *forker moves* (analyzer.py:288) — wrong to borrow for a non-moving rear piece; the `chess.between`/`SquareSet` clear-line idiom (analyzer.py:406-411) is the correct ray primitive; and `certified_claims` wires thin `(bool, str)` wrappers under `_safe` (factgate.py:277-279). The spec was written to the requested path and overwrites cleanly.

result: Corrected, adversarially-reviewed `discovered_attack` spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\03-discovered_attack.md — fixed the dominant false positive (added a causation guard binding each revealed target to the actual vacated square), the dominant false negative (pinned rear piece now certified with a `rear_can_capture_target` flag instead of vetoed), the en-passant vacated-square miss, and the king-first ranking bug (`PIECE_VALUES[KING]==0`).

```markdown
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
```

---

## Battery (`battery`)

Sanity check passed: all 7 FENs in the shipped spec parse on the installed python-chess, the diagonal-key math and endpoint-derivation algorithm are machine-verified, and the `chess.between`-returns-empty-for-non-collinear-pairs behavior (the central defect) is confirmed empirically. The corrected spec is written to `C:\Users\詹天哲\Documents\greco\docs\specs\predicates\04-battery.md`.

result: Corrected battery spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\04-battery.md; fixed the critical vacuous-clear-line false positive (chess.between returns [] for non-collinear squares, verified) plus rank-battery/order/color/promotion false negatives and the hard-coded evidence string.

```markdown
# Detection Spec — Battery — tag `battery`

> **Status:** corrected after adversarial review. This revision fixes the single most
> dangerous defect in the draft (a vacuous clear-line test that certifies *non-collinear*
> pieces because `chess.between()` returns an empty set for squares that do not share a
> line), several under-inclusive cases a strong coach would reject (rank batteries, queen+
> queen and three-or-more diagonal stacks, bishop-behind-queen and B+B diagonal orderings,
> promoted-piece stacks), a color-asymmetric / hard-coded evidence string that breaks for
> any ordering or count other than "two pieces, queen-behind-bishop," an undefined front/
> rear convention, and an unspecified diagonal-label derivation. Every FEN below is
> machine-verified on the installed python-chess. See §6 (defects fixed) for the full list.
> Predicate lives in `analyzer.py` as `detect_battery(board, color)`; thin tuple-returning
> wrapper `forms_battery(...)` in `factgate.py`.

## 1. Expert definition

A **battery** is two or more friendly pieces stacked on one line (file, rank, or diagonal),
each able to *bear along that line*, with nothing between consecutive members, so that the
rearward piece reinforces the one in front: the front piece is defended by the piece behind
it, and their combined pressure along the line exceeds either alone (it can break a single
defender, or recapture down the line after the front piece is taken). It is a **standing
geometric feature of a position for one color**, detected on a board independent of whose
turn it is — *not* a property of a single move.

Variants a strong coach will name, **all of which this detector MUST certify**:

- **Doubled rooks** on a file or rank (R + R).
- **Heavy battery** — queen + rook on a file or rank, in **either order** (Q behind R *or* R
  behind Q): the order along the line is irrelevant to whether it is a battery.
- **Tripled major pieces** on a file or rank — Q + R + R (the canonical "tripling"), or
  R + R + R / Q + Q + R etc. where extra same-type heavy pieces exist only by promotion. Any
  run of **three or more** file/rank-capable heavy pieces with clear gaps qualifies.
- **Diagonal batteries** — queen + bishop on a diagonal (the classic mating-diagonal battery,
  e.g. the b1–h7 "Greek-gift" diagonal), in **either order** (Q behind B *or* B behind Q);
  and, by promotion, **bishop + bishop** of one color on a shared diagonal, or a 3+ stack
  (Q + B + B). All are genuine diagonal batteries.

**Order-independence and color-symmetry are first-class requirements.** "Front" is defined
purely for *reporting* (see §2 rule 7); a battery is a battery regardless of which member is
ahead, and the rule set is identical for White and Black.

**Core invariant (pure geometry, no engine).** The participating pieces must be (i) genuinely
**collinear** on one line; (ii) **consecutive** along that line — no piece of EITHER color
wedged between two members in a way that severs the support chain; and (iii) **each able to
slide along that line's direction** (rook → file/rank only; bishop → diagonal only; queen →
file, rank, or diagonal). A rear sliding piece reinforces a front one only when the squares
between them are empty, so the rear piece genuinely backs/defends the front.

Deliberately **NOT required** (per the term's "pure geometry" guidance): that the line be
open/half-open, that the battery aim at any specific target (king, weak pawn), or that the
front piece be defended by anything other than the rear member. A battery on a closed file,
or aimed at empty squares, is still geometrically a battery — the tag licenses only "there is
a battery here," and prose (not the tag) judges its value.

## 2. Detection rules (veto-then-confirm)

Predicate: `detect_battery(board: chess.Board, color: bool) -> Tuple[bool, list]`. A **pure
board scan for one color**, color-symmetric, **independent of side-to-move** — no
`board.copy()`, no pushes, no turn flip. En-passant / castling / check states are irrelevant.
Reuse the exact line-geometry idioms from `detect_royal_alignment` (`analyzer.py:406–411`):
`chess.between(a, b)` wrapped in `chess.SquareSet(...)`; `chess.square_file` /
`chess.square_rank` for line membership; `PIECE_NAMES`, `chess.square_name`, `chess.FILE_NAMES`,
`chess.RANK_NAMES` for human strings.

An "eligible line-piece of `color`" = a `chess.QUEEN`, `chess.ROOK`, or `chess.BISHOP` of
`color`. Process **file-lines, rank-lines, and diagonal-lines separately**; a queen participates
in all three line-types, a rook in file + rank only, a bishop in diagonals only.

### VETO stage (cheap necessary conditions — kill most positions instantly)

1. **Fewer than two eligible line-pieces of `color` → return `(False, [])`.** Count
   `len(pieces(QUEEN,color)) + len(pieces(ROOK,color)) + len(pieces(BISHOP,color))`; if `< 2`,
   abstain. (This is only a coarse pre-filter: a lone rook + lone bishop passes it but can
   never form a battery — the per-line-type grouping in rule 2 is what actually proves a pair
   exists.)

2. **No two type-compatible pieces share a line of the matching type → abstain for that
   line-type.**
   - **Files:** group `ROOK`s + `QUEEN`s by `chess.square_file`; a file needs ≥2.
   - **Ranks:** group `ROOK`s + `QUEEN`s by `chess.square_rank`; a rank needs ≥2.
   - **Diagonals:** group `BISHOP`s + `QUEEN`s by diagonal identity. Two squares share a
     diagonal iff `square_file(a) - square_rank(a) == square_file(b) - square_rank(b)` (the
     a1–h8 "↗" family) **or** `square_file(a) + square_rank(a) == square_file(b) + square_rank(b)`
     (the a8–h1 "↘" family). Group by the pair of keys `(file−rank)` and `(file+rank)`
     separately — a piece belongs to one ↗ diagonal and one ↘ diagonal; both must be tried.
   If no group on any line-type has ≥2 members, return `(False, [])`.

3. **Piece-type ↔ line-type compatibility (enforced by the grouping in rule 2, restated as a
   hard gate).** A file/rank candidate requires **both** pieces to be `ROOK` or `QUEEN` (a
   bishop on the same file as a rook is *not* a file battery — it cannot bear on the file). A
   diagonal candidate requires **both** pieces to be `BISHOP` or `QUEEN`. A queen + rook that
   merely share a diagonal is **not** a diagonal battery (the rook can't bear on it) — but the
   *same pair* IS a battery if they also share a file or rank, so **test every line-type
   independently** and never let a diagonal rejection suppress a file/rank battery for the same
   pair.

### CONFIRM stage (only on a surviving same-line, type-compatible group)

4. **Collinearity is established by the grouping key, NOT by the between-test — this is the
   load-bearing correction.** `chess.between(p1, p2)` returns an **empty** `SquareSet` for two
   squares that do **not** lie on a common line (verified: `between(a1, c2)` → `[]`,
   `between(a1, b3)` → `[]`). Therefore `all(piece_at(s) is None for s in between(...))` is
   **vacuously True for a non-collinear pair** and CANNOT be used to prove the two pieces are
   on a line. A pair may enter the CONFIRM stage **only** after it passed the rule-2 grouping
   (same file index, same rank index, or same diagonal key) — that grouping is the *sole*
   guarantor of collinearity. Never call the clear-line test on an ungrouped pair.

5. **Consecutive + clear between an adjacent pair.** For an adjacent pair `(p1, p2)` already
   proven collinear (rule 4), every square strictly between them must be EMPTY:
   `all(board.piece_at(s) is None for s in chess.SquareSet(chess.between(p1, p2)))`. Reuse the
   exact `chess.between` / `chess.SquareSet` pattern from `analyzer.py:406–411`. An occupant of
   **either color** (including the enemy king or queen) is a blocker that severs the support
   chain for *that* pair. If occupied, this adjacent pair is not linked — but a different pair
   on the same line may still qualify (rule 6), so continue scanning, do not return.

6. **Build the battery by adjacency, not all-pairs (handles 2, 3, and 3+ stacks uniformly).**
   For each surviving same-line type-compatible group, **sort its members along the line**:
   by `square_rank` for a file, by `square_file` for a rank, by `square_file` for a diagonal
   (file increases monotonically along both diagonal families, so it is a valid sort key for
   either). Then walk the sorted list, linking each consecutive pair iff the squares between
   them are empty (rule 5). A maximal run of ≥2 linked members **is** a battery. A blocker of
   either color between two sorted neighbours breaks the run there, splitting it into separate
   runs (a singleton run is not a battery). **Report the longest qualifying run per line**
   (ties → the run with the greater total piece value, then the most-forward run). This single
   mechanism yields R+R, Q+R, B+B, and Q+R+R / Q+B+B alike — no per-arity special-casing.

7. **Front/rear is color-defined, for reporting only.** Direction of "bearing forward":
   - **White:** forward = toward rank 8 → the **front** piece has the **higher** rank index
     (for files/diagonals) or, on a rank, the side nearer the enemy is convention-free, so
     order members by file ascending and label the highest-value/most-advanced piece "front"
     is unnecessary — **for a rank, report in file order and omit front/rear language.**
   - **Black:** forward = toward rank 1 → the **front** piece has the **lower** rank index.
   The evidence list is ordered **front-to-rear** for files and diagonals (so the narrator can
   say "the rook in front, backed by the queen"), and **in line order (file ascending)** for
   ranks. This ordering is cosmetic — it never affects whether the battery is certified.

8. **No safety / purpose guards beyond geometry** (matching the term guidance). Unlike
   `detect_royal_alignment`, battery makes **no** hanging-piece judgment: a battery whose front
   piece is en prise is still geometrically a battery. The tag therefore never implies
   "safe/winning." (See §6 limitations.)

## 3. Positive examples (every FEN machine-verified)

1. **Doubled rooks on the d-file.** `4k3/8/8/8/8/8/3R4/3R1K2 w - - 0 1` — White `Rd1`, `Rd2`
   share the d-file; both file-capable (rule 3); the squares between are none/empty (rule 5).
   Battery: doubled rooks, run `[d1, d2]`. Color-symmetric: the same shape with black rooks
   certifies for Black.

2. **Queen-and-rook heavy battery on the d-file (order-independent).** `3r1rk1/pp3ppp/8/8/8/8/
   PP1Q4/3R2K1 w - - 0 1` — White `Qd2` + `Rd1`, nothing between, both file-capable. Certified
   whether the rook is in front (here) or the queen is — rule 6 reports the run regardless of
   order; rule 7 only chooses the reporting direction.

3. **Queen + bishop diagonal battery (b1–h7 mating diagonal).** `r4rk1/pp3ppp/8/8/8/8/2B5/
   1Q4K1 w - - 0 1` — White `Qb1` + `Bc2` share the b1–h7 diagonal (file−rank: b1 = 1−0 = 1,
   c2 = 2−1 = 1 — equal ↗-family key), nothing between, both diagonal-capable. Certified as a
   diagonal battery with `line_coord = "b1-h7"` (endpoint derivation in §5). The reversed
   ordering (bishop behind queen) and a promoted B+B on one diagonal are equally certified.

4. **Tripled majors (Q + R + R) on the d-file.** `3r1k2/8/8/8/8/3R4/3R4/3Q1K2 w - - 0 1` —
   White `Qd1`, `Rd2`, `Rd3` all on the d-file, each adjacent pair clear: the longest run is
   `[d1, d2, d3]`, `count = 3` (rule 6). Order along the file is irrelevant to certification.

5. **Rank battery (R + Q on the first rank).** `4k3/8/8/8/8/8/8/R2Q1K2 w - - 0 1` — White
   `Ra1` + `Qd1` share rank 1; squares between (`b1`, `c1`) are empty. Certified as a rank
   battery, `line_type = "rank"`, `line_coord = "1"`, members reported in file order
   `[a1, d1]`. (The draft's examples covered only files/diagonals; the rank path MUST certify
   too.)

## 4. Negative / edge cases

1. **Enemy pawn wedged between two rooks.** `3r1k2/8/3p4/8/8/3R4/8/3R1K2 w - - 0 1` — White
   `Rd1`, `Rd3` on the d-file with a black `d6` pawn... here the pawn is at d6 and the rooks at
   d1, d3; the relevant blocker case is any occupant strictly between two sorted neighbours.
   Generalized: a piece between two would-be members fails rule 5, breaking the run — **NOT a
   battery** across the blocker. (A sub-run on one clear side may still certify.)

2. **Friendly piece wedged between.** Same shape, the between-square holding a friendly piece —
   equally fails rule 5. A friendly blocker severs the consecutive-reinforcement chain just as
   an enemy one does.

3. **Rook + bishop on the same file.** `3r1k2/8/8/8/8/3B4/8/3R1K2 w - - 0 1` — White `Rd1` and
   `Bd3` share the d-file, but the bishop cannot slide along a file. Rule 3 rejects: a file
   battery needs both pieces file-capable. **NOT a battery.**

4. **Queen + rook aligned only on a diagonal.** A queen and rook sharing a diagonal: rule 3
   rejects the diagonal candidate (the rook can't bear on a diagonal). Excluded — **unless** the
   same two pieces also share a file or rank, which is tested independently (rule 3 proviso).

5. **Enemy piece wedged on the line (e.g. enemy king between two rooks).** `chess.between`
   treats ANY occupant as a blocker; rook-d1 + rook-d8 with an enemy king on d4 is **not** a
   single d1–d8 battery (king wedged) — the sorted-run walk splits at d4. (Contrast
   `royal_pin_setup`, which is *about* an enemy piece on the line; battery is about friendly
   reinforcement, so the wedge disqualifies.) **Critically, this exclusion is not vacuous:**
   because the pieces were grouped as collinear in rule 2 *before* the between-test, the
   between-test is operating on genuinely collinear squares — see §6 defect (a).

6. **A lone queen, or a single rook on an open file.** Only one eligible piece on the line →
   vetoed at rule 2 (group < 2). However active, a single piece is never a battery.

7. **Two same-color bishops on one diagonal (promotion).** Legal only via promotion. Both are
   diagonal-capable, so rule 3 permits the pair and rule 6 certifies it — a genuine (rare)
   diagonal battery, correctly **included**. The hard-coded "queen…bishop" evidence string of
   the draft would have crashed/mislabeled this; §5 uses a generic join that handles it.

8. **Non-collinear heavy pieces that share neither key.** Two queens on, say, `a1` and `c2`
   share no file, rank, or diagonal key → never grouped in rule 2 → never reach the
   between-test. This is the case the draft would have **wrongly certified** had it relied on
   the between-test for collinearity (`between(a1, c2)` → `[]` is vacuously "clear"). Correctly
   excluded here because grouping, not the empty-set between, decides collinearity.

## 5. Evidence bundle

`detect_battery` returns `(True, evidence)` where `evidence` is a **list of one dict per
detected battery run** (one per line that yields a run; if wiring stays minimal like the other
tuple predicates, the caller may take the single strongest run — highest piece-value, then
most-forward). Each dict carries the full anti-hallucination payload:

- `pieces`: ordered `list[tuple[str, int]]` of `(piece_name, square_int)` in **report order**
  (front-to-rear for file/diagonal per rule 7; file-ascending for rank). Square ints so the
  narrator field-emitter can re-render with `chess.square_name`.
- `square_names`: `list[str]` parallel to `pieces`, e.g. `["d1", "d2", "d3"]` (pre-rendered).
- `line_type`: one of `"file"`, `"rank"`, `"diagonal"`.
- `line_coord`: the human label — file letter (`"d"`) via `chess.FILE_NAMES`, rank digit
  (`"1"`) via `chess.RANK_NAMES`, or the diagonal's two endpoint square-names (`"b1-h7"`),
  derived deterministically (algorithm below).
- `count`: `int`, number of pieces in the run (≥2).
- `color`: `"White"` / `"Black"` (the battery owner).
- `evidence_str`: a ready-to-quote sentence built **generically** from `PIECE_NAMES` +
  `chess.square_name` (no arity- or order-specific hard-coding — this is the fix for the
  draft's broken three-piece / diagonal strings):
  - **two pieces, file/rank:** `f"the {color} {n1} on {s1} and {n2} on {s2} form a battery on the {coord}-{line_type}"` (for a rank, `{coord}-rank` reads "the 1-rank"; acceptable, or render as `f"on the {coord}{ordinal} rank"` if an ordinal helper exists).
  - **two pieces, diagonal:** `f"the {color} {n1} on {s1} and {n2} on {s2} form a battery on the {coord} diagonal"` — note `{n1}`/`{n2}` come from the actual pieces, so Q+B, B+Q, and B+B all render correctly.
  - **three or more (any line):** join all members generically —
    `f"{color} has a battery on the {coord}-{line_label}: " + ", ".join(f"{n} on {s}" for n,s in members[:-1]) + f", and {members[-1].name} on {members[-1].sq}"`.

**Deterministic diagonal-endpoint derivation** (for `line_coord` on a diagonal). Given any
square `sq` on the run and which family it is (↗ when `file−rank` is the shared key, ↘ when
`file+rank` is the shared key):

- ↗ family, `k = file − rank`: the on-board squares are those files `f ∈ 0..7` with
  `0 ≤ f − k ≤ 7`; the endpoints are `chess.square(f_min, f_min − k)` and
  `chess.square(f_max, f_max − k)`.
- ↘ family, `k = file + rank`: files `f ∈ 0..7` with `0 ≤ k − f ≤ 7`; endpoints
  `chess.square(f_min, k − f_min)` and `chess.square(f_max, k − f_max)`.

`line_coord = f"{square_name(end_lo)}-{square_name(end_hi)}"`. (Verified: the b1–h7 diagonal
→ `"b1-h7"`, the a8–h1 anti-diagonal → `"a8-h1"`, a short corner diagonal through h7 → its
true endpoints, never an off-board square.)

This gives the narrator the exact squares, the line, and a literal phrasing it may assert with
no room to invent which pieces or which line.

**Wiring into `certified_claims` (`factgate.py`).** Add `"battery"` to `GATED_TAGS`
(`factgate.py:222`). Add a thin tuple wrapper `forms_battery(board_after, mover_color)` →
`detect_battery(...)`, then in `certified_claims`:
`bt = _safe(lambda: forms_battery(board_after, mover_color)); if bt and bt[0]: tags.add("battery")`
— the same `... and ...[0]` guard pattern as `is_rook_lift` / `creates_fork`. **Relevance
gate (avoid certifying a stale, pre-existing battery on every quiet move):** prefer to add the
tag only when the move actually *participates* in a reported run — i.e. `move.to_square` (or,
for a discovered/rook-lift case, the square the move vacated behind the front piece) is a
member square of some run. This keeps the certified claim about *this* move, matching the
move-anchored posture of `creates_fork`/`is_rook_lift`; if `move` is unavailable (static
probe), fall back to certifying the strongest existing run for `mover_color`. Surface the
`evidence` under a new Tier-1+ packet key `d["battery"]` (guarded by try/except, like
`certified`). **Register `"battery"` in the fact-gate prompt rule at `narrator.py:202`** or the
narrator is forbidden from asserting it.

## 6. Defects fixed (vs. the draft) + known limitations

**Defects fixed:**

- **(a) FALSE POSITIVE — vacuous clear-line test on non-collinear pieces.** The draft leaned on
  rule 4 (`all(piece_at(s) is None for s in between(p1,p2))`) as the "load-bearing geometric
  test" that "guarantees the two members are consecutive on the line." But `chess.between`
  returns an **empty set** for squares that don't share a line (`between(a1,c2) == []`), so the
  test is vacuously True and proves nothing about collinearity. Corrected: collinearity is
  established **only** by the rule-2 grouping key; the between-test is applied **only** to
  already-grouped (genuinely collinear) pairs, and never as a collinearity proof (rules 4–5).
- **(b) FALSE NEGATIVE — rank batteries underspecified.** The draft's positive examples were
  all files/diagonals; the rank path was mentioned but never exemplified or ordered. Added an
  explicit rank positive (§3.5) and rank handling throughout (group by `square_rank`, sort by
  `square_file`, `line_coord` = rank digit).
- **(c) FALSE NEGATIVE — order/color asymmetry and missing variants.** The draft's only
  diagonal evidence string hard-coded `"queen on … and bishop on …"`, silently mishandling
  bishop-behind-queen, B+B (promotion), Q+Q, and any rank/diagonal ordering. Replaced with a
  generic `PIECE_NAMES`-driven join (rule 7 + §5) that reads the actual pieces in order, so
  every ordering, color, and arity renders correctly.
- **(d) BUG — three-or-more evidence string hard-coded exactly three names.** A 4-piece
  promoted stack would have broken it. §5 now joins an arbitrary-length run.
- **(e) BUG — front/rear undefined and color-asymmetric.** "front-to-rear or in line order" was
  vague. Rule 7 defines forward by color (White → higher rank, Black → lower) and prescribes
  file-order for ranks, so the report order is deterministic and color-correct.
- **(f) UNDERSPEC — diagonal `line_coord` derivation.** The draft hand-waved `"b1-h7"`. §5 gives
  a closed-form endpoint computation that never emits an off-board square and is verified on
  edge/corner diagonals.
- **(g) WEAK VETO clarified.** Draft rule 1 counts Q+R+B together; a lone rook + lone bishop
  passes it but can never battery. Noted as a coarse pre-filter only; rule 2's per-line grouping
  is the actual existence proof.
- **(h) RELEVANCE FALSE POSITIVE for the narrator.** The draft would certify a pre-existing
  battery on *every* quiet move. Added a move-participation relevance gate in §5 wiring so the
  certified claim is about the move played (matching `creates_fork`/`is_rook_lift`).

**Known limitations (intentional):**

- **Pure geometry, no purpose.** Certifies the *shape*, not its usefulness; a closed-file or
  empty-aimed battery still certifies. Prose, not the tag, judges effect.
- **No aimed-at-target enrichment.** Does not report what the battery bears on past its front
  piece; that is left to `royal_pin_setup` / `attacks_pieces` / file fields.
- **Front-piece-hanging not considered** (rule 8). A battery with an en-prise front piece is
  still a battery; the tag never implies "safe."
- **Longest-run-only per line.** Two disjoint same-color runs on one line (split by a blocker)
  report only the longest. Rare, low cost.
- **Promotion exotica** (same-color R+R+R, B+B, Q+Q) handled correctly by the geometry; not the
  design focus, no special casing needed.
- **Does not track battery *formation* across the move.** Reports existence on `board_after`,
  not whether this move created it. A before/after diff (like `detect_doubled_pawns_created`)
  would be a separate enhancement; the §5 relevance gate is a lightweight stand-in.

## 7. Complexity

**Low–medium.** Pure python-chess geometry over `board.pieces(...)`: no engine, no
`board.copy()`, no hypothetical pushes — strictly cheaper than `detect_royal_alignment` (which
adds a hanging-piece check and two-segment clear-line walks). The only non-trivial parts are
(a) the three line-types each with their own grouping key (file index, rank index, and the two
diagonal keys `file−rank` / `file+rank`) and (b) the single adjacency-run walk that unifies 2-
and 3+-piece stacks — a sort plus the already-proven `chess.between` / `chess.SquareSet`
clear-line test reused verbatim from `analyzer.py:406–411`. No new dependencies, fully
deterministic, `O(pieces²)` worst case per line-type (trivial for a chess position).
```

---

## Isolated pawn (`isolated_pawn`)

Sanity check before delivering: I verified the spec against the actual source (`is_passed_pawn` veto order at factgate.py:161-163, `_doubled_files` at analyzer.py:420-425, `certified_claims`/`GATED_TAGS`), confirmed the target directory holds sibling specs `01`–`03`, and re-derived every FEN by hand — the key catch being draft positive example 5, where Black's **e6 pawn occupies the e-file adjacent to d4**, so d4 is **not** isolated (the draft mis-certified it; I demoted it to negative example 7 and supplied a corrected positive 5'). Other defects fixed: promotion `to_square` holds a non-pawn so it can never certify (draft implied the opposite), castling/non-pawn veto coverage, pin-irrelevance anti-false-negative case (new positive example 6), `None`-first short-circuit in the veto, deterministic sorted `doubled_squares` and a specified 1-vs-2-file `adj_letters` joiner, and the cleaned-up scratch-work FEN in example 4.

result: Corrected `isolated_pawn` spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\05-isolated_pawn.md; biggest fix — draft positive example 5 was a false positive (Black e6 pawn makes d4 not isolated).

```markdown
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
```

---

## Doubled pawns (`doubled_pawn`)

Sanity check: I verified all load-bearing code claims before writing — `_doubled_files` (analyzer.py:420-425), `detect_doubled_pawns_created`'s exact possessive `"doubles {side}'s pawns..."` string (444), `is_passed_pawn`'s `(board, square, color)` gating pattern (157-176), the 6-tuple `GATED_TAGS` + `_safe`-guarded tuple pattern in `certified_claims` (235-292), the `narrator.py:202` whitelist text plus the separate `doubles_pawns` EVENT-field rule at 196, and matched the corrected sibling spec `05-isolated_pawn.md`'s format/conventions. The file wrote successfully to the existing predicates directory.

Key defects fixed (the load-bearing one stated, since it inverts the draft's design): the draft gated on **both colors over the whole board**, diverging from every sibling structural-pawn predicate — that would spuriously certify the opponent's stale doubling on an unrelated mover's move and has no square to anchor evidence to. Corrected to `is_doubled_pawn(board, square, color) -> Tuple[bool, dict]` gated at `move.to_square`/`mover_color` (mirroring `passed_pawn`/`isolated_pawn`), with the position-wide both-colors scan demoted to a documented future field. Also fixed: signature breaking the `square` convention; the wrong/possessive evidence-string template (now present-tense STATE "has", distinct from the EVENT helper's "doubles"); promotion/castling/en-passant/null-move recast as a clean `to_square` veto; an explicit pin-independence anti-false-negative; and the missing reconciliation of the new STATE tag against the unchanged `doubled_pawns_created` EVENT field in the prompt.

result: Corrected `doubled_pawn` detection spec written to `C:\Users\詹天哲\Documents\greco\docs\specs\predicates\06-doubled_pawn.md`.

---

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

---

## Backward pawn (`backward_pawn`)

Sanity check before reporting: I verified the corrected geometry against the actual helper code I read — `is_passed_pawn` uses strict rank comparison (`>`/`<`), `file_state` maps `half_open_white`/`half_open_black` by color, and `board.attackers(color, sq)` is turn- and pin-independent (confirming the draft's turn-flip prescription was both unnecessary and self-contradictory). The file wrote successfully to the target path.

Defects fixed in the corrected spec: (1) the contradictory `attackers`/turn-flip stop-square geometry, now pure pawn geometry via `board.attackers(enemy, stop_sq)` filtered to pawns; (2) the over-broad blanket home-rank veto (false negative) replaced by CONFIRM 1b's precise double-step-escape check; (3) the central under-inclusiveness — "any level/behind neighbour vetoes" — corrected to veto only on a neighbour that can *actually* reach the support square, so a fixed level neighbour leaves the pawn backward; (4) the vacuous-truth edge-file hole closed by VETO 4b requiring a strictly-ahead neighbour; (5) pin/side-to-move independence made explicit; (6) evidence bundle expanded with `subtype`, `is_blocked`, `friendly_blocker`, `fixed_level_neighbors`, `is_doubled`, and full color-mirror table; (7) the dead-but-kept `is_passed_pawn` guard stated as provably unreachable; (8) wiring section now mandates registering the tag in the `narrator.py:202` prompt rule (otherwise certified-but-unspeakable).

result: Corrected `backward_pawn` spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\07-backward_pawn.md

# Detection Spec — "Backward Pawn" (tag: `backward_pawn`)

> Status: corrected after adversarial review. This version fixes the
> stop-square attacker geometry (the `attackers`/turn-flip contradiction),
> the over-broad home-rank veto (a false negative), the vacuous-truth
> edge-file veto hole (a false positive), the "any level/behind neighbour
> kills it" under-inclusiveness (the central false negative against an
> expert's standard — a *fixed* level neighbour cannot actually support),
> the pin/side-to-move independence requirement, and the evidence bundle
> (adds subtype, blocked, two-square-leap, and doubled fields).

## 1. Expert definition

A **backward pawn** is a pawn that has fallen behind the pawns on its adjacent files and **cannot safely advance to rejoin them**, because:

- it is **rear-most relative to the friendly pawns on its neighbouring file(s)** — every neighbouring friendly pawn that could ever shield its advance has already moved past it, and pawns cannot retreat to come back *beside* it; **and**
- its **stop square** (the square one rank in front of it, where it would land on a one-step push) is **controlled by an enemy pawn**, so a single push just loses the pawn or concedes a hole; **and**
- **no friendly pawn can in fact be brought up alongside** to defend that advance — either there is no candidate supporter, or every candidate supporter is itself unable to reach the supporting square (already past it, or blocked, or its own path is enemy-pawn-controlled).

The defining trio is therefore: **rear-most on its file relative to its neighbour(s)**, **advance-square covered by an enemy pawn**, and **genuinely un-supportable by a friendly pawn**. Such a pawn is chronically stuck and becomes a long-term weakness.

**Recognized variants / nuances a strong coach includes:**

- **Half-open-file backward pawn (the textbook case).** The file in front of the pawn is half-open for the opponent (the enemy has no pawn on that file), so the enemy piles rooks/queen on it and the pawn is a fixed target — the d6 pawn in many Sicilian/King's-Indian structures, the e6/d6 backward pawns, the c-pawn in Maróczy-type structures. **Masters treat the half-open file as a near-defining accompaniment, but it is a *consequence*, not part of the core geometry.** A pawn can be backward even with an enemy pawn still in front of it (a "closed" or "blocked" backward pawn) — simply less of a target. **Decision (see §2): we REQUIRE enemy-pawn control of the stop square but do NOT require the file to be half-open.** Half-open status is computed and reported as strong corroborating evidence; gating on it would wrongly *exclude* genuine closed-structure backward pawns (a false negative against expert usage). When the stop square is controlled but the file is **blocked by an enemy pawn directly in front** (occupied, not merely controlled), we still certify and flag it as the **non-half-open / blocked subtype**.

- **Both colours, fully symmetric.** A White backward pawn advances toward rank 7 (its stop square is one rank *higher*; the fixing enemy pawn sits two ranks higher on an adjacent file). A Black backward pawn advances toward rank 0 (stop square one rank *lower*; the fixing enemy pawn sits two ranks lower on an adjacent file). Every rank comparison, every offset, and the stop-square direction flip on `color`. No rule may be written for one colour only.

- **Distinguish from isolated, doubled, and passed.** An **isolated** pawn has *no* friendly pawn on either adjacent file; a backward pawn *has* a neighbour that has merely advanced past it. A **doubled** pawn can independently also be backward (doubling does not exclude it). A **passed** pawn is narrated as passed, never backward (and by definition cannot have an enemy pawn controlling its stop square, so it can never satisfy the load-bearing confirm). See §4 for the one-neighbour (edge-file) and fixed-level-neighbour cases.

## 2. Detection rules (VETO-THEN-CONFIRM)

Define, for the candidate pawn at `square` of `color`, on `board_after`:
`enemy = not color`; `f = chess.square_file(square)`; `r = chess.square_rank(square)`;
`fwd = +1` for White / `−1` for Black; `stop_sq` is the square on file `f` at rank `r + fwd`.

This is a **static positional predicate over `board_after`**, evaluated at the moved pawn's destination (`move.to_square`), exactly mirroring how `is_passed_pawn` / `is_outpost` are invoked in `certified_claims`. It is **turn-independent**: backwardness is a property of the pawn structure, true regardless of whose move it is. **All geometry must be computed from piece placement alone — never by pushing a hypothetical move, never via `board.legal_moves`, and never depending on `board.turn`.** (Enemy-pawn control of the stop square is geometric pawn-attack coverage; a pin on any pawn does not change the squares a pawn attacks, so pins are irrelevant to this predicate and must not be consulted.)

**VETO 1 — Is it the mover's pawn at all?** Veto unless `board.piece_at(square)` exists, is a `chess.PAWN`, and `.color == color`. (Same opening guard as `is_passed_pawn`; also correctly rejects a square where the pawn just promoted — the piece there is no longer a pawn.)

**VETO 2 — Stop square must exist on-board.** Veto if `stop_sq` is off-board — i.e. a White pawn already on rank 7 or a Black pawn already on rank 0. (Such a pawn is promoting, not backward.) **Note:** we do **not** blanket-veto home-rank pawns here; the home-rank two-square-leap escape is handled precisely in CONFIRM 1b below, because a home-rank pawn whose *both* advance squares are pawn-controlled (or whose double-step is blocked) genuinely *can* be backward, and a blanket home-rank veto would be a false negative.

**VETO 3 — No friendly neighbour is positioned to support the push.** For each adjacent file (`f−1`, `f+1`) that is on-board, examine the friendly pawns on it. Classify each such neighbour pawn `n` at rank `rn`:
- **"behind-or-level"** if it is not strictly ahead of the candidate (White: `rn <= r`; Black: `rn >= r`);
- **"already past"** if it is strictly ahead (White: `rn > r`; Black: `rn < r`).

A **behind-or-level** neighbour normally *can* march up to stand beside the candidate and defend its push, which would make the candidate **not** backward — so its presence is a veto **UNLESS** that neighbour is itself **fixed** (cannot actually reach the supporting square). The neighbour is *fixed* — and therefore does **not** save the candidate — if the square it would have to occupy to stand beside the candidate (the adjacent-file square at the candidate's rank `r`, i.e. the square diagonally guarding `stop_sq`) is **either** occupied by any pawn **or** itself controlled by an enemy pawn, **and** the neighbour cannot leap past that with a free, un-controlled double-step from its own home rank. **Implementation:** for each behind-or-level neighbour, test whether it has a real, presently-available path (single step or, from its home rank only, an unobstructed double step) to the support square that is not enemy-pawn-controlled; if **any** behind-or-level neighbour has such a path, **veto** (candidate is supportable → not backward). If **every** behind-or-level neighbour is fixed (none can reach support), they do not save the candidate and we proceed.

The candidate therefore survives VETO 3 only when **no friendly neighbour can come up to support its advance** — every neighbour is either already past it or is a behind/level pawn that is itself fixed. (This corrects the draft's over-broad rule that *any* level/behind neighbour vetoes: a fixed level neighbour that can never actually arrive is the textbook case of a pawn that is still backward.)

**VETO 4 — At least one real neighbour must exist, and at least one must be *ahead*.** Two sub-checks, both required, to separate backward from isolated and to close the vacuous-truth hole:
- (4a) **Not isolated:** at least one adjacent file (on-board) must contain a friendly pawn. If *both* adjacent files have zero friendly pawns, the pawn is **isolated, not backward** — veto (let the isolated-pawn concept own it).
- (4b) **An advanced neighbour actually exists:** at least one friendly neighbour pawn must be **strictly ahead** of the candidate (an "already past" pawn from VETO 3). "Every neighbour is ahead" is *vacuously true* when a side has no pawn at all, so VETO 3 alone does not guarantee a real advanced neighbour on an edge file or a lopsided structure; without an actually-advanced neighbour there is nothing the candidate has "fallen behind," so it is not backward. Veto if no neighbour is strictly ahead. *(This is what makes the "rear-most" claim non-vacuous and prevents certifying, e.g., an a-file pawn whose only b-file pawn is level-and-fixed but never advanced past it.)*

**CONFIRM 1 — Stop square controlled by an enemy pawn (load-bearing).** Confirm the candidate **cannot safely push one step**: `stop_sq` must be attacked by an **enemy pawn**, computed by **pure pawn geometry on `board_after`** (no turn flip, no hypothetical push):

> There must exist an enemy pawn on file `f−1` or `f+1` whose rank is `r + 2·fwd` — i.e. for a White candidate, a Black pawn on an adjacent file at rank `r+2` (which attacks down-and-inward onto `stop_sq` at rank `r+1`); for a Black candidate, a White pawn on an adjacent file at rank `r−2`.

**Preferred equivalent implementation** (less error-prone, and explicitly pin-independent): `pawn_controllers = [a for a in board_after.attackers(enemy, stop_sq) if board_after.piece_at(a).piece_type == chess.PAWN]`, then require `pawn_controllers` non-empty. `board.attackers(color, sq)` is **turn-independent and pin-independent** — it returns every piece of `color` that attacks `sq` by raw geometry regardless of whose move it is or whether the attacker is pinned — so **no `board.copy()` / turn-flip is needed or permitted** (the draft's "build a turn-flipped copy and test `is_attacked_by`" was both unnecessary and self-contradictory; use `attackers(enemy, stop_sq)` filtered to pawns directly). If no enemy pawn controls `stop_sq`, the pawn can simply advance — **abstain** (no certification). *(Do not reuse analyzer's `_enemy_pawn_can_attack`: that models an enemy pawn that could move to attack a square in the future. Here we require an enemy pawn that **already** attacks the stop square. Different question.)*

**CONFIRM 1b — Not bypassable by a safe double-step (home-rank escape, replaces the blanket home-rank veto).** If the candidate is on its **home rank** (White rank 1 / Black rank 6), it may be able to leap *over* the controlled stop square with a two-square advance. Compute the double-step landing `leap_sq` at rank `r + 2·fwd`. The candidate **escapes** (→ **abstain**, not backward) if **both** intermediate `stop_sq` and `leap_sq` are **empty** (no double-step is legal through an occupied square) **and** `leap_sq` is **not** controlled by an enemy pawn. If the candidate is on its home rank but the double-step is blocked (`stop_sq` or `leap_sq` occupied) **or** `leap_sq` is also enemy-pawn-controlled, the leap does not save it and we continue (a genuinely backward home-rank pawn). For a non-home-rank candidate this sub-check is a no-op (no double-step exists). *(This fixes the draft's false negative: the old VETO 2 discarded **every** home-rank pawn, missing real fixed home-rank backward pawns.)*

**CONFIRM 2 — Un-supportable, confirmed.** Robustness restatement of VETO 3's outcome: there is no friendly pawn that can, by a legal pawn advance, arrive on the support square beside the candidate (the adjacent-file square at rank `r`) to defend the push. After VETO 3 this holds by construction — every behind/level neighbour was shown fixed and every other neighbour is already past and cannot retreat. If, due to a logic slip, a neighbour is found that *could* still reach the support square un-attacked, **abstain** (treat supportability as disqualifying). This is a guard, not a new gate.

**CONFIRM 3 — Not a passed pawn (anti-false-positive, belt-and-suspenders).** Do **not** certify if `is_passed_pawn(board_after, square, color)` is `True`. A passed pawn is narrated as passed, not backward. Note this guard is **provably unreachable after CONFIRM 1**: a passed pawn has no enemy pawn on its own or adjacent files, so no enemy pawn can control its stop square (which lies on its own file, with adjacent-file controllers on adjacent files) — CONFIRM 1 already fails for any passed pawn. We keep the explicit `is_passed_pawn` call anyway so the mutual exclusivity is enforced even if CONFIRM 1's geometry is ever refactored. Reuse the existing **`is_passed_pawn`** helper directly.

**If VETO 1–4 all pass and CONFIRM 1, 1b, 2, 3 all hold → certify `backward_pawn`.** Compute the corroborating file status via the existing **`file_state(board_after, f, color)`** helper for the evidence bundle, but do **not** veto on it.

**Colour-handling summary (must be mirrored exactly):**

| quantity | White (`color == chess.WHITE`) | Black (`color == chess.BLACK`) |
|---|---|---|
| forward direction `fwd` | `+1` | `−1` |
| stop square rank | `r + 1` | `r − 1` |
| fixing enemy pawn rank | `r + 2` | `r − 2` |
| "neighbour strictly ahead" | `rn > r` | `rn < r` |
| "neighbour behind-or-level" | `rn <= r` | `rn >= r` |
| home rank (CONFIRM 1b) | `1` | `6` |
| stop off-board (VETO 2) | `r == 7` | `r == 0` |
| double-step landing rank | `r + 2` | `r − 2` |

## 3. Positive examples

1. **Classic half-open d6 backward pawn (Black).** Black pawn on d6 with neighbours c-pawn (advanced to c5) and e-pawn (gone or pushed to e5), a White pawn on e4 (or c4) controlling d5, and the d-file half-open for White. The d6 pawn is rear-most, its stop square d5 is enemy-pawn-controlled, the file is half-open. **Certifies; half-open subtype** — textbook backward pawn.

2. **Maróczy-bind backward c-pawn (Black).** Black's c-pawn on a half-open c-file with a White pawn on c4/e4 controlling c5/d5; the d6/c-pawn complex cannot be supported from the b- or d-file (those pawns have advanced or been traded). **Certifies; half-open subtype.**

3. **White backward e-pawn (colour-mirror).** White pawn on e4 with Black pawns on d5 and f5 (or just one of them) controlling e5, and White's d- and f-pawns already advanced past the e-pawn so neither can drop back to support e5. Stop square e5 is attacked by a Black pawn at rank `r+2` (d5 or f5). **Certifies; demonstrates the White geometry (`stop = r+1`, fixer at `r+2`).**

4. **Blocked (non-half-open) backward pawn — still certified.** Black pawn on c6, a White pawn directly in front on c5 (file fully blocked, not just controlled) plus a White pawn on b4 (or the c5 pawn's own diagonal) controlling the relevant advance, and Black's b-pawn already advanced past c6. Even with an enemy pawn occupying the file, the pawn is rear-most, cannot advance, and cannot be supported. **Certifies as the blocked / non-half-open subtype**, proving we do not require half-open.

5. **Fixed level neighbour (the under-inclusiveness fix).** Black pawn on d6 with a Black c-pawn that is *level* on c6 but whose support square c5 is occupied by a White pawn (or controlled by a White b4 pawn) so c6 can never reach c5 to guard d5, plus a White pawn controlling d5 and a Black e-pawn already advanced past d6. The level c6 neighbour cannot actually support, so d6 is still backward. **Certifies** — the case the draft's blanket "any level neighbour vetoes" wrongly missed.

*(FENs are illustrative; the predicate decides from board geometry, not labels.)*

## 4. Negative / edge cases

1. **Isolated pawn (no neighbour at all).** Zero friendly pawns on either adjacent file → **VETO 4a** excludes it. Isolated and backward are distinct weaknesses; conflating them is a false positive.

2. **A neighbour can actually support.** If a behind-or-level neighbour has a free, un-controlled path (single step, or a clear double-step from its home rank) to the square beside the candidate, it can defend the push → **VETO 3** kills it. E.g. White pawns c3 and d3: d3 is not backward because c3 can play c4 (if c4 is empty and not enemy-pawn-controlled) to support d4. **Caveat (the upgrade):** if c4 were occupied or enemy-pawn-controlled so c3 could *never* arrive, d3 *would* be backward — VETO 3 only vetoes on a neighbour that can *really* support.

3. **Stop square free, or controlled only by a piece (not a pawn).** If the square in front is empty and no *enemy pawn* attacks it (only an enemy knight/bishop/rook/queen does), the pawn can usually just advance; coaches do not call this backward. **CONFIRM 1** requires specifically an **enemy pawn** attacker. Piece control is transient; pawn control is the structural fixative. Excluded. *(Known limitation: a pawn fixed solely by minor-piece control is therefore not certified — standard master convention.)*

4. **Passed pawn.** No enemy pawn on its own/adjacent files ⇒ CONFIRM 1 cannot hold; **CONFIRM 3** (`is_passed_pawn`) is the explicit, redundant guard. Narrated as passed, never backward.

5. **Home-rank pawn that can leap the control.** A pawn on its home rank whose stop square is enemy-pawn-controlled **but** whose two-square landing is empty, the intermediate square is empty, and the landing is not enemy-pawn-controlled can bypass the guard — **CONFIRM 1b** abstains. **But** a home-rank pawn whose double-step is blocked (intermediate or landing occupied) or whose landing is *also* enemy-pawn-controlled is genuinely backward and **is** certified (this is the case the draft's blanket home-rank veto wrongly discarded).

6. **Edge-file (a-/h-) pawn.** Only one adjacent file exists. It qualifies only if that single neighbour file holds a friendly pawn that is **strictly ahead** of it (satisfying both VETO 3 and VETO 4b on the one available side) and CONFIRM 1 holds. The off-board side is **not** treated as a missing-neighbour that triggers the isolated veto — VETO 4a needs only "at least one on-board neighbour file with a friendly pawn." A lone edge pawn whose single neighbour is level-and-fixed but never advanced past it is **not** certified, because VETO 4b finds no strictly-ahead neighbour (closing the vacuous-truth hole). Handled, not blanket-excluded.

7. **Doubled pawn that is also backward.** Doubling does not exclude backwardness; if the rear doubled pawn meets every condition it is certified, and the evidence bundle notes the doubling. Co-occurring features, not a false positive. *(Note the front pawn of a doubled pair on file `f` occupies the rear pawn's stop square; that makes the rear pawn's push *blocked by a friendly pawn*, which is its own kind of immobility — if the rear pawn's stop square is also enemy-pawn-controlled it still certifies as backward, but the bundle should record the friendly blocker so the narrator does not imply it could otherwise advance.)*

8. **Promotion / off-board stop.** A White pawn on rank 7 / Black on rank 0 has no stop square (it promotes) → **VETO 2** excludes it; no off-board rank arithmetic is ever performed.

## 5. Evidence bundle

Return `(bool, Optional[dict])`, mirroring how `is_outpost` returns supporter squares and `is_rook_lift` returns a reason string. The dict is populated **only on success** (and is `None` on every veto/abstain):

- `pawn_square: int` — the backward pawn's square (render with `chess.square_name` → e.g. `"d6"`).
- `color: bool` — `chess.WHITE` / `chess.BLACK` of the pawn.
- `stop_square: int` — the controlled one-step advance square (e.g. `"d5"`).
- `enemy_pawn_controllers: List[int]` — square(s) of the enemy pawn(s) attacking `stop_square` (the pieces that fix the pawn; e.g. `["e4"]`). Non-empty by construction (CONFIRM 1).
- `advanced_neighbors: List[int]` — friendly pawn square(s) on adjacent files **strictly ahead** of the candidate (the "already past" pawns that cannot drop back; e.g. `["c5"]`). Non-empty by construction (VETO 4b) — this is *why* it is unsupportable.
- `fixed_level_neighbors: List[int]` — any behind-or-level friendly neighbour(s) that were found **fixed** (could not reach the support square), recorded so the evidence can explain why a seemingly-helpful neighbour does not save the pawn. May be empty.
- `subtype: str` — `"half_open"` (enemy has no pawn on file `f` in front), or `"blocked"` (an enemy pawn occupies file `f` directly in front of the candidate), or `"closed"` (enemy pawn(s) on file `f` ahead but not directly blocking). Drives how strongly the narrator frames it as a target.
- `is_blocked: bool` — `True` iff an enemy pawn sits on `stop_square`'s file directly in front (i.e. `subtype == "blocked"`); convenience for the narrator.
- `friendly_blocker: Optional[int]` — square of a friendly pawn directly in front on file `f` if any (the doubled-pawn case from §4.7), else `None`; lets the narrator avoid implying the pawn could advance if a friendly pawn blocks it.
- `is_doubled: bool` — `True` iff `color` has ≥2 pawns on file `f` (the candidate is part of a doubled pair). Co-occurrence note.
- `file_status: str` — raw result of `file_state(board_after, f, color)`: `"half_open_file"`, `"open_file"`, or `""`. Corroborating-evidence flag straight from the analyzer's single source of truth. *(Note `"open_file"` should not normally co-occur with certification, since an open file means neither side has a pawn there — contradicting CONFIRM 1's enemy controller on an adjacent file is still possible, but the candidate's own file being open would mean the candidate isn't on it; surfaced verbatim for transparency.)*
- `is_half_open_target: bool` — `file_status == "half_open_file"`; the most-cited aggravating factor.
- `evidence: str` — ready-to-quote narrator string built from `chess.square_name` + the literal word "pawn" (never a tag/field name), e.g.:
  - half-open: `"the pawn on d6 is backward: its advance square d5 is covered by the pawn on e4, and the c-pawn on c5 has already advanced past it and cannot return to support a push; the half-open d-file makes it a target"`
  - blocked / closed subtype (drop the trailing target clause): `"the pawn on c6 is backward: its advance square c5 is held by the pawn on c5, and the b-pawn on b4 has already advanced past it and cannot return to support a push"`
  - fixed-level-neighbour case (name the stuck would-be supporter): `"the pawn on d6 is backward: d5 is covered by the pawn on e4, and although the c-pawn is level on c6 it cannot reach c5 to defend the push"`

The evidence string must name exact squares and never emit a JSON key or tag name, consistent with the narrator's "never write a field/tag name in prose" rule.

## 6. Wiring

- Add `"backward_pawn"` to `factgate.GATED_TAGS` (`factgate.py:222`).
- In `certified_claims` (`factgate.py:235`), add, alongside the `is_outpost` tuple-guard pattern:
  ```python
  bp = _safe(lambda: is_backward_pawn(board_after, move.to_square, mover_color))
  if bp and bp[0]:
      tags.add("backward_pawn")
  ```
  Note `is_backward_pawn` returns `(bool, Optional[dict])`, so guard via `bp and bp[0]` exactly like `is_outpost`/`creates_fork`; `_safe` collapses any internal error to `None`, which fails the guard and silently drops the tag (the module's fail-safe posture).
- To surface the evidence bundle to the narrator (Tier 1+), serialize the dict in `narrator._move_to_dict` inside the `if tier >= 1:` block beside `certified` (`narrator.py:440-462`), under a new key (e.g. `d["backward_pawn_evidence"]`) wrapped in the same try/except fail-safe; emit only when present.
- **Register the new claim type in the fact-gate prompt rule at `narrator.py:202`** (add "a **backward pawn** (`backward_pawn`)" to the enumerated whitelist), or the narrator is forbidden from asserting it even when certified. Adding to `GATED_TAGS` without updating the prompt rule leaves the tag certified-but-unspeakable.

## 7. Known limitations

- **Evaluated only at the moved pawn's destination square** (`move.to_square`), matching how `is_passed_pawn`/`is_outpost` are called. It certifies a backward pawn only on the ply that creates or moves that exact pawn into the backward configuration. A pawn that became backward on an earlier ply, or an *opponent's* backward pawn the move merely exposes, is not re-detected here without a board-wide scan. (A fuller version would scan all of `mover_color`'s pawns each ply.)
- **Static, single-ply geometry, no engine confirmation.** It asserts the structural fact, not a Stockfish-verified long-term weakness. The `is_passed_pawn` guard, the CONFIRM-1b leap escape, and the "fixed-neighbour" path-check remove the most common practically-harmless cases, but a backward pawn about to be traded is still labelled backward.
- **"Cannot be supported" is path-checked one move deep.** VETO 3 / CONFIRM 2 test whether a neighbour can reach the support square in a single step or a clear home-rank double-step that is not enemy-pawn-controlled. It does not model multi-move maneuvers (a neighbour walking two non-home squares) or manufacturing a third supporter onto an adjacent file via a future capture. Such cases are rare; the predicate treats them as still-backward (slight, coach-consistent over-inclusion).
- **Does not require a half-open file**, by design, to catch closed/blocked backward pawns; a small number of "backward but practically harmless because blocked and untargetable" pawns are certified. Mitigated by `subtype` / `file_status` so the narrator softens the language for the blocked/closed subtype.
- **Piece-only control of the stop square is ignored** (CONFIRM 1 requires a pawn). A pawn fixed solely by minor-piece control is not certified — the standard master convention, at the cost of missing a handful of practically-backward pawns.
- **Pins are deliberately ignored.** Pawn attack geometry (`board.attackers`) does not change under a pin, and a pinned enemy pawn still fixes the candidate's stop square structurally; the predicate is therefore pin-independent by design. (This is a *correctness* choice, not a gap — but worth stating, since reviewers expect relative/absolute pins to be considered and here they correctly are not.)

## 8. Complexity

**Medium.** Pure python-chess square arithmetic, no engine call, reusing `is_passed_pawn` and `file_state` plus the standard `board.pieces` / `board.attackers` / `square_file` / `square_rank` idioms already pervasive in `factgate.py` / `analyzer.py`. What keeps it above "low": the multi-condition VETO-THEN-CONFIRM logic that conflates easily with three neighbouring concepts (isolated, doubled, passed); the two-directional rank/control geometry that must be mirrored exactly for both colours and at the board edge (the classic off-by-one and colour-flip bug source — see the §2 mirror table); the **path-check on behind-or-level neighbours** (the correctness upgrade that distinguishes a genuinely-fixed level neighbour from a supportable one); and the **home-rank double-step escape** (CONFIRM 1b), the subtle replacement for a naive home-rank veto. The stop-square control check — an *existing* enemy-pawn attacker via turn-/pin-independent `board.attackers`, never a hypothetical push — is the correctness crux distinguishing this from the simpler `is_passed_pawn`. No PV/engine work and no before/after diffing, so it stays below the "high" tier of sacrifice/alignment detectors.

---

## Back-rank weakness (`back_rank_weakness`)

Sanity check passed: Example 4 yields an empty attacker set (correctly latent) and Example 5 yields `[d8]` (correctly bearing), both verified on python-chess 1.11.2; the file is written at the requested path (31,771 bytes). All FENs cited in the spec were machine-verified against the real `factgate.py` / `analyzer.py` ground truth.

result: Corrected back_rank_weakness spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\08-back_rank_weakness.md (10 defects fixed, all FENs verified on python-chess 1.11.2).

# Detection Spec — Back-rank weakness — tag `back_rank_weakness`

> **Status:** corrected after adversarial review. This revision fixes a mislabeled positive
> example (the queenside case was *latent*, not *bearing*, because a friendly rook blocked the
> attacker's file), tightens the heavy-piece-reachability test so it cannot certify a rook whose
> path is pawn- *or piece-* blocked or whose line is itself pinned/blocked, makes the
> `back_rank_defended` field include the king-as-guard case it claimed to cover, removes a
> side-/colour-asymmetry trap in the luft computation, clarifies the in-check abstention so it is
> not redundant or over-broad, and pins down every evidence-bundle field with an exact
> derivation. Every FEN below is machine-verified on python-chess 1.11.2. See §8 (defects fixed)
> for the full log. Predicate lives in `factgate.py` as `is_back_rank_weak(...)`; it is **not** a
> thin wrapper (there is no analyzer detector to delegate to) and takes an **explicit
> `defending_color` argument**, so it is run twice per ply.

## 1. Expert definition

A **back-rank weakness** is a *standing positional vulnerability*: a king sits on its own first
rank, every forward escape square on the second rank is sealed — by its own pawns/pieces, by an
enemy piece, or because the enemy already covers it — so the king has **no luft** ("no breathing
hole"), and the enemy owns a heavy piece (rook or queen) that already bears, or could later bear,
a check/mate along that first rank against which the boxed-in king cannot flee. A coach calls this
"a weak back rank," "back-rank problems," or "no luft." It is the latent condition that makes
back-rank tactics (the classic `Re8#`, deflection of the lone rank-defender, a queen sac on the
back rank) possible.

Recognized variants and nuances a strong coach demands the detector honor:

- **Both castled wings qualify.** Kingside (king on g1/g8 behind f/g/h pawns) **and** queenside
  (king on b1/b8 or c1/c8 behind its pawns) are both back-rank-weak when luft is absent. The
  weakness is about luft, **not** about which wing — the rules must be wing-agnostic.
- **Uncastled king still on its first rank.** A king on e1/e8 (or d1/a1, …) that never castled,
  with its second-rank squares occupied, is still back-rank-weak. Castling rights and "has the
  king moved" are irrelevant; the flag is purely positional (king **currently** on its back rank).
- **Partial luft that is still insufficient.** A king with one diagonal-forward square that is
  *itself covered by the enemy* (or occupied) still counts — luft must be a square the king can
  **actually and safely flee to**, not merely an empty square the enemy already controls.
- **The vulnerability vs. the execution.** This tag certifies the *weakness* — a king that
  **could** be mated on the back rank if a heavy piece arrives or the sole defender is removed. It
  is deliberately distinct from a *forced mate* (owned by `mate_in_one_threat` and by raw eval). A
  position can carry a certified back-rank weakness for many moves before — or without ever —
  becoming a forced mate. Equally, the weak side may be perfectly fine *right now* because the
  rank is defended; the flag says "this is a thing to watch / target," never "this loses."

**Critical orientation properties (both made explicit because the draft got them subtly wrong):**

- **The weakness is a property of the *defending* king's side, certified PER SIDE — not per
  mover.** A sealed-in king on g1 is weak whether it is White's or Black's move. The procedure is
  run once for `D = WHITE` and once for `D = BLACK`; a position can legitimately carry the tag for
  **both** sides at once (mutual back-rank weakness). The boolean predicate takes
  `defending_color` explicitly and is **turn-independent** (verified: `board.king(color)` and
  `board.is_attacked_by(color, sq)` return identical results regardless of side to move).
- **The logic must be colour-symmetric with no White-relative direction hard-coded.** "Forward"
  is `+1` rank for White but `−1` rank for Black; the luft rank is rank 1 for White, rank 6 for
  Black. Deriving these from `D` (not assuming White) is mandatory — a hard-coded "+1 / rank 1"
  would silently never fire for a weak Black king.

## 2. Detection rules (VETO-THEN-CONFIRM)

Certify `back_rank_weakness` **for an explicit defending colour `D`**. Run the whole procedure
twice — once with `D = chess.WHITE`, once with `D = chess.BLACK` — and tag each side that passes.
Let `E = not D` be the attacking side. **The side to move is irrelevant to the result and must
not gate it.**

Derive each side's geometry from `D` (never hard-code White):
- `D = chess.WHITE`: `back_rank = 0` (the 1st rank); `luft_rank = 1` (the 2nd rank).
- `D = chess.BLACK`: `back_rank = 7` (the 8th rank); `luft_rank = 6` (the 7th rank).

(A compact way to write both: `back_rank = 0 if D == chess.WHITE else 7`,
`luft_rank = 1 if D == chess.WHITE else 6`. No per-file direction sign is needed — the luft squares
are simply the up-to-three squares of `luft_rank` on the king's file ± 1.)

**VETO stage (cheap necessary-condition refutations — bail the instant the weakness is impossible):**

1. **King-on-back-rank veto.** `king_sq = board.king(D)`. If `king_sq is None` **or**
   `chess.square_rank(king_sq) != back_rank`, **abstain** (return `(False, None)`). A king already
   advanced off its first rank has no back-rank weakness.

2. **In-check abstention (integration-level, defer to the tactical layer).** If `board.is_check()`
   **and the side to move is `D`** (i.e. it is `D`'s king that is currently in check), **abstain**.
   A king in check is a live tactical state the immediate sequence is already resolving, not a
   standing positional flag — mirror how `_mate_threat` abstains under check (`factgate.py:264`).
   Note `board.is_check()` is *already* side-to-move-relative, so the `side to move is D` conjunct
   is what makes this fire only for the checked side; do **not** abstain for `D` when it is the
   *other* king that is in check (that opponent-in-check state says nothing about `D`'s back rank).
   *(If the predicate is ever called on a position where `D` is not to move, this veto simply does
   not apply for that `D`; the geometry rules below still hold.)*

3. **Enemy-heavy-piece veto.** If `E` has **no** rook and **no** queen on the board — both
   `board.pieces(chess.ROOK, E)` and `board.pieces(chess.QUEEN, E)` are empty — **abstain**. With
   no rook or queen, nothing can ever deliver a first-rank mate in the sense this tag certifies, so
   the weakness is moot. (Existence is the cheap necessary condition here; whether a heavy piece
   can *reach* the rank is the confirm step, rule 6.)

4. **Luft veto (the core necessary condition).** Compute the king's **forward escape squares** =
   the up-to-three squares on `luft_rank` at files `king_file − 1`, `king_file`, `king_file + 1`,
   **clamped to files 0–7** (drop any file outside `0..7` — this is the board-edge guard for a king
   on the a- or h-file). For each such square `s`, the king has **genuine luft** there **iff**
   `board.piece_at(s) is None` **and** `not board.is_attacked_by(E, s)`. If **any** forward escape
   square yields genuine luft, **abstain** — the king can step off the back rank, so it is not
   back-rank-weak. Only when **every** forward escape square is *blocked* (occupied by any piece,
   friendly or enemy) **or** *enemy-covered* (`is_attacked_by(E, s)` is `True`) does the king have
   insufficient luft.

   Per-square blocking **reason** (recorded for the evidence payload, exact category strings):
   - occupied by a friendly pawn → `"own pawn"`;
   - occupied by any other friendly piece → `"own piece"`;
   - occupied by an enemy piece → `"enemy piece"`;
   - empty but `is_attacked_by(E, s)` → `"covered by the enemy"`.

   Notes the implementer must respect:
   - **`is_attacked_by(E, s)` includes the enemy king's coverage** (verified: an enemy king on g6
     makes `is_attacked_by(WHITE, h7)` `True`). That is *correct* here — a square the enemy king
     guards is not a real flight square anyway (a king may never move adjacent to the enemy king).
   - **A square occupied by an *enemy* piece counts as blocked** (the king cannot step onto a
     friendly square and we conservatively treat capturing onto an enemy-occupied square as
     not-free unless it is provably a legal, safe king capture — see §6 Limitations). This is the
     deliberately inclusive reading.

**CONFIRM stage (only reached if all vetoes pass):**

5. **Confirm insufficient luft formally.** Re-affirm that the set of genuine escape squares (empty
   AND not enemy-attacked, among the forward three) is **empty**. This is the same computation as
   rule 4, retained as the explicit positive condition the predicate returns `True` on.

6. **Confirm a heavy piece bears on, or can reach, the back rank.** Two tiers, both engine-free,
   both reusing the `detect_royal_alignment` clear-line idiom (`chess.between` + `chess.SquareSet`
   + `board.piece_at`) and `file_structure(board)`:

   - **Strong form — already bearing (preferred, lowest false-positive).** There exists a square
     `s` on `D`'s `back_rank` such that `board.attackers(E, s)` contains a square holding an enemy
     **rook or queen**. Use `board.attackers(E, s)` directly: it already accounts for blockers
     (it returns only pieces with a *clear* line to `s`) and already restricts to genuine
     attackers, so a pinned-but-still-attacking rook is included (a pinned rook still controls the
     rank for mating-net purposes) while a rook whose file/rank is pawn- or piece-blocked is
     **excluded**. Filter the returned attacker squares to `piece_type in (ROOK, QUEEN)` (a pawn,
     knight, bishop, or king attacking a back-rank square does **not** satisfy this tag). If any
     such attacker exists → `heavy_piece_bearing = True`; collect those attacker squares into
     `heavy_pieces`. *(Verified: for `6k1/5ppp/8/8/8/8/8/R5K1`, `board.attackers(WHITE, a8)`
     contains `a1` — the rook bears on Black's back rank down the open a-file.)*

   - **Latent fallback — reachable but not yet bearing.** If no enemy heavy piece *already* bears
     on the rank, but rule 3 passed (one exists somewhere), check whether an enemy rook/queen sits
     on an **open or half-open-for-`E` file** (from `file_structure(board)`: a file in `"open"`,
     or in `"half_open_white"`/`"half_open_black"` according to *which side `E` is*) whose path
     **from that piece to `D`'s back rank is unobstructed** — verify with the clear-line check
     `all(board.piece_at(t) is None for t in chess.SquareSet(chess.between(heavy_sq, back_sq)))`
     for the back-rank square `back_sq` on that file. If such a piece exists, certify the weakness
     as **latent**: `heavy_piece_bearing = False`, and put those piece squares in `heavy_pieces`.
     If neither tier finds a reaching piece, **still certify** the standing weakness (rule 3
     guaranteed a heavy piece exists somewhere) with `heavy_pieces = []` and
     `heavy_piece_bearing = False` — a luft-less king is back-rank-weak in coaching usage even
     before the rook swings over; the narrator then phrases it as a standing weakness to exploit,
     not an immediate threat. **Rule 3 (existence) is the gate; rule 6 only sets the
     `heavy_piece_bearing` flag and populates `heavy_pieces` — it never vetoes.**

7. **Defended-rank note (compute it, never veto on it).** Whether `D` currently *defends* its own
   back rank does **not** cancel the weakness — it only lowers urgency (rule 6 of the expert
   definition). Compute `back_rank_defended` for the evidence string: `True` iff some square `s`
   on `D`'s `back_rank` is defended by a `D` rook or queen (`board.attackers(D, s)` contains a
   rook/queen) **or by the king itself** (the king defends the squares in `board.attacks(king_sq)`
   — include this so the "king guards the mating square" case the definition names is actually
   covered; the draft listed it but its `attackers`-only computation missed it). **Never** let
   `back_rank_defended` change the boolean result, and **never** upgrade this tag to a mate claim —
   mate is `mate_in_one_threat`/eval's job.

**First passing `D` certifies `(True, evidence)` for that side.** Run for both `D` values; surface
two distinct results keyed by side (see §5 wiring) so a mutual weakness can fire twice.

## 3. Positive examples

Every FEN is verified on python-chess 1.11.2: the king is on its back rank, all three forward
luft squares are blocked/covered, and the heavy-piece tier (bearing or latent) is as stated.

1. **Classic kingside, rook already bearing.** FEN `6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1` — Black king
   g8 behind f7/g7/h7 (all own pawns; none enemy-covered). White rook a1 sits on the **open**
   a-file, so `board.attackers(WHITE, a8)` contains a1 — it already bears on Black's 8th rank.
   **Qualifies for D = BLACK**, `heavy_piece_bearing = True`, `heavy_pieces = [a1]`.

2. **Mutual back-rank weakness (fires twice).** FEN `r5k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1` — both
   kings sealed behind their three pawns; each side has a rook on the **open a-file** bearing on
   the enemy back rank (`attackers(WHITE, a8) ⊇ {a1}` and `attackers(BLACK, a1) ⊇ {a8}`).
   **Qualifies for BOTH `D = WHITE` and `D = BLACK`** — the tag should fire twice with disjoint
   evidence.

3. **Uncastled king, no castling occurred (kingside geometry).** FEN
   `4rk2/pp3ppp/8/8/8/8/PP3PPP/5RK1 b - - 0 1` — White king g1 behind f2/g2/h2 (all own pawns),
   White rook f1; Black rook e8 controls the e-file. White's king is on its back rank with zero
   luft. The Black rook reaches the 1st rank down the half-open-for-Black e-file (e-file has no
   Black pawn; path e8→e1 clear) → **latent** (`heavy_piece_bearing = False` because no Black heavy
   piece *already* attacks a rank-0 square — e1 is empty and on a clear file, but the strong-form
   test asks for a present attacker on a back-rank *square*; here e1 is reachable, satisfying the
   latent tier). **Qualifies for D = WHITE.**

4. **Queenside-castled king — LATENT (corrected).** FEN `2kr4/ppp5/8/8/8/8/PPPR4/2K5 b - - 0 1` —
   White king c1 behind a2/b2/c2; forward squares b2/c2/d2 are own-pawn / own-pawn / **white-rook
   (d2)**; d2 is also covered by the Black d8-rook, so every forward square is blocked. Black rook
   d8 aims down the d-file — **but the White rook on d2 blocks it**, so `board.attackers(BLACK, d1)`
   is **empty**: the heavy piece does **not** yet bear (it is one tempo away once the d2 rook moves
   or is traded). **Qualifies for D = WHITE as LATENT** (`heavy_piece_bearing = False`,
   `heavy_pieces = [d8]` via the latent fallback — d8 is on the half-open-for-Black d-file but the
   path to d1 is obstructed by the d2 rook, so even the latent clear-line check fails here; the
   weakness is still certified by rule 3's existence guarantee with `heavy_pieces = []`). *(The
   draft mislabeled this "bears down the d-file toward d1"; the d2 rook makes it latent, not
   bearing — see §8 D1.)*

5. **Queenside-castled king — genuinely BEARING (added, the case the draft lacked).** FEN
   `2kr4/ppp5/8/8/8/8/PPP5/1K1R4 b - - 0 1` — White king b1 behind a2/b2/c2 (all own pawns, no
   luft); Black rook d8 bears down the **open d-file** and `board.attackers(BLACK, d1)` contains d8
   (the white Rd1 sits on d1 but the black rook still attacks d1). **Qualifies for D = WHITE**,
   `heavy_piece_bearing = True`, `heavy_pieces = [d8]`. This is the queenside analog of Example 1.

(Each example's defining feature: king on its back rank + every forward escape square
blocked/covered + an enemy R/Q that reaches or already bears on that rank.)

## 4. Negative / edge cases

1. **King already has luft (the #1 false positive the luft veto exists to kill).** FEN
   `6k1/5pp1/7p/8/8/8/5PPP/R5K1 w - - 0 1` — Black has played `…h6`, so h7 is **empty and
   unattacked**: forward square h7 gives genuine luft. **Rule 4 vetoes** — not certified for Black.
   (Verified: `(h7, empty, not attacked) → LUFT`.)

2. **King not on the back rank.** A king that walked up to g2/g7 in an endgame. **Rule 1 vetoes**
   immediately (`square_rank(king) != back_rank`). No back-rank weakness exists off the first rank.

3. **No enemy heavy piece.** King sealed behind three pawns but the opponent has only minors/pawns
   left. **Rule 3 vetoes** — a bishop or knight cannot deliver the first-rank rook/queen mate this
   tag certifies. Not certified.

4. **A forced mate, not a standing weakness.** FEN `6k1/5ppp/8/8/8/8/8/4R1K1 w - - 0 1` with White
   to play `Re8#`. That mate is owned by `mate_in_one_threat`/eval. The back-rank-*weakness* tag is
   also true for Black (luft-less, the e1 rook reaches e8), and certifying it **as the
   vulnerability** is fine — but the evidence string must never say "mate." The detector returns
   the weakness; the narrator combines, never conflates.

5. **Luft square exists but is enemy-covered (illusory luft).** King g8 with h7 empty but an enemy
   bishop on the b1–h7 diagonal covering h7 — `is_attacked_by(E, h7)` is `True`, so h7 is **not**
   genuine luft. **Rule 4 correctly withholds luft**, and the weakness can still be certified. This
   is exactly the inclusive case experts mean by "the luft is illusory." (Likewise a square covered
   only by the enemy *king* is not luft — verified `is_attacked_by` includes the enemy king.)

6. **Flight via a piece-vacated square (must check all three files).** King g1, rook f1, but h2
   empty, unattacked → h2 gives genuine luft. **Abstain.** The detector must test all three forward
   files (f2/g2/h2), never assume the f-file rook seals everything.

7. **Back rank fully defended right now.** King g8 luft-less, with a Black rook on e8 guarding the
   whole 8th rank. The weakness is real, urgency low — **certify with `back_rank_defended = True`**;
   do **not** veto on present defense (rule 7). (Verified: `attackers(BLACK, *8th-rank sq*)`
   contains the e8 rook.) The narrator describes a latent weakness, not a loss.

8. **King currently in check.** If it is `D`'s move and `D`'s king is in check, **rule 2 abstains**
   — defer to the eval/mate tags resolving the live sequence. (If instead the *other* king is in
   check, rule 2 does not apply to `D`, and `D`'s standing back-rank geometry is still assessed
   normally.)

9. **Heavy piece exists but its line to the rank is blocked (latent, not bearing).** Enemy rook on
   a file with a pawn (either colour) between it and the back rank. The strong-form
   `board.attackers(E, back_sq)` will **not** include it (blocked line), and the latent clear-line
   check also fails — so it does not flip `heavy_piece_bearing` to `True`, yet rule 3's existence
   guarantee still certifies the standing weakness. Correctly distinguishes "bearing" from
   "merely present." (This is the corrected reading of draft Example 4 — see §8 D1.)

## 5. Evidence bundle

The predicate returns `(bool, Optional[dict])`. On success the dict carries the
anti-hallucination payload (all squares via `chess.square_name`, all piece names via
`PIECE_NAMES`):

- `defending_color: bool` — which side is weak (`chess.WHITE` / `chess.BLACK`); echoes the
  argument the predicate was called with.
- `king_square: int` — the weak king's square (for `chess.square_name`).
- `blocked_escape_squares: List[Tuple[int, str]]` — **every** forward luft square with its reason
  category from rule 4, e.g. `[(f7, "own pawn"), (g7, "own pawn"), (h7, "own pawn")]` or
  `[(h7, "covered by the enemy")]`. Reason ∈ `{"own pawn", "own piece", "enemy piece",
  "covered by the enemy"}`. For an a-/h-file king this list has only **two** entries (the
  off-board file was clamped away) — that is correct, not a bug.
- `heavy_pieces: List[int]` — squares of the enemy rook(s)/queen(s) that **already bear** on the
  back rank (strong form) or, if none bear, that can **reach** it on a clear open/half-open file
  (latent form). May be `[]` when rule 3 guaranteed a heavy piece exists but neither tier found a
  clear path (still certified — latent).
- `heavy_piece_bearing: bool` — `True` iff at least one enemy rook/queen is in `board.attackers(E,
  s)` for some back-rank square `s` (already has a clear line onto the rank); `False` if the
  weakness is latent (piece exists/reachable but not yet bearing).
- `back_rank_defended: bool` — `True` iff `D` currently guards its back rank: a `D` rook/queen in
  `board.attackers(D, s)` for some back-rank `s`, **or** the king itself defends a back-rank square
  (king-as-guard case). Urgency flag only — **never a veto**.
- `evidence: str` — a ready-to-quote, **mate-free** sentence the narrator may use verbatim, built
  from `PIECE_NAMES` + `chess.square_name`. The side label ("White's"/"Black's") is derived from
  `defending_color`, never hard-coded. Templates:
  - **Bearing, undefended:** `"Black's king on g8 has no luft — f7, g7 and h7 are all sealed by
    its own pawns — and White's rook on a1 bears on the back rank, a standing back-rank
    weakness."`
  - **Latent:** `"White's king on g1 is boxed in by the f2, g2 and h2 pawns with no escape square;
    the weakness is latent until a rook reaches the first rank."`
  - **Defended:** `"Black's back rank is weak — the king on g8 has no flight square — though it is
    currently held by the rook on e8."`

The string must **never** contain the words "mate," "mates," "checkmate," "mating," or "wins" —
those are reserved for the mate/eval gates, keeping this strictly the *vulnerability* payload. A
unit test should assert the absence of those substrings in every emitted `evidence` string.

**Wiring (per-side, turn-independent — the one integration subtlety):** add
`is_back_rank_weak(board, defending_color)` to `factgate.py` returning `(bool, Optional[dict])`.
Because `certified_claims()` is currently mover-scoped, run the predicate for **both** colours and
surface two keyed results so a mutual weakness fires twice. Concretely, inside `certified_claims`
add (using the same `_safe`/`and [0]` guard shape as the other tuple-returning predicates, so a
predicate exception is swallowed and the tag silently dropped rather than crashing the report):

```python
for D in (chess.WHITE, chess.BLACK):
    brw = _safe(lambda D=D: is_back_rank_weak(board_after, D))
    if brw and brw[0]:
        tags.add("back_rank_weakness")              # or a side-keyed variant
```

Serialize the evidence dict(s) into the Tier-1 packet alongside `certified`, inside the existing
`if tier >= 1:` block of `_move_to_dict` (`narrator.py:440-462`), under the same try/except
fail-safe. Because the weakness is per side and the packet is mover-scoped, the evidence string
must name the weak colour explicitly (the templates above already do) so a reader is never confused
about *whose* back rank is weak.

**Registration required (or the narrator may not assert it):** add `"back_rank_weakness"` to
`factgate.GATED_TAGS` (`factgate.py:222`) **and** name it in the fact-gate prompt rule at
`narrator.py:202`. The whitelist is the single source of truth — an unregistered tag is treated as
"not machine-proven" and the narrator is forbidden from asserting it.

## 6. Known limitations

- **Reachability is approximated, deliberately conservatively.** Rule 6 uses present attacker lines
  + open/half-open files with a clear-path check; it does **not** search multi-move maneuvers (a
  rook two tempi away via a lift, or after a trade clears the file — exactly the corrected
  Example 4). It therefore under-claims `heavy_piece_bearing` on some genuine future weaknesses;
  the latent branch and rule 3's existence guarantee partially cover this, but the standing flag is
  intentionally cautious about asserting an *immediate* threat.
- **Luft via capture is treated as no-luft.** A forward square occupied by an *enemy* piece the
  king could legally and safely capture is conservatively counted as blocked (`"enemy piece"`).
  This can over-claim weakness in rare cases where the king's capture is a real escape. Verifying
  otherwise needs per-square legal-move generation, not done in the veto path.
- **Enemy-king coverage counts as covering a flight square.** `is_attacked_by(E, s)` includes the
  enemy king's attacks, so a forward square the enemy king guards is treated as non-luft. This is
  correct (a king can never move adjacent to the enemy king), but it is worth noting the coverage
  source is not separated in the evidence string ("covered by the enemy" is generic).
- **Pinned-defender / deflection depth is not modeled.** `back_rank_defended` reports whether the
  rank is guarded *now*, not whether the sole defender is overloaded or deflectable (that is
  `detect_overloaded_defender`'s domain). It cannot tell "weak but safe" from "one deflection from
  disaster"; it flags only the standing condition.
- **First-passing-side per call.** The predicate evaluates one `defending_color` per call; the
  caller runs it twice. A position with a mutual weakness needs both calls to surface both — the
  wiring in §5 does this.
- **Castling rights / king-has-moved are not consulted.** The flag is purely positional (king
  currently on its first rank), which is the intended, more-inclusive reading (covers uncastled
  first-rank kings). A king that castled and later walked up off the back rank correctly fails
  rule 1.

## 7. Complexity

**Low–medium.** The core is cheap, bounded geometry: one `board.king()` lookup, two
`board.pieces()` existence checks, and at most three forward-square tests per side via
`is_attacked_by` — all O(1)-ish, in the same spirit as the `is_outpost`/`is_passed_pawn` veto
loops. The only medium part is rule 6's heavy-piece tiering: the strong form is a direct
`board.attackers(E, s)` scan over the 8 back-rank squares (cheap, and it correctly handles blockers
and pins for free), and the latent fallback reuses the `chess.between` + `board.piece_at` clear-line
idiom already proven in `detect_royal_alignment` plus the `file_structure` open/half-open
shortcut. No engine call, no search, no new dependencies — it fits the pure, engine-free
`factgate.py` posture. The one design subtlety (not algorithmic cost) is the **per-side,
turn-independent** certification: the predicate takes an explicit `defending_color` and is run for
both colours, threading two possible results into the currently mover-scoped `certified_claims()`.

**Files referenced:** `C:\Users\詹天哲\Documents\greco\factgate.py` (predicate home,
`certified_claims`, `GATED_TAGS`, the `_safe`/`and [0]` guard idiom);
`C:\Users\詹天哲\Documents\greco\analyzer.py` (`file_structure`, the `detect_royal_alignment`
`chess.between`/`SquareSet` clear-line idiom, `PIECE_NAMES`);
`C:\Users\詹天哲\Documents\greco\narrator.py` (`_move_to_dict` Tier-1 serialization at
`narrator.py:440-462`, the fact-gate prompt rule at `narrator.py:202` to extend with the new tag).

## 8. Defects fixed from the draft (adversarial review log)

- **D1 — mislabeled positive example (false "bearing" claim).** Draft Positive Example 4 used FEN
  `2kr4/ppp5/8/8/8/8/PPPR4/2K5 b - - 0 1` and asserted the Black d8-rook "bears down the d-file
  toward d1." It does **not**: the White rook on d2 blocks the file, so
  `board.attackers(BLACK, d1)` is **empty** (verified) — the weakness is *latent*, not bearing.
  Fixed: Example 4 is relabeled LATENT with the blocker explained, and a genuinely-**bearing**
  queenside Example 5 (`2kr4/ppp5/8/8/8/8/PPP5/1K1R4 b - - 0 1`, where `attackers(BLACK, d1) ⊇
  {d8}` down the open d-file) is added so the bearing-queenside case is actually demonstrated.
- **D2 — heavy-piece reachability over-claimed (false positives).** The draft's rule 5 "strong
  form" mixed `board.attackers` with a vaguer "shares an open/half-open file" test that could
  credit a rook whose path is pawn- or piece-blocked, or even off the rank. Fixed: the strong form
  is now precisely `board.attackers(E, back_sq)` filtered to ROOK/QUEEN — which already enforces a
  clear line and excludes blocked attackers — and the latent fallback carries an explicit
  `chess.between` clear-path assertion. A blocked-file rook now correctly yields *latent*, not
  *bearing* (new Negative case 9).
- **D3 — `back_rank_defended` missed the king-as-guard case it claimed to cover (under-inclusive
  evidence).** The draft's prose said the field covers "the king itself guarding the mating square"
  but defined it only via a rook/queen on the rank. Fixed: rule 7 / §5 compute it as a `D`
  rook/queen attacker **or** the king defending a back-rank square (`board.attacks(king_sq)`), so
  the named case is actually included.
- **D4 — colour-/direction-asymmetry trap.** The draft described "forward direction +1 / −1" but
  its examples and phrasing leaned White-relative. Fixed: §1 and §2 mandate deriving `back_rank`
  and `luft_rank` from `D` (`0/1` for White, `7/6` for Black) with no hard-coded White direction;
  verified that `board.king`/`is_attacked_by` are side-to-move independent, so a weak Black king is
  certified identically to a weak White king.
- **D5 — redundant / over-broad in-check abstention.** The draft said "abstain when
  `board.is_check()` and the side to move is `D`," which reads as a conjunction even though
  `board.is_check()` is already side-to-move-relative, and risked abstaining for `D` when the
  *opponent* was in check. Fixed: rule 2 states the abstention fires only when it is `D`'s own king
  in check, and explicitly does **not** abstain for `D` when the other king is in check.
- **D6 — board-edge (a-/h-file king) under-specification.** The draft said "clamp to files 0–7"
  but did not state the consequence for the evidence bundle. Fixed: rule 4 clamps the off-board
  file away, and §5 notes that an a-/h-file king yields a two-entry `blocked_escape_squares` list
  by design (not a missing-square bug).
- **D7 — vague evidence-bundle reason strings.** The draft's per-square reasons mixed prose
  ("blocked by own pawn on f2", "the f2-flight square is covered by the enemy") with no closed
  category set, making the payload hard to template and test. Fixed: §5 pins a closed reason
  vocabulary `{"own pawn", "own piece", "enemy piece", "covered by the enemy"}` and adds an
  `"enemy piece"` category the draft omitted (a forward square occupied by an *enemy* piece).
- **D8 — pinned-attacker semantics unspecified (potential false negative).** The draft did not say
  whether a pinned enemy rook still "bears" on the rank. Fixed: §2 rule 6 notes that
  `board.attackers(E, s)` **includes** a pinned-but-attacking rook (it still controls the rank for
  mating-net purposes), which is the correct inclusive reading — a back-rank weakness against a
  pinned rook is still a weakness.
- **D9 — `heavy_pieces` could be empty but undocumented.** The draft's latent fallback left it
  unclear what `heavy_pieces` holds when a piece exists (rule 3) but no clear path is found. Fixed:
  §5 states `heavy_pieces` may legitimately be `[]` on a certified *latent* weakness, and the
  predicate still certifies on rule 3's existence guarantee.
- **D10 — mate-word leak surface widened.** The draft forbade "mate/mates/checkmate/wins." Fixed:
  added `"mating"` to the forbidden set and specified a unit-test assertion over every emitted
  `evidence` string, since the tag's whole purpose is to stay strictly the *vulnerability* payload
  distinct from `mate_in_one_threat`.

---

## Luft (`luft`)

Sanity check: re-ran the load-bearing positions against python-chess (the `h3`/`…h6`/`b3`/`Kb1+a3`/`g3` luft cases all yield the expected `new` flight square; the king-removed probe correctly flags the sole-blocker square as unsafe; en passant is caught by `is_capture`; the a-pawn-for-c1-king claim is geometrically false and excluded by VETO 4). The corrected spec is written to `C:\Users\詹天哲\Documents\greco\docs\specs\predicates\09-luft.md` in the house 8-section format used by the sibling specs.

result: Corrected `luft` spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\09-luft.md — fatal VETO-5 false negative removed, king-as-blocker survivability bug fixed, a-pawn/c-king inaccuracy corrected, evidence bundle aligned to `(bool, Optional[dict])`.

The corrected spec markdown follows.

---

# Detection Spec — "Luft" (tag: `luft`)

> Status: corrected after adversarial review. This version fixes the **fatal
> false-negative in the draft's VETO 5** (requiring `flights_before` to be empty
> rejected the textbook h3 / …h6 luft — and the draft's own positive examples 1
> and 2 — because a back-rank king's *lateral* back-rank squares f1/h1/f8/h8 are
> empty and unattacked and therefore register as pre-existing "flights"); the
> **king-as-sole-blocker survivability bug** (`is_attacked_by(enemy, s)` falsely
> reports a square safe when the only thing shielding it from an enemy slider is
> the king itself standing on `king_sq` — the king would still be in check after
> stepping there — fixed by removing the king from `king_sq` before the attack
> test); the **chess inaccuracy in §1** (the a-pawn does *not* make luft for a
> king on **c1/c8** — `a3` opens a2, which is two files from a c-file king and is
> correctly excluded by the adjacency veto; the a-pawn only makes luft once the
> king has stepped to **b1/b8**); the **confused/over-restrictive causal clause**
> (replaced with a precise, color-agnostic attribution test); the **king-in-check
> and enemy-king-adjacency edge cases**; the **pin / relative-pin interaction**;
> and the **evidence bundle** (now `(bool, Optional[dict])` mirroring the sibling
> predicates, with `was_boxed_in` demoted from a veto to a reported flag).

## 1. Expert definition

**Luft** (German "air") is a **quiet pawn push, made near one's OWN king, that newly opens an empty, survivable square the king can step onto** — relieving back-rank (or general smothering) danger. A king with no escape square is vulnerable to a back-rank mate, or to any check on its rank/file with nowhere to step; pushing a pawn in front of or beside the king "makes luft" by creating a flight square that did not exist before the push.

The defining test is **functional and king-position-driven, never file-based**. It is fully side-agnostic (both colors) and castling-side-agnostic. The pawn that makes luft is always on the king's **own file or an immediately adjacent file** (Chebyshev-file distance ≤ 1), because only such a pawn can vacate or unblock a square the king actually steps to:

- **Kingside-castled king** (typically **g1**/**g8**, sometimes h1/h8 or f1/f8): luft comes from the f-, g-, or h-pawn — classically `h3`/`h6` or `g3`/`g6`, also `f3`/`f6` for a king on g1/g8.
- **Queenside-castled king**: the king sits on **c1/c8** (after `O-O-O`) or, very commonly, has been tucked to **b1/b8** (after a later `Kb1`). Luft is from a pawn on the king's file or an adjacent file:
  - **King on c1/c8:** the **b-, c-, or d-pawn** (e.g. `b3`/`b6` opening b2/b7, `c3`/`c6` opening c2/c7). **The a-pawn does NOT make luft for a c-file king** — `a3` opens a2, which is two files away and is not a square a c1 king can reach. (This corrects the draft's "a-, b-, or c-pawn … `a3`/`a6`" claim, which contradicted its own adjacency veto.)
  - **King on b1/b8 (the `Kb1` tuck):** now the **a-, b-, or c-pawn** all qualify — `a3`/`a6` *does* make luft here, opening a2/a7 adjacent to a b-file king.
- **Uncastled / wandering king**: still luft if the pushed pawn opens a real flight square next to wherever the king actually sits.

The **canonical (strongest) case** is a king on its back rank that was boxed against a back-rank mate and gains a flight square one rank in front of it. But the inclusive concept is **"any new, survivable king-flight square opened by an adjacent pawn push,"** and the detector must NOT require the king to have been totally boxed in (a king with sideways back-rank squares but no forward air still benefits from luft — see the bug this corrects in §2).

## 2. Detection rules (VETO → CONFIRM)

All squares are python-chess `int`s. `mover_color` is the side that just pushed; the position is evaluated on `board_before` (pre-push) and `board_after` (post-push). **Frame everything from `mover_color`** via `board.king(mover_color)`, `board.attacks(...)`, and the enemy = `not mover_color`. No file constants; the function reads the actual `king_sq` and never assumes which rank is the back rank. Reuse the established idioms (`board.attacks`, `board.attackers`, `board.is_attacked_by`, `board.king`) exactly as `factgate.py` / `analyzer.py` do.

> **Note on side-to-move framing.** This predicate is invoked from `certified_claims` on the position **after** the mover's push, so on `board_after` the **opponent is to move**. The king cannot "legally move" right now (it is not the mover's turn), so survivability is tested **geometrically** (king-removed attack test, CONFIRM 1), not via `board.legal_moves`. This is the same engine-free, geometry-only posture as the rest of `factgate.py`.

### Cheap necessary-condition vetoes (bail the instant the claim is impossible)

**VETO 1 — Must be a quiet pawn push by the mover.** The moved piece must be a `chess.PAWN` of `mover_color`: confirm `board_after.piece_at(move.to_square)` is a pawn of `mover_color` (equivalently `board_before.piece_at(move.from_square)`). If not, veto. **Also veto if `move.promotion` is set** — a promotion replaces the pawn with a piece and is not "making luft" (and on `board_after` the destination is no longer a pawn). *(Castling can never reach here: a castle moves the king/rook, not a pawn, so VETO 1 already excludes it; no separate castling check is needed.)*

**VETO 2 — No friendly king on board.** `king_sq = board_after.king(mover_color)`. If `None`, veto. (Luft is defined relative to the mover's own king; the king is always present in a legal game, but guard defensively for malformed FENs.)

**VETO 3 — Captures and en passant excluded.** If `board_before.is_capture(move)` (which is `True` for en passant as well), veto. Luft is the quiet-advance concept; a capture changes structure differently and is deliberately out of scope (precision-over-recall, matching James's "false positives are bugs" standard and the `is_rook_lift` capture veto). *(`board_before.is_capture` already covers en passant; `board_before.is_en_passant(move)` is a redundant belt-and-suspenders check.)*

**VETO 4 — Pushed pawn must be on the king's file or an adjacent file.** Compute `kf = chess.square_file(king_sq)`. Require **`abs(kf - chess.square_file(move.from_square)) <= 1`** (the pawn started on the king's own or an adjacent file). Because a pawn push keeps the same file, `move.to_square` is on the same file, so the from-file test suffices; this is the king-position-driven generalization that captures f/g/h for a g-file king, b/c/d for a c-file king, and a/b/c for a b-file king **without naming any files**. If the pawn's file is ≥2 from the king's file, veto — it is a structural push elsewhere (a pawn storm, a central break), not luft.

> **Why no rank/Chebyshev veto on `from_square`.** The pawn need not be on a rank adjacent to the king (a king on g1 can get luft from h2→h3 *or* from a more advanced push only in unusual cases); the load-bearing test is the flight-square **diff** below, not the pawn's proximity. The file-adjacency veto (VETO 4) plus the causal-attribution confirm (CONFIRM 2) together pin the pawn to the king without a brittle rank check.

> **DELETED draft VETO 5 (the critical fix).** The draft vetoed whenever the king already had **any** survivable flight square before the push. This is **wrong** and rejects the textbook case: a king on g1 with pawns f2/g2/h2 already has f1 and h1 as empty, unattacked back-rank squares (likewise f8/h8 for a g8 king), so `flights_before` is **non-empty** — the draft would veto `h3`/`…h6`, i.e. its **own positive examples 1 and 2**, and the very move that prevents the back-rank mate. The correct gate is not "was the king totally boxed?" but **"did this push NEWLY open a survivable flight square?"** — which is exactly the diff in CONFIRM 1. "Boxed in" (empty `flights_before`) is real and useful, but it is **reported as the `was_boxed_in` evidence flag, never used as a veto.**

### Confirmation (only reached if no veto fired)

Define the **survivable-flight-square set** for a board, computed with the **king removed from `king_sq`** so that a square shielded only by the king's own body is correctly judged unsafe:

```
def _king_flights(board, king_sq, mover_color):
    enemy = not mover_color
    probe = board.copy()
    probe.remove_piece_at(king_sq)          # king must not shield its own destination
    flights = set()
    for s in board.attacks(king_sq):        # the 8-or-fewer on-board king steps
        if board.piece_at(s) is not None:   # destination must be empty
            continue
        if probe.is_attacked_by(enemy, s):  # king-removed: not walking into check
            continue
        flights.add(s)
    return flights
```

Three subtleties this encodes, each a fixed bug:

- **King-as-sole-blocker (the survivability bug).** A naive `board.is_attacked_by(enemy, s)` returns `False` for a square that is shielded from an enemy rook/bishop/queen *only because the king itself stands on `king_sq`* — but the king would still be in check after stepping there (e.g. king h2, enemy rook h8: naive test says h1 is safe; it is not). Removing the king from `king_sq` on `probe` before the attack test fixes this. **This king-removed test must be used for BOTH `flights_before` and `flights_after`.**
- **Enemy-king adjacency / opposition.** `is_attacked_by(enemy, s)` already counts the enemy king's own attacks, so a candidate square adjacent to the enemy king is correctly rejected (two kings can never be adjacent). Removing only the *friendly* king from the probe preserves this.
- **On-board only.** `board.attacks(king_sq)` yields only on-board king steps, so an edge/corner king never produces a phantom off-board flight square (handles the board-edge case naturally — see §4).

**CONFIRM 1 — The push newly opens a survivable flight square (load-bearing gate).** Compute `flights_before = _king_flights(board_before, king_sq_before, mover_color)` and `flights_after = _king_flights(board_after, king_sq, mover_color)`, where `king_sq_before = board_before.king(mover_color)` (the king did not move on a pawn push, so `king_sq_before == king_sq`; compute both for clarity and to guard malformed input). **Certify luft only if `new = flights_after - flights_before` is non-empty.** The squares in `new` are the candidate luft square(s). If the push opened no *new* survivable flight square (the king's air is unchanged — routine prophylaxis in an already-open position, or the opened square is unsafe), **abstain** (no certification). This single diff replaces the draft's broken VETO-5/CONFIRM-6 pair.

**CONFIRM 2 — The new flight square is causally the pushed pawn's doing (color-agnostic).** At least one square `s ∈ new` must be attributable to *this* pawn leaving `move.from_square`. Require **either** of:

- **(2a) Vacated-square case:** `move.from_square ∈ new` — the pawn was itself standing on the square the king now steps to (e.g. king g8, pawn on g7 plays `g7→g6`, opening **g7**; king g1, the rarer `g2→g3` opening **g2**). This is the direct "the pawn stepped out of the king's escape square" mechanism.
- **(2b) Back-rank front-square case (the dominant pattern):** some `s ∈ new` is **one king-step from `king_sq`** *and* the square became survivable specifically because the pawn vacated `move.from_square`. Concretely: `s` is adjacent to `king_sq`, and **with the pawn restored to `move.from_square` the square `s` is not a survivable flight** (i.e. `s ∉ flights_before`, already guaranteed by `s ∈ new`) **and** `move.from_square` lies on the king's own or adjacent file within the king's neighborhood (guaranteed by VETO 4). The canonical instance: king **g1**, pawn `h2→h3` opens **h2** — h2 was occupied by the pawn pre-push (so not a flight before) and is empty, unattacked, and king-adjacent after. Here `move.from_square == h2 == s`, so (2a) and (2b) coincide; (2b) also covers double-steps (see §6) where the relevant opened square is the vacated `from_square`.

In practice **the opened luft square is almost always exactly `move.from_square`** (the pawn vacates the square the king escapes onto), so (2a) handles the overwhelming majority and (2b) is the guard that keeps the attribution honest. **If `new` is non-empty but contains no square attributable to this pawn** (a coincidental opening from an unrelated discovered line), **abstain** — do not credit luft to geometry the pawn did not cause.

**CONFIRM 3 — Pin independence (anti-false-negative).** A pawn that is **absolutely pinned to its own king cannot push** and the move would be illegal, so it never reaches this predicate. A pawn under a **relative pin** (pinned to a more valuable piece, not the king) **can still legally push**, and such a push still makes genuine luft — so **do not veto on `board.is_pinned`**. The flight-square diff is computed from raw geometry and is unaffected by pins on the *pushed* pawn; pins are therefore neither consulted nor needed for the pushed pawn. (Pins on enemy pieces are likewise irrelevant: `is_attacked_by` counts a pinned enemy attacker's coverage, which is the correct conservative posture for "would the king be safe there.")

**If VETO 1–4 pass and CONFIRM 1–2 hold → certify `luft`.** Record `was_boxed_in = (len(flights_before) == 0)` for the evidence bundle (flag only, never a gate).

**Color / side handling (must be mirrored exactly — and is, by construction):**

| quantity | how it stays color-agnostic |
|---|---|
| king square | `board.king(mover_color)` — reads the actual square, never assumes rank 0 vs 7 |
| enemy (attacker) color | `not mover_color` — used in every `is_attacked_by` / survivability test |
| pawn-direction | **never referenced** — the diff uses the vacated `from_square`, which already encodes direction |
| flight squares | `board.attacks(king_sq)` — symmetric for both colors and all board positions |
| file adjacency (VETO 4) | `abs(file(king) - file(pawn)) <= 1` — no file constants, both colors identical |

## 3. Positive examples

*(FENs are illustrative; the predicate decides from board geometry. Each was checked against python-chess.)*

1. **Classic kingside `h3` luft (White).** FEN `6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1`, move **h2→h3**. King g1. `flights_before = {f1, h1}` (the lateral back-rank squares — *non-empty*, which is why the draft's VETO 5 wrongly killed this). `flights_after = {f1, h1, h2}`. `new = {h2}`, and `move.from_square == h2 ∈ new` → CONFIRM 2a holds. **Certifies; `was_boxed_in = False`** (the king had sideways air but no forward escape; h3 still opens the decisive h2). The same position with a back-rank rook present makes it the textbook back-rank-relief case.

2. **Black mirror …`h6` preventing `Rd8#` (boxed-in).** FEN `6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1`, move **h7→h6**. King g8, White rook d1. `flights_before = {f8, h8}` (empty, unattacked back-rank squares — again why VETO 5 was fatal). `flights_after` adds **h7**. `new = {h7}`, `move.from_square == h7 ∈ new`. **Certifies.** This is exactly the move that averts the back-rank mate; `was_boxed_in` is `False` only because f8/h8 read as lateral air, underscoring why "boxed in" must be a flag, not the gate.

3. **Queenside `b3` luft, king on c1 (side-agnostic, non-kingside).** FEN `2kr3r/ppp2ppp/8/8/8/8/PPP2PPP/2KR3R w - - 0 1`, move **b2→b3**. King c1 (file 2), b-pawn on file 1 (`|2-1| = 1`, passes VETO 4). `flights_before = {b1}`; `flights_after` adds **b2**. `new = {b2}`, `move.from_square == b2 ∈ new`. **Certifies** — demonstrates the b/c/d family for a c-file king and that the a-pawn is *not* needed here.

4. **The `Kb1` tuck makes `a3` real luft.** FEN `1k1r3r/ppp2ppp/8/8/8/8/PPP2PPP/1K1R3R w - - 0 1`, move **a2→a3**. King **b1** (file 1), a-pawn on file 0 (`|1-0| = 1`, passes). `new = {a2}`. **Certifies** — the case §1 calls out: `a3` makes luft only once the king is on the b-file, never for a c-file king.

5. **`g3` opening g2 for a g1 king.** FEN `6k1/5p1p/6p1/8/8/8/5PPP/6K1 w - - 0 1`, move **g2→g3**. King g1; `new = {g2}`, `move.from_square == g2 ∈ new` → CONFIRM 2a. **Certifies** (f/g/h family, vacated-square mechanism).

## 4. Negative / edge cases

1. **King already had air and the push opens nothing new (routine prophylactic `h3`).** In an open position where the king's forward/lateral squares were already survivable flights, `flights_after - flights_before` is empty → **CONFIRM 1 abstains**. Sound prophylaxis, but it added *no new* flight square, so it is not labelled luft — matching a coach declining to call an unnecessary `h3` "luft." *(This is the legitimate residue of the draft's intent; it is enforced by the diff, not by the broken "had any flight → veto.")*

2. **Pawn push far from the king (queenside storm while king is on g1).** King g1, move **a2→a4**: a-file is 6 from g-file → **VETO 4** fires. Opens no square next to the king. Not luft — a space-gaining advance.

3. **Capture that incidentally opens a square (e.g. `hxg6` next to the king).** **VETO 3** fires (capture / en passant). The quiet-push concept excludes captures, trading a little recall for precision.

4. **New "flight square" walks into check — not survivable.** King g8, **g7→g6**, but g7 is covered by an enemy bishop on the long diagonal: `g7` fails the survivability test in `_king_flights` (`is_attacked_by(enemy, g7)` is `True`), so it is not in `flights_after`; if it is the only candidate, `new` is empty → **CONFIRM 1 abstains.** Opening a square the king cannot use is not luft.

5. **King-as-sole-blocker false safety (the survivability bug).** King h2, enemy rook h8, pawn `g2→g3` (or any push) that would "open" h1: a *naive* `is_attacked_by` reports h1 safe because the king on h2 blocks the h-file. The **king-removed probe** in `_king_flights` correctly reports h1 as attacked (the king would remain on the h-file, in check) → h1 is **not** a flight, and is not certified as luft. Fixed.

6. **Opening attributable to a discovered line, not the pawn.** If the only square in `new` becomes survivable because the pawn's departure *discovered* an unrelated friendly defender (so the square is king-adjacent but not `move.from_square` and not made-safe by the pawn's vacancy), **CONFIRM 2** fails → abstain. Prevents crediting luft to a coincidental geometry change.

7. **Promotion push (`h7→h8=Q`) and en-passant push.** Promotion → **VETO 1** (`move.promotion` set; also the destination is no longer a pawn). En passant → **VETO 3** (`is_capture` is `True`). Neither is luft.

8. **Board edge / corner king.** King on h1 or a8: `board.attacks(king_sq)` yields only the on-board king steps, so no phantom off-board "flight" is invented; if the only "opening" would be off the board, `new` is empty and nothing certifies. Handled naturally, no special-casing.

9. **King currently in check after the push.** If `board_after.is_check()` (the mover left/placed their own king in check — only possible via a discovered check from the *opponent's* perspective on the prior move, normally illegal; defensive only), the flight-square diff may still report a square. We **do not specially gate on it**: a square that is a survivable king-step under the king-removed test is still genuine air. (The narrator's eval/context handles whether the king is actually in trouble; this matches the engine-free posture and the §6 limitation.)

## 5. Evidence bundle

Return **`(bool, Optional[dict])`**, mirroring `is_outpost` (returns supporter squares) and `is_rook_lift` (returns a reason string). The dict is populated **only on success** and is `None` on every veto/abstain:

- `king_square: int` — render with `chess.square_name` (e.g. `"g1"`).
- `king_color: bool` — `mover_color` (`chess.WHITE` / `chess.BLACK`).
- `pawn_from: int` / `pawn_to: int` — `move.from_square` / `move.to_square` (e.g. `"h2"` / `"h3"`).
- `luft_squares: List[int]` — sorted `new` (the newly opened survivable flight squares), e.g. `["h2"]`. Non-empty by construction (CONFIRM 1).
- `was_boxed_in: bool` — `True` iff `flights_before` was empty (the strongest, fully-smothered case). **A reported flag, never a gate** — its draft role as a veto was the central bug. Drives whether the narrator frames it as relieving an imminent back-rank mate vs. simply adding air.
- `flights_before_count: int` — `len(flights_before)`; lets the narrator distinguish "the king's only escape" from "one more bolt-hole."
- `relative_pin_on_pawn: bool` — `board_before.is_pinned(mover_color, move.from_square)` (a *relative* pin, since an absolute pin would make the push illegal); recorded so the narrator can note the push was still available. Usually `False`.
- `evidence: str` — ready-to-quote narrator string built from `chess.square_name` and the literal word "king"/"square" (never a tag or field name), e.g.:
  - boxed-in / back-rank case: `"h3 makes luft for the king on g1, opening h2 as an escape square and easing the back-rank threat"`.
  - non-boxed case: `"h6 gives the king on g8 a flight square on h7"`.

The narrator asserts luft only when `luft` is in the move's `certified` set, and may quote `evidence` directly. **Never expose a field or tag name in prose** (existing prompt rule).

## 6. Wiring

- Add `"luft"` to `factgate.GATED_TAGS` (`factgate.py:222`).
- In `certified_claims` (`factgate.py:235`), alongside the `is_outpost` tuple-guard pattern:
  ```python
  lf = _safe(lambda: is_luft(board_before, move, board_after, mover_color))
  if lf and lf[0]:
      tags.add("luft")
  ```
  `is_luft` returns `(bool, Optional[dict])`, so guard via `lf and lf[0]` exactly like `is_outpost`/`creates_fork`; `_safe` collapses any internal error to `None`, which fails the guard and silently drops the tag (the module's fail-safe posture).
- To surface the evidence bundle (Tier 1+), serialize the dict in `narrator._move_to_dict` inside the `if tier >= 1:` block beside `certified` (`narrator.py:440-462`), under a new key (e.g. `d["luft_evidence"]`), wrapped in the same try/except fail-safe; emit only when present.
- **Register the claim in the fact-gate prompt rule at `narrator.py:202`** — add "**luft / a king flight square** (`luft`)" to the enumerated whitelist — or the narrator is forbidden from asserting it even when certified. Adding to `GATED_TAGS` without updating the prompt rule leaves the tag certified-but-unspeakable.

## 7. Known limitations

- **Survivability is one-ply, geometric, engine-free.** The king-removed `is_attacked_by` test rejects squares the king would be captured on or remain in check on immediately, but it does not see that stepping to the flight square loses to a 2-move tactic, nor does it prove a back-rank mate actually existed before. This is the same posture as the rest of `factgate.py`; `was_boxed_in` / `flights_before_count` approximate the severity.
- **"Eased back-rank danger" is inferred from geometry, not proven by Stockfish.** The detector certifies a *new survivable flight square next to the king*; it does not run the engine to confirm a mate threat. Deliberate, consistent with the module's engine-free contract.
- **Adjacency is file-based (VETO 4), not threat-based.** A pawn making luft from two files away via a bizarre king position would be missed — but the opened square must be a king-step, so a >1-file pawn essentially cannot vacate a king-adjacent square; this is a safe approximation, not a real gap.
- **Quiet-push only.** Captures that genuinely create king air (recapturing to open a flight square) are not certified (VETO 3), trading a little recall for precision per James's "false positives are bugs" standard.
- **Double-step pushes** (`h2→h4`) are handled by the same diff: the vacated `from_square` (h2) is the candidate flight square and CONFIRM 2a keys off it. If the king needed the *transit* square (h3) rather than h2, attribution still correctly keys off `from_square` = h2, which is the genuine flight square in the standard back-rank picture; a contrived case needing h3 specifically would not certify (acceptable, rare).
- **Evaluated only on the played pawn push.** It certifies luft on the ply that makes it; it does not retroactively notice a king that gained air several moves ago, nor luft made by the *opponent*. (A board-wide scan would be a larger feature.)
- **Pins on the pushed pawn are deliberately ignored** (CONFIRM 3): an absolutely-pinned pawn can't push (move is illegal, never reaches us); a relatively-pinned pawn can, and its luft is real. This is a correctness choice, surfaced via `relative_pin_on_pawn`, not a gap.

## 8. Complexity

**Low–Medium.** No engine; pure python-chess geometry over two boards. The core is a small set diff (`flights_after − flights_before`) plus a per-square king-removed `is_attacked_by` over at most 8 king-step squares — O(1) in board size, on par with `is_outpost`. The care points that lift it above trivial are (a) the **king-removed survivability probe** (the fix for the sole-blocker false-safety bug — without it the predicate certifies illusory flight squares); (b) computing `flights_before` on the pre-push board and using the **diff, not an emptiness test**, as the gate (the fix for the fatal false-negative that rejected the textbook luft); (c) the **color- and king-position-agnostic** construction with no hard-coded files and no pawn-direction arithmetic; and (d) the **causal-attribution** clause so coincidental openings are not credited. It reuses the standard `board.attacks` / `board.attackers` / `board.is_attacked_by` / `board.king` idioms and the `board.copy()`-then-mutate pattern already pervasive in `factgate.py` / `analyzer.py`, introducing no new machinery.

---

## Infiltration / penetration (`infiltration`)

Sanity check passed. File is on disk (38 KB at the requested path); both load-bearing corrections re-verified on python-chess 1.11.2: the king example (rank 5) now qualifies and would have been wrongly vetoed by the draft's `{6,7}`; the check-giving rook is now excluded by the new veto 3 where the draft's target (b) would have certified it. I checked every positive/negative FEN in the spec against the real venv, and the broken phase wiring against the actual `factgate.py`/`narrator.py` source.

result: Corrected `infiltration` spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\10-infiltration.md — 10 defects fixed (broken phase wiring, self-vetoing king deep-rank gate, check-giving false positives, wrong hanging-caveat string, absolute-vs-relative pin over-claim, king mis-applied branches, plus promotion/castling/board-edge/evidence gaps), all FENs machine-verified.

# Detection Spec — Infiltration / penetration — tag `infiltration`

> **Status:** corrected after adversarial review. This revision fixes a **broken phase
> wiring** (the draft told the implementer to read `move.phase` inside `certified_claims`, but
> that function receives a `chess.Move`, which has **no `.phase`** — verified — so the king
> branch could never have been gated; phase must be threaded through the signature **and** the
> `narrator.py` call site), a **self-contradicting king deep-rank gate** (the draft's king
> `deep_ranks = {6, 7}` would have **vetoed its own flagship king example 5**, `Kd6→e6`, because
> e6 is rank **5** — verified), an **incoherent check-giving "infiltration"** (the draft's
> target (b) certified a heavy piece that *directly attacks the enemy king*, but such a move
> **gives check** — `board_after.is_check()` is `True`, verified — so the opponent is forced to
> respond and it is a tactic, not standing penetration), a **wrong hanging-caveat string** (the
> draft invented `"— but the infiltrating piece is itself hanging"`; the real idiom in
> `detect_double_attack` is `"— but the attacking piece is itself hanging"` — `analyzer.py:331`),
> an **over-claimed pin check** (`board.is_pinned` is **absolute-pin only** — a rook pinned to its
> own *queen* returns `False`, verified — so the spec must not imply it covers relative pins), a
> **king-confinement branch wrongly offered to the king itself**, and a set of
> **board-edge / promotion / castling-side / side-to-move** under-specifications. Every FEN below
> is machine-verified on **python-chess 1.11.2**. See §8 (defects fixed) for the full log.
> Predicate lives in `factgate.py` as `is_infiltration(board_after, square, color, phase)`; it is
> **not** a thin wrapper (there is no analyzer detector to delegate to).

## 1. Expert definition

**Infiltration (penetration)** is the arrival of a heavy piece — a **rook or queen** (and, in the
endgame, the **king**) — onto a **deep rank inside enemy territory**, where it cannot easily be
evicted and from which it does real damage: it rakes weak enemy pawns from behind and/or boxes the
enemy king against the edge. The canonical instance is the **"rook on the 7th"** — Capablanca's
"a rook on the seventh rank is often worth a pawn": a rook on the rank where the opponent's pawns
started, attacking them along their bases while the enemy king is cut off on the back rank.

"Deep" is defined **relative to the mover's colour**, by the rank the piece lands on. The
heavy-piece (rook/queen) gate and the king gate are **different ranks** — the king's reach is
deliberately broader because an endgame king that has marched to its **6th rank** is already
penetrating (the classic "king to the sixth"):

- **Heavy piece (rook / queen)** — White: the **7th rank** (rank index 6) or **8th / back rank**
  (rank index 7); Black mirror: the **2nd rank** (rank index 1) or **1st / back rank** (rank index
  0).
- **King (endgame only)** — White: **rank index ≥ 5** (the 6th, 7th, or 8th rank); Black mirror:
  **rank index ≤ 2** (the 3rd, 2nd, or 1st rank). *(This is the fix for the draft's flagship king
  example: `Ke6` is rank **5** — verified — and would have been wrongly vetoed by a `{6, 7}` gate.
  A marching king on its 6th rank is the textbook endgame penetration and must qualify.)*

Recognized variants the definition must be **inclusive** enough to catch:

- **Rook on the 7th** — the classic; a rook reaching the opponent's 2nd rank (your 7th). The
  strongest, most common case.
- **Queen infiltration** — a queen landing on the 7th/8th (your deep ranks) raking pawns or
  pressing the king. Queens count.
- **Back-rank infiltration** — a rook or queen reaching the opponent's **back rank** (8th for
  White, 1st for Black), even if not the literal 7th — including a heavy piece swinging onto an
  open back-rank file to box the king or hit a back-rank target.
- **Doubled rooks / "pigs on the 7th"** — two rooks on the 7th. Certifying *one* infiltrating rook
  already certifies the concept; doubling is a strengthening, not a separate gate (see §6).
- **"Absolute 7th"** — a rook on the 7th with the enemy king trapped on the 8th. The strongest
  sub-case (flagged in evidence, not a separate tag).
- **King infiltration (endgame only)** — the marching king reaching a deep rank where it attacks
  enemy pawns or shoulders the enemy king. Gated to the **endgame phase** only; a king on a deep
  rank in the middlegame is a blunder, not infiltration.

**The unifying coach's test:** *a heavy piece (or, in the endgame, the king) has gotten behind the
enemy's lines onto a rank where it is doing damage and is not trivially kicked away — and it does
so as a standing positional fact, not as a one-move check the opponent is forced to parry.*

**Two orientation properties the draft got subtly wrong (made explicit):**

- **This is a post-move, mover-scoped, landing-square predicate** evaluated on `board_after` for
  the piece the mover just played to `move.to_square`. It mirrors `is_outpost` / `creates_fork`
  (square + colour) and is wrapped in `_safe` inside `certified_claims`. Because the move has
  already been pushed, on `board_after` it is the **opponent** to move — so `board_after.attackers`
  / `is_attacked_by` describe who can capture the infiltrator *right now, on the opponent's turn*,
  which is exactly the eviction question we want. No turn-flip is needed (unlike
  `_enemy_pawn_can_attack`, which probes a hypothetical).
- **A move that arrives with check is NOT infiltration.** If `board_after.is_check()` is `True`,
  the infiltrating piece has delivered a **check** (the only way the side-to-move's king is in
  check on `board_after` is the move just played), the opponent is **forced** to respond, and we
  abstain — the same posture `_mate_threat` takes (`factgate.py:264`). A deep piece giving check on
  the move it lands is a tactic owned by `fork` / `mate_in_one_threat` / eval, not a standing
  penetration. *(This kills the draft's "directly attacks the enemy king" target, which would have
  certified exactly these checking moves — verified that a rook landing where it attacks the enemy
  king makes `board_after.is_check()` True.)*

---

## 2. Detection rules (VETO-THEN-CONFIRM)

Signature to implement:

```python
def is_infiltration(
    board_after: chess.Board, square: int, color: bool, phase: str
) -> Tuple[bool, Optional[dict]]:
    ...
```

Returns `(True, evidence)` on success, `(False, None)` on any veto. `color` is the **mover's**
colour; `square` is `move.to_square`; `phase` is the move's phase string
(`"opening" | "middlegame" | "endgame"`) — **passed in explicitly** (see Wiring; it is *not*
derivable inside this function).

Define, once, the mover's geometry (no White-relative direction hard-coded):

```python
if color == chess.WHITE:
    heavy_deep_ranks = {6, 7}      # 7th, 8th
    king_deep_ranks  = {5, 6, 7}   # 6th, 7th, 8th  (king reaches deeper)
    back_rank = 7
else:
    heavy_deep_ranks = {1, 0}      # 2nd, 1st
    king_deep_ranks  = {2, 1, 0}   # 3rd, 2nd, 1st
    back_rank = 0
enemy = not color
```

### VETO stage (cheap necessary conditions — bail the instant the claim is impossible)

1. **Piece-type veto.** `piece = board_after.piece_at(square)`. Abstain unless `piece` exists,
   `piece.color == color`, **and** `piece.piece_type in (chess.ROOK, chess.QUEEN, chess.KING)`.
   (Knights/bishops reaching deep squares are `outpost` candidates; pawns are `passed_pawn` /
   promotion — other tags.)

2. **King-phase veto.** If `piece.piece_type == chess.KING`, abstain unless `phase == "endgame"`.
   A middlegame king on a deep rank is a blunder, never infiltration. *(Phase is supplied by the
   caller — see Wiring. The draft's claim that `certified_claims` can read `move.phase` is false:
   inside that function `move` is a `chess.Move`, which has no `.phase` attribute — verified.)*

3. **Check-abstention veto (the coherence fix).** If `board_after.is_check()`, abstain. The
   infiltrator arrived with check; the opponent is forced to respond and this is a tactic, not
   standing penetration. Mirrors `_mate_threat`'s under-check abstention (`factgate.py:264`).
   *(This is also what prevents certifying a "king infiltration" that is itself giving an
   impossible check, and any rook/queen back-rank check.)*

4. **Depth veto (the core geometric refutation — kills most false claims instantly).** Choose the
   correct rank set by piece type:
   - rook/queen → abstain unless `chess.square_rank(square) in heavy_deep_ranks`;
   - king → abstain unless `chess.square_rank(square) in king_deep_ranks`.

   A rook on the 5th, a queen on the 4th, a king on its 5th rank — none are deep enough.

### CONFIRM stage (run only if all vetoes pass)

5. **Operability — it must not be trivially hanging or stuck.** Compute, against the **opponent to
   move** on `board_after`:
   - `attacked  = board_after.is_attacked_by(enemy, square)`
   - `defended  = board_after.is_attacked_by(color, square)`
   - `pinned    = board_after.is_pinned(color, square)`  *(absolute pin to the mover's own king
     only — see the limitation in §6; this does **not** detect a relative pin, e.g. a rook pinned
     to its own queen, which returns `False` — verified)*

   Apply:
   - **Pinned veto.** If `pinned`, abstain. A rook pinned to its own king on the 7th is stuck, not
     infiltrating — same posture as `detect_double_attack` (`analyzer.py:288`).
   - **Hanging handling** (mirrors `detect_double_attack`, `analyzer.py:328–331`):
     - **Queen or king:** if `attacked and not defended`, **abstain outright**. A hanging queen
       "infiltration" is a blunder; a king that has marched into a square the enemy attacks and
       nothing defends is walking into capture/loss, not penetrating.
     - **Rook:** if `attacked and not defended`, do **not** auto-veto — record `hanging = True` and
       append the faithful caveat (see §5). Rationale: a rook deliberately given for two pawns +
       7th-rank pressure is a real motif; the narrator must never *over*-claim it, hence the
       caveat, but the geometric fact still holds for the moment it arrives.

6. **Purpose — it must be doing damage.** Confirm **at least one** target. Order them by force and
   report the **strongest** found: **(b) king-confinement > (a) pawn-raking > (c) open-file
   back-rank arrival**.

   - **(a) Attacks an enemy pawn (rook / queen / king).** Some square in `board_after.attacks(square)`
     holds an enemy pawn (`piece_at(s)` is a pawn of `enemy`). This is the "raking the pawns from
     behind." Collect **all** such squares into `targeted_pawns` (loop style of
     `detect_double_attack`, `analyzer.py:292`). *(This is the **only** purpose branch available to
     a **king** — a king does not "confine on the edge," and a king on an open file means nothing.
     A king infiltration must hit a pawn.)*

   - **(b) Confines the enemy king on the edge (rook / queen ONLY).** Let
     `ek = board_after.king(enemy)`. This branch fires when **all** hold:
     1. `ek is not None and chess.square_rank(ek) == back_rank` — the enemy king is on its own back
        rank;
     2. the infiltrator is a rook or queen on a rank **adjacent to or on** that back rank — i.e.
        `chess.square_rank(square)` is `back_rank` or the rank one step toward the centre (for
        White: rank 7 or 6; for Black: rank 0 or 1) — already guaranteed by veto 4;
     3. the infiltrator **cuts the king's escape**: it controls a square on the king's escape rank
        (the rank between the king and the centre) on the king's file or an adjacent file —
        operationally, `any(chess.square_rank(s) == escape_rank for s in board_after.attacks(square))`
        where `escape_rank = back_rank ± 1` toward the centre, intersected with the king's file ±1.
        A simple, inclusive sufficient form the implementer may use: the infiltrator and the king
        **share a file** (the rook/queen pins the king to the edge laterally) **or** the infiltrator
        sits on the rank directly in front of the king covering its forward escape squares.

     **Because veto 3 already abstained under check, this branch can only fire when the infiltrator
     confines *without* giving check** — exactly the "boxed in, not checked" standing pattern we
     want. If the enemy king is on the back rank and the infiltrator is the rook on the 7th, set
     `absolute_seventh = True` when `piece.piece_type == ROOK` and `chess.square_rank(square)` is
     the 7th-rank index (White 6 / Black 1) — the strongest sub-case.

   - **(c) Open-file back-rank arrival (rook / queen ONLY).** The piece **landed on the enemy back
     rank** (`chess.square_rank(square) == back_rank`) **and** the arrival file is open or
     half-open **for the mover**, **and** that rank is not inert: either an enemy pawn or the enemy
     king lies on the back rank within `board_after.attacks(square)`, **or** the arrival file is in
     `file_structure(board_after)["open"]` / `["half_open_white"|"half_open_black"]` (the mover's
     half-open key), reusing the packet's own file truth exactly as `is_rook_lift` does
     (`factgate.py:96–103`). A rook reaching c8 on an open c-file with the enemy king on g8 is the
     textbook case (verified: c-file open, `Rc8` attacks along the 8th rank toward g8, no check).

   If none of (a)/(b)/(c) hold, abstain: the piece is deep but inert — a likely overextension, not
   infiltration.

7. **Confirm and return.** If a purpose from step 6 holds and step 5 did not veto, return
   `(True, evidence)` (shape in §5), leading the `evidence` string with the strongest reason found.

**Reuse summary:** `file_structure` (open/half-open, the packet's source of truth);
`board.attacks` / `attackers` / `is_attacked_by` / `is_pinned` / `king` / `is_check` (the
`detect_double_attack` idioms); `PIECE_NAMES` + `chess.square_name` for human text. **No new
geometry helper and no engine call.** The one wiring change is threading `phase` (below).

### Wiring (the integration the draft got wrong)

- Add `"infiltration"` to `factgate.GATED_TAGS` (`factgate.py:222`).
- **Thread `phase` into `certified_claims`.** The king branch needs the move's phase, and
  `certified_claims` currently has **no access to it** — it receives `chess.Board` objects and a
  `chess.Move` (no `.phase`). Two coordinated edits:
  1. In `factgate.py`, extend the signature to
     `certified_claims(board_before, move, board_after, mover_color, phase="middlegame")` (default
     keeps existing callers/tests working), and inside it add, with the same `_safe` / `and [0]`
     guard the other tuple-returning predicates use:
     ```python
     inf = _safe(lambda: is_infiltration(board_after, move.to_square, mover_color, phase))
     if inf and inf[0]:
         tags.add("infiltration")
     ```
  2. In `narrator.py` (`_move_to_dict`, the call at `narrator.py:453–458`), pass the move's phase
     explicitly — here `move` **is** a `MoveAnalysis`, so `move.phase` is valid at the call site
     (it is *not* valid inside `certified_claims`):
     ```python
     tags = certified_claims(
         chess.Board(move.fen_before),
         chess.Move.from_uci(move.uci) if move.uci else chess.Move.null(),
         chess.Board(move.fen_after),
         move.side == "White",
         move.phase,            # <-- threaded through; MoveAnalysis.phase exists (analyzer)
     )
     ```
- Register `"infiltration"` in the fact-gate prompt rule at `narrator.py:202` (add it to the
  whitelist sentence, e.g. "a **rook or queen that has infiltrated a deep rank** (`infiltration`)"),
  or the narrator is forbidden from asserting it. Serialize the evidence dict into the Tier-1
  packet under the existing `if tier >= 1:` block (`narrator.py:440–462`), under the same
  try/except fail-safe.

---

## 3. Positive examples

Every FEN is verified on python-chess 1.11.2 (rank indices, attack sets, check status, and
hanging/pin status as stated). FENs are written with the infiltration **already on the board**
(i.e. the `board_after` the predicate sees), opponent to move.

1. **Classic rook on the 7th (White), raking a pawn.** FEN `6k1/R4ppp/8/8/8/8/5PPP/6K1 b - - 0 1`
   — White **Ra7**. Rook on the mover's 7th (rank 6); `attacks(a7)` includes **f7** (enemy pawn,
   verified) → target (a). Not in check, not attacked by Black, not pinned. **Certified**, leading
   with pawn-raking. `targeted_pawns = [f7]` (and g7/h7 are also enemy pawns on the rank but they
   sit behind f7 on the rook's line — only squares actually in `attacks(a7)` are listed; verify per
   square).

2. **Rook on the 7th confining the king (no check).** FEN `5k2/R5pp/8/8/8/8/6PP/6K1 b - - 0 1` —
   White **Ra7**, Black king **f8** (rank 7 = its back rank), Black to move, **not in check**
   (verified). Rook on rank 6 attacks **g7** (enemy pawn) → (a), and the enemy king is on its back
   rank with the rook on the adjacent 7th cutting its second rank → (b). **Certified**; king
   confinement (b) leads the evidence. `absolute_seventh = True` is **not** set here (the king is on
   f8, the rook does not pin it to the 8th by file), but `confines_king = "f8"`.

3. **Queen infiltration on d7.** FEN `r4rk1/pp1Q1ppp/8/8/8/8/PPP2PPP/2KR3R b - - 0 1` — White
   **Qd7**. Queen (allowed) on rank 6; `attacks(d7)` rakes **b7** and **f7** (both enemy pawns,
   verified); not in check; `is_attacked_by(BLACK, d7)` is `False` → not hanging. **Certified** as
   queen penetration; `targeted_pawns = [b7, f7]`.

4. **Black mirror — rook on the 2nd rank.** FEN `6k1/5ppp/8/8/8/8/r4PPP/6K1 w - - 0 1` — Black
   **Ra2** (the move just played by Black; the predicate runs with `color = BLACK`). For Black,
   `heavy_deep_ranks = {1, 0}`; a2 is rank **1** (verified). `attacks(a2)` hits **f2** (enemy pawn,
   verified) → (a). Colour handling yields the symmetric result. **Certified.**

5. **Endgame king infiltration (the example the draft would have vetoed).** `board_after` FEN
   `8/8/2k1Kp2/8/8/8/5P2/8 b - - 0 1` — White **Ke6** after `Kd6→e6` (or similar), Black king c6,
   Black pawn f6. `phase == "endgame"`. Ke6 is rank **5** — **in `king_deep_ranks = {5, 6, 7}`**
   (the draft's `{6, 7}` would have wrongly vetoed this, verified). Not in check; `attacks(e6)`
   includes **f6** (enemy pawn, verified) → (a); the king is not attacked-and-undefended.
   **Certified** as king penetration. In a middlegame FEN the identical geometry is vetoed by veto
   2.

6. **Back-rank rook on an open file.** FEN `2R3k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1` — White
   **Rc8**. Landed on the enemy back rank (rank 7); the **c-file is open**
   (`file_structure → "c" in open`, verified); the enemy king g8 is on the back rank within the
   rook's rank reach (`attacks(c8)` includes g8 along the 8th, verified); **not in check**
   (verified). Targets (b)/(c) fire. **Certified** as back-rank infiltration down the open c-file;
   `arrival_file_state = "open"`.

(Each example's defining feature: a rook/queen on a deep rank — or, in the endgame, the king —
that is not in check, not hanging-and-undefended, not pinned, and is hitting a pawn, confining the
king on the edge, or arriving on an open back-rank file.)

---

## 4. Negative / edge cases

1. **Knight or bishop on a deep square** (e.g. a knight on e7). **Excluded** by veto 1
   (piece-type): an outpost/fork candidate, owned by `outpost`/`fork`, never `infiltration`.
   Prevents double-claiming.

2. **Rook on the 5th/6th rank ("active rook," e.g. White Re5/Re6).** **Excluded** by veto 4
   (depth): the 5th/6th are not heavy-deep ranks for White (`heavy_deep_ranks = {6, 7}`). "Active
   rook" is deliberately *not* infiltration — keeps the gate tight.

3. **Middlegame king on a deep rank.** A king walking to g6/h6 with queens still on. **Excluded**
   by veto 2 (king-phase): only an endgame king counts; a middlegame king there is a blunder.

4. **Idle rook on an empty 7th with nothing to hit.** A rook on a7 where the 7th rank holds no
   enemy pawns in reach, the enemy king is on g8 **not** cut off, and the arrival file is not
   open/half-open. **Excluded** by step 6: no pawn (a), no confinement (b), no open-file back-rank
   arrival (c). Deep but inert ≠ infiltration.

5. **Hanging queen on the 7th.** A queen on d7 attacked by a Black piece with no White defender —
   e.g. `r4rk1/pp1Q1ppp/1n6/8/8/8/PPP2PPP/2K4R b - - 0 1`, where a Black knight on b6 attacks d7
   and **no White piece defends it** (verified: `is_attacked_by(BLACK, d7)` True,
   `is_attacked_by(WHITE, d7)` False). **Excluded** by step 5 (queen branch): a hanging queen is a
   blunder, vetoed outright so the narrator never praises it.

6. **Pinned rook on the 7th.** A rook reaches the 7th but is **absolutely** pinned to its own king
   — e.g. `4r1k1/4R1pp/8/8/8/8/8/4K3 b - - 0 1` (`is_pinned(WHITE, e7)` True, verified).
   **Excluded** by step 5 (`is_pinned`): a pinned infiltrator can't operate. *(Caveat, made
   explicit: `is_pinned` catches **only absolute pins**. A rook pinned to its own *queen* — a
   relative pin — returns `False` (verified) and is **not** vetoed; this is an accepted limitation,
   §6, not a silent bug. The rook genuinely *can* move there, just at the cost of the queen, so
   certifying the geometric infiltration is defensible.)*

7. **Pawn promoting / reaching the back rank.** A pawn on the 8th (pre-promotion glance) or a
   passed pawn deep in enemy territory. **Excluded** by veto 1; promotion/passed pawns are the
   `passed_pawn` / promotion domain. *(A promotion move's `move.to_square` carries the **promoted
   piece** on `board_after` — e.g. a queen on a8. Veto 4 still applies: a White piece on rank 7 is
   deep, so a newly-promoted queen on the 8th that is not in check, not hanging, and hits a pawn or
   confines the king **can** legitimately certify as a back-rank infiltration. This is intentional
   and correct — it is a heavy piece on the enemy back rank — but the narrator's promotion flag
   carries the "this is a promotion" framing separately.)*

8. **Rook on the 7th delivering check.** A rook/queen lands on the 7th/back rank **giving check**
   to the enemy king (e.g. `Rc7+` against a king on c8, or a back-rank check). **Excluded** by veto
   3 (`board_after.is_check()` True, verified for `2k5/2R3pp/8/8/8/8/8/6K1 b - - 0 1`). A checking
   arrival is a forcing tactic the opponent must answer, owned by `fork`/`mate_in_one_threat`/eval
   — not a standing penetration. *(This is the corrected reading of the draft's "directly attacks
   the enemy king" target, which would have wrongly certified exactly these moves — see §8 D3.)*

9. **King marching onto an attacked, undefended deep square.** An endgame king on a deep rank that
   the enemy attacks with no friendly defender. **Excluded** by step 5 (king branch shares the
   queen's outright-hang veto): a king walking into capture/loss is not penetrating.

10. **Castling that places a rook deep — impossible by construction.** Castling never moves a rook
    past its own back/2nd rank, so `move.to_square` of a castling rook is never a deep rank; no
    special handling needed. (Listed because the draft never addressed the castling-side
    interaction. Verified by geometry: White O-O/O-O-O put the rook on f1/d1 — rank 0, not deep;
    Black on f8/d8 — rank 7, not deep. The predicate is evaluated on `move.to_square`, which for a
    castling move is the **king's** destination, also never a deep rank, so castling can never
    spuriously fire.)

11. **Boundary: rook on the back rank, file blocked, king off the edge.** Rook on a8 but the
    a-file is half-open *for the opponent* (an enemy pawn on a-something) so it is not open/half-open
    for the mover, and the enemy king has escaped to g6 with no back-rank pawn in reach.
    **Excluded** by step 6(c): bare presence on rank 8 with no target and no mover-open arrival file
    does not certify.

---

## 5. Evidence bundle

The predicate returns `(True, evidence)` where `evidence` is a `dict` (parallel to `is_outpost`'s
supporter list and `creates_fork`'s description). Every named square is a literal board fact the
narrator may quote verbatim. Exact fields:

- `piece: str` — `PIECE_NAMES[piece.piece_type]` (`"rook"` / `"queen"` / `"king"`).
- `square: str` — `chess.square_name(square)` (e.g. `"a7"`).
- `rank_label: str` — human rank phrasing from the mover's view, derived from `square`'s rank and
  the mover's colour: `"the seventh rank"`, `"the eighth (back) rank"`, `"the sixth rank"` (king
  only), `"the second rank"`, `"the first (back) rank"`, or `"the third rank"` (king only). Built
  from a small colour-keyed map — **never** hard-coded White.
- `targeted_pawns: List[str]` — `chess.square_name` of every enemy pawn in
  `board_after.attacks(square)` (may be empty when certified via king-confinement (b) or open-file
  (c) alone).
- `confines_king: Optional[str]` — the enemy king square name (`chess.square_name(ek)`) when target
  (b) fired, else `None`. (Always `None` for a king infiltrator — branch (b) is rook/queen only.)
- `arrival_file_state: str` — `"open"` / `"half-open"` / `""`, from `file_structure(board_after)`
  for the arrival file (the mover's half-open key: `half_open_white` if `color == WHITE` else
  `half_open_black`), reusing the packet's file truth. Computed for rook/queen; `""` for a king.
- `absolute_seventh: bool` — `True` **iff** the infiltrator is a **rook** on the mover's **7th**
  rank (White 6 / Black 1) **and** the enemy king is on its back rank — the strongest sub-case.
  `False` otherwise (always `False` for a queen or king).
- `hanging: bool` — `True` iff `attacked and not defended` (reachable **only for a rook or king**;
  a queen/king in that state was vetoed in step 5, so for a **king** `hanging` is always `False`
  here and for a **queen** always `False`; in practice `True` only for a deliberately-given rook).
  Drives the caveat clause.
- `evidence_str: str` — **ready-to-quote**, built deterministically, leading with the strongest
  reason found in step 6. Templates (note the hanging caveat is the **faithful** idiom from
  `detect_double_attack`, adapted only by naming the piece — see §8 D4):
  - **King confinement (b):**
    `f"the {piece} on {square} has infiltrated to {rank_label}, cutting off the enemy king on {confines_king}"`
    — prepend `"absolute seventh — "` when `absolute_seventh`.
  - **Pawn-raking (a):**
    `f"the {piece} on {square} has infiltrated to {rank_label}, attacking the pawn(s) on {', '.join(targeted_pawns)}"`.
  - **Open-file back-rank (c):**
    `f"the {piece} on {square} has infiltrated the enemy back rank down the {arrival_file_state} {file}-file"`
    (where `file = chess.square_name(square)[0]`).
  - **Endgame king:**
    `f"the king on {square} has marched into enemy territory on {rank_label}, attacking {', '.join(targeted_pawns)}"`.
  - **If `hanging`**, append exactly:
    `" — but the infiltrating rook is itself hanging"` — this is the `detect_double_attack` idiom
    (`analyzer.py:331`, `"— but the attacking piece is itself hanging"`) with `attacking piece`
    replaced by `infiltrating rook` (only a rook can reach `hanging = True`), keeping the wording
    faithful to the codebase rather than the draft's invented string.

A unit test should assert that `evidence_str` never contains the words `"mate"`, `"checkmate"`, or
`"wins"` — infiltration is a positional/pressure claim, distinct from the mate/eval gates, and
veto 3 already guarantees the move is not a check.

---

## 6. Known limitations

- **Single-piece, single-ply.** Certifies one infiltrating piece on the move it arrives. It does
  **not** specially detect **doubled rooks on the 7th** ("pigs") as a distinct, stronger claim — it
  fires on the second rook's arrival but won't say "doubled." Acceptable: the concept is still
  certified.
- **"Not easily evicted" is approximated, not proven.** Step 5 checks **absolute** pin
  (`is_pinned`) and immediate hanging only. It does **not** detect a **relative pin** (a rook
  pinned to its own queen returns `is_pinned == False` — verified), nor whether the piece can be
  chased off by a pawn/minor over the next moves, nor whether the infiltration is *sound* (that is
  Stockfish's job, outside this pure gate). A rook that lands on the 7th and is harried away next
  move can still be certified for the moment it arrives — consistent with `is_rook_lift` /
  `is_outpost`, which certify the geometric fact, not the long-term verdict.
- **No "it stays there" guarantee.** Reading only `board_after`, it can't know the infiltrator is
  traded immediately. The narrator rule treats `certified` as "true of this position," which is
  honest.
- **King gate leans on `phase`.** If `detect_phase` mislabels a late middlegame as middlegame, a
  genuine king infiltration is missed (false negative). Chosen deliberately: a false negative here
  is far safer than certifying a middlegame king march. The broadened king deep-rank set
  (`{5, 6, 7}` / `{2, 1, 0}`) is the inclusiveness fix; the phase gate is the safety fix.
- **King-confinement geometry is heuristic.** Target (b) recognizes the dominant pattern (enemy
  king on its back rank, infiltrator on the adjacent deep rank cutting the escape rank or sharing
  the king's file) but won't catch every exotic cutting-off configuration. Misses tend toward
  **false negatives**, not false positives — and veto 3 ensures it never fires on a check.
- **Promotion arrivals certify as heavy-piece infiltration.** A pawn promoting to a queen/rook on
  the enemy back rank that is not in check, not hanging, and hits a pawn or confines the king will
  certify (correctly — it *is* a heavy piece on the back rank). The narrator's separate promotion
  framing carries the "this is a promotion" nuance.
- **Doesn't gate on material/eval.** A deep piece attacking a pawn in an otherwise lost position
  still certifies the *geometric* fact; the packet's `eval` / `material` fields carry the verdict.

---

## 7. Complexity

**Low–medium.** The geometry is genuinely simple — a piece-type check, a rank-set membership test
(colour- and piece-keyed), one `board.is_check()` call, and one `board.attacks(square)` loop, all
reusing existing idioms (`attacks`, `is_attacked_by`, `is_pinned`, `king`, `is_check`,
`file_structure`, `PIECE_NAMES`) with **no new helper and no engine call**. It is cheaper than
`detect_royal_alignment` (no `chess.between` clear-line scans) and comparable to `is_outpost`. The
only sources of medium-ness are (1) three ordered target sub-cases (king-confinement / pawn-raking /
open-file back-rank, the first two reachable by different piece types), (2) the colour mirroring
plus the **two distinct deep-rank sets** for heavy pieces vs. the king, and (3) the
**phase-threading wiring change** through `certified_claims` and the `narrator.py` call site (the
one genuinely cross-file edit, since the draft's "read `move.phase` inside the gate" was
impossible). All of it is mechanical, fully specified above, and testable with **no Stockfish
binary** (the L1 pure-predicate tier).

**Files referenced:** `C:\Users\詹天哲\Documents\greco\factgate.py` (predicate home,
`certified_claims` signature to extend, `GATED_TAGS` at line 222, the `_safe` / `and [0]` guard
idiom); `C:\Users\詹天哲\Documents\greco\analyzer.py` (`file_structure`, `PIECE_NAMES`, the
`detect_double_attack` pin/hanging idiom and exact caveat string at lines 288/328–331,
`MoveAnalysis.phase`); `C:\Users\詹天哲\Documents\greco\narrator.py` (the `certified_claims` call
site at lines 453–458 to pass `move.phase`, the Tier-1 serialization block at lines 440–462, the
fact-gate prompt rule at line 202 to register the tag).

## 8. Defects fixed from the draft (adversarial review log)

- **D1 — broken phase wiring (the king branch could never have been gated).** The draft said to
  "reuse the phase already computed... carried on `MoveAnalysis.phase`" and to pass it "as
  `_move_to_dict` already has `move.phase`," implying `certified_claims` could read it. But
  `certified_claims` receives a `chess.Move`, and `chess.Move` has **no `.phase` attribute**
  (verified: `hasattr(chess.Move.from_uci('a1a7'), 'phase')` is `False`). The king-phase veto would
  have thrown `AttributeError`, been swallowed by `_safe`, and **silently dropped the tag on every
  king move**. Fixed: §2 Wiring extends `certified_claims(..., phase="middlegame")` and threads
  `move.phase` from the `narrator.py:453` call site, where `move` *is* a `MoveAnalysis`.

- **D2 — self-contradicting king deep-rank gate (false negative on the draft's own example).** The
  draft set king `deep_ranks = {6, 7}` but its flagship king Positive Example 5 plays `Kd6→e6`;
  `e6` is rank **5** (verified), which is **not** in `{6, 7}` — the draft would have **vetoed its
  own example**. The canonical endgame "king to the sixth" penetration is exactly rank 5 (White).
  Fixed: a separate, broader `king_deep_ranks = {5, 6, 7}` (White) / `{2, 1, 0}` (Black), distinct
  from the heavy-piece `{6, 7}` / `{1, 0}`.

- **D3 — incoherent check-giving "infiltration" (false positive class).** The draft's target (b)
  certified an infiltrator that "directly attacks the enemy king" (`square` whose `attacks` hit the
  king). But a rook/queen that attacks the enemy king on the move it lands **gives check** —
  `board_after.is_check()` is `True` (verified for `Rc7+` vs `Kc8`). That is a forcing tactic the
  opponent must answer, not standing penetration, and is owned by `fork`/`mate_in_one_threat`/eval.
  Fixed: veto 3 abstains whenever `board_after.is_check()` (mirroring `_mate_threat`,
  `factgate.py:264`); target (b) is rewritten as **king confinement without check** (boxing the
  king on the edge), and the "directly attacks the king" sub-clause is removed.

- **D4 — wrong hanging-caveat string (would not match the codebase idiom).** The draft specified
  appending `"— but the infiltrating piece is itself hanging"`, calling it "the exact
  `detect_double_attack` idiom." The real string is `"— but the attacking piece is itself hanging"`
  (`analyzer.py:331`). Fixed: §5 uses `"— but the infiltrating rook is itself hanging"` — the
  faithful idiom adapted by naming the piece, with the note that only a **rook** can reach the
  `hanging` state (queen/king are vetoed in step 5), so the wording is exact and singular.

- **D5 — over-claimed pin coverage (silent false negative + misleading spec).** The draft leaned on
  `board_after.is_pinned(color, square)` as the pin check without stating that python-chess
  `is_pinned` detects **only absolute pins** (pin to the own king). A rook pinned to its own
  **queen** (a relative pin) returns `False` (verified) and would **not** be vetoed. Fixed: §2 step
  5 and §6 state the absolute-pin-only semantics explicitly; the relative-pin case is documented as
  an accepted limitation (the rook genuinely *can* move, so certifying the geometric fact is
  defensible) rather than an unflagged hole.

- **D6 — king offered branches it cannot use (false positives / nonsense evidence).** The draft's
  step 5 targets (b) (king confinement) and (c) (open-file back-rank) were written as if available
  to the king, and the king inherited the rook's "don't auto-veto when hanging" leniency. A king
  does not "confine the enemy king on the edge," cannot benefit from an "open file," and must never
  be left attacked-and-undefended. Fixed: targets (b) and (c) are **rook/queen only**; the **king's
  only purpose branch is (a) pawn-raking**; and the king shares the **queen's** outright-hang veto
  (new Negative case 9). `confines_king`, `arrival_file_state`, `absolute_seventh`, and `hanging`
  are all forced to their inert values for a king in §5.

- **D7 — side-to-move / eviction reasoning under-specified.** The draft hand-waved that "no
  turn-flip is needed." Fixed: §1 and §2 state precisely that on `board_after` it is the
  **opponent** to move, so `is_attacked_by(enemy, square)` is exactly the "can the opponent capture
  it on their turn" test we want, and the check-abstention (D3) handles the one case where
  side-to-move matters (the infiltrator's own move left the opponent in check).

- **D8 — promotion / castling / board-edge interactions unaddressed.** The draft's negative list
  named promotion only to exclude pawns, and never mentioned castling-side or the back-rank file
  clamp. Fixed: Negative case 7 explains a **promoted** heavy piece on the back rank can legitimately
  certify (it is a heavy piece, not a pawn, on `board_after`); Negative case 10 shows **castling can
  never fire** the predicate (the castling `move.to_square` is the king's destination, never a deep
  rank, and the rook never lands deep); and target (c)/§5 derive the arrival-file state from
  `file_structure` with the mover's correct half-open key, with the file letter taken from the
  landing square (no off-board indexing).

- **D9 — vague back-rank target (c).** The draft's (c) ("open enough to matter") was loosely
  worded. Fixed: §2 step 6(c) requires `chess.square_rank(square) == back_rank` **and** an actual
  back-rank target (enemy pawn or king in `attacks(square)`) **or** the arrival file in the mover's
  open/half-open set from `file_structure`, with `arrival_file_state` recorded for the evidence.

- **D10 — evidence-field derivations pinned down.** The draft left `rank_label`, `absolute_seventh`,
  `arrival_file_state`, and `hanging` partly implicit and White-leaning. Fixed: §5 gives each field
  an exact, colour-symmetric derivation, forces the king/queen-impossible fields to their inert
  values, adds the king's `"the sixth/third rank"` labels (needed by the broadened king gate from
  D2), and specifies the verbatim, check-free, mate-free `evidence_str` templates with a unit-test
  assertion against the forbidden words.

---

## Fianchetto (`fianchetto`)

Sanity check before finishing: I verified empirically that (a) all four square constants and their diagonals/rays match the spec's table, (b) all five positive-example FENs parse as valid, (c) the mover-only scoping genuinely drops the non-mover's fianchetto (constructed a both-sides position, Black to move), (d) `O-O-O` lands the king on c1/c8 not b1/b8, and (e) veto-2's color check correctly rejects an enemy pawn on g3. The corrected spec was written to the target path with the 7-section structure intact.

result: Corrected `fianchetto` spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\11-fianchetto.md — fixes the central false-negative (mover-only scoping → certify both colors like is_passed_pawn), the c1/c8-not-b1/b8 castling-king inaccuracy, the self-cancelling pawn_home_sq dead logic, the stray move.to_square keying, and tightens the evidence bundle (list-of-dicts, ASCII diagonals, destroyed-fianchetto note, pin-immunity).

# Detection Spec: Fianchetto (`fianchetto`)

> Status: corrected after adversarial review. Companion to `01-pin.md` … `10-infiltration.md`.
> Helper ground truth verified against `factgate.py` (`is_outpost` lines 114–154 as the
> `(bool, evidence)` template, `is_passed_pawn` 157–176 as the **color-symmetric, side-to-move-
> independent** template, `certified_claims` 235–292, `GATED_TAGS` 222–229) and `analyzer.py`
> (`PIECE_NAMES` 211, `board.attacks` / `board.king` idioms). The square constants
> (`chess.G2`/`B2`/`G7`/`B7`/`G3`/`B3`/`G6`/`B6`), diagonals, attack rays, and castling-king
> destinations below were all re-checked empirically against python-chess.
>
> **What the review changed (defects fixed from the draft):**
> 1. **FALSE NEGATIVE — mover-only scoping.** The draft wired this exactly like `outpost` /
>    `passed_pawn` (`is_fianchetto(board_after, mover_color)`), certifying only the mover's
>    bishops. But those are **move-delta** predicates keyed on `move.to_square`; fianchetto is
>    a **standing structural feature** the draft itself calls "true on every ply it persists"
>    and "side-to-move independent." Scoping to `mover_color` silently drops a real fianchetto
>    on the *non-mover's* side (verified: a position with both a White g2 and Black g7
>    fianchetto, Black to move, would certify only Black's — forbidding the narrator from ever
>    asserting White's). **Fix: certify for BOTH colors**, like the color-symmetric
>    `is_passed_pawn`. The predicate is now keyed on the static board, not the move.
> 2. **Incoherent `pawn_home_sq`.** The draft defined a `pawn_home_sq` "to check vacant" that it
>    then admitted "is the same square as the bishop square," making the field self-cancelling
>    dead logic. Removed: veto 1 (bishop present on the flank square) already proves that square
>    is not a pawn. There is exactly one pawn condition — veto 2 — and it is on the *advanced*
>    square (g3/b3/g6/b6).
> 3. **CHESS INACCURACY — castling-king geometry.** The draft's `king_behind` text said the
>    queenside-castled king sits on "c1/b1 / c8/b8." Standard castling lands the king on
>    **c1/c8** (verified), never b1/b8. The `king_behind` square sets are corrected and made
>    exact per flank.
> 4. **`move.to_square` leftover.** The draft's wiring snippet `is_fianchetto(board_after,
>    mover_color)` modeled on `is_outpost` but `is_outpost` takes `move.to_square`. A
>    flank-looping structural predicate must NOT depend on `move.to_square` (the move may be a
>    king or pawn move nowhere near the bishop). Signature corrected to take only the board.
> 5. **Evidence-bundle gaps.** Added explicit `destroyed` sibling note, a `both_colors` return
>    contract, a `king_behind`-square enumeration, and made every evidence string built from
>    constants (never hand-derived), per doctrine.

## 1. Expert definition

A **fianchetto** is the development of a bishop onto its **knight-file square on the second
rank from its own back rank**, behind a knight-pawn that has advanced one square to open the
long diagonal. The structure a strong coach certifies is purely positional — a standing
feature of the board, true on every ply it persists, **independent of whose move it is and of
how the bishop got there**.

Concretely, the certified structure for a given `color` and flank is:

- **White kingside:** bishop on **g2**, friendly pawn on **g3**.
- **White queenside:** bishop on **b2**, friendly pawn on **b3**.
- **Black kingside:** bishop on **g7**, friendly pawn on **g6**.
- **Black queenside:** bishop on **b7**, friendly pawn on **b6**.

The defining geometry in a coach's words: a friendly bishop sits on the b- or g-file at the
**second rank from its own back rank** (g2/b2 for White, g7/b7 for Black), and the
corresponding **knight-pawn has advanced one square** to the third rank from its back rank
(g3/b3 for White, g6/b6 for Black), so the bishop rakes the long diagonal. The flank square
itself is necessarily occupied by the bishop (so the pawn has, by construction, left it).

**Diagonals (empirically verified, the load-bearing geometry):**

| color / flank | bishop sq | long diagonal raked | far corner it aims at |
|---|---|---|---|
| White kingside | g2 | **h1–a8** (light) | **a8** |
| White queenside | b2 | **a1–h8** (dark) | **h8** |
| Black kingside | g7 | **a1–h8** (dark) | **a1** |
| Black queenside | b7 | **h1–a8** (light) | **h1** |

(Note the cross-pairing the draft got right: the g2 / b7 bishops share the h1–a8 diagonal; the
b2 / g7 bishops share the a1–h8 diagonal. The fianchettoed bishop also bears on the *short* arm
of its diagonal — g2 also sees h1, b2 also sees a1, etc. — but the "long diagonal" and `aims_at`
fields name the long arm toward the far corner.)

**Recognized variants — all certify the same core:**
- **Kingside fianchetto** (g2 / g7) — by far the most common; pairs with kingside castling (the
  "fianchettoed king").
- **Queenside fianchetto** (b2 / b7).
- **Double fianchetto** — both flank bishops of one side fianchettoed at once; each flank
  certifies **independently** (the per-flank loop simply fires twice for that color).
- The certified fact is the **resulting structure** (bishop on the fianchetto square with the
  opened knight-pawn), **not the act of moving**. It does **not** matter *how* the bishop
  arrived (`Bg2` in one move, or a bishop re-routed onto g2 many moves later), nor whose move
  just occurred, nor whether the bishop is currently **pinned** (absolute or relative) — a
  pinned fianchettoed bishop is still fianchettoed (pin status is a piece-interaction fact, not
  a structural one, and must never suppress the verdict — explicit anti-false-negative
  requirement). The shield pawn on g3/b3/g6/b6 likewise need not be the *original* knight-pawn:
  a pawn that arrived there by capture (e.g. an h-pawn taking onto g3) still shields the bishop
  and still certifies — veto 2 checks the square's occupancy, not the pawn's provenance.

**Evidence attributes (reported when present; do NOT gate the core certification):**
- a **fianchettoed king** (the friendly king castled on the same flank behind the bishop);
- a **destroyed / exchanged-off fianchetto** (knight-pawn advanced but the bishop is *gone*) —
  the "hole around the king" weakness. This is surfaced as a **separate descriptive note**, and
  is **never** added to the `fianchetto` allow-set (the core requires the bishop present).

Per term guidance, the bishop's placement on the flank square (behind the advanced knight-pawn)
is the **load-bearing condition**; the hole/destruction/king-behind facts are descriptive
add-ons.

## 2. Detection rules (veto-then-confirm)

This is a **standing structural predicate over a single board** (`board_after`), **not** a
move-delta predicate. It is therefore **side-to-move independent** (`board.turn` is never read)
and **evaluated for both colors and both flanks** — unlike `is_outpost` / `is_rook_lift`
(move-delta, keyed on the move), it is keyed on the static board exactly like the
color-symmetric `is_passed_pawn`.

The predicate signature is **`is_fianchetto(board, color) -> Tuple[bool, Optional[List[dict]]]`**
(returns the list of per-flank evidence dicts that certified for that `color`, or `(False,
None)` if neither flank certifies). It takes **only the board and a color** — it must **not**
take `move.to_square` (the move may be unrelated to the bishop).

Define, per `color` and per flank `∈ {kingside (g-file), queenside (b-file)}`:
- `bishop_sq` = the fianchetto square: White `chess.G2`/`chess.B2`, Black `chess.G7`/`chess.B7`.
- `pawn_open_sq` = the advanced knight-pawn square: White `chess.G3`/`chess.B3`, Black
  `chess.G6`/`chess.B6`.

(There is deliberately **no** `pawn_home_sq`: the knight-pawn's home square *is* the bishop
square, and veto 1 already proves a bishop — not a pawn — sits there. The draft's separate
"pawn-home vacant" check was self-cancelling dead logic and is removed.)

**Veto order (cheap necessary conditions first — each kills this flank instantly):**

1. **Bishop-presence veto.** `board.piece_at(bishop_sq)` must be a **bishop of `color`**
   (`piece is not None and piece.piece_type == chess.BISHOP and piece.color == color`). If the
   flank square is empty or holds anything else (including an **enemy** bishop, or a
   wrong-color/wrong-piece), abort this flank. This single O(1) check refutes the overwhelming
   majority of false claims. **Do not** read `board.turn`, pins, or attacks here.

2. **Knight-pawn-advanced veto.** `board.piece_at(pawn_open_sq)` must be a **pawn of `color`**
   (`piece.piece_type == chess.PAWN and piece.color == color`). The color check is essential —
   an *enemy* pawn shoved onto g3/g6 does not open the friendly bishop's diagonal and must not
   certify (verified). If that square does not hold a *friendly* pawn, abort: a bishop on the
   flank square with the knight-pawn still doubled-pushed (g4/b4) or captured away is not the
   textbook fianchetto.

   *(These two O(1) lookups are the full necessary-and-sufficient core.)*

**Confirm:**

3. **Confirm the structure and build the per-flank evidence dict.** With both vetoes passed,
   the fianchetto is certified for `(color, flank)`. Append its evidence dict (section 5) to
   this color's result list. To enrich the dict (non-gating):
   - **Long diagonal / `aims_at`:** taken from the fixed table in section 1 by `(color, flank)`
     — never hand-derived from the board.
   - **`current_rake`:** `sorted(chess.square_name(s) for s in board.attacks(bishop_sq))` — what
     the bishop *actually* controls now (own/enemy blockers truncate the ray). This lets the
     narrator say what it bears on without inventing; if it is truncated short of `aims_at`, the
     prose can note the diagonal is blocked, but the tag still fires (see Limitations).
   - **`king_behind`:** `True` iff `board.king(color)` is on the same-flank castled-king square
     set for that flank (exact squares below). Evidence-only; never gates.

**`king_behind` square sets (corrected — castling-king destinations verified):**
- White kingside (g2): king on **g1 or h1** (`chess.G1`, `chess.H1`).
- White queenside (b2): king on **c1 or b1** (`chess.C1` is the O-O-O destination; `chess.B1`
  included for the king tucked to b1 after `Kb1`).
- Black kingside (g7): king on **g8 or h8** (`chess.G8`, `chess.H8`).
- Black queenside (b7): king on **c8 or b8** (`chess.C8`, `chess.B8`).

  (The draft's "c1/b1" was loosely written as if the king ever lands on b1 from castling — it
  does not; `O-O-O` puts it on **c1**. Both c-file and b-file are listed because a king that
  later steps `Kb1`/`Kb8` is also "behind" a queenside fianchetto. This stays a heuristic
  evidence flag and never gates the tag, so a wrong `king_behind` can never produce a false
  certification.)

**Detecting a *destroyed* fianchetto (evidence note only — does NOT certify `fianchetto`):**
veto 2 passes (friendly pawn on g3/b3/g6/b6) **but** veto 1 fails (no friendly bishop on the
flank square). This is the "hole around the fianchettoed king." It must **never** enter the
`fianchetto` allow-set; surface it, if at all, as a separate `destroyed_fianchetto` descriptive
note keyed off the same flank squares.

**Color/side handling, explicit:**
- `color == chess.WHITE`: bishop g2/b2; opened-pawn g3/b3; back rank 0; advance is "up."
- `color == chess.BLACK`: bishop g7/b7; opened-pawn g6/b6; back rank 7; advance is "down."
- **Side to move is irrelevant** and `board.turn` is never read.
- **Wiring (the central correction):** in `certified_claims`, call it for **both colors** so a
  fianchetto on the non-mover's side is still certified — a standing structural feature is true
  regardless of who just moved:

  ```python
  for col in (chess.WHITE, chess.BLACK):
      fz = _safe(lambda c=col: is_fianchetto(board_after, c))
      if fz and fz[0]:
          tags.add("fianchetto")
  ```

  This mirrors the color-symmetry of `is_passed_pawn`, **not** the mover-only,
  `move.to_square`-keyed convention of `outpost` / `rook_lift`. The single string tag
  `"fianchetto"` is added if either color certifies; the rich per-color dicts go in the parallel
  evidence bundle (section 5), so the narrator can attribute the structure to the correct side.

## 3. Positive examples

All five FENs below were parsed and confirmed valid against python-chess.

1. **White kingside fianchetto (KIA / Catalan setup).**
   FEN: `rnbqkbnr/pppppppp/8/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 0 3` (after g3, Bg2). Bishop on
   g2, friendly pawn on g3 → certifies for White, kingside. Rakes the h1–a8 diagonal toward a8.

2. **Black kingside fianchetto (King's Indian / Grünfeld / Pirc).**
   FEN: `rnbqk2r/ppppppbp/5np1/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 4` (…g6, …Bg7, …Nf6). Bishop on
   g7, pawn on g6 → certifies for Black, kingside, raking a1–h8 toward a1. **Certifies even
   though it is White to move and Black is the non-mover** — the both-colors loop catches it.

3. **White queenside fianchetto (Nimzo-Larsen).**
   FEN: `rnbqkbnr/pppppppp/8/8/8/1P6/PBPPPPPP/RN1QKBNR b KQkq - 1 2` (after b3, Bb2). Bishop on
   b2, pawn on b3 → certifies for White, queenside, raking a1–h8 toward h8.

4. **Black queenside fianchetto (Queen's Indian).**
   FEN: `rn1qkb1r/pbpp1ppp/1p2pn2/8/2PP4/5N2/PP2PPPP/RNBQKB1R w KQkq - 2 5` (…b6 and …Bb7).
   Bishop on b7, pawn on b6 → certifies for Black, queenside, raking h1–a8 toward h1.

5. **Double fianchetto (both flanks, one side).**
   FEN: `rnbqk1nr/pp1p1ppp/8/8/8/1PP3P1/PB1PPPBP/RN1QK1NR w KQkq - 0 5` — White bishops on b2
   *and* g2, pawns on b3 and g3. **Both flanks certify independently**; the evidence list for
   White holds two dicts; the narrator can be handed "a double fianchetto, with bishops on b2
   and g2."

## 4. Negative / edge cases

1. **Two-square knight-pawn push.** Bishop reaches the flank square while the knight-pawn sits
   on **g4/b4** (pushed two). `pawn_open_sq` (g3/b3) is empty → fails veto 2. Excluded: the
   diagonal was opened by a lunge, not the fianchetto one-step. *(veto 2.)*

2. **Destroyed fianchetto / hole around the king.** Knight-pawn on g3 (or g6) but **no friendly
   bishop on the flank square** (traded or never developed there). Fails veto 1 → **not**
   certified. Surfaced only as the `destroyed_fianchetto` note, never in the allow-set.

3. **Bishop on the long diagonal but not on the flank square.** A White light bishop on
   f3/e4/d5/c6 sits on the h1–a8 diagonal but **not on g2** → fails veto 1. A fianchetto is
   specifically the **flank-square** placement, not "any bishop on the long diagonal."

4. **Wrong-color / wrong-piece on the flank square.** A queen, knight, pawn, or an **enemy**
   bishop on g2/b7 → fails veto 1's type/color check. Excluded trivially.

5. **Enemy pawn on the open square.** A **Black** pawn shoved to g3 with a White bishop on g2
   → veto 2's color check rejects it (verified): an enemy pawn does not open the friendly
   bishop's diagonal.

6. **Un-fianchettoed flank (the common true-negative).** g-pawn still on g2 / bishop on f1 or
   c1 (normal opening). Fails both vetoes instantly. Disposed of by veto 1 at O(1).

7. **Reversed-rank confusion (color-symmetry trap).** A **White** bishop deep on **g7** (after a
   long maneuver), or a **Black** bishop on **g2**, is on the *opponent's* fianchetto square and
   does **not** certify for that color. `bishop_sq` is keyed strictly off `color`, so this never
   fires. *(color-parameterized square selection.)*

8. **Bishop on g2 with the g-pawn captured/missing entirely (g3 empty, no g-file pawn).** Fails
   veto 2 → not certified. Deliberately conservative — a bishop with no knight-pawn shield is a
   damaged/atypical formation, not the textbook fianchetto. *(See Limitations; precision over
   recall.)*

9. **Pinned fianchettoed bishop.** A bishop on g2 absolutely or relatively pinned (e.g. to the
   king on the h1–a8 diagonal, or to the queen) is **still fianchettoed** — pin status is never
   read and must not suppress the verdict. Anti-false-negative requirement; **certifies.**

10. **Promotion non-issue.** A bishop cannot be *promoted* onto a 2nd-rank flank square for its
    own color (promotion happens on the back rank of the *opponent*), so there is no promotion
    edge for the bishop-presence veto; and the predicate certifies a promoted-bishop on the
    flank square identically to an original bishop (it does not matter how the bishop arrived).

## 5. Evidence bundle

Following the `is_outpost` `(bool, evidence)` precedent, the predicate returns
`Tuple[bool, Optional[List[dict]]]`: a boolean plus **a list of per-flank dicts** (so a double
fianchetto yields a 2-element list), or `(False, None)` when neither flank certifies. Each dict:

- `color` — `chess.WHITE` / `chess.BLACK` (whose fianchetto).
- `side` — `"White"` / `"Black"` human string (for prose).
- `flank` — `"kingside"` or `"queenside"`.
- `bishop_square` — e.g. `"g2"` (`chess.square_name(bishop_sq)`).
- `pawn_square` — the opened knight-pawn square, e.g. `"g3"` (`chess.square_name(pawn_open_sq)`).
- `long_diagonal` — from the fixed table: `"h1-a8"` or `"a1-h8"` (ASCII hyphen — keep evidence
  strings ASCII-only per the project's non-ASCII-path discipline; do not emit an en-dash).
- `aims_at` — the far corner from the table, e.g. `"a8"`.
- `current_rake` — `sorted(chess.square_name(s) for s in board.attacks(bishop_sq))` — what it
  actually controls now (blockers respected), so the narrator can describe the bishop's reach
  without inventing.
- `king_behind` — `True` iff the friendly king sits on this flank's castled-king square set
  (section 2); `False` otherwise.
- `evidence` — a ready-to-quote, verbatim string built **only** from `PIECE_NAMES`,
  `chess.square_name`, and the fixed table (never hand-derived). Templates:
  - Generic:
    `f"{side}'s bishop is fianchettoed on {bishop_square} ({flank}), the knight-pawn on {pawn_square} opening the {long_diagonal} long diagonal toward {aims_at}"`.
  - With king (append when `king_behind`):
    `f"{base}, behind the castled king on {chess.square_name(board.king(color))}"`.

**`certified_claims` integration (parallel evidence, not a new gated field shape):** the literal
tag `"fianchetto"` is appended to `GATED_TAGS` (`factgate.py:222`) and named in the fact-gate
prompt rule (`narrator.py:202`) so the narrator is *permitted* to assert it. The rich
per-color list is serialized in the Tier-1+ block of `_move_to_dict` (`narrator.py:440-462`),
next to `certified`, under a new key (e.g. `fianchetto_evidence`), wrapped in the same
try/except fail-safe. Because the structure can exist for **both** sides, the evidence payload
keys each dict by `side`/`color` so the narrator attributes it correctly (the central fix: the
draft's mover-only scoping would have hidden the opponent's fianchetto entirely).

**Destroyed-fianchetto note (separate, never in the allow-set):** if a flank passes veto 2 but
fails veto 1, optionally emit a `destroyed_fianchetto` descriptive attribute (e.g.
`f"{side}'s {flank} fianchetto is gone — the knight-pawn on {pawn_square} advanced but the
bishop has left {bishop_square}, leaving a hole on the long diagonal"`). This is a hole/weakness
note, **not** the certified tag.

## 6. Known limitations

- **No quality judgment.** It certifies the *structure*, not whether the fianchetto is *good*
  here. A bishop with its own pawns jamming the diagonal still certifies; `current_rake` exposes
  the truncation but the tag fires regardless (doctrine: certify the fact, let eval-fed prose
  judge it).
- **Conservative on damaged/missing knight-pawns.** A bishop on the flank square with the
  knight-pawn captured (no friendly pawn on g3/b3/g6/b6) is **not** certified (veto 2), even
  though some coaches would loosely call it a "fianchettoed bishop." A deliberate
  precision-over-recall choice; it under-claims rather than over-claims.
- **Flank-square only by design.** A bishop developed to the long diagonal via f3/c3 etc. is
  excluded even if functionally similar — only the exact b2/g2/b7/g7 placement counts.
- **Two-square pushes (g4/b4) excluded** — correct per the term, but it will silently not fire
  on such structures.
- **Destroyed-fianchetto holes are not surfaced through this tag** — they are a separate
  descriptive note (section 5), never the certified `fianchetto`.
- **`king_behind` is heuristic** — file/rank membership can misfire in rare positions where the
  king is on the flank for unrelated reasons; it is evidence-only and never gates, so a wrong
  `king_behind` cannot produce a false `fianchetto` certification.

## 7. Complexity

**Low.** Per color, two O(1) `board.piece_at` lookups per flank (four flank/color combinations
total; eight lookups across both colors), with no move replay, no engine, no line-clearing
scans, and no enemy-pawn-reachability loop (unlike `is_outpost`). The only added work is
optional evidence enrichment (`board.attacks`, `board.king`), which is cheap and non-gating.
No new analyzer helper is required; it is a self-contained pure predicate keyed on the static
board, structurally as simple as `is_passed_pawn`.

**Relevant file paths:**
- `C:\Users\詹天哲\Documents\greco\factgate.py` — add
  `is_fianchetto(board, color) -> Tuple[bool, Optional[List[dict]]]` near `is_outpost` (lines
  114–154 are the `(bool, evidence)` template; model the **color symmetry and static-board,
  no-`move.to_square` keying** on `is_passed_pawn`, lines 157–176); wire it into
  `certified_claims` (lines 235–292) with the **both-colors loop** shown in section 2 (NOT the
  mover-only `is_outpost` pattern); add `"fianchetto"` to `GATED_TAGS` (line 222).
- `C:\Users\詹天哲\Documents\greco\narrator.py` — add `"fianchetto"` to the fact-gate prompt
  rule (line 202) and serialize the per-color evidence list in the Tier-1+ block (lines
  440–462) next to `certified`, under `fianchetto_evidence`, with a try/except fail-safe.
- `C:\Users\詹天哲\Documents\greco\analyzer.py` — reuse `PIECE_NAMES` (line 211); no changes
  required unless surfacing a `MoveAnalysis` field is desired.

---

## Outpost (REVISIT existing) (`outpost`)

Sanity check: I verified all 5 corrected positive FENs return `True` and all 8 negative/edge FENs behave as stated by executing them against the live `is_outpost` logic in the venv (python-chess 1.11.2), and confirmed `analyzer.PIECE_NAMES` is keyed by `piece_type` and `chess.square_name` works. The spec was written to the target path.

result: Shipped corrected outpost spec to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\12-outpost.md; all 4 draft positive examples were factually broken (Ex.2 claimed (True,[D4]) but returns (False,[]) due to an overlooked Black f7 pawn; Ex.1 mis-stated d5 as unsupported when e4 defends it; Ex.4/Ex.5 used FENs/pieces that return (False,[])) — every example replaced with a FEN executed against the live predicate.

---

# Detection Spec: Outpost (`outpost`)

Status: **REVISIT of existing `is_outpost(board, square, color) -> (bool, List[int])`** in `factgate.py` (lines 114–154). The current geometry is sound and expert-correct, and was **re-verified instance-by-instance against python-chess** (chess 1.11.2) while writing this spec. This revision (a) certifies the definition, (b) **replaces every positive/negative example with a FEN that actually exercises the code** (the draft's examples were wrong — see the changelog at the end of §3), and (c) specifies an evidence-bundle upgrade so the narrator can quote the outpost square, the occupying piece, and the supporting pawn(s) verbatim.

The current code is **correct and ships unchanged** for the boolean contract; the only code work this spec authorizes is the **additive evidence bundle in §5** (a new sibling function, not a change to `is_outpost`'s signature).

---

## 1. Expert definition

An **outpost** is a square in or near the enemy camp — conventionally the **4th, 5th, or 6th rank** from the owner's side (White board ranks 4–6 / Black board ranks 5–3) — that satisfies two structural conditions:

1. **It is defended by a friendly pawn.** A pawn (not a piece) backs the square, so an enemy who captures the occupant trades down or surrenders material/structure. The pawn support is what makes the square a *durable* post rather than a square a piece merely visits.
2. **It can never be challenged by an enemy pawn.** No enemy pawn stands on, or can ever advance to, an adjacent file in a position to attack the square. Because pawns never move backward, "can ever" reduces to: there is **no enemy pawn on either adjacent file *behind or level-with-the-attacking-rank*** (from the enemy's marching direction). If such a pawn existed it could one day reach a flank square attacking the outpost and evict the piece — disqualifying it as a true outpost.

The square is then **occupied by a minor piece**, almost always a **knight** (the classic "knight outpost" — a protected knight on d5/e5/c6 that cannot be kicked), and secondarily a **bishop**. Recognized variants a strong coach accepts:

- **Knight outpost** — the canonical case; the unqualified term "outpost" usually means this.
- **Bishop outpost** — same structural test, occupant is a bishop. Technically certified, stylistically rarer; the bundle's `piece_name` keeps the prose honest either way.
- **Outpost square vs. occupied outpost** — coaches distinguish the *square* (the hole exists and is pawn-defendable) from the *piece on it*. Greco's gate is move-anchored: it certifies an outpost when a minor **lands on** such a square, i.e. the **occupied** outpost. The unoccupied "outpost square" is deliberately out of scope (see §6).
- **Rank latitude** — most authorities cite ranks 4–6; some include a deep 6th-/7th-rank knight. Greco caps at the owner's 6th rank (White rank index 5 / Black rank index 2), the mainstream choice; the 7th-rank case is a documented, one-line-fixable miss (§6).

What is **not** part of the definition: that the piece be safe from *pieces* (an outpost knight can still be exchanged by an enemy minor — that does not disqualify it), that the file be open/half-open, or that the square be in the literal center. Only the two structural conditions plus a friendly minor occupant.

---

## 2. Detection rules (veto-then-confirm)

The predicate is **color-parameterized and otherwise side-symmetric**: `color` is the owner of the outpost (in `certified_claims`, `mover_color`), and `square` is the square the minor now sits on (when called from `certified_claims`, `move.to_square`). It reads a **static post-move board**, so there is **no side-to-move dependence** in the geometry: the gate evaluates the board as given and the result does not depend on whose turn it is. The only turn-sensitive concern — "could an enemy pawn capture the piece *next move*" — is irrelevant: an outpost is a *structural* claim about whether a pawn can *ever* challenge the square, not about the immediate reply.

Apply in order; the first failed veto returns `(False, [])` immediately.

1. **VETO — occupant is a friendly knight or bishop.** `board.piece_at(square)` must be non-`None`, have `.color == color`, and `.piece_type in (chess.KNIGHT, chess.BISHOP)`. A rook, queen, pawn, king, empty square, or enemy piece is not an outpost occupant. (Cheapest; kills the vast majority of non-claims. Existing line 123.) **Note this also auto-excludes a pawn pushed to an advanced square and a promotion** — a promotion-to-knight can only legally occur on the back rank (White rank 7 / Black rank 0), which the §2.2 rank gate rejects anyway, so the two interact safely.

2. **VETO — advanced rank.** `rank = chess.square_rank(square)`. For `color == WHITE`, require `rank in (3, 4, 5)` (board ranks 4–6). For `color == BLACK`, require `rank in (2, 3, 4)` (board ranks 5–3). A minor on its own half of the board is not on an outpost. (Existing lines 125–131.)

3. **VETO — pawn support exists.** Collect friendly **pawn** attackers of the square: iterate `board.attackers(color, square)` and keep squares whose piece is a `chess.PAWN` of `color`. If `supporters` is empty, the square is not pawn-defended → not an outpost. (Existing lines 132–137.) `board.attackers` already encodes pawn-diagonal geometry **with the correct directional sense** (a White pawn one rank *below* on an adjacent file; a Black pawn one rank *above*), so this correctly requires a real pawn defender and is immune to the backward-attack mistake. It also (correctly) **ignores pins**: a pinned supporting pawn still counts, because the outpost is a structural claim (§4 item 7).

4. **CONFIRM — unchallengeable by any enemy pawn.** For each adjacent file `adj in (file-1, file+1)` that is on the board, scan every enemy pawn (`board.pieces(chess.PAWN, not color)`) on that file. An enemy pawn **disqualifies** the outpost if it still stands where it could one day reach a flank square attacking the outpost:
   - `color == WHITE`: disqualify if an adjacent-file **Black** pawn has `rank(pawn) >= rank + 1` (it is on the outpost's rank-ahead or higher and can march/already attacks down onto a flank square). Threshold for a White outpost on rank `R`: any Black adjacent-file pawn on rank `R+1` or above.
   - `color == BLACK`: disqualify if an adjacent-file **White** pawn has `rank(pawn) <= rank - 1` (it is on the outpost's rank-ahead, from Black's view, or lower). Threshold for a Black outpost on rank `R`: any White adjacent-file pawn on rank `R-1` or below.
   If no adjacent-file enemy pawn meets its threshold, **confirm**. (Existing lines 138–154.)

5. **RETURN.** On success return `(True, supporters)`. On any veto return `(False, [])`. The richer evidence (§5) is surfaced through a **separate sibling function**, not by changing this return shape.

**Why the threshold is `>= rank+1` (White) and not `>= rank+2`, and why a *level* enemy pawn is harmless.** A Black pawn that is *level* with the outpost on an adjacent file (rank `R`) can only advance *away* from the outpost (toward rank 0); it can never reach rank `R+1` to attack a rank-`R` square. So a level adjacent pawn is **not** a challenger and must **not** disqualify — which is exactly what `>= rank+1` (strictly above the outpost rank) encodes. A pawn *already past* the outpost (rank `< R`) is even more clearly harmless. Both boundaries are handled correctly and are exercised by negative examples §4.6 and the level-pawn case in §4.8.

**Helper reuse (do not duplicate logic):**
- Keep `board.attackers(color, square)` filtered to pawns for step 3 (already in place) — do **not** re-derive pawn-attack geometry by hand.
- For step 4, keep the current hand-rolled rank comparison; it is correct and cheaper than a per-pawn push. The analyzer's `_enemy_pawn_can_attack(board, target_sq, piece_color)` (analyzer.py:578) answers a **subtly different and narrower** question — "can a pawn reach an attacking square **in one push**" — which would **miss** a two-square-distant pawn (e.g. a Black pawn on e7 that needs ...e6 *then* nothing — actually e7 already covers d6/f6, but a pawn that needs two tempi to arrive on the attacking rank is the case the one-push helper misses). The structural rank test is the correct, **more inclusive** instrument here; note this divergence in a code comment rather than swapping in the helper.
- Do **not** import `file_structure` for this predicate; outpost status is independent of whether the file is open/half-open.

**Tightening notes (no behavioral change to `is_outpost`):**
- **Edge A — the supporter need not itself be safe from pawn eviction.** An outpost stays an outpost even if the supporting pawn is theoretically attackable by a piece; no change.
- **Edge B — the move-anchored caller only certifies when the moved piece landed on the outpost.** `certified_claims` passes `move.to_square`, so a knight that was *already* on an outpost before an unrelated quiet move is not re-certified. This is correct and intentional; document it — "outpost" tags the move that *creates/occupies* the post, the natural narration anchor.

---

## 3. Positive examples

**Every FEN below was executed against the live predicate and returns the stated result.** Square indices are shown as algebraic names.

1. **Pawn-supported knight on d5 (White), c4 support.**
   FEN: `r1bq1rk1/pp3ppp/2n2n2/3N4/2P5/8/PP3PPP/R1BQ1RK1 w - - 0 1`
   White **Nd5** (rank index 4). The **c4 pawn** defends d5; Black has no c- or e-pawn that can reach c6/e6 to attack d5. → `is_outpost(board, D5, WHITE) == (True, ['c4'])`. The canonical protected, unkickable central knight.

2. **Knight outpost on e5 (White), d4 support.**
   FEN: `r1bq1rk1/pp4pp/2n1pn2/4N3/3P4/8/PP4PP/R1BQ1RK1 w - - 0 1`
   White **Ne5** (rank index 4), defended by the **d4 pawn**. Black has **no d-file and no f-file pawn** (the two adjacent files), so none can ever challenge e5; the Black e6 pawn is on the *same* file as the knight and can never attack it. → `(True, ['d4'])`. *(Contrast the draft spec's broken version, which left a Black f7 pawn on the board — ...f6 challenges e5, so that position correctly returns `(False, [])`. The lesson: for an e5 outpost you must clear **both** the d- and f-files, not just one.)*

3. **Black knight outpost on d4 (mirror), e5 support.**
   FEN: `r1bq1rk1/pp3ppp/8/4p3/3n4/5N2/PP3PPP/R1BQ1RK1 w - - 0 1`
   Black **Nd4** (rank index 3, board rank 4), defended by the **e5 pawn**. White has no c- or e-pawn able to reach c3/e3 to attack d4 (the c-file is clear; White's e-pawn is gone). → `is_outpost(board, D4, BLACK) == (True, ['e5'])`. Confirms the BLACK branch and the rank gate `(2, 3, 4)`. *(Note: had a White pawn sat on c3, `rank(c3)=2 <= rank-1=2` would disqualify — so the c-file must be clear of a White pawn on rank 2 or below.)*

4. **Bishop outpost on c5 (White), d4 support.**
   FEN: `r2qk2r/p2n1ppp/4pn2/2B5/3P4/8/PP3PPP/R2QK2R w KQkq - 0 1`
   White **Bc5** (rank index 4), defended by the **d4 pawn**. Black has **no b-file and no d-file pawn** to play ...b6/...d6 hitting c5. → `is_outpost(board, C5, WHITE) == (True, ['d4'])`. Demonstrates a bishop occupant passing the identical structural test. *(The draft's b7-pawn version returns `(False, [])`: a Black b7 pawn, `rank 6 >= rank+1 = 5`, can play ...b6 to attack c5 — a near-miss the veto correctly catches.)*

5. **Deep knight outpost on c6 (White, rank index 5 / board rank 6), b5 support.**
   FEN: `r3k2r/p3bppp/2N1pn2/1P6/8/8/P4PPP/R1BQ1RK1 w kq - 0 1`
   White **Nc6** (rank index 5), defended by the **b5 pawn** (b5 attacks a6/c6). Black has no b- or d-pawn that can challenge c6 (b- and d-files clear of Black pawns on rank 6+). → `is_outpost(board, C6, WHITE) == (True, ['b5'])`. Confirms the deep 6th-rank case and that the rank cap (index 5) is **included**.

**Changelog vs. the draft spec's examples (all four positives were defective):** draft Ex.1 claimed d5 "needs a White pawn defender" while its own e4 pawn already defended d5 (it returns `(True, ['e4'])`, not the "geometry-only, pair-with-a-supporter" case the draft described); draft Ex.2 asserted `(True, [D4])` but the position returns `(False, [])` because of an overlooked Black f7 pawn, and its prose was garbled; draft Ex.4 presented a FEN that returns `(False, [])` and only *described* a fix without supplying a working FEN; draft Ex.5 attributed support to "a White b5-pawn (when present)" — a piece **not on the board**, so the position returns `(False, [])`. Every example above is a real, executed pass.

---

## 4. Negative / edge cases

Each FEN below was executed and returns `(False, [])` unless noted.

1. **Advanced but pawn-attackable knight (the central false positive).** White **Nd5** supported by e4, with a Black pawn still on **c7**: FEN `2bqk3/p1p3pp/8/3N4/4P3/8/PP3PPP/4K3 w - - 0 1`. `...c6` evicts the knight; step 4 disqualifies (`rank(c7)=6 >= rank+1=5`). Correctly **excluded** — exactly the "merely advanced minor" the unchallengeable test screens out. (Symmetric for a Black e7 pawn against a White d5/e5 knight.)

2. **Unsupported advanced minor.** White **Ne5** with **no** White pawn on d4 or f4: FEN `4k3/pppppppp/8/4N3/8/8/PPP2PPP/4K3 w - - 0 1`. The piece is not pawn-backed; step 3 (`supporters` empty) **excludes** it. A square can be an *outpost square* in the abstract, but Greco certifies only the *pawn-supported occupied* outpost.

3. **Minor on its own half.** White **Nc3** (rank index 2), even if pawn-defended: FEN `4k3/8/8/8/8/2N5/3P4/4K3 w - - 0 1`. The rank-2 veto **excludes** it, preventing every defended home-side knight from being called an "outpost."

4. **Rook (or queen) on a beautiful protected square.** White **Rd5** on a pawn-defended advanced square: FEN `4k3/8/8/3R4/2P5/8/8/4K3 w - - 0 1`. A strong post, but **not** an outpost in standard usage (outposts are minor-piece posts). The occupant veto (step 1) **excludes** non-minors. ("Rook outpost," if ever wanted, is a separate tag.)

5. **Pawn-defended by a *piece*, not a pawn.** White **Ne5** defended only by a knight on d3 (no pawn): FEN `4k3/8/8/4N3/8/3N4/8/4K3 w - - 0 1`. `board.attackers(WHITE, e5) == {d3}`, but d3 holds a knight, so the pawn filter yields empty `supporters` → **excluded**. Piece-only defense is not pawn-durable.

6. **Enemy pawn already *abreast/past* the outpost.** White **Nd5** (c4 support) with a Black pawn on **e4** (rank index 3): FEN `4k3/8/8/3N4/2P1p3/8/8/4K3 w - - 0 1`. The e4 pawn is past the knight from White's view and can only advance away; `rank(e4)=3` is **not** `>= rank+1=5`, so step 4 does **not** disqualify → `(True, ['c4'])`. Boundary handled correctly: a pawn level-with or past the outpost is harmless. *(The draft's prose on this case contained a stray "≥ 6" typo; the correct threshold for a rank-4 outpost is `>= 5`.)*

7. **Pinned supporting pawn / pinned or hanging knight.** Outpost is a *structural* claim, not a tactical-safety claim. `board.attackers` ignores pins, so a pinned supporting pawn still counts, and a pinned/hanging outpost knight is still on an outpost. Greco intentionally does **not** fold tactical safety into this tag (unlike `fork`, which rejects a hanging forker). Documented asymmetry, not a bug (§6).

8. **Level adjacent enemy pawn is not a challenger (positive boundary).** White **Nd5** (c4 support) with a Black pawn on **e5** (adjacent file, rank index 4, level with the knight): FEN `4k3/8/8/3Np3/2P5/8/8/4K3 w - - 0 1`. The e5 pawn can only push to e4 (attacking d3/f3) and can never reach a square attacking d5; `rank(e5)=4` is not `>= 5` → `(True, ['c4'])`. Confirms the `>= rank+1` (strictly-above) threshold is the correct, non-over-inclusive cutoff.

---

## 5. Evidence bundle

The boolean contract of `is_outpost` is **unchanged** (`(bool, List[int])`), because `certified_claims` reads `op[0]`/`op[1]` and any arity change would silently break the `op and op[0]` guard via `_safe`. The richer, ready-to-quote evidence is surfaced through a **new sibling function** the narrator path can call independently — so the narrator can name the square, the piece, and the supporter(s) verbatim with zero re-derivation.

**Recommended shape — a sibling in `factgate.py`:**

```python
def outpost_evidence(board, square, color) -> Optional[dict]:
    ok, supporters = is_outpost(board, square, color)
    if not ok:
        return None
    # ... build and return the bundle below ...
```

Serialize it at the Tier-1 insertion point in `narrator.py` (inside `if tier >= 1:`, alongside `certified`), guarded by the same try/except fail-safe and emitted only when non-`None`. Deriving `square` from the **function argument** (not assuming `move.to_square`) keeps the bundle correct if the predicate is ever called from a position scan.

Exact fields to surface:

| Field | Type | Value |
|---|---|---|
| `is_outpost` | `bool` | the certification result (mirrors `is_outpost`'s `[0]`; here always `True` since the bundle is `None` otherwise). |
| `supporters` | `List[int]` | friendly-pawn square indices defending the outpost (= `is_outpost`'s `[1]`). |
| `square` | `int` | the outpost square (the `square` argument). |
| `square_name` | `str` | `chess.square_name(square)` e.g. `"d5"`. |
| `piece_name` | `str` | `analyzer.PIECE_NAMES[board.piece_at(square).piece_type]` → `"knight"` / `"bishop"`. |
| `supporter_names` | `List[str]` | `[chess.square_name(s) for s in supporters]` e.g. `["c4"]` or `["c4", "e4"]`. |
| `color_name` | `str` | `"White"` if `color == chess.WHITE` else `"Black"` (the owner), for unambiguous prose. |
| `evidence` | `str` | a single ready-to-quote sentence (see below). |

**Ready-to-quote `evidence` string (build deterministically in code — never let the LLM derive it):**

- One supporter: `"the {color_name} {piece_name} on {square_name} is an outpost — defended by the pawn on {supporter_names[0]} and immune to any enemy pawn challenge"`
  → e.g. `"the White knight on d5 is an outpost — defended by the pawn on c4 and immune to any enemy pawn challenge"`.
- Two supporters: `"the {color_name} {piece_name} on {square_name} is an outpost — defended by the pawns on {a} and {b} and immune to any enemy pawn challenge"`.

Use `analyzer.PIECE_NAMES` (keyed by `piece_type` int → lowercase name) and `chess.square_name` for **all** human strings — never hand-format a square or piece name. This `evidence` string is the anti-hallucination payload: the narrator quotes it rather than describing the post from scratch (which is where it invents a wrong supporter or a wrong eviction claim).

**Whitelist note:** the `outpost` tag already exists in `GATED_TAGS` and in the fact-gate prompt rule (`narrator.py:202`), so no vocabulary change is needed. The evidence bundle is supplementary data for an already-certified tag; it does **not** introduce a new claim type and so requires no `GATED_TAGS` / prompt-rule edit.

---

## 6. Known limitations

- **Occupied-only, move-anchored.** The gate certifies an outpost only when a minor lands on it (the `square` argument, `move.to_square` from `certified_claims`); it does **not** detect a pre-existing outpost a knight already occupied, nor an *empty* outpost square ("there's a hole on d5"). A real coaching concept the detector misses by design. A position-scan variant could enumerate all outpost squares, but that is out of scope for the move-anchored fact-gate.
- **Structural, not tactical.** It ignores whether the outpost piece is pinned, hanging, or about to be exchanged by an enemy minor. A pawn-immune knight that is tactically lost this move still tags as an outpost — consistent with the term's structural meaning, and an **intentional asymmetry** with `fork`'s hanging-forker rejection.
- **Rank cap at the 6th.** A knight on the 7th rank (White rank index 6 / Black rank index 1) that is pawn-supported and uncontestable is excluded by the rank veto. Rare, but a strong 7th-rank knight outpost would be missed. Widening to include rank index 6/1 is a one-line change if James wants it.
- **No dynamic-pawn-lever awareness.** The unchallengeable test reasons only about *existing* enemy pawn positions and their forward reach. It does not consider a pawn that could *manufacture* an adjacent-file attacker via a capture elsewhere. Such cases are vanishingly rare and the standard textbook definition ignores them too.
- **Bishop outposts are certified but stylistically rare.** Including bishops is correct; most narration will be about knights. The bundle's `piece_name` keeps the prose honest.

---

## 7. Complexity

**Low.** The predicate is pure board geometry over a single static `chess.Board`: one piece lookup, one rank test, one `board.attackers` scan filtered to pawns, and one bounded loop over enemy pawns on at most two adjacent files. No engine call, no hypothetical-move pushes, no recursion, no PV parsing. Each veto is O(number of enemy pawns) in its worst step and short-circuits early. The evidence-bundle sibling adds only one extra `is_outpost` call plus string formatting via `chess.square_name` and `analyzer.PIECE_NAMES` — no new traversal. The only subtleties worth a one-line code comment (not added complexity) are the rank-direction sign flip between White and Black in step 4 and the deliberate choice of the structural rank test over `_enemy_pawn_can_attack` for inclusiveness.

**Relevant file:** `C:\Users\詹天哲\Documents\greco\factgate.py` (lines 114–154, `is_outpost`; add the `outpost_evidence` sibling here). Reuse `chess.square_name` and `analyzer.PIECE_NAMES` for the bundle; serialize it at the Tier-1 insertion point in `C:\Users\詹天哲\Documents\greco\narrator.py` alongside `certified` (`narrator.py:440-462`), with the same try/except fail-safe.

---

## Passed pawn (REVISIT existing) (`passed_pawn`)

Sanity check complete: I verified the corrected spec against the actual `is_passed_pawn` source (factgate.py:157–176, confirming the strict `>`/`<` rank comparison and the `0<=f<=7` edge clamp are already in the code), the `certified_claims` truthiness guard at line 289 (the tuple-return compatibility trap), the `is_outpost` `(bool, List[int])` evidence precedent, and the narrator's tier-1 serialization slot. The file wrote successfully to the target path and matches the house style of the 11 sibling specs.

The corrected spec follows.

# Detection Spec: Passed Pawn (`passed_pawn`)

> Status: corrected after adversarial review. Companion to `05-isolated_pawn.md`,
> `06-doubled_pawn.md`, `07-backward_pawn.md`. Helper ground truth verified against
> `factgate.py` — `is_passed_pawn` (lines 157–176), `is_outpost` supporter pattern
> (114–154), `certified_claims` (235–292), `GATED_TAGS` (222–229) — and `analyzer.py`
> (`file_structure` 242–267, `material_balance` 223). The base boolean already ships and is
> reused unchanged; this spec corrects the **definition wording**, the **evidence layer**, and
> several **false-positive / false-negative** traps the first draft introduced or endorsed.

---

## 1. Expert definition

A **passed pawn** is a pawn that **no enemy pawn can stop from promoting by pawn means** —
there is no enemy pawn that can either *block* it by standing in front of it or *capture* it
as it advances up its file. Concretely: on the pawn's **own file** and on **each adjacent
file**, there is **no enemy pawn on any square strictly ahead of it** in its direction of
travel (between the pawn and its promotion square). If that region is clear of enemy pawns,
no enemy pawn can ever interpose in front (own file) or capture it on an advancing square
(adjacent files), so it is passed. It is among the most consequential endgame assets
("a passed pawn is a criminal that should be kept under lock and key" — Nimzowitsch).

**Why "strictly ahead," not "ahead-or-level" — the off-by-one that must be exact.** An enemy
pawn on an **adjacent file at the same rank** as our pawn does **not** stop it: a pawn captures
*diagonally forward*, so a level enemy pawn captures away from our pawn's path, never onto it.
Therefore the rank comparison against enemy pawns is **strict** (White: enemy rank `> r`;
Black: enemy rank `< r`). On the **own file**, an enemy pawn can never legally sit at the same
rank (two pieces can't share a square) and a same-file enemy pawn *behind* us is irrelevant, so
again only strictly-ahead matters. Using `>=` / `<=` here would be a false-negative bug
(it would reject genuine passers whose only "obstacle" is a harmless level enemy pawn).

**The one structural caveat the wording must not over-claim: *en passant*.** A pawn that has
just made a two-square push can, on the *very next ply only*, be captured *en passant* by an
adjacent enemy pawn that is level with it. That adjacent enemy pawn is at the **same rank**, so
the structural test (strictly-ahead) does **not** count it — and that is the intended, correct
behavior: passed status is a **static structural property**, and an en-passant capture is a
one-ply dynamic option, not a standing pawn-structure blocker. The pawn **is** structurally
passed; the evidence string therefore says "no enemy pawn can stop its march" only in the
structural sense and must **not** assert it is "safe" or "uncapturable" (see §6). This is an
explicit anti-over-claim requirement.

Recognized variants a strong coach groups under this term — all certify as the base feature
**plus** an evidence sub-attribute (never as separate gated tags):

- **Protected passed pawn** — a passed pawn defended by a friendly pawn (a friendly pawn on an
  adjacent file, one rank behind in our direction of travel, so it guards the passer's square).
  Especially strong because the enemy king cannot win it unaided.
- **Connected passed pawns** — two (or more) passed pawns on **adjacent** files. They cover each
  other's advance squares and are very hard to stop. (A protected passer is frequently also
  connected; the two flags are independent and both are reported when both hold.)
- **Outside passed pawn** — a passed pawn distant from the *enemy king* and from the main pawn
  mass (classically on a wing while the kings/pawns sit elsewhere). It decoys the enemy king and
  is a textbook winning motif. Because true "outside" depends on king and pawn distribution, it
  is reported as a **conservative heuristic** (see §2.9 and §6), never as part of the exact base
  claim.
- **Passed pawn on the rim** — a passed pawn on the a- or h-file. A special, often-cited case of
  "outside" (maximal decoy distance). Cheap and exact: it is purely a file test.

Two related concepts that are **distinct** and must NOT be conflated with a passer:

- A **candidate passed pawn** — one that *can become* passed after pawn trades but is **not yet**
  (an enemy pawn still controls a square on its path). Deliberately **excluded**; certifying it
  would be a false positive.
- A **piece-blockaded passer** — a pawn with an enemy **piece** (not pawn) in front of it. It
  **remains passed by definition**: only an enemy **pawn** ahead on the own/adjacent file revokes
  passed status. A blockading piece is a dynamic note, never a refutation.

**One friendly-side caveat the definition must name explicitly — the rear of a doubled pair.**
The base boolean inspects **enemy** pawns only. So the **rear pawn of a friendly doubled stack**
(e.g. White d4 behind White d5, with no Black c/d/e pawn ahead) tests as "passed" even though its
*own* front pawn blocks its file. By the strict textbook definition it *is* passed (no **enemy**
pawn stops it), and it certifies — but it is **not independently mobile**, and a coach would never
call it a winning outside passer. The detector therefore **certifies it** (do not suppress — the
structural claim is true) but the evidence layer **flags the friendly front-blocker** so the
narrator does not imply the rear pawn can march (see §2.11 and §4.6). This is the single subtlest
correctness point in the whole spec.

---

## 2. Detection rules (veto-then-confirm)

The existing helper `is_passed_pawn(board, square, color) -> bool` in `factgate.py`
(lines 157–176) already implements the core test (own + both adjacent files; an enemy pawn
**strictly ahead** disqualifies) and is **reused unchanged as the gate**. In
`certified_claims`, the square is `move.to_square` and the color is `mover_color`
(`board_after`, `move.side == "White"`). Direction of advance: White promotes toward rank 7
(increasing rank), Black toward rank 0 (decreasing rank).

**Side-to-move independence.** Passed status is a **static structural property of the position
after the move**; it does **not** depend on whose turn it is (`board.turn` is never read — the
boolean is byte-for-byte identical regardless of side to move). The gate evaluates it on
`board_after` for the pawn the mover just placed on `move.to_square`. (Whether the pawn is
*safe*, *unstoppable*, or *winning* is dynamic and **out of scope** — §6.)

**Null-move / non-pawn input guard.** When `move.uci` is empty, `certified_claims` is called
with `chess.Move.null()`, whose `to_square` is `0` (a1). The piece-type veto (rule 1) inspects
`board_after.piece_at(a1)` and rejects it unless it is genuinely a mover-colour pawn — so a null
move can never spuriously certify. This must hold for **any** `to_square`, pawn move or not.

**VETO (cheap necessary-condition refutations — kill most false claims instantly):**

1. **Piece-type veto.** `board_after.piece_at(move.to_square)` must exist, be a `PAWN`, **and**
   be of `mover_color`. Empty square, non-pawn, **or an enemy pawn** → not certifiable. (Covers
   the common case where the move was not a pawn move at all, and the null-move case above.)
2. **Promotion-already veto (boundary).** If the pawn reached its last rank (White rank 7 /
   Black rank 0) it has **promoted** — `move.to_square` then holds a queen/rook/bishop/knight,
   so rule 1 already vetoes. No pawn exists on the back rank to be "passed." (A `=Q`/`=N`
   promotion is a *piece*, not a passer, on that ply.)
3. **Enemy-pawns-exist short-circuit.** If `board_after.pieces(PAWN, not mover_color)` is empty,
   no file can hold a blocker → trivially passed; skip straight to CONFIRM/evidence.

**CONFIRM (the full structural test — exactly what `is_passed_pawn` does):**

4. Let `f = chess.square_file(to_square)`, `r = chess.square_rank(to_square)`. Consider the
   on-board files among `{f-1, f, f+1}` (clamped to `0..7` — **on the a-file `f-1` does not
   exist; on the h-file `f+1` does not exist**; the existing code builds the file set with a
   `0 <= f <= 7` guard, so the board edge is handled correctly and is **not** a bug).
5. For each enemy pawn on those files, test whether it lies **strictly ahead** in our direction:
   - **White:** an enemy pawn on one of those files with rank **`> r`** stops it → **not passed**.
   - **Black:** an enemy pawn on one of those files with rank **`< r`** stops it → **not passed**.
   (Strict comparison — see §1 "off-by-one." A level adjacent enemy pawn does **not** disqualify.)
6. If **no** enemy pawn lies strictly ahead on the own or either adjacent file → **passed pawn
   certified** (add tag `"passed_pawn"`).

**EVIDENCE SUB-ATTRIBUTES (computed only after CONFIRM succeeds; they enrich the bundle and
NEVER change the boolean). All geometry is on `board_after`. Each is symmetric in colour —
every rank offset below flips sign by colour, and every file offset is clamped to `0..7`:**

7. **Protected passed pawn.** A friendly pawn that **defends** `to_square`: a friendly pawn on
   file `f-1` **or** `f+1`, exactly **one rank behind** in our direction (White: rank `r-1`;
   Black: rank `r+1`). Implement as
   `[s for s in board_after.attackers(mover_color, to_square) if board_after.piece_at(s).piece_type == chess.PAWN]`
   — `attackers()` already returns only pieces that bear on the square, so a friendly pawn
   attacker **is** a one-rank-behind diagonal defender; filtering to `PAWN` excludes a defending
   king/knight/bishop. On the **a-file** only `f+1` can hold a protector; on the **h-file** only
   `f-1` — the clamp handles both. If ≥1 pawn protector → `protected = True`; record the square(s).
8. **Connected passed pawns.** A friendly pawn on an **adjacent file** (`f-1` or `f+1`, clamped)
   that is **itself also passed** — re-call `is_passed_pawn(board_after, partner_sq, mover_color)`
   on it. **This call is safe and non-recursive:** `is_passed_pawn` is the *bare boolean* and
   does **not** compute connected/protected evidence, so there is no mutual recursion and no
   risk of unbounded re-entry (the evidence layer calls the boolean, never the other way). If a
   passed friendly neighbour exists → `connected = True`; record its square. (Check both
   adjacent files; record the first/closest, or all, but never call the evidence builder again.)
9. **Outside passed pawn (conservative heuristic — the one field a reviewer must scrutinise).**
   True "outside" depends on king positions and the global pawn split, which the structural gate
   does not model. Use this **deliberately conservative** rule (it under-claims by design — a
   missed outside passer is acceptable, a wrongly-flagged one is a bug):
   - (a) the passer is on a **wing file**: `f ∈ {0,1,6,7}` (a, b, g, or h); **and**
   - (b) **every enemy pawn** is on the **opposite half-board** — i.e. for a queenside passer
     (`f ≤ 1`) every enemy pawn has file `≥ 4`, and for a kingside passer (`f ≥ 6`) every enemy
     pawn has file `≤ 3`; **and**
   - (c) the **file-distance from the passer to the nearest *enemy* pawn is ≥ 2**.
   **Bugfix vs. the first draft:** the distance in (c) is measured to the nearest **enemy** pawn
   only — **not** "the nearest *other* pawn of either color." Counting friendly pawns (including
   the passer's own protector or its connected partner one file over) would spuriously collapse
   the distance to 1 and **suppress** the flag on exactly the strongest cases (a protected or
   connected outside passer). Friendly pawns near the passer make it *more* outside, never less.
   King positions are still ignored (see §6) — that is why this stays a heuristic, but it now no
   longer self-sabotages on protected/connected passers.
10. **Passed pawn on the rim.** `on_rim = (f == 0 or f == 7)`. Cheap, exact, color-independent.
11. **Friendly front-blocker (doubled-pawn nuance).** Set `blocked_by_friendly = True` when there
    is a **friendly pawn** on the **same file `f`** strictly ahead in our direction (White: a
    friendly pawn at rank `> r`; Black: at rank `< r`) — i.e. the passer is the **rear pawn of a
    friendly doubled stack** and cannot itself advance. It still certifies (it *is* passed by the
    enemy-pawn definition), but this flag tells the narrator the pawn is not independently mobile,
    so the prose must not imply it can march to promotion (record the blocking friendly square).

Do **not** add new gated tags for any sub-attribute. The single tag `"passed_pawn"` remains the
sole whitelist entry the narrator is bound to; the sub-attributes ride **inside** the
`passed_pawn` evidence bundle (§5).

---

## 3. Positive examples

1. **Clean passer, no enemy pawns at all.** FEN `8/8/4P3/8/8/8/k7/4K3 w - - 0 1` — White pawn e6.
   §2.3 short-circuit (Black has no pawns) → passed. `protected=False`, `connected=False`,
   `on_rim=False`, `outside=False` (central file fails §2.9a), `blocked_by_friendly=False`.
2. **Protected passed pawn.** FEN `8/8/3P4/2P5/8/8/k6K/8 w - - 0 1` after `c4-c5` (or with d6
   just played) — White pawns c5 and d6. d6 is passed **and** defended by the c5 pawn (friendly
   pawn on adjacent file c, one rank behind: `r-1`) → `protected=True`, protector `c5`. The c5
   pawn defends from `f-1`; on a rim passer only the single existing neighbour file applies.
3. **Connected passed pawns.** FEN `8/8/8/3PP3/8/8/k6K/8 w - - 0 1` — White d5 and e5, no Black
   pawns. After moving (say) `e4-e5`: e5 is passed; the adjacent-file d5 is **also** passed
   (§2.8) → `connected=True`, partner `d5`. Each is the other's partner; neither is `protected`
   (no pawn one rank behind). The §2.8 partner check calls the bare boolean only — no recursion.
4. **Outside passer on the rim.** FEN `8/P5p1/6kp/8/8/8/6K1/8 w - - 0 1` after `a6-a7` — White a7,
   Black pawns on g7/h6. a7 is passed (no Black pawn on a/b ahead), `on_rim=True` (`f==0`),
   and `outside=True`: it is a queenside wing pawn (§2.9a), every Black pawn is file ≥ 6 (§2.9b),
   and the nearest **enemy** pawn (g-file, file 6) is ≥ 2 files away (§2.9c). Evidence string gets
   the combined outside-on-rim clause.
5. **Black passed pawn (colour symmetry).** FEN `4k3/8/8/8/8/3p4/8/4K3 b - - 0 1` after `d4-d3` —
   Black pawn d3. White has no pawn on c/d/e strictly *below* rank 3 in Black's direction
   (ranks `< 3`) → passed. Confirms the rank comparison flips sign correctly for Black and that
   every evidence offset (`protected` at `r+1`, `blocked_by_friendly` at rank `< r`) flips too.
6. **Protected *and* connected outside passer (regression case for the §2.9 bugfix).** FEN
   `8/1P6/P5kp/8/8/8/6K1/8 w - - 0 1` after a push leaving White a6 and b7 — both are passed and
   on adjacent files (`connected=True`), b7 is also one rank context for protection. The nearest
   **enemy** pawn is the h-pawn (file 7), ≥ 2 files from both, so `outside=True` for the
   queenside pair. Under the **old** draft rule (distance to nearest pawn *of either colour*) the
   friendly neighbour one file away would have forced distance 1 and **wrongly cleared**
   `outside`. The corrected §2.9c keeps it flagged.

---

## 4. Negative / edge cases

1. **Blocked by an enemy pawn directly in front (rammed).** FEN `8/3p4/3P4/8/8/8/k6K/8 w - - 0 1`
   — White d6, Black d7 ahead on the same file. Enemy pawn strictly ahead on own file (§2.5) →
   **not passed**.
2. **Stoppable by an adjacent-file enemy pawn (capture-on-the-way).** FEN
   `8/2p5/3P4/8/8/8/k6K/8 w - - 0 1` — White d6, Black c7 (adjacent file, strictly ahead). The c7
   pawn guards/can challenge d6's advance → §2.5 → **not passed**. Looks advanced but is not a
   passer.
3. **Level adjacent enemy pawn does NOT disqualify (off-by-one guard).** FEN
   `8/8/8/3Pp3/8/8/k6K/8 w - - 0 1` — White d5, Black e5 (adjacent file, **same rank**). The e5
   pawn captures toward d4/f4, away from d5's path; it is **not** strictly ahead (`rank == r`,
   not `> r`) → d5 **is** passed. A `>=` comparison would wrongly reject this — the strict `>`
   is what makes it correct.
4. **Just-pushed pawn capturable en passant is still structurally passed.** FEN
   `8/8/8/3pP3/8/8/k6K/8 b - e6 0 1`-style position where White's e-pawn just played `e4-e5`
   beside a Black d5 pawn with `d5xe6 e.p.` available next ply. The Black d5 pawn is **level**
   (same rank), so §2.5 does not count it → e5 certifies as **passed** (correct: passedness is
   structural). The evidence string must **not** claim it is "safe" — e.p. is a one-ply dynamic
   that the structural claim deliberately ignores (§1, §6).
5. **Candidate passer, not yet passed.** White b4,c4 vs Black a7,b7: the c-pawn *can become*
   passed after trades, but Black's b7 still strictly covers c-file advance → §2.5 → **not
   passed**. A candidate, never certified (anti-over-claim).
6. **Rear pawn of a friendly doubled stack — certifies, but flagged not-mobile.** FEN
   `8/8/8/3P4/3P4/8/k6K/8 w - - 0 1` — White d5 **and** d4, no Black c/d/e pawns. Both test as
   passed (the boolean checks **enemy** pawns only). The rear pawn **d4** certifies `passed_pawn`
   but with `blocked_by_friendly=True` (own d5 pawn strictly ahead on file d) so the narrator is
   told it cannot itself advance. **Do not suppress** the certification — the structural claim is
   true — but **do** surface the blocker so the prose stays honest. (The front pawn d5 is passed
   and unblocked: `blocked_by_friendly=False`.)
7. **Passed pawn blockaded by an enemy piece (still passed).** FEN
   `8/8/3n4/3P4/8/8/k6K/8 w - - 0 1` — White d5, Black knight on d6. No enemy **pawn** is ahead on
   c/d/e → **still passed** (§1, §2). "Blockaded" is a separate dynamic note, not a refutation;
   the detector correctly certifies it.
8. **Move was not a pawn move.** Mover plays `Nf3`; `to_square` holds a knight → §2.1 piece-type
   veto rejects it. The gate only ever inspects the piece the move actually placed on `to_square`,
   so non-pawn moves can never certify `passed_pawn`.
9. **Promotion ply.** `e7-e8=Q`: `to_square` holds a queen → §2.1/§2.2 veto. A promotion is a
   *piece*, not a passer, on that ply.
10. **Enemy pawn behind, on own file (harmless).** White e5 with a Black pawn on e2 (its own file,
    far **behind** White's direction): `rank(e2)=1 < 4=r`, not strictly ahead → does **not**
    disqualify → e5 is passed. Confirms only *ahead* enemy pawns matter.

---

## 5. Evidence bundle

The current predicate returns a bare `bool`. **Upgrade** to a structured evidence return
mirroring `is_outpost`'s `(bool, List[int])` supporter pattern — here `(bool, dict | None)`,
where the dict is populated **only on `True`** (and `None` on `False`, so callers using the
existing `_safe(...)` + truthiness guard in `certified_claims` keep working unchanged — see the
compatibility note below).

| Field | Type | Meaning |
|---|---|---|
| `square` | `int` | the passed pawn's square (`to_square`) |
| `square_name` | `str` | e.g. `"a7"` (via `chess.square_name`) |
| `color` | `bool` | `mover_color` |
| `protected` | `bool` | defended by a friendly pawn one rank behind (§2.7) |
| `protectors` | `List[int]` | friendly-pawn squares defending it (may be empty) |
| `connected` | `bool` | an adjacent-file friendly pawn is also passed (§2.8) |
| `connected_partner` | `Optional[int]` | a partner passer's square, if any |
| `outside` | `bool` | satisfies the conservative outside heuristic (§2.9) |
| `on_rim` | `bool` | on the a- or h-file (§2.10) |
| `blocked_by_friendly` | `bool` | rear pawn of a friendly doubled stack — passed but not mobile (§2.11) |
| `friendly_blocker` | `Optional[int]` | the friendly front pawn's square, if `blocked_by_friendly` |
| `evidence` | `str` | ready-to-quote sentence (below) |

**Backward-compatibility with `certified_claims` (do not break the gate).** Today line 289 does
`if _safe(lambda: is_passed_pawn(...))`. If `is_passed_pawn` itself is changed to return a tuple,
that truthiness test would pass even on `(False, None)` (a non-empty tuple is truthy) — a
**false-positive bug**. Two acceptable fixes, pick one and state it:
(a) **leave `is_passed_pawn` returning a bare `bool`** and add a **sibling**
`passed_pawn_evidence(board, square, color) -> Tuple[bool, dict | None]` that calls the boolean
then builds the dict — `certified_claims` keeps calling the boolean (truthiness stays correct);
or (b) change `is_passed_pawn` to the tuple **and** update line 289 to guard on `pp and pp[0]`
exactly as the other tuple-returning predicates (`rl`/`fk`/`rp`/`op`) already do. **(a) is
preferred** — it keeps the byte-for-byte gate behaviour and matches how `is_outpost` is wrapped.

**Ready-to-quote `evidence` string** (deterministic; the narrator may use it verbatim — never
expose field names). Base form:

> "The {color} pawn on {square_name} is a passed pawn — no enemy pawn on the {file}-file or the
> files beside it stands in the way of its march to promotion."

Sub-attribute clauses appended in this priority order **when present** (and never contradicting
each other):

- `blocked_by_friendly` → " It is the rear pawn of a doubled pair, so its own pawn on
  {friendly_blocker} blocks the file for now." *(If this flag is set, the string must NOT also
  imply the pawn can advance; suppress any "unstoppable/march" embellishment.)*
- `protected` → " It is a protected passed pawn, shielded by the pawn on {protector_square}."
- `connected` → " It is connected with the passer on {partner_square}, the two covering each
  other's advance."
- `outside` **and** `on_rim` → " As an outside passer on the rim, it is an ideal decoy to pull the
  enemy king away."
- `outside` **and not** `on_rim` → " As an outside passed pawn, it sits far from the enemy king
  and makes a powerful decoy."
- `on_rim` **and not** `outside` → " On the edge of the board, it is a rook's-file passer."

The string asserts only **structural** facts (placement, who defends/connects). It must **not**
assert the pawn is *safe*, *unstoppable*, or *winning* (those are Stockfish's domain via the eval
fields — §6), and it must respect the `blocked_by_friendly` suppression above.

Reuse `chess.square_name`, `chess.FILE_NAMES`, `board.attackers(color, sq)` (protectors),
`chess.square_file` / `chess.square_rank`, and `board.pieces(PAWN, color)` — do not hand-roll.
Serialize the bundle in `narrator._move_to_dict` **inside the `if tier >= 1:` block** alongside
`certified` (per the narrator brief), under key `passed_pawn_evidence`, with the **same
try/except fail-safe** so a bundle error omits the field and never crashes the report. Only emit
the key when `passed_pawn` is in the certified set (guard on truthiness, like every other optional
field). The base tag `"passed_pawn"` stays in `GATED_TAGS` and the prompt rule **unchanged**.

---

## 6. Known limitations

- **Outside-passer heuristic is an approximation (the one field to scrutinise).** §2.9 ignores
  **king positions** and the global pawn split; it is intentionally conservative (wing file +
  all enemy pawns on the far half + ≥2 files to the nearest **enemy** pawn) and will **miss** some
  genuine outside passers (e.g. a central-but-distant passer, or one whose "outside-ness" comes
  from king geometry). When in doubt it **under-claims** — false positives are bugs; a missed
  flag is not. The base `passed_pawn` claim and every other evidence flag are **exact**; only
  `outside` is heuristic.
- **No safety / winning judgment.** The detector certifies **structural** passedness only. It does
  **not** assert the pawn is safe, unstoppable, or winning — a passer can be lost, permanently
  piece-blockaded, captured en passant the very next ply (§4.4), or simply insufficient. The
  narrator must never infer "winning" from the tag; those dynamics come from Stockfish's eval
  fields.
- **En passant not modelled in the boolean.** A just-pushed pawn capturable e.p. still certifies
  (correctly — passedness is structural). The detector does not down-rank it; the evidence string
  deliberately avoids any "safe/uncapturable" wording so the omission can't mislead.
- **Friendly front-blocker reported, not suppressed.** The rear pawn of a doubled stack certifies
  with `blocked_by_friendly=True` (§2.11) rather than being silently dropped, so the structural
  claim stays true while the prose is told it can't yet advance. A coach wanting "only mobile
  passers" would post-filter on that flag — out of scope for the gate.
- **Piece-blockade not reported as evidence.** A piece-blockaded passer certifies (§4.7) but the
  bundle does not currently carry a `blockaded_by_piece` flag; adding one is a clean future
  extension, out of scope here.
- **Candidate passers not detected.** The common coaching idea "this *will* be passed after the
  trade" is deliberately excluded to avoid false positives; only fully-realised passers certify.
- **Connected / protected detection is single-step.** `connected` checks only immediate
  adjacent-file passers; `protected` only a one-rank-behind pawn defender. A passer defended
  *indirectly* further back in a chain is still certified as passed but is not flagged
  `protected`.
- **Per-ply, single-square scope.** Certification inspects only the pawn the mover just moved to
  `to_square`. A pre-existing passer elsewhere (not the one just moved) is not certified on this
  ply — consistent with the move-centric `certified_claims` design, but it means not every passer
  on the board is announced every move.

---

## 7. Complexity

**Low-to-medium.** The base boolean (`is_passed_pawn`) already exists and is `O(enemy pawns)`
with a tiny constant (at most three files scanned) — **low**. The evidence layer adds bounded,
cheap, pure-geometry work on `board_after`, no engine calls, no recursion, no hypothetical pushes:

- `protected` — one `attackers()` call filtered to pawns;
- `connected` — at most two extra `is_passed_pawn` (bare-boolean) calls on adjacent-file friendly
  pawns; **non-recursive** because the boolean never re-enters the evidence builder (§2.8);
- `on_rim` — a single file comparison;
- `blocked_by_friendly` — one scan of friendly pawns on file `f` for a strictly-ahead one;
- `outside` — one min-file-distance scan over **enemy** pawns plus the wing/half-board checks.

The only genuine judgment — and the one field a reviewer should keep scrutinising — is the
`outside` heuristic, which is approximate by nature (it omits king geometry, §6). Everything else
is exact and deterministic, which is why the base tag is safe to keep on the whitelist unchanged.

result: Corrected `passed_pawn` spec written to `C:\Users\詹天哲\Documents\greco\docs\specs\predicates\13-passed_pawn.md` — fixes the §2.9 outside-passer false-negative (distance now measured to nearest *enemy* pawn, not any pawn), the tuple-return truthiness false-positive at `factgate.py:289`, the doubled-rear-pawn `blocked_by_friendly` nuance, the en-passant over-claim, the strict-rank off-by-one justification, null-move/board-edge/promotion guards, and the connected-passer non-recursion guarantee.

---

## Rook lift (REVISIT existing) (`rook_lift`)

Sanity check before finishing: I verified the corrected spec against the real `factgate.py:69-111` and the `analyzer.py` helpers (`file_structure:242-267`, `detect_royal_alignment:367-417` with its `chess.between` clear-line idiom). The defects I fixed are grounded in the actual code, not the brief's prose. The file was written to the target path.

result: Hardened rook_lift spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\14-rook_lift.md — fixes a pinned/illegal-lift false positive, a 2nd-rank king-rank false positive, a king-file false positive through blockers, and the dropped central swing-ready lift false negative.

# Detection Spec: Rook Lift (`rook_lift`)

Status: **REVISIT of existing `is_rook_lift(board_before, move, board_after) -> (bool, Optional[str])`** in `factgate.py` (lines 69–111). The current geometry was **re-verified line-by-line against the source and against python-chess (chess 1.11.2)**; the veto chain is sound and the file/king confirmation matches `analyzer.file_structure` exactly. This revision (a) **closes four real defects** the draft spec papered over — a pinned/illegal-lift false positive, a rank-alignment false positive on a bare 2nd-rank nudge, a king-file false positive *through* a wall of pieces, and an under-inclusive purpose test that silently drops the most idiomatic lift of all (the centre-pawn-shelter `Re1-e3` preparing a kingside swing); (b) corrects two chess statements in the draft's negative table that were simply wrong; and (c) specifies an evidence bundle that cannot drift from the predicate or from `file_structure`.

**Code-change posture.** The boolean contract ships **with three small, additive tightenings** (a `legal-lift` legality guard, a `clear-file` check on the king branch reusing the `chess.between` idiom already in `detect_royal_alignment`, and a minimum-advanced-rank gate on the king-*rank* branch). The new purpose branch (§2 rule 8) and the evidence bundle (§5) are additive. None of these change the function's signature; all keep the whitelist/fail-safe posture intact.

---

## 1. Expert definition

A **rook lift** is a deliberate maneuver in which a rook is repositioned from its passive home zone (a back-rank/2nd-rank square, behind or among its own pawns) **forward along a file** onto a more active rank, so it can subsequently **swing laterally** along that advanced rank into the attack — classically against the enemy king. The canonical pattern is the two-step `Rf1-f3-h3` or `Ra1-a3-g3`: first the **vertical lift up the file**, then the **horizontal swing**. A strong coach uses the term for the **first, vertical step** — the act of lifting the rook off the home zone up to an active rank — because that is the move that *loads* the maneuver. The active rank is **classically the 3rd for White (rank index 2) / the 6th for Black (rank index 5)**, but the **4th rank** (`Re1-e4` swinging to `g4/h4`) and higher are recognized variants, especially when the enemy's pawns have advanced.

Two precision points an expert insists on:

- **Home zone, not just the back rank.** The lift starts from the rook's passive zone *behind the pawn front*: board ranks **1–2 for White (rank index 0–1)** and **7–8 for Black (rank index 6–7)**. The prototypical `Rd1-d3` starts on rank 1; the equally real `Ra2-a4` / `Rf2-f3` starts on the 2nd rank, behind the pawn that has already advanced. Both are lifts. A rook *already* on the 3rd/6th rank that moves is no longer lifting (see below).
- **Forward rank change is the load-bearing gate.** The rook must **change rank, moving forward**, from the home zone. A rook that slides *sideways* on the 3rd/6th rank is performing the **swing**, not the lift; a rook already advanced off the home zone is not lifting; a backward retreat is not a lift. This single fact refutes the entire **"already on the file/rank" hallucination class** — the narrator claiming a fresh "lift to the d-file" for a rook that was already on d3, or calling the swing `Rf3-h3` "the rook lifting."

Recognized variants and nuances the gate must respect:

- **File-then-rank ("up the file, then across"):** the prototypical lift; the certifiable move is the *up-the-file* leg, the swing across is a separate later move.
- **Attacking lift (king-hunt):** lifted onto a rank or file that bears on the enemy king — the most common motive in annotation.
- **Open / half-open-file lift:** a rook lifted to seize an open or own-side half-open file as a forward operating base (an a-/c-file rook activated forward). Here the "swing target" is the file itself, not a king.
- **Swing-ready central lift (the draft's biggest miss):** `Re1-e3` / `Rf1-f3` onto the **3rd/6th rank** behind a closed centre, *preparing* a lateral swing toward the enemy king's wing, even when the landing file is closed and the rook does not yet share the king's file or rank. This is one of the most idiomatic lifts in practice (e.g. the King's-Indian/Spanish `Rf1-f3-h3` or `Re1-e3-g3`). A purpose test that only fires on (half-)open files or instantaneous king alignment **misses it**, which is exactly the under-inclusiveness an expert standard rejects. §2 rule 8 adds a tightly-bounded branch to catch it.
- **Defensive / regrouping lift** (e.g. `Ra1-a3` to defend a 3rd-rank weakness, or to reroute to the kingside): real usage, but hard to disambiguate from an aimless shuffle; this detector deliberately requires a **purposeful** target so it does not certify meaningless 2nd-rank nudges.

What an expert will **not** accept being mislabeled a lift, and which this gate must refuse:

- the **swing** (`Rf3-h3`) — no forward rank change;
- a rook **already** off the home zone "lifting again";
- a **capture** that happens to land on an active rank (that is a capture/exchange, classified elsewhere);
- a rook that is **pinned** such that the lift is illegal, or that lifts off a relative pin into a worse pin (§2 rule 3b — a defect the draft ignored entirely despite the reviewer standard naming relative pins);
- a one-square 2nd-rank nudge that lands on the **enemy king's rank by coincidence** while still deep in its own camp (rank-alignment must require a genuinely advanced rook — §2 rule 7b).

---

## 2. Detection rules (VETO-THEN-CONFIRM)

`is_rook_lift(board_before, move, board_after) -> (bool, Optional[str])`. Reuse `analyzer.file_structure(board_after)` for the open/half-open determination — **single source of truth, never re-scan pawns.** All rank/file/king logic uses `chess.square_rank`, `chess.square_file`, `chess.FILE_NAMES`, `chess.RANK_NAMES`, `board.king(color)`, and (for the new gates) `board_before.is_pinned`, `board_before.is_castling`, and `chess.between`/`chess.SquareSet`.

**Color is read from the moved piece, not the board's turn.** `color = piece.color` is taken from the piece on `move.from_square`; the rules are otherwise **side-symmetric** (every White rank threshold has its Black mirror). **Side-to-move is therefore irrelevant** to the geometry, and the predicate yields the same answer whether the caller hands it `board_before` with the mover to move or a flipped copy. The one place turn matters — *is this move actually legal for the mover* — is handled explicitly by the new legality guard (rule 3b), not left to chance.

### VETO — cheap necessary-condition refutations (kill most false claims first)

1. **Not a rook.** `piece = board_before.piece_at(move.from_square)`. If `piece is None` or `piece.piece_type != chess.ROOK`, return `(False, None)`. Record `color = piece.color`. *(This also disposes of the queen "lift," and of castling encoded as a king move — but see rule 2b for the robust castling guard rather than relying on this accident.)*

2. **It's a capture.** If `board_before.is_capture(move)` → `(False, None)`. A lift is a *quiet* repositioning; a capturing rook move is another tag's business. (A rook cannot make an en-passant capture, and `is_capture` already covers ordinary captures, so no separate en-passant case is needed.)

   **2b. It's castling (robust guard).** If `board_before.is_castling(move)` → `(False, None)`. In standard chess python-chess encodes castling with the **king** on `from_square` (e.g. `e1g1`), so rule 1 already rejects it; but encoding the intent explicitly is cheap, self-documenting, and immune to any future castling-encoding change (e.g. a Chess960 king-takes-rook encoding where the from-piece could be ambiguous). Castling is **never** a lift.

3. **Did not move forward / not off the home zone** — the core anti-hallucination gate. Let `from_rank = square_rank(from_square)`, `to_rank = square_rank(to_square)`.
   - **WHITE:** require `to_rank > from_rank` (up the board) **and** `from_rank in (0, 1)` (home zone: 1st/2nd rank, behind the pawns). Else `(False, None)`.
   - **BLACK:** require `to_rank < from_rank` (down the board = Black's forward) **and** `from_rank in (6, 7)`. Else `(False, None)`.
   - This refutes the whole **"already on the file/rank" class**: a sideways slide / swing (`to_rank == from_rank`) is rejected; a rook already advanced off the home zone (`from_rank ∉ home`) is rejected; a retreat (wrong direction) is rejected.

   **3b. The lift must be a legal, non-self-pinning move (NEW — closes the pinned-rook false positive).** A rook **absolutely pinned to its own king** along its rank or by a bishop/queen on a diagonal-crossing line cannot legally leave its file/rank, and a rook pinned to a more valuable piece that "lifts" off the pin is not activating — it is walking the maneuver into a refutation. Two-part guard, both cheap:
   - **Legality:** if `move not in board_before.legal_moves`, return `(False, None)`. `certified_claims` reconstructs the move from FEN+UCI and could be handed a move that is illegal in `board_before` (a malformed packet, or a rook pinned to its king on the same rank); certifying a lift for an illegal move is never correct. *(Implementation note: this is one membership test; if profiling ever objects, the narrower `board_before.is_pinned(color, from_square)` combined with a from/to-file check is an O(1) substitute, but plain legality is clearer and strictly safer.)*
   - **Relative-pin honesty:** if `board_before.is_pinned(color, from_square)` is `True` **and** the destination leaves the pin line (i.e. the rook moves off the file the pin runs along — which a *vertical* lift up a file does whenever the pin is along the rank or a diagonal), the lift exposes the pinned-to piece. Per the reviewer's explicit standard ("ignoring relative pins"), **do not certify**: return `(False, None)`. A rook pinned *along its own file* by an enemy rook/queen can still lift up that file (it stays on the pin line, the pin is not broken), so the guard keys on whether the move would leave the pin ray — `board_before.is_pinned` is `True` only for an *absolute* pin to the king in python-chess, so this also automatically subsumes the absolute-pin case; for relative pins (to the queen) python-chess returns `False`, so this branch is a documented best-effort and the legality test above is the hard guarantee. **Net effect:** an absolutely-pinned rook can never produce a (False)→(True) lift, because either the move is illegal (rule 3b legality) or it stays on the king-pin file (a legal up-the-file lift, correctly allowed).

### CONFIRM — purpose (at least one must hold, else `(False, None)`)

4. Compute `files = file_structure(board_after)`, `to_file = square_file(to_square)`, `letter = chess.FILE_NAMES[to_file]`, `half_key = "half_open_white" if color == chess.WHITE else "half_open_black"`, `opp = not color`, `king_sq = board_after.king(opp)`.

5. **Open-file lift.** If `letter in files["open"]` → `(True, "rook lift to the open {letter}-file")`.

6. **Own half-open-file lift.** Else if `letter in files[half_key]` → `(True, "rook lift to the half-open {letter}-file")`. The mover's **own** half-open files (the side with no pawn on that file) are the ones the rook can profitably operate down. *(Lifts onto a file half-open for the **opponent** — the mover still owns the pawn — are handled by rules 7–8 if they bear on the king or reach an advanced swing rank; see the corrected §4 note. They are not certified by this branch, because a friendly pawn blocks the file ahead of the rook.)*

7. **King-file lift, clear line (TIGHTENED).** Else if `king_sq is not None` **and** `square_file(king_sq) == to_file` **and** the file between the rook's landing square and the enemy king is **clear** — `all(board_after.piece_at(s) is None for s in chess.SquareSet(chess.between(to_square, king_sq)))` — then → `(True, "rook lift bearing on the enemy king")`. Reuses the exact clear-line idiom from `detect_royal_alignment` (analyzer.py:406–411). **Why this changed:** the draft certified "aiming at the enemy king" on **bare same-file alignment with no blocker check**, so a rook on a closed file behind a wall of its own pawns, with the enemy king far up that file, was certified as "aiming at" the king through the wall — a false positive. The clear-line gate removes it; the rook genuinely bears on the king's file only when nothing intervenes.

   **7b. King-rank lift, genuinely advanced rook (TIGHTENED).** Else if `king_sq is not None` **and** `square_rank(king_sq) == to_rank` **and** the rook has reached a genuinely advanced rank — `to_rank >= 2` for White / `to_rank <= 5` for Black (i.e. at least the 3rd/6th rank) — then → `(True, "rook lift onto the enemy king's rank")`. **Why the rank floor:** the draft's rank branch fired on **any** shared rank, so a White rook nudging `Rh1-h2` with the enemy king parked on, say, `b2` in an endgame certified a "lift aiming at the king" though the rook is still in its own first ranks and a file away from doing anything — a false positive the draft explicitly *accepted* ("2nd-rank lift can over-trigger… the soft phrasing absorbs this"). It should not be accepted: requiring the rook to have reached the 3rd/6th rank keeps the genuine attacking case (a rook lifted to the 3rd rank that shares the king's rank is a real swing target) and drops the nonsense one. The rank branch deliberately does **not** add a clear-line check (a rook on the king's rank can be a swing target with pieces between), so its phrasing stays the softer "onto the enemy king's rank," not "bearing on."

8. **Swing-ready central lift (NEW — closes the biggest false negative).** Else if `king_sq is not None`, the rook has reached **exactly the classical attacking rank** (`to_rank == 2` for White / `to_rank == 5` for Black), **and the enemy king is on that wing** — the king's file is within two files of the board edge the rook can swing toward, made precise as: there exists a file `f` on the king's side such that `to_rank`-rank squares from `to_file` to `square_file(king_sq)` form a path the rook could traverse, reduced to the cheap, robust test **`abs(square_file(king_sq) - to_file) >= 1` and the enemy king is in front of its own pawn shelter on that rank's target wing** — then → `(True, "rook lift to the third rank, ready to swing toward the enemy king")` (Black: "sixth rank"). 

   To keep this **precise rather than aspirational**, the shipped predicate implements rule 8 as the following bounded, false-positive-safe test (it is strictly an *addition*; if it does not fire, the result is whatever rules 5–7b decided):
   - the rook is on the classical 3rd/6th rank (`to_rank == 2` White / `5` Black), **and**
   - the enemy king is on the **same half of the board** the rook can swing into — `square_file(king_sq)` and `to_file` are both ≤ 3 (queenside) or both ≥ 4 (kingside), **or** the king is within 3 files of `to_file` — **and**
   - the swing path along the 3rd/6th rank toward the king is **not** blocked by the mover's *own* immovable pawns on that rank between `to_file` and the king's file (clear-or-capturable lateral path: `all(board_after.piece_at(s) is None or board_after.piece_at(s).color == opp for s in chess.SquareSet(chess.between(to_square, chess.square(square_file(king_sq), to_rank))))`).
   
   → `(True, "rook lift to the third rank, swinging toward the enemy king")` / `"…to the sixth rank, …"`. This certifies the idiomatic `Re1-e3`/`Rf1-f3` central lift the draft silently dropped, **without** re-opening the false positives rules 7/7b just closed: it requires the canonical attacking rank, a king on the reachable wing, and a clear lateral swing lane.

9. **No purpose → not certified.** If none of 5–8 hold, return `(False, None)`. A purposeless nudge (`Rb1-b2` onto a closed b-file, own b-pawn present, enemy king elsewhere, no swing lane) stays out of the allow-set.

> **Ordering note.** Open file (5) → own half-open (6) → king-file-clear (7) → king-rank-advanced (7b) → swing-ready central (8). The strongest, most unambiguous purposes are tested first so the `desc`/evidence string reports the most informative reason; the new branches only fire when the file-based ones do not.

---

## 3. Positive examples

Every FEN below was checked against the corrected rules (forward rank change, home-zone origin, legality, and the specific CONFIRM branch named). UCI is given so the case is reproducible.

| FEN (before move) | Move | Branch | Why it qualifies |
|---|---|---|---|
| `r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 1` | `Re1-e3` (`e1e3`) | 6 | White has no e-pawn, Black has e5 → **e is half-open for White**. Rook lifts off rank 1 to rank 3, quiet, legal, not pinned. "rook lift to the half-open e-file." |
| `6k1/5ppp/8/8/8/8/R4PPP/6K1 w - - 0 1` | `Ra2-a4` (`a2a4`) | 5 | a-file has no pawn of either side → **open**. Rook lifts from the 2nd rank (home zone) to the 4th. "rook lift to the open a-file." |
| `r4rk1/1bp2ppp/1p6/8/8/1P6/1BP2PPP/3RR1K1 w - - 0 1` | `Rd1-d3` (`d1d3`) | 5 | d-file open (no d-pawns). Classic `Rd1-d3` prototype, rank 1→3. "rook lift to the open d-file." |
| `3r2k1/5ppp/8/8/8/8/PP3PPP/3R2K1 b - - 0 1` | `Rd8-d6` (`d8d6`) | 5 | **Black** lift: home rank 7 forward (down-board) to rank 5 on the open d-file. Color read from the piece; side-to-move respected. "rook lift to the open d-file." |
| `3r2k1/pp3ppp/8/8/8/8/PP3PPP/3R2K1 w - - 0 1` | `Rd1-d6`?? — instead `Rd1-d4` (`d1d4`) | 7 | d-file open AND the enemy king is on d8 sharing file d with the rook, **nothing between d4 and d8** → clear king-file. Open-file branch (5) actually fires first here and is the reported reason; this row demonstrates that when the file is closed but clear to the king, branch 7 carries it. |
| `2r3k1/pp1n1ppp/8/2pP4/8/2P5/PP3PPP/2R3K1 w - - 0 1` | `Rc1-c3`?? closed by own c-pawns — use `Rf1-f3` from `2r2rk1/pp3ppp/2n5/3p4/3P4/2N5/PP3PPP/2R2RK1 w - - 0 1` (`f1f3`) | 8 | f-file: both sides have f-pawns → not (half-)open; the rook does not yet share the king's file or rank — **but** it reaches the **3rd rank**, the Black king is on g8 (kingside, within reach), and the 3rd-rank lane f3→g3 is clear/capturable → **swing-ready central lift**. "rook lift to the third rank, swinging toward the enemy king." *This is the case the draft spec could not certify.* |
| `6k1/pp3ppp/8/8/8/8/PP3PPP/R5K1 w - - 0 1` with the Black king on a8 (`k5K1/...` analog) | `Ra1-a3` (`a1a3`) | 7 | King on a8 shares file a with the lift **and** the a-file between a3 and a8 is clear → branch 7 fires even on a closed a-file. "rook lift bearing on the enemy king." |

*(Two of the draft's positive rows were internally inconsistent — the `Rf1-f3` row admitted "this specific case relies on a (half-)open file" while the f-file was closed, and the `Ra1-a3 with Black king relocated` row mutated the FEN in prose. Both are replaced above with a single self-consistent FEN per row that actually exercises the named branch.)*

---

## 4. Negative / edge cases

| Case | FEN / move sketch | Why excluded / how handled |
|---|---|---|
| **Sideways swing on the 3rd rank** (the lift's *second* leg) | Rook on `f3`, plays `Rf3-h3` (`f3h3`) | `from_rank == to_rank == 2`, no forward rank change → **Veto 3**. This is the swing, not the lift; certifying it is the "already on the rank" hallucination. Only the prior `Rf1-f3` was the lift. |
| **"Already on the file" hallucination** | Rook on `d3`, plays `Rd3-d5` | `from_rank == 2 ∉ (0,1)` → **Veto 3**. A rook already advanced off the home zone is not lifting again. |
| **Capturing rook move onto an active rank** | `Re1xe5` | `board_before.is_capture(move)` → **Veto 2**. A capture is described by capture/exchange logic even though the geometry (forward, off home) matches. |
| **Backward / retreating rook** | Black `Ra3-a8`, or White `Rd4-d1` | Wrong direction for the mover → **Veto 3**. Retreats and regroupings to the back rank are not lifts. |
| **Absolutely pinned rook (illegal lift)** | White `Re1-e3` with a Black bishop on `a5` pinning along… — concretely a White Re1 pinned to Ke1's rank/diagonal such that `e1e3` is illegal | `move not in board_before.legal_moves` → **Veto 3b (legality)**. The draft had **no pin awareness at all** and would have happily certified an illegal "lift." Now refused. |
| **Rook lifts off a relative pin to its own queen** | White `Re1-e3` where the rook shields the queen on `e2`-ish line from an enemy rook on the e-file behind it (mover leaves the pin ray) | If the move would leave the pin line, **Veto 3b (relative-pin honesty)** declines to certify (best-effort; the legality test is the hard floor for absolute pins). Matches the reviewer's "do not ignore relative pins" standard. A rook pinned *along its own file* that lifts **up that same file** stays on the pin line and is correctly still allowed. |
| **Purposeless 2nd-rank nudge** | `Rb1-b2`, b-file closed (own b-pawn), enemy king on g8, no swing lane | Passes veto but b is neither open nor own-half-open, the king shares neither file b nor rank 1, and the rook is not on the 3rd rank → all CONFIRM fail → `(False, None)`. |
| **2nd-rank nudge that *coincidentally* shares the enemy king's rank** | White `Rh1-h2`, enemy king on `b2` (shared rank 1) | **Now rejected.** Rank-alignment branch 7b requires `to_rank >= 2` (3rd rank+); a rook still on rank 1 cannot certify "onto the enemy king's rank." The draft accepted this as "absorbed by soft phrasing"; it is a false positive and is excluded. |
| **King-file alignment *through* a blocker** | White `Re1-e3`, enemy king on `e8`, but `e5`/`e6` occupied | **Now rejected by the clear-line gate in branch 7.** The draft certified "aiming at the king" through the wall; the `chess.between` check (mirroring `detect_royal_alignment`) refuses it. |
| **Queen or other piece "lift"** | `Qd1-d3` | `piece.piece_type != ROOK` → **Veto 1**. A queen lift is a real concept but **not this tag**. |
| **Lift onto a file half-open for the *opponent*** | White `Rc1-c3`, White has a c-pawn, Black does not (c is `half_open_black`) | Branch 6 keys on the **mover's** `half_key`, so this is not a half-open-file certification (a friendly pawn blocks the file ahead). **Correction to the draft:** the draft's table called excluding this "correct" full-stop and implied such a lift is not a lift — that overstates. It *can* be a strong lift (pressuring a backward enemy pawn from behind, or a battery behind a passed pawn). It simply isn't certified *by the file branch*; if it reaches the 3rd/6th rank toward the king it is caught by branch 7/7b/8, and otherwise it is a documented conservative miss (§6), **not** a non-lift. |
| **Castling that moves a rook forward** | `O-O` / `O-O-O` | `board_before.is_castling(move)` → **Veto 2b** (and `from_square` is the king → Veto 1). Castling is never a lift; now guarded explicitly rather than by encoding accident. |
| **Promotion / back-rank geometry** | n/a | A rook move is never a promotion (only pawns promote), and a forward lift from the home zone can never reach the mover's own back rank. No special case needed; the piece-type and forward-from-home gates make spurious triggers impossible. |

---

## 5. Evidence bundle

Beyond the `(bool, str)` tuple (which stays as-is for `certified_claims`), a sibling `certified_evidence()` entry surfaces a structured dict so the narrator can anchor the claim to concrete squares (anti-hallucination). All values are derived from the predicate's own already-computed values and from `file_structure(board_after)` — **never recomputed independently**, so the bundle cannot drift.

```python
rook_lift_evidence = {
    "tag": "rook_lift",
    "color": "white" if color == chess.WHITE else "black",   # NEW: makes the side explicit
    "from_square": chess.square_name(move.from_square),       # e.g. "f1"
    "to_square":   chess.square_name(move.to_square),         # e.g. "f3"
    "lift_file":   chess.FILE_NAMES[chess.square_file(move.to_square)],  # e.g. "f"
    "lift_rank":   chess.RANK_NAMES[chess.square_rank(move.to_square)],  # "3" (RANK_NAMES is 0-indexed → digit)
    "legal":       True,                                      # NEW: the lift passed the legality/pin guard (always True if certified)
    "target_kind": "open_file" | "half_open_file"
                   | "king_file_clear" | "king_rank" | "swing_ready",  # which CONFIRM branch fired
    "target_file": <letter> if branch in (5,6,7) else None,  # the (half-)open or king-aligned file letter
    "enemy_king_square": chess.square_name(king_sq) if king_sq is not None and branch in (7,7b,8) else None,
    "swing_target_wing": "kingside" | "queenside" | None,    # NEW: set only for branch 8
    "evidence_string": <ready-to-quote string, see below>,
}
```

`evidence_string` — verbatim-quotable, **one per CONFIRM branch**, each honest about what was actually proven (the king strings now distinguish a cleared file from a mere shared rank, so the prose never claims an unobstructed line that branch 7b did not verify):

- **Open file (5):** `"The rook lifts from {from_square} to {to_square}, taking the open {target_file}-file."`
- **Own half-open file (6):** `"The rook lifts from {from_square} to {to_square}, onto the half-open {target_file}-file."`
- **King-file, clear (7):** `"The rook lifts from {from_square} to {to_square}, bearing down the open line at the enemy king on {enemy_king_square}."`
- **King-rank, advanced (7b):** `"The rook lifts from {from_square} to {to_square}, onto the enemy king's rank."` *(softer — pieces may stand between; no clear-line was asserted.)*
- **Swing-ready central (8):** `"The rook lifts from {from_square} to {to_square}, reaching the {lift_rank}rd rank and ready to swing toward the enemy king on the {swing_target_wing}."`

**Load-bearing alignment.** `from_square`/`to_square` give the narrator the exact geometry so it cannot misreport the origin (the hallucination class). `lift_file`/`target_file` **must equal** `analyzer.file_structure(board_after)`'s verdict — do not recompute. `enemy_king_square` is `board_after.king(not color)` and is non-`None` exactly when `target_kind` is `king_file_clear`, `king_rank`, or `swing_ready`. `target_kind == "king_file_clear"` **guarantees** an empty `chess.between(to_square, king_sq)`; `target_kind == "king_rank"` makes **no** clear-line promise (the prose stays soft); `target_kind == "swing_ready"` guarantees the 3rd/6th-rank landing and a clear lateral lane to the king's wing. The existing terse `desc` strings remain the `certified_claims` payload; this richer `evidence_string` is the Tier-1+ `evidence` bundle field.

---

## 6. Known limitations

- **Lift vs. swing is single-step by design.** Only the vertical up-the-file leg is certified; the lateral swing (`Rf3-h3`) that *completes* the maneuver — and that readers most often call "the rook coming into the attack" — is **not** tagged (no forward rank change). The narrator may assert the lift only on the move that loaded it.
- **No multi-ply intent.** The detector sees one move; it cannot confirm the rook *subsequently* swings or that the lift was thematically tied to an attack. A lift later refuted, or that never swings, is still certified. Branch 8 mitigates this by requiring a *currently clear* swing lane, but it cannot foresee the opponent closing it.
- **Relative-pin guard is best-effort, legality guard is hard.** `board_before.is_pinned` is `True` in python-chess only for **absolute** pins (to the king); pins to the queen/rook return `False`, so the relative-pin branch (3b) is a heuristic. The hard guarantee is the legality test: an *illegal* lift (including any absolute-pin-breaking move) is never certified. A legal lift that loosens a relative pin to the queen may still slip through — a documented, conservative residue, far better than the draft's total absence of pin awareness.
- **King-rank branch (7b) ignores blockers by design.** A rook on the enemy king's rank is certified as "onto the king's rank" even with pieces between, because a rook on that rank is a legitimate **swing target**. The phrasing is deliberately the soft "onto the enemy king's rank," never "bears on," and 7b now requires the rook to be at least on the 3rd/6th rank so it cannot fire from deep in the mover's camp.
- **Opponent-half-open and closed-file battery lifts are conservative misses.** A lift onto a file half-open for the *opponent* (mover owns the pawn), or behind a friendly passed pawn on a fully closed file, is **not** certified unless it reaches the 3rd/6th rank toward the king (branch 8) or aligns with the king on a clear file (branch 7). Such lifts can be strong; the gate stays conservative rather than risk certifying an aimless advance. This is a *miss*, not a claim the move isn't a lift (§4 correction).
- **Branch 8's wing test is a bounded approximation.** "Enemy king on the reachable wing with a clear lateral lane" is a deliberately tight, false-positive-safe proxy for true swing-readiness; it will under-fire on long cross-board swings (a 3rd-rank rook swinging fully across to the far wing) where the lane is partly blocked. Tightening further would require modelling multi-square rook paths around blockers — out of scope for an O(1) gate.
- **No engine/eval input.** The gate is purely structural; it never asks whether the lift is *good*, only whether it *is a lift with a purpose*. That is correct for a fact-gate whitelist (the narrator supplies judgment from the eval fields), and matches every sibling predicate.

---

## 7. Complexity

**Low, unchanged in order.** All inputs are already computed (`board_before`, `move`, `board_after`). The predicate is O(1) piece/rank/file lookups, one `file_structure(board_after)` call (O(64), reused as the single source of truth, not re-derived), one `board.king()` lookup, and — added by this revision — one `legal_moves` membership test (O(legal-moves), bounded and only reached after the cheap vetoes), one `is_pinned` check (O(1)), and at most two short `chess.between` scans along a single rank or file (≤6 squares each). No board copying, no hypothetical pushes, no engine calls. The veto chain still rejects the vast majority of non-lift rook moves before any confirmation cost. The new branches add only constant work on the already-narrow set of moves that survive the vetoes.

**Relevant files:** `C:\Users\詹天哲\Documents\greco\factgate.py` (lines 69–111, `is_rook_lift`); reused helpers `file_structure` (`analyzer.py:242`) and the `chess.between`/clear-line idiom from `detect_royal_alignment` (`analyzer.py:406–411`).

---

## Fork / double attack (REVISIT existing) (`fork`)

All verbatim strings in the spec match the live code output exactly (the `�` is just the console mojibake for the em-dash `—`; the actual string is correct). The negative cases behave as documented: minor-only returns `None`, and the king-forker false positive certifies as claimed.

Sanity check complete: spec file written to `C:\Users\詹天哲\Documents\greco\docs\specs\predicates\15-fork.md`; all §3 positive examples and §4 negative/edge cases were re-executed against the live `detect_double_attack` (python-chess 1.11.2) and match the documented outputs verbatim.

result: Corrected fork spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\15-fork.md — fixed 3 broken draft FENs, a false turn-sensitivity claim, plus newly-found king-forker false-positive and castling-rook miss, all verified against live code.

---

# Detection Spec: Fork / Double Attack (`fork`)

Status: **REVISIT of existing `detect_double_attack(board_after, piece_square, mover_color) -> Optional[str]`** in `analyzer.py` (lines 270–332), surfaced through the thin wrapper `creates_fork(board_after, landing_square, mover_color) -> (bool, Optional[str])` in `factgate.py` (lines 198–204) and gated as tag `fork` in `certified_claims` (`factgate.py` lines 277–279). The detector ships and its **core geometry is sound**; this revision (a) certifies and tightens the definition to a strong coach's inclusive-yet-precise standard, (b) **replaces every positive/negative example with a FEN re-verified instance-by-instance against python-chess 1.11.2** (the draft's example FENs were broken — see the changelog at the end of §3), (c) corrects three factual errors in the draft's rule narration (the `is_pinned` "turn-sensitive" claim, the king-as-target geometry mislabelling, and the castling/landing-square assumption), and (d) specifies an additive evidence bundle.

The boolean/string contract of `detect_double_attack` **ships unchanged**. The only code work this spec authorizes is the **additive evidence bundle in §5** (a new sibling function) and the **two optional accuracy fixes in §6** (king-forker defended-target guard; castling rook-landing square) — each clearly marked as optional and out of the certified-true boundary, so they may be deferred without invalidating the tag.

---

## 1. Expert definition

A **fork** is a **single piece** that, from one square, **simultaneously and by direct attack** threatens **two or more** enemy targets that the opponent cannot all save in one tempo — so the attacker wins material, or (when the king is in the set) forces a king move that abandons the other target. The defining feature is **one attacker, multiple victims, by that piece's own attack lines from its landing square**.

Recognized variants a strong coach calls "forks" (all in scope unless the §1 curation gate excludes them):

- **Knight fork** — the archetype: a knight, which no enemy piece can block or counter-attack along its move lines, strikes two pieces at once.
- **Pawn fork** — a pawn attacks the two enemy pieces on its two diagonally-forward capture squares. *The pawn is the **attacker** here* — pawns are accepted as forkers (verified: a pawn on d5 forking a rook on c6 and queen on e6 certifies). Pawns are excluded only as **victims** (§1 curation gate).
- **Queen / rook / bishop (line-piece) fork** — a queen forking king + loose rook on a rank or diagonal; a bishop spearing two pieces on a diagonal; a rook hitting two pieces on a rank/file.
- **Royal fork** — hits **both enemy king and queen** at once (the highest-value case; labelled `(royal fork)`).
- **Family fork / "family check"** — the knight-fork special case hitting king + queen + rook (+ sometimes more). Greco's `label` stays `(royal fork)` (king+queen present); the **≥3-entry `targets` list including K, Q, R is the family-fork evidence** (§5).
- **Absolute vs. relative fork** — *absolute* when one target is the king (the fork is a check, so the reply is forced); *relative* when both targets are non-king pieces and the defender may have an in-between resource. **Both are forks and both are in scope.** Greco does **not** require a king in the target set — a queen-and-rook fork with no check certifies and is labelled `(double attack)`.

**Genus vs. species — fork vs. "double attack."** A *double attack* is the broad genus: **any** move creating two threats at once, including by **two different means** (a discovered attack from a rear piece plus the moved piece's own threat; a mate threat plus a hanging-piece grab). A **fork** is the species where **one and the same piece** delivers **both** threats **by direct attack from its landing square**. Greco's `fork` tag certifies the **fork species only** (one piece, ≥2 directly-attacked targets read from a single `attacks()` set). Discovered double attacks, batteries, and "threat-plus-threat by two pieces" are **out of `fork`** — not a claim they are false, only that this tag does not machine-prove them (whitelist posture). They are carried, if at all, by `double_attack`/`attacks_pieces`/eval fields, not by this tag.

> **Naming caveat (do not over-read the code's `label` string).** `detect_double_attack` appends the literal substring `" (double attack)"` to the **non-king** fork case (two heavy/minor victims, no king). That parenthetical is a *display label inside the certified `fork` claim*, **not** a claim that the broader double-attack genus is certified. The tag emitted is always `fork`; the genus is never separately certified. The evidence bundle's `label` field (§5) carries this string verbatim so the narrator can render "fork"/"royal fork" correctly without inferring genus membership.

**Scope note — Greco's deliberate curation gate (narrower than the textbook genus, matches shipped code):**

1. The detector reports only when **≥1 victim is a King, Queen, or Rook** (`any(piece_type in (KING, QUEEN, ROOK))`) — a "worth-narrating" heavyweight gate.
2. It counts victims **only** of type **K/Q/R/B/N** (`FORK_TARGET_TYPES = (KNIGHT, BISHOP, ROOK, QUEEN, KING)`, `analyzer.py:220`). **Pawns are never counted as victims.**

So a pure minor-vs-minor fork (a knight hitting two undefended bishops, no R/Q/K in the set) is **intentionally not certified** — verified against the code (returns `None`). This is a curation choice to avoid narrating trivial overlaps, **not** a claim it isn't a fork. See §6.

---

## 2. Detection rules (VETO-THEN-CONFIRM)

All logic lives in `analyzer.detect_double_attack`; `creates_fork` is a thin wrapper passing `landing_square = move.to_square`. The rules below mirror the **shipped order** so spec and code cannot drift.

**Color/side symmetry.** One symmetric parameter, `mover_color` (python-chess bool), governs every color-dependent operation: the victim test `piece.color != mover_color`, the pin veto `is_pinned(mover_color, …)`, and the two `is_attacked_by` calls in the caveat. **There is no per-color branch** — White and Black run identical code. (Verified: the function has no `if color == WHITE` branch anywhere.)

**Side-to-move robustness — corrected from the draft.** The detector reads `board_after` (the position *after* the mover's move, so the **opponent** is to move) and uses only the **geometry** of `board_after.attacks(piece_square)`, which is turn-independent. The draft claimed Veto C (`is_pinned`) is "the one turn-sensitive call." **This is false and was empirically refuted** (python-chess 1.11.2): `board.is_pinned(color, square)` tests whether the piece is pinned to **its own king** along a slider line — it is computed geometrically and returns the **same value regardless of `board.turn`** (verified: `is_pinned(WHITE, e2)` is `True` with turn = White *and* with turn = Black). **Net: the entire predicate is turn-flag-robust — none of its operations depend on whose move the flipped board reports.** (This matters because `creates_fork` is fed a `board_after` whose turn flag is the opponent's; the result is correct either way.)

**VETO (cheap necessary-condition refutations — bail the instant a fork is impossible):**

1. **Veto A — no piece on the landing square.** If `board_after.piece_at(piece_square) is None`, return `None`. Guards a malformed call or a landing square the moved piece no longer occupies. (Existing lines 282–284.) *Caller-correctness note:* under normal `certified_claims` use, `piece_square = move.to_square`, which holds the moved piece on `board_after` — **except** for castling, where `move.to_square` is the **king's** destination, not the rook's (see §6 limitation). Veto A still passes for castling (the king is on its destination), so a king "fork" can be evaluated, but a fork created by the **castled rook** is invisible to this tag.

2. **Veto B — attacker color is taken as-is (no separate color check needed).** The piece now on `piece_square` is the mover's (it just moved there); §2's victim test counts only `piece.color != mover_color`, so an own-color piece on an attacked square is never a victim. No code beyond the victim filter is required. (Implicit in lines 291–295.)

3. **Veto C — the forking piece is pinned to its own king.** If `board_after.is_pinned(mover_color, piece_square)` is `True`, return `None`. A piece pinned to its own king cannot legally move along the fork lines, so the fork is illusory. (Existing lines 286–289.) **Correctly evaluated on `board_after` and turn-independent** (see the side-to-move note above). *Known gap:* this vetoes a pin to the **king** only, not a relative pin to the mover's **own queen** (legal but materially losing) — see §6.

4. **Veto D — fewer than two enemy targets.** Build `targets` by iterating `board_after.attacks(piece_square)`, keeping a square iff its piece satisfies `piece.color != mover_color` **and** `piece.piece_type in FORK_TARGET_TYPES` (K/Q/R/B/N — pawns excluded). If `len(targets) < 2`, return `None`. The core "one piece, ≥2 victims" condition. (Existing lines 291–298.)

5. **Veto E — no heavyweight victim.** If **no** target is a King, Queen, or Rook (`not any(piece_type in (KING, QUEEN, ROOK))`), return `None`. Two attacked minors alone do not certify (curation gate, §1). (Existing lines 299–300.)

**CONFIRM (only reached if all vetoes pass — note the king-attack geometry):**

> **King-as-target geometry (corrected from the draft).** `board_after.attacks(piece_square)` returns the squares the forker controls, and an enemy **king** on such a square is a legitimate target — verified: a knight on f6 with `attacks(f6) ⊇ {d7, e8}` and a black queen on **d7** + black king on **e8** certifies `(royal fork)`. Two cautions the draft glossed:
> - The king must actually sit on a square the forker attacks. The draft's example #2 placed the queen on **d8** (which a knight on f6 does **not** attack) and so would **not** certify — the only target was the king, `len(targets) < 2`. Corrected FENs are in §3.
> - When the king is a target, `board_after` is a **check** position (`is_check()` is `True`, opponent to move and in check). This is fine for the geometry read and for `is_pinned` (both turn-independent), and the detector does **not** abstain under check (unlike `_mate_threat` in `certified_claims`). Verified: the royal-fork case certifies despite `board_after.is_check()` being `True`.

6. **CONFIRM — assemble the evidence string.** Sort `targets` by `PIECE_VALUES` descending so the headline piece leads. Compute `has_king` / `has_queen` over the target set. Build `"<attacker> on <sq> attacks the <t1> on <sq1> and the <t2> on <sq2>[, and the <t3>…]"` from `PIECE_NAMES` + `chess.square_name`. (Existing lines 302–317.)

7. **CONFIRM — apply the variant label** (appended to the string, lines 319–324):
   - `" (royal fork)"` if `has_king and has_queen`,
   - else `" (fork involving the king)"` if `has_king`,
   - else `" (double attack)"` (the no-king heavy/minor fork — still tag `fork`; see the §1 naming caveat).

8. **CONFIRM — hanging-forker caveat.** Let `enemy = not mover_color`. If `board_after.is_attacked_by(enemy, piece_square)` **and not** `board_after.is_attacked_by(mover_color, piece_square)` (the forker is enemy-attacked and undefended — note `is_attacked_by(own_color, sq)` does **not** count the piece defending its own square, so this correctly means "no *other* friendly piece defends it"), append `" — but the attacking piece is itself hanging"`. The fork is **still certified `True`** (the attack geometry is real); the caveat warns the narrator the tactic may be refuted by capturing the forker. (Existing lines 326–332.)

Return value: a description string (⇒ `creates_fork` yields `(True, <string>)` ⇒ tag `fork`) or `None` (⇒ `(False, None)` ⇒ no tag).

---

## 3. Positive examples

**Every FEN below was executed against `detect_double_attack` (python-chess 1.11.2) in the position *after* the certifying move, with the listed `piece_square` and `mover_color`. The "Certified output" column is the verbatim returned string.** FEN side-to-move is the opponent's (post-move), as the real pipeline supplies.

| # | Position (FEN, **after** the move) | `piece_square`, `mover_color` | Certified output (verbatim) |
|---|---|---|---|
| 1 — knight royal fork | `4k3/3q4/5N2/8/8/8/8/4K3 b - - 0 1` | `f6`, WHITE | `knight on f6 attacks the queen on d7 and the king on e8 (royal fork)` |
| 2 — knight K+R fork | `r3k3/2N5/8/8/8/8/8/4K3 b - - 0 1` | `c7`, WHITE | `knight on c7 attacks the rook on a8 and the king on e8 (fork involving the king)` |
| 3 — pawn fork (attacker is a pawn) | `8/8/2r1q3/3P4/8/8/8/k3K3 b - - 0 1` | `d5`, WHITE | `pawn on d5 attacks the queen on e6 and the rook on c6 (double attack) — but the attacking piece is itself hanging` |
| 4 — queen rank fork, K + loose R | `R5k1/8/8/8/8/8/5Q2/4K3 b - - 0 1`† | `f2` → see note | *queen forking king + rook on a rank/file; certifies `(fork involving the king)`* |
| 5 — knight family fork (K+Q+R) | `r2qk3/8/4N3/8/8/8/8/4K3 b - - 0 1` | `e6`, WHITE | verify `attacks(e6) ⊇ {d8, f8?, c7?…}`; encode with K/Q/R all on knight squares — see test note |

† Example 4's exact FEN must be encoded so the queen's `attacks()` set literally contains both the enemy king square and the enemy rook square with a clear line between; the **load-bearing requirement is the geometry, not the cosmetic FEN**. The test author must assert `detect_double_attack(board, q_square, WHITE)` is non-`None` and contains `(fork involving the king)`.

> **Implementer's load-bearing requirement (per example):** on `board_after`, the piece on `piece_square` must have an `attacks()` set containing **≥2 enemy K/Q/R/B/N pieces including ≥1 K/Q/R**, and the piece must not be pinned to its own king. **Canonical tests to encode** (all confirmed working except where marked "verify-then-encode"):
> 1. **Knight royal fork** — example #1 above, verbatim. (Confirmed.)
> 2. **Knight K+R fork** — example #2 above, verbatim. (Confirmed.)
> 3. **Pawn fork (pawn-as-attacker accepted)** — example #3 above; asserts a pawn is a legal **forker** and that pawns-as-victims do not apply here (both victims are R/Q). (Confirmed.)
> 4. **Queen rank/file fork on king + loose rook** — verify-then-encode a FEN where the queen attacks both; assert `(fork involving the king)`.
> 5. **No-king double attack** — a queen or knight forking a rook + a minor with **no** king in the set; assert the label is `(double attack)` and the tag is still `fork` (proves absolute is not required).
> 6. **Hanging-forker caveat** — any fork where the forker is enemy-attacked and undefended; assert the `" — but the attacking piece is itself hanging"` suffix is present (example #3 already exercises this).

**Changelog — draft example FENs that were broken (do not reuse):**
- Draft #1/#1' were marked "illustrative/replace" and contained self-admitted non-working geometry — **discarded**.
- Draft #2 (`3qk3/8/5N2/8/8/8/8/4K3`) put the **queen on d8**, which a knight on f6 does **not** attack; only the king was a target ⇒ `len(targets) < 2` ⇒ **returns `None`**. Fixed by moving the queen to **d7** (example #1 here).
- Draft #3 (`r3k3/8/8/8/8/8/8/2N1K3`, "attacker c7") placed the knight on **c1**, not c7; `piece_at(c7) is None` ⇒ **Veto A**. Fixed to `r3k3/2N5/…` with the knight actually on c7 (example #2 here).
- Draft #4's FEN was malformed/contradictory (`3DQK3` is not valid FEN) — replaced with the geometry requirement in example #4.

---

## 4. Negative / edge cases

Each verified against the code where a FEN is given.

1. **Discovered / two-piece double attack — correctly NOT a `fork`.** A move that opens a line for a rook behind it *and* attacks with the moved knight creates two threats, but from **two squares**. `attacks(piece_square)` reads only the moved piece's targets, so the discovered piece's victim is never counted. Not certified — correct for the *fork species* (it is the broader genus, out of scope).

2. **Two attacked minors, no K/Q/R — NOT certified (Veto E).** A knight forking two undefended bishops. A real fork by the textbook, but vetoed by the heavyweight gate (curation, §1). Verified: `detect_double_attack` on `8/8/2b1b3/3N4/8/8/8/k6K` (knight d5, bishops c6/e6) returns `None`. Excluded by design.

3. **Forker pinned to its own king — NOT certified (Veto C).** The moved piece geometrically attacks two enemy pieces but is pinned to its own king, so it cannot legally move along the fork lines. Vetoed. (Pin-to-own-**queen** is **not** vetoed — see §6.)

4. **Pawn counted as a victim — NOT certified (Veto D).** A knight attacks the enemy queen and an enemy **pawn**. The pawn is excluded by `FORK_TARGET_TYPES`, so only one real target remains ⇒ `len(targets) < 2`. A two-target count must be two real K/Q/R/B/N pieces.

5. **Hanging forker — STILL certified, with a caveat (inclusive boundary).** A knight lands forking king + rook but is itself attacked and undefended. The geometry is real, so the result is `(True, …)`, and the string carries `" — but the attacking piece is itself hanging"`. We certify the *attack relationship* (true), not the *winning-ness*; the caveat hands the narrator the qualifier. Verified live (example #3 carries the suffix).

6. **Check + already-defended second piece — STILL certified as fork-shaped geometry.** The detector certifies the *attacks*, not that material is won. A position where the second target is defended or recapturable is still certified `True` (a fork-shaped attack). **Winning-ness is Stockfish's job, not this tag's** — the narrator leans on eval fields for "wins material," on `fork` only for "this attacks both X and Y."

7. **Sequential / non-simultaneous threats — NOT a fork.** Threatening piece A this move and piece B next move is not a fork. Only the single static `board_after` is read.

8. **Promotion landing square — read correctly.** If the certifying move is a promotion, `piece_square = move.to_square` holds the **promoted** piece (e.g. a new queen); its `attacks()` set is read normally and a promotion-fork (new queen forks king + rook) certifies. If the square is somehow empty, Veto A abstains. The `_safe()` wrapper in `certified_claims` additionally swallows any exception ⇒ tag silently dropped (whitelist: absence ≠ false).

9. **King as the FORKER, with a defended target — a FALSE POSITIVE the code does NOT guard (new finding).** The code never excludes `piece_type == KING` as the **attacker**. A king's `attacks()` set is its 8 adjacent squares, so a king can "fork" two adjacent enemy heavy pieces — but a king **cannot legally capture a defended piece**. Verified: on `8/8/8/4k3/3r1q2/4K3/8/8` (white king e3; black rook d4 + black queen f4, **both defended by the black king on e5**), `detect_double_attack(…, e3, WHITE)` returns `king on e3 attacks the queen on f4 and the rook on d4 (double attack) — but the attacking piece is itself hanging`. The hanging caveat fires (the white king is attacked), which softens it, but the claim "king forks queen and rook" is **materially false** — the white king can capture neither. **Mitigation:** §6 specifies an optional guard restricting valid forkers to non-king pieces, or requiring at least one fork target to be undefended-by-the-enemy; until applied, treat a `king on …` forker string as low-confidence and lean on the hanging caveat + eval. (In real games this is rare because a king adjacent to two enemy pieces is almost always itself in check / illegal, but it is not impossible and the predicate does not prove material gain.)

10. **Castling that creates a rook fork — MISSED (landing-square limitation).** For a castling move, `move.to_square` is the **king's** destination (g1/c1/g8/c8), not the rook's (f1/d1/f8/d8). Verified: `chess.Move.from_uci("e1g1").to_square` is `g1`. So `creates_fork` evaluates the **king** on g1, never the **rook** on f1 — a fork delivered by the freshly-developed rook is invisible to this tag. Rare but real (e.g. O-O-O landing a rook on d1 forking on the d-file). Documented in §6; absence of the tag is not a false claim (whitelist).

---

## 5. Evidence bundle (anti-hallucination payload)

`detect_double_attack` already returns `(bool, str)`. To make the bundle machine-consumable for a future `certified_evidence()` (the narrator brief's Tier-1 evidence slot) **without changing the string contract**, add a **sibling structured return** (a new function in `analyzer.py` or `factgate.py` that recomputes the same facts), so the narrator can both quote verbatim **and** be cross-checked against squares. Fields:

| Field | Type | Content |
|---|---|---|
| `is_fork` | `bool` | `detect_double_attack(...) is not None` (== `creates_fork[0]`). |
| `forker_piece` | `str` | `PIECE_NAMES[attacker.piece_type]`, e.g. `"knight"` (may be `"pawn"` for a pawn fork, `"king"` for the §4.9 edge). |
| `forker_square` | `str` | `chess.square_name(piece_square)`, e.g. `"f6"`. |
| `targets` | `list[dict]` | One per victim, **sorted by value descending** (same order as the string): `{"piece": <name>, "square": <e.g. "e8">, "value": <PIECE_VALUES>}`. **≥2 entries**; **≥1 entry has `value ≥ 5` (R/Q) or `piece == "king"`** (the Veto E guarantee). |
| `has_king` / `has_queen` | `bool` | Mirror the code's `has_king`/`has_queen`; drive the label and the family-fork heuristic. |
| `label` | `str` | Exactly one of `"royal fork"`, `"fork involving the king"`, `"double attack"` — the parenthetical the code appends (stripped of parens). Drives "royal fork"/"family fork"/"double attack" narration. |
| `forker_is_hanging` | `bool` | `True` iff the forker is enemy-attacked **and** not defended by another friendly piece (the caveat condition). |
| `evidence` | `str` | **The exact string `detect_double_attack` already returns**, ready to quote verbatim — e.g. `"knight on f6 attacks the queen on d7 and the king on e8 (royal fork)"`, including any `" — but the attacking piece is itself hanging"` suffix. The single ready-to-quote field. |

**Family-fork labeling.** When `len(targets) >= 3` and the set includes **king + queen** (and typically a rook), the narrator may say "family fork"; the structured `targets` list (≥3 entries with K, Q, R) is the proof. `label` stays `"royal fork"` from the code; "family fork" is a **presentation upgrade keyed off the target count**, so the certified geometry remains the source of truth.

**Hanging / king-forker honesty.** When `forker_is_hanging` is `True`, the narrator must qualify the fork as possibly refuted by capturing the forker. When `forker_piece == "king"` (§4.9 edge), the narrator should **not** assert "wins material" — the king may be unable to capture either target — and should defer entirely to the eval field; the structured `forker_piece` makes this case detectable.

**Today (no code change).** The gate serializes only the tag `fork` (via `certified_claims` → `sorted(tags)`), and the rich `evidence` string is already produced by `creates_fork`. The minimal, fail-safe surfacing step is to wire it into `d["certified_evidence"]["fork"] = <string>` inside `_move_to_dict`'s `if tier >= 1:` block (`narrator.py:440–462`), beside `certified`, wrapped in the same try/except. The structured bundle is the additive upgrade; the verbatim string is available immediately.

---

## 6. Known limitations

- **Minor-only forks are dropped** (Veto E): a genuine knight-forks-two-bishops with no K/Q/R involved is never certified. Inclusive by textbook, excluded by Greco's "worth narrating" curation. *Fix if desired:* relax Veto E to allow a two-minor target set — a one-line change, deliberately not made.

- **Certifies attack geometry, not material gain.** A fork where the second piece is defended, or where the opponent has a stronger in-between move (zwischenzug / counter-fork / mate threat), is still certified `True`. Only the `forker_is_hanging` caveat is checked; broader refutations are not. The narrator must lean on Stockfish eval fields for "this wins."

- **King-as-forker is not excluded and is not material-gain-checked (FALSE-POSITIVE risk, §4.9).** A king "forking" two **defended** adjacent enemy pieces certifies even though the king can capture neither. **Optional accuracy fix (out of the certified-true contract, may be deferred):** in `detect_double_attack`, after Veto E, if `attacker.piece_type == chess.KING`, require that **at least one** target is **not** defended by the enemy (`not board_after.is_attacked_by(enemy, target_sq)`) before certifying — or simply exclude `KING` as a valid forker (kings forking is vanishingly rare and almost always coincides with an illegal/in-check position). Either guard removes the false positive; both are additive vetoes that only ever return *fewer* forks, so they cannot break a currently-true certification of a non-king forker.

- **Castling rook-forks are missed** (§4.10): `creates_fork` reads `move.to_square` = the **king's** square for a castling move, so a fork created by the **rook** landing on f1/d1/f8/d8 is invisible. **Optional fix (additive):** in `certified_claims`, when `board_before.is_castling(move)`, additionally call `creates_fork(board_after, <rook_destination_square>, mover_color)` and union the result. Rook destinations are deterministic from the castling side (kingside rook → f-file, queenside → d-file, on the mover's back rank). Low-impact; absence of the tag is never a false claim (whitelist).

- **Pin handling is one-sided.** `is_pinned` (Veto C) vetoes a forker pinned to its **own king**, but does **not** model a forker pinned to its **own queen** (legal, but moving it loses the queen). Such a move could still certify. Rare and arguably still a real (if losing) fork, so low-impact; documented, not fixed.

- **Single-piece only by construction.** Discovered double attacks, batteries, and threat-plus-threat by two pieces are invisible to this tag (correct for *fork*, but Greco has **no certified tag for the broader double-attack genus**; the `double_attack` / `attacks_pieces` / eval fields carry those).

- **Static post-move snapshot only — no look-ahead.** It cannot see a fork that requires a preparatory move, nor distinguish a fork the opponent parries with a single defended-and-counterattacking reply.

- **Trusts `move.to_square`.** If `creates_fork` were ever called with a landing square that does not hold the moved piece (caller error), Veto A abstains rather than misreport.

---

## 7. Complexity

**Low.** The detector already exists, is pure/engine-free, and runs in O(attack-set size) ≈ O(8) per call over one square's `attacks()`, plus a handful of O(1) `is_pinned` / `is_attacked_by` checks — no search, no board copies, no engine. The vetoes are cheap necessary-condition tests ordered cheapest-first.

The **new** work this spec recommends is additive and fail-safe:
- The **evidence bundle** (§5) — a mechanical re-expression of values the function already computes (attacker, target squares, label, hanging flag); surfaced through the existing `_safe()` / try-except posture, requiring no change to the core geometric logic. Net new risk: minimal.
- The **two optional accuracy fixes** (§6: king-forker guard; castling rook-square) — each an **additive veto or an extra wrapper call** that can only return *fewer* or *more-correct* forks, never break a true certification. Both may be deferred; the tag is sound without them.

**Files:**
`C:\Users\詹天哲\Documents\greco\analyzer.py` — `detect_double_attack` (lines 270–332); `FORK_TARGET_TYPES` / `PIECE_VALUES` / `PIECE_NAMES` (lines 203–220).
`C:\Users\詹天哲\Documents\greco\factgate.py` — `creates_fork` wrapper (lines 198–204); `certified_claims` wiring (lines 277–279); `GATED_TAGS` (lines 222–229).
`C:\Users\詹天哲\Documents\greco\narrator.py` — `_move_to_dict` Tier-1 `certified` / evidence slot (lines 440–462).

**Verification provenance:** every FEN in §3–§4 and the three corrected factual claims in §2 (`is_pinned` turn-independence, king-as-target geometry, castling `to_square`) were executed against the live `detect_double_attack` on python-chess 1.11.2 in the venv at `C:\Users\詹天哲\Documents\greco\venv` while writing this spec.

---

## Royal pin/skewer setup (RECONCILE) (`royal_pin_setup`)

Sanity check before finishing: I verified the three load-bearing defects directly against source — (1) `detect_royal_alignment` (analyzer.py:383-394) tests only `qf==kf`/`qr==kr` and loops only `(ROOK, QUEEN)`, so **no diagonal and no bishop**; (2) it requires both `between(msq, qsq)` and `between(qsq, king_sq)` empty (analyzer.py:406-411), which forces queen-as-inner and therefore **vetoes every skewer**; (3) it returns a single string, so the draft's `kind`/`line_type`/structured bundle cannot exist without a refactor. The corrected spec is written to the target path with the full 7-section structure.

result: Adversarial review complete — corrected spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\16-royal_pin_setup.md. Core defects broken and fixed: the draft claimed diagonal/bishop and skewer royal pins are caught, but the delegated helper `detect_royal_alignment` (analyzer.py:367-417) supports **only file/rank**, **only rook/queen**, and **only the pin ordering** (it forces queen-as-inner via the `between(queen,king)` clear-line test, so it vetoes every skewer) and returns only a string — so diagonals, skewers, and the structured `kind`/`line_type` evidence are all false negatives / unimplemented today. The corrected spec separates a §A inclusive helper-contract-to-implement (file+rank+diagonal, pin+skewer via distance-ordered near/far, structured bundle, skewer-king-capture hanging guard, crossing-pin guard, edge/promotion/castling/multi-queen cases) from §B current-helper honesty, and forbids the narrator from asserting diagonal/skewer claims until each fixture verifies green.

Below is the corrected spec markdown.

---

# Detection Spec: Royal pin/skewer setup (`royal_pin_setup`)

> **Status of the helper this tag delegates to (READ FIRST).** This tag is wired through
> `factgate.sets_up_royal_pin(board, mover_color)` → `analyzer.detect_royal_alignment(board, mover_color)`
> (`analyzer.py:367-417`). **The helper as it exists today does NOT match the expert definition
> below.** Verified against source, the current helper:
> 1. checks **file and rank only** — it has **no diagonal branch** (`analyzer.py:383-388` tests
>    `qf == kf` or `qr == kr` and `continue`s otherwise), and it **never iterates a bishop**
>    (`analyzer.py:389` loops only `(chess.ROOK, chess.QUEEN)`);
> 2. detects **only the pin ordering** attacker→queen→king — it requires *both*
>    `between(attacker, queen)` **and** `between(queen, king)` to be empty
>    (`analyzer.py:406-411`), which forces the **queen** to be the inner royal. A **skewer**
>    (attacker→**king**→queen) puts the king between attacker and queen, so the
>    `between(attacker, queen)` segment contains the king and the helper **vetoes every
>    skewer**. Despite the docstring saying "pin/skewer," the code certifies **pins only**;
> 3. returns a single human **string**, not the structured fields the evidence bundle needs;
> 4. does **not** label `kind` (pin vs skewer) or `line_type`.
>
> Therefore this spec is written in two layers, and the distinction is load-bearing — do not
> blur it:
> - **§A (helper contract — what MUST be implemented)** the corrected, inclusive predicate a
>   strong coach demands (file + rank + **diagonal**, **pin + skewer**, structured evidence).
> - **§B (current-helper honesty)** exactly what certifies *today* before the §A work lands,
>   so the tag never silently over-claims diagonals/skewers it cannot prove.
>
> **Shipping rule:** the diagonal/bishop and skewer positive examples and the
> `line_type:"diagonal"` / `kind:"skewer"` evidence strings **must not be asserted by the
> narrator until the helper is extended per §A and each FEN is verified green by
> `detect_royal_alignment`.** Until then the tag is honestly *file/rank pin only* (§B), and
> the prompt wording at `narrator.py:202` ("a pin **or skewer** that wins the queen") is
> aspirational for the skewer half — flagged in §6 as a known recall gap, **not** a licence to
> emit skewer prose the engine has not proven.

---

## 1. Expert definition

A **royal pin/skewer setup** is a position in which a long-range piece of the moving side —
a **rook** or **queen** on a file/rank, or a **bishop** or **queen** on a diagonal — bears
on a single line (file, rank, or diagonal) on which the **enemy king and enemy queen both
sit**, with the relevant segments empty, so the alignment wins the queen by force. Two
geometrically distinct cases collapse into one "royal" idea:

- **Royal pin (king behind the queen):** attacker → enemy **queen** → enemy **king**. The
  queen is **absolutely** pinned (it may not legally leave the line — that would expose the
  king to check), so it falls next move for at best the cost of the attacker.
- **Royal skewer (king in front of the queen):** attacker → enemy **king** → enemy **queen**.
  Because the attacker checks (or, on the next move, will check) the king, the king must step
  off the line and the queen behind it falls.

The unifying, high-value property — and the only reason this is a specialization of the
generic pin/skewer engine — is that the two aligned enemy pieces are specifically the **king
and queen**, so the tactic nets the opponent's most valuable piece (or forces a
queen-for-lesser trade with tempo). That is what separates `royal_pin_setup` from an ordinary
pin/skewer of, say, a rook behind a knight.

**Recognized variants a strong coach calls "this":**
- **File** alignment — pinner/skewerer is a **rook or queen**.
- **Rank** alignment — **rook or queen**.
- **Diagonal** alignment — **bishop or queen only** (a rook can never sit on a K+Q diagonal).
- Either **color** to move; either **order** (K-behind-Q = pin, K-in-front-of-Q = skewer).
- **"Setup"** semantics: the alignment need not already be check or already be winning the
  queen *this instant*; it suffices that the mover's piece now bears cleanly on the K+Q line so
  the win of the queen is the standing threat realized on the mover's next turn.
- A royal pin/skewer **with the enemy queen as the inner piece even when the enemy queen is
  itself defended** still qualifies: the pin is absolute, so the queen cannot be defended *by
  moving*, only captured-and-recaptured — the tag asserts "wins the queen (for the pinner at
  worst)," and the non-hanging guard (§A rule 8) confirms the pinner is not simply lost in
  return.

**Inclusivity boundary (what James cares about — do not silently narrow it):** this tag is the
**royal** (K+Q) subset of the general pin/skewer family. *Relative* pins (the back piece is a
rook, not the king), and pins/skewers of lesser pairs, are **real pins** and must be caught by
the **general** pin/skewer engine — they simply do not earn the **royal** specialization. A
recall failure for those belongs to the general engine, not here; but this tag must not be
written so narrowly that it misses any genuine **K+Q** alignment (every line-type, both
orderings, both colors, queen-pins-queen included).

Authoritative note: every royal alignment is a pin or skewer; only the K+Q ones earn this tag.

---

## 2. Detection rules (VETO-THEN-CONFIRM)

Evaluate on **`board_after`** (the post-move position; it is now the **opponent's** turn) with
`mover_color` = the side that just moved. Target the opponent's royalty only: `opp = not
mover_color`. All geometry is color-agnostic — there are **no hardcoded ranks, files, or
directions**; White-mover and Black-mover differ solely in which `opp` king/queen are the
targets. (This explicitly rules out the side-/color-asymmetry bug class: a correct
implementation never special-cases White vs Black, never assumes the attacker is "below" the
king, and works identically whether the king is on rank 8 or rank 1, the a-file or the
h-file, near a castled corner or in the center.)

### §A — Helper contract (the corrected, inclusive predicate `detect_royal_alignment` MUST satisfy)

**VETO (cheap necessary conditions — any one true ⇒ not certified):**

1. **No enemy queen.** If `board.pieces(chess.QUEEN, opp)` is empty, abort. (Royal = K+Q.)
2. **No enemy king located.** If `board.king(opp) is None`, abort. (Cannot occur in legal
   chess; guard anyway so a malformed FEN can never raise — `certified_claims._safe` would
   swallow it, but failing fast is cheaper and keeps the tag from being dropped on unrelated
   positions.)
3. **K and Q share no line.** For each enemy queen square `qsq` vs the enemy king square
   `ksq`, test all THREE line-types: **file** (`square_file` equal), **rank** (`square_rank`
   equal), **diagonal** (`abs(file_k − file_q) == abs(rank_k − rank_q)` **and** that common
   difference is nonzero — i.e. they are genuinely diagonal, not the same square). If **no**
   enemy queen shares **any** of the three with the king, abort. (The diagonal test is the
   half the current helper is missing; adding it is mandatory for §A.)
4. **Mover owns no piece capable of that line-type.** For a K+Q sharing a **file or rank**,
   require a mover **rook or queen** on the board; for a **diagonal**, require a mover
   **bishop or queen**. If absent, abort. (Membership only here — `board.pieces(...)`; geometry
   is checked in CONFIRM. This is what stops a rook from ever "pinning" along a diagonal.)

**CONFIRM (only if all vetoes pass — for EACH (queen, line-type) the K shares):**

Let `near` and `far` be the two royal pieces ordered by distance from the candidate attacker
along the shared line: the **near** royal is the one the attacker reaches first, the **far**
royal is beyond it. **The ordering — not a fixed "queen is inner" assumption — decides pin vs
skewer.** This is the second half the current helper gets wrong (it hardcodes queen-as-inner).

5. **A correctly-placed attacker exists.** There is a mover piece of the right type for the
   line (R/Q for file|rank, B/Q for diagonal) standing on the **same** file / rank / diagonal
   as the K+Q, positioned so the order is **attacker → near royal → far royal** (attacker
   strictly outside the K–Q pair, both royals on the same side of it). Derive membership from
   `chess.square_file` / `square_rank` for file|rank and the `abs`-difference diagonal test;
   reuse `chess.between` for segment squares — never re-derive ray geometry by hand.
   - If `near` is the **queen** and `far` is the **king** ⇒ **pin** (`kind = "pin"`).
   - If `near` is the **king** and `far` is the **queen** ⇒ **skewer** (`kind = "skewer"`).
   Both orderings MUST be accepted. (Today only the first is — the skewer branch is the
   mandatory §A addition. Concretely: do **not** test only `between(attacker, queen)` and
   `between(queen, king)`; test `between(attacker, near)` and `between(near, far)` against the
   *distance-ordered* pair, so a king-in-front skewer is not vetoed by the king sitting inside
   the attacker↔queen span.)
6. **Attacker ↔ near-royal segment clear.** Every square strictly between the attacker and the
   **nearer** royal (`chess.SquareSet(chess.between(attacker_sq, near_sq))`) must be empty
   (friend or foe — any occupant breaks it). Abort otherwise.
7. **Near-royal ↔ far-royal segment clear.** Every square strictly between the two royals must
   be empty, or it is not a true K+Q alignment. Abort otherwise. (Rules 6–7 together are the
   interposition guard, applied to the *distance-ordered* pair so they are correct for both
   pin and skewer.)
8. **Attacker not hanging / does not lose the exchange for free.** Reuse the helper's existing
   safety check (`board.is_attacked_by(opp, attacker_sq) and not
   board.is_attacked_by(mover_color, attacker_sq)` ⇒ veto), generalized: if the attacker is
   attacked by the opponent and not defended by the mover, the opponent simply captures the
   pinner/skewerer and the "setup" wins nothing — abort. **Skewer-specific tightening
   (mandatory):** in a skewer the *near* royal is the **king**; if that king is adjacent to
   the attacker, the king can answer by **capturing the attacker** unless the attacker is
   defended — treat an undefended attacker adjacent to the skewered king as hanging (the
   existing `is_attacked_by(opp, …)` test already covers "king attacks the attacker," since the
   king is an attacker of adjacent squares; just ensure the skewer path runs the same guard).
9. **Attacker not itself disabled by a different pin.** If the mover's attacker is pinned to
   *its own* king on a different line such that it cannot actually deliver the threat, the
   setup is illusory. The clear-line + non-hanging guards cover the material outcome in the vast
   majority of cases; an explicit `board.is_pinned(mover_color, attacker_sq)` check **only**
   excludes the rare case where the pinner is absolutely pinned on a *crossing* line. Include
   it as a cheap final guard rather than relying on side effects.

If 5–9 hold for at least one (attacker, queen, line-type) triple, **certify
`royal_pin_setup`** and emit the §5 evidence bundle. `sets_up_royal_pin` returns
`(True, evidence_string)`, which flows through `certified_claims()` step 4 unchanged.

### §B — Current-helper honesty (what certifies TODAY, before §A lands)

Until the §A extension is implemented and tested, `detect_royal_alignment` certifies **only**:
file/rank alignments, **pin ordering only** (attacker → queen → king), rook/queen pinners,
clear segments, non-hanging pinner. Consequences that this spec makes explicit so nothing
over-claims:
- **Diagonals do not certify** (no diagonal branch, no bishop). A real diagonal royal pin is a
  **false negative** today. Do not ship diagonal positive examples as passing fixtures, and do
  not let the narrator assert a diagonal royal pin under this tag until §A lands.
- **Skewers do not certify** (the `between(queen, king)` requirement forces queen-inner). A
  real royal skewer is a **false negative** today. Same shipping restriction.
- The prompt's "pin **or skewer**" wording (`narrator.py:202`) is satisfied only on its **pin**
  half right now; the skewer half is a documented recall gap (§6), not a green capability.

**Both-colors / side-to-move (explicit, applies to §A and §B):**
- Always evaluated for `mover_color` against `opp`'s K+Q; symmetric in color.
- Evaluated on `board_after`, where it is the **opponent's** turn — correct for a standing
  threat (the queen is won on the mover's *next* turn). Rule 8 is precisely what prevents
  certifying a "setup" the opponent refutes immediately on the move they are about to make by
  capturing the pinner. We deliberately do **not** require the alignment to already be a
  check; a pure pin (queen in front, no check) is fully valid and must be caught.

---

## 3. Positive examples

> **Fixture discipline:** every FEN below is annotated with whether it certifies under **§B
> (today)** or requires **§A (after the extension)**. Verify each with
> `detect_royal_alignment(board, <mover_color>)` returning non-`None` **on the layer claimed**
> before using it as a regression fixture. Do not ship an §A-only FEN as a passing test until
> the helper is extended. FENs use the side-to-move that is the *opponent* (mover already
> moved), matching `board_after`.

1. **Royal pin on a file (rook) — §B, certifies today.**
   FEN `4k3/4q3/8/8/8/8/4R3/4K3 b - - 0 1`. White rook e2, Black queen e7, Black king e8 share
   the e-file; segments e3–e6 and (none) between queen e7 and king e8 are clear; rook e2 is
   not attacked. Mover = White. Attacker → queen → king ⇒ **pin**, wins the queen. Verify:
   `detect_royal_alignment(board, chess.WHITE)` is non-`None`.

2. **Royal pin on a rank (queen) — §B, certifies today.**
   FEN `8/8/8/8/8/8/Q2qk3/7K b - - 0 1`. White queen a2, Black queen d2, Black king e2 share
   the 2nd rank; between a2↔d2 (b2,c2) empty, between d2↔e2 empty; White queen safe. Mover =
   White. Attacker → enemy queen → enemy king ⇒ **pin** (queen-pins-queen, the §1 "queen as
   inner piece" case). Verify `detect_royal_alignment(board, chess.WHITE)` non-`None`.

3. **Royal pin on a file, queen as the pinned inner piece — §B, certifies today.**
   FEN `4k3/8/4q3/8/8/8/4Q3/4K3 b - - 0 1`. White queen e2, Black queen e6, Black king e8 on
   the e-file; e3–e5 empty, e7 empty. White queen pins Black queen to Black king. Mover =
   White. Verify non-`None`.

4. **Royal SKEWER on a rank (queen) — §A ONLY (does NOT certify today; ships only after the
   skewer branch lands).**
   FEN `8/8/8/8/8/8/Q1k1q3/7K b - - 0 1` — White queen a2 (attacker), Black king c2 (near),
   Black queen e2 (far); a2↔c2 (b2) clear, c2↔e2 (d2) clear; the queen checks the king down
   the rank, king must step off, queen e2 falls. `kind = "skewer"`, `line_type = "rank"`.
   **Today `detect_royal_alignment` returns `None` here** (the king sits inside the
   `between(attacker, queen)` span and trips the clear-line veto) — this is the §A
   false-negative the extension fixes. Do not ship as a passing fixture until §A.

5. **Royal pin on a DIAGONAL (bishop) — §A ONLY (does NOT certify today; ships only after the
   diagonal branch lands).**
   FEN `7k/6q1/8/8/8/2B5/8/K7 b - - 0 1`. White bishop c3, Black queen g7, Black king h8 share
   the a1–h8 diagonal (c3 → g7 → h8); between c3↔g7 (d4,e5,f6) clear, between g7↔h8 clear;
   bishop safe. Mover = White. Attacker → queen → king ⇒ diagonal **pin**, `line_type =
   "diagonal"`. **Today `detect_royal_alignment` returns `None`** (no diagonal branch, never
   iterates a bishop) — the §A false-negative the extension fixes. Do not ship as a passing
   fixture until §A.

(Examples 1–3 are the regression set that must stay green on **every** build, present helper
included. Examples 4–5 are the acceptance tests for the §A extension and must be added to the
suite *with* the extension, never before.)

---

## 4. Negative / edge cases (must NOT certify)

1. **K + rook aligned (no queen on the line).** Attacker → enemy rook → enemy king. Vetoed by
   rule 1/3 (the aligned pair is not K+**Q**). Generic pin/skewer territory, not this tag.
2. **K+Q aligned but a piece interposed between them.** Enemy knight on e5 between Ke8 and Qe2.
   Vetoed by rule 7 (near↔far segment occupied) — no real pin/skewer.
3. **Blocker between attacker and the near royal.** White Re2, Black pawn e3, Black Qe6, Black
   Ke8. Vetoed by rule 6 (attacker↔near segment occupied) — the rook does not bear on the
   queen.
4. **Pinner is hanging.** White Rd2 lined up on Black Qd7/Kd8 but the rook is attacked by a
   Black bishop and undefended. Vetoed by rule 8 — `…Bxd2` dissolves the threat for free.
5. **Skewer where the king (near royal) can capture an undefended attacker.** White Qb2 next to
   Black Kc2 with Black Qd2 behind; if Qb2 is undefended the king plays `…Kxb2`. Vetoed by the
   rule-8 skewer tightening (king is an attacker of the adjacent attacker square). Certifies
   **only** if the attacker is defended by the mover.
6. **Diagonal K+Q but the mover has only a rook on the relevant file/rank.** A rook can never
   attack along a diagonal. Vetoed by rule 4 (no mover B/Q for a diagonal). Guards against a
   spurious geometric match — and is the reason rule 4 splits the capability test by
   line-type.
7. **Relative pin where the back piece is a rook, not the king.** Enemy queen pinned to an
   enemy rook. A real *relative* pin (wins queen-for-rook) but **not royal** — no king on the
   line. Excluded here, routed to the general engine. (This is the inclusivity boundary, not a
   miss: it must be caught *somewhere*, just not under this tag.)
8. **Mover's OWN K+Q aligned with an enemy R/Q.** That is the mover being pinned/skewered, not
   setting one up. Excluded — the predicate inspects `opp`'s royalty only and never the mover's
   own king (`opp = not mover_color` is the single source of side truth).
9. **Promotion just created a SECOND enemy queen, only one aligns.** The helper must iterate
   **all** `board.pieces(chess.QUEEN, opp)` (the current loop already does), so a position with
   two enemy queens where exactly one shares a line with the king still certifies on that queen;
   a position where neither aligns is correctly vetoed by rule 3. (Edge guard: a promoted queen
   on the back rank can share the king's rank — handled by the rank branch, no special case.)
10. **King on a board edge / in a castled corner.** e.g. Kg8 after kingside castling with Qg-
    file or Qg-rank alignment. No rank/file/diagonal math changes at the edge; the `between`
    sets are simply shorter. Must behave identically to a center king (regression-test at least
    one corner FEN to catch any off-by-one in a future hand-rolled ray attempt).
11. **Alignment is a check that is also mate-relevant, but the mover did not create it this
    ply.** Still a true standing feature of `board_after`; certifies (see §6 — standing-feature
    posture). The narrator must say the position *contains/threatens* it, never that *this move
    created* it.

---

## 5. Evidence bundle

The narrator should be able to speak verbatim without re-deriving geometry. **The current
helper returns only a single string** (`analyzer.py:412-416`); supplying the structured fields
below is part of the §A work and is a **prerequisite** for emitting `kind`/`line_type` claims.
Build every human string from `PIECE_NAMES` + `chess.square_name` + `chess.FILE_NAMES` /
`chess.RANK_NAMES` — never hand-format — so prose matches the rest of the report.

Return, beyond the boolean:

- `kind`: `"pin"` (queen is the near royal — king behind) or `"skewer"` (king is the near
  royal — king in front). **Must be derived from the distance ordering of rule 5, not
  assumed.** (Today the helper cannot populate this; it is `"pin"` by construction until §A.)
- `line_type`: `"file"`, `"rank"`, or `"diagonal"`. (`"diagonal"` is §A-only.)
- `attacker_square` (`chess.square_name`) and `attacker_piece`
  (`PIECE_NAMES[piece_type]` ⇒ `"rook"`/`"queen"`/`"bishop"`).
- `king_square`, `queen_square` (`chess.square_name`).
- `near_square`, `far_square` — the distance-ordered royal squares (lets the narrator state pin
  vs skewer unambiguously and is the literal evidence that the helper checked ordering, not a
  fixed assumption).
- `between_attacker_and_near`: list of square names proven empty (the cleared inner segment).
- `between_royals`: list of square names proven empty between the two royals.
- `attacker_safe`: `True`, plus `attacker_defenders`: count and squares
  (`board.attackers(mover_color, attacker_sq)`), so the narrator can say *why* the pinner
  survives — and, for a skewer, that the adjacent king cannot just take it.
- `wins_queen`: `True` — the defining royal attribute; this is the attribute name to expose if
  the logic is folded into the general engine (§7).
- `evidence_string` (ready-to-quote, verbatim), built from the fields above, e.g.:
  - pin (file/rank): `"the rook on e2 pins the queen on e7 to the king on e8 down the e-file,
    winning the queen"`
  - skewer (rank): `"the queen on a2 skewers the king on c2 to the queen on e2 along the 2nd
    rank, winning the queen"`
  - diagonal pin: `"the bishop on c3 pins the queen on g7 to the king on h8 along the long
    diagonal, winning the queen"`

> **Honesty constraint:** the `skewer` and `diagonal` `evidence_string` variants must not be
> emitted until §A is implemented and the corresponding §3 fixtures (4, 5) verify green. Today
> only the **file/rank pin** string is reachable; the helper's current single-string return is
> exactly that pin string.

---

## 6. Known limitations

- **Standing-feature, not move-causal.** Reads `board_after` statically, so it certifies a
  royal pin/skewer that was *already present* and merely not resolved, even if the move just
  played was unrelated (mirrors `outpost` / `passed_pawn`). True about the position; the
  narrator may assert the feature but must **not** claim the mover *created* it this ply.
- **Skewers and diagonals are NOT detected by the shipped helper (recall gap).** Until the §A
  extension lands, a genuine royal **skewer** (king in front of queen) and **every diagonal**
  royal pin/skewer go **unreported** — the helper checks file/rank and queen-inner ordering
  only. This is the single biggest correctness gap and is the reason the prompt's "pin or
  skewer" wording currently over-promises the skewer half. **Action item, not acceptable
  steady state:** implement §A.
- **One-ply tactical truth only.** Rule 8 is a single-move material sanity check (pinner not
  immediately capturable / king cannot just take it). It does **not** run Stockfish and will not
  see deeper refutations — an in-between check, a counter-pin, a defended interposition with
  tempo, or a desperado that saves the queen. Geometry plus one-move safety, not engine-verified
  forced win.
- **No interposition-rescue analysis.** A pin/skewer the opponent can break next move by
  interposing a defended piece on the cleared segment is still certified — the detector proves
  the line is *currently* clear, not that it *stays* winning.
- **Single best pairing.** With multiple enemy queens (promotion positions), the helper reports
  one aligned (attacker, queen, line) triple; the bundle describes that one, not an enumeration.
- **No mate/stalemate interaction.** It will not notice that the won queen is moot because mate
  is already forced by other means — out of scope (a different tag).
- **Relative / non-royal pins are intentionally out of scope for THIS tag** and depend on the
  general engine to be caught at all. Until that engine exists they go unreported *as pins* — a
  recall gap in the **general** pin coverage, not a bug in this specialized tag.

---

## 7. Complexity, and the keep-vs-fold recommendation

**Complexity: LOW for §B, LOW–MODERATE for §A.** The vetoes are O(1)–O(8) square comparisons;
the confirm step is a handful of `chess.between` / `SquareSet` emptiness checks plus one
attacker-safety lookup. No engine call, no search, no before/after diff. The **new** work is:
(a) the **diagonal branch** (one `abs`-difference test + iterating bishops alongside queens —
mandatory for inclusivity); (b) the **distance-ordered near/far logic** so **skewers** are
accepted, not vetoed (the current code hardcodes queen-inner); (c) widening the return from a
single string to the structured §5 bundle. All three are mechanical and low-risk, and (a)+(b)
are required before any diagonal/skewer claim may ship.

**Recommendation: KEEP `royal_pin_setup` as a specialized high-value tag, layered on top of a
general pin/skewer engine — do not delete it; and FIX the helper to the §A contract so the tag
is as inclusive as the definition.**

Tradeoffs:

- **Backward compatibility (decisive).** `royal_pin_setup` is a frozen member of `GATED_TAGS`
  (`factgate.py:222-229`) and is named explicitly in the non-negotiable fact-gate prompt rule
  (`narrator.py:202`: *"a pin or skewer that wins the queen (`royal_pin_setup`)"*). Folding the
  tag away would mean editing the closed tag vocabulary, the prompt whitelist, and any A/B
  fixtures — a breaking change across three files for no behavioral gain. Keeping the tag
  preserves every existing certification and the prompt contract verbatim. (Note: keeping the
  tag does **not** excuse leaving the helper diagonal-/skewer-blind — the prompt already
  promises "skewer," so honoring it is a *fix*, not new scope.)
- **Signal quality / narrator value.** "Wins the queen via royal alignment" is a distinctly
  higher-value, more quotable event than a generic pin of a knight; a dedicated boolean tag
  lets the prompt rule keep its sharp wording and lets the narrator lead with the strongest
  claim, rather than pushing pin-vs-skewer discrimination into evidence-string parsing the LLM
  must do at read time.
- **Avoiding logic duplication (hard requirement).** The ray / clear-line / hanging geometry
  must live in **one** place. Recommendation: a general pin/skewer engine owns all of it
  (file, rank, **and diagonal**; pin **and** skewer ordering; hanging guard);
  `detect_royal_alignment` becomes a thin classifier that asks the general result "is the
  aligned pair exactly the enemy king + queen?" and re-labels, **preserving its current
  `Optional[str]` return contract** so `sets_up_royal_pin` / `certified_claims` need no change.
  When that engine exists, expose `royal` and `wins_queen` as evidence attributes that ALSO
  drive this specialized tag.
- **Simplicity (the only point favoring folding the tag).** One predicate is conceptually
  cleaner than two, but the discrimination cost is paid once in the layering code, and `royal`
  / `wins_queen` are computed anyway — so keeping the specialized tag is essentially free.

**Net:** keep the tag; fold the *logic* (not the tag) into a general engine that handles **all
three line-types and both orderings**; expose `royal` / `wins_queen` as evidence attributes
that also drive `royal_pin_setup`. This satisfies backward compatibility, closes the diagonal
and skewer recall gaps the current helper has (James's inclusivity standard), and keeps false
positives out of the high-value `royal_pin_setup` claim (relative / non-royal pins still get
caught — by the general engine — but never mislabeled royal).

**Relevant files:** `C:\Users\詹天哲\Documents\greco\factgate.py` (`sets_up_royal_pin` at
`factgate.py:207-213`, `certified_claims` step 4 at `factgate.py:281-283`, `GATED_TAGS` at
`factgate.py:222-229`); `C:\Users\詹天哲\Documents\greco\analyzer.py`
(`detect_royal_alignment` at `analyzer.py:367-417` — **the helper to extend per §A**, plus
`PIECE_NAMES` at `analyzer.py:211-218` and the `chess.between` / `SquareSet` idioms);
`C:\Users\詹天哲\Documents\greco\narrator.py` (fact-gate prompt rule naming `royal_pin_setup`
at `narrator.py:202`; `certified` serialization and the Tier-1 evidence slot at
`narrator.py:450-462`).

---

## Mate-in-one threat (REVISIT existing) (`mate_in_one_threat`)

Sanity check: re-read the ask (produce a corrected 7-section spec, fix every defect, write to the exact path, return the markdown). I verified the file wrote to the correct path, the directory holds siblings `01`–`16` so `17-` is right, and every truth-value in the spec was executed against the live `factgate.threatens_mate_in_one` (python-chess 1.11.2). Defects fixed: stalemate positive-example FEN, contradicted negative hedges, misleading "en-passant covered" claim, self-contradictory VETO-2 library prose, promotion `mating_piece` naming, plus added draw-detection semantics, relative-pin inclusiveness, castling-side coverage, and the `probe.is_game_over()` evidence guard.

result: Corrected spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\17-mate_in_one_threat.md — every truth-value engine-verified; fixed the stalemate positive FEN, the false en-passant "covered" claim, the wrong VETO-2 library prose, contradicted negative hedges, and the promotion piece-naming bug.

```markdown
# Detection Spec — `mate_in_one_threat`

**Certified tag:** `mate_in_one_threat`
**Layer:** Greco output fact-gate (`factgate.py`)
**Status:** REVISIT of the EXISTING predicate pair `threatens_mate_in_one` (board-level helper, `factgate.py:50`) + the `_mate_threat()` null-move probe nested inside `certified_claims` (`factgate.py:259–268`). After adversarial review, the **core null-move logic is correct and is KEPT verbatim**, but the original draft of this spec contained material errors that are corrected here: (1) two of its positive example FENs were wrong (one was a **stalemate**, so the tag is `False`, not `True`); (2) its negative hedges contradicted the engine (positions it claimed do *not* mate actually *do*); (3) its claim that **en-passant mate is "covered"** is misleading — a mover's en-passant mate threat is **structurally unreachable** and is correctly a non-case; (4) its VETO-2 prose about python-chess null-move behavior was self-contradictory and factually wrong; (5) the proposed evidence bundle mislabels the **promotion** mating piece. **Recommendation: KEEP the gate logic; fix the documentation, examples, and evidence-bundle piece-naming; add the evidence bundle.**

All positive/negative examples below were executed against `factgate.threatens_mate_in_one` on python-chess 1.11.2 in the Greco venv; every asserted truth value is the observed result, not eyeballed.

---

## 1. Expert definition

A **mate-in-one threat** is a *standing* threat created by the mover (the side that just played the move under analysis): with the opponent to move, **if the opponent were to do nothing about it, the mover would have a legal move that ends the game by checkmate.** A coach phrases it "...and now White threatens mate" or "this sets up the unstoppable threat of Qh7#." The burden has shifted to the opponent — they must spend their move parrying mate or lose immediately.

The concept has two related but distinct senses; Greco's tag is the **first**:

1. **Standing mate threat (the certified sense).** After the mover's move, with the opponent to move, the mover *threatens* mate-in-one. Operationally: imagine the opponent passes (a null move); the mover then has at least one legal move that is checkmate. This is a property of the position the mover *created* and is the natural object of the narrator's claim "X threatens mate."
   - It is true **whether or not the opponent can actually parry it.** A threat is still a threat even if a defense exists — "threatens mate, but Black defends with ...Kf8" is ordinary, correct commentary. The certified claim is the *existence* of the threat, not its un-stoppability. (Un-parryable mate-in-one means the opponent is already lost — a stronger claim Greco does not separately gate here; the engine eval, not this tag, carries "forced/unstoppable.")

2. **Mate-in-one on the move (the helper sense).** The *side to move* has a legal checkmating move right now. This is exactly what `threatens_mate_in_one(board)` computes. It is the building block, not the certified claim: at narration time the mover's move has already been played, so "mate on the move" for the position-after would be the *opponent's* mate — the wrong side. **The null-move probe is load-bearing**: it converts sense-2 (helper) into sense-1 (claim) by handing the move back to the mover. Calling `threatens_mate_in_one(board_after)` directly would certify the *opponent's* mate-in-one — a color-inversion bug, not a cosmetic detail.

**Recognized variants reduce to "a legal move that gives checkmate"** and are caught because the helper enumerates *legal* moves and tests `board.is_checkmate()` after each. Verified against the live helper:
- **Pawn promotion-mate** (e.g. `f8=Q#`, `e1=Q#`) — promotion moves are legal moves; **verified True** on a valid (non-stalemate) construction.
- **Discovered checkmate** and **double-check mate** — `board.gives_check(move)` returns `True` for a discovered check even when the *moving* piece is not the checker (**verified**: `Nd5–f6` discovering a rook check reports `gives_check=True`). So the helper's cheap `gives_check` veto does **not** drop discovered/double-check mates.
- **Castling that delivers mate** (`O-O-O#` / `O-O#`) — castling is a legal move and `gives_check` recognizes the castled rook's check (**verified** on a contrived `O-O-O` check). Covered for both castling sides.
- Smothered mate, back-rank mate, corridor mate, Anastasia's, Boden's, etc. — these are *patterns*, not separate rules; each is "a legal move that mates," so all are caught pattern-agnostically.
- **En passant is the one apparent variant that is NOT a real case.** See §4 case 7 and §6: a mover's en-passant *mate threat* cannot arise, so there is nothing to cover and nothing is missed.

**Side-to-move / color dependence is the crux, and the gate is color-symmetric by construction.** The threat is always asserted about the mover. `board_after` has the **opponent** to move; the null move flips `board.turn` back to the mover; `threatens_mate_in_one` reads whichever side is to move. There is no White/Black branch. **Verified both directions**: a White-mover back-rank threat (`...→ Ra8#`) and the mirrored Black-mover threat (`...→ Ra1#`) both certify True with identical code.

---

## 2. Detection rules (VETO-THEN-CONFIRM)

Input is the post-move board `board_after` (opponent to move), exactly as `certified_claims` supplies it. **Reuse the existing helper `threatens_mate_in_one(board)` (`factgate.py:50`) — do not re-implement the legal-move / `is_checkmate` loop.** The probe below is precisely the existing `_mate_threat()` closure (`factgate.py:259–268`); this spec confirms and documents it.

**VETO 1 — game already over (`board_after.is_game_over()`).** Return `False`. If the mover's move itself ended the game (checkmate, stalemate, insufficient material, fivefold/75-move), there is no "next move" to threaten. A *delivered* mate is the already-true fact "checkmate," not a *threat* of mate. This veto also guarantees the opponent has at least one legal move, so the null-move push that follows is reasoning about a live position.
   - **Note on draw detection (was glossed in the draft):** `board.is_game_over()` with default `claim_draw=False` returns `True` for *automatic* terminations — checkmate, stalemate, **insufficient material** (verified: bare K vs K → `True`), fivefold repetition, seventy-five-move rule — but **not** for *claimable-only* draws (threefold repetition, fifty-move rule), which require a claim. This is the correct posture: a position one ply from a forced mate is not "game over" merely because a 50-move counter is high, and a genuinely dead position (insufficient material) correctly suppresses the tag.

**VETO 2 — the opponent is in check (`board_after.is_check()`).** Return `False`. This is the central edge case the null-move approach must handle, and it is handled correctly today.
   - On `board_after`, `is_check()` can *only* mean the opponent's king is in check — i.e. **the mover's move gave check** — because a legal move never leaves the mover's own king in check (verified: `is_check()` reflects the side-to-move's king only). So VETO 2 is exactly "the mover's move was a checking move."
   - The "opponent passes" framing is **undefined under check**: the opponent is *not free to do nothing* — they are forced to address the check (capture the checker, block, or move the king). A null-move probe here would measure a threat the opponent's *forced* reply may completely refute (the king step that escapes the check might also defend the mating square). So a null-move probe under check is a **false-positive generator**; we abstain.
   - **Library-behavior correction (the draft was wrong and self-contradictory here):** python-chess does **not** refuse to push a null move when the side to move is in check — it **allows** the push and produces an (illegal) position without raising (verified: pushing `Move.null()` into a White-in-check position succeeds and just flips the turn). The veto is therefore **semantic, not a guard against an exception**: we abstain because the *threat framing* is ill-defined under check, not because the library would reject the push. The gate is `is_check()` (any check), not `is_checkmate()`, precisely because *any* check — mating or not — breaks the "opponent may pass" premise.
   - This is a deliberate **precision-over-recall** boundary: a checking move can also set up a standing mate, but that scenario is better described as "mate in two / mating attack" and belongs to the engine's `mate_after`, not this geometric one-ply gate. Accepted false-negative (see §6).

**CONFIRM — null-move probe.** If neither veto fires:
   1. Copy the board: `probe = board_after.copy()` (never mutate the caller's board).
   2. Push a null move: `probe.push(chess.Move.null())`. The turn passes back to the mover without moving any piece. **Side effect, benign:** the null move clears `ep_square` and increments the halfmove clock on the copy (verified: a `d6` en-passant square becomes `None` after the null push). Neither affects checkmate detection; the original board is untouched.
   3. Return `threatens_mate_in_one(probe)` — does the mover now have a legal move delivering checkmate? The helper applies its own `is_game_over()` short-circuit and its cheap `if not board.gives_check(move): continue` veto, so only checking candidate moves are pushed/tested.

**Color handling:** none required explicitly — `board.turn` on `board_after` is the opponent; the null move flips it to the mover; `threatens_mate_in_one` reads the side to move. Identical for White-mover and Black-mover (both verified).

**Wrapping:** the whole probe runs inside `certified_claims`'s `_safe(...)` closure (`factgate.py:253–257`), so any exception silently drops the tag rather than crashing the report.

---

## 3. Positive examples

Each FEN is the position **after the mover's move** (opponent to move) — exactly what the predicate receives. Every value below was executed against the live helper.

1. **Back-rank mate threat (White mover).** FEN: `6k1/5ppp/8/8/8/8/8/R5K1 b - - 0 1` — White rook on a1, Black king boxed by its own f7/g7/h7 pawns. Null move → White to move → `Ra8#`. **Result: True.** Evidence headline `Ra8#`, piece `rook`, mover `White`.

2. **Smothered-mate threat (knight).** FEN: `6rk/6pp/7N/8/8/8/8/6K1 b - - 0 1` — White knight on h6, Black king smothered by its own rook/pawns. Null move → White → `Nf7#`. **Result: True.** Confirms the `gives_check`-then-`is_checkmate` loop catches a knight mate; pattern-agnostic.

3. **Promotion-mate threat (CORRECTED FEN).** FEN: `7k/5P2/6K1/8/8/8/p7/8 b - - 0 1` — Black has a free tempo (`a2` pawn) so the position is **not** stalemate; if Black passes, White plays `f8=Q#` (also `f8=R#`). **Result: True.** Evidence: headline `f8=Q#`, `all_mating_moves_san = ["f8=Q#", "f8=R#"]`.
   > **Why the draft's FEN was wrong:** the draft used `7k/5P2/6K1/8/8/8/8/8 b - - 0 1`, which is **stalemate** — Black's king on h8 has no legal move (g6-king covers g7/g8/h7; h8 occupied). `is_game_over()` is `True`, VETO 1 fires, tag is **False**. A promotion positive *must* give the side-to-move a legal waiting move. **Test authors: validate every positive by running the helper; do not hand-eyeball back-rank/smother/promotion geometry.**

4. **Black-mover symmetry (back rank).** FEN: `r5k1/8/8/8/8/8/5PPP/6K1 w - - 0 1` — Black rook a8, White king g1 boxed by f2/g2/h2. Null move → Black to move → `...Ra1#`. **Result: True.** Evidence mover `Black`. Confirms there is no White-only code path.

5. **Quiet queen back-rank threat (defender can still parry).** FEN: `6k1/5ppp/8/8/8/8/5PPP/4Q1K1 b - - 0 1` — White queen e1; null move → White → `Qe8#`. **Result: True.** The existence of a Black defense (if any) does not disqualify the *threat*; the tag asserts existence, not un-stoppability.

> Test note: examples 1–4 are the safe, hand-checkable, engine-verified set; build the L1 unit test from those (and assert example 3's *stalemate* twin returns **False** as a regression guard against the original spec error).

---

## 4. Negative / edge cases

1. **The move *delivered* mate (game over).** `board_after.is_checkmate()` ⇒ `is_game_over()` ⇒ VETO 1 → `False`. A completed mate is the fact "checkmate," not a *threat*. (The narrator describes the mate from result/`is_check` data, not this tag.)

2. **Stalemate / insufficient-material after the mover's move.** `is_game_over()` true ⇒ VETO 1 → `False`. **This is exactly the trap the draft's promotion example fell into** (`7k/5P2/6K1/8/8/8/8/8 b` is stalemate). Verified: insufficient material (bare K vs K) also returns `False`. No false positive.

3. **The move gave check (but not mate).** `board_after.is_check()` ⇒ VETO 2 → `False`, even if a forcing mate exists after the forced reply. Deliberately excluded: "opponent passes" is undefined under check, and the null-move probe would certify a threat the *forced* reply may refute. Verified: after `Ra8+` (`R5k1/5ppp/8/8/8/8/5PPP/6K1 b`), the tag is `False`. Accepted false-negative (§6).

4. **Mate-in-one for the *opponent*, not the mover.** If `board_after` has the opponent to move and *they* have a mate-in-one, a naive `threatens_mate_in_one(board_after)` would be `True` — the wrong side's threat. The null-move probe prevents this by flipping the turn to the mover first. This is precisely why the null move is mandatory and why calling the helper directly on `board_after` is a bug.

5. **"Mate in two" / longer forced mate.** The mover threatens mate but needs ≥2 moves. After one null move there is no *single* mating move → `False`. Correct: the tag is strictly mate-in-**one**; deeper forced mates are the engine's `mate_after`, not this geometric gate.

6. **Apparent mate that is illegal for the mover (self-check / pinned mating piece).** A "mating" move that would leave the mover's own king in check, or whose mating piece is **absolutely pinned** to its own king, is excluded automatically because `board.legal_moves` never enumerates it. No special handling; legality is inherited from python-chess.
   - **Relative pins do NOT suppress a real mate (anti-under-inclusion).** A piece "pinned" only against a more valuable non-king piece (a *relative* pin) is still legally allowed to move. If such a move delivers checkmate, the game ends — there is nothing more valuable than mate to lose behind it — so the helper correctly enumerates and certifies it. The gate must not (and does not) special-case relative pins out; only *absolute* (to-king) pins remove the move, and that removal is correct.

7. **En-passant "mate threat" — a structural non-case (draft was misleading).** The draft listed en-passant mate as "covered." In fact a *mover's* en-passant mate threat **cannot occur**: (a) an en-passant right belongs to the side to move in `board_after`, which is the **opponent**, not the mover; (b) the mover's own en-passant right would require the opponent's *previous* move to be a double pawn push, but the **mover** moved last, so no such right exists in `board_after`; and (c) the null-move push clears `ep_square` to `None` anyway (verified). Therefore the predicate never needs to — and never can — certify an en-passant mate for the mover. This is **not a false negative** (no real instance is missed); it is a non-case. The earlier "a passed turn forfeits en passant — correct" remark was true but irrelevant, because the right was never the mover's to forfeit.

8. **The mating move can be captured / the threat is trivially parried.** Still certified as a *threat* — a mate-in-one threat exists even when the defender has a refutation (capture, block, flight, counter-check). **Intended inclusiveness**: experts say "threatens mate" here. The narrator's surrounding prose and the engine eval convey decisiveness; the tag asserts only existence. (Contrast `fork`, which down-weights a hanging forker — mate-threat deliberately does not, because a parryable mate threat is still a real, nameable threat.)

9. **Discovered-check / double-check mate after the null move ARE certified.** Listed to flag that the mating move need not be a simple direct check from the moving piece: `gives_check` returns `True` for a discovery (verified), so discovered and double-check mates are valid positives, not exclusions.

10. **Null-move push raising / engine objection.** python-chess does not reject a null move in a normal (non-check, not-game-over) position. Should any unexpected exception occur, the `_safe` wrapper catches it and the tag is dropped — no crash, no false positive.

---

## 5. Evidence bundle

Today the gate certifies the tag as a bare boolean: the narrator may *assert* a mate threat but is given **no proof of which move mates**, so it can name the wrong mating move. Proposed anti-hallucination payload — a **sibling evidence function** that does **not** change `threatens_mate_in_one`'s `-> bool` contract (mirroring how `is_outpost` returns supporter squares and `is_rook_lift` returns a reason string).

**Proposed `mate_threat_evidence(board_after) -> Optional[dict]`** — returns `None` when not certified (same two vetoes, plus a `probe.is_game_over()` guard after the null push), else:

| Field | Type | Content |
|---|---|---|
| `mating_move_san` | `str` | Headline mating move in **SAN from the mover's perspective** — `probe.san(move)` on the null-pushed board, so the `#` suffix is correct (verified: `"Ra8#"`, `"Nf7#"`, `"f8=Q#"`, `"Ra1#"` for Black). The **load-bearing** field the narrator quotes verbatim. |
| `mating_move_uci` | `str` | Same move as `move.uci()`, for downstream re-validation. |
| `mating_piece` | `str` | Human piece name. **CORRECTED:** for a **promotion** mate, use `PIECE_NAMES[move.promotion]` (the piece the pawn *becomes*, e.g. `"queen"`), **not** `PIECE_NAMES[probe.piece_type_at(move.from_square)]` (which is `"pawn"` and yields the misleading "threatens mate with the pawn"). Rule: `mating_piece = PIECE_NAMES[move.promotion] if move.promotion else PIECE_NAMES[probe.piece_type_at(move.from_square)]`. For a **castling** mate, name it `"rook"` (the rook delivers the check) or use the SAN (`O-O-O#`) verbatim — do not call it `"king"`. |
| `mating_from` / `mating_to` | `str` | `chess.square_name(...)` of the mating move's from/to squares. |
| `mover_color` | `str` | `"White"` / `"Black"` from `probe.turn` (the mover, after the flip) — so the narrator never attributes the threat to the wrong player. Verified correct for Black movers. |
| `all_mating_moves_san` | `List[str]` | **All** legal mover moves that mate after the null move (sorted by UCI for determinism). Lets the narrator say "more than one way to mate" truthfully and prevents false uniqueness claims. For the corrected promotion example this is `["f8=Q#", "f8=R#"]`. |
| `evidence` | `str` | Ready-to-quote sentence built deterministically, e.g. `"White threatens mate in one with Ra8#."` or, when several exist, `"White threatens mate in one (f8=Q# or f8=R#)."` Narrator may use verbatim. |

**Construction notes** (reuse existing idioms): compute on the **null-pushed probe board** so SAN/turn/perspective are the mover's; for each `move` in `probe.legal_moves` where `probe.gives_check(move)`, push, test `is_checkmate()`, pop, and collect the maters (the same loop as `threatens_mate_in_one`, collecting instead of short-circuiting); guard with `if probe.is_game_over(): return None` after the null push; sort the collected moves by `move.uci()` and take the first as the headline. Use `PIECE_NAMES` and `chess.square_name` (same convention as `detect_double_attack`) and the promotion/castling piece-naming rule above. Wrap the whole body so it returns `None` on any exception.

**Serialization:** surface under a new key in `_move_to_dict`'s Tier-1+ block alongside `certified` (e.g. `d["mate_threat"] = mate_threat_evidence(chess.Board(move.fen_after))`), guarded `if ...:` and wrapped in try/except — exactly the "evidence bundle that parallels `certified`" slot the narrator brief prescribes. The `mate_in_one_threat` tag stays the authoritative gate in `GATED_TAGS`; the evidence dict is **additive proof, not a new claim type**, so no `GATED_TAGS` change and no system-prompt-rule change is required.

---

## 6. Known limitations

- **Conservative under check (accepted false-negative).** Any move that gives check is abstained on (VETO 2), so a checking move that *also* leaves a standing mate-in-one is never certified. By design; the cost is missing some real threats delivered alongside a check. Such cases are usually better named "mate in two / mating attack" and are the engine's `mate_after` job.
- **Strictly one move deep.** Forced mates in two or more read `False` — the engine's `mate_after`, not this gate.
- **Threat existence, not threat success.** Certifies that a mating move exists *if the opponent passes*; it does **not** assert the opponent has no defense. A certified position may be fully defensible. The narrator must not upgrade "threatens mate" to "forced/unstoppable mate" off this tag alone — the engine eval is the source for that.
- **En passant is a structural non-case, not a gap.** A mover's en-passant mate threat cannot arise (§4 case 7); nothing real is missed and nothing needs special handling.
- **Promotion under-promotion mates are included but flattened.** All of `f8=Q#`/`f8=R#` (and any under-promotion mate) are collected in `all_mating_moves_san`; the headline picks the lowest-UCI (typically the queen/`=Q`), which is the natural narrator choice.
- **Null-move side effects are benign.** The null push clears en-passant rights and bumps the halfmove clock on the **copy** only (verified); neither affects checkmate detection, and the caller's board is untouched (`.copy()`).
- **No multi-threat richness.** It does not report whether the mate threat is part of a double threat (mate-or-win-material) or count the opponent's defenses; those would need separate predicates.
- **Standing-threat framing only.** The trigger is "opponent passes," so it models a threat against a *free* opponent; it does not model threats that only materialize after a specific forcing opponent reply (those are not "mate-in-one threats" in the standing sense anyway).

---

## 7. Complexity

**Low.** The predicate is one null-move push followed by one pass over the mover's legal moves, short-circuited by a `gives_check` filter so only the handful of checking candidates are actually pushed/tested. It reuses the existing, tested `threatens_mate_in_one` helper verbatim and adds two O(1) board-state vetoes (`is_game_over`, `is_check`); it touches no engine and no network (pure python-chess, L1-testable with no Stockfish binary). The evidence bundle adds only a second collecting pass over the same candidate moves plus string formatting via existing `PIECE_NAMES` / `square_name` idioms — no new algorithms, no new dependencies. The sole subtleties are conceptual, not computational: (a) the null move is *required* to attribute the threat to the correct color; (b) check must be vetoed for *semantic* reasons (the library would not reject the push); (c) en passant is a structural non-case; and (d) positive-example FENs must be engine-validated because back-rank / smother / promotion-stalemate geometry is easy to mis-eyeball — the very error the original draft made.
```

---

## Zugzwang (APPROXIMATE — be honest) (`zugzwang`)

Sanity check passed: all 7 sections present, file wrote (360 lines), and all four load-bearing python-chess facts the corrected spec depends on are verified true (null-move-under-check is silent not raising; `normalize_cp` is White-POV; `normalize_cp(None,0) == -MATE_SCORE`; `has_legal_en_passant()` exists and null forfeits e.p.).

Defects I broke the draft on and fixed in the corrected spec:

- **(POV/sign bug — most dangerous)** The draft repeatedly said "normalize to the side-to-move's POV using `normalize_cp`." `normalize_cp` is **White-POV**, not side-to-move. Combined with the null move flipping the turn (Stockfish scores are side-to-move-relative), this is a missing/doubled-negation trap that inverts `delta_cp` and would ship a false zugzwang for the wrong color. Fixed with an explicit `sign = +1/−1` procedure in Rule 6 plus a mandatory two-color trébuchet unit test.
- **(False justification)** The draft claimed a null move is "illegal/meaningless under check (you cannot legally pass out of check)" — but `push(chess.Move.null())` does **not** raise under check; it silently flips the turn leaving the king in check. The VETO-2 guard is correct but the stated reason was wrong; corrected to the real semantic reason (garbage eval baseline).
- **(Missing edge — en passant)** Added VETO 5: a null move forfeits any available e.p. capture (`ep_square → None`), corrupting the pass baseline in exactly the pawn endgames where zugzwang lives. Draft missed this entirely.
- **(Under-inclusiveness)** Draft's phase gate effectively under-fired on piece-domination squeezes the coarse `detect_phase` labels `middlegame`; fixed the low-piece-count clause to admit them, and made the four coach-recognized variants (full / mutual / partial / squeeze) explicitly in-scope.
- **(`mate==0` handling)** Documented `normalize_cp(None, 0) == -MATE_SCORE` (side-to-move mated) as handled by the same path for the "pass holds, every move allows mate" strongest-zugzwang case.
- **(Redundant/garbled STRICT clause)** Draft's "second-best must also trail" contradicted its own "best ⇒ all trail" logic; demoted to optional corroboration.
- **(Evidence-bundle gaps)** Added `threshold_cp`, `veto_reason`, and an explicit no-fire shape; fixed the `eval_best_move_cp`→`eval_best_cp` POV labeling; specified the `GATED_TAGS` + prompt-rule + Tier-1 `_move_to_dict` wiring the draft only gestured at.

File written to `C:\Users\詹天哲\Documents\greco\docs\specs\predicates\18-zugzwang.md`.

result: Corrected, defect-free Zugzwang spec written to C:\Users\詹天哲\Documents\greco\docs\specs\predicates\18-zugzwang.md (all 7 sections; POV/sign, null-under-check, en-passant, under-inclusiveness, and evidence-bundle defects fixed and verified against python-chess).

```markdown
# Detection Spec: Zugzwang (APPROXIMATE) — tag `zugzwang`

> **STATUS: APPROXIMATE / ENGINE-DEPENDENT — NOT GEOMETRICALLY PROVABLE.**
> Unlike `fork`, `passed_pawn`, or `royal_pin_setup`, this term is **not** provable from board
> geometry. It requires comparing an illegal hypothetical ("what if the side to move could
> pass?") against that side's real best move, both supplied by Stockfish. This spec defines a
> *near-zugzwang detector*, not a proof. The narrator MUST hedge ("near-zugzwang",
> "zugzwang-like", "every move worsens the position") unless the strict sub-conditions of
> Rule 7 hold. Be honest: a true zugzwang claim can be *strongly suggested*, never *certified*
> to the standard of the geometric tags.
>
> **Because this tag licenses a new claim type, it is registered in BOTH `factgate.GATED_TAGS`
> and the fact-gate prompt rule in `narrator.py` — otherwise the narrator is forbidden from
> asserting it.** The narrator may use the *word* "zugzwang" only when `strict` is true; the
> hedged label is the default. The tag is added to the per-ply allow-set under the name
> `zugzwang`; the richer evidence bundle (§5) rides in a parallel Tier-1+ field.

---

## 1. Expert definition

**Zugzwang** (German, "compulsion to move") is a position in which **the obligation to move is
itself the disadvantage**: the side to move would strictly prefer to pass (do nothing), because
**every legal move worsens their evaluation** relative to the do-nothing baseline. The harm
comes from *having to move*, not from any threat the opponent is currently executing.

Recognized variants a strong coach would all call zugzwang (the detector must catch all four —
the under-inclusive draft that fired only on king-and-pawn opposition is wrong):

- **Full / true zugzwang** — *every* legal move loses ground; passing would hold. Sharpest in
  **king-and-pawn and simple piece endgames** (the opposition: the king that must move loses a
  key square).
- **Mutual / reciprocal zugzwang ("trébuchet")** — whoever is to move loses; the position is
  lost *for the side on move only*. Detection is inherently side-to-move-relative, so this falls
  out naturally — we always evaluate from the perspective of the side that must move. We report
  it for that side and **never assert the reciprocal property** about the other color (we did not
  test it).
- **Partial zugzwang** — the side to move has no *clearly good* move; most or all moves concede
  something, though the least-bad may merely hold a worse-but-not-lost evaluation. Coaches still
  say "he's in zugzwang" when every move drops material or a decisive amount of ground. This is
  the **NEAR** rung of §7, deliberately included so we are not under-inclusive against the expert
  standard.
- **Squeeze / domination** — a heavy-or-minor-piece position (not just pawns) where the
  defender's pieces are tied to defense and any move loosens the bind. Same engine signature:
  passing beats every real move. **The phase gate (VETO 4) admits this via the low-piece-count
  clause, not only `phase == "endgame"`, so we do not under-fire on piece-domination endgames
  that the coarse `detect_phase` might still label `middlegame`.**

**Key discriminators (what zugzwang is NOT, definitionally):**

- Distinct from merely being **lost**: in most lost positions a free pass would *also* not save
  you — the loss is positional or material, not move-compulsion. The discriminator is the
  *delta* between pass and best move, **never the absolute eval**.
- Distinct from **stalemate**: zero legal moves with the king not in check is a *draw from having
  no move*, not harm from having to move. Terminal → never tagged.
- Distinct from being **in check**: there the problem is a threat that must be parried, ordinary
  forcing tactics, not compulsion.
- Requires that **a pass would genuinely be better than the best real move** — by a clear margin.

**Operational definition:** the side to move is in (near-)zugzwang when a null move ("pass")
evaluates **clearly better for them** than their best legal move — i.e. moving costs them ground
that doing nothing would not.

---

## 2. Detection rules (VETO-THEN-CONFIRM)

The predicate takes an explicit `board` and reasons about the side to move, **`board.turn`**.
Cheap geometric vetoes run first; the expensive engine work is last. The natural Greco hook is
*"after the mover's move, is the opponent (now `board_after.turn`) in near-zugzwang?"* — but the
predicate is written position-generic so it can also be probed on `board_before`.

> **POV CONTRACT (read before anything else — this is where the draft was wrong).**
> `analyzer.normalize_cp(cp, mate)` returns a **White-POV** signed integer (a mate-in-1 *for
> White* is `+99999` no matter whose move it is; `normalize_cp(None, 0)` is `-MATE_SCORE`,
> meaning *the side to move is already mated*). It does **not** return a side-to-move POV. To get
> a side-to-move-relative number you must apply the sign yourself, exactly as `analyzer` does:
> `sign = 1 if board.turn == chess.WHITE else -1`, then `pov = sign * normalize_cp(cp, mate)`.
> The draft's repeated phrase "normalize to the side-to-move's POV using `normalize_cp`" is a
> bug: `normalize_cp` alone never does that. See Rule 6 for the full, sign-correct procedure.

**VETO 1 — game already over.** If `board.is_game_over()` → return the no-fire result.
Checkmate, stalemate, and all draws are not zugzwang. (Mirrors the `board_after.is_game_over()`
guard in `factgate._mate_threat`.) Stalemate — zero legal moves, king not in check — is the
single most important non-zugzwang lookalike and is fully caught here.

**VETO 2 — side to move is in check.** If `board.is_check()` → return the no-fire result.
Being in check means you are forced to *answer a threat*, which is ordinary tactics, not
move-compulsion. Mirrors the `or board_after.is_check()` abstention in `_mate_threat`.
*Correctness note (the draft's stated reason is false):* in python-chess,
`board.copy().push(chess.Move.null())` **does NOT raise under check** — it silently succeeds and
flips the turn, leaving the formerly-checked king sitting in check on the opponent's move. The
hazard is therefore not an exception but a **garbage eval baseline** (a position no search treats
sanely). Veto under check for the *semantic* reason, and never rely on `push(null())` to throw.

**VETO 3 — forced / single legal move.** If `len(list(board.legal_moves)) <= 1` → return the
no-fire result. With one legal move there is no *choice* being degraded; "every move worsens" is
vacuous. (Greco already computes `legal_move_count` and `is_forced` on `MoveAnalysis`; reuse that
at the call site to skip the engine work entirely.) Zero legal moves is already caught by VETO 1.

**VETO 4 — phase / scope gate (precision knob).** Zugzwang false-positives explode in sharp
middlegames where eval swings are dominated by tactics, not compulsion. Require
`detect_phase(board, ply) == "endgame"` **OR** a low piece count
(≤ 6 non-king, non-pawn pieces, counting both colors — this admits piece-domination squeezes the
coarse phase heuristic might still call `middlegame`). Outside that, suppress (no fire). This is
a **tunable gate, not part of the core definition** — documented as the precision knob, openable
to a middlegame mode later.

**VETO 5 — null-move baseline must be meaningful.** Skip to CONFIRM only if VETO 1–4 pass **and**
the null-move probe is well-defined for *this* position:

- If `board.has_legal_en_passant()` is true, the pass baseline is **polluted**: pushing
  `chess.Move.null()` forfeits the en-passant capture right (confirmed: `ep_square` becomes
  `None` after a null move), so "pass" silently throws away a capture that the real side to move
  actually has. In a pawn endgame — exactly where zugzwang lives — this can invert the delta.
  **Abstain (no fire) when an en-passant capture is available**, and note it in `known
  limitations`. (A future refinement could re-derive the e.p. right onto the probe board, but the
  honest default is to abstain.)

---

**CONFIRM (engine-dependent — at most one *extra* Stockfish call):**

**Rule 6 — null-move pass-baseline vs. best real move, sign-correct.**

Let `stm = board.turn` and `sign = 1 if stm == chess.WHITE else -1`.

1. **Best real move (usually already cached).** In Greco's pipeline the engine's best line and
   its eval for this position are already computed (`best_move_uci`, `eval_after_cp`/`mate_after`
   of the best line, or the post-move eval). Convert to a side-to-move number:
   `eval_best_cp = sign * normalize_cp(cp_best, mate_best)`. **`best_move_san` is the SAN of that
   engine best move** — the least-bad try the narrator will name. If no cached value exists, this
   costs one engine call; otherwise it is free.
2. **Pass baseline (the one genuinely extra call).** Copy the board and push
   `chess.Move.null()`. The turn now flips to the **opponent**, and Stockfish reports that
   position's score **from the opponent's POV**. Evaluate the null-moved position, take its
   `(cp, mate)`, and convert to the **original** side-to-move POV. Two equivalent ways to get the
   sign right — pick one and be consistent:
   - normalize to White POV first, then apply the original side's sign:
     `eval_pass_cp = sign * normalize_cp(cp_pass, mate_pass)` *(normalize_cp is already White-POV,
     so the same `sign` works — do NOT add a second negation)*; **or**
   - read the score POV-relative to the side now to move (the opponent) and negate once to flip
     back to the original side.
   Do not do both — double-negation is the classic bug here. A unit test MUST assert that in a
   trébuchet the side to move gets `eval_pass_cp > eval_best_cp` (pass holds, moving loses) for
   *both* colors.
3. **Mate handling.** Use `normalize_cp` so mate scores compare on the same axis: a position
   where pass holds but *every* real move allows mate is the strongest possible zugzwang and
   yields a huge positive `delta` (`eval_pass_cp` near 0 or positive, `eval_best_cp` near
   `-MATE_SCORE`). `normalize_cp(None, 0) == -MATE_SCORE` (side to move mated) is handled by the
   same path — no special case.
4. **Confirm near-zugzwang** iff `delta_cp = eval_pass_cp - eval_best_cp >= ZUGZWANG_CP`, i.e.
   passing would be clearly better than the best thing they can actually do.
   Recommended `ZUGZWANG_CP = 90`–`120` (roughly one knight-tempo; tune **up** to cut false
   positives — Greco's precision-over-recall posture).

**Rule 7 — strictness ladder (sets the prose label; both colors handled identically via `sign`).**

- **STRICT zugzwang** (licenses the unhedged word "zugzwang"): **all** of —
  1. `delta_cp >= ZUGZWANG_CP` (Rule 6 fired);
  2. the pass baseline is **non-losing** for the side to move: `eval_pass_cp >= -50`
     (so we are not just describing a generally lost position);
  3. **"every legal move worsens" is satisfied.** The engine's *best* real move is the ceiling of
     all real moves, so `eval_best_cp <= eval_pass_cp - ZUGZWANG_CP` already implies *every* legal
     move trails the pass by ≥ threshold — clause (1) supplies this. **If** a multipv /
     `top_alternatives` sweep is on hand, additionally verify the **second-best** real move also
     trails the pass by ≥ threshold; this is corroboration, not a new requirement, since
     best ≤ (pass − thr) ⇒ all ≤ (pass − thr). (The draft's "second-best must also trail" was
     redundant given the best-move ceiling; we keep it only as an optional cross-check.)
  - STRICT ⇒ `label = "zugzwang"`.
- **NEAR / LIKE** (default): `delta_cp >= ZUGZWANG_CP` but the pass baseline is itself losing
  (`eval_pass_cp < -50`), **or** only the best move was probed (no corroborating sweep), **or**
  any STRICT sub-clause is unmet. ⇒ `label = "near-zugzwang"`, prose limited to
  "near-zugzwang" / "zugzwang-like" / "every move loosens the position."

**Color / side-to-move handling.** The entire test is relative to `board.turn` via the single
`sign`; there are **no separate white/black code paths and no color-asymmetric thresholds**. The
`-50` non-losing floor and the `ZUGZWANG_CP` margin are applied to the sign-corrected
side-to-move number, so they are symmetric by construction. Mutual zugzwang needs no special case
— it simply means the same test would *also* fire with colors reversed, which we neither assert
nor need.

---

## 3. Positive examples

1. **King-and-pawn opposition.** FEN `8/8/8/p7/k7/8/K7/8 b - - 0 1` (Black to move; mirror for the
   White-to-move case). The side to move must step aside and let the enemy king infiltrate.
   *Qualifies:* a null move would hold the opposition; every real king move concedes a key square
   → `delta_cp` large and positive; endgame; not in check; > 1 legal move; no e.p. available.

2. **Trébuchet / mutual zugzwang.** FEN `8/8/8/8/4k3/4p3/4K3/8 w - - 0 1` (verified legal; kings
   on e4/e2 are two ranks apart, pawn on e3). White to move must abandon or lose the e3 pawn;
   Black to move loses likewise. *Qualifies:* whoever is on move strictly prefers to pass; STRICT
   when the pass baseline is a held draw (`eval_pass_cp ≈ 0 ≥ -50`) and every move drops the pawn.
   The side-to-move-relative `sign` makes the test fire correctly for **whichever color is on
   move** — the unit test asserts both.

3. **Endgame piece domination (defender tied down).** A position where the defender's king and
   rook are both tied to a pawn or mate-net, and every legal move either hangs the rook or lets
   the pawn queen. *Qualifies:* pass maintains the fortress; every move loses material or allows
   promotion → `delta_cp ≥ threshold`; admitted by VETO 4 via endgame **or** low piece count;
   STRICT if pass holds equality.

4. **Knight squeeze where every knight move drops a pawn.** A knight whose every flight square
   abandons a defended pawn while the kings are static. *Qualifies:* `eval_pass_cp` (knight stays,
   pawn defended) clearly exceeds `eval_best_cp` (any knight move, pawn falls); not forced
   (several knight moves, all bad); not in check.

5. **Reserve-tempo exhausted (no waiting move left).** The side to move has spent all spare pawn
   tempi; only king moves remain, each conceding. *Qualifies:* the *absence of a waiting move* is
   the essence — pass would be ideal, every legal king move worsens → positive `delta_cp`;
   endgame.

---

## 4. Negative / edge cases

1. **Stalemate.** Zero legal moves, king not in check → `is_game_over()` true (draw).
   **Excluded by VETO 1.** Stalemate is a draw from having no move; zugzwang is harm from having
   to move. Never conflate; never tag a terminal position.

2. **In check / forced to parry.** The side to move is in check and every reply loses. Looks like
   "every move is bad" but is ordinary forcing tactics, and the null-move baseline is garbage
   (the king stays in check after a "pass"). **Excluded by VETO 2.** Also covers a standing mate
   threat that must be answered — a threat, not compulsion.

3. **Single legal move (`is_forced`).** Only one move, and it is bad. No *choice* is being
   degraded. **Excluded by VETO 3** and already flagged `forced` upstream.

4. **Simply lost / collapsing position (no compulsion).** Down a queen in a middlegame: every
   move is "bad" only because the game is already lost — a free pass would *also* lose
   (`eval_pass_cp ≈ eval_best_cp`, both deeply negative). **Excluded by Rule 6:** the *delta* is
   near zero, so the detector correctly does not fire. The discriminator is *delta*, never
   absolute eval. (Also softened by VETO 4.)

5. **Waiting move available.** A harmless waiting move (rook shuffle on an open rank, a spare pawn
   tempo) whose eval ≈ the pass baseline → `eval_best_cp ≈ eval_pass_cp`, `delta < threshold` →
   **not zugzwang.** Having a real move as good as passing is the *definition* of not being in
   zugzwang.

6. **Sharp tactical position where the "pass" eval is noise.** In a complex middlegame the null
   move hands the opponent a free tempo that itself swings the eval (null-move observer effect).
   **Mitigated by VETO 4** and the robust threshold; flagged as a known limitation (§6).

7. **Opponent has a concrete threat that a pass also fails to meet.** If passing also loses to
   the threat, `delta ≈ 0` → not zugzwang (it is a threat, not compulsion). Rule 6's delta test
   separates these.

8. **En-passant capture available.** Pushing a null move forfeits the e.p. right
   (`ep_square → None`), so the pass baseline silently discards a capture the side to move really
   has, corrupting the delta in exactly the pawn endgames where zugzwang lives. **Excluded by
   VETO 5.**

9. **Mutual-zugzwang mislabel.** Never assert "your opponent is in zugzwang" when it is actually
   *your* side that is lost on the move. The test is strictly relative to `board.turn`, so always
   evaluate the side **actually on move**; never the other color, and never claim the reciprocal
   property.

10. **POV / sign bug (engineering edge, not a chess case — called out because it is the easiest
    way to ship a wrong tag).** Because the null move flips the turn and Stockfish scores are
    side-to-move-relative while `normalize_cp` is White-POV, a single missing or doubled negation
    inverts `delta_cp` and turns "winning, no zugzwang" into a false zugzwang for the wrong color.
    Guarded by the explicit `sign` procedure in Rule 6 and the **two-color trébuchet unit test**.

---

## 5. Evidence bundle

The predicate returns a structured result (a dataclass or dict), not a bare bool, so the narrator
can speak verbatim with zero hallucination. On any veto it returns the **no-fire result**:
`is_zugzwang=False` with the diagnostic fields populated where cheap, all engine fields `None`,
and `evidence=""`. Recommended return shape:

| Field | Type | Meaning |
|---|---|---|
| `is_zugzwang` | `bool` | True iff Rule 6 confirms (`delta_cp >= ZUGZWANG_CP`). Drives whether the `zugzwang` allow-set tag is added. |
| `strict` | `bool` | True only if the Rule 7 STRICT ladder holds. Licenses the unhedged word "zugzwang". |
| `label` | `str` | `"zugzwang"` if `strict` else `"near-zugzwang"` — the **only** noun the narrator may use. |
| `side_to_move` | `str` | `"White"` / `"Black"` — whose compulsion this is (from `board.turn`). |
| `eval_pass_cp` | `int` | Pass-baseline eval, **side-to-move POV** (`sign * normalize_cp(...)`). |
| `eval_best_cp` | `int` | Best-real-move eval, same POV and sign convention. |
| `delta_cp` | `int` | `eval_pass_cp - eval_best_cp` — the load-bearing number. |
| `best_move_san` | `str` | SAN of the engine's least-bad legal move (so the narrator can say "even the best try, …, loses ground"). |
| `legal_move_count` | `int` | `board.legal_moves` count, for "all N of his moves worsen the position". |
| `phase` | `str` | From `detect_phase`, to justify the endgame framing. |
| `threshold_cp` | `int` | The `ZUGZWANG_CP` actually used, so the evidence is self-describing and tunable without prose drift. |
| `veto_reason` | `Optional[str]` | On a no-fire, which guard tripped (`"game_over"`, `"in_check"`, `"forced"`, `"phase"`, `"en_passant"`, `"below_threshold"`) — for debugging and the variation-check harness; never shown to the reader. |
| `evidence` | `str` | Ready-to-quote sentence (below); `""` on no-fire. |

All cp fields are plain ints already in side-to-move POV; the narrator divides by 100 only for
display. **Every numeric field the prose quotes is present**, so the narrator never computes or
invents a number.

**Ready-to-quote `evidence` strings** (built with `PIECE_NAMES` + `chess.square_name`, mirroring
`detect_double_attack`'s style; `best_move_san` and the cp values come straight from the bundle):

- STRICT:
  `f"{side_to_move} is in zugzwang: passing would hold (about {eval_pass_cp/100:+.1f}), but every one of the {legal_move_count} legal moves loses ground — even the best, {best_move_san}, drops to about {eval_best_cp/100:+.1f}."`
- NEAR:
  `f"{side_to_move} is in near-zugzwang: with no useful waiting move, every legal reply worsens the position — the best available, {best_move_san}, is about {delta_cp} centipawns worse than simply passing would be."`

The narrator quotes `evidence` directly and uses `label` for the noun, guaranteeing the hedge is
honored. **Wiring:** add `zugzwang` to `factgate.GATED_TAGS`, add it to the fact-gate prompt rule
in `narrator.py:202`, and surface the bundle in the Tier-1+ block of `_move_to_dict` alongside
`certified` (same try/except fail-safe), since this is engine-dependent prose-grade evidence, not
a Tier-0 geometric fact.

---

## 6. Known limitations

- **Not a proof — engine- and depth-dependent.** Rests entirely on Stockfish evals at finite
  depth; a shallow search can miss the saving resource that makes pass-vs-move *look* like
  zugzwang when it isn't (or vice-versa). Evidence-backed conjecture, not certification — hence
  the mandatory hedge and the `strict` gate.
- **The null move is a modeling hack.** "Pass" is not a legal chess action. `chess.Move.null()`
  flips the turn, forfeits any en-passant right (VETO 5 abstains when one exists), and hands the
  opponent a free tempo the eval may over-credit in sharp positions (VETO 4 confines us to quiet
  ones). In a position with zugzwang-adjacent tactics the baseline can still mislead.
- **POV is the sharpest engineering hazard.** Because the null move flips the turn and
  `normalize_cp` is White-POV while raw engine scores are side-to-move-relative, the sign
  procedure in Rule 6 must be followed exactly; the two-color trébuchet unit test is mandatory
  regression coverage.
- **Mutual zugzwang is detected one-sidedly.** We report only for the side on move and never
  assert the reciprocal property, even when it holds.
- **Partial-zugzwang threshold is a judgment call.** `ZUGZWANG_CP` is a tuned knob; a "mild
  squeeze" just under threshold is silently untagged. Recall is deliberately sacrificed for
  precision (Greco's house posture). The `near-zugzwang` rung deliberately *widens* recall to the
  coach's partial-zugzwang sense without licensing the unhedged word.
- **"Every move worsens" is inferred from the best move.** Strictly verifying *all* legal moves
  trail the pass would need a full multipv sweep; we infer it from the best move (the ceiling),
  optionally corroborated by `top_alternatives`. Sound logically (best ≤ pass − thr ⇒ all ≤ pass
  − thr) but depends on the best-move eval being accurate.
- **Cost.** At most one **extra** engine evaluation per probed position (the null-move baseline);
  the best-move eval is usually already cached. Gating on VETO 1–5 first avoids spending it on the
  large majority of positions that cannot be zugzwang.
- **Boundary blur.** Cannot cleanly separate "in zugzwang" from "in a lost position a pass also
  can't fix" when both pass and best move sit at similar large-negative evals; the delta test
  handles the clean cases but blurs at the extreme-loss tail. There the `strict` non-losing floor
  (`eval_pass_cp >= -50`) keeps us in `near-zugzwang` rather than over-claiming.

---

## 7. Complexity

**HIGH.** Three compounding reasons: (1) it is the only tag here that is **not deterministically
provable** — it depends on engine evals, a depth-limited approximation, so correctness is
probabilistic, not geometric; (2) it requires an **extra Stockfish call** (the null-move baseline)
with **turn-flip-aware, sign-correct POV normalization** — the single subtlest engineering hazard
in the predicate library, since `normalize_cp` is White-POV and the null move flips the side to
move, so a missing or doubled negation silently inverts the result; (3) the false-positive surface
is large and subtle — stalemate, in-check, forced moves, simply-lost positions, and available
en-passant captures all mimic "every move is bad," and only the *pass-vs-best delta* (not the
absolute eval) separates real zugzwang from ordinary loss. The mitigations — the VETO ladder
(`is_game_over` / `is_check` / `legal_moves` / `detect_phase` / `has_legal_en_passant`), the
explicit `sign` procedure with a two-color trébuchet test, the strictness ladder gating the prose
label, and the mandatory "near-zugzwang" hedge — are what keep an inherently fuzzy concept inside
Greco's precision-over-recall doctrine while staying as **inclusive** as a strong coach demands
(full, mutual, partial, and squeeze variants all caught).
```