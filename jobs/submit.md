# Submitting And Scheduling A Job

How to package, place, queue, and run a job. Chapter 1 is the mechanism,
Chapter 2 the step-by-step, Chapter 3 the classic bugs. Part of the `jobs/` set;
the hub is `../jobs.md`. Siblings: `resume.md`, `liveness.md`, `diagnose.md`,
`report.md`.

The default: `cd` into the code directory, `tpu enqueue` with all usable
`--archs` (among v4, v5p, v6e, v6p, v7) and several data `--metros`, and keep one
serial `tpu build-worker` draining the queue.

---

## Chapter 1 — How Submission Works

### The two queues and the serial build-worker

**Every job goes through a local queue that a single serial `tpu build-worker`
drains into the XManager queue, one build at a time.** `tpu enqueue` appends a
run to a durable local list (`~/.tpu_local_queue.json`) — instant, free, no bill
while it waits; the worker then claims one QUEUED entry, builds it, records its
XID, and repeats. States: QUEUED → BUILDING → SUBMITTED → RUNNING
(`tpu queue-status`, `tpu check`).

Serial is the default because builds are always in flight on this shared
workstation: two concurrent builds race on blaze's `output_base` (keyed per
checkout root, not per copy dir) and ship a zombie XID with zero work units.
`tpu queue` is the one-shot synchronous fallback — only when you KNOW no other
build is running.

### The smart router picks the cell and the group

**On the enqueue path the router owns cell and group selection; you supply the
compute target and the candidates, not the placement.** It pins whichever cell
can place the slice right now (most free chips, never oversold or full) and
prints `Smart cell: pinned --cell=…`.

- Do NOT pass `--group` on `tpu enqueue`: the router re-places the job as price
  and capacity shift, and a pin defeats that. The CLI nudges "Pass --group=9 to
  pin it" — ignore it. A manual `--group`, like `--priority>0`, is operator-only.
- `--cell` always wins. `--metros` constrains the pick to data-co-located metros.
  `TPU_NO_SMART_CELL=1` opts out.

### `--power` is the target; `--archs` are the generations allowed to meet it

**`--power` and `--archs` are required together: `--power` is the compute you
want, `--archs` the generations allowed to satisfy it.** `--power` scales across
generations (`--power_tolerance`, default 0.5), so adding an older family widens
placement without shrinking the run. A chip count is not a size: `v6p-32` and
`v7-32` are equal, `v6e-32` is half (`../tpu_reference.md`).

### Data locality is per metro

**A job must write its checkpoints to a bucket in its OWN metro; writing across a
metro runs ~94x slower and the pruner deletes the job.** Locality is metro-level:
every storage cell in one metro reads that metro's one bucket (`../storage.md`).
Only metros with a registered storage cell in
`cell_locality.py::_METRO_STORAGE_CELL` are legal — naming any other kills the
job silently. Group-storage metros: `cbf ckv cmh dfw grq las lpp mrn sin tul`.

### Tiers: train on PROD, evals either way

**Every TRAINING job runs on `--tier=PROD`; never train on BATCH.** BATCH is a
paying best-effort tier that any PROD demand preempts the instant a slot is
contested, so a training run on BATCH is silently starved and still costs. PROD
is already the launcher default, so `--tier=PROD` is mostly for the audit trail.

An eval runs on either tier — BATCH for a short or restartable one, PROD once it
must finish (a long generation loop, a paper number). The only tier rule is
*train on PROD only*. Set the tier with `--tier`, never the dead `--priority`
flag; priority ≤ 25 bills you personally, above it bills the group.

### Groups

**Pick the group that holds your floor.** The enqueue router picks it; this table
is for the `tpu queue` fallback or an operator-authorized pin.

| Group | Alloc (short) | Use for |
|---|---|---|
| 9 | `fr-dna-grand-challenge-team-resource` | TPU training default: nearly all our v6p/v7/v4 floor. |
| 8 | `brain-vasp-shared-user-xm` | CPU-only, with `--skip-preflight`. No TPU floor. |
| 5 | `vqfree-xm` | Free pool, auto-injects PROD. |
| 1, 7 | `*-resources-prod-shared` | Shared prod, thin floors; g9 fallback. |
| 2, 3, 4 | `*viscam*` / `*interns*` | viscam / intern allocations. |

