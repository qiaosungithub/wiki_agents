# The `tpu` Tooling Itself

Read this only when changing, rebuilding, or debugging the `tpu` CLI and its
daemon. Using it to launch and inspect jobs is `jobs.md`. Native code and
`~/work/tpu_cmd/README.md` outrank this file for flags and workflows.

## Two Halves, Two Repositories, And Why

| Half | Location | Contents |
|---|---|---|
| Shell + launcher | `~/work/tpu_cmd/` | wrapper script, launcher, README |
| Built checkers | a google3 CitC path under `experimental/users/<user>/tpu_utils/` | money/quota/infra checkers, shared utilities, preflight (topology, capacity, market, router), probes |

The split is forced by the build system, not by preference: the checker half
imports google3 packages, depends on internal build targets, and the daemon runs
its compiled binaries on a loop.

**The google3 half cannot be symlinked out.** All three variants fail — an
absolute directory symlink is rejected outright, a relative one escapes the
source root, and per-file symlinks fail at action execution. Only the reverse
works: real files in google3, a symlink in `~/work` pointing at them, for
navigation only.

Both halves are versioned. The google3 half uses a separate git directory so the
worktree stays in place and the build is unaffected — only a tiny pointer file
sits in the source tree. Do not try to unify them with one repo plus a symlink:
git records a symlink as the link itself, so committing it would back up none of
the files behind it.

**A source-control checkout is not a backup.** The checker half was originally
unknown to the depot entirely; until its change submits, the git repo is the
only recovery path.

Self-asserting test scripts (ones that exit non-zero on failure rather than
using the test framework) must be declared as test targets. Declared as
binaries they silently never run and the test command cheerfully reports that no
tests were found.

## The Cache Daemon

The status commands read a cache file, so they are instant; all latency lives in
the background daemon that refreshes it. The commands warn when that cache is
stale, so **a full daemon round must finish well inside the staleness
threshold.**

- Each checker binary pays a substantial interpreter cold start while its actual
  RPCs cost under a second. Running them serially paid that tax repeatedly and
  pushed a round past the threshold. They are independent and write to disjoint
  outputs, so they run **concurrently**.
- When the staleness alarm fires, **check the round duration the daemon logs
  before believing its "credentials expired" hint** — that message is a guess and
  is usually wrong.
- **Rebuild all checker binaries in one build invocation.** Building a single
  target evicts the others from the output directory, and the daemon then
  reports failures that look like data or auth bugs.

## Job Bookkeeping

The live registry is the file `tpu check` renders from; an older predecessor
file is no longer written and survives only as a fallback for resume.

**Clear archives rather than deletes**, moving entries to a legacy file. Keep
it: an entry is the only mapping from an experiment id back to its checkpoint
bucket, staging directory, and launch log once the job and work unit are gone.

**Cancel is not clear.** Cancelling stops the experiment and pins the registry
entry so the daemon's auto-retry can never resubmit an explicitly killed job;
the entry stays on the board until archived.

**Recovering a past run's config** is a shell helper that reads the staging
directory from the registry (falling back to the legacy file, so archived ids
still resolve) and copies the exact config out of that immutable snapshot. It
learns *which* file to copy by grepping the launch log, because a snapshot
contains the whole config directory. This is why deleting a finished
experiment's config from the checkout is safe, and it is the answer to "which
config produced this run".

## Error Classification And Auto-Retry

The daemon parses launch logs and classifies failures — defragmentation
preemption, resource exhaustion, allocator rejection (the fallback for a failure
with no stated reason), and unknown.

**Auto-retry is narrow on purpose**: only a guaranteed-tier job rejected by the
allocator is retried, a few times, minutes apart. That is the client resubmitting
a *new experiment*, which is a completely different mechanism from the in-job
restart budget in `jobs.md`. **Preempted jobs are not covered by it.**

**A preempted job is dead, not pending.** With no restart budget the torn-down
gang counts as a task failure and the job is never re-queued. The status tool
used to render any work unit whose message merely contained "preempt" as
pending, which made dead experiments look like they were queuing for hours.
Terminal state must win over a substring match; a genuinely queued job that was
preempted earlier is labelled as such. When changing this logic, remember the
daemon runs compiled binaries — a source edit does nothing until you rebuild.

## Preflight Internals

Verdict layers, from cheapest: an in-process topology whitelist plus
per-allocation minimum-slice rules; one availability RPC asking whether any cell
in this allocation and tier has enough obtainable chips; and a headroom
heuristic that warns when remaining quota is thin. On dynamic pools that last
warning is near-permanent and low-signal.

The router ranks surviving candidates by cap-blocked status (a blocked
combination is kept and explained rather than silently dropped), verdict,
headroom, cost, and accelerator preference. **Headroom differs by tier on
purpose**: the guaranteed tier uses remaining quota, the batch tier uses
obtainable chips, because the batch pass never consults a floor at all.

Market data comes from a cache written by the money checker each daemon round,
so the router stays offline and fast; when that cache is missing or stale it
says so loudly and falls back to price-blind ranking rather than failing.

Per-allocation minimum-slice rules are **pool policy, not physical law** — a
slice below the minimum is a perfectly valid hardware topology, just disallowed
by the admission config, and rejected instantly. The batch tier typically allows
down to the architecture's own minimum. These rules live in a table in the
preflight code; update it when you meet an allocation that behaves differently.

## Metrics Tables

Tables expire after a long window measured from **last access**, and renew on
every read or write. Pin one explicitly if it must outlive that.

The table CLI does not work from this workstation — a restricted credential
blocks the service, and every local binary hits the same wall. This is a
workstation limitation only; a job writes fine. Use the browser URLs in
`research/result_logging.md`.
