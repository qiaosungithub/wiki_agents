# XManager And Borg Jobs

Read this for queueing, inspecting, resuming, or debugging jobs on the Google
internal XManager/Borg stack. Read `data_locality.md` before choosing cells or
runtime storage, plus the target project's own guide.

## Submission Contract

- Agents submit through
  `source ~/work/tpu_cmd/tpu_wrapper.sh && tpu queue ...`. Never call
  `xm launch` or `xmanager launch` directly. Only the wrapper may do so
  internally.
- The shared `~/work/tpu_cmd/xm_launcher.py` owns common packaging, staging, and
  job registration. Project checkouts provide versioned configuration and a
  link or reference to the shared launcher; do not grow independent launcher
  implementations without an explicit design change.
- Put model, data, and training semantics in versioned config. Wrapper-level
  resource routing and explicit transient selectors such as `load_from` or
  `resume_xid` may remain CLI arguments.
- Confirm the source checkout, branch, dirty state, effective config, allocator,
  and target before launch. Use the project's real Research Hub attribution;
  never insert a placeholder merely to suppress an interactive prompt.
- A wrapper may create a unique CitC source snapshot before packaging. The
  resulting Bazel package is immutable: edits after packaging do not change a
  queued or running job.
- The wrapper records the XManager id and associated metadata for `tpu check`.
  Verify that registration after submission instead of assuming the launch
  transaction completed.

## Requirements And Runtime

- A job intended to consume guaranteed PROD quota must set
  `service_tier=xm.ServiceTier.PROD` in `xm.JobRequirements`. Do not substitute
  a legacy `xm_priority` field or silently accept BATCH/FREE.
- `xm.python_container` requires the selected pool to have a mapped GCP project.
  Use the allocator's supported packaging mode; native Borg allocators without
  that mapping require `xm_abc.Borg` with Bazel packaging.
- In JAX applications using `xm_jax.JaxFlags`, parse Abseil flags before
  distributed initialization. Call `jax.distributed.initialize()` inside
  `main(argv)`, never at module import time.

## Quota, Money & GQM Marketplace