Full strings: `~/work/tpu_cmd/tpu_wrapper.sh::get_alloc_by_group_id`.

CPU-only jobs schedule last in accelerator groups (CPU/RAM are ancillary in GQM),
so run them in the best-effort pool (`--group=8`, `go/gdm-cpu-only-jobs`,
pre-authorized, free). When it is dry, ride the team's PROD alloc with a cell
pinned in the data's metro and `--skip-preflight` — a CPU-only controller costs
almost nothing yet schedules immediately.

### The budget gate

**Before any launch the launcher runs `../tools/budget_check.py`: this job plus
all active jobs must project under 1/10 of G9 income, or the launch is halted.**
Active = running, pending, or queued, so a backlog cannot each look free. Over
the bar it prints `[[BUDGET_DEFERRED]]`, exits 3, and the worker parks the job
BUDGET_DEFERRED and auto-retries it (not a build failure). g3/g5 draw their own
credit balance; BATCH and CPU-only are free — all exempt.

### The launcher, config, and packaging

**One shared launcher owns packaging: `~/work/tpu_cmd/xm_launcher.py`. Projects
contribute versioned config, not launchers.** Never call `xm launch` /
`xmanager launch` directly — only the wrapper may, after you
`source ~/work/tpu_cmd/tpu_wrapper.sh` (`tpu` is a shell function, not a binary
on `PATH`).

- Semantics (model, data, training behavior) go in versioned config; only routing
  and transient selectors go on the command line.
- Edit the run config in place, pass no `--config`. Default mode is `remote_run`
  (write into `remote_run_config.yml`). Name a mode BARE (`--config=trm_sudoku`),
  never a path or filename.
- Packaging snapshots the code into an immutable CitC snapshot, so later edits
  cannot affect a queued or running job.

---

## Chapter 2 — Submitting A Job, Step By Step

Settle placement before packaging: packaging costs minutes, an allocator rejects
in seconds.

**Step 0 — `cd` into the code directory.** The CWD becomes the entry's `workdir`
and the whole tree is staged, so use a code subdir (`~/work/<repo>/torch_impl`),
never `~/work` (staging your home directory produces no job at all). Confirm with
the `packaged from:` line.

**Step 1 — Prepare the config.** Edit the run config in place, pass no
`--config`. On a SHARED checkout, edit a COPY and launch from that: every launch
overwrites the file the launcher reads, so two agents minutes apart package each
other's experiment. Commit code changes in the shared checkout (a deleted copy
takes its provenance with it).

**Step 2 — Settle placement.** Preflight is fifteen seconds and catches illegal
topology and no-capacity; green is necessary, not sufficient (it misses topology
fragmentation, which the allocator rejects seconds later).
- `tpu preflight --tpu_type=<t> --group=<g> --json` → `cells_ok` and per-cell
  obtainable, the only cell-level view.
- The metro the job WRITES to must be among your data metros.
- CPU-only jobs cannot be preflighted; submit with `--skip-preflight`.

**Step 3 — Enqueue.** The shape to copy:

```sh
cd ~/work/<repo>/<code-subdir>
tpu enqueue --power=v7-32 --archs=v7,v6p,v5p,v6e,v4 --metros=cbf,tul,lpp \
            --tier=PROD --job_name=<content-name> \
            --launch=config=my_cfg,exp_name=my_run
```

Easy to get wrong:
- All usable `--archs` (among v4, v5p, v6e, v6p, v7) and several data `--metros`,
  never one of each (Chapter 3). Drop an arch only when it cannot run the job
  (e.g. per-chip HBM too small); size with `--power` so the router scales the
  slice per generation.
- `--metros` is PLURAL on enqueue; `--metro` does not exist here.
- `--job_name` is REQUIRED (the local queue handle); `exp_name=` is the
  XManager / CNS handle. Both name the TASK and what distinguishes this launch,
  not just the model.
- Training passes `--tier=PROD`. Do not pass `--group`, nor `--priority>0`
  without the operator's permission.
