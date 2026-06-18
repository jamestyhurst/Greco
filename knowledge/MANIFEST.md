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
| `chess-generalship-young` | Chess Generalship | Franklin K. Young | 1910 | en | opening_theory | First published 1910; pre-1931, US copyright expired (95-year rule, 2026). | Original English | [Gutenberg #55278](https://www.gutenberg.org/ebooks/55278) |
| `blue-book-of-chess` | The Blue Book of Chess | Howard Staunton (ed.) | 1889 | en | opening_theory | First published 1889 (Staunton-based reprint); pre-1931, US copyright expired. | Original English | [Gutenberg #16377](https://www.gutenberg.org/ebooks/16377) |
| `bird-chess-history` | Chess History and Reminiscences | H. E. Bird | 1893 | en | opening_theory | First published 1893; pre-1931, US copyright expired. | Original English | [Gutenberg #4902](https://www.gutenberg.org/ebooks/4902) |
| `lasker-chess-strategy` | Chess Strategy | Edward Lasker | 1915 | en | chess_principles | First published 1915 (English); pre-1931, US copyright expired. | Original English | [Gutenberg #5614](https://www.gutenberg.org/ebooks/5614) |
| `lasker-chess-and-checkers` | Chess and Checkers: The Way to Mastership | Edward Lasker | 1918 | en | chess_principles | First published 1918 (English); pre-1931, US copyright expired. | Original English | [Gutenberg #4913](https://www.gutenberg.org/ebooks/4913) |
| `freeborough-chess-openings` | Chess Openings, Ancient and Modern | E. Freeborough and Rev. C. E. Ranken | 1896 | en | opening_theory | First published 1889; revised 1896; pre-1931, US copyright expired. | Original English — safe for verbatim quoting. | [archive.org](https://archive.org/details/chessopeningsanc00freerich) |
| `philidor-studies-of-chess` | Studies of Chess | A. D. Philidor (ed. Peter Pratt) | 1803 | en | opening_theory | Original work 1749 (Philidor); 1803 English edition pre-dates 1931 by 122 years, US copyright expired. | 1803 English edition edited by Peter Pratt; pre-1931 — safe for verbatim quoting. | [Gutenberg #78804](https://www.gutenberg.org/ebooks/78804) |
| `morphy-exploits-europe` | The Exploits and Triumphs, in Europe, of Paul Morphy | Frederick Milnes Edge | 1859 | en | opening_theory | First published 1859; pre-1931, US copyright expired. | Original English — safe for verbatim quoting. | [Gutenberg #34180](https://www.gutenberg.org/ebooks/34180) |
| `morphy-games-lowenthal` | Morphy's Games of Chess | Johann Jacob Löwenthal (ed.) | 1860 | en | opening_theory | First published 1860; pre-1931, US copyright expired. | Original English — safe for verbatim quoting. | [archive.org](https://archive.org/details/morphysgamesches00lowe) |

> The two `greco-seed-*` rows are **placeholder seed content**, written by the
> Greco project and released CC0, present only so the retrieval system is testable
> before the real public-domain books are acquired. Delete them once the masters
> below are in (and rebuild with `python knowledge.py`).

## Games in the corpus (PGN — no era restriction)

Chess moves are facts, not copyrightable expression. PGN files may be added regardless of the 1930 rule.

| File | Opening | Annotator | Date | Source |
|---|---|---|---|---|
| `opening_theory/games/alekhine-timoshenko-variation.pgn` | Alekhine Defence, Timoshenko Variation (B02) — 1.e4 Nf6 2.Nc3 d5 3.e5 d4 4.exf6 dxc3 5.fxg7 cxd2+ 6.Bxd2 Bxg7 | Greco / James Hurst | 2026-06-15 | Original annotation; moves are chess facts |

## Acquisition queue

The prioritised list of what to acquire (with sources, Gutenberg IDs, and the
"opening-theory-first" priority guidance) lives in **`SHOPPING_LIST.md`** — that is
the wishlist; this file is the registry of what's already in. When you acquire a book,
add its row to the table above and check it off in `SHOPPING_LIST.md`.

## Excluded (record anything you considered but could not clear)

| Title | Author | Reason excluded |
|---|---|---|
| _(none yet)_ | | |
| Checkmates for Three Pieces (#4542) | W. B. Fishburne | FEN position database, not prose — no value for RAG narrator |
| Checkmates for Four Pieces (#4656) | W. B. Fishburne | FEN position database (18M chars), not prose — excluded |
