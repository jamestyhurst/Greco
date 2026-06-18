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
