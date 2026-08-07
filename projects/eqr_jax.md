# EqR And EqR-jax

The `EqR` (PyTorch) and `EqR-jax` (JAX) checkouts are distinct implementations;
inspect the target's native docs and git state before porting anything between
them. `../jobs.md` owns launches and job diagnosis.

Longest guide here, and mostly reference — jump to what you need:

| Section | When |
|---|---|
| Data And Model Invariants · Launch And Packaging | changing configs or launching |
| Google3 Packaging Traps · JAX Startup Order | a job dies before `main()` |
| Evaluating A Published Checkpoint | restoring or comparing against released weights |
| Data And Checkpoint Locality · Sampler State · Boundary-Checkpoint Stall | a run is slow, deleted, or resumes wrong |
| Experiment Tracking · Reporting Its Metrics | reading or logging its numbers |
| Eval Protocol | deciding which accuracy is the headline |

## Data And Model Invariants

- **The q head is deliberately initialised never to halt**: zero weights and a
  `-5` bias, so `sigmoid(-5) ~ 0.0067` and ACT spends its full budget early on,
  learning to solve before learning to stop. Faithful to the torch reference.
  But **weight decay erodes it** — unmasked `wd 1.0` gives the bias a ~6900-step
  half-life, so the prior is largely gone by 50k (verifiable on a released
  checkpoint: the dead `q_continue` bias is the pure decay curve and matches
  `exp(-1e-4 t)` to three significant figures). Treat the `-5` as an early-
  training device, not a standing property, and note no test pins it.
- **`arch.q_head_sg` severs the halt objective from the trunk.** With it on the
  q head reads a `stop_gradient` latent, so its BCE updates only the head's own
  two parameters and the trunk gradient from the q term is exactly zero
  (measured across every `q_readout` mode). It also makes
  `arch.loss.q_halt_loss_weight` irrelevant: that weight is already a no-op on
  the head itself, since `atan2` is scale-invariant and the head's only gradient
  is the q term — what it really scales is the q signal's pull on the SHARED
  trunk, which `q_head_sg` removes entirely.
- `EqR-jax` maps configured dataset aliases in `data_util.py`; verify the live
  mapping for names such as `Maze-dynamic`, `Maze-30x30-multi` and
  `Sudoku-aug1000` instead of rewriting paths in launch commands. An alias that
  is not in `DATASET_PATHS` is passed through as a LITERAL path and the job dies
  at startup with "Dataset split train in <alias> does not exist" — and the
  entry has to exist in the checkout you launch FROM, which is not always the
  one you edited.
- **The maze grid is `30 x 30` holding a `29 x 29` perfect maze, padded — not
  cropped.** `_generate_perfect_maze` needs an odd size, so the generator takes
  `maze_n = n if n % 2 else n - 1` and writes `open_mask[:29, :29]`, leaving row
  29 and column 29 permanently wall. Verify against the corpus rather than
  assuming a crop: those two lines are constant across every sample. An older
  note here described a `maze_dataset` / `gen_dfs` path whose `grid_n=15`
  `as_pixels()` gave `31 x 31` cropped to `30 x 30`; that path is dead code on
  the current library version. Both paths are recursive backtracker, so the
  generator family is unchanged — but the padded geometry, and the solution
  length window that goes with it, are what the live code produces.
- Do not transfer checkpoint, logging, or runtime assumptions between the
  PyTorch and JAX implementations without checking both code paths.
- **Never sync a file between the two checkouts wholesale** (`../engineering.md`
  §Porting Between Related Checkouts). This repo already lost `_online_eval`
  from `train.py` that way while nine yamls kept setting `evaluation.online_eval`
  — the config promised a D16/D64 curve and the code measured one point, for
  eleven commits.
- **Registers are plain trainable tokens, and the knob is `arch.num_registers`.**
  An `(N, hidden)` table in `params` prepends N tokens, added after `embed_scale`
  so `register_init_std` is the std the trunk actually sees. The older
  `puzzle_emb_*` surface it replaced was inert three times over — a zero,
  non-trainable `consts` table looked up by a `puzzle_identifiers` column every
  dataset here fills with a constant 0, then reshaped by ceiling division and
  zero-padded so fifteen of sixteen slots were dead. All the retired names raise
  and name their successor, because pydantic drops an unknown field in silence.
  A checkpoint carrying `puzzle_emb` no longer restores; torch checkpoints
  convert with `--num-registers`.
