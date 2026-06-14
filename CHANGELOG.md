# Changelog

All notable changes to Greco are recorded here. This file follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Greco uses
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`). While Greco is
pre-1.0 (the `0.x` series), features and layout may still change between versions.

## [Unreleased]

## [0.6.0] — 2026-06-13

### Added
- **Medieval "ivory manuscript" theme for the desktop GUI.** Recoloured to the app icon's
  palette — wine `#7A1C26` field, ivory `#F5EDD4` objects, gold `#C9A23A` accents (ttk
  `clam` base). A calligraphic *Greco* wordmark (Gabriola); large, clearly-legible ivory
  pawn/knight/rook markers on the Game / Options / Setup sections (rendered big via a
  label-widget so they no longer compress to a blob); a gold primary **Analyze** button; and
  the narration log set as sepia ink on parchment in a manuscript serif. The king logo is
  applied to the window (title bar + taskbar) from `__init__` as well as `main()`.
  Inspirations: Gioachino Greco's hand-written chess manuscripts and the carved-ivory pieces
  of the Age of Empires II intro. Further ideas are parked under "Aesthetic backlog" in
  `docs/ROADMAP.md`; Greco Web will be themed to match in a follow-up.
- **Initial automated test suite** (`tests/`, pytest) — 27 tests covering the triage rules
  engine, report naming + the shareable-HTML export, the FastAPI routes (pipeline mocked), the
  knowledge-corpus FTS5 retrieval + theme extraction, the version-bump automation, and a GUI
  import smoke test. Run with `venv\Scripts\python -m pytest`; dev dependency pinned in
  `requirements-dev.txt`. `scripts/ship.py` runs the suite as its pre-push gate, so nothing
  reaches GitHub unless the tests pass.

## [0.5.0] — 2026-06-13

### Added
- **FastAPI web backend (Greco Online, Phase 1).** New `web/` package
  (`web/main.py` app, `web/routers/analysis.py`, `web/config.py`, `web/pipeline.py`,
  `web/templates.py`) serving the browser version on FastAPI: `POST /analyze`
  (PGN file upload **or** pasted text), `GET /report/{id}`, `GET /health`, and
  auto-generated interactive API docs at `/docs`. Pydantic-typed settings, an async
  endpoint that offloads the blocking Stockfish + Claude pipeline to a threadpool,
  and a trust-boundary guard on report serving. Reuses the shared pipeline unchanged
  (no analysis logic in the web layer). Also exposes the shareable export as
  `GET /report/{id}/shareable`. Verified: `/health`, `/`, `/docs` and 404 handling
  all respond correctly.

### Changed
- **`run_greco_web.bat` now launches the FastAPI app** (`python -m web.main`, uvicorn)
  instead of the Flask server. `requirements.txt` swaps Flask for
  `fastapi` / `uvicorn[standard]` / `python-multipart` / `jinja2`.

### Removed
- **`webapp.py` (the interim Flask server)** — replaced by the `web/` FastAPI package.
  The browser experience and URL (`http://127.0.0.1:5000`) are unchanged; the desktop
  GUI, CLI and `Greco.exe` are unaffected.

## [0.4.0] — 2026-06-13

### Added
- **Shareable single-file HTML export.** A new **"Export for email (single file)"**
  button in the desktop GUI (enabled once a report is ready) bundles the finished
  report into one self-contained `… (shareable).html` — every board, the eval graph,
  the CSS and the interactive replay viewer inlined — so it can be attached to an
  email as a single file. It is an **export product**: written next to the report with
  a clear `(shareable)` name, and it never replaces the working `.html` / `.md` /
  `_assets` files. Implemented as `outputs.export_shareable_html()` in the shared core
  (so the web front-end can reuse it); it runs the existing idempotent asset inliner,
  which also repairs any report that wasn't already self-contained. Verified on a real
  report: 0 external references in the output, originals left intact.

