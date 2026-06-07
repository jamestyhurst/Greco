# Greco

*A chess analyst that thinks like a player and writes like a critic.*

Named for Gioachino Greco (c. 1600–1634), the Italian master whose annotated games are considered the first chess literature.

Paste any PGN (or a Lichess URL) and Greco returns an analysis that combines:

- **Stockfish engine evaluation** — best moves, centipawn loss, mistake classification
- **Claude's narrative writing** — a flowing prose account of the game
- **Psychological inference** — why each player may have made or missed the best move
- **Board diagrams** — at every deep-commentary moment
- **Eval graph** — the engine's verdict plotted across the game

Every move in the game is acknowledged, but commentary depth varies according to a triage that weighs move quality, game phase, eval swings, and any player context you provide.

## What Greco is for

Greco supports three use cases, switched with `--use-case`:

| Mode | Voice | Best for |
|---|---|---|
| `companion` (default) | A chess commentator spectating *your* game and talking you through it as you watch — honest and knowledgeable, not a cheerleader | "Look at this cool game I played!" |
| `coaching` | Diagnostic; closes with "patterns to work on" | "Help me play better next time" |
| `commentary` | YouTube-style script (styled after Agadmator, Finegold, SammyChess & Chess Giant) with `[SCENE BREAK]` markers | "I'm writing a video about this game" |

If you don't pass `--use-case`, Greco asks at startup.

## Prerequisites

