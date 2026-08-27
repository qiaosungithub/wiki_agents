# RNN Unroll — Adding Problem (science line)

A SCIENCE line probing gradient propagation in a vanilla RNN on the **adding
problem** (long-range credit assignment). Not a product; the deliverable is a
falsifiable answer + a clean notebook. The operator drives pivots; keep runs
patient (no compute churn). Native lab notebook `~/work/rnn_unroll/research/
AUTORESEARCH_LOG.md` is the SOURCE OF TRUTH — read it end-to-start first; this
guide is the durable frame that keeps a fresh session from getting lost.

## The Question
Adding problem at sequence length T: two marked positions, output = sum of the
two marked values. Naive BPTT gradients vanish for early timesteps. Probes:
- How far up can the **solvable T** be pushed for a plain-Adam vanilla RNN?
- Do gradient-reweighting "unroll" mechanisms actually help, or is it all
  step-budget + lr? **Operator north star: solve-rate → ~100% at ever-larger T.**

## Where Everything Is
| Thing | Path |
|---|---|
| Code + notebook (local mirror) | `~/work/rnn_unroll/` (`train.py`, `unroll_util.py`, `unroll_optimizer.py`, `model.py`, `data.py`, `dynamic_precision.py`, `grad_probe.py`) |
| Lab notebook (READ FIRST, bottom-up) | `~/work/rnn_unroll/research/AUTORESEARCH_LOG.md` |
| Launch/watch scripts | `~/work/rnn_unroll/scripts/` |
| **Compute (REMOTE)** | GCE box `deepflow-4a100-40gb-junhwahur-1` (zone us-central1-b, project viscam-cloud), 4×A100-40GB. Local `logs_*` are EMPTY — real logs live on the box. SSH via `../gcp_gpu_ssh.md`. |
| W&B | project `rnn-unroll-adding` (entity zhh24-massachusetts-institute-of-technology); group = experiment name |
| Results spreadsheet | EqR workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, tab **`RNN-unroll-adding (qiaos)`** (sheet-id 960697842). Log conclusions here (`../research/result_logging.md`). |

**Compute is plain PROCESSES on a reserved box, NOT Borg/XManager** — so there
is NO BATCH tier and nothing is preemptible; `../jobs.md` does not apply. Runs
are `CUDA_VISIBLE_DEVICES=N .venv/bin/python train.py …`, 12 lanes (3/GPU),
driven by a `scripts/run_*.sh` scheduler that writes `_sched*.log` and a final
`ALL DONE` marker; a `watch_*.sh` polls over SSH and pings the owning session
via `~/.amply/bin/amply_notify <session_id> -`.

## How The Mechanism Works (the code)
- `model.py` VanillaRNN: `h_t=tanh(x_t W_ih^T + h_{t-1} W_hh^T + b)`, readout on
  final h. W_hh is SHARED across T timesteps = T "call sites".
- **Per-timestep site grads** via the zero-delta trick: add a zero
  `delta_t` (requires_grad) to W_hh at step t; `dL/d(delta_t)=g_t` EXACTLY, and
  `sum_t g_t = dL/dW_hh` (pinned by `test_unroll.py`). Torch analog of the JAX
  copy-trick in `coconut-jax/utils/unroll_util.py`.
- `unroll_util.merge_site_grads`: merge per-site GRADS → one grad → fed to ONE
  shared Adam. Knobs: `norm_power` (divide each g_t by ‖g‖^power; 1=full unit-
  normalize=textbook unroll, 0=plain sum, 0<p<1 partial), `norm_kind` (l2 |
  spectral=Newton-Schulz/Muon), `depth_weight` (see below), `sqrt_divisor`.