## [0.3.1] — 2026-06-13

### Fixed
- **Desktop launchers were dead after the Python 3.14 upgrade** (`Greco.vbs`,
  `run_greco.bat`, `run_greco_web.bat`). All three invoked a bare `python` / `pythonw`,
  which — once Python 3.14 was installed in `C:\Program Files\Python314` and took first
  place on `PATH` — resolved to the **base** interpreter instead of the project `venv`.
  Greco's dependencies live only in the `venv` (`include-system-site-packages = false`),
  so `gui.py` died instantly on `import httpx`: the desktop icon (run via `pythonw`, no
  console) failed **silently**, and `run_greco.bat` flashed a `ModuleNotFoundError`. Each
  launcher now calls the venv interpreter explicitly (`venv\Scripts\python(w).exe`) and
  shows a clear error (console line / message box) instead of failing silently if the venv
  is ever missing. The desktop-icon wiring itself (`wscript.exe → Greco.vbs`, confirmed by
  `verify_icon.ps1`) was correct and unchanged — the bug was inside the launcher scripts.
  Verified end-to-end by launching the real icon path (`wscript Greco.vbs`) and confirming
  the GUI starts under `venv\Scripts\pythonw.exe`.

### Added
- **Greco Web now runs.** Flask is pinned in `requirements.txt` and installed in the venv, so
  `run_greco_web.bat` → <http://127.0.0.1:5000> serves the browser version of Greco (verified
  returning HTTP 200 locally). The desktop app and CLI are unchanged.
- **`config.example.json`** — a placeholder config template for fresh setups. The real
  `config.json` (which holds the Anthropic API key) remains gitignored and untracked.
- **`scripts/bump_version.py`** and Conventional-Commits versioning rules in `CLAUDE.md` —
  version numbers and tags are now computed from the Git commit history with no external tools.

## [0.3.0] — 2026-06-13

