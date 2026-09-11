# RNN Unroll — Adding Problem (science line)

A science line probing gradient propagation in a vanilla RNN on the **adding
problem** (long-range credit assignment). Not a product; the deliverable is a
falsifiable answer and a clean notebook. The operator drives pivots; keep runs
patient, with no compute churn. The native lab notebook
`~/work/rnn_unroll/research/AUTORESEARCH_LOG.md` is the source of truth — read it
end-to-start first. Two chapters carry what stays true — the setting and what
the metrics mean (Chapter 1), and how to run research on the 4×A100 boxes
(Chapter 2) — and a third records what the experiments have found (Chapter 3).

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
| Compute (REMOTE) | four 4-card GCE boxes in project `viscam-cloud`, usable in parallel = **16 GPUs**: `qiaos-4a100` (us-central1-f, 40GB), `qiaos-4a100-2` (us-east1-b, 40GB), `qiaos-4a100-3` (us-central1-a, **80GB**), `deepflow-4a100-40gb-junhwahur-1` (us-central1-b, 40GB, lent). Local `logs_*` are empty; real logs live on the boxes. SSH + full box table in `../gcp_gpu_ssh.md` |
| W&B | project `rnn-unroll-adding`, entity `zhh24-massachusetts-institute-of-technology` |
| Results tab | EqR workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, tab `RNN-unroll-adding (qiaos)` (sheet-id 960697842); log conclusions here (`../research/result_logging.md`) |

**Compute is plain processes on reserved boxes, not Borg or XManager: no tiers,
nothing preemptible, and `../jobs.md` does not apply.**

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
verdict live in Chapter 2 §Reading the verdict.

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

## Chapter 2 — Running Research Against This Line

### Running on the boxes: one sweep per box, no shared filesystem

**Give each box its own sweep, its own isolated launch dir, and its own watcher;
a scheduler assumes it owns every GPU it sees, so two schedulers on one box
oversubscribe it.**

- A run is `CUDA_VISIBLE_DEVICES=N .venv/bin/python train.py …`. A
  `scripts/run_*.sh` scheduler drives the lanes and writes `_sched*.log` plus a
  final `ALL DONE` marker; a `watch_*.sh` polls over SSH and pings the owning
  session with `~/.amply/bin/amply_notify <session_id> -`.
- Convention is 12 lanes per box (3/GPU); the four boxes give 48 lanes. Cells use
  ~5GB/lane, so memory is never the binding constraint even on the 40GB boxes,
  and the 3-lanes/GPU cap is a CPU/thread limit that `preflight.sh` enforces —
  measure before raising it. `qiaos-4a100-3` has 80GB cards, double the rest.
- There is **no shared filesystem between boxes**: each holds its own copy of the
  code and its own logs, W&B is the only common sink, so cross-host duplicate
  cells cannot be detected locally and the CALLER must assign disjoint cells.
  Split work by *sweep*, not by arm.
- Launch detached as `setsid nohup … >log 2>&1 </dev/null &` (the `</dev/null`
  avoids a gcloud channel-EOF hang), one watcher per sweep pointed at the owning
  session id. Prefer `setsid` plus cron or a systemd unit over a tmux-parented
  loop for anything that must outlive the session: a watcher in a tmux pane dies
  with that pane's scope, and `systemd-oomd` takes the whole scope at once
  (invisible in `/proc/vmstat` `oom_kill`; read the journal, `../workstation.md`
  §Reclaiming Memory: Idle Blaze Heaps, Swap, And OOM).
  Check watcher liveness by process, not by "the log looks healthy" — a dead
  watcher's log is indistinguishable from a quiet one.

### Setting up a new box is a copy, not a build

**The DLVM image already carries torch, so a new box is a file copy plus a
`--system-site-packages` venv, not a heavy download.** Create it with
`python3 -m venv --system-site-packages .venv`; copy `*.py` + `run_t500.sh` +
`preflight.sh` from a working box (compare md5s afterwards, so arm spellings
cannot silently diverge), plus `~/.netrc` for W&B and `launch_u2.sh` to `/tmp/`.
Ubuntu 24.04 DLVM may lack `python3.12-venv`; `apt install` it if `ensurepip`
errors, and delete the half-built `.venv` before retrying. Verify with the repo's
own `test_unroll.py` (it pins the zero-delta identity) and a short real train —
two boxes running the same seed must produce bit-identical loss.

