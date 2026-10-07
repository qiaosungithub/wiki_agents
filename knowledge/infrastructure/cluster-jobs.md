# Running Jobs On The Cluster

Owns how a job is queued, placed, packaged, preempted, and restarted on the
internal XManager/Borg stack, and the identity, path, and disk rules a worker
runs under. Sibling pages: [resume-contracts.md](resume-contracts.md) owns how a
scheduler tells a job where to resume (`LOAD_FROM`, `restart_from`,
`CHECKPOINT_BUCKET`) and the new-training-package startup contract;
[wandb-upload.md](wandb-upload.md) owns the tpu-side automatic W&B upload. The
procedures are skills: submitting a job is
[job-submit](../../harness/skills/job-submit/SKILL.md), a failing, silent, or
wedged job (including liveness checks) is
[job-diagnose](../../harness/skills/job-diagnose/SKILL.md), and reporting job
status to the operator is [job-report](../../harness/skills/job-report/SKILL.md).
[knowledge/infrastructure/storage.md](storage.md) owns where data and checkpoints live,
[knowledge/infrastructure/tpu-reference.md](tpu-reference.md) accelerator naming and shapes, and
[the infra pages](market.md) the market, allocator, and CLI
internals. Read those only when the rules here do not explain what you see.

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this page whenever implementation details change.

Chapter 1 is how submission works; Chapter 2 is preemption, restart, and the
worker environment.

---

## Chapter 1 — How Submission Works

### The two queues and the single serial builder

**Every job goes through a local queue that a single serial builder drains into
the XManager queue, one build at a time.** On this host that builder is the
always-on TPU **dispatch-worker** (`route_check --dispatch_worker`, kept alive
by the `*/2` ops watchdog) — it does routing AND building, so nothing extra has
to be started. `tpu enqueue` appends a run to a durable local list
(`~/.tpu_local_queue.json`) — instant, free, no bill while it waits; the
dispatch-worker then claims one QUEUED entry, builds it, records its XID, and
repeats. States: QUEUED → BUILDING → SUBMITTED → RUNNING (`tpu queue-status`,
`tpu check`).

A SINGLE serial builder is enforced, not merely conventional: `route_check`
holds a per-queue-file singleton lock (`{queue_file}.builder.lock`, taken with
`flock(LOCK_EX|LOCK_NB)` for the process lifetime), so at most one builder ever
runs per queue — one for tpu (`~/.tpu_local_queue.json`), one for npu
(`~/lyy-work/.npu_local_queue.json`). This matters because builds are always in
flight on this shared workstation: two concurrent builds race on blaze's
`output_base` (keyed per checkout root, not per copy dir) and ship a zombie XID
with zero work units. So do NOT run `tpu build-worker` to "add" a builder — the
legacy `--worker` just loses the lock and exits every 5s. `tpu queue` is the
one-shot synchronous fallback — only when you KNOW no other build is running.

### The smart router picks the cell and the group

**On the enqueue path the router owns cell and group selection; you supply the
compute target and the candidates, not the placement.** It pins whichever cell
can place the slice right now (most free chips, never oversold or full) and
prints `Smart cell: pinned --cell=…`.

- Do NOT pass `--group` on `tpu enqueue`: the router re-places the job as price
  and capacity shift, and a pin defeats that. The CLI nudges "Pass --group=9 to
  pin it" — ignore it. A manual `--group`, like `--priority>0`, is operator-only (the one `--priority` exception is a small remote debug run at `--priority=1`, [local-debug skill §Local debug, then remote, before a real run](../../harness/skills/local-debug/SKILL.md#local-debug-then-remote-before-a-real-run)).
- `--cell` always wins. `--metros` constrains the pick to data-co-located metros.
  `TPU_NO_SMART_CELL=1` opts out.

### `--power` is the target; `--archs` are the generations allowed to meet it

**`--power` and `--archs` are required together: `--power` is the compute you
want, `--archs` the generations allowed to satisfy it.** `--power` scales across
generations (`--power_tolerance`, default 0.5), so adding an older family widens
placement without shrinking the run. A chip count is not a size: `v6p-32` and
`v7-32` are equal, `v6e-32` is half ([knowledge/infrastructure/tpu-reference.md](tpu-reference.md)).

### Data locality is per metro

**A job must write its checkpoints to a bucket in its OWN metro; writing across a
metro runs ~94x slower and the pruner deletes the job.** Locality is metro-level:
every storage cell in one metro reads that metro's one bucket ([knowledge/infrastructure/storage.md](storage.md)).
Only metros with a registered storage cell in
`cell_locality.py::_METRO_STORAGE_CELL` are legal — naming any other kills the
job silently. Group-storage metros: `cbf ckv cmh dfw grq las lpp mrn sin tul`.

### Tiers: train on PROD, evals either way