### Underlying Allocation Logic: PROD vs BATCH
- **PROD (`ServiceTier.PROD` / HighlyAvailable / Borg priority 200)**:
  - **Not preemption-proof.** PROD is safe from *higher-priority* preemption,
    but it is still evicted by **equal-priority slice defragmentation**
    (`SLICE_DEFRAGMENTATION`). Treat "PROD cannot be preempted" as false; size
    the restart budget below for PROD too.
  - Strict hard quota limit (**Quota-based**). Uses guaranteed group allocations
    assigned by Org/Team. Cannot be expanded via money. Exhaustion causes
    immediate admission failure (Borg `RESOURCES_EXCEEDED` / gRPC
    `RESOURCE_EXHAUSTED`, or the XM status category `FLEX_CEILING_EXCEEDED` /
    `DEFICIT_IN_PARENT_POOLS`).
  - **Rejected, never queued.** Admission is a one-shot check: over quota means
    instant failure, not a wait for capacity to free up. Any "queueing" is
    client-side retry (the daemon's 5×5min loop), not a Borg feature. Contrast
    with BATCH, which re-bids every market cycle.
  - PROD still has a shadow price in `ResourcePrices` (visible in `tpu money`),
    reflecting how contested that (cell, accelerator) is; it is **not** used
    for admission.
- **BATCH (`ServiceTier.BATCH` / NonProd / Borg priority 100)**:
  - **Preemptible** — always, including in the free pool. Priority is exactly
    **100** (`third_party/py/xmanager/xm/resources.py`, `ServiceTier`), which is
    below the goodput-protection threshold of 200, so BATCH TPU work is the
    first thing sacrificed in a squeeze.
  - TPU gangs are scheduled all-or-nothing with **no queue position and no
    aging**. Waiting longer does not improve your odds; a job that has sat
    "pending" for a day is not making progress toward being scheduled.
  - Governed by GQM (Global Quotas Marketplace). Every ~1 minute a market
    cycle runs: global demand and supply per `ResourceType` are aggregated
    across all MDBs and a **uniform equilibrium clearing price** is found by
    binary search. Cell-specific prices are then broadcast (they are the
    global equilibrium scaled by each cell's RPP).
  - Admission is **not** a simple `bidding_power ≥ price` check. Each MDB's
    demand-at-price is a step function, and the auction is combinatorial.
    `bp ≥ price * chips` is a **necessary-but-not-sufficient sanity signal**.
  - **Market Clearing Price**:
    - **0.00 Credits/hr (Free Pool)**: supply ≥ demand this cycle. Everyone
      clears at zero cost. NOTE: preemption still happens if a higher-priority
      job needs the machine.
    - **> 0.00 Credits/hr (Auction)**: demand exceeds supply. Only MDBs whose
      bid at their requested chip count clears the price get the resource.

### `ResourcePrices` sentinels: free vs unobtainable vs not offered

`MilliCreditsPerUnitHour` encodes non-numeric states in-band. Collapsing them
loses real signal, so decode all four cases separately:

| Raw value | Meaning | Render as |
|---|---|---|
| `0` | genuine free-pool clearing price | `0.00 (free pool)` |
| `INT64_MAX` | **unobtainable** in that cell this cycle | `unobtainable` |
| `INT64_MIN` / negative | no bid recorded; GQM sanitizes to 0 | `0.00` |
| *no row at all* | pool does not offer this card | `not offered` |

- A price of `0` is a **real auction outcome**, not missing data — verify by
  checking for the literal integer rather than assuming. Reference decoding
  lives in `gqm_tool.py` (`CASE WHEN ... 9223372036854775807 THEN -1 ...`).
- **Free does not mean available.** Price reflects last cycle's supply/demand,
  not inventory: a card can clear at 0.00 while only a handful of chips are
  actually obtainable. Always cross-check the BATCH forecast before choosing an
  accelerator on price alone.
- Because `INT64_MAX` cells are excluded from the price range, report the count
  of unobtainable cells alongside it, or a "free" row can look healthier than
  the pool really is.

### Reading quota correctly: `floor_v2`, not pool capacity

Three different numbers are easy to confuse; only the first is *your* quota.

| Source | Scope | Use for |
|---|---|---|
| `ResourceAllocationDetails.floor_v2` | this alloc | **Quota** |
| `get_pool_capacity(pool)` | the entire shared pool | nothing user-facing |
| `get_forecast_info(alloc)` | this alloc, live | **Obtainable** |

- **Quota must be read from `floor_v2`.** `get_pool_capacity` returns the whole
  resource pool (`deepmind-dynamic-pool` spans hundreds of cells and is shared
  by most of our groups), so using it overstates quota by orders of magnitude
  and makes every group in that pool display near-identical numbers. A quick
  smell test: if two groups show the same quota, the pool is being read.
- **All `tpu_*` fields in `resource_model.proto` are raw chip counts.** There is
  no milli-unit encoding; never divide by 1000. `//learning/deepmind/xmanager2/
  resources/proto/resource_model.proto` documents each field as "# of chips".
- The forecast column is a *prediction of what is schedulable now*, not a
  guarantee, and not pool capacity. Label it "Obtainable".
- When rolling several groups into one total, sum quota and usage but take the
  **max** of obtainable: groups sharing a pool are all looking at the same free
  chips, so summing double-counts them.

### Dynamic allocs: `Available = 0` is normal, not exhaustion

For `deepmind-dynamic/*` the floor is **recomputed continuously to track live
usage** rather than being a fixed grant. Consequences:

- `floor ≈ used` holds by construction, so a naive `Available = quota - used`
  sits at ~0 permanently. This does **not** mean the alloc is full.
- The floor visibly drifts between refreshes, and `used` can briefly exceed
  `quota`. Surface that as a caveat; do not "fix" it by clamping.
- To judge real headroom use **Obtainable** (forecast) or `tpu preflight`
  per-cell numbers, never `Available`.
- Corollary: preflight's "PROD quota headroom is thin / remaining=0" warning is
  near-permanent for dynamic allocs and carries little signal. The binding
  constraint is usually topology fragmentation instead.

### GQM Bidding Power: how it is computed
`bidding_power_hourly = daily_credit_income / 24 * income_leverage`.
- `daily_credit_income` = `SUM(UserAllocations.Weight) + SUM(LeadAllocations.Weight)` for this MDB in the target pool.
- `income_leverage` default = 2× (per-MDB overrides exist in `BiddingIncomeLeverageLimitOverrides`).
- The formula lives in `learning/agents/orcas/tools/gqm_tool/gqm_tool.py:get_bidding_power`
  and `//quota/marketplace/handlers/get_bidding_power_handler.cc`.

### `tpu money` CLI Usage
- **Command**: `tpu money` (Aliases: `tpu m`, `tpu price`).
- **Features**:
  - **Zero-latency offline fetch**: the CLI only `cat`s a cache file, so it is
    instant; all latency lives in the background daemon
    (`tpu_check_daemon.sh`), which refreshes on a loop.
  - **Group Money Table**: per MDB alloc, PROD/BATCH chip usage plus two
    distinct money figures — **Bidding Power** (credits earned per hour, a
    *flow*) and **Balance** (accumulated credits, a *stock*, from Spanner
    `MdbCreditBalance`). Do not conflate them: a large balance with tiny income
    still bids well for a while. Static-pool MDBs have no balance row and are
    shown as `n/a (static pool)` rather than `0`.
  - **Clearing Prices in Your Pools**: **BATCH only**, for major cards (v4,
    v5p, v6e, v6p), filtered to the pools you actually participate in. PROD
    prices are deliberately hidden — PROD admission is quota-gated, so its
    shadow price is noise for scheduling decisions.
- **Related Commands**:
  - `tpu quota` — per-alloc guaranteed floor, usage, and obtainable forecast.
  - `tpu quota -l` — map G1..GN to full MDB allocation paths.

### Cache daemon: keep the round shorter than the staleness threshold

`tpu quota` / `tpu money` warn when their cache is older than **180s**. The
daemon must therefore finish a full round well inside that budget.

- Each checker binary pays a **~15s Python/par cold start** while its actual
  RPCs cost <1s. Running the checkers serially paid that tax three times and
  pushed a round past the threshold, so the alarm fired every cycle. They are
  independent and write to disjoint outputs, so they run **concurrently**.
- When the alarm fires, check the round duration the daemon logs before
  believing its "LOAS/gcert expired" hint — that message is a guess, and
  `gcertstatus` usually disproves it.
- Rebuild **all** checker binaries in one `blaze build` invocation. Building a
  single target evicts the other binaries from `blaze-bin`, and the daemon then
  reports failures that look like data or auth bugs.

### Web UI for quota

Authoritative browser view (uberproxy 302 on `curl` is expected; open in a
browser):

- All allocs for a user: `https://xmanager.corp.google.com/resources/users/$USER`
- One alloc: `https://xmanager.corp.google.com/resources/pools/<pool>/allocations/<url-encoded alloc>`
- Whole pool usage: `https://xmanager.corp.google.com/resources/pools/<pool>/usage`

## Preemption, Restart, And Resume

### What a Borg task restart actually restores: nothing

A restart re-executes the binary from `main()` on a fresh machine with the same
argv and environment. There is **no process state, no memory image, no TPU HBM
snapshot, and no "execution position"**. Transparent migration is a Pathways
feature, not a property of a plain Borg job. Continuity of training is therefore
100% the application's job, via checkpoints.

### A job with no restart budget dies on its first preemption

`xm_abc.BorgScheduling` defaults to `max_task_failures=0` and
`max_per_task_failures=0`, i.e. *never restart*
(`third_party/py/xmanager/xm_abc/executors.py`). The preemption itself is a free
failure that is not counted, but when the TPU gang is torn apart the non-zero
task exit **is** counted, and Borg then declares the job dead. One preemption
kills the experiment.

Always pass an explicit `scheduling=`. `tpu_cmd/xm_launcher.py` sets it for both
tiers, with `--max_task_failures` / `--max_per_task_failures` (default 10) plus
`task_failure_credit_period=3600` so a long run is not killed by slow attrition
of unrelated one-off failures.

### Checkpoints must not live in `workdir`

`workdir` is task-local (`/tmp/...` on a TPU worker) and is wiped by the very
event the restart budget exists to survive. A restart budget without durable
checkpoints only buys you the right to redo the run from step 0.

### The env-var contract between launcher and training code

Resume/eval selectors travel as **environment variables**, not as `--config`
flags. This follows `unified_infra` (`infra/runjob.py`), and EqR-jax's `main.py`
already consumes exactly these names in `_ENV_CONFIG_OVERRIDES`.

| Env var | Set by | Meaning |
|---|---|---|
| `LOAD_FROM` | launcher `--load_from` | Checkpoint to evaluate or warm-start from. Local path or `gs://`. Explicit value always wins over auto-resume. |
| `WANDB_RESUME_ID` | launcher `--wandb_resume_id` | Tracking run to continue. |
| `CHECKPOINT_BUCKET` | launcher, always | Durable GCS prefix for this experiment's own checkpoints. Derived from the XID, so **every restart of a given XID resolves to the same prefix** — that stability is what makes in-process auto-resume well defined. |

Do **not** inject `--config.checkpoint_path`. `configs/default.py` has no such
field and the config flag is declared `lock_config=True`, so passing it makes
every job die at startup. This was a real, long-lived bug.

### Auto-resume has to live in the application

`unified_infra` solves resume from the outside: a 24/7 daemon greps each
attempt's log for the last complete checkpoint and passes it as `--load_from` on
the next launch (`infra/resume.py`, `infra/monitor.py`). Under Borg there is no
external brain in the loop — the launcher runs once, on your workstation, at
submit time — so the equivalent decision must happen **in-process at startup**.

EqR-jax implements this in `main.py::_apply_borg_autoresume` +
`utils/ckpt_util.py::latest_checkpoint`:

1. Read `$CHECKPOINT_BUCKET`; skip entirely if `LOAD_FROM` was set explicitly or
   the run is `eval_only`.
2. Enumerate `step_<N>[_<run_id>]` directories under `<bucket>/checkpoints`.
   Enumerating the prefix beats parsing logs: a rotated or lost log would
   otherwise silently restart from zero and discard real progress.
3. Skip any directory with no `extra.json`. That file is written **last**, so
   its absence marks a checkpoint that was still being written when the task
   died. This mirrors unified_infra's "a bare `Saving` with no `saved to` is
   incomplete and ignored" invariant.
4. Resume from the highest surviving step.

### `gs://` paths and the stdlib

Orbax reads and writes `gs://` natively through tensorstore, so checkpoint
payloads never need downloading. The stdlib is the problem:
`os.path.isdir("gs://...")` is always False, and `os.path.abspath` mangles the
URI into `"<cwd>/gs:/bucket/..."` — which is exactly how a remote `load_from`
turns into a bogus "directory does not exist" error. Route every existence check
through the `is_remote_path` / `resolve_path` / `path_is_dir` / `path_exists` /
`read_text` / `write_text` / `join_path` helpers in `utils/ckpt_util.py`
(backed by `etils.epath`, an orbax dependency).

## Preflight & Router (client-side pre-check before packaging)

Bazel packaging of an XM job costs ≈5 min. Submitting a job that the allocator
will reject in seconds wastes that time. `tpu preflight` runs client-side
checks in ≈15s to catch common failure modes BEFORE packaging.

### `tpu preflight` verdict layers

1. **L1 (µs, in-process)**: topology whitelist + per-alloc PROD min-slice
   rules (e.g. `deepmind-dynamic/*` forbids v6e slice < 16 chips). Catches
   `v6e-8`, `v6e-13`, `v7-8`, `v5p-8192`, and similar.
2. **L2 (~1 RPC, ~1–2s)**: `GoodputService.GetCellAvailability` → do any
   cells in this alloc + tier have ≥ request-chip count *obtainable*? Catches
   `alloc has 0 chips of this platform`, `all cells drained`, etc.
3. **L2.5 (heuristic)**: PROD headroom — if `remaining_quota < 2× request`,
   warn (YELLOW). If the pool is bursty this may still succeed; if not, expect
   `RESOURCES_EXCEEDED`. On `deepmind-dynamic/*` this warning is near-permanent
   and low-signal; see "Dynamic allocs: `Available = 0` is normal".

Verdict is one of **GREEN / YELLOW / RED**. `tpu queue` refuses to submit on
RED unless `--force` is passed. YELLOW proceeds with a warning. Use
`--skip-preflight` to bypass entirely.

### What preflight canNOT catch (important)

**Topology fragmentation** — e.g. the alloc has 1000 free v6e chips *in total*
across many cells, but no single cell has a contiguous `4x4` slice free. The
allocator will accept the submit, then reject seconds later with `Rejected by
Allocator/Borg`. **A GREEN preflight verdict is therefore a necessary but NOT
sufficient condition for success.**

The only API that reports free-slice topology counts is
`BorgMaster.ProbeSliceAvailability`, which is C++ only (no Python stubby
wrapper) and requires per-cell fan-out plus ACL grants. Building this is
tracked; today the workaround is the existing daemon auto-retry loop for
`PROD + "Rejected by Allocator/Borg"` (5 retries, 5-min gap).

Other things preflight cannot see: the exact GQM auction outcome for BATCH
(nobody can), transient BCID/attribution rejects, Research Hub attribution
prompts.

### `tpu route` (local router)

Given a desired *power class* (compute-equivalent), suggest the best
`(group, tpu_type)` combo across your allocations:

```
tpu route --power=v5p-32 [--tier=PROD] [--groups=1,3,5] [--top=3]
# power can be 'v5p-32', 'v6e-16', 'v4-32' (all equivalent), or a bare int.
```

Power equivalence (heuristic, v5p-chip units):
`1 v4 = 1 v5p = 0.5 v5e = 0.5 v6e = 0.5 v6p` chips.

Router fans out preflight checks in parallel (≈26s for 8 groups × 5 archs),
then ranks survivors by:

1. Verdict status (GREEN > YELLOW; RED filtered out).
2. `remaining_quota / requested_chips` (headroom ratio).
3. `max_cell_obtainable / requested_chips`.
4. Accelerator preference (v6e > v6p > v5p > v4 > v5e).

**Router does not solve L3 fragmentation either.** It picks the group with
the most headroom, but if all groups' available chips are fragmented, the
top-1 pick will still fail post-packaging. Consider running the router with
`--top=3` and manually preferring cells that historically succeed for you.

### `tpu queue --power=` shortcut

Instead of specifying `--group` and `--tpu_type`, pass `--power=` and the
wrapper will call the router internally, pick top-1, print the choice, then
preflight + submit.

### Full command reference

See `~/work/tpu_cmd/README.md` for exhaustive flag documentation and common
workflows. Highlights:

- `tpu queue --force` — override RED verdict.
- `tpu queue --skip-preflight` — skip the check entirely.
- `tpu preflight --json` — machine-readable verdict.
- `tpu route --verbose` — stream per-candidate probe results.

## TPU Topology & Performance Equivalences

Source of truth for legal topologies is `borg/common/locus_info.cc` (NOT
`learning/performance/ace/search_space_utils.py`, which is stale for v6e).
The wrapper's `preflight/topology.py` mirrors the relevant subset; add new
accelerators there.

### Legal shapes per accelerator

| Arch | Codename | Torus | Legal chip counts | Locus example |
|---|---|---|---|---|
| v4 | pufferfish | 3-D | 8, 16, 32, 64, 128, 256, 512, 1024, 2048 | `v4-32` → `2x2x4` |
| v5p | viperfish | 3-D | 8, 16, 32, 64, 128, 256, 512, 1024 | `v5p-64` → `4x4x4` |
| v6p | ghostfish | 3-D | 8, 16, 32, 64, 128, 256, 512 | – |
| v6e | ghostlite_pod | 2-D (8/machine, pod = 16×16) | 8, 16, 32, 64, 128, 256 | `v6e-16` → `4_4` |
| v5e | viperlite_pod | 2-D | 8, 16, 32, 64 | `v5e-16` → `4_4` |

Borg expects the shaped locus string (`2x2x4`, `4_4`, `16_16_wrap_xy`) NOT
the scalar core count. `xm_launcher.py` handles this translation.

### Per-allocator PROD min-slice policies (empirical)

Allocators inside `deepmind-dynamic/*` (including `vqfree-xm`,
`viscam-interns`, `gdm-viscam-goflow-dynamic`, etc.) enforce **min slice = 16
chips** at PROD tier for v4/v5p/v6e/v6p. Below that, the allocator rejects
instantly with `Rejected by Allocator/Borg`. These are pool policies, not
physical Borg rules — `v6e-8` (`locus:...:2_4`) is a valid Borg locus, it's
just disallowed by the deepmind-dynamic admission config.

BATCH tier typically allows down to the arch's minimum legal chip count.

`preflight/topology.py::_ALLOC_MIN_SLICE_RULES` encodes these; if you hit an
allocator with different rules, update that table.

### Performance Equivalence Heuristic

- **1 v6e chip ≈ 1 v6p chip ≈ 2 v5p chips ≈ 2 v4 chips** in compute/throughput.
- Consequently `v6e-16` ≈ `v6p-16` ≈ `v5p-32` ≈ `v4-32`.
- Used by `tpu route --power=` to enumerate equivalent options.


## Status And Diagnosis

1. Start with `tpu check` and resolve the exact experiment and work unit.
   Experiment-level `RUNNING` does not prove that hardware was allocated; use
   work-unit state, allocation, logs, and activity to distinguish queued from
   executing.
2. Read the complete relevant failure, not only the final status string. An
   immediate failure without logs can be allocator, topology, packaging, or
   authorization related.
3. If the error explicitly indicates expired or invalid credentials, ask the
   user to run `gcert`, then retry the read. Do not diagnose every access or
   missing-log failure as a credential problem.
4. If normal log access still fails after identity is valid, use the supported
   XManager API or `tpu_utils` in the current Google3 checkout to inspect the
   work-unit status message. Do not patch shared scripts with hard-coded job ids,
   and do not assume an alternate API bypasses authorization.

### TPU Check Error Rules & Auto-Retry Mechanism

The backend `tpu_check_daemon.sh` parses XManager launch logs and classifies errors as follows:

*   **Preempted by Defag**: Greps for `SLICE_DEFRAGMENTATION`.
*   **Resource Exhausted (Topology/Quota)**: Greps for `RESOURCE_EXHAUSTED` or `RESOURCES_EXCEEDED`.
*   **Rejected by Allocator/Borg**: Fallback for `FAILED` status with an empty or `unknown reason`.
*   **Unknown failure**: Greps for `FAILED` when `Preempted` is not present.

**Auto-Retry Policy**:
If a job is queued in the **PROD** tier and fails specifically with **"Rejected by Allocator/Borg"**, the daemon will automatically retry launching the job up to **5 times**, waiting 5 minutes (300 seconds) between each attempt.

That client-side retry is the daemon **resubmitting a new experiment**, which is
a different mechanism from the in-job Borg restart budget described in
§Preemption, Restart, And Resume. Preempted jobs are *not* covered by it.

**A preempted job is dead, not pending.** With `max_task_failures=0` (the old
default, see §Preemption) Borg counts the torn-down gang as a task failure and
never re-queues it. `tpu check` used to render any work unit whose status
message merely contained "preempt" as PENDING, which made dead experiments look
like they were still waiting in a queue for hours. Terminal state must win over
the preemption substring; a genuinely-queued job that was preempted earlier is
labelled `... (was preempted)`. Fixed in `infra_check.py` and `tpu_wrapper.sh`;
`infra_check` must be rebuilt with `blaze build` for the daemon to pick up
changes.

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this guide whenever implementation details change.
