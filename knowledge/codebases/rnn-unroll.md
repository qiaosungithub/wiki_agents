# RNN Unroll — Adding Problem (science line)

A science line probing gradient propagation in a vanilla RNN on the **adding
problem** (long-range credit assignment). Not a product; the deliverable is a
falsifiable answer and a clean notebook. The native lab notebook
`~/work/rnn_unroll/research/AUTORESEARCH_LOG.md` is the source of truth — read it
end-to-start first. This page owns the setting and what the metrics mean
(Chapter 1) and what the experiments have found (Chapter 2). How to run
research on the 4×A100 boxes is the
[rnn-unroll-runs skill](../../harness/skills/rnn-unroll-runs/SKILL.md);
the dense-supervision counterpart line is [knowledge/codebases/charlm.md](charlm.md).

---

## Chapter 1 — The Setting And What The Metrics Mean

### The question

**The adding problem gives one supervised output at the end, so naive BPTT
gradients vanish for the early timesteps.** At sequence length T there are two
marked positions and the output is the sum of the two marked values. The line
probes two things:

- how far the *solvable T* can be pushed for a plain-Adam vanilla RNN;
- whether gradient-reweighting "unroll" mechanisms actually help, or whether it
  is all step-budget and lr.

**Operator north star: solve-rate → ~100% at ever-larger T.**

### Where everything is

| Thing | Path |
|---|---|
| Code + notebook (local mirror) | `~/work/rnn_unroll/` (`train.py`, `unroll_util.py`, `unroll_optimizer.py`, `model.py`, `data.py`, `dynamic_precision.py`, `grad_probe.py`) |
| Lab notebook (READ FIRST, bottom-up) | `~/work/rnn_unroll/research/AUTORESEARCH_LOG.md` |
| Launch / watch scripts | `~/work/rnn_unroll/scripts/` (`run_*.sh` scheduler, `watch_*.sh`) |
| Compute (REMOTE) | four 4-card GCE boxes in project `viscam-cloud`, usable in parallel = **16 GPUs**: `qiaos-4a100` (us-central1-f, 40GB), `qiaos-4a100-2` (us-east1-b, 40GB), `qiaos-4a100-3` (us-central1-a, **80GB**), `deepflow-4a100-40gb-junhwahur-1` (us-central1-b, 40GB, lent). Local `logs_*` are empty; real logs live on the boxes. SSH + full box table in [gcp-gpu-ssh skill](../../harness/skills/gcp-gpu-ssh/SKILL.md) |
| W&B | project `rnn-unroll-adding`, entity `zhh24-massachusetts-institute-of-technology` |
| Results tab | EqR workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, tab `RNN-unroll-adding (qiaos)` (sheet-id 960697842); log conclusions here ([result-logging skill](../../harness/skills/result-logging/SKILL.md)) |

**Compute is plain processes on reserved boxes, not Borg or XManager: no tiers,
nothing preemptible, and [knowledge/infrastructure/cluster-jobs.md](../infrastructure/cluster-jobs.md) does not apply.**

### What the metrics mean

**Judge a cell by its solve rate over seeds, never by a single-seed MSE.** The
eval MSE is multi-modal, so one seed is noise; report the Fisher exact p against
the paired baseline. The task is a staircase, not bimodal:

| Eval MSE | Tier |
|---|---|
| < 0.02 | full-solve |
| ~0.083 = Var(a) | learned 1 of 2 markers |
| ~0.167 | memoryless |

