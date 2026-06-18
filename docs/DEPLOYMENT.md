# Deploying Greco to Render — Phase 7

This guide walks through deploying Greco Online as a live web app using
[Render](https://render.com). After completing it, anyone with the URL can sign up,
submit a PGN, and receive an engine-backed Greco report — from any device, no install.

---

## Prerequisites

- A GitHub account with the Greco repo pushed to it.
- A Render account (free tier is enough to start).
- An Anthropic API key.
- (Optional) SMTP credentials for report-ready emails.

---

## Step 1 — Create a new Blueprint on Render

1. In the Render dashboard, click **New → Blueprint**.
2. Connect your GitHub account and select the `Greco` repo.
3. Render detects `render.yaml` and shows two resources: **greco** (web service) +
   **greco-db** (PostgreSQL database). Click **Apply**.

Render provisions the database, installs dependencies, runs Alembic migrations, and
starts uvicorn — all from the `buildCommand` and `startCommand` in `render.yaml`.

---

## Step 2 — Set the required secrets

In the Render dashboard → **greco** service → **Environment**:

| Variable | Value | Required? |
|---|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | ✅ Required |
| `GRECO_APP_BASE_URL` | `https://greco.onrender.com` (your Render URL) | ✅ Required for email links |
| `GRECO_SMTP_HOST` | e.g. `smtp.gmail.com` | Optional — enables email |
| `GRECO_SMTP_USER` | Your SMTP username / Gmail address | Optional |
| `GRECO_SMTP_PASSWORD` | Your SMTP password or app password | Optional |
| `GRECO_SMTP_FROM` | Sender address, e.g. `greco@example.com` | Optional |

`GRECO_SECRET_KEY` and `DATABASE_URL` are handled automatically by `render.yaml`
(`generateValue: true` and `fromDatabase:` respectively).

---

## Step 3 — Trigger a deploy

After setting the env vars, click **Manual Deploy → Deploy latest commit** (or push a
commit to `main` — Render auto-deploys on push by default).

Watch the build log. A successful deploy ends with:

```
INFO:     Uvicorn running on http://0.0.0.0:10000
```

Open the **public URL** shown in the dashboard (e.g. `https://greco.onrender.com`).
You should see the Greco login page.

---

## Step 4 — First-time setup

1. Click **Register** and create the first user account.
   The first registered user automatically becomes an **admin**.
2. Submit a PGN to confirm the analysis pipeline works end-to-end.

---

## Architecture notes

### Database

Render provisions a **free PostgreSQL** database (`greco-db`). Connection details are
injected as `DATABASE_URL` via `fromDatabase` in `render.yaml`. SQLAlchemy reads this
env var at startup; Alembic reads it at build time to run migrations.

The free PostgreSQL plan includes 1 GB and expires after 90 days without any paid plan.
Upgrade to a paid database plan for long-term hosting.

### Stockfish

Stockfish is installed by `apt-get install -y stockfish` in the build step. The path
`/usr/games/stockfish` is set via the `STOCKFISH_PATH` env var. The version installed
from the Ubuntu apt repository is older than the latest release — this is fine for
Greco's use (move scoring + best-move finding); it does not affect narration quality.

To use a newer Stockfish binary, replace the `apt-get install` line in `render.yaml`
with a download from the official Stockfish releases page and update `STOCKFISH_PATH`.

### Report storage

Reports (HTML files) are stored on a **Render Persistent Disk** mounted at
`/mnt/reports`. The `GRECO_REPORTS_DIR=/mnt/reports` env var redirects the default
reports folder there. The disk persists across deploys and restarts.

The disk costs **$0.25/GB/month** (1 GB disk = ~$0.25/month). To run without a disk
(reports lost on restart/redeploy), remove the `disk:` block from `render.yaml` and
unset `GRECO_REPORTS_DIR` — the app degrades gracefully.

### Costs (approximate)

| Resource | Plan | Monthly cost |
|---|---|---|
| Web service | Starter | $7.00 |
| PostgreSQL | Free | $0.00 (90-day limit) |
| Persistent Disk (1 GB) | — | $0.25 |
| **Total** | | **~$7.25/month** |

The Anthropic API cost scales with usage (tokens per report). A typical Greco report
uses ~3,000–8,000 output tokens.

---

## Maintenance

### Schema migrations

To add a new column or table:
1. Write an Alembic migration: `python -m alembic revision -m "describe change"`
2. Edit the generated file in `alembic/versions/`.
3. Push to `main`. Render runs `alembic upgrade head` in the build step before
   the new app version starts serving traffic.

### Secrets rotation

Rotate `ANTHROPIC_API_KEY` in the Render dashboard (Environment tab). The app picks up
the new value on the next deploy. Do **not** rotate `GRECO_SECRET_KEY` — that would
invalidate all active user sessions.

### Backups

Enable automatic backups in the Render dashboard → **greco-db** → **Backups**.
The free plan supports manual snapshots; paid plans offer automated daily backups.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Build fails at `alembic upgrade head` | `DATABASE_URL` not set / DB not ready | Check that `greco-db` provisioned successfully |
| App starts but `/health` returns `engine_ok: false` | `STOCKFISH_PATH` wrong | Verify `/usr/games/stockfish` exists in the build log |
| Analyses fail with API error | `ANTHROPIC_API_KEY` missing or invalid | Set it in Environment, redeploy |
| Report-ready emails not sent | SMTP not configured | Set all `GRECO_SMTP_*` vars |
| Reports disappear after redeploy | No persistent disk | Add `disk:` block to `render.yaml` |
