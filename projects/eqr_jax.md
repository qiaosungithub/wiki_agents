# EqR And EqR-jax

Read this for the `EqR` and `EqR-jax` checkouts. They are distinct PyTorch and
JAX implementations; inspect the target checkout's native docs and git state
before porting behavior. `jobs.md` owns launches and job diagnosis.

## Data And Model Invariants

- `EqR-jax` maps configured dataset aliases in `data_util.py`; verify the live
  mapping for names such as `Maze-dynamic` and `Sudoku-aug1000` instead of
  rewriting paths in launch commands.
- The maze library's `grid_n=15` sample is `31 x 31`, while EqR consumes
  `30 x 30`. Preserve the existing top-left crop and path-length scaling unless
  the task explicitly changes the representation.
- Do not transfer checkpoint, logging, or runtime assumptions between the
  PyTorch and JAX implementations without checking both code paths.
- **Never sync a file between the two checkouts wholesale** (`engineering.md`
  §Porting Between Related Checkouts). This repo already lost `_online_eval`
  from `train.py` that way while nine yamls kept setting `evaluation.online_eval`
  — the config promised a D16/D64 curve and the code measured one point, for
  eleven commits.
- **`puzzle_emb_ndim: 128, puzzle_emb_len: 16` is ONE register plus fifteen dead
  slots.** `_input_embeddings` reshapes the `ndim`-wide table row into
  `puzzle_emb_len * hidden_size` and zero-pads the shortfall, so only the first
  slot carries table content; the rest are constant zeros that never receive
  gradient. All sixteen still shift every real token's rope index, and the
  q-head still reads slot 0. Faithful to upstream, but describe such a run as
  one register, not sixteen.
- **A zero-initialised trainable register is not equivalent to a small random
  one.** The table does receive gradient from step 0 and does grow (verifiable
  in `params/inner/puzzle_emb` across checkpoints), so "it never moves" is the
  wrong worry. The failure is early symmetry: with registers on, the q-head
  reads a register slot rather than a board cell, and a zero slot feeds it
  nothing during the steps that decide whether ACT ever learns to halt. Treat
  `puzzle_emb_init_std` as a load-bearing hyperparameter and ablate it
  alongside any register experiment.

## Launch And Packaging

- Edit the unrestricted home checkout. `tpu queue` creates a unique CitC source
  snapshot, repoints the staged target, and packages that snapshot. Post-package
  edits to the home checkout do not affect the job.
- **Write the run into `configs/remote_run_config.yml` and launch without a
  config argument.** `jobs.md` §Submission Contract owns this rule; the
  EqR-jax consequence is that `configs/` holds ONLY templates — `local_debug`,
  `remote_run`, and at most three task templates. A finished experiment's config
  is recovered from its immutable snapshot with `sexy <xid>`, not by keeping a
  file per run. The directory has been pruned twice already because launching by
  config name made every launch leave a file behind.
- EqR-jax uses XManager service tiers (`PROD` or `BATCH`), not legacy
  `xm_priority`. Resource selection and allocator constraints are in `jobs.md`.
- Treat the active BUILD target and launcher as authoritative. The current
  Bazel compatibility contract keeps the entry point in `srcs`, packages other
  Python/config files as `data`, excludes `testonly` dependencies from the
  production target, and resolves configs through runfiles.
- Preserve ordinary local imports through the entry point's execution-directory
  setup. Do not rewrite them to a hard-coded Google3 staging package. Any
  validation suppression is a narrow, current workaround to re-evaluate, not a
  general build rule.

## Google3 Packaging Traps

These all fail at module-import time, before `main()`, which on Borg looks like
an empty `status.message` and no log at all. Reproduce locally in ~45s instead
of guessing (see `jobs.md` §Debugging A Job That Dies With No Log):

- **`import wandb`** resolves via `//third_party/py/scamper:wandb_mock`, whose
  `imports = ["wandb_mock"]` attribute the hermetic launcher ignores. `main.py`
  adds the runfiles directory to `sys.path` explicitly.
