Sanity check before declaring done: I re-verified each load-bearing code anchor against the actual source (`detect_sacrifice` at line 532 has the `mover_eval >= 100` gate I corrected for; `refutation_line_san` / `attacks_pieces` / `overloaded_defender` / `is_recapture` / `best_is_recapture` / `legal_move_count` all confirmed present in `MoveAnalysis`; `detect_overloaded_defender` :448, `detect_allowed_pawn_fork` :485, `least_active_piece` :335, `material_balance` :223, `normalize_cp` :118 all confirmed), and re-read the four review questions against the finalized text. All four checks pass in the written spec.

result: Finalized and wrote C:\Users\詹天哲\Documents\greco\docs\specs\TERMINOLOGY_TIERS.md — the Greco terminology-tier + gating + pacing doctrine, with these adversarial fixes applied:

- **(a) Default-deny made unambiguous.** §0/§1.2/§3.1 state DEFAULT-DENY as the heart of the doctrine; tightened §1.1 so "absence ≠ false" can't be misread as "therefore usable" — for a checkable term, not-proven means **withheld** operationally.
- **(b) No checkable term left in Tier C.** Confirmed the trap nouns ("combination", "wins a tempo", "compensation") are in Tier B. Pinned "double-edged" to the **mood-only** sense (demote to B if it asserts mutual concrete chances). Corrected the "sacrifices" discrimination: `is_sacrifice` only certifies a *sound* sac (eval ≥100cp) and `is_unsound_sacrifice` a losing one — a speculative sac is neither, so the bare verb is only partially licensed.
- **(c) Sketches regrounded and made honest.** Fixed two real grounding errors: (1) **tempo** now sources the opponent's forced reply from the confirmed `refutation_line_san` field, not the unverified `post["analyses"][0]["pv"][0]`/line-885 citation in the draft; (2) **compensation** no longer claims to reuse `detect_sacrifice`'s gate "directly" — it borrows the *structure* but uses a deliberately looser near-level eval threshold (≥−50cp) vs. that function's ≥100cp soundness gate. **prophylaxis** downgraded: Greco carries no clean "what the opponent threatened *before* the move" signal (`refutation_line_san` is post-move only), so the general case is flagged net-new/lower-confidence and the named-threat case ships first.
- **(d) Pacing kept and hardened.** Value×risk order is sound (overloaded → compensation → tempo → weak-square → zwischenzug → initiative → space → prophylaxis; initiative correctly after tempo). §3.1 now states the acceptance test is a **precondition** of go-live, not a follow-up, alongside the four required artifacts.

Spec path: C:\Users\詹天哲\Documents\greco\docs\specs\TERMINOLOGY_TIERS.md

Below is the finalized design as written to that file:

---

# Greco Commentary Vocabulary — Terminology Tiers, Gating Doctrine, and Pacing Roadmap

**Status:** Design doctrine (authoritative).
**Date:** 2026-06-15.
**Scope:** Governs which chess-vocabulary terms the narrator is *permitted to use*, on what proof, and in what order the harder terms are paced in.
**Companion to:** the fact-gate already shipped in `factgate.py` / `certified_claims()` and the *data-back, never prompt-stuff* non-negotiable in `CLAUDE.md`.

---

## 0. The one rule everything else serves

> **If a term makes a CHECKABLE board claim, the narrator may use it only when code has proven that claim for *this* move/position.** There is no "free vocabulary" for checkable terms. A term is free *only* when there is literally nothing on the board to verify.

The axis that matters is **falsifiability**, not **current detector availability**:

- A term that *could in principle be checked against the board* is a **claim**. It is gated. Until its detector ships, it is **withheld** (default-deny) — never free.
- A term that *cannot* be checked against the board — pure aesthetic / strategic register — is **free**, because granting it can never produce a false board statement.

