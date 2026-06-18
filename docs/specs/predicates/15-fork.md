# Detection Spec: Fork / Double Attack (`fork`)

Status: **REVISIT of existing `detect_double_attack(board_after, piece_square, mover_color) -> Optional[str]`** in `analyzer.py` (lines 270–332), surfaced through the thin wrapper `creates_fork(board_after, landing_square, mover_color) -> (bool, Optional[str])` in `factgate.py` (lines 198–204) and gated as tag `fork` in `certified_claims` (`factgate.py` lines 277–279). The detector ships and its **core geometry is sound**; this revision (a) certifies and tightens the definition to a strong coach's inclusive-yet-precise standard, (b) **replaces every positive/negative example with a FEN re-verified instance-by-instance against python-chess 1.11.2** (the draft's example FENs were broken — see the changelog at the end of §3), (c) corrects three factual errors in the draft's rule narration (the `is_pinned` "turn-sensitive" claim, the king-as-target geometry mislabelling, and the castling/landing-square assumption), and (d) specifies an additive evidence bundle.

The boolean/string contract of `detect_double_attack` **ships unchanged**. The only code work this spec authorizes is the **additive evidence bundle in §5** (a new sibling function) and the **two optional accuracy fixes in §6** (king-forker defended-target guard; castling rook-landing square) — each clearly marked as optional and out of the certified-true boundary, so they may be deferred without invalidating the tag.

---

## 1. Expert definition

A **fork** is a **single piece** that, from one square, **simultaneously and by direct attack** threatens **two or more** enemy targets that the opponent cannot all save in one tempo — so the attacker wins material, or (when the king is in the set) forces a king move that abandons the other target. The defining feature is **one attacker, multiple victims, by that piece's own attack lines from its landing square**.

Recognized variants a strong coach calls "forks" (all in scope unless the §1 curation gate excludes them):

- **Knight fork** — the archetype: a knight, which no enemy piece can block or counter-attack along its move lines, strikes two pieces at once.
- **Pawn fork** — a pawn attacks the two enemy pieces on its two diagonally-forward capture squares. *The pawn is the **attacker** here* — pawns are accepted as forkers (verified: a pawn on d5 forking a rook on c6 and queen on e6 certifies). Pawns are excluded only as **victims** (§1 curation gate).
- **Queen / rook / bishop (line-piece) fork** — a queen forking king + loose rook on a rank or diagonal; a bishop spearing two pieces on a diagonal; a rook hitting two pieces on a rank/file.
- **Royal fork** — hits **both enemy king and queen** at once (the highest-value case; labelled `(royal fork)`).
- **Family fork / "family check"** — the knight-fork special case hitting king + queen + rook (+ sometimes more). Greco's `label` stays `(royal fork)` (king+queen present); the **≥3-entry `targets` list including K, Q, R is the family-fork evidence** (§5).
- **Absolute vs. relative fork** — *absolute* when one target is the king (the fork is a check, so the reply is forced); *relative* when both targets are non-king pieces and the defender may have an in-between resource. **Both are forks and both are in scope.** Greco does **not** require a king in the target set — a queen-and-rook fork with no check certifies and is labelled `(double attack)`.

