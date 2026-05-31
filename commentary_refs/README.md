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
