# RAFT — optical flow reproduction + per-site optimizer (science line)

Reproduce RAFT-small (Teed & Deng, ECCV 2020) on the authors' Chairs+Things
(C+T) schedule, then compare ordinary AdamW against the per-relative-distance
normalize-then-sum optimizer
([Chapter 2 §What the per-site optimizer is](#what-the-per-site-optimizer-is)).
The applicability audit that chose RAFT-small and verified the gradient
decomposition is
[archived](../../archive/audits/20260907-raft-applicability-elt-dev.md). This
page owns the setting, the declared reference recipe, the targets, what the
per-site optimizer is, what the arms have shown, and the facts of the JAX port.
How to run a job on either the GCE box or Borg is the
[raft-runs skill](../../harness/skills/raft-runs/SKILL.md). Chapter 1 is the setting and what the eval
numbers mean, Chapter 2 what the arms have shown, and the last part the JAX
port, a separate codebase.

---

## Chapter 1 — The Setting And What The Metrics Mean

### Where everything is

| Thing | Path |
|---|---|
| Code (source of truth, git) | `~/work/raft/` = upstream `princeton-vl/RAFT` @ 2888e15 verbatim + `train_repro.py` (seeded, resumable, timed trainer with the authors' semantics), `site_grads.py` (per-call copies, distance buckets, `GroupAdamW`), `scripts/run_ct.sh` (C -> T -> evaluate.py chain), `scripts/box_prepare_data.sh`, `scripts/check_site_grads.py` |
| Box copy | `qiaos-4a100:~/work/raft` (copied by tarball; compare md5 before a launch), venv `.venv` (torch 2.9.1+cu129, opencv-headless, scipy, wandb). Reach it with `--account=qiaos@google.com` ([gcp-gpu-ssh skill](../../harness/skills/gcp-gpu-ssh/SKILL.md)). |
| Data (ONLY on `qiaos-4a100`) | `~/datasets/{FlyingChairs_release,FlyingThings3D,Sintel,KITTI}`, symlinked as `~/work/raft/datasets`; FlyingThings3D holds TRAIN + left camera only (all RAFT reads: 22,390 png per pass, 44,780 pfm). Markers `~/datasets/_markers/ok.*`, log `~/datasets/_logs/prepare.log`. |
| Pretrained | `~/work/raft/models/raft-small.pth` etc. (the authors' models.zip) |
| Logs / checkpoints | `~/work/raft/logs/<run>.log`, `~/work/raft/checkpoints/<run>/{last.pt,step_N.pth,<run>.pth,train_log.jsonl}` |
| W&B | project `raft-repro`, entity `zhh24-massachusetts-institute-of-technology`; groups `raftsmall_C_baseline`, `raftsmall_CT_baseline` |
| Results tab | EqR workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, tab **`raft-small (qiaos)`** (resolve by title) |

### The declared reference recipe

**`train_standard.sh --small`: Chairs 100k steps, batch 10, lr 4e-4, crop
368x496, wd 1e-4; then Things 100k, batch 6, lr 1.25e-4, crop 400x720, wd 1e-4,
restored from the Chairs weights; gamma 0.8, 12 update iterations, clip 1.0,
fp32.** One GPU per run equals the authors' 2-GPU DataParallel for RAFT-small:
the small model has no BatchNorm (instance norm / none), so splitting the batch
changes nothing but numerics. The paper trained its small model for 160k
iterations in total (supplement Table 2) with an unrecovered stage split, so the
100k+100k schedule is our declared reference, not the paper's exact run.

Measured on A100-40GB: 0.19 s/step, 6.3 GiB at Chairs shape, so the C stage is
~5.5 h and C+T ~12 h per run (Sintel validation every 5k steps adds ~1 h to T).

### The targets, and why the eval pipeline is trusted

Paper Table 1, `Ours (small)` after C+T (median of 3 seeds): Sintel(train) clean
**2.21** / final **3.35**; KITTI-15(train) epe **7.51** / F1-all **26.9**.

**The eval pipeline agrees with an independent implementation to 0.003 EPE, so a
reproduction is judged against those paper numbers.** The released
`raft-small.pth` evaluated with our copy of `evaluate.py` gives Sintel 2.125 /
3.276 and KITTI 7.65 / 25.30, which matches torchvision's independent evaluation
of the same ported weights (`C_T_V1`: 2.1231 / 3.279, 7.6557 / 25.2801). The
paper numbers describe a different seed than the released checkpoint.

---

## Chapter 2 — What The Experiments Have Found

### What the per-site optimizer is

**`--site_mode reldist` runs each of the update block's 12 calls (motion encoder
+ ConvGRU + flow head) on a fresh differentiable copy of its parameters,
differentiates each of the 12 supervised losses separately, and sends the (call
i, loss j) contribution to bucket n = j - i + 1.** The sum of buckets equals the
ordinary gradient (`scripts/check_site_grads.py`, run it after ANY change to
`site_grads.py`). `GroupAdamW` keeps one AdamW state per (parameter, n); the
update is sum_n (1/n) U_n / sqrt(sum_n 1/n^2), and a parameter with a single
bucket (the flow head, since the next round detaches the flow) is divided by 1.
The same global clip coefficient (clip 1.0 over the ordinary gradient) scales
every bucket; decoupled wd once; fnet/cnet stay on torch AdamW.
`--site_merge sum` is the identity control (one AdamW on the summed buckets =
baseline). Cost at the Chairs shape on A100-40GB: 0.49 s/step and 6.5 GiB against
the baseline's 0.195 s/step and 6.3 GiB, i.e. 2.5x per step (12 per-loss backward
passes over the recurrent prefix, 78 call-backwards instead of 12), so C ~14 h
and C+T ~30 h
per seed.

### The baseline reproduces the paper

**On the GCE box the authors' `evaluate.py` after C+T 100k+100k reproduces the
paper within noise** — 3 seeds, the median seed 2 landing on 2.21 / 3.35 / 7.51
within 0.02 EPE:

| seed | Sintel clean | Sintel final | KITTI epe | KITTI F1-all |
|---|---|---|---|---|
| 1234 | 2.088 | 3.240 | 7.149 | 24.19 |
| 1 | 2.290 | 3.405 | 7.625 | 25.92 |
| 2 | 2.208 | 3.333 | 7.512 | 25.46 |

Seed spread is ~0.2 EPE on Sintel and ~0.5 on KITTI, so a one-seed comparison
between arms is below the noise; use 4 seeds. Chairs-stage final val EPE is
1.73-1.77 (8 Borg ranks: baseline 1.734-1.773, reldist at the same lr
1.770-1.804).

### At the same lr, reldist is a mildly worse run, not a broken one

**Matched on lr, reldist trains ~1.5% higher loss on Chairs from 5k steps on
(below the baseline for the first 1k), the signature of a 1.6-1.85x larger
effective step on the update block, not a bug.** Borg, 4 seeds
per arm (1234/1/2/3, H100, eval one rank per checkpoint):

| arm (same lr 4e-4 / 1.25e-4) | Chairs val (end of C) | Sintel clean | Sintel final | KITTI epe | KITTI F1 |
|---|---|---|---|---|---|
| baseline | 1.753 +- 0.019 | 2.135 +- 0.118 | 3.438 +- 0.127 | 7.293 +- 0.330 | 24.98 +- 0.75 |
| reldist | 1.791 +- 0.015 | 2.312 +- 0.060 | 3.386 +- 0.082 | 7.933 +- 0.510 | 26.19 +- 0.68 |

Chairs val is +0.04 in every seed, Sintel clean +0.18 and KITTI epe +0.64 / F1
+1.2 pt (Welch t 2-3), Sintel final ties the baseline; the Things-stage loss gap
closes from 1.3% at 25k to 0.5% at 90k as the lr decays. A GCE 3-seed run agrees (reldist
Chairs val 1.777 +- 0.007; wandb groups raftsmall_reldist_{C,CT}):

| seed | Sintel clean | Sintel final | KITTI epe | KITTI F1 |
|---|---|---|---|---|
| 1234 | 2.298 | 3.319 | 8.287 | 26.16 |
| 1 | 2.252 | 3.453 | 7.471 | 26.01 |
| 2 | 2.038 | 3.384 | 7.972 | 26.41 |

The pooled 7-vs-7 comparison over both boxes reads Sintel clean +0.10, final
0.00, KITTI epe +0.57, F1 +1.1 pt for reldist at the same lr.

### `--site_align ema` removes the norm inflation, which explains the whole deficit

**The sqrt divisor assumes orthogonal buckets, and `--site_align ema` divides the
merged update back to one Adam step's norm whatever the correlation.** Measured on
the Borg Chairs job (same lr in both arms), the update block's update norm under
reldist is 1.85x the baseline's early and 1.56x from 30k on with equal bucket
norms, i.e. a mean pairwise cosine of ~0.45 falling to ~0.28. The knob keeps, per
parameter tensor (`--site_align_scope block` for one scalar), a bias-corrected
EMA of r = ||sum_n w_n U_n|| / sqrt(sum_n w_n^2 ||U_n||^2) and divides the merged
update by it (r == 1 for a single bucket). Measured update norms at steps
100-200: baseline 5.2-5.4e-3, reldist 9.5e-3, align 5.3-5.4e-3. Arm name `align`
(`run_arm.sh <gpu> <seed> align --site_mode reldist --site_align ema`, Borg
`configs/chairs_align.yml`).

**Aligned, reldist matches the baseline on Chairs, so the norm inflation explains
the whole reldist deficit there.** Over 4 Borg seeds align's end-of-C val is
1.746-1.774 (mean 1.756), equal to the baseline's 1.753 +- 0.019, against 1.791
+- 0.015 for unaligned reldist; the measured EMA ratio r drifts 1.59 -> 1.53-1.55
over 28k-90k steps. Whether the per-site grouping buys anything beyond parity is
what the align Things stage and eval decide.

### Two-band mode (`--site_mode d1`): the owner's simplification

**Instead of 12 relative-distance buckets, `--site_mode d1` separates only two
bands, as in the charLM / nanoGPT call-diagonal lines: G1 = sum_j dL_j/dtheta_j
(call and loss in the same round; the flow head is G1-only by structure) and
G_rest = total - G1.** Two Adam states, update (U_1 + w U_rest) / sqrt(1 + w^2)
with `--site_w w` (w = 0 is Adam on G1 alone; the flow head has divisor 1).
`site_grads.two_band()` costs T single-call backwards plus one full backward that
also yields the fnet / cnet gradients: 3.8 vs 5.3 steps/s on the A100 (1.35x,
against reldist's 2.5x). The structural band-2 membership is read off
`bucket_by_distance` on the first batch (`CallCopies.rest_names`), never from
numerically nonzero moments. `check_site_grads.py` checks 4-5 cover it (bands ==
{bucket 1, sum of buckets >= 2} to 1e-5, d1+sum == baseline, w in {0, .5, 1}
round-trips); on a GPU the fnet bias-before-instance-norm gradients are ~1e-8
atomic-add noise, so the check compares fnet/cnet gradients relative to the
largest one. The two-band alignment ratio r at init is 1.0 / 1.22 / 1.29 for w =
0 / 0.5 / 1. The sweep is w in {0, 0.2, 0.5, 1.0} at the baseline lr, run names
`raftsmall_d1w{0,02,05,1}_{C,CT}_s<seed>`.

---

## The JAX/google3 port (RAFT-google-sqa -> raft_launch)

A separate codebase from the PyTorch `~/work/raft/` above. This is the JAX /
Scenic optical-flow trainer: git source of truth at `~/work/RAFT-google-sqa`
(github), launched from a non-git file-copy mirror `~/work/raft_launch` via `tpu
enqueue`. The wrapper relocates the `:main` py_binary into a renamed stagedir and
builds it there.

### A stray `configs/BUILD` in the launch workdir voids config packaging, so every launch dies with zero CNS bytes

**Keep `raft_launch/configs/BUILD` absent: if that file exists, Blaze treats
`configs/` as a subpackage boundary, and `data = glob(["configs/**/*.py"])` in
`raft_launch/BUILD` then captures zero files instead of the config payload.**
`configs/load_config.py` never reaches the relocated binary's runfiles, so every
job dies at flag-parse time with `OSError: Failed loading config file ... No such
file or directory: .../configs/load_config.py`. That happens before the first log
beacon, so the job writes zero bytes to CNS and `tpu check` reports "CODE BUG:
unrecoverable application failure", which reads as a pre-main() death with no
readable log. The glob is `allow_empty = True` (the canonical in-place build
wants a no-op there), so the empty result is silent at build time and only bites
at runtime.

It recurs because `raft_launch` is a file-copy mirror of the github repo. The
github `RAFT-google-sqa/configs/BUILD` is legitimate and must stay (it defines the
`:base_config` py3_library used for the Python imports), but any cp/rsync of
github into `raft_launch` drags it into the launch workdir, where it must not be.
Neither staging path removes it: the tpu wrapper's staging rsync and the `tpu
enqueue` snapshot (`queue_cli.py::_STAGE_EXCLUDES`) exclude only build and data
junk, not `BUILD`. A frozen enqueue snapshot that looks clean was taken after the
file had already been deleted, not self-healed. Only `configs/` is data-globbed,
so `configs/BUILD` is the one dangerous file; the other subpackage `BUILD` files
in the tree are legitimate and must be left alone.

The fix, and the sync procedure that keeps the broken state from coming back,
is in the [raft-runs skill](../../harness/skills/raft-runs/SKILL.md#syncing-the-jax-ports-launch-mirror).