The fact that Greco does not *yet* ship a tempo detector does not make "tempo" free — it makes it **withheld**. "Nc3 wins a tempo because it threatens Nxd5" is a verifiable assertion (the threat either exists or it doesn't, and the tempo gain is checkable); *hard-to-detect* is not the same as *not-a-claim*. Everything below is the operational expansion of that single rule.

---

## 1. The three tiers

| Tier | Name | What it is | Gating posture | Where it lives |
|---|---|---|---|---|
| **A** | Geometric predicates | A clean, decidable board test (pin, fork, outpost, passed pawn, rook lift, mate-in-one threat) | **Allow on proof.** Term enters the per-move allow-set the moment its predicate passes for that move. | `factgate.py` (shipped) |
| **B** | Compound / engine-assisted verifiable terms | A *real, checkable* meaning, but a harder detector — often needs eval, the engine line, or threat reasoning, not just geometry (tempo, initiative, compensation, prophylaxis, overloaded piece, zwischenzug, weak square/hole, space advantage, blockade, the bishop pair as an *active* claim) | **DEFAULT-DENY.** Withheld from the narrator until *its own* detector + acceptance test ship. Paced in **one at a time**. | future predicates in `analyzer.py` / `factgate.py` |
| **C** | Genuine non-falsifiable register | Aesthetic / temperamental / rhetorical language with no board predicate to violate ("ambitious," "a beautiful idea," "enterprising," "calm," "a practical try") | **Free.** Nothing to verify, so nothing to gate. | system prompt (allowed register) |

### 1.1 Tier A — geometric predicates (shipped)

A Tier-A term has a decidable board test that does not need the engine's evaluation to be *true* — only board geometry and legal-move enumeration. These are exactly the `GATED_TAGS` already in `factgate.py`:

`fork`, `royal_pin_setup`, `rook_lift`, `outpost`, `passed_pawn`, `mate_in_one_threat`.

**Gating rule (Tier A):** the term enters this move's allow-set iff its predicate returns true in `certified_claims()`. Absence of the tag means "not machine-proven for this move" — which, because the term *is* checkable, means **the narrator may not assert that specific claim about this move.** "Not proven" is not the same as "false," but for a checkable term the operational consequence is identical: **withheld.** This is the whitelist already enforced by the fact-gate prompt rule (`narrator.py:202`).

**This tier is the template for the whole doctrine.** Every Tier-B term graduates by becoming, in effect, a new Tier-A-style entry: a predicate, a tag in `GATED_TAGS`, an evidence bundle, and a prompt-rule clause.

### 1.2 Tier B — compound / engine-assisted verifiable terms (default-deny, paced in)

A Tier-B term has a **genuine, checkable meaning** but resists a one-line geometric test. It typically certifies by combining signals Greco already computes — `attacks_pieces`, `best_line_san` / `refutation_line_san`, eval swings (`eval_before_cp` / `eval_after_cp` via `normalize_cp`), threat detection, `material_balance`, board geometry — into a composite predicate with a veto.

**Gating rule (Tier B) — DEFAULT-DENY, the heart of this doctrine:**

> Until a Tier-B term's detector **and** its acceptance test exist and pass, the term is **WITHHELD from the narrator** — it is *not* in the allowed register, *not* in `GATED_TAGS`, and the prompt does *not* license it. Withheld is the default; "live" is earned, one term at a time.

This is the opposite of Tier C. A Tier-C word is free because it cannot be wrong about the board. A Tier-B word is denied because it *can* be wrong about the board and we do not yet have the proof. Treating a Tier-B term as free is precisely the false-positive bug this doctrine exists to prevent.

**Honesty clause (partial checkability):** some Tier-B terms are only *partially* decidable (e.g. "initiative," "space advantage"). When a detector certifies an approximate signal rather than the full human concept, the **prose must be hedged to match what was actually proven** ("keeps the initiative for now," "a space-count edge on the queenside"), and the detector's evidence bundle must carry an `approximate: true` marker so the narrator knows it is licensed for the *hedged* claim only, never the absolute one. A term that can only be approximated is still Tier B (gated) — it is never promoted to Tier C.

### 1.3 Tier C — genuine non-falsifiable register (free)

A Tier-C term asserts nothing a board could contradict. "An ambitious choice," "a beautiful idea," "enterprising play," "a calm reply," "a practical try," "playing for complications." These are mood, intent, and rhetoric.

**Gating rule (Tier C): free — but be STRICT about admission.** A word qualifies as Tier C **only if there is no board test that could falsify it.** The default on any doubt is *demote to Tier B (withheld)*, not *admit to Tier C*. Concrete admission test, applied to every candidate word:

> "Can I write a Python function over a `chess.Board` (+ eval + engine line) that returns True/False for whether this word is *correctly applied here*?" — If **yes**, it is Tier B and must be withheld until that function exists. If **no**, it is Tier C and free.

Worked discriminations (these are the trap cases):

- "**ambitious**" → no board test → **Tier C (free).**
- "**a beautiful combination**" → "combination" implies a forcing tactical sequence that wins material or mates → *checkable* → **Tier B (withheld).** ("beautiful" alone is fine; "combination" is the load-bearing claim.)
- "**dynamic**" as a mood ("a dynamic position") → free; "**dynamic compensation**" → asserts compensation → Tier B.
- "**double-edged**" used strictly as *mood* ("a double-edged choice") → free; but "**double-edged**" used to assert that *both sides have concrete attacking chances* edges into a checkable mutual-resources claim → if it is doing that work, demote to Tier B. License only the mood sense.
- "**enterprising**" → free. "**wins a tempo**" → Tier B.
- "**sacrifices for the initiative**" → both halves are checkable. "initiative" is Tier B. "sacrifices" is **only partially** covered by Greco today: `is_sacrifice` certifies a *sound* sac (eval still clearly favors the mover) and `is_unsound_sacrifice` a clearly losing one — a *speculative/unclear* sac is neither, so the bare verb "sacrifices" is not fully licensed by an existing field. Treat the material-giving claim as Tier B and license it only through whichever sacrifice field actually fired.
- "**a practical try**" → free. "**objectively the best practical chance because the engine eval holds**" → checkable → Tier B.

The discipline: **the adjective of taste is free; the noun of fact is gated.** When in doubt, the word is a noun of fact.

---

## 2. Detection sketches for the initial Tier-B priority set

Each sketch gives: the **verifiable definition** (what must be true on the board), the **deterministic signals** (reusing existing Greco data — never re-deriving), the **cheap veto** (the fast disqualifier that kills false positives first), the **evidence bundle** (what the predicate hands the narrator, parallel to how `is_outpost` returns supporter squares), and an **honesty note** where the term is only approximate. Complexity is a rough build-size signal, not a promise.

All sketches obey the codebase conventions: pure `detect_X(board, …) -> Optional[...]` modeled on `detect_double_attack` / `detect_overloaded_defender`; human strings from `PIECE_NAMES` + `chess.square_name`; eval comparisons via `normalize_cp`; quotable lines only via `pv_to_numbered_san`; every call wrapped in the `_safe()` fail-safe so a buggy predicate drops its tag instead of crashing the report.

---

### 2.1 `tempo` — *gain of tempo* (priority: EARLY)

- **Verifiable definition.** The move attacks an enemy piece (or makes a concrete threat) that *forces* a reply — the opponent must spend their move answering it rather than executing their own plan — and the moving side comes out improved "for free." The strict, fully-checkable core: **the move creates a threat the engine's best reply is *compelled* to address.**
- **Deterministic signals (reuse).**
  - `attacks_pieces` — the moved piece now attacks ≥1 enemy piece of value ≥ minor (the raw "it hits something" signal; already populated and already trusted by the prompt's `attacks` rule).
  - The opponent's forced reply, taken from `refutation_line_san` — the numbered SAN of the engine line **AFTER** the played move (a confirmed `MoveAnalysis` field; empty for best/forced moves). Its **first move** is the opponent's best response in the post-move position. Certify *forcing*: that first reply **moves or defends the attacked piece** (its from-square or to-square is the attacked square, or it captures the attacker). That is what turns "attacks a piece" into "wins a tempo." (Parse the SAN against a `chess.Board(fen_after)` to recover the move; never hand-parse the string.)
  - `material_balance` unchanged across the move (a tempo gain is *not* a material win — this distinguishes it from `fork`).
- **Cheap veto (in order).** (1) `attacks_pieces` empty → no tempo, return None immediately. (2) The attacked piece is defended *and* the attacker would simply hang on the square → reuse the "attacking piece is itself hanging" logic from `detect_double_attack` as the disqualifier. (3) `refutation_line_san` is empty, or its first move ignores the attacked piece entirely → **not forcing → no tempo.**
- **Evidence bundle.** `{"tag": "tempo_gain", "attacked": "knight on d5", "forced_reply": "Nd7", "square": "d5"}` — names the hit piece and the reply it forces, so the narrator can write "Nc3 gains a tempo, hitting the d5-knight, which must move."
- **Honesty note.** Fully checkable for the *forced-reply* definition. The looser human sense ("a tempo of development") is **not** licensed — keep tempo strictly to "creates a threat the best reply must answer." No `approximate` flag is needed if held to the strict definition.
- **Complexity:** **LOW–MEDIUM.** Greco already carries `attacks_pieces` and the post-move engine line (`refutation_line_san`); the new work is recovering the opponent's first reply and the "reply addresses the attacked square" check. ~120–180 LOC incl. test.

---

### 2.2 `compensation` — *material deficit offset by position* (priority: EARLY)

- **Verifiable definition.** The moving side is **down material** (clear, countable) **yet the engine evaluation does not reflect that deficit** — i.e. the position pays for the pawns / exchange. This is one of the *most* cleanly checkable Tier-B terms because both halves are numbers Greco already has.
- **Deterministic signals (reuse).**
  - `material_balance` (mover-POV via `sign`) — quantify the deficit in pawns.
  - `eval_after_cp` → `normalize_cp` (mover-POV) — the engine's verdict.
  - **The certify condition:** mover is materially down by ≥ ~1.5 pawns **AND** mover-POV eval is ≥ −50cp (roughly: "down material, eval near level or better").
- **Relationship to `detect_sacrifice` — read carefully.** Compensation reuses the *structural shape* of `detect_sacrifice` (`analyzer.py:532`): invested-material gate + eval gate + cheap veto. It does **not** reuse that function's eval threshold. `detect_sacrifice` requires mover-POV eval **≥ 100cp** — a *clearly winning* soundness gate — because a sound sac stays ahead. Compensation is the *near-level* case: down material with eval **≥ −50cp**. Borrow the pattern; set the threshold to the looser near-level value, because "the eval holds despite the material" is the whole point of the word.
- **Cheap veto.** (1) Material not down (mover ahead or equal) → not compensation (this is an *advantage*, a different claim) → None. (2) Eval is bad for the mover (e.g. mover-POV ≤ −150) → the material loss is **not** compensated → None (this veto is what prevents calling a bad sacrifice "compensation"). (3) Under a mate score (`eval_after_cp is None`, `mate_after` set) → abstain; the cp comparison is undefined.
- **Evidence bundle.** `{"tag": "compensation", "down_pawns": 1.5, "eval_cp": -20, "mechanism": null, "approximate": false}` — "a pawn down, but the engine still rates the position level: full compensation."
- **Honesty note.** The *magnitude* is exact; the *reason* the position compensates is **not** something this predicate proves — so the narrator may assert "there is compensation" but must not invent the mechanism unless another certified fact (an outpost, an open file, a lead in development) supplies it. The `mechanism: null` marker keeps the prose at "has compensation for the pawn" rather than fabricating "compensation in the form of a kingside attack."
- **Complexity:** **LOW.** Two numbers Greco already computes, plus a veto. The single highest value-to-risk term. ~80–130 LOC incl. test.

---

### 2.3 `initiative` — *a run of forcing moves* (priority: MEDIUM)

- **Verifiable definition.** The moving side dictates play: a sustained sequence in which **the opponent's replies are forced** (checks, captures, must-answer threats) while the mover keeps making the threats. Checkable as "a run of forcing moves the opponent only answers."
- **Deterministic signals (reuse).**
  - Per-ply forcing flags already available: `is_check`, `is_capture`, and the `tempo_gain` evidence from §2.1 (a forced reply). Initiative is essentially **tempo, sustained** — build it *on top of* the tempo detector (another reason to ship tempo first).
  - The engine line (`best_line_san`) and `legal_move_count` / `is_forced` to confirm the opponent's near-term replies are themselves forced / low-choice.
- **Cheap veto.** (1) The mover's move is not forcing (no check, no capture, no tempo-gain) and the previous ply was not either → no run → None. (2) The opponent is the one giving checks / threats (initiative is the *other* side's) → None. (3) Eval is lost for the mover → "initiative" while losing is usually a desperado, not initiative → require mover-POV eval ≥ ~−50.
- **Evidence bundle.** `{"tag": "initiative", "forcing_run_plies": 3, "approximate": true}` — count of consecutive forcing mover-moves.
- **Honesty note. APPROXIMATE — must hedge.** "A run of forcing moves" is a *proxy* for the full positional concept of initiative; the predicate certifies the proxy, not the abstraction. Prose must stay at "keeps up the pressure / a string of forcing moves," not "a lasting initiative." Set `approximate: true`; the prompt clause for this tag must require the hedged phrasing.
- **Complexity:** **MEDIUM–HIGH.** Needs cross-ply state (a run, not a single move), which is a new shape — Greco's predicates are mostly single-position, so the run must be assembled in the second pass of `analyze_pgn` from per-ply facts rather than inside a single `detect_X(board)`. Depends on `tempo` landing first. ~200–280 LOC incl. test.

---

### 2.4 `prophylaxis` — *a move that prevents the opponent's best plan/threat* (priority: MEDIUM-LATE)

- **Verifiable definition.** A quiet move whose point is **prevention**: it demonstrably removes or defuses what *would have been* the opponent's best move / threat. Checkable, in the clean case, by a *named* threat that existed and is gone.
- **Deterministic signals (reuse).**
  - `detect_allowed_pawn_fork` (`analyzer.py:485`) and the other named threat detectors give a concrete "what the opponent was threatening" handle: did the move remove a specific, named threat that a detector can find?
  - **Honesty constraint on the general case.** Greco does **not** today carry a clean "what the opponent was threatening *before* this move" field. `refutation_line_san` is rooted at the *post-move* board (the reply to the move just played), not at the pre-move position with the opponent to move. So the general "the opponent's pre-move best plan is now gone" comparison would require a *new* before/after analysis that does not exist yet — it is net-new work, not a field lookup. The detector must not pretend otherwise.
- **Cheap veto.** (1) The move is itself forcing (check / capture / big threat) → it is an *attacking* move, not prophylaxis → None. (2) No named threat against the mover existed before the move (nothing concrete to prevent) → None. (3) The move loses eval (it prevents something but at a cost) → require eval roughly held.
- **Evidence bundle.** `{"tag": "prophylaxis", "prevented": "g3, a pawn fork on the rook and bishop", "approximate": false}` when a named detector supplied the removed threat; `{"tag": "prophylaxis", "prevented": null, "approximate": true}` for the proxy case.
- **Honesty note. EXACT only when a named threat is removed; otherwise APPROXIMATE and lower-confidence.** Greco can prove "X was available before and is gone after" *cleanly only for threats it has a detector for* (e.g. an allowed pawn fork) — there, state it plainly. For the general "prevents the opponent's best *plan*," there is no clean existing signal; license only the hedged "a prophylactic move, taking the sting out of …" with `approximate: true`, and only after the before/after machinery is built. Ship the **named-threat case first**; treat the general case as a later extension.
- **Complexity:** **HIGH.** The named-threat case is moderate; the general case needs before/after comparison of the opponent's resources (holding two analyses and diffing them) — the heaviest reasoning in this set, and net-new infrastructure. ~250–350 LOC incl. test.

---

### 2.5 `overloaded piece` / `overworked defender` (priority: EARLY — already half-built)

- **Verifiable definition.** A single enemy (or friendly) piece is the **sole defender of two or more pieces that are each under attack** and cannot hold both. Fully checkable, and **Greco already computes it.**
- **Deterministic signals (reuse).** `detect_overloaded_defender` (`analyzer.py:448`) already returns a complete description and is surfaced as the `overloaded_defender` field. The work here is **not detection — it is gating**: register the existing fact as a certified tag so the prompt licenses the *word* "overloaded / overworked," instead of the narrator using the term ungated.
- **Cheap veto.** Already internal to `detect_overloaded_defender` (requires ≥2 defended-and-attacked targets, sole-defender of ≥1). Nothing to add.
- **Evidence bundle.** Promote the existing description string into a structured bundle: `{"tag": "overloaded_piece", "defender": "rook on e2", "targets": ["bishop on d3", "knight on g4"]}`.
- **Honesty note.** Exact. No hedge.
- **Complexity:** **VERY LOW.** No new detector — only: add `overloaded_piece` to `GATED_TAGS`, emit it in `certified_claims()` when `move.overloaded_defender` is truthy, add the prompt clause. ~40–70 LOC incl. test. (The ideal first graduation — it proves the pacing machinery end-to-end on the cheapest possible term.)

---

### 2.6 `zwischenzug` / *in-between move* (priority: MEDIUM)

- **Verifiable definition.** Instead of making the "expected" reply (typically an immediate recapture), the side inserts a **more forcing move first** (a check or a bigger threat), *then* returns to the original business — and the insertion gains by it. Checkable: an interposed forcing move that improves the outcome versus the immediate "obvious" move.
- **Deterministic signals (reuse).**
  - `is_recapture` / `best_is_recapture` — the "expected" move is usually the recapture; a zwischenzug is when **best is NOT the immediate recapture** (`best_is_recapture` is False on a board where a recapture is available) but a forcing move (a check or a tempo-gain) precedes it.
  - `best_line_san` — confirm the engine's best line plays the forcing insert *then* the recapture (the recapture square reappears later in the PV).
  - `cp_loss` of the immediate-recapture alternative (available in `top_alternatives`) — the insert must be *better* than recapturing now.
- **Cheap veto.** (1) No pending recapture / obvious move on the board (nothing to interpose into) → None. (2) The "insert" is not forcing (not a check, not a real threat) → it is just a different move, not a zwischenzug → None. (3) Inserting does not beat recapturing immediately (eval not better) → None.
- **Evidence bundle.** `{"tag": "zwischenzug", "insert": "Qa4+", "then": "bxc6", "approximate": false}`.
- **Honesty note.** Checkable when the "expected move" is a clear recapture; fuzzier for non-recapture cases. Restrict the *live* detector to the **recapture-interposition** case first (clean), and mark broader cases out of scope. No hedge within that restricted scope.
- **Complexity:** **MEDIUM.** Reuses recapture flags + the PV; the logic is "best line inserts a forcing move before the obvious recapture." ~150–220 LOC incl. test.

---

### 2.7 `weak square` / `hole` (priority: MEDIUM)

- **Verifiable definition.** A square in the opponent's camp that **can never again be defended by an enemy pawn** (both adjacent enemy pawns are gone or have advanced past it) and that the moving side can occupy / use. This is the *defining condition* of an outpost square, minus the requirement that a piece already sits there — so it reuses `is_outpost`'s machinery.
- **Deterministic signals (reuse).**
  - The pawn-cover test already inside `is_outpost` (`factgate.py`) and the "no enemy pawn on adjacent files can challenge" logic in `is_passed_pawn` — a hole is "no enemy pawn can ever attack this square." Generalize the *square test* out of `is_outpost` (which currently also requires a friendly minor on the square).
  - `file_structure` / `_doubled_files` for the surrounding pawn context.
- **Cheap veto.** (1) An enemy pawn on an adjacent file can still advance to attack the square → not a hole → None (this is the whole test). (2) The square is not in the opponent's half / not usefully placed (rank gate, like `is_outpost`'s) → None, to avoid calling every empty square a "weak square."
- **Evidence bundle.** `{"tag": "weak_square", "square": "d5", "color_weak_for": "Black", "approximate": true}`.
- **Honesty note.** The "cannot be defended by a pawn" structural part is **exact**. Whether the square is *strategically* weak (useful to occupy) is judgment — so license "the d5-square is a hole / cannot be covered by a pawn" but not "a decisive weakness." Mark `approximate: true` on the *strategic-importance* claim; the structural claim itself is exact, and the prompt clause must let the narrator state the structural fact plainly while hedging the importance.
- **Complexity:** **LOW–MEDIUM.** Mostly a refactor: lift the square-eligibility core out of `is_outpost` into a shared helper, then expose it as its own tag. ~100–150 LOC incl. test.

