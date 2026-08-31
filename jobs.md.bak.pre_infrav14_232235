# Running Jobs On The Cluster

Queue, inspect, resume, and debug a job on the internal XManager/Borg stack.
`storage.md` owns where data and checkpoints live, `tpu_reference.md`
accelerator naming and shapes, `infra/` the market, allocator, and CLI
internals — read those only when the rules here do not explain what you see.

## The Submission Queue In One Screen

**This is a SHARED workstation that chronically has several builds in flight, so
the default submission path is `tpu enqueue` (instant, free) + one serial
`tpu build-worker` draining builds one at a time.** A one-shot `tpu queue` races
any other in-flight build on the blaze `output_base` (per checkout ROOT, not per
copy dir) and silently ships a **zombie XID with 0 work units**; only serial
building cures it (`infra/tpu_cli.md` §The Local-Queue Smart Router owns why).

| You want | Do | Details |
|---|---|---|
| Launch one job (default) | `tpu enqueue …` with a `tpu build-worker` running — it builds serially, cell auto-picked | §The Local Queue |
| Launch a batch / sweep | `tpu enqueue` each arm; the same worker drains them one at a time | §The Local Queue |
| Keep a run in its data metro | add `--metro=<m>` (e.g. `cbf`); a full metro **refuses** rather than roaming to a no-data cell | §Choosing Where To Run |
| One-shot, no worker (fallback) | `tpu queue …` — synchronous, returns an XID; ONLY when no other build is in flight | §Submission Contract |
| A job stuck PENDING past 10 min | the router cancels and re-routes it to a placeable cell | §The Local Queue |

Both paths share one submission contract (same flags, same registry) and the
same smart cell pick — the least-oversold placeable cell, so you rarely pass
`--cell` (it always wins; `TPU_NO_SMART_CELL=1` opts out; §Choosing Where To Run).

## The Launch Workflow

Run this every launch. Each step names the section that explains it; this is the
skeleton, the detail is below. Placement (steps 2–4) is cheap and settled
*before* packaging, because packaging costs minutes and an allocator rejects in
seconds.

1. **Prepare the submission** (§Submission Contract). Semantics in versioned
   config; on a shared checkout, edit the config in a COPY and launch from it;
   `--tier=PROD` for training, `BATCH` only for eval.
2. **Pick the group** (§Choosing Where To Run). Default **g9** for TPU (it holds
   the floor), **g8** for CPU-only. `tpu quota` tells you WHICH GROUP holds a
   floor for the accelerator — nothing about cells.
3. **The cell is auto-picked — you usually skip this step** (§Choosing Where To
   Run). The submit pins the most-free non-oversold placeable cell for you; add
   `--metro=<m>` if the run is data-locality-locked. Only drop to the manual
   probes below when you need to OVERRIDE the pick or understand a rejection:
   - `tpu preflight --tpu_type=<t> --group=<g> --json` → the `cells_ok` list with
     a per-cell **obtainable** count (the only cell-level view; `tpu quota` has
     none). Obtainable means "can be *got*", not "can be *held*".
   - `stubby call master.<cell>.borg:9413 BorgMaster.ProbeSliceAvailability` for
     **free contiguous slices** — a cell can hold thousands of obtainable chips
     and *one* placeable slice (shape uses UNDERSCORES; `research/v7_storage_placement.md`).
   - Intersect with a cell where you hold a **floor** and your **data is
     co-located** (§Choosing Where To Run; `storage.md`). Same obtainable number
     is an idle guarantee in one (group,cell) and borrowed-reclaimable in another.
4. **Preflight, then verify the snapshot** (§Choosing Where To Run,
   §Submission Contract). Green is necessary, not sufficient; CPU-only jobs use
   `--skip-preflight`. `diff` the packaged config against what you meant to run.
5. **Submit, then confirm it is REAL** (§`state: RUN`). An XID is not a job and
   `state: RUN` is not evidence — confirm a `VMGROUP_STATE_RUN` at the cluster
   layer before you start waiting.
6. **If it sits PENDING, read the work unit's own verdict before reacting**
   (§When A Pending Job Should Move) — do NOT reflexively resubmit or wait. The
   verdict, not the obtainable table, tells you whether to move cell, move
   group, or leave it queued.

## Submission Contract

- **Submit through the wrapper**: `source ~/work/tpu_cmd/tpu_wrapper.sh &&
  tpu enqueue ...` (the default path; a `tpu build-worker` drains it serially —
  §The Local Queue). Never call `xm launch` / `xmanager launch` directly; only
  the wrapper may do so internally.
  `tpu` is a shell FUNCTION, not a binary on `PATH` — so a launcher SCRIPT that
  wraps it (e.g. sourcing a guard helper) must `source
  ~/work/tpu_cmd/tpu_wrapper.sh` in the SAME shell, or the call dies with `tpu:
  command not found` (seen as an instant guard "DEAD", ~6 s, no stagedir).
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
  **The default is `remote_run`; write the run into `remote_run_config.yml` and
  DO NOT pass `--config`.** If a mode must be named, pass the BARE name
  (`--config=trm_sudoku`), never a path or filename: the launcher wraps the
  value into `configs/<mode>_config.yml`, so `--config=configs/x_config.yml`
  double-wraps to `configs/configs/x_config.yml_config.yml` and the job dies at
  startup with "Could not locate …". The launcher now normalises the value and,
  on a resume, refuses a missing config before packaging — but the contract is
  the bare mode, and a resume that skipped this check once shipped exactly this
  bug.
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
- **The cell is auto-selected by default.** The submit pins the best placeable
  cell for you (§Choosing Where To Run); pass `--cell` to override, `--metro=<m>`
  to constrain the pick to a data-co-located metro, or `TPU_NO_SMART_CELL=1` to
  opt out. This is transparent — no command changes.
