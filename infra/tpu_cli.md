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

- **Run the checkers concurrently.** Each pays a substantial interpreter cold
  start while its RPCs cost under a second, so serial runs paid that tax
  repeatedly and pushed a round past the threshold. They are independent and
  write to disjoint outputs.
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

## Job Bookkeeping

The live registry is the file `tpu check` renders from; an older predecessor
file is no longer written and survives only as a fallback for resume.

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
