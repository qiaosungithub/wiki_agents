# VLM Training

Read this when changing training, checkpointing, resume, or evaluation code in
`jax_llava`, `PaliGemma-baseline`, or `beifen-Paligemma`. Datasets, coordinates,
and benchmark mirrors are `vlm_data.md`; reporting a result is `vlm_metrics.md`.
Current code and native configs outrank this file.

## Contract

- **These are Type 1 checkouts** (`README.md`, `../storage.md`): data,
  checkpoints, and compute in one region. Validate locality before listing or
  opening a payload; fail fast on a missing path.
- **Preserve each checkout's execution model.** A pmap checkpointing pattern is
  not automatically correct for a globally sharded JIT/HSDP TrainState; a port
  keeps each side's sharding, dependency, and initialization choices.
- **The staged config is the experiment definition.** WandB and the spreadsheet
  record what ran; old row numbers and incident job ids are not architecture.
- **Name the concern before changing code** — model semantics, mesh/batch, data
  stream, checkpoint transaction, stage transition, final eval — then exercise
  it with the smallest smoke hitting the real path and read the logs and
  produced state. A clean process exit proves nothing.

## Mesh, Model, And Data Stream

- **Process-local batch shape comes from the data mesh axes only**: the last
  mesh axis is the model axis, not data parallelism. **Shard explicitly and
  mesh-aware** for activation constraints and checkpoint restore; no mesh
  context is guaranteed during shape evaluation.
- **Never materialize full vocabulary logits** where a hidden-space token loss
  exists, and never gather a full sharded TrainState onto every host.
- **Deliberate model behavior stays** unless the task changes it: prompt-causal
  masking, connector optimizer separation, late-fusion gradient stops,
  task-specific generation budgets.
- **A stateful loader checkpoint is valid only for a compatible data recipe** —
  process topology, local batch, workers, roots, mix weights, shuffle state,
  seeds. Remap only known same-dataset regional replicas, no other path.
- **Restored loader state defines the stream**, so do not also advance the seed
  by checkpoint step. **Missing shards are configuration errors**, never
  transient failures to retry around.
- WebDataset shuffle state is expensive to serialize; align snapshot cadence
  with durable checkpoints unless explicitly testing replay.

## Checkpoints, Stage Boundaries, Final Eval

**A checkpoint counts only after all four steps, in order:** every process
writes pending dataloader state; the model/optimizer checkpoint completes under
the execution model's correct Orbax strategy; dataloader sidecars are finalized
under it; only then is the completion marker logged. **Discovery keys on that
final marker** — never a `Saving` line, never a sidecar path.

- **JIT/HSDP saves global sharded arrays with all processes participating**;
  never `process_allgather` the whole TrainState. **The pmap path writes replica
  0 from process 0 only**: slice `x[0]`, `device_get` it on host 0, and save
  through Orbax with `MultiprocessingOptions(active_processes={0})` — never
  through Flax's multihost `save_checkpoint` wrapper, whose barriers the other
  processes never reach; hold them at an explicit `sync_global_devices` instead.
  `active_processes` in a checkout's `utils/ckpt_util.py` is the marker that
  separates the two saves, so grep for it before porting checkpoint code either
  way.
- **Same-stage resume restores full state; a stage boundary may be a params-only
  restore** with a fresh optimizer, possibly needing shape adaptation before
  sharding. Assert the restored global step, never infer it, and **always save
  the stage-boundary checkpoint** even when the cadence does not divide it.
- **A final-eval-only run restores model state without building or restoring the
  training dataloader**, which is what allows a different compatible topology.
  Its checkpoint is still Type 1: copy it into the chosen region or pin the job,
  never read a remote bucket. Roots, mirror validation, exact-count rules, and
  scoring for the Stage-3 final eval (DocVQA, RealWorldQA) are in `vlm_data.md`.

## Telemetry Goes To The Checkpoint Bucket, Never `workdir`

**`$CHECKPOINT_BUCKET` is the only location outliving the task**; `workdir` on a
TPU worker is the task's own tmpfs. Scalars survive through the datatable, but
images written via `Writer.write_images` did not survive at all on Borg in
either `jax_llava` or `PaliGemma-baseline`: all three sinks are dead there —
google3 `wandb` mock, tensorboard refused at construction, PNG fallback under
`workdir`.

- **Create the destination directory first** (CNS refuses a write into a missing
  parent) and **swallow telemetry failures**, which must never kill a run.
  Verify: `fileutil ls $CHECKPOINT_BUCKET/` shows `viz/` beside `checkpoints/`
  and `logs/`.
- **`http://flatboard/xid/<XID>` renders scalars only**; images are at
  `http://datatable/xid/<XID>/viz`. LOAS refuses the datatable CLI from a
  workstation, so read the PNGs — `fileutil cp` from `$CHECKPOINT_BUCKET/viz/`,
  or `gbrowser screenshot --corp <url>` for a page. **Images sent to a datatable
  need their own table**: large arrays interleaved into the scalar table make
  flatboard unusably slow even when nobody opens it.
