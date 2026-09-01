# Running Jobs On The Cluster

Queue, inspect, resume, and debug a job on the internal XManager/Borg stack.
`storage.md` owns where data and checkpoints live, `tpu_reference.md`
accelerator naming and shapes, `infra/` the market, allocator, and CLI
internals. Read those only when the rules here do not explain what you see.

**Before you submit anything after a large code change, run the CPU
`local_debug` path first** (`engineering.md` §Debug Locally On CPU Before You
Spend A Remote Round Trip). A build plus a queue wait plus a schedule is the
expensive way to find a bug a workstation finds in two minutes.

## The Submission Queue In One Screen

**Submit with `tpu enqueue` (instant, free) plus one serial `tpu build-worker`.**
Builds are always in flight on this shared workstation, so one-shot `tpu queue`
races them on blaze `output_base` (per checkout ROOT, not per copy dir),
silently shipping a zombie XID, 0 work units. Only serial building cures it
(`infra/tpu_cli.md` §The Local-Queue Smart Router).

`cd` into the CODE directory before `tpu enqueue`: CWD becomes the job's
`workdir`, staging the whole tree. From `~/work` it stages your entire home
directory, dying with `produced no XID`, naming compilation for a staging
failure. Check the `packaged from:` line (§The Local Queue: `tpu enqueue` + Serial Build-Worker).

| You want | Do | Details |
|---|---|---|
| One job (default) | `cd <code dir>`, `tpu enqueue …`, `tpu build-worker` up; auto cell | §The Local Queue: `tpu enqueue` + Serial Build-Worker |
| A batch / sweep | `tpu enqueue` per arm; the same worker drains them | §The Local Queue: `tpu enqueue` + Serial Build-Worker |
| Data locality | `--metro=<m>` (e.g. `cbf`); full metros refuse, never roam to no-data cells | §Choosing Where To Run |
| Telling runs apart | `exp_name=` names the TASK, not just the model | §Name The Experiment After Its Job, Not After Its Model |
| Fallback, no worker | `tpu queue …`, synchronous, returns an XID; ONLY when nothing else builds | §Submission Contract |
| PENDING past 10 min | OFF by default: arm the reroute sweep to cancel and re-route | §The Local Queue: `tpu enqueue` + Serial Build-Worker |

Both share one submission contract (same flags, registry) and smart pick:
least-oversold placeable cell. `--cell` is rarely needed, always wins.
`TPU_NO_SMART_CELL=1` opts out (§Choosing Where To Run).

## The Launch Workflow

**Run this every launch; settle placement (steps 2–4) before packaging**:
packaging costs minutes, allocators reject in seconds. Each step names its
section.

0. `cd` into the launched code directory (§The Local Queue: `tpu enqueue` + Serial Build-Worker): CWD becomes the
   entry's `workdir`; the whole tree stages. Use a code subdir
   (`~/work/<repo>/torch_impl`), never `~/work`; check `tpu enqueue`'s
   `packaged from:` line.
1. Prepare the submission (§Submission Contract). Semantics in versioned config;
   on a shared checkout edit a COPY and launch it. `--tier=PROD` trains, `BATCH`
   evals only.
2. Pick the group (§Choosing Where To Run): default g9 for TPU (it holds the
   floor), g8 CPU-only. `tpu quota` names WHICH GROUP holds an accelerator's
   floor, never cells.
3. Cell auto-picked, usually skipped (§Choosing Where To Run). Submit pins the
   most-free non-oversold placeable cell; add `--metro=<m>` if
   data-locality-locked. Probes below only OVERRIDE it or explain rejections:
   - `tpu preflight --tpu_type=<t> --group=<g> --json` → `cells_ok`, per-cell
     obtainable counts, the only cell-level view (`tpu quota` has none).
     Obtainable means "can be got", not "can be held".
   - `stubby call master.<cell>.borg:9413 BorgMaster.ProbeSliceAvailability`
     for free contiguous slices. A cell with thousands of obtainable chips may
     hold one placeable slice (shape uses UNDERSCORES;
     `research/v7_storage_placement.md`).
   - Intersect: a cell with your floor and data (§Choosing Where To Run;
     `storage.md`). The same obtainable number is idle-guaranteed in one
     (group,cell), borrowed-reclaimable in another.
4. Preflight, then verify the snapshot (§Choosing Where To Run, §Submission
   Contract). Green is necessary, not sufficient; CPU-only jobs use
   `--skip-preflight`. `diff` packaged config against intent.
5. Submit, then confirm it is REAL (§`state: RUN` Is Not Evidence That Anything Runs). An XID is not a job,
   `state: RUN` not evidence: check `VMGROUP_STATE_RUN` at the cluster layer
   before waiting.
6. If PENDING, read the work unit's verdict (§When A Pending Job Should Move);
   do NOT resubmit or wait reflexively. It, not the obtainable table, says: move
   cell, move group, or stay queued.

## Submission Contract

- **Submit through the wrapper**:
  `source ~/work/tpu_cmd/tpu_wrapper.sh && tpu enqueue ...` (default; a
  `tpu build-worker` drains it serially, §The Local Queue: `tpu enqueue` + Serial Build-Worker). Never call
  `xm launch` / `xmanager launch` directly; only the wrapper may, internally.
  `tpu` is a shell FUNCTION, not a binary on `PATH`, so a SCRIPT wrapping it
  (e.g. one sourcing a guard helper) must itself
  `source ~/work/tpu_cmd/tpu_wrapper.sh` in the SAME shell. Else
  `tpu: command not found`: instant guard "DEAD", ~6 s, no stagedir.
- One shared launcher. `~/work/tpu_cmd/xm_launcher.py` owns packaging, staging,
  and job registration. Projects contribute versioned config, not launchers.
- Semantics go in versioned config: model, data, training behavior. Only routing
  and transient selectors go on the command line.
- Edit the run config in place; pass no `--config`. Invocation strings are not
  durable, and named configs grow one file per finished experiment. Nothing is
  lost: snapshots are immutable and a helper restores a past run's exact config
  (`infra/tpu_cli.md`). The default is `remote_run`, so write the run into
  `remote_run_config.yml`. Name a mode BARE (`--config=trm_sudoku`), never a
  path or filename: the launcher wraps it into `configs/<mode>_config.yml`, so
  `--config=configs/x_config.yml` becomes
  `configs/configs/x_config.yml_config.yml`, dying at startup with "Could not
  locate …". The launcher now normalizes the value and, on resume, refuses a
  missing config before packaging. Still pass the bare mode: a resume skipping
  this check shipped this bug.
- On a shared checkout, edit the config in a COPY and launch from that. "In
  place" means the file the launcher reads, not the worktree. Every launch
  overwrites it: two agents launching minutes apart package each other's
  experiment. Copy the checkout, write the config there, launch, delete the
  copy; packaging rsyncs into a fresh snapshot regardless, reading neither VCS
  state nor the launch directory. Code changes are the exception: commit them in
  the shared checkout, since a deleted copy takes its provenance with it.
- Confirm before launching: checkout, branch, dirty state, effective config,
  allocator, target. Use real attribution, never a placeholder to silence a
  prompt.
- Verify the SNAPSHOT, not the file you edited: one `diff` of the packaged
  config against what you meant covers the copy, the overwrite, and staging.
- Cells are auto-selected (§Choosing Where To Run). Override with `--cell`,
  constrain the pick to a data-co-located metro with `--metro=<m>`, or opt out
  with `TPU_NO_SMART_CELL=1`. No command changes.
- Packaging freezes the code: the wrapper snapshots it, so later edits cannot
  affect a queued or running job.