### The run settings the operator has standardized

**`--steps 60000` for every run, `--dynamic_precision` default-on for unroll, and
every (arm, lr) cell gets exactly 5 seeds — enforced in the launcher, not in
memory.**

- `--steps 60000` is standardized because solve rate is extremely step-sensitive
  (the task is curriculum-like).
- `--dynamic_precision` is default-on for unroll, implemented as AUTO=-1 (on for
  unroll, off for baseline).
- **EPS rule:** dynamic-precision and eps-shrink go together — eps must be
  smaller than any grad norm (only to prevent /0), or it re-swamps the vanished
  grads it should revive. Hook eps `1e-300` (fp64-safe; the old `1e-30` failed to
  revive t≤50 at T200), merge `norm_eps 1e-38`; `adam_atan2` is eps-free and the
  natural fit.
- **Every (arm, lr) cell gets 5 seeds**, enforced by
  `preflight.sh <launcher> <jobs-file>`, which refuses any job file with a cell of
  a different size (alongside the thread-cap check). A 4-seed probe carved out to
  fill idle lanes finishes and produces a real-looking verdict.
- **Do not change the setting (T, steps) unless the baseline saturates.** If the
  baseline saturates (~100%) at its best lr for a given T, push T higher (history:
  T110→120→140 saturated, jumped to T200).

### Calibrate each arm's lr on u_norm

**An lr does NOT transfer between merge rules, and no variant is a "win" without
matching the baseline's step budget and lr.** Each merge rule changes Adam's real
step size, so the same lr means a different update; the early "np0.5 65% >>
baseline 20%" headline was an artifact of undertraining the baseline (20k steps)
and vanished at 60k. Calibrate on `u_norm`, not the gradient norm (Adam's m/√v
rescales per coordinate): `train.py` logs `u_norm/total`, the true update norm
measured by snapshotting weights around `opt.step()`. Probe all arms at one lr,
set each arm's base lr from the ratio `u_ref/u_arm`, then search ±3x. The ratio
drifts with the step window (spectral 0.200 at steps [100,300] vs 0.612 at
[500,1500]) and `u_norm` itself decays ~20x over a run, so compare arms only over
identical windows, quote the window with the number, and never average windows
into one "constant"; the ±3x grid (9x span) absorbs the drift.

### Launch discipline: stagger, verify by process, never edit a live launcher

**Verify a launch by counting processes per seed, never by the launcher's own
success message.** A missing arm or script makes the remote guard misfire while
the wrapper still prints its LAUNCHED line and the card idles for a full watcher
cycle; the check is `ps -eo cmd | grep -c "[t]rain[.]py.*<cell>_s<N>$"` for each
of the 5 seeds.

- **Stagger seed launches by ≥ 40 s** (28 s was measured insufficient): forking
  every lane at once makes concurrent `wandb.init` handshakes time out and kill
  seeds silently, while the card still reads busy and the watcher still prints a
  healthy lane count.
- **The boxes' launcher scripts DRIFT, so grep the arm on the box you are about
  to use**, copy a launcher to a new name before adding arms, and never edit one
  in place while the schedulers are reading it incrementally.
- **A `run_*.sh` scheduler started days ago re-runs its whole jobfile forever**,
  truncating the finished logs each pass (a `_sched.log` shows `DONE` immediately
  followed by `START` for the same seed). Before concluding a log was corrupted,
  check `ps` for an old scheduler owning it; before killing one, confirm the
  completed data is already on W&B, then kill the parent first (it respawns
  lanes), then the per-lane shells, then the `train.py` children.

### The logging pipeline — one cell = one W&B group = 5 seeds = one row

**Every metric cell in the tab is `mean ± sd` over the 5 seeds; log conclusions
to the tab, not just the notebook.**

- Two W&B group conventions coexist and BOTH are real: per-cell `T500.<arm>@<lr>`
  (one group per (arm, lr), 5 runs each) and per-batch `<setting>_<topic>_<date>`
  (e.g. `normpower_probe`). Match whichever the neighbouring rows use; do not
  convert one into the other. Set `--wandb_group` at launch; back-fill a finished
  run with `api.run(...).group = ...; .update()`.
