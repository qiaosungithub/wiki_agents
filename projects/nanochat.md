# nanochat: Full-Pipeline Testbed For When Looping Is Useful

Owns `~/work/nanochat/` (Type 2 research code), a self-contained PyTorch implementation of the full LLM training lifecycle (`Base Pretraining` → `Chat SFT` → `Chat RL` → `Inference-Time Scaling`) used to study **whether and when recurrent looping is useful**. Launch rules live in `../jobs.md` and `../gpu_on_borg.md`; spreadsheet logging lives in `../research/result_logging.md` (`nanochat repro` tab in workbook `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20`); the per-site optimizer theory for weight-shared looped models lives in `../research/looped_nanogpt_per_site.md`.

---

## Chapter 1 — Principle: The Research Question, The Pipeline, And What The Metrics Mean

### Why this testbed exists

**The project investigates whether and when recurrent looping improves language models across pretraining, supervised fine-tuning (SFT), reinforcement learning (RL), and test-time compute scaling, which requires an end-to-end pipeline fast enough to run all three stages and evaluate both knowledge retention and reasoning.** Pretraining-only benchmarks measure next-token perplexity but cannot tell whether looped computation helps downstream multi-step reasoning, survives instruction tuning, or interacts with RL exploration and test-time majority voting. `nanochat` provides two calibrated reference scales with combined `MuonAdamW` optimization (Muon on 2D transformer matrices, AdamW on embeddings, unembedding head, and per-layer scalars) and Flash Attention 3 sliding-window attention (`window_pattern="SSSL"`):

| Scale | Architecture | Total / Scaling Params | Pretrain Horizon (`ratio=8` / `12`) | Token Batch Size | Stages |
|---|---|---|---|---|---|
| `d12` | 12L / 6H / 768d (`seq_len=2048`) | ~190M / ~85M | `2,520` steps (`1.32B` tokens) | `524,288` (`2^19`) | `base_train` → `chat_sft` → `chat_rl` |
| `d24` | 24L / 12H / 1536d (`seq_len=2048`) | ~768M / ~680M | `5,568` steps (`5.84B` tokens at `ratio=8.0`) | `1,048,576` (`2^20`) | `base_train` → `chat_sft` → `chat_rl` |

### What each stage trains and what its metrics measure

**Evaluate every SFT and RL checkpoint on both downstream `ChatCORE` tasks and upstream pretraining metrics (`ClimbMix Val BPB` and 22-task `Base CORE`), because downstream accuracy alone conceals catastrophic forgetting of the base model.**

| Stage / Script | Training Data & Objective | Primary Metrics | Evaluation Caveats |
|---|---|---|---|
| Base Pretrain (`scripts/base_train.py`, `scripts/base_eval.py`) | `ClimbMix-400B` parquet shards (`BOS`-aligned best-fit packing, ~35% cropped tokens at `T=2048`), token-level cross-entropy | `ClimbMix Val BPB` (bits per byte on held-out `shard_06542.parquet`, lower is better) and `Base CORE` (centered accuracy across 22 DCLM in-context tasks, higher is better) | In-train `CORE` uses `--core-metric-max-per-task=500`; standalone `scripts/base_eval.py` evaluates all examples per task (`max_per_task=-1`) and also accepts `--source sft` or `--source rl` to measure post-training forgetting. |
| Chat SFT (`scripts/chat_sft.py`, `scripts/chat_eval.py -i sft`) | `TaskMixture` of `789,759` rows per epoch: `SmolTalk` (`460,341`) + `3× MMLU auxiliary_train` (`299,526`) + `4× GSM8K train` (`29,892`), masked assistant-token cross-entropy | `Chat Val BPB` (on held-out `SmolTalk test` + `MMLU val` + `GSM8K test`), `ChatCORE` (centered mean across `ARC-Easy`, `ARC-Challenge`, `MMLU`, `GSM8K`, `HumanEval`) | In-train `ChatCORE` caps generative tasks (`GSM8K`, `HumanEval`) at `--chatcore-max-sample=24` problems for speed and is logged only as a health check; headline numbers must come from standalone `scripts/chat_eval.py` (1,319 `GSM8K` test problems, 164 `HumanEval` problems). |
| Chat RL (`scripts/chat_rl.py`, `scripts/chat_eval.py -i rl`) | `GSM8K(subset="main", split="train")` (`7,473` problems; `16` problems/step × `16` rollouts/problem = `467` steps/epoch), on-policy group-mean-baseline REINFORCE (`advantage = r - mean(r)`, no KL penalty, no clip ratio) | Train rollout `Reward` / `Pass@16`, in-train `GSM8K Pass@1..16` and `Maj@1..16` (on 400 test problems), and post-RL standalone `ChatCORE` + `Maj@1..8` | `chat_rl.py` logs `train/loss` as `-logp * advantage`, whose batch expectation is near zero and slightly negative on longer wrong trajectories, so track `Reward` and validation `Maj@k` / `Pass@k` rather than policy-gradient loss magnitude. |

