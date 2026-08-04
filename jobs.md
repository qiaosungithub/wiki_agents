# Running Jobs On The Cluster

Read this to queue, inspect, resume, or debug a job on the internal
XManager/Borg stack. `storage.md` owns where data and checkpoints live;
`tpu_reference.md` owns accelerator naming and shapes; `infra/` holds the
market, allocator, and CLI internals you need only when the basics do not
explain what you see.

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
- **Edit the run config in place; do not select or override it from the command
  line.** Write what you intend to run into the project's single run config and
  launch with no config argument. Two reasons, both learned the hard way:
  behavior that lives in an invocation string is reproducible only if that
  string survives, and it survives nowhere durable; and naming configs on the
  command line turns the config directory into one file per finished experiment
  (one project reached 39, was pruned to 5, and grew back). Recovering a past
  run's config is already solved — the source snapshot is immutable, so a helper
  copies the exact file back out.
- **Confirm before launching**: checkout, branch, dirty state, effective config,
  allocator, target. Use real attribution; never insert a placeholder to silence
  a prompt.
- **Packaging freezes the code.** The wrapper snapshots the checkout and
  packages that snapshot; edits afterwards do not affect a queued or running
  job.
- **Verify registration after submit** rather than assuming the launch
  transaction completed.

## Requirements And Runtime

- A job meant to consume guaranteed capacity must set the PROD service tier
  explicitly. Do not substitute a legacy priority field or silently accept a
  lower tier.
- Container-style packaging requires the pool to have a mapped cloud project;
  native allocators without one need Bazel packaging.
- In JAX jobs, parse flags before distributed initialization, and never
  initialize at module import time. See `projects/eqr_jax.md` for the
  google3-specific startup order, which is stricter than the public contract.

## Debugging A Job That Dies With No Log

**Reproduce locally first.** The staged package is an ordinary build target, so
the exact artifact the cluster will run can be built and executed on the
workstation. Running it with `--help` is enough: flags are parsed only after
every module-level import has run, so import-time failures surface in seconds.
Do this before every launch that changes imports or dependencies. It costs
minutes and catches a class of bug that is nearly undiagnosable remotely.

**Recognize a pre-`main()` death by its shape**: an empty status message, no
application log anywhere including any mirroring the app installs, and no
surviving job handle. Seeing all three at once *is* the diagnosis. Do not
re-launch to collect logs that cannot exist.

Getting logs, most reliable first:

1. Run the staged binary locally.
2. The work unit's job state — cell, user, job name, task counts, status
   message. This usually requires asking the API for detailed status
   explicitly; without that the field is silently empty and reads exactly like
   "the job is gone". The underlying job is garbage-collected within minutes,
   but the work-unit status message survives much longer and usually carries the
   actual exception.
3. **Application-level log mirroring to durable storage**, teed from the start
   of the program and flushed on error lines. It outlives the task, the work
   unit, and the experiment — but only covers failures after the program starts.
   Under Borg this is often the *only* log, so protect it (see
   `engineering.md` on handlers stealing streams).
4. The log-tailing CLI, which works sometimes.
5. The log-search CLI, which may be blocked by workstation permissions.

**Read the failure classification before doing anything else.** `tpu check`
labels the failure; a code-bug verdict means the fix is in your source and
hunting for preemption or quota is wasted time. Two caveats: the column is
served from a cache refreshed roughly once a minute, so run the checker binary
directly for an immediate answer; and a blank verdict on a pending job means
"queued, nothing wrong".

**Two failure modes survive a green build and a local smoke test**, because both
only fire remotely:

- **Standard-library file APIs against a distributed path.** They raise a
  permission error or silently answer False. Anything touching a remote
  checkpoint prefix must go through the path-library helper, never `os.path`.
- **Mocked third-party libraries.** The build substitutes stubs for some
  external packages; missing attributes raise at *call* time, so a path that
  runs every N steps fails minutes into a run.

## Preemption, Restart, And Resume

**A restart restores nothing.** The binary re-executes from the top on a fresh
machine with the same arguments. There is no process state, no memory image, no
accelerator snapshot, no execution position. Continuity of training is entirely
the application's job, via checkpoints.

