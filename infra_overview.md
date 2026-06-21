# Unified Infra Overview

Use this guide for the architecture and shared invariants of `unified_infra`, the
group-wide TPU job scheduler. For scheduling / queue / TPU-selection rules read
`infra_scheduling.md`. For resume/rerun, the single-job chain, and checkpoint
discovery read `infra_resume.md`. For user-facing TPU commands (including the
still-useful legacy `tpu` helpers) read `tpu.md`.

`unified_infra` **replaces** the old per-user mix of `xibo_tpu_manager` (launch /
mount-disk / tmux) and the local `tpu_manager/MONITOR.py` (auto-resume) with one
standalone system that any user, on any machine, drives through shared SSD state.
The old xibo CLI is **not** fully retired — a few of its commands are still the
best tool for the job (see "Legacy xibo coexistence" below) — but **job
scheduling, dispatch, monitoring, and resume now all go through `infra`**, not
through `MONITOR.py` / `tpu run` / `tpu resume`.

Project-local source snapshots of the old system are preserved verbatim in
`project_agents_archive.md`. Legacy sandbox notes are in
`external_memory_archive.md`.

## Where The Code And State Live

- Repo: `/kmh-nfs-ssd-us-mount/code/qiao/work/unified_infra`.
- Canonical architecture doc: `unified_infra/README.md` (read it for the full
  design; this guide is the agent-facing summary).
- Python package: `unified_infra/infra/` (daemon, scheduler, monitor, classify,
  resume, store, …). Resume-decision policy: `unified_infra/docs/resume_rules.md`.
  Failure-mode/recovery doc: `unified_infra/docs/robustness.md`.
- Thin CLI launcher (any machine): `unified_infra/bin/infra`.
- Daemon supervisor: `unified_infra/bin/infrad`.
- **All authoritative state lives under `$INFRA_STATE_DIR`** (default
  `unified_infra/state/`): `pool.json` (pending queue), `jobs.json` (jobs that
  left the queue — active or terminal), `tpus.json` (managed-TPU registry),
  `signals.jsonl` (ready-TPU inbox), `worker_logs/`, `mount_locks/`,
  `errors.log`, `daemon.health`, `.state.journal`.
  Staging snapshots and each job's `output.log` follow the NFS convention, not
  `state/` (see "Key paths" in `infra_scheduling.md`).

## Shell Setup (already in `/home/sqa/.bash_aliases`)

```bash
export INFRA_STATE_DIR="/kmh-nfs-ssd-us-mount/code/qiao/work/unified_infra/state"
export INFRA_DAEMON_URL="http://10.130.0.83:8765"   # daemon host internal IP
alias infra="/kmh-nfs-ssd-us-mount/code/qiao/work/unified_infra/bin/infra"
alias ics="infra check"        # rich status of YOUR jobs (was old `tcs`)
ka()        # opens jobs.json + pool.json in the editor
cl <id>     # opens that job's output.log
gl <id>     # prints that job's output.log path
tl <id>     # tail -f that job's output.log
gest <id>   # prints that job's stage_dir
```

`<id>` is a job id (full 8-char hex or a unique prefix). These helpers resolve it
across both `pool.json` and `jobs.json`.

- **Read-only** commands (`check`, `list`, `info`, `logs`) read the shared SSD
  state directly and need **no** env.
- **Mutating** commands (`queue`, `kill`, `cancel`, `clean`, `priority`,
  `recover`, `signal`) talk to the daemon's HTTP control plane and require
  `INFRA_DAEMON_URL` to be set (it is exported above). Without it the CLI errors
  `INFRA_DAEMON_URL is required for mutating infra commands` — this is required
  on **every** machine, including the daemon host (there is no Unix-socket
  fallback).

## Architecture (one paragraph)

A single **central infra host** runs `infra daemon` 24/7 and is the **only writer**
of authoritative JSON state. Each job is one **tmux window** (in the `infra` tmux
session on that host) running the staging + remote-launch logic. An external
TPU-allocation system (`tpu_request_manager`, the 申卡 script) sends the daemon a
**signal** the moment it has a ready TPU; the daemon picks one pending job to run
on it. Users anywhere run thin `infra` CLI commands; they never launch anything
themselves. Mutating commands submit a bounded request to the daemon's
private-network HTTP control plane, which queues it; the daemon's main loop drains
the queue and performs the serial `handle_request` path.