- **Packaging freezes the code.** The wrapper packages a snapshot; later edits
  do not affect a queued or running job.
- **Verify registration after submit** rather than assuming the launch
  transaction completed.
- **Default to `tpu enqueue` + one serial `tpu build-worker` — for a single job
  as much as for a batch.** On this shared workstation a one-shot `tpu queue`
  races other in-flight builds on the blaze `output_base` and ships a
  0-work-unit zombie XID; the serial worker builds one at a time, the only thing
  that avoids it. `tpu build-worker start` once, then `tpu enqueue` each run from
  its own checkout and watch `tpu queue-status`. Mechanism, the failure modes it
  cures, and the worker's guards: `infra/tpu_cli.md` §The Local-Queue Smart
  Router. `tpu queue` (one-shot, synchronous) is the fallback for when you KNOW
  no other build is in flight.

## Requirements And Runtime

- **Every TRAINING job must pass `--tier=PROD` explicitly. `BATCH` is for
  eval-only jobs.** BATCH is best-effort and is preempted by any PROD demand the
  instant a slot is contested. The launcher default IS PROD for every group
  (g5 injects it; others inherit XManager's `_DEFAULT_SERVICE_TIER=PROD`), so
  pass `--tier=PROD` for a clean audit trail, not to change behavior. `tpu
  check`'s TIER column echoes the REQUESTED string from the local registry, not
  Borg truth: a `-` means "untagged, so it ran the PROD default", NOT
  "non-PROD" — read the work unit/allocator for ground truth. Only ever run
  evals on BATCH.
  **GPU is the one nuance:** most GPUs have a free (0.00) BATCH pool and GPU PROD
  is cheap, so a short GPU *smoke* on BATCH is fine — but BATCH still preempts
  (`guarantee reclaim`), so use `--tier=PROD` the moment a GPU run must actually
  finish. `gpu_on_borg.md` §Tiers owns this.
- **Priority <= 25 charges the person; above it charges the group.** The free
  tiers simply do not touch the team's GCU allocation. `BATCH` reads like the
  cheap option and is the opposite: a *paying* best-effort tier billing the
  group.
- **Set the tier with `--tier`, never `--priority`** (that wrapper flag is dead —
  parsed, never read). Prefer the named tiers: a raw numeric `--tier=N` changes
  who pays (`<= 25` bills you personally) and shrinks the per-cell task cap. A
  bigger number does not win contention either — schedulability is set by the
  quota floor/market, not the number (`infra/quota_market.md`).
- **A CPU-only batch job does not belong in an accelerator group.** In GQM, CPU
  and RAM are *ancillary* to accelerator usage, so a job asking for neither is
  scheduled last, always — structural, and waiting never fixes it (a priority-0
  probe sat in `starting` for 14 hours). Use the shared best-effort CPU pool
  (`go/gdm-cpu-only-jobs`, `--group=8` in our launcher): **pre-authorised** —
  own LDAP, no request, no approval — and it bills nothing. **Its ceiling is per
  user** (order 1000 GCU, 1 TiB RAM), so two 900-task jobs evict *each other*;
  run them serially.
- **But the shared CPU pool can be empty for days, and then a CPU-only job never
  schedules at all.** When it is dry, ride the team's PROD accelerator alloc
  instead: a CPU-only *controller* (a server-side data copy is the archetype —
  a few cores driving storage-layer copies, `§Where The Storage CLI Exists`)
  costs the accelerator group almost nothing yet schedules immediately where the
  shared pool has zero. Submit to the same `(group, PROD)` your long jobs already
  run on, pin a cell in the data's metro, add `--skip-preflight` (CPU-only
  cannot be preflighted), and confirm `VMGROUP_STATE_RUN`. The shared-pool
  advice is for genuinely-free best-effort batch; it is **not** a prohibition on
  PROD for CPU-only. Diagnose from your own fleet: two submits differing ONLY in
  group — shared pool sits unscheduled for a day, PROD alloc reaches RUN in ~1
  minute.
- Container-style packaging requires the pool to have a mapped cloud project;
  native allocators without one need Bazel packaging.
- **In JAX jobs, parse flags before distributed initialization**, and never
  initialize at module import time. `projects/eqr_jax.md` has the
  google3-specific startup order, stricter than the public contract.

