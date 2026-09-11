# EqR And EqR-jax

`EqR` (PyTorch) and `EqR-jax` (JAX) are separate implementations of
continuous-space reasoning for sudoku and mazes. **Never port runtime, data,
checkpoint or logging behavior between them** without reading both code paths.
Unless a rule names the torch side, it describes `EqR-jax`. Owned elsewhere:
launches and job diagnosis `../jobs.md`, placement `../storage.md`, spreadsheet
discipline `../research/result_logging.md`.

Four chapters: **Chapter 1** the invariants of the model, data, and config;
**Chapter 2** launching, resuming, and operating a run; **Chapter 3** reading
the numbers — metrics and the eval protocol; **Chapter 4** the RoboTwin
Diffusion-Policy baseline (a distinct sub-project).

---

## Chapter 1 — Invariants: The Model And Data

### Model and q-head invariants

- The q head's `-5` no-halt bias is an early-training device, not a standing
  property. `sigmoid(-5) ~ 0.0067` makes ACT spend its full budget before
  learning to stop, as in the torch reference, but unmasked `wd 1.0` gives it a
  ~6900-step half-life: a released checkpoint's dead `q_continue` bias is pure
  `exp(-1e-4 t)`. No test pins it.
- `arch.q_head_sg` severs the halt objective from the trunk. The q head reads a
  `stop_gradient` latent, so the q term's trunk gradient is exactly zero in
  every `q_readout` mode, and `arch.loss.q_halt_loss_weight` becomes a no-op:
  `atan2` is scale-invariant on the head itself, and the weight only scaled the
  trunk pull `q_head_sg` removes. `q_head_sg: true` performs best; training the
  head separately costs the trunk nothing.
- Registers are plain trainable tokens; the knob is `arch.num_registers`. An
  `(N, hidden)` table in `params` prepends N tokens after `embed_scale`, so
  `register_init_std` is the std the trunk sees. It replaced a `puzzle_emb_*`
  surface inert three ways over (zero, non-trainable `consts`, keyed by a
  `puzzle_identifiers` column every dataset fills with 0). Retired names raise
  and name their successor, since pydantic drops unknown fields silently. A
  `puzzle_emb` checkpoint no longer restores; torch ones convert with
  `--num-registers`.
- A zero-initialized register is not a neutral default. `register_init_std`
  defaults to 0.02, not upstream's 0, because a zero slot feeds the q head
  nothing during the steps that decide whether ACT ever learns to halt. Ablate
  it with any register experiment.
- `mlp_t: true` makes `pos_encodings` a complete no-op: bit-identical logits
  across `rope`, `rope2d` and `none`, the MLP-T branch never reading the table.
  Every `local_debug*` config and upstream's sudoku recipe set it, so a run
  reported as "rope2d" alongside `mlp_t` measured no position encoding.