**Solve threshold = 0.05**, which cleanly separates full-solve from the 1-of-2
tier. The statistical floors and pooling rules for turning solve rates into a
verdict live in
[the rnn-unroll-runs skill §Reading the verdict](../../harness/skills/rnn-unroll-runs/SKILL.md#reading-the-verdict).

### How the mechanism works (the code)

**`W_hh` is shared across all T timesteps, so each timestep is a "call site"
whose per-site gradient can be extracted and re-merged before one shared Adam
step.**

- `model.py` VanillaRNN: `h_t = tanh(x_t W_ih^T + h_{t-1} W_hh^T + b)`, readout on
  the final `h`.
- **Per-timestep site grads via the zero-delta trick**: add a zero `delta_t`
  (`requires_grad`) to `W_hh` at step t; then `dL/d(delta_t) = g_t` exactly and
  `sum_t g_t = dL/dW_hh` (pinned by `test_unroll.py`). Torch analog of the JAX
  copy-trick in `coconut-jax/utils/unroll_util.py`.
- `unroll_util.merge_site_grads` merges per-site grads into one grad fed to ONE
  shared Adam. Knobs: `norm_power` (divide each `g_t` by `‖g‖^power`; 1 = full
  unit-normalize = textbook unroll, 0 = plain sum, 0<p<1 partial), `norm_kind`
  (`l2` | `spectral` = Newton-Schulz/Muon), `depth_weight`, `sqrt_divisor`.
- `unroll_optimizer.PerSiteAdamHH` is the TRUE unroll (optimizer state 真 unroll):
  each call site keeps its own Adam state `(m_i, v_i)` and per-site step, then the
  updates are merged. Flavors: `atan2` (EqR-faithful, epsilon-free) | `adamw`.
- `dynamic_precision.py`: backward hooks that rescale an underflowing
  hidden-state grad back to O(1), preserving direction (the operator's "dynamic
  grad scale"). `merge_selected_sites` routes grad to only
  `{markers, n_random, n_last}` sites (selective-site probe, uses the privileged
  marker positions).

**`depth_weight` ranks sites, and the operator wants the last loop (nearest the
loss) at weight 1 with polynomial — not exponential — decay toward the front**,
so early grads are still "eaten" but the terminal loss is preserved: that is
`poly1_late` (1/r) / `poly2_late` (1/r²), and `poly*_early` (weight 1 on the
earliest loop) is backwards. `poly*_late` ranks from the sequence end
(`rlate = C - i`), and under TBPTT the code re-ranks to the live window, so with
k live sites the weights span 1..1/k (or 1..1/k²). Before using a new depth
weight, print the weights it actually applies to the live sites: an un-re-ranked
`poly*_early` would be 1/471..1/500 (varying only ~6% across the window), a no-op
wearing a name.

---

## Chapter 2 — What The Experiments Have Found

### Solving is emergent horizon expansion

**"Solving" is a self-curriculum: `rho(W_hh)` climbs during training and the
vanishing wall recedes.** The spectral norm climbs (e.g. 1.13→3.23), early-
timestep grads grow ~20-35 orders as rho rises, and solve is delayed and
grokking-like — eval sits at 0.16 for thousands of steps, then drops. Falsifiable
via a cheap rho probe (`torch.linalg.matrix_norm(W_hh, ord=2)`).

### Full normalization is uniquely fatal

**`norm_power=1.0` annihilates the site-magnitude ordering exactly, which is why
every merge-side intervention helps on np0.5 and fails on np1.0.** Full unroll
(norm_power=1) is uniquely fatal — 0/10 at T100, p=0.011 vs baseline — because
complete L2-normalization erases the magnitude the optimizer needs; partial
(power ≤ 0.5) matches plain Adam, and precision/eps/depth-weight alone do NOT
rescue it. Measured at production shape (h128, T=500, k=30): raw site norms span
2.0e104; under `p=0.5` the ten sites nearest the loss carry **92.94%** of the
merged weight, under `p=1.0` they carry **2.00%** — exactly their share by count,
because every one of 499 live sites enters with weight 1.000. Masking or
reweighting a uniform sum is a rescale, not a reweighting, so there is nothing for
`--site_mask_k` or `--unroll_ih` to exploit. Measured at initialisation; the
profile shifts as rho climbs, and a mid-training re-measurement has not been done.

### Partial vs complete unroll, and knobs that silently no-op

**`--unroll_ih 0` versus `1` is not "a variant versus the default": the rows
without it are PARTIAL unrolls.** W_ih and b are used at every timestep exactly
like W_hh, so an unroll that merges only W_hh leaves per-timestep gradients
unextracted; present a W_ih row as the complete form and mark the W_hh-only rows
as incomplete, not the reverse. And **a flag that reaches only one branch is
accepted, changes nothing, and names the arm after a treatment it never
received**: `--unroll_ih 1` once sat inside the non-`true_state` branch, so on
truestate arms it was a no-op and `ihts_*` runs were bit-identical to their
`ts_*` twins. When a knob must apply to several code paths, assert it at the point
of USE in each path, and gate it with a test that treated and untreated runs
DIFFER (measured, production shape: W_ih norm 0.8389 vs 0.8704 after 12 steps). A
gate that only checks "flag off reproduces the old numbers" passes while flag-on
does nothing.

### TBPTT: true truncation beats full BPTT

**TRUE TBPTT beats full BPTT, and the trainable window can be 1% of T.**
`--tbptt_k K` detaches h at t=T-K so the backward graph physically stops (early-
timestep `|dL/dx|` is exactly 0). At T=300 full BPTT is 0/5 while k=3 and k=10 are
each 4/5; at T=500 k=3 falls to 0/5, so the solvable band moves along k as T
grows. Do not confuse three families: `ttbptt*` = TRUE TBPTT · `tbptt*` = the OLD
`--site_mask_k` (truncates W_hh site-grads only) · `tt_unroll*` = true truncation
plus a merge rule.

**At a fair 60k steps, no unroll variant has beaten baseline at a matched cell
yet.** Reconfirmed against TRUE TBPTT at T=300 with per-arm lr calibrated by
u_norm: control (plain truncation k=10) 4/5, np0.5 3/5, spectral 0/5. Matching
the control is NOT a win.

### The rule export result

**Weight sharing exports the in-window rule to zero-gradient timesteps; this is
arithmetic, not argument.** A net reading only marker2 has a hard MSE floor
Var(v1)=1/12=0.0833. marker1 is always drawn from [0,T/2) so it is never inside
the trainable window, yet truncated runs finish strictly below 0.0833 —
impossible without reading marker1. The timestep-invariant rule learned in-window
is exported by weight sharing to the zero-gradient timesteps.

**A cell straddling a theoretical floor needs the full 5 seeds before the floor
is called a ceiling.** k=1 at T=300 showed 2/5 finals near 1/12=0.0833 and read
like a "supervision only supports half the rule" ceiling; the complete cell was
0.0852/0.0753/0.1647/0.0560/0.0968 — a three-way spread with one seed strictly
below the floor, so the right reading is high variance (the rule forms
unreliably), not a ceiling. A ceiling predicts concentration; check for it before
naming one.

### Contamination: a bug-kill looks like a clean negative

**A negative result may drop an arm only if it depends on NO default-on
experimental knob and had a positive control that solved in the same sweep.** A
dynamic_precision-ON result from the era of the pre-fix hook measured a bug, not
the idea: the rescue hook sat on every hidden state, `loss.backward()` summed the
real param grads across timesteps through those hooks, and a per-timestep rescale
does not cancel in that sum, so W_ih/W_hh/b got the wrong gradient direction
(cos 0.18-0.25 vs true; the readout was unaffected because it branches off
upstream). Corrupted params park on the memoryless plateau 0.167, so every
dyn-prec-ON result from that era — including its negatives — is void, and a
negative from it does not close an arm. The fix gates the rescue
(`_RESCUE_ENABLED` + `rescue_active()`, open only around the site-grad
extraction, dormant during `loss.backward()`); guard before citing any dyn-prec
result with `grep -c _RESCUE_ENABLED dynamic_precision.py` (must be nonzero).
Detector for the general case: bug-kills are ~10x tighter than genuine failures
(poisoned sweep CV 0.23% vs genuine-failure CV 2.43%), so if failing cells agree
to <1% CV across arms with genuinely different knobs, audit the shared code path
before writing "none of the arms work" (full post-mortem:
`~/work/rnn_unroll/research/CONTAMINATION_AUDIT.md`).

### Open directions

**Untested is not tried-and-failed.** Partial `norm_power` (≤0.5) is the standard
reference arm; the named merge-side arms still to be measured are depth-weight
1/n & 1/n² (as `poly*_late`), spectral / Muon (`norm_kind spectral`),
selective-site (`merge_selected_sites`), and the TRUE per-site optimizer state
(`PerSiteAdamHH`). Further survey ideas: log-space norm, per-step whitening,
only-normalize-nonzero, magnitude-floor/hybrid, RMS vs L2. Some of these appeared
closed by dyn-prec-ON evidence that is now void (see [§Contamination](#contamination-a-bug-kill-looks-like-a-clean-negative)), so treat
them as untested, not failed.