### Added
- **Coaching spectator-learner mode** (`narrator.VOICE_COACHING`, `narrator.build_user_prompt`).
  When `user_is == "neither"` (the user is studying a game they didn't play), Greco now
  applies an explicit instructional orientation: the winning player is treated as a positive
  role model to emulate, the losing player as a constructive case study in what to avoid,
  and every annotated moment closes with a portable lesson the reader can carry into their
  own games. The winner's inaccuracies are framed as "slower victories, not defeats"; the
  loser's good moves are credited genuinely. Wired via a new "Spectator-learner mode" block
  in `VOICE_COACHING` and a context line injected into the user prompt when `user_is == "neither"`.
  Validated by an A/B test (Fischer–Andersson, Siegen 1970, coaching voice, Sonnet 4.6)
  which confirmed 9 verbatim corpus 8-grams in the corpus-ON arm vs 0 in baseline — the
  coaching voice reliably produces genuine verbatim quotation from the retrieved corpus
  (improved over the previous commentary-voice test which showed 0/0 on Opus 4.8).

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
  - **A/B harness + finding:** `tools/knowledge_ab_test.py` (**developer tool only**
    — not part of the shipped product; see `tools/README.md`) generates a report
    with the corpus OFF vs ON for the same game (toggled by a new `with_knowledge`
    parameter on the narrator). Now produces three outputs: the two full-report .md
    files **plus `C_spotlight.md`** — a quick-read diff containing the verbatim
    corpus hits in context, attribution sentences from each arm side-by-side, and
    the closing section from each arm. The terminal also prints the exact 8-word
    phrases that matched verbatim, so the developer can see WHAT was quoted without
    opening the full reports. Testing (coaching voice, Sonnet 4.6, Fischer–Andersson)
    confirmed 9 verbatim 8-grams in the corpus-ON arm vs 0 baseline — the coaching
    voice reliably produces genuine quotation from the retrieved corpus (stronger
    than the prior commentary-voice test on Opus 4.8, which showed 0/0). Acquisition
    is now steered toward **deep opening theory and annotated games** (content the
    model lacks) over general-advice books. Reliable verbatim quoting will likely
    need a deterministic "featured passage" mechanism (noted for later).

- **Knowledge corpus — shorter quotes and stricter game-state matching** (`knowledge.py`,
  `narrator.py`). Two improvements to how Greco uses retrieved book passages, motivated by
  an A/B finding that the Capablanca "defend pawns" quote was applied to a position where
  pieces, not pawns, were being defended:

  - **Sentence-level extraction.** New `_extract_key_sentences()` scores every sentence in a
    ~380-word chunk by query-word overlap and returns the 1–2 highest-scoring sentences
    (≤ 55 words total). The narrator now receives a short, quotable excerpt — not the full
    chunk — as its primary quote target, so it can reproduce the master's words cleanly
    without having to cut a long block mid-thought.

  - **Theme tagging on `Passage`.** Two new fields: `matched_theme: str` (which retrieval
    theme found this passage, e.g. `"endgame"` or `"sacrifice"`) and
    `matched_phrases: List[str]` (the FTS phrases used). `retrieve()` now uses internally
    tagged queries so every returned passage knows why it was retrieved.

  - **Structured block format with POSITION VALIDATION.** `load_knowledge_for_game()` now
    formats each passage as three labelled sections: (1) **QUOTABLE EXCERPT** — the short
    extracted sentence(s), the only text the narrator may quote directly; (2) **POSITION
    VALIDATION** — an explicit gate naming the retrieval theme and instructing the narrator
    to skip the passage if its concrete claim doesn't match the specific position (e.g.
    "quote says 'defend pawns' but pieces are being defended — skip"); (3) **FULL PASSAGE**
    — background context, explicitly marked "do not quote from this section."

  - **Phase and tactic gates.** Passages retrieved on `"endgame"`, `"opening"`, or
    `"sacrifice"` themes carry an additional gate line restricting use to the appropriate
    game phase or move type — preventing an endgame principle from being cited on a
    middlegame move, for example.

  - **Narrator prompt updated.** `VOICE_COACHING` in `narrator.py` now contains a numbered
    three-step procedure: read the POSITION VALIDATION block; check that the passage's
    concrete claim matches the position; only then quote from the QUOTABLE EXCERPT. The
    previous vague "when one genuinely fits" language is replaced by an explicit gate.

- **Interactive PGN viewer in HTML reports** (`outputs.py`, `build_pgn_viewer`). Every
  self-contained HTML report now embeds a click-through replay board (backlog #8). It is
  fully self-contained — no CDN, no external files, works offline and by email:
  - The 12 piece graphics are borrowed from python-chess's own SVG set (via `<use>`
    references to a hidden `<defs>` block), so the replay board is visually identical to
    the inline static analysis boards.
  - The per-ply data array (FENs, SANs, classifications, eval) is injected as a JSON
    `<script>` block; the board renders client-side from this array with no chess logic
    needed in the browser.
  - Keyboard navigation: ← / → to step through moves, Home / End to jump to start/end.
  - Move list panel: each move is clickable; blunders, mistakes, inaccuracies, and
    brilliant moves are highlighted with colour-coded badges matching the inline boards.
  - Eval display and a Flip button on each position.
  - The viewer is inserted just before the first `<hr>` divider in the HTML body (after
    the eval graph, before the narrative), so the report reads: header → eval graph →
    replay board → annotated narrative.
  - `markdown_to_html()` gains `game` and `flipped` parameters; `main.py` passes them
    through so the viewer is always generated when building from the CLI.

