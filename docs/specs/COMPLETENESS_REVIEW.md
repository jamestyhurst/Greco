Sanity check before declaring done: I re-verified each finding against the source files I read, not the prompt summaries. #1 — `16-royal_pin_setup.md` §5 does say `evidence_string` while DATA_ARCHITECTURE §2 requires `evidence`. #2 — pin §5 uses `pinned_square`/`behind_square`; skewer §5 uses `front_square`/`back_square`. #3 — the per-predicate bundles omit the required `tag`/`squares` keys. #4 — index says `maia_default_elo` (lines 116, 145); MAIA spec says `maia_default_rating` (lines 157, 257). #5 — content plan row says pin's "predicate exists in analyzer" but pin is status new and its own spec forbids `is_pinned` as the gate. #7 — Label A's recapture guard is disarmed when `p_best is None`, which is exactly the `maia_best_move_off_list` branch, so an obvious off-list move can be certified `engine_move`. All confirmed against the files.

result: Wrote C:\Users\詹天哲\Documents\greco\docs\specs\COMPLETENESS_REVIEW.md — 10 actionable gaps/inconsistencies, the most serious being evidence-bundle field-name divergences that break the certified_evidence quoting mechanism and a Maia `engine_move` loophole that mislabels obvious off-list moves; plus 7 verified-solid items.

The findings:

# Completeness & Consistency Review — Greco Design Package

**Verdict:** the package is strong. Pin includes relative pins/pawns-as-front; luft is side-agnostic covering queenside castling and the Kb1 tuck; zugzwang is honestly approximate; no checkable term is mis-filed as Tier C; all 18 predicate specs exist and the index complexity ratings match. The defects below are real.

**1. `evidence` vs `evidence_string` — royal_pin_setup breaks the canonical bundle contract.** DATA_ARCHITECTURE §2 makes `evidence` a required key and the prompt mechanism quotes it; `16-royal_pin_setup.md` §5 names the field `evidence_string`. The narrator/`certified_claims` will find no `evidence` on the one tag that already ships → dropped tag or unquotable bundle. **Fix:** rename `evidence_string` → `evidence`.

**2. Pin/skewer rear-piece field names disagree.** Pin §5 uses `pinned_square`/`behind_square`; skewer §5 uses `front_square`/`back_square` for the same geometry; DATA_ARCHITECTURE's example anchors on the pin vocabulary. Downstream code (and the deferred `check_geometry` anchor) must special-case per tag. **Fix:** one square-vocabulary across pin/skewer/DATA_ARCHITECTURE (recommend `attacker_square`/`front_square`/`back_square`).

**3. Required `tag` and `squares` keys missing from the per-predicate bundles.** DATA_ARCHITECTURE §2 mandates `tag` + `evidence` and a conventional `squares` array, but pin/skewer/royal/luft/zugzwang bundles omit `tag` and a generic `squares` (luft has `luft_squares`, etc.). Ambiguous who injects them. **Fix:** state in PREDICATE_SPECS that every bundle also carries `tag`/`squares`, and decide whether the detector or `certified_claims` adds them.

**4. Maia default-rating config key named inconsistently.** Index D5 + step 5 say `maia_default_elo`; MAIA_INTEGRATION §4/§5.4 (authoritative) says `maia_default_rating` (env `GRECO_MAIA_DEFAULT_RATING`). **Fix:** change both index occurrences to `maia_default_rating`.

**5. Content-plan glossary `pin` row mis-states detection status.** §A.4 says "python-chess `is_pinned`; predicate exists in analyzer" — but `detect_pin` is new (only `detect_royal_alignment` exists), and pin §2/§6 explicitly forbids `is_pinned` as the gate. **Fix:** "structural `detect_pin` (new); `is_pinned` corroboration only."

**6. `kind` carries three different value-vocabularies.** pin/skewer: `"absolute"|"relative"`; royal_pin_setup §A: `"pin"|"skewer"`. Plus `line` (pin/skewer) vs `line_type` (royal). Generic consumers mis-interpret. **Fix:** disambiguate (royal → `kind="pin"|"skewer"` + separate `pin_strength`); standardize `line`.

**7. Maia `engine_move` can mislabel an obvious off-list move.** Label A fires on `gap>100 AND (p_best<0.10 OR maia_best_move_off_list)` with a recapture guard `NOT (best_is_recapture AND p_best>=0.50)`. The guard is **disarmed when `p_best is None`** — which is exactly the `maia_best_move_off_list` case. An only-legal/forced/obvious move that fell outside Maia's queried top-K gets `off_list=True`, `p_best=None`, bypasses the recapture guard, and is certified `engine_move` — the precise mislabel the gate must prevent. **Fix:** require a wide top-K for the off-list branch; add an obviousness veto (`legal_move_count<=2`/`is_forced`/check/only-capture) independent of recapture; abstain from `engine_move` when `p_best is None`.

**8. Index hides the royal skewer/diagonal recall gap.** royal_pin_setup documents that the live helper detects file/rank PINS only, yet `narrator.py:202` already says "pin or skewer." The index D1 never tells James the shipped skewer/diagonal prose is currently unbacked pending the §A helper extension. **Fix:** one sentence in D1/§2-row-16.

**9. Two open questions the index missed.** (9a) Who adds `tag`/`squares` to the ~12 new bundles (DATA_ARCHITECTURE §4.2 only shows the 6 existing tags). (9b) The DATA_ARCHITECTURE §5.3 prompt edit says only "quote `evidence`" — it does not carry zugzwang's `label`/`strict` hedge rule, so the shipped gate could permit the unhedged word "zugzwang." **Fix:** add both to index §4 / the prompt-edit text.

**10. Minor: side-label representation drifts** across bundles (skewer `mover_color:"white"`, zugzwang `side_to_move:"White"`, luft `king_color:bool`). **Fix:** standardize to title-case `"White"/"Black"` and note it in DATA_ARCHITECTURE §2.

**Solid (no action):** relative pins; side-agnostic luft; honest approximate zugzwang; no checkable Tier-C term; every Tier-B term has a detection sketch; all 18 specs exist with matching complexity ratings; the `== set()` → `== {}` test fix; variation-validator `fact_packets` threading.

Full review with fixes and priority order at `C:\Users\詹天哲\Documents\greco\docs\specs\COMPLETENESS_REVIEW.md`.