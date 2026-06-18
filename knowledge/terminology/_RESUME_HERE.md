# RESUME HERE — Chess Terminology Glossary review (paused 2026-06-15)

> Handoff for the next session. James paused to save tokens; `/handoff` wasn't available, so
> **this file is the handoff.** Read this, then `chess-terminology-glossary.md`, then continue
> the term-by-term review exactly as described under "The method."

## What this work is
**Glossary-first development (Priority #1b)** for Greco's commentary-accuracy wave. We're building
a chess **terminology glossary** — simultaneously the narrator's *vocabulary* and the *source
material* for the fact-gate predicates — and reviewing **each detectable term's definition with
James, one at a time**, before any of it is treated as settled or written into code.

Sequencing rule (James): the glossary (#1b) **precedes** the predicate code (#1c) — the glossary
defines the term universe and the precise condition each predicate must test.

## The method (continue exactly this)
For each term, present **via `AskUserQuestion`**: the **prose definition** + a **`→ Verifiable
as:`** line (the precise testable condition that becomes the predicate). James answers
"Good as-is" or "Needs a fix" (with a note). On approval, mark the term `✅ approved 2026-06-15`
inline in the glossary. On a fix, refine — when he says "show me how experts define it," pull
**verbatim** definitions from the web (Wikipedia glossary + dedicated articles + a second source)
— and re-present. Up to 4 terms per `AskUserQuestion` call. **The glossary file is the live
record** (✅ approved / ⏸ open markers are inline).

## Core doctrine settled this session (do not relitigate)
- **Three tiers.** `[A]` geometric predicate (decidable board test — build now) · `[B]`
  checkable-but-harder (DEFAULT-DENY: withheld from the narrator until a detector + acceptance
  test ship, paced in one at a time) · `[C]` genuinely free (NO checkable claim — effectively
  empty).
- **"Nothing checkable is ever free."** Hard-to-detect ≠ not-a-claim. The earlier
  "non-falsifiable register (free)" framing was a dangerous loophole and is gone (James's catch).
- **`[B]` splits into `[B-engine]` and `[B-human]`.** `[B-human]` = aesthetic/"human" words
  (brilliant, beautiful, elegant, a practical try, enterprising…) — these must be gated to a
  model of **human perception** (surprise, difficulty, error-probability → the **Maia /
  human-vs-engine track**), **NOT** to raw eval/sacrifice/material. This is James's key insight;
  fold it into `docs/specs/TERMINOLOGY_TIERS.md` and the Maia design when the `[B]` work begins.
- **Definition ≠ permission.** The glossary supplies vocabulary; the *code* (`factgate.py` →
  `certified_claims()`) decides whether a term may be applied to a position. Internal labels
  (e.g. "x-ray relative pin") are **code-side only — never printed verbatim** in a report;
  narrator phraseology is a separate, later discussion.

## `[A]` review status
**✅ Approved (13):**
- **pin (v3)** — material-consequence: pinned ⟺ moving it would lose material along the line it
  shields (run a static-exchange check on the exposed line); covers a knight pinned to an
  *undefended* b-pawn, not just "a bigger piece directly behind"; the pin **dissolves** once the
  shielded target gains an adequate defender.
- **skewer · discovered attack · discovered check · double check · battery** — as written.
- **fork (v2)** — ≥2 enemy targets, at least one unsaveable on the reply, forker not merely
  hanging.
- **outpost (v2)** — distinguish an **outpost square** (structural: pawn-defended, no enemy pawn
  can ever attack it) from a piece **"on an outpost"** (friendly piece on such a square); rank
  4–7 is *typical, not required*.
- **passed pawn (v2)** — rook-file edge case handled (a-pawn has only the b-file beside it).
- **isolated pawn · doubled pawns** — as written.
- **backward pawn (v2)** — half-open file **NOT** required (D4), recorded as an attribute.
- **rook lift (v2)** — explicitly distinct from *doubling rooks* (a lift is one rook up-then-
  across; doubling is a two-rook battery).

**⏸ Open — RESUME HERE (two questions for James):**
1. **Infiltration / penetration** — broadened beyond rook-on-7th to *any* piece deep in the
   enemy camp (knight on a deep weak square, queen, endgame king). **Needs his call** on whether
   the provisional verifiable-as (heavy piece on the 7th/8th **OR** a piece on a pawn-unattackable
   square ≥ rank 5) is inclusive/precise enough.
2. **Fianchetto** — redundant "knight-pawn advanced" clause dropped. **Needs his ruling on the
   Timoshenko edge case** (1.e4 Nf6 2.Nc3 d5 3.e5 d4 4.exf6 dxc3 5.fxg7 cxd2+ 6.Bxd2 Bxg7): is a
   bishop that reaches g7 **by capture, with no g-pawn**, "fianchettoed"? Claude's lean: the
   supporting pawn is constitutive → no. Decide: pure bishop-placement vs. requires the
   knight-pawn present (g6/g3 · b6/b3).

**Not yet reviewed (~6):** back-rank weakness, luft, mate-in-one threat, open file, half-open
file, zugzwang `[A* approximate]`. Then the `[B-engine]`/`[B-human]` terms and the rest.

## Deferred / flagged
- **Timoshenko Variation → opening corpus**: a task chip was spawned (id `task_05070134`) to add
  the line as an annotated PGN under `knowledge/opening_theory/games/`.
- **`[B-human]` ↔ Maia**: fold the human-perception-detector idea into `TERMINOLOGY_TIERS.md` and
  the Maia design when `[B]` work starts.
- **Contemplated next direction (James):** a `/grill-me` interview + a **Product Requirements
  Document (PRD)** to drive *large* changes in the Greco project. Likely a separate, bigger
  initiative — surface it early next session.

## Files to read (in order)
1. `knowledge/terminology/chess-terminology-glossary.md` — the glossary (live record, ✅/⏸).
2. `docs/specs/00_INDEX.md` — the design-package index + decisions D1–D7.
3. `docs/specs/PREDICATE_SPECS.md` — the 18 adversarially-reviewed predicate specs (operational
   detail behind the `[A]` terms).
4. `docs/specs/TERMINOLOGY_TIERS.md` — the gating doctrine (update with `[B-human]`).
5. `docs/specs/KNOWLEDGE_CONTENT_PLAN.md` — the eventual deposit format (`text.txt` + `meta.json`
   + MANIFEST row) once definitions are approved.
6. Notion: the **Greco** page + **Greco Dev Log** (cross-device source of truth).

## Working-method reminders
- James is learning CS through this project: state the symptom, then the invariant that should
  hold, then offer his hypothesis as one option and a better one if it exists. **Tell him when a
  hypothesis is wrong or incomplete — don't just confirm.** Define jargon; first principles.
- Engage with his chess reasoning — his pin and fianchetto catches were both correct and improved
  the specs.
- **Machine/tooling:** do **NOT** use heavy parallel `Workflow` fan-outs here (3 host-level
  deaths last time; subagent file-writes don't persist — capture via return values). Prefer
  sequential `Agent` calls or direct work. Non-ASCII path → always `pathlib` + `encoding="utf-8"`
  + `PYTHONUTF8=1`.
- Nothing is committed to git; all changes are local in the working tree. No version bump
  (still 0.10.0).
