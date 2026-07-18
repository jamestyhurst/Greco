# Scoresheet Import — photo of a handwritten scoresheet → verified PGN

> **Status:** spec ready, not yet built (roadmap #37). Sonnet-executable: phased,
> concrete acceptance criteria, graceful fallback at every phase.
>
> **Vision link (Doctrine Law 3):** the Design Concept's core input is "a completed
> chess game," but James's OTB games only exist on paper. Today the path is tedious
> typing or generic OCR chat sessions — both produce broken records. Two real
> casualties, 2026-07-18, both from hand transcription of 2026-06-18 OTB games:
>
> * `Rafay vs James 2026-06-18.pgn` — `24...Rc8` ambiguous (both rooks legal);
>   invalid PGN until repaired by hand.
> * `Andrija vs James 2026-06-18.pgn` — `7...Nd7` ambiguous **and** `33...Rd7`
>   flat-out illegal; the file still cannot be replayed and has no report.

## Core principle

**The vision model proposes; python-chess disposes** (data-back, never prompt-stuff).
A move enters the PGN only if it is legal from the reconstructed position. Every
repair is logged and recorded in an `[Annotator]` tag; nothing is silently guessed.
The key insight is *constraint propagation*: at any position only ~30 moves are
legal, so chess's own rules resolve most OCR ambiguity — including by look-ahead
(`7...Nd7` in the Andrija game is provably the b8-knight, because `21. Bxf6`
later captures a piece that must still be on f6).

## Shape

Developer CLI first: `tools/scoresheet_import.py --image <photo> [--library]`.
GUI/web upload is Phase 4, later, with James's UX approval. Model: Sonnet-class
vision via the existing config (`config.json` key); one call per sheet. No engine.

## Phases

**Phase 0 — harness.** CLI takes image path(s) (jpg/png; multi-page = multiple
images in order), loads config, sends a transcription prompt, saves the raw model
output to a sidecar `.transcription.json`. *Accept:* runs end-to-end on any photo;
raw output saved even when later phases fail.

**Phase 1 — structured transcription.** Model returns JSON: optional headers
(players, date, event, result if legible) + an ordered list of half-move tokens
with `{text, confidence, alternatives[]}`, `"?"` for illegible cells. *Accept:*
schema-validated JSON from a clear test sheet; illegible cells marked, not invented.

**Phase 2 — legality-gated reconstruction (the heart; pure python-chess, no API).**
Replay from the start position, consuming tokens:
1. Exactly one legal reading → accept.
2. Ambiguous (the `Rc8` case) → branch on each candidate and look ahead through the
   remaining transcribed moves; prune branches that make a later move illegal (the
   `Bxf6` proof). A branch that survives uniquely → accept, log the inference. Still
   ambiguous at game end → pick the first candidate, record the ambiguity in the
   `[Annotator]` tag.
3. Illegal (the `Rd7` case) → generate candidate repairs from the legal-move set,
   ranked by OCR-confusability (K↔R, a↔d, 3↔8, B↔E, x dropped, etc.) and the
   model's `alternatives`; accept a repair only if it is the *unique* candidate
   surviving look-ahead. Otherwise mark the ply **UNRESOLVED** — emit the valid
   prefix as a partial PGN plus a human-readable repair report, never a broken file.
*Accept (unit tests, no API needed):* resolves the real Rafay ambiguity; proves
Andrija `7...Nbd7` by look-ahead; refuses to guess Andrija `33...Rd7` and reports
it UNRESOLVED with its candidate list.

**Phase 3 — output.** Write the PGN (headers + `[Annotator]` audit trail), print
the repair report, and with `--library` deposit into `Documents\Chess Game Files`
root (never into `Games with Reports` — auto-filing happens at report time). The
final file must pass the same full-replay validation the library sweep uses.
*Accept (Law 1):* a real scoresheet photo from James becomes a validated PGN and
then a Greco report he judges faithful.

**Phase 4 — GUI/web upload (later; needs James).** Not autonomous.

## Fallbacks

Vision call fails or returns unparseable output → keep the sidecar transcription
and exit nonzero with instructions; reconstruction dead-ends → partial PGN + repair
report. In no case is an invalid PGN written to the library.

## Non-goals (v1)

Descriptive notation, multi-game sheets, handwriting fine-tuning, live capture.
