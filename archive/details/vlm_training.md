# VLM Training Overview

Shared training memory for JAX LLaVA, PaliGemma-baseline,
`beifen-Paligemma`, and related VLM reproduction work.

This file is the training overview. Put dataset/upload/counting details in
`vlm_data.md`; put checkpoints, stateful dataloader resume, and final-eval
restore details in `vlm_checkpointing.md`.

## Read Order

When working on VLM training code:

1. Read this file.
2. Read `vlm_data.md` for dataset recipes or region-local data rules.
3. Read `vlm_checkpointing.md` for checkpoint/resume/eval-only work.
4. For TPU launch/resume work, read `tpu.md`, `infra_scheduling.md`, and
   `infra_resume.md`.
5. For result logging, read `spreadsheet_logging.md` and
   `spreadsheet_logging_playbook.md`.

Exact legacy project-local snapshots are preserved in
`project_agents_archive.md`.

## Active LLaVA-1.5 Reproduction Tracking

- Spreadsheet:
  `https://docs.google.com/spreadsheets/d/1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ/edit?gid=1146448969#gid=1146448969`.
- Rows 146-148 on gid `1146448969` contain the current reproduction-progress
  checkpoint. Row 147 is the LLaVA-1.5 7B target line; row 148 is the first
  init run.
- First init run: `CLIP-L @ 336 + gemma3-1B`, blip-3o pretrain, SFT mix of
  LLaVA-OV1.5, VQA, GQA, and TextCaps style data. WandB:
  `exalted-haze-9 | Sqa24's workspace | jax-llava`.
- Target metrics from row 147:
  MME-P `1511`, VQAv2 `78.5`, TextVQA `58.2`, MMBench `64.3`,
  POPE `84.2`, VStar `~48.7`, OCRBench `29.7`, MMVP `24.7`,
  CountBench `~47.0`, VisWiz `50.0`, SEED-Bench image `66.1`,
  ScienceQA-IMG `66.8`, and GQA `62.0`.
- POPE in row 148 is adversarial F1 (`pope_adversarial_f1_stage2_final=80`),
  not macro F1. The same final eval also logs macro F1 `82.58`.
- Non-original LLaVA-1.5-paper probes in the current sheet/report:
  VStar, OCRBench, MMVP, CountBench, RefCOCOg, and ImageNet KNN.
- First row-148 run data: stage 1 `blip3o-short`; stage 2 LLaVA-OV1.5,
  VQAv2, GQA train, TextCaps train, and Visual Genome QA with weights
  `[22, 0.4, 0.94, 0.022, 1.7]`.
- Current JAX LLaVA `remote_run_config.yml` changes stage 1 to `cc12m` and
  adds OKVQA, A-OKVQA, OCRVQA, Visual Genome detection, and RefCOCO to stage 2.
- Parsed v5p-64 throughput for first LLaVA-style curriculum jobs:
  stage 1 median `5.63` steps/s all points (`5.69` filtered >2 steps/s);
  stage 2 median `3.91` steps/s all points (`3.94` filtered >2 steps/s).

## HSDP / PJIT / Model Rules

- `model.prompt_causal` defaults to `True`: image prefix tokens are
  bidirectional while prompt/text tokens remain causal.
- The projector/connector has its own optimizer group. Use
  `training.connector_learning_rate` or legacy `training.projector_learning_rate`.
- Eval generation uses task-specific token budgets:
  `eval_tokens_shortqa`, `eval_tokens_mid`, `eval_tokens_ocr`,
  `eval_tokens_refcoco`, `eval_tokens_pixelbench`, and `eval_tokens_mmbench`.
  Set `sampling.beam_size` once for deliberate beam-search final evals.
- `utils/pjit_util.py` treats the final mesh axis as the model axis for HSDP.
  Batch/data arrays are sharded only over preceding data axes.
- Prefer a process-major HSDP mesh with the final model axis host-local when
  topology allows. This keeps `global_batch / process_count` dataloader batches
  compatible with `make_array_from_process_local_data`; the old failure looked
  like `process data has 32 elements. Process addresses 64 elements`.
- Training loss should use `token_xent_loss_from_hidden(...)`, not a full
  `embedder.decode(out)` over `(B, K + T, vocab)`.
- CLIP/LLaVA and PrefixMAE paths use best-effort
  `constrain_batch_model(...)` constraints around image features, q/k/v,
  attention maps, and hidden activations. Keep these when editing HSDP paths.
