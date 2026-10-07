---
name: nanochat-runs
description: Stage offline assets for, submit, checkpoint, warm-start, and log nanochat Base, SFT, and RL jobs on Borg GPUs, one titled block per job and one row per stage in the nanochat repro tab.
---

# nanochat Runs — Running, Checkpointing, And Logging

This skill relies on [the nanochat knowledge page](../../../knowledge/codebases/nanochat.md) for the
pipeline, the two reference scales, what each stage's metrics measure, the
decoupled sampling settings, and the findings so far, including how to keep SFT
and RL training problems disjoint in a new recipe. Launch rules live in
[knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md) and [gpu-on-borg skill](../gpu-on-borg/SKILL.md); spreadsheet logging lives in
[result-logging skill](../result-logging/SKILL.md) (`nanochat repro` tab in workbook
`1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20`), and which workbook and tab a
result goes to is [knowledge/environment/result-workbooks.md §Which Tab](../../../knowledge/environment/result-workbooks.md#which-tab).

## Offline CNS assets and cluster routing

**Every Borg GPU job runs without internet access, so `local_assets.tar` (`tokenizer/`, `eval_bundle/`, `task_data/`) and the `ClimbMix-400B` parquet shards (`base_data_climbmix/shard_00000..00134.parquet` plus validation `shard_06542.parquet`) must be staged in `/cns/<cell>/home/qiaos/nanochat_cache/` (`si-d` for metro `sin`, `is-d` for metro `cbf`, `mb-d` for metro `ckv`) before submission.** At container startup, `main.py` unpacks `local_assets.tar` from `$NANOCHAT_CNS_DIR` into `/tmp/nanochat_cache` (`$NANOCHAT_BASE_DIR`) once on the parent process before spawning `torchrun` workers, and `utils/locality.py` only relocates `data_dir` to the landing cell when `local_assets.tar` exists on that cell. Always submit with `--metros=sin,cbf,ckv` and `--archs=h100,b200` so the router places jobs into co-located GPU metros (`sin` hosts `sj`/`sh`/`sm`, `cbf` hosts `is`, `ckv` hosts `mb`) rather than cells lacking a staged CNS replica or 40 GiB A100s where `d24` FP8/BF16 batch sizes require gradient-accumulation clamping. Note that for `base_train.py` with sliding-window attention (`window_pattern="SSSL"`), `Flash Attention 3` is compiled for Hopper (`SM90`, `h100`) and falls back to PyTorch SDPA without sliding-window support on Blackwell (`SM100`, `b200`), making `h100-8` ~2.6× faster (`~1.8h` vs `~4.8h`) and slightly more accurate (`Val BPB = 0.7153 / Base CORE = 26.27%` on `h100-8` vs `0.7191 / 24.34%` on `b200-8`) when `window_pattern="SSSL"` is active.

## Pretraining with intermediate checkpoints and optimizer warm-start

**When running `d24` pretraining from scratch (`configs/load_config.py:d24_pretrain`, `5,568` steps), set `--save-every=500` and `--core-metric-every=500` so all 12 intermediate checkpoints (`steps 500, 1000, ..., 5500, 5568`) and their sharded `MuonAdamW` states are preserved for downstream branching.**

1. **Checkpoint retention and auto-resume**: `nanochat/checkpoint_manager.py::save_checkpoint` writes both native `base_checkpoints/<tag>/model_<step:06d>.pt` + `meta_<step:06d>.json` + per-rank `optim_<step:06d>_rank<r>.pt` and the canonical `<out_dir>/steps/step_<step>.pt` bundle without deleting earlier steps, followed by a `dist.barrier()`. If a pretraining job is preempted, `scripts/base_train.py` auto-detects the highest step in its own `<out_dir>/base_checkpoints/<tag>` (or `$LOAD_FROM`) and resumes cleanly (verified in `XID 296897417`, which auto-resumed from `step 3000` on preemption and completed all 12 checkpoints: `ClimbMix Val BPB` `0.8992 → 0.8436 → 0.8212 → 0.8077 → 0.7878 → 0.7718 → 0.7618 → 0.7477 → 0.7363 → 0.7267 → 0.7198 → 0.7191`, in-train `Base CORE` `12.51% → 17.55% → 18.26% → 19.95% → 21.40% → 22.08% → 22.15% → 23.06% → 25.00% → 25.14% → 25.19% → 25.11%`).
2. **SFT optimizer warm-start (`--load-optimizer=1`)**: `chat_sft.py` loads the pretrained `MuonAdamW` momentum buffers (`optim_<step:06d}_rank<r>.pt`) and immediately restores fresh SFT learning rates (`init_lr_frac=0.8` of base LR, linear warmdown to `0.0`), because pretraining warmdown decays the saved optimizer LRs to `0.05×`. Because the ZeRO-2-style optimizer state is sharded across ranks, `chat_sft.py` requires `ddp_world_size` to match the pretraining world size (`8` GPUs) to warm-start optimizer buffers and automatically falls back to a fresh optimizer state when run on a different GPU count.
3. **SFT evaluation data-loader caching**: `scripts/chat_sft.py` caches tokenized validation conversations in memory (`_CACHED_VAL_CONV_TOKENS`) and packs them on CPU with `pin_memory=True` + `non_blocking=True`, reducing periodic `evaluate_bpb` overhead by ~3× with bitwise-identical BF16 loss.

## Logging to the `nanochat repro` tab

**Log every completed run to the `nanochat repro` tab (`sheetId = 1585203617`) of workbook `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` as one titled block per job and one row per stage, leaving inapplicable cells blank rather than writing `n/a`.** In SFT training rows, columns `G–K` hold the 24-sample `(in-train)` `ChatCORE` sub-scores and the immediately following row (`s2 chat_eval_sft`) holds the full-dataset evaluation; never compare an `(in-train)` estimate against a full evaluation row.