- A checkpoint-sharded resume also passes `--topology_locked`, so the router only
  moves it within the same mesh geometry (`v6p-32` and `v7-32` are both `2x4x4`;
  `v6e-32` is not) — see `resume.md`.

**Step 4 — Drain.** Make sure a serial build-worker is up
(`tpu build-worker status`, else `start`); enqueuing alone submits nothing.
`tpu queue-status` shows progress.

**Step 5 — Verify it is REAL.** An XID is not a job and `state: RUN` is not
evidence anything runs (`liveness.md`): confirm `VMGROUP_STATE_RUN` at the
cluster layer. `diff` the packaged config against what you meant (the SNAPSHOT,
not the file you edited).

**Step 6 — If it stays PENDING, read the verdict; do not resubmit reflexively**
(each resubmit stacks another work unit on the same slice). Act on the live
unit's `GQM_RESOURCE_DEFICIT_INFO` or `deep_probe` verdict:

| Verdict | Means | Move? |
|---|---|---|
| `GQM_OVERSOLD_MARKET` (names a cell) | that cell is oversold | Yes — another may take it |
| `GQM_RESOURCE_DEFICIT_INFO`, deficit N (names a cell) | short N chips there | Yes — pick a smaller deficit |
| `resource-guarantee-reclaim` | a floor holder reclaimed borrowed capacity | Yes — to a (group,cell) where you hold a floor |
| `dynamic root pool … capped by adjusted ceiling` | a pool-wide limit | No — change tier / generation, or wait |

First rule out two non-capacity causes moving cell will not fix: a price cap /
limit order (`../tools/limit_order.sh status` shows `BLOCKING`), and a
launcher-side failure that never reached the scheduler (an XID with no work unit,
or no XID — `diagnose.md`).

**Commands:**

| Command | Does |
|---|---|
| `tpu enqueue --power=… --archs=… --metros=… --job_name=… --launch=…` | Add a run to the local queue. `--power` and `--archs` are required together. |
| `tpu queue-status` (alias `tpu qs`) | The local queue plus, live, why each job waits or where it is placeable. |
| `tpu build-worker start` \| `stop` \| `status` | The serial build-worker in its own tmux session; one build in flight. |
| `tpu dequeue <job_id>` | Remove one entry before it is submitted. |
| `tpu requeue [job_id…]` | Return HELD job(s) to QUEUED after you fix the cause. |
| `tpu route-tick [--reroute --nodry_run]` | One router pass by hand; `--reroute` cancels and re-queues jobs PENDING past 10 min. |
| `tpu queue …` | Deprecated one-shot synchronous submit; the fallback when no worker is up. |

---

## Chapter 3 — Classic Bugs And What To Do

Symptom → cause → fix. A `[[MARKER]]` in a reason string is the machine-readable
verdict — trust it over the surrounding prose: `[[STAGE_SRC_REFUSED]]`,
`[[STAGE_RSYNC_TIMEOUT]]`, `[[STAGE_RM_REFUSED]]`, `[[STAGE_INCOMPLETE]]`,
`[[BUDGET_DEFERRED]]`.

### Packaging and the wrong directory

| Symptom | Cause | Fix |
|---|---|---|
| `build produced no XID (found[]/crash?)`, deterministic every attempt, stagedir mirrors your home dir | enqueued from `~/work`; the packager recurses the whole home tree and times out | `cd` into the code subdir; check the `packaged from:` line |
| Retryable `found[]` no-XID that usually succeeds on retry | the concurrent-build `output_base` race | build serially; never `tpu queue` during another build |
| `[[STAGE_INCOMPLETE]]`, empty run directory | the completeness check missed the entry source (some packages use `main_eqr.py`, not `main.py`) | fix the BUILD `srcs`; the marker names the missing artifact |

### Router and placement flags

| Symptom | Cause | Fix |
|---|---|---|
| Job re-routes to the same contested cell forever, burning re-routes and XIDs without moving | a single `--archs` / `--metros` leaves exactly one candidate cell in the fleet | name SEVERAL `--archs` and SEVERAL data `--metros` on every job |
| `FATAL … Did you mean: metros ?` | `--metro` does not exist on enqueue | use `--metros` (plural); the singular is a `tpu queue` thing |
| Empty shell in XManager, 0 bytes in CNS, nothing says why | a metro with no registered storage cell makes `_local_bucket()` fail closed and `SystemExit` after the XM experiment exists | only list metros in `_METRO_STORAGE_CELL` |
| `phx` / `ske` refused at enqueue | unregistered for CNS storage; they bill the personal 500 GiB quota and leave 0-byte files | use a group-storage metro; the escape hatch is an explicit `--bucket` |

