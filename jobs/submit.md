# Submitting And Scheduling A Job

Package, place, queue, and schedule a job: the submission queue, the smart
router, the launch workflow and contract, requirements and tiers, choosing where
to run, the local `tpu enqueue` + serial build-worker path, and the pre-launch
budget gate. Part of the `jobs/` set; the hub is `../jobs.md`. Siblings:
`resume.md`, `liveness.md`, `diagnose.md`, `report.md`.

## The Submission Queue In One Screen

**Submit with `tpu enqueue` (instant, free) plus one serial `tpu build-worker`.**
Builds are always in flight on this shared workstation, so one-shot `tpu queue`
races them on blaze `output_base` (per checkout ROOT, not per copy dir),
silently shipping a zombie XID, 0 work units. Only serial building cures it
(`../infra/tpu_cli.md` §The Local-Queue Smart Router).

`cd` into the CODE directory before `tpu enqueue`: CWD becomes the job's
`workdir`, staging the whole tree. From `~/work` it stages your entire home
directory, dying with `produced no XID`, naming compilation for a staging
failure. Check the `packaged from:` line (§The Local Queue: `tpu enqueue` + Serial Build-Worker).

| You want | Do | Details |
|---|---|---|
| One job (default) | `cd <code dir>`, `tpu enqueue …`, `tpu build-worker` up; auto cell | §The Local Queue: `tpu enqueue` + Serial Build-Worker |
| A batch / sweep | `tpu enqueue` per arm; the same worker drains them | §The Local Queue: `tpu enqueue` + Serial Build-Worker |
| Widening the router's choices (do this on EVERY job) | `--archs=a,b,c` and `--metros=x,y,z` — several of each | §Give The Router More Than One Way To Say Yes |
| Data locality | `--metros=<m>[,…]` (e.g. `cbf,tul`); full metros refuse, never roam to no-data cells | §Give The Router More Than One Way To Say Yes |
| Telling runs apart | `exp_name=` names the TASK, not just the model | §Name The Experiment After Its Job, Not After Its Model |
| Naming the queue entry | `--job_name=<content-name>` — **REQUIRED**: enqueue REFUSES without it (no more auto `<power>-<hash>`) | §Name The Experiment After Its Job, Not After Its Model |
| Group / placement | leave `--group` UNSET — the smart router owns group selection | §The Local Queue: `tpu enqueue` + Serial Build-Worker |
| Fallback, no worker | `tpu queue …`, synchronous, returns an XID; ONLY when nothing else builds | §Submission Contract |
| PENDING past 10 min | OFF by default: arm the reroute sweep to cancel and re-route | §The Local Queue: `tpu enqueue` + Serial Build-Worker |

Both share one submission contract (same flags, registry) and smart pick:
least-oversold placeable cell. `--cell` is rarely needed, always wins.
`TPU_NO_SMART_CELL=1` opts out (§Choosing Where To Run).

## Give The Router More Than One Way To Say Yes

**Name SEVERAL architectures and SEVERAL metros on every job, because the
router can only re-place a preempted run among the candidates you listed, so a
single `--archs=v7 --metros=mrn` leaves exactly one cell in the fleet and the
job re-submits to the same contested cell forever instead of moving.** Measured:
a v7-32 pinned that way burned four re-routes and three XIDs without moving,
while v7 was quoted at the same price in fifteen metros. Passing one value is
accepted by the CLI and reads as a normal launch; nothing warns you.

```sh
# The shape to copy. Several archs, several metros.
tpu enqueue --power=v7-32 --archs=v7,v6p,v5p --metros=cbf,tul,lpp \
            --tier=PROD --launch=config=my_cfg,exp_name=my_run
```

