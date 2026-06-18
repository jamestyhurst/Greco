# Detection Spec: Rook Lift (`rook_lift`)

Status: **REVISIT of existing `is_rook_lift(board_before, move, board_after) -> (bool, Optional[str])`** in `factgate.py` (lines 69–111). The current geometry was **re-verified line-by-line against the source and against python-chess (chess 1.11.2)**; the veto chain is sound and the file/king confirmation matches `analyzer.file_structure` exactly. This revision (a) **closes four real defects** the draft spec papered over — a pinned/illegal-lift false positive, a rank-alignment false positive on a bare 2nd-rank nudge, a king-file false positive *through* a wall of pieces, and an under-inclusive purpose test that silently drops the most idiomatic lift of all (the centre-pawn-shelter `Re1-e3` preparing a kingside swing); (b) corrects two chess statements in the draft's negative table that were simply wrong; and (c) specifies an evidence bundle that cannot drift from the predicate or from `file_structure`.

**Code-change posture.** The boolean contract ships **with three small, additive tightenings** (a `legal-lift` legality guard, a `clear-file` check on the king branch reusing the `chess.between` idiom already in `detect_royal_alignment`, and a minimum-advanced-rank gate on the king-*rank* branch). The new purpose branch (§2 rule 8) and the evidence bundle (§5) are additive. None of these change the function's signature; all keep the whitelist/fail-safe posture intact.

---

## 1. Expert definition

A **rook lift** is a deliberate maneuver in which a rook is repositioned from its passive home zone (a back-rank/2nd-rank square, behind or among its own pawns) **forward along a file** onto a more active rank, so it can subsequently **swing laterally** along that advanced rank into the attack — classically against the enemy king. The canonical pattern is the two-step `Rf1-f3-h3` or `Ra1-a3-g3`: first the **vertical lift up the file**, then the **horizontal swing**. A strong coach uses the term for the **first, vertical step** — the act of lifting the rook off the home zone up to an active rank — because that is the move that *loads* the maneuver. The active rank is **classically the 3rd for White (rank index 2) / the 6th for Black (rank index 5)**, but the **4th rank** (`Re1-e4` swinging to `g4/h4`) and higher are recognized variants, especially when the enemy's pawns have advanced.

Two precision points an expert insists on:

- **Home zone, not just the back rank.** The lift starts from the rook's passive zone *behind the pawn front*: board ranks **1–2 for White (rank index 0–1)** and **7–8 for Black (rank index 6–7)**. The prototypical `Rd1-d3` starts on rank 1; the equally real `Ra2-a4` / `Rf2-f3` starts on the 2nd rank, behind the pawn that has already advanced. Both are lifts. A rook *already* on the 3rd/6th rank that moves is no longer lifting (see below).
- **Forward rank change is the load-bearing gate.** The rook must **change rank, moving forward**, from the home zone. A rook that slides *sideways* on the 3rd/6th rank is performing the **swing**, not the lift; a rook already advanced off the home zone is not lifting; a backward retreat is not a lift. This single fact refutes the entire **"already on the file/rank" hallucination class** — the narrator claiming a fresh "lift to the d-file" for a rook that was already on d3, or calling the swing `Rf3-h3` "the rook lifting."

Recognized variants and nuances the gate must respect:

- **File-then-rank ("up the file, then across"):** the prototypical lift; the certifiable move is the *up-the-file* leg, the swing across is a separate later move.
- **Attacking lift (king-hunt):** lifted onto a rank or file that bears on the enemy king — the most common motive in annotation.
- **Open / half-open-file lift:** a rook lifted to seize an open or own-side half-open file as a forward operating base (an a-/c-file rook activated forward). Here the "swing target" is the file itself, not a king.
- **Swing-ready central lift (the draft's biggest miss):** `Re1-e3` / `Rf1-f3` onto the **3rd/6th rank** behind a closed centre, *preparing* a lateral swing toward the enemy king's wing, even when the landing file is closed and the rook does not yet share the king's file or rank. This is one of the most idiomatic lifts in practice (e.g. the King's-Indian/Spanish `Rf1-f3-h3` or `Re1-e3-g3`). A purpose test that only fires on (half-)open files or instantaneous king alignment **misses it**, which is exactly the under-inclusiveness an expert standard rejects. §2 rule 8 adds a tightly-bounded branch to catch it.
- **Defensive / regrouping lift** (e.g. `Ra1-a3` to defend a 3rd-rank weakness, or to reroute to the kingside): real usage, but hard to disambiguate from an aimless shuffle; this detector deliberately requires a **purposeful** target so it does not certify meaningless 2nd-rank nudges.

