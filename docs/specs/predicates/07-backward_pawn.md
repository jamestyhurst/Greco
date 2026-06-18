# Detection Spec — "Backward Pawn" (tag: `backward_pawn`)

> Status: corrected after adversarial review. This version fixes the
> stop-square attacker geometry (the `attackers`/turn-flip contradiction),
> the over-broad home-rank veto (a false negative), the vacuous-truth
> edge-file veto hole (a false positive), the "any level/behind neighbour
> kills it" under-inclusiveness (the central false negative against an
> expert's standard — a *fixed* level neighbour cannot actually support),
> the pin/side-to-move independence requirement, and the evidence bundle
> (adds subtype, blocked, two-square-leap, and doubled fields).

## 1. Expert definition

A **backward pawn** is a pawn that has fallen behind the pawns on its adjacent files and **cannot safely advance to rejoin them**, because:

- it is **rear-most relative to the friendly pawns on its neighbouring file(s)** — every neighbouring friendly pawn that could ever shield its advance has already moved past it, and pawns cannot retreat to come back *beside* it; **and**
- its **stop square** (the square one rank in front of it, where it would land on a one-step push) is **controlled by an enemy pawn**, so a single push just loses the pawn or concedes a hole; **and**
- **no friendly pawn can in fact be brought up alongside** to defend that advance — either there is no candidate supporter, or every candidate supporter is itself unable to reach the supporting square (already past it, or blocked, or its own path is enemy-pawn-controlled).

The defining trio is therefore: **rear-most on its file relative to its neighbour(s)**, **advance-square covered by an enemy pawn**, and **genuinely un-supportable by a friendly pawn**. Such a pawn is chronically stuck and becomes a long-term weakness.

**Recognized variants / nuances a strong coach includes:**

- **Half-open-file backward pawn (the textbook case).** The file in front of the pawn is half-open for the opponent (the enemy has no pawn on that file), so the enemy piles rooks/queen on it and the pawn is a fixed target — the d6 pawn in many Sicilian/King's-Indian structures, the e6/d6 backward pawns, the c-pawn in Maróczy-type structures. **Masters treat the half-open file as a near-defining accompaniment, but it is a *consequence*, not part of the core geometry.** A pawn can be backward even with an enemy pawn still in front of it (a "closed" or "blocked" backward pawn) — simply less of a target. **Decision (see §2): we REQUIRE enemy-pawn control of the stop square but do NOT require the file to be half-open.** Half-open status is computed and reported as strong corroborating evidence; gating on it would wrongly *exclude* genuine closed-structure backward pawns (a false negative against expert usage). When the stop square is controlled but the file is **blocked by an enemy pawn directly in front** (occupied, not merely controlled), we still certify and flag it as the **non-half-open / blocked subtype**.

- **Both colours, fully symmetric.** A White backward pawn advances toward rank 7 (its stop square is one rank *higher*; the fixing enemy pawn sits two ranks higher on an adjacent file). A Black backward pawn advances toward rank 0 (stop square one rank *lower*; the fixing enemy pawn sits two ranks lower on an adjacent file). Every rank comparison, every offset, and the stop-square direction flip on `color`. No rule may be written for one colour only.

- **Distinguish from isolated, doubled, and passed.** An **isolated** pawn has *no* friendly pawn on either adjacent file; a backward pawn *has* a neighbour that has merely advanced past it. A **doubled** pawn can independently also be backward (doubling does not exclude it). A **passed** pawn is narrated as passed, never backward (and by definition cannot have an enemy pawn controlling its stop square, so it can never satisfy the load-bearing confirm). See §4 for the one-neighbour (edge-file) and fixed-level-neighbour cases.

## 2. Detection rules (VETO-THEN-CONFIRM)

Define, for the candidate pawn at `square` of `color`, on `board_after`:
`enemy = not color`; `f = chess.square_file(square)`; `r = chess.square_rank(square)`;
`fwd = +1` for White / `−1` for Black; `stop_sq` is the square on file `f` at rank `r + fwd`.

This is a **static positional predicate over `board_after`**, evaluated at the moved pawn's destination (`move.to_square`), exactly mirroring how `is_passed_pawn` / `is_outpost` are invoked in `certified_claims`. It is **turn-independent**: backwardness is a property of the pawn structure, true regardless of whose move it is. **All geometry must be computed from piece placement alone — never by pushing a hypothetical move, never via `board.legal_moves`, and never depending on `board.turn`.** (Enemy-pawn control of the stop square is geometric pawn-attack coverage; a pin on any pawn does not change the squares a pawn attacks, so pins are irrelevant to this predicate and must not be consulted.)

