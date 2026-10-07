---
name: tpu-tooling
description: Use when changing, rebuilding, or debugging the `tpu` CLI or its parts, namely the checkers, cache daemon, job registry, preflight, the smart router, local queue and serial build-worker, and the budget enforcer.
---

# Changing, Rebuilding, And Debugging The `tpu` Tooling

This skill relies on knowledge pages for how the tool works:
[knowledge/infrastructure/tpu-cli.md](../../../knowledge/infrastructure/tpu-cli.md) owns the two halves, operator scoping, the cache daemon,
the log-tail sidecar, the job registry, error classification, preflight, and the
heavy-verb locks; [knowledge/infrastructure/router.md](../../../knowledge/infrastructure/router.md) owns the router modules, the serial
build-worker, and the preferred-pool skip; [knowledge/infrastructure/budget.md](../../../knowledge/infrastructure/budget.md) owns the two
income/10 gates. This skill owns the build commands, running the worker, queue
and enforcer, invoking `npu`, and the debugging drills. Native code and
`~/work/tpu_cmd/README.md` outrank this skill for flags and workflows; launching
and inspecting jobs is [knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md).

Chapter 1 is what to read before changing a part. Chapter 2 is building and
running it. Chapter 3 is debugging it.

---

## Chapter 1 — Before You Change A Part

### Read the invariant for the part you touch

Read the matching section before editing.