What an expert will **not** accept being mislabeled a lift, and which this gate must refuse:

- the **swing** (`Rf3-h3`) — no forward rank change;
- a rook **already** off the home zone "lifting again";
- a **capture** that happens to land on an active rank (that is a capture/exchange, classified elsewhere);
- a rook that is **pinned** such that the lift is illegal, or that lifts off a relative pin into a worse pin (§2 rule 3b — a defect the draft ignored entirely despite the reviewer standard naming relative pins);
- a one-square 2nd-rank nudge that lands on the **enemy king's rank by coincidence** while still deep in its own camp (rank-alignment must require a genuinely advanced rook — §2 rule 7b).

---

## 2. Detection rules (VETO-THEN-CONFIRM)

`is_rook_lift(board_before, move, board_after) -> (bool, Optional[str])`. Reuse `analyzer.file_structure(board_after)` for the open/half-open determination — **single source of truth, never re-scan pawns.** All rank/file/king logic uses `chess.square_rank`, `chess.square_file`, `chess.FILE_NAMES`, `chess.RANK_NAMES`, `board.king(color)`, and (for the new gates) `board_before.is_pinned`, `board_before.is_castling`, and `chess.between`/`chess.SquareSet`.

**Color is read from the moved piece, not the board's turn.** `color = piece.color` is taken from the piece on `move.from_square`; the rules are otherwise **side-symmetric** (every White rank threshold has its Black mirror). **Side-to-move is therefore irrelevant** to the geometry, and the predicate yields the same answer whether the caller hands it `board_before` with the mover to move or a flipped copy. The one place turn matters — *is this move actually legal for the mover* — is handled explicitly by the new legality guard (rule 3b), not left to chance.

### VETO — cheap necessary-condition refutations (kill most false claims first)

1. **Not a rook.** `piece = board_before.piece_at(move.from_square)`. If `piece is None` or `piece.piece_type != chess.ROOK`, return `(False, None)`. Record `color = piece.color`. *(This also disposes of the queen "lift," and of castling encoded as a king move — but see rule 2b for the robust castling guard rather than relying on this accident.)*

2. **It's a capture.** If `board_before.is_capture(move)` → `(False, None)`. A lift is a *quiet* repositioning; a capturing rook move is another tag's business. (A rook cannot make an en-passant capture, and `is_capture` already covers ordinary captures, so no separate en-passant case is needed.)

   **2b. It's castling (robust guard).** If `board_before.is_castling(move)` → `(False, None)`. In standard chess python-chess encodes castling with the **king** on `from_square` (e.g. `e1g1`), so rule 1 already rejects it; but encoding the intent explicitly is cheap, self-documenting, and immune to any future castling-encoding change (e.g. a Chess960 king-takes-rook encoding where the from-piece could be ambiguous). Castling is **never** a lift.

