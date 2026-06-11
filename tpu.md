# TPU Management Guide

## Infrastructure overview

TPU jobs run on Google Cloud TPUs managed via the `xibo_tpu_manager` system. Jobs are tracked in a Google Spreadsheet and a local `data.json`.

Key paths:
- TPU manager: `/home/jzc/zhichengjiang/working/xibo_tpu_manager/`
- Python binary: `/kmh-nfs-ssd-us-mount/code/hanhong/miniforge3/bin/python`
- Shorthand alias: `tpu` = `<python> <manager>/tpu.py`

---

## Finding available TPUs

```bash
python /kmh-nfs-ssd-us-mount/code/qiao/work/tpu_dls/wrap_master.py
```

Look for `[IDLE]` entries. Only use **v5p ≤ 64 chips** or **v6e ≤ 32 chips**.

`tou` is only an interactive shell alias from `/home/sqa/.bashrc`:

```bash
python /kmh-nfs-ssd-us-mount/code/qiao/work/tpu_dls/wrap_master.py
```

In non-interactive shells, run the Python command directly. By default it prints
cached audit records from:

```bash
/kmh-nfs-ssd-us-mount/code/qiao/work/tpu_dls/.tpu_audit_records.json
```

Use `--cache false` to force a fresh audit. A fresh audit SSHes to each TPU and
checks accelerator holders with:

```bash
sudo lsof -t /dev/accel* /dev/vfio/*
```

The `users=[...]` shown by `tou` are remote Linux users that hold accelerator
devices. They are not necessarily the real experiment owner. In particular, many
jobs launched through shared tooling run as remote user `sqa`.

---

## Claiming and launching a job

```bash
# 1. Claim the TPU (creates a lock so others don't take it)
tpu zhan <full_tpu_name> <user>

# 2. Launch the job (stages code, SSHes in, runs training)
tpu run <full_tpu_name> <user> dir=<N> [--config.key=value ...]
```

- `dir=N` selects which project directory to use (check with `tpu ls <user>`).
- Code is rsynced from the current working directory to a timestamped staging dir at launch. Always be on the right branch before launching.
- To bypass the "maybe dead job" confirmation prompt: add `-f` flag to `tpu run`.
- `tpu run` also accepts `--config.*` overrides passed through to the training script.

Shorthand (defined in `~/.bash_aliases`):
```bash
ftmd <full_name> <alias>   # = tpu zhan + tpu fang + tmd (mount disk)
```

---

## Monitoring jobs

```bash
tpu check <user>           # show all job statuses (alias: tcs = tpu check sqa)
tpu monitor <user> col=2   # live monitor (alias: tms)
```

### Attributing `sqa` TPU occupancy

When `tou` reports `users=['sqa']`, identify the real owner in this order:

For a full report across all currently `sqa`-held TPUs, use:

```bash
detect_zombie
```

This alias runs:

```bash
python /kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager/detect_zombie.py
```

The script uses `tou`'s shared cache, refreshes it if it is stale, SSHes to every
BUSY TPU whose remote holders include Linux user `sqa`, reads the real
accelerator-holding processes, extracts `--workdir=...`, and correlates that
logdir with xibo `data.json` plus local tmux windows. If `tou` refresh times out,
it falls back to the existing cache and marks stale selections with fresh remote
probe states such as `NOT_SQA`. Use `detect_zombie --refresh` when you explicitly
want to force a full `tou` refresh first.

The text report intentionally hides the remote `users=['sqa']` detail and prints
the inferred real owner as `holder=<user>`; different holders are colorized in
interactive output. Use `--no-color` for plain text output. By default the
command emits a terminal bell when the report finishes; use `--no-bell` to
disable it.

Output states:

| State | Meaning |
|-------|---------|
| `LIVE` | Remote holder matches an active xibo job/window. |
| `ZOMBIE` | Remote holder matches only inactive/superseded manager state. |
| `ZOMBIE?` | No `data.json` match and the local log is stale; likely orphaned, but verify before killing. |
| `UNKNOWN` | No `data.json` match, but the log is recent or unavailable. |
| `NOT_SQA` | `tou` cache selected the TPU, but a fresh remote probe shows the holder is no longer `sqa`. |

1. Match the TPU name or logdir against xibo manager state:

```bash
jq -r '.users | to_entries[] as $u
  | $u.value.job_data[]?
  | select(.tpu=="kmh-tpuvm-...")
  | [$u.key,.windows_id,.status,.job_tags,.log_dir] | @tsv' \
  /kmh-nfs-ssd-us-mount/code/zhichengjiang/working/xibo_tpu_manager/data.json
```

2. If manager status looks stale, SSH to the TPU and inspect the actual process
holding the accelerator:

```bash
gcloud compute tpus tpu-vm ssh <tpu> --zone <zone> --worker=all --ssh-flag=-n \
  --command 'PIDS=$(sudo lsof -t /dev/accel* /dev/vfio/* 2>/dev/null | sort -u);
    for p in $PIDS; do
      ps -p "$p" -o user=,pid=,ppid=,etimes=,etime=,args= -ww;
      readlink -f "/proc/$p/cwd" 2>/dev/null;
    done'
```

3. Map `--workdir=...` or the process cwd back to the owner. Common patterns:

| Path pattern | Real owner signal |
|--------------|-------------------|
| `/kmh-nfs-ssd-us-mount/logs/sqa/text-jit/...` | usually `bird` via xibo `data.json` |
| `/kmh-nfs-ssd-us-mount/logs/sqa/sqa_Flow_matching/...` | often `cyx` or `yinuo`; check `data.json` |
| `/kmh-nfs-ssd-us-mount/logs/sqa/yinuo_clip/...` | `yinuo` |
| `/kmh-nfs-ssd-us-mount/logs/sqa/paligemma-baseline/...` | `sqa` unless another xibo user owns the matching window |
| `/kmh-nfs-ssd-us-mount/logs/jzc/xibo_manager_for_agents/...` | `jzc` agent infra, not xibo `data.json` |

If `data.json` says `finished` or `error` but `lsof` still shows Python
processes, treat it as a stale or orphaned accelerator holder until the owner
confirms whether it should be killed.

Status meanings:
- `Compiling` — JAX compilation in progress (normal, takes a few minutes)
- `Running` / `Unknown` — training in progress
- `Error` — may be a real crash OR a false positive from checkpoint-save log output

**Always verify "Error" status** by reading the actual log file before taking action. Checkpoint saves print orbax messages that `tpu check` misclassifies as errors.

---

## Reading logs

```bash
# Get the log directory for a given tmux window ID
python /kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager/see_log.py <window_id>

# Then grep for eval results or errors
grep -E "eval_accuracy|eval epoch|Error|Traceback" <logdir>/output.log | tail -20
```

Logs live at `/kmh-nfs-ssd-us-mount/logs/<user>/<taskname>/<timestamp>_<tpu>_<zone>__<tags>/output.log`.

---

## Registering a new TPU

Use `register_tpu_and_write_spreadsheet` to register a new machine in both `data.json` and the Google Spreadsheet simultaneously:

```bash
python -c "
import sys
sys.path.insert(0, '/home/jzc/zhichengjiang/working/xibo_tpu_manager')
from utils.logger import register_tpu_and_write_spreadsheet
register_tpu_and_write_spreadsheet(
    full_name='kmh-tpuvm-v6e-8-spot-gzy-XXXXXX',
    zone='us-east5-b',          # or asia-northeast1-b
    pre=False,
    spot=True,
    tpu_alias='v6e-8-tmp53',    # with 'e' — used in tpu run commands
    spreadsheet_name='v6-8-tmp53'  # without 'e' — written to spreadsheet column B
)
"
```

**Do NOT use `tpu register` (interactive)** — it only writes `data.json`, not the spreadsheet. `tpu run` will fail with "not found in sheet" if the spreadsheet entry is missing.

### Alias naming convention

The alias number range encodes the zone:

| Zone | v6e-8 alias range | Example |
|------|-------------------|---------|
| asia-northeast1-b | `v6e-8-tmp201+` / `v6-8-tmp201+` | v6e-8-tmp201 |
| us-east5-b | `v6e-8-tmp51+` / `v6-8-tmp51+` | v6e-8-tmp51 |

Always check the zone of the machine before picking an alias number. Grep `data.json` to find the next free number in the correct range.

---

## Handling preemptions

Spot TPUs can be preempted. The auto-resume script handles this automatically:

```
/kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager/MONITOR.py
```

**Do not modify the resume logic** and **do not manually relaunch** preempted jobs — the monitor will do it.

When `MONITOR.py` sees an error job whose old TPU still exists but `tou` reports
it as BUSY, it logs `按卡没了处理` and reruns/resumes the job on another TPU. That
path does not kill the old TPU's remote Python processes. The `tpu resume` /
`tpu rerun` command kills processes on the new target TPU before launch, but it
does not clean the previous TPU after the replacement job has been created.

If `tou` still shows the old TPU busy after a rerun, verify the holder with
`lsof`/`ps` first. If it is a stale orphan from the old job, release the remote
device with:

```bash
tpu kill-remote <full_tpu_name>
```

`tpu clean <user>` and `tmux kill-window` clean local manager/tmux state; they do
not guarantee that orphaned remote `main.py` or `pt_data_worker` processes are
gone.

### Judging zombie TPU holders

Do not decide from `tou` alone. A faithful zombie judgement needs all three
signals:

1. Manager state: `tpu check <user>` or `data.json` has no active, current job
for the exact TPU/logdir. Old statuses such as `finished`, `killed`, `rerunned`,
`resumed`, or `error` with a newer child are not active owners.
2. Tmux state: the recorded local tmux window is gone, or the only remaining
window is not the one that launched the remote process.
3. Remote state: `sudo lsof -t /dev/accel* /dev/vfio/*` still finds Python
processes whose `ps` command line points at an old `--workdir=...` logdir, often
with `PPID=1`, stale log mtime, and no matching live window.

Only call it a zombie when the remote holder is real but the manager/tmux owner
is gone or superseded. If the log is still moving and there is a matching active
window/job, it is a live job even if `tpu check` prints `Error` or `Unknown`.

---

## Closing stale windows

After a job errors and is relaunched in a new window, clean up the old window:

```bash
tmux kill-window -t <user>:<window_id>
```
