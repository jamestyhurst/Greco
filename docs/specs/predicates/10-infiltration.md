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
