# Infra Resume, The Single-Job Chain, And Recovery

Use this guide to understand how `unified_infra` resumes/reruns a failed job, the
one-job-one-chain model, the `dead_runs` history, how failures are classified as
resume vs terminal, how checkpoints are discovered, and how to recover. Read
`infra_overview.md` for architecture and `infra_scheduling.md` for TPU
selection/pinning. Resume work is automatic — the daemon does it; you mostly
**read** this state to debug, not drive it.

## One Job, One Chain

A job keeps its **same 8-char hex id** for its whole life. A resume is **not** a new
job and **not** a separate row: when a RUNNING job dies and is eligible to continue,
the *same* job is mutated back to PENDING and re-dispatched. The whole history lives
inside the job:

- **`nodes`** — the committed **checkpoint trail**. Each node is one past attempt
  that actually **saved a new checkpoint**: `{stage_dir, log_dir, tpu_type, zone,
  ckpt_step}`. `nodes[-1]` is the resume source. An attempt that died *without*
  saving new progress is **not** a node — the next resume just continues from the
  previous node (or from scratch).
- **`restarts`** — total resume/rerun attempts (checkpointed or not), for
  visibility. `infra check` shows it as the `RST` column, e.g. `3·ck15000` =
  restarted 3 times, newest checkpoint at step 15000.
