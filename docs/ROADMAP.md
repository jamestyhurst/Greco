# Greco Roadmap

Greco turns any chess game into an engine-backed, AI-narrated report. **Its direction is
now Greco Online** — a hosted, multi-user web app you open in any browser (including your
phone), with no install. Today Greco runs as a standalone Windows desktop app; that's the
foundation we're building out from. Versioning is [Semantic](https://semver.org/)
(`MAJOR.MINOR.PATCH`); see [../CHANGELOG.md](../CHANGELOG.md) for what has shipped.

## Where we are — v0.2.0
- Working Tkinter GUI over the full pipeline (importers → analyzer → triage → narrator
  → outputs).
- Branded icon (title bar + taskbar), informative report names, E:-drive output and
  PGN sync, commentary-learning, local git + E: backup.
- **Settings panel**: Stockfish path, API key, model selector, reports folder — all
  persisted to `config.json`; no environment variables needed after first run.
- **SVG chronological ordering**: board images now appear in strict ply order in HTML
  reports; filenames prefixed with ply number; `data-ply` attributes on all figures.
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
| 1 | **Greco Online · Phase 1** — web server over the pipeline: browser upload → report (localhost) — `webapp.py` + `run_greco_web.bat` (Flask; additive, desktop app untouched) | L | **in progress** |
| 2 | **Greco Online · Phase 2** — async analysis jobs + status page (Queued → Analyzing → Done) | M | todo |
| 3 | **Greco Online · Phase 3** — accounts + roles (login, per-user games, admin) | L | todo |
| 4 | **Greco Online · Phase 4** — database (SQLite locally → PostgreSQL hosted) | M | todo |
| 5 | **Greco Online · Phase 5** — phone-friendly UI + dashboard + CSV/PDF export | M | todo |
| 6 | **Greco Online · Phase 6** — account auto-import + "report ready" email | M | todo |
| 7 | **Greco Online · Phase 7** — deploy (Render/Railway, domain, HTTPS) | M | todo |
| 8 | Interactive PGN viewer in the report HTML — *front-end layer of Greco Online* — **Opus-tier** (self-contained JS board + move navigation) | L | todo |
| 9 | "Read aloud" in the report HTML — *front-end layer of Greco Online* — Web Speech API (`speechSynthesis`), no extra files | M | todo |
| 10 | `knowledge/` corpus — public-domain chess books retrieved (RAG, SQLite FTS5) and wired into the narrator; themes detected from engine ground truth. **Infrastructure built & verified (`knowledge.py`); awaiting content** (deposit per `knowledge/README.md`). | M | **infra done · content todo** |
| 11 | Bulk-gather more commentary transcripts (Agadmator + SammyChess) | M | todo |
| 12 | Tighten the OTB classical-vs-rapid classifier (or use a curated source) | S | todo |

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

## Working conventions
- **Versioning:** bump PATCH for fixes, MINOR for new features, MAJOR for big/breaking
  changes; record every change in `CHANGELOG.md`.
- **Backups:** local git is the source of truth; `E:\Chess\Greco` is a mirror. (A private
  GitHub remote is an option for off-site backup, and becomes the natural home for the code
  once Greco is hosted online.)
