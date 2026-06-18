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
