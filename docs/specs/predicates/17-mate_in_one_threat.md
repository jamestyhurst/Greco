# Detection Spec — `mate_in_one_threat`

**Certified tag:** `mate_in_one_threat`
**Layer:** Greco output fact-gate (`factgate.py`)
**Status:** REVISIT of the EXISTING predicate pair `threatens_mate_in_one` (board-level helper, `factgate.py:50`) + the `_mate_threat()` null-move probe nested inside `certified_claims` (`factgate.py:259–268`). After adversarial review, the **core null-move logic is correct and is KEPT verbatim**, but the original draft of this spec contained material errors that are corrected here: (1) two of its positive example FENs were wrong (one was a **stalemate**, so the tag is `False`, not `True`); (2) its negative hedges contradicted the engine (positions it claimed do *not* mate actually *do*); (3) its claim that **en-passant mate is "covered"** is misleading — a mover's en-passant mate threat is **structurally unreachable** and is correctly a non-case; (4) its VETO-2 prose about python-chess null-move behavior was self-contradictory and factually wrong; (5) the proposed evidence bundle mislabels the **promotion** mating piece. **Recommendation: KEEP the gate logic; fix the documentation, examples, and evidence-bundle piece-naming; add the evidence bundle.**

All positive/negative examples below were executed against `factgate.threatens_mate_in_one` on python-chess 1.11.2 in the Greco venv; every asserted truth value is the observed result, not eyeballed.

---

## 1. Expert definition

A **mate-in-one threat** is a *standing* threat created by the mover (the side that just played the move under analysis): with the opponent to move, **if the opponent were to do nothing about it, the mover would have a legal move that ends the game by checkmate.** A coach phrases it "...and now White threatens mate" or "this sets up the unstoppable threat of Qh7#." The burden has shifted to the opponent — they must spend their move parrying mate or lose immediately.

The concept has two related but distinct senses; Greco's tag is the **first**:

1. **Standing mate threat (the certified sense).** After the mover's move, with the opponent to move, the mover *threatens* mate-in-one. Operationally: imagine the opponent passes (a null move); the mover then has at least one legal move that is checkmate. This is a property of the position the mover *created* and is the natural object of the narrator's claim "X threatens mate."
   - It is true **whether or not the opponent can actually parry it.** A threat is still a threat even if a defense exists — "threatens mate, but Black defends with ...Kf8" is ordinary, correct commentary. The certified claim is the *existence* of the threat, not its un-stoppability. (Un-parryable mate-in-one means the opponent is already lost — a stronger claim Greco does not separately gate here; the engine eval, not this tag, carries "forced/unstoppable.")

2. **Mate-in-one on the move (the helper sense).** The *side to move* has a legal checkmating move right now. This is exactly what `threatens_mate_in_one(board)` computes. It is the building block, not the certified claim: at narration time the mover's move has already been played, so "mate on the move" for the position-after would be the *opponent's* mate — the wrong side. **The null-move probe is load-bearing**: it converts sense-2 (helper) into sense-1 (claim) by handing the move back to the mover. Calling `threatens_mate_in_one(board_after)` directly would certify the *opponent's* mate-in-one — a color-inversion bug, not a cosmetic detail.

**Recognized variants reduce to "a legal move that gives checkmate"** and are caught because the helper enumerates *legal* moves and tests `board.is_checkmate()` after each. Verified against the live helper:
- **Pawn promotion-mate** (e.g. `f8=Q#`, `e1=Q#`) — promotion moves are legal moves; **verified True** on a valid (non-stalemate) construction.
- **Discovered checkmate** and **double-check mate** — `board.gives_check(move)` returns `True` for a discovered check even when the *moving* piece is not the checker (**verified**: `Nd5–f6` discovering a rook check reports `gives_check=True`). So the helper's cheap `gives_check` veto does **not** drop discovered/double-check mates.
- **Castling that delivers mate** (`O-O-O#` / `O-O#`) — castling is a legal move and `gives_check` recognizes the castled rook's check (**verified** on a contrived `O-O-O` check). Covered for both castling sides.
- Smothered mate, back-rank mate, corridor mate, Anastasia's, Boden's, etc. — these are *patterns*, not separate rules; each is "a legal move that mates," so all are caught pattern-agnostically.
- **En passant is the one apparent variant that is NOT a real case.** See §4 case 7 and §6: a mover's en-passant *mate threat* cannot arise, so there is nothing to cover and nothing is missed.