- **Harvest by GROUP, never by scanning a run list.** Runs launched without an
  explicit `--wandb_group` inherit whatever the predecessor's launcher hardcoded
  and land in someone else's group, so put group routing in the launcher.
  `api.runs(project)` returns only a recent window, so a scan reports 0 for a
  group that exists; filter by `{"group": <name>}` or
  `{"display_name": {"$regex": ...}}`.
- **The tab's cell label is not the wandb run name**, and the mismatch returns
  `NO RUNS`, not an error. The tab and group use `T500.<arm>@<lr>`; the run's
  display name is `T500_<arm>_lr<lr>_s<seed>` (`.`→`_`, `@`→`_lr`). Verify a
  harvest path by reproducing a row already in the tab before trusting it on a
  new one.
- **An lr string is a REGEX LANDMINE**: `5.761e-4` contains `.` and `-`, so
  `{"display_name": {"$regex": f"^{cell}_s[0-9]+$"}}` returns 0 for a cell that
  exists, and 0 reads as "the data is gone". Always `re.escape()` the cell name,
  or look the run up by id.
- **TOUCHED must come from the eval stream**, not a marker the producer writes at
  exit. A metric derived from `solved_at=` reads live cells as 0/5 however far
  below threshold they have gone; derive TOUCHED the way FINAL and best are.
- A cell in the tab is one clause; shared protocol goes in the block header
  written once, and per-row notes carry only what changes interpretation
  (`../research/result_logging.md` §Short Cells; Formatting Is Part Of The
  Result).
- **Spreadsheet write traps** (owned by `research/result_logging.md`):
  `gsheets mutate insert-rows --start=N` blanks the row that was at N+1 (the
  `--range "'Tab'!35:37"` form does not), so re-read the whole block after every
  insert and re-write any row that lost its cells; `mutate format` edits by STYLE
  INDEX, so formatting one row silently recolours every other row sharing that
  style. Grey the rows a predicate SELECTS, never the rows a DATE contains — a
  branch-specific fix (`true_state` only) leaves same-date runs that were always
  correct — so derive the colouring predicate from each run's own recorded config
  and check it selects a non-empty set before applying it.

### Reading the verdict

**Compare two arms at each arm's own best lr, not by pooling the rungs of a
ladder.** An lr ladder is one search, not a sample of independent conditions, so
pooling badly-tuned rungs inflates the denominator and buys a p-value that
reports ladder length, not effect: a pooled 14/15 vs 0/25 gave p=6e-10 where the
honest best-vs-best of the same data gives 5/5 vs 0/5, p=0.0040. State which rung
won and its best eval.

- **Cap a paired comparison at min(step reached by BOTH arms).** A cap from one
  arm truncates the other and can invert the result: one reading gave 16/20 pairs
  p=0.0118 where the matched cap gives 14/20 p=0.115.
- **A null is a statement about how many pairs you pooled, not about the effect.**
  Four rungs of W_ih-complete vs W_hh-only on np0.5 k=10 gave TOUCHED 14/20
  (Fisher p=0.33) and paired 13/20 (sign p=0.26); fourteen rungs of the same arm,
  same harvest and cap rule, give paired 54/70 (sign p=5.9e-6, Wilcoxon 1.8e-7)
  and TOUCHED 36/70 vs 18/70 (p=0.0030). Quote a null with its pair count, and
  verify a p you are about to publish against a second implementation plus a
  label-shuffled control that must come back non-significant.
- **Pool across lrs only WITHIN one arm.** `--unroll_ih` and `--site_mask_k` both
  help np0.5 and fail on np1.0, so pooling the two arms averages opposite
  responses. At n=5 the two-sided sign test floors at p=0.0625 and a single-rung
  Fisher test at p=1/252=0.004 one-sided, so buy power with more seeds at the
  winning rung, not with more rungs.
- **Fleet capacity is 16 concurrent cells** (4 boxes × 4 GPUs, one 5-seed cell
  per GPU, measured 20 lanes/box), and a 5-rung ladder per arm is 5 of them. Any
  plan with more than three arms at a full sqrt3 ladder is over capacity; compute
  this before pre-registering rungs.

---

## Chapter 3 — What The Experiments Have Found

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
closed by dyn-prec-ON evidence that is now void (see §Contamination), so treat
them as untested, not failed.
