# Detection Spec: Piece Activity & Development (`development`)

Status: **NEW predicate family — awaiting James's approval.** Introduces one general,
engine-free **piece-activity primitive** (`piece_activity`) and one derived per-move claim,
`development`, built on top of it. Motivated by the recurring narrator error James flagged:
*"…a6 allows the development of the a8-rook"* — a positional claim Greco has **no fact for**,
so the LLM invents it (structurally the same bug as "b4 kicks the knight," but in a concept
class the fact-gate never covered). `factgate.py` contains the word "develop" **zero times**
today; "development" lives only as loose coaching in the narrator prompt, ungated. This spec
closes that gap the same way pin/outpost/rook-lift were closed: a deterministic predicate
certifies the claim from the board alone, and the narrator may assert it only when certified.

**Design posture.** Everything here is **pure and engine-free** (python-chess only), matching
the `factgate` contract. The core insight (James, 2026-07-22): **development is *derived* from
piece activity** — a developing move is one that raises a piece's activity — so activity is the
primitive and development is a positive delta on it. Every rule below was **implemented and run
against real positions** before being written down; the verified activity numbers appear in the
example tables. Two findings from that bench test shaped the final design and are called out
in-line: (1) a naive "safe-move" filter silently rejected **Nf3**, the most canonical developing
move in chess — so the primitive is the simpler, more robust **control-count**; (2) control-count
is a **dead signal for rooks** — so rooks get their own castling/connection track.

**Approval tags.** The predicate itself is a pure detector (no wording); it may be implemented
once James approves the *definition* here. The narrator-facing **wording** in §7 (the
`_FACTGATE_NARRATOR_RULES` entry and the NON-NEGOTIABLE prohibition) is drafted but **must ship
tagged `# ⚠️ PENDING_APPROVAL`** until James signs the exact phrasing (per `CLAUDE.md`).

---

## 1. Expert definition

**Piece activity.** The *activity* (or *scope*, *mobility*) of a piece is **how many squares it
controls** from where it stands. It is a property of a `(piece, position)` pair — the same knight
is worth far more on f3 (8 squares) than on g1 (3) or h3 (4, the rim). This is the oldest
positional heuristic in computer chess: Claude Shannon's 1950 evaluation function put a *mobility*
term beside material. Activity is **board-decidable** — no engine required — which is exactly why
it belongs in the fact-gate.

**Development.** A move **develops** a piece when it **raises that piece's activity** — brings it
from a low-scope square to a higher-scope one — *or* clears the way for a friendly piece to do so.
Crucially, a move can develop a piece **other than the one that moved**: `1.e4` does not "develop"
the e-pawn, it **opens the f1-bishop's diagonal**, raising the bishop's scope from 2 to 6. The
classical developing acts are: bringing the **minor pieces** (knights, bishops) off the back rank
toward the centre; **castling** (which safeguards the king *and* activates a rook); and clearing
the back rank so the **rooks connect** and can seize open files.

**One inclusive measure, but scoped valuation (measurement ≠ valuation).** Per James, the
*activity primitive* is computed **uniformly for every piece, including the king** — it is an
objective count. But whether *more activity is good* — i.e. whether to call it "development" — is
**not** uniform, and that judgment is where a naive "activity = good" rule would rebuild the very
bug we are killing, facing the other way:

| Piece | Measured by `piece_activity`? | Certified as `development`? |
|---|---|---|
| Knight, Bishop | yes | **yes** — control-count delta (the primary track) |
| Rook | yes | **yes, but via castling / connection**, *not* control-count (see §3; control-count is a dead signal for rooks) |
| Queen | yes | **no** — an early queen sortie raises mobility but is not "development" (already discouraged in the prompt) |
| King | yes | **no in the opening/middlegame** — extra king mobility there is *exposure*, not development; endgame king activation is already covered by the existing `king_active_endgame` tag |
| Pawn | (scope = its capture squares only) | **never of itself** — but a pawn move can certify `development` **of a minor it unblocks** (the `1.e4`/f1-bishop case) |

