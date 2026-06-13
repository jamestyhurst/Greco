# Changelog

All notable changes to Greco are recorded here. This file follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Greco uses
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`). While Greco is
pre-1.0 (the `0.x` series), features and layout may still change between versions.

## [Unreleased]

### Added
- **Knowledge corpus — a retrieval layer over public-domain chess books**
  (`knowledge.py` + `knowledge/`). Greco can now draw on classical chess
  literature (Capablanca, Lasker, …) when narrating: at analysis time it detects
  the game's themes from the engine ground truth (the opening, plus any
  sacrifice / fork / pin / doubled-pawns / open-file / endgame the analyzer
  flagged), searches the corpus for matching passages, and hands the **verbatim
  text** to the narrator to quote or paraphrase with attribution. This is
  retrieval-augmented generation (RAG) — the quote is exact because it is looked
  up, not generated — and it extends Greco's *data-back, never prompt-stuff*
  principle: the books supply timeless *principles*, never facts about the game
  (the engine remains the sole source of board truth).
  - Search uses **SQLite FTS5** full-text indexing (with a LIKE-based fallback if
    FTS5 is unavailable); the index is generated from the text files and rebuilt
    automatically whenever the corpus changes on disk. It is gitignored.
  - Books are deposited as cleaned UTF-8 `text.txt` + `meta.json` under
    `knowledge/opening_theory/` or `knowledge/chess_principles/`; the deposit
    protocol and the legal boundary (US 95-year rule; translations carry their
    own copyright) are documented in `knowledge/README.md` and the legal registry
    `knowledge/MANIFEST.md`. Content acquisition can be outsourced (e.g. to
    Cowork) without any code change — drop files in, Greco picks them up.
  - Ships with two small Greco-authored **CC0 seed texts** so retrieval works
    before the real books are added; they are safe to delete once the masters are
    in. The narrator integration is fully fail-safe: with an empty corpus or any
    error, the report is produced exactly as before.
  - `python knowledge.py --status` lists what is indexed (verify a deposit);
    `python knowledge.py --query "<terms>"` previews matching passages.
  - **Index quality:** non-prose chunks (game scores in descriptive notation,
    diagram markers) are filtered out at index time, so retrieval returns only
    quotable teaching prose; an `INDEX_VERSION` forces a rebuild when this logic
    changes even if the texts are untouched.
  - **First real book + acquisition tooling:** Capablanca's *Chess Fundamentals*
    (1921, Gutenberg #33870) is now in the corpus as a worked example.
    `tools/fetch_gutenberg.py` downloads a Gutenberg book, strips its
    header/footer/license, and deposits it cleaned (refuses anything dated after
    1930). `knowledge/SHOPPING_LIST.md` is a prioritised, updateable acquisition
    wishlist (sources + Gutenberg IDs) for an agent to work from.
  - **A/B harness + finding:** `tools/knowledge_ab_test.py` generates a report
    with the corpus OFF vs ON for the same game (toggled by a new `with_knowledge`
    parameter on the narrator). Testing on Fischer–Andersson (Siegen 1970) showed
    the wiring works but a frontier model already knows general chess principles
    and rarely quotes an injected general-principles corpus — so acquisition is
    now steered toward **deep opening theory and annotated games** (content the
    model lacks) over general-advice books. Reliable verbatim quoting will likely
    need a deterministic "featured passage" mechanism (noted for later).

### Fixed
- **TLS/SSL connectivity on the Python 3.14 venv** (`narrator._make_http_client`).
  After the interpreter upgrade, all Anthropic API calls failed with
  `CERTIFICATE_VERIFY_FAILED: Basic Constraints of CA cert not marked critical`:
  this network re-signs HTTPS through a middlebox whose CA the OS trusts but whose
  Basic Constraints OpenSSL 3.x (Python 3.11+) rejects, while the old Python 3.8
  OpenSSL tolerated it. Fixed by verifying via the OS-native trust store
  (`truststore` → Windows SChannel), with the previous certifi+Windows-store
  context kept as a fallback. Added `truststore` to `requirements.txt`. This
  unblocks every Greco API call on the upgraded interpreter, not just the A/B test.

### Infrastructure
- **Python 3.14.6 venv** — Greco's virtual environment rebuilt on Python 3.14.6 (64-bit,
  `C:\Program Files\Python314\`), replacing the prior Python 3.8.5 32-bit environment.
  All dependencies installed cleanly; `PYTHONUTF8=1` required when running pip from a
  PowerShell session due to the non-ASCII username path. No code changes needed;
  the runtime upgrade resolves the Python 3.8 end-of-life concern and aligns with the
  64-bit / 3.11+ target called out in guide §5.4.

## [0.2.0] — 2026-06-12

### Added
- **Standalone `Greco.exe`** (PyInstaller, `--windowed` = no console window, Greco
  icon embedded; all dependencies bundled). Built and deployed with `build_exe.bat`
  to **`C:\Users\Public\Greco`** — an **ASCII path is required**: the non-ASCII
  username in `C:\Users\<unicode>\…` makes the frozen Tcl/Tk fail to find its own
  files, so the app must run from a path with no non-ASCII characters. The desktop
  shortcut now launches this `.exe`.
- **Crisper app icon**: each icon size is rendered individually (king fills the frame)
  so it stays clear at 16–32 px instead of looking fuzzy.
- **Game finders** (`tools/find_games.py`): download PGNs from Chess.com (your own
  games) or PGN Mentor (master/OTB games), filtered by time class / result / opening.
- **No Stockfish console window** pops up during analysis anymore.
- **Reports save to `Documents\Greco Reports` (C:) by default again** (override with
  the `GRECO_REPORTS_DIR` environment variable).
- **Voice refinements**: honour relationship/addressing instructions from the note
  (e.g. write a report *to* your dad, calling him "you" and you "your son" instead of
  "White"/"Black"); scale the LANGUAGE to the reader (plain descriptions over raw
  coordinates for beginners); a Daily / correspondence voice; and Companion mode can
  be a warm keepsake rather than a Stockfish data-dump when the note asks for it.
- **Settings panel** (`gui.py`): the Setup section now persists all configuration to
  `config.json` in the project folder — Stockfish path, Anthropic API key, Claude
  model, and reports output folder. Values are loaded on startup (falling back to
  environment variables) and saved automatically before each analysis run. No
  environment variables required after the first run.
- **Model selector**: choose between `claude-sonnet-4-6`, `claude-opus-4-8`, and
  `claude-fable-5` from a dropdown in the Setup section; the selection is passed
  directly to `generate_narrative` and shown in the status bar during the run.
- **Reports folder picker**: choose any output directory from a Browse dialog instead
  of relying on the `GRECO_REPORTS_DIR` environment variable.

### Fixed
- **Board SVGs now appear in strict chronological order** in HTML reports. Previously,
  periodic snapshot boards (every 6 plies) that had no matching narrative header were
  dumped into an "Other key positions" section at the *bottom* of the document, after
  boards from the late middlegame and endgame. They are now placed in an "Additional
  positions" section *before* the narrative body, so all board images appear in
  ascending ply order. The list is also explicitly sorted by ply as a safety net.
- **Board filenames now include the ply number** as a zero-padded prefix
  (`ply027_m14w_Rd1.svg`), so files in the assets folder sort naturally in the same
  order as the game moves.
- **`data-ply` attribute** added to every `<figure class="board">` element in HTML
  output, encoding the half-move index. This makes the ordering machine-verifiable
  and will support the planned interactive PGN viewer.

### Planned
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
