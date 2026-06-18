# Knowledge Corpus — Acquisition Shopping List

The **wishlist**: public-domain chess books worth pulling into Greco's corpus, where
to find them, and what to prioritise. This is the file an acquiring agent (e.g.
Cowork) works *from* and keeps *updated*.

> **Two files, two jobs.** This is the shopping list (what to GET and where).
> `MANIFEST.md` is the registry (what's already IN the corpus + its legal basis).
> When you acquire a book: deposit it (see `README.md`), add a `MANIFEST.md` row,
> then check it off **here** with the date.

---

## How to use this file (acquiring agent: read this)

**Workflow per book:**
1. Pick a target below (work top priority first).
2. Confirm it is public domain — first published **1930 or earlier**, OR a
   pre-1931 translation. If you can't confirm, move it to *Excluded* with a note.
3. Acquire + deposit:
   - **Project Gutenberg** → `python tools/fetch_gutenberg.py --id <N> --bucket <b> --slug <s> --title "..." --author "..." --year <Y>` (downloads, strips boilerplate, writes the folder). It **refuses** any year > 1930.
   - **Internet Archive / other** → download the plain-text/OCR, clean it per `README.md` (strip page headers, OCR junk, diagram markers), and write `text.txt` + `meta.json` by hand into the right bucket.
4. Add a `MANIFEST.md` row.
5. `python knowledge.py --status` → confirm the chunk count rose.
6. **Check it off here** (`[x]` + date) and add any new finds you discover.

**Status legend:** `[ ]` wanted · `[~]` in progress · `[x]` acquired (in corpus) · `[!]` blocked/excluded (note why)

---

## ⭐ Priority guidance — READ BEFORE BULK-DOWNLOADING (from the 2026-06-13 A/B test)

An A/B test (Greco's narrator with the corpus OFF vs ON, on a real game) showed that a
strong modern model **already knows general chess principles** and will state them in
its own words whether or not the books are present. So **books of general advice add
little** — the narrator says the same things regardless. The corpus earns its keep on
content the model does *not* reliably know:

1. **Deep OPENING THEORY — HIGHEST VALUE.** Specific lines, variations, and move-by-move
   analysis. The model's deep opening knowledge is fuzzy and error-prone; concrete old
   theory is exactly the gap the corpus fills. **This is the category to prioritise.**
2. **Specific annotated master games & tournament books — HIGH.** Concrete analysis of
   particular games (and their PGN), not general maxims.
3. **Endgame specifics — MEDIUM.** Exact technique and theoretical positions.
4. **General principles / strategy / mastery — LOWER.** Largely redundant with what the
   model already produces. Acquire a *few* of the best (done: Capablanca) for the option
   of verbatim quotation, but **do not bulk-acquire** this category.

> Note on the "quote verbatim" goal: in testing, the narrator tended to *paraphrase with
> attribution* ("as Capablanca observed…") rather than quote exactly, and did so only
> sometimes. Reliable verbatim quoting will likely need a mechanism change (a deterministic
> "featured passage" inserted into the report) — tracked separately. None of that changes
> the priorities above: opening theory and concrete analysis are worth acquiring regardless.

---

## Sources (where to look)
- **Project Gutenberg** — `gutenberg.org`; clean plain text. Chess listing: [subject/1677](https://www.gutenberg.org/ebooks/subject/1677). Best first stop; works with `fetch_gutenberg.py`.
- **Internet Archive** — `archive.org`; scans + OCR (`*_djvu.txt`). Huge for opening theory and tournament books; needs more cleaning.
- **Google Books** — full-view/PD only (pre-1929).
- Always record the original publication year — it drives the legal check.

---

## A. Opening theory — ⭐ HIGHEST PRIORITY  ·  bucket: `opening_theory`

| Status | Title | Author | Year | Lang | Source | Notes |
|---|---|---|---|---|---|---|
| `[x]` | **Chess Openings, Ancient and Modern** | Freeborough & Ranken | 1889/1896 | en | [archive.org](https://archive.org/details/chessopeningsanc00freerich) | **Acquired 2026-06-17.** 92k words; opening_theory bucket. OCR cleaned. |
| `[ ]` | Handbuch des Schachspiels | Bilguer / von der Lasa | 1843–1916 eds | de | [archive.org](https://archive.org/details/handbuchdesscha00schagoog) | The 19th-c. opening encyclopedia; German |
| `[ ]` | Modern Chess Openings, 1st ed. | Griffith & White | 1911 | en | verify (archive.org) | EARLY eds only — later MCO editions are NOT public domain |
| `[x]` | **The Modern Chess Instructor** | Wilhelm Steinitz | 1889 | en | [archive.org](https://archive.org/details/modernchessinstr00steirich) | **Acquired 2026-06-18.** 496k chars; opening_theory bucket. Archive.org djvu OCR; double-spaces collapsed. Part I (1889) + analysis. |
| `[x]` | **Chess Generalship** | Franklin K. Young | 1910 | en | [Gutenberg #55278](https://www.gutenberg.org/ebooks/55278) | **Acquired 2026-06-17.** 40k words; opening_theory bucket |
| `[x]` | **The Chess Openings** | H. E. Bird | 1880 | en | [archive.org](https://archive.org/details/chessopenings00bird) | **Acquired 2026-06-18.** 268k chars; opening_theory bucket. Archive.org djvu OCR; double-spaces collapsed. |
| `[x]` | **The Blue Book of Chess (Staunton-based)** | Howard Staunton (ed.) | 1889 | en | [Gutenberg #16377](https://www.gutenberg.org/ebooks/16377) | **Acquired 2026-06-17.** 103k words; opening_theory bucket |

## B. Annotated master games & tournament books — HIGH  ·  `opening_theory` or `chess_principles` (+ PGN → `opening_theory/games/`)

| Status | Title | Author/Editor | Year | Lang | Source | Notes |
|---|---|---|---|---|---|---|
| `[ ]` | New York 1924 (tournament book) | annot. Alekhine | 1925 | en | verify (archive.org) | Famous deep annotations |
| `[ ]` | Hastings 1895 (tournament book) | — | 1896 | en | verify (archive.org) | Landmark event, annotated |
| `[x]` | **Book of the Sixth American Chess Congress (New York 1889)** | Ed. Wilhelm Steinitz | 1891 | en | [archive.org](https://archive.org/details/booksixthameric00steigoog) | **Acquired 2026-06-18.** 1.04M chars; opening_theory bucket. All 210 games from 1889 NY International tournament, annotated by Steinitz. Archive.org djvu OCR; double-spaces collapsed. |
| `[x]` | **The Exploits of Paul Morphy (Edge)** | Frederick Milnes Edge | 1859 | en | [Gutenberg #34180](https://www.gutenberg.org/ebooks/34180) | **Acquired 2026-06-17.** 54k words; opening_theory bucket. Morphy's games in Europe with narrative. |
| `[x]` | **Morphy's Games of Chess (Löwenthal ed.)** | Johann Jacob Löwenthal (ed.) | 1860 | en | [archive.org](https://archive.org/details/morphysgamesches00lowe) | **Acquired 2026-06-17.** 156k words; opening_theory bucket. OCR cleaned. |
| `[ ]` | Mr. Blackburne's Games at Chess | J. H. Blackburne | 1899 | en | verify (archive.org) | Attacking classics |
| `[x]` | **Chess History and Reminiscences** | H. E. Bird | 1893 | en | [Gutenberg #4902](https://www.gutenberg.org/ebooks/4902) | **Acquired 2026-06-17.** 65k words; opening_theory bucket |
| `[ ]` | British Chess Magazine (pre-1930 vols) | — | 1881– | en | [archive.org](https://archive.org/details/britishchessmaga1882watk) | Periodical: annotated games + theory |

## C. Endgames — MEDIUM  ·  bucket: `chess_principles`

| Status | Title | Author | Year | Lang | Source | Notes |
|---|---|---|---|---|---|---|
| `[ ]` | Theorie und Praxis der Endspiele | Johann Berger | 1890 | de | verify (archive.org) | Classic endgame treatise; German |
| `[ ]` | (endgame sections of Capablanca & Lasker manuals already cover the basics) | — | — | — | — | acquire standalone endgame works only if they add specifics |

## D. Tactics / combinations — MEDIUM  ·  bucket: `chess_principles`

| Status | Title | Author | Year | Lang | Source | Notes |
|---|---|---|---|---|---|---|
| `[x]` | **The Minor Tactics of Chess** | Young & Howell | 1894 | en | [archive.org](https://archive.org/details/minortacticsofch00youn) | **Acquired 2026-06-18.** 235k chars; chess_principles bucket. Archive.org djvu OCR; double-spaces collapsed. |
| `[x]` | **The Major Tactics of Chess** | Young & Howell | 1896 | en | [archive.org](https://archive.org/details/majortacticsofch00younrich) | **Acquired 2026-06-18.** 114k chars; chess_principles bucket. Archive.org djvu OCR; double-spaces collapsed. |

## E. General principles / strategy / mastery — LOWER (model already knows most)  ·  `chess_principles`

| Status | Title | Author | Year | Lang | Source | Notes |
|---|---|---|---|---|---|---|
| `[x]` | **Chess Fundamentals** | José Raúl Capablanca | 1921 | en | [Gutenberg #33870](https://www.gutenberg.org/ebooks/33870) | **Acquired 2026-06-13.** English original |
| `[x]` | **Chess Strategy** | Edward Lasker | 1915 | en | [Gutenberg #5614](https://www.gutenberg.org/ebooks/5614) | **Acquired 2026-06-17.** 81k words; chess_principles bucket |
| `[x]` | **Chess and Checkers: The Way to Mastership** | Edward Lasker | 1918 | en | [Gutenberg #4913](https://www.gutenberg.org/ebooks/4913) | **Acquired 2026-06-17.** 55k words; chess_principles bucket |
| `[x]` | **Common Sense in Chess** | Emanuel Lasker | 1896 | en | [archive.org](https://archive.org/details/commonsenseinche00laskrich) | **Acquired 2026-06-18.** 115k chars; chess_principles bucket. Archive.org djvu OCR; double-spaces collapsed. |
| `[ ]` | The Principles of Chess in Theory and Practice | James Mason | 1894 | en | verify (archive.org) | English original |
| `[ ]` | My System / Mein System | Aron Nimzowitsch | 1925 (de); Eng. trans. Hereford 1929 | de/en | verify | German original PD; the **1929 Hereford English translation** may be PD — confirm before quoting it |
| `[ ]` | Modern Ideas in Chess | Richard Réti | 1923 (Eng. trans.) | en | verify | German 1922; 1923 English translation likely PD — confirm |
| `[ ]` | Lasker's Manual of Chess | Emanuel Lasker | 1927 (English ed.) | en | verify | Borderline; confirm the English edition is pre-1931 |

## Excluded / watch (not yet PD or unconfirmed)

| Title | Author | Reason |
|---|---|---|
| Das Schachspiel (The Game of Chess) | Siegbert Tarrasch | First published **1931** — not PD until **Jan 1, 2027** |
| The Art of Sacrifice in Chess | Rudolf Spielmann | First published **1935** — not PD until **2031** |
| Any *modern* translation of Nimzowitsch/Réti/Tarrasch | — | Modern translations carry their own copyright — use a pre-1931 translation or the original language |

---

## Autonomous search-acquisition session — ideas & queries

For a hands-off "go find and deposit chess books" run, in priority order:

1. **Sweep Gutenberg's chess shelf:** open [gutenberg.org/ebooks/subject/1677](https://www.gutenberg.org/ebooks/subject/1677), list every title, keep those first published ≤ 1930, prioritise opening-theory and annotated-games titles, and `fetch_gutenberg.py --id <N>` each. (The tool refuses anything dated after 1930.)
2. **Mine Internet Archive for opening theory & tournament books** — queries like `chess openings` / `chess tournament book` / `<event> <year>` with `mediatype:texts` and a pre-1931 date filter; grab the `*_djvu.txt`, clean, deposit by hand.
3. **Chase the named targets above** marked "verify" — confirm the year, find the cleanest text, deposit.
4. For every acquisition: confirm PD → deposit → `MANIFEST.md` row → check off here with the date → note anything you excluded and why.
5. **Lean opening-theory-heavy.** Per the priority guidance, a dozen solid opening-theory and annotated-game works are worth more to Greco than fifty general-principles books.