**Relation to the existing square-landing tags.** Greco already ships a scatter of good-square
detectors — `knight_on_fifth`, `bishop_centralized`, `rook_on_seventh`, `knight_centralized`, … —
which are *piecemeal* proxies for activity ("the knight reached a strong square"). `development`
is the **general** claim those are special cases of. They **co-fire** freely; when a specific
square tag also fires, the narrator prefers its concrete square language and uses `development`
for the "gains scope / develops" framing (§7).

---

## 2. The activity primitive

```python
from analyzer import PIECE_VALUES   # add to factgate's existing `from analyzer import (...)`

def piece_activity(board: chess.Board, square: int) -> int:
    """Greco's piece-activity unit: the number of squares the piece on `square`
    controls (its scope / influence). PURE, turn-independent geometry via
    board.attacks() — no engine, no network. 0 for an empty square.

    This is Shannon-style mobility. A minor leaping off the back rank shows a large
    jump (Ng1-f3: 3 -> 8; Bf1-c4: 6 -> 10); a quiet pawn nudge that frees a single
    square behind the pawn front does not (a8-rook after ...a6: 2 -> 3).

    NB: `board.attacks()` counts CONTROLLED squares — including squares occupied by
    friendly pieces (which the piece defends) and enemy pieces (which it attacks).
    That is deliberate: defence and attack are both activity. It is turn-independent,
    which is why it is measured the same way in `board_before` and `board_after`
    without ever flipping the side to move (the flip that a legal-move count would
    require is unsafe and was the source of the Nf3 mis-count — see §9)."""
    if board.piece_at(square) is None:
        return 0
    return len(board.attacks(square))


def _piece_hangs(board_after: chess.Board, square: int, color: bool) -> bool:
    """Correctly evaluated on the AFTER board, where the piece truly sits on `square`:
    is it lost outright? Attacked by an enemy piece worth LESS than it (loses the
    exchange), or attacked and wholly undefended (hangs). Used to refuse crediting a
    minor's 'development' when the move drops it (e.g. Bxf7+ into Kxf7). There is no
    self-defence artifact here: a piece cannot defend its own square."""
    piece = board_after.piece_at(square)
    if piece is None:
        return False
    val = PIECE_VALUES[piece.piece_type] or 100          # king: never lost -> max
    enemy = board_after.attackers(not color, square)
    if not enemy:
        return False
    cheapest = min(PIECE_VALUES[board_after.piece_type_at(s)] or 100 for s in enemy)
    if cheapest < val:
        return True
    return not board_after.attackers(color, square)
```

`piece_activity` is also exported as **evidence** for any piece the narrator discusses (§6), so
the model can say "the knight's reach jumps from three squares to eight" with a real number
instead of a vibe.

---

## 3. The `development` claim — VETO → CONFIRM

`is_developing_move(board_before, move, board_after, mover_color) -> Tuple[bool, Optional[dict]]`
— the standard `factgate` predicate signature, wired into `certified_claims` exactly like its
siblings. Reuses the already-shipped `is_connected_rooks` (factgate.py) and `file_structure`
(analyzer) as single sources of truth — never re-derives them.

**Development is a piece's FIRST journey off its home square.** The full-game shakeout (§4.1)
proved this is load-bearing: without it, the detector kept firing "development" on middlegame and
endgame piece-shuffles (a bishop improving on move 71, rooks incidentally re-lining-up on move
50). A coach never calls those "development" — that word means *bringing a piece out for the first
time in the opening*. So the minor tracks require the piece to **originate on** (2a) or **still sit
on** (2b) its home square, and a **phase gate** (`_still_developing`: at least one own minor still
home) confines the rook-connection track to the opening. Later piece improvements are *activity*,
not *development* — and are correctly left silent.