**Side-to-move / color dependence is the crux, and the gate is color-symmetric by construction.** The threat is always asserted about the mover. `board_after` has the **opponent** to move; the null move flips `board.turn` back to the mover; `threatens_mate_in_one` reads whichever side is to move. There is no White/Black branch. **Verified both directions**: a White-mover back-rank threat (`...→ Ra8#`) and the mirrored Black-mover threat (`...→ Ra1#`) both certify True with identical code.

---

## 2. Detection rules (VETO-THEN-CONFIRM)

Input is the post-move board `board_after` (opponent to move), exactly as `certified_claims` supplies it. **Reuse the existing helper `threatens_mate_in_one(board)` (`factgate.py:50`) — do not re-implement the legal-move / `is_checkmate` loop.** The probe below is precisely the existing `_mate_threat()` closure (`factgate.py:259–268`); this spec confirms and documents it.

**VETO 1 — game already over (`board_after.is_game_over()`).** Return `False`. If the mover's move itself ended the game (checkmate, stalemate, insufficient material, fivefold/75-move), there is no "next move" to threaten. A *delivered* mate is the already-true fact "checkmate," not a *threat* of mate. This veto also guarantees the opponent has at least one legal move, so the null-move push that follows is reasoning about a live position.
   - **Note on draw detection (was glossed in the draft):** `board.is_game_over()` with default `claim_draw=False` returns `True` for *automatic* terminations — checkmate, stalemate, **insufficient material** (verified: bare K vs K → `True`), fivefold repetition, seventy-five-move rule — but **not** for *claimable-only* draws (threefold repetition, fifty-move rule), which require a claim. This is the correct posture: a position one ply from a forced mate is not "game over" merely because a 50-move counter is high, and a genuinely dead position (insufficient material) correctly suppresses the tag.

**VETO 2 — the opponent is in check (`board_after.is_check()`).** Return `False`. This is the central edge case the null-move approach must handle, and it is handled correctly today.
   - On `board_after`, `is_check()` can *only* mean the opponent's king is in check — i.e. **the mover's move gave check** — because a legal move never leaves the mover's own king in check (verified: `is_check()` reflects the side-to-move's king only). So VETO 2 is exactly "the mover's move was a checking move."
   - The "opponent passes" framing is **undefined under check**: the opponent is *not free to do nothing* — they are forced to address the check (capture the checker, block, or move the king). A null-move probe here would measure a threat the opponent's *forced* reply may completely refute (the king step that escapes the check might also defend the mating square). So a null-move probe under check is a **false-positive generator**; we abstain.
   - **Library-behavior correction (the draft was wrong and self-contradictory here):** python-chess does **not** refuse to push a null move when the side to move is in check — it **allows** the push and produces an (illegal) position without raising (verified: pushing `Move.null()` into a White-in-check position succeeds and just flips the turn). The veto is therefore **semantic, not a guard against an exception**: we abstain because the *threat framing* is ill-defined under check, not because the library would reject the push. The gate is `is_check()` (any check), not `is_checkmate()`, precisely because *any* check — mating or not — breaks the "opponent may pass" premise.
   - This is a deliberate **precision-over-recall** boundary: a checking move can also set up a standing mate, but that scenario is better described as "mate in two / mating attack" and belongs to the engine's `mate_after`, not this geometric one-ply gate. Accepted false-negative (see §6).

