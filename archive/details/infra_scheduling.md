# Infra Scheduling, Queueing And TPU Selection

Use this guide to queue jobs, understand how the daemon picks which job runs on a
ready TPU, set allowed TPU types/regions, run interactive debug reservations, and
understand the 申卡 (TPU-request) signal path. Read `infra_overview.md` first for
the architecture, env vars, and state files. For resume/rerun and the single-job
chain, read `infra_resume.md`.

## Queueing A Job

All mutating commands need `export INFRA_DAEMON_URL=http://10.130.0.83:8765`
(already in `.bash_aliases`). Queue from your code dir, or re-queue from an
existing staged snapshot:

```bash
# Stage the current code dir and queue:
infra queue --types=v5p-64,v6e-32 --regions=us-central1,us-east5 --priority=10 \
    -- main.py --config=configs/load_config.py:remote_run

# Re-queue from an existing staged snapshot (no re-stage):
infra queue --stage-dir /…/staging/<user>/<ts>-…-code --types=v6e-32 --regions=… \
    -- main.py --config=configs/load_config.py:remote_run
```

- The command after `--` is the script + its `--config.*` overrides, run on the
  TPU. Set `logging.wandb_notes` here (see below), do not rely on config files.
- **Run-defining parameters belong in the staged dir's config files, NOT in CLI
  `--config.X` overrides** (user rule, 2026-07-13): when rerunning/varying a job,
  copy the staged dir, edit `configs/remote_run_config.yml` in place (lr changes,
  top-level `load_from:` for stage reruns, …) with a short comment naming the job
  id + rationale, then `infra queue --stage-dir <new-dir>` with a bare command.
  Reason: the staged dir alone must fully reproduce the run; CLI flags live only
  in pool.json. `wandb_notes` (the job name) is the one exception — it stays on
  the CLI. Resume safety is unchanged: monitor resumes inject env `LOAD_FROM`
  (env wins over the config file) and `strip_resume_overrides()` drops stale CLI
  flags. Stage-boundary rerun recipe: point `load_from:` at a log dir whose MAX
  saved ckpt is exactly the boundary step (e.g. 150000 → params-only restore +
  fresh optimizer, starts the next stage); pin `--regions` to the ckpt bucket's
  region (`gs://kmh-gcp-<region>/…`). First applied: ea923558.
- **Staging happens at queue time** by rsync from your code dir; staging
  **rejects code dirs > 1.5 MB** after standard excludes. The staged snapshot must
  be visible from the daemon host (shared NFS). The job keeps that exact
  `stage_dir` for its whole life and **re-dispatches from it on resume (no
  re-stage)** — so do not delete a staged snapshot still referenced by an
  active/resumable job (see `storage_cleanup.md`).
- The owner recorded is the **trusted OS user** running the CLI; the remote Linux
  user defaults to `$INFRA_USER`/`$USER`.
- There is no `qsqa` / xibo working-dir-id flow anymore. `infra queue` stages and
  enqueues directly; you do not pick a `dir=N` slot.

## How The Daemon Picks A Job (signal-driven sampling)

When a signal announces a ready TPU `(full_name, zone, type)`:

1. Collect **every pending job** in the global pool whose **allowed types** and
   **allowed regions** both admit this TPU.
2. Group the matching jobs by **user**. Sample one user with probability
   **proportional to that user's number of matching jobs** (so a user with more
   runnable-on-this-card jobs is more likely picked — fair sharing, verified ~2:1).
3. Within the chosen user, launch their **highest-priority** matching job; ties
   broken by **queue order** (earliest `queued_at` first).

Resuming jobs live in the **same** pool and participate in the same sampling — a
resume is the *same* job re-queued, not a new row (see `infra_resume.md`). Priority
is unchanged across the chain.

## Allowed Types / Regions And Pinning

- `--types` is family+size, e.g. `v5p-64`, `v6e-32`, matching the
  `<gen><variant>-<size>` form (`_extract_tpu_type`). `--regions` are short forms,
  e.g. `us-central1`, `us-east5`, `asia-northeast1-b` (a full zone like
  `us-east5-b` is also accepted and matches that exact zone).
- Empty allow-lists mean "any". A job runs on a card only if `matches_tpu(type,
  zone)` is true.
- **Pinning:** once a job has saved **any** checkpoint, it is **pinned to that
  checkpoint's exact type + zone** for the rest of its life — cross-zone checkpoint
  copy is intentionally not supported, so resume stays put. A from-scratch job with
  no checkpoint yet keeps its original broad allow-lists. So choose `--regions`
  carefully: the first checkpoint locks the job into one zone.

### Cost-class / data-locality conventions (carried over from xibo)

These are **operator conventions** for choosing `--types`/`--regions`, not enforced
by the daemon. They still matter for not wasting big cards:

- Low-cost jobs (e.g. `MAE-B`, `jit`, `unify-base`, `llava-1.5 reproduction`):
  `v6e-32` or `v5/v5p-64`. High-cost jobs: `v6e-64` or `v5/v5p-128`. GPT-B/DeiT:
  `v6e<=16` or `v5/v5p<=32`.
- `llava-1.5 reproduction` jobs are low-cost but **v5-only**: use exactly
  `v5/v5p-64`, not v6/v6e.
- `laion-400m` data is **only in `asia-northeast1-b`**: queue, resume, and rerun
  for such jobs may only use `--regions=asia-northeast1-b`.
