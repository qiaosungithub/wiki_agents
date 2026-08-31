# The `tpu` Tooling Itself

The `tpu` CLI, its checkers, cache daemon, job registry, and preflight
internals. Read this only when changing, rebuilding, or debugging the tool;
launching and inspecting jobs is `../jobs.md`. Native code and
`~/work/tpu_cmd/README.md` outrank this file for flags and workflows.

## Two Halves, Two Repositories, And Why

| Half | Location | Contents |
|---|---|---|
| Shell + launcher | `~/work/tpu_cmd/` | wrapper script, launcher, README |
| Built checkers | a google3 CitC path under `experimental/users/<user>/tpu_utils/` | money/quota/infra checkers, shared utilities, preflight (topology, capacity, market, router), probes |

The build system forces the split: the checker half imports google3 packages,
depends on internal build targets, and the daemon loops over its compiled
binaries.

**The google3 half cannot be symlinked out.** All three variants fail: an
absolute directory symlink is rejected, a relative one escapes the source root,
per-file symlinks fail at action execution. Only the reverse works, for
navigation: real files in google3, a symlink in `~/work` pointing at them.

Both halves are versioned, the google3 half through a separate git directory, so
the worktree stays put, the build is unaffected, and only a tiny pointer file
sits in the source tree. Do not unify them with one repo plus a symlink: git
records a symlink as the link itself, so committing it backs up none of the
files behind it. A checkout is also not a backup; the checker half is still
unknown to the depot, so until its change submits the git repo is the only
recovery path. Verify with `g4 files
//depot/google3/experimental/users/<user>/tpu_utils/...`: "no such file(s)"
means the git repo is still the only copy.

Self-asserting test scripts, which exit non-zero on failure instead of using the
test framework, must be declared as test targets. Declared as binaries they
never run, and the test command reports no tests found.

## A Frozen Board Outlives Its Cause

**A long-lived daemon whose cwd is on the CitC FUSE mount dies silently when
that mount is recreated.** Its python children fail at `os.getcwd()` with
`OSError: [Errno 107] Transport endpoint is not connected`, every checker
outputs nothing, and the correct "only overwrite the cache when the new output
is non-empty" guard then keeps the last good board forever.

The symptom is plausibility, not an error. `tpu check` renders every job as
`SUBMITTED`, the cache-miss fallback, so the board looks like a queue that has
not started rather than one that stopped updating, while the process stays
alive, the loop turns, and the log scrolls.

Diagnose by timestamp, not by liveness: `ls -la ~/.tpu_check_cache.txt` against
`date`. A `.tmp` file newer than the cache and zero bytes is the signature.
`tmux capture-pane -t tpu-daemon -p | tail` shows the real error; the daemon's
own stderr never reaches the board.

Restart with an explicit start directory outside the mount, or the new process
inherits the dead handle from its parent:
`tmux respawn-pane -k -c "$HOME" -t tpu-daemon '<the while-true loop>'`.

## One Tool, Two Operators