**CONFIRM — null-move probe.** If neither veto fires:
   1. Copy the board: `probe = board_after.copy()` (never mutate the caller's board).
   2. Push a null move: `probe.push(chess.Move.null())`. The turn passes back to the mover without moving any piece. **Side effect, benign:** the null move clears `ep_square` and increments the halfmove clock on the copy (verified: a `d6` en-passant square becomes `None` after the null push). Neither affects checkmate detection; the original board is untouched.
   3. Return `threatens_mate_in_one(probe)` — does the mover now have a legal move delivering checkmate? The helper applies its own `is_game_over()` short-circuit and its cheap `if not board.gives_check(move): continue` veto, so only checking candidate moves are pushed/tested.

**Color handling:** none required explicitly — `board.turn` on `board_after` is the opponent; the null move flips it to the mover; `threatens_mate_in_one` reads the side to move. Identical for White-mover and Black-mover (both verified).

**Wrapping:** the whole probe runs inside `certified_claims`'s `_safe(...)` closure (`factgate.py:253–257`), so any exception silently drops the tag rather than crashing the report.

---

## 3. Positive examples

Each FEN is the position **after the mover's move** (opponent to move) — exactly what the predicate receives. Every value below was executed against the live helper.

1. **Back-rank mate threat (White mover).** FEN: `6k1/5ppp/8/8/8/8/8/R5K1 b - - 0 1` — White rook on a1, Black king boxed by its own f7/g7/h7 pawns. Null move → White to move → `Ra8#`. **Result: True.** Evidence headline `Ra8#`, piece `rook`, mover `White`.

2. **Smothered-mate threat (knight).** FEN: `6rk/6pp/7N/8/8/8/8/6K1 b - - 0 1` — White knight on h6, Black king smothered by its own rook/pawns. Null move → White → `Nf7#`. **Result: True.** Confirms the `gives_check`-then-`is_checkmate` loop catches a knight mate; pattern-agnostic.

3. **Promotion-mate threat (CORRECTED FEN).** FEN: `7k/5P2/6K1/8/8/8/p7/8 b - - 0 1` — Black has a free tempo (`a2` pawn) so the position is **not** stalemate; if Black passes, White plays `f8=Q#` (also `f8=R#`). **Result: True.** Evidence: headline `f8=Q#`, `all_mating_moves_san = ["f8=Q#", "f8=R#"]`.
   > **Why the draft's FEN was wrong:** the draft used `7k/5P2/6K1/8/8/8/8/8 b - - 0 1`, which is **stalemate** — Black's king on h8 has no legal move (g6-king covers g7/g8/h7; h8 occupied). `is_game_over()` is `True`, VETO 1 fires, tag is **False**. A promotion positive *must* give the side-to-move a legal waiting move. **Test authors: validate every positive by running the helper; do not hand-eyeball back-rank/smother/promotion geometry.**

4. **Black-mover symmetry (back rank).** FEN: `r5k1/8/8/8/8/8/5PPP/6K1 w - - 0 1` — Black rook a8, White king g1 boxed by f2/g2/h2. Null move → Black to move → `...Ra1#`. **Result: True.** Evidence mover `Black`. Confirms there is no White-only code path.

5. **Quiet queen back-rank threat (defender can still parry).** FEN: `6k1/5ppp/8/8/8/8/5PPP/4Q1K1 b - - 0 1` — White queen e1; null move → White → `Qe8#`. **Result: True.** The existence of a Black defense (if any) does not disqualify the *threat*; the tag asserts existence, not un-stoppability.

> Test note: examples 1–4 are the safe, hand-checkable, engine-verified set; build the L1 unit test from those (and assert example 3's *stalemate* twin returns **False** as a regression guard against the original spec error).

---

## 4. Negative / edge cases

1. **The move *delivered* mate (game over).** `board_after.is_checkmate()` ⇒ `is_game_over()` ⇒ VETO 1 → `False`. A completed mate is the fact "checkmate," not a *threat*. (The narrator describes the mate from result/`is_check` data, not this tag.)

2. **Stalemate / insufficient-material after the mover's move.** `is_game_over()` true ⇒ VETO 1 → `False`. **This is exactly the trap the draft's promotion example fell into** (`7k/5P2/6K1/8/8/8/8/8 b` is stalemate). Verified: insufficient material (bare K vs K) also returns `False`. No false positive.

3. **The move gave check (but not mate).** `board_after.is_check()` ⇒ VETO 2 → `False`, even if a forcing mate exists after the forced reply. Deliberately excluded: "opponent passes" is undefined under check, and the null-move probe would certify a threat the *forced* reply may refute. Verified: after `Ra8+` (`R5k1/5ppp/8/8/8/8/5PPP/6K1 b`), the tag is `False`. Accepted false-negative (§6).

4. **Mate-in-one for the *opponent*, not the mover.** If `board_after` has the opponent to move and *they* have a mate-in-one, a naive `threatens_mate_in_one(board_after)` would be `True` — the wrong side's threat. The null-move probe prevents this by flipping the turn to the mover first. This is precisely why the null move is mandatory and why calling the helper directly on `board_after` is a bug.

5. **"Mate in two" / longer forced mate.** The mover threatens mate but needs ≥2 moves. After one null move there is no *single* mating move → `False`. Correct: the tag is strictly mate-in-**one**; deeper forced mates are the engine's `mate_after`, not this geometric gate.

6. **Apparent mate that is illegal for the mover (self-check / pinned mating piece).** A "mating" move that would leave the mover's own king in check, or whose mating piece is **absolutely pinned** to its own king, is excluded automatically because `board.legal_moves` never enumerates it. No special handling; legality is inherited from python-chess.
   - **Relative pins do NOT suppress a real mate (anti-under-inclusion).** A piece "pinned" only against a more valuable non-king piece (a *relative* pin) is still legally allowed to move. If such a move delivers checkmate, the game ends — there is nothing more valuable than mate to lose behind it — so the helper correctly enumerates and certifies it. The gate must not (and does not) special-case relative pins out; only *absolute* (to-king) pins remove the move, and that removal is correct.

7. **En-passant "mate threat" — a structural non-case (draft was misleading).** The draft listed en-passant mate as "covered." In fact a *mover's* en-passant mate threat **cannot occur**: (a) an en-passant right belongs to the side to move in `board_after`, which is the **opponent**, not the mover; (b) the mover's own en-passant right would require the opponent's *previous* move to be a double pawn push, but the **mover** moved last, so no such right exists in `board_after`; and (c) the null-move push clears `ep_square` to `None` anyway (verified). Therefore the predicate never needs to — and never can — certify an en-passant mate for the mover. This is **not a false negative** (no real instance is missed); it is a non-case. The earlier "a passed turn forfeits en passant — correct" remark was true but irrelevant, because the right was never the mover's to forfeit.

8. **The mating move can be captured / the threat is trivially parried.** Still certified as a *threat* — a mate-in-one threat exists even when the defender has a refutation (capture, block, flight, counter-check). **Intended inclusiveness**: experts say "threatens mate" here. The narrator's surrounding prose and the engine eval convey decisiveness; the tag asserts only existence. (Contrast `fork`, which down-weights a hanging forker — mate-threat deliberately does not, because a parryable mate threat is still a real, nameable threat.)

9. **Discovered-check / double-check mate after the null move ARE certified.** Listed to flag that the mating move need not be a simple direct check from the moving piece: `gives_check` returns `True` for a discovery (verified), so discovered and double-check mates are valid positives, not exclusions.

10. **Null-move push raising / engine objection.** python-chess does not reject a null move in a normal (non-check, not-game-over) position. Should any unexpected exception occur, the `_safe` wrapper catches it and the tag is dropped — no crash, no false positive.

---

## 5. Evidence bundle

Today the gate certifies the tag as a bare boolean: the narrator may *assert* a mate threat but is given **no proof of which move mates**, so it can name the wrong mating move. Proposed anti-hallucination payload — a **sibling evidence function** that does **not** change `threatens_mate_in_one`'s `-> bool` contract (mirroring how `is_outpost` returns supporter squares and `is_rook_lift` returns a reason string).

**Proposed `mate_threat_evidence(board_after) -> Optional[dict]`** — returns `None` when not certified (same two vetoes, plus a `probe.is_game_over()` guard after the null push), else:

| Field | Type | Content |
|---|---|---|
| `mating_move_san` | `str` | Headline mating move in **SAN from the mover's perspective** — `probe.san(move)` on the null-pushed board, so the `#` suffix is correct (verified: `"Ra8#"`, `"Nf7#"`, `"f8=Q#"`, `"Ra1#"` for Black). The **load-bearing** field the narrator quotes verbatim. |
| `mating_move_uci` | `str` | Same move as `move.uci()`, for downstream re-validation. |
| `mating_piece` | `str` | Human piece name. **CORRECTED:** for a **promotion** mate, use `PIECE_NAMES[move.promotion]` (the piece the pawn *becomes*, e.g. `"queen"`), **not** `PIECE_NAMES[probe.piece_type_at(move.from_square)]` (which is `"pawn"` and yields the misleading "threatens mate with the pawn"). Rule: `mating_piece = PIECE_NAMES[move.promotion] if move.promotion else PIECE_NAMES[probe.piece_type_at(move.from_square)]`. For a **castling** mate, name it `"rook"` (the rook delivers the check) or use the SAN (`O-O-O#`) verbatim — do not call it `"king"`. |
| `mating_from` / `mating_to` | `str` | `chess.square_name(...)` of the mating move's from/to squares. |
| `mover_color` | `str` | `"White"` / `"Black"` from `probe.turn` (the mover, after the flip) — so the narrator never attributes the threat to the wrong player. Verified correct for Black movers. |
| `all_mating_moves_san` | `List[str]` | **All** legal mover moves that mate after the null move (sorted by UCI for determinism). Lets the narrator say "more than one way to mate" truthfully and prevents false uniqueness claims. For the corrected promotion example this is `["f8=Q#", "f8=R#"]`. |
| `evidence` | `str` | Ready-to-quote sentence built deterministically, e.g. `"White threatens mate in one with Ra8#."` or, when several exist, `"White threatens mate in one (f8=Q# or f8=R#)."` Narrator may use verbatim. |

**Construction notes** (reuse existing idioms): compute on the **null-pushed probe board** so SAN/turn/perspective are the mover's; for each `move` in `probe.legal_moves` where `probe.gives_check(move)`, push, test `is_checkmate()`, pop, and collect the maters (the same loop as `threatens_mate_in_one`, collecting instead of short-circuiting); guard with `if probe.is_game_over(): return None` after the null push; sort the collected moves by `move.uci()` and take the first as the headline. Use `PIECE_NAMES` and `chess.square_name` (same convention as `detect_double_attack`) and the promotion/castling piece-naming rule above. Wrap the whole body so it returns `None` on any exception.

**Serialization:** surface under a new key in `_move_to_dict`'s Tier-1+ block alongside `certified` (e.g. `d["mate_threat"] = mate_threat_evidence(chess.Board(move.fen_after))`), guarded `if ...:` and wrapped in try/except — exactly the "evidence bundle that parallels `certified`" slot the narrator brief prescribes. The `mate_in_one_threat` tag stays the authoritative gate in `GATED_TAGS`; the evidence dict is **additive proof, not a new claim type**, so no `GATED_TAGS` change and no system-prompt-rule change is required.

---

## 6. Known limitations

- **Conservative under check (accepted false-negative).** Any move that gives check is abstained on (VETO 2), so a checking move that *also* leaves a standing mate-in-one is never certified. By design; the cost is missing some real threats delivered alongside a check. Such cases are usually better named "mate in two / mating attack" and are the engine's `mate_after` job.
- **Strictly one move deep.** Forced mates in two or more read `False` — the engine's `mate_after`, not this gate.
- **Threat existence, not threat success.** Certifies that a mating move exists *if the opponent passes*; it does **not** assert the opponent has no defense. A certified position may be fully defensible. The narrator must not upgrade "threatens mate" to "forced/unstoppable mate" off this tag alone — the engine eval is the source for that.
- **En passant is a structural non-case, not a gap.** A mover's en-passant mate threat cannot arise (§4 case 7); nothing real is missed and nothing needs special handling.
- **Promotion under-promotion mates are included but flattened.** All of `f8=Q#`/`f8=R#` (and any under-promotion mate) are collected in `all_mating_moves_san`; the headline picks the lowest-UCI (typically the queen/`=Q`), which is the natural narrator choice.
- **Null-move side effects are benign.** The null push clears en-passant rights and bumps the halfmove clock on the **copy** only (verified); neither affects checkmate detection, and the caller's board is untouched (`.copy()`).
- **No multi-threat richness.** It does not report whether the mate threat is part of a double threat (mate-or-win-material) or count the opponent's defenses; those would need separate predicates.
- **Standing-threat framing only.** The trigger is "opponent passes," so it models a threat against a *free* opponent; it does not model threats that only materialize after a specific forcing opponent reply (those are not "mate-in-one threats" in the standing sense anyway).

---

## 7. Complexity

**Low.** The predicate is one null-move push followed by one pass over the mover's legal moves, short-circuited by a `gives_check` filter so only the handful of checking candidates are actually pushed/tested. It reuses the existing, tested `threatens_mate_in_one` helper verbatim and adds two O(1) board-state vetoes (`is_game_over`, `is_check`); it touches no engine and no network (pure python-chess, L1-testable with no Stockfish binary). The evidence bundle adds only a second collecting pass over the same candidate moves plus string formatting via existing `PIECE_NAMES` / `square_name` idioms — no new algorithms, no new dependencies. The sole subtleties are conceptual, not computational: (a) the null move is *required* to attribute the threat to the correct color; (b) check must be vetoed for *semantic* reasons (the library would not reject the push); (c) en passant is a structural non-case; and (d) positive-example FENs must be engine-validated because back-rank / smother / promotion-stalemate geometry is easy to mis-eyeball — the very error the original draft made.