**A job with no restart budget dies on its first preemption.** The scheduling
defaults are "never restart": the preemption itself is a free failure, but the
non-zero task exit when the gang is torn apart is counted, and the job is then
declared dead. Always pass an explicit scheduling policy. Ours allows unlimited
task failures but at most one per task per credit window — a long run should
survive any number of unrelated preemptions, while a task that keeps dying is a
real bug and should be declared dead rather than retried forever.

Two settings worth copying into any launcher: open log-read access, so anyone
including future-you can read the logs without an ACL dance; and no
interconnect-resilient slice for accelerator jobs, since resilience costs
roughly a third of throughput and being rescheduled onto a healthy slice beats
finishing much slower.

**Resuming an experiment is not pointing at a checkpoint.** The resume flag
appends a work unit to an existing experiment; because the checkpoint prefix is
derived from the experiment id, the new attempt lands on the same prefix and the
application's own auto-resume finds the newest complete checkpoint. The launcher
must **not** also pass an explicit load path: only the job can know which step
finished writing, and an explicit request is exactly what auto-resume yields to,
so passing a guess both supplies an unusable path and disables the mechanism
that would have found the right one. Reserve an explicit load path for a
genuinely external checkpoint, and point it at a concrete step directory.

**Auto-resume must live in the application.** With no external daemon in the
loop, the decision happens in-process at startup: read the checkpoint prefix,
skip if an explicit load was requested or the run is eval-only, enumerate the
step directories, **ignore any directory missing the marker file that is written
last** (its absence means the write was interrupted), and resume from the
highest surviving step. Enumerating the prefix beats parsing logs — a rotated
log would otherwise silently restart from zero.

**Checkpoints must not live in the working directory.** That directory is
task-local and is wiped by the very event the restart budget exists to survive.
A restart budget without durable checkpoints only buys the right to redo the run
from step zero.

**A restart loop is not evidence of a crash, or of slowness.** A job can restart
forever while every attempt *succeeds*: if the training loop produces zero steps
and returns normally, the process exits 0, the scheduler sees a clean finish and
starts it again. Nothing appears in the logs but successful runs. Use the
kill-versus-exit tests in `engineering.md` before blaming infrastructure, and
verify a resume by **step progress**, never by exit status.

## Identity, Paths, And Local Disk On A Worker

- **A cluster job is a different security principal from you.** Nothing you can
  read interactively is automatically readable from a worker, and the same wall
  blocks log mirroring to a personal bucket. Cheapest fix by far is to use the
  internal distributed filesystem, which the job identity can read and write
  natively — usually a one-line path change. Otherwise a bucket owner must grant
  the job's principal access; note an organization-level deny policy can block
  even owners. Service-account keys are not an option.
- **The temporary directory is a RAM disk you must size yourself.** The default
  is small, and every task of a multi-task job stages its own private copy of
  whatever it downloads, so an undersized value surfaces mid-run as "no space
  left on device". A job that moves large files should stream through a bounded
  buffer rather than sizing the disk up to hold a whole one.
- **The RAM disk and the memory limit are two different knobs.** Sizing `/tmp`
  does nothing for a process that allocates; they are separate requirements and
  the launcher must pass each explicitly. Watch for a resource that has to be
  named in its own field: appending it to the accelerator string reads as a
  second *accelerator*, which is accepted and then ignored.
- **Shell file utilities do not exist inside the container.** Use the in-process
  path library for remote I/O from inside a job.
- **Remote URIs break the standard library.** A directory check on a bucket URI
  is always False and path normalization mangles the URI, which is exactly how a
  valid remote load path turns into a bogus "does not exist" error. Route every
  existence check through the project's path helpers.

**The launcher-to-application contract travels as environment variables**, not
as config flags: where to load an external checkpoint from, which tracking run
to continue, and the durable checkpoint prefix for this experiment. The prefix
is derived from the experiment id, so every restart of a given experiment
resolves to the same location — that stability is what makes in-process
auto-resume well defined. Do not inject a checkpoint path as a config flag if
the config schema is locked; every job will die at startup.

## Launcher-Side Failures That Look Like Scheduler Failures

The submit path runs on the workstation, and several of its failure modes
produce an XID with no work unit, or no XID at all. Read them as local problems,
not as allocator or quota rejections.

- **Never pipe content into the submit command.** The launcher asks a handful of
  attribution questions; each is satisfied by an EOF, so redirecting from
  `/dev/null` answers all of them. Piping something like `yes` instead
  segfaults the underlying CLI outright — no XID, no diagnostic.
