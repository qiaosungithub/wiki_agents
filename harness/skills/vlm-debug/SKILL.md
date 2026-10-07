---
name: vlm-debug
description: Run and verify a training, checkpoint, resume, or eval change in jax_llava, PaliGemma-baseline, or beifen-Paligemma, and get its telemetry (scalars, images) out of a Borg job and read it back.
---

# Validate VLM Changes

Read the contracts in [knowledge/codebases/vlm-training.md](../../../knowledge/codebases/vlm-training.md) (training, checkpoints,
resume, eval, silent-correctness traps) and [knowledge/codebases/vlm-data.md](../../../knowledge/codebases/vlm-data.md)
(datasets, coordinates, mirrors) first. The general local-then-remote drill for
any large code change is
[local-debug skill §Local debug, then remote, before a real run](../local-debug/SKILL.md#local-debug-then-remote-before-a-real-run). This skill
owns running and verifying a VLM change and getting its telemetry out.

## Exercise the real path before you trust it

**Name the concern before changing code, then exercise it with the smallest
smoke test that hits the real path.** The concerns are model semantics,
mesh/batch, data stream, checkpoint transaction, stage transition, and final
eval. Read the logs and the produced state; a clean process exit proves nothing.

## Getting telemetry out and reading it back

**`$CHECKPOINT_BUCKET` is the only location outliving the task; `workdir` on a
TPU worker is the task's own tmpfs.** Scalars survive through the datatable.
Images written via `Writer.write_images` do not survive on Borg in either
`jax_llava` or `PaliGemma-baseline`: all three sinks are dead there — google3
`wandb` mock, tensorboard refused at construction, PNG fallback under `workdir`.

- Create the destination directory first; CNS refuses a write into a missing
  parent. Swallow telemetry failures, which must never kill a run. Verify:
  `fileutil ls $CHECKPOINT_BUCKET/` shows `viz/` beside `checkpoints/` and
  `logs/`.
- `http://flatboard/xid/<XID>` renders scalars only; images are at
  `http://datatable/xid/<XID>/viz`. Read scalars back from the workstation per
  [harness/skills/result-logging/references/chart-links.md §Reading The Curves From The Workstation](../result-logging/references/chart-links.md#reading-the-curves-from-the-workstation)
  (the bucket first, then `gbrowser --corp screenshot`); read images with
  `fileutil cp` from `$CHECKPOINT_BUCKET/viz/`.
- Images sent to a datatable need their own table; large arrays interleaved into
  the scalar table make flatboard unusably slow even when nobody opens it.
