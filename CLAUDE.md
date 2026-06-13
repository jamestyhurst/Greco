# CLAUDE.md — Greco

Greco turns a chess PGN into an engine-backed, AI-narrated report
(`importers → analyzer → triage → narrator → outputs/renderers`; thin Tkinter GUI / CLI /
local Flask web front-ends over a shared pipeline). Python; Stockfish via `python-chess`;
narration via the Anthropic API.

## Read this before developing
The development guide and the "build Greco to be ready for StayPlus-class contract work"
strategy live in a descriptively-named companion file, imported here so it loads automatically:

@Greco_Development_Guide_and_StayPlus_Readiness.md

The always-on secrets protocol is imported too:

@secrets-and-api-key-protection.md

Greco doubles as a learning vehicle for James. When you build a feature that exercises a core
software concept, briefly teach it as you go (a few sentences + where to read more), then carry
on. Concept-by-concept map: `software-skills-you-can-learn-from-greco.md`.

## Non-negotiables (detail in the guide)
1. **🔴 Secrets:** `config.json` holds a real, tracked Anthropic API key. Rotate it, untrack it
   (`git rm --cached` + `.gitignore`), ship a `config.example.json`, and load secrets from env
   vars only. Never print the key. Full protocol: `secrets-and-api-key-protection.md` (imported
   above); summary in guide §5.1.
2. **Build to contract grade:** explicit state machines, enforced RBAC, DB migrations, and
   idempotent syncs — these Greco Online phases are the StayPlus training program. (Guide §4–§5.)
3. **Keep the architecture:** *data-back, never prompt-stuff*; thin front-ends over the shared
   core; product-vs-in-house (= proto multi-tenancy). (Guide §5.3.)
4. **Adopt FastAPI past Phase 1; plan the Python 3.11+ 64-bit upgrade.** (Guide §5.2, §5.4.)
5. **Assume non-ASCII / spaced paths** (the account username is non-ASCII): `pathlib`,
   `encoding="utf-8"`, ASCII-only public ids. (Guide §5.5.)
6. Maintain semantic versioning, the CHANGELOG, and docs on every change.
7. **Cross-device sync:** at session start, check the Notion Dev Log for phone-originated
   entries newer than the last laptop entry and surface them before working. After any
   completed feature, architectural decision, or session ending in-progress, write a Notion
   Dev Log entry. Push to GitHub after each self-contained unit of completed work. If a push
   is deferred, log it in Notion so the phone doesn't assume GitHub is current.
   Full protocol: `sync-doctrine.md` (in `Developer Notes (Greco)\`, loaded via `Documents\CLAUDE.md`).
8. **Developer Notes derivatives must never be pushed to GitHub.** Files in
   `Documents\Developer Notes (Greco)\` hold private business strategy (StayPlus client
   context, personal roadmap) and are kept *outside* the repo by design — they never appear
   in `git status`. However, copies or derivatives can land in the working tree. Any such
   file must be in `.gitignore` before it is ever staged. Current gitignored derivatives:
   `Greco_Development_Guide_and_StayPlus_Readiness.md`, `software-skills-you-can-learn-from-greco.md`.
   If you add a new planning doc to the repo root, add it to `.gitignore` immediately and
   verify with `git status` before committing.