- Verify registration after submit; never assume the transaction completed.
- Default to `tpu enqueue` plus one serial `tpu build-worker`, for one job as
  much as a batch: `tpu build-worker start` once, then `tpu enqueue` each run
  from its own checkout, watching `tpu queue-status`. On this shared
  workstation, a one-shot `tpu queue` races in-flight builds on the blaze
  `output_base` and ships a 0-work-unit zombie XID. Only the serial worker,
  building one at a time, avoids that. Mechanism, cured failure modes, and
  guards: `infra/tpu_cli.md` §The Local-Queue Smart Router. `tpu queue`
  (one-shot, synchronous) is the fallback when you KNOW no other build is in
  flight.

## Name The Experiment After Its Job, Not After Its Model

**`exp_name=` must say what that launch was FOR, not merely which model it
trained.** It is the only human-readable handle a run carries into
`xmanager list`, the flatboard link, and its CNS log directory. Launch a probe,
a training run, and a resume in one night under the same model name, and next
morning the three XIDs are indistinguishable. The dashboards show three
identical rows, and picking the wrong one fails silently, because each is a real
run of the right model.

Name the task and the state that distinguishes this launch:

```
parcae-140m-torch                     the model — not enough
parcae-140m-torch-sanity              the 8-GPU CUDA/NCCL probe
parcae-140m-torch-repro-resume9216    the reproduction, resuming from step 9216
```

The CNS log directory embeds it (`xid_<XID>_<ts>_<exp_name>/`), so a good name
also makes `fileutil ls` self-describing months later, when the XID no longer
means anything to anyone.

## Requirements And Runtime

- **Every TRAINING job must pass `--tier=PROD` explicitly; `BATCH` is for
  eval-only jobs.** BATCH is best-effort, preempted the instant PROD demand
  contests a slot. PROD is already the launcher default for every group (g5
  injects it, others inherit XManager's `_DEFAULT_SERVICE_TIER=PROD`), so
  `--tier=PROD` is for the audit trail, not behavior. `tpu check`'s TIER column
  echoes the REQUESTED string from the local registry, not Borg truth: `-` means
  "untagged, ran the PROD default", not "non-PROD". Read the work
  unit/allocator for ground truth. Run evals only on BATCH. GPU nuance: most
  have a free (0.00) BATCH pool and cheap PROD, so a short smoke there is fine,
  but BATCH still preempts (`guarantee reclaim`). Use `--tier=PROD` once a GPU
  run must finish. `gpu_on_borg.md` §Rule 6 — Tiers owns this.
- Priority <= 25 charges the person, above it the group. Free tiers spare the
  team's GCU allocation. `BATCH` reads cheap but is the opposite: a paying
  best-effort tier billing the group.
- Set the tier with `--tier`, never the dead `--priority` wrapper flag (parsed,
  never read). Prefer named tiers. A raw numeric `--tier=N` changes who pays
  (`<= 25` bills you personally) and shrinks the per-cell task cap. Bigger
  numbers win no contention: the quota floor/market sets schedulability, not the
  number (`infra/quota_market.md`).
- Keep CPU-only batch out of accelerator groups. In GQM, CPU and RAM are
  ancillary to accelerator usage, so a job asking for neither always schedules
  last. This is structural and waiting never fixes it: a priority-0 probe sat in
  `starting` for 14 hours. Use the shared best-effort CPU pool
  (`go/gdm-cpu-only-jobs`, `--group=8` in our launcher): pre-authorized (own
  LDAP, no request, no approval), bills nothing. Its per-user ceiling (order
  1000 GCU, 1 TiB RAM) makes two 900-task jobs evict each other; run serially.
- That pool can sit empty for days, stranding CPU-only jobs. When dry, ride the
  team's PROD accelerator alloc: a CPU-only controller costs that group almost
  nothing yet schedules immediately where the pool has zero. Archetype: a
  server-side data copy, a few cores driving storage-layer copies
  (`§Where The Storage CLI Exists, And Where It Does Not`). Use the same `(group, PROD)` as your long
  jobs, pin a cell in the data's metro, add `--skip-preflight` (CPU-only cannot
  be preflighted), confirm `VMGROUP_STATE_RUN`. That covers genuinely-free
  best-effort batch, not a ban on PROD for CPU-only. Diagnose from your own
  fleet: two submits differing ONLY in group, the pool unscheduled a day, the
  PROD alloc at RUN in ~1 minute.
- Container-style packaging needs the pool to have a mapped cloud project;
  native allocators without one need Bazel packaging.
- In JAX jobs, parse flags before distributed initialization, never at module
  import time. `projects/eqr_jax.md` has the google3-specific startup order,
  stricter than the public contract.

## Choosing Where To Run

Packaging costs minutes, an allocator rejects in seconds: settle placement
first. Decisions here, mechanism in `infra/`.

- **The cell is now chosen for you by default, so you rarely pass `--cell`.**
  Each submit pins whichever cell can place the slice RIGHT NOW (most free
  chips, not oversold), printing `Smart cell: pinned --cell=…`. Otherwise jobs
  pile onto oversold cells while chips idle: 13 v7-32 on `yulpptr`, `yukulwh`
  holding 101 free slices. `--cell` wins, `--power` picks for itself, a comma
  `--tpu_type` list and `TPU_NO_SMART_CELL=1` skip it, and no candidate defers
  silently to the allocator. It never blocks. The group below outranks the
  cell.
  - A data-locality-locked run passes `--metro`, not a hand-pinned `--cell`.
    Ranking only free chips and oversold, it can strand a run a metro from its
    bucket: 4-5x throughput, then a pruner kill (storage rule). Locality is
    METRO-level: one metro, one storage cell (cbf's `yucbfiv`, `yucbful`,
    `yucbfwv`, `yucbfsl`, `je` all read `/cns/is-d`). `--metro=<m>` (e.g.
    `--metro=cbf`) takes that metro's least-oversold cell, `--metros=a,b`
    several. A router selector never reaching the launcher, `--metro` beats a
    `--cell` pin. Roam metros only with no storage need.
    - `--metro` fails CLOSED. A full metro refuses rather than roaming
      out-of-metro to a no-data cell whose dataloader crashes. That drift put
      3 arms on `yuskedq`. Wait, or pin `--cell=<in-metro cell>` and
      stage-and-queue. Only a NO-data run overrides: `--force` /
      `TPU_METRO_FALLBACK=1`.
- Pick the group holding your floor (last bullet): idle guarantee versus
  borrowed and reclaimable.

  | Group | Alloc (short) | Use for |
  |---|---|---|
  | 9 | `fr-dna-grand-challenge-team-resource` | TPU training default: nearly all our real v6p/v7/v4 floor, plus stable jobs. |
  | 8 | `brain-vasp-shared-user-xm` | CPU-only, `--skip-preflight`. No TPU floor, `tpu quota` empty: size fan-outs by what schedules (§`state: RUN` Is Not Evidence That Anything Runs), not quota. |
  | 5 | `vqfree-xm` | Free pool, auto-injects PROD (§Requirements And Runtime). |
  | 1, 7 | `*-resources-prod-shared` | Shared prod, thin-to-zero floors. Contended-g9 fallback, not a default. |
  | 2, 3, 4 | `*viscam*` / `*interns*` | viscam/intern allocations. |

  Full strings: `~/work/tpu_cmd/tpu_wrapper.sh::get_alloc_by_group_id`, the
  single source of truth. g9 is only a start: fall back once its accelerator
  floor is spent, or your data's metro has none.
- Convert power classes first: a chip count is not a size (`tpu_reference.md`).
  `tpu route --power=` turns one into an allocation, type, and cell.
