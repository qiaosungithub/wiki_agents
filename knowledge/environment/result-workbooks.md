# Experiment Result Workbooks

Owns project-to-workbook routing and the current results destinations. Writing
and formatting results is [harness/skills/result-logging/SKILL.md](../../harness/skills/result-logging/SKILL.md).

### Which Tab

**Resolve the project's live tab by exact title rather than gid, and inspect its header before trusting a saved tab name or row number.**

| Project | Spreadsheet | Tab |
|---|---|---|
| VLM (PaliGemma / JAX LLaVA) | `1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ` | The cleaned PaliGemma/JAX LLaVA tab |
| looped nanoGPT (the idea line) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (its own workbook, `Looped Nanogpt`) | `looped nanogpt (cleaned 2)` — the curated research tab for parcae / loopformer / ouro ([knowledge/research/looped_nanogpt_per_site.md](../research/looped_nanogpt_per_site.md)). The superseded `looped nanogpt (cleaned)` tab and the older `looped nanogpt` tab in the same workbook, plus the same-titled tab in `17pvrMbOKOKFiIa-…` and `Parcae unroll-optim (qiaos)` there, are read-only history. |
| MoR (Mixture-of-Recursions recipe on SmolLM-360M, parcae-torch port) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (same workbook as looped nanoGPT) | `MoR SmolLM-360M` (`sheetId = 905260049`, created 2026-10-04) — every MoR-recipe run (configs `mor-smollm-360m-*.yml`, repo MoR-sqa): vanilla, recursive N_r = 2 / 3 / 4, and their per-site (f, w) variants. Row 3 holds the shared recipe once; rows 4–8 are the orange `official baseline` block (MoR paper Table 3, 20B-token rows). E / F are NLL / ppl at the trained depth T = N_r (F = exp(E)); I is the depth sweep D1-D(N_r)-D(2N_r); K is the per-site stepsize f / w (mean over core matrices), blank for plain AdamW rows. Same `[3 seed]` fold rule as below. |
| RR (Retrofitted Recurrence, TinyLlama (4,8,4) train-recurrence-4, etd-rr port) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (same workbook as looped nanoGPT) | `RR TinyLlama-484` (`sheetId = 1406021947`, created 2026-10-05, a format clone of the MoR tab) — every RR run in repo etd-rr (branch retrofit-rr): training runs `rr-tinyllama-484-rec4{,-rhofro-ema,-rhofro-raw}.yml` and downstream eval jobs `rr-eval-*.yml`. Row 3 holds the shared recipe once; rows 4–5 are the orange `official baseline` block (RR paper Appendix Table 3, GSM8K / MATH at test R = 1 / 4 / 32); rows 7–8 are the calibration block (the released rec4 checkpoint through our eval_rr harness, XID 296193527). Columns (since 2026-10-19, operator request: no k= / r= / code names in run labels): the run label is split over A-E in plain language — A input injection between loop passes, B that mechanism's init (what the model starts as, e.g. `99% input (≈ plain model)`, `100% previous pass`), C layer blocks prelude + looped + coda with removed layers noted (e.g. `4 + 8 + 4 (layers 4-9 removed)`, `10 + 8 + 4 (none removed)`, `22 (no loop)`), D train depth sampling as distribution + mean depth (`fixed N` / `Poisson, mean N` / `Poisson-lognormal, mean N, no curriculum` / `Poisson-lognormal, curriculum mean 2 → N`; RR train recurrence r = mean depth r + 1), E note (bold `RR baseline` on every RR-recipe row; otherwise only the one variable that separates sibling rows); no step count in A-E (G has it). Then F Setting, G Steps, H Equiv. FLOPs, I train loss, J val loss, K / L GSM8K flex / strict, M MATH, N val depth sweep, O Status, P val bpb, Q flatboard, R wandb. Block-title rows and `  ↳` sub-rows keep their text in A with B-E empty; code names (CtL, mod, ETD, ...) stay only in F and the block titles. An eval job of one of our trained checkpoints goes directly under its training row as `  ↳ eval of the row above`. Same `[3 seed]` fold rule as below. |
| nanochat (karpathy/nanochat repro: d24 released checkpoints + d12 from scratch, base → SFT → RL, repo `~/work/nanochat`) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (same workbook as looped nanoGPT) | `nanochat repro` (`sheetId = 1585203617`, created 2026-10-05, a format clone of the MoR tab) — every nanochat job (exp names `nanochat-*`, presets in `configs/load_config.py`: `eval_repro` / `sft_repro` / `rl_repro` / `posttrain_repro` / `full_d12_pipeline`). **One row per stage**; one job = one titled block (`<model> <what> (XID …, config …)`), stages `s<k> <stage name>` in order. Row 3 holds the shared recipe once; rows 4–8 are the orange reference block (GPT-2 CORE 0.256525, README leaderboard run 6, and the meta of the released d24 base step 5568 / SFT step 466 checkpoints). D = final train loss (debiased EMA; RL rows: token-level PG loss, reward in L); E = final val bpb (base: ClimbMix val; SFT: chat val mixture); F = CORE (base_eval, 22 DCLM tasks, every example; per-task accuracies in L) or ChatCORE (chat_eval); G–K = ARC-Easy / ARC-Challenge / MMLU / GSM8K / HumanEval % from the full chat_eval. SFT-stage G–K are the in-train ChatCORE estimate (GSM8K / HumanEval capped at 24 problems) and say `(in-train)`; the full eval is the next row. wandb = `n/a` (nanochat runs use `--run dummy`). |

