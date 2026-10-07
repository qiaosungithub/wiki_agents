---
name: job-submit
description: Submit a job or a batch to the cluster with `tpu enqueue`, settle placement, verify it is really running, and fix the classic submission bugs.
---

# Submitting A Job

How the queues, the smart router, `--power` / `--archs`, metro locality, tiers,
groups, the budget gate, and the launcher work is
[knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md);
passing a checkpoint to a job (`LOAD_FROM`, `restart_from`) is
[knowledge/infrastructure/resume-contracts.md](../../../knowledge/infrastructure/resume-contracts.md).
This skill owns the step-by-step and the classic submission bugs. A job that
fails or goes silent after it is submitted is
[job-diagnose](../job-diagnose/SKILL.md).

**Before you submit anything after a large code change, run the CPU
`local_debug` path first** ([local-debug skill §Local debug, then remote, before a real run](../local-debug/SKILL.md#local-debug-then-remote-before-a-real-run)). A build plus a queue wait plus a schedule is the
expensive way to find a bug a workstation finds in two minutes.

The default: `cd` into the code directory, `tpu enqueue` with all usable
`--archs` (among v4, v5p, v6e, v6p, v7) and several data `--metros`. That is the
whole submit step — the always-on TPU dispatch-worker (kept alive by the `*/2`
ops watchdog) is the sole builder and drains the queue on its own. You do NOT
start a `tpu build-worker`; there is no separate TPU build-worker on this host.

---

## Submitting A Job, Step By Step

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
  never one of each (§Classic Bugs And What To Do). Drop an arch only when it cannot run the job
  (e.g. per-chip HBM too small); size with `--power` so the router scales the
  slice per generation.
- `--metros` is PLURAL on enqueue; `--metro` does not exist here.
- `--job_name` is REQUIRED (the local queue handle); `exp_name=` is the
  XManager / CNS handle. Both name the TASK and what distinguishes this launch,
  not just the model.
- Training passes `--tier=PROD`. Do not pass `--group`, nor `--priority>0`
  without the operator's permission — the standing exception is a small remote
  debug run at `--priority=1` ([local-debug skill §Local debug, then remote, before a real run](../local-debug/SKILL.md#local-debug-then-remote-before-a-real-run)).
- A checkpoint-sharded resume also passes `--topology_locked`, so the router only
  moves it within the same mesh geometry (`v6p-32` and `v7-32` are both `2x4x4`;
  `v6e-32` is not) — see [knowledge/infrastructure/resume-contracts.md](../../../knowledge/infrastructure/resume-contracts.md).

**Step 4 — Drain.** Nothing to start: the always-on TPU dispatch-worker drains
the queue. `tpu queue-status` shows progress.

**Step 5 — Verify it is REAL.** An XID is not a job and `state: RUN` is not
evidence anything runs ([job-diagnose skill §`state: RUN` Is Not Evidence That Anything Runs](../job-diagnose/SKILL.md#state-run-is-not-evidence-that-anything-runs)): confirm `VMGROUP_STATE_RUN` at the
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
limit order ([`tools/limit_order.sh`](../../../tools/limit_order.sh) `status` shows `BLOCKING`), and a
launcher-side failure that never reached the scheduler (an XID with no work unit,
or no XID — [job-diagnose skill](../job-diagnose/SKILL.md)).

**Commands:**

| Command | Does |
|---|---|
| `tpu enqueue --power=… --archs=… --metros=… --job_name=… --launch=…` | Add a run to the local queue. `--power` and `--archs` are required together. |
| `tpu queue-status` (alias `tpu qs`) | The local queue plus, live, why each job waits or where it is placeable. |
| `tpu build-worker start` \| `stop` \| `status` | The serial build-worker in its own tmux session; one build in flight. |
| `tpu dequeue <job_id>` | Remove a not-yet-live entry. Refuses a non-terminal row by default (fail-closed); a QUEUED/BUILD_REQUESTED/BUDGET_DEFERRED/HELD row has no XID, so `--force` drops it completely — a refusal is not a deadlock ([§A refused dequeue is not a deadlock](../job-diagnose/SKILL.md#a-refused-dequeue-is-not-a-deadlock--only-submittedrunning-have-an-xid)). |
| `tpu requeue [job_id…]` | Return HELD job(s) to QUEUED after you fix the cause. |
| `tpu route-tick [--reroute --nodry_run]` | One router pass by hand; `--reroute` cancels and re-queues jobs PENDING past 10 min. |
| `tpu queue …` | Deprecated one-shot synchronous submit; the fallback when no worker is up. |

---

## Classic Bugs And What To Do

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
| The whole queue is parked for a shift | someone enqueued `--priority>0`; the queue drains highest-priority-first | default is `priority=0`; `--priority>0` is operator-only, except a small remote debug run at `--priority=1` ([local-debug skill §Local debug, then remote, before a real run](../local-debug/SKILL.md#local-debug-then-remote-before-a-real-run)) |
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