## Choosing Where To Run

Packaging costs minutes; an allocator rejects in seconds — settle placement
first. The decisions are here; the mechanism is in `infra/`.

- **The cell is now chosen for you by default — you rarely pass `--cell`.**
  Every submit first asks which cell can actually place the slice RIGHT NOW
  (most free chips, not oversold) and pins it, so a submit stops landing on an
  oversold cell while the same accelerator sits idle elsewhere (the disease that
  once pinned 13 v7-32 jobs to an oversold `yulpptr` while `yukulwh` had 101 free
  slices). It prints `Smart cell: pinned --cell=…`. Your own `--cell` always
  wins; `--power` does its own pick; a comma `--tpu_type` list and
  `TPU_NO_SMART_CELL=1` skip it; and if nothing can be recommended it silently
  falls back to letting the allocator choose — it can only help, never block. So
  the group still matters (below), but the cell usually does not.
  - **A data-locality-locked run passes `--metro`, not a hand-pinned `--cell`.**
    The pick ranks on free chips and oversold ONLY; it has no storage-co-location
    dimension (next bullet), so left unconstrained it can send a run to a cell a
    metro away from its checkpoint bucket — 4-5x throughput and the pruner kills
    it (storage rule). But data-locality is a METRO-level constraint, not a
    cell-level one: a whole metro shares one storage cell (cbf's `yucbfiv`,
    `yucbful`, `yucbfwv`, `yucbfsl`, `je` all read `/cns/is-d`), so you do not
    need to name a single cell. Pass **`--metro=<m>`** (e.g. `--metro=cbf`) and
    the smart pick stays inside that metro while still choosing the least-oversold
    cell in it — same-metro AND avoids the stall, both at once. `--metros=a,b`
    allows several. `--metro` is a router selector only (it never reaches the
    launcher). Reserve an explicit `--cell` for when you truly must pin one exact
    cell; for storage locality, `--metro` is the right, less brittle tool. Only a
    run with no storage constraint should let the default roam all metros.
    - **`--metro` fails CLOSED when the metro is full.** If no cell in the named
      metro can place the slice right now, the submit **refuses** (rather than
      roaming to an out-of-metro, no-data cell where the dataloader
      would crash — the exact incident that drifted 3 arms to `yuskedq`). Wait
      and retry (the metro frees up), or pin an explicit `--cell=<in-metro cell>`
      to stage-and-queue there. Only a run with NO data need should override with
      `--force` / `TPU_METRO_FALLBACK=1` to permit an out-of-metro cell.
- **Pick the group first, and default to the one that actually holds your floor.**
  A PROD floor is per (group, accelerator, cell) (last bullet), so the group is
  not cosmetic — it decides whether a slice sits inside an idle guarantee or is
  borrowed and reclaimable. For this account:

  | Group | Alloc (short) | Use for |
  |---|---|---|
  | **9** | `fr-dna-grand-challenge-team-resource` | **TPU training — the default.** Holds essentially all of this account's real v6p / v7 / v4 floor; where the stable jobs already run. |
  | **8** | `brain-vasp-shared-user-xm` | **CPU-only jobs**, with `--skip-preflight`. No TPU floor at all — its `tpu quota` table is empty, so size a CPU fan-out by what actually schedules (§`state: RUN`), never by quota. |
  | 5 | `vqfree-xm` | Free pool; auto-injects PROD (§Requirements). |
  | 1, 7 | `*-resources-prod-shared` | Shared prod; thin-to-zero floors — a fallback when g9 is contended, not a default. |
  | 2, 3, 4 | `*viscam*` / `*interns*` | viscam / intern allocations. |

  Full alloc strings are in `~/work/tpu_cmd/tpu_wrapper.sh::get_alloc_by_group_id`
  (the single source of truth). "Default g9" is a starting point, not a law: if
  g9's floor for the accelerator you want is already fully used, or your data
  lives in a metro g9 has no floor in, fall back by the (group, accelerator,
  cell) rule below.
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
- **`tpu quota` answers one question — which group holds a floor — and nothing
  about cells or schedulability.** It prints Quota / Used / Available /
  Obtainable aggregated per GROUP, with **no cell column**. Quota is the
  guaranteed floor (a contract, not a ceiling); Available = Quota−Used reads ~0
  almost always (the steady state in the next bullet); only Obtainable carries
  live signal, and even that is group-aggregated. So use `tpu quota` to pick the
  GROUP (who holds a floor for this accelerator), never to choose a cell or make
  a go/no-go — the number that decides a launch is the per-CELL obtainable from
  `tpu preflight --json`.