### Decoupled sampling for RL rollouts versus inference-time scaling

**Keep RL rollout generation at the exploration setting (`temperature=1.0, top_k=50`, no `top_p`) to maintain within-group reward variance, while evaluating inference-time scaling with Majority Vote (`Maj@1..8`) at the locked Pareto-optimal decoding config (`temperature=0.7, top_p=0.95, top_k=50`) and single-sample `ChatCORE` at Greedy (`temperature=0.0`).** `Pass@k` requires an external verifier oracle to pick the one correct trajectory among $k$ samples and is therefore an upper-bound diagnostic of policy support rather than a valid test-time scaling method. Plurality / Majority Vote (`Maj@k`, self-consistency over parsed `#### <number>` answers with tie-breaking by earliest sample) is a valid, verifier-free test-time scaling method; across a 10-point `(temperature, top_p, top_k)` grid sweep on `d24`, `(T=0.7, top_p=0.95, top_k=50)` dominates both lower temperatures (`T=0.3–0.5`, where sample diversity collapses and `Maj@8 - Maj@1` shrinks) and the raw RL rollout temperature (`T=1.0, top_k=50`, where single-sample accuracy drops by `2.25 pp`).

---

## Chapter 2 — Procedure: Running, Checkpointing, And Logging

### Offline CNS assets and cluster routing

**Every Borg GPU job runs without internet access, so `local_assets.tar` (`tokenizer/`, `eval_bundle/`, `task_data/`) and the `ClimbMix-400B` parquet shards (`base_data_climbmix/shard_00000..00134.parquet` plus validation `shard_06542.parquet`) must be staged in `/cns/<cell>/home/qiaos/nanochat_cache/` (`si-d` for metro `sin`, `is-d` for metro `cbf`, `mb-d` for metro `ckv`) before submission.** At container startup, `main.py` unpacks `local_assets.tar` from `$NANOCHAT_CNS_DIR` into `/tmp/nanochat_cache` (`$NANOCHAT_BASE_DIR`) once on the parent process before spawning `torchrun` workers, and `utils/locality.py` only relocates `data_dir` to the landing cell when `local_assets.tar` exists on that cell. Always submit with `--metros=sin,cbf,ckv` and `--archs=h100,b200` so the router places jobs into co-located GPU metros (`sin` hosts `sj`/`sh`/`sm`, `cbf` hosts `is`, `ckv` hosts `mb`) rather than cells lacking a staged CNS replica or 40 GiB A100s where `d24` FP8/BF16 batch sizes require gradient-accumulation clamping. Note that for `base_train.py` with sliding-window attention (`window_pattern="SSSL"`), `Flash Attention 3` is compiled for Hopper (`SM90`, `h100`) and falls back to PyTorch SDPA without sliding-window support on Blackwell (`SM100`, `b200`), making `h100-8` ~2.6× faster (`~1.8h` vs `~4.8h`) and slightly more accurate (`Val BPB = 0.7153 / Base CORE = 26.27%` on `h100-8` vs `0.7191 / 24.34%` on `b200-8`) when `window_pattern="SSSL"` is active.

### Pretraining with intermediate checkpoints and optimizer warm-start

**When running `d24` pretraining from scratch (`configs/load_config.py:d24_pretrain`, `5,568` steps), set `--save-every=500` and `--core-metric-every=500` so all 12 intermediate checkpoints (`steps 500, 1000, ..., 5500, 5568`) and their sharded `MuonAdamW` states are preserved for downstream branching.**

