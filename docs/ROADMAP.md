# Greco Roadmap

Greco turns any chess game into an engine-backed, AI-narrated report. **Its direction is
now Greco Online** — a hosted, multi-user web app you open in any browser (including your
phone), with no install. Today Greco runs as a standalone Windows desktop app; that's the
foundation we're building out from. Versioning is [Semantic](https://semver.org/)
(`MAJOR.MINOR.PATCH`); see [../CHANGELOG.md](../CHANGELOG.md) for what has shipped.

## Where we are — v0.29.0

> See [../CHANGELOG.md](../CHANGELOG.md) for the per-version detail. **All seven Greco
> Online phases through Phase 6 are complete.** The web layer is a full multi-user FastAPI
> app with accounts, roles, a SQLite database with Alembic migrations, a phone-friendly
> dashboard with CSV export, Lichess account integration (recent-games panel, one-click
> analysis), and report-ready email notifications. Phase 7 (deploy) is the remaining
> milestone on the path to v1.0. Earlier highlights: engine-sourced variation lines the
> narrator may only quote (never invent), a wasted-tempo coaching concept, player names
> usable in every voice, a real daily/correspondence register, a guaranteed verbatim
> "featured passage", GitHub Actions CI, a large correctness sweep, and — the structural
> answer to the "LLM vs. engine" trust problem — the **Output Fact-Gate** (`factgate.py`)
> plus the **Layer-2 claim-verification self-test** (`factcheck.py` / `tools/verify_report.py`).
> v0.20.0–v0.29.0 completed the full **18-predicate Tier-A fact-gate library**: every
> certifiable chess claim (pin, skewer, discovered attack, backward pawn, infiltration,
> fianchetto, outpost evidence, zugzwang, and more) now has a deterministic detector,
> an evidence bundle, narrator guidance, and L2 acceptance tests (156 tests total).
> The voice prompts were also rewritten to align with the design concept (chess witness
> framing in Companion, human-chess principle in Coaching, spectator-event framing in
> Commentary) and the web form gained structured context fields (audience level, recipient,
> per-player context).

### Baseline (v0.3.0)
- Working Tkinter GUI over the full pipeline (importers → analyzer → triage → narrator
  → outputs).
- Branded icon (title bar + taskbar), informative report names, E:-drive output and
  PGN sync, commentary-learning, local git + E: backup.
- **Settings panel**: Stockfish path, API key, model selector, reports folder — all
  persisted to `config.json`; no environment variables needed after first run.
- **SVG chronological ordering**: board images woven into the narrative in strict ply
  order; filenames prefixed with ply number; `data-ply` attributes on all figures.
- **Interactive PGN viewer**: every HTML report embeds a self-contained click-through
  replay board (keyboard navigation, move list with badges, eval display, flip button).
- **Greco Online Phase 1**: `web/` (FastAPI) + `run_greco_web.bat` — full pipeline via browser
  on localhost (interactive API docs at `/docs`); same output as the desktop app.
- **Knowledge corpus (RAG)**: public-domain chess books (Capablanca) retrieved at
  analysis time; narrator quotes with attribution; verbatim proven in A/B tests.
- **Standalone `Greco.exe`**: double-click launch, no console, no separate Python
  install, icon embedded. (This was the old v1.0 target — it shipped, and now serves as
  the local launcher while the focus shifts online; see *Superseded vision* below.)

## The vision — Greco Online  ← primary direction

**This vision takes precedence over the earlier "installable `.exe`" product vision.** The
`.exe` already exists and remains a fine way to run Greco on this machine, but shipping a
desktop binary to other people is no longer the headline goal. The headline goal is a
Greco you reach from any browser: log in, upload (or auto-import) a game, get your report
— from a laptop or a phone, no install, shareable by a link instead of a file. This is the
only path that makes Greco multi-user and phone-accessible, and it turns Greco from a
script-on-one-laptop into real, hosted software.

The plan is **seven phases**, ordered so each one ships a Greco you'd want anyway and
stands on its own (committed when done — a partial march still leaves Greco better).
Target version numbers come from the PRD §7 milestone mapping.

