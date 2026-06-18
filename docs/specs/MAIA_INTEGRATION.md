# Maia Integration for Greco — Human-vs-Engine MOVE and LINE Comparison

**Design doc — implementation wave "Maia-1"**
Author: Claude Code · Date: 2026-06-15 · Status: Design / not yet built
Target files: `analyzer.py`, `narrator.py`, `factgate.py`, `web/config.py`, `outputs.py`, `config.example.json` (+ a new `maia.py` engine wrapper)

---

## 0. Executive summary

Greco today computes one source of board truth: **Stockfish** (objective best move + eval), surfaced as typed fields on `MoveAnalysis` and gated into prose by `factgate.certified_claims()`. This integration adds a **second source of truth — Maia** — a neural engine trained on *human* games that predicts what a human of a given rating would actually play.

With both, Greco can do what a strong human commentator does:

- **Per MOVE:** when a player misses Stockfish's best, label whether that best move was **humanly findable** or an **"engine move"** (objectively best, but a human — even a strong one — would rarely find it). Conversely, certify when a mistake was a **predictable human error** (the kind of move humans at that level routinely play).
- **Per LINE:** generate and contrast a **human continuation** (Maia's most-likely line) against the **engine continuation** (Stockfish's PV) over several plies — so the report can say "a human would have gone here; the engine prefers there," and treat deep engine lines as sidelines the way professional annotators do.

The two new claim types — **`engine_move`** and **`predictable_human_error`** (plus the anti-`engine_move` label **`humanly_findable`**) — flow through the *existing* fact-gate whitelist so the narrator may only use the phrase "engine move" when it is machine-certified. This preserves the **data-back, never prompt-stuff** non-negotiable (CLAUDE.md §3 / guide §5.3).

**Three things this wave deliberately does NOT do:** (1) build the settings panel (documented as roadmap only); (2) lock Maia to `nodes=1` (rejected — default is **adaptive** node budgets); (3) ship a thin Stockfish-only "human proxy" (rejected — we go straight to Maia, with a first-principles fallback held in reserve as contingency).

---

## 1. What Maia is, and the realistic Windows reality

### 1.1 What Maia is

Maia is a set of neural network weights for **lc0** (Leela Chess Zero). lc0 is a separate UCI engine built on the Leela/AlphaZero architecture (policy + value heads over a board representation). Stock Leela weights are trained by self-play to be *superhuman*; **Maia weights are instead trained on millions of human games filtered by rating band**, so the network's *policy head* outputs a probability distribution that approximates **"what would a human of rating R play here?"** rather than "what is objectively best."

Two outputs matter to us:

1. **The policy distribution** — for the current position, a probability over legal moves. Maia's top policy move ≈ the move a human at that rating is most likely to play. This is the human-prediction signal.
2. **The value/eval** — Maia, like any lc0 net, also produces an evaluation. It is *not* a substitute for Stockfish's objective eval (Maia is intentionally human-flawed); we keep Stockfish as the objective authority and use Maia's eval only as a secondary, human-perception signal.

Maia ships as **one weight file per rating band**, named by band, e.g. `maia-1100.pb.gz` … `maia-1900.pb.gz` (the publicly trained Maia-1 bands are 1100–1900 in 100-point steps). The stated *target* range is ~600–2600; the honest position is that **the trained Maia-1 bands cover 1100–1900**, and we **clamp** ratings outside that to the nearest available band (a 700-rated player is served by `maia-1100`; a 2400 player by `maia-1900`), recording the clamp so the report and logs are honest about it. (Wider coverage — Maia-2 / per-player Maia — is a future weights swap, not a code change.)

### 1.2 Windows setup — be realistic

This machine has bitten the project before with: a **non-ASCII username** in every path (`C:\Users\詹天哲\...`), an **antivirus that freezes the box on auto-installed software/scheduled tasks** (AVG froze the system on a winget `.cmd` task), a **TLS-intercepting network** that breaks Python HTTPS, and a **Python 3.14 upgrade trap** where launchers calling bare `python` silently died.

Concrete setup, designed around all four:

| Item | Decision | Why / caveat |
|---|---|---|
| **lc0 binary** | Download the official **Windows lc0 release** (a `.zip`, no installer) and unzip into the repo, e.g. `greco\engines\lc0\lc0.exe`. **Pick the CPU/OpenBLAS or DNNL/Eigen build, not the CUDA build,** unless an NVIDIA GPU is confirmed present. | A no-installer zip avoids the AVG auto-install freeze. CPU build avoids a CUDA/cuDNN dependency chain. Download **manually** in a browser, not via a scripted installer ("Manual updates only"). |
| **Maia weights** | Download each band's `.pb.gz` manually; store at `greco\engines\maia\maia-1100.pb.gz` … `maia-1900.pb.gz`. | `.pb.gz` is lc0's gzipped protobuf weight format; lc0 reads it directly, no unzip needed. Manual download sidesteps the TLS-intercept problem that breaks Python downloaders here (use `truststore` if we ever script it). |
| **Path handling** | **All engine/weights paths via `pathlib.Path`, passed to the subprocess as `str(path)`; every file opened `encoding="utf-8"`.** Treat `C:\Users\詹天哲\...` as the default case. Pass weights to lc0 with `--weights="<abs path>"` quoted, or via the `WeightsFile` UCI option. | The non-ASCII username is in the default install path. python-chess's `popen_uci` takes the exe path as a string and spawns via `subprocess`; the make-or-break check is whether lc0 itself accepts a non-ASCII `--weights`/`WeightsFile` path. **Mitigation, and the reason this is low-risk: keep weights under the repo (`greco\engines\maia\…`), which is reachable by an ASCII-relative path even though the absolute path contains the non-ASCII username.** Phase 0 verifies the absolute non-ASCII path first; the repo-relative path is the fallback. |
| **Console window** | Reuse the existing `creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)` trick from `analyzer.open_engine()` (line 31) for the lc0 subprocess too. | Stops a black console popping up under the GUI/exe — same fix already proven for Stockfish. |
| **Launcher** | No change to launcher doctrine — Greco still launches via `venv\Scripts\pythonw`; lc0 is a child subprocess of that Python, inheriting nothing special. | Keeps the 3.14-upgrade-trap fix intact (launchers must call venv python, never bare `python`). |
| **Dependency footprint** | **Zero new Python packages.** lc0 is driven over UCI through the **already-present `python-chess`** (`chess.engine.SimpleEngine.popen_uci`). The cost is **disk + a second subprocess**, not pip. | lc0.exe + DLLs ≈ tens of MB; each Maia band ≈ a few MB; nine bands well under ~100 MB total. No `truststore`/network code needed at runtime once files are in place. The PyInstaller `Greco.spec` build must bundle/locate `engines\` — noted as a build-step follow-up (§9). |

### 1.3 lc0 UCI specifics Greco must handle

lc0 speaks UCI like Stockfish, but with engine-specific options. Note that `analyzer.open_engine(engine_path, retries=3, timeout=20.0)` takes a single positional path and forwards `timeout`/`creationflags` to `popen_uci`; the Maia wrapper mirrors its retry/timeout/`CREATE_NO_WINDOW` shape but **cannot call `open_engine` directly**, because lc0 needs a post-spawn `configure(...)` step (weights + backend) before it is usable. The wrapper must:

1. **Load weights by setting the UCI option** before search:
   `setoption name WeightsFile value C:\Users\詹天哲\Documents\greco\engines\maia\maia-1500.pb.gz`
   (equivalently passable as the `--weights=` command-line arg at spawn). **Switching rating band = pointing `WeightsFile` at a different `.pb.gz`.** **Decision: lazily spawn-and-cache one lc0 process per distinct band used in the game** (usually 1–2, keyed by band), so White and Black at different ratings each get a stable process and we avoid weight-reload churn within a game.
2. **Force the CPU backend explicitly** if no GPU: `setoption name Backend value blas` (or `eigen`/`dnnl` per the downloaded build) so lc0 doesn't try and fail to find CUDA. The exact backend string is confirmed at Phase 0 against the build actually downloaded.
3. **Read the policy distribution.** Two viable routes:
   - **`go nodes N` + `info` parsing (chosen):** run a small search; with `setoption name MultiPV value K` lc0 emits `info ... multipv K ... pv <move> ...` lines and a `bestmove`, giving the top-K moves ranked by the search. For Maia at low nodes this ranking tracks the human policy closely. Driven via python-chess's `engine.analyse(board, limit, multipv=K)`, which returns a clean list of `{pv, score}` dicts.
   - **`VerboseMoveStats` policy dump (richer but brittle):** lc0 can emit per-move policy priors (`P:` values) via verbose stats — the raw human probability per move, exactly the "Maia probability of move X" signal we want. The output format is less stable across lc0 versions, so capture it **only as an optional enrichment behind a try/except** that can never crash a report (same fail-safe posture as `factgate._safe`).
4. **Guarantee the Stockfish best move is in the queried set.** The labels in §5 key off **`maia_best_move_p`** — Maia's probability of *Stockfish's* best move. A genuine engine move is precisely the one Maia ranks low or **off the top-K MultiPV list**, in which case `maia_best_move_p` is *unknown*, not zero. To make the signal sound:
   - Where possible, query Maia with the Stockfish best move **forced into the candidate set** (lc0 supports restricting/seeding search via `searchmoves`/`root_moves`; python-chess exposes `root_moves` on `engine.analyse`). Running a tiny secondary `analyse` with `root_moves=[best_move]` yields Maia's value/visit for that exact move so `maia_best_move_p` is always populated when Maia ran.
   - If, after that, the best move is still genuinely absent/negligible in a sufficiently wide top-K, treat `maia_best_move_p ≈ 0` **only when K was wide enough that absence is meaningful** (record `maia_best_move_off_list=True`); otherwise leave it `None` and let the label predicates abstain (§5.2). This stops a narrow-K miss from masquerading as a certified engine move.
5. **Convert the search ranking into probabilities.** With MultiPV we get an ordering and an lc0 eval per move, not a normalized human probability. **Two-tier approach:** (a) if VerboseMoveStats policy priors are available, use them directly as `p_maia` (`p_estimated=False`); (b) otherwise derive a **softmax over the per-move evals** of the MultiPV set as a proxy, flagged `p_estimated=True` so downstream labels stay conservative on an estimate.
6. **python-chess specifics:** `chess.engine.SimpleEngine.popen_uci(str(lc0_path), timeout=30.0, creationflags=CREATE_NO_WINDOW)`, then `engine.configure({"WeightsFile": str(band_path), "Backend": "blas"})`, then `engine.analyse(board, chess.engine.Limit(nodes=N), multipv=K)`. Use a **generous spawn timeout (≈30 s, vs Stockfish's 20 s)** because loading a net file takes longer than Stockfish's near-instant handshake; keep the same retry loop as `open_engine`.

---

## 2. Why NOT nodes=1 — the adaptive node-budget design

A single-node Maia gives only the raw top policy move; the goal is *thorough human-vs-engine LINE comparison*, and sometimes the human line is the more relevant object than the engine line. A line needs depth, and a slightly-searched Maia gives a more coherent multi-ply human continuation than a pure policy greedy-rollout.

But running deep Maia on every one of ~80 plies would roughly double-or-worse the per-game cost (§6). So the default is **ADAPTIVE**: spend Maia nodes where human-vs-engine contrast is *informative* (mistakes, blunders, sharp/critical moments) and stay cheap where it isn't (forced replies, dead-quiet positions, already-decided games).

### 2.1 The adaptive table (position type → Maia node budget)

The position type is read from facts Greco **already computes** on `MoveAnalysis` (`is_forced`, `classification`, `is_only_good_move`, `still_winning`, `is_sacrifice`/`is_brilliant`, eval swing) and the `tier` already assigned by `triage.py`. Node budgets are deliberately round; tune after first runs.

| # | Position type (from existing fields) | Maia node budget | Trustworthy human-line depth | Justification |
|---|---|---|---|---|
| 1 | **Forced** (`is_forced`, exactly 1 legal move) | **0 — skip Maia entirely** | none | Only one move; "what a human plays" is trivially that move. No human/engine contrast possible. Pure savings. |
| 2 | **Quiet & already decided** (`still_winning` both sides of move, small \|cp_loss\|, low tier) | **1 node** | 1 ply (top policy move only) | Human and engine almost always agree; record the top human move cheaply, no line. |
| 3 | **Normal quiet** (good/best move, tier 0–1, no tactical flags) | **10 nodes** | top-3 moves, no continuation | Enough for a stable top-3 human distribution to answer "was the played move natural?" without a line. |
| 4 | **Inaccuracy** (`classification == "inaccuracy"`, tier 2) | **100 nodes** | top-3 + **2-ply** human line | Worth knowing if the better move was humanly obvious; a short human line shows the plausible human path. |
| 5 | **Mistake / blunder** (`classification in {"mistake","blunder"}`, tier 2–3) | **400 nodes** | top-3 + **up to 4-ply** human line vs engine PV | The core use case: certify `engine_move` vs `humanly_findable` vs `predictable_human_error`, and contrast a multi-ply human line against Stockfish's line. |
| 6 | **Critical / sharp** (`is_only_good_move`, sound/brilliant sacrifice, large eval swing, or `tier == 3`) | **800 nodes** | top-3 + **up to 6-ply** human line vs engine PV | Only-move and sacrifice moments are where humans and engines diverge most; spend the most here. |
| 7 | **Mate-relevant** (mate score before/after) | **400 nodes** | top-3 + human line to mate horizon (≤6 ply) | Did a human have a realistic shot at the mate, or was it engine-only? Same budget as blunders. |

**Honest caveat on line depth (corrected from earlier drafts).** The "human-line depth" column is the depth we are willing to *present as a human line*. At a few hundred nodes, lc0's PV beyond roughly the first 2–3 plies is increasingly shaped by search, not raw human policy — so deep plies are not a pure "what a human would play" signal. The wrapper therefore caps `maia_line_san` at the trustworthy depth above; any further plies are dropped rather than over-claimed. The first ply (the human's most-likely move) is always the strongest signal and is what the per-move labels rely on; the line is supporting colour, judged at its endpoint by Stockfish (`maia_line_eval_cp`).

**Override hook:** a single setting `maia_nodes_override` (§4) replaces the entire table with one fixed node count for *every* non-forced position when set — for users who explicitly want uniform deep human lines everywhere (and accept the cost). Blank = adaptive (this table). Forced positions (#1) are still skipped even under an override, because there is genuinely nothing to compare.

**Why adaptive is the right default:** the table concentrates compute exactly where Greco already concentrates *narration* depth (the `tier` system). Tier-0 "acknowledge-only" moves get 0–1 Maia nodes; tier-3 deep-analysis moves get 800. Maia cost scales with the number of *interesting* moves in a game, not its length — a clean, quiet game costs almost nothing extra; a messy tactical game costs the most exactly where the human-vs-engine story is most worth telling.

---

## 3. The per-ply human-comparison fact block

A new, optional block added to `MoveAnalysis`, populated in the analyzer's second pass and serialized into the narrator fact-packet alongside `certified`. It parallels the existing engine fields rather than replacing them.

### 3.1 New fields on `MoveAnalysis` (add after `refutation_line_san`, the current last field at line 99)

All default to "empty/absent" so a move where Maia was skipped (forced, or Maia unavailable) is simply blank — the truthiness-guarded convention every existing optional field follows.

```python
# --- Human-comparison block (Maia). All optional; empty when Maia skipped/unavailable. ---
maia_rating_band:        Optional[int] = None   # e.g. 1500 — the band actually used for THIS mover
maia_rating_clamped:     bool = False           # True if player's Elo was clamped to nearest band
maia_rating_defaulted:   bool = False           # True if no PGN Elo and the config default was used
maia_top_moves:          List[Dict[str, Any]] = field(default_factory=list)
                                                # ranked: [{san, uci, p_maia, p_estimated(bool), cp_maia}], top-K
