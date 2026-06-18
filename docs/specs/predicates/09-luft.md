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
