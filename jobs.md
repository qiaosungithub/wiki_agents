# Running Jobs On The Cluster

Queue, inspect, resume, and debug a job on the internal XManager/Borg stack.
`storage.md` owns where data and checkpoints live, `tpu_reference.md`
accelerator naming and shapes, `infra/` the market, allocator, and CLI
internals — read those only when the rules here do not explain what you see.

## Submission Contract

- **Submit through the wrapper**: `source ~/work/tpu_cmd/tpu_wrapper.sh &&
  tpu queue ...`. Never call `xm launch` / `xmanager launch` directly; only the
  wrapper may do so internally.
- **One shared launcher.** `~/work/tpu_cmd/xm_launcher.py` owns packaging,
  staging, and job registration. Projects contribute versioned configuration,
  not their own launcher.
- **Put semantics in versioned config; keep only routing and transient
  selectors on the command line.** Model, data, and training behavior belong in
  the config file.
- **Edit the run config in place and launch with no config argument.** Behavior
  living in an invocation string is reproducible only while that string
  survives, and it survives nowhere durable; naming configs also grows one file
  per finished experiment. Nothing is lost — the snapshot is immutable and a
  helper copies a past run's exact config back out (`infra/tpu_cli.md`).
- **When the checkout is shared, edit the config in a COPY and launch from it.**
  "In place" means in the file the launcher reads, not the shared worktree:
  every launch overwrites that one file, so two agents launching minutes apart
  package each other's experiment. Copy the checkout, write the config there,
  launch, delete the copy — packaging rsyncs into a fresh snapshot anyway and
  reads neither VCS state nor the launch directory. **Code changes are the
  exception**: they belong in the shared checkout and must be committed there,
  since a copy is deleted and its provenance with it.
- **Confirm before launching**: checkout, branch, dirty state, effective config,
  allocator, target. Use real attribution; never insert a placeholder to silence
  a prompt.
- **Verify the SNAPSHOT, not the file you edited.** One `diff` of the packaged
  config against what you meant to run covers the whole path: the copy, the
  overwrite, and the launcher's staging.
- **Packaging freezes the code.** The wrapper packages a snapshot; later edits
  do not affect a queued or running job.
- **Verify registration after submit** rather than assuming the launch
  transaction completed.

## Requirements And Runtime

- **A job meant to consume guaranteed capacity must set the PROD service tier
  explicitly.** Do not substitute a legacy priority field or accept a lower
  tier; omitting the tier defaults to PROD.
- **Priority <= 25 charges the person; above it charges the group.** The free
  tiers simply do not touch the team's GCU allocation. `BATCH` reads like the
  cheap option and is the opposite: a *paying* best-effort tier billing the
  group.
- **A CPU-only batch job does not belong in an accelerator group.** In GQM, CPU
  and RAM are *ancillary* to accelerator usage, so a job asking for neither is
  scheduled last, always — structural, and waiting never fixes it (a priority-0
  probe sat in `starting` for 14 hours). Use the shared best-effort CPU pool
  (`go/gdm-cpu-only-jobs`, `--group=8` in our launcher): **pre-authorised** —
  own LDAP, no request, no approval — and it bills nothing. **Its ceiling is per
  user** (order 1000 GCU, 1 TiB RAM), so two 900-task jobs evict *each other*;
  run them serially.
- Container-style packaging requires the pool to have a mapped cloud project;
  native allocators without one need Bazel packaging.
- **In JAX jobs, parse flags before distributed initialization**, and never
  initialize at module import time. `projects/eqr_jax.md` has the
  google3-specific startup order, stricter than the public contract.

## Choosing Where To Run

Packaging costs minutes; an allocator rejects in seconds — settle placement
first. The decisions are here; the mechanism is in `infra/`.

- **Convert power classes before you launch.** A chip count is not a size
  (`tpu_reference.md`); `tpu route --power=` turns a power class into a concrete
  allocation, type, and cell.
- **Preflight before packaging.** Fifteen seconds, and it catches the common
  rejections — illegal topology, minimum-slice rules, no capacity of that
  platform, thin headroom (layers in `infra/tpu_cli.md`). The wrapper refuses to
  submit on red without an override.
- **Preflight cannot verdict a CPU-only job at all** (`Unknown accelerator arch
  'cpu'`) — it models TPU allocations only. Submit those with
  `--skip-preflight`: skipping a check with no opinion, not overriding a
  warning.
- **A green verdict is necessary, not sufficient.** It cannot see topology
  fragmentation — free chips spread across cells with no contiguous slice make
  the allocator accept the submit then reject it seconds later (the daemon
  auto-retries that one rejection) — nor predict a market outcome, transient
  attribution rejects, or prompts. Ask for several candidates and prefer cells
  that historically work for you.
