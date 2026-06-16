# VLM Checkpointing And Resume

Use this guide for durable checkpoint copies, `load_from` /
`load_from_pretrained`, stateful dataloader sidecars, final eval restores, and
checkpoint-save incidents.

## Durable Pretrained Checkpoint Convention

- Shell helper `ltgcp <absolute_local_logdir>` maps `ltg(local_logdir)` from
  `gs://<regional-bucket>/qiao_zhicheng_hanhong_files/...` to
  `gs://<same-regional-bucket>/pretrained-ckpts/qiao_zhicheng_hanhong_files/...`
  and copies recursively.
- Buckets under `pretrained-ckpts/` are treated as durable and should not be
  cleaned with ordinary run logs. When a training job successfully finishes,
  mirror the latest final `checkpoint_<step>` into the same bucket's
  `pretrained-ckpts/qiao_zhicheng_hanhong_files/...` prefix.
- `jax_llava` and `beifen-Paligemma` checkpoint loaders should resolve
  `load_from_pretrained` params-only restores by first checking the normal
  zone-local bucket path, then the same-zone `pretrained-ckpts` fallback.
- xibo launch should preflight finetune configs with `load_from_pretrained`:
  if the normal target-zone checkpoint and same-zone pretrained checkpoint are
  both missing, but another zone has the pretrained copy, copy latest
  `checkpoint_<step>` from pretrained to pretrained before starting the job.
- Before launching a manual `eval_only` job or a completed-curriculum "just
  final eval" rerun from an existing final checkpoint, first copy that final
  `checkpoint_<step>` to every allowed eval region:
  `us-central1`, `us-east5`, and `asia-northeast1-b`. Use `tpu cc` or the
  current checkpoint-copy helper before queueing. Do not rely on the queue
  staying in the checkpoint's original region; eval-phase scheduling is allowed
  to choose another compatible TPU, and the job must restore from a same-region
  checkpoint rather than reading across regions.

## Stateful Dataloader Resume

- Enable with `dataset.stateful_dataloader: True`; current JAX LLaVA remote
  config enables it by default.
- Requires `torchdata==0.8.0`. Missing `torchdata.stateful_dataloader` should
  fail fast.
- Sidecars are written beside model checkpoints at
  `checkpoint_<step>/dataloader_state/process_<rank>.pkl`.
- Exact restore is valid only for the same process count, process-local batch
  size, worker count, prefetch factor, data roots/types, mix weights, seed
  offset, and topology.
- Stateful resume serializes WebDataset cursors, shuffle buffers, RandomMix
  state, worker RNGs, and topology metadata. Buffer entries use `(url, key)`
  references rather than raw image bytes and hydrate by searching the same-zone
  shard on restore.
- Normal `load_from` resume folds checkpoint step into `dataset.data_seed_offset`.
  `load_from_pretrained` is params-only and starts with `step_offset=0`.
- GCS training roots must match `config.zone` before glob/listing or WebDataset
  reads; mismatches raise immediately to prevent cross-region transfer.
- Missing/inaccessible WebDataset paths are fatal. Do not replace these guards
  with retry loops around nonexistent buckets or paths.
- 2026-06-11 full-state resume fix: topology comparison canonicalizes only the
  three same-dataset replica prefixes `gs://kmh-gcp-us-central1/data`,
  `gs://kmh-gcp-us-east5/data`, and `gs://kmh-gcp-asia-northeast1-b/data`.
  When restoring loader state in another allowed zone, only those `/data`
  prefixes inside the saved loader state are remapped to the current zone-local
  bucket. Do not remap checkpoints, pretrained buckets, or arbitrary GCS paths.
- TorchData `StatefulDataLoader` defaults to snapshotting every batch. With our
  50K WebDataset shuffle buffers this serializes large state constantly and can
  drop SFT speed from normal `~9-10 steps/s` to `~1-2 steps/s`. Keep
  `dataset.stateful_snapshot_every_n_steps=None` so code uses checkpoint cadence
  by default; set a small explicit value only for debugging replay behavior.