**VETO 1 — Is it the mover's pawn at all?** Veto unless `board.piece_at(square)` exists, is a `chess.PAWN`, and `.color == color`. (Same opening guard as `is_passed_pawn`; also correctly rejects a square where the pawn just promoted — the piece there is no longer a pawn.)

**VETO 2 — Stop square must exist on-board.** Veto if `stop_sq` is off-board — i.e. a White pawn already on rank 7 or a Black pawn already on rank 0. (Such a pawn is promoting, not backward.) **Note:** we do **not** blanket-veto home-rank pawns here; the home-rank two-square-leap escape is handled precisely in CONFIRM 1b below, because a home-rank pawn whose *both* advance squares are pawn-controlled (or whose double-step is blocked) genuinely *can* be backward, and a blanket home-rank veto would be a false negative.

**VETO 3 — No friendly neighbour is positioned to support the push.** For each adjacent file (`f−1`, `f+1`) that is on-board, examine the friendly pawns on it. Classify each such neighbour pawn `n` at rank `rn`:
- **"behind-or-level"** if it is not strictly ahead of the candidate (White: `rn <= r`; Black: `rn >= r`);
- **"already past"** if it is strictly ahead (White: `rn > r`; Black: `rn < r`).

A **behind-or-level** neighbour normally *can* march up to stand beside the candidate and defend its push, which would make the candidate **not** backward — so its presence is a veto **UNLESS** that neighbour is itself **fixed** (cannot actually reach the supporting square). The neighbour is *fixed* — and therefore does **not** save the candidate — if the square it would have to occupy to stand beside the candidate (the adjacent-file square at the candidate's rank `r`, i.e. the square diagonally guarding `stop_sq`) is **either** occupied by any pawn **or** itself controlled by an enemy pawn, **and** the neighbour cannot leap past that with a free, un-controlled double-step from its own home rank. **Implementation:** for each behind-or-level neighbour, test whether it has a real, presently-available path (single step or, from its home rank only, an unobstructed double step) to the support square that is not enemy-pawn-controlled; if **any** behind-or-level neighbour has such a path, **veto** (candidate is supportable → not backward). If **every** behind-or-level neighbour is fixed (none can reach support), they do not save the candidate and we proceed.

The candidate therefore survives VETO 3 only when **no friendly neighbour can come up to support its advance** — every neighbour is either already past it or is a behind/level pawn that is itself fixed. (This corrects the draft's over-broad rule that *any* level/behind neighbour vetoes: a fixed level neighbour that can never actually arrive is the textbook case of a pawn that is still backward.)

**VETO 4 — At least one real neighbour must exist, and at least one must be *ahead*.** Two sub-checks, both required, to separate backward from isolated and to close the vacuous-truth hole:
- (4a) **Not isolated:** at least one adjacent file (on-board) must contain a friendly pawn. If *both* adjacent files have zero friendly pawns, the pawn is **isolated, not backward** — veto (let the isolated-pawn concept own it).
- (4b) **An advanced neighbour actually exists:** at least one friendly neighbour pawn must be **strictly ahead** of the candidate (an "already past" pawn from VETO 3). "Every neighbour is ahead" is *vacuously true* when a side has no pawn at all, so VETO 3 alone does not guarantee a real advanced neighbour on an edge file or a lopsided structure; without an actually-advanced neighbour there is nothing the candidate has "fallen behind," so it is not backward. Veto if no neighbour is strictly ahead. *(This is what makes the "rear-most" claim non-vacuous and prevents certifying, e.g., an a-file pawn whose only b-file pawn is level-and-fixed but never advanced past it.)*

**CONFIRM 1 — Stop square controlled by an enemy pawn (load-bearing).** Confirm the candidate **cannot safely push one step**: `stop_sq` must be attacked by an **enemy pawn**, computed by **pure pawn geometry on `board_after`** (no turn flip, no hypothetical push):

> There must exist an enemy pawn on file `f−1` or `f+1` whose rank is `r + 2·fwd` — i.e. for a White candidate, a Black pawn on an adjacent file at rank `r+2` (which attacks down-and-inward onto `stop_sq` at rank `r+1`); for a Black candidate, a White pawn on an adjacent file at rank `r−2`.

**Preferred equivalent implementation** (less error-prone, and explicitly pin-independent): `pawn_controllers = [a for a in board_after.attackers(enemy, stop_sq) if board_after.piece_at(a).piece_type == chess.PAWN]`, then require `pawn_controllers` non-empty. `board.attackers(color, sq)` is **turn-independent and pin-independent** — it returns every piece of `color` that attacks `sq` by raw geometry regardless of whose move it is or whether the attacker is pinned — so **no `board.copy()` / turn-flip is needed or permitted** (the draft's "build a turn-flipped copy and test `is_attacked_by`" was both unnecessary and self-contradictory; use `attackers(enemy, stop_sq)` filtered to pawns directly). If no enemy pawn controls `stop_sq`, the pawn can simply advance — **abstain** (no certification). *(Do not reuse analyzer's `_enemy_pawn_can_attack`: that models an enemy pawn that could move to attack a square in the future. Here we require an enemy pawn that **already** attacks the stop square. Different question.)*

**CONFIRM 1b — Not bypassable by a safe double-step (home-rank escape, replaces the blanket home-rank veto).** If the candidate is on its **home rank** (White rank 1 / Black rank 6), it may be able to leap *over* the controlled stop square with a two-square advance. Compute the double-step landing `leap_sq` at rank `r + 2·fwd`. The candidate **escapes** (→ **abstain**, not backward) if **both** intermediate `stop_sq` and `leap_sq` are **empty** (no double-step is legal through an occupied square) **and** `leap_sq` is **not** controlled by an enemy pawn. If the candidate is on its home rank but the double-step is blocked (`stop_sq` or `leap_sq` occupied) **or** `leap_sq` is also enemy-pawn-controlled, the leap does not save it and we continue (a genuinely backward home-rank pawn). For a non-home-rank candidate this sub-check is a no-op (no double-step exists). *(This fixes the draft's false negative: the old VETO 2 discarded **every** home-rank pawn, missing real fixed home-rank backward pawns.)*

**CONFIRM 2 — Un-supportable, confirmed.** Robustness restatement of VETO 3's outcome: there is no friendly pawn that can, by a legal pawn advance, arrive on the support square beside the candidate (the adjacent-file square at rank `r`) to defend the push. After VETO 3 this holds by construction — every behind/level neighbour was shown fixed and every other neighbour is already past and cannot retreat. If, due to a logic slip, a neighbour is found that *could* still reach the support square un-attacked, **abstain** (treat supportability as disqualifying). This is a guard, not a new gate.

**CONFIRM 3 — Not a passed pawn (anti-false-positive, belt-and-suspenders).** Do **not** certify if `is_passed_pawn(board_after, square, color)` is `True`. A passed pawn is narrated as passed, not backward. Note this guard is **provably unreachable after CONFIRM 1**: a passed pawn has no enemy pawn on its own or adjacent files, so no enemy pawn can control its stop square (which lies on its own file, with adjacent-file controllers on adjacent files) — CONFIRM 1 already fails for any passed pawn. We keep the explicit `is_passed_pawn` call anyway so the mutual exclusivity is enforced even if CONFIRM 1's geometry is ever refactored. Reuse the existing **`is_passed_pawn`** helper directly.

**If VETO 1–4 all pass and CONFIRM 1, 1b, 2, 3 all hold → certify `backward_pawn`.** Compute the corroborating file status via the existing **`file_state(board_after, f, color)`** helper for the evidence bundle, but do **not** veto on it.

**Colour-handling summary (must be mirrored exactly):**

| quantity | White (`color == chess.WHITE`) | Black (`color == chess.BLACK`) |
|---|---|---|
| forward direction `fwd` | `+1` | `−1` |
| stop square rank | `r + 1` | `r − 1` |
| fixing enemy pawn rank | `r + 2` | `r − 2` |
| "neighbour strictly ahead" | `rn > r` | `rn < r` |
| "neighbour behind-or-level" | `rn <= r` | `rn >= r` |
| home rank (CONFIRM 1b) | `1` | `6` |
| stop off-board (VETO 2) | `r == 7` | `r == 0` |
| double-step landing rank | `r + 2` | `r − 2` |

## 3. Positive examples

1. **Classic half-open d6 backward pawn (Black).** Black pawn on d6 with neighbours c-pawn (advanced to c5) and e-pawn (gone or pushed to e5), a White pawn on e4 (or c4) controlling d5, and the d-file half-open for White. The d6 pawn is rear-most, its stop square d5 is enemy-pawn-controlled, the file is half-open. **Certifies; half-open subtype** — textbook backward pawn.

2. **Maróczy-bind backward c-pawn (Black).** Black's c-pawn on a half-open c-file with a White pawn on c4/e4 controlling c5/d5; the d6/c-pawn complex cannot be supported from the b- or d-file (those pawns have advanced or been traded). **Certifies; half-open subtype.**

3. **White backward e-pawn (colour-mirror).** White pawn on e4 with Black pawns on d5 and f5 (or just one of them) controlling e5, and White's d- and f-pawns already advanced past the e-pawn so neither can drop back to support e5. Stop square e5 is attacked by a Black pawn at rank `r+2` (d5 or f5). **Certifies; demonstrates the White geometry (`stop = r+1`, fixer at `r+2`).**

4. **Blocked (non-half-open) backward pawn — still certified.** Black pawn on c6, a White pawn directly in front on c5 (file fully blocked, not just controlled) plus a White pawn on b4 (or the c5 pawn's own diagonal) controlling the relevant advance, and Black's b-pawn already advanced past c6. Even with an enemy pawn occupying the file, the pawn is rear-most, cannot advance, and cannot be supported. **Certifies as the blocked / non-half-open subtype**, proving we do not require half-open.

5. **Fixed level neighbour (the under-inclusiveness fix).** Black pawn on d6 with a Black c-pawn that is *level* on c6 but whose support square c5 is occupied by a White pawn (or controlled by a White b4 pawn) so c6 can never reach c5 to guard d5, plus a White pawn controlling d5 and a Black e-pawn already advanced past d6. The level c6 neighbour cannot actually support, so d6 is still backward. **Certifies** — the case the draft's blanket "any level neighbour vetoes" wrongly missed.

*(FENs are illustrative; the predicate decides from board geometry, not labels.)*

## 4. Negative / edge cases

1. **Isolated pawn (no neighbour at all).** Zero friendly pawns on either adjacent file → **VETO 4a** excludes it. Isolated and backward are distinct weaknesses; conflating them is a false positive.

2. **A neighbour can actually support.** If a behind-or-level neighbour has a free, un-controlled path (single step, or a clear double-step from its home rank) to the square beside the candidate, it can defend the push → **VETO 3** kills it. E.g. White pawns c3 and d3: d3 is not backward because c3 can play c4 (if c4 is empty and not enemy-pawn-controlled) to support d4. **Caveat (the upgrade):** if c4 were occupied or enemy-pawn-controlled so c3 could *never* arrive, d3 *would* be backward — VETO 3 only vetoes on a neighbour that can *really* support.

3. **Stop square free, or controlled only by a piece (not a pawn).** If the square in front is empty and no *enemy pawn* attacks it (only an enemy knight/bishop/rook/queen does), the pawn can usually just advance; coaches do not call this backward. **CONFIRM 1** requires specifically an **enemy pawn** attacker. Piece control is transient; pawn control is the structural fixative. Excluded. *(Known limitation: a pawn fixed solely by minor-piece control is therefore not certified — standard master convention.)*

4. **Passed pawn.** No enemy pawn on its own/adjacent files ⇒ CONFIRM 1 cannot hold; **CONFIRM 3** (`is_passed_pawn`) is the explicit, redundant guard. Narrated as passed, never backward.

5. **Home-rank pawn that can leap the control.** A pawn on its home rank whose stop square is enemy-pawn-controlled **but** whose two-square landing is empty, the intermediate square is empty, and the landing is not enemy-pawn-controlled can bypass the guard — **CONFIRM 1b** abstains. **But** a home-rank pawn whose double-step is blocked (intermediate or landing occupied) or whose landing is *also* enemy-pawn-controlled is genuinely backward and **is** certified (this is the case the draft's blanket home-rank veto wrongly discarded).

6. **Edge-file (a-/h-) pawn.** Only one adjacent file exists. It qualifies only if that single neighbour file holds a friendly pawn that is **strictly ahead** of it (satisfying both VETO 3 and VETO 4b on the one available side) and CONFIRM 1 holds. The off-board side is **not** treated as a missing-neighbour that triggers the isolated veto — VETO 4a needs only "at least one on-board neighbour file with a friendly pawn." A lone edge pawn whose single neighbour is level-and-fixed but never advanced past it is **not** certified, because VETO 4b finds no strictly-ahead neighbour (closing the vacuous-truth hole). Handled, not blanket-excluded.

7. **Doubled pawn that is also backward.** Doubling does not exclude backwardness; if the rear doubled pawn meets every condition it is certified, and the evidence bundle notes the doubling. Co-occurring features, not a false positive. *(Note the front pawn of a doubled pair on file `f` occupies the rear pawn's stop square; that makes the rear pawn's push *blocked by a friendly pawn*, which is its own kind of immobility — if the rear pawn's stop square is also enemy-pawn-controlled it still certifies as backward, but the bundle should record the friendly blocker so the narrator does not imply it could otherwise advance.)*

8. **Promotion / off-board stop.** A White pawn on rank 7 / Black on rank 0 has no stop square (it promotes) → **VETO 2** excludes it; no off-board rank arithmetic is ever performed.

## 5. Evidence bundle

Return `(bool, Optional[dict])`, mirroring how `is_outpost` returns supporter squares and `is_rook_lift` returns a reason string. The dict is populated **only on success** (and is `None` on every veto/abstain):

- `pawn_square: int` — the backward pawn's square (render with `chess.square_name` → e.g. `"d6"`).
- `color: bool` — `chess.WHITE` / `chess.BLACK` of the pawn.
- `stop_square: int` — the controlled one-step advance square (e.g. `"d5"`).
- `enemy_pawn_controllers: List[int]` — square(s) of the enemy pawn(s) attacking `stop_square` (the pieces that fix the pawn; e.g. `["e4"]`). Non-empty by construction (CONFIRM 1).
- `advanced_neighbors: List[int]` — friendly pawn square(s) on adjacent files **strictly ahead** of the candidate (the "already past" pawns that cannot drop back; e.g. `["c5"]`). Non-empty by construction (VETO 4b) — this is *why* it is unsupportable.
- `fixed_level_neighbors: List[int]` — any behind-or-level friendly neighbour(s) that were found **fixed** (could not reach the support square), recorded so the evidence can explain why a seemingly-helpful neighbour does not save the pawn. May be empty.
- `subtype: str` — `"half_open"` (enemy has no pawn on file `f` in front), or `"blocked"` (an enemy pawn occupies file `f` directly in front of the candidate), or `"closed"` (enemy pawn(s) on file `f` ahead but not directly blocking). Drives how strongly the narrator frames it as a target.
- `is_blocked: bool` — `True` iff an enemy pawn sits on `stop_square`'s file directly in front (i.e. `subtype == "blocked"`); convenience for the narrator.
- `friendly_blocker: Optional[int]` — square of a friendly pawn directly in front on file `f` if any (the doubled-pawn case from §4.7), else `None`; lets the narrator avoid implying the pawn could advance if a friendly pawn blocks it.
- `is_doubled: bool` — `True` iff `color` has ≥2 pawns on file `f` (the candidate is part of a doubled pair). Co-occurrence note.
- `file_status: str` — raw result of `file_state(board_after, f, color)`: `"half_open_file"`, `"open_file"`, or `""`. Corroborating-evidence flag straight from the analyzer's single source of truth. *(Note `"open_file"` should not normally co-occur with certification, since an open file means neither side has a pawn there — contradicting CONFIRM 1's enemy controller on an adjacent file is still possible, but the candidate's own file being open would mean the candidate isn't on it; surfaced verbatim for transparency.)*
- `is_half_open_target: bool` — `file_status == "half_open_file"`; the most-cited aggravating factor.
- `evidence: str` — ready-to-quote narrator string built from `chess.square_name` + the literal word "pawn" (never a tag/field name), e.g.:
  - half-open: `"the pawn on d6 is backward: its advance square d5 is covered by the pawn on e4, and the c-pawn on c5 has already advanced past it and cannot return to support a push; the half-open d-file makes it a target"`
  - blocked / closed subtype (drop the trailing target clause): `"the pawn on c6 is backward: its advance square c5 is held by the pawn on c5, and the b-pawn on b4 has already advanced past it and cannot return to support a push"`
  - fixed-level-neighbour case (name the stuck would-be supporter): `"the pawn on d6 is backward: d5 is covered by the pawn on e4, and although the c-pawn is level on c6 it cannot reach c5 to defend the push"`

The evidence string must name exact squares and never emit a JSON key or tag name, consistent with the narrator's "never write a field/tag name in prose" rule.

## 6. Wiring

- Add `"backward_pawn"` to `factgate.GATED_TAGS` (`factgate.py:222`).
- In `certified_claims` (`factgate.py:235`), add, alongside the `is_outpost` tuple-guard pattern:
  ```python
  bp = _safe(lambda: is_backward_pawn(board_after, move.to_square, mover_color))
  if bp and bp[0]:
      tags.add("backward_pawn")
  ```
  Note `is_backward_pawn` returns `(bool, Optional[dict])`, so guard via `bp and bp[0]` exactly like `is_outpost`/`creates_fork`; `_safe` collapses any internal error to `None`, which fails the guard and silently drops the tag (the module's fail-safe posture).
- To surface the evidence bundle to the narrator (Tier 1+), serialize the dict in `narrator._move_to_dict` inside the `if tier >= 1:` block beside `certified` (`narrator.py:440-462`), under a new key (e.g. `d["backward_pawn_evidence"]`) wrapped in the same try/except fail-safe; emit only when present.
- **Register the new claim type in the fact-gate prompt rule at `narrator.py:202`** (add "a **backward pawn** (`backward_pawn`)" to the enumerated whitelist), or the narrator is forbidden from asserting it even when certified. Adding to `GATED_TAGS` without updating the prompt rule leaves the tag certified-but-unspeakable.

## 7. Known limitations

- **Evaluated only at the moved pawn's destination square** (`move.to_square`), matching how `is_passed_pawn`/`is_outpost` are called. It certifies a backward pawn only on the ply that creates or moves that exact pawn into the backward configuration. A pawn that became backward on an earlier ply, or an *opponent's* backward pawn the move merely exposes, is not re-detected here without a board-wide scan. (A fuller version would scan all of `mover_color`'s pawns each ply.)
- **Static, single-ply geometry, no engine confirmation.** It asserts the structural fact, not a Stockfish-verified long-term weakness. The `is_passed_pawn` guard, the CONFIRM-1b leap escape, and the "fixed-neighbour" path-check remove the most common practically-harmless cases, but a backward pawn about to be traded is still labelled backward.
- **"Cannot be supported" is path-checked one move deep.** VETO 3 / CONFIRM 2 test whether a neighbour can reach the support square in a single step or a clear home-rank double-step that is not enemy-pawn-controlled. It does not model multi-move maneuvers (a neighbour walking two non-home squares) or manufacturing a third supporter onto an adjacent file via a future capture. Such cases are rare; the predicate treats them as still-backward (slight, coach-consistent over-inclusion).
- **Does not require a half-open file**, by design, to catch closed/blocked backward pawns; a small number of "backward but practically harmless because blocked and untargetable" pawns are certified. Mitigated by `subtype` / `file_status` so the narrator softens the language for the blocked/closed subtype.
- **Piece-only control of the stop square is ignored** (CONFIRM 1 requires a pawn). A pawn fixed solely by minor-piece control is not certified — the standard master convention, at the cost of missing a handful of practically-backward pawns.
- **Pins are deliberately ignored.** Pawn attack geometry (`board.attackers`) does not change under a pin, and a pinned enemy pawn still fixes the candidate's stop square structurally; the predicate is therefore pin-independent by design. (This is a *correctness* choice, not a gap — but worth stating, since reviewers expect relative/absolute pins to be considered and here they correctly are not.)

## 8. Complexity

**Medium.** Pure python-chess square arithmetic, no engine call, reusing `is_passed_pawn` and `file_state` plus the standard `board.pieces` / `board.attackers` / `square_file` / `square_rank` idioms already pervasive in `factgate.py` / `analyzer.py`. What keeps it above "low": the multi-condition VETO-THEN-CONFIRM logic that conflates easily with three neighbouring concepts (isolated, doubled, passed); the two-directional rank/control geometry that must be mirrored exactly for both colours and at the board edge (the classic off-by-one and colour-flip bug source — see the §2 mirror table); the **path-check on behind-or-level neighbours** (the correctness upgrade that distinguishes a genuinely-fixed level neighbour from a supportable one); and the **home-rank double-step escape** (CONFIRM 1b), the subtle replacement for a naive home-rank veto. The stop-square control check — an *existing* enemy-pawn attacker via turn-/pin-independent `board.attackers`, never a hypothetical push — is the correctness crux distinguishing this from the simpler `is_passed_pawn`. No PV/engine work and no before/after diffing, so it stays below the "high" tier of sacrifice/alignment detectors.
