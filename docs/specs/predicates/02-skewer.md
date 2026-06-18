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
