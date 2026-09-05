# VLM Training

Read this when changing training, checkpointing, resume, or evaluation code in
`jax_llava`, `PaliGemma-baseline`, or `beifen-Paligemma`. Datasets, coordinates,
and benchmark mirrors: `vlm_data.md`. Reporting a result: `vlm_metrics.md`.
Current code and native configs outrank this file.

## Contract

- **Type 1 checkouts** (`README.md`, `../storage.md`): data, checkpoints, and
  compute in one region. Validate locality before listing or opening a payload;
  fail fast on a missing path.
- Keep each checkout's execution model. A pmap checkpointing pattern may be
  wrong for a globally sharded JIT/HSDP TrainState; a port keeps each side's
  sharding, dependency, and initialization choices.
- The staged config is the experiment definition. WandB and the spreadsheet
  record what ran; old row numbers and incident job ids are not architecture.
- Name the concern before changing code (model semantics, mesh/batch, data
  stream, checkpoint transaction, stage transition, final eval). Then exercise
  it with the smallest smoke test hitting the real path, and read the logs and
  produced state. A clean process exit proves nothing.

## Mesh, Model, And Data Stream

- **Process-local batch shape comes from the data mesh axes only**: the last
  mesh axis is the model axis, not data parallelism. Shard explicitly and
  mesh-aware for activation constraints and checkpoint restore; no mesh context
  is guaranteed during shape evaluation.
- Never materialize full vocabulary logits where a hidden-space token loss
  exists, and never gather a full sharded TrainState onto every host.
- Deliberate model behavior stays unless the task changes it: prompt-causal
  masking, connector optimizer separation, late-fusion gradient stops,
  task-specific generation budgets.
- A stateful loader checkpoint is valid only for a compatible data recipe:
  process topology, local batch, workers, roots, mix weights, shuffle state,
  seeds. Remap only known same-dataset regional replicas, no other path.
- Restored loader state defines the stream, so do not also advance the seed by
  checkpoint step. Missing shards are configuration errors, not transient
  failures to retry around.
- WebDataset shuffle state is expensive to serialize; align snapshot cadence
  with durable checkpoints unless explicitly testing replay.

## Checkpoints, Stage Boundaries, Final Eval

**A checkpoint counts only after four steps, in order.** Every process writes
pending dataloader state; the model/optimizer checkpoint completes under the
execution model's correct Orbax strategy; dataloader sidecars are finalized
under it; then the completion marker is logged. Discovery keys on that final
marker, never a `Saving` line or a sidecar path.

- JIT/HSDP saves global sharded arrays with all processes participating; never
  `process_allgather` the whole TrainState. The pmap path writes replica 0 from
  process 0 only: slice `x[0]`, `device_get` on host 0, save through Orbax with
  `MultiprocessingOptions(active_processes={0})`. Not through Flax's multihost
  `save_checkpoint` wrapper, whose barriers the other processes never reach;
  hold them at an explicit `sync_global_devices`. `active_processes` in a
  checkout's `utils/ckpt_util.py` marks which of the two saves you are reading,
  so grep for it before porting checkpoint code either way.
- Same-stage resume restores full state. A stage boundary may instead be a
  params-only restore with a fresh optimizer, maybe needing shape adaptation
  before sharding. Assert the restored global step, never infer it, and always
  save the stage-boundary checkpoint even when the cadence does not divide it.
- A final-eval-only run restores model state without building or restoring the
  training dataloader, which allows a different compatible topology. Its
  checkpoint is still Type 1: copy it into the chosen region or pin the job,
  never read a remote bucket. Roots, mirror validation, exact-count rules, and
  Stage-3 final eval scoring (DocVQA, RealWorldQA) are in `vlm_data.md`.

## Distributed Eval And Mesh: The Silent-Correctness Traps

Two migration bugs each left a run converging and reporting healthy while the
result was wrong. Nothing failed, so nothing flagged them.

- **A distributed eval must ask the sharding which global rows each rank owns;
  never assume `PROC_INDEX * B`.** The generation step returns the global
  gathered batch (`local_B * num_proc` rows), but a host-local
  `zip(batch["aux"], out_strs, batch["is_pad"])` stops at the shortest. So every
  rank silently scored `out_strs[0:local_B]`, process 0's answers. Ranks 1..N
  then score at chance and the pooled number collapses (VQAv2 read 16.84 vs
  67.63) while teacher-forced train acc still matches to -0.0003 — collapsed
  eval with a perfect training curve is the diagnosis: the bug is in the
  autoregressive path, not the model. The separating probe is per-rank accuracy;
  a global offset-shift test reads as "alignment fine". Invert the placement
  from the sharding and raise on a row-count mismatch.
- **An unknown accelerator in the mesh table must fail loud, not fall back to a
  flat 1-D mesh.** `get_mesh()` looked `device_kind` up in a `TOPOLOGIES` table
  and, on no match, silently built a `(N,)` mesh meant for CPU/GPU debug. v7 was
  missing, so every param sharded across all devices and every matmul paid a
  full-mesh collective. That is 7x slower but correct, so it survived a full
  production run. A fallback that preserves correctness is the hardest bug to
  see. Make `get_mesh` warn on an unknown kind, and probe the mesh a real slice
  builds.
  Register v7 by its `device_kind` — `tpu7`, not `v7`; the wrong key looks like
  a fix and changes nothing (`../tpu_reference.md`).

## Telemetry Goes To The Checkpoint Bucket, Never `workdir`

**`$CHECKPOINT_BUCKET` is the only location outliving the task**; `workdir` on a
TPU worker is the task's own tmpfs. Scalars survive through the datatable.
Images written via `Writer.write_images` do not survive on Borg in either
`jax_llava` or `PaliGemma-baseline`: all three sinks are dead there — google3
`wandb` mock, tensorboard refused at construction, PNG fallback under
`workdir`.

- Create the destination directory first; CNS refuses a write into a missing
  parent. Swallow telemetry failures, which must never kill a run. Verify:
  `fileutil ls $CHECKPOINT_BUCKET/` shows `viz/` beside `checkpoints/` and
  `logs/`.
- `http://flatboard/xid/<XID>` renders scalars only; images are at
  `http://datatable/xid/<XID>/viz`. Read scalars back from the workstation per
  `../research/result_logging.md` §Reading The Curves From The Workstation
  (the bucket first, then `gbrowser --corp screenshot`); read images with
  `fileutil cp` from `$CHECKPOINT_BUCKET/viz/`. Images sent to a datatable
  need their own table; large arrays interleaved into the scalar table make
  flatboard unusably slow even when nobody opens it.