- `LlavaGemma.generate_beam_search(...)` is cumulative-logprob beam search, not
  a greedy alias. It keeps EOS beams alive and decodes only the last prompt
  hidden state during prefill to avoid `[B, prompt_len, vocab]` logits.
- Late-fusion `txt_feature_layer>0` can be slow under HSDP if the text-prefix LM
  blocks are frozen but their outputs still receive gradients. The active fix is
  `model.stop_gradient_text_features=None` auto-inferred to true when the
  text-prefix side is frozen, so the frozen text-only prefix is treated as a
  fixed feature while image/connector gradients through the later full-sequence
  LM blocks remain intact. Set it explicitly false only if intentionally training
  through that text-prefix path, for example loc embedding experiments.

## ImageNet KNN Baselines

- 2026-06-17 full TFDS ImageNet KNN under the current `eval_imagenet_knn.py`
  protocol uses `model.encode_image(...)` and mean-pools CLIP patch tokens. For
  `openai/clip-vit-large-patch14-336` this is a pure CLIP-L image-tower metric,
  not a connector/Gemma metric.
- A no-`load_from` CLIP-L init eval on us-east5 TFDS produced
  `knn_full_acc_raw_final=71.193` and
  `knn_full_acc_pca_whitened_final=77.963`.
- Window 7796's final checkpoint at step 52180 produced the exact same numbers
  (`71.193` raw / `77.963` PCA-whitened), so its ImageNet KNN is just the frozen
  CLIP-L baseline. A spreadsheet value around `51` is likely from a different
  encoder/protocol, for example MAE/PaliGemma, not CLIP-L.
- 2026-06-17 follow-up: window 7796's W&B config showed top-level
  `training.freeze_image_encoder=false`, but the effective curriculum stage
  config had `training.stage1.freeze_image_encoder=true` and
  `training.stage2.freeze_image_encoder=true`. `_build_curriculum_stage_config`
  applies stage-specific overrides, so always inspect `training.stageN.*` when
  judging what trained. A rerun of the CFG 1:1:1 LLaVA-1.5 recipe was queued as
  `dir=51` with `training.stage2.freeze_image_encoder=false` and W&B notes
  prefix `[stage2 unfreeze image encoder rerun]`. The original run's
  `checkpoint_2180` stage boundary had already been removed from all three
  buckets, so the rerun starts from scratch and redoes the short frozen stage 1
  before entering unfrozen stage 2.

## PaliGemma / Two-Stage Curriculum

- 2026-06-20 sync rule: `PaliGemma-baseline` should track
  `beifen-Paligemma`'s data, prompt, eval, config, stateful dataloader,
  curriculum, Qwen/Gemma, and logging behavior, but must keep the
  jit-style HSDP/FSDP execution path instead of reverting to pmap. When copying
  beifen changes over, preserve `config.sharding="hsdp"`, `prepare_pjit_funcs`,
  HSDP activation constraints, hidden-space token xent, sharded TrainState init,
  and mesh-aware host-local batch handling.
- `PaliGemma-baseline` should follow `beifen-Paligemma` for vendored dependency
  layout: `big_vision` and `gemma` are symlinks to
  `/kmh-nfs-ssd-us-mount/code/hanhong/shared/{big_vision,gemma}`, not duplicate
  checked-out directories.
- For HSDP/FSDP local batch sizing, do not blindly divide global batch by
  `jax.process_count()`. Infer the process-local batch from the data mesh axes:
  in HSDP the final mesh axis is the model axis, so only the preceding axes
  shard batch/data arrays. A bad implementation fails with
  `Invalid host data ... process data has N elements. Process addresses M
  elements`.
- HSDP activation constraints should use explicit `NamedSharding(mesh, spec)`.
  Calling `jax.lax.with_sharding_constraint(..., PartitionSpec(...))` during
  `jax.eval_shape(model.init)` can fail because there is no active mesh.
- Row-level location-token training with frozen LM embeddings is implemented by
  keeping the full embedding leaf trainable and zeroing non-location rows in the
  update. In that mode it is valid for the frozen-params tree to be empty.
- The active remote entry is `main.py --config=configs/load_config.py:remote_run`,
  backed by `configs/remote_run_config.yml`. Patch `remote_run_config.yml` to the
  exact variant before each queue call, then queue with `infra queue` (see
  `infra_scheduling.md`):
  ```bash
  infra queue --types=v5p-64 --regions=us-central1,us-east5 \
      -- main.py --config=configs/load_config.py:remote_run \
      --config.logging.wandb_notes="<experiment-tag>"
  ```
  `infra queue` stages the current working tree itself; there is no `qsqa` /
  xibo working-dir-id flow anymore.