1. **Greco-on-localhost (the leap).** *(v0.10 — done)*
   *After this phase: a user on this machine can generate a Greco report from a browser without opening a terminal.*
   Put a web server in front of the existing pipeline: browser → upload a PGN → HTML report, running on your machine first. Everything below builds on this. The analysis pipeline stays unchanged behind it; this is the desktop → web jump.

2. **Async jobs + status page.** *(v0.11 — done)*
   *After this phase: a user can submit a game and walk away — it processes in the background and the report appears when it's ready.*
   Stockfish analysis is slow, so run it in the background: the page shows Queued → Analyzing → Narrating → Done → Failed, and reveals the report when it's ready.

3. **Accounts + roles.** *(v0.12 — done)*
   *After this phase: a user has their own account and sees only their own games and reports.*
   Log in; each user sees their own games and reports; an admin account can see all of them.

4. **Database.** *(v0.13 — done)*
   *After this phase: games and reports survive a server restart and can be queried reliably.*
   Replace the files-and-folders storage (`config.json`, the reports folder) with a real database — SQLite locally to start, PostgreSQL once hosted — holding users, games, reports, and jobs.

5. **Phone-friendly UI + dashboard + export.** *(v0.14–v0.15 — done)*
   *After this phase: a user can open Greco on their phone, see their game history, and export a report as PDF.*
   Make the web UI work well on a phone; add a dashboard (your games, accuracy trend, recent reports) and CSV/PDF export. This absorbs the old desktop-polish ideas: drag-and-drop upload and a recent-games list become web features here, and "Save as PDF" becomes the export above. (PDF is a *static* snapshot for printing or sharing — it can't carry the interactive board, so the interactive PGN viewer stays in the HTML report and PDF is its lower-priority companion format; pursuing the viewer doesn't rule out PDF. You can already "Print → Save as PDF" any HTML report from the browser today, so a one-click PDF button is polish, not a blocker.)

6. **Auto-import + "report ready" notification.** *(v0.16 — done)*
   *After this phase: a user can connect their Lichess account and Greco will show recent games for one-click analysis and email them when a report is ready.*
   Lichess account integration (profile page, recent-games panel with one-click analysis), Lichess URL direct input in the upload form, and SMTP email notification when a report finishes processing.

7. **Deploy it.** *(target: v1.0)*
   *After this phase: anyone in the world can open a URL, sign up, upload a PGN, and get a Greco report — from any device, no install.*
   Host on Render or Railway with a real domain and HTTPS — Greco becomes a live web app you can hand someone a link to.