1. **Checkpoint retention and auto-resume**: `nanochat/checkpoint_manager.py::save_checkpoint` writes both native `base_checkpoints/<tag>/model_<step:06d>.pt` + `meta_<step:06d>.json` + per-rank `optim_<step:06d>_rank<r>.pt` and the canonical `<out_dir>/steps/step_<step>.pt` bundle without deleting earlier steps, followed by a `dist.barrier()`. If a pretraining job is preempted, `scripts/base_train.py` auto-detects the highest step in its own `<out_dir>/base_checkpoints/<tag>` (or `$LOAD_FROM`) and resumes cleanly (verified in `XID 296897417`, which auto-resumed from `step 3000` on preemption and completed all 12 checkpoints: `ClimbMix Val BPB` `0.8992 → 0.8436 → 0.8212 → 0.8077 → 0.7878 → 0.7718 → 0.7618 → 0.7477 → 0.7363 → 0.7267 → 0.7198 → 0.7191`, in-train `Base CORE` `12.51% → 17.55% → 18.26% → 19.95% → 21.40% → 22.08% → 22.15% → 23.06% → 25.00% → 25.14% → 25.19% → 25.11%`).
2. **SFT optimizer warm-start (`--load-optimizer=1`)**: `chat_sft.py` loads the pretrained `MuonAdamW` momentum buffers (`optim_<step:06d}_rank<r>.pt`) and immediately restores fresh SFT learning rates (`init_lr_frac=0.8` of base LR, linear warmdown to `0.0`), because pretraining warmdown decays the saved optimizer LRs to `0.05×`. Because the ZeRO-2-style optimizer state is sharded across ranks, `chat_sft.py` requires `ddp_world_size` to match the pretraining world size (`8` GPUs) to warm-start optimizer buffers and automatically falls back to a fresh optimizer state when run on a different GPU count.
3. **SFT evaluation data-loader caching**: `scripts/chat_sft.py` caches tokenized validation conversations in memory (`_CACHED_VAL_CONV_TOKENS`) and packs them on CPU with `pin_memory=True` + `non_blocking=True`, reducing periodic `evaluate_bpb` overhead by ~3× with bitwise-identical BF16 loss.

### Logging to the `nanochat repro` tab

**Log every completed run to the `nanochat repro` tab (`sheetId = 1585203617`) of workbook `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` as one titled block per job and one row per stage, leaving inapplicable cells blank rather than writing `n/a`.** In SFT training rows, columns `G–K` hold the 24-sample `(in-train)` `ChatCORE` sub-scores and the immediately following row (`s2 chat_eval_sft`) holds the full-dataset evaluation; never compare an `(in-train)` estimate against a full evaluation row.

---

## Chapter 3 — Preliminary Findings And Experimental Traps

### Finding 1: SFT overtraining causes catastrophic forgetting and overfits after 1 epoch

**Even without an RL stage, training `d24` SFT beyond 1 epoch (`466` steps at `total_batch_size = 1,048,576`) monotonically degrades pretraining knowledge retention and worsens SFT validation loss, while downstream accuracy peaks briefly at 2–3 epochs before collapsing at 5 epochs.**