maia_best_move_p:        Optional[float] = None # Maia probability of STOCKFISH'S best move (key signal); None if unknown
maia_best_move_off_list: bool = False           # True if SF best was absent from a wide top-K (p≈0, meaningful)
maia_played_p:           Optional[float] = None # Maia probability of the move ACTUALLY played
maia_played_rank:        Optional[int] = None   # rank of the played move in Maia's list (1 = most human); None if off-list
maia_line_san:           str = ""               # numbered SAN of Maia's HUMAN continuation (capped at trustworthy depth)
maia_line_eval_cp:       Optional[int] = None   # Stockfish eval at the END of the Maia human line (White POV)
maia_nodes_used:         int = 0                 # node budget actually spent (for cost logging / transparency)
human_label:             Optional[str] = None    # certified label: 'engine_move' | 'humanly_findable'
                                                #                  | 'predictable_human_error' | None
```

### 3.2 What each piece answers (mapped to the requirements)

- **Stockfish best move + eval** — already present (`best_move_san`, `eval_after_cp`/`mate_after`, `best_pv_san`, `best_line_san`). Unchanged; the human block sits *beside* it.
- **Maia top move(s) + probabilities at the chosen rating** — `maia_top_moves` (the ranked list with `p_maia`), tagged with `maia_rating_band`.
- **The played move's Maia probability + eval** — `maia_played_p` (how human was the actual move?) and its slot in `maia_top_moves` gives `cp_maia`. `maia_played_rank` makes "the 1st / 5th / off-list most human move" expressible.
- **The Maia probability of the engine's best move** — `maia_best_move_p`. **This is the single most important number for labeling** (§5): "Stockfish says Nf6; how likely was a human to find Nf6?" Guaranteed populated when Maia ran (§1.3 item 4), or explicitly `None`/`off_list` so labels abstain rather than guess.
- **Optional Maia continuation LINE alongside the Stockfish line** — `maia_line_san` (the human line, capped at trustworthy depth per §2.1) sits next to the existing `best_line_san` / `best_pv_san` (the engine line). `maia_line_eval_cp` lets the report say "the human line lands at roughly +0.4, the engine line at +1.8" — an honest, Stockfish-judged contrast of where each path leads.

### 3.3 Serialization into the narrator fact-packet (`narrator._move_to_dict`)

Following the three insertion points and the existing conventions (truthiness-guard, try/except fail-safe, never expose key names in prose):

- **Tier 1+ block** (`if tier >= 1`, alongside `eval_before`, `pieces`, `certified` at narrator.py:440–462): emit a compact `human` sub-dict — `band`, `top` (top-3 `{san, p}`), `best_move_p`, `played_p`, `played_rank`, and `label` (the certified human label). This is the human analog of `certified` and belongs where `certified` already lives.
- **Tier 2+ block** (`if tier >= 2`, alongside `best_pv`, `variations` at narrator.py:465–503): add the heavier `human_line` (the `maia_line_san` numbered line + `maia_line_eval_cp`) so the multi-ply human-vs-engine line contrast only loads on deep-analysis moves and never bloats tier-1 payloads.
- Every emission guarded `if move.maia_top_moves:` (skip-safe) and wrapped in `try/except` so a Maia glitch omits the block rather than crashing the report — identical to how `certified` is wrapped today.

**The human line must be quoted through `analyzer.pv_to_numbered_san`** (never hand-numbered), exactly like every other narrator-quotable line, so an illegal Maia move can never leak into prose — and so the variation fact-checker can later treat `maia_line_san` as an *allowed* line (§8).

---

## 4. The `maia_nodes_override` setting and the settings-panel roadmap

### 4.1 The override and companion keys (this wave: config-key + Pydantic plumbing only)

Settings resolve through `web/config.py:resolve_settings()`, which reads `config.json` (via `_load_config()`), applies env fallbacks, and returns a **Pydantic `Settings` model** (`web/config.py:27`). Today that model exposes `engine`, `model`, `reports_dir`, `engine_ok`, `key_ok` (note: the resolved Stockfish path is the `engine` field, not a `stockfish_path` field). Adding a config key is therefore a **two-place edit**: read it in `resolve_settings()` AND add a typed field to the `Settings` model — mirroring how `engine`/`engine_ok` are paired.

New keys for this wave (all config + env fallback, **no panel**):

| Config key | Env fallback | Type / default | `Settings` field(s) to add |
|---|---|---|---|
| `maia_enabled` | `GRECO_MAIA_ENABLED` | bool; default = auto (true iff lc0 + ≥1 weight file are found) | `maia_enabled: bool`, `maia_ok: bool` (mirrors `engine_ok`: lc0 binary present AND ≥1 band present) |
| `maia_nodes_override` | `GRECO_MAIA_NODES` | int or blank; **blank/absent → adaptive** (§2.1 table); **positive int → that fixed node count for every non-forced position** | `maia_nodes_override: Optional[int] = None` |
| `maia_default_rating` | `GRECO_MAIA_DEFAULT_RATING` | int; default `1500` | `maia_default_rating: int = 1500` |
| `lc0_path` | `GRECO_LC0_PATH` | path; default `<repo>/engines/lc0/lc0.exe` | `lc0_path: str = ""` |
| `maia_weights_dir` | `GRECO_MAIA_WEIGHTS_DIR` | path; default `<repo>/engines/maia/` | `maia_weights_dir: str = ""` |

`maia_nodes_override` is validated as a non-negative int (Pydantic does this for free on a typed field); a blank string resolves to `None` = adaptive. `maia_ok` becomes the master gate read by the analyzer (§7 hard fallback). Add the placeholder keys to `config.example.json` (never the real `config.json`, which is gitignored — secrets protocol).

### 4.2 The settings panel is OUT OF SCOPE — roadmap note

**There is no Greco settings panel yet.** Today, settings live in `config.json` and are read by `resolve_settings()`; the desktop GUI writes some of them ad hoc. Building a real panel is a **future wave**, explicitly out of scope here. This wave only adds the **config keys + env fallbacks + Pydantic fields + plumbing**; `maia_nodes_override` is wired so a future panel can expose it with zero core changes.

**Roadmap item — "Greco Settings Panel" (future wave).** When built, it should expose (and persist to `config.json`) at minimum:

| Setting | Type | Default | Notes |
|---|---|---|---|
| Stockfish path | file path | (none) | already in `config.json` (resolved to `Settings.engine`) |
| Anthropic API key | secret string | (none) | already in `config.json`; **never echo/log it** (secrets protocol) — panel writes the user's own key locally |
| Model | string | `claude-sonnet-4-6` | already in `config.json` (validated against `MODELS`) |
| Output folder (reports_dir) | folder path | Documents\Greco Reports | already in `config.json` |
| **lc0 path** | file path | `greco\engines\lc0\lc0.exe` | new — Maia |
| **Maia weights folder** | folder path | `greco\engines\maia\` | new — Maia |
| **Maia rating band** | enum/auto | Auto (from PGN Elo) | new — overrides PGN-derived band when set |
| **maia_nodes_override** | int / blank | blank = adaptive | new — the §2.1 override |
| **Maia enabled** | bool | auto-detect | new — master switch |

This panel is itself a **StayPlus-readiness exercise** (guide §F4 dynamic typed forms + validation): validated typed inputs, a config write, "generic defaults + per-user override." Worth building to contract grade *when its wave comes* — not now.

---

## 5. The certified human-difficulty labels (code-side predicates → allow-set)

These are the heart of the feature: machine-certified labels that license the narrator to use specific human-difficulty language, gated by the **same whitelist mechanism** as the existing six `GATED_TAGS`. The narrator may say **"engine move" ONLY when certified.**

### 5.1 Where the labels live

**Decision: extend `factgate.py`** with a function `human_label(move_analysis) -> Optional[str]` that consumes the already-populated Maia fields, plus three new tags registered in `GATED_TAGS`. Keeping it in `factgate.py` means there is **one fact-gate module** and one prompt rule to maintain — the rule that any new claim type must be added to **both** `GATED_TAGS` and the prompt rule to stay authoritative.

Unlike the existing `certified_claims()` predicates (which take board objects), `human_label` reads the Maia fields already on the `MoveAnalysis` (populated in the second pass, §3). `certified_claims()` is extended to call it under a `_safe(...)` wrapper and add the resulting tag, so any error or `None` silently drops the tag — same posture as every existing tag.

### 5.2 The three labels and their threshold definitions

All thresholds are expressed in the requested currency: **Maia probability of the best move (`maia_best_move_p`)**, **eval gap (`cp_loss`, mover-POV centipawns)**, and **the played move's Maia probability (`maia_played_p`)**. Numbers are starting points to calibrate after first runs; they are deliberately conservative (precision-over-recall, matching the existing fact-gate posture).

Let:
- `p_best` = `maia_best_move_p` (Maia's probability a human plays Stockfish's best move; may be `None` if unknown, or ≈0 with `maia_best_move_off_list=True`)
- `p_played` = `maia_played_p` (Maia's probability of the move actually played)
- `gap` = `cp_loss` (centipawns lost vs best, mover POV — already on `MoveAnalysis`)

**Abstention precondition (applies to all three labels):** emit *no* human label unless `maia_played_rank is not None` (Maia actually ran on this ply — not skipped/forced/unavailable). This is the `_safe`/"absence ≠ false" posture: when Maia didn't run, we say nothing about human difficulty.

**Label A — `engine_move`** *(the best move was objectively best but a human would rarely find it)*
Certified when the player did NOT find the best move AND the best move is humanly obscure:

```
gap  > 100                                   # missing it actually cost >1 pawn (a real miss, not a quiet best)
AND ( (p_best is not None AND p_best < 0.10) # a human at this band plays SF's move <10% of the time, OR
      OR maia_best_move_off_list )           # SF's move was absent from a WIDE top-K (meaningfully p≈0)
