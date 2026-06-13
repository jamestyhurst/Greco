# Greco Roadmap

Greco turns any chess game into an engine-backed, AI-narrated report. **Its direction is
now Greco Online** — a hosted, multi-user web app you open in any browser (including your
phone), with no install. Today Greco runs as a standalone Windows desktop app; that's the
foundation we're building out from. Versioning is [Semantic](https://semver.org/)
(`MAJOR.MINOR.PATCH`); see [../CHANGELOG.md](../CHANGELOG.md) for what has shipped.

## Where we are — v0.3.0
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
- **Greco Online Phase 1**: `webapp.py` + `run_greco_web.bat` — full pipeline via browser
  on localhost; same output as the desktop app.
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
stands on its own (committed when done — a partial march still leaves Greco better):

1. **Greco-on-localhost (the leap).** Put a web server in front of the existing pipeline:
   browser → upload a PGN → HTML report, running on your machine first. Everything below
   builds on this. The analysis pipeline stays unchanged behind it; this is the desktop →
   web jump.
2. **Async jobs + status page.** Stockfish analysis is slow, so run it in the background:
   the page shows Queued → Analyzing → Narrating → Done → Failed, and reveals the report
   when it's ready.
3. **Accounts + roles.** Log in; each user sees their own games and reports; an admin
   account can see all of them.
4. **Database.** Replace the files-and-folders storage (`config.json`, the reports folder)
   with a real database — SQLite locally to start, PostgreSQL once hosted — holding users,
   games, reports, and jobs.
5. **Phone-friendly UI + dashboard + export.** Make the web UI work well on a phone; add a
   dashboard (your games, accuracy trend, recent reports) and CSV/PDF export. This absorbs
   the old desktop-polish ideas: drag-and-drop upload and a recent-games list become web
   features here, and "Save as PDF" becomes the export above. (PDF is a *static* snapshot for printing or
   sharing — it can't carry the interactive board, so the interactive PGN viewer stays in
   the HTML report and PDF is its lower-priority companion format; pursuing the viewer
   doesn't rule out PDF. You can already "Print → Save as PDF" any HTML report from the
   browser today, so a one-click PDF button is polish, not a blocker.)
6. **Auto-import + "report ready" notification.** Generalize the Chess.com game finder
   into "connect your account → auto-import new games → auto-analyze," and email you when a
   report is ready.
7. **Deploy it.** Host on Render or Railway with a real domain and HTTPS — Greco becomes a
   live web app you can hand someone a link to.

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

| # | Task | Size | Status |
|---|------|------|--------|
| 1 | **Greco Online · Phase 1** — web server over the pipeline: browser upload → report (localhost) — `webapp.py` + `run_greco_web.bat` (Flask; additive, desktop app untouched) | L | **done** |
| 2 | **Greco Online · Phase 2** — async analysis jobs + status page (Queued → Analyzing → Done) | M | todo |
| 3 | **Greco Online · Phase 3** — accounts + roles (login, per-user games, admin) | L | todo |
| 4 | **Greco Online · Phase 4** — database (SQLite locally → PostgreSQL hosted) | M | todo |
| 5 | **Greco Online · Phase 5** — phone-friendly UI + dashboard + CSV/PDF export | M | todo |
| 6 | **Greco Online · Phase 6** — account auto-import + "report ready" email | M | todo |
| 7 | **Greco Online · Phase 7** — deploy (Render/Railway, domain, HTTPS) | M | todo |
| 8 | Interactive PGN viewer in the report HTML — *front-end layer of Greco Online* — self-contained JS board + move navigation, keyboard controls, color-coded move list, eval display, flip button | L | **done** |
| 9 | "Read aloud" in the report HTML — *front-end layer of Greco Online* — Web Speech API (`speechSynthesis`), no extra files | M | todo |
| 10 | `knowledge/` corpus — public-domain chess books retrieved (RAG, SQLite FTS5) and wired into the narrator; themes detected from engine ground truth. **Infrastructure built & verified (`knowledge.py`); awaiting content** (deposit per `knowledge/README.md`). | M | **infra done · content todo** |
| 11 | Bulk-gather more commentary transcripts (Agadmator + SammyChess) | M | todo |
| 12 | Tighten the OTB classical-vs-rapid classifier (or use a curated source) | S | todo |
| 13 | **Test suite** — `tests/` directory with `pytest`; cover knowledge retrieval (FTS5 returns correct passages), triage logic (tiers fire correctly), and webapp routes (`/analyze` accepts a PGN, returns HTML). This is the single highest-impact portfolio signal: the absence of tests is visible in the file tree before a reviewer reads any code. Also the StayPlus prerequisite: "how do you know X is correct?" is answered with tests. | M | todo |
| 14 | **GitHub Actions CI** — `.github/workflows/ci.yml` that runs `pytest` on every push and PR, showing a green check mark on all commits. Prerequisite: item #13 must exist first; CI is the automation wrapper (~10-line YAML once tests are in place). | S | todo |
| 15 | **App screenshots in README** — a `/screenshots/` folder with two images: the Tkinter desktop GUI (settings panel or main window with a game loaded) and the Flask web interface in a browser (upload form + resulting report). Link both from the README Quick Start section. Fastest way to show "this is real software" to someone who hasn't run it. | S | todo |
| 16 | **Expand knowledge corpus beyond Capablanca** — deposit at least two more public-domain books per `knowledge/README.md` and the SHOPPING_LIST. Good first targets: Nimzowitsch's *My System*, Tarrasch's *The Game of Chess*, or a Euwe game collection. The README and CHANGELOG promise a sophisticated RAG system; a single book doesn't demonstrate it. (Overlaps with #10; this item tracks the portfolio optics specifically — one book is not enough.) | M | todo |

**Folded in / superseded:**
- *Polish (Save-as-PDF, drag-and-drop a PGN, recent-games list)* — absorbed into Greco
  Online Phase 5 (export + dashboard + web upload), where these are natural web features.
- *Private GitHub repo for phone ↔ laptop* — **superseded** by Greco Online: once Greco is
  a website, you just open it on your phone, so there's nothing to git-sync.

**Recently shipped** (newest first): settings panel (config.json, model selector, reports
folder picker); SVG chronological ordering (ply-prefixed filenames, data-ply attributes,
sorted placement); developer auto-`similar` hook + folder cap; voice refinements
(relationship framing, reader-level language, Daily voice, keepsake mode, timid first
moves, winning-a-piece ≠ a trade); standalone `Greco.exe`; game finders (Chess.com + PGN
Mentor); commentary-learning; report naming; versioning + docs.

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