- **`//third_party/py/pydantic` is v1-only** (its top-level `__init__.py` is
  empty); `pydantic.BaseModel` needs `:pydantic_v2`.
- The wandb mock has **no `sdk` submodule**, so `wandb.sdk.*` in a type
  annotation must be quoted or it is evaluated at class-creation time.
- **`strict_deps = False` hides all of the above at build time.** A green build
  proves nothing; run the binary.
- Config discovery must not rely on `__file__` alone — under Bazel the CWD is
  inside `main.runfiles/google3` and the yaml may not sit where `__file__`
  implies. `configs/load_config.py` searches several roots.

## JAX Startup Order

- **Do not call `jax.distributed.initialize()`.** google3's JAX self-initialises
  on first backend use, driven by the `--jax_port` / `--jax_controller_address`
  flags XManager injects (`jax_google.py::_lazy_initialization`). Calling it
  yourself either duplicates that work or, with the flags absent, raises
  `ValueError: coordinator_address should be defined`.
- Nothing before that point may touch JAX. `log_for_0` asks
  `jax.process_index()` who it is, which boots the backend and then makes
  initialisation illegal (`RuntimeError: ... must be called before any JAX
  calls`). `main.py` uses a JAX-free `_boot_log` during startup.

## Evaluating A Published Checkpoint

- `extra.json` records only the fields that were **overridden** at training
  time. `_resolve_eval_config` must MERGE that over the config defaults, not
  replace the section, or `hidden_size`/`num_heads`/`L_layers` vanish and
  pydantic reports `Field required [type=missing]`.
- Dataset names in a checkpoint may not match `DATASET_PATHS`. The published
  sudoku checkpoint says `Sudoku-1k`, which is the same corpus as
  `Sudoku-aug1000`; unmapped names are passed through as literal paths and fail
  later as "split train does not exist".
- The published checkpoint **does** carry an EMA shadow, at `blob["ema"]["shadow"]`
  (12 tensors, mu=0.999). It differs from the raw params by ~5e-3, so EMA is never
  the explanation for a large accuracy gap. (An earlier note here claimed the
  opposite; it was wrong.)
- **Torch keys carry a `_orig_mod.model.` prefix** (`torch.compile` plus the
  wrapper module). Neither segment exists in the flax tree.
  `tools/convert_torch_ckpt.py` now strips known wrapper prefixes automatically —
  do not rely on passing `--strip-prefix` by hand.
- **Orbax `partial_restore=True` returns unmatched leaves unchanged**, i.e. still
  holding `model.init`'s random values, with no error and no warning. A fully
  mismatched key set therefore evaluates at chance (Sudoku showed `all/accuracy`
  0.0907 = 1/11 with `exact_accuracy` 0.0) and looks like a modelling problem.
  `utils/ckpt_util.assert_tree_matches` compares key sets and shapes before
  restoring, and `assert_restored_differs` catches the case where metadata is
  unreadable. Never add a restore path that bypasses both.
- Restore with explicit `RestoreArgs(restore_type=np.ndarray)`. Without it orbax
  infers a placement per array and raises `sharding ... Got None` on a multi-host
  job. Older orbax hides this by reading the checkpoint's `_sharding` file and
  only warning, so it cannot be reproduced on a single-device CPU box.
- The released sudoku checkpoint was **not** trained with the released training
  recipe: its `extra.json` says `pos_encodings: none` and `puzzle_emb_ndim/len:
  512/16` (hence `seq_len` 97, not 81), while `config/train/eqr_sudoku.yaml` says
  `rope` and no puzzle embedding. Reproducing the paper's numbers by training
  requires the checkpoint's arch, not the published recipe.