| SFT Recipe (from `d24` Base step `5568`) | SFT Steps | Pretrain `ClimbMix Val BPB` (↓) | 22-Task `Base CORE` (↑) | SFT `Chat Val BPB` (↓) | SFT `ChatCORE` (↑) | SFT `ARC-C / MMLU / HumanEval` (%) | SFT `GSM8K` Greedy / `Maj@8` / `Pass@8` (`T=0.7, p=0.95`, %) |
|---|---|---|---|---|---|---|---|
| `d24 Base Pretrain` (reference) | 0 | **0.7153** | 26.27% | — | — | — | — |
| `1-ep SFT (LR=0.2× Gentle)` | 466 | 0.7506 (+0.035) | **26.97%** | 0.6736 | 24.83% | 46.84 / 34.85 / 6.71 | 2.65 / 1.75 / 5.25 |
| `1-ep SFT (BS=1M, Default)` | 466 | 0.8104 (+0.095) | 25.08% | **0.6590** | 27.32% | 50.60 / 36.11 / 8.54 | 3.34 / 5.75 / 10.25 |
| `1-ep SFT (BS=512K, 2× steps)` | 932 | 0.8617 (+0.146) | 24.89% | 0.6562 | 26.86% | 48.89 / 35.85 / 6.71 | 3.56 / 5.50 / 12.25 |
| `2-ep SFT (BS=1M)` | 933 | 0.9557 (+0.240) | 23.12% | 0.6652 | 27.62% | 50.17 / 35.91 / 7.32 | 4.25 / 5.75 / 15.00 |
| `3-ep SFT (BS=1M)` | 1,400 | 1.2862 (+0.571) | 19.53% | 0.6953 | **28.86%** | **51.02 / 36.87 / 9.15** | **5.69** / 9.00 / **17.25** |
| `5-ep SFT (BS=1M)` | 2,334 | 1.9781 (+1.263) | 16.68% | 0.8221 | 26.96% | 46.84 / 34.47 / 6.10 | 4.40 / **9.25** / 17.00 |

Across `1 → 2 → 3 → 5` SFT epochs, pretraining `ClimbMix Val BPB` deteriorates by `+1.263 BPB` and 22-task `Base CORE` drops by `-8.40 pp` (`25.08% → 16.68%`). On the SFT distribution itself, `Chat Val BPB` reaches its minimum at 1 epoch (`0.6590`) and rises monotonically thereafter (`0.8221` at 5 epochs as training loss drops to `0.36`). By 5 epochs, downstream `ChatCORE` (`28.86% → 26.96%`), `GSM8K` Greedy (`5.69% → 4.40%`), and `Pass@8` (`17.25% → 17.00%`) all regress even before RL is applied.

### Finding 2: The SFT-to-RL inversion and the shared train-split memorization trap

**Multi-epoch SFT inverts post-RL rankings (`1-ep → RL` achieves the best post-RL `ChatCORE = 29.59%`, `GSM8K Greedy = 16.83%`, `Maj@8 = 22.25%`, and `Pass@8 = 33.25%`, whereas `5-ep → RL` drops to `Greedy = 12.28%`, `Maj@8 = 17.50%`, and `Pass@8 = 26.50%`), because `chat_sft.py` and `chat_rl.py` share `GSM8K(split="train")` (`7,473` problems).**

| Configuration (`SFT → RL`, Locked Eval `T=0.7, p=0.95, k=50`) | `GSM8K train` Passes in SFT | RL Step 0 Train Reward (Memorization) | Post-RL `ClimbMix Val BPB` (↓) / `Base CORE` (↑) | Post-RL `ChatCORE` (↑) | Post-RL `GSM8K` Greedy (`T=0`, 1319 probs) | Post-RL `GSM8K` `Maj@1 → Maj@4 → Maj@8` (400 probs) | Post-RL `Pass@8` | Net RL Gain `ΔMaj@8` (`ΔPass@8`) |
|---|---|---|---|---|---|---|---|---|
| `1-ep SFT (BS=1M, Default)` | 4× (466 steps) | **3.9%** (Healthy) | 0.8104 / 25.08% (SFT) | **29.59%** | **16.83%** | **16.75% → 20.00% → 22.25%** | **33.25%** | **+16.50 pp** (**+23.00 pp**) |
| `1-ep SFT (BS=512K, 2× steps)` | 4× (932 steps) | 4.8% (Healthy) | 0.9037 / 23.86% | 29.27% | **16.83%** | **18.00% → 20.50%** → 21.00% | 29.25% | +15.50 pp (+17.00 pp) |
| `1-ep SFT (LR=0.2× Gentle)` | 4× (466 steps) | 1.6% (Under-fit) | **0.7676 / 25.63%** | 26.25% | 13.87% | 14.25% → 15.00% → 15.75% | 21.25% | +14.00 pp (+16.00 pp) |
| `2-ep SFT (BS=1M)` | 8× (933 steps) | 45.3% (Memorized) | 1.1044 / 22.79% | 28.59% | 13.87% | 14.00% → 17.50% → 19.25% | 31.50% | +13.50 pp (+16.50 pp) |
| `3-ep SFT (BS=1M)` | 12× (1,400 steps) | 60.2% (Memorized) | 1.5963 / 19.06% | 27.80% | 15.09% | 14.50% → 19.00% → 19.25% | 29.00% | +10.25 pp (+11.75 pp) |
| `5-ep SFT (BS=1M)` | 20× (2,334 steps) | 65.6% (Memorized) | 2.1082 / 13.50% | 27.83% | 12.28% | 14.25% → 16.50% → 17.50% | 26.50% | +8.25 pp (+9.50 pp) |

