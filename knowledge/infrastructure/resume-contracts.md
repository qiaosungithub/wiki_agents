# Resume Contracts

How a scheduler tells a job where to resume, and how a new training package must
be written so the fleet can resume it. Two chapters: **Chapter 1** is the resume
contracts (the read-only `LOAD_FROM` channel, the read/write `restart_from`
channel, and the `CHECKPOINT_BUCKET` write path); **Chapter 2** is the contract a
new training package must meet. Sibling pages: [cluster-jobs.md](cluster-jobs.md)
owns queueing, placement, preemption, and the worker environment;
[wandb-upload.md](wandb-upload.md) owns the tpu-side W&B upload. Submitting the
resumed job is [job-submit](../../harness/skills/job-submit/SKILL.md).

The default in one line: pass the checkpoint through
`tpu enqueue --launch="...,load_from=<path>"` for eval or warm-start, or
`...,restart_from=<workdir>,restart_step=<N>` to resume a training run, and clear
it once the job writes its own first checkpoint.

---

## Chapter 1 — How Resume Works

### The `LOAD_FROM` Contract

**A scheduler tells a job where to resume by setting the env var `LOAD_FROM` to
the checkpoint path VERBATIM — the leaf, never a config key, never a "fixed up"
path.** Consumers read `LOAD_FROM`; the per-project config key differs (EqR-jax
`load_from`, codi/coconut `load_model_path`), and writing the key works on most
lines and silently cold-starts the rest (a smoke test on any EqR-jax line
certifies it). Never parse, normalize, or complete the path: four incompatible
shapes coexist and every "helpful" transformation breaks one. Replay the job's
reported `latest_checkpoint()` string unchanged; a bucket root or `checkpoints/`
parent raises `FileNotFoundError` after a reassuring metadata warning.

| Family | Shape | Note |
|---|---|---|
| EqR-jax (maze, trm-arc1, hrm-trm) | `step_<N>/` | the job appends `/state` |
| codi, coconut | `step_<N>/` | flat, no `/state` subdirectory |
| paligemma, jax_llava | `checkpoint_<N>` | flax file |
| torch ports | `step_<N>.pt` | a single FILE, not a directory |

**Deliver `LOAD_FROM` only through `--launch`; it arrives as a launcher flag
(`--load_from` → `job_env_vars`), never by shell inheritance.** The two routes
that look right fail asymmetrically:

| What you type | What happens |
|---|---|
| `LOAD_FROM=<path> tpu enqueue ...` | Silently dropped: the job cold-starts from step 0, trains happily, reports SUCCESS. |
| `tpu enqueue --load_from=<path>` | Loud `FATAL Flags parsing error: Unknown command line flag 'load_from'`: the wrapper passthrough allows it, the binary does not declare it. Cheap: it refuses. |
| `tpu enqueue --launch="...,load_from=<path>"` | Works: `--launch` k=v pairs go verbatim to `tpu queue` at submit. |

**Clear `LOAD_FROM` once the job writes its first checkpoint, or set it on first
dispatch only.** It wins unconditionally and disables auto-resume, so a pinned
`LOAD_FROM` reloads one old checkpoint at every preemption: a run at step 380k
restarted from 298k, read as instability, not an infra fault. A job that cannot
find its `LOAD_FROM` must FAIL CLOSED: a cold start looks like a successful launch
and shows only in the loss curve. Confirm the resume took from the job's own log
line `resumed from <path> at step <N>` with the N you expected; the watcher treats
a `cold start` and a low step as FAILURE, not only crashes.

### The `restart_from` Contract

**`LOAD_FROM` is READ-ONLY: correct for eval and warm-start, WRONG for resuming a
training run whose checkpointer prunes.** A car handed `LOAD_FROM` sets
`workdir = LOAD_FROM` and writes back into it; an orbax manager with
`max_to_keep=N` then deletes the very checkpoints it resumed from, so the run dies
at step 0 with its own CNS output dir never created.

**Training resume travels as `restart_from` + `restart_step`, never `load_from`;
the two are mutually exclusive and setting both is a launch error, not a merge.**
`restart_from` READS the old run and WRITES the new car's own `$CHECKPOINT_BUCKET`,
self-clearing once the new car saves its first checkpoint.

| | reads from | writes to | use for |
|---|---|---|---|
| `LOAD_FROM=<leaf>` | the leaf | **same dir** (`workdir=LOAD_FROM`) | eval; a cold warm-start off a frozen external ckpt |
| `restart_from=<workdir>` + `restart_step=<N>` | `<workdir>/checkpoints/<N>` | the NEW car's `$CHECKPOINT_BUCKET` | resuming a training run that keeps checkpointing |

`restart_from` is the **WORKDIR** — the parent of `checkpoints/`, and it must NOT
end in a digit. `restart_step` is the step, named **explicitly**: a missing step
resolves silently to "latest". Both fail closed if the other is absent (ELT:
`configs/load_config.py::_apply_restart_from_env`). Delivery is the same `--launch`
channel, `tpu enqueue --launch="...,restart_from=<dir>,restart_step=<N>"`, exported
as `$ELT_RESTART_FROM` / `$ELT_RESTART_STEP`. Auto-resume
(`route_lib.build_warm_restart_entry`) picks the mechanism from the surviving
checkpoint's LAYOUT: an ELT `checkpoints/<bare-int>` leaf → `restart_from` +
`restart_step`; every other family → `load_from`.