- **A zero-initialised register is not a neutral default.** `register_init_std`
  defaults to 0.02 rather than upstream's 0, because the failure is early
  symmetry: with registers on, the q-head can read a register slot instead of a
  board cell, and a zero slot feeds it nothing during the steps that decide
  whether ACT ever learns to halt. Treat it as a load-bearing hyperparameter and
  ablate it alongside any register experiment.
- **`mlp_t: true` makes `pos_encodings` a complete no-op** — bit-identical
  logits across `rope`, `rope2d` and `none`, because the MLP-T branch replaces
  self-attention and never reads the table. Every `local_debug*` config and
  upstream's own sudoku recipe set it. A run reported as "rope2d" alongside
  `mlp_t` measured no position encoding at all.
- **`rope2d` combined with registers is refused at config load.** The flat table
  that used to serve that combination was not a rotation: row and column angles
  landed in one 2x2 block, so it was orthogonal only on the board diagonal
  (mean det 0.609, 17.8% orientation-flipped) and translation invariance was
  gone. Rebuilding it needs PaliGemma's layout — half-width `[row(q), col(q)]`
  then DUPLICATE. Plain 1-D `rope` is fine with a prefix: the shift is exactly
  invariant.

## Launch And Packaging

- Edit the unrestricted home checkout. `tpu queue` creates a unique CitC source
  snapshot, repoints the staged target, and packages that snapshot. Post-package
  edits to the home checkout do not affect the job.
- **Write the run into `configs/remote_run_config.yml` and launch without a
  config argument.** `../jobs.md` §Submission Contract owns this rule; the
  EqR-jax consequence is that `configs/` holds ONLY templates — `local_debug`,
  `remote_run`, and at most three task templates. A finished experiment's config
  is recovered from its immutable snapshot with `sexy <xid>`, not by keeping a
  file per run. The directory has been pruned twice already because launching by
  config name made every launch leave a file behind.
- **Several agents share this checkout, so launch from a copy** (`../jobs.md`
  §Submission Contract). `rsync -aL` the tree minus `.git`/`data`/`logs` into
  `/tmp`, write `configs/remote_run_config.yml` there, `tpu queue` from that
  directory, delete it. The tree is ~5 MB, `tpu queue` re-rsyncs it into the
  CitC stagedir anyway, and `xm_launcher.py` is a symlink that `-aL`
  dereferences — Bazel refuses to glob a package containing an absolute
  symlink, so the dereference is required, not incidental.
- EqR-jax uses XManager service tiers (`PROD` or `BATCH`), not legacy
  `xm_priority`. Resource selection and allocator constraints are in `../jobs.md`.
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
of guessing (see `../jobs.md` §Debugging A Job That Dies With No Log):

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
  0.0907 = 1/11 with `acc` 0.0) and looks like a modelling problem.
  `utils/ckpt_util.assert_tree_matches` compares key sets and shapes before
  restoring, and `assert_restored_differs` catches the case where metadata is
  unreadable. Never add a restore path that bypasses both.
- Restore with explicit `RestoreArgs(restore_type=np.ndarray)`. Without it orbax
  infers a placement per array and raises `sharding ... Got None` on a multi-host
  job. Older orbax hides this by reading the checkpoint's `_sharding` file and
  only warning, so it cannot be reproduced on a single-device CPU box.
- The released sudoku checkpoint was **not** trained with the released training
  recipe, but not for the reason its `extra.json` first suggests. The
  `pos_encodings: none` there is NOT a deviation from the recipe's `rope` — both
  run `mlp_t: true`, so the two are the same function. The real difference is
  the puzzle embedding: the checkpoints set `puzzle_emb_ndim/len` 512/16 (hence
  `seq_len` 97, not 81) with a NON-ZERO table (std ~0.03-0.04, no zero entries),
  while the reference yaml never mentions the knob. So the published weights
  were not produced by the published code, and reproducing the paper's numbers
  by training requires the checkpoint's arch.
