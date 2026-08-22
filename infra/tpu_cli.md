# The `tpu` Tooling Itself

The `tpu` CLI, its checkers, cache daemon, job registry, and preflight
internals. Read this only when changing, rebuilding, or debugging the tool —
using it to launch and inspect jobs is `../jobs.md`. Native code and
`~/work/tpu_cmd/README.md` outrank this file for flags and workflows.

## Two Halves, Two Repositories, And Why

| Half | Location | Contents |
|---|---|---|
| Shell + launcher | `~/work/tpu_cmd/` | wrapper script, launcher, README |
| Built checkers | a google3 CitC path under `experimental/users/<user>/tpu_utils/` | money/quota/infra checkers, shared utilities, preflight (topology, capacity, market, router), probes |

The split is forced by the build system, not preference: the checker half
imports google3 packages, depends on internal build targets, and the daemon runs
its compiled binaries on a loop.

**The google3 half cannot be symlinked out.** All three variants fail — an
absolute directory symlink is rejected outright, a relative one escapes the
source root, per-file symlinks fail at action execution. Only the reverse works:
real files in google3, a symlink in `~/work` pointing at them, for navigation.

Both halves are versioned, the google3 half through a separate git directory so
the worktree stays in place and the build is unaffected — only a tiny pointer
file sits in the source tree. Do not unify them with one repo plus a symlink:
git records a symlink as the link itself, so committing it backs up none of the
files behind it. And **a source-control checkout is not a backup** — the checker
half is still unknown to the depot, so until its change submits the git repo is
the only recovery path. Verify with `g4 files
//depot/google3/experimental/users/<user>/tpu_utils/...`: "no such file(s)"
means the git repo is still the only copy.

**Self-asserting test scripts** (exiting non-zero on failure instead of using
the test framework) must be declared as test targets; declared as binaries they
silently never run and the test command reports that no tests were found.

## A Frozen Board Outlives Its Cause

**A long-lived daemon whose cwd is on the CitC FUSE mount dies silently when
that mount is recreated.** Its python children then fail at `os.getcwd()` with
`OSError: [Errno 107] Transport endpoint is not connected`, every checker
produces empty output, and the "only overwrite the cache when the new output
is non-empty" guard — which is correct — keeps the last good board forever.

**The symptom is not an error, it is plausibility**: `tpu check` renders every
job as `SUBMITTED`, the cache-miss fallback, so the board looks like a queue
that has not started rather than a board that stopped updating. The process is
alive, the loop is turning, and the log is scrolling the whole time.

**Diagnose by timestamp, not by liveness**: `ls -la ~/.tpu_check_cache.txt`
against `date`. A `.tmp` file that is newer than the cache AND zero bytes is
the signature. `tmux capture-pane -t tpu-daemon -p | tail` shows the real
error; the daemon's own stderr never reaches the board.

**Restart with an explicit start directory outside the mount**, or the new
process inherits the dead handle from its parent:
`tmux respawn-pane -k -c "$HOME" -t tpu-daemon '<the while-true loop>'`.

## One Tool, Two Operators

**`npu` is `tpu` with a different registry, not a fork.** A collaborator
(lyy) works on this workstation under the same Unix account, so ownership is
expressed by four environment variables that every consumer reads with the old
hardcoded path as its default: `TPU_JOBS_FILE`, `TPU_JOBS_LEGACY_FILE`,
`TPU_CHECK_CACHE_FILE`, `TPU_JOB_NAME_PREFIX`. Unset, the tool behaves exactly
as it did before they existed — the way to verify a change here is to diff the
full `tpu check` output against the pre-change script, not to eyeball it.

The `npu` function sets them with `local -x`, never a bare `export`: a plain
export would leak into every later `tpu` in that shell and silently file the
owner's next job into the collaborator's registry.

**A second registry needs a second daemon.** The board renders from
`$TPU_CHECK_CACHE_FILE`; with nobody writing it, every job on that board reads
`SUBMITTED` forever while looking perfectly alive (`run-npu-daemon.sh`).

**It is bookkeeping, not a boundary** — same Unix user, same XManager account,
same quota. The `lyy-` experiment-title prefix exists because the XM UI is the
one view that cannot see the registry split.

**Splitting the registry splits what each operator WRITES, not what they see
or can touch.** Every consumer that reaches past the registry has to be scoped
by hand, and each of these shipped broken because the registry split looked
like it had covered them:

- **The board unions two sources with different scopes.** `check` merges the
  per-operator registry with the `infra_check` cache, and that cache is
  per-ACCOUNT: it lists every experiment the Unix user owns, whoever launched
  it. Unioned blind, the collaborator's board showed all 33 of the owner's
  runs. A scoped board keeps a job only if the operator's own registry records
  it **or** its name carries their prefix — the second clause covers a job
  launched outside the registry, and the prefix survives the cache's name
  truncation because it sits at the front.
- **`cancel` is destructive and was unguarded.** It passed any XID straight to
  `xmanager stop`; one mistyped digit stopped the other operator's job. A
  scoped operator may cancel exactly what their own board shows, and a mixed
  batch is refused whole rather than half-executed.
- **Auto-recovery managed the *other* operator's process.** The quota/money
  cache is legitimately shared, but the daemon writing it belongs to the
  account owner. A stale cache plus one `npu quota` ran
  `tmux kill-session -t tpu-daemon` and killed it — the frozen board that
  recovery exists to repair, caused by the repair.
- **A consumer that reaches past the registry may still read the owner's, and
  some still do.** `infra_check` reads a hardcoded `~/.tpu_jobs.json`, not
  `$TPU_JOBS_FILE`, so the guest daemon's infra pass polls the OWNER's registry.
  Harmless only because both boards then reflect the owner's jobs; a real fix
  scopes the path. Treat any unscoped path here as a latent instance of this bug.

**The owner stays unscoped on purpose.** Whoever pays for the quota needs to
see and stop everything running on it; the partial view belongs to the guest.

`scripts/test_operator_scope.sh` pins all of it, with `xmanager` and `tmux`
shadowed by shell functions so it touches nothing real. A guard nobody can
break on purpose is a guard nobody notices deleting.

## The Cache Daemon

The status commands read a cache file, so they are instant; all latency lives in
the background daemon refreshing it, and the commands warn when the cache is
stale. **A full daemon round must therefore finish well inside the staleness
threshold.**

- **Split the round into a fast lane and a slow lane.** The commands warn per
  cache, so a slow checker must not hold a fast one past the alarm. money and
  quota are cheap (~40s) and the round WAITS for them; infra_check scales with
  registry size (one serial RPC per tracked job) and takes minutes, so it runs
  DETACHED — the round never waits on it, and a `kill -0` guard skips launching
  a second pass while one is still in flight. A single `wait` barrier over all
  three once let a multi-minute infra pass age money.txt past its threshold
  while money's own data had been ready for seconds.
- **Every checker cold-starts once; keep them out of a serial chain.** Each pays
  a substantial interpreter cold start while its RPCs cost under a second, so
  running them one after another pays that tax repeatedly. They share no state
  and write to disjoint outputs, so they run in parallel.
- **Rebuild all checker binaries in one build invocation.** Building a single
  target can publish an output namespace holding only that target, and the
  daemon then reports failures that look like data or auth bugs.
- **Never `readlink -f` the build output symlink.** It is two hops with opposite
  lifetimes: the first is stable and worth pinning against a concurrent build,
  the second is republished per build with only that build's targets behind it.
  Collapsing both freezes the daemon inside one build's namespace where no later
  rebuild can reach it — binaries sit in `blaze-bin`, correctly built, while the
  daemon insists they do not exist. Pin one hop, re-resolve the rest at each
  use, and fall back to the live path.
- When the staleness alarm fires, **check the round duration the daemon logs
  before believing its "credentials expired" hint** — that message is a guess
  and is usually wrong.
- **A checker the daemon cannot find is repaired by the daemon**, rate-limited,
  rebuilding all of them together. A hint printed into a detached tmux pane is
  not a fix, and the staleness auto-recovery restarts the session — never the
  problem.
- **The command re-renders the cache; it does not print it.** `tpu check` parses
  the daemon's cached table and rebuilds its own, so a column the daemon
  computes and writes can still be invisible if the command's parser drops it.
  The running table's per-cell placement (`REGION`, e.g. `europe (lpp)`) lived in
  the cache for a long time while the command showed only `XID|STATUS|NAME|…|WHY`
  — the fix was in the parser, not the daemon. Before concluding "the tool does
  not collect X", run the daemon binary directly and diff its columns against
  what the command prints; the section layouts differ (running carries an extra
  `REGION|DETAILS` pair the 6-column pending/done rows do not), so a parser must
  gate per-section on the column count rather than a fixed index.
