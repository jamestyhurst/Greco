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
