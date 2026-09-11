# Resume Contracts

How a scheduler tells a job where to resume, and the startup contract a new
training package must meet: the read-only `LOAD_FROM` channel (eval / warm-start),
the read/write-split `restart_from` channel for a checkpointing training run, and
the six things a new package must satisfy so auto-resume and the evidence layer
can read it. Part of the `jobs/` set; the hub is `../jobs.md`.

## The `LOAD_FROM` Contract

**A scheduler tells a job where to resume by setting the env var `LOAD_FROM` to
the checkpoint path, VERBATIM: never a config key, never a "fixed up" path.**
Every launcher, requeue path and resume tool follows it.

Consumers read `LOAD_FROM`; the config key differs per project (EqR-jax
`load_from`, codi/coconut `load_model_path`). Writing the key works on most
lines and silently cold-starts the rest. The failure is partial: a smoke test
on any EqR-jax line certifies the bug.

Never parse, normalize, or complete the path: four incompatible shapes coexist
and every "helpful" transformation breaks one.

| Family | Shape | Note |
|---|---|---|
| EqR-jax (maze, trm-arc1, hrm-trm) | `step_<N>/` | the job appends `/state` |
| codi, coconut | `step_<N>/` | flat, no `/state` subdirectory |
| paligemma, jax_llava | `checkpoint_<N>` | flax file |
| torch ports | `step_<N>.pt` | a single FILE, not a directory |

Replay the job's reported string (its `latest_checkpoint()`) unchanged.
`LOAD_FROM` names the leaf; a bucket root or `checkpoints/` parent raises
`FileNotFoundError` after a reassuring metadata warning.

Clear `LOAD_FROM` once the job writes its first checkpoint, or set it on first
dispatch only. It wins unconditionally and disables auto-resume, so a pinned
`LOAD_FROM` reloads one old checkpoint at every preemption: a run at step 380k
restarted from 298k, reading as instability, not an infra fault.

`LOAD_FROM` has one working delivery channel,
`tpu enqueue --launch="...,load_from=<path>"`. Two plausible routes fail
asymmetrically:

| What you type | What happens |
|---|---|
| `LOAD_FROM=<path> tpu enqueue ...` | Silently dropped: the job cold-starts from step 0, trains happily, reports SUCCESS. `LOAD_FROM` arrives only as a launcher flag (`xm_launcher.py`, `--load_from` → `job_env_vars`), never by shell inheritance. |
| `tpu enqueue --load_from=<path>` | Loud `FATAL Flags parsing error: Unknown command line flag 'load_from'`: the wrapper's passthrough allows it, the binary does not declare it. Cheap: it refuses. |
| `tpu enqueue --launch="...,load_from=<path>"` | Works: `--launch` k=v pairs go verbatim to `tpu queue` at submit. |

Row one is the standard silent failure: a cold start looks healthy for an hour.
Confirm from the job's own log, `resumed from <path> at step <N>`, with the N
you expected. Its watcher treats `cold start` and a low step as FAILURE, not
only crashes.

`CHECKPOINT_BUCKET` is separate, never repointed on resume: it says where the
job writes, `LOAD_FROM` where it reads. Torch ports take their working
directory from it, so moving it restarts them from scratch. `CHECKPOINT_BUCKET`
is also the launcher's ONLY write-location statement: it never forwards
`--bucket`, and exports `<root>/logs/<project>/<folder>`, not the root passed.
A binary reading `--bucket` gets its Borg default (empty, in a careful
implementation), so records degrade to stderr, unreadable behind the LOAS wall.
Hence the costliest symptom: `state=SUCCESS`, zero bytes written, the run
genuinely happened (peak RSS showed torch loaded at 9.7 GB) and left nothing.
Resolve as `--bucket` or `$CHECKPOINT_BUCKET`, in that order, so an explicit
flag stays authoritative as in the launcher, and log which won. Suffix trap:
`--bucket=/cns/X/eqr_data` writes under
`/cns/X/eqr_data/logs/<project>/<folder>`: its root looks empty and reads as
failure. Never read through `CHECKPOINT_BUCKET`; that is `LOAD_FROM`'s job
(§The `LOAD_FROM` Contract).