- 2026-06-12 dataloader sidecar save fix: do not use `gcsfs.pipe_file()` for
  `checkpoint_*/dataloader_state/process_*.pkl`. It can hit a Python/gcsfs/email
  stdlib mismatch (`HeaderWriteError`) on one worker and leave a model checkpoint
  with missing loader sidecars. `jax_llava` and `beifen-Paligemma` now use
  `tf.io.gfile` for sidecar read/write and run a startup write probe under
  `_dataloader_state_probe/process_*.pkl` after creating/restoring the train
  loader; the probe exercises `state_dict` serialization and GCS write/rename,
  then deletes the object so environment issues fail at step 0 instead of at
  the first checkpoint.
- 2026-06-12 dataloader probe fix: `workdir` is a `main.py --workdir` argument,
  not a config field. Startup dataloader-state probes must pass the local
  `workdir` parameter through `_create_train_iterator`; do not call
  `config.workdir`. The bad form caused `KeyError: 'workdir'` before training
  started in JAX LLaVA and beifen-Paligemma staged jobs.
- 2026-06-15 resume-startup refinement: after a successful exact dataloader
  restore, skip the startup write probe. It only re-serializes the already
  restored large loader state and can stall for minutes before model checkpoint
  restore. Keep the probe for fresh runs or non-restored loaders. On big SFT
  jobs, `iter(train_loader)` itself can still take several minutes while 128
  workers start and touch same-zone GCS; do not kill it as hung while worker CPU
  is high and log timestamps eventually move.

## Checkpoint Completion Ordering

- 2026-06-15 checkpoint ordering fix: windows 7698/7699 exposed a half-saved
  `checkpoint_2400` with model files but no final dataloader sidecars after a
  JAX fatal abort during checkpoint save. Window 7700 then accidentally started
  stage 1 from step 0 because the manual restart lost `--config.load_from`; it
  was killed and marked superseded by 7701. `jax_llava` and
  `beifen-Paligemma` now serialize each process's dataloader state first to
  `_pending_dataloader_state/checkpoint_<step>/process_<rank>.pkl`, sync all
  processes, let Orbax create/write `checkpoint_<step>`, then rename the pending
  sidecars into `checkpoint_<step>/dataloader_state/` and only then emit the
  `Checkpoint at step ... saved to ...` completion log. This preserves the rule
  "dataloader state before checkpoint completion" without pre-creating Orbax's
  checkpoint directory.
- 2026-06-15 follow-up: window 7702 showed why sidecar log wording matters.
  `find_saving_window.py` briefly misread `Dataloader state saved to
  .../_pending_dataloader_state/checkpoint_2400/...` as a completed checkpoint.
  The monitor finder now only accepts model-checkpoint completion lines, and
  `jax_llava` / `beifen-Paligemma` log sidecar writes as `written at` instead of
  `saved to`.

## Checkpoint Writer Incidents

- 2026-06-12/15 checkpoint writer fix: HSDP/JIT checkpoints are saved as
  gathered host trees, not topology-specific sharded arrays. The writer must
  avoid both failure modes: every host writing the same GCS `checkpoint_N`
  directory races (`ValueError: Destination ... already exists`, seen in
  jax_llava window 7544), while process-0-only calls through Flax
  `checkpoints.save_checkpoint()` still install Flax/Orbax multihost barriers
  and mismatch with nonzero hosts. The working pattern in `../jax_llava` and
  `../beifen-Paligemma` was: all hosts write pending dataloader sidecars; all
  hosts sync; process 0 gathers to host memory and calls a raw Orbax
  `Checkpointer(PyTreeCheckpointHandler(...), multiprocessing_options=...)`
  with `MultiprocessingOptions(primary_host=0, active_processes={0})`; all
  hosts sync with `jax.experimental.multihost_utils.sync_global_devices`;
  process sidecars are finalized under `checkpoint_N/dataloader_state`; sync
  again; only then log the completed checkpoint marker. This preserved `keep=3`
  via Flax's private pruning helper but bypassed Flax's save wrapper.