- Compare against the right baseline. Upstream `README.md` reports **two** sets:
  a 2048-example smoke eval (`cumulative_exact_acc_top1` 99.19 ± 0.12) and the
  423,168-example full set (99.79). `different_init/any_correct` is
  mathematically `pass@n` but is the only one reported, since `pass@k` is emitted
  only for `k < n`. `cumulative_exact_acc_topN` is the mean accuracy of the N
  most-converged samples, so `...top4` equals `convergence_top_k/exact_accuracy`.

## Data And Checkpoint Locality

`storage.md` owns the rule (co-locate compute with storage or the pruner deletes
the job) and the measured cost. Both halves are automatic here, and both are
overridable:

- `dataset/data_util.py::_local_data_root` picks the dataset mirror matching
  `$BORG_CELL` / `$CLOUD_ZONE`; `$EQR_DATA_ROOT` still wins. Mirrors live in
  `_MIRRORS`, and an unlisted cell keeps the old default rather than inventing a
  path.
- `tpu_cmd/xm_launcher.py::_local_bucket` picks the checkpoint bucket matching
  `--cell` from `_CELL_BUCKETS`; an explicit `--bucket` still wins.

**When you add a new compute cell, mirror the data and add both entries.**

Related but distinct: `utils/ckpt_util.py` has one host read a REPLICATED
checkpoint and broadcast it, because N hosts reading the same file amplifies the
read N-fold. Distance and amplification are separate problems needing separate
fixes.

## Sampler State Must Not Scale With The Corpus

The dataloader used to persist `group_order` — `rng.permutation(num_groups)` —
in every checkpoint. On the full sudoku corpus that is ~3.8M integers written
one per line: a 45 MB `extra.json` rewritten every save. A job deleted mid-write
truncated it, and the resume then died parsing the checkpoint's own bookkeeping.
The 1k corpus never showed it.

The permutation is a pure function of the RNG state and never needed storing.
What was missing was a handle on the state from BEFORE the draw — `rng_state`
has already been advanced by that epoch's sampling — so `epoch_rng_state` is
recorded instead and `_iter_train` replays the permutation. 890 bytes.

**Anything added to sampler state must be O(1) in corpus size. If it is not,
store the seed and replay it.**

## The Boundary-Checkpoint Stall

A checkpoint written on an **iteration boundary** could not be resumed from, and
the failure was silent.

`epoch_idx` in `puzzle_dataset._iter_train` counts epochs consumed *within* the
current iteration, so the last save of an iteration stored
`epoch_idx == epochs_per_iter`. Resuming evaluated `while 5000 < 5000` -> False,
the loader yielded **zero batches**, training "finished" without a step, the
process exited 0, and Borg restarted it. Every attempt looked like a clean
success, and with the default cadence it poisoned every other checkpoint, so
recovering from a preemption was a coin flip.

Fixed in `0b31a2a`: an exhausted cursor now means "the previous iteration
finished", so the resume starts the next one at 0 and drops the spent
permutation. Two things to carry forward:

- **Verify a resume by step progress, not by exit status** (`jobs.md` §A restart
  loop is not evidence of a crash).
- **Inspect `train_dataset.train_state.epoch_idx` in `extra.json`** when a resume
  makes no progress. One `fileutil cat` settles it.

## Experiment Tracking

- Config fields may retain historical `wandb` names. No `WANDB_API_KEY` is needed.
- **In google3 `import wandb` resolves to `//third_party/py/scamper:wandb_mock`,
  which implements only `init`, `log`, `finish`, `Table`, `plot` and `Video` —
  and its `log()` is a bare `logging.debug` that stores nothing.** Every other
  attribute (`util.generate_id`, `define_metric`, `Histogram`, `Artifact`,
  `run._step`) raises `AttributeError` **at call time**, i.e. on Borg, after
  packaging and scheduling have both succeeded. Route every wandb call through
  the shims in `utils/wandb_util.py`; `safe_log()` additionally swallows failures,
  because telemetry must not be able to kill a TPU run.