- **A full `/tmp` breaks the submit with `SIGBUS`.** `/tmp` is a RAM-backed
  tmpfs, so a core dump from a local repro can fill it and the next writer dies
  on a page it cannot get. Disable cores for local repro runs, and check free
  space before submitting. Remember every byte in `/tmp` is a byte of RAM taken
  from the same machine that is doing the 5-minute cold imports.
- **Bazel refuses to glob a package containing an absolute symlink**
  ("Absolute symlinks are forbidden"), so a checkout that symlinks the shared
  launcher must be copied into the source tree with symlinks dereferenced. The
  rejection is cached in the package glob cache, so fixing the tree is not
  enough — the build server has to be restarted before the error clears.

Distinguishing these from remote failures is cheap: a job that never created a
work unit, or a launch that produced no XID, never reached the scheduler at all.

## Preflight Before You Pay For Packaging

Packaging costs minutes; an allocator rejects in seconds. The client-side
preflight check runs in about fifteen seconds and catches the common rejections:
illegal topologies and per-allocator minimum slice rules, allocations with no
capacity of that platform, and thin headroom. It returns green/yellow/red, and
the wrapper refuses to submit on red without an override.

**A green verdict is necessary, not sufficient.** Preflight cannot see topology
fragmentation — an allocation can have hundreds of free chips spread across
cells with no contiguous slice anywhere, and the allocator accepts the submit
then rejects it seconds later. The only API that reports free-slice topology is
not reachable from here; today the mitigation is the daemon's automatic retry
loop for that specific rejection. Preflight also cannot predict a market
outcome, transient attribution rejects, or interactive prompts.

The router turns a desired *power class* into a concrete allocation, type, and
cell, ranking candidates by whether a price cap blocks them, verdict, headroom,
cost, and accelerator preference. It reads cached market data so it stays fast
and offline, and says so loudly when that cache is stale rather than ranking
blind. It does not solve fragmentation either — asking for several candidates
and preferring cells that historically work for you is the practical answer.

**Convert power classes before you launch.** A chip count is not a size; see
`tpu_reference.md`. `tpu route --power=` does the arithmetic.

**The market summary samples cells; it does not enumerate them.** Its price
table prints a few representative cells per accelerator, so reading it as a
complete list understates where an accelerator exists -- badly enough to have
sent one plan chasing a quota request in the single metro it named, when the
chips were in a dozen. To answer *where can this run at all*, read the router's
cache directly (`~/.tpu_quota_cache_dir/market.json`), which lists every cell
with a price, keyed by an internal card code -- confirm the code by checking
that a cell you already run on appears under it. Then intersect that list with
storage placement (`storage.md`) before choosing.

## Status And Diagnosis

1. Start from `tpu check` and resolve the exact experiment and work unit.
   Experiment-level "running" does not prove hardware was allocated — use
   work-unit state, allocation, logs, and activity to tell queued from
   executing.
2. Read the complete relevant failure, not the final status string. An immediate
   failure with no logs can be allocator, topology, packaging, or authorization.
3. If the error explicitly names expired credentials, ask the user to
   re-authenticate and retry. Do not diagnose every access failure as a
   credential problem.
4. If log access still fails with a valid identity, use the supported API or the
   checker tools to read the work-unit status message. Do not patch shared
   scripts with hard-coded job ids, and do not assume an alternate API bypasses
   authorization.

The job registry, its archived predecessor, config recovery from a snapshot, and
cancel-versus-clear semantics are in `infra/tpu_cli.md`.

## Metrics And Curves

There is no external experiment tracker here; the internal equivalent stores
scalars in a table service and plots them in a dashboard service, both keyed by
experiment id. `research/result_logging.md` owns the URL forms and the rules for
verifying a run actually wrote metrics. Two points worth knowing up front:

- **An empty chart page means no data was written, not a broken link.** There is
  no 404 for a missing table, so a blank page is a writer problem to diagnose in
  the job, not a URL to retype.
- A job that never calls a metric writer produces no table. Writing is one
  dependency plus one constructor call, and the settings that are easy to get
  wrong (explicit opt-in, rank-0 only, periodic flush) are owned by
  `research/result_logging.md` and the project guide.

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this guide whenever implementation details change.
