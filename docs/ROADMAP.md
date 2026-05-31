# Greco Roadmap

Greco's direction: a friendly, standalone desktop app that turns any chess game into an
engine-backed, AI-narrated report. Versioning is [Semantic](https://semver.org/)
(`MAJOR.MINOR.PATCH`); see [../CHANGELOG.md](../CHANGELOG.md) for what has shipped.

## Where we are — v0.1.0
- Working Tkinter GUI over the full pipeline (importers → analyzer → triage → narrator
  → outputs).
- Branded icon (title bar + taskbar), informative report names, E:-drive output and
  PGN sync, commentary-learning, local git + E: backup.

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

## Later ideas
- Distribute Greco to other computers (the `.exe` makes this possible).
- A larger, curated commentary-reference library (bulk Agadmator + SammyChess).

## Working conventions
- **Versioning:** bump PATCH for fixes, MINOR for new features, MAJOR for big/breaking
  changes; record every change in `CHANGELOG.md`.
- **Backups:** local git is the source of truth; `E:\Chess\Greco` is a mirror. (A
  private GitHub remote is an option for off-site backup + phone/laptop collaboration.)