### Daemon main loop (`infra/daemon.py`, ~10s interval)

1. **drain HTTP requests** (the queued mutating commands).
2. **drain signals** (`signals.jsonl`) → dispatch a pending job onto each ready TPU.
3. **`monitor.reconcile()`** — reap finished jobs, classify failures, resume/rerun,
   handle kills, expire debug reservations, detect stuck dispatch.
4. **idle-card sweep** every ~5 min — re-run scheduling for each managed TPU that
   holds no active job (reclaims cards freed by a finished/killed job or whose
   signal was missed).
5. **watchdog + health write** (`daemon.health`).

> `daemon control timeout` (HTTP 503) on a mutating command means the main loop
> was busy (long reconcile / idle-sweep) and did not drain the queued request
> within `CONTROL_HTTP_REQUEST_TIMEOUT` (30s). It is **transient** — retry. It does
> *not* mean the daemon is down; check `infrad status` if retries keep failing.

### Dispatch and teardown are non-blocking

The daemon never blocks on slow prep. On each signal it **atomically claims** one
job (removes it from the pool under the exclusive state lock — the job lock, so two
cards can never grab the same job) and **spawns a detached worker** (`infra.worker`)
that does zhan + mount-disk + opens the tmux window, then loops on. Each worker's
mount/zhan/launch output is captured to a per-job **dispatch log** on the SSD
(`infra info <id>` shows the path). Teardown (the remote `gcloud ssh` kill) also
runs in a background thread; a teardown that can't confirm the chips were freed
leaves the job non-terminal and its card reserved, and retries next loop.

Signals can arrive duplicated/concurrently, so the daemon ignores a signal for a
card that already has an active job — two jobs never land on one card.

## Running The Daemon (infra host only)