- **A full or fully-consumed quota floor is NOT a blocker — it is the steady
  state.** `used == quota, available 0` is normal for these allocs (a floor is a
  guarantee, not a limit); the job still queues and runs, and preflight's YELLOW
  about it is informational. The number that decides whether a job starts is the
  **per-cell obtainable** count in `tpu preflight --json` (and, once submitted,
  the work unit's own `GQM_RESOURCE_DEFICIT_INFO`). It is volatile and
  uncorrelated with storage — the cell with the largest co-located quota can
  read *zero* while middling cells run to completion — so re-check immediately
  before launching and pick a cell currently good on both axes.
- **`tpu route` and the market summary only SAMPLE cells — never read either as
  the complete list.** Both show roughly one cell per accelerator, so treating
  them as exhaustive says an accelerator exists only where the sample landed
  (once `tpu route --power=v6p-64` reported v6p solely in `yuphxrp`, phx with no
  team storage, while preflight's `cells_ok` listed nine cells including two
  co-located with our data — nearly costing a run its locality). For *where can
  this run at all*, ask `tpu preflight --json` for the full `cells_ok`, or read
  the router's market cache (`infra/quota_market.md`), then intersect with
  storage placement (`storage.md`).
- **Prefer cells whose metro holds storage you can actually write** — the
  scheduler ranks on capacity and price and knows nothing about your data, so
  the cell with the most free chips is often the one with no team storage, where
  everything lands on the personal per-cell ceiling (`storage.md` owns placement
  and why distance kills a run). Make it a *preference* over a cell list, not a
  ban: a storage-less cell is real capacity as long as something sweeps the
  quota. The platform reads a multi-cell allow-list only in its
  spatially-flexible mode, so set both together; pinning a cell bypasses both.
- **A PROD floor is per (group, accelerator, cell) — a tier alone guarantees nothing.** A
  RoboTwin DP smoke took FIVE launches to hold: `BATCH v6e-8` was preempted 4x by
  higher-priority prod during the ~3-min cold-import; `PROD v6e-16` in `yucbfrl` was
  guarantee-reclaimed twice because **group 1 has a ZERO v6e floor there** (`preflight`
  still lists thousands of chips *obtainable* — obtainable is borrowed capacity a guarantee
  holder can reclaim mid-compile, not a floor); `PROD v7-16 yutulpz` hit "cell oversold".
  It only stuck on **`v7-16`, group 9, in `yulpptr`/`yutulpz`** — the exact (group,
  accelerator, cell) where this account's STABLE jobs already run, co-located with the data
  mirrors. **Diagnose capacity from your own fleet: launch where your long jobs already
  survive, not where preflight says chips are obtainable.**

## When A Pending Job Should Move

**A fresh submit already picks a placeable cell** (§Choosing Where To Run), so
this section is mostly for a job that went PENDING AFTER it was placed, or one
submitted with an explicit `--cell`. A fresh submit will avoid the oversold
cell on its own.

**Queued is not failed, and PENDING for hours can be normal** (an oversold pool
leaves work units PENDING for hours). Do NOT reflexively resubmit — every
resubmission stacks another work unit contending the same slice. Instead, **read
the work unit's own verdict** (`deep_probe` / `why_probe` on the live unit, or
its `GQM_RESOURCE_DEFICIT_INFO`) and act on THAT. The obtainable table cannot
tell these cases apart — it reads the same in all of them.

| Work unit verdict | What it means | Move? |
|---|---|---|
| `GQM_OVERSOLD_MARKET` "in cell X…" | that CELL is oversold | **Change cell** — the verdict names it; another cell may take it |
| `GQM_RESOURCE_DEFICIT_INFO`, deficit N (names a cell) | short N chips in that cell | **Change cell** — pick one with a smaller/zero deficit |
| `resource-guarantee-reclaim` | you held borrowed capacity; a floor holder took it back | **Change to a (group,cell) where YOU hold a floor**, don't re-fight for borrowed chips |
| `dynamic root pool … capped by adjusted ceiling` (deficit names NO cell; g1/g5/g9 read identical) | pool-wide limit | **Cell won't help.** Change tier, change accelerator generation, or wait for the price to fall |

**Two false-pending causes to rule out first**, because neither is a capacity
problem and neither is fixed by moving cell:

- **A price cap (limit order) triggered.** A pending job is pulled from the queue
  *before* any capacity check when the pool price exceeds the cap — free chips do
  not help, and the cap is pool-wide so moving cell does nothing. It is often a
  teammate's group-wide cap silently applying to you. Check
  `tools/limit_order.sh status` for `BLOCKING` first (`infra/quota_market.md`).
- **It never actually reached the scheduler.** An XID with no work unit, or no
  XID at all, is a launcher-side failure, not a queue — read it as a local
  problem (§Launcher-Side Failures).

**When the verdict is ambiguous, stop reading tables and queue a real probe.**
A short submit with the real workload answers "can I get this slice here" at 100%;
the capacity table was ~12% accurate against the live queue
(`research/accelerator_choice.md`).

## The Local Queue: `tpu enqueue` + Serial Build-Worker

**`tpu enqueue` + a serial `tpu build-worker` is the DEFAULT submission path**
(§Submission Contract), for a single job as much as for a batch: on this shared
workstation the serial worker is the only thing that avoids the concurrent-build
`output_base` race and its 0-work-unit zombie XID (`infra/tpu_cli.md`).
Enqueuing is instant and free — a queued job costs nothing (PENDING does not
bill) — and the worker builds one at a time. Beyond the single-job case the
router also:

- drains a **batch / sweep** as capacity frees up, no babysitting N submits;
- **re-routes automatically** anything that goes PENDING after placement (the
  10-minute sweep, below);
- handles a **mixed batch across several checkouts** (each entry remembers its
  own source dir).

The mental model is two queues. The **local queue** is a durable, unlimited list
of desired runs; the router drains it into the XM queue one placement at a time,
choosing a cell that can place the slice **right now** (free chips, not the
obtainable table; never an oversold or full cell) and re-routing anything stuck.
`tpu queue` — the one-shot fallback — instead admits a job to ONE cell and waits.

**Never enqueue with `priority` > 0 without the operator's explicit permission.**
The local queue drains highest-priority-first (`tpu enqueue --priority=N`; the
router sorts by `-priority`, so a bigger number jumps the queue). On this shared
workstation every line enqueues into the *same* local queue, so one line quietly
setting `--priority=5` or `6` parks every default `priority=0` job behind it
indefinitely — a line that never raised its priority can be starved for the whole
shift while wondering why its arms never build. **The default is `priority=0` and
you leave it there.** Raising it is a fleet-wide fairness decision, not a
per-line optimization: only the operator, who can see all lines' needs, may
authorize a `priority>0`. If your batch genuinely needs to go first, ask — do not
self-assign. (This is distinct from the dead `tpu queue --priority` CLI flag
above, which is parsed but never read; the *local-queue* priority field IS
honored, which is exactly why misusing it starves peers.)

| Command | Does |
|---|---|
| `tpu enqueue --power=v7-32 --archs=v7,v6p --launch=config=...` | Add a desired run. `--archs` lists the accelerator generations it accepts; `--launch=k=v,flag` is passed verbatim to `tpu queue` at submit. |
| `tpu queue-status` (alias `tpu qs`) | The local queue plus, live, why each job waits or which cell it is placeable in now. |
| `tpu dequeue <job_id>` | Remove one before it is submitted. |
| `tpu requeue [job_id...]` | Return HELD job(s) to QUEUED after you fix the cause (empty = all held). |
| `tpu build-worker start` \| `stop` \| `status` | The SERIAL build-worker (dedicated tmux session): claims one QUEUED job at a time as BUILDING, runs its build, records the XID, repeats. One build in flight at a time — the safe way to drain a batch. |
| `tpu route-tick` | Run one router pass by hand (no daemon/worker): plan (dry-run) then, with `--nodry_run`, submit placeable jobs. `--reroute --nodry_run` cancels jobs stuck PENDING past 10 min and re-queues them. |

A job's state moves QUEUED → **BUILDING** (a worker is running its build now, the
one live build) → SUBMITTED → RUNNING; `tpu queue-status` and `tpu check` show
which stage each is in. A build that produces no XID (a `found[]` zombie) is
requeued, not left dangling; a crashed worker's stale BUILDING claim is reclaimed
after `--build_stale_s`.

**HELD is the anti-churn park.** An unattended worker must not spin forever on a
job it can never build, so it moves such a job to **HELD** (skipped until a human
acts) instead of requeuing it endlessly: a `--workdir` that does not exist (park
immediately — the wrong source would be packaged), or a job that fails to produce
an XID `--max_build_attempts` times (default 3). This is exactly what catches a
stale/duplicate enqueue (e.g. entries whose runs are already on Borg) or an
empty-workdir batch enqueued from the wrong directory — they sit HELD, not
churning or double-firing. Fix the cause (usually: re-`tpu enqueue` from the
right checkout so `workdir` is captured) and `tpu requeue` the rest; inspect why
with `tpu queue-status`.

**A checkpoint-sharded resume must pass `--topology_locked`.** Then the router
only moves the job between shapes of the SAME mesh geometry — `v6p-32` and
`v7-32` are both `2x4x4` and interchangeable, but `v6e-32` (`4_8`) is not, and a
locked job is never placed on it. Omit the flag only for a run that can retrain
from scratch. A chip count is not a size (see the top-level rule): give `--power`
an explicit `arch-chips` so the lock has a mesh to anchor to.

**`tpu enqueue` captures the checkout you run it from, so enqueue from the right
tree.** `tpu queue` packages its source by rsyncing the CURRENT directory into
the stagedir, and the router runs the submit from the entry's `workdir`
(defaulting to the CWD at enqueue time). A run whose config or edits live in a
particular checkout — a per-arm snapshot dir, an edit not passed via `--config`
— must be enqueued FROM that directory, or the router ships a copy of the wrong
source. `tpu queue-status` and `tpu route-tick` print the packaging dir so you
can check it before it submits; override with `tpu enqueue --workdir=<dir>`. Only
a run whose every difference rides on an explicit flag is safe to enqueue from
anywhere.

