---
name: remote-control-operations
description: Launch a run through the remote-control git interface, run or restart its poller, status-mirror, and W&B daemons, and debug a commit that did not launch or a mirror that stopped updating.
---

# Operate The Remote-Control Job Interface

Read [knowledge/codebases/remote-control.md](../../../knowledge/codebases/remote-control.md)
first for how the interface works: the parts, the poller tick, the frozen
snapshot per commit, the run config schema and recorded statuses, the status
mirror, and the W&B reporting daemon with its per-run block. This skill owns
using it, running its daemons, and common debug.

Chapter 1 is using it and running the daemons; Chapter 2 is common debug.

---

## Chapter 1 — Using It (使用方法)

### The collaborator's side (launch a run)

1. Add or edit `run_config.yml` at the repo root, and commit the code you want
   to run alongside it.
2. `git push` to the tracked branch. That is the whole action: the push IS the
   launch.
3. Watch it in `google-job-info`: find `jobs/<xid>__<exp_name>/status.txt`, or
   read `npu_check.txt` / `index.md` at the repo root.

One commit fires exactly one run. To launch again, push another commit.

### The operator's side (run the pipeline)

Both halves run as resident tmux loops on `sqa-large`, restartable by hand:

```bash
# inbound poller
tmux new-session -d -s remote-control-poller \
    ~/work/remote-control-pipeline/poller_loop.sh

# outbound status daemon
tmux new-session -d -s google-job-info -c ~/work/google-job-info-daemon \
    'while true; do bash daemon.sh; echo "restart in 30s"; sleep 30; done'
```

The poller needs the `npu` shell function (its scripts source the wrapper) and a
live `npu build-worker` to actually submit. `run_poller.sh` is the cron variant
of one tick (`*/2` + flock), used instead of the tmux loop if you prefer cron.

### Test a commit without firing a job

```bash
cd ~/work/remote-control-pipeline
RC_DRY_RUN=1 RC_PROCESS_BACKLOG_ON_INIT=1 python3 poller.py
```

This does everything except invoke `npu`, printing the exact `npu enqueue`
command for each commit.

### The knobs (env vars)

Poller: `RC_REPO_URL`, `RC_BRANCH` (auto = origin default), `RC_SUBMIT_CMD`
(`npu`|`tpu`), `RC_DRY_RUN`, `RC_ALLOW_PRIORITY`, `RC_PROCESS_BACKLOG_ON_INIT`,
`RC_HOME`, `RC_POLL_INTERVAL`. Daemon: `GJI_REPO_DIR`, `GJI_INTERVAL`,
`GJI_BRANCH`; `generate.py` reads the registry from `NPU_JOBS_FILE`
(`~/lyy-work/.npu_jobs.json`).

### Operator: run the reporting daemon

```bash
tmux new-session -d -s wandb-upload -c ~/work/wandb-upload-daemon \
  'while true; do python3 daemon.py --once >> logs/daemon.log 2>&1; sleep 900; done'
```

Manual controls: `python3 daemon.py --once --dry-run` (plan the whole board,
change nothing); `python3 daemon.py --xid=<XID>` (upload one job, ignoring
state — the test path). On first start it BASELINES every pre-existing terminal
job (records them as skipped, uploads none), so only jobs finishing *after* the
daemon starts are uploaded — historical jobs are not back-filled.

---

## Chapter 2 — Common Debug (常用 debug)

### First-run baselining is not a bug

**The first ever poller tick BASELINES all existing commits (`SKIPPED_BASELINE`)
and launches nothing.** Turning the daemon on does not fire the repo's history;
only commits pushed after that fire. Set `RC_PROCESS_BACKLOG_ON_INIT=1` on the
first tick if you actually want the backlog.

### A processed commit is never retried

**Once a commit is in `state/processed.json` it is never processed again, in any
status.** This is deliberate: a flaky re-read cannot double-submit. So a
`FAILED_CONFIG` / `FAILED_DISPATCH` commit stays failed. To fix a bad run, push
a NEW commit; do not expect the poller to pick the old one up again. Re-running
the identical tree means either a new (empty) commit, or carefully deleting that
sha's entry from `processed.json`.

### Inbound (poller) symptoms

| Symptom | Likely cause | Check / fix |
|---|---|---|
| A pushed commit never launches | poller loop not running | `tmux has-session -t remote-control-poller`; `tail logs/loop.log`; restart |
| Commit dispatched, but job never schedules | poller only enqueues; the build-worker submits | `tmux has-session -t npu-build-worker`; `npu check`; `npu queue-status` |
| Commit shows `FAILED_CONFIG` | missing/invalid `run_config.yml`, or unknown `mode` | read the `error` in `processed.json`; fix yml; push a NEW commit |
| Commit shows `FAILED_DISPATCH` | enqueue ran but was refused | `error` field + `logs/poller.log` tail; fix, push new commit |
| A `priority>0` request had no effect | clamped by default | set `RC_ALLOW_PRIORITY=1` only if you really mean to park the shared queue |
| Want to preview the exact command | dry run | `RC_DRY_RUN=1 … python3 poller.py` |

### Outbound (daemon) symptoms

| Symptom | Likely cause | Check / fix |
|---|---|---|
| `google-job-info` stops updating | daemon loop not running | `tmux has-session -t google-job-info`; `tail google-job-info-daemon/logs/daemon.log` |
| Tick logs "empty output; aborting" | `npu check` returned nothing | the tick keeps the last good snapshot on purpose; check the wrapper / registry |
| No new commit though jobs changed | nothing truly changed, or push failing | `git -C ~/work/google-job-info log -1`; daemon.log for push errors |
| Job folder missing for a run | not on the board yet, or pruned when it left | folders mirror the live board; a vanished xid is pruned by design |

### Affects both halves

| Symptom | Cause | Fix |
|---|---|---|
| Nothing updates after a reboot | tmux does not survive reboot, and there is no `@reboot` cron | re-create both tmux sessions by hand ([§The operator's side (run the pipeline)](#the-operators-side-run-the-pipeline)) |
| `npu: command not found` when run by hand | the `npu` shell function only exists after sourcing the wrapper | `source ~/work/tpu_cmd/tpu_wrapper.sh` first |
| Confused which registry a job is in | `npu` = lyy's registry, `tpu` = sqa's; same CLI, different board | [knowledge/infrastructure/tpu-cli.md](../../../knowledge/infrastructure/tpu-cli.md); the pipeline uses `npu` by default (`RC_SUBMIT_CMD`) |