```python
_DEVELOP_MIN_GAIN = 2                       # OPEN(James): 2 vs 3 — see §11 (wide margin, non-fragile)
_DEVELOPABLE_MINORS = (chess.KNIGHT, chess.BISHOP)
_HOME_SQUARES = {
    (chess.WHITE, chess.KNIGHT): {chess.B1, chess.G1},
    (chess.WHITE, chess.BISHOP): {chess.C1, chess.F1},
    (chess.BLACK, chess.KNIGHT): {chess.B8, chess.G8},
    (chess.BLACK, chess.BISHOP): {chess.C8, chess.F8},
}

def _on_home(color, piece_type, square):
    return square in _HOME_SQUARES.get((color, piece_type), set())

def _still_developing(board, color):
    """Phase gate: the side is still developing while any of its minors sits on a home
    square. Once every minor has left home (or been traded), 'development' is over —
    later improvements are ACTIVITY, not development."""
    return any(_on_home(color, pt, s)
               for pt in _DEVELOPABLE_MINORS for s in board.pieces(pt, color))

def is_developing_move(board_before, move, board_after, mover_color):
    mover = board_before.piece_at(move.from_square)
    if mover is None or mover.color != mover_color:     # VETO: not the mover's piece
        return (False, None)
    color_name = "white" if mover_color == chess.WHITE else "black"

    # ── Track 1 — CASTLING is development by definition (unambiguous, happens once) ──
    if board_before.is_castling(move):
        return (True, {"tag": "development", "track": "castle", "color": color_name,
                       "desc": "castles — the king reaches safety and a rook is activated"})

    gains = []
    # ── Track 2a — a minor makes its FIRST move off its home square, and doesn't hang ─
    if (mover.piece_type in _DEVELOPABLE_MINORS
            and _on_home(mover_color, mover.piece_type, move.from_square)
            and not _piece_hangs(board_after, move.to_square, mover_color)):
        before = piece_activity(board_before, move.from_square)
        after  = piece_activity(board_after,  move.to_square)
        if after - before >= _DEVELOP_MIN_GAIN:
            gains.append({"kind": "moved", "piece": PIECE_NAMES[mover.piece_type],
                          "square": chess.square_name(move.to_square), "before": before, "after": after})

    # ── Track 2b — a line OPENED for a friendly minor STILL ON its home square (…e4 → Bf1) ─
    for pt in _DEVELOPABLE_MINORS:
        for sq in board_after.pieces(pt, mover_color):
            if sq == move.to_square or not _on_home(mover_color, pt, sq):
                continue                                # only an undeveloped, home minor
            b = board_before.piece_at(sq)
            if b is None or b.piece_type != pt or b.color != mover_color:
                continue                                # must be the SAME minor, sitting still
            before = piece_activity(board_before, sq)
            after  = piece_activity(board_after,  sq)
            if after - before >= _DEVELOP_MIN_GAIN:
                gains.append({"kind": "opened", "piece": PIECE_NAMES[pt],
                              "square": chess.square_name(sq), "before": before, "after": after})

    # ── Track 3 — ROOKS newly CONNECTED (often by the move clearing the LAST back-rank
    #    piece — a minor or the queen), but ONLY while development is still ongoing, so
    #    the endgame's incidental rook line-ups are not mislabelled 'development'. ─────
    cb = is_connected_rooks(board_before, mover_color)
    ca = is_connected_rooks(board_after,  mover_color)
    connected = (bool(ca and ca[0]) and not bool(cb and cb[0])
                 and _still_developing(board_after, mover_color))

    if gains or connected:
        ev = {"tag": "development", "track": "activity", "color": color_name, "gains": gains[:3]}
        if connected:
            ev["rooks_connected"] = True
        return (True, ev)
    return (False, None)
```

**Why these tracks and no others (v1).** Castling and rook-connection are the *unambiguous*
rook-development signals and exactly match James's account ("rooks are developed by castling and
by clearing the back rank so they connect"). The minor tracks capture everything else. A rook
reaching an open file is real *activity* but is already certified by `rook_lift` / the
`rook_on_*` tags, so it is intentionally left to them here (revisit: §11 O2). Queen and king are
excluded from the *claim* by simply never being in a track (their *activity* is still measured by
the primitive).

---

## 4. Positive examples (verified on python-chess 1.10.0)

