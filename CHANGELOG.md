# Changelog

All notable changes to Greco are recorded here. This file follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Greco uses
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`). While Greco is
pre-1.0 (the `0.x` series), features and layout may still change between versions.

## [Unreleased]

## [0.16.0] — 2026-06-18

### Added
- **Lichess URL input (R-IN1)** — the analysis form now accepts a Lichess game URL or
  8-character game ID directly. `load_from_lichess()` fetches the PGN before passing it
  to the pipeline. Priority: Lichess URL > file upload > pasted text. Returns 400 with a
  human-readable error if the game cannot be fetched. Three new tests cover the happy
  path, error path, and priority over pasted PGN text.
- **Report-ready email notification (Phase 6 / F15)** — Greco can now email the user
  when an analysis job completes. Uses stdlib `smtplib` (no new dependencies). Silently
  skipped if `smtp_host` is not configured. Configured via `config.json` (or
  `GRECO_SMTP_*` env vars): `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`,
  `smtp_from`, `app_base_url`. Graceful no-op on delivery failure. 7 new tests.
- **Lichess account integration (Phase 6)** — users can save their Lichess username in
  their profile (`GET/POST /profile`). When set, the My Reports page shows their 10 most
  recent Lichess games with one-click "Analyze" buttons (POSTs directly to `/analyze`).
  `GET /profile/lichess-games` returns recent games as JSON (Lichess NDJSON API).
  `lichess_username` column added to the `users` table (Alembic migration 003).
  8 new tests. 263 tests pass total.

## [0.15.0] — 2026-06-18

### Added
- **CSV export and report delete for My Reports** (Phase 5 continuation).
  - `GET /my-reports/export` — downloads the user's report history as a CSV
    file (`report_id, game, date`).
  - `GET /admin/reports/export` — admin-only CSV of all reports across all
    users (`report_id, username, game, date`).
  - `POST /my-reports/{rid}/delete` — removes the ownership record for a report
    (file is kept). Users can only delete their own reports; admins can delete
    any report; non-owners get 403.
  - `web/db.py` — `delete_report_ownership()` function added.
  - `tests/test_dashboard.py` — 15 tests total (CSV export + delete coverage
    added); 248 tests pass total.

## [0.14.0] — 2026-06-18

### Added
- **Greco Online Phase 5 — My Reports + Admin dashboard** (target v0.14).
  Users can now view a history of their past analyses; admins can see all
  users and their report counts.
  - `GET /my-reports` — logged-in user's report history (newest first),
    showing game title and Open/Download links for each.
  - `GET /admin/users` — admin-only view: all registered users with email,
    role badge, and report count. Returns 403 for non-admin users.
  - `web/routers/dashboard.py` — new router for both routes.
  - `web/templates.py` — `_DASHBOARD` template (report list table with
    wine/ivory/gold theme and responsive navigation) and `_ADMIN_USERS`
    template (user table with role badges).
  - Alembic migration `002` — `ALTER TABLE report_ownership ADD COLUMN
    base TEXT` (nullable) so each record stores the game title (e.g.,
    "Fischer vs Spassky") without parsing HTML filenames.
  - `web/models.py` and `web/db.py` — `ReportOwnership.base` field;
    `create_report_ownership(rid, uid, base=None)` updated; new
    `get_user_reports()` and `get_all_reports()` functions.
  - `web/routers/analysis.py` — passes `base=result.base` to
    `create_report_ownership` when an analysis completes.
  - `web/main.py` — dashboard router registered.
  - Main form footer — "My Reports" link added.
  - `tests/test_dashboard.py` — 9 new tests (empty list, own reports only,
    isolation between users, admin/non-admin access control).
  - 239 tests pass total.

## [0.13.0] — 2026-06-18

### Added
- **Greco Online Phase 4 — SQLAlchemy ORM + Alembic migrations** (target v0.13).
  Replaces the raw sqlite3 DB layer with SQLAlchemy 2.0 and introduces Alembic
  for schema version control. The public API of web/db.py is unchanged — no
  callers needed updating.
  - `web/models.py` — declarative ORM models: `User` (id, username, email,
    password_hash, role, created_at) and `ReportOwnership` (report_id, user_id,
    created_at). `User.is_admin` property retained.
  - `web/db.py` rewritten with SQLAlchemy. Module-level `engine` and
    `SessionLocal` (monkeypatchable for tests). All CRUD functions use session
    context managers with `expire_on_commit=False` so returned objects are
    safe to use after session close. `init_db()` now calls
    `Base.metadata.create_all(engine)` (idempotent, like before).
  - `alembic/` directory with `env.py` (imports `_DB_URL` from `web.db`;
    derives the live DB path so Alembic always targets the same file as the
    app), `script.py.mako` template, and initial revision
    `001_create_users_and_report_ownership` (upgrade / downgrade both defined).
    `render_as_batch=True` enables ALTER TABLE support in SQLite.
  - `alembic.ini` at repo root. URL is a placeholder overridden in `env.py`;
    run `alembic upgrade head` (fresh install) or `alembic stamp head` (adopt
    existing Phase 3 schema) to sync the DB.
  - `requirements.txt` — `sqlalchemy>=2.0` and `alembic>=1.13` added.
  - `tests/test_auth.py` — `tmp_db` fixture upgraded to create a SQLAlchemy
    engine + sessionmaker pointing at a temp file, then monkeypatch
    `web.db.engine` and `web.db.SessionLocal`. 230 tests pass.

## [0.12.0] — 2026-06-18

### Added
- **Greco Online Phase 3 — accounts + roles** (target v0.12). Users can register, log in,
  and log out. The first registered user automatically becomes an admin; all others are
  regular users. Report submissions are tied to the submitting user so per-user scoping
  is ready for Phase 5. Public report links (GET /report/{id}) remain accessible without
  login per PRD requirement R-OUT11.
  - `web/db.py` — SQLite persistence layer (stdlib sqlite3, WAL mode, foreign keys ON).
    Two tables: `users` (id, username, email, password_hash, role, created_at) and
    `report_ownership` (report_id, user_id). All DB access is encapsulated here — no
    raw SQL elsewhere. The DB file (`greco_web.db`) is gitignored.
  - `web/auth.py` — password hashing via `bcrypt` directly (passlib dropped: its compat
    shim fails on Python 3.14 + bcrypt ≥ 4.x). Session helpers (set/clear) and two
    FastAPI dependencies: `get_current_user` (optional) and `require_login` (enforced,
    raises `NotAuthenticated` which the app handler converts to a login redirect).
  - `web/routers/auth.py` — `/auth/register`, `/auth/login`, `/auth/logout` routes.
    Registration validates: username regex (3–30 chars, alphanumeric+underscore), email
    format, min 8-char password, max 72-byte password (bcrypt hard limit), no duplicate
    username or email. Login accepts username *or* email.
  - `web/templates.py` — `_AUTH` Jinja2 template (register + login forms, wine/ivory/gold
    theme). `render_auth(mode, error, prefill)` function. Main form footer shows
    "Logged in as X" and a logout button.
  - `web/config.py` — `secret_key` field on `Settings`; loaded from `web_secret_key`
    in config.json or `GRECO_SECRET_KEY` env var; falls back to a process-stable
    ephemeral random key (with a startup warning).
  - `web/main.py` — `SessionMiddleware` added (signed cookie, tamper-evident);
    `init_db()` called in lifespan; `NotAuthenticated` app-level exception handler.
  - `requirements.txt` — `bcrypt>=4.0` added.
- **34 new auth tests** in `tests/test_auth.py`: password hashing round-trips, DB CRUD,
  first-user-admin logic, login by username or email, registration validation, logout,
  report ownership, unauthenticated redirect. All 230 tests pass.
- `tests/test_web.py` — `bypass_auth` autouse fixture so existing route tests remain
  focused on the pipeline/HTTP layer rather than auth.

## [0.11.0] — 2026-06-17

### Added
- **Knowledge corpus expansion — 9 new public-domain texts (2026-06-17).** Corpus grew from
  3 seed entries to 12 text sources (658 → 1223 FTS5 chunks). New books deposited, all
  pre-1931 US public domain:
  - `opening_theory` bucket: *Chess Generalship* (Young, 1910; Gutenberg #55278), *The Blue
    Book of Chess* (Staunton ed., 1889; Gutenberg #16377), *Chess History and Reminiscences*
    (Bird, 1893; Gutenberg #4902), *Chess Openings, Ancient and Modern* (Freeborough &
    Ranken, 1896; archive.org, OCR-cleaned), *Studies of Chess* (Philidor ed. Pratt, 1803;
    Gutenberg #78804), *The Exploits and Triumphs of Paul Morphy* (Edge, 1859; Gutenberg
    #34180), *Morphy's Games of Chess* (Löwenthal ed., 1860; archive.org, OCR-cleaned).
  - `chess_principles` bucket: *Chess Strategy* (Edward Lasker, 1915; Gutenberg #5614),
    *Chess and Checkers: The Way to Mastership* (Edward Lasker, 1918; Gutenberg #4913).
  - `SHOPPING_LIST.md` updated with acquisition dates; `MANIFEST.md` updated with legal basis
    for all new entries. Fishburne FEN-database books (#4542, #4656) excluded.
  - `tools/fetch_gutenberg.py` patched to use the OS truststore (`truststore.SSLContext`)
    so downloads work behind the corporate TLS proxy on this machine.
- **Greco Online Phase 2 — async jobs + status page** (#2, target v0.11). `POST /analyze`
  now returns a `_WAITING` page immediately and submits the pipeline as a FastAPI
  `BackgroundTask`. New module `web/jobs.py`: `JobStatus` enum (queued/running/done/failed),
  `Job` dataclass, thread-safe `JobRegistry`. New `GET /job/{id}` JSON endpoint for polling.
  New `GET /result/{id}` page renders the finished report or error. The waiting page polls
  every 2 s via `fetch()` and auto-navigates when done. Fully tested (11 new tests in
  `tests/test_web_jobs.py`; `tests/test_web.py` updated to test the async flow end-to-end).
- **"Read aloud" button in report HTML** (#9). A floating `♪ Read aloud` toggle button
  injected into every generated `.html` report via the Web Speech API (`speechSynthesis`).
  Reads narrative paragraphs one by one with gold-highlight tracking; stops on the second
  click or when the report ends. Hides itself gracefully when the API is absent (Safari iOS /
  older browsers). `markdown_to_html` gains an opt-out `read_aloud=False` parameter.
- **`strip_unverified_variations(md, game)`** in `outputs.py` — backlog #26. Promotes the
  existing confabulation detector from a `stderr` warning to an enforced strip: any
  parenthetical variation containing a move not in the engine lines is silently removed from
  the Markdown before the report is assembled. The surrounding prose is preserved. Called
  automatically in `assemble_report`; 8 new tests in `tests/test_strip_variations.py`.
- **`build_user_prompt` structured context inputs** — backlog #27. `audience_level`,
  `recipient`, `white_player`, `black_player` context blocks now thread from all three
  front-ends (GUI, web form, CLI) into the narrator prompt. Audience-level selector and
  recipient field added to both the Tkinter GUI and the FastAPI web form. Tested in
  `tests/test_narrator_context.py` and `tests/test_web.py`.
- **Computed decisive-moments block** in the narrator user prompt (#24). `_decisive_moments()`
  pre-computes the biggest eval swings and first decisive ply; the result is injected into
  every prompt to ground the closing summary. Tested in `tests/test_narrator_decisive.py`.
- **`verify_report` integration tests and `ship.py` gate** (#31).
  `tests/test_verify_integration.py` exercises the full `_move_to_dict → verify_report`
  pipeline with synthetic data (no Stockfish, no API key). `scripts/ship.py` step 2b
  optionally runs `tools/verify_report.py --no-llm` against saved fixtures when they exist.

### Changed
- **`VOICE_COMPANION` rewritten from "spectator-commentator" to "witness and gift".**
  The opening no longer frames the AI as a chess commentator performing for an audience.
  It now operates in one of two clearly defined orientations detected from the user's note:
  Chess Witness (a private conversation with a knowledgeable friend who was there) and
  Gift/Keepsake (a report addressed to a named recipient, scaled to their chess level and
  relational context). Each orientation has explicit instructions; the closing no longer
  mimics a commentator sign-off.
- **`VOICE_COACHING` gains the affirmative human-chess principle.** An explicit paragraph
  credits bluffing, demoralisation, and choosing positions that exploit a specific human
  opponent as valid coaching concepts — not just "mistakes with understandable psychology"
  but potentially correct decisions against a human. "Bluffing" and "demoralising the
  opponent" added to the cognitive pattern vocabulary.
- **`VOICE_COMMENTARY` gains spectator-event framing for personal games.** When the user
  was a participant, the narration now frames the game as a watched event — creating the
  social experience of having had an audience, even for a casual game.
- **`docs/ROADMAP.md`:** each phase now opens with a user story ("after this phase, a user
  can…") and a PRD-aligned version target (v0.11–v1.0). Essay Mode added as backlog #32.
- **`docs/ARCHITECTURE.md`:** governing documents table added at the top, pointing to
  the design concept, PRD, and retrospective as the design authority for this codebase.

## [0.10.0] — 2026-06-14

The **Output Fact-Gate** and the **Layer-2 self-test** — the structural answer to the
"LLM vs. engine" trust problem: compute what the engine can *prove*, let the narrator
assert only that, and then automatically *audit* the finished report against the facts.
The mirror image, on the output side, of the existing input validation gate.

### Added
- **`factgate.py` — the Output Fact-Gate predicate library.** Pure, engine-free code
  predicates (cheap necessary-condition veto → fuller confirm) that CERTIFY a claim from
  the board alone: `threatens_mate_in_one`, `is_rook_lift` (the doctrine's worked example —
  its from/to forward-rank check is what kills the "already on the file" hallucination),
  `is_outpost`, `is_passed_pawn`, `file_state`, plus `creates_fork` / `sets_up_royal_pin`
  thin-wrapping the analyzer's detectors so the allow-set can never drift from the fact
  packet. `certified_claims()` builds the per-ply **allow-set** of proven claim tags,
  serialised into the fact packet as `certified` (Tier 1+) and enforced by one scoped
  system-prompt rule: the narrator may assert a fork / pin / rook-lift / outpost /
  passed-pawn / mate-threat ONLY when its tag is certified for that move.
- **`factcheck.py` + `tools/verify_report.py` — the Layer-2 claim-verification self-test.**
  Deterministic, CI-safe contradiction detectors that bind a prose claim to one specific
  move and fire only on an unambiguous refutation (precision over recall, so a CI gate never
  cries wolf): `check_geometry` (the "moved onto the g-file" class), `check_piece_square`
  (vs the `pieces` field), `check_material` (vs the settled material), and `check_variations`
  (wrapping the existing variation validator). Plus an advisory, key-gated **LLM judge**
  (`run_llm_judge`) that shows a checker model the fact packet + the prose and asks "does the
  prose contradict these facts?". The CLI runs the deterministic gate (**exit 1** on a
  contradiction — a real CI / "let it cook" gate) and the judge only when an API key is
  present (advisory, never fails the build). It reads a saved analysis
  (`main.py --save-analysis`), so it needs no engine at check time.
- `main.py --save-analysis` now stamps the payload with `"schema": 1` for the verifier.
- Tests: `tests/test_factgate.py` and `tests/test_factcheck.py` — all hermetic (no engine/key).

### Notes
- Verified end-to-end: the self-test automatically caught the king-on-the-g-file bug
  (deterministic gate, exit 1), and the live LLM judge produced **no false positives** on a
  clean report. This is the first substantial build-out of the output-side trust gate; the
  predicate library and the deterministic detectors are deliberately a starter set
  (precision-first) to be grown over time.

## [0.9.0] — 2026-06-14

This release makes Greco able to *show* why a move is bad with real engine lines,
adds a tempo-coaching concept, gives every voice the players' real names and a
proper daily-game register, guarantees one verbatim master quote per report, adds
CI, and clears a batch of correctness bugs found in a deep multi-agent code sweep.

### Added
- **Engine-sourced variation lines (the ...Kg7 fix).** The analyzer now keeps the
  engine's principal variation *from the position after the move actually played*
  (`MoveAnalysis.refutation_line_san` — "what your move runs into") alongside a
  deepened best line (`best_line_san`, "what to play instead"), both rendered as
  move-numbered SAN on the real board (`pv_to_numbered_san`, with a hard legality
  guard). The narrator serialises these as a `variations` array (Tier 2/3) and a new
  system-prompt section forbids writing any move not present in that data — so Greco
  can finally write "*(if 25. g5 then …exg5 26. fxg5)*" with every move guaranteed to
  come from Stockfish, not the model. `outputs.find_unverified_variation_moves` is a
  code-level trust boundary that flags any confabulated move in a written line
  (verified end-to-end: a real coaching run produced zero unverified moves).
- **Coaching concept: the wasted / self-defeating tempo.** A threat that only induces
  a move the opponent already wanted (the ...Kg7 → ...Kxf6, then g5-anyway shape) — and
  the "helping your opponent develop" family — now have explicit prompt treatment,
  proven from the real engine lines rather than asserted.
- **Player names across every mode.** Names resolve from the PGN headers, then the
  filename (`importers.parse_players_from_filename` → `narrator.resolve_player_names`),
  and the prompt now prefers a real name over "White"/"Black" in all three voices. The
  psychology tier-boost for a named player's errors now fires from the headers, so GUI
  and web reports get it too (previously CLI-only).
- **Deterministic featured passage.** One best-matching public-domain passage is
  selected and formatted into a finished, attributed, verbatim quotation the narrator
  is told to include — so a master's words reliably reach the page instead of being
  smoothed into paraphrase.
- **GitHub Actions CI** (`.github/workflows/ci.yml`): runs the (engine/key-free)
  pytest suite on every push and pull request.
- **Test suite roughly doubled** (now ~86): analyzer geometry + numbered SAN, narrator
  serialization + prompt rules, importers, the outputs validator + HTML escaping +
  daily detection, the knowledge featured passage, and triage name-boost + turning
  points.

### Changed
- **Daily / correspondence games are now identified to the narrator.** `is_daily_game`
  (TimeControl `1/259200` or ≥86400s, with an Event/Site backstop) drives an explicit
  per-game "daily protocol" block, and `_humanize_time_control` finally renders the
  correspondence format instead of mislabeling it "classical" — so the existing daily
  voice (no time-pressure excuses) actually activates.
- Tier 1 moves now receive the `pieces` and `eval_before` ground-truth anchors
  (previously Tier 2+), removing a hallucination surface on short comments.
- `best_pv` deepened to 10 plies for multi-move tactics; the prompt forbids continuing
  a line past where the engine data stops.

### Fixed
- **Terminal-checkmate evaluation sign**: a game won by checkmate no longer reads as a
  loss for the winner; the engine is never queried on a game-over board.
- **`still_winning` clamp** no longer silently downgrades a genuine throw-away to a
  plain "good" move (it demotes by one severity step and only fully forgives small slips).
- **`detect_allowed_pawn_fork`** filters to legal pushes (no more "allows a fork" for a
  pinned pawn), a pinned piece no longer reports an undeliverable fork, and a
  royal-alignment pin is only claimed when the line is genuinely clear.
- **Diagram-set drift**: the narrator now computes diagram plies with the same
  `boards_at`/`periodic_every` as assembly, and `--boards-at off` truly renders none.
- **HTML safety**: untrusted PGN header values and the report `<title>` are escaped (a
  stored-XSS guard for the coming multi-user web).
- **Web** no longer returns a server traceback to the browser (logged server-side under
  an error id; full detail only when `GRECO_DEBUG` is set).
- A pasted PGN whose `[Site]` mentions chess.com loads as raw PGN instead of erroring.
- Game phase is computed on the resulting position; turning-point detection is seeded
  from the real starting evaluation.

## [0.8.1] — 2026-06-14

### Fixed
- **Reworked how reports choose headers and board diagrams — fixes the recurring
  out-of-order / clumped diagrams *and* the header-vs-bold duplication.** A `### N. SAN`
  header is now strictly a board-diagram anchor. The diagram set is decided in code
  (`select_diagram_plies`) and handed to the narrator (each move's `diagram` flag), so it
  writes exactly one header section per diagrammed move and marks every *other* move with a
  standard chess symbol (`!`, `?`, `?!`, `!!`, …) in bolded prose — never a header. Boards are
  placed at each move in game order (`_place_board`, which creates the header if the narrator
  didn't), and a final pass strips any stray header the model put on a non-diagrammed move.
  Validated on a fresh coaching analysis: 13 diagrams in strict ply order, every header anchors
  a board, no duplicates.
- **Geometry hallucinations.** Each move now carries its `from`/`to` squares and the prompt
  forbids inventing movement or pawn-attack geometry (a pawn attacks only the two diagonal
  squares — never along its own file). The earlier "king stepped onto the g-file" /
  "g-pawn threatens the g-file king" errors are gone.

### Changed
- **Coaching mode now bridges the human–engine gap explicitly.** On a move the engine
  disagreed with, it names the sound human idea behind the move actually played and explains
  the engine's choice in human-reachable terms, not just an evaluation delta.

## [0.8.0] — 2026-06-13

### Changed
- **Greco Web and the generated report now wear the same wine/ivory/gold manuscript theme as
  the desktop app.** `web/templates.py` (form / result / error pages) recoloured to a wine
  background, parchment cards, gold buttons + accents, an ivory king wordmark, and a manuscript
  serif. The report HTML from `outputs.markdown_to_html` — and therefore the emailed single-file
  export — now renders on a parchment page with wine/gold headings, a gold double-rule under the
  title, framed board diagrams, and a wine/gold replay viewer (previously a blue/grey scheme).
  Verified by regenerating a report: it carries the new palette and drops the old `#2b6cb0` blue.
  (Period web fonts, parchment textures and illuminated borders remain in the roadmap's
  "Aesthetic backlog" for later.)

### Added
- **Settable default PGN folder.** A new "Pick PGNs from:" field in the desktop Setup panel
  controls which folder the PGN file picker opens to, persisted in `config.json` (`pgn_dir`).
  It defaults to `Documents\Chess Game Files` (the C: source) instead of the E: library —
  resolved by `default_pgn_dir()` (Chess Game Files → `E:\Chess\PGNs` → home), so the picker
  lands somewhere sensible even before anything is configured. Browse to change it; it saves
  with your other settings on Analyze.

## [0.6.1] — 2026-06-13

### Fixed
- **Repeated move headers in reports.** On dramatic Tier-3 moves (the ones that also get a board
  diagram), the narrator sometimes emitted the same `### N. SAN` anchor header twice in a row, so
  the move name showed up two or three times around the board. `assemble_report` now collapses
  any immediately-repeated move header *before* boards are anchored. Also fixed a latent
  board-anchor bug: the anchor regex used `\b` after the SAN, which fails for moves ending in
  `+` / `#`, so checks like `17. Nf6+` never anchored to their header and their diagram was
  mis-placed — now uses `(?!\w)`. The narrator prompt also now says to write each move header at
  most once. New tests cover the collapse and the check-move anchor.

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
