# Secrets & API-Key Protection Protocol

Applies to **Greco and every future project** — including StayPlus-class contract work, where
a leaked key can mean a client's money, a third-party account (Guesty), or guest/worker PII.
The cheapest place to build this discipline is here, on one API key.

This is both a **standing instruction for Claude Code** and a **protocol for James**. It is the
detailed companion to §5.1 of `Greco_Development_Guide_and_StayPlus_Readiness.md`.

---

## Standing Instruction (Claude Code)

Follow these in every session, in any repo:

1. **Never write a real secret into a tracked file** — not source, config, tests, docs, commit
   messages, or logs. "Secret" = API keys, tokens, passwords, connection strings, private keys.
2. **Never print, echo, or log a secret value**, even partially, even for debugging.
3. **Read secrets from environment variables or a secrets manager** — code looks them up at
   runtime; it does not contain them.
4. **Any committed config is an *example* with placeholders** (`config.example.json`,
   `.env.example`). The real file is git-ignored.
5. **Ensure secret-bearing files are git-ignored *before* the first commit** that would touch
   them. Check `.gitignore` first.
6. **If you find a secret in the working tree or git history, STOP and flag it.** Rotate +
   untrack before doing other work — do not "note it for later."
7. **When adding any new integration** (Guesty, Stripe, Twilio, a database URL…), wire its
   credential via an environment variable from the very first line of code.

---

## Immediate remediation — the `config.json` key in Greco

`config.json` currently holds a real, plaintext Anthropic API key and is **not** git-ignored.
Do this before other work (see also guide §5.1):

1. **Rotate it now** — treat the key as compromised; revoke/regenerate at the Anthropic console.
2. `git rm --cached config.json` — stop tracking it.
3. Add `config.json` (and `.env`, `*.key`, `*.pem`) to `.gitignore`.
4. Commit `config.example.json` with placeholder values; document setup in `docs/USAGE.md`.
5. If the repo was **ever pushed anywhere**, purge the key from history with `git filter-repo`
   (or BFG) before it is hosted/shared, then rotate again.
6. Never print the key in any output.

---

## How to store secrets, by environment

| Environment | Where the secret lives | How code reads it |
|---|---|---|
| **Local dev** | OS user env var, or a git-ignored `.env` file | `os.environ[...]`, or `python-dotenv` for `.env` |
| **Desktop app (end user)** | OS env var or OS keychain; a settings file the *user* owns, never shipped with a key baked in | settings panel writes the user's own key locally |
| **Production (Render/Railway)** | the platform's env-var / secret settings | `os.environ[...]` at boot |

Rules that hold everywhere:
- **Separate keys per environment** (dev key ≠ prod key) and keep each **least-privilege**.
- **Never ship a secret to the browser/client.** Keep it server-side. (Greco's `webapp.py`
  already binds to `127.0.0.1` and keeps the key server-side — that instinct is correct;
  preserve it when hosting.)

---

## The example-config pattern

- Ship `config.example.json` / `.env.example` with safe placeholders and comments.
- Resolution order in code: **environment variable → local git-ignored config → clear error**
  with a message telling the user how to set it. (Greco's `resolve_settings()` already does
  env-var fallback — keep that shape, just make the tracked file an example.)

---

## Prevent leaks with tooling

- **`.gitignore`** the obvious files: `config.json`, `.env`, `*.key`, `*.pem`, `*.pfx`.
- **Pre-commit secret scanning**: add `gitleaks` or `detect-secrets` as a pre-commit hook so a
  key can't be committed by accident.
- **Remote-side protection**: enable the host's secret-scanning / push-protection if available
  (e.g., GitHub) once the repo is remote.

---

## Rotation policy

- Rotate **immediately** on any suspicion of exposure (committed, logged, pasted, shared).
- Rotate when a collaborator with access leaves.
- Rotate **on a schedule** for shared/production keys (e.g., every 90 days).

---

## If a secret leaks — incident response

1. **Revoke/rotate** at the provider first; everything else is secondary.
2. **Remove** from the working tree and from git history; coordinate any force-push.
3. **Check the provider's usage logs** for unauthorized use / unexpected spend.
4. **Record** what leaked, how, and the fix, so the gap is closed for next time.

---

## Pre-commit / pre-deploy checklist

- [ ] No real secret in any tracked file (grep your diff before committing)
- [ ] Secret-bearing files are git-ignored
- [ ] An example/placeholder config is present and documented
- [ ] Code loads secrets from env vars / a secret store, not from tracked files
- [ ] Secret scanner runs clean
- [ ] (deploy) production secrets are set in the platform, never in the repo

---

## Why this matters (and how it generalizes)

A leaked key is someone else spending your money or reading your data. Greco risks one
Anthropic key; **StayPlus would risk a Guesty API key, a payment-processor credential, and
guest/worker PII** — exactly the assets a client will hold you responsible for. "How do you
manage secrets?" is a question a serious client *will* ask. Build the muscle on Greco's single
key and you can answer it credibly.
