---
name: raft-runs
description: Run RAFT-small reproduction and per-site optimizer arms on the GCE box or as a Borg GPU job, stage the FlyingChairs and FlyingThings3D data, record a results row, and keep the JAX port's launch mirror buildable.
---

# RAFT Runs — Running Research Against This Line

This skill relies on [the RAFT knowledge page](../../../knowledge/codebases/raft.md) for
where the code, data, logs, and W&B project live, the declared reference recipe
and its measured cost, the targets, what each optimizer arm is, what the arms
have shown, and the JAX port. Reaching the box is [gcp-gpu-ssh skill](../gcp-gpu-ssh/SKILL.md).

## Two ways to run: the GCE box and Borg

**The GCE box `qiaos-4a100` runs one seed per GPU; a Borg h100-8 job runs 8
independent single-GPU ranks at the same per-step speed as one A100-40GB
(baseline 4.9-5.0 steps/s, reldist 2.35 steps/s), so a Borg job buys 8 concurrent
runs, not a faster run.** The box holds the only dataset copy, so compare md5
before a launch. Run names are `raftsmall_<arm>_{C,CT}_s<seed>` from
`scripts/run_arm.sh` (the first
baseline batch predates it and is named `raftsmall_{C,CT}_s<seed>`). A launcher
must never be edited in place while it runs; the tarball sync is safe because tar
replaces the inode.

## The Borg / XManager path

`~/work/raft/borg/` is the launch dir (the tpu wrapper packages the CWD):
`main.py` (the EqR-torch launcher contract: boot lamp, `known_only` flags, no I/O
at import, `device_count` guard), `borg_run.py` (streams the dataset tars from
CNS into the task's RAM disk, then re-execs one process per GPU; every rank is an
independent single-GPU `train_repro` run named by `configs/<mode>.yml`),
`reexec.py` / `beacon.py` copied from EqR-torch-maze128 with `RAFT_*` env names.
Checkpoints go to `/tmp/raft_runs/<name>` and are mirrored after every save to
`$CHECKPOINT_BUCKET/runs/<name>/` (`train_repro --mirror_dir`); a restarted task
restores `last.pt` from the mirror. Beacon JSONL: `$CHECKPOINT_BUCKET/sanity/`.

```bash
cd ~/work/raft/borg && source ~/work/tpu_cmd/tpu_wrapper.sh
tpu enqueue --power=h100-8 --archs=h100 --tier=PROD --metros=cmh --job_id=<id> \
  --launch=group=9,config=chairs_repro,exp_name=<what-this-launch-is-for>,tmp_ram_fs_gib=64,ram_gib=160
```

`tmp_ram_fs_gib` / `ram_gib` ride inside `--launch=` (only `load_from`,
`wandb_resume_id`, `cell` are refused there). **Gate every enqueue locally
first**: `RAFT_ALLOW_CPU=1 python
borg/main.py --config=local_cpu_smoke --data_root=<dir with a fake tar> ...`
exercises the real re-exec, staging, mirror and resume, then a `blaze build` of
an `rsync -aL` copy under `$STAGE_WS_ROOT/experimental/qiaos/` plus
`--import_check` (torch 2.14.0a0+google3 imports take ~60 s).

## DataLoader workers inside a PAR: fork once, before any validation

**Inside a PAR the DataLoader needs the stdlib `fork` context
(`train_repro --mp_context fork`).** The patched `torch.multiprocessing` context
launches a resource tracker that needs `sys.executable`, which is None in a PAR
(`TypeError: expected bytes, NoneType found` on every rank).

**Fork the workers once (`--persistent_workers 1`, `--torch_threads 1`), never
per epoch.** With the authors' per-epoch re-fork every rank hung at step 6669,
the first epoch boundary after the step-5000 validation; the two boundaries
before validation were fine, so the parent's state after validation (CPU tensor
ops start the intra-op thread pool) is what the fork cannot survive. Persistent
workers are forked before any validation or CNS push. `train_repro
--watchdog_secs` writes `stall_<step>.txt` with every thread's stack to the run
dir and the mirror; read it before guessing.

## Data on CNS, and why the Things stage stages raw flow to RAM

