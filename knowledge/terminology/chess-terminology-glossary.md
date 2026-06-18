# Chess Terminology — Greco Narrator Vocabulary

> **STATUS: IN REVIEW (paused 2026-06-15).** Definitions are being approved term-by-term with
> James. `[A]` geometric terms: **13 approved (✅), 2 open (⏸ infiltration, fianchetto), ~6
> unreviewed**; `[B]`/`[C]` and all supporting vocabulary pending.
> **To resume, read `RESUME_HERE.md` in this folder first.**
> Date: 2026-06-15. Author: Greco project.
>
> **Review convention used in this file:**
> - `✅ approved YYYY-MM-DD` — James has explicitly approved this definition.
> - `⏸` — James has seen this term but a specific ruling is still pending.
> - `⚠️ NEEDS JAMES REVIEW` — written by Claude; James has **not** approved this definition.
>   Do not treat it as settled or write code that depends on this wording until James signs off.
> - No marker at all — same as ⚠️ (unreviewed); applies to all supporting/descriptive vocabulary
>   below each numbered section header.

---

## How to read this file

**The load-bearing rule — a definition is NOT a permission.** This file says what a term
*means*. It does **not** grant the narrator permission to apply the term to a real position.
Permission is decided in **code**, by the fact-gate (`factgate.py` → `certified_claims()`),
never by a word appearing here. Vocabulary lives here; the *right to use a word about a board*
lives in the detectors. (Full doctrine: `docs/specs/TERMINOLOGY_TIERS.md`.)

**Tier legend** — every term is tagged with exactly one tier:

- **[A] — geometric predicate.** A clean, decidable board test. Implemented in code now (or
  trivially buildable). The narrator may assert it the instant the predicate fires.
- **[A\*] — geometric but approximate.** Decidable only with an engine-assisted estimate; the
  prose must hedge (e.g. "near-zugzwang"). Only `zugzwang` is here.