* **`--power` is the compute target and `--archs` are the generations allowed
  to satisfy it**; they are required together, and `--power` already scales
  across generations (`--power_tolerance`, default 0.5), so adding an older
  family widens placement without shrinking the run. `v6p-32` and `v7-32` are
  chip-for-chip equal (`../tpu_reference.md`), and equal topology, so a
  `topology_locked` resume survives the swap — check `same_topology()` before
  assuming that for other pairs.
* **The flag is `--metros` (plural) — `--metro` does not exist on `enqueue` and
  dies with `FATAL … Did you mean: metros ?`.** The error teaches the spelling
  and not the arity, so the usual repair is `--metros=<one>`, which is the
  failure this section exists to prevent. (`tpu queue`, the deprecated
  synchronous path, does take the singular. Do not copy its examples.)
* **Only list a metro that has a STORAGE CELL in
  `cell_locality.py::_METRO_STORAGE_CELL`; naming any other one does not slow
  the job down, it kills it silently.** A job placed in a metro with no
  registered bucket makes the launcher's `_local_bucket()` fail closed and
  `SystemExit` — after the XM experiment exists but before the work unit is
  added, so you get an empty shell in XManager and zero bytes in CNS, with
  nothing anywhere saying why. One line lost seven cars to this. Read the table
  before adding a metro:
  `python3 -c "import cell_locality as c; print(sorted(c._METRO_STORAGE_CELL))"`.
* **Every metro holding a copy of your data belongs in the list**, and the
  metro your job WRITES to must be among them: a training loop writing across a
  metro runs ~94x slower and the pruner deletes it (`../storage.md`). Resolve
  metros from that same measured table, never by eye — `/cns/si-d`=sin,
  `is-d`=cbf, `oi-d`=tul, `qo-d`=mrn, `li-d`=lpp are examples, not the list
  (`../storage.md` §Never Hand-Maintain A Cell -> Metro -> Bucket Table).
* **Do not widen a metro list from where jobs have LANDED — that history
  contains the metros that killed them.** A quote-less metro may well be
  reachable (`market.json` prices an arch in fewer metros than actually run
  it), so the price table understates the options; but "the scheduler can place
  me here" and "I can write my checkpoints here" are different claims, and only
  `_METRO_STORAGE_CELL` answers the second. Landing history answers neither: it
  records where cars went, including the ones that died on arrival.
* **GPUs: widen the metros even when the arch cannot widen.** `h100` and `b200`
  are both routable and rank biggest-card-first, so `--archs=h100,b200` is
  usually right; where a CUDA build genuinely targets one card, that is the one
  legitimate single-arch job — the metro list still has no excuse to be short.

## The Launch Workflow

**Run this every launch; settle placement (steps 2–4) before packaging**:
packaging costs minutes, allocators reject in seconds. Each step names its
section.

0. `cd` into the launched code directory (§The Local Queue: `tpu enqueue` + Serial Build-Worker): CWD becomes the
   entry's `workdir`; the whole tree stages. Use a code subdir
   (`~/work/<repo>/torch_impl`), never `~/work`; check `tpu enqueue`'s
   `packaged from:` line.
1. Prepare the submission (§Submission Contract). Semantics in versioned config;
   on a shared checkout edit a COPY and launch it. Training is always
   `--tier=PROD`; an eval picks its tier by whether it must finish
   (§Requirements And Runtime).
2. Pick the group (§Choosing Where To Run): default g9 for TPU (it holds the
   floor), g8 CPU-only. `tpu quota` names WHICH GROUP holds an accelerator's
   floor, never cells. **But on the `tpu enqueue` smart-router path do NOT pass
   `--group` — the router owns group selection (§The Local Queue). This g9
   default and the group table apply to the synchronous `tpu queue` fallback,
   or an operator-authorized pin, not to a normal enqueue.**