- **Never read a full quota floor as a blocker, and never let preflight's
  YELLOW about it stop a launch.** `used == quota, available 0` is the STEADY
  STATE of these allocs, not a problem: the floor is a guarantee, not a limit,
  and the job still queues and still runs. Preflight says YELLOW for it every
  time; that line is informational. The only numbers that decide anything are
  the per-cell obtainable counts and, once submitted, the work unit's own
  `GQM_RESOURCE_DEFICIT_INFO`.
- **A fully-consumed quota floor does not mean nothing will schedule.** The
  per-group view can read `used == quota, available 0` while tens of thousands
  of chips are obtainable: a floor is a guarantee, not a limit
  (`infra/quota_market.md`). The number that decides whether a job starts is the
  per-cell obtainable count in preflight's `--json`. It is **volatile and
  uncorrelated with storage** — the cell with the largest co-located quota can
  have *zero* while middling cells run to completion — so re-check immediately
  before launching and pick a cell currently good on both axes.
- **`tpu route` samples cells too — ask `tpu preflight --json` for the list.**
  The router's table shows ONE cell per accelerator, and reading it as the
  complete answer says an accelerator exists only where the sample landed:
  `tpu route --power=v6p-64` reported v6p solely in `yuphxrp` (phx, no team
  storage), while preflight's `cells_ok` listed nine cells including
  `yutulpz` (tul) and `yucbfiv` (cbf) — both co-located with our data. That
  near-cost a run its data locality.
- **The market summary samples cells; it does not enumerate them.** Reading its
  price table as the complete list understates where an accelerator exists —
  enough to have sent one plan chasing quota in one metro when the chips were in
  a dozen. For *where can this run at all*, read the router's market cache
  (`infra/quota_market.md`), then intersect with storage placement
  (`storage.md`).
- **Prefer cells whose metro holds storage you can actually write** — the
  scheduler ranks on capacity and price and knows nothing about your data, so
  the cell with the most free chips is often the one with no team storage, where
  everything lands on the personal per-cell ceiling (`storage.md` owns placement
  and why distance kills a run). Make it a *preference* over a cell list, not a
  ban: a storage-less cell is real capacity as long as something sweeps the
  quota. The platform reads a multi-cell allow-list only in its
  spatially-flexible mode, so set both together; pinning a cell bypasses both.

## Preemption, Restart, And Resume

- **A restart restores nothing.** The binary re-executes from the top on a fresh
  machine with the same arguments: no process state, memory image, accelerator
  snapshot, or execution position. Continuity is the application's job, via
  checkpoints.
- **A job with no restart budget dies on its first preemption.** The defaults
  are "never restart": the preemption is a free failure, but the non-zero task
  exit when the gang is torn apart is counted and the job declared dead. Always
  pass an explicit scheduling policy — ours allows unlimited task failures but
  at most one per task per credit window, so a long run survives unrelated
  preemptions while a task that keeps dying is declared dead rather than retried
  forever.
- **Checkpoints must not live in the working directory.** It is task-local and
  wiped by the very event the restart budget exists to survive; a budget without
  durable checkpoints only buys the right to redo the run from step zero.
- **A preempted job can stay `running` and never progress again.** Where each
  task walks a fixed list of work items, an index already passed is never
  revisited, so once the tail is preempted the job holds its slot, reports
  healthy, and produces nothing forever. **Gate completion on progress, not
  liveness** — poll finished units and act when the count *stalls*, not when the
  job disappears. Two corpora each stopped a handful of units short this way, so
  budget for finishing a tail by other means.
- **Size a work unit against the preemption window, not against convenience.** A
  unit longer than the mean uninterrupted window can never complete, and the
  failure is silent: every task busy, nothing emitted, no error. A ~6-minute
  window against a 195-minute shard is permanent zero progress that looks
  exactly like a healthy job; re-slicing to minutes costs nothing when the work
  is a pure function of its index.
- Two settings worth copying into any launcher: **open log-read access**, so
  anyone including future-you reads logs without an ACL dance; and **no
  interconnect-resilient slice** for accelerator jobs, since resilience costs
  roughly a third of throughput and rescheduling onto a healthy slice beats
  finishing much slower.
- **A restart loop is not evidence of a crash, or of slowness.** A training loop
  producing zero steps returns normally, exits 0, and the scheduler starts it
  again — forever, with nothing in the logs but successful runs. Use the
  kill-versus-exit tests in `engineering.md` before blaming infrastructure, and
  verify a resume by **step progress**, never by exit status.

