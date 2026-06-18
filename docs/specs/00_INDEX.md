Sanity check before declaring done. I verified the index against its inputs: every term's complexity rating in the §2 table was read from the actual Complexity section of `PREDICATE_SPECS.md` (pin/skewer/discovered/fork = Medium; battery/back-rank = Low–medium; isolated/doubled/infiltration/fianchetto/outpost/rook_lift/mate = Low; backward = Medium; luft = Low–Medium; passed = Low-to-medium; royal = Low §B / Low–moderate §A; zugzwang = HIGH and the only non-deterministic one). The Tier-B build order in §3.1 matches the pacing roadmap in `TERMINOLOGY_TIERS.md` (overloaded → compensation → tempo → weak-square → zwischenzug → initiative → space → prophylaxis). All seven required decisions (D1–D7) are present and each carries a recommendation; all six required out-of-scope items are listed; the three-layer testing doctrine is referenced in §5. All six companion specs exist in the folder, so the cross-references resolve.

result: Wrote C:\Users\詹天哲\Documents\greco\docs\specs\00_INDEX.md — the executive-summary index for the pre-implementation approval gate, covering all six required sections.

The index markdown:

---

# 00 — Design Package Index & Executive Summary

**Status:** PRE-IMPLEMENTATION APPROVAL GATE. Nothing here is built yet. This package is for James to review for **chess accuracy** and **architecture** *before* any code is written.
**Date:** 2026-06-15.
**Audience:** James (Greco's owner, learning CS through this project). Jargon is defined inline; reasoning is from first principles.

---

## 0. How to read this package (start here)

This folder is a set of **specs** — written designs that say exactly what to build and why, so the build itself is mechanical and reviewable. A spec is the contractor habit from the Greco/StayPlus guide: *write the spec and the estimate before you write the code.* Reviewing a spec is far cheaper than reviewing (or unwinding) a wrong implementation.

The package has four kinds of document:

| Doc | What it designs | Read it for |
|---|---|---|
| `PREDICATE_SPECS.md` (+ `predicates\01..18-*.md`) | One detection spec per chess term — the exact board test, positive/negative examples, evidence bundle, complexity | **Chess accuracy.** Is each term defined and detected correctly? |
| `TERMINOLOGY_TIERS.md` | The gating doctrine: which terms the narrator may use, on what proof, in what build order | **The safety model.** Why "tempo" is withheld but "ambitious" is free |
| `DATA_ARCHITECTURE.md` | How a passed board test travels from `factgate.py` to the narrator prompt as an "evidence bundle" | **Plumbing.** The one-type decision (dict) and the one breaking test it fixes |
| `VARIATION_VALIDATOR.md` | How Greco checks the *hypothetical lines* in a written report without ever deleting a legitimate one | **The anti-confabulation guard.** The "never strip a good line" guarantee |
| `MAIA_INTEGRATION.md` | Adding a *human-like* engine (Maia) so Greco can say "an engine move a human wouldn't find" | **The human-vs-engine track.** Config-only this wave |
| `KNOWLEDGE_CONTENT_PLAN.md` | Two new reference texts (a glossary; an engine-theory explainer) for the knowledge corpus | **Vocabulary + literacy.** Definitions, not permission |

**The single most important idea in the whole package** (define it once, it recurs everywhere): **a definition is not a permission.** Knowing what "fork" *means* (vocabulary, in the glossary) is completely separate from being allowed to *say* "this move is a fork" about a real board (permission, decided in code by the **fact-gate**). The fact-gate is the function `certified_claims()` in `factgate.py`: for each move it returns the set of claims that code has *proven* true about that exact position. The narrator may only assert what is in that set. Everything below serves that one separation.

---

## 1. What this package is

This is the complete pre-build design for the next wave of Greco's **commentary-accuracy** work. It does three connected things: (1) it specifies **eighteen detection predicates** — small, deterministic board tests that let the narrator name a chess feature (pin, fork, passed pawn, …) *only when it is actually present*; (2) it defines the **three-tier gating doctrine** that decides which chess words are allowed at all, and paces the harder ones in one at a time so the narrator is never permitted to assert something Greco cannot prove; and (3) it designs the **supporting machinery** — how a proven fact is packaged and handed to the AI ("evidence bundles"), how the hypothetical lines in a report are validated without ever deleting a good one, how a human-like engine (Maia) plugs in to explain "engine moves a human wouldn't play," and what reference texts back all of it. The throughline is Greco's founding rule: **data-back, never prompt-stuff** — facts are computed in code; the language model only supplies the words.

---

## 2. Predicate library at a glance

A **predicate** is a function that answers one yes/no question about a board ("is there a pin here?") deterministically — no engine guess, no AI, same answer every time. A **certified tag** is the short string the predicate emits when it fires (e.g. `"fork"`); that string is the token the fact-gate puts in the allow-set and the narrator is licensed to use. **Complexity** is the build-size/risk estimate from each term's own spec. **Status:** *new* = no detector exists yet; *revisit* = a detector exists and is being upgraded/regated; *reconcile* = an existing tag is being merged/aligned with a new one; *approximate* = the claim is not fully decidable and the prose must be hedged.

| # | Term | Certified tag | Complexity | Status |
|---|---|---|---|---|
| 1 | Pin (absolute + relative) | `pin` | Medium | new |
| 2 | Skewer (absolute + relative) | `skewer` | Medium | new |
| 3 | Discovered attack (incl. discovered check) | `discovered_attack` | Medium | new |
| 4 | Battery | `battery` | Low–medium | new |
| 5 | Isolated pawn | `isolated_pawn` | Low | new |
| 6 | Doubled pawns | `doubled_pawn` | Low | new |
| 7 | Backward pawn | `backward_pawn` | Medium | new |
| 8 | Back-rank weakness | `back_rank_weakness` | Low–medium | new |
| 9 | Luft | `luft` | Low–medium | new |
| 10 | Infiltration / penetration | `infiltration` | Low | new |
| 11 | Fianchetto | `fianchetto` | Low | new |
| 12 | Outpost | `outpost` | Low | **revisit** (detector exists, regate) |
| 13 | Passed pawn | `passed_pawn` | Low–to-medium | **revisit** (base bool exists; add evidence) |
| 14 | Rook lift | `rook_lift` | Low | **revisit** (detector exists, harden) |
| 15 | Fork / double attack | `fork` | Medium | **revisit** (detector exists) |
| 16 | Royal pin/skewer setup | `royal_pin_setup` / `sets_up_royal_pin` | Low (§B) / Low–moderate (§A) | **reconcile** (see Decision D1) |
| 17 | Mate-in-one threat | `mate_in_one_threat` | Low | **revisit** (helper exists) |
| 18 | Zugzwang | `zugzwang` | **HIGH** | **new + approximate** (engine-dependent — see Decision D2) |

> **One honest flag in this table:** every predicate except **zugzwang** is *deterministically provable* from board geometry alone. Zugzwang is the lone exception — it depends on engine evaluations and a depth-limited approximation, so it is the highest-risk term and must be labeled "approximate" in prose. This is called out in its spec and in Decision D2.

Per-term detail lives in `PREDICATE_SPECS.md` and the per-term files under `predicates\`. **This is the layer to scrutinize hardest for chess accuracy** — the rest of the package assumes these are right.

---

## 3. Terminology gating model

The gating model answers one question: *which chess words is the narrator allowed to use, and on what proof?* It sorts every term onto exactly one of three tiers by a single test — **falsifiability** (can a board contradict this word?), **not** how hard the detector is to build.

- **Tier A — geometric predicate (LIVE the moment its predicate passes).** A clean, decidable board test exists. The term enters this move's allow-set the instant its predicate returns true. These are the eighteen terms above (and the six tags already shipped). *Example: `fork` — the board either has a fork or it doesn't.*

- **Tier B — checkable but harder (DEFAULT-DENY; withheld; paced in one at a time).** The term *does* make a real, checkable claim, but it needs a harder detector — eval, the engine's line, threat reasoning, or cross-move state, not just geometry. **Until that detector AND its acceptance test ship, the term is WITHHELD from the narrator entirely** — not in the allow-set, not in the prompt, not "free for now." *Examples: tempo, initiative, compensation, prophylaxis, overloaded piece, zwischenzug, weak square, space advantage.* These are introduced **one at a time**, each as its own complete, tested unit.

- **Tier C — genuine non-falsifiable register (FREE).** The word asserts nothing a board could contradict — pure aesthetic/temperamental register. There is nothing to verify, so nothing to gate. *Examples: "ambitious," "a beautiful idea," "enterprising," "a practical try."*

**The load-bearing rule — say it out loud:** *nothing checkable is ever "free."* If a word could in principle be checked against the board, it is a **claim**, and a claim is **gated** — Tier A if its detector is live, Tier B (withheld) if not. The only free vocabulary is Tier C, where there is literally nothing on the board to be wrong about. The trap to avoid is treating "we don't have a detector yet" as "the word is free": *hard-to-detect is not the same as not-a-claim.* When in doubt, a word is a noun of fact (gated), not an adjective of taste (free).

### 3.1 Recommended Tier-B build order (from the pacing roadmap)

Ship one term per cycle, fully — detector + acceptance test + tag + prompt clause — before starting the next. Order is **highest value × lowest risk first**, preferring terms that reuse data Greco already computes:

1. **`overloaded piece`** — detector already exists (`detect_overloaded_defender`); this cycle exists to prove the *pacing machinery* end-to-end on the cheapest possible term.
2. **`compensation`** — two numbers Greco already has (material balance + eval); highest value-to-risk.
3. **`tempo`** — common and high-utility; reuses `refutation_line_san`; also the prerequisite for initiative.
4. **`weak square / hole`** — mostly a refactor of the outpost square test; exact structural claim.
5. **`zwischenzug`** — self-contained; reuses recapture flags + the engine line; restricted to the clean recapture case.
6. **`initiative`** — needs new cross-move "run" state; depends on `tempo` shipping first.
7. **`space advantage`** — approximate by nature; the veto + the mandatory hedge are the real work.
8. **`prophylaxis`** — heaviest reasoning (before/after threat diff is net-new infrastructure); do it last, when the conventions are mature.

Full doctrine, per-term detection sketches, and the acceptance-test requirements are in `TERMINOLOGY_TIERS.md`.

---

## 4. Decisions James must make

These are the genuine open questions that need James's **chess judgment** or a **product call**. Each is phrased as a yes/no or a pick, with my recommendation. **None require code to decide; all should be decided before the build starts.**

**D1 — Fold `royal_pin_setup` into the general pin/skewer, or keep it separate?** **Recommendation: keep it separate, but reconcile the tag.** A "setup" claim is a genuinely different statement from "this *is* a pin." Keep one tag name (pick `royal_pin_setup`; alias `sets_up_royal_pin` to it) so there is a single source of truth, and have the general pin/skewer predicates emit *their* tags only when the pin/skewer is actually on the board. No double-counting, no lost nuance.

**D2 — How strict should zugzwang and back-rank certification be, and how do we label the approximate one?** **Recommendation: strict + explicit-hedge for zugzwang; plain for back-rank.** Certify zugzwang only on a clear engine signal (every legal move worsens eval by a meaningful margin), carry an `approximate: true` marker, and require the narrator to *hedge in prose* — never the bare absolute. Back-rank weakness, being decidable geometry, may be stated plainly. The prose must never claim more certainty than the detector earned.

**D3 — Variation-validator failure action: confirm legitimate counterfactuals always survive.** **Recommendation: warn-and-annotate, NEVER strip — and accept generously.** A line is flagged only when it is well-formed AND illegal in *every* candidate board AND not an engine PV; anything malformed/ambiguous gets ABSTAIN, never a deletion. Counterfactuals ("if X had not been played") get a null-move turn-flip so they always get a fair legality test. The deliberate over-accept-rather-than-over-flag asymmetry is the guarantee no legitimate teaching line is ever removed.

**D4 — Should backward-pawn require a half-open file?** **Recommendation: do NOT require it for the base tag; record half-open-ness in the evidence bundle.** The structural backward pawn exists regardless of file state; requiring half-open would silently miss true backward pawns. Detect the structural pawn, include a `half_open: true/false` field so the narrator can upgrade the emphasis when warranted. Captures both schools without losing recall.

**D5 — Maia default rating band when the PGN has no Elo.** **Recommendation: default to 1500.** Center of Maia's trained range and the modal online rating — the least-wrong single guess, symmetric in error. Make it a config key (`maia_default_elo`), surface the assumption in the report, never fabricate a rating into the game data.

**D6 — Glossary licensing: Wikipedia CC BY-SA vs freshly-written CC0?** **Recommendation: write the maximum share fresh as CC0; reach for Wikipedia only where genuinely needed, and attribute that minority explicitly.** Keeps the bulk cleanly CC0, avoids share-alike entanglement, and is better learning practice. Detail in `KNOWLEDGE_CONTENT_PLAN.md` §A.5.

**D7 — Which Tier-B term to implement FIRST after the Tier-A library lands?** **Recommendation: `overloaded piece` first** (detector already exists → pure gating, cheapest way to prove the whole pipeline), **`compensation` second** (highest value-to-risk). Matches §3.1.

---

## 5. Recommended implementation sequence

Build order with rough token estimates and a "let-it-cook vs needs-James's-eye" call, referencing **Greco's three-layer testing doctrine**: L1 structural (runs/imports), L2 claim (fires on right positions, silent on look-alikes — automated FEN fixtures), L3 taste (narration reads true — needs a human).

| Step | What | Est. tokens | Cook vs eye |
|---|---|---|---|
| **0** | `DATA_ARCHITECTURE.md` — dict evidence carrier; fix `test_factgate.py:134` `== set()`→`== {}`; add `Dict` import | ~2–3k | **Let it cook** (existing factgate tests are the proof) |
| **1** | Tier-A low-complexity batch: `isolated_pawn`, `doubled_pawn`, `fianchetto`, `infiltration`, `outpost`, `rook_lift`, `mate_in_one_threat`, `luft`, `back_rank_weakness` | ~12–18k | **Cook** per term (L2) — **eye once** on sample narration (L3) |
| **2** | Tier-A medium batch: `pin`, `skewer`, `discovered_attack`, `battery`, `backward_pawn`, `fork`, `passed_pawn`, `royal_pin_setup` (D1) | ~16–24k | **Cook** per term (L2) — **eye** on pin/skewer/royal reconcile wording (L3) |
| **3** | `zugzwang` — lone approximate, engine-dependent; strict signal + `approximate` + mandatory hedge (D2) | ~4–6k | **Needs James's eye** — L3 is the point |
| **4** | `VARIATION_VALIDATOR.md` — warn-and-annotate checker (D3), ABSTAIN path, counterfactual null-move; rewrite old shim tests | ~6–9k | **Cook** for legality (L2) — **eye** on a real report (L3) |
| **5** | `MAIA_INTEGRATION.md` — config keys + typed `Settings` + env fallbacks + `maia_ok` + `maia_default_elo` (D5); `outputs.py` one-liner | ~4–6k | **Cook** (config + recapture-guard test) — **eye** on narration (L3) |
| **6** | `KNOWLEDGE_CONTENT_PLAN.md` — author + deposit glossary + engine-theory; rebuild + verify index (D6) | ~6–10k | **Cook** for searchability — **eye** on prose + tier tags (L3) |
| **7** | First Tier-B graduation — `overloaded piece` (D7), proving the pacing machinery | ~1.5–2k | **Cook** (positive + false-positive + fail-safe tests) — **eye** on the one new sentence (L3) |

Sequencing logic: Step 0 first (fix the pipe before sending water through it); predicates before the consumers (validator, Maia); first Tier-B term last, on proven ground; low-complexity before medium within Tier-A.

---

## 6. Out of scope for this wave

- **The Maia settings-panel UI** — only config keys + env fallbacks + typed `Settings` fields ship; the `maia_nodes_override` hook is documented, the panel stays roadmap.
- **Full individualized / Transfer Maia** — later; this wave uses standard rating-band models only.
- **Training any model from scratch** — never; Greco uses Stockfish and pre-trained Maia weights as given.
- **All Tier-B detectors beyond the first** — only `overloaded piece` graduates (D7); the rest stay withheld, paced in per §3.1.
- **Any new knowledge bucket, `THEME_QUERIES` keys, or narrator-injection of the new texts** — glossary/engine-theory are searchable-but-not-injected this wave.
- **Verbatim post-1930 quotation** (Shannon/Turing) — ships as original CC0 prose until license is individually verified.

---

Spec path: `C:\Users\詹天哲\Documents\greco\docs\specs\00_INDEX.md`. Companion specs in the same folder; `PREDICATE_SPECS.md` is the one to read with a chessboard in hand.