| Position (before) | Move | Track | Verified activity | Certified |
|---|---|---|---|---|
| after `1.e4 e5 2.Nf3 Nc6` | `Bf1–c4` | 2a moved | bishop **6 → 10** (+4) | ✅ develops the bishop |
| after `1.e4 e5` | `Ng1–f3` | 2a moved | knight **3 → 8** (+5) | ✅ develops the knight |
| after `1.d4 d5` | `Nb1–c3` | 2a moved | knight **3 → 8** (+5) | ✅ develops the knight |
| starting position | `1.e4` | 2b opened | **f1-bishop 2 → 6** (+4) | ✅ develops the **bishop** (not the pawn) |
| Italian, king & rook home | `O-O` | 1 castle | — | ✅ castles (rook activated, king safe) |
| last back-rank minor leaves | (that move) | 3 connected | `is_connected_rooks` flips ⊥→⊤ | ✅ rooks now connected |

The margin is wide: every genuine developing move lands at **+4/+5**, far above the threshold, so
the exact value of `_DEVELOP_MIN_GAIN` (2 vs 3) changes none of these verdicts.

### 4.1 Full-game validation

The detector was replayed over two complete real games. It fires on **exactly** the opening
developing moves and then goes correctly silent — its last `development` firing coincides with the
end of each side's development:

- **JamesTortoise vs NinaTitova** (55 plies): fires on `1.Nf3`, `1…d6` (opens the c8-bishop),
  `2.d3` (opens the c1-bishop), `4…Nf6`, `5.Nbd2`, `7.Bb2`, `8…Nc6`, `9…Be6`, `10.O-O`, `10…O-O`
  — last firing at **move 10** (castling). Nothing fires thereafter.
- **Spassky vs Fischer, 1972 WC G13** (148 plies): fires through the opening (`1.e4` opens Bf1,
  `1…Nf6`, `3.d4` opens Bc1, `3…d6` opens Bc8, `4.Nf3`, `5.Bc4`, `6…Bg7`, `7.Nbd2`, both castlings,
  `13.Ne4` opens Bc1, `16.Bd2`) — last firing at **move 16**. The 130 plies of middlegame/endgame
  that follow — including `34.Bg3`, `71.Bc5`, and several endgame rook line-ups — produce **no**
  `development` claim, exactly as a coach would judge. *(An earlier build without the home-square
  gate wrongly fired on all of those; the gate is what fixed it.)*

---

## 5. Negative / edge cases (verified)

