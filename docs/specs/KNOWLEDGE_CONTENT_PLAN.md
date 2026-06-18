The plan is written and verified (319 lines, full heading structure intact). I checked it against the ask point-by-point: code-free deposit path under `chess_principles\texts\` justified over a dedicated bucket; seed-template `meta.json` for both; 9-column MANIFEST rows; three-tier classification with worked assignments and the conservative default-deny rule; the definition-vs-permission separation made explicit with `TERMINOLOGY_TIERS.md` referenced (not duplicated); CC BY-SA attribution recorded in `meta.json` `pd_basis` + `source_url` with the share-alike note; and the engine-theory section covering Turing/Turochamp through SF16/NNUE, centipawns, and the why-engines-differ hook, with the Shannon/Turing PD-status caveat (post-1930, not assumed PD, paraphrase-only by default).

result: KNOWLEDGE_CONTENT_PLAN.md written to C:\Users\詹天哲\Documents\greco\docs\specs\KNOWLEDGE_CONTENT_PLAN.md — full deposit plan for the `greco-glossary` and `greco-engine-theory` slugs under `chess_principles\texts\`.

---

The plan markdown:

# Knowledge Content Plan — Glossary & Engine-Theory Subfolders

**Status:** spec / not-yet-deposited
**Author:** Greco project
**Date:** 2026-06-15
**Scope:** Two new content deposits into `greco\knowledge\` — a **chess glossary** (definitions only) and a **chess-engine-theory** explainer. This document is the deposit plan; it follows the existing `knowledge\README.md` protocol, `meta.json` schema, and `MANIFEST.md` format exactly. Companion doctrine for the glossary's gating tiers lives in `TERMINOLOGY_TIERS.md` (referenced, **not** duplicated here).

---

## 0. The one hard constraint that shapes everything below

`knowledge.py` hard-codes exactly two top-level buckets:

```python
BUCKETS = ("opening_theory", "chess_principles")   # knowledge.py line 60
```

The loader only scans `<bucket>\texts\<book-slug>\` (`_iter_book_dirs`). **A new top-level `glossary\` or `engine_theory\` folder would be invisible to the indexer.** Therefore both deposits go in as `<book-slug>` folders **inside `chess_principles\texts\`** — the code-free path. This is the same path the existing `greco-seed-principles` slug already uses.

Two slugs:

- `greco-glossary` → `chess_principles\texts\greco-glossary\`
- `greco-engine-theory` → `chess_principles\texts\greco-engine-theory\`

Each is one `text.txt` + one `meta.json`, blank-line-separated paragraphs, ≥200 chars total, each indexable chunk ≥40 prose words and not move-number-dense.

### Narration-injection caveat (decide deliberately)

Both deposits are authored as `author: "Greco project"`. Per `_is_human_authored` (`knowledge.py` lines 589–596), content with an empty author **or** author `"greco project"` (case-insensitive) is:

- **Indexed and `--query`-searchable** — yes.
- **Injected into narrator prompts via `load_knowledge_for_game()`** — **NO** (filtered out, exactly like the seed texts).

This is the correct default for both subfolders:

- The **glossary** is the narrator's *vocabulary reference*, not a quotable corpus passage. It should never be force-fed into a report as a "FEATURED PASSAGE." Authoring it as `"Greco project"` keeps it searchable for tooling/diagnostics while keeping it out of the injection path. **The narrator's permission to USE a glossary term is governed entirely by CODE (the fact-gate), not by retrieval — see §1.4.**
- The **engine-theory** explainer is reference material for *building* Greco's human-vs-engine narration features; it is not period prose to be quoted at the reader. Same rationale.

If, later, you want either deposit to actually reach the narrator as quotable text, that is a `knowledge.py` change (real bucket in `BUCKETS`, new `THEME_QUERIES` keys + `themes_from_game` emission, and a non-`"Greco project"` author or an edit to the human-authored gate) — out of scope for this content drop.

---

# PART A — CHESS GLOSSARY SUBFOLDER (definitions only)

## A.1 Where it lives, and why

**Location:** `greco\knowledge\chess_principles\texts\greco-glossary\`

**Why `chess_principles\texts\` and not a dedicated terminology bucket:**

I considered a dedicated `terminology\` bucket. **Rejected**, because:

1. A new bucket is **not code-free** — it requires editing `BUCKETS` in `knowledge.py`, and to get any retrieval benefit you'd also have to add `THEME_QUERIES` keys and `themes_from_game` routing. That is gratuitous for a reference artifact that, by design (§0 caveat), should **not** be narrator-injected anyway.
2. `chess_principles` is already the catch-all for "strategy / tactics / middlegame / endgame" per the README's bucket rules. A glossary of chess terms is squarely strategy/tactics vocabulary. It belongs there.
3. The `bucket` value the loader uses comes from the **folder location, not the JSON** (`_read_meta`), so dropping the slug under `chess_principles\texts\` automatically and correctly tags every chunk `bucket = "chess_principles"`. No mismatch risk.

So: code-free, semantically correct, and consistent with the existing seed precedent. The glossary is a `<book-slug>` like any other.

### Folder tree (Part A)

```
greco\knowledge\chess_principles\texts\greco-glossary\
├── meta.json
└── text.txt
```

## A.2 Authoring format (so it indexes correctly)

The chunker splits on **blank-line paragraph boundaries** and targets ~380 words/chunk. To make the glossary chunk cleanly and survive the prose filters:

- **One term per paragraph.** Format each entry as a single blank-line-delimited paragraph:

  ```
  Fork. A single piece attacks two or more enemy pieces at once, so the
  opponent cannot save them all. A knight fork that hits the king and queen
  simultaneously is called a royal fork. [Tier A — geometric predicate.]
  ```

- **Write each entry as real prose sentences**, not a `term: gloss` colon stub. `_is_quotable_prose` **drops** a chunk with fewer than 40 prose words (4+-letter lowercase runs), so a glossary that is just `Pin — a pin is...` one-liners risks individual chunks being filtered. Mitigation: the chunker accumulates *multiple* paragraphs up to ~380 words per chunk, so a run of ~6–10 term-paragraphs forms one chunk that easily clears the 40-word prose gate. **Do not** isolate a single 15-word definition into its own chunk; let entries pool.
- **No move-number-dense entries.** `_is_quotable_prose` also drops a chunk with ≥8 numbered moves or where move-notation outweighs prose/8. Define terms in words; avoid illustrative `1. e4 e5 2. Nf3` lines inside the glossary text. If an example move is unavoidable, keep it to a bare SAN token in running prose (e.g. "after Nc3").
- **The three-tier tag is part of the entry text**, written as a trailing bracketed marker: `[Tier A — geometric predicate.]`, `[Tier B — default-deny until detector ships.]`, or `[Tier C — non-falsifiable register.]`. Note `_clean_chunk` strips `[...]` markers **≤80 chars** at index time, so the tier marker is **invisible to FTS search and to any quoted excerpt** — exactly what we want: the tier tag is human/CODE-facing documentation, never narrator-quotable text. (If you ever want the tier searchable, write it as `Tier: B` prose instead of bracketed.)

**Target size: ~150–300 terms.** At one paragraph each, that is a substantial `text.txt` (well over the 200-char stub floor; expect ~3,000–9,000 words → ~10–25 chunks).

## A.3 The definition / permission separation (make it explicit)

**This is the load-bearing doctrine of the glossary.** State it at the top of `text.txt` as a preamble paragraph, and enforce it in design:

> **The glossary defines a term. It does NOT grant permission to apply that term to any given position.** A definition answers "what does *fork* mean?" Permission to write "this move is a fork" about a specific board is decided **in code**, by the fact-gate (`factgate.py` → `certified_claims()`), never by the presence of the word in this glossary. Vocabulary and fact-gating are two separate systems: this file is vocabulary; `factgate.py` and the per-tier detectors are the gate.

Concretely:

- A **Tier A** term (e.g. `fork`) has its meaning here *and* a live geometric predicate in `factgate.py`. The narrator may assert it about a position **only** when the corresponding tag is in that move's `certified` allow-set (e.g. `"fork"` ∈ `GATED_TAGS`). The glossary entry does not change that — it just tells the reader/maintainer what the word means.
- A **Tier B** term (e.g. `tempo`, `initiative`) is defined here but **default-deny**: there is no detector yet, so the narrator is **withheld** from asserting it about a position until a detector ships and (if it licenses a new claim type) the tag is registered in both `GATED_TAGS` and the fact-gate prompt rule. The definition existing in the glossary must **not** be read as a license to use the term.
- A **Tier C** term (e.g. `ambitious`, `enterprising`) asserts no checkable board fact, so it carries no gate — it is free register.

The gating **doctrine**, the Tier-B detection roadmap, and the pacing/sequencing plan for which detectors ship first live in `TERMINOLOGY_TIERS.md`. This plan references that file and does not restate its rules.

## A.4 Three-tier classification — the rule applied to terms

Every glossary entry is tagged with exactly one tier. The classification rule (conservative, default-deny):

- **Tier A — geometric predicate (implemented now).** A clean python-chess board test exists or is trivially buildable. Enters the allow-set when its predicate passes. Examples: pin, skewer, fork, discovered attack, battery, outpost, passed/isolated/doubled/backward pawn, rook lift, infiltration, fianchetto, back-rank weakness, luft, mate threat. (Zugzwang is Tier A but **approximate** — flag it as such in its entry.)
- **Tier B — checkable but compound / engine-assisted (PACED IN, default-deny until a detector ships).** The term *does* make a verifiable claim, but needs a harder detector. **These are not free vocabulary** — withheld from the narrator until a detector exists. Examples: tempo, initiative, compensation, prophylaxis, overloaded/overworked piece, zwischenzug, weak square / hole, space advantage, blockade, minority attack, breakthrough, trebuchet, opposition (distant/diagonal), zugzwang-by-triangulation.
- **Tier C — genuine non-falsifiable register (free).** ONLY words asserting no checkable board fact — aesthetic/judgment register. Examples: ambitious, beautiful, enterprising, calm, a practical try, principled, ugly, committal, double-edged (as mood, not as a measured eval).

**Conservatism rule (verbatim intent):** if a term makes a claim that COULD be checked, it is **Tier B (default-deny)**, never Tier C. No tier other than Tier C is ever described as "use freely."

### Worked tier assignments (representative — not the full 150–300)

| Term | Tier | Note |
|---|---|---|
| pin | A | python-chess `is_pinned`; predicate exists in analyzer |
| skewer | A | royal-alignment template (`detect_royal_alignment`) |
| fork / double attack | A | `creates_fork` → `"fork"` gated tag |
| discovered attack | A | geometric (line-uncovering test) |
| battery | A | same-line doubled heavy/bishop test |
| outpost | A | `is_outpost` → `"outpost"` gated tag |
| passed pawn | A | `is_passed_pawn` → `"passed_pawn"` gated tag |
| isolated pawn | A | file-structure test |
| doubled pawns | A | `_doubled_files` / `detect_doubled_pawns_created` |
| backward pawn | A | structural test (buildable) |
| rook lift | A | `is_rook_lift` → `"rook_lift"` gated tag |
| infiltration | A | rank-penetration test (buildable) |
| fianchetto | A | bishop-on-long-diagonal-from-g2/b2 test |
| back-rank weakness / luft | A | escape-square test |
| mate in one / mate threat | A | `threatens_mate_in_one` → `"mate_in_one_threat"` |
| zugzwang | A* | **approximate** — mark the entry "approximate detector" |
| tempo | B | "Nc3 wins a tempo because it threatens Nxd5" is a CHECKABLE claim — needs a tempo detector; **withheld** |
| initiative | B | checkable-but-compound; no detector yet |
| compensation | B | eval + material gate exists (`detect_sacrifice`) but not generalized; **withheld** as a named claim |
| prophylaxis | B | requires opponent-threat modeling |
| overloaded / overworked piece | B | `detect_overloaded_defender` exists, but surfaced as its own field, not a gated certified tag — **withheld as a "certified" assertion** until registered |
| zwischenzug | B | requires forcing-sequence analysis |
| weak square / hole | B | pawn-control test (buildable, not shipped) |
| space advantage | B | square-count heuristic; needs detector |
| blockade | B | piece-in-front-of-passer test; needs detector |
| minority attack | B | plan-level; hard detector |
| ambitious | C | judgment register, no board claim |
| beautiful / a beautiful idea | C | aesthetic |
| enterprising | C | register |
| calm | C | register |
| a practical try | C | register |
| double-edged (as mood) | C | register only — NOT as a numeric eval claim |

The full deposit assigns a tier to **every** term. Anything ambiguous defaults to **B**.

## A.5 Licensing — three source classes, recorded in `meta.json`

The glossary draws from three legally distinct sources. The corpus's legal convention records provenance in `pd_basis` / `translation_status` (documentation fields — never read by the indexer, but required by the README/MANIFEST protocol). For a **mixed-source** file, record all three classes in `pd_basis` and attribute the CC-BY-SA portion explicitly.

1. **Wikipedia "Glossary of chess" — CC BY-SA (usable WITH attribution).** Any entry adapted from Wikipedia's glossary must be attributed. **How attribution is recorded:** in `meta.json`, set `source_url` to the article and spell out the CC BY-SA obligation in `pd_basis`, including the license name, a link, and the share-alike note. Example value:

   > `"pd_basis": "Mixed sources. Definitions adapted from Wikipedia 'Glossary of chess' (https://en.wikipedia.org/wiki/Glossary_of_chess), licensed CC BY-SA 4.0 — attribution required, derivative shares alike. Public-domain definitions drawn from pre-1931 texts already in this corpus. Remaining definitions are original Greco-authored work released CC0."`

   Also add a one-line attribution paragraph **inside `text.txt`** (top preamble): *"Selected definitions adapted from Wikipedia's 'Glossary of chess', CC BY-SA 4.0."* — so the attribution travels with the content even if `meta.json` is separated from it. **Share-alike note:** because CC BY-SA is share-alike, the *adapted definitions* are not CC0; the file is therefore mixed-license, which `pd_basis` must state. (Greco-original and PD entries remain freely reusable; only the Wikipedia-derived portion carries the SA obligation.)

2. **Public-domain texts already in the corpus (pre-1931).** Definitions paraphrased or quoted from `capablanca-chess-fundamentals` (1921) or other cleared PD works are free; note "public-domain, pre-1931" in `pd_basis`. No per-term attribution legally required, but cite the source work in the entry where you quote it verbatim.

3. **Freshly written / general-knowledge definitions (CC0).** Most entries should be **original Greco-authored** plain-language definitions — like the existing `greco-seed-*` entries. These are CC0, year 2026, `author: "Greco project"`. **Preferred default:** writing definitions fresh avoids the CC BY-SA share-alike entanglement entirely. Lean on this class; reach for Wikipedia only when a term genuinely needs it.

> **Practical recommendation:** author the *maximum* possible share of the 150–300 entries as original CC0 prose (class 3). This keeps the bulk of the file cleanly CC0 and confines the share-alike obligation to a small, clearly-flagged minority of class-1 entries. The fewer Wikipedia-derived entries, the simpler the license posture.

## A.6 `meta.json` TEMPLATE — glossary

```json
{
  "title": "Chess Glossary (Greco narrator vocabulary)",
  "author": "Greco project",
  "year": 2026,
  "language": "en",
  "source_url": "https://en.wikipedia.org/wiki/Glossary_of_chess",
  "pd_basis": "Mixed sources. Most definitions are original Greco-authored work released CC0. Some adapted from Wikipedia 'Glossary of chess' (https://en.wikipedia.org/wiki/Glossary_of_chess), CC BY-SA 4.0 — attribution required and noted in text.txt, derivative shares alike. A few paraphrased from pre-1931 public-domain corpus texts (e.g. Capablanca, Chess Fundamentals, 1921).",
  "translation_status": "Original English — no translation involved.",
  "bucket": "chess_principles",
  "seed_placeholder": true
}
```

Notes:
- `author: "Greco project"` + `year: 2026` follow the seed template (the better template for Greco-authored content). This also means the file is **searchable but not narrator-injected** (§0) — the intended behavior for a vocabulary reference.
- `bucket` must equal `"chess_principles"` to match the folder; the loader uses the folder location regardless, but keep them consistent.
- `seed_placeholder: true` is optional; included to mark this as a Greco-authored reference rather than a period book. Harmless to the loader (never read).
- Only `title`, `author`, `year` are consumed by the index; the rest is legal/registry documentation.

## A.7 MANIFEST.md row — glossary

Add to the **"Texts in the corpus"** table (9 columns: `Slug | Title | Author | Year | Lang | Bucket | PD basis | Translation status | Source`):

```
| `greco-glossary` | Chess Glossary (Greco narrator vocabulary) | Greco project | 2026 | en | chess_principles | Mixed: mostly original CC0; some entries CC BY-SA 4.0 (Wikipedia 'Glossary of chess', attributed in text.txt, share-alike); some paraphrased from pre-1931 PD corpus texts | Original English | Wikipedia 'Glossary of chess' (CC BY-SA 4.0) + Greco-authored |
```

---

# PART B — CHESS ENGINE THEORY SUBFOLDER (markdown explainer)

## B.1 Purpose

Reference material so Greco can **explain engine moves to a human reader** — feeding the Maia / human-vs-engine narration track. This is James's chosen investment **instead of** building a thin Stockfish proxy: rather than just relaying engine numbers, Greco should be able to articulate *why* an engine plays as it does and *why a human wouldn't*. The content is the conceptual backbone for that narration capability.

## B.2 Where it lives, and why

**Location:** `greco\knowledge\chess_principles\texts\greco-engine-theory\`

Same reasoning as the glossary (§A.1): code-free deposit under the existing `chess_principles` bucket; a dedicated `engine_theory\` bucket would require a `BUCKETS` edit and is unnecessary for reference material that should not be narrator-injected by default (§0). Engine theory is "how the analysis tool works," which sits comfortably under the strategy/principles catch-all.

> **Filename note:** the README says `text.txt` (plain UTF-8). The brief calls this a "markdown" deposit. **Resolution:** author the content as markdown-flavored prose but **save it as `text.txt`** so the loader picks it up — the indexer reads `text.txt` only and treats `#`/`##` headings as plain text (they are harmless to FTS). Do **not** name the indexed file `*.md`; the loader won't read it. Keep human-readable `.md` working copies in a `_drafts\` scratch dir if desired (folders starting with `_` are ignored by the loader).