- Metrics reach a UI through **DeepMind Datatables**, written via
  `clu.metric_writers` (`//third_party/py/clu/metric_writers:notf`).
  `research/result_logging.md` §Chart Links owns the URL forms and the
  `write_to_datatable=True` ACL trap. Two constraints specific to this code:
  only `process_index()==0` may construct a writer (the key is `(wid, step)` and
  all tasks of a work unit share one `wid`), and it must flush periodically —
  CLU's destructor cancels the writer thread instead of draining it.
- Every run that reaches a conclusion is logged to the `EqR-reproduction` tab
  with its chart link; see `research/result_logging.md`.
- **Anything that builds a logging handler unhooks the remote log mirror.**
  `main.py` tees stdout/stderr into `$CHECKPOINT_BUCKET/logs/rank_<n>.log`
  before anything else runs, but stdlib handlers capture the stream they were
  constructed with, so `clu.metric_writers.create_default_writer` silently
  steals it back. Symptom: the job runs fine and the log stops dead after a few
  lines (XID 275709629 mirrored 173 lines; every job after the CLU writer
  landed mirrored exactly 4). Call `logging_util.reattach_absl_handlers()`
  after constructing anything that touches logging. Note the handler to repoint
  is `get_absl_handler().python_handler`, not `get_absl_handler()` — the outer
  object has no `setStream`, and the original call raised `AttributeError` into
  a bare `except: pass` for its entire life.
- Under Borg that mirrored file is the ONLY log: the local stream dies with the
  task, and `analog` may be unavailable from a workstation. Losing it turns a
  one-line diagnosis into a blind guess.
- Resume uses the exact XManager experiment identity (`resume_xid`) and its
  workdir. Verify checkpoint and config continuity before treating appended
  charts as one run.
- Checkpoints go to `$CHECKPOINT_BUCKET` (injected by the launcher), never to
  `workdir`, which is task-local `/tmp` and is wiped by every Borg restart.
  `main.py::_apply_borg_autoresume` rediscovers the newest complete checkpoint
  there at startup. `load_from` accepts `gs://` and must be handled through the
  path helpers in `utils/ckpt_util.py`, not `os.path`. The launcher/runtime
  contract for `LOAD_FROM`, `WANDB_RESUME_ID`, and `CHECKPOINT_BUCKET` is owned
  by `jobs.md` §Preemption, Restart, And Resume.
- Do not query the WandB API for EqR-jax unless current code proves that a real
  external WandB run was created.

## Reporting Its Metrics

`research/result_logging.md` owns the general rule; these are the EqR-jax
specifics that keep biting.

- **A logged key is not a delivered column, and nothing says so.** The sink is
  DeepMind Datatables through `utils/wandb_util.py`, whose `_flatten_scalars`
  silently DROPS anything not float-able — a histogram, a figure, an array, a
  bool, a string, a NaN. The google3 `wandb` mock stores nothing either. So a
  metric can be computed on every step, for the whole life of a feature, and
  reach no reader, with no error at either end. **Verify a new metric by
  printing the payload the run actually logs, not by testing the function that
  builds it.** `README.md` §metrics is the checked-in description of that
  surface; keep it true.

- **An eval's denominator is its REAL rows, not the rows it was fed.** Feeding
  more rows than the split holds is legal — a `512 x 2` maze eval feeds 1024 for
  1000 puzzles — and `puzzle_dataset._collate_batch` pads the ragged tail with
  `labels = IGNORE_LABEL_ID`. Those rows are EXCLUDED from every metric rather
  than scored: the loss head gates on `valid = loss_counts > 0`, and the
  breadth/convergence tallies filter through `eval_fn._drop_unscorable`, so
  `different_init/total_samples` reports the real count. Padding costs compute,
  not correctness. Do not apply a hand correction on top — that now
  UNDER-reports.

  This is a fix worth knowing about because the failure it replaced was silent
  and large: a pad row satisfies `((pred == labels) | ~mask).all(-1)` vacuously,
  so it used to count as a perfect solve for every replica, and one maze eval
  reported an accuracy that was entirely manufactured by 24 pad rows. Read
  `total_samples` to confirm which regime a number came from, and check that
  `different_init/avg_pass_rate` equals `all/exact_accuracy` **of the same
  weight set** — `ema/` against `ema/`, never across the two. They measure the
  same thing by different routes, so they agree exactly or something is wrong.

