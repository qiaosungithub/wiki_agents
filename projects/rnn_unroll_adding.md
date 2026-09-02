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
| W&B | project `rnn-unroll-adding` (entity zhh24-massachusetts-institute-of-technology). **Two group conventions coexist and BOTH are real**: per-cell `T500.<arm>@<lr>` (the T=500 campaign's own scheme, one group per (arm, lr), 5 runs each) and per-batch `<setting>_<topic>_<date>` (e.g. `T500_v8_20260830`, `normpower_probe`). Match whichever the neighbouring rows of that block use — do not convert one into the other. Set `--wandb_group` at launch; back-fill a finished run with `api.run(...).group = ...; .update()`. |
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

- **`norm_power=1.0` annihilates the site-magnitude ordering exactly, which is
  why every merge-side intervention works on np0.5 and fails on np1.0.**
  Measured at production shape (h128, T=500, k=30): raw site norms span 2.0e104;
  under `p=0.5` the ten sites nearest the loss carry **92.94%** of the merged
  weight, under `p=1.0` they carry **2.00%** — exactly their share by count,
  because every one of 499 live sites enters with weight 1.000. Masking or
  reweighting a uniform sum is a rescale, not a reweighting, so there is nothing
  for `--site_mask_k` or `--unroll_ih` to exploit. This was carried as an
  untested hypothesis for two generations; it is now measured (at
  initialisation — the profile shifts as rho climbs, and a mid-training
  re-measurement has not been done).

## Ideas Backlog / Operator Ideas (status)
eps-shrink ✅std · dynamic_precision ✅default-on (impl FIXED 2026-08-28) ·
depth-weight 1/n & 1/n² (use poly*_late!) ⏳ · partial norm_power ✅champ ·
spectral/Muon ⏳ · selective-site ⏳ · TRUE per-site optimizer state ⏳ · idea-7
extensions (log-space norm, per-step whitening, only-normalize-nonzero,
magnitude-floor/hybrid, RMS vs L2) = survey.
**⏳ means UNTESTED, not "tried and failed"** — the dyn-prec-ON evidence that
appeared to close some of these was void (see Confirmed Findings). Being
re-measured under the fixed hook.

## Errors This Line Repeats (each cost a real result)

**`gsheets mutate insert-rows --start=N` BLANKS the row that was at N+1.**
Observed three times: the inserted row appears, and the row immediately below it
comes back empty on read-back. Re-read the whole block after every insert and
re-write any row that lost its cells; keep the row's values in the shell script
so the restore is one command. `mutate format` has the sibling defect — it edits
by STYLE INDEX, so formatting one row silently recolours every other row sharing
that style (greying rows 177-208 also greyed 174 and later 161).

**An lr string is a REGEX LANDMINE: `5.761e-4` contains `.` and `-`.** Querying
wandb with `{"display_name": {"$regex": f"^{cell}_s[0-9]+$"}}` returns 0 for a
cell that exists, and 0 reads as "the data is gone". Two separate false alarms
this shift, one of which nearly became a "we lost a 60k TOUCHED 5/5 cell"
report. Always `re.escape()` the cell name, or look the run up by id.

**A `run_t500.sh` scheduler started days ago RE-RUNS ITS WHOLE JOBFILE FOREVER**,
truncating the finished logs each time: `_sched.log` showed `DONE` immediately
followed by `START` for the same seed, and one cell had burned four full 60k
rounds. Before concluding a cell's log was corrupted, check `ps` for an old
scheduler owning it; before killing one, confirm the completed data is already
on wandb. Kill the parent first (it respawns lanes), then the per-lane shells,
then the `train.py` children.

**Create a W&B group for every batch you launch, and resolve a group's existence
by QUERYING it, never by scanning a run list.** Runs launched without an explicit
`--wandb_group` inherit whatever the predecessor's launcher hardcoded, so a
batch silently lands in someone else's group; 96 runs across three v13 batches
did. Put the group routing in the launcher so it cannot be forgotten.
★ `api.runs(project)` returns only a recent window, so a scan for
mis-grouped runs reports 0 while 79 sit outside it, and a group that the window
missed reads as "never existed". **This produced a false retraction**: the
per-cell `T500.<arm>@<lr>` groups were declared fabricated and 54 spreadsheet
links called dead, when all 39 T=500 cells in fact resolve to 5 runs each.
Always filter by `{"group": <name>}` or `{"display_name": {"$regex": ...}}`
before concluding anything is absent.

**A cell in the results tab is one clause, and shared context belongs in the
block header written once.** Notes reached 407 characters per row restating the
same protocol; `../research/result_logging.md` §Short Cells owns the rule. Per
row, write only what changes interpretation — usually just how the comparison
twin scored.

**`--unroll_ih 0` versus `1` is not "a variant versus the default": the rows
without it are PARTIAL unrolls.** W_ih and b are used at every timestep exactly
like W_hh, so an unroll that merges only W_hh leaves per-timestep gradients
unextracted. Present a W_ih row as the complete form and mark the W_hh-only rows
as incomplete, not the reverse.

**A flag that only reaches one branch is accepted, changes nothing, and names
the arm after a treatment it never received.** `--unroll_ih 1` was parsed and
recorded on every arm, but the W_ih merge sat inside the non-`true_state` branch
of the substitution block, so on truestate arms it was a no-op: `ihts_*` runs
were bit-identical to their `ts_*` twins for weeks of GPU time. Nothing errored
and the run name said `ih`. When you add a knob that must apply to several code
paths, assert it at the point of USE in each path, and gate it with a test that
the treated and untreated runs DIFFER (measured, production shape: W_ih norm
0.8389 vs 0.8704 after 12 steps). A gate that only checks "flag off reproduces
the old numbers" passes happily while flag-on does nothing.

**Verify a launch by counting processes per seed, never by the launcher's own
success message.** A missing arm or a missing script makes the remote guard
misfire while the wrapper still prints its LAUNCHED line, and the card idles for
a full watcher cycle. `ps -eo cmd | grep -c "[t]rain[.]py.*<cell>_s<N>$"` for
each of the 5 seeds is the check.

**The four boxes' launcher scripts DRIFT; grep the arm on the box you are about
to use.** `run_t500_v12.sh` on box2 has `tu_np1_30_mask10` but not the np0.5
version, so an edit anchored on a line that exists elsewhere fails there. Copy
the launcher to a new name before adding arms; never edit in place while ~30
launchers are reading it incrementally.

**Stagger seed launches by >= 40 s.** `run_t500_v12.sh` forks every lane at once
and concurrent `wandb.init` handshakes time out, killing seeds silently: the
card still reads busy and the watcher still prints a healthy lane count. 28 s
was measured to be insufficient.

**A metric derived from a marker the producer writes AT EXIT cannot describe a
running cell.** The watcher counted TOUCHED via `solved_at=`, so live cells read
0/5 however far below the threshold they had gone. Derive TOUCHED from the eval
stream, like FINAL and best.

**Cap a paired comparison at min(step reached by BOTH arms).** A cap taken from
one arm silently truncates the other and inverts the result: one such reading
gave 16/20 pairs and p=0.0118 where the matched cap gives 14/20 and p=0.115.

**At n=5 the two-sided sign test floors at p=0.0625**, so no single (arm, lr)
cell can ever be significant on paired seeds. Pool across lrs — but only within
one arm: `--unroll_ih` and `--site_mask_k` both help np0.5 and fail on np1.0, so
pooling the two arms averages opposite responses.

**A null on this line is a statement about how many pairs you pooled, not about
the effect; the same data reverses when the ladder grows.** Four rungs of
W_ih-complete vs W_hh-only on np0.5 k=10 gave TOUCHED 14/20 (Fisher p=0.33) and
paired 13/20 (sign p=0.26), reported as "the ceiling moves, the median does
not". Fourteen rungs of the same arm, same harvest, same cap rule, give paired
54/70 (sign p=5.9e-6, Wilcoxon 1.8e-7) and TOUCHED 36/70 vs 18/70 (p=0.0030).
No earlier number was wrong and nothing was recomputed differently — the small
pool simply could not separate "no effect" from "too few pairs". Quote a null
only with its pair count, and verify a p you are about to publish against a
second implementation plus a label-shuffled control that must come back
non-significant.

**Fleet capacity is 16 concurrent cells, and a 5-rung ladder per arm is 5 of
them.** Four boxes x 4 GPUs, one 5-seed cell per GPU (measured: 20 lanes/box).
So any plan with more than three arms at a full sqrt3 ladder is over capacity
and needs either a narrowed ladder or a second wave. Compute this BEFORE
pre-registering rungs; discovering it at launch time forces the ladder to be
re-picked, which is the one thing pre-registration exists to prevent.

**The tab's cell label is not the wandb run name, and the mismatch returns
`NO RUNS` rather than an error.** The tab and the group use
`T500.<arm>@<lr>`; the run's display name is `T500_<arm>_lr<lr>_s<seed>`
(`.`->`_`, `@`->`_lr`). Feeding the harvest tool the tab's label reports a
finished cell as missing, which reads as lost data. Verify a harvest path by
reproducing a row already in the tab before trusting it on a new one.

**`poly*_late` ranks sites from the SEQUENCE end, `poly*_early` from the live
window start; under TBPTT only the second is window-aligned.** `rlate = C - i`,
so with k live sites the late weights span 1..1/k (or 1..1/k^2), which is a real
profile. The early weights would be 1/471..1/500 — all but identical — if they
were not explicitly re-ranked to the live window, and the code does re-rank
them. Before using a new depth weight, print the weights it actually applies to
the live sites; a weight that varies by 6% across the window is a no-op wearing
a name.

**Grey the rows a predicate SELECTS, never the rows a DATE contains.** A bulk
pass greying "everything predating the W_ih fix" over-greyed 90 rows: the fix
was branch-specific (`true_state` only), so runs that were always correct share
the date. Measured afterwards: the rule for the actual bug (`unroll_ih=1` AND
`true_state=1`) matches ZERO logged rows, because the affected runs were killed
before they were ever logged. Derive a colouring predicate from each run's own
recorded config, and check it selects a non-empty set before applying it.

**A watcher started from a tmux pane dies with that pane's scope, and
`systemd-oomd` takes the whole scope at once.** One sweep killed this line's
20-minute watcher and its capacity sentinel simultaneously; neither logged an
error, and the line ran unwatched for 9.5 hours while two GPUs sat idle after a
cell finished. Two consequences: check liveness by process, not by "the log
looks healthy" (a dead watcher's log is indistinguishable from a quiet one), and
prefer `setsid` plus a cron or systemd unit over a tmux-parented loop for
anything that must outlive an interactive session. The kill is invisible in
`/proc/vmstat` `oom_kill`; read the journal (`../monitoring.md` §Memory And Disk
Wake Criteria).

## Working Rhythm
Queue serially (GPUs shared 12 lanes per box); launch from an isolated dir (e.g.
`rnn_unroll_v3`) so edits never contaminate a running scheduler that reads
`train.py` live. Launch detached as `setsid nohup … >log 2>&1 </dev/null &` (the
`</dev/null` avoids a gcloud channel-EOF hang). One watcher per sweep, pointed at
the owning session id. Record every decision + result in the notebook.
