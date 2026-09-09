# RAFT — optical flow reproduction + per-site optimizer (science line)

Reproduce RAFT-small (Teed & Deng, ECCV 2020) on the authors' Chairs+Things
(C+T) schedule, then compare ordinary AdamW against the per-relative-distance
normalize-then-sum optimizer (`../research/normalize_then_sum.md`). The
applicability audit that chose RAFT-small and verified the gradient decomposition
is `../archive/audits/20260907-raft-applicability-elt-dev.md`.

## Where Everything Is

| Thing | Path |
|---|---|
| Code (source of truth, git) | `~/work/raft/` = upstream `princeton-vl/RAFT` @ 2888e15 verbatim + `train_repro.py` (seeded, resumable, timed trainer with the authors' semantics), `site_grads.py` (per-call copies, distance buckets, `GroupAdamW`), `scripts/run_ct.sh` (C -> T -> evaluate.py chain), `scripts/box_prepare_data.sh`, `scripts/check_site_grads.py` |
| Box copy | `qiaos-4a100:~/work/raft` (copied by tarball; compare md5 before a launch), venv `.venv` (torch 2.9.1+cu129, opencv-headless, scipy, wandb). Reach it with `--account=qiaos@google.com` (`../gcp_gpu_ssh.md`). |
| Data (ONLY on `qiaos-4a100`) | `~/datasets/{FlyingChairs_release,FlyingThings3D,Sintel,KITTI}`, symlinked as `~/work/raft/datasets`; FlyingThings3D holds TRAIN + left camera only (all RAFT reads: 22,390 png per pass, 44,780 pfm). Markers `~/datasets/_markers/ok.*`, log `~/datasets/_logs/prepare.log`. |
| Pretrained | `~/work/raft/models/raft-small.pth` etc. (the authors' models.zip) |
| Logs / checkpoints | `~/work/raft/logs/<run>.log`, `~/work/raft/checkpoints/<run>/{last.pt,step_N.pth,<run>.pth,train_log.jsonl}` |
| W&B | project `raft-repro`, entity `zhh24-massachusetts-institute-of-technology`; groups `raftsmall_C_baseline`, `raftsmall_CT_baseline` |
| Results tab | EqR workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, tab **`raft-small (qiaos)`** (resolve by title). Row 1 banner = the protocol; header row 2: config / seed n / train loss C / train loss T / Chairs val EPE / Sintel clean / Sintel final / KITTI EPE / KITTI F1-all / chart C stage / chart T stage / logdir / notes (each stage is its own W&B run, so a row carries both group links). Multi-seed cells `mean +- sd`; official-report and eval-reproduction rows sit above the train-reproduction row (`../research/result_logging.md`). |

## The Recipe (declared reference schedule)

`train_standard.sh` with `--small`: Chairs 100k steps, batch 10, lr 4e-4, crop
368x496, wd 1e-4; then Things 100k, batch 6, lr 1.25e-4, crop 400x720, wd 1e-4,
restored from the Chairs weights; gamma 0.8, 12 update iterations, clip 1.0,
fp32. **One GPU per run equals the authors' 2-GPU DataParallel for RAFT-small**:
the small model has no BatchNorm (instance norm / none), so splitting the batch
changes nothing but numerics. The paper trained its small model for 160k
iterations in total (supplement Table 2) with an unrecovered stage split; the
100k+100k schedule above is our declared reference, not the paper's exact run.

Measured on A100-40GB: 0.19 s/step, 6.3 GiB at Chairs shape -> C stage ~5.5 h,
C+T ~12 h per run (Sintel validation every 5k steps adds ~1 h to T).

## Targets And The Validated Evaluation

Paper Table 1, `Ours (small)` after C+T: Sintel(train) clean **2.21** / final
**3.35**; KITTI-15(train) epe **7.51** / F1-all **26.9** (median of 3 seeds).
The released `raft-small.pth` evaluated with our copy of `evaluate.py` gives
Sintel 2.125 / 3.276 and KITTI 7.65 / 25.30, which matches torchvision's
independent evaluation of the same ported weights (`C_T_V1`: 2.1231 / 3.279,
7.6557 / 25.2801) to 0.003 EPE. So the eval pipeline is right, and the paper
numbers describe a different seed than the released checkpoint.

**Reproduced (2026-09-08, GCE box, authors' evaluate.py after C+T 100k+100k):**

| seed | Sintel clean | Sintel final | KITTI epe | KITTI F1-all |
|---|---|---|---|---|
| 1234 | 2.088 | 3.240 | 7.149 | 24.19 |
| 1 | 2.290 | 3.405 | 7.625 | 25.92 |
| 2 | 2.208 | 3.333 | 7.512 | 25.46 |

The median seed (2) lands on the paper's 2.21 / 3.35 / 7.51 within 0.02 EPE;
seed spread is ~0.2 EPE on Sintel and ~0.5 on KITTI, so a one-seed comparison
between arms is below the noise. Chairs-stage final val EPE was 1.73-1.77 on both
boxes (8 Borg ranks: baseline 1.734-1.773, reldist at the same lr 1.770-1.804).

**Borg, 4 seeds per arm, same recipe (H100, `tpu enqueue`; eval jobs run the
authors' `evaluate.py` one rank per checkpoint). Mean +- sd over seeds 1234/1/2/3;
results tab `raft-small (qiaos)` rows 7-12 in the EqR workbook:**

| arm (same lr 4e-4 / 1.25e-4) | Chairs val (end of C) | Sintel clean | Sintel final | KITTI epe | KITTI F1 | XIDs (C / T / eval) |
|---|---|---|---|---|---|---|
| baseline | 1.753 +- 0.019 | 2.135 +- 0.118 | 3.438 +- 0.127 | 7.293 +- 0.330 | 24.98 +- 0.75 | 287498529 / 287670760 / 287760103 |
| reldist | 1.791 +- 0.015 | 2.312 +- 0.060 | 3.386 +- 0.082 | 7.933 +- 0.510 | 26.19 +- 0.68 | 287498529 (ranks 4-7) / 287672556 / 287848141 |
| reldist + `--site_align ema` | 1.756 +- 0.012 | T stage running 09-09 | | | | 287679583 / 287847547 / pending |

Reading (2026-09-09): at the same lr, reldist is a mildly worse run, not a broken
one. Its train loss sits ~1.5% above the baseline's on Chairs from 5k steps on
(below it for the first 1k), Chairs val is +0.04 in every seed, Sintel clean
+0.18 and KITTI epe +0.64 / F1 +1.2 pt (Welch t 2-3), Sintel final on the
baseline; the Things-stage loss gap closes from 1.3% at 25k to 0.5% at 90k as
the lr decays. That is the signature of a 1.6-1.85x larger effective step on
the update block (next subsection), and the align arm, which removes exactly
that, tracks the baseline's Chairs-val curve at every 10k checkpoint. GCE single
seed (1234) agrees: reldist 2.298 / 3.319 / 8.287 / 26.16 (tab row 10; seeds
1 / 2 land 09-09 ~11:00Z), align seed 1234 Chairs val 1.791 (row 12).

## Per-Site Treatment (the experiment)

`--site_mode reldist`: the update block (motion encoder + ConvGRU + flow head)
runs each of the 12 calls on a fresh differentiable copy of its parameters; each
of the 12 supervised losses is differentiated separately; the (call i, loss j)
contribution goes to bucket n = j - i + 1. Sum of buckets == ordinary gradient
(`scripts/check_site_grads.py`, run it after ANY change to `site_grads.py`).
`GroupAdamW` keeps one AdamW state per (parameter, n); update = sum_n (1/n) U_n /
sqrt(sum_n 1/n^2); a parameter with a single bucket (flow head: the next round
detaches the flow) is divided by 1. The same global clip coefficient (clip 1.0
over the ordinary gradient) scales every bucket; decoupled wd once; fnet/cnet
stay on torch AdamW. `--site_merge sum` is the identity control (one AdamW on
the summed buckets = baseline). Cost, measured at the Chairs shape on A100-40GB:
0.49 s/step and 6.5 GiB against the baseline's 0.195 s/step and 6.3 GiB, i.e.
2.5x per step (12 per-loss backward passes over the recurrent prefix, 78
call-backwards instead of 12), so C ~14 h and C+T ~30 h per seed.

Run names are `raftsmall_<arm>_{C,CT}_s<seed>` from `scripts/run_arm.sh`
(the first baseline batch predates it and is named `raftsmall_{C,CT}_s<seed>`).
A launcher must never be edited in place while it runs; the tarball sync is safe
because tar replaces the inode.

## The Borg / XManager Path (GPU via `tpu enqueue`)

`~/work/raft/borg/` is the launch dir (the tpu wrapper packages the CWD): `main.py`
(the EqR-torch launcher contract: boot lamp, `known_only` flags, no I/O at
import, `device_count` guard), `borg_run.py` (streams the dataset tars from CNS
into the task's RAM disk, then re-execs one process per GPU; every rank is an
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

Measured on an h100-8 task running 8 independent ranks (XID 287466325): the
baseline does 4.9-5.0 steps/s and the reldist arm 2.35 steps/s, the same per-step
speed as one A100-40GB on the GCE box, so a Borg job buys 8 concurrent runs, not
a faster run. **DataLoader workers inside a PAR need the stdlib `fork` context**
(`train_repro --mp_context fork`): the patched `torch.multiprocessing` context
launches a resource tracker that needs `sys.executable`, which is None in a PAR
(`TypeError: expected bytes, NoneType found` on every rank, XID 287458555).

**Inside a PAR, fork the DataLoader workers once (`--persistent_workers 1`,
`--torch_threads 1`), never per epoch.** With the authors' per-epoch re-fork, every
rank hung at step 6669, the first epoch boundary after the step-5000 validation
(XIDs 287466325 and 287485326; the watchdog dump shows the main thread in
`_data_queue.get` and the freshly forked workers never answering). The two
boundaries before the validation were fine, so the parent's state after
validation (CPU tensor ops start the intra-op thread pool) is what the fork
cannot survive. Persistent workers are forked before any validation or CNS push.
`train_repro --watchdog_secs` writes `stall_<step>.txt` with every thread's stack
to the run dir and pushes it to the mirror; read it before guessing.

`tmp_ram_fs_gib` / `ram_gib` ride inside `--launch=` (only `load_from`,
`wandb_resume_id`, `cell` are refused there). Local gates before any enqueue:
`RAFT_ALLOW_CPU=1 python borg/main.py --config=local_cpu_smoke --data_root=<dir with
a fake tar> ...` (real re-exec, staging, mirror, resume), then a `blaze build` of a
`rsync -aL` copy under `$STAGE_WS_ROOT/experimental/qiaos/` plus `--import_check`
(torch 2.14.0a0+google3 imports take ~60 s).

**Data on CNS: `/cns/go-d/home/qiaos/raft_data/` (metro cmh, group quota).**
`tars/{FlyingChairs_release,Sintel_training,KITTI_training,FlyingThings3D_frames}.tar`
for RAM-disk staging; `raw/FlyingThings3D/optical_flow/TRAIN/*/*/{into_future,into_past}/left/*.pfm`
(259 GiB) read per file by the indexed loader (`datasets_cns.py` +
`things_index.json`, enumeration identical to the authors' class;
`frame_utils._open` routes `/cns/` paths through epath). Measured from an h100-8
task in `ga` reading go-d (`configs/io_probe.yml`, XID 287524092): one thread
82 MB/s, 14 files/s, p50 64 ms per 5.9 MB pfm; eight threads 881 MB/s,
149 files/s, p50 56 ms. Four Things-stage ranks need ~120 files/s (~700 MB/s),
but **forked DataLoader workers cannot read CNS** (the parent already holds the
RPC state; every worker died at once, XID 287659289), so the Things stage stages
the raw flow into the RAM disk too: `stage_raw` (`RAFT_THINGS_FLOW_MODE=ramdisk`,
`tmp_ram_fs_gib=330`, `ram_gib=420`) copies the 40,302 flow files the index
names (233.5 GiB) in 233 s at 1 GiB/s with 16 threads; the frames tar takes
190 s. Per-file CNS reads are fine from the main process only. The metro list must stay
`cmh` until the data is mirrored elsewhere. Route used: box -> GCS
(`gs://qiaos-viscam-data-multi/raft_data`, ~1 GiB/s) -> cloudtop (337 MiB/s) ->
`fileutil cp` (`scripts/cloudtop_stage_to_cns.sh`, sizes verified both hops); the
SSH relay measured 29 MB/s and is the wrong tool for 330 GiB.

### The bucket directions are correlated; `--site_align ema` measures and removes it

The sqrt divisor assumes pairwise-orthogonal bucket updates. Measured on the Borg
Chairs job (same lr in both arms), the update block's update norm under reldist
is 1.85x the baseline's early and 1.56x from 30k steps on, with equal bucket
norms, i.e. a mean pairwise cosine of ~0.45 falling to ~0.28. `--site_align ema`
keeps, per parameter tensor (`--site_align_scope block` for one scalar), a
bias-corrected EMA of r = ||sum_n w_n U_n|| / sqrt(sum_n w_n^2 ||U_n||^2) and
divides the merged update by it, so it keeps one Adam step's norm whatever the
correlation (r == 1 for a single bucket). Measured at steps 100-200: baseline
5.2-5.4e-3, reldist 9.5e-3, align 5.3-5.4e-3. Arm name `align`
(`run_arm.sh <gpu> <seed> align --site_mode reldist --site_align ema`,
Borg `configs/chairs_align.yml`).
Outcome on Chairs (4 Borg seeds, 09-09): align's end-of-C val 1.746-1.774 (mean
1.756) equals the baseline's 1.753 +- 0.019, against 1.791 +- 0.015 for
unaligned reldist; the measured EMA ratio r drifts 1.59 (28k) -> 1.53-1.55
(90k). So the norm inflation explains the whole reldist deficit on Chairs;
whether the per-site grouping buys anything beyond parity is what the align
Things stage + eval (XID 287847547, chained) decides.

## Traps Already Paid For

- **NumPy 2.5 on the box breaks the authors' `readFlow`** (`int()` of a 1-element
  array); `core/utils/frame_utils.py` in our copy indexes it. Symptom: every
  `.flo` dataset (Chairs, Sintel) dies in the DataLoader worker.
- **`import datasets` resolves to HuggingFace's package on any machine that has
  it** (the cloudtop does); `train_repro.py` inserts `core` at `sys.path[0]`, the
  authors' scripts append it. The box venv has no HF datasets today.
- **`pgrep -f <script>` inside a `gcloud ssh --command` matches the ssh shell
  itself** and reads as "already running". Guard launches with `flock`, verify
  by `pgrep -af '^bash /full/path'` or by the log advancing.
- Freiburg serves ~10-27 MiB/s per client IP in total, regardless of connection
  count; a second box got nothing. The 310 GiB flow archive is the long pole
  (~3-4 h). `aria2c -c` resumes; the prep script is idempotent by markers.
- `wandb.util.generate_id` no longer exists (wandb 0.29); the trainer makes its
  own id and keeps it in `checkpoints/<run>/wandb_id.txt`.