- **`pin_type` / `pin_zone`** — once *any* checkpoint exists, the job is pinned to
  that exact type+zone for life (a checkpoint can't move across zones). No checkpoint
  yet → keeps original broad allow-lists.
- **`load_from`** — `nodes[-1].log_dir`, injected at launch via env `LOAD_FROM` so
  the next attempt restores from the last checkpoint. Empty when there is no node
  (clean rerun from scratch).
- **`wandb_resume_id`** — fixed for the whole chain, so all attempts continue **one**
  wandb run.

Because the chain is one job, `infra check` shows it as a **single row** (not one
row per resume), `infra info` lists its `nodes`, and `infra clean` forgets the whole
chain at once. Each attempt always gets a **fresh `log_dir`** at launch — attempts
never share an `output.log` / workdir / ckpt dir.

## `dead_runs`: Every Terminated Attempt Is Kept

In addition to the checkpoint-advancing `nodes` chain, each job keeps **`dead_runs`**
— a full record of **every real attempt that terminated** (preempt / error /
code-bug / killed / resume-capped), *including* the ones the resume logic discards
because they saved no new checkpoint. This was added so a failed attempt's logdir
never vanishes: before `dead_runs`, a run that died before checkpointing left no
trace (the user hit this with job `128dec89`). A run that checkpointed **and** then
died appears in **both** `nodes` and `dead_runs`.

Each `dead_runs` entry: `{log_dir, stage_dir, tpu, tpu_type, zone, start_step (the
step it resumed from; 0 = from scratch), end_step (max ckpt it reached, or null),
started_at, finished_at, exit_code, outcome, reason, restart_index}`. `outcome` is
one of `failed` / `code_bug` / `resume_cap` / `killed`.

`infra info <job_id>` prints `dead_runs` after the nodes, one line per terminated
run with its `start`/`end` step, outcome, reason, zone, and `output.log` path — so
to find an old failed attempt's log for debugging, run `infra info <id>` and read
the `dead_runs` lines. Debug jobs (`is_debug`) and jobs with no `log_dir` are not
recorded.

## Resume vs Terminal (`classify.py`)

When a job exits — or its log goes stale, or its window vanishes — `classify.py`
decides resume vs terminal. Full ordered policy and empirical basis:
**`unified_infra/docs/resume_rules.md`**.

- A bare "Traceback present" is **not** a usable signal: gcloud's SSH wrapper and
  JAX's TPU init both emit tracebacks on pure infra failures, and real bugs are
  trailed by SSH-255 barrier noise from other workers. Instead the classifier parses
  the traceback's **content** — the **deepest frame's file path** is the
  discriminator: under `/staging/…/code/` ⇒ **code bug**; in `xla_bridge.py` /
  `distributed.py` / `threading.py` / gcloud SDK / `wandb` teardown ⇒ **infra**.
- **OOM is treated as a code bug** (terminal). Compile-time `RESOURCE_EXHAUSTED …
  Ran out of memory in memory space hbm` means the model doesn't fit the chip — fix
  the config / use a bigger card, don't resume. **Watch out:** an OOM can be *masked*
  by secondary SSH-255 / coordination errors in the log tail; if a job keeps
  rerunning on an "infra exception", grep the full log for `RESOURCE_EXHAUSTED` /
  `Ran out of memory` before trusting the classification (this was the `a2056e02`
  misclassification — the visible tail was an SSH `commanderror` that hid the real
  v6e compile OOM, so it kept rerunning instead of stopping).
- A **code bug**, or hitting the resume cap `INFRA_MAX_RESUME` (default 100), is
  **terminal**: the job stays FAILED, no resume.
- **Dispatch / infra failures are never terminal** — preempt, SSH error, JAX
  abort, deleted card, lost reservation, hang. The job continues as itself.

On a resumable exit:

1. **Commit or discard the dead attempt.** Scan its `log_dir` for the max `saved to
   … step_N` checkpoint. If it beats the last node's step, **append a node** and pin
   to its zone. If it saved nothing new (including a from-scratch run that died before
   its first checkpoint), **discard** — no node added. Either way the attempt is
   appended to `dead_runs`.
2. **Re-dispatch the same job.** Back to PENDING, `restarts += 1`, a fresh `log_dir`
   minted at launch, the previous checkpoint carried via `LOAD_FROM=<nodes[-1].log_dir>`
   plus the chain-stable `WANDB_RESUME_ID`. With no node yet, `LOAD_FROM` is empty.

A **hang detector** kills a RUNNING job whose `output.log` is idle past
`INFRA_HANG_SECONDS` (≈1h), then lets it resume the same way — covering silent
deadlocks. There is **no** manual same-card resume interface; resume goes back
through the pool and the next matching signal/sweep.

## Checkpoint Discovery (`resume.py`)

- A checkpoint is usable only via a `saved to … step_N` completion line. A bare
  `Saving checkpoint …` with no later `saved to` is **incomplete** and does not
  count (the xibo invariant, preserved). `saved_step` returns the **max** such step.
- Do **not** count dataloader sidecar messages as checkpoints. Our training code now
  logs sidecar writes as `written at`, and the model-checkpoint completion as
  `saved to`, precisely so the discriminator can't be fooled by a half checkpoint's
  pending dataloader state. (See `vlm_checkpointing.md` for the save ordering:
  pending sidecars → Orbax checkpoint → finalize sidecars → emit completion log.)

## Resume / Rerun TPU Choice

- **Pinned once checkpointed.** As soon as a job has any checkpoint, resume is
  restricted to the **exact same type + zone** (`pin_type`/`pin_zone`). This is
  stricter than the old xibo phase-dependent rules (training=same-type,
  pretrain=same-zone, eval=flexible) — `unified_infra` always pins to the
  checkpoint's exact zone because cross-zone checkpoint copy is not supported.
- **From-scratch rerun** (no checkpoint yet) keeps the job's original
  `--types`/`--regions` allow-lists and may land on any matching card.
- **`laion-400m`** jobs must stay in `asia-northeast1-b` (data locality); set
  `--regions=asia-northeast1-b` so neither the first launch nor any resume escapes.
- **Eval-only / "just final eval" reruns:** because a checkpointed job pins to one
  zone, copy the final `checkpoint_<step>` to **every allowed eval region**
  (`us-central1`, `us-east5`, `asia-northeast1-b`) with `tpu cc` *before* queueing a
  fresh eval job, then queue it pinned to the region you want. Do not rely on a
  cross-region read. See `vlm_checkpointing.md`.

## Recovery

- `infra recover` self-heals state after a daemon crash / lost info (re-adopts live
  jobs, reconciles the store). A non-disruptive `infrad restart` also re-adopts
  running jobs from persisted state.
- **Finding a failed attempt's log/stagedir:** `infra info <id>` → read the
  `dead_runs` lines (each has the `log_dir`/`output.log` and the steps it covered).
- **Stagedir durability matters.** A job re-dispatches from its recorded `stage_dir`
  (no re-stage). If that snapshot was deleted, the next attempt's window fails with
  `cd … No such file or directory` and never starts training. Treat
  `/kmh-nfs-ssd-us-mount/staging/<user>` as non-durable: cleanup must skip every
  `stage_dir` still referenced by an active/resumable job (see `storage_cleanup.md`).
  Recovery if a stagedir is gone: rebuild a checkout from the last checkpoint's
  printed `FLAGS.config`, then `infra queue --stage-dir <recovery> …` pinned to the
  checkpoint's zone with the same code.
- **Legacy migration.** State from the old multi-row father/child lineage model is
  collapsed into the single-job form once, idempotently, on daemon start
  (`monitor.migrate_legacy_chains`): each lineage becomes its live tip, its
  checkpointed ancestors become `nodes`, superseded rows are dropped.
