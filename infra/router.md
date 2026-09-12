# The Smart Router And Serial Build-Worker

The cell picker, the local queue with auto-reroute, and the serial build-worker
that makes "enqueue jobs however you like" safe on this shared workstation.
Sibling of `tpu_cli.md` (the rest of the tool); the user-facing workflow is
`../jobs/submit.md` §The smart router picks the cell and the group and §The two
queues and the serial build-worker. Native code outranks this page; the modules
are `pytype_strict_library` targets in the google3 checker half.

## Principle

**One scheduling core serves two entry points: the default smart cell-pick that
every `tpu queue` now does, and the advanced local queue that drains unlimited
enqueues with auto-reroute.** Neither replaces the one-shot `tpu queue`; the
picker only pins a `--cell` onto it.

| Module | Role |
|---|---|
| `route_lib.py` | Pure scheduling core: queue schema (`QueueEntry`), placement, priority + seeded-random fairness, cell ranking by placeable slices, effective-price type selection (raw price discounted by a pool-size bonus), topology lock. No I/O, no RPC, unit-tested in full. |
| `avail_provider.py` | Wraps `GetCellAvailability` (the same RPC as `slice_probe`) plus the money `market.json` cache into `(avail_by_cell, arch_price, arch_pool)`. Free chips (`max_available_chips`) decide; `obtainable_capacity` is never read for a decision, because it lies. |
| `pick_cell.py` | The default-path picker. One RPC for the requested type, ranks with `best_cell_for_shape`, prints the single best cell (or nothing). `tpu queue` pins `--cell=<that>` unless the user pinned a cell, used `--power`, passed a comma type, or set `TPU_NO_SMART_CELL=1`. Accepts `--metros`. Fail-safe by contract: any failure prints nothing and the wrapper lets the allocator choose. |
| `preflight/router.py` + `router_cli.py` | The `--power` path (`tpu route`, `tpu queue --power`). Expands a power class to (arch, chips) options, runs preflight per (group, cell), and ranks. Accepts `--metros`, a hard data-locality filter over `cap.cells_ok`, so `--power` and metro co-locality compose. Cell→metro resolution is the shared `metro_util` leaf. `rank()` applies `_GROUP_PREF` (g3/g5 before g9). |
| `route_check.py` | The tick and the serial build-worker. `--reroute` cancels jobs stuck PENDING past the deadline and re-queues. `--worker` runs the serial build loop. Binary and library share the source; the binary target re-exports it. |
| `queue_cli.py` | `tpu enqueue` / `queue-status` / `dequeue`. Reuses route_check's queue persistence and a dry-run planning tick for the live status view. |

**Everything unit-tests offline because the side effects sit behind seams.** The
submitter (`tpu queue`/`tpu cancel` shell-out), the availability provider, and
the XManager status probe are all injected; the 90-plus tests use fakes and
never touch a real RPC or shell. Keep it that way: a test needing the network
will not run in the daemon's build.

**Availability is keyed per `(cell, arch)`, not by bare cell name, because a
cell can host two accelerator generations at once** (`je` carries both a v6e and
a v7 pod; `nk`/`nl` both v6e and v6p). Key by `cell|arch`, or the second
generation silently overwrites the first and the router never sees it. Anything
that draws down a cell's free chips within a tick must match by content (cell
and arch), not by dict key.

**A topology-locked job anchors its mesh before the first placement, then only
same-mesh shapes are eligible.** Once placed, `locked_geometry` is frozen
(`v6p-32`↔`v7-32`, both `2x4x4`; never `v6e-32`, `4_8`). Before the first
placement nothing is pinned, so it anchors to the mesh named by the job's own
`--power` spec: a locked `v6p-32` never first-lands on a v6e-64 (`8_8`) that
merely fell inside the power tolerance window. A bare-int power names no arch, so
a locked job with one is unplaceable by design; it would be guessing a mesh for
a sharded checkpoint.

### The Serial Build-Worker Is The Cure For Concurrent-Build Failures