- `rope2d` with registers is refused at config load: the flat table it served
  was not a rotation (row and column angles in one 2x2 block, orthogonal only on
  the board diagonal). A rebuild needs PaliGemma's half-width `[row(q),
  col(q)]`-then-DUPLICATE layout; plain 1-D `rope` is fine with a prefix.

### Dataset and corpus invariants

- A dataset alias missing from `DATASET_PATHS` becomes a literal path and kills
  the job at startup with "Dataset split train in <alias> does not exist". Check
  the live mapping in `dataset/data_util.py` (`Maze-dynamic`,
  `Maze-30x30-multi`, `Sudoku-aug1000`) in the checkout you launch *from*, not
  the one you edited.
- `dataset.online_aug` is the sudoku symmetry group, not a generic augmenter. It
  reshapes each batch to `(B, 9, 9)`, so on a 900-cell board it raises inside
  the train loader, after packaging and scheduling are paid for. Now refused off
  sudoku.
- Size `--tmp_ram_fs_gib` from the payload before launching a 20M-row corpus.
  `sync_dataset_to_local` mirrors the split into `/tmp`, a Borg RAM disk
  (default 16 GiB), once per task. A corpus holds more than the loader reads:
  Setting-A ones ship a `shards/` tree as large as the payload, now skipped with
  `seeds.npy` and `provenance.json` by `_UNUSED_BY_TRAINING`. Read `Staged N
  MB`.
- `_UNUSED_BY_TRAINING` skips `shards/` but not `parts/`, so a mirror can hold
  generation intermediates. A training run stages the full split (`staging={}`),
  so a mirror carrying an extra `parts/` tree can overflow the RAM disk and die
  `OSError: [Errno 28] No space left on device` in `sync_dataset_to_local` at
  step 0, every retry. The launcher calls that "Job terminated in state
  FAILURE", not "CODE BUG": read the attempt log for the ENOSPC before blaming
  the arm you changed. Fix: a clean mirror, `parts` in `_UNUSED_BY_TRAINING`, or
  delete the intermediates. (Seen on settingB-v3 adv: `nm-d`/`li-d` clean 69G,
  `is-d` an extra 78G `parts/`, 227G total, overflowing a 92 GiB disk.)
- The maze grid is `30 x 30` holding a `29 x 29` perfect maze, padded, not
  cropped. `_generate_perfect_maze` needs an odd size, so it takes
  `maze_n = n if n % 2 else n - 1` and writes `open_mask[:29, :29]`. Row 29 and
  column 29 stay wall on every sample.

### Run length and the "epoch" trap

- **`training.total_steps` is the only run-length input** and the train loader
  is endless. `epochs`, `max_steps` and `train_epochs_per_iter` are retired and
  raise naming their successor; a fixed-size corpus prints its epoch budget as a
  report, never a stopping rule. Default run length is 150k steps for maze-128.
- An "epoch" here was never a pass over the data: every builder writes
  `mean_puzzle_examples = 1` and every corpus holds 1000 groups, so
  `steps_per_epoch` floored to 1 and `epochs: 50000` meant 50,000 steps.
  Distrust the concept in an old config or checkpoint.

### Never sync a file between the two checkouts wholesale

**Copy behavior by reading both code paths, never by syncing a file**
(`../engineering.md` §Porting between related checkouts). This repo lost
`_online_eval` from `train.py` that way while nine yamls kept setting
`evaluation.online_eval`.

---

## Chapter 2 — Operating A Run

### Launch and packaging

- **Edit the unrestricted home checkout, launch from a `/tmp` copy.** Packaging
  is a unique CitC snapshot, so post-package edits never reach the job, and
  several agents share the checkout (`../jobs/submit.md` §The launcher, config, and packaging).
  `rsync -aL` the tree minus `.git`/`data`/`logs`, write the config there, then
  `tpu enqueue` *from* that copy: the default serial path (`../jobs.md`), which
  records the copy as the entry `workdir`. `-aL` is required because
  `xm_launcher.py` is an absolute symlink and Bazel will not glob a package
  containing one. Delete the copy only *after* the build-worker has built it (`tpu
  queue-status` shows SUBMITTED) — a `workdir` that vanishes before its turn is
  parked HELD, not packaged.
- Write the run into `configs/remote_run_config.yml` and launch without a config
  argument (`../jobs/submit.md` §The launcher, config, and packaging). EqR-jax consequence: `configs/`
  holds only templates (`local_debug`, `remote_run`, per-task); recover a
  finished experiment's config from its snapshot with `sexy <xid>`. Launching by
  config name leaves a file behind.
- EqR-jax uses XManager service tiers (`PROD` / `BATCH`), not legacy
  `xm_priority`; resource selection and allocator constraints are `../jobs.md`.
- Treat the active BUILD target and launcher as authoritative: entry point in
  `srcs`, other Python/config files as `data`, `testonly` deps excluded from the
  production target, configs resolved through runfiles. Keep ordinary local
  imports working through the entry point's execution-directory setup; do not
  rewrite them to a hard-coded google3 staging package.

### Dies before `main()`

Every trap below fails at module-import time, which on Borg means an empty
`status.message` and no log at all. **Reproduce locally in ~45s instead of
guessing** (`../jobs/diagnose.md` §Debugging A Job That Dies With No Log).
`strict_deps = False` hides all the packaging ones at build time, so a green
build proves nothing.

| Trap | Fix |
|---|---|
| `import wandb` resolves via `//third_party/py/scamper:wandb_mock`, whose `imports = ["wandb_mock"]` the hermetic launcher ignores | `main.py` adds the runfiles directory to `sys.path` explicitly |
| `//third_party/py/pydantic` is v1-only (empty top-level `__init__.py`) | `pydantic.BaseModel` needs `:pydantic_v2` |
| The wandb mock has no `sdk` submodule, and `wandb.sdk.*` in an annotation is evaluated at class-creation time | quote the annotation |
| Under Bazel the CWD is inside `main.runfiles/google3`, so the yaml may not sit where `__file__` implies | `configs/load_config.py` searches several roots; never key discovery on `__file__` alone |

JAX startup order: do not call `jax.distributed.initialize()`. google3's JAX
self-initializes on first backend use from the `--jax_port` /
`--jax_controller_address` flags XManager injects
(`jax_google.py::_lazy_initialization`); calling it duplicates that work, and
without the flags it raises `ValueError: coordinator_address should be defined`.
Nothing before that point may touch JAX: `log_for_0` asks `jax.process_index()`
who it is, booting the backend and making init illegal
(`RuntimeError: ... must be called before any JAX calls`), so `main.py` uses a
JAX-free `_boot_log`.

### Data and checkpoint locality

`../storage.md` owns the rule: co-locate compute with storage or the pruner
deletes the job. Both halves are automatic and overridable, and **adding a
compute cell means mirroring the data and adding both entries**:

| Resolver | Picks | Override |
|---|---|---|
| `dataset/data_util.py::_local_data_root` | dataset mirror matching `$BORG_CELL` / `$CLOUD_ZONE` from `_MIRRORS`; an unlisted cell keeps the old default rather than inventing a path | `$EQR_DATA_ROOT` |
| `tpu_cmd/xm_launcher.py::_local_bucket` | checkpoint bucket matching `--cell` from `_CELL_BUCKETS` | `--bucket` |

A run reads its own metro's mirror. The five mirror dicts in `data_util.py`
(`_MIRRORS`, `_OFFLINE_MIRRORS`, `_SETTINGA_MIRRORS`, `_SETTINGB_MIRRORS`,
`_SETTINGB_V3_MIRRORS`) share one cell→root mapping; keep them in sync when
adding a cell:

| metro | data cell | v-family | completeness |
|---|---|---|---|
| cbf | `is-d` | v7 | full (generation source) |
| tul | `nm-d` (data) / `oi-d` (ckpt) | v7 | full |
| lpp | `li-d` | v7 | full |
| dfw | `rs-d` | v4 | full (all datasets; added for cheap v4) |
| las | `dl-d` | v4 | PARTIAL — maze v4 working set only (64x64-offline + companions + settingA/B); NOT settingB_v3 / 128x128 |

Since `las`/`dl-d` is partial, `../storage.md` §Existence Is Not Completeness
bites: check `_MIRRORED`/`_SUCCESS` on `dl-d` before pinning a job there.
`research/v7_storage_placement.md` owns the cell survey and the `las` naming
trap (`la-d`/`lb-d` are `lpp`, not `las`; only `dl-d` is `las`).

**Every host must read the checkpoint itself.** Having rank 0 read and
`broadcast_one_to_all`, instead of N hosts amplifying the read, halts the TPU
core with `RuntimeUnexpectedCoreHalt` *after* the read succeeds:
`ocp.Checkpointer.restore()` is itself a collective ending in a
`sync_global_processes` barrier. It is unpatchable as written, since non-readers
cannot predict the dtype orbax returns; `ckpt_util.py` records the one
construction that would work (`MultiprocessingOptions(primary_host=0,
active_processes={0})`). Distance has a fix here, read amplification does not.

**A host-local single-device model cannot be orbax-saved unchanged on a
multi-host slice.** The DP-CNN baseline (`dp_train.py`) shards nothing — every
host runs an identically-seeded replica — so its params are
`SingleDeviceSharding` `jax.Array`s, and `ocp.StandardCheckpointer.save` refuses
them when `jax.process_count() > 1` (`ValueError: Cannot serialize host local
jax.Array ... in multi-host setting`). `active_processes={0}` skips the write
*barrier* but not this check, so it crashes only on a real ≥2-host Borg slice at
the first save (step_100); no single-process or hermetic smoke catches it. Fix:
`jax.device_get` the payload to host numpy before save, and restore into a numpy
target symmetrically.

### Loader and sampler state

- Verify a resume by step progress, not exit status (`../jobs/liveness.md`
  §Preemption, Restart, And Resume). The retired `epochs /
  train_epochs_per_iter` design checkpointed an exhausted cursor, so a resume
  evaluated `while N < N`, yielded zero batches, and exited 0 — every restart
  looking like a clean success.
- Anything added to sampler state must be O(1) in corpus size; otherwise store
  the seed and replay it. Persisting `group_order` = `rng.permutation(num_groups)`
  meant 3.8M integers in a 45 MB `extra.json` rewritten every save, and a
  mid-write deletion left the resume parsing its own truncated bookkeeping.
  Replay needs the state from *before* the draw, so `epoch_rng_state` is stored
  (`rng_state` has already advanced) and `_iter_train` replays the permutation.
- Cast a `np.searchsorted` key to the index array's dtype. The arrays are
  `int32` and a Python `int` is int64, so NumPy upcasts the *entire* array every
  batch: 364x on `_iter_test`, ~20 hours instead of ~3 minutes per pass over a
  20M-row split. Throughput pinned at constant batches/s regardless of batch
  size means a fixed per-batch cost, not an I/O problem.
- A batch larger than the split makes the loader spin silently: the train path
  is drop-last, so it yields nothing, re-shuffles, yields nothing again — 100%
  CPU, no batches, no error, forever. Clamp with `min(batch_size, n)`; a global
  batch larger than a small eval split hangs the run too.

Both loader defects were invisible while every split was 1k rows and bite harder
the larger the corpus; re-check them if either is reverted.

---

## Chapter 3 — Reading The Numbers

### Experiment tracking: the logging surface

Config fields keep historical `wandb` names; no API key is needed, and there is
no real external tracker unless current code proves one was created.

- **`import wandb` resolves to a mock** implementing only `init`, `log`,
  `finish`, `Table`, `plot`, `Video`, whose `log()` stores nothing; every other
  attribute raises at call time — on Borg, after packaging and scheduling. Route
  calls through `utils/wandb_util.py`, whose `safe_log()` swallows failures;
  telemetry must not kill a run.