- Preflight before packaging: fifteen seconds, catching illegal topology,
  minimum-slice rules, no platform capacity, thin headroom (layers in
  `infra/tpu_cli.md`). Red submits are refused absent an override.
- Preflight cannot verdict a CPU-only job (`Unknown accelerator arch 'cpu'`),
  modeling TPU allocations only. Submit those with `--skip-preflight`: a
  no-opinion check skipped, not a warning overruled.
- A green verdict is necessary, not sufficient. It misses topology
  fragmentation: non-contiguous free chips let the allocator accept, then
  reject seconds later (the daemon auto-retries that one rejection). Market
  outcomes, transient attribution rejects and prompts are invisible too. Ask
  for several candidates, preferring proven ones.
- `tpu quota` names which group holds a floor: Quota/Used/Available/Obtainable
  per GROUP, no cell column, no schedulability. Quota is a guaranteed floor, a
  contract not a ceiling. Available = Quota−Used reads ~0 almost always (next
  bullet), and only Obtainable is live, group-aggregated. Read `tpu quota` per
  GROUP with your accelerator's floor, never per cell or as go/no-go: launches
  turn on `tpu preflight --json`'s per-CELL obtainable.
- A fully-consumed floor is the steady state, not a blocker.
  `used == quota, available 0` is normal for these allocs, the job queues and
  runs, preflight's YELLOW informational. Starts turn on `tpu preflight --json`,
  then the work unit's `GQM_RESOURCE_DEFICIT_INFO`. Obtainable is volatile and
  storage-blind: the largest co-located quota can read zero while middling
  cells finish. Re-check before launch, on both axes.
- `tpu route` and the market summary only SAMPLE cells, roughly one per
  accelerator, never the complete list. `tpu route --power=v6p-64` once put v6p
  solely in `yuphxrp`, phx with no team storage, while preflight's `cells_ok`
  listed nine cells, two co-located with our data: nearly a lost locality. Take
  full `cells_ok` from `tpu preflight --json` or the market cache
  (`infra/quota_market.md`), intersected with storage (`storage.md`).
- Prefer cells whose metro holds storage you can write. The scheduler ranks
  capacity and price, not data, so the freest cell often lacks team storage.
  Writes then hit the personal per-cell ceiling (`storage.md` owns placement
  and why distance kills a run). Preference, not ban: a storage-less cell is
  real capacity while something sweeps the quota. A multi-cell allow-list reads
  only in spatially-flexible mode, so set both; a pin bypasses both.
- A PROD floor is per (group, accelerator, cell); a tier alone guarantees
  nothing. A RoboTwin DP smoke took FIVE launches. `BATCH v6e-8` was preempted
  4x by higher-priority prod during the ~3-min cold-import. `PROD v6e-16` in
  `yucbfrl` was guarantee-reclaimed twice, group 1 having a ZERO v6e floor
  there. The thousands `preflight` calls obtainable are borrowed capacity a
  guarantee holder reclaims mid-compile, not a floor. `PROD v7-16 yutulpz` hit
  "cell oversold". Only `v7-16`, group 9, in `yulpptr`/`yutulpz` stuck, where
  STABLE jobs already run beside the data mirrors. Launch where long jobs
  survive, not where preflight calls chips obtainable.

## When A Pending Job Should Move

A fresh submit picks a placeable cell, avoiding the oversold one (§Choosing
Where To Run); this covers PENDING after placement, or an explicit `--cell`.

**Queued is not failed, and PENDING for hours can be normal** on an oversold
pool. Do not resubmit reflexively: each stacks another work unit contending the
same slice. Act on the live unit's verdict: `deep_probe`/`why_probe`, or its
`GQM_RESOURCE_DEFICIT_INFO`. The obtainable table cannot tell these apart.

| Verdict | Means | Move? |
|---|---|---|
| `GQM_OVERSOLD_MARKET` "in cell X…" | that cell is oversold | Yes; it names the cell, another may take it |
| `GQM_RESOURCE_DEFICIT_INFO`, deficit N (names a cell) | short N chips there | Yes; pick a smaller/zero deficit |
| `resource-guarantee-reclaim` | a floor holder reclaimed your borrowed capacity | Yes: to a (group,cell) where you hold a floor, not borrowed chips |
| `dynamic root pool … capped by adjusted ceiling` (deficit names no cell; g1/g5/g9 identical) | pool-wide limit | No; change tier or accelerator generation, or wait for the price to fall |

Rule out two non-capacity causes first; moving cell fixes neither:

- A price cap (limit order) triggered. Over the cap, the queue drops the job
  before any capacity check, so free chips do not help. The cap is pool-wide,
  often a teammate's group-wide one applying to you silently. Check
  `tools/limit_order.sh status` for `BLOCKING` first (`infra/quota_market.md`).
- It never reached the scheduler. An XID with no work unit, or no XID, is a
  launcher-side failure, not a queue: a local problem (§Launcher-Side Failures That Look Like Scheduler Failures).

When the verdict is ambiguous, probe: a short submit of the real workload
answers "can I get this slice here" at 100%, where the capacity table was ~12%
accurate against the live queue (`research/accelerator_choice.md`).

## Verify The Scheduler Exists Before You Rely On It

**`tpu` answering "not built" usually means the PATH to its binaries moved, not
that anything is missing; three faults share the symptom.** Blaze names an
output_base after `md5(workspace_directory)`, or the `<md5>_buildrabbit` sibling
root when `$BUILD_EXECROOT` is set. Two environments on one checkout own two
roots; the last to build repoints `blaze-out`/`blaze-bin`, hiding
`route_check` / `queue_cli` / `jobd`, binaries intact in the other root. It
self-heals when the symlink swings back, reading as random drift (six
occurrences in one shift, 2026-08-30).

| Symptom | Cause | Do |
|---|---|---|
| `rc=127 command not found` | `tpu` off `PATH`; `~/.bashrc` sources `~/work/tpu_cmd/tpu_wrapper.sh` | `source ~/work/tpu_cmd/tpu_wrapper.sh` |
| `rc=1 "not built"`, worker still submitting | symlink flipped to a root lacking them | nothing; the resolver searches real roots, else rebuild |
| `rc=1 "not built"`, nothing ever built | genuinely absent | rebuild serially, never during another build |

Fallbacks all beginning `$G3/blaze-out/...` are one path: `blaze-out` is the
rewritten symlink, so all miss together. The wrapper enumerates real output
roots (`$BUILD_EXECROOT`, the `md5(workspace)` root, its `_buildrabbit` sibling,
the symlink last as a hint). It takes the newest that exists, failing closed.
Fallbacks sharing a mutable component are not redundant.

A long-lived worker keeps executing its original inode: a busy `ps` line is no
evidence binaries are reachable, nor "not built" that it died. Run the tool, do
not inspect it.

```bash
tpu queue-status          # prints the queue => the scheduler is really there
```
Rebuild when it says "not built", serially:
```bash
cd /google/src/cloud/qiaos/run_amply_workspace/google3 && \
  blaze build experimental/users/qiaos/tpu_utils:{route_check,queue_cli,jobd}
```
`blaze` printing `Target up-to-date` does not prove the build produced anything;
only a fresh mtime does. Nor the converse: a `py_binary` product is an ELF
launcher whose SOURCE lives in `<target>.runfiles/`, so grepping it finds nothing
even on a correct build.

For a LONG-RUNNING process, "it is in the runfiles" is a false green: those
entries symlink at the workspace source, so an edit refreshes the file while a
daemon started hours ago runs old code from memory. Running it tests a new
process, not the daemon. The discriminator is start time versus source mtime
(`ps -eo pid,lstart` against `stat -c %y`): an older process means the fix is
not live. Restart and re-check the same way (`engineering.md`
§External Writes Are Transactions, "Never kill by pattern").