**Enqueuing alone submits nothing; a running `tpu build-worker` is what drains
and submits it** (one build at a time). The separate AUTO-reroute sweep
(cancel-and-requeue a job stuck PENDING past 10 min) is off by default: run
`tpu route-tick --reroute --nodry_run` yourself, or arm the daemon's router lane
with `TPU_ROUTE_ENABLED=1` (unset by default). Neither the worker nor the router
ever submits into an oversold/full cell or cancels a job whose live status it
cannot read. Tool internals: `infra/tpu_cli.md`.

## The `LOAD_FROM` Contract

**A scheduler tells a job where to resume from by setting the environment variable
`LOAD_FROM` to the checkpoint path, VERBATIM — never by a config key, and never after
"fixing up" the path.** Any new launcher, requeue path, or resume tool must follow this
exactly; it is the one interface every family in this fleet already speaks.

**The contract is the ENV VAR, not the config key.** `LOAD_FROM` is what all consumers read.
Which config key it lands in differs per project — EqR-jax family uses `load_from`, the
codi/coconut family uses `load_model_path` — so a producer that writes the *key* instead of
the *variable* keeps working on most lines and silently cold-starts the rest. That failure is
partial by construction: a smoke test on any EqR-jax line passes and certifies the bug.

**Never parse, normalise, or complete the path.** Four incompatible checkpoint shapes coexist,
and every "helpful" transformation breaks at least one:

| Family | Shape | Note |
|---|---|---|
| EqR-jax (maze, trm-arc1, hrm-trm) | `step_<N>/` | the job appends `/state` itself |
| codi, coconut | `step_<N>/` | flat, there is **no** `/state` subdirectory |
| paligemma, jax_llava | `checkpoint_<N>` | flax file |
| torch ports | `step_<N>.pt` | **a single FILE, not a directory** |

Store the string the job itself reported (its `latest_checkpoint()`), replay it unchanged.
`LOAD_FROM` must point at the **leaf**; a bucket root or a `checkpoints/` parent raises
`FileNotFoundError` — after first printing a reassuring metadata warning.

**Clear `LOAD_FROM` once the job has written its own first checkpoint, or set it only for the
first dispatch.** An explicit `LOAD_FROM` wins unconditionally and disables the job's own
auto-resume, so leaving it pinned makes every later preemption reload the same old
checkpoint: a run measured at step 380k restarted from 298k, and it reads as training
instability rather than as an infra fault.

**`CHECKPOINT_BUCKET` is a separate variable and must not be repointed on resume.** It says
where the job *writes*; `LOAD_FROM` says where it *reads*. The torch ports derive their whole
working directory from it, so moving it silently restarts them from scratch.

**Read remote if you must; write local always.** A cross-metro restore read is survivable
(6.0 GiB across the Atlantic measured at ~14 s). A training loop *writing* checkpoints across
a metro is not: throughput falls ~6x same-continent and ~94x cross-continent, blocking saves
push duty cycle under the 0.20 floor, and the WIM pruner deletes the job — no preemption
notice, no crash. Prefer copying the checkpoint to the compute cell's own CNS prefix before
launch (swap the prefix, keep the tail verbatim) and point `LOAD_FROM` at the local copy.

**A job that cannot find its `LOAD_FROM` must fail closed.** Cold-starting instead is the
expensive silent failure: it looks like a successful launch, burns the full run, and only the
loss curve shows it began from scratch.

## Preemption, Restart, And Resume

- **A restart restores nothing.** The binary re-executes from the top on a fresh
  machine with the same arguments: no process state, memory image, accelerator
  snapshot, or execution position. Continuity is the application's job, via
  checkpoints.
- **A job with no restart budget dies on its first preemption.** The preemption
  is a free failure, but the non-zero task exit when the gang is torn apart is
  counted and the job declared dead. Always pass an explicit scheduling policy —
  ours allows unlimited task failures but at most one per task per credit window,
  so a long run survives unrelated preemptions while a task that keeps dying is
  declared dead rather than retried forever.
- **⚠️ In a preemption STORM (thin/borrowed capacity, no floor), the default
  `borg_max_per_task_failures=1` will kill a job that is merely trying to hold
  its ground — this is NOT the same as "never restart".** The `xm_launcher.py`
  defaults are actually `borg_max_task_failures=-1` (unlimited),
  `borg_max_task_evictions=-1` (unlimited), but `borg_max_per_task_failures=1`
  with a 7200s credit window. A *clean* preemption counts as an eviction (budget
  unlimited, fine), BUT when the gang is torn apart the surviving tasks often
  exit non-zero — counted as a per-task *failure*, not an eviction. On a cell
  where you have no floor and get ABORTed repeatedly, each task burns its single
  failure credit within one 7200s window and the whole job flips to FAILED
  (signature: `task_states=[ABORT×N, FAILURE×k]`, WU=FAILED). Observed 2026-08-21:
  four PaliGemma v4-256 arms on `oe` (no v4 floor) all died this way, repeatedly,
  even though a pure-PENDING job would have waited harmlessly for hours.
  **To "queue and ride out the storm" — i.e. keep re-attempting until a window
  holds, instead of dying — you MUST raise the per-task budget explicitly:**
  `tpu queue ... --borg_max_per_task_failures=100` (with the default unlimited
  eviction budget). Then repeated ABORTs re-queue instead of failing the job.
  A job that stays PENDING and never schedules is NEVER failed for waiting
  (board routinely shows others pending 2d+); only a schedule-then-abort with an
  exhausted per-task budget dies. **If you have a real floor elsewhere (see the
  survival test above), prefer that — the budget knob is for riding out a storm
  on borrowed capacity, not a substitute for a floor.**
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

