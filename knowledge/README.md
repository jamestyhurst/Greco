# Greco Knowledge Corpus — deposit protocol

This folder is Greco's **reference library of public-domain chess books**. At
analysis time, `knowledge.py` searches these texts for passages relevant to the
game being analyzed (its opening, and the tactics/structures the engine detected)
and hands the *actual passage* to the narrator to quote or paraphrase. The books
are never used to train anything — they are retrieved verbatim (this is "RAG",
retrieval-augmented generation), which keeps Greco's promise: *data-back, never
prompt-stuff*.

**Anyone (or any agent, e.g. Cowork) adding content: follow this exactly.** The
pipeline code does not need to change — drop files in the right place, in the
right format, and Greco picks them up automatically on the next run.

---

## 1. Where files go

```
knowledge/
├── opening_theory/
│   ├── texts/                       # books about specific openings
│   │   └── <book-slug>/
│   │       ├── text.txt             # REQUIRED — the cleaned full text, UTF-8
│   │       └── meta.json            # REQUIRED — bibliographic + legal metadata
│   └── games/                       # annotated master games as PGN (any era)
│       └── <whatever>.pgn
├── chess_principles/                # strategy, middlegame, endgame, mastery
│   └── texts/
│       └── <book-slug>/
│           ├── text.txt
│           └── meta.json
├── MANIFEST.md                      # the legal registry — ADD A ROW PER BOOK
└── knowledge.db                     # GENERATED index — do not edit, gitignored
```

- `<book-slug>` is lowercase, ASCII, hyphenated: `capablanca-chess-fundamentals`.
  (ASCII slugs only — the machine path already contains non-ASCII characters, so
  keep public identifiers ASCII and put the real title in `meta.json`.)
- **Which bucket?** A work about openings → `opening_theory/`. A work about
  strategy, tactics, the middlegame, or the endgame → `chess_principles/`.
- Folder names starting with `.` or `_` are ignored (use `_drafts/` for scratch).

## 2. `text.txt` — the content

- **Plain UTF-8 text.** No PDF, no HTML, no DOCX.
- **Cleaned:** strip page headers/footers, running titles, page numbers, and
  scan/OCR artifacts (broken hyphenation, garbled diagrams, stray ligatures).
- **Paragraphs separated by a blank line.** Chapter/section headings on their own
  line. Greco chunks the text on blank-line boundaries, so this matters.
- Leave the prose as written; do **not** modernize or paraphrase. The whole point
  is verbatim quotation.
- A file under ~200 characters is treated as a stub and skipped.

## 3. `meta.json` — the metadata (one per book)

```json
{
  "title": "Chess Fundamentals",
  "author": "José Raúl Capablanca",
  "year": 1921,
  "language": "en",
  "source_url": "https://www.gutenberg.org/ebooks/33870",
  "pd_basis": "First published 1921; US copyright expired (pre-1930).",
  "translation_status": "Original English — safe for verbatim quoting.",
  "bucket": "chess_principles"
}
```

`title`, `author`, `year` are used for the in-report attribution, so get them
right. `year` is the **original publication year** (it drives the legal check).

## 4. Legal boundary — non-negotiable

- Only works **first published in 1930 or earlier** (US 95-year rule, as of 2026;
  the line advances one year every January 1).
- **English originals** (Capablanca 1921, Lasker 1896) are clean for verbatim use.
- **A translation has its own copyright.** A German original (Nimzowitsch, Réti,
  Tarrasch) may be public-domain while a *modern* English translation is not — use
  only a pre-1930 translation, or the original-language text. Record which in
  `translation_status`.
- **Chess moves are facts, not expression** — PGN/game files of any era are fine,
  regardless of the 95-year rule. They go in `opening_theory/games/`.
- If you cannot confirm a work is pre-1931 (or a confirmed public-domain
  translation), **do not add it.** Note the exclusion in `MANIFEST.md` instead.

## 5. After adding files

1. Add a row to `MANIFEST.md` (title, author, year, language, PD basis, source).
2. Run `python knowledge.py --status` from the `greco/` folder to confirm the new
   book is listed and the chunk count went up. (Greco also rebuilds the index
   automatically whenever the texts change, so this step is just verification.)

## 6. Candidate first acquisitions (all public domain)

| Title | Author | Year | Bucket | Note |
|---|---|---|---|---|
| Common Sense in Chess | Emanuel Lasker | 1896 | chess_principles | English original — clean |
| Chess Fundamentals | José Raúl Capablanca | 1921 | chess_principles | English original — clean |
| My System | Aron Nimzowitsch | 1925 | chess_principles | German original PD; verify any English translation's date |
| Modern Ideas in Chess | Richard Réti | 1923 | chess_principles | German original PD; same caveat |
| Handbuch des Schachspiels | Bilguer / von der Lasa | 19th c. | opening_theory | Earliest major opening encyclopedia — firmly PD |

> The two `greco-seed-*` folders currently present hold short, Greco-authored
> placeholder notes (CC0) so the retrieval system works before any real books are
> added. They are safe to leave or delete; once the masters above are in, you can
> remove the seed folders and rebuild.