### Flags that do not do what they read like

| Symptom | Cause | Fix |
|---|---|---|
| `tpu enqueue --dry_run` still submitted and pre-debited the budget | `--dry_run` belongs to `route-tick`; on enqueue it does nothing and defaults true | there is no rehearsal mode — read the queue file / `tpu queue-status`, never the command's own output |
| Startup dies "Could not locate …" | `--config=configs/x_config.yml` gets wrapped into `configs/configs/x_config.yml_config.yml` | pass a BARE mode name (`--config=trm_sudoku`) |
| The whole queue is parked for a shift | someone enqueued `--priority>0`; the queue drains highest-priority-first | default is `priority=0`; `--priority>0` is operator-only |
| A job is pinned to a group and not re-placed | `--group` passed on enqueue overrides the router | never pass `--group` on enqueue |

### Tiers and CPU-only

| Symptom | Cause | Fix |
|---|---|---|
| A training run is silently starved but still billing | it landed on BATCH | `--tier=PROD` on every training job |
| A CPU-only job sits in `starting` for hours | CPU and RAM are ancillary in accelerator groups, so it schedules last | `--group=8` best-effort pool; when dry, ride the PROD alloc with `--skip-preflight` and a metro-pinned cell |
| An eval is preempted repeatedly | a must-finish eval was left on BATCH | move it to PROD; tier is not the binding constraint once restart cost exceeds the saving |

### The build-worker and HELD

| Symptom | Cause | Fix |
|---|---|---|
| The whole queue parks ~30 min after a worker is killed | a mid-build kill leaves a BUILDING row; the backpressure gate refuses new dispatch until `--build_stale_s` (1800 s) expires | anything that kills workers on a timer must reset the killed BUILDING rows to QUEUED (`lock_yield.sh` does this) |
| A job is parked HELD | `--workdir` does not exist, or an XID failed `--max_build_attempts` (3) times — often a stale or duplicate enqueue already on Borg | fix the cause, usually a fresh `tpu enqueue` from the right checkout, then `tpu requeue` |
| A row parked for hours builds stale code | a HELD row records a workdir PATH, not a commit, and packaging rsyncs it at build time | prefer a fresh enqueue from the intended tree over `tpu requeue` |

### The scheduler looks missing

**`tpu` answering "not built" usually means the PATH to its binaries moved, not
that anything is gone.** Blaze names an `output_base` per checkout root; two
environments on one checkout own two roots, and the last to build repoints
`blaze-out`, hiding the binaries in the other root. Run the tool to check it
(`tpu queue-status`), not a `ps` line — a long-lived worker keeps running its
original inode.

| Symptom | Cause | Do |
|---|---|---|
| `rc=127 command not found` | `tpu` is off `PATH` | `source ~/work/tpu_cmd/tpu_wrapper.sh` |
| `rc=1 "not built"`, worker still submitting | the symlink flipped to a root lacking the binaries | nothing; the resolver searches the real roots |
| `rc=1 "not built"`, nothing ever built | genuinely absent | rebuild serially, never during another build |

Rebuild serially:
```bash
cd /google/src/cloud/qiaos/run_amply_workspace/google3 && \
  blaze build experimental/users/qiaos/tpu_utils:{route_check,queue_cli,jobd}
```

### PENDING that is not a failure

**Queued is not failed, and PENDING for hours can be normal on an oversold
pool.** Read the clause after the colon in `waiting: <clause>`: an
availability-fetch failure parks a job in QUEUED with `attempts` unchanged and
looks just like waiting behind demand. `last_reason` is a snapshot rewritten only
on change, not a heartbeat — text unchanged for N minutes proves the state has
not changed, not that the failure continues; re-derive with a probe. `tpu quota`
reads `available 0` as its steady state: a fully-consumed floor is not a blocker,
the job still queues and runs.