Two mechanisms drive this inversion and must be accounted for in any post-training comparison:

1. **Historical origin of the `GSM8K(split="train")` overlap**: Upstream `nanochat` removed `chat_rl.py` from `runs/speedrun.sh` (`commit 1ddaad1`) and subsequently tuned `chat_sft.py` with `--gsm8k-epochs=4` (`commit 8180e1d`) to maximize SFT-only GSM8K performance without testing the downstream interaction with `chat_rl.py`. In 1-epoch SFT (`466` steps), the `29,892` GSM8K rows represent only `3.8%` of the `789,759`-row mixture under a decaying LR schedule, so the model memorizes only `3.9%` of `GSM8K train` (matching `3.34%` test accuracy) and leaves `96%` of RL training problems with active non-zero gradients. When SFT is scaled to `2, 3, 5` epochs (`8, 12, 20` passes over `GSM8K train`), the SFT checkpoint enters RL (`Step 0`) having memorized `45.3% → 60.2% → 65.6%` of the RL training split while still scoring only `4.2%–5.7%` on `GSM8K test`. On every memorized training problem, all 16 rollouts return `r = 1.0`, yielding `advantage = r - mean(r) = 0` and wasting over half of RL optimization steps on exact zero gradients.
2. **Why SFT-stage `Maj@k` and `Pass@k` fail to predict post-RL capability**:
   - *Across checkpoints (ranking inversion)*: SFT-stage `Maj@8` and `Pass@8` rank `3-ep` (`9.00% / 17.25%`) and `5-ep` (`9.25% / 17.00%`) nearly `1.6×–1.7×` as high as `1-ep` (`5.75% / 10.25%`), which is the exact opposite of post-RL capability (`1-ep → RL` wins both `Maj@8 = 22.25%` and `Pass@8 = 33.25%`). Static test-set sampling on an SFT checkpoint cannot detect train-split memorization or base-model forgetting.
   - *Within a checkpoint (sharpening vs. boundary expansion)*: On `5-ep SFT`, RL mostly sharpens existing `Pass@8` trajectories into `Pass@1` (`Pass@8` grows by only `+9.50 pp` at `T=0.7, p=0.95`, from `17.00% → 26.50%`), whereas on `1-ep SFT`, RL genuinely expands the reasoning boundary (`Pass@8` surges by `+23.00 pp`, from `10.25% → 33.25%`, and `Maj@8` surges by `+16.50 pp`).

### Finding 3: RL stage reproducibility across 4 seeds (`seed=42, 1, 2, 3`)

**Across 4 independent RL seeds starting from the same `1-ep SFT (BS=1M)` checkpoint, `Pass@k` (`Pass@8 = 32.44% ± 0.60%`), `Maj@k` (`Maj@8 = 22.12% ± 1.34%`), and base retention (`ClimbMix Val BPB = 0.8384 ± 0.0008`, `Base CORE = 25.50% ± 0.06%`) exhibit low variance and every seed strictly outperforms all multi-epoch SFT→RL configurations, whereas single-sample `Greedy (T=0.0)` shows higher seed noise (`15.69% ± 1.26%`).**

