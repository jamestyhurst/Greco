# Greco Architecture (brief)

Greco is a **pipeline**. The GUI and CLI are thin front-ends; all the analysis lives in
the modules below. The front-ends add **no analysis logic**.

## Pipeline
```
PGN source → engine evaluation → commentary tiers → AI narration → assembled report
```

| Module | Role |
|---|---|
| `importers.py` | Load a PGN (local file, Lichess URL/ID, or raw text). |
| `analyzer.py` | Run Stockfish on every position and compute ground-truth facts (material, forks, pins, escape squares, …). Returns a `GameAnalysis`. |
| `triage.py` | Assign each move a commentary tier (0–3) = how much to write about it. |
| `narrator.py` | One streaming Claude call. System prompt + per-voice addendum (+ optional commentary-style references); the user prompt is the engine ground-truth. |
| `outputs.py` | Assemble Markdown (header, move list, boards, eval graph) and a self-contained HTML report; report naming + output-location helpers. |
| `renderers.py` | Board SVGs and the evaluation graph (matplotlib). |
| `openings.py` | Identify the opening by exact move order (lichess CC0 database). |
| `commentary.py` | Load human-commentator transcripts as STYLE-ONLY references. |
| `tts.py` | Optional Windows text-to-speech. |
| `gui.py` | Tkinter desktop front-end. |
| `main.py` | Command-line front-end. |
| `version.py` | Single source of truth for the version number. |

## Core principle: data-back, never prompt-stuff
Every board fact the narrator states is **computed in `analyzer.py`** and handed to
Claude. The model supplies *language and psychology*, never raw board facts — that is
what keeps Greco accurate. Commentary references follow the same rule: they teach
*voice*, never facts.

## Environment notes
- Python 3.8 (32-bit); needs `PYTHONUTF8=1`.
- SSL uses the **Windows certificate store** (see `narrator.py`) because the default
  bundle is missing a root this network presents.
- Stockfish path and the Anthropic API key come from environment variables
  (`STOCKFISH_PATH`, `ANTHROPIC_API_KEY`).

## Launchers (current)
- `run_greco.bat` — console-visible launcher (reliable); the desktop shortcut uses this.
- `Greco.vbs` — no-console launcher (`pythonw`); optional, headed for replacement by a
  packaged `Greco.exe`.
