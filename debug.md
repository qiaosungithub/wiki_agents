# Remote Debug Guide

## Overview

Remote debugging runs your code on a TPU VM using a minimal toy config. The pipeline is:

1. `ka.sh` — select the target VM and infer its zone
2. `debug_remote.sh` — stage code, clear old state, SSH in, and run

---

## Scripts

### `ka.sh`

Sets environment variables used by other scripts:

- `VM_NAME` — the TPU VM name (edit to switch targets)
- `ZONE` — inferred automatically from the VM name (e.g. `v6e` → `us-central1-b`)
- `DATA_ROOT`, `CONDA_PY_PATH`, `TFDS_DATA_DIR`, etc.

**Usage:** sourced by other scripts. Can also be sourced manually:

```bash
source ka.sh                          # use default VM from file
source ka.sh <vm_name>                # specify VM, auto-infer zone
source ka.sh <vm_name> <zone>         # specify both
```

When adding a new VM family, update the zone-inference block in `ka.sh`.

### `debug_remote.sh`

Stages the current working directory to an NFS staging path, then SSHes into all workers and runs `main.py` with a debug config.

```bash
bash debug_remote.sh                  # use default VM from ka.sh
bash debug_remote.sh <vm_name>
bash debug_remote.sh <vm_name> <zone>
```

What it does internally:
1. Sources `ka.sh` to get `VM_NAME` / `ZONE`
2. `rsync`s the current directory to `$STAGEDIR` on NFS (excluding `.git`, `__pycache__`, etc.)
3. Clears the GCS log directory (prevents checkpoint-already-exists errors on rerun)
4. Kills any existing `main.py` processes on all workers
5. SSHes into all workers and runs `main.py --config=…:remote_debug`
6. Tees stdout/stderr to `$LOGDIR/output.log`

**Add a debug config** (`configs/remote_debug_config.yml`) with a very small dataset, small model, few steps, and all eval tasks enabled so you can test the full pipeline end-to-end quickly.

---

## Common pitfalls and fixes

### Orbax "destination already exists"

Orbax refuses to overwrite an existing checkpoint. On rerun, the script must clear the GCS checkpoint directory first:

```bash
GCS_LOGDIR=gs://your-bucket/path/to/debug-logdir
gsutil -m rm -r ${GCS_LOGDIR} 2>/dev/null || true
```

Add this to `debug_remote.sh` before the SSH command.

### NFS stale file handles (`.nfs*` files)

NFS creates `.nfs*` placeholder files for open handles. `rm -rf` will fail silently or non-zero on these if `set -e` is active. Use:

```bash
sudo rm -rf $LOGDIR 2>/dev/null || sudo mv $LOGDIR ${LOGDIR}_old_$(date +%s) 2>/dev/null || true
```

The `mv` fallback handles the case where rm fails but the directory can be renamed.

### JAX subprocess claiming the TPU

If your eval or postprocessing spawns a subprocess that also imports JAX, it will try to claim the TPU already held by the parent process and fail with:

```
RuntimeError: Unable to initialize backend 'tpu': ABORTED: The TPU is already in use
```

Fix: set `JAX_PLATFORMS=cpu` in the subprocess environment:

```python
env = os.environ.copy()
env["JAX_PLATFORMS"] = "cpu"
subprocess.run(cmd, env=env, check=True)
```

This only affects the child process; the parent's JAX state is unmodified.

### Batch size not divisible by local device count

JAX sharding requires the batch dimension to be divisible by the number of devices it's sharded across (typically `jax.local_device_count()`). The last batch from a DataLoader with `drop_last=False` may be smaller.

Fix: always pass `batch_size=batch_size` to your batch-preparation function so it pads the last batch with zeros and sets an `is_pad` mask. Skip padded entries in the output loop:

```python
batch = prepare_batch_data(raw_batch, batch_size=batch_size)
for item, out, is_pad in zip(batch["aux"], out_strs, batch["is_pad"].tolist()):
    if is_pad:
        continue
    ...
```

### All processes must iterate the same number of times

JAX collective operations (all-gather, reduce-scatter) are blocking: every process must call them the same number of times. If different processes have different dataset sizes and iterate their DataLoaders independently, ranks with fewer samples will exit the loop early while others hang waiting for the collective.

Fix options:
- Use a fixed loop count (`fixed_num_steps`) based on the max samples across all processes, and provide dummy batches when a rank's loader is exhausted.
- Use a sampler that pads all ranks to the same count.

---

## Monitoring the run

The log is written to `$LOGDIR/output.log` on NFS and is accessible immediately from the head node:

```bash
tail -f $LOGDIR/output.log
```

Use `grep` to filter for key events:

```bash
tail -f $LOGDIR/output.log | grep -E "Error|Traceback|step=|acc=|score="
```

If the VM is preempted, SSH will fail with exit code 255 or messages like `ABORTED` / `resource not found`. Re-claim the VM and rerun.
