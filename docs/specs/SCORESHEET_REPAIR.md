# Spec: Scoresheet Auto-Repair (replay-verified move disambiguation)

**Status:** Approved for build (James, 2026-07-19 session) — fallback policy still open, see §6.
**Link to vision:** closes the canon's acknowledged handwritten/OTB input gap
(design concept: inputs assume a digital PGN exists); extends the 2026-07-19
mud-proof ingestion layer (`parse_pgn_game`). Model: the tool that still fires
after being dropped in the mud.

## 1. Problem

`parse_pgn_game` now *refuses loudly* when movetext contains an ambiguous SAN
(`Rc8`, both rooks legal) or an illegal token (transcription typo). Refusal
beats the old silent truncation, but the mud-proof ideal is to **process the
game anyway** when the intended move can be determined — the way a human
replaying the scoresheet on a real board would.

## 2. Key insight

The rest of the scoresheet is evidence. At a failure point, each candidate
interpretation forks a hypothetical game; **replay the remaining recorded
moves against each fork**. Usually exactly one candidate lets the entire
remainder replay legally — that is what the writer meant. This is
constraint-satisfaction, not guessing, and it is decisive precisely on real
scoresheets (a wrong fork desynchronizes the position and the remainder
collapses within a few plies).

## 3. Algorithm (bounded, deterministic)

```
repair(tokens, board, depth):
  walk tokens, applying moves, until token T fails to parse
  candidates(T):
    ambiguous SAN  -> every legal move matching T's piece + destination
    illegal SAN    -> every legal move whose SAN is within edit-distance 1
                      of T, plus T with common pen-slips applied
                      (file/rank off-by-one, missing 'x', N<->B confusion)
  for each candidate c (max 8):
    replay remaining tokens after applying c
    on a second failure, recurse — but total repairs per game <= 3
  keep candidates whose full remainder replays legally
```

- Exactly **one** surviving candidate → apply it, record a repair note, continue.
- Zero or multiple survivors → fall back (§6).
- Hard caps: ≤3 repair points per game, ≤8 candidates per point, depth-first
  with early abort. A cap hit is a fallback, never a hang.

## 4. Disclosure (data-back honesty)

Every applied repair is recorded as a structured fact:
`{move_no, side, written, resolved, kind: ambiguous|typo, survivors: 1}`.

- Repairs are listed in the report's header block (mechanical text, e.g.
  "Transcription repairs: 24...Rc8 read as Rac8 — verified by replaying the
  remaining 12 moves").
- ⚠️ Any wording the NARRATOR uses about repairs is narrator-rule territory:
  **PENDING_APPROVAL tag required until James approves the phrasing.** The
  mechanical header line above is output-layer text, not narration.

## 5. Where it lives

- New module `scoresheet_repair.py` (pure: tokens + board in, moves +
  repair-facts out; no engine, no API).
- Called from `parse_pgn_game` in `analyzer.py` ONLY when `game.errors` is
  non-empty — the clean path stays untouched.
- The raw token walk uses `sanitize_pgn`-cleaned text (already guaranteed).

## 6. OPEN QUESTION — fallback policy (James to decide)

When repair fails (zero or multiple full-replay survivors):

- **Option A (provisional default): stop with a repair-shop error** — extend
  today's `parse_pgn_game` message with the candidate list and how far each
  survived. Cleanest data, tool refuses until the human fixes the file.
- **Option B: analyze the verifiable prefix + a prominent banner** — report
  covers moves 1..N with an explicit "scoresheet unreadable from move N+1;
  candidates were X/Y" banner. More mud-tolerant; risks a fragment being
  mistaken for the whole game if the banner is ever lost in rendering.

Build Option A first (it is a strict extension of the existing error path);
implement B behind it once James picks.

## 7. Acceptance criteria (all must pass)

1. The Rafay-game scenario: a PGN with bare `Rc8` at move 24 where both rooks
   are legal but only one survives replay → auto-resolved, repair fact
   recorded, full 36-move analysis, no error raised.
2. Genuinely undecidable ambiguity (both survive to the end) → fallback path,
   candidates named.
3. Single-typo scoresheet (e.g. `Nf3` written for `Nf6`) → repaired when the
   remainder verifies; unrepairable garbage → fallback with the edit-distance
   candidates listed.
4. ≥12 new regression tests in `tests/test_scoresheet_repair.py`, including
   the cap limits (4th repair point → fallback) and a nested two-repair game.
5. Zero behavior change for clean PGNs (full suite stays green).
6. No narrator-visible wording without a PENDING_APPROVAL tag.

## 8. Build phases (one autonomous session)

- **P1** token walker + candidate generator, unit-tested against fixed FENs.
- **P2** replay verifier + caps; the pure module complete.
- **P3** `parse_pgn_game` integration + repair-fact plumbing to the report
  header; regression suite; full-suite green.
- **P4** run a real hand-mutilated PGN end-to-end (copy of the Rafay game
  with the move-24 disambiguation removed) and verify the report discloses
  the repair. Done = this output verified, per Law 1.
