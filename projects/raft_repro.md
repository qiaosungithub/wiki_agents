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
the summed buckets = baseline). Cost: 12 per-loss backward passes over the
recurrent prefix, ~3-4x a baseline step (measure; do not quote until measured).

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