## The Local Queue: `tpu enqueue` + Serial Build-Worker

**`tpu enqueue` plus a serial `tpu build-worker` is the DEFAULT submission path**
(§Submission Contract), single job or batch. Only it dodges the concurrent-build
`output_base` race and its 0-work-unit zombie XID (`infra/tpu_cli.md`). An
`enqueue` is free and instant; PENDING does not bill. It also:

- drains a batch or sweep as capacity frees, no babysitting N submits;
- re-routes anything PENDING after placement (the 10-minute sweep, below);
- handles a mixed batch across checkouts, each keeping its dir.

Two queues. The router drains a durable, unlimited local list of desired runs
into the XM queue, one placement at a time. It places onto free chips now, not
the obtainable table, and never onto an oversold or full cell. `tpu queue`
takes one job to ONE cell.

`phx` and `ske` are refused at `tpu enqueue`; do not route around it. Unregistered
for CNS storage, they bill the PERSONAL 500 GiB quota (~468G used, handle
poisoned), fail `resource_exhausted`, and still leave a 0-byte file, so the job
looks productive. An unknown metro only `SystemExit`s into an inert
zero-work-unit shell. Three unbypassable gates refuse at zero credits:
`queue_cli`, `jobchain.validate_enqueue` (v2 store),
`xm_launcher._local_bucket`. Escape hatch: explicit group-billed `--bucket`.
Group-storage metros: `cbf ckv cmh dfw grq las lpp mrn sin tul`.

`tpu queue` is deprecated (soft): it warns on stderr and points here. It stays
for two reasons. `enqueue` only PARKS a job for a serial `build-worker`, so
`tpu queue` is the only synchronous path when that worker is down. And
`enqueue`'s own `--launch` args pass verbatim to `tpu queue` at submit.

Never enqueue with `priority` > 0 without the operator's explicit permission.
The queue drains highest-priority-first (`tpu enqueue --priority=N`; the router
sorts by `-priority`). All lines share it, so one setting `--priority=5` or `6`
parks every `priority=0` job for a shift. The default is `priority=0`; only the
operator may authorize a `priority>0`. It IS honored, unlike the dead
`tpu queue --priority` flag, parsed but never read.