- A `MAE-L` encoder + a large LM can OOM at compile time on v6e (≈31.25 G/chip).
  Big models need v5p (≈95 G/chip): restrict `--types` accordingly. (This was the
  `a2056e02` incident — a v6e-64 compile OOM, `Ran out of memory in memory space
  hbm. Used 68.44G of 31.25G`.)
- Preserve the cost-class tokens in `logging.wandb_notes` when re-queueing a
  variant; they are how a human reads the run's intended size, and the operator
  conventions above key off them.

## Idle-Card Sweep

Every ~5 min the daemon re-runs scheduling for each **managed TPU that holds no
active job** — cards freed by a finished/killed/released job, or acquired but whose
signal was missed. Managed TPUs are tracked in `state/tpus.json` (populated by
every signal). This reclaims capacity that would otherwise sit idle. You do not
need to re-signal a freed card; the sweep finds it.

## Debug Runs (interactive card reservation)

```bash
infra debug --types=v5p-64 --minutes=60
```

This queues a special job that **reserves a matching card and runs nothing**: it
mounts the disk, opens an **idle tmux window** in the staged code on the infra
host, and holds the reservation for `--minutes` (default 30). You attach (`tmux
attach -t infra`) and run your own commands. Debug jobs **never resume** and are
**not** liveness-checked; when the window closes or the time expires, the card is
released. The reservation is kept alive by re-`zhan` each loop.

This is the new-infra replacement for manually `tpu zhan`-ing a card for debugging.
For the in-VM debug-config smoke-run workflow (`debug_remote.sh`), see `debug.md`.

## 申卡 / Signals (ready-TPU transport)

The daemon does **not** create TPUs. An external allocator — `tpu_request_manager`
(the 申卡 script) — creates TPUs and, the moment it has one ready, calls:

```bash
infra signal <full_tpu_name> --zone=<zone> --type=<type>
```

(best-effort, flock-safe for concurrent allocator instances). This appends a record
to `state/signals.jsonl`; the daemon drains it and runs scheduling. The TPU is
assumed provisioned, but the daemon still runs mount-disk (idempotent) + a
`jax.devices()` check (all types except v5p, which is exempt) before launch. You
can also call `infra signal` by hand to point the daemon at a card you know is
ready. Signals can be **duplicated/concurrent**; the daemon dedupes by card.

**All 申卡 cards are one shared pool.** A card is **not** owned by the user in its
name (`zongyili-*`, `xianbang-*`, …) — every allocator signals the *same* daemon, and
the daemon schedules **any** user's pending job onto **any** matching ready card (the
fair-sampling above). So if you have a pending job and see a **READY card the daemon
isn't using**, it just means that card's allocator never signaled *our* daemon: it
won't be in `tpus.json`, and the idle-sweep only re-checks cards it already knows. Any
admin can run `infra signal <full_name> --zone=<z> --type=<t>` **by hand** to pull it
into the pool — your pending job then schedules onto it. The pre-launch mount-disk
(plus `jax.devices()` for non-v5p) still gates it, so hand-signaling a
wedged/unreachable card just fails dispatch and re-queues; it won't run a job on a
broken card. (Flaky SSH on a freshly-created spot card can make this mount step stall
or fail — try the next ready card.)

If the 申卡 script seems stuck, check it is appending to `signals.jsonl` and that
the daemon is draining (`infrad status`, `errors.log`). Signals may be HMAC-gated
(see `infra_overview.md`).

## Inspecting & Managing Queued/Running Jobs

```bash
infra check                 # rich status of YOUR jobs (alias: ics). One row per
                            # job-chain; RST column = restarts·lastCkptStep.
infra list                  # flat list of YOUR jobs (--all: admin only)
infra info <job_id>         # status + stage_dir / output.log / dispatch log + nodes
                            #   + dead_runs (every terminated attempt)
infra logs <job_id> [-f]    # tail output.log (or --what dispatch -f for mount/launch)
infra cancel <job_id>       # remove a PENDING job from the pool
infra kill <job_id>         # stop a RUNNING / RESERVED job (daemon tears it down)
infra clean [ids…]          # forget terminal job-chains (-n dry-run, --keep N,
                            #   --all admin). Default: all your terminal jobs.
infra priority <job_id> <n> # re-prioritize a pending job
```

- `cancel` only works on **pending** jobs; to stop a **running** job use `kill`.
- `pool.json` holds pending jobs; once a job leaves the queue (starting / running /
  reserved / finished / failed / killed / cancelled) it lives in `jobs.json`. A job
  you "cancelled" that still shows in `infra check` may actually be a different,
  near-identically-named job still pending — check the id, not the name.

## Key Paths

- NFS root (`DATA_ROOT`): `/kmh-nfs-ssd-us-mount`
- Staging: `/<DATA_ROOT>/staging/<user>/<ts>-<salt>-<commit>-code`
- Logs: `/<DATA_ROOT>/logs/<user>/<TASKNAME>/<ts>_<salt>_<vm>_<zone>__…/output.log`
- GCP creds: `/kmh-nfs-ssd-us-mount/code/qiao/<zone-short>.json`
- Reservation locks (shared with xibo): `/kmh-nfs-ssd-us-mount/code/qiao/tpu_lock`
- Infra state: `$INFRA_STATE_DIR` (`unified_infra/state/`) — see `infra_overview.md`.