- Compare against the right baseline. Upstream `README.md` reports **two** sets:
  a 2048-example smoke eval (`cumulative_exact_acc_top1` 99.19 ± 0.12) and the
  423,168-example full set (99.79). `different_init/any_correct` is
  mathematically `pass@n` but is the only one reported, since `pass@k` is emitted
  only for `k < n`. `cumulative_exact_acc_topN` is the mean accuracy of the N
  most-converged samples, so `...top4` equals `convergence_top_k/acc`.

## Data And Checkpoint Locality

`../storage.md` owns the rule (co-locate compute with storage or the pruner deletes
the job) and the measured cost. Both halves are automatic here, and both are
overridable:

- `dataset/data_util.py::_local_data_root` picks the dataset mirror matching
  `$BORG_CELL` / `$CLOUD_ZONE`; `$EQR_DATA_ROOT` still wins. Mirrors live in
  `_MIRRORS`, and an unlisted cell keeps the old default rather than inventing a
  path.
- `tpu_cmd/xm_launcher.py::_local_bucket` picks the checkpoint bucket matching
  `--cell` from `_CELL_BUCKETS`; an explicit `--bucket` still wins.

**When you add a new compute cell, mirror the data and add both entries.**

Related but distinct: **every host must read the checkpoint itself.** The
obvious optimisation — one host reads and broadcasts, since N hosts reading one
file amplifies the read N-fold — is not available, because `ocp.Checkpointer.
restore()` is ITSELF a collective: it ends in a `sync_global_processes` barrier.
"Rank 0 reads, the rest wait in `broadcast_one_to_all`" therefore puts two
different programs on one channel and halts the TPU core with
`RuntimeUnexpectedCoreHalt`, after the read has already succeeded. It cannot be
patched as written — the non-readers would have to predict the dtype orbax
returns, and a leaf stored as bf16 defeats any static guess. It was buying 0.22s
on a 108 MiB tree against an uncatchable halt. `ckpt_util.py` records the one
construction that would work (`MultiprocessingOptions(primary_host=0,
active_processes={0})`) so nobody re-adds it blind. Distance and amplification
remain separate problems, but only distance has a fix here.

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

## Training Length Is A Step Count

`training.total_steps` is the only run-length input and the train loader is
endless. `epochs`, `max_steps` and `train_epochs_per_iter` are retired and raise
naming their successor; a fixed-size corpus still gets its epoch budget printed,
as a report and never a stopping rule.

That deleted a whole failure mode rather than fixing it. Training used to be cut
into `epochs / train_epochs_per_iter` outer iterations, and a checkpoint written
on an iteration boundary stored an exhausted cursor: the resume evaluated
`while N < N` -> False, the loader yielded **zero batches**, training "finished"
without a step, the process exited 0, and Borg restarted it. Every attempt
looked like a clean success. Two things outlive the code:

- **Verify a resume by step progress, not by exit status** (`../jobs.md` §A restart
  loop is not evidence of a crash).
- An "epoch" here was never a pass over the data. Every builder writes
  `mean_puzzle_examples = 1` and every corpus holds 1000 groups, so at the
  shipped batch size `steps_per_epoch` floored to **1** — `epochs: 50000` meant
  50,000 steps. The name is gone; distrust the concept if you meet it in an old
  config or checkpoint.

## Experiment Tracking

Config fields keep historical `wandb` names; no API key is needed, and there is
no real external tracker unless current code proves one was created.

- **`import wandb` resolves to a mock** implementing only `init`, `log`,
  `finish`, `Table`, `plot`, `Video`, whose `log()` stores nothing. Every other
  attribute raises **at call time** — on Borg, after packaging and scheduling
  succeeded. Route calls through `utils/wandb_util.py`; `safe_log()` swallows
  failures, because telemetry must not kill a run.