**Every TRAINING job runs on `--tier=PROD`; never train on BATCH.** BATCH is a
paying best-effort tier that any PROD demand preempts the instant a slot is
contested, so a training run on BATCH is silently starved and still costs. PROD
is already the launcher default, so `--tier=PROD` is mostly for the audit trail.

An eval runs on either tier — BATCH for a short or restartable one, PROD once it
must finish (a long generation loop, a paper number). The only tier rule is
*train on PROD only*. Set the tier with `--tier`, never the dead `--priority`
flag; priority ≤ 25 bills you personally, above it bills the group.

### Groups

**Pick the group that holds your floor.** The enqueue router picks it; this table
is for the `tpu queue` fallback or an operator-authorized pin.

| Group | Alloc (short) | Use for |
|---|---|---|
| 9 | `fr-dna-grand-challenge-team-resource` | TPU training default: nearly all our v6p/v7/v4 floor. |
| 8 | `brain-vasp-shared-user-xm` | CPU-only, with `--skip-preflight`. No TPU floor. |
| 5 | `vqfree-xm` | Free pool, auto-injects PROD. |
| 1, 7 | `*-resources-prod-shared` | Shared prod, thin floors; g9 fallback. |
| 2, 3, 4 | `*viscam*` / `*interns*` | viscam / intern allocations. |

Full strings: `~/work/tpu_cmd/tpu_wrapper.sh::get_alloc_by_group_id`.

CPU-only jobs schedule last in accelerator groups (CPU/RAM are ancillary in GQM),
so run them in the best-effort pool (`--group=8`, `go/gdm-cpu-only-jobs`,
pre-authorized, free). When it is dry, ride the team's PROD alloc with a cell
pinned in the data's metro and `--skip-preflight` — a CPU-only controller costs
almost nothing yet schedules immediately.

### The budget gate

**Before any launch the launcher runs [`tools/budget_check.py`](../../tools/budget_check.py): this job plus
all active jobs must project under 1/10 of G9 income, or the launch is halted.**
Active = running, pending, or queued, so a backlog cannot each look free. Over
the bar it prints `[[BUDGET_DEFERRED]]`, exits 3, and the worker parks the job
BUDGET_DEFERRED and auto-retries it (not a build failure). g3/g5 draw their own
credit balance; BATCH and CPU-only are free — all exempt.

### The launcher, config, and packaging

**One shared launcher owns packaging: `~/work/tpu_cmd/xm_launcher.py`. Projects
contribute versioned config, not launchers.** Never call `xm launch` /
`xmanager launch` directly — only the wrapper may, after you
`source ~/work/tpu_cmd/tpu_wrapper.sh` (`tpu` is a shell function, not a binary
on `PATH`).

- Semantics (model, data, training behavior) go in versioned config; only routing
  and transient selectors go on the command line.
- Edit the run config in place, pass no `--config`. Default mode is `remote_run`
  (write into `remote_run_config.yml`). Name a mode BARE (`--config=trm_sudoku`),
  never a path or filename.
- Packaging snapshots the code into an immutable CitC snapshot, so later edits
  cannot affect a queued or running job.

---

## Chapter 2 — Preemption And The Worker Environment

Surviving preemption with the right restart budget, and the identity / path /
disk rules a worker runs under. How to tell a live job from a dead one that
still reads `state: RUN` is a procedure, in
[job-diagnose](../../harness/skills/job-diagnose/SKILL.md).

### Preemption, Restart, And Resume

**A restart restores nothing: the binary re-executes from the top on a fresh
machine with the same arguments, and only application checkpoints survive** — no
process state, memory image, accelerator snapshot, or execution position. So keep
checkpoints OUT of the working directory (task-local, wiped by the very event the
budget exists to survive), or the budget buys only a step-zero rerun.

- Set an explicit restart budget, or the first preemption is fatal. `xm_launcher.py`
  defaults `borg_max_task_failures=-1` and `borg_max_task_evictions=-1` (both
  unlimited) plus `borg_max_per_task_failures=1` on a 7200s credit window. A clean
  preemption is an eviction, harmless against an unlimited budget; a torn-apart
  gang leaves survivors exiting non-zero, a per-task failure; a repeat offender is
  declared dead, not retried forever.
- In a preemption STORM `borg_max_per_task_failures=1` kills a job merely holding
  ground — it is not a never-restart setting. With no floor, repeated ABORTs burn
  each task's one credit inside one 7200s window and the job flips to FAILED
  (`task_states=[ABORT×N, FAILURE×k]`, WU=FAILED; seen killing no-floor v4-256 arms
  repeatedly). Ride it out on `tpu queue ... --borg_max_per_task_failures=100`,
  evictions unlimited, so ABORTs re-queue instead of failing the job; a real floor
  beats this stopgap.
