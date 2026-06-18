# Detection Spec: Royal pin/skewer setup (`royal_pin_setup`)

> **Status of the helper this tag delegates to (READ FIRST).** This tag is wired through
> `factgate.sets_up_royal_pin(board, mover_color)` → `analyzer.detect_royal_alignment(board, mover_color)`
> (`analyzer.py:367-417`). **The helper as it exists today does NOT match the expert definition
> below.** Verified against source, the current helper:
> 1. checks **file and rank only** — it has **no diagonal branch** (`analyzer.py:383-388` tests
>    `qf == kf` or `qr == kr` and `continue`s otherwise), and it **never iterates a bishop**
>    (`analyzer.py:389` loops only `(chess.ROOK, chess.QUEEN)`);
> 2. detects **only the pin ordering** attacker→queen→king — it requires *both*
>    `between(attacker, queen)` **and** `between(queen, king)` to be empty
>    (`analyzer.py:406-411`), which forces the **queen** to be the inner royal. A **skewer**
>    (attacker→**king**→queen) puts the king between attacker and queen, so the
>    `between(attacker, queen)` segment contains the king and the helper **vetoes every
>    skewer**. Despite the docstring saying "pin/skewer," the code certifies **pins only**;
> 3. returns a single human **string**, not the structured fields the evidence bundle needs;
> 4. does **not** label `kind` (pin vs skewer) or `line_type`.
>
> Therefore this spec is written in two layers, and the distinction is load-bearing — do not
> blur it:
> - **§A (helper contract — what MUST be implemented)** the corrected, inclusive predicate a
>   strong coach demands (file + rank + **diagonal**, **pin + skewer**, structured evidence).
> - **§B (current-helper honesty)** exactly what certifies *today* before the §A work lands,
>   so the tag never silently over-claims diagonals/skewers it cannot prove.
>
> **Shipping rule:** the diagonal/bishop and skewer positive examples and the
> `line_type:"diagonal"` / `kind:"skewer"` evidence strings **must not be asserted by the
> narrator until the helper is extended per §A and each FEN is verified green by
> `detect_royal_alignment`.** Until then the tag is honestly *file/rank pin only* (§B), and
> the prompt wording at `narrator.py:202` ("a pin **or skewer** that wins the queen") is
> aspirational for the skewer half — flagged in §6 as a known recall gap, **not** a licence to
> emit skewer prose the engine has not proven.

---

## 1. Expert definition

A **royal pin/skewer setup** is a position in which a long-range piece of the moving side —
a **rook** or **queen** on a file/rank, or a **bishop** or **queen** on a diagonal — bears
on a single line (file, rank, or diagonal) on which the **enemy king and enemy queen both
sit**, with the relevant segments empty, so the alignment wins the queen by force. Two
geometrically distinct cases collapse into one "royal" idea:

- **Royal pin (king behind the queen):** attacker → enemy **queen** → enemy **king**. The
  queen is **absolutely** pinned (it may not legally leave the line — that would expose the
  king to check), so it falls next move for at best the cost of the attacker.
- **Royal skewer (king in front of the queen):** attacker → enemy **king** → enemy **queen**.
  Because the attacker checks (or, on the next move, will check) the king, the king must step
  off the line and the queen behind it falls.

The unifying, high-value property — and the only reason this is a specialization of the
generic pin/skewer engine — is that the two aligned enemy pieces are specifically the **king
and queen**, so the tactic nets the opponent's most valuable piece (or forces a
queen-for-lesser trade with tempo). That is what separates `royal_pin_setup` from an ordinary
pin/skewer of, say, a rook behind a knight.

**Recognized variants a strong coach calls "this":**
- **File** alignment — pinner/skewerer is a **rook or queen**.
- **Rank** alignment — **rook or queen**.
- **Diagonal** alignment — **bishop or queen only** (a rook can never sit on a K+Q diagonal).
- Either **color** to move; either **order** (K-behind-Q = pin, K-in-front-of-Q = skewer).
- **"Setup"** semantics: the alignment need not already be check or already be winning the
  queen *this instant*; it suffices that the mover's piece now bears cleanly on the K+Q line so
  the win of the queen is the standing threat realized on the mover's next turn.