**Resuming an experiment is not pointing at a checkpoint.** The resume flag
appends a work unit to an existing experiment, and since the checkpoint prefix
derives from the experiment id, the new attempt lands on the same prefix where
auto-resume finds the newest complete checkpoint. The launcher must **not** also
pass an explicit load path: only the job knows which step finished writing, and
auto-resume yields to an explicit request, so a guess both supplies an unusable
path and disables the mechanism that would have found the right one. Reserve one
for a genuinely external checkpoint, at a concrete step directory.

**A resume re-runs the ORIGINAL snapshot, never the current checkout.** That
snapshot is immutable and already built; packaging the working tree instead
resumes a checkpoint into code it has never seen, and an active checkout drifts
away within days — retired config keys are *refused* by the newer validator, so
a run's own config dies at flag-parse time after a full packaging round, and a
new default that adds or renames a module makes the checkpoint unrestorable,
surfacing minutes in as a model mismatch. So resolve the stagedir from the job
registry and re-run that, treating a missing or unknown stagedir as an error:
falling back to "package whatever is here now" is the bug, not the recovery.
**A deliberate code change belongs in a new experiment**, where the comparison
is honest, not in a resume where nothing records that the code changed.

**Auto-resume must live in the application**, in-process at startup: read the
checkpoint prefix, skip if an explicit load was requested or the run is
eval-only, enumerate the step directories, **ignore any directory missing the
marker file written last** (its absence means the write was interrupted), and
resume from the highest surviving step. Enumerating the prefix beats parsing
logs, which a rotation would restart from zero.

## Identity, Paths, And Local Disk On A Worker

- **A cluster job is a different security principal from you.** Nothing you read
  interactively is automatically readable from a worker, and the same wall
  blocks log mirroring to a personal bucket. Cheapest fix by far is the internal
  distributed filesystem, which the job identity reads and writes natively —
  usually a one-line path change. Otherwise a bucket owner must grant the job's
  principal access; an org-level deny policy can block even owners, and
  service-account keys are not an option.
- **The temporary directory is a RAM disk you must size yourself.** The default
  is small and every task stages its own private copy of what it downloads, so
  an undersized value surfaces mid-run as "no space left on device". A job
  moving large files should stream through a bounded buffer instead.
- **The RAM disk and the memory limit are two different knobs** the launcher
  must pass explicitly; sizing `/tmp` does nothing for a process that allocates.
  Watch for a resource that must be named in its own field: appended to the
  accelerator string it reads as a second *accelerator*, accepted and ignored.
- **Shell file utilities do not exist inside the container**, and **the standard
  library breaks on a distributed path or remote URI** — `os.path` raises a
  permission error or silently answers False, a bucket URI fails a directory
  check, and normalization mangles the URI, which is how a valid remote load
  path becomes a bogus "does not exist". Route every existence check and remote
  read through the project's path helpers. This survives a green build and a
  local smoke test, because it only fires remotely.
- **The launcher-to-application contract travels as environment variables**, not
  config flags: the external checkpoint to load, the tracking run to continue,
  and the durable checkpoint prefix. That prefix derives from the experiment id,
  so every restart resolves to the same location — the stability that makes
  in-process auto-resume well defined. Do not inject a checkpoint path as a
  config flag if the config schema is locked; every job dies at startup.

## Status And Diagnosis

1. Start from `tpu check` and resolve the exact experiment and work unit.
   Experiment-level "running" does not prove hardware was allocated — use
   work-unit state, allocation, logs, and activity to tell queued from
   executing.
2. **Read the failure classification before anything else.** A code-bug verdict
   means the fix is in your source, so hunting preemption or quota is wasted
   time. The column comes from a cache refreshed about once a minute, so run the
   checker binary directly for an immediate answer; a blank verdict on a pending
   job means "queued, nothing wrong".
3. Read the complete relevant failure, not the final status string: an immediate
   failure with no logs can be allocator, topology, packaging, or authorization.
4. If the error explicitly names expired credentials, ask the user to
   re-authenticate and retry — do not diagnose every access failure as a
   credential problem.
5. If log access still fails with a valid identity, use the supported API or the
   checker tools to read the work-unit status message. Do not patch shared
   scripts with hard-coded job ids, and do not assume an alternate API bypasses
   authorization.

The job registry, its archived predecessor, config recovery from a snapshot, and
cancel-versus-clear semantics are in `infra/tpu_cli.md`.

**"Clean up the finished runs" means `tpu clear`, not deleting data.** The word
is ambiguous and the two tools are unrelated: `tpu clear` tidies the BOARD,
archiving finished and failed registry entries to `~/.tpu_jobs_legacy.json`
(never deleting them, and config recovery still resolves archived ids), while
`tpu gc` is the checkpoint sweeper on CNS. Reach for `clear` when `tpu check` is
cluttered; reach for `gc` only when a cell is filling up. Allow one daemon cycle
(~60s) for cleared entries to leave the board.