**Every parcae / loopformer / ouro run, and any new nanoGPT-setting run, logs to
the `looped nanogpt (cleaned 2)` tab (`sheetId = 117747425`) of workbook
`1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` by default.** It is the operator's
re-cleaned copy (2026-10-01) of the previous `looped nanogpt (cleaned)` tab and
keeps only the new-weight-recipe blocks and reference baselines worth comparing
against
([link](https://docs.google.com/spreadsheets/d/1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20/edit#gid=117747425)).
The superseded `looped nanogpt (cleaned)` tab (`sheetId = 1779859670`) is
retired as of 2026-10-01: do not write to it, and do not take row numbers from
it. The older `looped nanogpt` tab (`sheetId = 642888791`) in the same workbook,
and the `looped nanogpt` and `Parcae unroll-optim (qiaos)` tabs in the EqR
workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, are unpruned history.
All of these are read-only. Resolving an old title or the wrong workbook writes
into a frozen tab and nothing errors, and `looped nanogpt (cleaned)` is a prefix
of the live title, so match the FULL title exactly. Pick the workbook by ID,
then the tab by exact title (`looped nanogpt (cleaned 2)`).

Three exceptions log to their own tab of the same workbook, never to
`looped nanogpt (cleaned 2)`: a MoR-recipe run (SmolLM-360M, `mor-smollm-360m-*`
configs) goes to `MoR SmolLM-360M`, an RR run (etd-rr, `rr-tinyllama-484-*` /
`rr-eval-*` configs, exp names `rr-*`) goes to `RR TinyLlama-484`, and a nanochat
job (repo `~/work/nanochat`, exp names `nanochat-*`) goes to `nanochat repro`.
Their model, data, budget and eval set share nothing with the nanoGPT rows, so
their numbers are not comparable to them.

The call/loss-diagonal line's `nanoGPT (qiaos)` tab is a separate line and
stays in the EqR workbook. The current ideas are
[knowledge/research/looped_nanogpt_per_site.md](../research/looped_nanogpt_per_site.md)
and [knowledge/research/midtrain_loop_adaptation.md](../research/midtrain_loop_adaptation.md) (the RR line).

- The workbooks also hold dated backup tabs, so a stale gid or name can write into a frozen snapshot nobody reads.
- Inside the tab, put a new row next to its comparison target ([result-logging skill §Choose the row before the values](../../harness/skills/result-logging/SKILL.md#choose-the-row-before-the-values)); a new line of work opens a titled block below the method it belongs to, not a new tab.