- **Several different keys are called `lm_loss`. Name the one you mean.** A
  run's log carries `train/lm_loss` (train split) and a
  `D<k>/{ema,online}/all/lm_loss` per online-eval depth and weight set; a
  standalone eval logs `{ema,online}/all/lm_loss` and writes `all/lm_loss` into
  its results json. They differ in split, weights, denominator, and cadence, and
  the eval ones are ~30 points against ~1500. A claim about "the loss" that does
  not say which key is unfalsifiable, and quoting the train curve at someone
  reading the eval chart inverts the conclusion — the two have disagreed in sign
  on a real run.

- **Loss keys are SUMS over rows; the divisor is `global_batch_size`, not
  `count`.** The loss head returns every metric summed, and
  `train.py::process_metrics` picks the divisor per key: anything ending in
  `loss` divides by `global_batch_size`, most other keys divide by `count`,
  which is only the rows that HALTED that step (single digits out of hundreds).
  Dividing a loss by `count` inflates it by ~100x and still looks plausible.
  `README.md` §metrics holds the full divisor table — read it before hand-
  reducing any raw key.

- **`train/lm_loss` is not comparable across runs that halt at different
  depths.** It is measured at whatever ACT depth each model chose, so a run
  pinned at `halt_max_steps` is buying its lower loss with more compute than a
  run that halts early. Check `train/steps` before putting two of these numbers
  in one table; if they differ, the comparison needs a fixed-depth eval instead.

- **`final train/*` is ONE BATCH, and the code will not smooth it for you.**
  The logged final value is whichever step landed on the `log_per_step` grid, so
  it carries full batch-to-batch variance. Compute a tail-window mean over the
  logged curve and compare runs on that. There is deliberately no knob: the one
  that existed averaged the pre-denominator sums, so its "smoothed loss" was
  ~`global_batch_size` times the real one.

- **The in-training `D16/{ema,online}/all/exact_accuracy` and its D64 twin ARE
  the numbers to read.** The periodic eval runs the headline protocol — B=1 at
  D=16 and D=64, on both weight sets — every `training.eval_interval_steps`, and
  every training config sizes
  `evaluation.global_batch_size x max_eval_steps` to the population a standalone
  eval scores. So a run's result is a column of its own training curve. Two
  qualifications belong with the number:

  *Cadence.* It is a sampled curve, not a continuous one —
  `training.eval_interval_steps`, currently 5000 in every training config, with
  `checkpoint_interval_steps` a divisor of it, so each evaluated step has a
  checkpoint behind it. Keep that alignment when changing either: report the
  peak for a family that rises then collapses, and a peak with no checkpoint
  cannot be re-evaluated or published.

  *Sample count.* It is a FIXED-SIZE SUBSET wherever the split is larger — 2048
  rows of sudoku's 422,786, comparable to upstream's 2048-sample figure and not
  to its full-split one. Maze's 1000-puzzle split is covered whole.

  Breadth is what the periodic eval does not do. `evaluation.final_eval: true`
  runs the full `evaluation.sweep` cartesian product against the final
  checkpoint **in the same job**, so a paper-protocol row never depends on
  remembering to launch a second one; a standalone `eval_only` run is for
  scoring a checkpoint after the fact. Verify the sizing in the config rather
  than assuming it: a config whose product differs is measuring a different
  population, whichever direction the number moved.

## Eval Protocol: Report B=1 First

