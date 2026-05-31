# Changelog

All notable changes to Greco are recorded here. This file follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Greco uses
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`). While Greco is
pre-1.0 (the `0.x` series), features and layout may still change between versions.

## [Unreleased]

### Planned
- **Standalone `Greco.exe`** (via PyInstaller): one double-click to run, no console
  window, no separate Python install required, Greco icon embedded. This replaces the
  `.bat` / `.vbs` launcher scripts.
- **Settings panel** in the GUI: edit the Stockfish path, API key, model, and output
  folder from inside the window (no environment variables needed).
- Bulk-gather more commentary references (Agadmator + SammyChess).

## [0.1.0] — 2026-05-31

First versioned release. Greco turns a chess game (PGN) into an engine-backed,
AI-narrated, self-contained HTML report.

### Added
- **Desktop GUI** (`gui.py`): choose a PGN and a voice (companion / coaching /
  commentary), click Analyze; it runs in the background with a progress bar, streams
  the narrative live, then opens the HTML report. Includes **Open report** and
  **Open report folder** buttons.
- **Greco app icon** — a medieval king on a wine-and-gold medallion — in the window
  title bar and the Windows taskbar (replacing the default Python/Tk icon).
- **Informative report filenames**: `White vs. Black, <TimeCategory>, <Year>`.
- **Output to the E: drive** (`E:\Chess\Reports`), falling back to `Documents` when
  E: is not connected.
- **Automatic PGN sync**: PGNs in `Documents\Chess Game Files` are copied to
  `E:\Chess\PGNs` at logon and on each launch.
- **Commentary-learning** (`commentary.py` + `commentary_refs/`): Greco can study real
  commentator transcripts for *voice only* (never board facts). Seeded with Agadmator
  (Morphy's Opera Game) and SammyChess (Kasparov's Scotch, 5 games, ordered PGNs). A
  helper fetches YouTube transcripts (`commentary_refs/_tools/fetch_transcript.py`).
- **Version control + backup**: the project is now a local git repository, mirrored to
  `E:\Chess\Greco`.

### Notes
- `gui.py` was recovered from the Claude Code session transcript after an out-of-disk
  write truncated it to 0 bytes; git was introduced so a loss like that can't recur
  silently.

### Known limitations
- Launch goes through `run_greco.bat`, which shows a console window. The no-console
  launcher and the standalone `.exe` are tracked under **[Unreleased]**.