1. **Python 3.8+**
2. **Stockfish** chess engine binary
   - Download from [stockfishchess.org/download](https://stockfishchess.org/download/)
   - Unzip and remember the full path to `stockfish.exe`
3. **Anthropic API key** — create one at [console.anthropic.com](https://console.anthropic.com/)

## Setup

### 1. Install Python dependencies

> If your Windows username contains non-ASCII characters and pip throws a `UnicodeEncodeError`, set `PYTHONUTF8=1` and add `--trusted-host` flags for pypi.

```powershell
$env:PYTHONUTF8="1"
python -m pip install --user `
    --trusted-host pypi.org `
    --trusted-host pypi.python.org `
    --trusted-host files.pythonhosted.org `
    -r requirements.txt
```

### 2. Set environment variables

```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
[Environment]::SetEnvironmentVariable("STOCKFISH_PATH", "C:\path\to\stockfish.exe", "User")
# Open a new PowerShell window so the variables are loaded.
```

## Usage

### Desktop app (easiest — no command line)

Double-click **`run_greco.bat`** (or run `python gui.py`). A window opens where you:
1. Browse to a PGN file,
2. pick a report style (companion / coaching / commentary) and which side you played,
3. click **Analyze game**.

Greco runs Stockfish + Claude in the background (with a progress bar), then opens the finished HTML report in your browser. Reports are saved to `Documents\Greco Reports\<White> vs <Black>\`. The Stockfish path and API key auto-fill from your environment variables; you can also paste them into the window.

### Command line

### Quick start

```powershell
python main.py --pgn-file examples\morphy_opera.pgn --output examples\morphy.md
```

### A game you played

```powershell
python main.py --pgn-file my_game.pgn `
    --user-is white `
    --use-case companion `
    --user-note "I'm proud of the queen sacrifice at move 24" `
    --output reports\my_game.md
```

### A Lichess URL

```powershell
python main.py --pgn-url https://lichess.org/abc12def --output reports\lichess.md
```

### Coaching report on the same game

```powershell
python main.py --pgn-file my_game.pgn --user-is white --use-case coaching --output reports\my_game_coaching.md
```

### YouTube commentary script

```powershell
python main.py --pgn-file my_game.pgn --use-case commentary --user-note "Hook the audience with the queen sacrifice" --output scripts\my_game.md
```

### HTML report (single self-contained file)

```powershell
python main.py --pgn-file my_game.pgn --format html --output reports\my_game.md
# writes reports\my_game.md and reports\my_game.html
```

The `.html` embeds every board diagram and the eval graph directly in the file — open it in any browser and all images show with no links to click, and you can move or email the single file freely.

**Want a PDF?** Open the `.html` in your browser and press `Ctrl+P` → "Save as PDF". Every image is embedded, so they all travel into the PDF. (No extra software needed.)

### Hear it read aloud

```powershell
# Read aloud as soon as the report is ready:
python main.py --pgn-file my_game.pgn --speak

# Or save narration to an audio file (uncompressed WAV — ~50 MB for a full game):
python main.py --pgn-file my_game.pgn --audio reports\my_game.wav
```

Uses the Windows built-in speech engine — no install, no internet. (WAV files are large; audio is opt-in so it never bloats your drive unless you ask for it.)

## Accuracy: grounded in the real board

Greco feeds the model engine ground truth so it describes the *actual* position, not chess clichés:

- **Material tracking** — every move carries the running material balance and what it captured, so explanations are grounded in who's up or down.
- **Recapture precision** — "recapture" is used only when the opponent just captured on that square; a move that takes a *pushed* pawn is a plain capture.
- **Real threats** — forks and double attacks are detected from the board (e.g. "knight on e6 attacks the king on g7 and the queen on c7 — royal fork") rather than guessed.
- **No invented features** — files are only called open/half-open when they actually are.

### All useful flags

| Flag | Purpose |
|---|---|
| `--pgn-file PATH` | Local PGN file |
| `--pgn-url URL` | Lichess URL or 8-character game ID |
| `--pgn TEXT` | Raw PGN text on the command line |
| `--source X` | Auto-detect (path, URL, or PGN text) |
| `--user-is white\|black\|neither` | Tag yourself for second-person address (board is also flipped for Black) |
| `--use-case companion\|coaching\|commentary` | Voice (interactive prompt if omitted) |
| `--user-note "..."` | A personal note Greco will respond to directly |
| `--white-context "..."` | Free-form context about White |
| `--black-context "..."` | Free-form context about Black |
| `--boards-at off\|tier3\|tier2\|all` | Which moves get board diagrams (default tier3) |
| `--no-eval-graph` | Skip the eval-graph PNG |
| `--format md\|html\|both` | Output format (default both). The HTML is **self-contained** — boards and eval graph are embedded, no links to open |
| `--speak` | Read the narrative aloud when finished (Windows built-in voice) |
| `--audio PATH.wav` | Save the spoken narrative to a `.wav` file |
| `--voice-rate N` | Speech speed, -10 (slow) to 10 (fast); default 0 |
| `--depth N` | Engine search depth (default 18) |
| `--time-per-move S` | Seconds per position (overrides --depth) |
| `--multipv N` | Top-N candidate moves (default 3) |
| `--model MODEL` | Claude model (default `claude-sonnet-4-6`; try `claude-opus-4-7`) |
| `--max-tokens N` | Max output tokens (default 8000) |
| `--output PATH` | Where to write the report; creates a sibling `<stem>_assets/` folder for images |
| `--save-analysis PATH` | Dump the raw engine analysis as JSON |

## How it works (modules)

| File | Role |
|---|---|
| `importers.py` | Loads PGN from a file, Lichess URL, or raw text |
| `analyzer.py` | Drives Stockfish over every position; records best move, centipawn loss, alternatives, phase |
| `triage.py` | Assigns commentary tier 0–3 per move using classification, eval swings, forced-move detection, player context |
| `narrator.py` | Single streaming Claude call. Three voice modes (companion / coaching / commentary), each with a distinct system prompt |
| `renderers.py` | SVG boards (via python-chess) and PNG eval graphs (via matplotlib) |
| `outputs.py` | Assembles the final Markdown: header + move list + eval graph + narrative with board images inserted at the right move headers. Optional HTML wrap. |
| `main.py` | CLI orchestrator |

## Cost / time guidance

- Engine analysis of a 40-move game at `--time-per-move 0.8` and 4 CPU threads: ~45 seconds.
- One Claude Sonnet call: roughly 3–10K input tokens, 3–8K output tokens, ~$0.05–$0.15 per game.
- Opus (`--model claude-opus-4-7`) is noticeably more expensive but writes more vivid prose.

## Roadmap

- Chess.com per-game URL import (currently only Lichess; for Chess.com, download the PGN manually)
- Print-friendly stylesheet for the HTML output
- Batch mode for multiple PGNs in a folder
