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

---

## Closing stale windows

After a job errors and is relaunched in a new window, clean up the old window:

```bash
tmux kill-window -t <user>:<window_id>
```