- The daemon does **not** auto-classify cost from `wandb_notes`; you choose the
  card by setting `--types`/`--regions` yourself. Still keep meaningful cost-class
  tokens in `logging.wandb_notes` (e.g. `MAE-B`, `jit`, `unify-base`,
  `llava-1.5 reproduction`) so a human reading the run knows its intended size, and
  follow the cost-class conventions in `infra_scheduling.md` (low-cost →
  `v6e-32`/`v5p-64`; high-cost → `v6e-64`/`v5p-128`; `MAE-L`+large LM needs v5p).
- As of 2026-06-08, the runnable baseline is
  `training.curriculum: pretrain_sft_two_stage`.
- Stage 1 is a 150K-step 512-resolution pretrain mix with `laion-aes`, `cc12m`,
  `blip3o-short`, `rendered-text-512`, Visual Genome QA/grounded captions/detect,
  `textcaps-train`, `tallyqa`, and `dvqa-train`, with weights
  `[50, 12, 5, 20, 1.7, 5.4, 5.4, 0.1, 0.25, 2.3]`.
- Stage 2 is 90K-step SFT on the LLaVA/VQA/VG/RefCOCO recipe, Adam `1e-5`, weight
  decay `0.002`.
- `pure und baseline` means `vlm_loss_weight=1.0`,
  `text_only_loss_weight=0.0`, `cfg_loss_weight=0.0`, and
  `recon_loss_weight=0.0`.
- For heavy mixed-data runs, `dataset.num_workers` was reduced from 16 to 8.
- Two-stage resumes use global step to choose stage:
  `< stage1_steps` restores pretrain fully; `== stage1_steps` restores params
  only into SFT and starts a fresh optimizer; between stage boundary and final
  step restores SFT fully.
- In `beifen-Paligemma`, stage-boundary params-only restore supports increasing
  PrefixMAE `model.num_learnable_tokens` between stages. Existing
  `learnable_tokens` / `learnable_pos_embed` rows are copied exactly and appended
  rows are Gaussian-initialized from the old bank's mean/std. Configure
  `model.learnable_token_resize_stats` as `scalar` or `per_channel`. Shrinking K
  is intentionally unsupported; full same-stage resume should still use matching
  shapes.
- Two-stage does not support `load_from_pretrained`; use `finetune: True` for a
  standalone SFT from a pretrain checkpoint.
- Stage 2 logs/saves global steps but uses stage-local offset for SFT dataloader
  and LR schedule.
- The stage-1 boundary checkpoint is copied to durable `pretrained-ckpts/...`
  before SFT, and final checkpoint is copied there at the end.
- The stage boundary checkpoint must be saved even when the stage length is not
  divisible by `checkpoint_per_step`.

## Curriculum Implementation Fixes

- 2026-06-12 locked-config fix: every key in the curriculum stage override
  allowlist must be predeclared in `configs/default.py` before absl locks the
  config. Missing defaults such as `training.siglip_warmup_steps` cause
  `_build_curriculum_stage_config` to raise `KeyError` before training starts.
  `beifen-Paligemma` and `PaliGemma-baseline` now declare no-op defaults for the
  stage-only fields and baseline uses `with dataset_config.unlocked()` plus
  explicit `del` instead of unsupported `ConfigDict.pop()`.
- 2026-06-15 wandb logging fix: window 7692 failed after restore/compile during
  `write_texts(... stage2_vis_samples ...)` because the wandb async service
  raised `AssertionError` inside `wandb.log`. This is a logging robustness issue,
  not a checkpoint/dataloader/JAX failure. `../jax_llava` and
  `../beifen-Paligemma` now wrap wandb init/config/log/finish calls so failures
  emit `[WARNING] wandb ... failed; training will continue`. Text logging falls
  back to `output.log`; image logging falls back to local PNG files.
- 2026-06-15 speed baseline: do not compare stage-1 projector pretrain speed
  with stage-2 visual-instruction SFT speed. In the
  `stage2_visual_instruction_sft` v5p-64 HSDP/JIT jobs with `batch_size=512`,
  `freeze_image_encoder=true`, `freeze_lm=false`, and shuffled OV1.5 SFT data,
  steady training is about `1.6 steps/s` around steps 2300-2400. The parent
  20260614 run logged stage-1 projector pretrain around `4.0-4.4 steps/s`, but
  its stage-2 SFT logged `1.60-1.62 steps/s` at 2300-2400. Window 7703's
  `1.63 steps/s` is therefore normal for that stage; its bug was the checkpoint
  save failure, not input throughput.
