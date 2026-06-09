<div align="center">

<img src="assets/greco.png" alt="Greco" width="140" />

# Greco

**A chess analyst that thinks like a player and writes like a critic.**

Paste a game. Get a human-readable story of how it was won and lost — engine-accurate, move by move.

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/Engine-Stockfish-769656)](https://stockfishchess.org/)
[![Narration](https://img.shields.io/badge/Narration-Claude-D97757)](https://www.anthropic.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/version-0.1.0-orange.svg)](CHANGELOG.md)

</div>

---

Greco pairs the **Stockfish** engine with **Claude** to turn a raw PGN into a flowing,
illustrated game annotation — the kind a strong coach might write, not a wall of
centipawn numbers. It is named for **Gioachino Greco** (c. 1600–1634), the Italian
master whose annotated games are considered the first chess literature.

Every move is engine-evaluated; commentary depth is then *triaged* so the writing lingers
on the turning points and moves briskly through the quiet ones. The result is a report
with board diagrams, an evaluation graph, and prose that explains **why** — including the
human psychology behind a missed or brilliant move.

## See it in action

These are real reports Greco produced. The Markdown versions render right here on GitHub —
**click to read a full annotated game:**

| Game | What it shows |
|---|---|
| 🏆 [**Spassky vs. Fischer**, 1972 World Championship](sample-reports/Boris%20Spassky%20vs.%20Robert%20James%20Fischer%2C%201972/Boris%20Spassky%20vs.%20Robert%20James%20Fischer%2C%201972.md) | One of the most famous endgames ever played, narrated end to end |
| ♟️ [**Volokitin vs. Ivanchuk**, Aerosvit 2006](sample-reports/Andrei%20Volokitin%20vs%20Vassily%20Ivanchuk/report.md) | A razor-sharp Alekhine Defense |
| 👤 [**redwood1978 vs. JamesTortoise**, Daily 2025](sample-reports/redwood1978%20vs.%20JamesTortoise%2C%20Daily%2C%202025/redwood1978%20vs.%20JamesTortoise%2C%20Daily%2C%202025.md) | A real amateur game in *companion* voice |

Each report also ships a **self-contained `.html`** (every diagram embedded — open in any
browser, or print to PDF) alongside the Markdown. Browse them all in
[`sample-reports/`](sample-reports/).

<div align="center">

*Every report includes an engine-evaluation graph of the whole game:*

<img src="sample-reports/Andrei%20Volokitin%20vs%20Vassily%20Ivanchuk/report_assets/eval.png" alt="Evaluation graph" width="640" />

</div>

## Three ways to read a game

Greco writes in three voices, switched with `--use-case`:

| Mode | Voice | Best for |
|---|---|---|
| `companion` *(default)* | A commentator spectating *your* game — honest and knowledgeable, not a cheerleader | *"Look at this game I played!"* |
| `coaching` | Diagnostic; closes with concrete "patterns to work on" | *"Help me play better next time"* |
| `commentary` | YouTube-style script with `[SCENE BREAK]` markers | *"I'm writing a video about this game"* |

## Accurate by construction

The model never guesses about the board. Greco computes the ground truth in
`analyzer.py` and hands it to Claude, so the writing describes the *actual* position —
not chess clichés:

- **Material tracking** — every move carries the running material balance and what it captured.
- **Real tactics** — forks, pins, and double attacks are detected from the board, not invented.
- **Recapture precision** — "recapture" only when the opponent just captured on that square.
- **No phantom features** — files are called open/half-open only when they truly are.

> **Core principle — *data-back, never prompt-stuff*:** the engine supplies the facts;
> the model supplies language and psychology. That division is what keeps Greco honest.
> See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## How it works

```
PGN source → Stockfish evaluation → commentary triage → Claude narration → assembled report
  importers        analyzer             triage            narrator         outputs + renderers
```

A thin GUI (`gui.py`) and CLI (`main.py`) are the only front-ends — **all** analysis lives
in the pipeline modules, so both share identical behavior. Full module map in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start

```powershell
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Point Greco at Stockfish and your Anthropic key (never hardcoded)
[Environment]::SetEnvironmentVariable("STOCKFISH_PATH",   "C:\path\to\stockfish.exe", "User")
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...",               "User")

# 3a. Desktop app — browse to a PGN, pick a style, click Analyze
python gui.py

# 3b. ...or the command line
python main.py --pgn-file "sample-games/Spassky vs Fischer - 1972 WC Game 13 (Alekhine Defense).pgn" --use-case commentary
```

You'll need **Python 3.8+**, the free [Stockfish](https://stockfishchess.org/download/)
binary, and an [Anthropic API key](https://console.anthropic.com/). A 40-move game costs
roughly **$0.05–$0.15** and under a minute.

📖 **Full usage** — every flag, Lichess import, audio narration, HTML/PDF output — is in
[`docs/USAGE.md`](docs/USAGE.md).

## Tech stack

| | |
|---|---|
| **Language** | Python 3.8+ |
| **Engine** | Stockfish (via `python-chess` UCI) |
| **Narration** | Claude (Anthropic API, streaming) |
| **Rendering** | `python-chess` SVG boards · `matplotlib` eval graphs |
| **Front-ends** | Tkinter desktop GUI · argparse CLI |
| **Output** | Markdown · self-contained HTML · optional Windows TTS audio |

## Repository layout

```
greco/
├── importers · analyzer · triage · narrator · outputs · renderers   # the pipeline
├── openings · commentary · tts                                       # supporting modules
├── gui.py · main.py                                                  # front-ends
├── docs/            ARCHITECTURE · USAGE · ROADMAP · product-vs-in-house
├── sample-games/    example PGNs (famous games + real amateur play)
├── sample-reports/  full reports Greco generated, Markdown + HTML
└── examples/        smaller worked examples
```

## Roadmap

Settings panel, interactive PGN viewer in the HTML report, and polish (drag-and-drop,
recent-games list, PDF export). Tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md).

Content curation — discovering new PGNs and gathering commentary transcripts — is
**outsourced to a Claude coworker agent** that deposits files into the directories Greco
already watches. Greco stays purely reactive; the agent handles the logistics. See the
[Coworker agent section](docs/ROADMAP.md#coworker-agent--outsourced-content-curation) in
the roadmap.

## License

[MIT](LICENSE) © James Tyhurst. Stockfish and the Anthropic API are each governed by their
own licenses/terms.