- **Greco Online — Phase 1** (`webapp.py`, `run_greco_web.bat`). A local Flask web server
  puts the full Greco pipeline behind a browser UI (backlog #1). Key points:
  - Run `python webapp.py` (or double-click `run_greco_web.bat`), then open
    `http://127.0.0.1:5000` in any browser. No extra setup if the desktop app already works.
  - Upload a PGN file or paste PGN text, choose voice, speed, and user-side; click Analyze.
    The response is the same self-contained HTML report the desktop app produces.
  - Reads `config.json` (the same file the desktop settings panel writes) for Stockfish
    path, API key, model, and reports folder. Never writes to it.
  - Report links use integer ids (pure ASCII) to sidestep the non-ASCII reports-folder
    path that would break URL encoding. Links are ephemeral (cleared on restart); a
    persistent database is Phase 4.
  - Binds to `127.0.0.1` only — reachable only from this machine, keeping the API key
    server-side. Phase 7 replaces this localhost dev server with a real host.
  - Phase 1 runs the analysis synchronously (the page waits ~1-2 minutes). Phase 2 will
    replace that with an async job queue and live status page.
  - `gui.py`, `main.py`, and `Greco.exe` are completely untouched — the web front-end is
    a fourth thin layer over the shared pipeline.

- **Chrome launcher for HTML reports** (`gui.py`, `open_report_in_browser`). The "Open
  report" button now preferentially launches Chrome directly (passing the file path as an
  argument), which is robust on this machine's non-ASCII profile path. The helper
  `_find_chrome()` checks `PATH`, standard install folders, and the Windows App Paths
  registry. Falls back to `webbrowser.open()` if Chrome is not found.

- **House-voice style guide** (`commentary.py`, `commentary_refs/GRECO_STYLE.md`). An
  explicit, author-controlled style specification is now loaded into the narrator prompt
  via `load_style_guide()`, alongside the transcript references. Unlike the transcripts —
  from which the model must infer voice indirectly — the style guide is a direct
  instruction set (pacing, tone, structure, excitement beats). It is the most reliable and
  verifiable lever on Greco's voice. `GRECO_STYLE.md` blends the two reference voices:
  Agadmator (calm, long-form storytelling) and SammyChess (fast, punchy, purpose-driven).

- **New commentary references** (`commentary_refs/`):
  - `agadmator-kasparov-immortal/` — Agadmator's transcript of Kasparov vs Topalov
    (Wijk aan Zee 1999) + verified PGN. A full-game Agadmator voice sample.
  - `sammychess-fischer-italian/` — SammyChess transcript of a Fischer Italian-game video
    with 6 verified PGNs (Fischer vs Fine 1963; four Davis simul games, 1964; Fischer vs
    Bisguier, Poughkeepsie 1963). Complete PGN coverage verified move-by-move.
  - `WORKFLOW.md` — living documentation of the commentary-reference maintenance workflow:
    James's preferences (balance of voices, real transcripts only, complete PGN coverage
    per video before moving on) and the proven methodology for acquiring new references.

- **PLACEHOLDER transcript filter** (`commentary.py`). `_collect()` now skips transcript
  files whose first line is `PLACEHOLDER` (case-insensitive). Prevents unfilled scaffold
  stubs from reaching the narrator.

- **Unanchored boards woven into narrative** (`outputs.py`, `_insert_unanchored_boards`).
  Boards that the narrator gave no anchorable header to (periodic snapshots, or notable
  moves discussed only in prose) are now inserted directly into the narrative at their
  chronological ply position, instead of being collected into a block. The helper finds
  the correct insertion point by scanning for the next already-placed board with a higher
  ply number. Every board figure in the final HTML now reads in strict game order.
  *(Note: an intermediate form — "Additional positions" section before the narrative — was
  documented in [0.2.0] but the final implementation is this woven-in approach.)*

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

- **A/B harness — B-arm identification** (`tools/knowledge_ab_test.py`). The condition
  `"books" in name.lower()` incorrectly matched `A_no_books` before `B_with_books`,
  causing the console to report "0 verbatim corpus hits" even when the B arm had genuine
  matches. Fixed by switching to `name.startswith("B_")`.

