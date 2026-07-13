# TPU Operations Guide

TPU jobs are scheduled, launched, monitored, and resumed by **`unified_infra`** (see
`infra_overview.md`, `infra_scheduling.md`, `infra_resume.md`). This file covers the
**user-facing day-to-day**: checking jobs and logs through `infra`, finding/holding
cards, diagnosing stale "zombie" holders, and the **legacy `tpu` (xibo) commands that
are still worth using** for a few specific tasks.

The old `xibo_tpu_manager` + `tpu_manager/MONITOR.py` no longer schedule or resume
jobs. Do **not** use `tpu run` / `tpu resume` / `tpu rerun` / `qsqa` / `data.json`
to manage jobs — use `infra`. A handful of legacy `tpu` subcommands remain the best
tool for their job and are listed under "Legacy `tpu` commands" below.

## Quick Reference (new infra)

Mutating commands need `export INFRA_DAEMON_URL=http://10.130.0.83:8765` (already in
`.bash_aliases`). Read-only commands need nothing.

```bash
infra check                  # rich status of YOUR jobs (alias: ics)
infra list                   # flat list
infra info <job_id>          # placement, stage_dir, output.log, dispatch log,
                             #   nodes (checkpoint trail), dead_runs (failed attempts)
infra logs <job_id> [-f]     # tail output.log   (cl/gl/tl aliases also work)
infra queue --types=… --regions=… -- main.py --config=…   # launch (see infra_scheduling.md)
infra debug --types=v5p-64 --minutes=60                   # reserve a card, run nothing
infra kill <job_id>          # stop a running/reserved job
infra cancel <job_id>        # remove a pending job
infra clean [ids…]           # forget terminal job-chains
```

Shell helpers (`.bash_aliases`): `ics` = `infra check`; `ka` opens
`jobs.json`+`pool.json`; `cl <id>` opens that job's `output.log`; `gl <id>` prints
its path; `tl <id>` tails it; `gest <id>` prints its `stage_dir`. `<id>` is a full
8-char hex id or a unique prefix.

## Finding Available TPUs (`tou`)

`tou` (interactive alias for `wrap_master.py`) shows live TPU visibility — zone,
IDLE/BUSY, and holder Linux users:

```bash
python /kmh-nfs-ssd-us-mount/code/qiao/work/tpu_dls/wrap_master.py
```

By default it prints cached audit records from
`/kmh-nfs-ssd-us-mount/code/qiao/work/tpu_dls/.tpu_audit_records.json`. Use
`--cache false` to force a fresh audit (SSHes to each TPU and runs
`sudo lsof -t /dev/accel* /dev/vfio/*`). In non-interactive shells, run the python
command directly.

Caveats:

- `users=[…]` are the **remote Linux users** holding accelerator devices, not
  necessarily the experiment owner. Under unified_infra, each job runs as its own
  remote Linux account (`job.user`), so the holder usually *is* the owner; older
  shared-tooling jobs often ran as remote user `sqa`.
- IDLE alone is **not** proof a card is free — a freshly created job can look IDLE
  before worker processes appear. The daemon also re-checks reservations and
  environment before launch.
- Capacity comes from the 申卡 allocator (`tpu_request_manager`) + the idle sweep,
  not from you hand-picking cards. To grab a card for **interactive** work, use
  `infra debug` rather than manually claiming one.

## Reading Logs

```bash
infra logs <job_id>           # tail output.log
infra logs <job_id> -f        # follow
infra logs <job_id> --what dispatch -f   # the mount/zhan/launch (dispatch) log
cl <job_id>                   # open output.log in the editor
gl <job_id>                   # print the output.log path
grep -E "eval_accuracy|eval epoch|Error|Traceback|saved to" "$(gl <job_id>)" | tail -20
```

Logs live at `/kmh-nfs-ssd-us-mount/logs/<user>/<taskname>/<ts>_<salt>_<vm>_<zone>__…/output.log`.
`infra info <job_id>` also prints `dead_runs` lines pointing at the `output.log` of
each **previous failed attempt** — use those to debug a job that resumed past a crash.

### Reading job status correctly

- `infra check` is the authoritative live view. One row per job-chain; the `RST`
  column is `restarts·lastCkptStep`.
