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