- **`AGE` is derived in the wrapper, not the daemon.** The active/pending tables
  show `AGE` = wall-clock since *submission*, parsed from the timestamp
  `tpu_wrapper` already baked into each entry's `logdir`
  (`eqr_run_YYMMDD_HHMMSS`) or `bucket_cp_path` (`..._YYYYMMDD_HHMMSS_...`) in
  `~/.tpu_jobs.json` (`_age_str`). It is submit-age (queue + run), NOT pure Borg
  run-uptime — the daemon cache carries no work-unit start time, so "how long has
  it actually been *training*" still comes from `STEP × sec/step`, not `AGE`. On
  the pending board `AGE` doubles as "how long stuck in the auction". Add a
  wrapper column by editing the per-section `*_headers`/`*_caps` lists and the
  matching `*_rows.append(...)` — no daemon rebuild needed, effect is immediate.

## Job Bookkeeping

The live registry is the file `tpu check` renders from; an older predecessor
file is no longer written and survives only as a fallback for resume.

- **A terminal row is polling load, not just clutter.** infra_check issues one
  serial RPC per tracked job, so hundreds of never-migrating rows
  (`TERMINAL_RECONCILED`, `CANCELLED`) inflate the round for jobs whose state
  can never change again. The daemon filters terminal status out of its poll
  set, and archiving them keeps the live registry small; do both, since a fresh
  registry accretes them continuously.
- **Clear archives rather than deletes**, moving entries to a legacy file. Keep
  it: an entry is the only mapping from an experiment id back to its checkpoint
  bucket, staging directory, and launch log once the job and work unit are gone.
- **Cancel is not clear.** Cancelling stops the experiment and pins the registry
  entry so the daemon's auto-retry can never resubmit an explicitly killed job;
  the entry stays on the board until archived.
- **Recovering a past run's config** is a shell helper that reads the staging
  directory from the registry (falling back to the legacy file, so archived ids
  still resolve) and copies the exact config out of that immutable snapshot,
  learning *which* file by grepping the launch log because a snapshot holds the
  whole config directory. This answers "which config produced this run", and is
  why deleting a finished experiment's config from the checkout is safe.

## Error Classification And Auto-Retry

The daemon parses launch logs and classifies failures — defragmentation
preemption, resource exhaustion, allocator rejection (the fallback for a failure
with no stated reason), and unknown.

**Auto-retry is narrow on purpose**: only a guaranteed-tier job rejected by the
allocator is retried, a few times, minutes apart. That is the client
resubmitting a *new experiment*, a completely different mechanism from the
in-job restart budget in `../jobs.md`, and **preempted jobs are not covered.**

**A preempted job is dead, not pending** (`../jobs.md` owns why: no restart
budget means the torn-down gang counts as a task failure). Rendering any work
unit whose message merely contained "preempt" as pending made dead experiments
look like they were queuing for hours: **terminal state must win over a
substring match**, while a genuinely queued job preempted earlier is labelled as
such. When changing this logic, remember the daemon runs compiled binaries — a
source edit does nothing until you rebuild.

## Preflight Internals

Verdict layers, cheapest first: an in-process topology whitelist plus
per-allocation minimum-slice rules; one availability RPC asking whether any cell
in this allocation and tier has enough obtainable chips; and a headroom
heuristic warning when remaining quota is thin — on dynamic pools that last
warning is near-permanent and low-signal.

The router ranks surviving candidates by cap-blocked status (a blocked
combination is kept and explained rather than silently dropped), verdict,
headroom, cost, and accelerator preference. **Headroom differs by tier on
purpose**: the guaranteed tier uses remaining quota, the batch tier obtainable
chips, because the batch pass never consults a floor. Market data comes from a
cache the money checker writes each daemon round, so the router stays offline
and fast; when that cache is missing or stale it says so loudly and falls back
to price-blind ranking rather than failing.

**Per-allocation minimum-slice rules are pool policy, not physical law** — a
slice below the minimum is a valid hardware topology, disallowed by the
admission config and rejected instantly. The batch tier typically allows down to
the architecture's own minimum. These rules live in a table in the preflight
code; update it when an allocation behaves differently.

## Metrics Tables

Tables expire after a long window measured from **last access**, renewing on
every read or write; pin one explicitly if it must outlive that.

**The table CLI does not work from this workstation** — a restricted credential
blocks the service and every local binary hits the same wall. This is a
workstation limitation only, a job writes fine; use the browser URLs in
`../research/result_logging.md`.

## The Local-Queue Smart Router

Two things share this core: the **default** smart cell pick that every
`tpu queue` now does (`pick_cell`), and the **advanced** local queue that drains
unlimited enqueues with auto-reroute (`route_check` / `queue_cli`). User-facing
workflow is `../jobs.md` §Choosing Where To Run (the default) and §The Local
Queue (advanced). Neither replaces the one-shot `tpu queue` — the picker only
pins a `--cell` onto it. Modules in the google3 half, each a
`pytype_strict_library` with its own `pytype_strict_contrib_test`:

| Module | Role |
|---|---|
| `route_lib.py` | Pure scheduling core: queue schema (`QueueEntry`), placement, priority + seeded-random fairness, cell ranking by placeable slices, effective-price type selection (raw price discounted by a pool-size bonus), topology lock. No I/O, no RPC — unit-tested in full. |
| `avail_provider.py` | Wraps `GetCellAvailability` (the same RPC as `slice_probe`) plus the money `market.json` cache into `(avail_by_cell, arch_price, arch_pool)`. Free chips (`max_available_chips`) decide; `obtainable_capacity` is never read for a decision — it lies. |
| `pick_cell.py` | **The default-path picker.** One RPC for the requested type, ranks with `best_cell_for_shape`, prints the single best cell (or nothing). `tpu queue` pins `--cell=<that>` unless the user pinned a cell / used `--power` / passed a comma type / set `TPU_NO_SMART_CELL=1`. Accepts `--metros` (the wrapper forwards `tpu queue --metro/--metros`) so a data-locality-locked run stays in its storage metro while still dodging the oversold cells inside it. FAIL-SAFE by contract: any failure prints nothing and the wrapper lets the allocator choose. |
| `route_check.py` | The tick: load queue → fetch availability → plan → submit via `tpu queue` (default `--dry_run`). `--reroute` cancels jobs stuck PENDING past the deadline and re-queues. Binary + library share the source; the binary target just re-exports it. |
| `queue_cli.py` | `tpu enqueue` / `queue-status` / `dequeue`. Reuses route_check's queue persistence and a dry-run planning tick for the live status view. |

**Side effects sit behind seams so the whole thing unit-tests offline.** The
submitter (`tpu queue`/`tpu cancel` shell-out), the availability provider, and
the XManager status probe are all injected; the 90-plus tests use fakes and
never touch a real RPC or shell. Keep it that way — a test that needs the network
is a test that will not run in the daemon's build.

**A cell can host two accelerator generations at once** (`je` carries both a
v6e and a v7 pod; `nk`/`nl` both v6e and v6p). Availability is therefore keyed
per `(cell, arch)` as `cell|arch`, not by bare cell name, or the second
generation silently overwrites the first and the router never sees it. Anything
that draws down a cell's free chips within a tick must match by content
(cell AND arch), not by dict key.

**A topology-locked job must anchor its mesh before the first placement.** Once
placed, `locked_geometry` is frozen and only same-mesh shapes are eligible
(`v6p-32`↔`v7-32`, both `2x4x4`; never `v6e-32`, `4_8`). Before the first
placement there is no pinned geometry, so it anchors to the mesh named by the
job's own `--power` spec — a locked `v6p-32` never first-lands on a v6e-64 (`8_8`)
that merely fell inside the power tolerance window. A bare-int power names no
arch, so a locked job with one is unplaceable by design (it would be guessing a
mesh for a sharded checkpoint).

**The re-route sweep never cancels on missing data.** It only cancels a job the
XManager probe CONFIRMS is still PENDING; UNKNOWN (probe failed, no work units)
is a no-op, and a job that has since started RUNNING is promoted, not killed. The
clock rule (submitted, older than the deadline) is `route_lib.needs_reroute`; the
live check and the cancel/cool-down side effects are in `route_check.run_reroute`.

**The daemon's router lane is the 4th lane, OFF by default.** `TPU_ROUTE_ENABLED`
unset is a complete no-op — the daemon behaves exactly as before. Armed, it runs
like the infra lane: DETACHED with a `kill -0` guard, so its serial RPCs never
delay the money/quota fast lane, and `TPU_ROUTE_DRYRUN=1` (the default when
armed) plans and logs without submitting. The queue file is operator-scoped like
the registry: `npu` points `TPU_LOCAL_QUEUE_FILE` at lyy's copy, so an enqueue
under one operator never lands in the other's queue.

**Building it: `blaze build $CHECKER_SUBDIR:{route_check,queue_cli,pick_cell}`**
(the binaries; the libraries and tests come along as deps). A py-strict binary
may not depend on another binary — that is why each binary's logic lives in a
`*_lib` library that the binary and any dependent (queue_cli on route_check_lib)
import, rather than one binary importing another. The wrapper's `_PICK_CELL_BIN`
points at the built `pick_cell`; if it is ever missing, `tpu queue` simply skips
the smart pick (fail-safe) — so rebuild it with the others after any change.
