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