- **A/B harness — move header labels for normalized text** (`tools/knowledge_ab_test.py`,
  `_nearest_move_header`). Attribution sentences passed to the function had been
  lowercased and punctuation-stripped, so the exact-string search into the original
  Markdown always failed, returning `"(position unknown)"`. Fixed with a three-tier
  fallback: exact → case-insensitive → first-three-words match.

### Infrastructure
- **A/B harness — ply-matched attribution table** (`tools/knowledge_ab_test.py`). The
  previous side-by-side attribution comparison showed arm A's quote at move 43 and arm B's
  at move 24 — not an equivalent comparison. `_ply_matched_attr_rows()` now groups
  attribution sentences from all arms by their nearest move header, producing a single
  table where each row is one unique move and absent attributions show as "—", making
  non-equivalence visible at a glance. `C_spotlight.md` uses this table.

- **A/B harness — JSON ply packet** (`tools/knowledge_ab_test.py`, `_generate_ply_packet`).
  `main()` now writes `D_ply_packet.json` alongside the arm reports: a structured record of
  every significant move (tier ≥ 1) with ply number, notation, phase, classification,
  `cp_loss`, and `eval_after_cp`. Provides a stable positional reference for anchoring
  cross-arm comparisons by move without re-parsing the Markdown.

- **A/B compare widget template** (`tools/ab_compare_widget.html`). A reusable HTML
  template for `show_widget` calls in future A/B comparison sessions. Contains the full
  CSS and layout with `{{PLACEHOLDER}}` slots for game title, model line, metric counts,
  ply-matched attribution rows, and a closing pattern pair. Eliminates rebuilding the
  widget from scratch each session.

- **Roadmap — four knowledge-corpus optional ideas** (`docs/ROADMAP.md`). Added to
  `## Later ideas`: deterministic featured passage (two variants: `meta.json` pre-vetting
  and `outputs.py` mechanical insertion); move-level retrieval (per-move FTS queries);
  negative filtering (drop filler passages whose theme is absent from detected features);
  and auditable chain-of-thought validation (narrator emits a bracketed `[Verified: …]`
  line per quote for A/B auditability).

- **Style A/B test harness** (`tools/style_ab_test.py`). Developer tool for measuring
  how much the house style guide and commentary transcripts actually change Greco's voice.
  Analyzes one game with Stockfish once, then calls Claude with style sources toggled
  (none / style guide only / transcripts only / full). Prints a voice-marker frequency
  table and writes one .md arm file per combination. Reads engine path and API key from
  `config.json`, exactly like the GUI.

- **`verify_icon.ps1`** — idempotent script that checks (and repairs if needed) the
  desktop shortcut so it always points to the live source (`Greco.vbs → pythonw gui.py`)
  rather than a frozen `.exe`. Uses the `IShellLinkW` COM shell API rather than
  `WScript.Shell`, because `WScript.Shell` mangles the target path under a non-ASCII
  username. `build_exe.bat` now calls this script after every build to re-assert the
  live-source shortcut, and the script clarifies that the `.exe` at
  `C:\Users\Public\Greco` is for sharing only — the desktop icon is independent of it.

- **Developer guidance documents** (root of repo, untracked; loaded by `CLAUDE.md`):
  `Greco_Development_Guide_and_StayPlus_Readiness.md` (StayPlus readiness map and
  Greco-as-curriculum bridge), `secrets-and-api-key-protection.md` (standing secrets
  protocol), and `software-skills-you-can-learn-from-greco.md` (concept-by-concept
  learning map). `tools/README.md` documents the developer tools in `tools/`.

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
  dumped into an "Other key positions" section at the bottom of the document, after
  boards from the late middlegame and endgame. The final implementation (shipped in
  [0.3.0] as `_insert_unanchored_boards`) weaves these boards directly into the narrative
  body at their correct ply position, so every board figure in the document reads in
  strict game order. See [0.3.0] for the full description.
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