## Debugging A Job That Dies With No Log

**Reproduce locally first.** The staged package is an ordinary build target, so
the exact artifact the cluster will run builds and runs on the workstation, and
`--help` is enough: flags parse only after every module-level import, so
import-time failures surface in seconds. Do this before any launch that changes
imports or dependencies.

**Recognize a pre-`main()` death by its shape**: an empty status message, no
application log anywhere including any the app mirrors, and no surviving job
handle. Seeing all three at once *is* the diagnosis — do not re-launch to
collect logs that cannot exist. **But check the storage quota before trusting
that shape**: an over-quota cell yields the same evidence from a job that ran
for hours, because the log file is *created* and its first write refused, so a
0-byte log means either "never started" or "could not write". Artefacts
timestamped long after launch settle it instantly (`storage.md` §An Over-Quota
Cell Looks Like A Broken Program).

Getting logs, most reliable first:

| Source | Caveat |
|---|---|
| The staged binary run locally | Only reproduces import- and startup-time failures. |
| The work unit's job state — cell, user, job name, task counts, status message | Ask the API for *detailed* status explicitly or the field is silently empty, reading exactly like "the job is gone". The job is garbage-collected within minutes; the status message survives much longer and usually carries the actual exception. |
| **Application-level log mirroring to durable storage**, teed from program start and flushed on error lines | Outlives task, work unit, and experiment, but only covers failures after the program starts. Under Borg it is often the *only* log, so protect it (`engineering.md`: handlers steal streams). |
| The log-tailing CLI | Works sometimes. |
| The log-search CLI | May be blocked by workstation permissions. |

**Two failure modes survive a green build and a local smoke test** because both
only fire remotely: **standard-library file APIs against a distributed path**
(§Identity, Paths, And Local Disk On A Worker), and **mocked third-party
libraries**, where the build substitutes stubs for some external packages
(`engineering.md` §Failure Modes That Only Appear On The Long Path).

## Launcher-Side Failures That Look Like Scheduler Failures

The submit path runs on the workstation and several of its failure modes produce
an XID with no work unit, or no XID at all. **A job that never created a work
unit, or a launch that produced no XID, never reached the scheduler** — read
those as local problems, not allocator or quota rejections.

- **Never pipe content into the submit command.** Each attribution question is
  satisfied by an EOF, so redirecting from `/dev/null` answers all of them, and
  piping something like `yes` segfaults the underlying CLI outright — no XID, no
  diagnostic.
- **A full `/tmp` breaks the submit with `SIGBUS`.** `/tmp` is RAM-backed tmpfs,
  so a core dump from a local repro fills it and the next writer dies on a page
  it cannot get. Disable cores for local repro runs and check free space before
  submitting; every byte in `/tmp` is RAM taken from the machine doing the cold
  imports.
- **Bazel refuses to glob a package containing an absolute symlink**
  ("Absolute symlinks are forbidden"), so a checkout that symlinks the shared
  launcher must be copied in with symlinks dereferenced. The rejection is cached
  in the package glob cache, so fixing the tree is not enough — restart the
  build server.
- **The launcher forwards flags as a `key=value` dict, so the binary must
  survive that shape.** `--app.<flag>=<v>` passes one flag verbatim, but a
  *positional* argument is inexpressible and a `store_true` flag arrives as
  `--flag=` and is rejected by argparse. Both kill every task inside argument
  parsing, before any logging, and with an unlimited restart budget the job
  churns forever writing nothing — exactly like a scheduler problem. Select
  subcommands with a valued flag; give every boolean an explicit value.
- **A flag must behave correctly for BOTH "absent" and "present but empty".**
  A default of `""` collapses two different inputs: the flag was passed, parsed
  as empty, took the default branch, and the fleet silently ran the wrong mode.
  Default to `None` and test all spellings.
- **Have each task record its own identity and mode where you can read it
  later.** On a job whose tasks never log, a startup marker written to
  distributed storage may be the only diagnostic that exists — and it is how the
  next trap gets caught: **`$BORG_TASK_INDEX` is never set by XManager**; use
  the BCL `%task%` macro.

## Metrics And Curves

There is no external experiment tracker here; the internal equivalent stores
scalars in a table service and plots them in a dashboard service, both keyed by
experiment id. `research/result_logging.md` owns the URL forms, how to verify a
run actually wrote metrics, and the settings that are easy to get wrong
(explicit opt-in, rank-0 only, periodic flush).

- **An empty chart page means no data was written, not a broken link.** There is
  no 404 for a missing table, so a blank page is a writer problem to diagnose in
  the job, not a URL to retype.
- A job that never calls a metric writer produces no table at all; writing is
  one dependency plus one constructor call.

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this guide whenever implementation details change.