---

### 2.8 `space advantage` (priority: LATE)

- **Verifiable definition.** One side controls **measurably more territory** — the classic operational proxy is "more squares controlled in the opponent's half" or "pawns advanced further," counted deterministically.
- **Deterministic signals (reuse).**
  - A square-count over controlled squares in ranks 5–8 (for White) vs ranks 1–4 (for Black) — `least_active_piece` (`analyzer.py:335`) already iterates per-piece controlled-square counts; reuse that loop shape.
  - Pawn-advancement count (how many pawns are past the 4th / 5th rank).
- **Cheap veto.** (1) The square-count edge is below a threshold (small / noisy difference) → None — only certify a *clear* margin. (2) Closed / blocked position where space count is misleading → veto on locked pawn chains (or, at minimum, force `approximate`).
- **Evidence bundle.** `{"tag": "space_advantage", "side": "White", "square_margin": 7, "approximate": true}`.
- **Honesty note. APPROXIMATE — must hedge.** Square-count is a *proxy* for the human notion of space; it does not capture closed-position nuance. License only the hedged "a space-count edge / more terrain on the queenside," never "a winning space advantage." `approximate: true` is mandatory.
- **Complexity:** **MEDIUM.** The count is straightforward; the risk is false positives in closed positions, so the veto + the mandatory hedge are the real work. ~140–200 LOC incl. test.