- Waiting is never fatal: a never-scheduled job is NEVER failed for it (others
  routinely pend 2d+); only schedule-then-abort on an exhausted budget dies.
- Gate on finished units, not liveness: a task walking a fixed list never revisits
  a passed index, so preempting the tail leaves the job `running` — slot held,
  nothing emitted. Act on a stalled count, and finish tails by other means.
- Size a work unit against the preemption window, not convenience: a unit longer
  than the mean uninterrupted window never completes and fails silently (a
  ~6-minute window against a 195-minute shard). Re-slicing to minutes is free when
  work is a pure function of its index.
- A restart loop proves neither a crash nor slowness: a training loop producing
  zero steps exits 0 and restarts forever, logging only successes. Verify a resume
  by step progress, never exit status; use the kill-versus-exit tests in
  [harness/engineering.md §Diagnose from evidence, not the most available story](../../harness/engineering.md#diagnose-from-evidence-not-the-most-available-story) first.
- Two launcher settings, each cheap: open log-read access (sparing an ACL dance),
  and NO interconnect-resilient slice for accelerator jobs (resilience costs
  roughly a third of throughput; rescheduling onto a healthy slice beats finishing
  much slower).

Resuming is not pointing at a checkpoint. The resume flag appends a work unit to
the existing experiment, and the prefix comes from the experiment id, so the
attempt lands there and auto-resume picks the newest complete checkpoint. The
launcher must NOT also pass an explicit load path (auto-resume yields to explicit
requests, and a guess disables it with an unusable path); reserve explicit paths
for external checkpoints, at a concrete step directory. The env-var resume
contracts themselves are [resume-contracts.md](resume-contracts.md).

A resume re-runs the ORIGINAL snapshot, immutable and prebuilt, never the current
checkout, which drifts within days. Re-run the stagedir from the job registry;
packaging the working tree resumes the checkpoint into code it never saw — the
newer validator refuses retired config keys and kills the run at flag-parse time,
or a renamed module leaves the checkpoint unrestorable minutes in as a model
mismatch. Missing or unknown is an error, never a cue to package what is here now;
deliberate code changes belong in a new experiment.

Auto-resume belongs in the application, in-process at startup: read the checkpoint
prefix, skip it for an explicit load or an eval-only run, enumerate step
directories, ignore any without the last-written marker file (its absence means an
interrupted write), and resume from the highest surviving step. Enumerating the
prefix beats parsing logs, which a rotation restarts from zero.

### Where The Storage CLI Exists, And Where It Does Not

**The storage command-line tool is on the workstation and NOT inside a job
container**, which decides where a data-movement job should run. A container ships
the path-library client and nothing else, so shelling out to the CLI there does
not fail loudly: it hangs until the timeout with no output, in state `RUN`, with
nothing in the termination records because nothing terminated (two assembly jobs
burned half an hour each that way).

This is more than "handle both backends". Server-side concatenation and
cross-cell copy exist only on the workstation path; in a container the same
operation carries every byte through the task, so a tens-of-GB copy cannot finish
inside a preemption window on the cluster but finishes comfortably from a
workstation (not preemptible, acting only as a controller). Probe which backend is
live at runtime and branch, and keep a local branch too, or the code is
untestable off distributed storage.

### Identity, Paths, And Local Disk On A Worker

**A cluster job is a different security principal from you:** nothing you read
interactively is automatically readable from a worker, and the same wall blocks
log mirroring to a personal bucket. The cheapest fix is the internal distributed
filesystem, which the job identity reads and writes natively (usually a one-line
path change); otherwise a bucket owner must grant the job's principal access — an
org-level deny policy can block even owners, and service-account keys are not an
option.

- The temporary directory is a RAM disk you must size yourself: the default is
  small and every task stages its own private copy of what it downloads, so an
  undersized value surfaces mid-run as "no space left on device". A job moving
  large files should stream through a bounded buffer instead.
- The RAM disk and the memory limit are two different knobs the launcher must pass
  explicitly; sizing `/tmp` does nothing for a process that allocates. A resource
  appended to the accelerator string reads as a second accelerator, accepted and
  ignored — name it in its own field.
- Route every existence check and remote read through the project's path helpers:
  shell file utilities do not exist in the container, and the standard library
  breaks on a distributed path or remote URI (`os.path` raises a permission error
  or silently answers False, a bucket URI fails a directory check, normalization
  mangles the URI), so a valid remote load path becomes a bogus "does not exist".
  This survives a green build and a local smoke test because it only fires
  remotely.
- The launcher-to-application contract travels as environment variables, not config
  flags: the external checkpoint to load, the tracking run to continue, and the
  durable checkpoint prefix (derived from the experiment id, so every restart
  resolves to the same location — what makes in-process auto-resume well defined).
  Do not inject a checkpoint path as a config flag if the schema is locked; every
  job dies at startup.