Run the daemon as a **standalone** process via the supervisor — do **not** run
`infra daemon` inside a tmux session you might later kill (that would cascade and
kill the separate `infra` session holding the jobs' windows):

```bash
infrad start | stop | restart | status | log
```

A `restart` is **non-disruptive**: it kills only the daemon PID; running jobs keep
going and the new daemon re-adopts them from persisted state. The two HTTP env
vars are **not** set by infrad for you — export them in infrad's environment first
or startup fails with `HTTP control is not configured`:

```bash
INFRA_CONTROL_HTTP_HOST=10.130.0.83 INFRA_CONTROL_HTTP_PORT=8765 infrad start
```

`infra recover` self-heals state after a crash / lost info.

## User Isolation & Admin

Two distinct identities:

- **Logical identity** = `$INFRA_USER` (else `$USER`), stored as `job.user`.
  **Spoofable**; used only for *attribution* — scheduling weight and the remote
  Linux user. Not a privilege.
- **Trusted identity** = the real OS login, stored as `job.owner_os` at creation.
  This is the **authorization** identity for kill/cancel/scoping.

Rules:

- **Remote Linux isolation** (default): each job runs on the TPU VM as a separate
  Linux account `job.extra["remote_user"]` (defaults to `job.user`), created with
  passwordless sudo. Processes, Python envs, and `.disk_mounted` markers are
  per-Linux-user.
- **Scoping/ownership is by the trusted OS user.** By default every command
  (`check`, `list`, `info`, `logs`) shows **only jobs you created**, and
  `kill`/`cancel` act **only on your own** jobs. `INFRA_USER=<victim>` cannot view
  or act on a victim's jobs.
- **Admins** (`sqa`, `lyy`, `zhh`; trusted OS user, override `INFRA_ADMINS`) keep
  full power: `--all` to view everyone's jobs, and `kill`/`cancel`/`info`/`logs`
  on any user's job. A non-admin `--all` falls back to own.
- **Signal authentication.** A ready-TPU signal drives daemon-owned GCP ops, so it
  is a privilege boundary. `infra signal` is admin-only, but the inbox file is
  writable, so for real enforcement drop a shared HMAC key at
  `$INFRA_STATE_DIR/.signal.key` (`chmod 600`); the daemon then drops any unsigned
  or forged signal. Without the key it runs in legacy unauthenticated mode and
  warns at startup.

## Reservation Locks (shared with legacy xibo)

Central reserve locks live in `/kmh-nfs-ssd-us-mount/code/qiao/tpu_lock`, the
**same dir xibo uses**, keyed by exact TPU lease name with a 30-min TTL.

- Everything infra reserves is written as `unified_<tpu>_<YYYY-MM-DD_HH-MM-SS>`
  (override with `INFRA_RESERVE_USER`). So xibo / `tou` see a **single holder,
  `unified`**, for all infra-held cards.
- A lock whose user is **not** `unified` is **foreign** (xibo / manual). Infra
  honors it as reserved, **never removes or expires it** (fail-closed), and `zhan`
  refuses a foreign-held card. Only `unified_*` locks get the TTL, renewal, and
  release.
- Set `INFRA_TPU_LOCK_DIR` to isolate a test daemon from production locks.

## Error Log (daily maintenance)

Failures the daemon **cannot cleanly resolve on its own** are appended to
`$INFRA_STATE_DIR/errors.log` (TAB-separated `UTC <TAB> category <TAB> message
<TAB> key=value …`):

| category | meaning | typical action |
|---|---|---|
| `teardown_failed` | a job's remote kill (gcloud SSH) didn't confirm; card kept reserved, retries each loop | check the TPU is reachable; if deleted, next loop clears it; else `gcloud … ssh` in and kill stragglers |
| `mount_lock` | per-TPU mount lock under `state/mount_locks/` couldn't be opened/locked | check dir ownership/permissions and disk space |
| `lost_reservation` | a RUNNING job's `zhan` lock was taken by another holder (TTL lapse / daemon outage); job failed onto a fresh card | usually self-heals via resume; investigate if frequent |
| `dispatch_failed` | a job gave up after `MAX_DISPATCH_ATTEMPTS` mount/launch attempts | read its dispatch log (`infra info <id>` → dispatch path) for the real mount error |
| `dispatch_stuck` | a job sat in STARTING with a live window but no worker past the timeout | inspect the orphaned window via `tmux attach -t infra` |

Triage:

```bash
tail -n 50 "$INFRA_STATE_DIR/errors.log"
cut -f2 "$INFRA_STATE_DIR/errors.log" | sort | uniq -c | sort -rn   # by category
infra info <job_id>                    # placement + dispatch log path
infra logs <job_id> --what dispatch    # the mount/launch output
```

Repeated `teardown_failed` / `lost_reservation` for the same TPU is the strongest
signal a human is needed (a wedged VM, or two systems fighting over a card).

## Legacy Xibo Coexistence

The old xibo CLI is **kept** because some commands are still the most convenient
tool. Use the new `infra` commands for everything about *jobs* (queue / status /
logs / kill / cancel / resume), but these legacy `tpu` helpers remain useful:

- `tpu cc …` — cross-region checkpoint copy (still the helper for copying a final
  `checkpoint_<step>` to all allowed eval regions). See `vlm_checkpointing.md`.
- `tpu mount-disk <name> [--force]` — manual mount-disk on a card (e.g. before a
  hand-run remote debug). Infra mounts automatically at dispatch; this is for
  ad-hoc work on a card you reserved yourself.
- `tou` / `wrap_master.py` and `detect_zombie` — live TPU visibility and zombie /
  stale-holder diagnosis. See `tpu.md`.
- `tpu kill-remote <tpu> [remote_user=<user>]` — kill stale remote processes left
  on a VM. See `tpu.md`.

Do **not** use `MONITOR.py`, `tpu run`, `tpu resume`, `tpu rerun`, `qsqa`, or the
xibo `data.json`/`queue.json` for scheduling anymore — those are superseded by
`infra queue` and the daemon. The old `data.json` is no longer authoritative live
state.

## What Lives Where

| Topic | File |
|---|---|
| User-facing TPU commands, `tou`, `detect_zombie`, legacy `tpu` helpers, zombie diagnosis | `tpu.md` |
| Queue semantics, scheduling/sampling, TPU selection, signals (申卡), debug runs | `infra_scheduling.md` |
| Single-job chain, nodes, `dead_runs`, resume-vs-terminal classify, checkpoint discovery, recovery | `infra_resume.md` |
| VLM checkpoint and dataloader details that affect resume decisions | `vlm_checkpointing.md` |
| Cleanup of stagedirs, local disk, daemon/worker temp state | `storage_cleanup.md` |
