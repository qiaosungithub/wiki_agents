# VLM Training Contracts

Applies to `jax_llava`, `PaliGemma-baseline`, and `beifen-Paligemma`.

Owns model, sharding, checkpoint, resume, and evaluation semantics for the VLM
checkouts. Data schemas are in [knowledge/codebases/vlm-data.md](vlm-data.md); scores are in [knowledge/codebases/vlm-metrics.md](vlm-metrics.md).
Validate changes with [harness/skills/vlm-debug/SKILL.md](../../harness/skills/vlm-debug/SKILL.md). Current code and
project-native configs outrank this page.

## Chapter 1 — How Training, Checkpointing, And Resume Work

### The checkout contract

**Keep data, checkpoints, and compute in the same region, and treat the staged
config as the experiment definition.**

- Locality and checkpoint-copy policy are defined in [harness/skills/infra-operations/SKILL.md](../../harness/skills/infra-operations/SKILL.md). Validate locality before listing or opening GCS payloads, and fail fast on a missing path.
- WandB and the tracking spreadsheet record what ran; old row numbers and incident job ids are not architectural truth.
- Preserve each checkout's execution model, because a correct pmap checkpointing pattern is not automatically correct for a globally sharded JIT/HSDP TrainState.
- When porting between related checkouts, copy behavior deliberately and retain project-specific sharding, dependency, and initialization choices ([harness/engineering.md](../../harness/engineering.md#porting-between-related-checkouts) §Porting between related checkouts).

### HSDP and model semantics

**In HSDP, derive the process-local batch shape from the data mesh axes, because
the final mesh axis is the model axis and does not count as data parallelism.**

- Use explicit mesh-aware sharding for activation constraints and checkpoint restore, and do not assume a mesh context exists during shape evaluation.
- Avoid materializing full vocabulary logits when hidden-space token loss is available, and avoid gathering a full sharded TrainState onto every host.
- Preserve deliberate model behavior such as prompt-causal masking, connector optimizer separation, late-fusion gradient stops, and task-specific generation budgets, unless the task explicitly changes them.

### Dataloader state and exact resume

**A stateful dataloader checkpoint is valid only for a compatible data recipe, in
which process topology, local batch, workers, roots, mix weights, shuffle state,
and seeds all agree.**

- Remap only known same-dataset regional replicas, never arbitrary GCS paths.
- Restored loader state means its saved RNG and cursor define the stream, so do not also advance the seed by checkpoint step.
- A missing dataset shard is a configuration error, not a transient failure to hide behind retries.
- Large WebDataset shuffle state is expensive to serialize, so keep snapshot cadence aligned with durable checkpoints unless you are explicitly testing replay.

### The checkpoint transaction

**A training checkpoint is complete only after these steps finish in order, and
discovery must key on the final model completion marker, never on a `Saving`
line or a sidecar path.**

1. Each process writes pending dataloader state.
2. The model/optimizer checkpoint completes using the execution model's correct Orbax strategy.
3. Dataloader sidecars are finalized under that checkpoint.
4. Only then is the completion marker logged.

| Execution model | Correct save |
|---|---|
| JIT/HSDP | Every process saves the global sharded arrays together. Never `process_allgather` the whole TrainState |
| pmap (`beifen-Paligemma`) | Every process slices replica 0. Only process 0 copies it to host with `jax.device_get` and writes it through Orbax with `active_processes={0}`. All processes then meet at a `sync_global_devices` barrier |

- The pmap path calls Orbax directly because Flax's multihost `save_checkpoint` wrapper installs its own barriers, which mismatch when only process 0 calls it.
- Re-evaluate this split if a checkout changes execution model, and grep its `utils/ckpt_util.py` for `active_processes` before porting a save.

### The save log line is an interface

**Infra reads saves from the job's `output.log`, so print the `saved to` line only
after the model checkpoint has committed.**

| A line that contains | Infra reads it as |
|---|---|
| `pretrained` | Nothing; the line is skipped |
| `saved to` and a step number | A completed save; the highest such step is the resume point |
| `saving` and a step number | A save that started, not one that finished |

- The words and a `step N`, `step_N`, or `stepN` match in any case, while a `checkpoint_N` or `checkpoint/N` path must be lowercase; a `saved to` line with no step is ignored.
- A trainer that mirrors a stage-boundary or just-loaded checkpoint into the durable `pretrained-ckpts/` bucket must put `pretrained` in that line. Otherwise infra resumes from a step missing from the job's own directory and marks the chain a code bug.
- Before re-saving a step, delete its leftover directory, or Orbax raises "Destination already exists". `PaliGemma-baseline` and `beifen-Paligemma` do this, so check your checkout before relying on it.

### Resume only from a committed checkpoint

**Resume only from a step directory that holds `commit_success.txt`, because a
save killed midway leaves a directory with a higher step number and no commit
marker.**

- At a stage boundary the stub also reads as proof that the stage finished, so it can be mirrored as the boundary checkpoint and then fail the next stage's restore.
- Read `_latest_checkpoint_or_none` in the checkout's `utils/ckpt_util.py` before resuming it by hand. Only `PaliGemma-baseline` checks the marker when it resolves `LOAD_FROM`; the others take the latest step directory.
- When the resolver does not check, confirm that the step it will pick holds `commit_success.txt` before you launch.

### Resume enters only through the environment

**Infra hands resume state to a job only through environment variables, so a
config's `load_from` is a seed that the first resume replaces.**

- On every attempt infra unsets `LOAD_FROM`, `LOAD_FROM_STEP`, `LOAD_FROM_DEVICES`, and `WANDB_RESUME_ID`, then exports the values for the checkpoint it resumes from ([harness/skills/infra-operations/SKILL.md](../../harness/skills/infra-operations/SKILL.md)).
- The checkout's `main.py` maps the environment onto the config, with `"load_from": ("LOAD_FROM", "load_from", "CONFIG_LOAD_FROM"),` as the `load_from` entry.
- When the config and the environment disagree, `PaliGemma-baseline` and `beifen-Paligemma` let the environment win and log it, while `jax_llava` raises. Check which behavior you have before seeding a chain through the config.
- None of these checkouts reads `LOAD_FROM_STEP` or `LOAD_FROM_DEVICES`, so the checkpoint that `LOAD_FROM` resolves to decides the step.
- An attempt with no resume point runs with `LOAD_FROM` unset, and the checkout falls back to its own workdir resolver.

### A failed restore must raise at startup

**A resume that cannot restore must raise before the first step, because a
restore that finds nothing can return the initial state without an error and
train a fresh model under the resumed run's name.**

- Log the restored path and step once at startup, such as `resumed from <path> at step <N>`, so every attempt can be matched to its checkpoint.
- Write the resume guard as a pure function of the config, the environment, and the checkpoint listing, so a CPU test can exercise it with no accelerator.

### Curriculum and final evaluation

**A same-stage resume restores full state, while a stage-boundary transition can
be a params-only restore with a fresh optimizer that may need shape adaptation
before sharding.**

- Assert the restored global step rather than inferring it.
- Always save the stage-boundary checkpoint, even when checkpoint cadence does not divide the stage length.
- A final-eval-only run restores model state without constructing or restoring the training dataloader, which lets it evaluate on a different compatible topology.
- An eval checkpoint still has to be local to the selected region, so copy it deliberately or pin the job per [harness/skills/infra-operations/SKILL.md](../../harness/skills/infra-operations/SKILL.md) rather than relying on a remote bucket read.
- Data roots, scoring protocols, and mirror validation for the default Stage-3 final eval (DocVQA, RealWorldQA) are in [knowledge/codebases/vlm-data.md](vlm-data.md#final-eval-benchmarks) §Final-eval benchmarks.

### Devices and paths

**Take the device count from `jax.device_count()`, not from the TPU type name,
because the suffix counts cores and some families place two cores on each JAX
device.**

- Infra lists those families in `_MEGACORE_FAMILIES = ("v4", "v5p")`, and `devices_for_tpu_type` maps a v5p-64 to 32 JAX devices.
- Make the global batch divisible by the number of data-parallel devices, which in HSDP excludes the model axis.
- Test a `gs://` path with `exist_general` from `utils/ckpt_util.py`, never with `os.path`, which reports every GCS path as missing.

---

## Chapter 2 — Traps That Report Healthy

### Eval rows must follow the sharding

**Pair each generated output with its input row by the batch sharding, and raise
when the counts differ, because `zip` stops at the shortest list without an
error.**

- A scorer that pairs a rank's `batch["aux"]` with the head of the gathered outputs scores every rank's rows against the first local batch of generations.
- The symptom is a collapsed generative score beside a healthy teacher-forced one, such as VQAv2 16.84 against 67.63 while train accuracy moved by -0.0003.
- Diagnose it with per-rank accuracy, because a global offset-shift test reports the alignment as fine.

### An unknown accelerator must fail loudly

**Check what `get_mesh` in `utils/pjit_util.py` does when no accelerator type
matches, because a silent fallback produces correct numbers slowly enough to pass
unnoticed through a whole production run.**

- A lenient checkout falls back to a one-dimensional `(global_device_count,)` mesh under `# Local CPU/GPU debug path.`, while a strict one raises `Unsupported TPU type`.
- Confirm what the process sees with `jax.local_devices()[0].device_kind` before trusting the mesh shape.

### Keep each model-axis group inside one host

**Build the mesh so that every model-axis group lies within a single host,
because a group that spans hosts makes each host feed its own batch into what the
mesh treats as one replica.**

- This false replication shows up as negative or infinite loss, hosts that disagree, and collapsed probe accuracy, and a single-host or CPU run cannot reproduce it.
- `PaliGemma-baseline` and `jax_llava` document the invariant and its guards under "Sharding invariant & CE guardrails" in their `README.md`.