3. Cell auto-picked, usually skipped (§Choosing Where To Run). Submit pins the
   most-free non-oversold placeable cell; add `--metro=<m>` if
   data-locality-locked. Probes below only OVERRIDE it or explain rejections:
   - `tpu preflight --tpu_type=<t> --group=<g> --json` → `cells_ok`, per-cell
     obtainable counts, the only cell-level view (`tpu quota` has none).
     Obtainable means "can be got", not "can be held".
   - `stubby call master.<cell>.borg:9413 BorgMaster.ProbeSliceAvailability`
     for free contiguous slices. A cell with thousands of obtainable chips may
     hold one placeable slice (shape uses UNDERSCORES;
     `../research/v7_storage_placement.md`).
   - Intersect: a cell with your floor and data (§Choosing Where To Run;
     `../storage.md`). The same obtainable number is idle-guaranteed in one
     (group,cell), borrowed-reclaimable in another.
4. Preflight, then verify the snapshot (§Choosing Where To Run, §Submission
   Contract). Green is necessary, not sufficient; CPU-only jobs use
   `--skip-preflight`. `diff` packaged config against intent.
5. Submit, then confirm it is REAL (`liveness.md` §`state: RUN` Is Not Evidence That Anything Runs). An XID is not a job,
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
  (`../infra/tpu_cli.md`). The default is `remote_run`, so write the run into
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
- Default to `tpu enqueue` plus one serial `tpu build-worker`, single job or
  batch; `tpu queue` (one-shot, synchronous) is the fallback only when you KNOW
  no other build is in flight. §The Local Queue: `tpu enqueue` + Serial
  Build-Worker owns the mechanism, the concurrent-build zombie XID it cures, and
  the guards.

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

**The same rule governs the local-queue name, and `tpu enqueue` now ENFORCES
it: `--job_name` is REQUIRED, and an enqueue without it is REFUSED.** There is
no auto-mint any more — a `v7-32-37351a` named after nothing made a queue of
hundreds (`tpu queue-status`, the build-worker log, `tpu dequeue`) unreadable
and the wrong arm easy to drop. Pass `--job_name=<content-name>` matching the
`exp_name` (e.g. `--job_name=elt_dit_ldit_eltopt`). `--job_name` is the local
handle, `exp_name` the XManager/CNS handle; both must name the task. (`--job_id`
is still accepted as the old spelling of this flag.)

## Requirements And Runtime

- **Every TRAINING job must pass `--tier=PROD` explicitly. Never train on
  BATCH.** BATCH is best-effort, preempted the instant PROD demand contests a
  slot. PROD is already the launcher default for every group (g5 injects it,
  others inherit XManager's `_DEFAULT_SERVICE_TIER=PROD`), so `--tier=PROD` is
  for the audit trail, not behavior. `tpu check`'s TIER column echoes the
  REQUESTED string from the local registry, not Borg truth: `-` means
  "untagged, ran the PROD default", not "non-PROD". Read the work
  unit/allocator for ground truth.
- **An eval may run on EITHER tier — pick by whether it must finish.** The only
  tier rule is *train on PROD only*; nothing about BATCH makes it right for
  every eval.
    - `BATCH` for a short eval, a smoke, or anything cheap to restart: the
      polite default, leaving the PROD budget bar to training.
    - `PROD` once the eval MUST finish — long generation loops, a paper number,
      anything whose restart cost exceeds the tier's saving. A 50k-image FID
      eval preempted repeatedly on BATCH cost, on PROD, far less than the tier
      saving implied: the tier was never the binding constraint.
  GPU nuance, same shape: most families have a free (0.00) BATCH pool and cheap
  PROD, so a short smoke there is fine, but BATCH still preempts (`guarantee
  reclaim`). Use `--tier=PROD` once a GPU run must finish. `../gpu_on_borg.md`
  §Rule 6 — Tiers owns this.
- Priority <= 25 charges the person, above it the group. Free tiers spare the
  team's GCU allocation. `BATCH` reads cheap but is the opposite: a paying
  best-effort tier billing the group.
- Set the tier with `--tier`, never the dead `--priority` wrapper flag (parsed,
  never read). Prefer named tiers. A raw numeric `--tier=N` changes who pays
  (`<= 25` bills you personally) and shrinks the per-cell task cap. Bigger
  numbers win no contention: the quota floor/market sets schedulability, not the
  number (`../infra/quota_market.md`).
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
  (`liveness.md` §Where The Storage CLI Exists, And Where It Does Not). Use the same `(group, PROD)` as your long
  jobs, pin a cell in the data's metro, add `--skip-preflight` (CPU-only cannot
  be preflighted), confirm `VMGROUP_STATE_RUN`. That covers genuinely-free
  best-effort batch, not a ban on PROD for CPU-only. Diagnose from your own
  fleet: two submits differing ONLY in group, the pool unscheduled a day, the
  PROD alloc at RUN in ~1 minute.