## Where The Storage CLI Exists, And Where It Does Not

**The storage command-line tool is on the workstation and NOT inside a job
container**, which decides where a data-movement job should run.

A container ships the path-library client and nothing else, so shelling out to
the CLI there does not fail loudly — it **hangs until the timeout with no
output**, in state `RUN`, with nothing in the termination records because
nothing terminated. Two assembly jobs burned half an hour each that way.

The consequence is not merely "handle both backends". Server-side concatenation
and cross-cell copy exist only on the workstation path; in a container the same
operation degrades to carrying every byte through the task — slow enough that a
tens-of-GB copy cannot finish inside a preemption window on the cluster but
finishes comfortably from a workstation (not preemptible, acting only as a
controller). Probe which backend is live at runtime and branch; keep a local
branch too, or the code is untestable off distributed storage — where the last
several bugs in ours survived.

## `state: RUN` Is Not Evidence That Anything Runs

**Check the VM-group states, not the job state.** A job reports `state: "RUN"`
while every one of its groups sits in `ASSIGN`/`PENDING`, and it will sit there
for hours:

```
borg --borg=<cell> findjobs --name_re="<user>_group_<XID>\..*" \
  | grep -oE "VMGROUP_STATE_[A-Z]+"
```

**No `VMGROUP_STATE_RUN` means nothing is running**, whatever the job says.

The scheduling ceiling this exposes is much lower than the advertised quota: on
the shared CPU pool, large fan-outs (order several hundred GiB of total RAM) sat
unscheduled for hours while a job a fraction that size reached RUN in seconds.
Size a fan-out against what actually schedules, and confirm it with the command
above before waiting on it.

Related launcher hygiene, each of which cost a real launch:

- **An XID is not a job.** Confirm at the cluster layer after launching; a
  launcher can print a normal-looking XID for something that never scheduled.
- **Truncate a launcher log before scraping it.** Scraping the last "Launched
  experiment" line picks up a killed earlier attempt's id, so the confirmation
  then checks a job that does not exist.
- **Stop takes the experiment flag**, not a positional or an abbreviated one.
- **A jobs-board entry outlives the experiment.** A queue entry can show
  `PENDING` for 21 hours after the experiment itself reports "not found";
  archive stale entries off the board rather than treating them as live work.