AND NOT (best_is_recapture AND p_best is not None AND p_best >= 0.50)
                                             # GUARD: never label an obvious recapture an "engine move"
```

The third clause is the explicit anti-mislabel guard: `MoveAnalysis.best_is_recapture` already flags when Stockfish's best move is a recapture. An only-recapture that any human would make has a *high* `p_best` and must never be certified `engine_move`; the guard refuses the label in that case even if the first two clauses somehow fire. If `p_best` is `None` and `maia_best_move_off_list` is false, the label abstains (we don't know how human the best move was). Interpretation for the narrator: "best was X, but that is an engine move — a player at this level finds it less than one time in ten." Keep the raw probability in the fact block so the model can phrase emphasis; only the boolean tag reaches the gate.

**Label B — `humanly_findable`** *(the missed best move was one a human realistically should have found)*
Certified when the player missed the best move but the best move was human-natural:

```
gap     > 100            # the player genuinely erred (missed best by >1 pawn)
AND p_best is not None    # we actually know how human the best move was
AND p_best >= 0.25        # and a human at this band finds the best move >=25% of the time
```

Interpretation: "this was findable — a quarter of players at your level would have played it." The anti-`engine_move`: it tells the player the miss was *not* excusable as engine depth.

**Label C — `predictable_human_error`** *(the mistake played was itself the typical human move)*
Certified when the player erred AND the move they played was a top human choice:

```
gap       > 100               # a real mistake (>1 pawn lost)
AND p_played is not None
AND p_played >= 0.20          # but the played move is one humans at this band play >=20% of the time
AND maia_played_rank <= 3     # and it was among Maia's top-3 human moves
```

Interpretation: "the move you played is a very human mistake — among the moves a player at your level most often chooses here." The most *coaching-relevant* label (companion/coaching use cases): it separates a freak error from a systematic, level-typical misjudgment.

**Mutual exclusivity & precedence.** A and B are mutually exclusive by their `p_best` thresholds (the 0.10–0.25 band is intentionally a no-label dead zone — neither clearly engine-only nor clearly findable → stay silent, the gate's "absence ≠ false" posture). C can co-occur with A (the best was an engine move *and* the player's reply was a typical human error) — both tags may be certified; the narrator phrases the combination. When the player **played the best move** (`gap` small) no human-difficulty label is emitted — there is no miss to characterize.

### 5.3 Registering the tags (the two mandatory edits)

A new claim type is only assertible if added in **both** places:

1. **`factgate.GATED_TAGS`** (factgate.py:222) — append `"engine_move"`, `"humanly_findable"`, `"predictable_human_error"`. `certified_claims()` adds them via a new `_safe`-wrapped call to `human_label(move_analysis)` (guarded exactly like the existing tags; a `None`/exception drops the tag silently). Because `human_label` needs the Maia fields, the `move_analysis` object (or its Maia fields) is threaded into the call site — the existing board-only signature is preserved and the new data passed alongside.
2. **The fact-gate prompt rule** (`narrator.py:202`, the "Certified claims (the fact-gate)" paragraph) — extend the whitelist sentence to name the three new tags and bind them: *assert "engine move" / "a humanly findable move" / "a typical human mistake at this level" ONLY if the corresponding tag is in this move's `certified` set; if absent, do not characterize the move's human difficulty.* As always, never write a tag/field name in prose.

This keeps the whitelist the **single source of truth**: the narrator is *forbidden* from calling anything an "engine move" unless `engine_move` is certified, and the data backing every certification is the Maia fact block — fully data-back, no prompt-stuffing.

### 5.4 Rating-band selection

1. **Primary:** read `WhiteElo` / `BlackElo` from PGN headers (already parsed into `GameAnalysis.headers`). The *mover's* Elo selects the band per ply (White moves use WhiteElo's band; Black moves use BlackElo's band — they can differ).
2. **Clamp** to the nearest available trained band (1100–1900 in 100s). Use **deterministic** arithmetic that avoids Python's banker's-rounding surprise on `.5` boundaries: `band = max(1100, min(1900, int((elo + 50) // 100) * 100))`. Set `maia_rating_clamped=True` whenever the raw Elo fell outside 1100–1900 (e.g. a 2500 player is analyzed with `maia-1900` — the most human-skilled net we have, with a noted ceiling).
3. **Absent headers:** fall back to `maia_default_rating` (config, default **1500** — a sensible "average club player"). Set `maia_rating_defaulted=True` so the narrator can hedge appropriately ("for a typical club-level player…").
4. **Malformed Elo** (non-integer, empty, `"?"`): treat as absent → default. Parse defensively (`try/except`, the project's standing posture for untrusted input).

---

## 6. Cost — two engines per critical position

### 6.1 Where the cost lands

Stockfish already runs on every position (unchanged). Maia adds a **second engine** only on positions the adaptive table doesn't skip, and only at the table's node budget. The cost is **node-count-bounded**, not wall-clock-fixed, so it scales with how *interesting* the game is.

Rough back-of-envelope for a typical ~40-move (80-ply) game on the CPU lc0 build:

| Move class (typical share of an 80-ply game) | ~plies | Maia nodes each | lc0 cost intuition |
|---|---|---|---|
| Forced (#1) | ~4 | 0 | free |
| Quiet decided (#2) | ~10 | 1 | ~instant |
| Normal quiet (#3) | ~45 | 10 | very cheap |
| Inaccuracy (#4) | ~10 | 100 | cheap |
| Mistake/blunder (#5) | ~8 | 400 | the bulk of the cost |
| Critical/sharp (#6) | ~3 | 800 | most-per-ply |

The total Maia node budget for such a game is dominated by the handful of mistake/critical plies, **not** the 45 quiet ones. On a CPU lc0 build, a single low-node Maia query is sub-second; a few-hundred-node query is on the order of a second or two; the heavy 800-node criticals are the slow part. **Honest estimate: adaptive Maia adds roughly tens of seconds to a couple of minutes per game on a CPU build**, concentrated on ~15–20 "interesting" plies — versus a **multiple-minutes** penalty if every ply got a deep Maia search. (Note the §1.3 best-move-inclusion step adds a small second query on missed-best plies; it is cheap because it searches a single root move.) Calibrate empirically on the first real runs and log `maia_nodes_used` per move to measure.

### 6.2 How adaptive nodes mitigate it (the whole point)

- **Forced and quiet plies — the majority of a game — cost ~0–10 nodes.** A 45-move quiet positional game spends almost nothing on Maia.
- **Spend is proportional to mistakes,** exactly where the human-vs-engine story has value — cost is *aligned with payoff*.
- **`maia_nodes_used` is logged per move**, so after a few games the table can be re-tuned from real timings rather than guesses.
- **The `maia_nodes_override` escape hatch** lets a user who wants uniform deep human lines opt into the higher cost knowingly — the default protects the common case.
- **Process reuse** (one cached lc0 per band, §1.3) avoids repeated weight-load latency — the dominant fixed cost on a net engine. Loading the `.pb.gz` once and reusing it across all of a game's plies is a large saving versus a fresh process per query.

---

## 7. Contingency — if Maia proves unworkable

This is project doctrine; this section references and wires it.

If Maia cannot be made to run acceptably on this machine (GPU/driver problems, lc0 instability, weight-load latency, the non-ASCII `--weights` path defeating lc0, or the build can't bundle `engines\`), Greco must **degrade gracefully to exactly today's behavior** and fall back to a **first-principles human-difficulty model**:

1. **Hard fallback (always safe):** if `maia_ok` is false (lc0/weights absent) or `maia_enabled` is false, **every Maia field stays empty and no human label is emitted.** Greco runs precisely as it does today — the human block is purely additive and truthiness-guarded, so its absence changes nothing. This is the first thing to build and test (the no-Maia baseline that must pass before Maia is wired in).

2. **First-principles human-difficulty model (the doctrinal contingency):** a *code-side* heuristic for "was this best move humanly findable?" built from features Greco already computes — e.g. best move is a quiet retreat / backward move, a deep tactic (long `best_pv` to realize the gain), a hard-to-see piece on the far side of the board, a counterintuitive sacrifice (`is_sacrifice`/`is_brilliant` on the *best* move), a quiet prophylactic move with no immediate point — informed by the planned `greco-engine-theory` deposit under `knowledge\chess_principles\texts\`. It produces the *same* `human_label` tags through the *same* `factgate` gate, so the narrator-facing contract is unchanged — only the *source* of the label differs (heuristic instead of Maia probability).

3. **LLM general knowledge — INTERIM scaffold ONLY, and it STILL passes the fact-gate.** As a stopgap before either Maia or the first-principles model is solid, the model's own sense of "humans rarely find this" may inform *phrasing* — but it may **NOT assert `engine_move` / `humanly_findable` / `predictable_human_error` unless that tag is certified** by code (Maia or first-principles). The whitelist is absolute: an uncertified human-difficulty claim is forbidden in prose exactly like an uncertified fork claim. This honors **data-back, never prompt-stuff** — the LLM scaffolds language, never licenses the claim.

The contingency is clean because all three sources (Maia / first-principles / interim) **converge on the same gated tags and the same fact-block shape.** Swapping the source is an internal change behind a stable interface — the "thin front-ends over a shared core" discipline.

---

## 8. Phased build order (proxy-free — straight to Maia)

There is **no proxy phase**. Each phase ends in something verifiable; nothing here touches the (nonexistent) settings panel.

**Phase 0 — Files on disk, manually, verified by hand.**
Download lc0 (CPU build, no installer) to `greco\engines\lc0\lc0.exe`; download Maia bands `maia-1100…1900.pb.gz` to `greco\engines\maia\`. Manually confirm from a shell that `lc0.exe` starts, accepts `setoption name WeightsFile value <abs .pb.gz>` with a **non-ASCII path**, accepts the chosen CPU `Backend` value, and answers `go nodes 10` with a `bestmove`. **This is the make-or-break Windows/path test — do it before writing any Python.** If the non-ASCII absolute path fails, fall back to the repo-relative `engines\` path. Add `engines\` to `.gitignore` (binaries/weights don't belong in the public repo) and note the manual-download step in the knowledge/MANIFEST-style docs.

**Phase 1 — `maia.py` engine wrapper (no analyzer wiring yet).**
A small module mirroring `analyzer.open_engine` (retry/timeout + `CREATE_NO_WINDOW`, but with the post-spawn `configure({"WeightsFile":…, "Backend":…})` step): `open_maia(lc0_path, weights_path, timeout=30.0)`; a per-band process cache; `query(board, nodes, multipv, sf_best_move=None) -> MaiaResult` returning top-K `{san, uci, p_maia, p_estimated, cp_maia}`, a `best_move_p` (forcing `sf_best_move` into the candidate set per §1.3 item 4), and a depth-capped `line_san`. Implement MultiPV-based probabilities first; add VerboseMoveStats policy priors behind try/except. **All paths `pathlib`, all opens `utf-8`.** Unit-test against a couple of FENs offline. Deliverable: a tested human-move predictor, independent of the report pipeline.

**Phase 2 — Rating-band selection + the no-Maia fallback.**
Implement band selection from `WhiteElo`/`BlackElo` with the deterministic clamp + default + malformed-handling (§5.4), and the **hard fallback** (`maia_ok` false → everything empty, Greco == today). Test that a game with no engine files produces an identical report to current main. Deliverable: the safety net, proven first.

**Phase 3 — `MoveAnalysis` fields + analyzer second-pass population + adaptive table.**
Add the §3.1 fields (after `refutation_line_san`, line 99) and the constructor wiring (analyzer.py ~967–1017). In `analyze_pgn`'s second pass, after computing `classification`/`tier`-relevant facts, consult the adaptive table (§2.1) (respecting `maia_nodes_override`), call `maia.query` at the chosen budget with the Stockfish best move passed in, and populate the human block — all wrapped so a Maia failure leaves the fields empty and the report intact. Log `maia_nodes_used`. Deliverable: fact-complete `MoveAnalysis` objects with human data.

**Phase 4 — The certified labels (`factgate` extension).**
Add `human_label(move_analysis)` and the three tags to `GATED_TAGS`; wire into `certified_claims` via `_safe` (threading the Maia fields to the call site). Extend the fact-gate prompt rule (`narrator.py:202`) to name and bind the three labels. Unit-test the thresholds (§5.2) against constructed `MoveAnalysis` fixtures — including the obvious-recapture guard (a missed-best ply where the best move is a high-`p_best` recapture must NOT certify `engine_move`). Deliverable: machine-certified `engine_move` / `humanly_findable` / `predictable_human_error`, gated.

**Phase 5 — Narrator fact-packet serialization.**
Emit the `human` sub-dict at tier 1+ and `human_line` at tier 2+ in `_move_to_dict` (§3.3), truthiness-guarded + try/except. Quote `maia_line_san` only through `pv_to_numbered_san`. Verify packets on a sample game; confirm the narrator renders "engine move" only when certified. Deliverable: human-vs-engine contrast reaching the page.

**Phase 6 — Cost calibration + config plumbing.**
Read `maia_enabled`, `maia_nodes_override`, `maia_default_rating`, `lc0_path`, `maia_weights_dir` in `resolve_settings()` with env fallbacks AND add the matching typed fields to the `Settings` Pydantic model (incl. `maia_ok`, §4.1). Add placeholder keys to `config.example.json`. Run several real games, read the logged `maia_nodes_used`/timings, and tune the §2.1 table and §5.2 thresholds. Document the future settings-panel roadmap row (§4.2). Deliverable: calibrated, configurable, honestly-costed integration.

**Phase 7 (optional, later) — Variation fact-check awareness + first-principles contingency.**
Teach `outputs.find_unverified_variation_moves` to treat `maia_line_san` as an *allowed* line (so a quoted human line isn't falsely flagged) — the SAN-pooling loop (`outputs.py:378–383`) just needs `allowed |= _san_tokens(getattr(m, "maia_line_san", "") or "")` added, a one-line change. Separately, stub the first-principles fallback model (§7 item 2) behind the same `factgate` interface. Deliverable: the contingency in reserve and clean variation-checking.

---

## 9. Open questions to close before/with Phase 0 (requirements-elicitation, per guide §3.3)

1. **GPU present?** Confirm whether this box has a usable NVIDIA GPU; if not, lock the CPU lc0 build (changes which release to download and the `Backend` option). *(Decide at Phase 0.)*
2. **Non-ASCII `--weights` path:** does the chosen lc0 build accept `C:\Users\詹天哲\...\maia-1500.pb.gz`? If not, the repo-relative `engines\` folder is the mitigation. *(The make-or-break Phase 0 test.)*
3. **Probability source:** is VerboseMoveStats stable on the downloaded lc0 version (true policy priors), or do we rely on the MultiPV-softmax estimate? Drives whether `p_maia` is exact or `p_estimated`. *(Settle in Phase 1.)*
4. **Best-move inclusion mechanism:** confirm the downloaded lc0 honors `root_moves`/`searchmoves` via python-chess so `maia_best_move_p` can always be populated on a missed-best ply (§1.3 item 4). *(Phase 1.)*
5. **Threshold calibration:** the §5.2 numbers (0.10 / 0.25 / 0.20, 100 cp) are first guesses; tune on real games against a human eye for "yes, that really was an engine move." *(Phase 6.)*
6. **Band coverage honesty:** confirm the report/UI language for clamped ratings (a 2400 player gets `maia-1900`) so we never imply Maia models a 2400 directly. *(Phase 2.)*
7. **PyInstaller bundling:** how `Greco.spec` will locate/bundle `engines\` for the frozen build (or whether Maia is desktop-source-only for now). *(Phase 6 / build follow-up.)*

---

**Net:** Maia becomes Greco's second source of board truth — a human-move predictor running as a cached lc0 subprocess alongside Stockfish, queried at adaptive node budgets concentrated on mistakes and critical moments. It populates a new optional human-comparison block on `MoveAnalysis`, certifies three new human-difficulty labels through the existing `factgate` whitelist (so "engine move" is only ever said when machine-proven, and never for an obvious recapture), and contrasts a Maia human line against the Stockfish engine line over several plies — all additive, fail-safe, path-careful for the non-ASCII profile, and degrading cleanly to today's behavior (and to a first-principles fallback) if Maia proves unworkable. The settings panel that would expose `maia_nodes_override` is explicitly a future wave; this design ships the config plumbing (config keys + env fallbacks + typed `Settings` fields) for it.

**Relevant files (all absolute):**
- `C:\Users\詹天哲\Documents\greco\analyzer.py` — `MoveAnalysis` fields after line 99 (§3.1); second-pass population + adaptive table (~920–1017); `open_engine` pattern at line 23 to mirror; `pv_to_numbered_san` at line 171 for the human line.
- `C:\Users\詹天哲\Documents\greco\factgate.py` — `human_label()` + 3 new `GATED_TAGS` at line 222 (§5).
- `C:\Users\詹天哲\Documents\greco\narrator.py` — fact-packet serialization in `_move_to_dict` (tier 1+ at 440–462, tier 2+ at 465–503; §3.3); fact-gate prompt rule at line 202 (§5.3).
- `C:\Users\詹天哲\Documents\greco\web\config.py` — `resolve_settings()` (line 48) + the `Settings` Pydantic model (line 27) for the new config keys and `maia_ok` flag (§4).
- `C:\Users\詹天哲\Documents\greco\outputs.py` — `find_unverified_variation_moves` SAN pool at lines 378–383, add `maia_line_san` (§8 Phase 7).
- `C:\Users\詹天哲\Documents\greco\config.example.json` — add Maia placeholder keys.
- New: `C:\Users\詹天哲\Documents\greco\maia.py` (engine wrapper) and `C:\Users\詹天哲\Documents\greco\engines\` (lc0 + weights, gitignored).
- Contingency corpus: `C:\Users\詹天哲\Documents\greco\knowledge\chess_principles\texts\greco-engine-theory\` (§7).