- Container-style packaging needs the pool to have a mapped cloud project;
  native allocators without one need Bazel packaging.
- In JAX jobs, parse flags before distributed initialization, never at module
  import time. `../projects/eqr_jax.md` has the google3-specific startup order,
  stricter than the public contract.

## Choosing Where To Run

Packaging costs minutes, an allocator rejects in seconds: settle placement
first. Decisions here, mechanism in `../infra/`.

- **The cell is now chosen for you by default, so you rarely pass `--cell`.**
  Each submit pins whichever cell can place the slice RIGHT NOW (most free
  chips, not oversold), printing `Smart cell: pinned --cell=…`. Otherwise jobs
  pile onto oversold cells while chips idle (a dozen slices stacked on one
  oversold cell with a sibling holding a hundred free). `--cell` wins, `--power` picks for itself, a comma
  `--tpu_type` list and `TPU_NO_SMART_CELL=1` skip it, and no candidate defers
  silently to the allocator. It never blocks. The group below outranks the
  cell.
  - A data-locality-locked run passes `--metro`, not a hand-pinned `--cell`.
    Ranking only free chips and oversold, it can strand a run a metro from its
    bucket: 4-5x throughput, then a pruner kill (storage rule). Locality is
    METRO-level: every storage cell in one metro reads that metro's one bucket
    (`../storage.md`). `--metro=<m>` (e.g.
    `--metro=cbf`) takes that metro's least-oversold cell, `--metros=a,b`
    several. A router selector never reaching the launcher, `--metro` beats a
    `--cell` pin. Roam metros only with no storage need.
    - `--metro` fails CLOSED. A full metro refuses rather than roaming
      out-of-metro to a no-data cell whose dataloader crashes. Wait, or pin
      `--cell=<in-metro cell>` and stage-and-queue. Only a NO-data run
      overrides: `--force` / `TPU_METRO_FALLBACK=1`.
- Pick the group holding your floor (last bullet): idle guarantee versus
  borrowed and reclaimable.

  | Group | Alloc (short) | Use for |
  |---|---|---|
  | 9 | `fr-dna-grand-challenge-team-resource` | TPU training default: nearly all our real v6p/v7/v4 floor, plus stable jobs. |
  | 8 | `brain-vasp-shared-user-xm` | CPU-only, `--skip-preflight`. No TPU floor, `tpu quota` empty: size fan-outs by what schedules (`liveness.md` §`state: RUN` Is Not Evidence That Anything Runs), not quota. |
  | 5 | `vqfree-xm` | Free pool, auto-injects PROD (§Requirements And Runtime). |
  | 1, 7 | `*-resources-prod-shared` | Shared prod, thin-to-zero floors. Contended-g9 fallback, not a default. |
  | 2, 3, 4 | `*viscam*` / `*interns*` | viscam/intern allocations. |

  Full strings: `~/work/tpu_cmd/tpu_wrapper.sh::get_alloc_by_group_id`, the
  single source of truth. g9 is only a start: fall back once its accelerator
  floor is spent, or your data's metro has none.
