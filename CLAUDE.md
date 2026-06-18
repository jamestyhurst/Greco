# CLAUDE.md — Greco

Greco turns a chess PGN into an engine-backed, AI-narrated report
(`importers → analyzer → triage → narrator → outputs/renderers`; thin Tkinter GUI / CLI /
local FastAPI web front-end over a shared pipeline). Python; Stockfish via `python-chess`;
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
1. **Secrets:** the Anthropic API key lives in `config.json`, which is **gitignored and
   untracked** — verified never committed and absent from all git history; `config.example.json`
   is the shipped placeholder template. Standing rule: never track, print, or echo the key; the
   real `config.json` stays local-only; any new secret loads from an env var or the gitignored
   config, never a tracked file. **Scan the staged diff for secrets before every push** (the repo
   is public) — see "Versioning, commits & GitHub sync" below. Full protocol:
   `secrets-and-api-key-protection.md` (imported above); summary in guide §5.1.
2. **Build to contract grade:** explicit state machines, enforced RBAC, DB migrations, and
   idempotent syncs — these Greco Online phases are the StayPlus training program. (Guide §4–§5.)
3. **Keep the architecture:** *data-back, never prompt-stuff*; thin front-ends over the shared
   core; product-vs-in-house (= proto multi-tenancy). (Guide §5.3.)
4. **Adopt FastAPI past Phase 1; plan the Python 3.11+ 64-bit upgrade.** (Guide §5.2, §5.4.)
5. **Assume non-ASCII / spaced paths** (the account username is non-ASCII): `pathlib`,
   `encoding="utf-8"`, ASCII-only public ids. (Guide §5.5.)
6. Maintain versioning, the CHANGELOG, and docs on every change — through the automated
   workflow in "Versioning, commits & GitHub sync" below (Conventional Commits drive
   `scripts/bump_version.py`; never hand-edit the version number).
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

## Versioning, commits & GitHub sync (automated)

The standing release workflow — it automates version bumps, tags, and pushes so they aren't
typed by hand each session. Designed from the Notion "Greco" page; it deliberately uses **no
external tools** (git-cliff/Rust were dropped — auto-installing software trips this machine's
antivirus). Pure Python + git only, run manually during a session (never as a background task).

> **One command — `python scripts\ship.py`** — does it all when a unit is finished AND verified:
> refuses on a dirty tree, smoke-imports the core modules, runs the secret scan, bumps + tags the
> version from your Conventional Commits, and pushes `main` + tags. `--dry-run` previews without
> pushing. It does **not** write Notion — add the Dev Log entry yourself afterward (step 5).
> The steps below are what `ship.py` automates (and what to do by hand if it ever can't run).

**1. Conventional Commits — always.** Every commit subject is `<type>: <description>` (also
`type(scope):` or `type!:`). Never freeform.

| type | meaning | version effect |
|---|---|---|
| `release` | deliberate milestone — a batch of features forming a meaningful product increment | MINOR |
| `feat` | individual new user-facing capability | PATCH |
| `fix` | bug fix | PATCH |
| `micro` | tiny tweak (wording, colour, a config value) | MICRO |
| `docs` / `refactor` / `test` / `chore` | no behaviour change | none |
| `type!:` or `BREAKING CHANGE` in the body | incompatible change | MAJOR |

*When to use `release:`:* after accumulating several `feat:` PATCH commits that together represent a named milestone (completing a roadmap phase, shipping a named feature set, a corpus expansion you consider substantial). One `release:` commit per milestone — the bump is intentional, not automatic. *Aesthetic changes:* a full re-theme is `feat` (PATCH); small style tweaks are `micro` (MICRO).

**2. 4-digit version** — `MAJOR.MINOR.PATCH.MICRO`, trailing zeros omitted (`0.3.1`, not
`0.3.1.0`). Single source of truth: `version.py`. Never hand-edit the number.

**3. Bump with the script.** Once the session's content commits are in on a clean tree:

```
python scripts\bump_version.py            # dry run — shows the computed next version
python scripts\bump_version.py --apply    # writes version.py, commits "chore: release vX", tags vX
```

It reads the commits since the last tag, takes the highest bump, and refuses to run on a dirty
tree. You still update `CHANGELOG.md` by hand: move `[Unreleased]` into a new `[vX] — DATE`
section. The script owns the number + tag; you own the human-readable log.

**4. Push completed, tested work** (after a self-contained unit is done AND verified):
  a. **Secret-scan first — ironclad, the repo is public.** Confirm `config.json` is untracked
     (`git ls-files --error-unmatch config.json` should error) and that
     `git grep -nI "sk-ant" -- .` returns only placeholders. Never push if a real secret
     appears in the diff.
  b. `git push && git push --tags`
  c. If a push is deferred/fails, log it in the Notion Dev Log (Type: Note, Status: Todo).

**5. Log to Notion.** After a completed feature/fix/decision (or a session ending mid-task), add
a Greco Dev Log entry: Device Laptop, Branch, Version, Status, Type, Notes. Protocol:
`sync-doctrine.md`.

**Never:** commit/print the API key; push without the secret scan; use a freeform commit subject
or hand-edit `version.py`; or set up a scheduled/background auto-push (session-driven and manual
only — background installers/tasks trip this machine's antivirus).
