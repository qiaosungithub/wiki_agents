# VLM Training

Read this when changing training, checkpointing, resume, or evaluation code in
JAX LLaVA, `PaliGemma-baseline`, or `beifen-Paligemma`. Dataset schemas,
uploads, and coordinate rules are in `vlm_data.md`. Current code and
project-native configs remain authoritative.

## First Principles

- Keep data, checkpoints, and compute in the same region; locality and
  checkpoint-copy policy are defined in `infra.md`. Validate locality before
  listing or opening GCS payloads, and fail fast on missing paths.
- Preserve each checkout's execution model. A correct pmap checkpointing pattern
  is not automatically correct for a globally sharded JIT/HSDP TrainState.
- Treat the staged config as the experiment definition. WandB and the tracking
  spreadsheet record what ran; old row numbers and incident job ids are not
  architectural truth.
- When porting between related checkouts, copy behavior deliberately and retain
  project-specific sharding, dependency, and initialization choices.

## HSDP And Model Semantics

- In HSDP, derive process-local batch shape from data mesh axes. The final mesh
  axis is the model axis and should not be counted as data parallelism.
- Use explicit mesh-aware sharding for activation constraints and checkpoint
  restore. Do not assume a mesh context exists during shape evaluation.
- Avoid materializing full vocabulary logits when hidden-space token loss is
  available, and avoid gathering a full sharded TrainState onto every host.
- Preserve deliberate model behavior such as prompt-causal masking, connector
  optimizer separation, late-fusion gradient stops, and task-specific generation
  budgets unless the task explicitly changes them.

## Dataloader State And Exact Resume

- A stateful dataloader checkpoint is valid only for a compatible data recipe:
  process topology, local batch, workers, roots, mix weights, shuffle state, and
  seeds must agree. Remap only known same-dataset regional replicas, never
  arbitrary GCS paths.
- Restoring exact loader state means its saved RNG and cursor define the stream;
  do not also advance the seed by checkpoint step.
- Missing dataset shards are configuration errors, not transient failures to hide
  behind retries.
- Large WebDataset shuffle state is expensive to serialize. Keep snapshot cadence
  aligned with durable checkpoints unless explicitly testing replay.

## Checkpoint Transaction

For a training checkpoint to count as complete:

1. Each process writes pending dataloader state.
2. The model/optimizer checkpoint completes using the execution model's correct
   Orbax strategy.
3. Dataloader sidecars are finalized under that checkpoint.
4. Only then is the completion marker logged.

Checkpoint discovery must use the final model completion marker, never a
`Saving` line or sidecar path. In JIT/HSDP code, save global sharded arrays with
all processes participating; do not `process_allgather` the whole TrainState.
In the current pmap path, a replicated local replica can use a process-0 host
write. Re-evaluate this distinction if a checkout changes execution model.

## Curriculum And Final Evaluation

- A same-stage resume restores full state. A stage-boundary transition can be a
  params-only restore with a fresh optimizer and may require shape adaptation
  before sharding. Assert the restored global step rather than inferring it.
- Always save the stage-boundary checkpoint, even when checkpoint cadence does
  not divide the stage length.
- A final-eval-only run should restore model state without constructing or
  restoring the original training dataloader. This allows evaluation on a
  different compatible topology.
- An eval checkpoint still has to be local to the selected region. Copy it
  deliberately or pin the job per `infra.md`; do not rely on a remote bucket
  read.
- Benchmark data roots, scoring protocols, and mirror validation for the
  default Stage-3 final eval (DocVQA, RealWorldQA) are in `vlm_data.md`.

## Before Changing Training Code

Identify which concern is actually in scope: model semantics, mesh/batch
semantics, data stream, checkpoint transaction, curriculum transition, or final
evaluation. Test that concern with the smallest local or remote smoke that can
exercise the real path, then inspect logs and produced state rather than treating
successful process exit as sufficient proof.