| You are changing | Read first |
|---|---|
| Any file the build compiles | [knowledge/infrastructure/tpu-cli.md §Every Source File Belongs In The Repo, Not Just A Checkout](../../../knowledge/infrastructure/tpu-cli.md#every-source-file-belongs-in-the-repo-not-just-a-checkout) |
| Anything per-operator: a registry, a queue file, a tmux session, cancel, the board | [knowledge/infrastructure/tpu-cli.md §One Tool, Two Operators](../../../knowledge/infrastructure/tpu-cli.md#one-tool-two-operators) |
| The cache daemon, a checker, or a rebuild path | [knowledge/infrastructure/tpu-cli.md §The Cache Daemon](../../../knowledge/infrastructure/tpu-cli.md#the-cache-daemon), [knowledge/infrastructure/tpu-cli.md §Cache Daemon Failure Modes](../../../knowledge/infrastructure/tpu-cli.md#cache-daemon-failure-modes), [knowledge/infrastructure/router.md §The Checker-Rebuild output_base Race](../../../knowledge/infrastructure/router.md#the-checker-rebuild-output_base-race) |
| Anything that writes the job registry | [knowledge/infrastructure/tpu-cli.md §Job Bookkeeping](../../../knowledge/infrastructure/tpu-cli.md#job-bookkeeping) |
| Failure labels, or anything that would resubmit a job | [knowledge/infrastructure/tpu-cli.md §Error Classification](../../../knowledge/infrastructure/tpu-cli.md#error-classification) |
| Preflight verdicts or ranking | [knowledge/infrastructure/tpu-cli.md §Preflight Internals](../../../knowledge/infrastructure/tpu-cli.md#preflight-internals) |
| The router core, the picker, the reroute sweep, or the build-worker | [knowledge/infrastructure/router.md §Chapter 1 — Principle](../../../knowledge/infrastructure/router.md#chapter-1--principle), [knowledge/infrastructure/router.md §The Re-route Sweep Never Cancels On Missing Data](../../../knowledge/infrastructure/router.md#the-re-route-sweep-never-cancels-on-missing-data), [knowledge/infrastructure/router.md §A Reroute Requeue Warm-Restarts From The Lineage Checkpoint](../../../knowledge/infrastructure/router.md#a-reroute-requeue-warm-restarts-from-the-lineage-checkpoint) |
| The g5/g3/g9 order of the dispatch worker | [knowledge/infrastructure/router.md §A Preferred Pool Is Skipped When It Cannot Hold The Job](../../../knowledge/infrastructure/router.md#a-preferred-pool-is-skipped-when-it-cannot-hold-the-job) |
| The heavy-verb shims or their locks | [knowledge/infrastructure/tpu-cli.md §Serializing Heavy Verbs: Separate Blaze And Hg Locks](../../../knowledge/infrastructure/tpu-cli.md#serializing-heavy-verbs-separate-blaze-and-hg-locks), [knowledge/infrastructure/tpu-cli.md §The Heavy-Verb Shim Must Not Swallow stderr](../../../knowledge/infrastructure/tpu-cli.md#the-heavy-verb-shim-must-not-swallow-stderr) |
| Pricing in either budget gate | [knowledge/infrastructure/budget.md §The Two Gates Disagreeing Is A Pump](../../../knowledge/infrastructure/budget.md#the-two-gates-disagreeing-is-a-pump), [knowledge/infrastructure/budget.md §A Daemon Prices From The Table It Imported At Startup](../../../knowledge/infrastructure/budget.md#a-daemon-prices-from-the-table-it-imported-at-startup) |

---

## Chapter 2 — Building And Running

Before starting a worker by hand, read [harness/policy.md §Global Rules](../../policy.md#global-rules) (§Jobs)
and [knowledge/infrastructure/cluster-jobs.md §The two queues and the single serial builder](../../../knowledge/infrastructure/cluster-jobs.md#the-two-queues-and-the-single-serial-builder): on this
shared workstation the always-on dispatch-worker is the sole builder.

### Building And Rebuilding Checkers

**Rebuild all checker binaries in one `blaze build` invocation, with the plain
proven command.** Building a single target can publish an output namespace
holding only that target, and the daemon then reports failures that look like
data or auth bugs. Exotic flags each broke it: a `startup`-class option (e.g.
`--noenable_dbip_auto_opt_in`) placed after the subcommand is rejected at parse
time and must precede `build`; `--spawn_strategy=local` breaks a non-sandboxed
genrule in the graph. Copy the command the daemon already runs; do not decorate
it.

Self-asserting test scripts (they exit non-zero on failure instead of using the
test framework) must be declared as test targets. Declared as binaries they
never run, and the test command reports no tests found.

### Building The Router Binaries

```
blaze build $CHECKER_SUBDIR:{route_check,queue_cli,pick_cell}
```

The binaries; the libraries and tests come along as deps. A py-strict binary may
not depend on another binary, so each binary's logic lives in a `*_lib` library
that the binary and any dependent (queue_cli on route_check_lib) import. The
wrapper's `_PICK_CELL_BIN` points at the built `pick_cell`; if it is ever
missing, `tpu queue` skips the smart pick (fail-safe), so rebuild it with the
others after any change.

### Pointing The Staging Workspace

**`export STAGE_WS_ROOT=<healthy google3 root>` before `build-worker start`.**
`tpu queue` stages into `${STAGE_WS_ROOT}/experimental/qiaos/eqr_jax_final_stages/`
(default the EqR-jax checkout); a data-locked or token-drained workspace forces a
different one. Two subtleties the worker path handles:

- `tmux new-session` attaches to the tmux server's stale env, so a bare `export`
  does not reach the session — `start` bakes STAGE_WS_ROOT into the worker
  command inline, so `export STAGE_WS_ROOT=...; tpu build-worker start` works (it
  prints the pinned root, or warns when unset).
- `stop` kills the worker child too, not just the tmux `while` shell, since an
  orphaned worker would keep holding the BUILDING slot.

STAGE_WS_ROOT then rides the env through `submit()` (a subprocess with no `env=`,
so it inherits) into `tpu queue`.

### Running The Worker And The Queue

`tpu build-worker start|stop|status` runs the loop in a self-restarting tmux
session; the queue file is operator-scoped, so `npu` gets its own worker. `tpu
enqueue` / `queue-status` / `dequeue` manage the queue; `tpu requeue [id...]`
un-HELDs a job after you fix its cause.

**The daemon's router lane is a 4th lane, off by default.** `TPU_ROUTE_ENABLED`
unset is a complete no-op. Armed, it runs like the infra lane — detached, with a
`kill -0` guard so its serial RPCs never delay the money/quota fast lane — and
`TPU_ROUTE_DRYRUN=1` (the default when armed) plans and logs without submitting.
The queue file is operator-scoped like the registry: `npu` points
`TPU_LOCAL_QUEUE_FILE` at lyy's copy, so an enqueue under one operator never
lands in the other's queue.

### Invoking npu

**The `npu` function sets its env vars with `local -x`, never a bare `export`.**
A plain export would leak into every later `tpu` in that shell and silently file
the owner's next job into the collaborator's registry. To verify a change to the
scoping, diff the full `tpu check` output against the pre-change script rather
than eyeballing it. A second registry needs a second daemon
(`run-npu-daemon.sh`): the board renders from `$TPU_CHECK_CACHE_FILE`, so with
nobody writing it every job there reads `SUBMITTED` forever while looking alive.

### Running The Enforcer

Inspect a single pass without touching anything:

```
budget_check_dir=~/work/wiki_agents/tools
python3 $budget_check_dir/budget_enforcer.py --once           # dry-run, prints the plan
```

Arm it only deliberately, and always point `--jobs-file` / `--local-queue-file`
at the right operator (the defaults are the `tpu` agent's; `npu`/lyy has its own
registry and queue). The watchdog already runs the armed daemon, so a hand-run
armed instance is for recovery, not routine.

---

## Chapter 3 — Debugging

### A Frozen Board Means The Daemon Lost Its cwd

**A long-lived daemon whose cwd is on the CitC FUSE mount dies silently when
that mount is recreated.** Its python children fail at `os.getcwd()` with
`OSError: [Errno 107] Transport endpoint is not connected`, every checker
outputs nothing, and the correct "only overwrite the cache when the new output
is non-empty" guard then keeps the last good board forever.

The symptom is plausibility, not an error: `tpu check` renders every job as
`SUBMITTED` (the cache-miss fallback), so the board looks like a queue that has
not started rather than one that stopped updating, while the process stays
alive, the loop turns, and the log scrolls. Diagnose by timestamp, not by
liveness: `ls -la ~/.tpu_check_cache.txt` against `date`; a `.tmp` file newer
than the cache and zero bytes is the signature, and `tmux capture-pane -t
tpu-daemon -p | tail` shows the real error. Restart with an explicit start
directory outside the mount, or the new process inherits the dead handle:
`tmux respawn-pane -k -c "$HOME" -t tpu-daemon '<the while-true loop>'`.

A shim that hides blaze's stderr makes a stalled build look like a frozen
terminal; test each gate as [knowledge/infrastructure/tpu-cli.md §The Heavy-Verb Shim Must Not Swallow stderr](../../../knowledge/infrastructure/tpu-cli.md#the-heavy-verb-shim-must-not-swallow-stderr) describes.