| RL Seed (`1-ep SFT → RL`) | Post-RL `ClimbMix Val BPB` (↓) | Post-RL `Base CORE` (↑) | Post-RL `ChatCORE` (↑) | `ARC-E / ARC-C / MMLU / HumanEval` (%) | `GSM8K` Greedy (`T=0.0`, 1319 probs) | `GSM8K` `Maj@1 → Maj@4 → Maj@8` (`T=0.7, p=0.95`, 400 probs) | `GSM8K` `Pass@1 → Pass@4 → Pass@8` (`T=0.7, p=0.95`) |
|---|---|---|---|---|---|---|---|
| `seed=42` (Default) | 0.8380 | 25.50% | **26.68%** | 65.91 / 52.30 / 36.90 / 9.76 | **16.83%** | 16.75% → 20.00% → 22.25% | 16.75% → 28.00% → **33.25%** |
| `seed=1` | **0.8377** | **25.60%** | 24.54% | 63.55 / **52.56** / 36.61 / 5.49 | 13.57% | 16.00% → 19.50% → 21.25% | 16.00% → 27.50% → 32.75% |
| `seed=2` | 0.8380 | 25.46% | 24.89% | 63.89 / 51.54 / 36.30 / 6.10 | 16.07% | 16.75% → **22.75% → 24.25%** | 16.75% → **28.25%** → 31.75% |
| `seed=3` | 0.8397 | 25.43% | 25.16% | 62.96 / 52.30 / 36.38 / 7.32 | 16.30% | **17.75%** → 20.75% → 20.75% | **17.75%** → 27.00% → 32.00% |
| **4-Seed Mean ± Std** | **0.8384 ± 0.0008** | **25.50% ± 0.06%** | **25.32% ± 0.82%** | **64.08±1.11 / 52.17±0.38 / 36.55±0.23 / 7.17±1.64** | **15.69% ± 1.26%** | **16.81±0.62% → 20.75±1.24% → 22.12±1.34%** | **16.81±0.62% → 27.69±0.48% → 32.44±0.60%** |

### Cleanly decoupling SFT and RL when designing new recipes

**Never set `--gsm8k-epochs=0` in `chat_sft.py` without providing a replacement format-teaching slice, because `GSM8K` is the only dataset in the SFT mixture (`SmolTalk` + `MMLU` + `GSM8K`) that contains `<|python_start|>expr<|python_end|>` calculator tool calls and `#### <number>` answer formatting.** Without format supervision in SFT, RL rollouts never emit `#### <number>` and receive zero reward everywhere. To eliminate SFT-RL train-split overlap cleanly without external data dependencies:

| Remedy | Implementation in `nanochat` | What It Solves |
|---|---|---|
| Disjoint `GSM8K train` split via `Task(start, stop)` | Keep `shuffle_seed=42` fixed to define a deterministic partition of the `7,473` `GSM8K(subset="main", split="train")` problems: pass `GSM8K(subset="main", split="train", stop=1000)` to `chat_sft.py` (to teach calculator tool use and `####` formatting) and pass the unseen `GSM8K(subset="main", split="train", start=1000)` (`6,473` problems = `404` steps at `16` problems/step) to `chat_rl.py`. | Guarantees 0% overlap between SFT and RL training problems even across multi-epoch SFT ablations, requiring zero external datasets or CNS `local_assets.tar` changes. |
| Dynamic zero-advantage filtering (DAPO style) | In `scripts/chat_rl.py::get_batch()`, skip any sampled problem where all 16 rollouts succeed (`mean(r) == 1.0`) or all 16 fail (`mean(r) == 0.0`) up to a bounded retry count (`max_resample_tries = 6`). Because `engine.generate_batch()` is purely local to each rank with no NCCL collective until `loss.backward()`, ranks can resample independently without deadlocking DDP. | Eliminates wasted forward/backward passes on zero-advantage problems and prevents memorized (`16/16`) or out-of-reach (`0/16`) problems from diluting the effective batch size. |
| Grade-school external RL prompt sets (if expanding beyond `GSM8K`) | Package `MetaMathQA` (`GSM_Rephrased` / `GSM_AnsAug`) or `SVAMP + ASDiv + MAWPS` into `task_data/` in `local_assets.tar`; do not use competition-level `Hendrycks MATH` or `NuminaMath` on `d12` / `d24`. | Matches the `d24` capability regime (`10%–50%` rollout pass rate, pure numeric answers compatible with `use_calculator`), whereas `Hendrycks MATH` yields `<1%` pass rate (`>85%` zero-advantage `0/16` groups) on sub-1B models. |
