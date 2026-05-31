# Greco: product vs. in-house

Greco wears two hats. Keeping them distinct keeps the **shareable product** clean
and generic, while still letting the **in-house system** (you + this laptop + Claude
Code) do extra, personalized things.

## The shareable product — what someone else could run
The core that turns a PGN into a report, with generic defaults and **no personal paths**:
- **Pipeline:** `importers, analyzer, triage, narrator, outputs, renderers, openings,
  commentary, tts`
- **Front-ends:** `gui.py`, `main.py`, and the packaged **`Greco.exe`**
- **Defaults:** reports → `Documents\Greco Reports`; engine path / API key / output
  folder come from environment variables (or, later, a settings panel) — never
  hardcoded drives or usernames
- **Versioning + docs:** `version.py`, `CHANGELOG.md`, `docs/`

## The in-house system — you, this machine, Claude Code
Customizations and automation specific to your setup:
- The **`E:\Chess\…`** layout (Greco backup, PGN library, reports) — opt-in via
  `GRECO_REPORTS_DIR` + the sync scripts, **not** baked into the product
- **Data-acquisition tools** in `tools/` (`find_games.py`) and
  `commentary_refs/_tools/` (`fetch_transcript.py`)
- Your **curated `commentary_refs/`**, your **personal PGN library**, the PGN sync,
  and any **scheduled / queued Claude Code tasks**
- Anything that **downloads or auto-acquires** resources for *your* Greco

## How we keep the line clean
- **Generic defaults + overrides.** Product code ships sensible defaults; personal
  settings come from environment variables (`GRECO_REPORTS_DIR`, `STOCKFISH_PATH`,
  `ANTHROPIC_API_KEY`) or a config file — never hardcoded.
- **`tools/` is in-house.** Acquisition/automation scripts live there and are not
  required to run Greco itself.
- A feature meant for the product ships with a default; an in-house feature stays
  opt-in. When in doubt, ask: *would a stranger running Greco want this on by default?*