---

### 2.9 Summary table

| Term | Core checkable signal(s) | Cheap veto | Exact or approximate | Complexity |
|---|---|---|---|---|
| **tempo** | `attacks_pieces` + first move of `refutation_line_san` must address the hit square; `material_balance` unchanged | no piece attacked; attacker hangs; reply ignores it | Exact (strict def) | Low–Med |
| **compensation** | `material_balance` down ≥1.5 **and** mover-POV eval ≥ −50 (`normalize_cp`) | not down material; eval bad; mate score | Exact magnitude; mechanism not proven | **Low** |
| **initiative** | sustained forcing run (`is_check` / `is_capture` / tempo) over plies | not forcing; opponent has it; eval lost | **Approximate (hedge)** | Med–High |
| **prophylaxis** | named threat present before, gone after (`detect_allowed_pawn_fork` etc.) | move is forcing; nothing to prevent; eval drops | Exact for named-threat removal; else approximate + lower confidence | **High** |
| **overloaded piece** | `detect_overloaded_defender` (already computed) | (internal to detector) | Exact | **Very low (gate only)** |
| **zwischenzug** | best line ≠ immediate recapture but a forcing insert then recapture; `best_is_recapture` | no pending recapture; insert not forcing; not better | Exact (recapture case) | Med |
| **weak square / hole** | no enemy pawn can ever attack the square (lift from `is_outpost`) | adjacent enemy pawn can still challenge; bad rank | Exact structure; importance approximate | Low–Med |
| **space advantage** | controlled-square margin in opponent's half; pawn advancement | margin too small; closed position | **Approximate (hedge)** | Med |