- Metrics reach a UI through Datatables via `clu.metric_writers`. URL forms and
  the explicit-opt-in trap are in `../research/result_logging.md` §Chart Links.
  Two constraints specific to this code: only `process_index()==0` may construct
  a writer (all tasks of a work unit share one key), and it must flush
  periodically — CLU's destructor cancels the writer thread instead of draining
  it.
- **Anything that builds a logging handler unhooks the remote log mirror.**
  `main.py` tees stdout/stderr to `$CHECKPOINT_BUCKET/logs/rank_<n>.log` first,
  but stdlib handlers capture the stream they were constructed with, so creating
  a metric writer silently steals it back — the job runs fine and the log stops
  dead after a few lines. Call `logging_util.reattach_absl_handlers()` after
  constructing anything that touches logging; the handler to repoint is
  `get_absl_handler().python_handler`, not the outer object, which has no
  `setStream`. Under Borg that mirrored file is the ONLY log.
- Resume uses the experiment identity (`resume_xid`) and its workdir; verify
  checkpoint and config continuity before treating appended charts as one run.
  Checkpoints go to `$CHECKPOINT_BUCKET`, never `workdir`;
  `main.py::_apply_borg_autoresume` rediscovers the newest complete checkpoint
  at startup. The env-var contract is owned by `../jobs.md`.
- Runs reaching a conclusion go to the `EqR-reproduction` tab; see
  `../research/result_logging.md`.

## Reporting Its Metrics

`../research/result_logging.md` owns the general rule; these are the EqR-jax
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
  `different_init/avg_pass_rate` equals `acc` **of the same
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
  run that halts early. Check `train/act_loops_mean` before putting two of these numbers
  in one table; if they differ, the comparison needs a fixed-depth eval instead.

- **A logged `train/*` value is the WHOLE INTERVAL, not one batch.**
  `StepAccumulator` folds every step and the step landing on the `log_per_step`
  grid drains it, with the divisor scaled by the interval length. So a point is
  already an average over `log_per_step` steps — but the FINAL point is still one
  interval, not a converged number, so compare runs on a tail-window mean over
  the logged curve rather than on the last row. There is deliberately no
  smoothing knob: the one that existed averaged the pre-denominator sums, so its
  "smoothed loss" was ~`global_batch_size` times the real one.

- **The in-training `D16/{ema,online}/acc` and its D64 twin ARE
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

  *The peak survives retention on purpose.* `training.checkpoint_best_metric`
  promotes the best-scoring step to `checkpoint_best_<n>/`, a name that
  deliberately falls OUTSIDE the `step_<N>` namespace every retention rule
  matches on — so the in-job pruner, `tpu gc`, and auto-resume all ignore it,
  and no future step-based sweeper has to be taught about it. Without it the
  default policy (newest 2 plus a 50k ladder) deletes exactly the checkpoint a
  peak-reporting row depends on: this family peaks off the ladder, at 120k of
  150k on maze and 40-45k of 50k on sudoku. `"auto"` resolves the metric
  against the FIRST REAL METRICS DICT rather than the config, because which
  accuracy a run reports depends on its dataset and head; it takes the maze
  headline (`walk_acc`/`solution_acc`) over `acc` where both exist, and a
  resolution that finds nothing disables the feature with a warning naming the
  keys that were available. Auto-resume still restores from the NEWEST
  checkpoint, never from the best — the two answer different questions.

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

## A Generative Model Is Scored On Whether Its Output Is A Solution

This is a generative loop: it *produces* an answer, so the question to ask is
"is what it produced a solution", not "does it equal the stored one". Those are
the same question only when the answer is unique — and every stock maze split
here is a `perfect` maze, i.e. acyclic, so its S→G shortest path IS unique.
`acc` has therefore been answering the reproduction question while
being read as the solving one. Harmless on those splits; badly wrong off them.

**Use `Maze-30x30-multi` whenever the claim is about solving.** 1000 fixed
braided mazes, every one carrying ≥2 shortest paths, built and verified per
puzzle by `tools/build_maze_multisolution_testset.py`. The gap it exposes is not
subtle: the same checkpoint scores **40.2 exact vs 99.3 solution** (D16, EMA).
The model was solving 99% of them and the old metric said 40%.