Read remote if you must; write local always. A cross-metro restore read is
survivable: 6.0 GiB across the Atlantic at ~14 s. A write across one is not:
throughput falls ~6x same-continent, ~94x cross-continent. Blocking saves push
duty cycle under the 0.20 floor and the WIM pruner deletes the job, with no
preemption notice and no crash. Copy the checkpoint to the compute cell's CNS
prefix first (swap the prefix, keep the tail verbatim) and point `LOAD_FROM`
there.

A job that cannot find its `LOAD_FROM` must fail closed: cold-starting looks
like a successful launch, burns the run, and shows only in the loss curve.

## The `restart_from` Contract (training resume ≠ `LOAD_FROM`)

**`LOAD_FROM` is a READ-ONLY contract. It is correct for EVAL and for warm-start,
and WRONG for resuming a TRAINING run whose checkpointer prunes.** A car handed
`LOAD_FROM` sets `workdir = LOAD_FROM` and writes back into it; an orbax manager
with `max_to_keep=N` then deletes the very checkpoints it resumed from, so the
run dies at step 0 with its own CNS output dir never created.

**Training resume travels as `restart_from` + `restart_step`, never `load_from`.**
The two mechanisms are mutually exclusive: `restart_from` READS the old run and
WRITES the new car's own `$CHECKPOINT_BUCKET`, and self-clears once the new car
saves its first checkpoint. `load_from` pins one directory for both read and
write. Setting both is a launch error, not a merge.

| | reads from | writes to | use for |
|---|---|---|---|
| `LOAD_FROM=<leaf>` | the leaf | **same dir** (`workdir=LOAD_FROM`) | eval; a cold warm-start off a frozen external ckpt |
| `restart_from=<workdir>` + `restart_step=<N>` | `<workdir>/checkpoints/<N>` | the NEW car's `$CHECKPOINT_BUCKET` | resuming a training run that keeps checkpointing |

`restart_from` is the **WORKDIR** — the parent of `checkpoints/`, and it must NOT
end in a digit. `restart_step` is the step, named **explicitly**: a missing step
resolves silently to "latest", the same ambiguity that reads a wrong resume as
training instability rather than a launch error. Both fail closed if the other is
absent (ELT: `configs/load_config.py::_apply_restart_from_env`). Delivery is the
same `--launch="..."` channel as any other launch kwarg
(`tpu enqueue --launch="...,restart_from=<dir>,restart_step=<N>"`); the launcher
exports them as `$ELT_RESTART_FROM` / `$ELT_RESTART_STEP`.

The scheduler's auto-resume (`route_lib.build_warm_restart_entry`) picks the
mechanism from the surviving checkpoint's LAYOUT: an ELT `checkpoints/<bare-int>`
leaf → `restart_from`+`restart_step`; every other family → `load_from`. If you
add a training project whose checkpointer prunes, it MUST resume via a
`restart_from`-style read/write split, and its checkpoint leaves must be
recognisable (next section) — otherwise auto-resume either corrupts the source or
holds forever.

## New Training Package Startup Contract

A training binary is not standalone: the fleet scheduler, its auto-resume, and the
CNS evidence layer all read it from the OUTSIDE. Six things must hold or the
package launches and silently misbehaves — the failures here are all of the
"looks healthy, produced nothing / trained wrong" kind that only surface in the
loss curve. Verify each on a CPU smoke before a remote round trip
(`../engineering.md §Debug Locally On CPU`).

