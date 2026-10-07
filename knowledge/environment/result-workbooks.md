# Experiment Result Workbooks

Owns which workbook and tab each project's results go to: the workbook ids,
the live tab per project, the routing exceptions, the read-only history tabs,
and the column naming that differs between the two EqR tabs. Writing a row
(the transaction, the header re-read, where the row goes) is [result-logging skill](../../harness/skills/result-logging/SKILL.md).
Per-tab column semantics: [knowledge/codebases/vlm-metrics.md](../codebases/vlm-metrics.md), [knowledge/codebases/eqr-jax.md](../codebases/eqr-jax.md).

## Which Tab

| Project | Spreadsheet | Tab |
|---|---|---|
| VLM (PaliGemma / JAX LLaVA) | `1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ` | the cleaned PaliGemma/JAX LLaVA tab |
| `EqR` / `EqR-jax` | `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0` | `EqR-refactored`. `EqR-reproduction` is pre-refactor, read-only history |
| char-LM / torch-rnn | `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0` | `charlm-torchrnn (qiaos)`. Every metric cell is `mean +- sd` over 4 seeds; one cell = one wandb group. Headline columns are the HELD-OUT split; the selection split has its own trailing column. Row format and the `gsheets --` trap: [knowledge/codebases/charlm.md](../codebases/charlm.md) |
| looped nanoGPT (the idea line) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (its own workbook) | `looped nanogpt (cleaned 2)` — the curated research tab for parcae / loopformer / ouro ([knowledge/research/looped_nanogpt_per_site.md](../research/looped_nanogpt_per_site.md)). The superseded `looped nanogpt (cleaned)` tab and the older `looped nanogpt` tab in the same workbook, plus the same-titled tab in `17pvrMbOKOKFiIa-…` and `Parcae unroll-optim (qiaos)` there, are read-only history. |
| MoR (Mixture-of-Recursions recipe on SmolLM-360M, parcae-torch port) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (same workbook as looped nanoGPT) | `MoR SmolLM-360M` (`sheetId = 905260049`, created 2026-10-04) — every MoR-recipe run (configs `mor-smollm-360m-*.yml`, repo MoR-sqa): vanilla, recursive N_r = 2 / 3 / 4, and their per-site (f, w) variants. Row 3 holds the shared recipe once; rows 4–8 are the orange `official baseline` block (MoR paper Table 3, 20B-token rows). E / F are NLL / ppl at the trained depth T = N_r (F = exp(E)); I is the depth sweep D1-D(N_r)-D(2N_r); K is the per-site stepsize f / w (mean over core matrices), blank for plain AdamW rows. Same `[3 seed]` fold rule as below. |
| RR (Retrofitted Recurrence, TinyLlama (4,8,4) train-recurrence-4, etd-rr port) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (same workbook as looped nanoGPT) | `RR TinyLlama-484` (`sheetId = 1406021947`, created 2026-10-05, a format clone of the MoR tab) — every RR run in repo etd-rr (branch retrofit-rr): training runs `rr-tinyllama-484-rec4{,-rhofro-ema,-rhofro-raw}.yml` and downstream eval jobs `rr-eval-*.yml`. Row 3 holds the shared recipe once; rows 4–5 are the orange `official baseline` block (RR paper Appendix Table 3, GSM8K / MATH at test R = 1 / 4 / 32); rows 7–8 are the calibration block (the released rec4 checkpoint through our eval_rr harness, XID 296193527). E / F are the fixed-set val loss / bpb at R = 4 (the train mean recurrence); G / H are GSM8K flexible-extract % and MATH math_verify % at R = 1 / 4 / 32; I is the val depth sweep D1-D4-D32; J / K are the per-site rho_fro / f means, `n/a` for the baseline optimizer. An eval job of one of our trained checkpoints goes directly under its training row as `  ↳ eval of the row above`. Same `[3 seed]` fold rule as below. |
| nanochat (karpathy/nanochat repro: d24 released checkpoints + d12 from scratch, base → SFT → RL, repo `~/work/nanochat`) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (same workbook as looped nanoGPT) | `nanochat repro` (`sheetId = 1585203617`, created 2026-10-05, a format clone of the MoR tab) — every nanochat job (exp names `nanochat-*`, presets in `configs/load_config.py`: `eval_repro` / `sft_repro` / `rl_repro` / `posttrain_repro` / `full_d12_pipeline`). **One row per stage**; one job = one titled block (`<model> <what> (XID …, config …)`), stages `s<k> <stage name>` in order. Row 3 holds the shared recipe once; rows 4–8 are the orange reference block (GPT-2 CORE 0.256525, README leaderboard run 6, and the meta of the released d24 base step 5568 / SFT step 466 checkpoints). D = final train loss (debiased EMA; RL rows: token-level PG loss, reward in L); E = final val bpb (base: ClimbMix val; SFT: chat val mixture); F = CORE (base_eval, 22 DCLM tasks, every example; per-task accuracies in L) or ChatCORE (chat_eval); G–K = ARC-Easy / ARC-Challenge / MMLU / GSM8K / HumanEval % from the full chat_eval. SFT-stage G–K are the in-train ChatCORE estimate (GSM8K / HumanEval capped at 24 problems) and say `(in-train)`; the full eval is the next row. wandb = `n/a` (nanochat runs use `--run dummy`). |