**Front-end layer (folded in from the old backlog):** the interactive PGN viewer and the
in-browser "read aloud" are the front-end polish of Greco Online (backlog #8–#9).

**Stack — pick for the long run:** Python backend (FastAPI) + PostgreSQL, server-rendered
HTML to start with a little JavaScript for interactivity; host on Render or Railway. This
reuses the Python Greco is already written in. *Prerequisite worth doing first:* upgrade to
Python 3.11+ 64-bit — it removes the `PYTHONUTF8` / SSL / pip workarounds this old 3.8.5
32-bit install forces. *Two cautions:* a hosted Greco spends real money per use (Claude
tokens + Stockfish CPU), so keep it behind a login / invite-only at first; and the API key
stays server-side, never shipped to the browser.

## Backlog — priority queue (pull "work orders" from here)

Ordered by priority. Sizes are rough: **S** = a prompt tweak / small edit;
**M** = a feature + a rebuild; **L** = a big feature or refactor. Work top-down;
each item is committed when done, so a partial batch is still saved progress.

**Idea-tracking convention.** Every product idea gets a numbered row here the moment
it is raised. When it ships **and** is verified (tested), mark it **done** (with the
version) and move it down to *Recently shipped* — the secondary list — so this queue
shows only live work. Don't delete a shipped idea; downshift it, so the record of what
was built stays visible.

| # | Task | Size | Status |
|---|------|------|--------|
| 1 | **Greco Online · Phase 1** — web server over the pipeline: browser upload → report (localhost) — `web/main.py` + `run_greco_web.bat` (FastAPI; additive, desktop app untouched) | L | **done** |
| 2 | **Greco Online · Phase 2** — async analysis jobs + status page (Queued → Running → Done / Failed) — `web/jobs.py` (JobRegistry), `GET /job/{id}` JSON status, `GET /result/{id}` result page, `POST /analyze` now returns the `_WAITING` page immediately; background task drives the pipeline; JS polls every 2 s and auto-navigates on Done | M | **done** |
| 3 | **Greco Online · Phase 3** — accounts + roles (login, per-user games, admin) | L | **done** (v0.12.0) |
| 4 | **Greco Online · Phase 4** — database (SQLite locally → PostgreSQL hosted) | M | **done** (v0.13.0) |
| 5 | **Greco Online · Phase 5** — phone-friendly UI + dashboard + CSV/PDF export | M | **done** (v0.14–v0.15) |
| 6 | **Greco Online · Phase 6** — Lichess account integration + "report ready" email | M | **done** (v0.16.0) |
| 7 | **Greco Online · Phase 7** — deploy (Render/Railway, domain, HTTPS) | M | todo |
| 8 | Interactive PGN viewer in the report HTML — *front-end layer of Greco Online* — self-contained JS board + move navigation, keyboard controls, color-coded move list, eval display, flip button | L | **done** |
| 9 | "Read aloud" in the report HTML — *front-end layer of Greco Online* — Web Speech API (`speechSynthesis`), no extra files | M | **done** |
| 10 | `knowledge/` corpus — public-domain chess books retrieved (RAG, SQLite FTS5) and wired into the narrator; themes detected from engine ground truth. **Infrastructure built & verified (`knowledge.py`); awaiting content** (deposit per `knowledge/README.md`). | M | **infra done · content todo** |
| 11 | Bulk-gather more commentary transcripts (Agadmator + SammyChess) | M | todo |
| 12 | Tighten the OTB classical-vs-rapid classifier (or use a curated source) | S | todo |
| 13 | **Test suite** — `tests/` directory with `pytest`; cover knowledge retrieval (FTS5 returns correct passages), triage logic (tiers fire correctly), and web routes (`/analyze` accepts a PGN, returns HTML; `/health` is live). This is the single highest-impact portfolio signal: the absence of tests is visible in the file tree before a reviewer reads any code. Also the StayPlus prerequisite: "how do you know X is correct?" is answered with tests. | M | **done** — `tests/` (26 tests; triage, outputs/export, web routes, knowledge FTS5, version automation), gated by `scripts/ship.py` |
| 14 | **GitHub Actions CI** — `.github/workflows/ci.yml` runs `pytest` on every push and PR (installs `python3-tk` + `requirements-dev.txt`; suite is engine/key-free by design). | S | **done** (v0.9.0) |
| 15 | **App screenshots in README** — a `/screenshots/` folder with two images: the Tkinter desktop GUI (settings panel or main window with a game loaded) and the FastAPI web interface in a browser (upload form + resulting report). Link both from the README Quick Start section. Fastest way to show "this is real software" to someone who hasn't run it. | S | todo |
| 16 | **Expand knowledge corpus beyond Capablanca** — deposit at least two more public-domain books per `knowledge/README.md` and the SHOPPING_LIST. Good first targets: Nimzowitsch's *My System*, Tarrasch's *The Game of Chess*, or a Euwe game collection. (Acquisition is a **Claude Cowork** task — book hunting/cleaning — not a Claude Code one.) | M | todo (→ Cowork) |
| 17 | **Engine-sourced variation lines** — refutation/best lines as a closed quotable set + the "only quote provided lines" rule + the `find_unverified_variation_moves` validator (the ...Kg7 fix). | L | **done** (v0.9.0) |
| 18 | **Wasted / self-defeating tempo coaching concept** — threats that induce a move the opponent already wanted; the "helping your opponent develop" family. | S | **done** (v0.9.0) |
| 19 | **Player names across all modes** — filename fallback + header-derived psychology tier-boost for GUI/web (was CLI-only). | M | **done** (v0.9.0) |
| 20 | **Daily / correspondence voice** — detect the game and inject the protocol; fix the time-control humaniser. | S | **done** (v0.9.0) |
| 21 | **Deterministic featured passage** — pick one best chunk and hand the model a finished, attributed, verbatim quote. | M | **done** (v0.9.0) |
| 22 | **Clickable variations in the replay viewer** — emit per-ply FENs for `variations` so a written line plays out on the board (2A phase 2; the per-ply data is the only missing piece). | M | **done** (v0.19.0) |
| 23 | **Per-ply material trajectory along engine lines** — annotate captures in `best_pv`/variations so "show the money" is computed, not model-tallied. | M | todo |
| 24 | **Computed decisive-moments block** — biggest eval swings + first-decisive ply, to ground the closing-summary claims in data rather than recollection. | S | **done** |
| 25 | **Multi-move sacrifice detection** — flag a material-down / eval-up window across plies in code (today the model judges it from the trajectory). | M | todo |
| 26 | **Auto-strip confabulated variation moves** — promote `find_unverified_variation_moves` from a warning to an enforced edit, once it is trusted not to mangle good prose. | S | **done** |
| 27 | **GUI/web per-player context fields** — let desktop/web users supply structured "White is my dad, an attacker" context (CLI-only via `--white-context` today). | S | **done** |
| 28 | **Output Fact-Gate predicate library** (`factgate.py`) — per-ply allow-set of engine-certified claims (fork, pin, rook-lift, outpost, passed-pawn, mate-threat) + scoped prompt rule. The output-side mirror of the input validation gate. | L | **done** (v0.10.0); all 18 Tier-A predicates complete through v0.29.0 |
| 29 | **Layer-2 claim-verification self-test** (`factcheck.py` / `tools/verify_report.py`) — deterministic CI-safe contradiction checks (exit-1 gate) + an advisory LLM-judge; runs off a saved analysis. | L | **done** (v0.10.0) |
| 30 | **Grow the predicate library + chess glossary** — Tier-A predicates (18) are done; next is Tier-B predicates (checkable-but-harder: overloaded piece, compensation, tempo, …) from the pacing roadmap in `docs/specs/TERMINOLOGY_TIERS.md`. | M | **Tier-A done** (v0.29.0); Tier-B todo |
| 31 | **Wire `verify_report` into the release/CI loop** — run the deterministic gate on a sample report in `ship.py` / CI so a confabulation regression fails the build. | S | **done** |
| 32 | **Essay Mode** — candidate fourth mode; answers chess questions analytically using the knowledge corpus; PGN optional as illustrative material. Design spec pending — see `Developer Notes (Greco)/Handoffs/package-d-essay-mode.md` before implementing. | M | todo (design first) |

**Folded in / superseded:**
- *Polish (Save-as-PDF, drag-and-drop a PGN, recent-games list)* — absorbed into Greco
  Online Phase 5 (export + dashboard + web upload), where these are natural web features.
- *Private GitHub repo for phone ↔ laptop* — **superseded** by Greco Online: once Greco is
  a website, you just open it on your phone, so there's nothing to git-sync.

**Recently shipped** (newest first): **v0.29.0** — `is_zugzwang` predicate (spec 18, engine-dependent approximate): null-move probe in `analyzer.py` first pass, sign-correct side-to-move POV conversion, 5-veto ladder, strictness ladder (STRICT/NEAR), full evidence bundle, narrator guidance; 13 new tests including mandatory two-color trébuchet regression. 156 total factgate tests.
**v0.28.0** — `outpost_evidence()` sibling function: ready-to-quote evidence bundle for certified outpost; serialized as `outpost_evidence` in narrator Tier-1+ block; narrator instruced to quote the `evidence` string. 7 new tests; 143 total.
**v0.27.0** — `is_fianchetto`: certifies bishop-on-flank + knight-pawn-advanced structure; both-colors loop; pin never suppresses; conservative on damaged structures; evidence bundle per flank with `king_behind` flag. 15 new tests; 136 total.
**v0.26.0** — `is_infiltration`: rook/queen on 7th/8th or endgame king ≥ rank 6; 5-veto ladder; hanging rook certifies with caveat; evidence bundle with `arrival_file_state` + `confines_king`. Phase threaded through `certified_claims()`. 16 new tests; 121 total.
**v0.25.0** — `is_backward_pawn`: rear-most on adjacent files, stop square enemy-pawn-controlled, no support lane; home-rank double-step escape; `subtype` + `fixed_level_neighbors` evidence. 10 new tests; 105 total.
**v0.24.0** — `creates_discovered_attack` + `detect_discovered_attack` in `analyzer.py`: plain / discovered check / double check; causation guard binds each revealed target to the specific vacated square; pinned-rear flag; en passant capture square joins vacated set. 9 new tests.
**v0.23.0** — `creates_skewer` + `detect_skewer`: absolute (king-in-front, gives check) and relative; pinned-attacker veto; no pawn-as-front-piece; mirrors pin's ray-walk engine. 9 new tests.
**v0.22.0** — `creates_pin` + `detect_pin`: absolute and relative pins by the mover's sliding pieces; 9-rule veto-then-confirm; pawn-as-front-piece; evidence bundle with `line`, `coord`, attacker/pinned/behind squares. 12 new tests.
**v0.21.0** — `is_luft` + `is_back_rank_weak`: luft certifies a quiet pawn push that opens a survivable king flight square; back-rank weakness certifies vulnerability (not mate) for both colors per ply. 16 new tests.
**v0.20.0** — `is_isolated_pawn` + `is_doubled_pawn`: IQP/isolani and isolated-doubled evidence; doubled-pawn STATE (distinct from the event field `doubled_pawns_created`). 29 new tests.
**v0.19.0** — Clickable variation lines in the PGN
replay viewer (#22): `_pv_to_fen_plies()` parses engine variation strings into per-ply FEN
data; `build_pgn_viewer()` embeds the data in the payload; JS `showVars()` renders "Better:"
/ "Then:" chips below the board — clicking any chip peeks at that position (highlighted in
green); pressing ←/→ returns to the game. 9 new tests; 282 total.
**v0.18.0** — Factgate: `creates_battery()` and `threatens_promotion()` predicates; both
added to `GATED_TAGS` + `certified_claims()` + narrator whitelist; king correctly excluded
from diagonal-capture promotion threats. 10 new tests; 273 total.
**v0.17.0** — Phase 7 deployment prep: `render.yaml` Render Blueprint, `docs/DEPLOYMENT.md`,
PostgreSQL support in `web/db.py` (`DATABASE_URL` env var, `postgres://` → `postgresql://`
normalization), `collation="NOCASE"` removed from models + migration 001,
`psycopg2-binary` added; period typography (Cinzel + EB Garamond from Google Fonts).
**v0.16.0** — Phase 6: Lichess account integration
(profile page, recent-games panel, one-click analysis), Lichess URL direct input in the
upload form, SMTP "report ready" email notification, `web/email_utils.py`, Alembic migration
003 (`lichess_username` column), full test coverage (`test_profile.py`, `test_email_utils.py`).
**v0.15.0** — CSV export (all reports) + per-report delete (admin only) in the dashboard.
**v0.14.0** — Phase 5: phone-friendly responsive web UI, per-user dashboard (accuracy trend,
recent reports, game history), star-rating accuracy display. **v0.13.0** — Phase 4: SQLite
database with SQLAlchemy 2.0 ORM (`web/models.py`, `web/db.py`) and Alembic migrations
(`alembic/`); report + game persistence across restarts. **v0.12.0** — Phase 3: accounts +
roles (bcrypt hashing, SessionMiddleware cookies, `require_login` dep, admin RBAC, per-user
report scoping). **v0.11.0** — Phase 2: async analysis jobs + status page
(`web/jobs.py` JobRegistry, Queued→Analyzing→Narrating→Done→Failed state machine, JS polling).
**v0.10.0** — Output Fact-Gate predicate library + per-ply allow-set + scoped prompt rule
(#28), and Layer-2 claim-verification self-test (deterministic CI gate + advisory LLM-judge +
`tools/verify_report.py`) (#29). **v0.9.0** — engine-sourced variation lines + confabulation
validator (#17); wasted-tempo coaching concept (#18); player names across all modes (#19);
daily/correspondence voice detection (#20); deterministic featured passage (#21); GitHub
Actions CI (#14); correctness sweep.
Earlier: settings panel; SVG chronological ordering; voice refinements (relationship framing,
reader-level language, keepsake mode, timid first moves, winning-a-piece ≠ a trade);
standalone `Greco.exe`; game finders (Chess.com + PGN Mentor); commentary-learning;
report naming; versioning + docs.

## Aesthetic backlog — ivory-manuscript / carved-ivory direction (brainstorm)

> Modular ideas for evolving Greco's look toward its two touchstones: **Gioachino Greco's
> hand-written chess manuscripts** and the **carved ivory medieval pieces of the Age of
> Empires II intro**. The established palette is the app icon's **wine `#7A1C26` /
> ivory `#F5EDD4` / gold `#C9A23A`**. Each item is independent — pick any, in any order.
> Stay anchored to those two touchstones; ideas that drift from "ivory manuscript / carved
> ivory pieces" are out of scope.

**Shipped so far:** wine/ivory/gold theme on the desktop GUI; calligraphic *Greco* wordmark
(Gabriola); sepia-ink-on-parchment manuscript narration log; large ivory pawn/knight/rook
section markers; king logo on the title bar + taskbar.

**Modular ideas (later):**
- [ ] **Carved-ivory piece *images*** — render dimensional ivory pieces (bevel/shadow, like the
  king logo) instead of font glyphs, for section markers + accents. Desktop: pre-rendered PNGs
  (à la `assets/make_icon.py`); web: inline SVG with CSS lighting. Where the "carved" quality
  really lands.
- [ ] **In-app king crest** — show the icon's king-in-a-roundel (gold rim, wine field, ivory
  king) as a top-left logo *inside* the window/page, not only on the title bar.
- [ ] **Illuminated borders & flourishes** — a thin gold filigree frame; corner motifs
  (fleur-de-lis or rook crenellations) on panels. Web first (SVG/CSS); desktop as art assets.
- [ ] **Drop-cap / illuminated initial** on the narration's first letter. Web: CSS
  `::first-letter`; desktop: a Text tag.
- [ ] **Parchment texture** on fields, the narration log, and the report background. Web: a
  tiling image; desktop: limited (flat parchment colour only).
- [ ] **Period typography pass** — evaluate a blackletter or chancery *Greco* wordmark; on the
  web, load real period faces (Cinzel / IM Fell English / EB Garamond) for headings + body.
- [ ] **3-tone wine depth** — deeper inset wine, mid field, gold hairlines, so panels read with
  dimension rather than flat colour.
- [ ] **Greco Web parity** — mirror the approved desktop wine/ivory/gold + manuscript look into
  `web/templates.py` (form + result pages). Richer treatment than desktop is possible here.
- [ ] **Report (`.html`) theming** — extend the aesthetic into the generated report CSS in
  `outputs.markdown_to_html` (today's report uses a blue/serif scheme) so the emailed output —
  including the shareable single-file export — matches the app.
- [ ] **Ruled manuscript margins** on the narration log (faint vertical rule + indented text),
  evoking a scribe's page.

## Greco Coach — the teaching vision (knowledge corpus, backlog #10)

**Vision:** *Greco Coach is an LLM + Stockfish-powered chess teacher/tutor that is
restricted to quoting and reading books published before `current_year − 95` (the
public-domain line), yet still learns, applies, and shares the knowledge of the old
masters — bridging the gap between supercomputers and human understanding.*

The `knowledge/` corpus is the spine of this: a curated library of public-domain chess
texts the narrator retrieves from at analysis time (see backlog #10 and
`knowledge/README.md`). The pre-95-year restriction is a deliberate feature, not a
limitation — it grounds Greco in the enduring, freely-shareable wisdom of the classical
masters. Verbatim quotation of those masters is most desired in **Coaching** mode, where
a master's own line can anchor a lesson; the capability is wired in and most reliable
there. (An A/B test, 2026-06-13, found a frontier model already *knows* general
principles and applies them in its own words even without the corpus — which is itself
aligned with "learn, apply, and share" — so the corpus's sharpest value is deep opening
theory and concrete analysis the model lacks, plus optional verbatim quoting.)

## Toward v1.0 — "feels like real software"

The v1.0 bar is now **Greco Online running hosted, with accounts** — a stranger could open
a link, log in, and get a report. The phases above are the path there.

## Superseded vision — the installable `.exe`
The previous v1.0 target was a standalone `Greco.exe` (PyInstaller bundle: double-click,
no console, no separate Python install). **That shipped** and remains the local launcher on
this machine — the launcher `.bat`/`.vbs` scripts it replaced are obsolete. It's preserved
here as history; it is **no longer the product direction**. Distributing a desktop binary
to other computers is deliberately de-prioritized in favour of hosting Greco online, where
updates are instant and every user is on the same version.

## Later ideas
- A larger, curated commentary-reference library (bulk Agadmator + SammyChess) — see
  backlog #11.
- Desktop distribution of the `.exe` to other computers — possible, but secondary to
  hosting Greco online.
- **Deterministic "featured passage" (knowledge corpus luxury feature) — two variants.**
  *Variant A (meta.json pre-vetting):* let the book depositor mark one sentence in each
  text as the canonical quotable line (`"featured_sentence": "…"` in `meta.json`); if a
  chunk contains that sentence, `_extract_key_sentences` always picks it, giving a
  predictable, human-vetted quote target. *Variant B (outputs.py mechanical insertion):*
  retrieve the best-matching passage and embed it as a formatted block-quote with
  attribution directly in the HTML report in `outputs.py`, independent of the model's
  choice — a guarantee that a master's words appear regardless of narrator discretion.
  Both are Greco Coach nice-to-haves, not core; Variant B alters report format, so it is
  a deliberate product decision for later.
- **Move-level retrieval (higher precision, higher cost).** Currently `knowledge.py`
  retrieves once per game. A per-move variant would query the corpus again for each
  tier 2/3 move, using only that move's specific detected features and phase. Cost: N FTS
  queries per report (cheap because SQLite FTS5 is local). Payoff: passages are matched to
  the exact move they'll annotate rather than the whole game. Worth doing once the corpus
  has enough books for per-move queries to return meaningfully different results than a
  per-game query.
- **Negative filtering against the game's detected features.** If a passage's
  `matched_theme` is e.g. `"doubled_pawns"` but the game's detected theme list (from
  `themes_from_game()`) does not include `"doubled_pawns"`, the passage was only retrieved
  as a second-pass filler and likely mismatches the game. Add a hard filter in
  `load_knowledge_for_game()` that drops any filler passage whose theme is absent from the
  game's genuine detected features — catches theme drift before it reaches the narrator.
- **Auditable chain-of-thought validation in the report.** Tell the narrator to emit one
  bracketed verification line each time it uses a corpus quote, e.g.
  `[Verified: Andersson's rooks were defending pieces, matching "overloaded defender".]`
  This line appears in the raw Markdown report and is visible during A/B testing, making
  it straightforward to check whether the position-validation step actually ran and what
  conclusion the narrator reached. Cost: ~15 words per quote used.
- **Corpus content priority (from the 2026-06-13 A/B test):** acquire **deep opening
  theory and annotated master games** first (content the model is unreliable on); treat
  general-principles books as low-priority. Tracked in `knowledge/SHOPPING_LIST.md`.

## Working conventions
- **Versioning:** bump PATCH for fixes, MINOR for new features, MAJOR for big/breaking
  changes; record every change in `CHANGELOG.md`.
- **Backups:** local git is the source of truth; `E:\Chess\Greco` is a mirror. (A private
  GitHub remote is an option for off-site backup, and becomes the natural home for the code
  once Greco is hosted online.)
