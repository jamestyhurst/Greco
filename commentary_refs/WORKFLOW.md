# Maintaining the commentary references — preferences & workflow

Accessible, living documentation for how this `commentary_refs` library is built and
extended. Part 1 is **James's preferences (the rules)**; Part 2 is the **proven
working methodology**. Keep both current as we add references or find better methods.

---

## Part 1 — James's preferences (the rules)

1. **Automate the tedium.** Prefer methods that remove repetitive manual steps. The
   point of this library is for Claude to gather and verify references so James
   doesn't have to.
2. **Greco's voice = SammyChess + Agadmator.** Greco's commentary draws directly and
   only from these two styles: SammyChess (fast, punchy, purpose-per-move, "can you
   find it?" beats) and Agadmator (calm, scene-setting, long-form storytelling). Keep
   a **balanced pool** of both. See `GRECO_STYLE.md`.
3. **Real transcripts only — never fabricate.** A commentator's words are only ever
   the real, fetched transcript. Never invent, paraphrase, or "reconstruct" what they
   said. If a transcript can't be fetched, leave a clearly-labelled placeholder; don't
   fill it with guesses.
4. **Style only, never chess facts.** Greco learns voice and pacing from these files.
   Every chess fact (evaluations, best moves, who's winning) comes from the engine.
5. **Complete PGN coverage per video — finish before moving on.** For a multi-game
   compilation, *every game that can be identified gets a verified PGN*, numbered to
   the video's presentation order, **before** adding the next video. A game that
   genuinely isn't in any public database is *documented* (verified opening line +
   "not located" status) — never faked.
6. **Verify, don't trust.** Every PGN is checked move-by-move against the transcript's
   narrated moves AND against a reputable database before it's saved.
7. **Document as we go.** Keep this file and the `README.md` current. New methods,
   gotchas, and preferences get written down here when they're discovered.

---

## Part 2 — Working methodology (how to add a reference)

### A. Pick the video and confirm the channel
- **SammyChess** is `@SammyChess1`. His format is single-player, opening-themed
  multi-game compilations (e.g. "Bobby Fischer's Brilliant Italian Game").
- **Agadmator** is `@agadmator`; mostly single-game story recaps.
- To list a channel's uploads without YouTube's heavy grid freezing the browser: open
  the channel `/videos` page in Chrome, then read the IDs + titles straight from the
  DOM with JavaScript:
  `[...document.querySelectorAll('a[href*="/watch?v="]')]` → return **only** the
  11-character video id and the title. Do **not** return full URLs — URLs/query
  strings trip the privacy filter and the whole result gets blocked.
- **Keep Chrome in the foreground, un-minimized.** Background tabs get throttled by the
  browser; that throttling is what freezes the renderer and disconnects the extension
  on heavy YouTube pages. Foregrounding fixed it.

### B. Fetch the transcript — the method that works
1. In Chrome, navigate to `https://youtubetotranscript.com/transcript?v=<VIDEO_ID>`.
2. Wait ~6 seconds for the Cloudflare "Just a moment…" check to **auto-clear** (it's a
   passive challenge — never try to solve a CAPTCHA), then `get_page_text`.
3. The result page header shows `Author : <channel name>` — **use it to verify the
   channel** before trusting the transcript. (This caught a wrong-channel, music-only
   video during the Fischer round.)
4. Clean the text: drop the site chrome (the "Transcript / Pin video / Copy / Translate"
   header and the "Back To Top / AI Features…" footer) and any mid-article injected ad
   (it can split a sentence — stitch the sentence back together).
5. Auto-captions garble names and terms. Keep the words as-is (the value is the *voice*),
   but record the garbles in `meta.json` (e.g. "Oar Cell" = Ojars Celle, "Viking
   Netherlands" = Wijk aan Zee, "purse defense" = Pirc Defense).

**What does NOT work (don't waste time on these):**
- The code sandbox / `bash` — it's been out of disk space (an infrastructure limit,
  unrelated to James's PC). Not needed for this workflow.
- YouTube's own "Show transcript" panel — the watch page is heavy and freezes the
  renderer; the panel also lazy-loads and is fiddly to trigger reliably.
- `youtubetranscript.com` (different site) — its undocumented API silently returns no
  captions. `web_fetch` on transcript sites only sees the page shell (JS hasn't run).

### C. Identify each game and get a VERIFIED PGN
1. Opponents are named in order in the transcript ("The first opponent is…", "The next
   opponent…", "The penultimate opponent…"). Normalize garbled names.
2. Match each game to a database entry by **player + opening + a few distinctive later
   moves** taken from the narration.
3. Pull a clean, verified PGN from **chessgames.com** via its plain-text endpoint:
   `https://www.chessgames.com/njs/api/game/viewPGN/<GID>` — returns `text/plain` PGN
   that `web_fetch` reads directly. Find the `<GID>` by web-searching the game (the
   chessgames URL is `…/chessgame?gid=<GID>`).
   - 365chess game pages render moves with JavaScript, so `web_fetch` can't read them —
     prefer chessgames for the actual movetext.
4. **Verify** the fetched moves against the transcript's narration before saving.
5. If a game truly isn't in public databases, record it in `meta.json` with its verified
   opening line and a "not located" status. Do **not** reconstruct a full PGN from the
   narration alone (rule 3 + 6).

### D. File layout (mirror the existing folders)
```
commentary_refs/
  <channel>-<topic>/
    transcript.txt                      (required — the real words)
    NN <White> vs <Black> (<event> <year>).pgn   (one per game, 2-digit order prefix)
    meta.json
```
- One folder per video; PGNs numbered `01`, `02`, … in the video's presentation order.
- `meta.json` fields: `title`, `commentator`, `source_url`, `video_id`,
  `channel_verified`, `games_in_order` (with per-game PGN status), `notes` (include the
  caption garbles and any uncertainty).

### E. PGN header block
`Event`, `Site`, `Date`, `Round`, `White`, `Black`, `Result`, `ECO`, `Opening`, then
the movetext. Keep names in full (e.g. "Robert James Fischer").

---

## Quick checklist for a new SammyChess video
- [ ] Confirm it's `@SammyChess1` (transcript page `Author` line).
- [ ] Fetch + clean the real transcript → `transcript.txt`.
- [ ] List the games in presentation order from the narration.
- [ ] For EACH game: identify → pull verified PGN from chessgames → check vs transcript.
- [ ] Any game not locatable → documented in `meta.json`, not faked.
- [ ] `meta.json` + `README.md` updated. Only then move to the next video.