- A royal pin/skewer **with the enemy queen as the inner piece even when the enemy queen is
  itself defended** still qualifies: the pin is absolute, so the queen cannot be defended *by
  moving*, only captured-and-recaptured — the tag asserts "wins the queen (for the pinner at
  worst)," and the non-hanging guard (§A rule 8) confirms the pinner is not simply lost in
  return.

**Inclusivity boundary (what James cares about — do not silently narrow it):** this tag is the
**royal** (K+Q) subset of the general pin/skewer family. *Relative* pins (the back piece is a
rook, not the king), and pins/skewers of lesser pairs, are **real pins** and must be caught by
the **general** pin/skewer engine — they simply do not earn the **royal** specialization. A
recall failure for those belongs to the general engine, not here; but this tag must not be
written so narrowly that it misses any genuine **K+Q** alignment (every line-type, both
orderings, both colors, queen-pins-queen included).

Authoritative note: every royal alignment is a pin or skewer; only the K+Q ones earn this tag.

---

## 2. Detection rules (VETO-THEN-CONFIRM)

Evaluate on **`board_after`** (the post-move position; it is now the **opponent's** turn) with
`mover_color` = the side that just moved. Target the opponent's royalty only: `opp = not
mover_color`. All geometry is color-agnostic — there are **no hardcoded ranks, files, or
directions**; White-mover and Black-mover differ solely in which `opp` king/queen are the
targets. (This explicitly rules out the side-/color-asymmetry bug class: a correct
implementation never special-cases White vs Black, never assumes the attacker is "below" the
king, and works identically whether the king is on rank 8 or rank 1, the a-file or the
h-file, near a castled corner or in the center.)

### §A — Helper contract (the corrected, inclusive predicate `detect_royal_alignment` MUST satisfy)

**VETO (cheap necessary conditions — any one true ⇒ not certified):**

1. **No enemy queen.** If `board.pieces(chess.QUEEN, opp)` is empty, abort. (Royal = K+Q.)
2. **No enemy king located.** If `board.king(opp) is None`, abort. (Cannot occur in legal
   chess; guard anyway so a malformed FEN can never raise — `certified_claims._safe` would
   swallow it, but failing fast is cheaper and keeps the tag from being dropped on unrelated
   positions.)
3. **K and Q share no line.** For each enemy queen square `qsq` vs the enemy king square
   `ksq`, test all THREE line-types: **file** (`square_file` equal), **rank** (`square_rank`
   equal), **diagonal** (`abs(file_k − file_q) == abs(rank_k − rank_q)` **and** that common
   difference is nonzero — i.e. they are genuinely diagonal, not the same square). If **no**
   enemy queen shares **any** of the three with the king, abort. (The diagonal test is the
   half the current helper is missing; adding it is mandatory for §A.)
4. **Mover owns no piece capable of that line-type.** For a K+Q sharing a **file or rank**,
   require a mover **rook or queen** on the board; for a **diagonal**, require a mover
   **bishop or queen**. If absent, abort. (Membership only here — `board.pieces(...)`; geometry
   is checked in CONFIRM. This is what stops a rook from ever "pinning" along a diagonal.)

**CONFIRM (only if all vetoes pass — for EACH (queen, line-type) the K shares):**

Let `near` and `far` be the two royal pieces ordered by distance from the candidate attacker
along the shared line: the **near** royal is the one the attacker reaches first, the **far**
royal is beyond it. **The ordering — not a fixed "queen is inner" assumption — decides pin vs
skewer.** This is the second half the current helper gets wrong (it hardcodes queen-as-inner).

5. **A correctly-placed attacker exists.** There is a mover piece of the right type for the
   line (R/Q for file|rank, B/Q for diagonal) standing on the **same** file / rank / diagonal
   as the K+Q, positioned so the order is **attacker → near royal → far royal** (attacker
   strictly outside the K–Q pair, both royals on the same side of it). Derive membership from
   `chess.square_file` / `square_rank` for file|rank and the `abs`-difference diagonal test;
   reuse `chess.between` for segment squares — never re-derive ray geometry by hand.
   - If `near` is the **queen** and `far` is the **king** ⇒ **pin** (`kind = "pin"`).
   - If `near` is the **king** and `far` is the **queen** ⇒ **skewer** (`kind = "skewer"`).
   Both orderings MUST be accepted. (Today only the first is — the skewer branch is the
   mandatory §A addition. Concretely: do **not** test only `between(attacker, queen)` and
   `between(queen, king)`; test `between(attacker, near)` and `between(near, far)` against the
   *distance-ordered* pair, so a king-in-front skewer is not vetoed by the king sitting inside
   the attacker↔queen span.)
6. **Attacker ↔ near-royal segment clear.** Every square strictly between the attacker and the
   **nearer** royal (`chess.SquareSet(chess.between(attacker_sq, near_sq))`) must be empty
   (friend or foe — any occupant breaks it). Abort otherwise.
7. **Near-royal ↔ far-royal segment clear.** Every square strictly between the two royals must
   be empty, or it is not a true K+Q alignment. Abort otherwise. (Rules 6–7 together are the
   interposition guard, applied to the *distance-ordered* pair so they are correct for both
   pin and skewer.)
8. **Attacker not hanging / does not lose the exchange for free.** Reuse the helper's existing
   safety check (`board.is_attacked_by(opp, attacker_sq) and not
   board.is_attacked_by(mover_color, attacker_sq)` ⇒ veto), generalized: if the attacker is
   attacked by the opponent and not defended by the mover, the opponent simply captures the
   pinner/skewerer and the "setup" wins nothing — abort. **Skewer-specific tightening
   (mandatory):** in a skewer the *near* royal is the **king**; if that king is adjacent to
   the attacker, the king can answer by **capturing the attacker** unless the attacker is
   defended — treat an undefended attacker adjacent to the skewered king as hanging (the
   existing `is_attacked_by(opp, …)` test already covers "king attacks the attacker," since the
   king is an attacker of adjacent squares; just ensure the skewer path runs the same guard).
9. **Attacker not itself disabled by a different pin.** If the mover's attacker is pinned to
   *its own* king on a different line such that it cannot actually deliver the threat, the
   setup is illusory. The clear-line + non-hanging guards cover the material outcome in the vast
   majority of cases; an explicit `board.is_pinned(mover_color, attacker_sq)` check **only**
   excludes the rare case where the pinner is absolutely pinned on a *crossing* line. Include
   it as a cheap final guard rather than relying on side effects.

If 5–9 hold for at least one (attacker, queen, line-type) triple, **certify
`royal_pin_setup`** and emit the §5 evidence bundle. `sets_up_royal_pin` returns
`(True, evidence_string)`, which flows through `certified_claims()` step 4 unchanged.

### §B — Current-helper honesty (what certifies TODAY, before §A lands)

Until the §A extension is implemented and tested, `detect_royal_alignment` certifies **only**:
file/rank alignments, **pin ordering only** (attacker → queen → king), rook/queen pinners,
clear segments, non-hanging pinner. Consequences that this spec makes explicit so nothing
over-claims:
- **Diagonals do not certify** (no diagonal branch, no bishop). A real diagonal royal pin is a
  **false negative** today. Do not ship diagonal positive examples as passing fixtures, and do
  not let the narrator assert a diagonal royal pin under this tag until §A lands.
- **Skewers do not certify** (the `between(queen, king)` requirement forces queen-inner). A
  real royal skewer is a **false negative** today. Same shipping restriction.
- The prompt's "pin **or skewer**" wording (`narrator.py:202`) is satisfied only on its **pin**
  half right now; the skewer half is a documented recall gap (§6), not a green capability.

**Both-colors / side-to-move (explicit, applies to §A and §B):**
- Always evaluated for `mover_color` against `opp`'s K+Q; symmetric in color.
- Evaluated on `board_after`, where it is the **opponent's** turn — correct for a standing
  threat (the queen is won on the mover's *next* turn). Rule 8 is precisely what prevents
  certifying a "setup" the opponent refutes immediately on the move they are about to make by
  capturing the pinner. We deliberately do **not** require the alignment to already be a
  check; a pure pin (queen in front, no check) is fully valid and must be caught.

---

## 3. Positive examples

> **Fixture discipline:** every FEN below is annotated with whether it certifies under **§B
> (today)** or requires **§A (after the extension)**. Verify each with
> `detect_royal_alignment(board, <mover_color>)` returning non-`None` **on the layer claimed**
> before using it as a regression fixture. Do not ship an §A-only FEN as a passing test until
> the helper is extended. FENs use the side-to-move that is the *opponent* (mover already
> moved), matching `board_after`.

1. **Royal pin on a file (rook) — §B, certifies today.**
   FEN `4k3/4q3/8/8/8/8/4R3/4K3 b - - 0 1`. White rook e2, Black queen e7, Black king e8 share
   the e-file; segments e3–e6 and (none) between queen e7 and king e8 are clear; rook e2 is
   not attacked. Mover = White. Attacker → queen → king ⇒ **pin**, wins the queen. Verify:
   `detect_royal_alignment(board, chess.WHITE)` is non-`None`.

2. **Royal pin on a rank (queen) — §B, certifies today.**
   FEN `8/8/8/8/8/8/Q2qk3/7K b - - 0 1`. White queen a2, Black queen d2, Black king e2 share
   the 2nd rank; between a2↔d2 (b2,c2) empty, between d2↔e2 empty; White queen safe. Mover =
   White. Attacker → enemy queen → enemy king ⇒ **pin** (queen-pins-queen, the §1 "queen as
   inner piece" case). Verify `detect_royal_alignment(board, chess.WHITE)` non-`None`.

3. **Royal pin on a file, queen as the pinned inner piece — §B, certifies today.**
   FEN `4k3/8/4q3/8/8/8/4Q3/4K3 b - - 0 1`. White queen e2, Black queen e6, Black king e8 on
   the e-file; e3–e5 empty, e7 empty. White queen pins Black queen to Black king. Mover =
   White. Verify non-`None`.

4. **Royal SKEWER on a rank (queen) — §A ONLY (does NOT certify today; ships only after the
   skewer branch lands).**
   FEN `8/8/8/8/8/8/4kq1Q/7K b - - 0 1`. White queen h2, Black king e2, Black queen f2 share
   the 2nd rank in the order attacker(h2) → king(f2)? — re-order for correctness:
   attacker h2, nearer royal is the **king** only if the king is between h2 and the queen.
   Canonical clean skewer: **`8/8/8/8/8/8/Q1k1q3/7K b - - 0 1`** — White queen a2 (attacker),
   Black king c2 (near), Black queen e2 (far); a2↔c2 (b2) clear, c2↔e2 (d2) clear; the queen
   checks the king down the rank, king must step off, queen e2 falls. `kind = "skewer"`,
   `line_type = "rank"`. **Today `detect_royal_alignment` returns `None` here** (the king sits
   inside the `between(attacker, queen)` span and trips the clear-line veto) — this is the
   §A false-negative the extension fixes. Do not ship as a passing fixture until §A.

5. **Royal pin on a DIAGONAL (bishop) — §A ONLY (does NOT certify today; ships only after the
   diagonal branch lands).**
   FEN `7k/6q1/8/8/8/2B5/8/K7 b - - 0 1`. White bishop c3, Black queen g7, Black king h8 share
   the a1–h8 diagonal (c3 → g7 → h8); between c3↔g7 (d4,e5,f6) clear, between g7↔h8 clear;
   bishop safe. Mover = White. Attacker → queen → king ⇒ diagonal **pin**, `line_type =
   "diagonal"`. **Today `detect_royal_alignment` returns `None`** (no diagonal branch, never
   iterates a bishop) — the §A false-negative the extension fixes. Do not ship as a passing
   fixture until §A.

(Examples 1–3 are the regression set that must stay green on **every** build, present helper
included. Examples 4–5 are the acceptance tests for the §A extension and must be added to the
suite *with* the extension, never before.)

---

## 4. Negative / edge cases (must NOT certify)

1. **K + rook aligned (no queen on the line).** Attacker → enemy rook → enemy king. Vetoed by
   rule 1/3 (the aligned pair is not K+**Q**). Generic pin/skewer territory, not this tag.
2. **K+Q aligned but a piece interposed between them.** Enemy knight on e5 between Ke8 and Qe2.
   Vetoed by rule 7 (near↔far segment occupied) — no real pin/skewer.
3. **Blocker between attacker and the near royal.** White Re2, Black pawn e3, Black Qe6, Black
   Ke8. Vetoed by rule 6 (attacker↔near segment occupied) — the rook does not bear on the
   queen.
4. **Pinner is hanging.** White Rd2 lined up on Black Qd7/Kd8 but the rook is attacked by a
   Black bishop and undefended. Vetoed by rule 8 — `…Bxd2` dissolves the threat for free.
5. **Skewer where the king (near royal) can capture an undefended attacker.** White Qb2 next to
   Black Kc2 with Black Qd2 behind; if Qb2 is undefended the king plays `…Kxb2`. Vetoed by the
   rule-8 skewer tightening (king is an attacker of the adjacent attacker square). Certifies
   **only** if the attacker is defended by the mover.
6. **Diagonal K+Q but the mover has only a rook on the relevant file/rank.** A rook can never
   attack along a diagonal. Vetoed by rule 4 (no mover B/Q for a diagonal). Guards against a
   spurious geometric match — and is the reason rule 4 splits the capability test by
   line-type.
7. **Relative pin where the back piece is a rook, not the king.** Enemy queen pinned to an
   enemy rook. A real *relative* pin (wins queen-for-rook) but **not royal** — no king on the
   line. Excluded here, routed to the general engine. (This is the inclusivity boundary, not a
   miss: it must be caught *somewhere*, just not under this tag.)
8. **Mover's OWN K+Q aligned with an enemy R/Q.** That is the mover being pinned/skewered, not
   setting one up. Excluded — the predicate inspects `opp`'s royalty only and never the mover's
   own king (`opp = not mover_color` is the single source of side truth).
9. **Promotion just created a SECOND enemy queen, only one aligns.** The helper must iterate
   **all** `board.pieces(chess.QUEEN, opp)` (the current loop already does), so a position with
   two enemy queens where exactly one shares a line with the king still certifies on that queen;
   a position where neither aligns is correctly vetoed by rule 3. (Edge guard: a promoted queen
   on the back rank can share the king's rank — handled by the rank branch, no special case.)
10. **King on a board edge / in a castled corner.** e.g. Kg8 after kingside castling with Qg-
    file or Qg-rank alignment. No rank/file/diagonal math changes at the edge; the `between`
    sets are simply shorter. Must behave identically to a center king (regression-test at least
    one corner FEN to catch any off-by-one in a future hand-rolled ray attempt).
11. **Alignment is a check that is also mate-relevant, but the mover did not create it this
    ply.** Still a true standing feature of `board_after`; certifies (see §6 — standing-feature
    posture). The narrator must say the position *contains/threatens* it, never that *this move
    created* it.

---

## 5. Evidence bundle

The narrator should be able to speak verbatim without re-deriving geometry. **The current
helper returns only a single string** (`analyzer.py:412-416`); supplying the structured fields
below is part of the §A work and is a **prerequisite** for emitting `kind`/`line_type` claims.
Build every human string from `PIECE_NAMES` + `chess.square_name` + `chess.FILE_NAMES` /
`chess.RANK_NAMES` — never hand-format — so prose matches the rest of the report.

Return, beyond the boolean:

- `kind`: `"pin"` (queen is the near royal — king behind) or `"skewer"` (king is the near
  royal — king in front). **Must be derived from the distance ordering of rule 5, not
  assumed.** (Today the helper cannot populate this; it is `"pin"` by construction until §A.)
- `line_type`: `"file"`, `"rank"`, or `"diagonal"`. (`"diagonal"` is §A-only.)
- `attacker_square` (`chess.square_name`) and `attacker_piece`
  (`PIECE_NAMES[piece_type]` ⇒ `"rook"`/`"queen"`/`"bishop"`).
- `king_square`, `queen_square` (`chess.square_name`).
- `near_square`, `far_square` — the distance-ordered royal squares (lets the narrator state pin
  vs skewer unambiguously and is the literal evidence that the helper checked ordering, not a
  fixed assumption).
- `between_attacker_and_near`: list of square names proven empty (the cleared inner segment).
- `between_royals`: list of square names proven empty between the two royals.
- `attacker_safe`: `True`, plus `attacker_defenders`: count and squares
  (`board.attackers(mover_color, attacker_sq)`), so the narrator can say *why* the pinner
  survives — and, for a skewer, that the adjacent king cannot just take it.
- `wins_queen`: `True` — the defining royal attribute; this is the attribute name to expose if
  the logic is folded into the general engine (§7).
- `evidence_string` (ready-to-quote, verbatim), built from the fields above, e.g.:
  - pin (file/rank): `"the rook on e2 pins the queen on e7 to the king on e8 down the e-file,
    winning the queen"`
  - skewer (rank): `"the queen on a2 skewers the king on c2 to the queen on e2 along the 2nd
    rank, winning the queen"`
  - diagonal pin: `"the bishop on c3 pins the queen on g7 to the king on h8 along the long
    diagonal, winning the queen"`

> **Honesty constraint:** the `skewer` and `diagonal` `evidence_string` variants must not be
> emitted until §A is implemented and the corresponding §3 fixtures (4, 5) verify green. Today
> only the **file/rank pin** string is reachable; the helper's current single-string return is
> exactly that pin string.

---

## 6. Known limitations

- **Standing-feature, not move-causal.** Reads `board_after` statically, so it certifies a
  royal pin/skewer that was *already present* and merely not resolved, even if the move just
  played was unrelated (mirrors `outpost` / `passed_pawn`). True about the position; the
  narrator may assert the feature but must **not** claim the mover *created* it this ply.
- **Skewers and diagonals are NOT detected by the shipped helper (recall gap).** Until the §A
  extension lands, a genuine royal **skewer** (king in front of queen) and **every diagonal**
  royal pin/skewer go **unreported** — the helper checks file/rank and queen-inner ordering
  only. This is the single biggest correctness gap and is the reason the prompt's "pin or
  skewer" wording currently over-promises the skewer half. **Action item, not acceptable
  steady state:** implement §A.
- **One-ply tactical truth only.** Rule 8 is a single-move material sanity check (pinner not
  immediately capturable / king cannot just take it). It does **not** run Stockfish and will not
  see deeper refutations — an in-between check, a counter-pin, a defended interposition with
  tempo, or a desperado that saves the queen. Geometry plus one-move safety, not engine-verified
  forced win.
- **No interposition-rescue analysis.** A pin/skewer the opponent can break next move by
  interposing a defended piece on the cleared segment is still certified — the detector proves
  the line is *currently* clear, not that it *stays* winning.
- **Single best pairing.** With multiple enemy queens (promotion positions), the helper reports
  one aligned (attacker, queen, line) triple; the bundle describes that one, not an enumeration.
- **No mate/stalemate interaction.** It will not notice that the won queen is moot because mate
  is already forced by other means — out of scope (a different tag).
- **Relative / non-royal pins are intentionally out of scope for THIS tag** and depend on the
  general engine to be caught at all. Until that engine exists they go unreported *as pins* — a
  recall gap in the **general** pin coverage, not a bug in this specialized tag.

---

## 7. Complexity, and the keep-vs-fold recommendation

**Complexity: LOW for §B, LOW–MODERATE for §A.** The vetoes are O(1)–O(8) square comparisons;
the confirm step is a handful of `chess.between` / `SquareSet` emptiness checks plus one
attacker-safety lookup. No engine call, no search, no before/after diff. The **new** work is:
(a) the **diagonal branch** (one `abs`-difference test + iterating bishops alongside queens —
mandatory for inclusivity); (b) the **distance-ordered near/far logic** so **skewers** are
accepted, not vetoed (the current code hardcodes queen-inner); (c) widening the return from a
single string to the structured §5 bundle. All three are mechanical and low-risk, and (a)+(b)
are required before any diagonal/skewer claim may ship.

**Recommendation: KEEP `royal_pin_setup` as a specialized high-value tag, layered on top of a
general pin/skewer engine — do not delete it; and FIX the helper to the §A contract so the tag
is as inclusive as the definition.**

Tradeoffs:

- **Backward compatibility (decisive).** `royal_pin_setup` is a frozen member of `GATED_TAGS`
  (`factgate.py:222-229`) and is named explicitly in the non-negotiable fact-gate prompt rule
  (`narrator.py:202`: *"a pin or skewer that wins the queen (`royal_pin_setup`)"*). Folding the
  tag away would mean editing the closed tag vocabulary, the prompt whitelist, and any A/B
  fixtures — a breaking change across three files for no behavioral gain. Keeping the tag
  preserves every existing certification and the prompt contract verbatim. (Note: keeping the
  tag does **not** excuse leaving the helper diagonal-/skewer-blind — the prompt already
  promises "skewer," so honoring it is a *fix*, not new scope.)
- **Signal quality / narrator value.** "Wins the queen via royal alignment" is a distinctly
  higher-value, more quotable event than a generic pin of a knight; a dedicated boolean tag
  lets the prompt rule keep its sharp wording and lets the narrator lead with the strongest
  claim, rather than pushing pin-vs-skewer discrimination into evidence-string parsing the LLM
  must do at read time.
- **Avoiding logic duplication (hard requirement).** The ray / clear-line / hanging geometry
  must live in **one** place. Recommendation: a general pin/skewer engine owns all of it
  (file, rank, **and diagonal**; pin **and** skewer ordering; hanging guard);
  `detect_royal_alignment` becomes a thin classifier that asks the general result "is the
  aligned pair exactly the enemy king + queen?" and re-labels, **preserving its current
  `Optional[str]` return contract** so `sets_up_royal_pin` / `certified_claims` need no change.
  When that engine exists, expose `royal` and `wins_queen` as evidence attributes that ALSO
  drive this specialized tag.
- **Simplicity (the only point favoring folding the tag).** One predicate is conceptually
  cleaner than two, but the discrimination cost is paid once in the layering code, and `royal`
  / `wins_queen` are computed anyway — so keeping the specialized tag is essentially free.

**Net:** keep the tag; fold the *logic* (not the tag) into a general engine that handles **all
three line-types and both orderings**; expose `royal` / `wins_queen` as evidence attributes
that also drive `royal_pin_setup`. This satisfies backward compatibility, closes the diagonal
and skewer recall gaps the current helper has (James's inclusivity standard), and keeps false
positives out of the high-value `royal_pin_setup` claim (relative / non-royal pins still get
caught — by the general engine — but never mislabeled royal).

**Relevant files:** `C:\Users\詹天哲\Documents\greco\factgate.py` (`sets_up_royal_pin` at
`factgate.py:207-213`, `certified_claims` step 4 at `factgate.py:281-283`, `GATED_TAGS` at
`factgate.py:222-229`); `C:\Users\詹天哲\Documents\greco\analyzer.py`
(`detect_royal_alignment` at `analyzer.py:367-417` — **the helper to extend per §A**, plus
`PIECE_NAMES` at `analyzer.py:211-218` and the `chess.between` / `SquareSet` idioms);
`C:\Users\詹天哲\Documents\greco\narrator.py` (fact-gate prompt rule naming `royal_pin_setup`
at `narrator.py:202`; `certified` serialization and the Tier-1 evidence slot at
`narrator.py:450-462`).