The headline number for any EqR run is **exact accuracy at B=1** (one restart,
no selection), reported at both depths the paper uses: **D=16** (the arch's own
`halt_max_steps`, the paper's baseline point) and **D=64** (its depth-scaling
point). Breadth is an extra, not the headline — it multiplies eval cost by B and
answers a different question. The spreadsheet's `EqR-reproduction` tab is laid
out this way: `Acc B=1 D=16`, `Acc B=1 D=64`, `Acc-any-correct (B=1)`, then a
free-text `additional results` column for anything breadth-derived.

### What the paper actually reports for breadth

The paper's B=128 figure (Maze 93.0) is **top-1 convergence accuracy**: pick the
restart with the smallest mean residual over the last L=3 iterations. It is
**not** majority vote, and the paper never reports majority vote at all.

That matters because majority vote scores HIGHER — for the released maze
checkpoint at D16/B128, majority vote reaches 99.2 against conv-top1's 94.9.
The reason the paper uses the weaker selector is not an oversight: conv-top1
tests the paper's own claim that latent convergence predicts solution quality,
whereas majority vote is a generic self-consistency trick that says nothing
about EqR. Do not "improve" a reproduction row by swapping in the higher number.

Majority vote here is a vote over the ENTIRE token sequence (`tuple(row)` as the
key in `eval_fn._update_di`), not per-token. A maze has one correct path and
many distinct wrong ones, so a plurality is enough for the correct answer to
win, which is why it is such a strong selector.

### Depth does not always help a breadth metric

`convergence_top_k=4` caps the candidate pool before top-1 is taken, and that
cap binds: for the released checkpoint, `convergence_top_k/any_correct` is
**95.70 at both D=16 and D=64**, so conv-top1 cannot benefit from depth. Base
capability does improve (`all/exact_accuracy` 82.61 -> 89.30, reproducing the
paper's 82.2 -> 88.9).

Meanwhile deeper reasoning makes the B restarts agree MORE, so replica diversity
falls (`different_init/any_correct` 99.90 at D16 -> 99.22 at D64) and vote-style
metrics get slightly worse (majority 99.2 -> 97.8). A breadth metric going down
as D goes up is therefore expected, not a bug.

### Online eval during training — where the reported number comes from

`evaluation.online_eval` names the (depth, breadth) points the in-training eval
scores every `training.eval_interval_steps`; it defaults to `[16, 64]` at B=1.
That default IS the headline protocol above, on both weight sets, so a training
run reports its own accuracy and a second job is not required to obtain one.
Set `online_eval: []` to restore the old single-point behaviour. Each point
rebuilds the module via `model_copy` (a frozen dataclass cannot be re-depthed in
place), so a point costs a recompile, not a checkpoint reload.

**Comparability rests on the sample count**, which `online_eval` does not
control: it is `evaluation.global_batch_size x max_eval_steps`, and the test
loader walks the split in order from the start, so two evals with the same
product score literally the same rows at any batch size. Keep a training
config's product equal to the standalone protocol's — 2048 for sudoku, the whole
split for maze — or its curve stops being comparable to an `eval_only` row.
Leaving `max_eval_steps` unset walks the entire split every interval, which on
sudoku is a few hundred times the work.

**For the full protocol in the same job, set `evaluation.final_eval: true`**
with a non-empty `evaluation.sweep`. It sweeps the final checkpoint after the
last training step, reading the weights off disk through the same engine a
standalone eval uses, so the breadth and convergence-top-k columns arrive
without a second launch to remember and match back by hand. Off by default
because the sweep is expensive; an empty sweep with it on is rejected at config
load rather than ending a long run with a log line.

**Every logged eval column names its point and its weights**, as
`D<depth>[B<breadth>]/{ema,online}/...`, and appears exactly once — there is no
bare `all/...` copy to point a chart at. Charts and flatboard URLs use
`D16/ema/all/exact_accuracy`. The distinction that matters when reading code: a
standalone `evaluate()` still RETURNS `{"all": {...}}` and its results json is
still keyed `all/...` — only the logged column name carries the prefix.
