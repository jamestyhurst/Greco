<div align="center">

<img src="assets/greco.png" alt="Greco" width="140" />

# Greco

**Chess analysis that reads like a coach wrote it — and plays back in your browser.**

Paste a game. Get a flowing, illustrated annotation: engine-accurate commentary, an
interactive replay board, and occasional quotes from the chess masters whose wisdom still
holds 100 years on.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/Engine-Stockfish-769656)](https://stockfishchess.org/)
[![Narration](https://img.shields.io/badge/Narration-Claude-D97757)](https://www.anthropic.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.0-orange.svg)](CHANGELOG.md)

</div>

---

Greco pairs **Stockfish** with **Claude** to turn a raw PGN into something worth reading — a
narrative with board diagrams, an eval graph, an interactive replay board, and prose that
explains **why** a move worked or failed: the tactics, the psychology, the exact moment a game
turned.

It is named for **Gioachino Greco** (c. 1600–1634), the Italian master whose annotated games
are considered the first chess literature. The project holds that tradition: engine accuracy is
the foundation, but the point is to *understand* the game.

## See it in action

These are real reports Greco produced. The Markdown versions render right here on GitHub —
**click to read a full annotated game:**

| Game | What it shows |
|---|---|
| 🏆 [**Spassky vs. Fischer**, 1972 World Championship](sample-reports/Boris%20Spassky%20vs.%20Robert%20James%20Fischer%2C%201972/Boris%20Spassky%20vs.%20Robert%20James%20Fischer%2C%201972.md) | One of the most famous endgames ever played, narrated end to end |
| ♟️ [**Volokitin vs. Ivanchuk**, Aerosvit 2006](sample-reports/Andrei%20Volokitin%20vs%20Vassily%20Ivanchuk/report.md) | A razor-sharp Alekhine Defense |
| 👤 [**redwood1978 vs. JamesTortoise**, Daily 2025](sample-reports/redwood1978%20vs.%20JamesTortoise%2C%20Daily%2C%202025/redwood1978%20vs.%20JamesTortoise%2C%20Daily%2C%202025.md) | A real amateur game in *companion* voice |

Each report ships a **self-contained `.html`** alongside the Markdown — every board diagram and
the interactive replay board are embedded inline; no server, no CDN, works offline or by email.

<div align="center">

*Every report includes an engine-evaluation graph of the full game:*

<img src="sample-reports/Andrei%20Volokitin%20vs%20Vassily%20Ivanchuk/report_assets/eval.png" alt="Evaluation graph" width="640" />

</div>

## What Greco produces

### Interactive replay board *(v0.3.0)*
Every HTML report embeds a complete click-through game viewer:
- Step through moves with ← / → keys, or click any move in the scrollable move list
- Blunders, mistakes, inaccuracies, and brilliant moves are colour-coded throughout
- Engine evaluation and a flip-board button on every position
- Fully self-contained — python-chess SVG piece graphics reused via `<use>` references,
  zero JavaScript dependencies, no CDN, works after the network is gone

### Three voices
| Mode | Voice | Best for |
|---|---|---|
| `companion` *(default)* | An honest, knowledgeable spectator of *your* game — not a cheerleader | *"Look at this game I played"* |
| `coaching` | Diagnostic; closes with concrete "patterns to work on" | *"Help me play better next time"* |
| `commentary` | YouTube-style script with `[SCENE BREAK]` markers | *"I'm making a video about this game"* |

Coaching mode also has a **spectator-learner orientation**: when you are studying a game you
didn't play, the winner becomes a positive role model to emulate and every annotated move closes
with a portable lesson you can carry into your own games.

### Classical chess literature *(v0.3.0)*
Greco maintains a curated library of **public-domain chess books** (Capablanca's *Chess
Fundamentals* is the first; more to follow) and retrieves the most relevant passages at analysis
time via **SQLite FTS5** full-text search. The retrieval matches the game's engine-detected
themes (a sacrifice, an endgame, a specific opening). When a retrieved passage genuinely fits the
position being annotated, the narrator quotes it with attribution — *"As Capablanca writes, …"* —
embedding timeless principle alongside engine evaluation.

This is **retrieval-augmented generation (RAG)**: the quote is exact because it was looked up,
not generated. Retrieval is verified by A/B test (Fischer–Andersson, Siegen 1970, coaching voice):
9 verbatim 8-grams in the corpus-ON arm vs 0 in baseline. The library is designed so new books
can be deposited with no code change — drop a cleaned text file in the right folder and Greco
picks it up on the next run.

### Accurate by construction
The model never guesses about the board. `analyzer.py` computes the ground truth and hands it to
Claude as structured data, so the prose describes the *actual* position — not chess clichés:

- **Real tactics** — forks, pins, double attacks detected from board geometry, not hallucinated
- **Material tracking** — running balance and what each move captured
- **Recapture precision** — "recapture" only when the opponent just captured on that square
- **No phantom features** — files called open only when they truly are
- **Psychology grounded in eval** — "blunder under time pressure" is flagged when the position confirms it

> **Core principle — *data-back, never prompt-stuff*:** the engine supplies the facts; Claude
> supplies language and psychology. That division is what keeps Greco honest.
> See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## How it works

```
PGN source → importers → analyzer (Stockfish) → triage → narrator (Claude) → outputs
                                                              ↑
                                                   knowledge.py  ← SQLite FTS5 corpus
                                                   commentary.py ← voice style guide + refs
```

The analysis pipeline is shared by every front-end. Two surfaces exist today — a Tkinter desktop
GUI and a FastAPI localhost web server — and both call the exact same pipeline with no divergence.

## Running Greco

### Desktop app
```powershell
python gui.py
```
Browse to a PGN, pick a voice and speed, click Analyze. The settings panel persists your
Stockfish path, API key, and model choice to `config.json` — no environment variables required
after the first run.

### Browser (Greco Online — Phase 1)
```powershell
python -m web.main          # or double-click run_greco_web.bat
# then open http://127.0.0.1:5000   (interactive API docs at /docs)
```
The full pipeline runs behind a local FastAPI server: upload a PGN in the browser, get the same
self-contained HTML report. The server reads the same `config.json` the desktop GUI writes, binds
to `127.0.0.1` only, and keeps the API key server-side. See *Greco Online* below.

### Command line
```powershell
set PYTHONUTF8=1   # needed on Windows when the username path contains non-ASCII characters
python main.py --pgn-file "sample-games/Spassky vs Fischer - 1972 WC Game 13 (Alekhine Defense).pgn" --use-case coaching
```

📖 Every flag, Lichess import, model selector, and output option is documented in
[`docs/USAGE.md`](docs/USAGE.md).

**Requirements:** Python 3.11+, free [Stockfish](https://stockfishchess.org/download/) binary,
[Anthropic API key](https://console.anthropic.com/). A 40-move game costs roughly **$0.05–$0.15**
and takes under a minute.

## Greco Online — where this is going

Greco is being developed toward a **hosted, multi-user web application** — open it in any
browser (including a phone), no install. The seven-phase roadmap:

| Phase | What ships | Status |
|---|---|---|
| **1 — Localhost web** | Full pipeline via browser on your own machine (`web/main.py`, FastAPI + `/docs`) | ✅ done |
| **2 — Async jobs** | Queued → Analyzing → Done status page; no more page-wait | todo |
| **3 — Accounts + roles** | Login; per-user game history; admin sees all | todo |
| **4 — Database** | SQLite → PostgreSQL; persistent, addressable reports | todo |
| **5 — Phone UI + export** | Responsive layout; accuracy-trend dashboard; CSV/PDF | todo |
| **6 — Auto-import + notify** | Connect Chess.com/Lichess → auto-analyze new games → email you | todo |
| **7 — Deploy** | Live on Render/Railway with a real domain and HTTPS | todo |

Each phase ships a Greco that is useful on its own. The PGN viewer (formerly backlog #8) shipped
in v0.3.0.

## Tech stack

| | |
|---|---|
| **Language** | Python 3.11+ |
| **Engine** | Stockfish (via `python-chess` UCI) |
| **Narration** | Claude API (streaming; claude-sonnet-4-6 / claude-opus-4-8 / claude-fable-5) |
| **Corpus RAG** | SQLite FTS5 full-text search over public-domain chess texts |
| **Replay board** | Self-contained JavaScript, python-chess SVG pieces, no external deps |
| **Rendering** | `python-chess` SVG boards · `matplotlib` eval graphs |
| **Front-ends** | Tkinter desktop GUI · FastAPI localhost web server · argparse CLI |
| **Output** | Markdown · self-contained HTML (boards, graph, and replay viewer all embedded) |

## Repository layout

```
greco/
├── importers.py · analyzer.py · triage.py     # analysis pipeline (data-back)
├── narrator.py · outputs.py                   # narration and report assembly
├── knowledge.py + knowledge/                  # corpus RAG layer (FTS5 + texts)
├── commentary.py + commentary_refs/           # voice style guide + reference transcripts
├── gui.py · web/ · main.py                    # front-ends (desktop / web / CLI)
├── docs/       ARCHITECTURE · USAGE · ROADMAP · product-vs-in-house
├── tools/      developer tools (A/B harness, Gutenberg fetcher, style tester)
├── sample-games/    example PGNs — famous games + real amateur play
└── sample-reports/  full Greco-generated reports — Markdown + self-contained HTML
```

## License

[MIT](LICENSE) © James Tyhurst. Stockfish and the Anthropic API are each governed by their own
licenses/terms.
