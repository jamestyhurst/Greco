# Greco Roadmap

Greco's direction: a friendly, standalone desktop app that turns any chess game into an
engine-backed, AI-narrated report. Versioning is [Semantic](https://semver.org/)
(`MAJOR.MINOR.PATCH`); see [../CHANGELOG.md](../CHANGELOG.md) for what has shipped.

## Where we are — v0.1.0
- Working Tkinter GUI over the full pipeline (importers → analyzer → triage → narrator
  → outputs).
- Branded icon (title bar + taskbar), informative report names, E:-drive output and
  PGN sync, commentary-learning, local git + E: backup.

## Backlog — priority queue (pull "work orders" from here)

Ordered by priority. Sizes are rough: **S** = a prompt tweak / small edit;
**M** = a feature + an exe rebuild; **L** = a big feature or refactor. Work top-down;
each item is committed when done, so a partial batch is still saved progress.

| # | Task | Size | Status |
|---|------|------|--------|
| 1 | Settings panel in the GUI (engine path / API key / model / output folder) | M | todo |
| 2 | `reference/` knowledge folder — openly-licensed openings/tactics/endgames, wired into the narrator (CC0 / CC-BY-SA only) | M | todo |
| 3 | Bulk-gather more commentary transcripts (Agadmator + SammyChess) | M | todo |
| 4 | Tighten the OTB classical-vs-rapid classifier (or use a curated source) | S | todo |
| 5 | Interactive PGN viewer embedded in the report HTML | L | todo |
| 6 | "Read aloud" in the report HTML (Web Speech API) | M | todo |
| 7 | Polish: one-click "Save as PDF", drag-and-drop a PGN, recent-games list | M | todo |
| 8 | Private GitHub repo for phone ↔ laptop (you authenticate) | S | todo |

**Recently shipped** (newest first): developer auto-`similar` hook + folder cap;
voice refinements (relationship framing, reader-level language, Daily voice, keepsake
mode, timid first moves, winning-a-piece ≠ a trade); standalone `Greco.exe`; game
finders (Chess.com + PGN Mentor); commentary-learning; report naming; versioning + docs.

## Toward v1.0 — "feels like real software"

1. **Standalone executable (`Greco.exe`)** — *next up.* Bundle Python + Greco with
   PyInstaller so Greco launches from a single double-click, with **no console window**
   and **no separate Python install**, the Greco icon embedded.
   - *Why not just polish the launcher script?* A `.bat` or `.vbs` only **starts** your
     existing Python install; the `.exe` **is** Greco. Once the `.exe` exists the
     launcher scripts are obsolete — so refining them is throwaway work toward this
     goal. (They also keep breaking in small ways, e.g. a stray space that crashed
     Python — exactly the fragility a real executable removes.)
   - *Do we strictly need an `.exe`?* The day-to-day experience you want (double-click →
     branded window → no console) can be delivered either by a fixed no-console launcher
     **or** by the `.exe`. The `.exe` is the more robust, self-contained, distributable
     endpoint, which is why it's the target.

2. **Settings panel** — edit the Stockfish path, API key, model, and output folder from
   inside the window (no environment variables required).

3. **Polish** — drag-and-drop a PGN, a recent-games list, one-click "Save as PDF".

## Feature wishlist (not yet scheduled — quick-prompt these when you have tokens)
- **Interactive PGN viewer inside the HTML report** — forward/back buttons that step
  through the recorded game on a board, the way chess.com / chessgames.com do.
  *Feasible:* embed a small self-contained JavaScript board + PGN viewer in the report
  HTML (the report stays a single shareable file).
- **"Read aloud" (TTS) inside the HTML report** — a play button that narrates the report
  in the browser. *Yes, this is possible:* the browser's built-in Web Speech API
  (`speechSynthesis`) speaks text with no extra files or server, so the report stays
  self-contained. (Greco already has desktop TTS via `tts.py`; this would be the
  in-browser version.)

## Later ideas
- Distribute Greco to other computers (the `.exe` makes this possible).
- A larger, curated commentary-reference library (bulk Agadmator + SammyChess).

## Working conventions
- **Versioning:** bump PATCH for fixes, MINOR for new features, MAJOR for big/breaking
  changes; record every change in `CHANGELOG.md`.
- **Backups:** local git is the source of truth; `E:\Chess\Greco` is a mirror. (A
  private GitHub remote is an option for off-site backup + phone/laptop collaboration.)