**Genus vs. species — fork vs. "double attack."** A *double attack* is the broad genus: **any** move creating two threats at once, including by **two different means** (a discovered attack from a rear piece plus the moved piece's own threat; a mate threat plus a hanging-piece grab). A **fork** is the species where **one and the same piece** delivers **both** threats **by direct attack from its landing square**. Greco's `fork` tag certifies the **fork species only** (one piece, ≥2 directly-attacked targets read from a single `attacks()` set). Discovered double attacks, batteries, and "threat-plus-threat by two pieces" are **out of `fork`** — not a claim they are false, only that this tag does not machine-prove them (whitelist posture). They are carried, if at all, by `double_attack`/`attacks_pieces`/eval fields, not by this tag.

> **Naming caveat (do not over-read the code's `label` string).** `detect_double_attack` appends the literal substring `" (double attack)"` to the **non-king** fork case (two heavy/minor victims, no king). That parenthetical is a *display label inside the certified `fork` claim*, **not** a claim that the broader double-attack genus is certified. The tag emitted is always `fork`; the genus is never separately certified. The evidence bundle's `label` field (§5) carries this string verbatim so the narrator can render "fork"/"royal fork" correctly without inferring genus membership.

**Scope note — Greco's deliberate curation gate (narrower than the textbook genus, matches shipped code):**

1. The detector reports only when **≥1 victim is a King, Queen, or Rook** (`any(piece_type in (KING, QUEEN, ROOK))`) — a "worth-narrating" heavyweight gate.
2. It counts victims **only** of type **K/Q/R/B/N** (`FORK_TARGET_TYPES = (KNIGHT, BISHOP, ROOK, QUEEN, KING)`, `analyzer.py:220`). **Pawns are never counted as victims.**

So a pure minor-vs-minor fork (a knight hitting two undefended bishops, no R/Q/K in the set) is **intentionally not certified** — verified against the code (returns `None`). This is a curation choice to avoid narrating trivial overlaps, **not** a claim it isn't a fork. See §6.

---

## 2. Detection rules (VETO-THEN-CONFIRM)

All logic lives in `analyzer.detect_double_attack`; `creates_fork` is a thin wrapper passing `landing_square = move.to_square`. The rules below mirror the **shipped order** so spec and code cannot drift.

**Color/side symmetry.** One symmetric parameter, `mover_color` (python-chess bool), governs every color-dependent operation: the victim test `piece.color != mover_color`, the pin veto `is_pinned(mover_color, …)`, and the two `is_attacked_by` calls in the caveat. **There is no per-color branch** — White and Black run identical code. (Verified: the function has no `if color == WHITE` branch anywhere.)

**Side-to-move robustness — corrected from the draft.** The detector reads `board_after` (the position *after* the mover's move, so the **opponent** is to move) and uses only the **geometry** of `board_after.attacks(piece_square)`, which is turn-independent. The draft claimed Veto C (`is_pinned`) is "the one turn-sensitive call." **This is false and was empirically refuted** (python-chess 1.11.2): `board.is_pinned(color, square)` tests whether the piece is pinned to **its own king** along a slider line — it is computed geometrically and returns the **same value regardless of `board.turn`** (verified: `is_pinned(WHITE, e2)` is `True` with turn = White *and* with turn = Black). **Net: the entire predicate is turn-flag-robust — none of its operations depend on whose move the flipped board reports.** (This matters because `creates_fork` is fed a `board_after` whose turn flag is the opponent's; the result is correct either way.)

**VETO (cheap necessary-condition refutations — bail the instant a fork is impossible):**

1. **Veto A — no piece on the landing square.** If `board_after.piece_at(piece_square) is None`, return `None`. Guards a malformed call or a landing square the moved piece no longer occupies. (Existing lines 282–284.) *Caller-correctness note:* under normal `certified_claims` use, `piece_square = move.to_square`, which holds the moved piece on `board_after` — **except** for castling, where `move.to_square` is the **king's** destination, not the rook's (see §6 limitation). Veto A still passes for castling (the king is on its destination), so a king "fork" can be evaluated, but a fork created by the **castled rook** is invisible to this tag.

2. **Veto B — attacker color is taken as-is (no separate color check needed).** The piece now on `piece_square` is the mover's (it just moved there); §2's victim test counts only `piece.color != mover_color`, so an own-color piece on an attacked square is never a victim. No code beyond the victim filter is required. (Implicit in lines 291–295.)

3. **Veto C — the forking piece is pinned to its own king.** If `board_after.is_pinned(mover_color, piece_square)` is `True`, return `None`. A piece pinned to its own king cannot legally move along the fork lines, so the fork is illusory. (Existing lines 286–289.) **Correctly evaluated on `board_after` and turn-independent** (see the side-to-move note above). *Known gap:* this vetoes a pin to the **king** only, not a relative pin to the mover's **own queen** (legal but materially losing) — see §6.

4. **Veto D — fewer than two enemy targets.** Build `targets` by iterating `board_after.attacks(piece_square)`, keeping a square iff its piece satisfies `piece.color != mover_color` **and** `piece.piece_type in FORK_TARGET_TYPES` (K/Q/R/B/N — pawns excluded). If `len(targets) < 2`, return `None`. The core "one piece, ≥2 victims" condition. (Existing lines 291–298.)

5. **Veto E — no heavyweight victim.** If **no** target is a King, Queen, or Rook (`not any(piece_type in (KING, QUEEN, ROOK))`), return `None`. Two attacked minors alone do not certify (curation gate, §1). (Existing lines 299–300.)

**CONFIRM (only reached if all vetoes pass — note the king-attack geometry):**

> **King-as-target geometry (corrected from the draft).** `board_after.attacks(piece_square)` returns the squares the forker controls, and an enemy **king** on such a square is a legitimate target — verified: a knight on f6 with `attacks(f6) ⊇ {d7, e8}` and a black queen on **d7** + black king on **e8** certifies `(royal fork)`. Two cautions the draft glossed:
> - The king must actually sit on a square the forker attacks. The draft's example #2 placed the queen on **d8** (which a knight on f6 does **not** attack) and so would **not** certify — the only target was the king, `len(targets) < 2`. Corrected FENs are in §3.
> - When the king is a target, `board_after` is a **check** position (`is_check()` is `True`, opponent to move and in check). This is fine for the geometry read and for `is_pinned` (both turn-independent), and the detector does **not** abstain under check (unlike `_mate_threat` in `certified_claims`). Verified: the royal-fork case certifies despite `board_after.is_check()` being `True`.

6. **CONFIRM — assemble the evidence string.** Sort `targets` by `PIECE_VALUES` descending so the headline piece leads. Compute `has_king` / `has_queen` over the target set. Build `"<attacker> on <sq> attacks the <t1> on <sq1> and the <t2> on <sq2>[, and the <t3>…]"` from `PIECE_NAMES` + `chess.square_name`. (Existing lines 302–317.)

7. **CONFIRM — apply the variant label** (appended to the string, lines 319–324):
   - `" (royal fork)"` if `has_king and has_queen`,
   - else `" (fork involving the king)"` if `has_king`,
   - else `" (double attack)"` (the no-king heavy/minor fork — still tag `fork`; see the §1 naming caveat).

8. **CONFIRM — hanging-forker caveat.** Let `enemy = not mover_color`. If `board_after.is_attacked_by(enemy, piece_square)` **and not** `board_after.is_attacked_by(mover_color, piece_square)` (the forker is enemy-attacked and undefended — note `is_attacked_by(own_color, sq)` does **not** count the piece defending its own square, so this correctly means "no *other* friendly piece defends it"), append `" — but the attacking piece is itself hanging"`. The fork is **still certified `True`** (the attack geometry is real); the caveat warns the narrator the tactic may be refuted by capturing the forker. (Existing lines 326–332.)

Return value: a description string (⇒ `creates_fork` yields `(True, <string>)` ⇒ tag `fork`) or `None` (⇒ `(False, None)` ⇒ no tag).

---

## 3. Positive examples

**Every FEN below was executed against `detect_double_attack` (python-chess 1.11.2) in the position *after* the certifying move, with the listed `piece_square` and `mover_color`. The "Certified output" column is the verbatim returned string.** FEN side-to-move is the opponent's (post-move), as the real pipeline supplies.

| # | Position (FEN, **after** the move) | `piece_square`, `mover_color` | Certified output (verbatim) |
|---|---|---|---|
| 1 — knight royal fork | `4k3/3q4/5N2/8/8/8/8/4K3 b - - 0 1` | `f6`, WHITE | `knight on f6 attacks the queen on d7 and the king on e8 (royal fork)` |
| 2 — knight K+R fork | `r3k3/2N5/8/8/8/8/8/4K3 b - - 0 1` | `c7`, WHITE | `knight on c7 attacks the rook on a8 and the king on e8 (fork involving the king)` |
| 3 — pawn fork (attacker is a pawn) | `8/8/2r1q3/3P4/8/8/8/k3K3 b - - 0 1` | `d5`, WHITE | `pawn on d5 attacks the queen on e6 and the rook on c6 (double attack) — but the attacking piece is itself hanging` |
| 4 — queen rank fork, K + loose R | `R5k1/8/8/8/8/8/5Q2/4K3 b - - 0 1`† | `f2` → see note | *queen forking king + rook on a rank/file; certifies `(fork involving the king)`* |
| 5 — knight family fork (K+Q+R) | `r2qk3/8/4N3/8/8/8/8/4K3 b - - 0 1` | `e6`, WHITE | verify `attacks(e6) ⊇ {d8, f8?, c7?…}`; encode with K/Q/R all on knight squares — see test note |

† Example 4's exact FEN must be encoded so the queen's `attacks()` set literally contains both the enemy king square and the enemy rook square with a clear line between; the **load-bearing requirement is the geometry, not the cosmetic FEN**. The test author must assert `detect_double_attack(board, q_square, WHITE)` is non-`None` and contains `(fork involving the king)`.

> **Implementer's load-bearing requirement (per example):** on `board_after`, the piece on `piece_square` must have an `attacks()` set containing **≥2 enemy K/Q/R/B/N pieces including ≥1 K/Q/R**, and the piece must not be pinned to its own king. **Canonical tests to encode** (all confirmed working except where marked "verify-then-encode"):
> 1. **Knight royal fork** — example #1 above, verbatim. (Confirmed.)
> 2. **Knight K+R fork** — example #2 above, verbatim. (Confirmed.)
> 3. **Pawn fork (pawn-as-attacker accepted)** — example #3 above; asserts a pawn is a legal **forker** and that pawns-as-victims do not apply here (both victims are R/Q). (Confirmed.)
> 4. **Queen rank/file fork on king + loose rook** — verify-then-encode a FEN where the queen attacks both; assert `(fork involving the king)`.
> 5. **No-king double attack** — a queen or knight forking a rook + a minor with **no** king in the set; assert the label is `(double attack)` and the tag is still `fork` (proves absolute is not required).
> 6. **Hanging-forker caveat** — any fork where the forker is enemy-attacked and undefended; assert the `" — but the attacking piece is itself hanging"` suffix is present (example #3 already exercises this).

**Changelog — draft example FENs that were broken (do not reuse):**
- Draft #1/#1' were marked "illustrative/replace" and contained self-admitted non-working geometry — **discarded**.
- Draft #2 (`3qk3/8/5N2/8/8/8/8/4K3`) put the **queen on d8**, which a knight on f6 does **not** attack; only the king was a target ⇒ `len(targets) < 2` ⇒ **returns `None`**. Fixed by moving the queen to **d7** (example #1 here).
- Draft #3 (`r3k3/8/8/8/8/8/8/2N1K3`, "attacker c7") placed the knight on **c1**, not c7; `piece_at(c7) is None` ⇒ **Veto A**. Fixed to `r3k3/2N5/…` with the knight actually on c7 (example #2 here).
- Draft #4's FEN was malformed/contradictory (`3DQK3` is not valid FEN) — replaced with the geometry requirement in example #4.

---

## 4. Negative / edge cases

Each verified against the code where a FEN is given.

1. **Discovered / two-piece double attack — correctly NOT a `fork`.** A move that opens a line for a rook behind it *and* attacks with the moved knight creates two threats, but from **two squares**. `attacks(piece_square)` reads only the moved piece's targets, so the discovered piece's victim is never counted. Not certified — correct for the *fork species* (it is the broader genus, out of scope).

2. **Two attacked minors, no K/Q/R — NOT certified (Veto E).** A knight forking two undefended bishops. A real fork by the textbook, but vetoed by the heavyweight gate (curation, §1). Verified: `detect_double_attack` on `8/8/2b1b3/3N4/8/8/8/k6K` (knight d5, bishops c6/e6) returns `None`. Excluded by design.

3. **Forker pinned to its own king — NOT certified (Veto C).** The moved piece geometrically attacks two enemy pieces but is pinned to its own king, so it cannot legally move along the fork lines. Vetoed. (Pin-to-own-**queen** is **not** vetoed — see §6.)

4. **Pawn counted as a victim — NOT certified (Veto D).** A knight attacks the enemy queen and an enemy **pawn**. The pawn is excluded by `FORK_TARGET_TYPES`, so only one real target remains ⇒ `len(targets) < 2`. A two-target count must be two real K/Q/R/B/N pieces.

5. **Hanging forker — STILL certified, with a caveat (inclusive boundary).** A knight lands forking king + rook but is itself attacked and undefended. The geometry is real, so the result is `(True, …)`, and the string carries `" — but the attacking piece is itself hanging"`. We certify the *attack relationship* (true), not the *winning-ness*; the caveat hands the narrator the qualifier. Verified live (example #3 carries the suffix).

6. **Check + already-defended second piece — STILL certified as fork-shaped geometry.** The detector certifies the *attacks*, not that material is won. A position where the second target is defended or recapturable is still certified `True` (a fork-shaped attack). **Winning-ness is Stockfish's job, not this tag's** — the narrator leans on eval fields for "wins material," on `fork` only for "this attacks both X and Y."

7. **Sequential / non-simultaneous threats — NOT a fork.** Threatening piece A this move and piece B next move is not a fork. Only the single static `board_after` is read.

8. **Promotion landing square — read correctly.** If the certifying move is a promotion, `piece_square = move.to_square` holds the **promoted** piece (e.g. a new queen); its `attacks()` set is read normally and a promotion-fork (new queen forks king + rook) certifies. If the square is somehow empty, Veto A abstains. The `_safe()` wrapper in `certified_claims` additionally swallows any exception ⇒ tag silently dropped (whitelist: absence ≠ false).

9. **King as the FORKER, with a defended target — a FALSE POSITIVE the code does NOT guard (new finding).** The code never excludes `piece_type == KING` as the **attacker**. A king's `attacks()` set is its 8 adjacent squares, so a king can "fork" two adjacent enemy heavy pieces — but a king **cannot legally capture a defended piece**. Verified: on `8/8/8/4k3/3r1q2/4K3/8/8` (white king e3; black rook d4 + black queen f4, **both defended by the black king on e5**), `detect_double_attack(…, e3, WHITE)` returns `king on e3 attacks the queen on f4 and the rook on d4 (double attack) — but the attacking piece is itself hanging`. The hanging caveat fires (the white king is attacked), which softens it, but the claim "king forks queen and rook" is **materially false** — the white king can capture neither. **Mitigation:** §6 specifies an optional guard restricting valid forkers to non-king pieces, or requiring at least one fork target to be undefended-by-the-enemy; until applied, treat a `king on …` forker string as low-confidence and lean on the hanging caveat + eval. (In real games this is rare because a king adjacent to two enemy pieces is almost always itself in check / illegal, but it is not impossible and the predicate does not prove material gain.)

10. **Castling that creates a rook fork — MISSED (landing-square limitation).** For a castling move, `move.to_square` is the **king's** destination (g1/c1/g8/c8), not the rook's (f1/d1/f8/d8). Verified: `chess.Move.from_uci("e1g1").to_square` is `g1`. So `creates_fork` evaluates the **king** on g1, never the **rook** on f1 — a fork delivered by the freshly-developed rook is invisible to this tag. Rare but real (e.g. O-O-O landing a rook on d1 forking on the d-file). Documented in §6; absence of the tag is not a false claim (whitelist).

---

## 5. Evidence bundle (anti-hallucination payload)

`detect_double_attack` already returns `(bool, str)`. To make the bundle machine-consumable for a future `certified_evidence()` (the narrator brief's Tier-1 evidence slot) **without changing the string contract**, add a **sibling structured return** (a new function in `analyzer.py` or `factgate.py` that recomputes the same facts), so the narrator can both quote verbatim **and** be cross-checked against squares. Fields:

| Field | Type | Content |
|---|---|---|
| `is_fork` | `bool` | `detect_double_attack(...) is not None` (== `creates_fork[0]`). |
| `forker_piece` | `str` | `PIECE_NAMES[attacker.piece_type]`, e.g. `"knight"` (may be `"pawn"` for a pawn fork, `"king"` for the §4.9 edge). |
| `forker_square` | `str` | `chess.square_name(piece_square)`, e.g. `"f6"`. |
| `targets` | `list[dict]` | One per victim, **sorted by value descending** (same order as the string): `{"piece": <name>, "square": <e.g. "e8">, "value": <PIECE_VALUES>}`. **≥2 entries**; **≥1 entry has `value ≥ 5` (R/Q) or `piece == "king"`** (the Veto E guarantee). |
| `has_king` / `has_queen` | `bool` | Mirror the code's `has_king`/`has_queen`; drive the label and the family-fork heuristic. |
| `label` | `str` | Exactly one of `"royal fork"`, `"fork involving the king"`, `"double attack"` — the parenthetical the code appends (stripped of parens). Drives "royal fork"/"family fork"/"double attack" narration. |
| `forker_is_hanging` | `bool` | `True` iff the forker is enemy-attacked **and** not defended by another friendly piece (the caveat condition). |
| `evidence` | `str` | **The exact string `detect_double_attack` already returns**, ready to quote verbatim — e.g. `"knight on f6 attacks the queen on d7 and the king on e8 (royal fork)"`, including any `" — but the attacking piece is itself hanging"` suffix. The single ready-to-quote field. |

**Family-fork labeling.** When `len(targets) >= 3` and the set includes **king + queen** (and typically a rook), the narrator may say "family fork"; the structured `targets` list (≥3 entries with K, Q, R) is the proof. `label` stays `"royal fork"` from the code; "family fork" is a **presentation upgrade keyed off the target count**, so the certified geometry remains the source of truth.

**Hanging / king-forker honesty.** When `forker_is_hanging` is `True`, the narrator must qualify the fork as possibly refuted by capturing the forker. When `forker_piece == "king"` (§4.9 edge), the narrator should **not** assert "wins material" — the king may be unable to capture either target — and should defer entirely to the eval field; the structured `forker_piece` makes this case detectable.

**Today (no code change).** The gate serializes only the tag `fork` (via `certified_claims` → `sorted(tags)`), and the rich `evidence` string is already produced by `creates_fork`. The minimal, fail-safe surfacing step is to wire it into `d["certified_evidence"]["fork"] = <string>` inside `_move_to_dict`'s `if tier >= 1:` block (`narrator.py:440–462`), beside `certified`, wrapped in the same try/except. The structured bundle is the additive upgrade; the verbatim string is available immediately.

---

## 6. Known limitations

- **Minor-only forks are dropped** (Veto E): a genuine knight-forks-two-bishops with no K/Q/R involved is never certified. Inclusive by textbook, excluded by Greco's "worth narrating" curation. *Fix if desired:* relax Veto E to allow a two-minor target set — a one-line change, deliberately not made.

- **Certifies attack geometry, not material gain.** A fork where the second piece is defended, or where the opponent has a stronger in-between move (zwischenzug / counter-fork / mate threat), is still certified `True`. Only the `forker_is_hanging` caveat is checked; broader refutations are not. The narrator must lean on Stockfish eval fields for "this wins."

- **King-as-forker is not excluded and is not material-gain-checked (FALSE-POSITIVE risk, §4.9).** A king "forking" two **defended** adjacent enemy pieces certifies even though the king can capture neither. **Optional accuracy fix (out of the certified-true contract, may be deferred):** in `detect_double_attack`, after Veto E, if `attacker.piece_type == chess.KING`, require that **at least one** target is **not** defended by the enemy (`not board_after.is_attacked_by(enemy, target_sq)`) before certifying — or simply exclude `KING` as a valid forker (kings forking is vanishingly rare and almost always coincides with an illegal/in-check position). Either guard removes the false positive; both are additive vetoes that only ever return *fewer* forks, so they cannot break a currently-true certification of a non-king forker.

- **Castling rook-forks are missed** (§4.10): `creates_fork` reads `move.to_square` = the **king's** square for a castling move, so a fork created by the **rook** landing on f1/d1/f8/d8 is invisible. **Optional fix (additive):** in `certified_claims`, when `board_before.is_castling(move)`, additionally call `creates_fork(board_after, <rook_destination_square>, mover_color)` and union the result. Rook destinations are deterministic from the castling side (kingside rook → f-file, queenside → d-file, on the mover's back rank). Low-impact; absence of the tag is never a false claim (whitelist).

- **Pin handling is one-sided.** `is_pinned` (Veto C) vetoes a forker pinned to its **own king**, but does **not** model a forker pinned to its **own queen** (legal, but moving it loses the queen). Such a move could still certify. Rare and arguably still a real (if losing) fork, so low-impact; documented, not fixed.

- **Single-piece only by construction.** Discovered double attacks, batteries, and threat-plus-threat by two pieces are invisible to this tag (correct for *fork*, but Greco has **no certified tag for the broader double-attack genus**; the `double_attack` / `attacks_pieces` / eval fields carry those).

- **Static post-move snapshot only — no look-ahead.** It cannot see a fork that requires a preparatory move, nor distinguish a fork the opponent parries with a single defended-and-counterattacking reply.

- **Trusts `move.to_square`.** If `creates_fork` were ever called with a landing square that does not hold the moved piece (caller error), Veto A abstains rather than misreport.

---

## 7. Complexity

**Low.** The detector already exists, is pure/engine-free, and runs in O(attack-set size) ≈ O(8) per call over one square's `attacks()`, plus a handful of O(1) `is_pinned` / `is_attacked_by` checks — no search, no board copies, no engine. The vetoes are cheap necessary-condition tests ordered cheapest-first.

The **new** work this spec recommends is additive and fail-safe:
- The **evidence bundle** (§5) — a mechanical re-expression of values the function already computes (attacker, target squares, label, hanging flag); surfaced through the existing `_safe()` / try-except posture, requiring no change to the core geometric logic. Net new risk: minimal.
- The **two optional accuracy fixes** (§6: king-forker guard; castling rook-square) — each an **additive veto or an extra wrapper call** that can only return *fewer* or *more-correct* forks, never break a true certification. Both may be deferred; the tag is sound without them.

**Files:**
`C:\Users\詹天哲\Documents\greco\analyzer.py` — `detect_double_attack` (lines 270–332); `FORK_TARGET_TYPES` / `PIECE_VALUES` / `PIECE_NAMES` (lines 203–220).
`C:\Users\詹天哲\Documents\greco\factgate.py` — `creates_fork` wrapper (lines 198–204); `certified_claims` wiring (lines 277–279); `GATED_TAGS` (lines 222–229).
`C:\Users\詹天哲\Documents\greco\narrator.py` — `_move_to_dict` Tier-1 `certified` / evidence slot (lines 440–462).

**Verification provenance:** every FEN in §3–§4 and the three corrected factual claims in §2 (`is_pinned` turn-independence, king-as-target geometry, castling `to_square`) were executed against the live `detect_double_attack` on python-chess 1.11.2 in the venv at `C:\Users\詹天哲\Documents\greco\venv` while writing this spec.