**`npu` is `tpu` with a different registry, not a fork.** A collaborator (lyy)
works on this workstation under the same Unix account, so environment variables
express ownership. Every consumer reads them, defaulting to the old hardcoded
path: `TPU_JOBS_FILE`, `TPU_JOBS_LEGACY_FILE`, `TPU_CHECK_CACHE_FILE`,
`TPU_JOB_NAME_PREFIX`, and for the local-queue router `TPU_LOCAL_QUEUE_FILE`
(lyy's own queue) and `TPU_BUILD_WORKER_SESSION` (lyy's own `npu-build-worker`
tmux session, so a build-worker start/stop never collides with sqa's). Scope
every new per-operator resource here too: the queue file and the worker session
each shipped a collision until added, since an unscoped shared path or tmux name
means one operator's action hits the other's. Unset, the tool behaves as before
they existed. To verify a change here, diff the full `tpu check` output against
the pre-change script rather than eyeballing it.

The `npu` function sets them with `local -x`, never a bare `export`: a plain
export would leak into every later `tpu` in that shell and silently file the
owner's next job into the collaborator's registry.

A second registry needs a second daemon. The board renders from
`$TPU_CHECK_CACHE_FILE`; with nobody writing it, every job there reads
`SUBMITTED` forever while looking alive (`run-npu-daemon.sh`).

This is bookkeeping, not a boundary: same Unix user, same XManager account, same
quota. The `lyy-` experiment-title prefix exists because the XM UI is the one
view that cannot see the registry split.

Splitting the registry splits what each operator writes, not what they see or
can touch. Every consumer reaching past the registry needs scoping by hand, and
each of these shipped broken because the split looked like it had covered them:

- **The board unions two sources with different scopes.** `check` merges the
  per-operator registry with the `infra_check` cache, which is per-account: it
  lists every experiment the Unix user owns, whoever launched it. Unioned blind,
  the collaborator's board showed all 33 of the owner's runs. A scoped board
  keeps a job only if the operator's own registry records it or its name carries
  their prefix. The second clause covers a job launched outside the registry,
  and the prefix survives the cache's name truncation because it sits at the
  front.
- `cancel` is destructive and was unguarded. It passed any XID straight to
  `xmanager stop`, so one mistyped digit stopped the other operator's job. A
  scoped operator may cancel exactly what their own board shows, and a mixed
  batch is refused whole rather than half-executed.
- Auto-recovery managed the other operator's process. The quota/money cache is
  legitimately shared, but the daemon writing it belongs to the account owner. A
  stale cache plus one `npu quota` ran `tmux kill-session -t tpu-daemon` and
  killed it, causing the frozen board that recovery exists to repair.
- A consumer that reaches past the registry may still read the owner's, and
  some still do. `infra_check` reads a hardcoded `~/.tpu_jobs.json`, not
  `$TPU_JOBS_FILE`, so the guest daemon's infra pass polls the owner's registry.
  That is harmless only because both boards then reflect the owner's jobs; a
  real fix scopes the path. Treat any unscoped path here as a latent instance of
  this bug.

The owner stays unscoped on purpose. Whoever pays for the quota needs to see and
stop everything running on it; the partial view belongs to the guest.

`scripts/test_operator_scope.sh` pins all of it, with `xmanager` and `tmux`
shadowed by shell functions so it touches nothing real.

## The Cache Daemon

Status commands read a cache file, so they are instant; the background daemon
refreshing it carries all the latency, and the commands warn when the cache is
stale. **A full daemon round must therefore finish well inside the staleness
threshold.**

- Split the round into a fast lane and a slow lane, since commands warn per
  cache and a slow checker must not hold a fast one past the alarm. The round
  waits for cheap money and quota (~40s); infra_check scales with registry size
  (one serial RPC per tracked job), takes minutes, and runs detached behind a
  `kill -0` guard that skips a second pass while one is in flight. One `wait`
  barrier over all three once aged money.txt past its threshold during a long
  infra pass, with money's own data ready for seconds.
- Every checker cold-starts once; keep them out of a serial chain. Each pays a
  substantial interpreter cold start while its RPCs cost under a second, so
  chaining them pays that tax repeatedly. They share no state and write to
  disjoint outputs, so run them in parallel.
- Rebuild all checker binaries in one build invocation. Building a single
  target can publish an output namespace holding only that target, and the
  daemon then reports failures that look like data or auth bugs.
- Never `readlink -f` the build output symlink. Its two hops have opposite
  lifetimes: the first is stable and worth pinning against a concurrent build,
  the second is republished per build with only that build's targets behind it.
  Collapsing both freezes the daemon in one build's namespace no later rebuild
  can reach, so binaries sit correctly built in `blaze-bin` while the daemon
  insists they do not exist. Pin one hop, re-resolve the rest at each use, and
  fall back to the live path.
- When the staleness alarm fires, check the round duration the daemon logs
  before believing its "credentials expired" hint, which is a guess and usually
  wrong.
- A checker the daemon cannot find is repaired by the daemon, rate-limited,
  rebuilding all of them together. A hint printed into a detached tmux pane is
  not a fix, and the staleness auto-recovery restarts the session, never the
  problem.
- **Serialize every self-heal rebuild behind one shared `flock`.** A checker
  binary is objfs-GC'd after a while, and three paths rebuild it: the daemon's
  self-heal, a wrapper's on-demand rebuild, a periodic keep-warm. Fired together
  they race on the single blaze output_base and republish each other's
  namespace, so none publishes a clean binary and the checker stays frozen while
  `blaze build` appears to run non-stop. A non-blocking `flock` shared by all
  rebuild paths collapses the storm to one build; the losers skip, never stack.
  (This is the checker-rebuild instance of the output_base race that §The
  Local-Queue Smart Router's serial build-worker cures for job builds.)
- A keep-warm rebuilds only when the binary is missing. A built binary survives
  a long time, so an unconditional periodic `blaze build` is overhead, and not
  free: blaze's `--shutdown_on_low_sys_mem` evicts the idle server under memory
  pressure, so each "up-to-date check" cold-respawns a multi-GB JVM heap that
  deepens the dip that evicted it. Steady state is a cheap liveness exec (the
  binary's own `--help`); pay for a real build only on a missing binary, plus a
  rare low-frequency refresh. If the build mtime never moves across many
  keep-warm cycles, every "rebuild" was wasted work.
- The rebuild is the plain, proven `blaze build`; exotic flags each broke it. A
  `startup`-class option (e.g. `--noenable_dbip_auto_opt_in`, declared `startup`
  in `tools/blaze.blazerc`) placed after the subcommand is rejected at parse
  time (`Unrecognized option`); it must precede `build` or not appear.
  `--spawn_strategy=local` breaks a non-sandboxed genrule (unuran) in the graph.
  Copy the command the daemon already runs; do not decorate it.
- The command re-renders the cache; it does not print it. `tpu check` parses the
  daemon's cached table and rebuilds its own, so a column the daemon computes
  and writes stays invisible if the command's parser drops it. The running
  table's per-cell placement (`REGION`, e.g. `europe (lpp)`) lived in the cache
  for a long time while the command showed only `XID|STATUS|NAME|…|WHY`; the fix
  was in the parser, not the daemon. Before concluding "the tool does not collect
  X", run the daemon binary directly and diff its columns against the command's.
  Section layouts differ (running carries an extra `REGION|DETAILS` pair the
  6-column pending/done rows do not), so a parser must gate per-section on the
  column count rather than a fixed index.
- `AGE` is derived in the wrapper, not the daemon. The active/pending tables
  show `AGE` = wall-clock since submission, parsed from the timestamp
  `tpu_wrapper` already baked into each entry's `logdir`
  (`eqr_run_YYMMDD_HHMMSS`) or `bucket_cp_path` (`..._YYYYMMDD_HHMMSS_...`) in
  `~/.tpu_jobs.json` (`_age_str`). It is submit-age (queue + run), not pure Borg
  run-uptime: the daemon cache carries no work-unit start time, so "how long has
  it actually been training" still comes from `STEP × sec/step`, not `AGE`. On
  the pending board `AGE` doubles as "how long stuck in the auction". Add a
  wrapper column by editing the per-section `*_headers`/`*_caps` lists and the
  matching `*_rows.append(...)`; no daemon rebuild needed, effect is immediate.

## Job Bookkeeping

The live registry is the file `tpu check` renders from. An older predecessor
file is no longer written and survives only as a resume fallback.

- **A terminal row is polling load, not just clutter.** infra_check issues one
  serial RPC per tracked job, so hundreds of never-migrating rows
  (`TERMINAL_RECONCILED`, `CANCELLED`) inflate the round for jobs whose state
  can never change again. The daemon filters terminal status out of its poll
  set, and archiving them keeps the live registry small. Do both, since a fresh
  registry accretes them continuously.
- Clear archives rather than deletes, moving entries to a legacy file. Keep it:
  an entry is the only mapping from an experiment id back to its checkpoint
  bucket, staging directory, and launch log once the job and work unit are gone.
- Cancel is not clear. Canceling stops the experiment and pins the registry
  entry so the daemon's auto-retry can never resubmit an explicitly killed job;
  the entry stays on the board until archived.
- Recovering a past run's config is a shell helper. It reads the staging
  directory from the registry (falling back to the legacy file, so archived ids
  still resolve) and copies the exact config out of that immutable snapshot,
  learning which file by grepping the launch log, since a snapshot holds the
  whole config directory. That answers "which config produced this run", and is
  why deleting a finished experiment's config from the checkout is safe.

## Error Classification And Auto-Retry

The daemon parses launch logs and classifies failures into defragmentation
preemption, resource exhaustion, allocator rejection (the fallback for a failure
with no stated reason), and unknown.

Auto-retry is narrow on purpose: only a guaranteed-tier job rejected by the
allocator is retried, a few times, minutes apart. That is the client
resubmitting a new experiment, a different mechanism from the in-job restart
budget in `../jobs.md`, and it does not cover preempted jobs.

**A preempted job is dead, not pending** (`../jobs.md` owns why: no restart
budget means the torn-down gang counts as a task failure). Rendering any work
unit whose message merely contained "preempt" as pending made dead experiments
look like they were queuing for hours. Terminal state must win over a substring
match, while a genuinely queued job preempted earlier is labeled as such. The
daemon runs compiled binaries, so a source edit here does nothing until you
rebuild.

## Preflight Internals

Verdict layers, cheapest first: an in-process topology whitelist plus
per-allocation minimum-slice rules; one availability RPC asking whether any cell
in this allocation and tier has enough obtainable chips; and a headroom
heuristic warning when remaining quota is thin. On dynamic pools that last
warning is near-permanent and low-signal.

The router ranks surviving candidates by cap-blocked status (a blocked
combination is kept and explained, not silently dropped), verdict, group
preference, headroom, cost, and accelerator preference. **Group preference
(`_GROUP_PREF`) puts g3/g5 ahead of g9** at PROD: g3/g5 are small dynamic pools
with their own credit balance, exempt from the G9 income/10 budget cap, so
spending them first preserves the regulated G9 budget. It sits above the
economics (headroom/cost) but below blocked+verdict, so it never promotes a
non-runnable or lower-confidence placement to save budget, and it is neutral at
BATCH (one free pool). Headroom differs by tier on purpose: the guaranteed tier
uses remaining quota, the batch tier obtainable chips, because the batch pass
never consults a floor. A `--metros` allow-list is a hard data-locality filter
applied before ranking: only cells in the named metro(s) survive, and a combo
with no in-metro cell drops out entirely, so `--power --metros` fails closed
rather than roaming to a no-data cell. Market data comes from a cache the money
checker writes each daemon round, keeping the router offline and fast. When that
cache is missing or stale it says so loudly and falls back to price-blind
ranking rather than failing.

Per-allocation minimum-slice rules are pool policy, not physical law. A slice
below the minimum is a valid hardware topology, disallowed by the admission
config and rejected instantly. The batch tier typically allows down to the
architecture's own minimum. These rules live in a table in the preflight code;
update it when an allocation behaves differently.

## Metrics Tables

Tables expire after a long window measured from last access, renewing on every
read or write. Pin one explicitly if it must outlive that.

**The table CLI does not work from this workstation.** A restricted credential
blocks the service and every local binary hits the same wall. This is a
workstation limitation only, and a job writes fine; use the browser URLs in
`../research/result_logging.md`.

## The Local-Queue Smart Router

Two things share this core: the default smart cell pick every `tpu queue` now
does (`pick_cell`), and the advanced local queue that drains unlimited enqueues
with auto-reroute (`route_check` / `queue_cli`). User-facing workflow is
`../jobs.md` §Choosing Where To Run (the default) and §The Local Queue
(advanced). Neither replaces the one-shot `tpu queue`; the picker only pins a
`--cell` onto it. Modules in the google3 half, each a `pytype_strict_library`
with its own `pytype_strict_contrib_test`:

| Module | Role |
|---|---|
| `route_lib.py` | Pure scheduling core: queue schema (`QueueEntry`), placement, priority + seeded-random fairness, cell ranking by placeable slices, effective-price type selection (raw price discounted by a pool-size bonus), topology lock. No I/O, no RPC, unit-tested in full. |
| `avail_provider.py` | Wraps `GetCellAvailability` (the same RPC as `slice_probe`) plus the money `market.json` cache into `(avail_by_cell, arch_price, arch_pool)`. Free chips (`max_available_chips`) decide; `obtainable_capacity` is never read for a decision, because it lies. |
| `pick_cell.py` | **The default-path picker.** One RPC for the requested type, ranks with `best_cell_for_shape`, prints the single best cell (or nothing). `tpu queue` pins `--cell=<that>` unless the user pinned a cell, used `--power`, passed a comma type, or set `TPU_NO_SMART_CELL=1`. Accepts `--metros` (the wrapper forwards `tpu queue --metro/--metros`) so a data-locality-locked run stays in its storage metro while still dodging the oversold cells inside it. Fail-safe by contract: any failure prints nothing and the wrapper lets the allocator choose. |
| `preflight/router.py` + `router_cli.py` | The `--power` path (`tpu route`, and `tpu queue --power`). Expands a power class to (arch, chips) options, runs preflight per (group, cell), and ranks (see the ranking section above). Now accepts `--metros`, a hard data-locality filter over `cap.cells_ok`, so `--power` and metro co-locality compose (they did not before 2026-08). Cell→metro resolution is the shared `metro_util` leaf, identical to the smart-cell path. `rank()` also applies `_GROUP_PREF` (g3/g5 before g9). |
| `route_check.py` | The tick and the serial build-worker. `--reroute` cancels jobs stuck PENDING past the deadline and re-queues. `--worker` runs the serial build loop (below). Binary and library share the source; the binary target just re-exports it. |
| `queue_cli.py` | `tpu enqueue` / `queue-status` / `dequeue`. Reuses route_check's queue persistence and a dry-run planning tick for the live status view. |

Side effects sit behind seams so the whole thing unit-tests offline. The
submitter (`tpu queue`/`tpu cancel` shell-out), the availability provider, and
the XManager status probe are all injected; the 90-plus tests use fakes and
never touch a real RPC or shell. Keep it that way: a test needing the network
will not run in the daemon's build.

**A cell can host two accelerator generations at once** (`je` carries both a
v6e and a v7 pod; `nk`/`nl` both v6e and v6p). Availability is therefore keyed
per `(cell, arch)` as `cell|arch`, not by bare cell name, or the second
generation silently overwrites the first and the router never sees it. Anything
that draws down a cell's free chips within a tick must match by content
(cell and arch), not by dict key.

A topology-locked job must anchor its mesh before the first placement. Once
placed, `locked_geometry` is frozen and only same-mesh shapes are eligible
(`v6p-32`↔`v7-32`, both `2x4x4`; never `v6e-32`, `4_8`). Before the first
placement nothing is pinned, so it anchors to the mesh named by the job's own
`--power` spec: a locked `v6p-32` never first-lands on a v6e-64 (`8_8`) that
merely fell inside the power tolerance window. A bare-int power names no arch,
so a locked job with one is unplaceable by design; it would be guessing a mesh
for a sharded checkpoint.

The re-route sweep never cancels on missing data. It only cancels a job the
XManager probe confirms is still PENDING. UNKNOWN (probe failed, no work units)
is a no-op, and a job that has since started RUNNING is promoted, not killed. The
clock rule (submitted, older than the deadline) is `route_lib.needs_reroute`; the
live check and the cancel/cool-down side effects are in `route_check.run_reroute`.

**The serial build-worker (`--worker`) is the cure for concurrent-build
failures.** Concurrent `tpu queue` builds on this workstation fail three ways:
(1) two builds sharing a checkout race on the blaze output_base → `found[]`
zombie work units (a same-checkout copy dir does not isolate it, because
output_base is per checkout root); (2) a burst of concurrent stage-writes drains
the CitC CreateSnapshot token bucket → truncated stagedir, `.par` crash
(per-workspace; a fresh workspace drains just as fast under a pile-on);
(3) stacked build memory peaks (survivable on 94G). Never building two at once
cures all three. The invariant is the BUILDING JobState held in the durable
queue file: `claim_next_build` does reclaim-stale plus claim-next as one
`flock`'d read-modify-write on a sidecar lockfile, so at most one entry is
BUILDING even across separate worker processes. `run_worker_once` claims one,
plans a cell, runs the one build, and records SUBMITTED, or requeues on no-XID
(the `found[]` guard, so a zombie is retried not left dangling). A crashed
worker's stale BUILDING claim is reclaimed after `--build_stale_s`. An
injectable stage-health probe brakes when srcfs failures spike
(`--srcfs_fail_brake`, mode-2 guard). `tpu build-worker start|stop|status` runs
it in a self-restarting tmux session (`start` bakes STAGE_WS_ROOT in, `stop`
kills the child, see above); the queue file is operator-scoped so `npu` gets its
own worker.

HELD parks a job the worker can never build, so it cannot churn: an unattended
worker that requeued a permanently-bad job would spin and starve the queue.
`JobState.HELD` (skipped by `next_queued`) is the park. `run_worker_once` moves
a job there when its `workdir` is set-but-nonexistent (immediate, since wrong
source would be packaged) or it has failed to yield an XID
`--max_build_attempts` times (default 3, the empty-workdir/`found[]`-repeat
case). This neutralizes a stale/duplicate enqueue (entries whose runs are
already on Borg) or a batch enqueued from the wrong dir: they sit HELD, not
double-firing. `route_lib.hold_entry`/`requeue_held` are the transitions; a
human runs `tpu requeue [id...]` after fixing the cause.

**Staging workspace: `export STAGE_WS_ROOT=<healthy google3 root>` before
`build-worker start`.** `tpu queue` stages into `${STAGE_WS_ROOT}/experimental/
qiaos/eqr_jax_final_stages/` (default the EqR-jax checkout); a data-locked or
token-drained workspace forces a different one. Two subtleties the worker path
handles: (1) `tmux new-session` attaches to the tmux server's stale env, so a
bare `export` does not reach the session -- `start` bakes STAGE_WS_ROOT into the
worker command inline, so `export STAGE_WS_ROOT=...; tpu build-worker start`
works (it prints the pinned root, or warns when unset). (2) `stop` kills the
worker child too, not just the tmux `while` shell, since an orphaned worker
would keep holding the BUILDING slot. STAGE_WS_ROOT then rides the env through
`submit()` (subprocess with no `env=`, so it inherits) into `tpu queue`.

One stage-write at a time per workspace is the lock that makes "enqueue jobs
however you like" safe. The build-worker's BUILDING flock serializes only its
own queue, not a bare or `tpu_queue_guarded` direct submit running at the same
time. Both rsync into the same workspace, whose CitC CreateSnapshot token bucket
is per-(user,workspace), so a concurrent stage-write burst drains it and
truncates stagedirs. The fix is a lock inside `tpu queue` around the stage-write
(mkdir + rsync + config copy), keyed by `STAGE_WS_ROOT`. Every submit path
funnels through `tpu queue`, so one lock there serializes staging across bare,
guarded, and worker alike. It is a bash `flock` on fd 200 over
`/tmp/tpu_stage.<ws>.lock`, released before the build/launch, since
different-checkout builds do not collide (only the token bucket was shared) and
serializing builds too would negate parallel checkouts. `-w 900` degrades to
unlocked rather than blocking forever, and `flock` auto-releases on process
death, so a killed `tpu queue` never wedges it. The exception is a holder wedged
in FUSE-D (`request_wait_answer`): it cannot die on SIGKILL, so killing it does
not release its `flock`, and only an srcfs restart's EIO-bounce frees the lock
(`../engineering.md` §External Writes Are Transactions). This lets an operator
fire jobs through any mix of paths without hand-coordinating a stage storm; the
earlier hand-serialization advice (`monitoring.md`) is now the fallback, not the
mechanism.

The daemon's router lane is the 4th lane, off by default. `TPU_ROUTE_ENABLED`
unset is a complete no-op. Armed, it runs like the infra lane, detached with a
`kill -0` guard, so its serial RPCs never delay the money/quota fast lane, and
`TPU_ROUTE_DRYRUN=1` (the default when armed) plans and logs without submitting.
The queue file is operator-scoped like the registry: `npu` points
`TPU_LOCAL_QUEUE_FILE` at lyy's copy, so an enqueue under one operator never
lands in the other's queue.

Building it: `blaze build $CHECKER_SUBDIR:{route_check,queue_cli,pick_cell}`
(the binaries; the libraries and tests come along as deps). A py-strict binary
may not depend on another binary, so each binary's logic lives in a `*_lib`
library that the binary and any dependent (queue_cli on route_check_lib)
import. The wrapper's `_PICK_CELL_BIN` points at the built `pick_cell`; if it is
ever missing, `tpu queue` skips the smart pick (fail-safe), so rebuild it with
the others after any change.