| Command | Does |
|---|---|
| `tpu enqueue --power=v7-32 --archs=v7,v6p --launch=config=...` | Add a run. `--power` and `--archs` are REQUIRED together: `--power` the target, `--archs` the generations satisfying it, whichever has capacity (`--power_tolerance`, default 0.5, accepts 0.75x-1.25x: the code computes `target * (1 +/- tol/2)`, though the flag's own help text and a code comment both say 1.5x). Not `tpu queue`, where `--power` and `--tpu_type` are exclusive. `--launch=k=v,flag` goes verbatim to `tpu queue` at submit; undeclared keys are REFUSED, so forward binary flags as `--launch=app.<flag>=<v>`. |
| `tpu queue-status` (alias `tpu qs`) | Local queue plus, live, why each job waits or where it is placeable. Run before trusting the scheduler: §Verify The Scheduler Exists Before You Rely On It. |
| `tpu dequeue <job_id>` | Remove one before it is submitted. |
| `tpu requeue [job_id...]` | Return HELD job(s) to QUEUED after you fix the cause (empty = all held). |
| `tpu build-worker start` \| `stop` \| `status` | SERIAL build-worker, own tmux session: claims one QUEUED job as BUILDING, builds it, records the XID, repeats. One build in flight, the safe way to drain a batch. |
| `tpu route-tick` | One router pass by hand (no daemon/worker): plan (dry-run), then submit placeable jobs with `--nodry_run`. `--reroute --nodry_run` cancels and re-queues jobs PENDING past 10 min. |

A job moves QUEUED → BUILDING (the one live build) → SUBMITTED → RUNNING, shown
by `tpu queue-status` and `tpu check`. A no-XID build (a `found[]` zombie) is
requeued, not dangling; a crashed worker's stale BUILDING claim expires after
`--build_stale_s`.

**A worker killed mid-build costs 30 minutes, not one build, so anything that
kills workers on a timer must reclaim what it killed.** `--build_stale_s`
defaults to 1800 s: the row stays BUILDING under a dead worker, and the
dispatch worker's backpressure gate (`N BUILD_REQUESTED/BUILDING still
draining; no new dispatch this round`) then refuses to start ANY other job
until it expires, so one killed build parks the whole queue. Measured
2026-09-01 on lyy's two-arm race: 70 minutes, both arms killed and parked in
turn, zero XIDs. The killer was the operator's own
`lyy-work/vlm/g3/watch/lock_yield.sh`, which pauses the npu dispatch worker
whenever a non-npu process has waited `THRESH=600 s` on
`/tmp/tpu_build.host.lock` — `tmux kill-session` plus SIGTERM to every
`route_check` matching the queue file, then `PAUSE=420 s`, then restart. Its
cycle (~8-9 min under contention) is SHORTER than a real build, so every firing
converted an in-flight build into a 30-minute park; the only trace afterwards is
`reclaimed: BUILDING claim went stale (>1800s)` in `last_reason`.

Three properties any such pauser needs. It must reset the BUILDING rows owned by
the worker it just killed back to QUEUED — safe precisely because no worker
exists during the pause, so this is the one moment a second writer cannot race
the drainer. It must not judge by a waiter's AGE alone: a waiter wedged in
FUSE-D never finishes, its `etimes` grows without bound, and the pause becomes
permanent (observed climbing 681 → 1209 → 1731 s across three firings). And it
must check WHO holds the lock before yielding: killing the dispatch worker does
nothing when the holder is a different process of the same operator (a
synchronous `tpu queue` launch), which is how one lyy launch made lyy pause
lyy's own queue for an hour while the lock never moved.

A `found[]` / no-XID verdict is a symptom, and the two cheapest causes are not
in your code. Read `last_reason`, then elapsed time: far LESS than a real build
means blaze was never reached (134 s against a 236 s honest build), so staging
or a gate is at fault. Two do:

- The stagedir completeness check verifies the entry source in the BUILD
  target's `srcs`, NOT always `main.py` (one package's is `main_eqr.py`). It
  refuses before the launcher's log, leaves the run directory empty, and prints
  `[[STAGE_INCOMPLETE]]` naming the missing artifact.
- A budget refusal parks `BUDGET_DEFERRED`, `attempts` untouched by design: a
  fleet-wide transient, not a per-job defect, never counting toward HELD.

A `[[MARKER]]` in the reason is the machine-readable verdict; trust it over the
prose around it. `[[STAGE_SRC_REFUSED]]`, `[[STAGE_RSYNC_TIMEOUT]]`,
`[[STAGE_RM_REFUSED]]`, `[[STAGE_INCOMPLETE]]`, `[[BUDGET_DEFERRED]]`.

`waiting: <something>` is not always capacity; read the clause after the colon.
An availability-fetch failure parks a job in QUEUED with `attempts` unchanged:
never escalating to HELD, never billing, looking queued behind demand.
`tpu route-tick` prints the live availability count; entries mean capacity is
fine.

`last_reason` is a snapshot, not a heartbeat, rewritten only on change. Text
unchanged over N minutes proves the STATE has not changed, not that the failure
continues. Re-derive with a probe.

HELD is the anti-churn park: what an unattended worker can never build waits for
a human. Two cases park: a `--workdir` that does not exist (at once, since the
wrong source would ship), and failing an XID `--max_build_attempts` times
(default 3). That catches stale or duplicate enqueues (already on Borg) and
empty-workdir batches from the wrong directory. Fix it, usually a fresh
`tpu enqueue` from the right checkout to capture `workdir`; then `tpu requeue`
and `tpu queue-status`.

A parked row records a workdir PATH, not a commit, so it is not the job it was
enqueued as and `tpu requeue` is the wrong verb. Packaging rsyncs that directory
at build time, so a row parked for hours fires against a moved-on checkout and
reproduces nothing while looking faithful. Prefer a fresh `tpu enqueue` from the
intended tree, requeuing only if `workdir` has not moved (`--priority` is not
yours to raise); retire an obsolete one-off.

Ask the owning line before parking or releasing its row; read the hold text as
a claim, not evidence. `workdir` names the owner, the fleet roster the session,
and an owner answers "still needed?" in one message, regularly no (a renamed
family, a superseded generation). If that line is dead, the row's history
decides. Never quote a `HELD:` reason as fact: watchers copy hold texts between
rows, so one may describe a neighbor's kwargs.

A checkpoint-sharded resume must pass `--topology_locked`; the router then moves
it only within the SAME mesh geometry. `v6p-32` and `v7-32` are both `2x4x4` and
interchangeable, `v6e-32` (`4_8`) is not, so a locked job never lands there.
Omit it only for a run that can retrain from scratch. A chip count is not a size
(top-level rule): give `--power` an explicit `arch-chips`.

`cd` into the code directory before `tpu enqueue`: step one of submitting
anything, not a refinement. `tpu enqueue` captures the CWD as the entry's
`workdir` and rsyncs that whole tree into the stagedir, so point it at a code
subdirectory (`~/work/<repo>/torch_impl`), never `~/work`.

Enqueuing from `~/work` does not ship wrong code; it produces no job at all,
reported as a crashed build. The packager recurses the home tree
(`AGENT_STATUS.md`, `agent-web`, `.monitor_watch` backups, every sibling
checkout) and times out or dies, so the run surfaces as
`build produced no XID (found[]/crash?); retry N/3`: compilation, not staging.
Each attempt leaves a stagedir behind (278 had accumulated).

Tell it from an ordinary failed build by the SHAPE of the failure, not by a
success rate. `found[]` also happens from a correct directory and usually
succeeds on retry; the wrong-workdir version fails deterministically, every
attempt at the same point, and its stagedir mirrors your home directory instead
of a checkout. Read what was staged: that separates the two before the third
attempt burns. Across 46 codi queue entries, 41 carried an XID and 5 did not,
and the 5 are not one population: two were enqueued from `~/work` and burned all
three attempts, two were retryable `found[]` from a correct
subdirectory, and one was an administrative HELD that never built.

Reading that field is not checking it: "differences all ride on explicit flags"
answers whether the right source ships, not whether the packager finishes. One
line reported `workdir=/…/work` half an hour before its builds failed, cleared
on exactly those grounds. The hazard is tree size, not contents.

Verify with the `packaged from:` line `tpu enqueue` prints, every time: it
echoes the captured directory, so a wrong tree shows one line after you submit,
not three failed builds later. `tpu queue-status` and `tpu route-tick` print it
too; `--workdir=<dir>` sets it explicitly.

The router submits from that captured `workdir`, while `tpu queue` rsyncs the
CURRENT directory. So enqueue FROM the checkout holding the run's config or
edits (a per-arm snapshot dir, an edit not via `--config`), or it ships the
wrong source. `tpu queue-status` and `tpu route-tick` show the packaging dir
before it submits; `tpu enqueue --workdir=<dir>` overrides. Only a run whose
differences ride entirely on explicit flags is safe to enqueue anywhere.

Enqueuing alone submits nothing: a running `tpu build-worker` drains and submits
it, one build at a time. The separate AUTO-reroute sweep (cancel and requeue a
job stuck PENDING past 10 min) is off by default; run
`tpu route-tick --reroute --nodry_run`, or arm the daemon's router lane with
`TPU_ROUTE_ENABLED=1` (unset). Neither submits into an oversold/full cell, nor
cancels a job whose status it cannot read. Internals: `infra/tpu_cli.md`.

## The `LOAD_FROM` Contract

**A scheduler tells a job where to resume by setting the env var `LOAD_FROM` to
the checkpoint path, VERBATIM: never a config key, never a "fixed up" path.**
Every launcher, requeue path and resume tool follows it.

Consumers read `LOAD_FROM`; the config key differs per project (EqR-jax
`load_from`, codi/coconut `load_model_path`). Writing the key works on most
lines and silently cold-starts the rest. The failure is partial: a smoke test
on any EqR-jax line certifies the bug.

Never parse, normalize, or complete the path: four incompatible shapes coexist
and every "helpful" transformation breaks one.

| Family | Shape | Note |
|---|---|---|
| EqR-jax (maze, trm-arc1, hrm-trm) | `step_<N>/` | the job appends `/state` |
| codi, coconut | `step_<N>/` | flat, no `/state` subdirectory |
| paligemma, jax_llava | `checkpoint_<N>` | flax file |
| torch ports | `step_<N>.pt` | a single FILE, not a directory |

Replay the job's reported string (its `latest_checkpoint()`) unchanged.
`LOAD_FROM` names the leaf; a bucket root or `checkpoints/` parent raises
`FileNotFoundError` after a reassuring metadata warning.

Clear `LOAD_FROM` once the job writes its first checkpoint, or set it on first
dispatch only. It wins unconditionally and disables auto-resume, so a pinned
`LOAD_FROM` reloads one old checkpoint at every preemption: a run at step 380k
restarted from 298k, reading as instability, not an infra fault.

`LOAD_FROM` has one working delivery channel,
`tpu enqueue --launch="...,load_from=<path>"`. Two plausible routes fail
asymmetrically:

| What you type | What happens |
|---|---|
| `LOAD_FROM=<path> tpu enqueue ...` | Silently dropped: the job cold-starts from step 0, trains happily, reports SUCCESS. `LOAD_FROM` arrives only as a launcher flag (`xm_launcher.py`, `--load_from` → `job_env_vars`), never by shell inheritance. |
| `tpu enqueue --load_from=<path>` | Loud `FATAL Flags parsing error: Unknown command line flag 'load_from'`: the wrapper's passthrough allows it, the binary does not declare it. Cheap: it refuses. |
| `tpu enqueue --launch="...,load_from=<path>"` | Works: `--launch` k=v pairs go verbatim to `tpu queue` at submit. |

Row one is the standard silent failure: a cold start looks healthy for an hour.
Confirm from the job's own log, `resumed from <path> at step <N>`, with the N
you expected. Its watcher treats `cold start` and a low step as FAILURE, not
only crashes.

`CHECKPOINT_BUCKET` is separate, never repointed on resume: it says where the
job writes, `LOAD_FROM` where it reads. Torch ports take their working
directory from it, so moving it restarts them from scratch. `CHECKPOINT_BUCKET`
is also the launcher's ONLY write-location statement: it never forwards
`--bucket`, and exports `<root>/logs/<project>/<folder>`, not the root passed.
A binary reading `--bucket` gets its Borg default (empty, in a careful
implementation), so records degrade to stderr, unreadable behind the LOAS wall.
Hence the costliest symptom: `state=SUCCESS`, zero bytes written, the run
genuinely happened (peak RSS showed torch loaded at 9.7 GB) and left nothing.
Resolve as `--bucket` or `$CHECKPOINT_BUCKET`, in that order, so an explicit
flag stays authoritative as in the launcher, and log which won. Suffix trap:
`--bucket=/cns/X/eqr_data` writes under
`/cns/X/eqr_data/logs/<project>/<folder>`: its root looks empty and reads as
failure. Never read through `CHECKPOINT_BUCKET`; that is `LOAD_FROM`'s job
(§The `LOAD_FROM` Contract).

Read remote if you must; write local always. A cross-metro restore read is
survivable: 6.0 GiB across the Atlantic at ~14 s. A write across one is not:
throughput falls ~6x same-continent, ~94x cross-continent. Blocking saves push
duty cycle under the 0.20 floor and the WIM pruner deletes the job, with no
preemption notice and no crash. Copy the checkpoint to the compute cell's CNS
prefix first (swap the prefix, keep the tail verbatim) and point `LOAD_FROM`
there.

A job that cannot find its `LOAD_FROM` must fail closed: cold-starting looks
like a successful launch, burns the run, and shows only in the loss curve.

## Preemption, Restart, And Resume

- **A restart restores nothing.** The binary re-executes from the top on a fresh
  machine, same arguments. No process state, memory image, accelerator snapshot
  or execution position survives, only application checkpoints.
- Without a restart budget the first preemption is fatal. Set an explicit
  scheduling policy: unlimited task failures, one per task per credit window.
  Long runs then survive unrelated preemptions, and a repeat offender is declared
  dead, not retried forever.
- In a preemption STORM (thin/borrowed capacity, no floor) the default
  `borg_max_per_task_failures=1` kills a job merely holding ground. It is not a
  never-restart setting. `xm_launcher.py` defaults: `borg_max_task_failures=-1`
  and `borg_max_task_evictions=-1`, both unlimited, plus
  `borg_max_per_task_failures=1` on a 7200s credit window. A clean preemption is
  an eviction, harmless against an unlimited budget. A torn-apart gang leaves
  survivors exiting non-zero, a per-task failure. With no floor, repeated ABORTs
  burn each task's one credit inside one 7200s window and the job flips to FAILED
  (`task_states=[ABORT×N, FAILURE×k]`, WU=FAILED). On 2026-08-21 four PaliGemma
  v4-256 arms on `oe` (no v4 floor) died this way repeatedly. Ride out a storm on
  `tpu queue ... --borg_max_per_task_failures=100`, evictions unlimited: ABORTs
  re-queue instead of failing the job. Waiting is never fatal: a never-scheduled
  job is NEVER failed for it, and the board routinely shows others pending 2d+.
  Only schedule-then-abort on an exhausted budget dies. A real floor beats this
  knob, a borrowed-capacity stopgap (see the survival test above).
- Keep checkpoints out of the working directory: task-local, wiped by the event
  the budget exists to survive. Without them the budget buys only a step-zero
  rerun.
- A task walking a fixed list never revisits a passed index. Preempt the tail and
  the job stays `running`: slot held, healthy, nothing emitted. Gate on finished
  units, not liveness. Act on a stalled count. Two corpora each stopped a handful
  of units short, so finish tails by other means.
- Size a work unit against the preemption window, not convenience. A unit longer
  than the mean uninterrupted window never completes and fails silently: every
  task busy, nothing emitted, no error. A ~6-minute window against a 195-minute
  shard never finishes and looks healthy. Re-slicing to minutes is free when work
  is a pure function of its index.
- Two launcher settings. Open log-read access, sparing an ACL dance. No
  interconnect-resilient slice for accelerator jobs: resilience costs roughly a
  third of throughput, and rescheduling onto a healthy slice beats finishing much
  slower.
- A restart loop proves neither a crash nor slowness. A training loop producing
  zero steps exits 0 and restarts forever, logging only successes. Use the
  kill-versus-exit tests in `engineering.md` before blaming infrastructure.
  Verify a resume by step progress, never exit status.

Resuming is not pointing at a checkpoint. The resume flag appends a work unit to
an existing experiment. The prefix comes from the experiment id, so the attempt
lands there and auto-resume picks the newest complete checkpoint. The launcher
must not also pass an explicit load path. Auto-resume yields to explicit
requests, and only the job knows which step finished writing. A guess disables it
with an unusable path. Reserve explicit paths for external checkpoints, at a
concrete step directory.

A resume re-runs the ORIGINAL snapshot, immutable and prebuilt, never the current
checkout, which drifts within days. Package the working tree and the checkpoint
resumes into code it never saw. The newer validator refuses retired config keys,
killing the run's own config at flag-parse time, a packaging round wasted. A new
default adding or renaming a module leaves the checkpoint unrestorable, surfacing
minutes in as a model mismatch. Re-run the stagedir from the job registry.
Missing or unknown is an error, never a cue to package what is here now.
Deliberate changes belong in a new experiment: a resume records nothing about
code changing.

Auto-resume belongs in the application, in-process at startup. Read the
checkpoint prefix, skip an explicit load or an eval-only run, and enumerate step
directories. Ignore any without the last-written marker file, whose absence means
an interrupted write. Resume from the highest surviving step. Enumerating the
prefix beats parsing logs, which a rotation restarts from zero.

## Where The Storage CLI Exists, And Where It Does Not

**The storage command-line tool is on the workstation and NOT inside a job
container**, which decides where a data-movement job should run.

A container ships the path-library client and nothing else, so shelling out to
the CLI there does not fail loudly. It hangs until the timeout with no output,
in state `RUN`, with nothing in the termination records because nothing
terminated. Two assembly jobs burned half an hour each that way.

This is more than "handle both backends". Server-side concatenation and
cross-cell copy exist only on the workstation path; in a container the same
operation carries every byte through the task. A tens-of-GB copy therefore
cannot finish inside a preemption window on the cluster, but finishes
comfortably from a workstation (not preemptible, acting only as a controller).
Probe which backend is live at runtime and branch. Keep a local branch too, or
the code is untestable off distributed storage, where the last several bugs in
ours survived.

## `state: RUN` Is Not Evidence That Anything Runs

**Check the VM-group states, not the job state.** A job reads `state: "RUN"`
for hours, all groups in `ASSIGN`/`PENDING`:

```
borg --borg=<cell> findjobs --name_re="<user>_group_<XID>\..*" \
  | grep -oE "VMGROUP_STATE_[A-Z]+"
```

No `VMGROUP_STATE_RUN` means nothing runs, whatever the job says.

Judge liveness by artifacts, not status queries. One run hung mid-epoch: no
crash, NCCL error, rank exit or new attempt. For 17 frozen minutes XM
`cancel --dry-run` said `RUNNING`, `tpu queue-status` `SUBMITTED`, both wrong.
(`borg findjobs` was empty, but that is not a third source: `--user=<me>` is
not a valid flag and returns empty rather than erroring, so an empty result
there means nothing unless you used `--user_re=` or `--name_re=`;
`engineering.md` §Verify The Premise Before Changing Anything.)
Frozen: log mirror, newest checkpoint `mtime`, step counter. Hangs are
invisible to grep; watchers need a stall probe on step numbers minutes apart.

Read every rank's newest attempt, not one log file; each qualifier fails alone.
A watcher pinned to `rank_0_attempt1.log` read "step 8097, no change" three
times while training ran on `attempt3`. Refitted to the newest, it froze on a
post-requeue dead XID.

| qualifier | what it defends against |
|---|---|
| every rank, not rank 0 | rank 0 exits while peers write, or the reverse |
| newest attempt each poll | preemption starts `attempt<N+1>`; old files read |
| artifact, not status query | XM and the queue report a dead job an hour |

The checkpoint directory is the strongest probe, independent of the log path.
No new `step_<N>` past one known wall-clock interval is a verdict, not a hint:
45 minutes without `step_10240` at a 1024-step cadence, XM still `RUNNING`.

XM state is unusable for liveness, not merely delayed; never bound its
staleness. The 17-minute case reads as lag. XM later said `RUNNING` 63 minutes
past a job's last byte, queue stuck at `SUBMITTED`. Another XID in that batch
showed `NOT_RUNNING`: tool fine, record wrong. Two lines hit that pair in one
night.

The scheduling ceiling sits far below the advertised quota. On the shared CPU
pool, fan-outs totaling several hundred GiB of RAM sat unscheduled for hours;
a fraction of that size reached RUN in seconds. Size fan-outs against what
schedules, using the command above.

Launcher hygiene, each having cost a launch:

- An XID is not a job: launchers print normal-looking ones for jobs that never
  scheduled. Confirm at the cluster layer.
- Truncate a launcher log before scraping: its last "Launched experiment" line
  may be a killed attempt's, naming a nonexistent job.
- Stop takes the experiment flag, not a positional or an abbreviated one.
- A jobs-board entry outlives the experiment: `PENDING` 21 hours after it
  reports "not found". Archive them, they are not work.
- A killed launcher tool-call does not stop the launch: a detached/`setsid`
  submit outlives its shell, so relaunching double-submits. Check the results
  file and `tpu check` first.
- Alive-but-wedged: board `running`, logs frozen, no restart. It started,
  unlike the unscheduled case, then hung mid-startup, classically at
  `Downloading dataset ...` staging the ~69G Maze mirror into `/tmp`. The Borg
  task lives, the process inside stuck: `running`, `1 active` WU, no new log
  lines, no `attemptN+1`. Borg restarts only dead tasks, so nothing trips the
  watchdog and the PROD slot burns indefinitely. Diagnose by newest log mtime
  against wall clock: >30 min of zero growth on all ranks, against a normal
  ~5 min download, is wedged, not slow. A sibling reading the same path fine,
  `step_*` ckpts advancing, blames these workers, not the data. Fix:
  `tpu cancel <xid>`, relaunch the validated config; fresh placement usually
  clears it. Verify `step>0`: the bug can re-roll onto another bad node.

## Identity, Paths, And Local Disk On A Worker

- **A cluster job is a different security principal from you.** Nothing you read
  interactively is automatically readable from a worker, and the same wall
  blocks log mirroring to a personal bucket. The cheapest fix is the internal
  distributed filesystem, which the job identity reads and writes natively,
  usually a one-line path change. Otherwise a bucket owner must grant the job's
  principal access; an org-level deny policy can block even owners, and
  service-account keys are not an option.
- The temporary directory is a RAM disk you must size yourself. The default is
  small and every task stages its own private copy of what it downloads, so an
  undersized value surfaces mid-run as "no space left on device". A job moving
  large files should stream through a bounded buffer instead.
- The RAM disk and the memory limit are two different knobs the launcher must
  pass explicitly; sizing `/tmp` does nothing for a process that allocates.
  Watch for a resource that must be named in its own field: appended to the
  accelerator string it reads as a second accelerator, accepted and ignored.
- Shell file utilities do not exist inside the container, and the standard
  library breaks on a distributed path or remote URI. `os.path` raises a
  permission error or silently answers False, a bucket URI fails a directory
  check, and normalization mangles the URI. That is how a valid remote load
  path becomes a bogus "does not exist". Route every existence check and remote
  read through the project's path helpers. This survives a green build and a
  local smoke test, because it only fires remotely.
- The launcher-to-application contract travels as environment variables, not
  config flags: the external checkpoint to load, the tracking run to continue,
  and the durable checkpoint prefix. That prefix derives from the experiment id,
  so every restart resolves to the same location, which is what makes in-process
  auto-resume well defined. Do not inject a checkpoint path as a config flag if
  the config schema is locked; every job dies at startup.

## Status And Diagnosis

1. From `tpu check`, resolve the exact experiment and work unit:
   experiment-level "running" is not allocated hardware. Work-unit state,
   allocation, logs, and activity tell queued from executing.
2. Read the failure classification first: a code-bug verdict puts the fix in
   your source, so preemption/quota hunting wastes time. Its cache refreshes
   about once a minute; run the checker binary directly. Blank on a pending job
   means "queued, nothing wrong".
3. Read the whole failure, not the final status string: immediate failure
   without logs can be allocator, topology, packaging, or authorization.
4. If the error explicitly names expired credentials, ask the user to
   re-authenticate and retry. Not every access failure is credentials.
5. If log access still fails with a valid identity, read the work-unit status
   message via the supported API or checker tools. Never hard-code job ids in
   shared scripts, nor assume another API skips authorization.

### Checking Whether One XID Is Still Alive

**`xmanager` is a shell function and `xmanager.par` is NOT on `PATH`; a bare
`xmanager.par ...` exits 127, which behind a `| grep` reads as "the job is
gone".** One line took three blank greps as three vanished jobs, all fine:

```bash
# Preferred: self-documenting, prints Status, no side effect on a live job.
source ~/work/tpu_cmd/tpu_wrapper.sh
tpu cancel --dry-run <xid>

# When sourcing the wrapper is inconvenient: ABSOLUTE path, capture rc.
XM=/google/bin/releases/xmanager/cli/xmanager.par
out=$("$XM" list --experiment_id=<xid> --archived=no \
        --columns=ID,Name,Status,FailedWorkUnits 2>&1); rc=$?
echo "rc=$rc"; echo "$out"
```

Note the `/cli/`: `/google/bin/releases/xmanager/xmanager.par` does not exist.
Never pipe it (`| grep`, `| head`): a pipeline reports its LAST stage's exit
status, hiding a missing binary as success-with-no-output.

Both exit 0 for a nonexistent XID: `rc=0` only means the query ran. Read the
`Status` line; silence answers only if it ran. `NOT_RUNNING` covers success and
failure: `FailedWorkUnits 0/1` is a clean finish, `1/1` a failed one.

Job registry, archived predecessor, snapshot config recovery,
cancel-versus-clear: `infra/tpu_cli.md`.

"Clean up the finished runs" means `tpu clear`, not deleting data: ambiguous
word, unrelated tools. `tpu clear` tidies the BOARD, archiving (never deleting)
finished and failed entries to `~/.tpu_jobs_legacy.json`, which config recovery
still resolves. `tpu gc` sweeps CNS checkpoints. Use `clear` for a cluttered
`tpu check`, `gc` only for a filling cell; cleared entries leave the board one
daemon cycle (~60s) later.

## Debugging A Job That Dies With No Log

**Reproduce locally first**, before any launch that changes imports or
dependencies. The staged package is an ordinary build target: the cluster's
exact artifact runs locally. `--help` suffices: flags parse only after every
module-level import, so import failures surface in seconds.

Reproduce in the RENAMED stagedir. The launcher rsyncs only the CWD into
`.../eqr_run_<ts>/` and builds `//<stagedir>:main`, destroying the
authoring-time google3 module path. A hardcoded absolute import
(`from google3.<original.pkg.path> import sibling`) or cross-package BUILD
`dep`/`data` label names something ABSENT from the staged binary: the worker
dies at import, before `main()`, no marker, behind the log wall. It builds
locally: that package is present.

Use the EqR-jax `eqr_run_*` idiom:
`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` in the entry
point, siblings imported by BARE name. Sibling `.py` ride along in a BUILD
`data` glob (`strict_deps = False`), relative SYMLINKS to one source of truth,
no drift; `rsync -aL` gives real files. `from . import x` fails: a
`py_binary` main runs as `__main__`, no parent package. Verify: build
`//<a-renamed-throwaway-dir>:main` without the sibling package, then `--help`.
In-place testing proves nothing.

Three signs diagnose a pre-`main()` death: empty status message, no application
log anywhere including mirrors, no surviving job handle. Do not re-launch for
impossible logs. Check quota first: an over-quota cell looks identical after
hours, log created, first write refused. A 0-byte log means never started or
unable to write; artifacts timestamped long after launch settle which
(`storage.md` §An Over-Quota Cell Looks Like A Broken Program).

Getting logs, most reliable first:

| Source | Caveat |
|---|---|
| Staged binary run locally: try FIRST | Covers most import and startup failures. The staged per-run SNAPSHOT (`.../eqr_run_<ts>_<hash>/`) ran, not your edited workspace: the two `main.py` differed by 45 lines and a md5 on 2026-08-29, so workspace line numbers describe a file never run. It carries a `BUILD`: `blaze build <snapshot_path>:main`, job's argv, ~40 s, zero credits. Answered what 47 credits of probe launches and four log instruments could not: flag arrival, torch load, beacon fire, startup latency. |
| Work unit job state: cell, user, job name, task counts, status message | Request detailed status explicitly, or it returns silently empty, like a gone job. Garbage-collected in minutes; the status message lasts far longer, usually with the exception. |
| App log mirrored to durable storage, teed from program start, flushed on error lines | Outlives task, work unit, and experiment; covers only post-start failures. Often Borg's only log, so protect it (`engineering.md`: handlers steal streams). |
| Log-tailing CLI | Works sometimes. |
| Log-search CLI | May be blocked by workstation permissions. |

Restricted-LOAS walls off EVERY worker-log service: from a workstation
credential, `borg tasklog`, `analog --remote`, and the F1/`get_job` path can
all return `PERMISSION_DENIED` (`borg tasklog` SIGABRTs on it), so stop after
the first. Write diagnostics to the destination, read with `fileutil`: a
numbered startup marker as the FIRST action in `main()`, one per stage, plus a
`try/except` dumping the traceback to CNS. Per `storage.md` §"write a copy's
evidence to the destination, not to a log".

That marker splits two look-alike deaths. `VMGROUP_STATE_RUN`, empty status,
zero output, no readable log is NOT necessarily a pre-`main()` death, only one
you cannot see. Present: reached `main()`, cause downstream. Absent: death
before logging, or an over-quota cell refused the first write (`storage.md`).

Two failure modes fire only remotely, past a green build and smoke test. First,
standard-library file APIs on a distributed path (§Identity, Paths, And Local
Disk On A Worker). Second, mocked third-party libraries, the build stubbing some
externals (`engineering.md` §Failure Modes That Only Appear On The Long Path).

## Launcher-Side Failures That Look Like Scheduler Failures

**A job that never created a work unit, or a launch that produced no XID, never
reached the scheduler.** Such submit-path failures are workstation-local, not
allocator or quota rejections.

- Never pipe into the submit command; background launches take stdin from
  `/dev/null`. Attribution prompts need only EOF, supplied by `< /dev/null`;
  piping `yes` segfaults the CLI, no XID, no diagnostic. WITHOUT `< /dev/null`,
  `nohup`/`setsid` reads EOF, re-loops, SUBMITS AGAIN: one `tpu queue` gives
  TWO experiments on one out_dir (two writers = corruption), while
  `~/.tpu_jobs.json` records one, leaving the survivor unregistered. Launch
  `tpu queue ... < /dev/null`; confirm EXACTLY ONE experiment with
  `"$XM" list --experiment_name=<name>`, rc captured. Never bare
  `xmanager.par ... | grep` (§Checking Whether One XID Is Still Alive:
  unresolved binary + pipeline reads like "no such job").
- No anti-dup wrapper killing the launcher on `Experiment id: N`. It prints at
  creation, BEFORE the blaze build (minutes) and any work unit; killing there
  leaves a RUNNING-forever zombie: experiment shell, "No work units found", no
  log dir, no out_dir. Only `Launched experiment N`, or on resume
  `Added N work unit(s) to experiment`, means finished; both print after the
  build and work-unit add. Retry on that line's ABSENCE, needing no kill logic
  under `< /dev/null`. Grep
  `Launched experiment|work unit\(s\) to experiment`, never `Experiment id:`.
- ANSI-strip output before grepping the XID. XManager colors it:
  `Launched experiment \e[1m\e[34m281839914\e[0m "name"`, so
  `Launched experiment \K\d+` matches nothing (ESC follows the space, not a
  digit) and a healthy job reads as "launch failed". Pipe through
  `sed 's/\x1b\[[0-9;]*m//g'` first. Likewise log-mirror step numbers and
  status: colored `SUBMITTED`/`Preempted.` have bitten watchers.
- A full `/tmp` breaks the submit with `SIGBUS`. `/tmp` is RAM-backed tmpfs, a
  repro's core dump fills it, the next writer dies on an unobtainable page.
  Disable repro cores, check free space first: every `/tmp` byte is RAM stolen
  from the machine doing cold imports.
- Bazel will not glob a package holding an absolute symlink ("Absolute symlinks
  are forbidden"). Dereference when copying a checkout that symlinks the shared
  launcher in. The package glob cache keeps that rejection: fixing the tree is
  not enough, restart the build server.
- The launcher forwards flags as a `key=value` dict the binary must accept.
  `--app.<flag>=<v>` passes one flag verbatim, but positionals are
  inexpressible and `store_true` arrives as `--flag=`, rejected by argparse.
  Both kill every task in parsing, before logging, and an unlimited restart
  budget churns forever writing nothing, like a scheduler problem. Select
  subcommands with a valued flag, booleans with explicit values.
- A flag must handle BOTH "absent" and "present but empty". A default of `""`
  collapses them: passed, parsed empty, default branch taken, fleet silently in
  the wrong mode. Default to `None`; test all spellings.
- Record each task's identity and mode somewhere readable: when tasks never log,
  a startup marker on distributed storage may be the only diagnostic.
  `$BORG_TASK_INDEX` is never set by XManager, so use the BCL `%task%` macro.

## Metrics And Curves

There is no external experiment tracker here. The internal equivalent stores
scalars in a table service and plots them in a dashboard service, both keyed by
experiment id. `research/result_logging.md` owns the URL forms, how to verify a
run actually wrote metrics, and the settings that are easy to get wrong
(explicit opt-in, rank-0 only, periodic flush).

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this guide whenever implementation details change.

## Budget Checking

**Before launching a job, the launcher automatically invokes
`tools/budget_check.py`: the projected GQM credits/hr of this job plus all
active jobs must not exceed 1/10 of G9 income** (boss directive, tightened from
1/3). Over the bar, the launch is halted. The `npu` aliases run their own
separate identical check.

What counts toward the bar, and what is exempt:
- Active = running, pending, or queued (option B). A job committed to the XM
  queue reserves budget before its Borg gang is RUNNING, so a backlog of pending
  jobs cannot each look free. The reroute lane (pending >10 min → auto-cancel)
  bounds how long a pending job holds that reservation, but only when it is
  armed; it is off by default (§The Local Queue: `tpu enqueue` + Serial Build-Worker). Only terminal zombies
  are dropped.
- g3/g5 are exempt: they draw on their own credit balance, not G9's income, so
  they neither count toward the aggregate nor are refused by it. The router
  (`tpu route`/`--power`) also prefers g3/g5 over g9 for the same reason
  (`infra/tpu_cli.md`).
- BATCH and CPU-only are exempt (free pool / no chips).
- Over the bar, the gate prints `[[BUDGET_DEFERRED]]` and exits 3. The
  local-queue worker reads that marker and parks the job BUDGET_DEFERRED,
  auto-retried when headroom opens, never as a build failure. A running-job
  enforcer (`tools/budget_enforcer.py`) separately cancels over-cap RUNNING
  jobs.