**Data on CNS: `/cns/go-d/home/qiaos/raft_data/` (metro cmh, group quota); the
metro list must stay `cmh` until the data is mirrored elsewhere.**
`tars/{FlyingChairs_release,Sintel_training,KITTI_training,FlyingThings3D_frames}.tar`
stage into the RAM disk;
`raw/FlyingThings3D/optical_flow/TRAIN/*/*/{into_future,into_past}/left/*.pfm`
(259 GiB) is read per file by the indexed loader (`datasets_cns.py` +
`things_index.json`, enumeration identical to the authors' class;
`frame_utils._open` routes `/cns/` paths through epath).

**Forked DataLoader workers cannot read CNS** (the parent already holds the RPC
state; every worker dies at once), so per-file CNS reads work only from the main
process and the Things stage stages the raw flow into the RAM disk too:
`stage_raw` (`RAFT_THINGS_FLOW_MODE=ramdisk`, `tmp_ram_fs_gib=330`, `ram_gib=420`)
copies the 40,302 flow files the index names (233.5 GiB) in 233 s at 1 GiB/s with
16 threads; the frames tar takes 190 s. Measured CNS read rates (h100-8 in `ga`
reading go-d, `configs/io_probe.yml`): one thread 82 MB/s, 14 files/s, p50 64 ms
per 5.9 MB pfm; eight threads 881 MB/s, 149 files/s, p50 56 ms, against the ~120
files/s (~700 MB/s) four Things-stage ranks need. The upload route was box -> GCS
(`gs://qiaos-viscam-data-multi/raft_data`, ~1 GiB/s) -> cloudtop (337 MiB/s) ->
`fileutil cp` (`scripts/cloudtop_stage_to_cns.sh`, sizes verified both hops); the
SSH relay measured 29 MB/s and is the wrong tool for 330 GiB.

## What a results row holds

**Each stage is its own W&B run, so a row carries a link for both.** Columns:
config / seed n / train loss C / train loss T / Chairs val EPE / Sintel clean /
Sintel final / KITTI EPE / KITTI F1-all / chart C stage / chart T stage / logdir
/ notes. Multi-seed cells are `mean +- sd`; official-report and eval-reproduction
rows sit above the train-reproduction row. The write mechanics are generic
([result-logging skill](../result-logging/SKILL.md)).

## Traps already paid for

- **NumPy 2.5 on the box breaks the authors' `readFlow`** (`int()` of a
  1-element array); `core/utils/frame_utils.py` in our copy indexes it. Every
  `.flo` dataset (Chairs, Sintel) otherwise dies in the DataLoader worker.
- **`import datasets` resolves to HuggingFace's package on any machine that has
  it** (the cloudtop does); `train_repro.py` inserts `core` at `sys.path[0]`, the
  authors' scripts append it. The box venv has no HF datasets.
- **`pgrep -f <script>` inside a `gcloud ssh --command` matches the ssh shell
  itself** and reads as "already running". Guard launches with `flock`, verify by
  `pgrep -af '^bash /full/path'` or by the log advancing.
- **Freiburg serves ~10-27 MiB/s per client IP in total**, regardless of
  connection count, and a second box gets nothing; the 310 GiB flow archive is
  the long pole (~3-4 h). `aria2c -c` resumes; the prep script is idempotent by
  markers.
- **`wandb.util.generate_id` no longer exists (wandb 0.29)**; the trainer makes
  its own id and keeps it in `checkpoints/<run>/wandb_id.txt`.

## Syncing the JAX port's launch mirror

Why a stray file in the launch mirror kills every launch is
[knowledge/codebases/raft.md §A stray `configs/BUILD` in the launch workdir voids config packaging, so every launch dies with zero CNS bytes](../../../knowledge/codebases/raft.md#a-stray-configsbuild-in-the-launch-workdir-voids-config-packaging-so-every-launch-dies-with-zero-cns-bytes).

Fix: sync with `raft_launch/sync_from_github.sh`, which mirrors github with
`--exclude=/configs/BUILD` and then strips any pre-existing copy, so the broken
state cannot be produced. After a sync done any other way, run
`raft_launch/strip_configs_build.sh`, which is idempotent, removes only
`configs/BUILD`, and fails closed if `configs/load_config.py` is missing. Never
delete the github `RAFT-google-sqa/configs/BUILD`.