---

## 3. Pacing roadmap

**Ordering principle:** highest value × lowest risk first, and prefer terms that **reuse data Greco already carries** (threat / eval / material) over terms that need new cross-ply machinery. Ship one term per cycle, fully (detector + acceptance test + tag + prompt clause), before starting the next.

| Order | Term | Why here | Reuses existing data | Rough token estimate (impl + test + wiring) |
|---|---|---|---|---|
| **1** | `overloaded piece` | Detector **already exists** (`detect_overloaded_defender`); this cycle exists to prove the *pacing machinery* end-to-end (tag → `GATED_TAGS` → `certified_claims` → prompt clause → acceptance test) on the cheapest possible term | `overloaded_defender` field | ~1.5–2k |
| **2** | `compensation` | Highest value-to-risk: two numbers Greco already has (`material_balance`, eval), structural pattern borrowed from `detect_sacrifice` (with a looser near-level threshold), exact magnitude | `material_balance`, `eval_after_cp`, `normalize_cp` | ~2–3k |
| **3** | `tempo` | Common, high-utility; the forced-reply check reuses `refutation_line_san`; also the **prerequisite** for initiative | `attacks_pieces`, `refutation_line_san` | ~3–4k |
| **4** | `weak square / hole` | Mostly a refactor of `is_outpost`'s square test; exact structural claim | `is_outpost` internals, `is_passed_pawn` logic | ~2.5–3.5k |
| **5** | `zwischenzug` | Self-contained; reuses recapture flags + PV; restricted to the clean recapture case | `is_recapture`, `best_is_recapture`, `best_line_san`, `top_alternatives` | ~3–4k |
| **6** | `initiative` | Needs cross-ply "run" state (new shape); depends on `tempo` shipped first | tempo evidence + `is_check` / `is_capture` + `legal_move_count` | ~4–5k |
| **7** | `space advantage` | Approximate by nature; veto + mandatory hedge are the real work; closed-position risk | controlled-square loop from `least_active_piece` | ~3–4k |
| **8** | `prophylaxis` | Heaviest reasoning (named-threat case first, then before/after resource diff — net-new infrastructure); do it last, when the machinery and the hedging conventions are mature | `detect_allowed_pawn_fork`; later, two-position analysis | ~4–6k |