- **A killed launcher tool-call does not stop the launch.** A detached/`setsid`
  submit keeps running after the shell that started it is killed; relaunching
  "because the first one died" then double-submits. Confirm what actually
  launched (the launcher's results file + `tpu check`) before any relaunch.
- **A worker can be alive-but-wedged: board `running`, logs frozen, no
  restart.** Distinct from the unscheduled case above (there the groups never
  reached RUN). Here the task *did* schedule and start, then hung mid-startup —
  the classic form is frozen at `Downloading dataset ...` (staging the ~69G
  Maze mirror to the worker's `/tmp`). The board keeps showing `running` with
  `1 active` WU because the Borg task is alive; the training process inside is
  stuck, so **no new log lines and no `attemptN+1`** (Borg only restarts a task
  that *dies* — a hung-but-alive task never trips the watchdog, so it burns the
  PROD slot indefinitely). Diagnosis: compare the newest log mtime to wall
  clock — a download that normally finishes in ~5 min but shows **>30 min of
  zero log growth across all ranks** is wedged, not slow. Rule out a data
  problem before blaming the worker: if a *sibling* job downloaded the same
  source path fine (check its `step_*` ckpts advancing), the source is good and
  it's these specific workers. Fix: `tpu cancel <xid>` then relaunch the same
  validated config — a fresh launch re-rolls worker placement and usually
  clears it. Always re-verify a relaunched job actually passes download into
  `step>0` — the same bug can re-roll onto another bad node.

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

**Reproduce in the RENAMED stagedir, not in place — the launcher rsyncs only the
CWD into `.../eqr_run_<ts>/` and builds `//<stagedir>:main`, which destroys the
google3 module path the code had at authoring time.** So a hardcoded absolute
import (`from google3.<original.pkg.path> import sibling`) or a cross-package
BUILD `dep`/`data` label points at something ABSENT from the staged binary, and
the worker dies at import time before `main()` — no marker, behind the log wall.
It builds and runs in your workspace only because the original package still
physically exists there, which is exactly what MASKS the bug. The fix is the
EqR-jax `eqr_run_*` idiom: the entry point does
`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` and imports
siblings by BARE name; the sibling `.py` ride along as a BUILD `data` glob
(`strict_deps = False`), carried as relative SYMLINKS to the one source of truth
so two copies cannot drift (`rsync -aL` materializes them as real files). A
package-relative import (`from . import x`) does NOT work — a `py_binary` main
runs as `__main__` with no parent package. **Verify by building
`//<a-renamed-throwaway-dir>:main` with the sibling package ABSENT and running
`--help`**; testing in place proves nothing.

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

**When restricted-LOAS walls off EVERY worker-log service, make the application
write its own diagnostics to CNS.** From a workstation credential, `borg
tasklog`, `analog --remote`, and the F1/`get_job` path can all return
`PERMISSION_DENIED` (and `borg tasklog` itself SIGABRTs on it) — do not keep
retrying them once one fails that way. The reliable substitute is application
diagnostics on the destination filesystem, readable with `fileutil`: a numbered
startup marker written as the FIRST action in `main()`, one marker per stage,
and a `try/except` that dumps the traceback to CNS. This is the concrete form of
`storage.md` §"write a copy's evidence to the destination, not to a log". A
marker written before the first guard also splits the two look-alike deaths
apart: **`VMGROUP_STATE_RUN` then an empty status, zero output, no readable log
is NOT necessarily a pre-`main()` death** — it may be an ordinary failure you
simply cannot see. If the startup marker landed, the process reached `main()`
and the cause is downstream; if no marker exists anywhere, the death is before
logging existed (or an over-quota cell refused the first write — rule that out
per `storage.md`).

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

- **Never pipe content into the submit command, and always redirect stdin from
  `/dev/null` for a backgrounded launch.** Each attribution question is
  satisfied by an EOF, so `< /dev/null` answers all of them, and piping
  something like `yes` segfaults the underlying CLI outright — no XID, no
  diagnostic. **A `nohup`/`setsid` launch WITHOUT `< /dev/null` is the
  dangerous case**: the attribution prompt reads EOF, but instead of exiting the
  CLI can re-loop and SUBMIT AGAIN — one `tpu queue` then yields TWO experiments
  on the same out_dir (two writers = corruption), and the shared `~/.tpu_jobs.json`
  records only one, so the survivor has no registry entry. Always background as
  `tpu queue ... < /dev/null`, and after launch confirm EXACTLY ONE experiment
  with `xmanager.par list | grep <name>` before walking away.
- **Do NOT build a home-grown "anti-dup" wrapper that kills the launcher on the
  `Experiment id: N` line.** That line prints at experiment *creation* — BEFORE
  the blaze build (minutes) and BEFORE any work unit is added. Killing the
  launcher there leaves a RUNNING-forever **zombie**: an experiment shell with
  "No work units found", no log dir, and an out_dir that is never created. The
  ONLY line that means "launch truly finished" is `Launched experiment N` (or,
  for a resume, `Added N work unit(s) to experiment`), printed AFTER the build +
  work-unit add. The wrapper already self-guards against dup retries (it retries
  only when that line is ABSENT), so with `< /dev/null` you do not need any
  kill logic — just let the launcher exit on its own and then confirm exactly
  one experiment. If you must detect completion programmatically, grep for
  `Launched experiment|work unit\(s\) to experiment`, never for `Experiment id:`.
- **ANSI-strip wrapper output before grepping for the XID.** XManager prints the
  XID wrapped in color codes: `Launched experiment \e[1m\e[34m281839914\e[0m
  "name"`. A pattern like `Launched experiment \K\d+` then matches nothing
  (the char after the space is ESC, not a digit) and you get a false "launch
  failed" verdict on a perfectly healthy job. Always pipe through
  `sed 's/\x1b\[[0-9;]*m//g'` first. (Same rule applies to parsing step numbers
  / status out of the log mirror — colored `SUBMITTED`/`Preempted.` have bitten
  watchers before.)
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

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this guide whenever implementation details change.

## Budget Checking

Before launching a job, the launcher automatically invokes `tools/budget_check.py`: the projected GQM credits/hr of this job **plus all active jobs** must not exceed **1/10 of G9 income** (boss directive, tightened from 1/3). Over the bar, the launch is halted. The `npu` aliases run their own separate identical check.

What counts toward the bar, and what is exempt:
- **Active = running, pending, or queued** (option B): a job the scheduler has committed to the XM queue reserves budget even before its Borg gang is RUNNING, so a backlog of pending jobs cannot each look free. The reroute lane (pending >10 min → auto-cancel) bounds how long a pending job holds that reservation. Only terminal zombies are dropped.
- **g3/g5 are exempt**: they draw on their own credit balance, not G9's income, so a g3/g5 job neither counts toward the aggregate nor is refused by it. The router (`tpu route`/`--power`) also *prefers* g3/g5 over g9 for the same reason (`infra/tpu_cli.md`).
- **BATCH and CPU-only are exempt** (free pool / no chips).
- On over-bar the gate prints `[[BUDGET_DEFERRED]]` and exits 3; the local-queue worker reads that marker and parks the job **BUDGET_DEFERRED** (auto-retried when headroom opens), never as a build failure. A running-job enforcer (`tools/budget_enforcer.py`) separately cancels over-cap RUNNING jobs.
