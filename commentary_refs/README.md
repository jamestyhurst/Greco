# Commentary style references

This folder teaches Greco **how good chess commentary sounds** by letting it read
transcripts of real human commentators. Greco studies the *style* (pacing, tension,
how they explain a position, when they get excited) — it does **not** copy any chess
facts from them. Every fact about your game still comes only from the engine.

## How to add a reference (about 2 minutes)

1. **Find a commentary video you like** on YouTube (e.g. an Agadmator game recap,
   a GothamChess recap, a Finegold lecture).
2. **Get its transcript:**
   - Easiest: on the YouTube page, click **"…more"** under the video, then
     **"Show transcript"** — and copy the text. *(This is the most reliable way.)*
   - Or paste the video URL into a "YouTube transcript" website and copy the text.
3. **Make a new folder inside this `commentary_refs` folder.** Name it anything
   descriptive, e.g. `agadmator-opera-game` (avoid starting the name with `_`).
4. Inside that new folder, save the transcript as a plain text file named
   **`transcript.txt`** (just the spoken words — timestamps are fine to leave in).
5. *(Recommended)* Save the **PGN** of the game being discussed as **`game.pgn`**
   in the same folder. This tells Greco which game the commentary goes with.
6. *(Optional)* Add a **`meta.json`** describing it (see `_example/meta.json`).

That's it. The next time you run Greco, it will read these automatically.

## What a reference folder looks like

```
commentary_refs/
    agadmator-opera-game/
        transcript.txt     (required — the commentator's words)
        game.pgn           (optional — the game they're discussing)
        meta.json          (optional — title / commentator / source URL)
```

## Good to know

- **Style only, never facts.** Greco is told, in strong terms, to learn only the
  commentator's *voice* and to ignore every chess claim they make. This keeps
  Greco accurate (its facts come from Stockfish), while sounding more natural.
- Folders whose name starts with `_` or `.` are **ignored** (that's why the
  `_example/` folder below is skipped). Very short files are ignored too.
- Greco currently blends in up to **3** references per run (about 5,000 characters
  each). Add as many as you like; it rotates through them in alphabetical order.
- The more *varied* and *high-quality* your references, the better — a couple of
  great transcripts beat ten mediocre ones.

## Automated fetching (what Claude set up)

Two references are already seeded:
- **`agadmator-opera-game/`** — Agadmator narrating Morphy's Opera Game (full
  transcript + the game's PGN + metadata). A calm, long-form storytelling sample.
- **`sammychess-kasparov-scotch/`** — SammyChess's fast, energetic Kasparov-Scotch
  video (transcript + metadata). It's a multi-game compilation, so there's no
  single matching PGN — the value here is the *voice*.

Claude can gather more automatically. The helper `_tools/fetch_transcript.py`
downloads a video's transcript (text only — it never downloads the video) via the
`youtube-transcript-api` library:

```powershell
set PYTHONUTF8=1
python commentary_refs\_tools\fetch_transcript.py <video_id_or_url> <out.txt>
```

One-time install of the library (uses this machine's pip workaround):

```powershell
set PYTHONUTF8=1
python -m pip install --user --trusted-host pypi.org --trusted-host files.pythonhosted.org youtube-transcript-api
```

Easiest of all: just give Claude a YouTube link (or say "get a few more Agadmator
and SammyChess videos") and it will create the folder, fetch the transcript, and
attach a matching PGN whenever the video covers a single identifiable game.