### The `CHECKPOINT_BUCKET` Write Path

**`CHECKPOINT_BUCKET` says where the job WRITES and is never repointed on resume;
`LOAD_FROM` / `restart_from` say where it READS.** Torch ports take their working
directory from it, so moving it restarts them from scratch. It is also the
launcher's ONLY write-location statement: the launcher never forwards `--bucket`
and exports `<root>/logs/<project>/<folder>`, not the root passed. A binary reading
`--bucket` gets its Borg default (empty, in a careful implementation), so records
degrade to stderr behind the LOAS wall — the costliest symptom is `state=SUCCESS`,
zero bytes written, though the run genuinely happened (peak RSS showed torch loaded
at 9.7 GB). Resolve the write path as `--bucket` then `$CHECKPOINT_BUCKET`, in that
order, so an explicit flag stays authoritative, and log which won. Suffix trap:
`--bucket=/cns/X/eqr_data` writes under `/cns/X/eqr_data/logs/<project>/<folder>`,
so its root looks empty and reads as failure.

**Read remote if you must; write local always.** A cross-metro restore READ is
survivable (6.0 GiB across the Atlantic at ~14 s); a cross-metro WRITE is not:
throughput falls ~6x same-continent, ~94x cross-continent, blocking saves push
duty cycle under the 0.20 floor, and the WIM pruner deletes the job with no
preemption notice and no crash. Copy the checkpoint to the compute cell's CNS
prefix first (swap the prefix, keep the tail verbatim) and point `LOAD_FROM` there.

### Checkpoint Cadence On Preemptible GPU (`checkpoint_minutes`)

**A preemptible run must bank a checkpoint faster than it is killed, measured in
minutes, not updates.** GPU PROD tasks (xborg, above-floor g9 and floor groups
alike) are killed WHOLE and from outside every few minutes to ~1 h: no rank exit
line, no traceback, every rank log stops in the same second. The last log line is
wherever the kill landed, so it is not a diagnosis. In the torch package
(nanoETD_adapt_loop) a restart cost ~16 min before update 1, 11 of them in the
serial `resume_share` turns for a 17 GB checkpoint. With only `checkpoint_interval: 500`
(~26 min of B200, ~50 min of H100 on the 10B-token OLMo runs) attempts died before
saving, and the router's in-place thrash rule (>= 3 restarts since the newest
own-bucket checkpoint) cancelled and requeued them into hours of GQM pending. That was
146 thrash cancels over 65 rows in 2026-11-10..12, including OLMo 10B ctrl-R4 stuck
at step 500 for 24 h and b0-R2 with zero steps in 26 h.

The fix is on main from 2026-11-12. `checkpoint_minutes` (top-level, default 15;
0 = the update cadence only) also saves once that much training has passed since
the last save. It checks every 10 updates, and all ranks agree through one
all-reduce. A timed save is an ordinary `steps/step_<N>.pt` (`N` need not be a
multiple of the interval; keep_last applies). It changes no math: losses, weights
and optimizer state are bitwise identical with and without it, and a resume from a
timed save is bitwise (tests/test_ckpt_clock.py). The key is outside the run
contract, so old checkpoints resume. `resume_share` with
`$RESUME_SHARE_CONCURRENT=auto` (the default) broadcasts the checkpoint once and
resumes all ranks together when host RAM fits, about 2.5x the file per receiver
plus 32 GiB (GPU hosts have 2-4 TiB). Otherwise it keeps the serial turns. A run on
an older snapshot has neither: move it to a commit with the fix at its next
requeue, with `load_from` set to its newest step file.