| Case | Position / move | Verified | Why refused |
|---|---|---|---|
| **The motivating bug** | `1.e4` then `1…a6`, a8-rook home | a8-rook **2 → 3** (+1) | Pawn never develops itself (track 2b measures the **rook**, not the pawn); the rook's +1 is below threshold, and a pawn nudge is not castling/connection. **`development` does NOT fire** — the "…a6 develops the a8-rook" claim is now impossible. |
| Early queen sortie | after `1.e4 e5`, `Qd1–h5` | queen mobility rises | Queen is not in any track — never "development." (Its activity is still *measured*; the narrator's "queen out early" guidance governs the valuation.) |
| Knight to the rim | after `1.e4 e5`, `Ng1–h3` | knight **3 → 4** (+1) | Below threshold — "knights on the rim are dim" falls out for free. |
| Rook shuffle on a clear rank | `Ra1–d1`, open board | rook **11 → 11** (0) | Control-count is flat for rooks; no connection change → refused. |
| King walk in the middlegame | `Kg1–h1` | — | King is not in any track — extra king mobility mid-game is exposure, not development. |
| Minor sacrificed onto a defended square | `Bxf7+` into `Kxf7` | bishop hangs on f7 | `_piece_hangs` is True on arrival → the scope gain is not credited as "development" (it is a sacrifice, classified elsewhere). |
| **Middlegame minor reshuffle** | an already-developed knight replays `…Nf3` from d2; `71.Bc5` in an endgame | scope may rise ≥2 | The minor does **not** originate on its home square → track 2a's home-square gate refuses it. This is *activity*, not *development*. (Verified: both real-game endgames go silent — §4.1.) |
| **Endgame rooks line up** | rooks incidentally connect on move 50 | connection flips ⊥→⊤ | The phase gate `_still_developing` is False (no minor left home) → the connection is not called "development." |

---

## 6. Evidence bundle

`certified_evidence()` surfaces a structured dict (never recomputed independently) so the narrator
anchors the claim to concrete pieces and numbers:

```python
development_evidence = {
    "tag": "development",
    "color": "white" | "black",
    "track": "castle" | "activity",
    # activity track only:
    "gains": [ {"kind": "moved" | "opened", "piece": "knight", "square": "f3",
                "before": 3, "after": 8} , … up to 3 ],
    "rooks_connected": True,          # present only when track 3 also fired
    "evidence_string": "The knight develops from g1 to f3, its reach jumping from 3 squares to 8.",
}
```

The `before`/`after` numbers come **only** from `piece_activity`; the connected flag comes **only**
from `is_connected_rooks` — the bundle cannot drift from the predicate.

---

## 7. Wiring (drafts — narrator wording is `PENDING_APPROVAL`)

**7.1 `certified_claims` registration** (factgate.py, beside the other `_safe(...)` calls):

```python
dev = _safe(lambda: is_developing_move(board_before, move, board_after, mover_color))
if dev and dev[0]:
    tags.add("development")
```

**7.2 `_FACTGATE_NARRATOR_RULES["development"]`** (narrator.py) — DRAFT, ship with
`# ⚠️ PENDING_APPROVAL` until James approves the exact wording:

> certifies that this move DEVELOPS a piece of the mover's — brings a **minor** from a low-scope
> square to a materially more active one, **opens a line** that activates a friendly minor that
> stayed put, **castles** (activating a rook and safeguarding the king), or clears the back rank so
> the **rooks connect**. Evidence gives `track` and, for the activity track, a `gains` list — each
> with the `piece`, its `square`, and its scope `before`/`after`. When certified: you MAY say the
> move "develops" / "activates" that specific piece, named; ground the activity track in the
> concrete scope gain ("the knight leaps to f3, its reach jumping from three squares to eight");
> for castling name both the king's safety and the rook's activation; for connected rooks say the
> back rank is cleared and the rooks now support each other. NEVER call a move "developing," a
> piece "developed," or a piece "activated" as a certified claim without this tag. Distinguish from
> the square-landing tags (`knight_on_fifth`, `bishop_centralized`, `rook_on_seventh`, …): when one
> also fires, prefer its concrete square language and use this tag for the "gains scope" framing.

**7.3 NON-NEGOTIABLE prohibition** (narrator.py "Accuracy and board truth" list) — DRAFT,
`PENDING_APPROVAL`, sibling to the doubled-pawn prohibition:

> - **"Develop" / "developed" / "activate" are certified claims — never assert them free-hand.**
>   A piece is "developed" only when the `development` fact certifies it (a minor gaining real
>   scope, a line opened for a minor, castling, or the rooks connecting). NEVER write that a move
>   "develops" or "activates" a piece, or that a piece "is developed," unless `development` fires
>   for it. The exact error this kills: calling a quiet pawn nudge that merely opens one square
>   behind the pawn front (…a6 "developing" the a8-rook) a developing move — that is not
>   development, and a piece shoved to a loose, exposed square (a rook on a6 with the b7-pawn still
>   home) is a **target**, not a developed piece; say *that* instead. "Toward the centre" / "into
>   play" is true only when the data backs a real activity gain; otherwise go VAGUE-BUT-TRUE.

**7.4 Fact packet** (`narrator._move_to_dict`): add the `development` evidence bundle to the
Tier-2/3 packet next to the other `certified` evidence, keyed `development`.

---

## 8. Tests to add (`tests/test_factgate.py` or new `tests/test_piece_activity.py`)

- `piece_activity`: Ng1 == 3, Nf3 == 8, Bf1(after e4) == 6, a8-rook == 2 then 3 after …a6.
- `development` **positive**: Bf1-c4, Ng1-f3, Nb1-c3, `1.e4` (credits the f1-bishop), `O-O`.
- `development` **negative (regression locks)**: **…a6 does NOT develop the a8-rook** (the
  headline test), early `Qh5`, `Ng1-h3` (rim), a rook shuffle on a clear rank, a middlegame king
  move, `Bxf7+` (hangs on arrival), and a **replayed middlegame `Nf3` from a non-home square**
  (the home-square gate — the fix the full-game replay forced).
- **Full-game invariant**: replaying a whole game, no `development` fires after both sides have
  finished developing (last firing ≈ the final minor out / castling — verified move 10 and 16 on
  the two sample games).
- `_piece_hangs`: true for a bishop on f7 attacked by the king and undefended; false for a
  defended/​unattacked square.

---

## 9. Known limitations

- **Control-count, not legal-move-count.** Activity is squares *controlled* (`board.attacks`),
  which (a) counts squares occupied by friendly pieces (defended) and enemy pieces (attacked), and
  (b) ignores pins and the side to move. This is a deliberate, robust choice: a strict legal-move
  count of a piece whose side is *not* to move needs an unsafe turn-flip, and that flip is exactly
  what mis-counted **Nf3 as +1** in the first bench build. Control-count is turn-independent and
  bug-free; the small semantic cost (a pinned piece's paper scope isn't reduced) is documented and
  minor. A pin-aware refinement is possible later (intersect with the pin ray).
- **Rooks are deliberately excluded from the mobility track.** Their control-count is nearly flat
  on a clear back rank (11→11), so it is not a usable development signal; rooks develop via
  castling/connection here, and via `rook_lift`/`rook_on_*` for open-file activity.
- **The home-square gate assumes standard chess.** "Development = first move off the home square"
  keys on the standard starting squares, so it (a) is not Chess960-aware, and (b) will not credit
  development when analysis *starts* from a mid-game FEN (a piece that was never seen on its home
  square this session). Both are acceptable for Greco (standard games, replayed from move 1); noted
  so the assumption is explicit.
- **Threshold is a heuristic**, not a truth. The wide observed margin (+4/+5 vs +1) makes it robust,
  but a contrived +2 non-developing shuffle could slip through; the evidence string always reports
  the actual squares so the narrator's prose stays honest.
- **No square-quality weighting (yet).** A central square and a rim square each count 1. The count
  *implicitly* rewards central posts (they see more squares), which is why Nh3 fails and Nf3 passes,
  but explicit piece-square weighting is a future refinement (§11 O5).
- **"How many moves to fully develop this piece"** (James's original question) is **not** in v1: it
  needs a per-piece *target* posting and a short plan, i.e. multi-ply reasoning. The primitive
  unlocks it (target_activity − current_activity) but it is a follow-up increment.
- **No opponent-activity / negative "exposure" claim.** v1 certifies development; the *anti*-
  development case (a loose, exposed piece) is handled by the prohibition (the narrator simply may
  not call it development) plus the eval. An explicit `misplaced_piece` predicate is a candidate
  follow-up (§11 O6).

---

## 10. Complexity

`piece_activity` is one `board.attacks()` (O(1)–O(27)). `is_developing_move` is: one castling
check; ≤1 hang check; the moved-minor delta (2 activity calls); the opened-line scan (2 activity
calls per friendly minor — at most 4 minors); and two `is_connected_rooks` calls (each O(1)–O(8)
along one line). No board copies, no hypothetical pushes, no engine. Comparable to the other
`certified_claims` predicates and dwarfed by the Stockfish eval already spent on the move.

---

## 11. OPEN decisions (James)

- **O1 — Threshold `_DEVELOP_MIN_GAIN`:** 2 or 3? Bench shows identical verdicts (wide margin).
  *Lean: 2.*
- **O2 — Rook track membership:** v1 = castling + newly-connected only (open-file rook activity
  left to `rook_lift`/`rook_on_*`). Add an explicit "rook to a newly open/half-open file" branch to
  `development` too, or keep it delegated? *Lean: keep delegated for v1.*
- **O3 — King:** measured by the primitive, excluded from `development`, endgame activation left to
  the existing `king_active_endgame` tag. Confirm this satisfies "include the king." *Lean: yes.*
- **O4 — Queen:** measured but never "developed." Confirm. *Lean: yes.*
- **O5 — Square-quality weighting:** ship the flat count now, add piece-square weighting later?
  *Lean: flat now (it already implicitly favours the centre), weight later if needed.*
- **O6 — Negative/exposure claim:** leave "loose/exposed piece" to the prohibition + eval for v1,
  spec a `misplaced_piece` predicate as a follow-up? *Lean: yes, follow-up.*
- **O7 — Exact narrator wording** (§7.2, §7.3): approve / edit. Ships `PENDING_APPROVAL` until then.
