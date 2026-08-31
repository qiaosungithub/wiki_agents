# RNN Unroll — Adding Problem (science line)

A SCIENCE line probing gradient propagation in a vanilla RNN on the **adding
problem** (long-range credit assignment). Not a product; the deliverable is a
falsifiable answer + a clean notebook. The operator drives pivots; keep runs
patient (no compute churn). Native lab notebook `~/work/rnn_unroll/research/
AUTORESEARCH_LOG.md` is the SOURCE OF TRUTH — read it end-to-start first.

## The Question
Adding problem at sequence length T: two marked positions, output = sum of the
two marked values. Naive BPTT gradients vanish for early timesteps. Probes:
- How far up can the *solvable T* be pushed for a plain-Adam vanilla RNN?
- Do gradient-reweighting "unroll" mechanisms actually help, or is it all
  step-budget + lr? **Operator north star: solve-rate → ~100% at ever-larger T.**

## Where Everything Is
| Thing | Path |
|---|---|
| Code + notebook (local mirror) | `~/work/rnn_unroll/` (`train.py`, `unroll_util.py`, `unroll_optimizer.py`, `model.py`, `data.py`, `dynamic_precision.py`, `grad_probe.py`) |
| Lab notebook (READ FIRST, bottom-up) | `~/work/rnn_unroll/research/AUTORESEARCH_LOG.md` |
| Launch/watch scripts | `~/work/rnn_unroll/scripts/` |
| **Compute (REMOTE)** | FOUR 4-card GCE boxes in project viscam-cloud, usable IN PARALLEL = **16 GPUs**: `qiaos-4a100` (us-central1-f, 40GB), `qiaos-4a100-2` (us-east1-b, 40GB), `qiaos-4a100-3` (us-central1-a, **80GB**), `deepflow-4a100-40gb-junhwahur-1` (us-central1-b, 40GB, lent). Local `logs_*` are empty — real logs live on the boxes. SSH + full box table in `../gcp_gpu_ssh.md`. |
| W&B | project `rnn-unroll-adding` (entity zhh24-massachusetts-institute-of-technology); group = experiment name |
| Results spreadsheet | EqR workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, tab `RNN-unroll-adding (qiaos)` (sheet-id 960697842). Log conclusions here (`../research/result_logging.md`). |

Compute is plain processes on reserved boxes, NOT Borg/XManager: no BATCH tier,
nothing preemptible, and `../jobs.md` does not apply. Runs are
`CUDA_VISIBLE_DEVICES=N .venv/bin/python train.py …`, 12 lanes (3/GPU) per box,
driven by a `scripts/run_*.sh` scheduler that writes `_sched*.log` and a final
`ALL DONE` marker. A `watch_*.sh` polls over SSH and pings the owning session via
`~/.amply/bin/amply_notify <session_id> -`.

Four boxes = 48 lanes, but keep a sweep on ONE box. Split work by *sweep*, not by
arm: a scheduler assumes it owns the GPUs it sees, so two schedulers on one box
oversubscribe it. Give each box its own sweep, its own isolated launch dir, and
its own watcher. **There is no shared filesystem between boxes** — each holds its
own copy of the code and its own logs; W&B is the only common sink, which is why
cross-host duplicate cells cannot be detected locally and the CALLER must assign
disjoint cells.

**Setting up a new box is a copy, not a build: the DLVM image already carries
torch, so the venv is `python3 -m venv --system-site-packages .venv` and nothing
heavy is downloaded.** Copy `*.py` + `run_t500.sh` + `preflight.sh` from a
working box (compare md5s afterwards, so arm spellings cannot silently diverge),
plus `~/.netrc` for W&B and `launch_u2.sh` to `/tmp/`. Ubuntu 24.04 DLVM may lack
`python3.12-venv`; `apt install` it if `ensurepip` errors, and delete the
half-built `.venv` before retrying. Verify with the repo's own `test_unroll.py`
(it pins the zero-delta identity) and a short real train — two boxes running the
same seed must produce bit-identical loss.

`qiaos-4a100-3` has **80GB** cards, double the rest. Cells use ~5GB/lane, so
memory has never been the binding constraint; the 3-lanes/GPU convention is a
CPU/thread limit that `preflight.sh` enforces, so measure before raising it there.

## How The Mechanism Works (the code)
- `model.py` VanillaRNN: `h_t=tanh(x_t W_ih^T + h_{t-1} W_hh^T + b)`, readout on
  final h. W_hh is shared across T timesteps = T "call sites".
- **Per-timestep site grads** via the zero-delta trick: add a zero
  `delta_t` (requires_grad) to W_hh at step t; `dL/d(delta_t)=g_t` exactly, and
  `sum_t g_t = dL/dW_hh` (pinned by `test_unroll.py`). Torch analog of the JAX
  copy-trick in `coconut-jax/utils/unroll_util.py`.