1. **Checkpoint layout is one of the registered shapes, and a complete
   checkpoint is distinguishable from an in-flight one.** The whole fleet's
   checkpoint parsers live in `route_lib.py` (`checkpoint_step` for
   `step_<N>[.pt]` / `checkpoint_<N>`; `elt_checkpoint_leaf_step` for ELT's
   `checkpoints/<bare-int>`). A NEW shape means a new parser there AND a new
   branch in `route_check._latest_complete_checkpoint`, or auto-resume cannot see
   your checkpoints and every resume HOLDs. Completeness must be atomic-rename
   based: write `<name>.tmp` (or orbax's `<N>.orbax-checkpoint-tmp-<uuid>`) and
   rename on finalize, so an interrupted save leaves a name the scanner rejects.
   A half-written checkpoint that scans as complete is resumed and corrupts.

2. **Resume mechanism matches §The `restart_from` Contract.** Eval/warm-start
   reads `LOAD_FROM`; a training run that keeps checkpointing resumes via
   `restart_from`+`restart_step` with a read/write split. FAIL CLOSED on the
   wrong combination at startup (ELT: `main_eqr.py` refuses `LOAD_FROM` on a
   training run, pointing at the right flags) — a guard that raises is cheaper
   than a run that mis-trains.

3. **The boot banner names the durable out_dir in a form the evidence layer
   parses.** The CNS evidence layer recovers a dead run's out_dir by regex over
   its rank-0 log (`route_lib.out_dir_from_log` / `_OUT_DIR_PATTERNS`). Emit ONE
   unambiguous line naming the post-locality CNS write dir — the launcher's
   `out_dir (post-locality) = '<path>'`, or ELT's
   `redirecting workdir -> $CHECKPOINT_BUCKET <path>`. No such line ⇒ no out_dir
   ⇒ no checkpoint scan ⇒ auto-resume HOLDs even though a good checkpoint exists.
   Also log `resumed from <path> at step <N>` on a resume so a cold-start bug is
   visible in the log, not only the loss curve.

4. **The launcher owns the read/write split; the binary never conflates it.**
   `$CHECKPOINT_BUCKET` says where the job WRITES and is never repointed on
   resume; `LOAD_FROM`/`restart_from` say where it READS. A training binary that
   sets `workdir` from the read path (instead of from `$CHECKPOINT_BUCKET`) is
   the exact ELT bug. Deliver resume selectors through the launcher
   (`--load_from` / `--restart_from` / `--restart_step` → env vars), never by
   shell inheritance (silently dropped) and never as an undeclared
   `--flag` (FATAL at parse) — see §The `LOAD_FROM` Contract's delivery table.

5. **`main.py` fails closed on every under-specified launch.** Missing config,
   missing workdir, a resume path that does not resolve, a step that is not an
   int — each must raise at startup, not default to a cold start. A cold start
   wearing a resume's clothes looks like a successful launch and burns the run.
   Keep the contract check a PURE function (ELT: `load_from_guard.py`) so it is
   unit-tested on CPU without importing the accelerator stack.

6. **The job tees stdout+stderr to a durable CNS text log, not only tfevents/
   wandb.** A metrics writer (`clu.metric_writers`, wandb) captures NUMBERS, not
   the traceback, the device list, or the resume line that says what a job did
   or why it died; the only other text a Borg task emits is per-attempt stderr,
   GC'd in minutes and never landed on CNS. A line that writes only tfevents
   therefore leaves NOTHING to read after a crash — the exact ELT-DiT gap that
   made eleven dead cars undiagnosable. Tee both streams into
   `<bucket>/logs/rank_<n>_attempt<k>.log`, ONE FILE PER ATTEMPT (a Borg retry
   reuses the task id, so a fixed name lets the retry clobber the attempt that
   holds the failure), started BEFORE distributed init and the first XLA compile
   — the long silent stretch where startup deaths live. Derive the rank without
   touching JAX (env vars / `--jax_task_id`, never `jax.process_index()`, which
   boots the backend and forecloses distributed init). The mirror must swallow
   its own errors and never raise into the run (telemetry that kills the job it
   instruments has negative value, `../engineering.md`). Reference implementations:
   maze128 `ref_jax/utils/log_mirror.py` (full) and parcae
   `models/logmirror.py` (minimal); item 3's rank-0 out_dir recovery already
   assumes this log exists.

