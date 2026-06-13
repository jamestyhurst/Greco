# Knowledge Corpus — Manifest

The single source of truth for **why each work in this corpus is legally usable**.
Add one row per book when you deposit it. The legal rule (US, as of 2026): only
works first published **1930 or earlier**; a translation carries its own
copyright, so a modern translation of a public-domain original is *not* usable —
record the translator/date or use the original-language text. Chess moves (PGN)
are facts and may be used regardless of era.

See `README.md` for the full deposit protocol.

## Texts in the corpus

| Slug | Title | Author | Year | Lang | Bucket | PD basis | Translation status | Source |
|---|---|---|---|---|---|---|---|---|
| `capablanca-chess-fundamentals` | Chess Fundamentals | José Raúl Capablanca | 1921 | en | chess_principles | First published 1921; US copyright expired (pre-1931) | Original English — safe for verbatim quoting | [Gutenberg #33870](https://www.gutenberg.org/ebooks/33870) |
| `greco-seed-principles` | Chess Principles (Greco reference notes) | Greco project | 2026 | en | chess_principles | Original work, released CC0 by the Greco project | Original English | — (seed placeholder) |
| `greco-seed-openings` | Opening Principles (Greco reference notes) | Greco project | 2026 | en | opening_theory | Original work, released CC0 by the Greco project | Original English | — (seed placeholder) |

> The two `greco-seed-*` rows are **placeholder seed content**, written by the
> Greco project and released CC0, present only so the retrieval system is testable
> before the real public-domain books are acquired. Delete them once the masters
> below are in (and rebuild with `python knowledge.py`).

## Acquisition queue

The prioritised list of what to acquire (with sources, Gutenberg IDs, and the
"opening-theory-first" priority guidance) lives in **`SHOPPING_LIST.md`** — that is
the wishlist; this file is the registry of what's already in. When you acquire a book,
add its row to the table above and check it off in `SHOPPING_LIST.md`.

## Excluded (record anything you considered but could not clear)

| Title | Author | Reason excluded |
|---|---|---|
| _(none yet)_ | | |
