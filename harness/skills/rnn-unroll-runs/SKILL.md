---
name: rnn-unroll-runs
description: Set up boxes for, launch, verify, harvest, log, and judge RNN unroll adding-problem sweeps on the GPU boxes, where one (arm, lr) cell is one W&B group of seeds and one tab row.
---

# RNN Unroll Runs — Running Research Against This Line

This skill relies on [the RNN unroll knowledge page](../../../knowledge/codebases/rnn-unroll.md)
for the question, the code and box paths, the solve threshold and tiers, how the
mechanism works, and the findings so far; read the lab notebook it names first.
The operator drives pivots; keep runs patient, with no compute churn. Box SSH is
[gcp-gpu-ssh skill](../gcp-gpu-ssh/SKILL.md); which workbook and tab a result goes to is
[knowledge/environment/result-workbooks.md §Which Tab](../../../knowledge/environment/result-workbooks.md#which-tab).

## Running on the boxes: one sweep per box, no shared filesystem

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
  (invisible in `/proc/vmstat` `oom_kill`; read the journal,
  [machine-health skill §Idle Blaze Heaps, Swap, And OOM](../machine-health/SKILL.md#idle-blaze-heaps-swap-and-oom)).
  Check watcher liveness by process, not by "the log looks healthy" — a dead
  watcher's log is indistinguishable from a quiet one.

## Setting up a new box is a copy, not a build

**The DLVM image already carries torch, so a new box is a file copy plus a
`--system-site-packages` venv, not a heavy download.** Create it with
`python3 -m venv --system-site-packages .venv`; copy `*.py` + `run_t500.sh` +
`preflight.sh` from a working box (compare md5s afterwards, so arm spellings
cannot silently diverge), plus `~/.netrc` for W&B and `launch_u2.sh` to `/tmp/`.
Ubuntu 24.04 DLVM may lack `python3.12-venv`; `apt install` it if `ensurepip`
errors, and delete the half-built `.venv` before retrying. Verify with the repo's
own `test_unroll.py` (it pins the zero-delta identity) and a short real train —
two boxes running the same seed must produce bit-identical loss.

## The run settings the operator has standardized

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

## Calibrate each arm's lr on u_norm

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

## Launch discipline: stagger, verify by process, never edit a live launcher

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

## The logging pipeline — one cell = one W&B group = 5 seeds = one row

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
  ([result-logging skill §Short Cells; Formatting Is Part Of The Result](../result-logging/SKILL.md#short-cells-formatting-is-part-of-the-result)).
- **Spreadsheet write traps** (owned by [result-logging skill](../result-logging/SKILL.md)):
  `gsheets mutate insert-rows --start=N` blanks the row that was at N+1 (the
  `--range "'Tab'!35:37"` form does not), so re-read the whole block after every
  insert and re-write any row that lost its cells; `mutate format` edits by STYLE
  INDEX, so formatting one row silently recolours every other row sharing that
  style. Grey the rows a predicate SELECTS, never the rows a DATE contains — a
  branch-specific fix (`true_state` only) leaves same-date runs that were always
  correct — so derive the colouring predicate from each run's own recorded config
  and check it selects a non-empty set before applying it.

## Reading the verdict

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