**Saves are asynchronous from 2026-11-14 (`checkpoint_async`, default true), so
the default cadence is `checkpoint_minutes: 5`.** A synchronous 17 GB save stalled
training 97-139 s (10-15% of wall time at 15 min). Now the update boundary pays only
the collectives (`optimizer.gathered()`) and a device -> host copy into reusable
pinned buffers. `torch.save` and the CNS write run on one background thread of the
chief: `.step_N.pt.tmp`, then flush/fsync and a size check, then an atomic rename to
`step_N.pt`, then a hidden `.step_N.pt.complete.json`. Every reader (own-bucket resume,
`LOAD_FROM`, resume_share, the router's probe) matches only `step_*.pt`, so a write
killed mid-way leaves a stale `.tmp` and the previous checkpoint wins (seen live: a
task killed during a write left an 11.4 GB `.step_250.pt.tmp`, ignored). Measured with
the OLMo 10B config: 0.3 s stall per save on b200-8 (XID 312662638) and 0.6 s on
h100-8 (XID 312640427); 7-11 s for the first save of an attempt, which allocates the
buffers and self-checks them. The write took 156 s at ~109 MB/s on b200 and ~100 s at
~170 MB/s on h100, and s/update during a write was never above idle (b200 3.010 vs
3.070, h100 5.941 vs 6.235). That is about
200 GB/h of CNS writes per OLMo job, and 5 files kept: newest `checkpoint_keep_last`
update-cadence plus newest `checkpoint_keep_timed` (2) timed. At most one write is in
flight. A timed trigger is deferred while a write runs, and skipped when the write
would outlast the gap to the next update-cadence save, which would otherwise wait
for it. Update-cadence and final saves, exports, online evals and the end of `fit`
wait for the in-flight write. With `checkpoint_async: false` every save is
synchronous again, so use 15 min there. Both keys are outside the run contract.
Code and tests: `utils/async_ckpt.py`, `tests/test_async_ckpt.py`; README
"Checkpoints are written every ...".

---

## Chapter 2 — New Training Package Startup Contract

A training binary is not standalone: the fleet scheduler, its auto-resume, and the
CNS evidence layer all read it from the OUTSIDE. Six things must hold or the
package launches and silently misbehaves — all "looks healthy, produced nothing /
trained wrong" failures that surface only in the loss curve. Verify each on a CPU
smoke before a remote round trip ([local-debug skill §Local debug, then remote, before a real run](../../harness/skills/local-debug/SKILL.md#local-debug-then-remote-before-a-real-run)).

1. **Checkpoint layout is a registered shape, and a complete checkpoint is
   distinguishable from an in-flight one.** The fleet's parsers live in
   `route_lib.py` (`checkpoint_step` for `step_<N>[.pt]` / `checkpoint_<N>`;
   `elt_checkpoint_leaf_step` for ELT's `checkpoints/<bare-int>`). A NEW shape
   needs a new parser there AND a new branch in
   `route_check._latest_complete_checkpoint`, or auto-resume cannot see your
   checkpoints and every resume HOLDs. Completeness must be atomic-rename based:
   write `<name>.tmp` (or orbax's `<N>.orbax-checkpoint-tmp-<uuid>`) and rename on
   finalize, so an interrupted save leaves a name the scanner rejects; a
   half-written checkpoint that scans as complete is resumed and corrupts.

2. **Resume mechanism matches Chapter 1**: eval / warm-start reads `LOAD_FROM`, a
   pruning training run resumes via `restart_from` + `restart_step`. FAIL CLOSED
   on the wrong combination at startup (ELT `main_eqr.py` refuses `LOAD_FROM` on a
   training run, pointing at the right flags) — a guard that raises is cheaper than
   a run that mis-trains.

3. **The boot banner names the durable out_dir in a form the evidence layer
   parses.** The evidence layer recovers a dead run's out_dir by regex over its
   rank-0 log (`route_lib.out_dir_from_log` / `_OUT_DIR_PATTERNS`). Emit ONE
   unambiguous line naming the post-locality CNS write dir —
   `out_dir (post-locality) = '<path>'` or ELT's
   `redirecting workdir -> $CHECKPOINT_BUCKET <path>`. No such line ⇒ no out_dir ⇒
   no checkpoint scan ⇒ auto-resume HOLDs even with a good checkpoint. Also log
   `resumed from <path> at step <N>` on a resume.

4. **The launcher owns the read/write split; the binary never conflates it.** A
   training binary that sets `workdir` from the read path instead of from
   `$CHECKPOINT_BUCKET` is the exact ELT bug. Deliver resume selectors through the
   launcher (`--load_from` / `--restart_from` / `--restart_step` → env vars), never
   by shell inheritance (silently dropped) and never as an undeclared `--flag`
   (FATAL at parse).

5. **`main.py` fails closed on every under-specified launch.** Missing config,
   missing workdir, a resume path that does not resolve, a step that is not an int
   — each must raise at startup, not default to a cold start that looks like a
   successful launch and burns the run. Keep the check a PURE function (ELT
   `load_from_guard.py`) so it is unit-tested on CPU without importing the
   accelerator stack.

6. **The job tees stdout+stderr to a durable CNS text log, not only
   tfevents / wandb.** A metrics writer (`clu.metric_writers`, wandb) captures
   NUMBERS, not the traceback, device list, or resume line, and the only other
   text a Borg task emits is per-attempt stderr, GC'd in minutes and never landed
   on CNS. Tee both streams into
   `<bucket>/logs/rank_<n>_attempt<k>.log`, ONE FILE PER ATTEMPT (a Borg retry
   reuses the task id, so a fixed name lets the retry clobber the attempt that holds
   the failure), started BEFORE distributed init and the first XLA compile — the
   long silent stretch where startup deaths live. Derive the rank without touching
   JAX (env vars / `--jax_task_id`, never `jax.process_index()`, which boots the
   backend and forecloses distributed init). The mirror must swallow its own errors
   and never raise into the run — the ELT-DiT gap that left eleven dead cars
   undiagnosable. Reference implementations: maze128 `ref_jax/utils/log_mirror.py`
   (full), parcae `models/logmirror.py` (minimal).