- 2026-06-15 checkpoint-2400 diagnosis: if a two-stage SFT job restores
  params-only from step 2180 with `checkpoint_per_step: 800`, the first
  checkpoint boundary is global step 2400. If `checkpoint_2400` is incomplete,
  every retry restarts from step 2180 and fails at 2400 again. For window 7703,
  the log reached `🚀 Saving checkpoint at step 2400`, so the allgather and
  `device_get` had already succeeded; the failure was inside the old
  multiprocess Flax/Orbax checkpoint save path, followed by coordination/GCS
  DNS errors on one worker. The bad GCS directory had only a 1.92 KiB model
  `checkpoint_2400`, while `_pending_dataloader_state/checkpoint_2400` had 8
  sidecars totaling 9.78 MiB, confirming that dataloader state was not the
  failed part. A v5p-64 remote full-pipeline smoke on
  `kmh-tpuvm-v5p-64-spot-llq6905wx` in `us-east5-a` passed after the raw Orbax
  process-0 writer: fresh checkpoints 2/3 and resume checkpoint 4 restored and
  saved correctly, each with 8 dataloader sidecars; `checkpoint_1` was pruned,
  proving `keep=3` still works.
- 2026-06-15 JAX LLaVA checkpoint-2400 root cause: window 7704 proved the old
  production save path was OOMing, not failing because of data or wandb. Worker
  4 showed Linux `oom-kill` at checkpoint time, killing the parent `main.py`.
  The immediate cause was `mu.process_allgather(state, tiled=True)` before every
  checkpoint: each host materialized a full TrainState, then process 0 tried to
  write it. The failed `checkpoint_2400` was only Orbax metadata (~1.9 KiB) plus
  pending dataloader state. Fix in `../jax_llava`: pass the sharded TrainState
  directly to checkpointing and let all processes save their shards with Orbax;
  do not all-gather or `device_get` the whole state. This does not make restore
  incomplete: the TrainState leaves JIT as a global sharded `jax.Array` PyTree,
  each host owns its addressable shards, Orbax writes the sharded metadata and
  per-process shard payloads, and restore reconstructs the global arrays from
  target sharding. Window 7705 validated the fix on
  `kmh-tpuvm-v5p-64-spot-llqb79mgn` in `us-east5-a`: it resumed W&B run
  `m4ylt3q9` from the complete stage1 checkpoint at global step 2180, trained
  through steps 2200/2300/2400, saved `checkpoint_2400` successfully, and kept
  training to step 2500. The valid sharded checkpoint is ~11.11 GiB with 8
  `dataloader_state/process_*.pkl` sidecars.
- Do not confuse that JAX LLaVA sharded checkpoint path with
  `beifen-Paligemma`'s current pmap checkpoint path. In `beifen-Paligemma`, the
  TrainState is replicated across the pmap replica axis, so checkpointing takes
  local replica 0 and process 0 writes a host PyTree checkpoint. That is complete
  for the current pmap path; if this code is moved to a true pjit/HSDP global
  sharded TrainState, use the JAX LLaVA all-process sharded Orbax path instead
  of process-0 replica-0 save.

## Final Eval Restore

- 2026-06-14 final-eval fix: when a two-stage JAX LLaVA curriculum checkpoint
  has already reached `total_steps`, final eval must restore only model state
  and run eval tasks. Do not route that path through `_run_train_phase`, because
  it constructs the train loader and tries to restore
  `checkpoint_*/dataloader_state/process_*.pkl`, making eval depend on the
  original TPU topology. Window 7640 failed this way after a v5p-64 training
  checkpoint was resumed for final eval on v5p-128.
- 2026-06-14 eval-launch reminder: before queueing a just-eval rerun such as a
  scorer-fix final eval, copy the final checkpoint to all three allowed regions
  first. A same-zone `load_from` path is not enough unless the queue is also
  hard-pinned to that region and will never be resumed elsewhere.