- `unroll_optimizer.PerSiteAdamHH`: the TRUE unroll ("optimizer state 真
  unroll") — each call site keeps its OWN Adam state (m_i,v_i), per-site step,
  merge the UPDATES. flavors: `atan2` (EqR-faithful, epsilon-free) | `adamw`.
- `dynamic_precision.py`: backward hooks that rescale an underflowing hidden-
  state grad back to O(1) (preserve direction, revive magnitude). = operator's
  "dynamic grad scale". `merge_selected_sites`: route grad to only {markers,
  n_random, n_last} sites (selective-site probe, uses privileged marker pos).

## Standing Rules The Operator Has Set (do not regress)
1. **Never call a variant a "win" without matching STEP-BUDGET and LR for the
   baseline.** The early "np0.5 65% >> baseline 20%" headline was an artifact of
   undertraining baseline (20k steps); at 60k it vanished. This is the #1 lesson.
2. **`--steps 60000` standardized** for all runs (task is curriculum-like; solve
   rate is extremely step-sensitive).
3. **Solve threshold = 0.05.** Task is a STAIRCASE not bimodal: full-solve
   (<0.02) / learned-1-of-2-markers (~0.083=Var(a)) / memoryless (~0.167). 0.05
   cleanly separates full-solve from the 1-of-2 tier.
4. **Metric = solve RATE over seeds**, never a single-seed MSE (bimodal noise).
   Report Fisher exact p vs the paired baseline.
5. **Decision rule for pivots:** if baseline saturates (~100%) at best-lr for a
   given T → push T higher. History: T110→T120→T140 saturated → jumped to T200.
   **Don't change the setting (T, steps) unless baseline saturates.**
6. **Dynamic precision (`--dynamic_precision`) DEFAULT ON for unroll** (operator,
   2026-08-27). Implemented as AUTO=-1 (on for unroll, off for baseline).
7. **EPS RULE:** dynamic-precision + eps-shrink go TOGETHER — eps must be SMALLER
   than any grad norm (only to prevent /0), else it re-swamps the vanished grads
   it should revive. Hook eps 1e-300 (fp64-safe); the old 1e-30 failed to revive
   t≤50 at T200. merge norm_eps 1e-38. adam_atan2 is eps-free = the natural fit.
8. **depth_weight direction:** operator wants the LAST loop (near loss) = weight
   1, polynomial (NOT exponential) decay toward the front, so early grads are
   still "eaten" but the terminal loss is preserved (closer to baseline). That is
   `poly1_late` (1/r) / `poly2_late` (1/r^2). `poly*_early` (weight 1 on the
   EARLIEST loop) is BACKWARDS — a bug that invalidated an early 1n/1n² sweep.
9. **Log conclusions to the spreadsheet tab** (not just the notebook).

## Confirmed Findings (mechanism)
- **"Solving" = emergent horizon expansion / self-curriculum:** rho(W_hh)
  spectral norm CLIMBS during training (e.g. 1.13→3.23), early-timestep grads
  grow ~20-35 orders as rho rises, the vanishing wall RECEDES; delayed grokking-
  like solve (eval sits at 0.16 for thousands of steps then drops). Falsifiable
  via a cheap rho probe (`torch.linalg.matrix_norm(W_hh, ord=2)`).
- **FULL unroll (norm_power=1) is uniquely fatal** (0/10 at T100; p=0.011 vs
  baseline) — complete L2-normalization erases the magnitude the optimizer needs.
  **Partial (power≤0.5) matches plain Adam.** Precision/eps/depth-weight alone do
  NOT rescue full normalization.
- **At fair 60k steps, no unroll variant has beaten baseline at a matched cell**
  yet; the T200 cell (baseline best 2/8=25%, not saturated) is the current
  discriminating test for the dyn-prec-on arms + the true-unroll optimizer.

## Ideas Backlog / Operator Ideas (status)
eps-shrink ✅std · dynamic_precision ✅default-on · depth-weight 1/n & 1/n² (use
poly*_late!) ⏳ · partial norm_power ✅champ · spectral/Muon ⏳ · selective-site ⏳
· TRUE per-site optimizer state ⏳ · idea-7 extensions (log-space norm, per-step
whitening, only-normalize-nonzero, magnitude-floor/hybrid, RMS vs L2) = survey.

## Working Rhythm
Patient line. Queue serially (GPUs shared 12 lanes); launch from an ISOLATED dir
(e.g. `rnn_unroll_v3`) so edits never contaminate a running scheduler that reads
`train.py` live. Launch detached as `setsid nohup … >log 2>&1 </dev/null &` (the
`</dev/null` avoids a gcloud channel-EOF hang). One watcher per sweep, pointed at
the current owning session id. Record every decision + result in the notebook.