**Never building two jobs at once is what makes concurrent enqueues safe; the
serial build-worker (`--worker`) enforces it.** Concurrent `tpu queue` builds on
this workstation fail three ways, and serializing cures all three:

1. two builds sharing a checkout race on the blaze output_base → `found[]`
   zombie work units (a same-checkout copy dir does not isolate it, because
   output_base is per checkout root);
2. a burst of concurrent stage-writes drains the CitC CreateSnapshot token
   bucket → truncated stagedir, `.par` crash (per-workspace; a fresh workspace
   drains just as fast under a pile-on);
3. stacked build memory peaks (survivable on 94 G, but real).

**The invariant is the BUILDING JobState in the durable queue file:
`claim_next_build` does reclaim-stale plus claim-next as one `flock`'d
read-modify-write on a sidecar lockfile, so at most one entry is BUILDING even
across separate worker processes.** `run_worker_once` claims one, plans a cell,
runs the one build, and records SUBMITTED, or requeues on no-XID (the `found[]`
guard, so a zombie is retried not left dangling). A crashed worker's stale
BUILDING claim is reclaimed after `--build_stale_s`.

**HELD parks a job the worker can never build, so it cannot churn.** An
unattended worker that requeued a permanently-bad job would spin and starve the
queue. `run_worker_once` moves a job to `JobState.HELD` (skipped by
`next_queued`) when its `workdir` is set-but-nonexistent (immediate — wrong
source would be packaged) or it has failed to yield an XID `--max_build_attempts`
times (default 3, the empty-workdir/`found[]`-repeat case). This neutralizes a
stale/duplicate enqueue or a batch enqueued from the wrong dir: they sit HELD,
not double-firing. A human runs `tpu requeue [id...]` after fixing the cause.

**One stage-write at a time per workspace is the lock that makes unlimited
enqueues safe.** The build-worker's BUILDING flock serializes only its own
queue, not a bare or guarded direct submit running at the same time. Both rsync
into the same workspace, whose CreateSnapshot token bucket is per-(user,
workspace), so a concurrent stage-write burst drains it and truncates stagedirs.
The fix is a `flock` inside `tpu queue` around the stage-write (mkdir + rsync +
config copy), keyed by `STAGE_WS_ROOT`; every submit path funnels through `tpu
queue`, so one lock there serializes staging across bare, guarded, and worker
alike. It is released before the build/launch, since different-checkout builds do
not collide (only the token bucket was shared), and `-w 900` degrades to
unlocked rather than blocking forever.

## Usage

### Building It

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

## Errors

### The Re-route Sweep Never Cancels On Missing Data

**A reroute only cancels a job the XManager probe confirms is still PENDING.**
UNKNOWN (probe failed, no work units) is a no-op, and a job that has since
started RUNNING is promoted, not killed. The clock rule (submitted, older than
the deadline) is `route_lib.needs_reroute`; the live check and the
cancel/cool-down side effects are in `route_check.run_reroute`. Do not let a
sweep cancel on an absence — an absence is the weakest possible reading
(`../AGENTS.md` §Evidence Order).

### A flock Wedged In FUSE-D Is The One Case That Does Not Self-Heal

**The CLI's own locks degrade after their `-w` window, so a wedged holder costs
each waiter at most ~30 min — except a holder wedged in FUSE-D
(`request_wait_answer`), which cannot die on SIGKILL and so never releases its
`flock`.** Only an srcfs restart's EIO-bounce frees it (`../engineering.md`
§External writes are transactions), and that restart is fleet control-plane and
operator-owned. Before reaching for it, note that the `-w` degradation already
caps normal waits. Detect a convoy by the held lock plus its waiters, not by an
aggregate D-count, which misses a one-orphan convoy.

### The Checker-Rebuild output_base Race

The serial build-worker cures the output_base race for job builds; the same race
in the checker-rebuild path is cured by a shared `flock` (`tpu_cli.md` §The Cache
Daemon). Both are the same root cause — concurrent blaze invocations sharing one
output_base republish each other's namespace — so if you add a third rebuild
path, serialize it behind the existing lock rather than adding a fourth racer.
