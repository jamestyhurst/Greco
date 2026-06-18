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