- Metrics reach a UI through Datatables via `clu.metric_writers`; URLs and the
  explicit-opt-in trap are `../research/result_logging.md` §Chart Links, and
  reading them back is the same file, §Reading The Curves From The Workstation.
  The torch port (`EqR-torch-maze128`) also mirrors every logged train row into
  its CNS beacon (`<bucket>/sanity/<XID>_<WID>_att<N>_rank0.jsonl`, event
  `train_metrics`), so its acceptance metric needs no service. Only
  `process_index()==0` may build a writer, and it must flush periodically, since
  CLU's destructor cancels the writer thread rather than draining it.
- Anything that builds a logging handler unhooks the remote log mirror, which
  under Borg is the only log. `main.py` tees stdout/stderr to
  `$CHECKPOINT_BUCKET/logs/rank_<n>.log`, but stdlib handlers capture the stream
  they were constructed with, so a metric writer steals it back and the log
  stops dead mid-run. Call `logging_util.reattach_absl_handlers()` afterwards;
  it repoints `get_absl_handler().python_handler`, not the outer object.
- Resume uses the experiment identity (`resume_xid`) and its workdir; verify
  checkpoint and config continuity before treating appended charts as one run.
  Checkpoints go to `$CHECKPOINT_BUCKET`, never `workdir`;
  `main.py::_apply_borg_autoresume` rediscovers the newest complete one at
  startup, and `../jobs.md` owns the env-var contract.
- Log a run that reaches a conclusion to the `EqR-refactored` tab, never
  `EqR-reproduction` (history); `../research/result_logging.md` owns how.
- Maze runs use `v7-32`: `v7-16` buys half the compute for the same wall clock,
  and the family's published rows are all v7-32. One ACT step is
  `H_cycles * (L_cycles + 1) * L_layers` layers (84 at the 3/6/4 default) and
  training unrolls the full `halt_max_steps`, so a 100k-step maze leg already
  runs ~8 hours at v7-16's measured 3.53 steps/s.

### Which key is it

**A logged key is not a delivered column, and nothing says so.**
`_flatten_scalars` in `utils/wandb_util.py` silently drops anything not
float-able (histogram, figure, array, bool, string, NaN) on the way to
Datatables, and the `wandb` mock stores nothing either. So a metric can be
computed every step for a feature's whole life and reach no reader, with no
error at either end. Verify a new metric by printing the payload the run
actually logs, not by testing the function that builds it.

Every logged eval column names its point and its weights, as
`D<depth>[B<breadth>]/{ema,online}/...`, and appears exactly once; charts use
`D16/ema/acc`. Two levels are gone from the sink: the `eval/depth`-style
coordinates (they print to the log), and the dataset `set` level (every corpus
declares `sets=["all"]`); a dataset with two sets makes it reappear.

**Several keys are called `lm_loss`. Name the one you mean.** They differ in
split, weights, denominator and cadence (eval ~30 points vs train ~1500).
Quoting the train curve at an eval-chart reader has inverted a real conclusion.

| Key | Source |
|---|---|
| `train/lm_loss` | train split, train cadence |
| `D<k>/{ema,online}/all/lm_loss` | online eval, per depth and weight set |
| `{ema,online}/all/lm_loss` | standalone eval; `all/lm_loss` in its results json |

`token_acc` is not comparable across output formats: a grid head's covers 900
board cells of which ~884 copy the observation, an AR head's `n_predict + 1`
real predictions, so two runs of one task can differ 53x in denominator. `acc`
(whole answer right) is the comparable column.

### Divisors and cadence

- **Loss keys are sums over rows and the divisor is `global_batch_size`, not
  `count`.** `train.py::process_metrics` picks per key: keys ending in `loss`
  divide by `global_batch_size`, most others by `count`, which counts only rows
  that halted that step. Dividing a loss by it inflates the number ~100x and
  still looks plausible.
- A logged `train/*` value is the whole interval, not one batch:
  `StepAccumulator` folds every step and the step on the `log_per_step` grid
  drains it, divisor scaled by the interval. Compare runs on a tail-window mean
  over the logged curve, not the last row. There is no smoothing knob: the one
  that existed averaged the pre-denominator sums, making its "smoothed loss"
  ~`global_batch_size` times real.
- `train/lm_loss` is not comparable across runs that halt at different depths: a
  run pinned at `halt_max_steps` buys its lower loss with more compute. Check
  `train/act_loops_mean` first; if the depths differ, use a fixed-depth eval.

### Denominators and padding rows

**An eval's denominator is its real rows, not the rows it was fed.** Feeding
more rows than the split holds is legal — a `512 x 2` maze eval feeds 1024 for
1000 puzzles — and `puzzle_dataset._collate_batch` pads the tail with
`labels = IGNORE_LABEL_ID`. Pad rows are excluded rather than scored: the loss
head gates on `valid = loss_counts > 0`, tallies filter through
`eval_fn._drop_unscorable`, and `different_init/total_samples` reports the real
count. Do not apply a hand correction on top; that now UNDER-reports. Before the
fix a pad row satisfied `((pred == labels) | ~mask).all(-1)` vacuously and
counted as a perfect solve, once manufacturing a whole maze accuracy out of 24
pad rows.