### Folder tree (Part B) — multi-file breakdown

The loader indexes a **single `text.txt`** per slug, so the "multi-file breakdown" is the **section structure inside one `text.txt`**, plus optional non-indexed draft sources alongside. Proposed structure:

```
greco\knowledge\chess_principles\texts\greco-engine-theory\
├── meta.json
├── text.txt                      # the indexed deposit — all sections concatenated, blank-line-separated
└── _drafts\                      # OPTIONAL, NOT indexed (leading underscore)
    ├── 01-history-turing-shannon.md
    ├── 02-search-minimax-alphabeta.md
    ├── 03-quiescence-evaluation.md
    ├── 04-nnue-and-sf16.md
    └── 05-centipawns-and-why-engines-differ.md
```

The five `_drafts\*.md` files are the authoring units; concatenate them (blank-line-separated) into the single `text.txt` that actually gets indexed. This gives a clean multi-file editing workflow without fighting the one-`text.txt`-per-slug loader.

### Section breakdown (the content of `text.txt`)

Each section is blank-line-separated, prose-heavy (≥40 prose words/chunk), and light on numbered move lists (so `_is_quotable_prose` doesn't drop chunks):

1. **History — the paper machines.** Turing / Turochamp (1948) the hand-executed "paper machine"; Shannon (1950) "Programming a Computer for Playing Chess" — evaluation function + minimax, Type A (brute-force) vs Type B (selective) distinction.
2. **Search — minimax and alpha-beta.** Minimax (back values up the tree, max self / min opponent); alpha-beta pruning (same answer, exponentially fewer nodes — the key search optimization).
3. **Quiescence search & evaluation functions.** Quiescence (extend at noisy leaves until quiet; cures the horizon effect); the static evaluation function (historically hand-written: material + king safety + pawn structure + mobility + piece-square tables).
4. **NNUE and Stockfish's modern eval.** NNUE (2020) the efficiently-updatable neural net evaluating positions fast enough for CPU alpha-beta; Stockfish 16 / 2023 **removing the hand-written classical eval entirely**, leaving NNUE as the sole evaluator.
5. **Centipawns & why engines find moves humans don't.** A centipawn is a **unit of advantage** (1/100 of "a pawn's worth of edge"), **not** a physical fraction of a pawn. Engines find inhuman moves via near-exhaustive **forcing search** over a **learned number**, with **no plan and no aesthetic** — the narration hook for the Maia/human-vs-engine track.

## B.3 Sourcing

- **Most is general knowledge → write fresh as original Greco-authored CC0 content.** The history, the search algorithms, the centipawn explanation, and the "why engines differ" framing are all general knowledge and should be authored from scratch in Greco's own words. This is class-3 (CC0, `author: "Greco project"`) — the cleanest license posture and the default for the whole deposit.
- **Where a verbatim public-domain quote would be desirable:** a short quotation from **Shannon's 1950 paper** (evaluation-plus-minimax idea, or the Type A / Type B distinction) or from **Turing's** writing would add authority to the history section. **PD status to verify before quoting verbatim:** Shannon (1950) and Turing-era (1948–1953) writings are **not automatically public domain** under the corpus's pre-1931 rule — they are post-1930 and almost certainly still under copyright. **Do not quote verbatim until status is individually confirmed.** Until then, **paraphrase** (the copyright is on the expression, not the idea). The safe default for this deposit is **100% paraphrase / original prose, CC0** — no verbatim historical quotes unless and until a specific source's PD/permission status is verified.
- **Indexing caution:** keep this text **prose-heavy and light on numbers** — densely numeric passages trip the move-number / sparse-prose filters in `_is_quotable_prose`. Explain centipawns in words; avoid eval tables and numbered move lines inside `text.txt`.

## B.4 `meta.json` TEMPLATE — engine theory

```json
{
  "title": "How Chess Engines Work (Greco engine-theory reference)",
  "author": "Greco project",
  "year": 2026,
  "language": "en",
  "source_url": "",
  "pd_basis": "Original Greco-authored work released CC0. Historical facts are general knowledge stated in original prose; no verbatim third-party text is included. Any future verbatim quotation (e.g. Shannon 1950, Turing) must be license-verified before addition — those works are post-1930 and not assumed public domain.",
  "translation_status": "Original English — no translation involved.",
  "bucket": "chess_principles",
  "seed_placeholder": true
}
```

## B.5 MANIFEST.md row — engine theory

```
| `greco-engine-theory` | How Chess Engines Work (Greco engine-theory reference) | Greco project | 2026 | en | chess_principles | Original Greco-authored work, released CC0. Historical facts in original prose; no verbatim third-party text. Future verbatim quotes (Shannon/Turing) require individual license verification (post-1930, not assumed PD) | Original English | Greco-authored (general knowledge) |
```

---

# PART C — DEPOSIT CHECKLIST (both subfolders, per README protocol)

1. **Create the two slug folders** under `chess_principles\texts\`: `greco-glossary\` and `greco-engine-theory\`, each with `text.txt` + `meta.json`.
2. **Author `text.txt`** per the format rules (UTF-8; blank-line-separated paragraphs; ≥200 chars; each chunk ≥40 prose words, not move-number-dense; glossary one-term-per-paragraph with stripped `[Tier X]` markers; engine-theory prose-heavy, light on numbers; CC BY-SA attribution preamble in the glossary).
3. **Add both MANIFEST.md rows** (§A.7, §B.5) to the "Texts in the corpus" table. No "Excluded" rows needed.
4. **Optionally tick SHOPPING_LIST.md** with the date.
5. **Rebuild + verify** from `greco\`: `python knowledge.py --status` — confirm both books appear and chunk count rose (index auto-rebuilds on the fingerprint change).
6. **Confirm searchability:** `python knowledge.py --query "fork"` and `python knowledge.py --query "centipawn"` should surface the new slugs.

## C.1 What this plan deliberately does NOT do

- Does **not** change `BUCKETS`, `THEME_QUERIES`, `themes_from_game`, or `_is_human_authored`. Both deposits are intentionally searchable-but-not-injected (§0).
- Does **not** duplicate the Tier-gating doctrine or the Tier-B detector roadmap/pacing — those live in `TERMINOLOGY_TIERS.md`.
- Does **not** add any verbatim post-1930 quotation; engine-theory ships as original CC0 prose until any specific quote's license status is verified.

## C.2 Separation-of-concerns summary (the doctrine this plan encodes)

| System | Lives in | Answers |
|---|---|---|
| **Vocabulary** (what a term means) | `greco-glossary\text.txt` (this deposit) | "What is a fork?" |
| **Permission** (may we apply the term to *this* position) | `factgate.py` `certified_claims()` + per-tier detectors | "Is *this move* a fork?" |
| **Tier doctrine** (which terms are gated, how Tier-B is paced in) | `TERMINOLOGY_TIERS.md` | "Why is *tempo* withheld?" |
| **Engine literacy** (how the tool computes its answer) | `greco-engine-theory\text.txt` (this deposit) | "Why did the engine play that, and why wouldn't a human?" |

The glossary supplies words; the code supplies the right to use them about a board. Keeping those two strictly separate is the whole point of the Tier classification — a definition in this file is **never** a license to assert the term, except for Tier C register that asserts no board fact at all.