- A "could not open log file" note on a card is not by itself failure — confirm the
  job is training by grepping the log for recent step counts.
- Checkpoint-save output (orbax messages) can look like errors in naive scanners.
  Always read the actual log before concluding a job failed; rely on the daemon's
  `classify.py` decision (see `infra_resume.md`), not a bare "Traceback" match.

## Diagnosing Stale / Zombie TPU Holders

A "zombie" = a remote process still holding the accelerator while no live job owns
it. Do not decide from `tou` alone. Confirm all three signals:

1. **Infra state:** `infra check` / `infra info` shows no active job for that exact
   TPU. (For any leftover legacy jobs, the old `data.json` is history, not an owner.)
2. **Window state:** no live tmux window on the infra host launched that process.
3. **Remote state:** `sudo lsof -t /dev/accel* /dev/vfio/*` still finds Python
   processes whose `ps` cmdline points at an old `--workdir=…`, often `PPID=1`, stale
   log mtime, no matching live job.

For a full report across `sqa`-held TPUs, the legacy helper still works:

```bash
detect_zombie            # = python tpu_manager/detect_zombie.py  (--refresh / --no-bell)
```

It refreshes the `tou` cache, SSHes to BUSY TPUs whose holders include Linux user
`sqa`, reads the real accelerator-holding processes, extracts `--workdir=…`, and
correlates with manager/tmux state. Treat its `data.json` correlation as **legacy**;
cross-check against `infra info` for unified_infra jobs.

To inspect a TPU's real holders directly:

```bash
gcloud compute tpus tpu-vm ssh <tpu> --zone <zone> --worker=all --ssh-flag=-n \
  --command 'PIDS=$(sudo lsof -t /dev/accel* /dev/vfio/* 2>/dev/null | sort -u);
    for p in $PIDS; do
      ps -p "$p" -o user=,pid=,ppid=,etimes=,etime=,args= -ww;
      readlink -f "/proc/$p/cwd" 2>/dev/null;
    done'
```

Only call it a zombie when the remote holder is real **and** the infra/tmux owner is
gone or superseded. If the log is still moving and a matching active job exists, it
is a live job even if a scanner prints "Error".

## Legacy `tpu` Commands (still useful)

These xibo `tpu` subcommands are **kept** because they remain the most convenient
tool. `tpu` is aliased to the xibo `tpu.py`. Do **not** use them for scheduling or
resume — only for the specific tasks below.

- **`tpu cc …`** — cross-region checkpoint copy. Still the helper for copying a final
  `checkpoint_<step>` to all allowed eval regions before an eval-only run (see
  `vlm_checkpointing.md` / `infra_resume.md`).
- **`tpu mount-disk <name> [--force]`** — manually mount the NFS disk + zone-local
  env wheels on a card. Infra does this automatically at dispatch; use it for ad-hoc
  work on a card you reserved yourself (e.g. a hand-run remote debug). Require both
  the `.disk_mounted` marker **and** `mountpoint -q /kmh-nfs-ssd-us-mount`; put
  `--force` after the name.
- **`tpu kill-remote <tpu> [remote_user=<user>]`** — kill stale remote processes on a
  VM. Bare `tpu kill-remote <tpu>` is an all-user kill; scope it with
  `remote_user=<user>`. Kill only matching process PIDs and device-holder PIDs; do
  **not** kill PPIDs (many workers have PPID 1).
- **`tpu zhan <tpu> <user>`** — manually write a reservation lock. Prefer `infra
  debug` for interactive holds; use `zhan` only for one-off manual coordination.
  Remember infra honors foreign (non-`unified`) locks and will refuse a card you
  hold under your own name (see `infra_overview.md`).

## Handling Preemptions

Spot TPUs get preempted. **The daemon auto-resumes** — do not manually relaunch a
preempted job. A resumable failure puts the same job back to PENDING and it
re-dispatches onto the next matching card, restoring from its last checkpoint (see
`infra_resume.md`). Only intervene to:

- Stop a job whose **bug** you want to fix: `infra kill <id>` (running) or
  `infra cancel <id>` (pending), fix, then `infra queue` again.
- Clean a **confirmed zombie** remote holder the daemon's teardown couldn't reach:
  `tpu kill-remote <tpu> remote_user=<user>` after verifying with `lsof`/`ps`.
