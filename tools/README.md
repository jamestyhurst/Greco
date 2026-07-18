# tools/ — Developer-Only Scripts

All scripts in this folder are **developer tools**: evaluation harnesses, data-acquisition
helpers, and diagnostics used while building and testing Greco. None of them are part of
the shipped product and none should be referenced from the GUI, the CLI, or the Flask/FastAPI
web layer.

| Script | Purpose |
|---|---|
| `knowledge_ab_test.py` | A/B test whether the public-domain knowledge corpus changes (and improves) the narrator's output. Generates two full reports (corpus OFF vs ON) plus a quick-diff `C_spotlight.md`. Output defaults to `Documents\Developer Tools (Greco)\ab-tests\` — A/B artifacts never go next to the PGN or into the game library. |
| `file_reported_pgns.py` | Backup protocol for the PGN library: moves any PGN in `Documents\Chess Game Files` whose report already exists into the `Games with Reports` sub-folder (the GUI/CLI do this automatically at report time; this sweep covers web-generated and historical reports). `--dry-run` previews. |
| `find_games.py` | Download PGNs from Chess.com or PGN Mentor, filtered by time class / result / opening. |
| `fetch_gutenberg.py` | Download a Gutenberg book, strip boilerplate, and deposit it into `knowledge/` for corpus acquisition. |

## What "developer-only" means in practice

- These scripts make direct API calls (Anthropic, Chess.com, Gutenberg) outside the normal
  Greco pipeline, and consume tokens / quota.
- They write output files into the repo or into the user's `Documents` folder — not into
  the standard Greco reports directory.
- They are not tested as part of any CI run and may require manual setup (Stockfish path,
  API key in `config.json`).
- Do not surface these tools in the Greco GUI, in USAGE.md, or in any user-facing
  documentation.