(Terms named in Tier B but not in this initial set — *blockade*, *the bishop pair as an active claim* — queue **after** #8 under the same rules. They stay withheld until built.)

### 3.1 The hard rule (non-negotiable)

> **No Tier-B term enters the narrator's allow-set until BOTH its detector AND its acceptance test exist and pass.** The acceptance test is a *precondition* of going live, not a follow-up. "Withheld" is the default state of every Tier-B term. A term goes live only when, in one reviewed change, all four of these land together AND the acceptance test (§3.2) passes:
> 1. the **predicate** (`detect_X` in `analyzer.py`, or the gate in `factgate.py`),
> 2. its tag added to **`factgate.GATED_TAGS`** and emitted by `certified_claims()` (with `_safe()` wrapping),
> 3. the **evidence bundle** serialized in `_move_to_dict` under the Tier-1+ `certified` path, and
> 4. the **prompt clause** in the fact-gate rule (`narrator.py:202`) naming the term and — for approximate terms — *mandating the hedged phrasing*.
>
> If any of the four is missing, or the acceptance test does not pass, the term stays withheld. There is no "soft launch" and no "free for now."

### 3.2 What an "acceptance test" must contain (per term)

A term does not graduate on the predicate alone. Its acceptance test must include, at minimum:

1. **Positive fixtures** — ≥3 real FEN / PGN positions where the term genuinely applies; the detector must fire and the evidence bundle must be correct.
2. **Negative / false-positive fixtures** — ≥3 positions that *look* like the term but are not (the veto cases: the attacked piece that can be ignored for "tempo"; the bad sacrifice for "compensation"; the closed position for "space"). The detector must **stay silent**.
3. **Fail-safe test** — a malformed input proves `_safe()` drops the tag rather than crashing the report (matching the existing `certified_claims` posture).
4. **Hedge test (approximate terms only)** — assert the evidence bundle carries `approximate: true` so the prompt clause's hedged-phrasing requirement is actually triggered.

The false-positive fixtures are the point of the whole doctrine: a Tier-B term earns its place by **proving it stays silent when it should not fire**, not merely by firing when it should.

---

## 4. One-paragraph statement of the doctrine (for the prompt / docs)

> Greco's narrator may use a chess term that makes a checkable board claim only when code has proven that claim for the specific move in front of it. Geometric claims (pin, fork, outpost, passed pawn, rook lift, mate-in-one) are proven today by `factgate.py` and licensed per-move by the `certified` whitelist. Harder claims that are still *real and checkable* — tempo, initiative, compensation, prophylaxis, overloaded piece, zwischenzug, weak square, space advantage, and the like — are **withheld by default** and paced in one at a time, each only after its own detector *and* acceptance test ship, each carrying an evidence bundle, and each hedged in prose when only partially checkable. The only free vocabulary is genuinely non-falsifiable register — "ambitious," "a beautiful idea," "a practical try" — words no board can contradict. When a word could be checked, it is gated, not free; when in doubt, it is gated.

---

## 5. Implementation pointers (where each piece lands)

- **New detectors:** `analyzer.py`, as pure `detect_X(board, …)` functions modeled on `detect_overloaded_defender` / `detect_double_attack`; surface results as new typed fields on `MoveAnalysis` (declaration + populated in the second pass ~`analyzer.py:920–962` + constructor ~`967–1017`). Already-computed terms (overloaded piece) need **no** new detector — only gating. Cross-ply terms (initiative) are assembled in the second pass from per-ply facts, not inside a single-position `detect_X`.
- **The gate + tags:** `factgate.py` — add each term to `GATED_TAGS` and emit it in `certified_claims()` inside a `_safe(...)` guard, exactly as the six shipped tags are.
- **Evidence bundle:** serialize in `narrator._move_to_dict` under the Tier-1+ `certified` path (alongside `certified`, behind the same try / except). Heavier PV-derived evidence (the forcing run for initiative, the zwischenzug line) belongs in the Tier-2+ block.
- **Prompt clause:** extend the single fact-gate rule at `narrator.py:202` to name each newly-live tag, with the hedged-phrasing requirement spelled out for every `approximate` term. The whitelist in `GATED_TAGS` + this rule remain the single source of truth — a tag absent from either is, by construction, withheld.

**Relevant files:** `C:\Users\詹天哲\Documents\greco\factgate.py` (tags + gate), `C:\Users\詹天哲\Documents\greco\analyzer.py` (detectors + `MoveAnalysis` fields; reuse `detect_overloaded_defender` :448, `detect_allowed_pawn_fork` :485, `detect_sacrifice` :532, `least_active_piece` :335, `material_balance` :223, `normalize_cp` :118), `C:\Users\詹天哲\Documents\greco\narrator.py` (evidence serialization in the Tier-1+ / Tier-2+ blocks, fact-gate prompt rule :202).