- **`solution_acc` (grid heads) / `walk_acc` (`final_head_type: ar`) is THE MAZE
  HEADLINE**, and `acc` stays beside it as a diagnostic rather than being
  removed — `acc` is emitted by the loss head for every dataset, and it is what
  tells you whether a model with `walk_acc` 0 learned anything at all. Scoring
  auto-enables on a maze dataset; `evaluation.solution_scoring` forces either
  way. Both reach the in-training periodic eval, so a maze run's result is
  `D16/ema/walk_acc` on its own training curve, exactly where `D16/ema/acc` is
  for sudoku.
- **A longer legal route counts as solved, deliberately.** Requiring the
  shortest path puts the label back into a metric whose purpose is to not need
  one. `shortest_solution_acc` / `shortest_walk_acc` carry the strict number
  separately, and its reference length is BFSed **from the row's own input
  board**, not read from the split's spec file.
- **Any `shortest_*` number measured before that BFS landed is a LOWER BOUND.**
  The spec array is in split order and the scorer indexed it by row-within-batch,
  so only the first batch at breadth 1 was aligned — 52.5% of rows at the shipped
  512-row eval, 0.33% at the B=128 sweep point. A wrong reference can only flip
  `shortest` True→False, so the error is one-directional and no arithmetic
  corrects it: re-score. The non-strict columns never read the reference and are
  unaffected.
- **Both scorers check against the INPUT board, never the label**, so neither
  can be satisfied by copying the target. `maze_solution.py` (grid heads) and
  `maze_walk.py` (AR heads) are the same definition for two output formats;
  keep them that way.
- **The empty prediction must be rejected explicitly.** A pad row decodes to no
  path at all, and "the cells form a route from S to G" is vacuously true for
  the empty set when S adjoins G — the same trap `_row_exact_correct` guards
  with its `supervised > 0` term.
- A test-only split still needs a `train/` directory: `just_evaluate` builds a
  train dataloader purely to read `vocab_size`/`seq_len` and never iterates it.
  One puzzle is enough, and keeps the split unusable for training.

## Eval Protocol: Report B=1 First

The headline number for any EqR run is **accuracy at B=1** (one restart, no
selection), reported at both depths the paper uses: **D=16** (the arch's own
`halt_max_steps`, the paper's baseline point) and **D=64** (its depth-scaling
point). Breadth is an extra, not the headline — it multiplies eval cost by B and
answers a different question.

**Which accuracy** depends on the dataset: `acc` on sudoku, `solution_acc` /
`walk_acc` on a maze (§A Generative Model Is Scored On Whether Its Output Is A
Solution). Both arrive from the same periodic eval, so the protocol is the same
and only the column name changes.

The spreadsheet's `EqR-reproduction` tab is laid out this way: `Acc B=1 D=16`, `Acc B=1 D=64`, `Acc-any-correct (B=1)`, then a
free-text `additional results` column for anything breadth-derived.

### A breadth eval can silently deliver less breadth than you asked for

The restart latents are drawn from a key broadcast to every device, so a draw is
a function of the WITHIN-DEVICE row index only. The effective breadth is
therefore `min(per_device_rows, n_init)`: when one example's B replicas straddle
devices, two of them get the same latent. Nothing in the metrics shows it —
`total_samples` stays right and `avg_pass_rate` still matches
`acc` — only diversity shrinks, so `different_init/any_correct`
and `convergence_top_k` under-report by exactly that factor. Config load now
refuses such a layout, but read the rule when sizing an eval by hand.

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
capability does improve (`acc` 82.61 -> 89.30, reproducing the
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
`D<depth>[B<breadth>]/{ema,online}/...`, and appears exactly once. Charts and
flatboard URLs use `D16/ema/acc`. The sweep path carries the same point tag as
the in-training eval, so a training curve and a standalone eval point are
directly comparable; the `eval/depth`-style coordinate columns that used to
carry that information are gone from the metric sink and print to the log.

The dataset `set` level is gone everywhere — column, `evaluate()`'s return value
and the results json alike. It only ever held the single value `all`, because
every corpus here declares `sets=["all"]`; a dataset declaring two sets makes
the level reappear.
