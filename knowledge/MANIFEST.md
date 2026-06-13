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
| `greco-seed-principles` | Chess Principles (Greco reference notes) | Greco project | 2026 | en | chess_principles | Original work, released CC0 by the Greco project | Original English | — (seed placeholder) |
| `greco-seed-openings` | Opening Principles (Greco reference notes) | Greco project | 2026 | en | opening_theory | Original work, released CC0 by the Greco project | Original English | — (seed placeholder) |

> The two `greco-seed-*` rows are **placeholder seed content**, written by the
> Greco project and released CC0, present only so the retrieval system is testable
> before the real public-domain books are acquired. Delete them once the masters
> below are in (and rebuild with `python knowledge.py`).

## Acquisition queue (confirmed public domain — not yet added)

| Title | Author | Year | Bucket | Legal note |
|---|---|---|---|---|
| Common Sense in Chess | Emanuel Lasker | 1896 | chess_principles | English original; clean for verbatim use |
| Chess Fundamentals | José Raúl Capablanca | 1921 | chess_principles | English original; clean |
| My System | Aron Nimzowitsch | 1925 | chess_principles | German original PD; a modern English translation is **not** PD — use a pre-1930 translation or the German |
| Modern Ideas in Chess | Richard Réti | 1923 | chess_principles | German original PD; same translation caveat |
| Handbuch des Schachspiels | Bilguer / von der Lasa | 19th c. | opening_theory | Earliest major opening encyclopedia; firmly PD |

## Excluded (record anything you considered but could not clear)

| Title | Author | Reason excluded |
|---|---|---|
| _(none yet)_ | | |