Two cross-checks. Read `total_samples` to confirm which regime a number came
from. Check `different_init/avg_pass_rate` against `acc` of the same weight set
(`ema/` with `ema/`, never across): one quantity by two routes, so they agree
exactly or something is wrong. On a unique-solution split the solution metric
and `acc` must also agree exactly (§Maze scoring).

### Harvesting Final Train Metrics

`../research/result_logging.md` §Every Row Carries Its Train Metrics owns *why*
every row needs its train columns; this owns *where the numbers are* when the
run was preempted and the obvious log looks empty.

**Only jax process 0 prints per-step train metrics, and after a preemption that
worker is a different physical log file.** The line to grep is
`[Info] [<step>/<total> <pct>%] loss=.. lm_loss=.. acc=.. exact=..`; it appears
only in the `rank_<n>.log` whose banner says `borg task <n> == jax process 0`.
That mapping is reshuffled on every retry, so the rank carrying the curve in
`attempt1` rarely carries it in the final one, and the old "proc0" rank reads
empty — mis-filed as "log rotated". The final segment is in a rank you have not
read yet.

Procedure (the run reached `step_<budget>`, so the curve exists). A size sort,
not a rank scan, sidesteps both traps below in one `ls`:

1. `fileutil ls` by size, not by rank. The log holding the curve is by far the
   largest.
   ```bash
   fileutil ls -l "$LOGDIR/logs/" | grep rank_ \
     | awk '{print $5, $NF}' | sort -rn | head -5   # size, path — biggest = training log
   ```
   Confirm its last progress line reached the budget
   (`grep -E '\[Info\] \[[0-9]+/<budget>' <file> | tail -1`); else take the
   next-largest that reached it.
2. Tail-window mean the last ~10 progress lines, not the single last row
   (§Divisors and cadence). Field map to `EqR-refactored` columns: `lm_loss=` →
   `final train/lm_loss`; `acc=` → `final train/token_acc`; `exact=` →
   `final train/acc` (whole-board exact).
3. `extra.json` in the checkpoint dir confirms `step` / `total_steps` (proof the
   run finished) but carries no metrics.

Two traps the size sort avoids: rank count follows topology, not a fixed 8 (a
`v6p-32` maze run has 64 hosts, so jax process 0 can be `rank_33`; derive the
range, never hard-code `seq 0 7`); and the last attempt is often eval-only
(after the final preemption the run reloads `step_<budget>` and evaluates, so
the final training segment is in an *earlier* attempt).

### Checkpoint retention: keep the peak

**The retained set is the result.** A peak whose weights were deleted cannot be
re-evaluated, published, or recovered by re-scoring.

- `training.checkpoint_best_metric` promotes the best step to
  `checkpoint_best_<metric>_<n>/`, outside the `step_<N>` namespace retention
  rules match, so the pruner, `tpu gc` and auto-resume ignore it. Without it the
  default policy (newest 2 plus a 50k ladder) deletes the peak your result needs,
  because this family peaks off the ladder: 120k of 150k on maze, 40-45k of 50k
  on sudoku. Auto-resume restores the newest checkpoint, never the best.
- `checkpoint_interval_steps` must divide `eval_interval_steps`, so every
  evaluated step has a checkpoint behind it. Config load does not check the
  relation and `promote_best_checkpoint` warns and skips, so a violated ratio
  costs the peak silently, one eval at a time. Both default to the same value in
  `configs/default.py`; a config overriding one must re-check. Verify by reading
  both keys in the config you are launching — `grep -n '_interval_steps'
  configs/<name>_config.yml` — never from the last run's numbers
  (`remote_run_config.yml` is overwritten by every launch, and smoke templates
  use single-digit intervals).
- Track several metrics; a policy driven by one inherits that metric's bugs.
  Paid once, when `auto` resolved to the single buggy key `solution_acc`. `auto`
  now keeps the best under every headline key the run reports (`walk_acc`,
  `solution_acc`, `acc`), one deduplicated directory each, so a metric fix costs
  a re-score, not the run. `"auto"` resolves against the first real metrics
  dict, not the config; `_BEST_METRIC_PREFERENCE` in `utils/ckpt_util.py` is the
  list in headline order, `resolve_best_metrics` the resolution. Read that tuple
  in the checkout you launch — a fully-qualified entry (`D16/ema/acc`) matches an
  exact key, a bare name (`acc`) matches `<point>/ema/<name>` at the shallowest
  breadth-1 point. Finding nothing disables retention behind one warning, after
  which the ladder deletes the peak; smoke the launched graph with the run's real
  `halt_max_steps` and `online_eval` and read the "tracking …" line.