- **[B] — checkable but harder (default-deny; paced in).** The term makes a *verifiable* claim
  but needs a compound detector (eval, the engine's line, cross-move state). Until that
  detector ships, the narrator is **withheld** from asserting it — it is **not** free vocabulary.
- **[C] — genuinely free (no checkable claim).** Reserved ONLY for words no board could ever
  prove false — in practice almost nothing qualifies. *Hard to detect is not the same as
  not-a-claim:* "calm" or "solid" is hard to detect yet perfectly falsifiable, so it is **not**
  free. (Corrected 2026-06-15 per James — the earlier "non-falsifiable register" framing was a
  loophole that would have let the narrator use checkable words inaccurately.)

**[B] splits into two flavors, by what kind of detector it needs:**
- **[B-engine]** — checkable from Stockfish / python-chess (eval, the engine's line, geometry).
- **[B-human]** — checkable only against a model of *human* play and perception (the Maia /
  human-vs-engine track), **not** raw engine metrics. Aesthetic/"human" words live here: calling
  a move "brilliant" claims a human finds it surprising and hard to find — it must be gated to a
  human-specific detector, never to "the engine likes this sacrifice."

**The `→ Verifiable as:` line** (on [A]/[A\*]/[B] entries) states the precise testable
condition — the bridge from this prose definition to a future predicate. This is what makes the
glossary "implementable in code later." It is a *specification of the test*, not the code.

**Sources.** Definitions synthesized from multiple expert references and cross-checked:
Wikipedia's *Glossary of chess*, *Chess tactic*, and the dedicated concept articles
(*Pin*, *Skewer*, *Fork*, *Discovered attack*, *Outpost*, *Fianchetto*, *Passed pawn*,
*Isolated pawn*, *Tempo*, *Compensation*, *Zugzwang*); standard chess literature; and Greco's
own adversarially-reviewed predicate specs (`docs/specs/PREDICATE_SPECS.md`). Where a term is
adapted from Wikipedia (CC BY-SA 4.0), that license is recorded in the deposit `meta.json`.

**Narration convention** (for any prose examples): full piece names — knight, bishop, queen,
rook, king; "plus check" rather than "plus" for a check.

---

## Tier summary (quick-review index)

**[A] geometric predicates (18 — the active build target):** pin, skewer, fork, discovered
attack, discovered check, double check, battery, outpost, passed pawn, isolated pawn, doubled
pawns, backward pawn, rook lift, infiltration, fianchetto, back-rank weakness, luft, mate-in-one
threat.

**[A\*] approximate:** zugzwang.

**[B-engine] checkable from engine/geometry (default-deny):** tempo, initiative, compensation,
prophylaxis, overloaded piece, zwischenzug, weak square / hole, space advantage, blockade,
minority attack, counterplay, x-ray, overprotection, calm, committal, solid, ambitious, risky.

**[B-human] checkable only against a human-play model (Maia track; default-deny):** brilliant,
beautiful, elegant, ugly, enterprising, principled, double-edged, a practical try.

**[C] genuinely free:** none confirmed — under review. Every evaluative word above has been moved
to [B]; [C] is reserved for pure rhetorical connectives that assert nothing about the board.

Everything else below is supporting/definitional vocabulary (mostly geometric facts the engine
already supplies, or descriptive terms with no standalone claim).

---

## 1. Tactical motifs

> **Review status:** Fork ✅, Pin ✅, Battery ✅, Skewer ✅, Discovered attack ✅,
> Discovered check ✅, Double check ✅ — approved by James 2026-06-15.
> All other terms in this section **⚠️ NEED JAMES REVIEW** (written by Claude; not yet approved).

**Fork** *[A] — ✅ approved 2026-06-15* — One piece attacks two or more enemy targets at once
such that the opponent cannot parry them all. Precisely: after the move a single friendly piece
attacks ≥2 enemy pieces (or a piece plus a mate/promotion threat), and **at least one target
cannot be saved** on the reply — the set includes the king (a forcing check-fork) and/or pieces
that are undefended or more valuable than the forker — so the forking side **nets material**
after the opponent's best response. The forking piece must not merely hang for nothing: if it is
capturable, the recapture must still win material. Variants: knight fork (the classic,
unblockable), pawn fork, queen fork, *royal fork* (king + queen), *family fork* (king + queen +
rook).
→ **Verifiable as:** after the move, one friendly piece attacks ≥2 enemy pieces; compute the
opponent's best save (move the most valuable, defend, or counter-check); certify only if the
forking side then wins material (a forked piece falls for inadequate compensation) or one target
is the king. Greco has `detect_double_attack` → the `fork` tag.

**Double attack** *[A]* — The broader family: two threats created by one move. A fork is a
double attack by a *single* piece; a double attack may also be two separate threats (e.g. one
piece unmasks a second's threat). Every fork is a double attack; not every double attack is a
fork.

**Pin** *[A — medium] — ✅ approved 2026-06-15 (v3)* — A piece is **pinned** when it stands on an
enemy bishop/rook/queen's line of attack and **moving it away would let that slider win material
along the now-open line** — the pinned piece is acting as a shield. **Absolute:** it shields its
own king, so moving it is *illegal*. **Relative:** it shields material that would be lost. The
shielded target may be **worth less than the pinned piece**, as long as winning it is a real
material gain — e.g. a knight pinned by a fianchettoed bishop to an **undefended b2-pawn**:
moving the knight allows …Bxb2, winning the pawn (and here also hitting the rook behind it). The
pin **dissolves the moment the shielded target gains an adequate defender** — e.g. Rb1 defends
b2, so the knight is then free (…Bxb2 Rxb2 is even).
→ **Verifiable as:** the pinned piece is the first piece on an enemy slider's ray; remove it and
run a static-exchange evaluation on the newly-exposed line — if the slider wins material (or the
exposed piece is the king → absolute), it is pinned. Re-running per position naturally captures
the pin dissolving once a defender arrives.
→ *Internal variant labels (absolute / relative / "x-ray") are code-side only — not narrator
phrasing. Report wording is TBD (per James).*

**Skewer** *[A] — ✅ approved 2026-06-15* — The same three-in-a-line geometry as a pin, but *reversed*: the more
valuable piece (or the king) is in **front**, and when it moves off the line the lesser piece
behind it is captured. An *absolute skewer* has the king in front; a *relative skewer* a
higher-value piece in front.
→ **Verifiable as:** friendly slider → enemy higher-value-or-king → enemy lesser piece,
collinear on the slider's line with a clear path; distinguished from a pin purely by the
front/back value ordering.

**Discovered attack** *[A] — ✅ approved 2026-06-15* — A move of one piece that *unmasks* an attack by a friendly bishop,
rook, or queen that the moved piece had been blocking. The power is that two things happen at
once: the moved piece can make its own threat while the unmasked piece makes another.
→ **Verifiable as:** comparing the unmasking friendly slider's attack set before vs. after the
move, a new enemy target appears on the vacated line that the slider could not previously reach.

**Discovered check** *[A] — ✅ approved 2026-06-15* — A discovered attack whose unmasked line hits the enemy king.
→ **Verifiable as:** the discovered-attack test where the newly-attacked piece is the king.

**Double check** *[A] — ✅ approved 2026-06-15* — A check delivered by *two* pieces simultaneously: the moving piece
gives check and *also* unmasks a checking piece behind it. The defender **must move the king**
(no block or capture can stop two checkers at once).
→ **Verifiable as:** after the move, the side to move is in check from ≥2 attackers.

**Battery** *[A] — ✅ approved 2026-06-15* — Two (or more) friendly pieces lined up on the same
file, rank, or diagonal so their pressure reinforces: doubled rooks on a file, queen-and-rook on
a file/rank, or queen-and-bishop on a diagonal.
→ **Verifiable as:** ≥2 friendly pieces of compatible movement are consecutive on one line,
aimed the same direction, with no friendly piece breaking the support.

**X-ray attack** *[B]* — A piece's influence "through" an enemy (or friendly) piece on a line —
it attacks or defends a square *beyond* the intervening piece, which matters once that piece
moves or is captured. Related to, but distinct from, the pin/skewer (an x-ray need not win
material on the spot). Withheld as a named claim until a precise detector separates it from
ordinary line attacks.

**Deflection** *[B]* — A tactic that forces an enemy piece *away* from a duty (defending a
square, a piece, or a mating square) by giving it a threat it must answer elsewhere. Checkable
in principle (the deflected piece's defensive duty can be computed) but needs forcing-sequence
analysis. Withheld.

**Decoy (attraction)** *[B]* — Luring an enemy piece *onto* a specific square (often by a
sacrifice) where it can be exploited — e.g. dragging the king into a fork or mating net.
Compound/forcing-sequence claim; withheld.

**Removing the defender (undermining)** *[B]* — Capturing or driving off the piece (or pawn)
that defends a key target, so the target then falls. Checkable but requires defender-mapping
and a follow-up; withheld.

**Interference (obstruction)** *[B]* — Interposing a piece (often a sacrifice) to cut the line
between an enemy piece and what it defends or where it must go. Forcing-sequence claim; withheld.

**Overloaded (overworked) piece** *[B]* — A single enemy piece burdened with two or more
defensive duties it cannot all fulfil; loading a second threat onto it wins. Greco already
computes an `overloaded_defender` field, but it is **not yet a certified gated claim** — withheld
as an *asserted* term until registered as a tag with its own test. (This is the recommended
first Tier-B graduation.)
→ **Verifiable as:** an enemy piece is the *sole* defender of ≥2 distinct things (pieces/
mating squares) such that it cannot cover both if one is attacked.

**Zwischenzug (in-between move / intermezzo)** *[B]* — Instead of making the "expected" reply
(a recapture or the answer to a threat), a player first injects a *more forcing* move (usually a
check or a bigger threat), then returns to the original business having gained. Checkable only
within a forcing sequence; withheld. Restrict the first detector to the clean "interpolated
check before recapture" case.

**Desperado** — A piece already doomed (trapped or hanging) that "sells itself dearest" — grabs
material or forces a draw before it is lost. Descriptive; arises from a forcing line.

**Windmill (see-saw)** — A repeating sequence of discovered checks and captures, where one
piece swings back and forth raking in material while the enemy king is shuffled in and out of
check. Rare; descriptive.

**Clearance** — Vacating a square, rank, file, or diagonal (often by sacrifice) so a friendly
piece can use it. Descriptive of intent within a line.

**Combination** — A forcing sequence of moves, usually involving a sacrifice, that achieves a
concrete gain (material or mate). An umbrella term for "a tactic that works by force."

**Trapped piece** *[B]* — An enemy piece with no safe square — it will be won regardless of
whose move it is. Checkable (enumerate its safe squares) but needs care around defenders and
counter-threats; withheld.

---

## 2. Pawn structure

> **Review status:** Isolated pawn ✅, Doubled pawns ✅, Backward pawn ✅, Passed pawn ✅ —
> approved by James 2026-06-15. All other terms in this section **⚠️ NEED JAMES REVIEW**.

**Isolated pawn** *[A] — ✅ approved 2026-06-15* — A pawn with **no friendly pawn on either adjacent file**. It cannot be
defended by a pawn, so pieces must guard it, and the square in front of it is a natural enemy
outpost — yet it also grants open/half-open lines and central space.
→ **Verifiable as:** no friendly pawn exists on either file immediately adjacent to the pawn's
file.

**Isolated queen's pawn (IQP / isolani)** *[A]* — An isolated pawn specifically on the d-file —
the most strategically important isolani, because it props up central outposts and opens the c-
and e-files for the rooks.
→ **Verifiable as:** isolated-pawn test on the d-file.

**Doubled pawns** *[A] — ✅ approved 2026-06-15* — Two friendly pawns on the **same file** (three = *tripled*). They
cannot defend each other and the front one blocks the rear, generally a structural weakness —
though they can grant a half-open file and extra central control.
→ **Verifiable as:** ≥2 friendly pawns share a file.

**Backward pawn** *[A] — ✅ approved 2026-06-15* — A pawn that has fallen behind the pawns on **both** adjacent files and
**cannot be safely advanced**: its advance (stop) square is controlled by an enemy pawn, and no
friendly pawn can come alongside to support the push. Often a chronic weakness because the file
in front is half-open for the enemy.
→ **Verifiable as:** no friendly pawn on an adjacent file is on or behind this pawn's rank
(it is the rearmost of its neighbours), AND its stop square is attacked by an enemy pawn, AND no
friendly pawn can advance to defend the stop square. *(Decision D4: do not require the half-open
file for the base tag; record it as an evidence attribute.)*

**Passed pawn** *[A] — ✅ approved 2026-06-15 (v2)* — A pawn with **no enemy pawn ahead of it** — on
its own file or any adjacent file — that could stop or capture it on the way to promotion. The
further advanced, the more dangerous.
→ **Verifiable as:** no enemy pawn occupies any square ahead of the pawn (toward promotion) on
its own file or on any *existing* adjacent file — an a-pawn has only the b-file beside it, an
h-pawn only the g-file (use the adjacent files that exist; don't index off the board).

**Protected passed pawn** *[A]* — A passed pawn defended by a friendly pawn; especially strong
because it needs no piece to babysit it.
→ **Verifiable as:** passed-pawn test, AND a friendly pawn defends it.

**Connected passed pawns** *[A]* — Two (or more) passed pawns on adjacent files; they shield and
promote each other and are very hard to blockade — often decisive on the sixth rank or beyond.
→ **Verifiable as:** ≥2 passed pawns on adjacent files.

**Outside passed pawn** *[B]* — A passed pawn far from the other pawns, used as a decoy: the
enemy king must chase it, abandoning the other wing. Checkable but needs a "distance from the
pawn mass" judgment; withheld as a named claim.

**Candidate passed pawn** *[B]* — A pawn that can *become* passed by force in a majority (it has
no enemy pawn directly in front and outnumbers the enemy pawns that could stop it). Needs a
majority/advance calculation; withheld.

**Hanging pawns** *[B]* — Two friendly pawns side by side (classically c- and d-pawns) on
half-open files with no friendly pawns on the files beside them — mobile and space-gaining, but
a target because neither can be defended by a pawn. Needs a structural pattern test; withheld.

**Pawn chain** — A diagonal line of pawns each defending the next; the **base** (the undefended
rear pawn) is the standard target, attacked via a pawn break.

**Pawn island** — A connected group of friendly pawns separated by empty files from the next
group; fewer, larger islands are generally healthier than many small ones.

**Pawn majority** — More friendly pawns than enemy pawns on one wing; its value is the ability
to manufacture a passed pawn there.

**Minority attack** *[B]* — Advancing a *minority* of pawns against an enemy *majority* (classic:
White's b- and a-pawns vs. Black's queenside majority) to provoke a weakness (a backward or
isolated pawn). Plan-level; withheld.

**Pawn storm** — Advancing a phalanx of pawns at the enemy king (typical in opposite-side
castling) to rip open lines. Descriptive of a plan.

**Pawn break (lever)** — A pawn move offering an exchange that, if taken or pushed past, opens
the position or frees one's own game; the standard way to challenge a pawn chain or gain space.

**Hole / weak square** *[B]* — A square that **can no longer be defended by a friendly pawn**
(both adjacent-file pawns have advanced past it or are gone) and sits in one's own territory; a
permanent home for an enemy piece (an enemy outpost). "Hole" and "weak square" are used
interchangeably for this. Checkable (it's the outpost test from the defender's side) but
withheld as a standalone narrator claim until a detector ships.
→ **Verifiable as:** no friendly pawn can ever again attack the square (no friendly pawn on
either adjacent file is behind it), and it is not occupied/contested by a friendly pawn.

**Blockade** *[B]* — Planting a piece (ideally a knight) directly *in front of* an enemy passed
or isolated pawn to stop it dead; the blockading square is safe precisely because the pawn
cannot attack the piece on it. Needs a passed/isolated-pawn-plus-occupancy test; withheld.

---

## 3. Pieces & activity

> **Review status:** Outpost ✅, Rook lift ✅ — approved by James 2026-06-15.
> Infiltration ⏸, Fianchetto ⏸ — pending James's ruling on the open questions.
> All other terms in this section **⚠️ NEED JAMES REVIEW**.

**Outpost** *[A] — ✅ approved 2026-06-15 (v2)* — Distinguish two things. An **outpost square** is a
square **defended by a friendly pawn** that **no enemy pawn can ever advance to attack** (no
enemy pawn remains on either adjacent file able to hit it) — the same square is a *hole* from
the opponent's side. A piece is **"on an outpost"** when a friendly piece (ideally a knight)
stands on such a square. The square's status is a *structural fact independent of occupancy*
(empty; a friendly piece → "on an outpost"; or even an enemy-held square one aims to take over).
Most valuable when advanced into enemy territory (≈ 4th–6th rank), but that rank range is
**typical, not a strict requirement**.
→ **Verifiable as (outpost square):** the square is defended by a friendly pawn AND no enemy
pawn on an adjacent file can ever advance to attack it. **"On an outpost":** that, plus a
friendly piece occupies the square. Greco has `is_outpost`.

**Rook lift** *[A] — ✅ approved 2026-06-15 (v2)* — Repositioning a **single** rook from the back
rank to an active attacking post — typically up a file to the 3rd rank (sometimes 4th/5th) and
then **across** toward the enemy king or a target (e.g. Rf1–f3–h3) — letting it join an attack
without an open file. **Distinct from doubling rooks** (stacking *both* rooks on one file/rank as
a battery): a lift is one rook's up-then-sideways maneuver; doubling is a two-rook battery.
→ **Verifiable as:** a rook reaches an advanced rank (commonly the 3rd) from its home rank,
poised to swing laterally toward the enemy position — not merely sliding up an open file, and not
two rooks doubling on a line. (The full lift spans moves — up, then across.) Greco has
`is_rook_lift`.

**Infiltration / penetration** *[A] — ⏸ DEFERRED, warrants further discussion (2026-06-15)* — A
piece penetrating deep into the enemy camp — reaching a square from which it attacks pawns,
pieces, or the king, usually through a weak square / hole the enemy can no longer defend with a
pawn. Canonical case: a rook or queen on the 7th/8th rank ("a rook on the seventh"); broadened to
include a knight on a deep outpost/weak square (Nf5, Ne6, Nd6), a bishop/queen on a weak square,
and a king infiltrating in the endgame. **Open question (James): is the proposed verifiable-as
inclusive / precise enough? Resume here.**
→ **Provisional verifiable as:** a friendly rook/queen on the opponent's 7th/8th rank, OR a
friendly piece established on a pawn-unattackable square deep in enemy territory (~rank 5+ from
the mover's side); entry-square stored as evidence.

**Fianchetto** *[A] — ⏸ pending: edge case under discussion (2026-06-15)* — Developing a bishop
to the long-diagonal flank square — **b2/g2 (White), b7/g7 (Black)** — so it rakes the long
diagonal. The redundant "knight-pawn advanced" clause is dropped (a bishop can only reach g2 once
the g-pawn has left). **Open edge case (James):** is a bishop that reaches the fianchetto square
**by capture, with no knight-pawn in front of it**, still "fianchettoed"? — e.g. the Timoshenko
Variation of the Alekhine (1.e4 Nf6 2.Nc3 d5 3.e5 d4 4.exf6 dxc3 5.fxg7 cxd2+ 6.Bxd2 Bxg7): the
g7-bishop has no g-pawn and arrived by capture. Decide whether *fianchetto* requires the
supporting knight-pawn present (g6/g3 · b6/b3) or is pure bishop-placement. Claude's lean: the
pawn is constitutive (lone bishop = "on the long diagonal," not strictly fianchettoed). **Resume
here.**
→ **Verifiable as (provisional):** a friendly bishop on b2/g2/b7/g7 — possibly AND the supporting
knight-pawn present on the third rank in front of it (pending the decision above).

**Good bishop / bad bishop** — A *bad bishop* is hemmed in by its own pawns fixed on its color;
a *good bishop* is unobstructed by them. Relative, structural judgment.

**The bishop pair** *[B]* — Holding both bishops while the opponent does not; in open positions
the two bishops cover both colors and are worth more than bishop+knight or two knights. As a
*static* fact it is trivially countable, but as an *advantageous claim* it depends on the
position being open — withheld as an asserted advantage until qualified.

**Opposite-colored bishops** — Each side has one bishop, on opposite colors. Famous for
drawish endgames (neither bishop can challenge the other) yet sharpening attacks in the
middlegame (the attacker's bishop has no defender of its color).

**Centralization** — Placing pieces toward the center, where they control the most squares and
can swing to either wing.

**Development** — Bringing the knights and bishops (then rooks, via castling) off their home
squares into active play during the opening; a *lead in development* is a head start in piece
activity.

**The initiative** *[B]* — The ability to keep making threats that force the opponent to
respond, dictating the course of play. Checkable in principle (a run of forcing moves the
opponent only answers) but needs cross-move "who is forcing whom" state; withheld. Depends on
`tempo` shipping first.

**Tempo** *[B]* — A single move as a unit of time. You **gain a tempo** when you achieve
something (usually development) *while* forcing the opponent to react — e.g. developing a knight
that attacks the queen, so the queen must move again and your development is "free." You **lose
a tempo** by moving the same piece twice for no gain. The claim "this move wins a tempo" is
**checkable** (the move develops/improves *and* makes a threat the opponent must answer) but
needs threat-plus-improvement detection; withheld until its detector ships.
→ **Verifiable as (future detector):** the move both (a) improves the mover's position
(develops a piece, or makes a real threat) and (b) attacks an enemy piece/creates a threat whose
forced answer does not improve the opponent — reusing Greco's threat detection and the engine's
reply line.

**Space advantage** *[B]* — Controlling more of the board (typically measured by pawns advanced
past the midline and the squares behind them), giving one's pieces more room to maneuver.
Approximate by nature (a square-count heuristic); withheld, and the prose must hedge.

**Prophylaxis** *[B]* — A move that *prevents* the opponent's plan or threat **before** it
materializes — anticipating and neutralizing their idea rather than pursuing one's own. The
heaviest Tier-B term: it needs a before/after model of the opponent's best plan. Withheld; built
last.

**Overprotection** *[B]* — Nimzowitsch's idea of defending a key point with *more* pieces than
strictly needed, so those pieces draw strength from it and the point can never be undermined.
Plan-level; withheld.

**Color complex** — A set of same-colored squares that has become weak (typically after the
bishop of that color is gone), which enemy pieces exploit.

**Knight on the rim** — A knight on the edge (a- or h-file), proverbially "dim" because it
controls few squares.

---

## 4. Files, ranks, lines & the board (mostly engine-supplied facts)

> **Review status:** No terms in this section have been approved by James. All **⚠️ NEED JAMES REVIEW**.

**Open file** *[A] — ⚠️ NEEDS JAMES REVIEW* — A file with no pawns of either color; the ideal highway for a rook or
queen.
→ **Verifiable as:** no pawn of either color on the file. (Greco computes `open_files`.)

**Half-open file** *[A] — ⚠️ NEEDS JAMES REVIEW* — A file with only the *enemy's* pawn(s) on it (none of yours); a
natural avenue to pressure that enemy pawn.
→ **Verifiable as:** the file has ≥1 enemy pawn and no friendly pawn. (Greco computes
`half_open_*`.)

**Closed file** — A file on which both colors have a pawn.

**The center** — The four central squares (d4, e4, d5, e5) and, more loosely, the larger central
zone; controlling it confers mobility and the ability to switch wings.

**Long diagonal** — The a1–h8 or a8–h1 diagonal; the bishop's most powerful line, the target of a
fianchetto.

**File / rank / diagonal** — A column (file), row (rank), or color-line (diagonal) of squares;
the basic geometry along which rooks (file/rank), bishops (diagonal) and queens (all) move.

---

## 5. King safety, attack & mating patterns

> **Review status:** No terms in this section have been approved by James. All **⚠️ NEED JAMES REVIEW**.

**Back-rank weakness** *[A] — ⚠️ NEEDS JAMES REVIEW* — A king stuck on its back rank behind its own unmoved pawns, with
no escape square, so an enemy rook or queen reaching that rank threatens mate. Certifies the
*vulnerability* (a standing weakness), distinct from an actual forced mate.
→ **Verifiable as:** the friendly king is on its back rank, its forward escape squares are
blocked by its own pawns/pieces (no luft), and the enemy has ≥1 rook or queen that could reach
the back rank.

**Back-rank mate** — The mate itself: a rook or queen checkmates along the back rank because the
king is fenced in by its own pawns.

**Luft** *[A] — ⚠️ NEEDS JAMES REVIEW* — "Air" for the king: a pawn move that opens an escape square so the king cannot
be mated on the back rank. **Side-agnostic** — for a kingside-castled king (g1/g8) the luft pawns
are the f/g/h pawns; for a **queenside-castled** king (c1/c8) they are the a/b/c pawns. Not a
fixed file list.
→ **Verifiable as:** a friendly pawn move, adjacent to or in front of the friendly king, that
newly creates an empty, non-fatal flight square the king could step to which did not exist
before the move.

**Mate-in-one threat** *[A] — ⚠️ NEEDS JAMES REVIEW* — The side to move threatens a checkmate on the next move that the
opponent must prevent.
→ **Verifiable as:** a null-move probe — if the opponent "passed," the mover would have a legal
move delivering checkmate (excluded when the mover is currently in check). Greco has
`threatens_mate_in_one`.

**Castling** — The one move that relocates king and rook together, tucking the king toward a
flank (kingside = short, O-O; queenside = long, O-O-O) where it is usually safer.

**Opposite-side castling** — The two kings castle on opposite wings, the classic signal for
mutual pawn storms and sharp, racing attacks.

**King safety / pawn shield** — The intact pawns (and pieces) sheltering the king; advancing or
losing the shield pawns *weakens* the king.

**Smothered mate** — A king mated by a knight while completely hemmed in by its own pieces — the
knight cannot be blocked or, being the sole checker reachable only by the king, captured.

**Perpetual check** — An unstoppable repeating series of checks the defender cannot escape,
forcing a draw by repetition; a standard saving resource for the worse side.

**Mating net** — A web of threats from which the king cannot escape; mate is inevitable even if
not immediate.

**Mating attack** — A sustained assault aimed at checkmating the king.

**Sacrifice** *[B]* — Deliberately giving up material for a greater (often non-material) gain.
A **real (sound) sacrifice** banks on long-term compensation that can't be immediately
recalculated; a **sham (pseudo-) sacrifice** is a short forced sequence that regains the material
or mates. Greco already detects sound vs. unsound sacrifices; the *named* certified claim is
governed by that detector.

**The exchange** — The trade of a rook for a minor piece; winning a rook for a bishop/knight is
"winning the exchange." An **exchange sacrifice** gives a rook for a minor piece for positional
compensation (an outpost, a color complex, an attack).

---

## 6. Strategic & evaluation concepts

> **Review status:** No terms in this section have been approved by James. All **⚠️ NEED JAMES REVIEW**.

**Material** *[A — engine fact]* — The total value of the pieces; "up/down material" is the
running balance. Greco computes `material_balance` directly; the claim is gated on that number,
not on prose.

**Compensation** *[B]* — The positional value gained in return for sacrificed material:
initiative and attack, a lead in development, an exposed enemy king, the bishop pair, a superior
pawn structure, space, or strong passed pawns. The defining test is that the **evaluation stays
roughly level despite the material deficit**. Checkable (material balance + engine eval, both of
which Greco has) but not yet generalized into a named claim; withheld — and a high-value early
Tier-B target.
→ **Verifiable as (future detector):** the mover is down material yet the engine evaluation is
near-equal or favorable — the gap is "paid for."

**Counterplay** *[B]* — The defending side's *own* active threats, used to offset the
opponent's pressure rather than passively defending. Checkable (does the worse side generate
forcing threats?) but compound; withheld.

**Simplification** — Trading pieces to reach a clearer position — usually to blunt an attack, or
to convert a material edge into a winning endgame.

**Dynamic vs. static** — *Static* factors are lasting (pawn structure, material); *dynamic*
factors are temporary and energetic (piece activity, initiative, threats). A *dynamic* style
accepts static weaknesses for activity.

**Gambit** — An opening sacrifice (usually a pawn) for development, initiative, or central
control.

**Equality** — A position the engine assesses as roughly balanced ("=").

**Winning / decisive advantage** — An advantage large enough to win with accurate play; Greco
expresses this through the engine evaluation, not as free prose.

**Quiet move** — A non-checking, non-capturing move — often the hardest to find in a combination,
because it threatens without announcing itself.

**Waiting move** — A move that changes little but passes the obligation to move back to the
opponent — decisive in zugzwang situations.

**Candidate move** — A move identified as worth calculating; "thinking in candidate moves" is
choosing among the two or three most promising tries.

---

## 7. Endgame concepts

> **Review status:** No terms in this section have been approved by James. All **⚠️ NEED JAMES REVIEW**.

**Zugzwang** *[A\*] — ⚠️ NEEDS JAMES REVIEW* — A position where **every** legal move worsens the player's position, so
they would prefer to pass but the rules forbid it. It is *not* the same as merely being worse —
the defining feature is that *all* moves hurt. Common in king-and-pawn endgames, rare with many
pieces (more pieces → more harmless moves). **Only partly decidable** — Greco can flag it only by
an engine estimate (every legal move drops the eval beyond a margin while a null move would be
better), so the prose must hedge ("near-zugzwang"/"zugzwang-like") unless the strict signal holds.
→ **Verifiable as (approximate):** for the side to move, every legal move's eval is meaningfully
worse than the (illegal) null-move eval — i.e. having to move is itself the problem.

**Mutual (reciprocal) zugzwang / trébuchet** — A position where *whoever* is to move is the one
harmed; the *trébuchet* is the pure case where the player to move loses outright.

**Opposition** — Kings facing each other with one square between them; the side **not** to move
"has the opposition" and can force the other king to give ground — a specialized king-and-pawn
zugzwang.

**Distant opposition** — The same battle of kings at a greater (odd-numbered) distance along a
file, rank, or diagonal.

**Triangulation** — A king maneuver that "wastes" a move (taking three moves to do a one-move
job) to hand the opponent the obligation to move — i.e. to put them in zugzwang.

**Fortress** — A drawing setup where the material-down side erects a position the stronger side
cannot break, regardless of material.

**Key squares** — The squares a king must reach to force a win (or that a defender must hold);
the heart of king-and-pawn endgame technique.

**Breakthrough** — A pawn sacrifice (often a sequence) that forces a passed pawn through an
apparently solid enemy pawn wall.

---

## 8. Register, aesthetic & "human" vocabulary *[Tier B — gated, default-deny]*

> **Review status:** No terms in this section have been approved by James. All **⚠️ NEED JAMES REVIEW.**
> (The tier placement was corrected by James 2026-06-15, but the individual definitions were not reviewed.)
>
> **Corrected 2026-06-15 (per James).** These were wrongly filed as "free register." They are
> **not** free: nearly every one makes a claim a board could prove wrong, so each is **gated**
> (default-deny until a detector ships). They split by the kind of detector required.

**[B-engine] — a checkable structural / quality core:**

**Calm** — a quiet, non-forcing move (no check, capture, or direct threat); a forcing move is not
calm. **Committal** — irreversibly fixes the pawn structure or king position; a move that changes
nothing lasting is not committal. **Solid** — creates no new weakness (no hole, no backward/
isolated pawn, no exposed king). **Ambitious** — objectively reaches beyond what the position
supports (an eval/risk signal). **Risky** — sharpens the position and raises variance (eval
volatility, opposite-side play).

**[B-human] — checkable only against a model of human play (the Maia / human-vs-engine track):**

**Brilliant** — objectively strong **and** humanly surprising / hard to find (low human-move
probability at the player's level, often a sacrifice whose point is deep). NOT "a sacrifice the
engine likes" — the *human* difficulty is the claim. **Beautiful / elegant** — aesthetic:
economy, paradox, a quiet or surprising point; human perception, not an eval threshold. **Ugly**
— achieves the aim by awkward / anti-positional means. **Enterprising** — willingly steers into
complications a human must navigate. **Principled** — follows the strategic guideline a human
would cite. **Double-edged** — chances for both sides; a human would call the position unclear.
**A practical try** — objectively not best, but poses real problems to a *human* opponent (high
human error-probability) — e.g. a swindle attempt in a lost position.

> **Detector note (folds into the Maia design / `TERMINOLOGY_TIERS.md`).** The [B-human] terms
> are the concrete reason the human-vs-engine model matters for *narration*, not just
> move-labeling: they need Maia-style "how would a human see this?" signals (surprise,
> difficulty, error-probability) before the narrator may use them. None are licensed until those
> detectors exist.

---

## Open notes for James (judgment calls embedded above)

1. **Tier placement of a few borderline terms.** I placed *bishop pair*, *outside passed pawn*,
   *candidate passed pawn*, *hanging pawns*, *trapped piece*, and *x-ray* in **[B]** (checkable
   but not-yet-built) rather than [A], because each needs more than a one-shot geometric test.
   Flag any you think are simpler than I've judged.
2. **Sacrifice & material** are really *engine facts* Greco already computes, so I tagged them to
   the existing detectors rather than as new predicates — confirm that framing.
3. **`weak square` / `hole`** I treated as one concept (two names). Confirm you want them merged.
4. **Coverage.** This is ~95 core terms — comprehensive for commentary, but deliberately omits
   archaic/slang glossary entries (e.g. "patzer", "woodpusher", "swindle" as slang). Tell me if
   you want those breadth terms added, or kept out as non-functional.