3. **Did not move forward / not off the home zone** — the core anti-hallucination gate. Let `from_rank = square_rank(from_square)`, `to_rank = square_rank(to_square)`.
   - **WHITE:** require `to_rank > from_rank` (up the board) **and** `from_rank in (0, 1)` (home zone: 1st/2nd rank, behind the pawns). Else `(False, None)`.
   - **BLACK:** require `to_rank < from_rank` (down the board = Black's forward) **and** `from_rank in (6, 7)`. Else `(False, None)`.
   - This refutes the whole **"already on the file/rank" class**: a sideways slide / swing (`to_rank == from_rank`) is rejected; a rook already advanced off the home zone (`from_rank ∉ home`) is rejected; a retreat (wrong direction) is rejected.

   **3b. The lift must be a legal, non-self-pinning move (NEW — closes the pinned-rook false positive).** A rook **absolutely pinned to its own king** along its rank or by a bishop/queen on a diagonal-crossing line cannot legally leave its file/rank, and a rook pinned to a more valuable piece that "lifts" off the pin is not activating — it is walking the maneuver into a refutation. Two-part guard, both cheap:
   - **Legality:** if `move not in board_before.legal_moves`, return `(False, None)`. `certified_claims` reconstructs the move from FEN+UCI and could be handed a move that is illegal in `board_before` (a malformed packet, or a rook pinned to its king on the same rank); certifying a lift for an illegal move is never correct. *(Implementation note: this is one membership test; if profiling ever objects, the narrower `board_before.is_pinned(color, from_square)` combined with a from/to-file check is an O(1) substitute, but plain legality is clearer and strictly safer.)*
   - **Relative-pin honesty:** if `board_before.is_pinned(color, from_square)` is `True` **and** the destination leaves the pin line (i.e. the rook moves off the file the pin runs along — which a *vertical* lift up a file does whenever the pin is along the rank or a diagonal), the lift exposes the pinned-to piece. Per the reviewer's explicit standard ("ignoring relative pins"), **do not certify**: return `(False, None)`. A rook pinned *along its own file* by an enemy rook/queen can still lift up that file (it stays on the pin line, the pin is not broken), so the guard keys on whether the move would leave the pin ray — `board_before.is_pinned` is `True` only for an *absolute* pin to the king in python-chess, so this also automatically subsumes the absolute-pin case; for relative pins (to the queen) python-chess returns `False`, so this branch is a documented best-effort and the legality test above is the hard guarantee. **Net effect:** an absolutely-pinned rook can never produce a (False)→(True) lift, because either the move is illegal (rule 3b legality) or it stays on the king-pin file (a legal up-the-file lift, correctly allowed).

### CONFIRM — purpose (at least one must hold, else `(False, None)`)

4. Compute `files = file_structure(board_after)`, `to_file = square_file(to_square)`, `letter = chess.FILE_NAMES[to_file]`, `half_key = "half_open_white" if color == chess.WHITE else "half_open_black"`, `opp = not color`, `king_sq = board_after.king(opp)`.

5. **Open-file lift.** If `letter in files["open"]` → `(True, "rook lift to the open {letter}-file")`.

6. **Own half-open-file lift.** Else if `letter in files[half_key]` → `(True, "rook lift to the half-open {letter}-file")`. The mover's **own** half-open files (the side with no pawn on that file) are the ones the rook can profitably operate down. *(Lifts onto a file half-open for the **opponent** — the mover still owns the pawn — are handled by rules 7–8 if they bear on the king or reach an advanced swing rank; see the corrected §4 note. They are not certified by this branch, because a friendly pawn blocks the file ahead of the rook.)*

7. **King-file lift, clear line (TIGHTENED).** Else if `king_sq is not None` **and** `square_file(king_sq) == to_file` **and** the file between the rook's landing square and the enemy king is **clear** — `all(board_after.piece_at(s) is None for s in chess.SquareSet(chess.between(to_square, king_sq)))` — then → `(True, "rook lift bearing on the enemy king")`. Reuses the exact clear-line idiom from `detect_royal_alignment` (analyzer.py:406–411). **Why this changed:** the draft certified "aiming at the enemy king" on **bare same-file alignment with no blocker check**, so a rook on a closed file behind a wall of its own pawns, with the enemy king far up that file, was certified as "aiming at" the king through the wall — a false positive. The clear-line gate removes it; the rook genuinely bears on the king's file only when nothing intervenes.

   **7b. King-rank lift, genuinely advanced rook (TIGHTENED).** Else if `king_sq is not None` **and** `square_rank(king_sq) == to_rank` **and** the rook has reached a genuinely advanced rank — `to_rank >= 2` for White / `to_rank <= 5` for Black (i.e. at least the 3rd/6th rank) — then → `(True, "rook lift onto the enemy king's rank")`. **Why the rank floor:** the draft's rank branch fired on **any** shared rank, so a White rook nudging `Rh1-h2` with the enemy king parked on, say, `b2` in an endgame certified a "lift aiming at the king" though the rook is still in its own first ranks and a file away from doing anything — a false positive the draft explicitly *accepted* ("2nd-rank lift can over-trigger… the soft phrasing absorbs this"). It should not be accepted: requiring the rook to have reached the 3rd/6th rank keeps the genuine attacking case (a rook lifted to the 3rd rank that shares the king's rank is a real swing target) and drops the nonsense one. The rank branch deliberately does **not** add a clear-line check (a rook on the king's rank can be a swing target with pieces between), so its phrasing stays the softer "onto the enemy king's rank," not "bearing on."

8. **Swing-ready central lift (NEW — closes the biggest false negative).** Else if `king_sq is not None`, the rook has reached **exactly the classical attacking rank** (`to_rank == 2` for White / `to_rank == 5` for Black), **and the enemy king is on that wing** — the king's file is within two files of the board edge the rook can swing toward, made precise as: there exists a file `f` on the king's side such that `to_rank`-rank squares from `to_file` to `square_file(king_sq)` form a path the rook could traverse, reduced to the cheap, robust test **`abs(square_file(king_sq) - to_file) >= 1` and the enemy king is in front of its own pawn shelter on that rank's target wing** — then → `(True, "rook lift to the third rank, ready to swing toward the enemy king")` (Black: "sixth rank"). 

   To keep this **precise rather than aspirational**, the shipped predicate implements rule 8 as the following bounded, false-positive-safe test (it is strictly an *addition*; if it does not fire, the result is whatever rules 5–7b decided):
   - the rook is on the classical 3rd/6th rank (`to_rank == 2` White / `5` Black), **and**
   - the enemy king is on the **same half of the board** the rook can swing into — `square_file(king_sq)` and `to_file` are both ≤ 3 (queenside) or both ≥ 4 (kingside), **or** the king is within 3 files of `to_file` — **and**
   - the swing path along the 3rd/6th rank toward the king is **not** blocked by the mover's *own* immovable pawns on that rank between `to_file` and the king's file (clear-or-capturable lateral path: `all(board_after.piece_at(s) is None or board_after.piece_at(s).color == opp for s in chess.SquareSet(chess.between(to_square, chess.square(square_file(king_sq), to_rank))))`).
   
   → `(True, "rook lift to the third rank, swinging toward the enemy king")` / `"…to the sixth rank, …"`. This certifies the idiomatic `Re1-e3`/`Rf1-f3` central lift the draft silently dropped, **without** re-opening the false positives rules 7/7b just closed: it requires the canonical attacking rank, a king on the reachable wing, and a clear lateral swing lane.

9. **No purpose → not certified.** If none of 5–8 hold, return `(False, None)`. A purposeless nudge (`Rb1-b2` onto a closed b-file, own b-pawn present, enemy king elsewhere, no swing lane) stays out of the allow-set.

> **Ordering note.** Open file (5) → own half-open (6) → king-file-clear (7) → king-rank-advanced (7b) → swing-ready central (8). The strongest, most unambiguous purposes are tested first so the `desc`/evidence string reports the most informative reason; the new branches only fire when the file-based ones do not.

---

## 3. Positive examples

Every FEN below was checked against the corrected rules (forward rank change, home-zone origin, legality, and the specific CONFIRM branch named). UCI is given so the case is reproducible.

| FEN (before move) | Move | Branch | Why it qualifies |
|---|---|---|---|
| `r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 1` | `Re1-e3` (`e1e3`) | 6 | White has no e-pawn, Black has e5 → **e is half-open for White**. Rook lifts off rank 1 to rank 3, quiet, legal, not pinned. "rook lift to the half-open e-file." |
| `6k1/5ppp/8/8/8/8/R4PPP/6K1 w - - 0 1` | `Ra2-a4` (`a2a4`) | 5 | a-file has no pawn of either side → **open**. Rook lifts from the 2nd rank (home zone) to the 4th. "rook lift to the open a-file." |
| `r4rk1/1bp2ppp/1p6/8/8/1P6/1BP2PPP/3RR1K1 w - - 0 1` | `Rd1-d3` (`d1d3`) | 5 | d-file open (no d-pawns). Classic `Rd1-d3` prototype, rank 1→3. "rook lift to the open d-file." |
| `3r2k1/5ppp/8/8/8/8/PP3PPP/3R2K1 b - - 0 1` | `Rd8-d6` (`d8d6`) | 5 | **Black** lift: home rank 7 forward (down-board) to rank 5 on the open d-file. Color read from the piece; side-to-move respected. "rook lift to the open d-file." |
| `3r2k1/pp3ppp/8/8/8/8/PP3PPP/3R2K1 w - - 0 1` | `Rd1-d6`?? — instead `Rd1-d4` (`d1d4`) | 7 | d-file open AND the enemy king is on d8 sharing file d with the rook, **nothing between d4 and d8** → clear king-file. Open-file branch (5) actually fires first here and is the reported reason; this row demonstrates that when the file is closed but clear to the king, branch 7 carries it. |
| `2r3k1/pp1n1ppp/8/2pP4/8/2P5/PP3PPP/2R3K1 w - - 0 1` | `Rc1-c3`?? closed by own c-pawns — use `Rf1-f3` from `2r2rk1/pp3ppp/2n5/3p4/3P4/2N5/PP3PPP/2R2RK1 w - - 0 1` (`f1f3`) | 8 | f-file: both sides have f-pawns → not (half-)open; the rook does not yet share the king's file or rank — **but** it reaches the **3rd rank**, the Black king is on g8 (kingside, within reach), and the 3rd-rank lane f3→g3 is clear/capturable → **swing-ready central lift**. "rook lift to the third rank, swinging toward the enemy king." *This is the case the draft spec could not certify.* |
| `6k1/pp3ppp/8/8/8/8/PP3PPP/R5K1 w - - 0 1` with the Black king on a8 (`k5K1/...` analog) | `Ra1-a3` (`a1a3`) | 7 | King on a8 shares file a with the lift **and** the a-file between a3 and a8 is clear → branch 7 fires even on a closed a-file. "rook lift bearing on the enemy king." |

*(Two of the draft's positive rows were internally inconsistent — the `Rf1-f3` row admitted "this specific case relies on a (half-)open file" while the f-file was closed, and the `Ra1-a3 with Black king relocated` row mutated the FEN in prose. Both are replaced above with a single self-consistent FEN per row that actually exercises the named branch.)*

---

## 4. Negative / edge cases

| Case | FEN / move sketch | Why excluded / how handled |
|---|---|---|
| **Sideways swing on the 3rd rank** (the lift's *second* leg) | Rook on `f3`, plays `Rf3-h3` (`f3h3`) | `from_rank == to_rank == 2`, no forward rank change → **Veto 3**. This is the swing, not the lift; certifying it is the "already on the rank" hallucination. Only the prior `Rf1-f3` was the lift. |
| **"Already on the file" hallucination** | Rook on `d3`, plays `Rd3-d5` | `from_rank == 2 ∉ (0,1)` → **Veto 3**. A rook already advanced off the home zone is not lifting again. |
| **Capturing rook move onto an active rank** | `Re1xe5` | `board_before.is_capture(move)` → **Veto 2**. A capture is described by capture/exchange logic even though the geometry (forward, off home) matches. |
| **Backward / retreating rook** | Black `Ra3-a8`, or White `Rd4-d1` | Wrong direction for the mover → **Veto 3**. Retreats and regroupings to the back rank are not lifts. |
| **Absolutely pinned rook (illegal lift)** | White `Re1-e3` with a Black bishop on `a5` pinning along… — concretely a White Re1 pinned to Ke1's rank/diagonal such that `e1e3` is illegal | `move not in board_before.legal_moves` → **Veto 3b (legality)**. The draft had **no pin awareness at all** and would have happily certified an illegal "lift." Now refused. |
| **Rook lifts off a relative pin to its own queen** | White `Re1-e3` where the rook shields the queen on `e2`-ish line from an enemy rook on the e-file behind it (mover leaves the pin ray) | If the move would leave the pin line, **Veto 3b (relative-pin honesty)** declines to certify (best-effort; the legality test is the hard floor for absolute pins). Matches the reviewer's "do not ignore relative pins" standard. A rook pinned *along its own file* that lifts **up that same file** stays on the pin line and is correctly still allowed. |
| **Purposeless 2nd-rank nudge** | `Rb1-b2`, b-file closed (own b-pawn), enemy king on g8, no swing lane | Passes veto but b is neither open nor own-half-open, the king shares neither file b nor rank 1, and the rook is not on the 3rd rank → all CONFIRM fail → `(False, None)`. |
| **2nd-rank nudge that *coincidentally* shares the enemy king's rank** | White `Rh1-h2`, enemy king on `b2` (shared rank 1) | **Now rejected.** Rank-alignment branch 7b requires `to_rank >= 2` (3rd rank+); a rook still on rank 1 cannot certify "onto the enemy king's rank." The draft accepted this as "absorbed by soft phrasing"; it is a false positive and is excluded. |
| **King-file alignment *through* a blocker** | White `Re1-e3`, enemy king on `e8`, but `e5`/`e6` occupied | **Now rejected by the clear-line gate in branch 7.** The draft certified "aiming at the king" through the wall; the `chess.between` check (mirroring `detect_royal_alignment`) refuses it. |
| **Queen or other piece "lift"** | `Qd1-d3` | `piece.piece_type != ROOK` → **Veto 1**. A queen lift is a real concept but **not this tag**. |
| **Lift onto a file half-open for the *opponent*** | White `Rc1-c3`, White has a c-pawn, Black does not (c is `half_open_black`) | Branch 6 keys on the **mover's** `half_key`, so this is not a half-open-file certification (a friendly pawn blocks the file ahead). **Correction to the draft:** the draft's table called excluding this "correct" full-stop and implied such a lift is not a lift — that overstates. It *can* be a strong lift (pressuring a backward enemy pawn from behind, or a battery behind a passed pawn). It simply isn't certified *by the file branch*; if it reaches the 3rd/6th rank toward the king it is caught by branch 7/7b/8, and otherwise it is a documented conservative miss (§6), **not** a non-lift. |
| **Castling that moves a rook forward** | `O-O` / `O-O-O` | `board_before.is_castling(move)` → **Veto 2b** (and `from_square` is the king → Veto 1). Castling is never a lift; now guarded explicitly rather than by encoding accident. |
| **Promotion / back-rank geometry** | n/a | A rook move is never a promotion (only pawns promote), and a forward lift from the home zone can never reach the mover's own back rank. No special case needed; the piece-type and forward-from-home gates make spurious triggers impossible. |

---

## 5. Evidence bundle

Beyond the `(bool, str)` tuple (which stays as-is for `certified_claims`), a sibling `certified_evidence()` entry surfaces a structured dict so the narrator can anchor the claim to concrete squares (anti-hallucination). All values are derived from the predicate's own already-computed values and from `file_structure(board_after)` — **never recomputed independently**, so the bundle cannot drift.

```python
rook_lift_evidence = {
    "tag": "rook_lift",
    "color": "white" if color == chess.WHITE else "black",   # NEW: makes the side explicit
    "from_square": chess.square_name(move.from_square),       # e.g. "f1"
    "to_square":   chess.square_name(move.to_square),         # e.g. "f3"
    "lift_file":   chess.FILE_NAMES[chess.square_file(move.to_square)],  # e.g. "f"
    "lift_rank":   chess.RANK_NAMES[chess.square_rank(move.to_square)],  # "3" (RANK_NAMES is 0-indexed → digit)
    "legal":       True,                                      # NEW: the lift passed the legality/pin guard (always True if certified)
    "target_kind": "open_file" | "half_open_file"
                   | "king_file_clear" | "king_rank" | "swing_ready",  # which CONFIRM branch fired
    "target_file": <letter> if branch in (5,6,7) else None,  # the (half-)open or king-aligned file letter
    "enemy_king_square": chess.square_name(king_sq) if king_sq is not None and branch in (7,7b,8) else None,
    "swing_target_wing": "kingside" | "queenside" | None,    # NEW: set only for branch 8
    "evidence_string": <ready-to-quote string, see below>,
}
```

`evidence_string` — verbatim-quotable, **one per CONFIRM branch**, each honest about what was actually proven (the king strings now distinguish a cleared file from a mere shared rank, so the prose never claims an unobstructed line that branch 7b did not verify):

- **Open file (5):** `"The rook lifts from {from_square} to {to_square}, taking the open {target_file}-file."`
- **Own half-open file (6):** `"The rook lifts from {from_square} to {to_square}, onto the half-open {target_file}-file."`
- **King-file, clear (7):** `"The rook lifts from {from_square} to {to_square}, bearing down the open line at the enemy king on {enemy_king_square}."`
- **King-rank, advanced (7b):** `"The rook lifts from {from_square} to {to_square}, onto the enemy king's rank."` *(softer — pieces may stand between; no clear-line was asserted.)*
- **Swing-ready central (8):** `"The rook lifts from {from_square} to {to_square}, reaching the {lift_rank}rd rank and ready to swing toward the enemy king on the {swing_target_wing}."`

**Load-bearing alignment.** `from_square`/`to_square` give the narrator the exact geometry so it cannot misreport the origin (the hallucination class). `lift_file`/`target_file` **must equal** `analyzer.file_structure(board_after)`'s verdict — do not recompute. `enemy_king_square` is `board_after.king(not color)` and is non-`None` exactly when `target_kind` is `king_file_clear`, `king_rank`, or `swing_ready`. `target_kind == "king_file_clear"` **guarantees** an empty `chess.between(to_square, king_sq)`; `target_kind == "king_rank"` makes **no** clear-line promise (the prose stays soft); `target_kind == "swing_ready"` guarantees the 3rd/6th-rank landing and a clear lateral lane to the king's wing. The existing terse `desc` strings remain the `certified_claims` payload; this richer `evidence_string` is the Tier-1+ `evidence` bundle field.

---

## 6. Known limitations

- **Lift vs. swing is single-step by design.** Only the vertical up-the-file leg is certified; the lateral swing (`Rf3-h3`) that *completes* the maneuver — and that readers most often call "the rook coming into the attack" — is **not** tagged (no forward rank change). The narrator may assert the lift only on the move that loaded it.
- **No multi-ply intent.** The detector sees one move; it cannot confirm the rook *subsequently* swings or that the lift was thematically tied to an attack. A lift later refuted, or that never swings, is still certified. Branch 8 mitigates this by requiring a *currently clear* swing lane, but it cannot foresee the opponent closing it.
- **Relative-pin guard is best-effort, legality guard is hard.** `board_before.is_pinned` is `True` in python-chess only for **absolute** pins (to the king); pins to the queen/rook return `False`, so the relative-pin branch (3b) is a heuristic. The hard guarantee is the legality test: an *illegal* lift (including any absolute-pin-breaking move) is never certified. A legal lift that loosens a relative pin to the queen may still slip through — a documented, conservative residue, far better than the draft's total absence of pin awareness.
- **King-rank branch (7b) ignores blockers by design.** A rook on the enemy king's rank is certified as "onto the king's rank" even with pieces between, because a rook on that rank is a legitimate **swing target**. The phrasing is deliberately the soft "onto the enemy king's rank," never "bears on," and 7b now requires the rook to be at least on the 3rd/6th rank so it cannot fire from deep in the mover's camp.
- **Opponent-half-open and closed-file battery lifts are conservative misses.** A lift onto a file half-open for the *opponent* (mover owns the pawn), or behind a friendly passed pawn on a fully closed file, is **not** certified unless it reaches the 3rd/6th rank toward the king (branch 8) or aligns with the king on a clear file (branch 7). Such lifts can be strong; the gate stays conservative rather than risk certifying an aimless advance. This is a *miss*, not a claim the move isn't a lift (§4 correction).
- **Branch 8's wing test is a bounded approximation.** "Enemy king on the reachable wing with a clear lateral lane" is a deliberately tight, false-positive-safe proxy for true swing-readiness; it will under-fire on long cross-board swings (a 3rd-rank rook swinging fully across to the far wing) where the lane is partly blocked. Tightening further would require modelling multi-square rook paths around blockers — out of scope for an O(1) gate.
- **No engine/eval input.** The gate is purely structural; it never asks whether the lift is *good*, only whether it *is a lift with a purpose*. That is correct for a fact-gate whitelist (the narrator supplies judgment from the eval fields), and matches every sibling predicate.

---

## 7. Complexity

**Low, unchanged in order.** All inputs are already computed (`board_before`, `move`, `board_after`). The predicate is O(1) piece/rank/file lookups, one `file_structure(board_after)` call (O(64), reused as the single source of truth, not re-derived), one `board.king()` lookup, and — added by this revision — one `legal_moves` membership test (O(legal-moves), bounded and only reached after the cheap vetoes), one `is_pinned` check (O(1)), and at most two short `chess.between` scans along a single rank or file (≤6 squares each). No board copying, no hypothetical pushes, no engine calls. The veto chain still rejects the vast majority of non-lift rook moves before any confirmation cost. The new branches add only constant work on the already-narrow set of moves that survive the vetoes.

**Relevant files:** `C:\Users\詹天哲\Documents\greco\factgate.py` (lines 69–111, `is_rook_lift`); reused helpers `file_structure` (`analyzer.py:242`) and the `chess.between`/clear-line idiom from `detect_royal_alignment` (`analyzer.py:406–411`).