- Convert power classes first: a chip count is not a size (`../tpu_reference.md`).
  `tpu route --power=` turns one into an allocation, type, and cell.
- Preflight before packaging: fifteen seconds, catching illegal topology,
  minimum-slice rules, no platform capacity, thin headroom (layers in
  `../infra/tpu_cli.md`). Red submits are refused absent an override.
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
  accelerator, never the complete list. `tpu route` once put v6p solely in a phx
  cell with no team storage, while preflight's `cells_ok` listed nine, two
  co-located with our data: nearly a lost locality. Take
  full `cells_ok` from `tpu preflight --json` or the market cache
  (`../infra/quota_market.md`), intersected with storage (`../storage.md`).
- Prefer cells whose metro holds storage you can write. The scheduler ranks
  capacity and price, not data, so the freest cell often lacks team storage.
  Writes then hit the personal per-cell ceiling (`../storage.md` owns placement
  and why distance kills a run). Preference, not ban: a storage-less cell is
  real capacity while something sweeps the quota. A multi-cell allow-list reads
  only in spatially-flexible mode, so set both; a pin bypasses both.
- A PROD floor is per (group, accelerator, cell); a tier alone guarantees
  nothing. The thousands `preflight` calls obtainable are borrowed capacity a
  guarantee holder reclaims mid-compile, not a floor. One smoke took FIVE
  launches — preempted on BATCH, then guarantee-reclaimed on a PROD cell where
  the group held a ZERO floor — and stuck only once placed in a (group, cell)
  where the team holds a real floor and STABLE jobs already run beside the data
  mirrors. Launch where long jobs survive, not where preflight calls chips
  obtainable.

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
  `../tools/limit_order.sh status` for `BLOCKING` first (`../infra/quota_market.md`).
- It never reached the scheduler. An XID with no work unit, or no XID, is a
  launcher-side failure, not a queue: a local problem (`diagnose.md` §Launcher-Side Failures That Look Like Scheduler Failures).

When the verdict is ambiguous, probe: a short submit of the real workload
answers "can I get this slice here" at 100%, where the capacity table was ~12%
accurate against the live queue (`../research/accelerator_choice.md`).

## Verify The Scheduler Exists Before You Rely On It

**`tpu` answering "not built" usually means the PATH to its binaries moved, not
that anything is missing; three faults share the symptom.** Blaze names an
output_base after `md5(workspace_directory)`, or the `<md5>_buildrabbit` sibling
root when `$BUILD_EXECROOT` is set. Two environments on one checkout own two
roots; the last to build repoints `blaze-out`/`blaze-bin`, hiding
`route_check` / `queue_cli` / `jobd`, binaries intact in the other root. It
self-heals when the symlink swings back, reading as random drift.

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
not live. Restart and re-check the same way (`../engineering.md`
§External Writes Are Transactions, "Never kill by pattern").

## The Local Queue: `tpu enqueue` + Serial Build-Worker

**`tpu enqueue` plus a serial `tpu build-worker` is the DEFAULT submission path**
(§Submission Contract), single job or batch. Only it dodges the concurrent-build
`output_base` race and its 0-work-unit zombie XID (`../infra/tpu_cli.md`). An
`enqueue` is free and instant; PENDING does not bill. It also:

- drains a batch or sweep as capacity frees, no babysitting N submits;
- re-routes anything PENDING after placement (the 10-minute sweep, below);
- handles a mixed batch across checkouts, each keeping its dir.

**`tpu enqueue --dry_run` still enqueues, and still pre-debits the budget.** The
flag belongs to `route-tick` (plan vs submit) and is merely visible in
`enqueue`'s shared flag namespace, where it does nothing — and it defaults to
`true`, so `--helpshort` reads as though enqueueing were the opt-in. The command
prints `enqueued <job_id>` and the row lands in `~/.tpu_local_queue.json` as
`BUILD_REQUESTED` with credits already pre-debited. Nothing errors, so this is
worse than a rejected flag: it executes what you thought you were rehearsing.
There is no rehearsal mode; to check what an enqueue did, read the queue file
(or `tpu queue-status`), never the command's own output.

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

