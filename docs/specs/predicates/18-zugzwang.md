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