**Every parcae / loopformer / ouro run, and any new nanoGPT-setting run, logs to
the `looped nanogpt (cleaned 2)` tab (`sheetId = 117747425`) of workbook
`1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` by default.** It is the operator's
re-cleaned copy (2026-10-01) of the previous `looped nanogpt (cleaned)` tab and
keeps only the new-weight-recipe blocks and reference baselines worth comparing
against. The superseded `looped nanogpt (cleaned)` tab (`sheetId = 1779859670`)
is retired as of 2026-10-01: do not write to it, and do not take row numbers
from it. The older `looped nanogpt` tab (`sheetId = 642888791`) in the same
workbook and the tab with the title `looped nanogpt` in the EqR workbook are
unpruned history. All of these are read-only. Resolving an old title or the
wrong workbook writes into a frozen tab and nothing errors, and
`looped nanogpt (cleaned)` is a prefix of the live title, so match the FULL
title exactly. Pick the workbook by ID, then the tab by exact title
(`looped nanogpt (cleaned 2)`).
Three exceptions log to their own tab of the same workbook, never to
`looped nanogpt (cleaned 2)`: a MoR-recipe run (SmolLM-360M, `mor-smollm-360m-*`
configs) goes to `MoR SmolLM-360M`, an RR run (etd-rr, `rr-tinyllama-484-*` /
`rr-eval-*` configs, exp names `rr-*`) goes to `RR TinyLlama-484`, and a nanochat
job (repo `~/work/nanochat`, exp names `nanochat-*`) goes to `nanochat repro`. Their model,
data, budget and eval set share nothing with the nanoGPT rows, so their numbers
are not comparable to them.
Inside the tab, put a new row next to its comparison target ([result-logging skill §Where The Row Goes](../../harness/skills/result-logging/SKILL.md#where-the-row-goes)); a new line of work opens a titled block below the method it belongs to.
The call/loss-diagonal line's own `nanoGPT (qiaos)` tab is a separate line and
stays in the EqR workbook ([knowledge/codebases/nanogpt-depth.md](../codebases/nanogpt-depth.md)).

**Resolve a tab by title, never by gid.** Both workbooks hold a tab with the same
gid for different projects, plus dated backup tabs of each other. A gid writes
into a frozen snapshot nobody reads. A new line of work opens a titled BLOCK at
the bottom of the live tab, as every family there does; not a new tab.

**The two EqR tabs use the same column positions but opposite metric NAMES, so
copying a number by name swaps a 99.2 with a 34.8.** In both tabs I is per-token
and J is whole-board exact; it is the names that trade places. `acc` means
whole-board exact in `EqR-refactored` and `accuracy` means per-token in
`EqR-reproduction`, so the shorter name flips meaning between the two. Map by
position and semantics, never by metric name, and re-derive from the live header
(row 2; row 1 is a banner, and `EqR-refactored`'s banner states the rename).

| Tab | I (per-token) | J (whole-board exact) | columns the other lacks |
|---|---|---|---|
| `EqR-refactored` | `final train/token_acc (SMOOTHED)` | `final train/acc (SMOOTHED)` | S `final train/total_loss`, T `in-train eval: acc / token-acc @ step` |
| `EqR-reproduction` | `final train/accuracy (SMOOTHED)` | `final train/exact_accuracy (SMOOTHED)` | — |