- `unroll_util.merge_site_grads`: merge per-site grads → one grad → fed to ONE
  shared Adam. Knobs: `norm_power` (divide each g_t by ‖g‖^power; 1=full unit-
  normalize=textbook unroll, 0=plain sum, 0<p<1 partial), `norm_kind` (l2 |
  spectral=Newton-Schulz/Muon), `depth_weight` (see below), `sqrt_divisor`.
- `unroll_optimizer.PerSiteAdamHH`: the TRUE unroll ("optimizer state 真
  unroll") — each call site keeps its own Adam state (m_i,v_i), per-site step,
  merge the updates. flavors: `atan2` (EqR-faithful, epsilon-free) | `adamw`.
- `dynamic_precision.py`: backward hooks that rescale an underflowing hidden-
  state grad back to O(1), preserving direction = operator's "dynamic grad
  scale". `merge_selected_sites`: route grad to only {markers, n_random, n_last}
  sites (selective-site probe, uses privileged marker pos).

## Standing Rules The Operator Has Set (do not regress)
1. **Never call a variant a "win" without matching step-budget and lr for the
   baseline.** The early "np0.5 65% >> baseline 20%" headline was an artifact of
   undertraining baseline (20k steps); at 60k it vanished. This is the #1 lesson.
2. `--steps 60000` standardized for all runs (task is curriculum-like; solve
   rate is extremely step-sensitive).
3. *Solve threshold = 0.05.* The task is a staircase, not bimodal: full-solve
   (<0.02) / learned-1-of-2-markers (~0.083=Var(a)) / memoryless (~0.167). 0.05
   cleanly separates full-solve from the 1-of-2 tier.
4. *Metric = solve rate over seeds*, never a single-seed MSE (bimodal noise).
   Report Fisher exact p vs the paired baseline.
5. *Decision rule for pivots:* if baseline saturates (~100%) at best-lr for a
   given T → push T higher. History: T110→T120→T140 saturated → jumped to T200.
   Don't change the setting (T, steps) unless baseline saturates.
6. `--dynamic_precision` is default-on for unroll (operator,
   2026-08-27). Implemented as AUTO=-1 (on for unroll, off for baseline).
7. *EPS RULE:* dynamic-precision + eps-shrink go TOGETHER. Eps must be smaller
   than any grad norm (only to prevent /0), else it re-swamps the vanished grads
   it should revive. Hook eps 1e-300 (fp64-safe); the old 1e-30 failed to revive
   t≤50 at T200. merge norm_eps 1e-38. adam_atan2 is eps-free = the natural fit.
8. `depth_weight` direction: the operator wants the last loop (near loss) = weight
   1, polynomial (NOT exponential) decay toward the front, so early grads are
   still "eaten" but the terminal loss is preserved. That is `poly1_late` (1/r) /
   `poly2_late` (1/r^2). `poly*_early` (weight 1 on the earliest loop) is
   backwards — a bug that invalidated an early 1n/1n² sweep.
9. *Log conclusions to the spreadsheet tab*, not just the notebook.
10. *An lr does NOT transfer between merge rules — calibrate on `u_norm`, and
    quote the step window.* Each rule changes Adam's real step size, so the
    same lr means a different update. `train.py` logs `u_norm/total`, the true
    update norm measured by snapshotting weights around `opt.step()`; the
    gradient norm is NOT a proxy (Adam's m/sqrt(v) rescales per coordinate).
    Probe all arms at one lr, set each arm's base lr from the ratio
    u_ref/u_arm, then search ±3x. The ratio drifts with the step window
    (spectral 0.200 at steps [100,300] vs 0.612 at [500,1500]), and u_norm
    itself decays ~20x over a run. So compare arms only over identical windows,
    quote the window with the number, and never average windows into one
    "constant".
    The ±3x grid (9x span) absorbs that drift.
11. *Every (arm, lr) cell gets 5 seeds* — enforce it in the launcher, not in
    your memory. `preflight.sh <launcher> <jobs-file>` refuses any job file with a
    cell of any other size, alongside the thread-cap check. A 4-seed "probe"
    carved out to fill idle lanes will finish and produce a real-looking
    verdict.

## Confirmed Findings (mechanism)
- "Solving" = emergent horizon expansion / self-curriculum. rho(W_hh)
  spectral norm climbs during training (e.g. 1.13→3.23), early-timestep grads
  grow ~20-35 orders as rho rises, and the vanishing wall recedes. Solve is
  delayed, grokking-like: eval sits at 0.16 for thousands of steps then drops.
  Falsifiable via a cheap rho probe (`torch.linalg.matrix_norm(W_hh, ord=2)`).
- Full unroll (norm_power=1) is uniquely fatal (0/10 at T100; p=0.011 vs
  baseline): complete L2-normalization erases the magnitude the optimizer needs.
  Partial (power≤0.5) matches plain Adam. Precision/eps/depth-weight alone do
  NOT rescue full normalization.
- At fair 60k steps, no unroll variant has beaten baseline at a matched cell
  yet. Reconfirmed 2026-08-30 against TRUE TBPTT at T=300 with per-arm lr
  calibrated by u_norm: control (plain truncation k=10) 4/5, np0.5 3/5,
  spectral 0/5. Matching the control is NOT a win.
- TRUE TBPTT beats full BPTT, and the trainable window can be 1% of T.
  `--tbptt_k K` detaches h at t=T-K so the backward graph physically stops
  (early-timestep `|dL/dx|` is exactly 0). At T=300 full BPTT is 0/5 while k=3
  is 4/5 and k=10 is 4/5; at T=500 k=3 falls to 0/5, so the solvable band moves
  along k as T grows. Do not confuse three families: `ttbptt*` = TRUE TBPTT ·
  `tbptt*` = the OLD `--site_mask_k` (truncates W_hh site-grads only) ·
  `tt_unroll*` = true truncation plus a merge rule.
- Rule export is the positive result, and it is arithmetic, not argument. A net
  reading only marker2 has a hard MSE floor Var(v1)=1/12=0.0833. marker1 is
  always drawn from [0,T/2) so it is never inside the trainable window, yet
  truncated runs finish strictly below 0.0833 — impossible without reading
  marker1. The timestep-invariant rule learned in-window is exported by weight
  sharing to zero-gradient timesteps.
- A cell straddling a theoretical floor needs the full 5 seeds before the floor
  is called a ceiling. k=1 at T=300 showed 2/5 finals near 1/12=0.0833 and read
  like a "supervision only supports half the rule" ceiling; the complete cell
  was 0.0852/0.0753/0.1647/0.0560/0.0968 — a three-way spread with one seed
  strictly below the floor. The right reading is high variance (the rule forms
  unreliably), not a ceiling. A ceiling predicts concentration; check for it
  before naming one.
- A `dynamic_precision`-ON result from before 2026-08-28 measured a bug, not the
  idea. The rescue hook sat on every hidden state, and `loss.backward()` summed
  the real param grads across timesteps through those hooks. A per-timestep
  rescale does not cancel in that sum, so W_ih/W_hh/b got the wrong gradient
  direction (cos 0.18-0.25 vs true; readout unaffected because it branches off
  upstream = the built-in control). Corrupted params can't learn
  marker→accumulation, so the model parks on the memoryless plateau 0.167.
  **Consequence: every dyn-prec-ON result, INCLUDING ITS NEGATIVES, is void and
  is being re-run.** Notably the "1/n & 1/n² fail even with dyn-prec ON (0/24,
  locked)" claim, which had been used to permanently drop those arms, is
  RETRACTED. Fixed via a gated rescue (`_RESCUE_ENABLED` + `rescue_active()`, the
  gate is open only around the site-grad extraction, dormant during
  `loss.backward()`). Guard before citing any dyn-prec result:
  `grep -c _RESCUE_ENABLED dynamic_precision.py` must be nonzero.
- A negative result may drop an arm only if it depends on NO default-on
  experimental knob, and only with a positive control that actually solved in
  the same sweep. Detector: bug-kills are ~10x tighter than genuine failures
  (poisoned sweep CV 0.23% vs genuine-failure CV 2.43%). If failing cells agree
  to <1% CV across arms with genuinely different knobs, audit the shared code
  path before writing "none of the arms work". Full rule + post-mortem:
  `~/work/rnn_unroll/research/CONTAMINATION_AUDIT.md`.

## Ideas Backlog / Operator Ideas (status)
eps-shrink ✅std · dynamic_precision ✅default-on (impl FIXED 2026-08-28) ·
depth-weight 1/n & 1/n² (use poly*_late!) ⏳ · partial norm_power ✅champ ·
spectral/Muon ⏳ · selective-site ⏳ · TRUE per-site optimizer state ⏳ · idea-7
extensions (log-space norm, per-step whitening, only-normalize-nonzero,
magnitude-floor/hybrid, RMS vs L2) = survey.
**⏳ means UNTESTED, not "tried and failed"** — the dyn-prec-ON evidence that
appeared to close some of these was void (see Confirmed Findings). Being
re-measured under the fixed hook.

## Working Rhythm
Queue serially (GPUs shared 12 lanes per box); launch from an isolated dir (e.g.
`rnn_unroll_v3`) so edits never contaminate a running scheduler that reads
`train.py` live. Launch detached as `setsid nohup … >log 2>&1 </dev/null &` (the
`</dev/null` avoids a gcloud channel-EOF hang). One watcher per sweep, pointed at
the owning session id. Record every decision + result in the notebook.