**Never pass `--group` on `tpu enqueue`; group selection is the smart router's
domain, not yours.** An unpinned row lets the router apply its own group
preference and re-place the job as capacity and price shift; pinning a group
overrides the scheduler and defeats the point of the smart queue. The enqueue
CLI actively nudges `Pass --group=9 to pin it` on every unpinned row — IGNORE
that nudge. Like `priority>0`, a manual `--group` is an operator-only decision;
do not add it on your own initiative. `tpu queue-status` confirms a correct row
as `group: 5 … pin_group: None` (router-chosen, unpinned).

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
until it expires, so one killed build parks the whole queue. A lock-yield timer
(`lyy-work/vlm/g3/watch/lock_yield.sh`) that `tmux kill-session`s and restarts
the dispatch worker on a cycle SHORTER than a real build converts every firing
into a 30-minute park; the only trace afterwards is `reclaimed: BUILDING claim
went stale` in `last_reason`.

Three properties any such pauser needs. It must reset the BUILDING rows owned by
the worker it just killed back to QUEUED — safe precisely because no worker
exists during the pause, the one moment a second writer cannot race the drainer.
It must not judge by a waiter's AGE alone: a waiter wedged in FUSE-D never
finishes, its `etimes` grows without bound, and the pause becomes permanent. And
it must check WHO holds the lock before yielding: killing the dispatch worker
does nothing when the holder is a different process of the same operator (a
synchronous `tpu queue` launch), which pauses the operator's own queue while the
lock never moves.

`lock_yield.sh` implements all three: `THRESH` is set above the CLI's own 1800 s
degrade window (so a pause is reserved for a wait the CLI cannot clear itself),
and a `_reclaim_killed_claims` step between the kill and the pause rewrites
BUILDING rows whose `worker_id` names a dead pid back to QUEUED. It leaves
`attempts` alone (a courtesy pause is not a failed attempt, keeping the
3-strikes HELD count honest), never touches a live or `worker_id`-absent row,
and writes temp-then-rename so an interrupted pass cannot leave half a queue
file.

A `found[]` / no-XID verdict is a symptom, and the two cheapest causes are not
in your code. Read `last_reason`, then elapsed time: far LESS than a real build
means blaze was never reached, so staging or a gate is at fault. Two do:

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
Each attempt leaves a stagedir behind.

Tell it from an ordinary failed build by the SHAPE of the failure, not by a
success rate. `found[]` also happens from a correct directory and usually
succeeds on retry; the wrong-workdir version fails deterministically, every
attempt at the same point, and its stagedir mirrors your home directory instead
of a checkout. Read what was staged: that separates the two before the third
attempt burns. A no-XID population is mixed — wrong-`~/work` deaths that burn
all three attempts, retryable `found[]` from a correct subdirectory, and
administrative HELDs that never built — so classify by the staged tree, not by
the bare count.

Reading that field is not checking it: "differences all ride on explicit flags"
answers whether the right source ships, not whether the packager finishes. The
hazard is tree size, not contents.

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
cancels a job whose status it cannot read. Internals: `../infra/tpu_cli.md`.

## Budget Checking

**Before launching a job, the launcher automatically invokes
`../tools/budget_check.py`: the projected GQM credits/hr of this job plus all
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
  (`../infra/tpu_cli.md`).
- BATCH and CPU-only are exempt (free pool / no chips).
- Over the bar, the gate prints `[[BUDGET_DEFERRED]]` and exits 3. The
  local-queue worker reads that marker and parks the job BUDGET_DEFERRED,
  auto-retried when headroom opens, never as a build failure. A running-job
  enforcer (`../tools/budget_enforcer.py`) separately cancels over-cap RUNNING
  jobs.