- Never point an eval at a ladder checkpoint of a running job: it races that
  job's `checkpoint_keep_last` and loses (`FileNotFoundError` on a path that
  existed when typed). Target what retention exempts — a milestone
  (`checkpoint_milestone_every`) or a `checkpoint_best_*`.
- Never sweep a name you do not recognise. A retention rule that cannot prove a
  copy is superseded (unreadable sidecar, no metric named) keeps it: a kept copy
  costs disk a tool can report, a deleted one costs weights nobody can reproduce.

### Eval protocol: report B=1 first

**The headline number for any EqR run is accuracy at B=1** (one restart, no
selection) at both depths the paper uses: D=16 (the arch's own `halt_max_steps`)
and D=64 (its depth-scaling point). Breadth is an extra — it multiplies eval cost
by B. Which accuracy depends on the dataset: `acc` on sudoku, `solution_acc` /
`walk_acc` on a maze (§Maze scoring), both from the same eval.

A run reports its own headline; a second job is not required.
`evaluation.online_eval` names the (depth, breadth) points the in-training eval
scores every `training.eval_interval_steps`, and its default `[16, 64]` at B=1
on both weight sets is the protocol above — a run's result is
`D16/{ema,online}/acc` (or `walk_acc`) on its own training curve.
`online_eval: []` restores the old single-point behavior. The `EqR-refactored`
tab matches: `Acc B=1 D=16`, `Acc B=1 D=64`, `Acc-any-correct (B=1)`, then
`additional results`.

- **Comparability rests on the sample count, which `online_eval` does not
  control.** The population is `evaluation.global_batch_size x max_eval_steps`,
  and the test loader walks the split in order from the start, so two evals with
  the same product score the same rows at any batch size. Keep a training
  config's product equal to the standalone protocol's, or its curve is not
  comparable to an `eval_only` row. Sudoku scores a FIXED 2048-row subset of
  422,786 (comparable to upstream's 2048-sample figure, not its full split);
  maze covers the whole 1000-puzzle split. Leaving `max_eval_steps` unset walks
  the entire split every interval.
- An eval batch is only correct against a device count, and a chip count is not
  one. `check_eval_batch_layout` needs `global_batch / process_count %
  local_devices == 0`. A `v7-32` is 64 devices over 8 hosts, so `500` gives
  `500/8 = 62`, `62 % 8 != 0`, raising before step 1. Prefer over-feeding: on a
  1000-row maze split no divisor of 1000 is a multiple of 64, so `512 x 2 =
  1024` is the answer; `TEST_POPULATIONS` caps the walk at the first 1000 rows
  and `drop_unscorable` removes the pad, so the scored population is unchanged.
- **Set `evaluation.final_eval: true` with a non-empty `evaluation.sweep`** to
  get breadth and convergence-top-k columns against the final checkpoint without
  a second launch (off by default; an empty sweep with it on is rejected). A
  breadth eval can silently deliver less breadth: restart latents come from a
  key broadcast to every device, so effective breadth is `min(per_device_rows,
  n_init)` and B replicas straddling devices get duplicate latents —
  `different_init/any_correct` and `convergence_top_k` then under-report. Config
  load refuses such a layout; apply the rule when sizing by hand.
- **The paper's B=128 figure (Maze 93.0) is top-1 convergence accuracy** — the
  restart with the smallest mean residual over the last L=3 iterations, not
  majority vote (which the paper never reports). Do not swap in the higher
  number: the weaker selector is the point (it tests whether latent convergence
  predicts solution quality). A breadth metric falling as depth rises is
  expected: deeper reasoning makes restarts agree, so diversity falls, while base
  `acc` improves (82.61 → 89.30, reproducing the paper's 82.2 → 88.9).

### Maze scoring: is the output a solution

A generative loop *produces* an answer, so the question is "is this a solution",
not "does it equal the stored one". Those coincide only when the answer is
unique, and every stock maze split here is `perfect` (acyclic, one S->G path),
so `acc` answers the reproduction question while being read as the solving one:
harmless there, wrong off it.

- **`solution_acc` (grid heads) / `walk_acc` (`final_head_type: ar`) is the maze
  headline**, with `acc` beside it as a diagnostic. Scoring auto-enables on a
  maze dataset, `evaluation.solution_scoring` forces it either way. A maze run's
  result is `D16/ema/walk_acc` where `D16/ema/acc` is for sudoku.
- On a unique-solution split the solution metric and `acc` must agree exactly,
  row for row; a divergence is a scorer bug. Use that as the scorer's test.
- Use `Maze-30x30-multi` whenever the claim is about solving: 1000 fixed braided
  mazes, each with >=2 shortest paths. One checkpoint scores 40.2 exact vs 99.3
  solution (D16, EMA), since a solver picking uniformly among shortest paths
  matches the label only 36.5% of the time.
- A grid head's `solution_acc` needs both a legal S->G route in the painted
  cells AND every unpainted cell still equal to the input board (without the
  second, a route over a board with S painted over scored solved while `acc`
  said wrong). `walk_acc` has no off-path cells to get wrong, so on a unique
  split `solution_acc` equals `acc` while `walk_acc` is looser. Both scorers
  check against the INPUT board, never the label; `maze_solution.py` and
  `maze_walk.py` are one definition for two formats.
- A longer legal route counts as solved, deliberately; `shortest_solution_acc` /
  `shortest_walk_acc` carry the strict number, BFSed from the row's own input
  board. The empty prediction must be rejected explicitly (`_row_exact_correct`
  guards on `supervised > 0`). A test-only split still needs a `train/`
  directory, because `just_evaluate` reads `vocab_size`/`seq_len` from it.
- Which number is a bound: a scorer reading only part of the output can only
  over-report (re-score; on a unique split the corrected value is that run's own
  `acc`). A `shortest_*` from before the input-board BFS is a lower bound. Two
  one-directional errors in opposite directions do NOT compose into a bound —
  state which fixes a number predates before calling it a bound.
- **Periodic-wall (Setting-A) corpora** (`Maze-period-easy` / `Maze-period-hard`,
  20M train + 1k test, `_SETTINGA_MIRRORS`) need the clocked scorer, and the
  wrong one scores the ground truth zero. `eval_fn.maze_scoring` picks
  `maze_periodic.py` when `P = vocab - 6 > 0`. Symptom of the wrong scorer:
  `solution_acc` at 0.0 all run while `acc` climbs — check the `[eval] maze
  solution scoring ON` line first. Score is `2^-floor(e/2)` for `easy` (P=2,
  vocab 8) but `2^-e` for `hard` (P=3, vocab 9); `hard` exists because P=2
  admits an O(1) shortcut. Full spec: `~/work/maze_settingA_data/DATASET_SPEC.md`.

### Close-loop: the headline scores ONE decision point

A close-loop puzzle (`dataset.closeloop`) is an episode. **The default
`dataset.closeloop_mode: persistent` gives one row one whole episode**: the ACT
latent `z` walks its decision points and keeps its value across each world
timestep, so training covers every decision point in order. The flatten-to-
independent-rows behavior survives only as the ablation arm `closeloop_mode:
flat`.

The test split is flat in both modes and fixes its timestep, so the reported
`acc` describes one decision point per episode, the easiest one (at the first
decision the phase rotation `(phase - t) % P` is the identity and the
observation is bit-identical to the stored board). An optimizer step advances a
row by one ACT step, not one decision, so an episode occupies
`n_decisions x halt_max_steps` steps (on the staged P=2 split: 104 shortest,
144.50 mean, 288 longest, ~9x fewer puzzles per step than open-loop D=16's 16).
`dataset.closeloop_refresh_every` (default 16) reuses one device batch for K
steps; config load refuses `K >= min_decisions x D`.

- A saturated `acc` is expected, not a strong result: the per-decision task
  carries no signal for this arch (a stratified sweep found 1.0000 everywhere).
  The signal is in the rollout (`evaluators/closeloop_eval.py`), where the
  model's own errors take it off the GT trajectory. Budget against the rollout
  metric, not `acc`; `acc ** d` is not an episode-success estimate. Measure other
  points with `dataset.test_decision_index` (index into the episode's own
  decision points; `-1` is structurally different — report it separately).
- `solution_acc` / `walk_acc` are both refused under close-loop (a segment stops
  `n_predict` moves along and never reaches G, so "route to G" is false on the
  label). `acc` and `token_acc` are the columns until the rollout metric lands;
  say so in the config header. `state_token_acc` has a do-nothing ~0.998 floor on
  P=2 (a rotation by `k = n_execute = 8` ticks is the identity); score changed
  cells only, or pick a `k` not a multiple of `P`.
- `arch.train_halt_head` defaults OFF under close-loop (the halt head decides
  when a TIMESTEP is settled, not when a puzzle is answered).
  `configs/local_debug_closeloop_config.yml` needs `--timeout 5400` (vs the 300s
  default), nearly all of it the rollout eval; `evaluation.closeloop_scoring:
  false` finishes in ~7 min if the claim is only "the pipeline runs".

---

## Chapter 4 — The RoboTwin DP Baseline

The RoboTwin 2.0 Diffusion-Policy (DP-CNN) baseline is on branch
`dp_dataloader_rewrite` (`dp_train.py`, `dataset/robotwin_dataset.py`,
`configs/remote_run_dp_config.yml` + `configs/dp_default.py`). The model is
single-device replicated: every host runs an identical seeded replica, one chip
does the work. So it is host/data-bound, not TPU-bound. `../storage.md` and
`../jobs.md` own launching; DP-specific facts are here.

### The five fixed ablation tasks

**The 5 ablation tasks are fixed — always use these five, never re-pick.** All 50
`clean_50` tasks cost ~26 h of accelerator time (~32 min/task); these 5 span the
skill families with none repeated. RoboTwin 2.0 has no official taxonomy, so the
grouping is derived and code-verified against `envs/*.py`.

| Task | Skill family (unique) | Arm | Object | Horizon (steps) | DP-Easy |
|---|---|---|---|---:|---:|
| `open_microwave` | articulated open (revolute door) | single | articulated | 537 (longest) | ? |
| `handover_block` | dual-arm handover | dual | rigid | 283 | 10% |
| `stack_blocks_three` | stacking (precise, long) | single | rigid | 481 | ? |
| `dump_bin_bigbin` | pour / granular (only non-rigid) | dual | granular | 265 | 49% |
| `beat_block_hammer` | tool-use (strike) | single | rigid+tool | 113 (shortest) | 42% |

Why this set: five disjoint skills and no plain pick-and-place (15 of the 50
tasks); object types cover articulated + rigid + granular; DP-Easy is a real
low->mid spread, not saturated or dead, so an ablation has signal.

### Running the baseline

- The dataloader is eager-decode-to-RAM (`dataset.eager_images: true`,
  `num_workers: 0`). A `clean_50` task is tiny (~3855 rows, 173 MB JPEG on disk,
  888 MB/camera decoded), so it decodes into RAM once (~2.6 s) then serves by
  O(1) index. Single-process reached 2.65 -> 12.1 batches/s; the
  `num_workers=16` pool reached only 5.0, IPC-bound (pickling ~88 MB/batch), not
  CPU-bound. End-to-end on a v7-8 the run holds ~10.4 steps/s. Leave eager OFF
  only for a corpus too large for host RAM.
- The v7 minimum slice is 8 chips, though `tpu preflight v7-4` reports GREEN:
  the allocator's min-slice rule blocks v7-4 with no work unit created. Use
  `v7-8` for a single-host-class DP probe (2 hosts x 4 chips). yumrnel g9 PROD
  is the proven-hold cell; its co-located bucket is `/cns/qo-d`.
- DP logging matches the EqR `train.py` progress line (`[step/total pct%] loss=,
  lr=, steps_per_second=`). Do not wrap the train loop in `prefetch_to_device`:
  its background thread runs the loader cursor ahead of the trainer, the
  `dataloader_state` sidecar records that advanced cursor, and a resume then
  skips those batches, breaking the O(1) resume contract.
- **Per-task training cost varies ~4.3x** (`total_steps =
  floor(n_windows/128) * 600`, n_windows 5572 for `beat_block_hammer` to 23902
  for `open_microwave`). For an EQUAL-COST ablation, cap with
  `training.max_steps`, not a fixed `num_epochs`. Results log to the
  `RoboTwin-DP` tab of the EqR workbook
  (`17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`): one row per task, training
  metrics + close-loop `success_rate`.

### Close-loop eval on the A100 (SAPIEN)

**The GPU-side close-loop evaluator is a SEPARATE manual step, not
auto-triggered.** GCS is the only rendezvous, since a Borg task cannot open an
IPv4 socket to the VM and the VM cannot read CNS. Training publishes each
checkpoint to the bucket
(`gs://qiaos-robotwin-eval-us-east4/runs/<xid>/checkpoints/step_<n>/`, state +
`extra.json` with the normalizer + `dataloader_state`); the eval is a worker on
the A100 VM `deepflow-1a100-80gb-jh-baseline` (34.186.64.63, us-east4-c, project
`viscam-cloud`), code at `~/work/robotwin_eval_bridge`.

- SSH from a restricted agent shell cannot `gcert`, but the metadata key works:
  `ssh -i ~/.ssh/google_compute_engine -o ProxyCommand="/usr/bin/corp-ssh-helper
  --proxy-mode=grue %h %p" qiaos@34.186.64.63` (network gate and auth gate fail
  separately, `../gcp_gpu_ssh.md`).
- Run: `~/work/jax_venv/bin/python eval_worker.py --task <T> --xid <X> --rollouts
  50 --on-backlog latest --interval 0`. It auto-spawns `sim_server.py` in
  `rt_venv` (numpy-1.x, SAPIEN); one worker maps one `--task` to all its XIDs, so
  a fleet needs one invocation per (task, xid). Drive serially from a `setsid`
  script (N=1 optimal; N>=2 drops throughput ~30%). Use a fresh `--state` file or
  a re-eval is skipped.
- Speed ~60 s/rollout (400-step episode), so 50 rollouts ~= 50 min/task. Uses
  EMA weights + the checkpoint's own normalizer. wandb on the VM is not logged
  in, so eval runs `WANDB_MODE=offline` or `--no-wandb`.
- Reference: click_bell (prior run 279324385) step_17400 scored 0.50 (25/50);
  the scripted expert hit 20/20 on the same seeds, so the harness is sound and
  0.50 is the model's real score.
