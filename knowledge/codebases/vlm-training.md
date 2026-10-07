# VLM Training

Read this when changing training, checkpointing, resume, or evaluation code in
`jax_llava`, `PaliGemma-baseline`, or `beifen-Paligemma`. Datasets, coordinates,
and benchmark mirrors: [knowledge/codebases/vlm-data.md](vlm-data.md). Reporting a result:
[knowledge/codebases/vlm-metrics.md](vlm-metrics.md). Running and verifying a change, and getting
telemetry out: [vlm-debug skill](../../harness/skills/vlm-debug/SKILL.md).
Current code and native configs outrank this file.

Chapter 1 is how training, checkpointing, resume, and eval work; Chapter 2 is
the silent-correctness traps that report healthy while the result is wrong.

---

## Chapter 1 — How Training, Checkpointing, Resume, And Eval Work

### The checkout contract

**A VLM checkout is a Type 1 payload — data, checkpoints, and compute in one
region — and keeps its own execution model.** Validate locality before listing or
opening a payload, and fail fast on a missing path
([knowledge/codebases/projects.md §Data Locality Follows The Category, Not The Task](projects.md#data-locality-follows-the-category-not-the-task),
[knowledge/infrastructure/storage.md](../infrastructure/storage.md)).

- The staged config is the experiment definition. WandB and the spreadsheet
  record what ran; old row numbers and incident job ids are not architecture.
- A pmap checkpointing pattern may be wrong for a globally sharded JIT/HSDP
  TrainState; a port keeps each side's sharding, dependency, and initialization
  choices.

### Mesh, model, and data stream

**Process-local batch shape comes from the data mesh axes only: the last mesh
axis is the model axis, not data parallelism.** Shard explicitly and mesh-aware
for activation constraints and checkpoint restore; no mesh context is guaranteed
during shape evaluation.

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

### Checkpoints, Stage Boundaries, Final Eval

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
  never read a remote bucket. Roots, mirror validation, and exact-count rules
  are in [vlm-data-operations skill §Mirroring the grounding and eval roots](../../harness/skills/vlm-data-operations/SKILL.md#mirroring-the-grounding-and-eval-roots);
  Stage-3 final eval scoring (DocVQA, RealWorldQA) is in
  [knowledge/codebases/vlm-data.md §The two final-eval benchmarks](vlm-data.md#the-two-final-eval-benchmarks).

---

## Chapter 2 — Silent-Correctness Traps

Two migration bugs each left a run converging and reporting healthy while the
result was wrong. Nothing failed, so nothing flagged them.

### A distributed eval must place rows by the sharding, not by rank index

**A distributed eval must ask the sharding which global rows each rank owns;
never assume `PROC_INDEX * B`.** The generation step returns the global gathered
batch (`local_B * num_proc` rows), but a host-local
`zip(batch["aux"], out_strs, batch["is_pad"])` stops at the shortest, so every
rank silently scored `out_strs[0:local_B]`, process 0's answers. Ranks 1..N then
score at chance and the pooled number collapses (VQAv2 read 16.84 vs 67.63)
while teacher-forced train acc still matches to -0.0003. Collapsed eval with a
perfect training curve is the diagnosis: the bug is in the autoregressive path,
not the model. The separating probe is per-rank accuracy; a global offset-shift
test reads as "alignment fine". Invert the placement from the sharding and raise
on a row-count mismatch.

### An unknown accelerator in the mesh table must fail loud

**An unknown accelerator in the mesh table must fail loud, not fall back to a
flat 1-D mesh.** `get_mesh()` looked `device_kind` up in a `TOPOLOGIES` table
and, on no match, silently built a `(N,)` mesh meant for CPU/GPU debug. v7 was
missing, so every param sharded across all devices and every matmul paid a
full-mesh collective. That is 7x slower but correct, so it survived a full
production run; a fallback that preserves correctness is the hardest bug to see.
Make `get_mesh` warn on an unknown kind, and probe the mesh a real slice builds.
Register v7 by its `device_kind` — `tpu7`, not `v7`; the wrong key looks like a
fix and changes nothing ([knowledge/infrastructure/tpu-reference.md](../infrastructure/tpu-reference.md)).
