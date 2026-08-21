# EqR And EqR-jax

`EqR` (PyTorch) and `EqR-jax` (JAX) are separate implementations of
continuous-space reasoning for sudoku and mazes. **Never port runtime, data,
checkpoint or logging behaviour between them** without reading both code paths;
unless a rule names the torch side it describes `EqR-jax`. Owned elsewhere:
launches and job diagnosis `../jobs.md`, placement `../storage.md`, spreadsheet
discipline `../research/result_logging.md`.

| Section | When |
|---|---|
| Data And Model Invariants · Launch And Packaging | changing a config or launching |
| Dies Before `main()` | a job produces no log at all |
| Data And Checkpoint Locality · Loader, Sampler State, And Run Length | a run is slow, hangs, is deleted, or resumes wrong |
| Evaluating A Published Checkpoint | restoring or comparing against released weights |
| Experiment Tracking · Metric Names, Divisors, And Denominators | reading or logging its numbers |
| Checkpoint Retention: Keep The Peak | the step a result depends on must survive |
| Eval Protocol · Maze Scoring · Close-Loop | deciding which accuracy is the headline |
| RoboTwin DP Baseline | training / ablating the Diffusion-Policy baseline; the 5 ablation tasks |

## Data And Model Invariants

- **The q head's `-5` no-halt bias is an early-training device, not a standing
  property.** `sigmoid(-5) ~ 0.0067` makes ACT spend its full budget before
  learning to stop (as in the torch reference), but unmasked `wd 1.0` gives it a
  ~6900-step half-life — the dead `q_continue` bias of a released checkpoint is
  pure `exp(-1e-4 t)`. No test pins it.
- **`arch.q_head_sg` severs the halt objective from the trunk:** the q head
  reads a `stop_gradient` latent, so the trunk gradient from the q term is
  exactly zero in every `q_readout` mode. It also makes
  `arch.loss.q_halt_loss_weight` irrelevant, that weight being a no-op on the
  head itself (`atan2` is scale-invariant) and having only ever scaled the trunk
  pull `q_head_sg` removes. **`q_head_sg: true` is the best-performing setting:
  training the head independently of the trunk does not cost the trunk.**
- **A dataset alias absent from `DATASET_PATHS` becomes a LITERAL path**,
  killing the job at startup with "Dataset split train in <alias> does not
  exist". Check the live mapping in `dataset/data_util.py` (`Maze-dynamic`,
  `Maze-30x30-multi`, `Sudoku-aug1000`) in the checkout you launch FROM, not the
  one you edited.
- **`dataset.online_aug` is the SUDOKU symmetry group, not a generic
  augmenter:** it reshapes each batch to `(B, 9, 9)`, so on a 900-cell board it
  raises inside the TRAIN LOADER, after packaging and scheduling are paid for.
  Inherited from a sudoku scale-up recipe rather than mistyped; refused off
  sudoku now.
- **Size `--tmp_ram_fs_gib` from the payload before launching a 20M-row
  corpus:** `sync_dataset_to_local` mirrors the split into `/tmp`, a Borg RAM
  disk (default 16 GiB), once per task — and a corpus holds more than the loader
  reads, Setting-A ones shipping a `shards/` tree as large as the payload (now
  skipped, with `seeds.npy` and `provenance.json`, by `_UNUSED_BY_TRAINING`).
  Read `Staged N MB`.
- **A per-metro mirror can be POLLUTED with generation intermediates, and
  `_UNUSED_BY_TRAINING` does not cover them all.** The settingB-v3 adv corpus
  mirrors diverged: `nm-d` (tul) and `li-d` (lpp) were clean 69G (arrays only),
  but `is-d` (cbf metro: `je` + every `yucbf*`) still carried a 78G `parts/`
  tree plus `shards/` and `fillin*.txt` — 227G total. `_UNUSED_BY_TRAINING`
  skips `shards/` but NOT `parts/`, so a TRAINING run (which stages the full
  split, `staging={}`) on a cbf cell copied `parts/` + inputs + labels past the
  92 GiB RAM disk and died `OSError: [Errno 28] No space left on device` in
  `sync_dataset_to_local`, at step 0, on every retry — while the identical
  config trained fine on `yutulpz`. The launcher classifies it "Job terminated
  in state FAILURE" (NOT "CODE BUG"), so read the attempt log for the ENOSPC
  before suspecting the arm you changed. Fix: launch on a clean mirror, or add
  `parts` to `_UNUSED_BY_TRAINING`, or delete the stray intermediates so a
  mirror matches `nm-d`/`li-d`.
- **The maze grid is `30 x 30` holding a `29 x 29` perfect maze, padded — not
  cropped:** `_generate_perfect_maze` needs an odd size, so it takes
  `maze_n = n if n % 2 else n - 1` and writes `open_mask[:29, :29]`, leaving row
  29 and column 29 wall on every sample.
- **Registers are plain trainable tokens; the knob is `arch.num_registers`.** An
  `(N, hidden)` table in `params` prepends N tokens after `embed_scale`, so
  `register_init_std` is the std the trunk sees. It replaced a `puzzle_emb_*`
  surface inert three ways over — zero, non-trainable `consts`, keyed by a
  `puzzle_identifiers` column every dataset fills with 0. Retired names raise
  and name their successor (pydantic drops unknown fields silently); a
  `puzzle_emb` checkpoint no longer restores, torch ones convert with
  `--num-registers`.
- **A zero-initialised register is not a neutral default:** `register_init_std`
  defaults to 0.02, not upstream's 0, because a zero slot feeds the q head
  nothing during the steps that decide whether ACT ever learns to halt. Ablate
  it with any register experiment.
- **`mlp_t: true` makes `pos_encodings` a complete no-op** — bit-identical
  logits across `rope`, `rope2d` and `none`, the MLP-T branch never reading the
  table. Every `local_debug*` config and upstream's sudoku recipe set it, so a
  run reported as "rope2d" alongside `mlp_t` measured no position encoding.
- **`rope2d` with registers is refused at config load:** the flat table that
  served it was not a rotation (row and column angles in one 2x2 block,
  orthogonal only on the board diagonal). Rebuilding it needs PaliGemma's
  half-width `[row(q), col(q)]`-then-DUPLICATE layout; plain 1-D `rope` is fine
  with a prefix.
- **Never sync a file between the two checkouts wholesale** (`../engineering.md`
  §Porting Between Related Checkouts). This repo lost `_online_eval` from
  `train.py` that way while nine yamls kept setting `evaluation.online_eval`.

## Launch And Packaging

- **Edit the unrestricted home checkout, launch from a `/tmp` copy.**
  `tpu queue` packages a unique CitC snapshot, so post-package edits never reach
  the job, and several agents share the checkout (`../jobs.md` §Submission
  Contract). `rsync -aL` the tree minus `.git`/`data`/`logs`, write the config
  there, `tpu queue`, delete it. `-aL` is required: `xm_launcher.py` is an
  absolute symlink, and Bazel will not glob a package containing one.
- **Write the run into `configs/remote_run_config.yml` and launch without a
  config argument** (rule owned by `../jobs.md` §Submission Contract). EqR-jax
  consequence: `configs/` holds ONLY templates — `local_debug`, `remote_run`,
  and per-task ones — and a finished experiment's config comes back from its
  snapshot with `sexy <xid>`. Launching by config name leaves a file behind.
- EqR-jax uses XManager service tiers (`PROD` / `BATCH`), not legacy
  `xm_priority`; resource selection and allocator constraints are `../jobs.md`.
- Treat the active BUILD target and launcher as authoritative: entry point in
  `srcs`, other Python/config files as `data`, `testonly` deps excluded from the
  production target, configs resolved through runfiles.
- Preserve ordinary local imports through the entry point's execution-directory
  setup; do not rewrite them to a hard-coded google3 staging package. Any
  validation suppression is a narrow current workaround, not a build rule.

## Dies Before `main()`

Every trap below fails at module-import time, which on Borg is an empty
`status.message` and no log at all. **Reproduce locally in ~45s instead of
guessing** (`../jobs.md` §Debugging A Job That Dies With No Log) — and note
`strict_deps = False` hides all the packaging ones at build time, so a green
build proves nothing.

| Trap | Fix |
|---|---|
| `import wandb` resolves via `//third_party/py/scamper:wandb_mock`, whose `imports = ["wandb_mock"]` the hermetic launcher ignores | `main.py` adds the runfiles directory to `sys.path` explicitly |
| `//third_party/py/pydantic` is v1-only (empty top-level `__init__.py`) | `pydantic.BaseModel` needs `:pydantic_v2` |
| The wandb mock has no `sdk` submodule, and `wandb.sdk.*` in an annotation is evaluated at class-creation time | quote the annotation |
| Under Bazel the CWD is inside `main.runfiles/google3`, so the yaml may not sit where `__file__` implies | `configs/load_config.py` searches several roots; never key discovery on `__file__` alone |

**JAX startup order. Do not call `jax.distributed.initialize()`:** google3's JAX
self-initialises on first backend use from the `--jax_port` /
`--jax_controller_address` flags XManager injects
(`jax_google.py::_lazy_initialization`), so calling it duplicates that work, or
without the flags raises `ValueError: coordinator_address should be defined`.
And **nothing before that point may touch JAX** — `log_for_0` asks
`jax.process_index()` who it is, booting the backend and making initialisation
illegal (`RuntimeError: ... must be called before any JAX calls`), so `main.py`
uses a JAX-free `_boot_log`.

## Data And Checkpoint Locality

`../storage.md` owns the rule — co-locate compute with storage or the pruner
deletes the job. Both halves are automatic here and overridable, and **when you
add a new compute cell you must mirror the data and add both entries**:

| Resolver | Picks | Override |
|---|---|---|
| `dataset/data_util.py::_local_data_root` | dataset mirror matching `$BORG_CELL` / `$CLOUD_ZONE` from `_MIRRORS`; an unlisted cell keeps the old default rather than inventing a path | `$EQR_DATA_ROOT` |
| `tpu_cmd/xm_launcher.py::_local_bucket` | checkpoint bucket matching `--cell` from `_CELL_BUCKETS` | `--bucket` |

**There are now FOUR full data metros plus one partial** (was three). A run
reads the mirror in its own metro; the five mirror dicts in `data_util.py`
(`_MIRRORS`, `_OFFLINE_MIRRORS`, `_SETTINGA_MIRRORS`, `_SETTINGB_MIRRORS`,
`_SETTINGB_V3_MIRRORS`) all carry the same cell→root mapping and must be kept in
sync when a cell is added:

| metro | data cell | v-family | completeness |
|---|---|---|---|
| cbf | `is-d` | v7 | full (generation source) |
| tul | `nm-d` (data) / `oi-d` (ckpt) | v7 | full |
| lpp | `li-d` | v7 | full |
| **dfw** | **`rs-d`** | **v4** | **full** (all datasets; added for cheap v4) |
| las | `dl-d` | v4 | **PARTIAL** — maze v4 working set only (64x64-offline + companions + settingA/B); NOT settingB_v3 / 128x128 |

`las`/`dl-d` being partial means `storage.md` §Existence Is Not Completeness
bites: check `_MIRRORED`/`_SUCCESS` on `dl-d` before pinning a job there rather
than assuming a dataset exists. `research/v7_storage_placement.md` owns the
authoritative cell survey and the `las` naming trap (`la-d`/`lb-d` are `lpp`, not
`las`; only `dl-d` is `las`).

**Every host must read the checkpoint itself.** The obvious optimisation — rank
0 reads and `broadcast_one_to_all` rather than N hosts amplifying the read
N-fold — halts the TPU core with `RuntimeUnexpectedCoreHalt` *after* the read
succeeded, `ocp.Checkpointer.restore()` being ITSELF a collective ending in a
`sync_global_processes` barrier; and it is unpatchable as written, non-readers
being unable to predict the dtype orbax returns. `ckpt_util.py` records the one
construction that would work
(`MultiprocessingOptions(primary_host=0, active_processes={0})`). Distance has a
fix here; read amplification does not.

**A host-local single-device model cannot be orbax-saved unchanged on a multi-host
slice.** The DP-CNN baseline (`dp_train.py`) shards nothing — every host runs an
identically-seeded replica — so its params are `SingleDeviceSharding` `jax.Array`s, and
`ocp.StandardCheckpointer.save` REFUSES them when `jax.process_count() > 1`
(`ValueError: Cannot serialize host local jax.Array ... in multi-host setting`).
`active_processes={0}` skips the write *barrier* but NOT this check. It trained clean to
step 90 then crashed at the step_100 save — invisible to any single-process local run or
hermetic-binary smoke, only on a real ≥2-host Borg slice. Fix: `jax.device_get` the payload
to host numpy before save, and restore into a numpy target symmetrically. Any replicated
(non-sharded) model checkpointing from a multi-host slice needs this.

## Loader, Sampler State, And Run Length

- **`training.total_steps` is the only run-length input** and the train loader
  is endless. `epochs`, `max_steps` and `train_epochs_per_iter` are retired and
  raise naming their successor; a fixed-size corpus still prints its epoch
  budget, as a report and never a stopping rule.
- **An "epoch" here was never a pass over the data:** every builder writes
  `mean_puzzle_examples = 1` and every corpus holds 1000 groups, so
  `steps_per_epoch` floored to **1** and `epochs: 50000` meant 50,000 steps.
  Distrust the concept in an old config or checkpoint.
- **Verify a resume by step progress, not by exit status** (`../jobs.md` §A
  restart loop is not evidence of a crash). The retired
  `epochs / train_epochs_per_iter` design checkpointed an exhausted cursor, so a
  resume evaluated `while N < N`, yielded zero batches, "finished" without a
  step and exited 0 — every restart looking like a clean success.
- **Anything added to sampler state must be O(1) in corpus size; otherwise store
  the seed and replay it.** Persisting `group_order` =
  `rng.permutation(num_groups)` meant 3.8M integers in a 45 MB `extra.json`
  rewritten every save, and a job deleted mid-write left the resume parsing its
  own truncated bookkeeping. Replay needs the state from BEFORE the draw, so
  `epoch_rng_state` is what is stored (`rng_state` has already been advanced)
  and `_iter_train` replays the permutation.
- **Cast a `np.searchsorted` key to the index array's dtype:** the arrays are
  `int32` and a Python `int` is int64, so NumPy upcasts the *entire* array on
  **every batch** — 364x on `_iter_test`, ~20 hours instead of ~3 minutes per
  pass over a 20M-row split. Recognise the signature: **throughput pinned at a
  constant batches/s regardless of batch size** is a fixed per-batch cost, not
  an I/O problem.
- **A batch larger than the split makes the loader spin silently:** the train
  path is drop-last, so it yields nothing, re-shuffles and yields nothing again
  — 100% CPU, no batches, no error, forever. Clamp with `min(batch_size, n)`.
  **This applies to training configs too:** a global batch larger than a small
  eval split hangs the run.

Both loader defects were invisible while every split was 1k rows and bite harder
the larger the corpus; re-check them if either is reverted.

## Evaluating A Published Checkpoint

- `extra.json` records only the fields **overridden** at training time, so
  `_resolve_eval_config` must MERGE it over the config defaults rather than
  replace the section, or `hidden_size`/`num_heads`/`L_layers` vanish and
  pydantic reports `Field required [type=missing]`.
- A checkpoint's dataset name may not be in `DATASET_PATHS`: the published
  sudoku one says `Sudoku-1k`, the same corpus as `Sudoku-aug1000`, and unmapped
  names become literal paths failing as "split train does not exist".
- **Torch keys carry a `_orig_mod.model.` prefix** (`torch.compile` plus the
  wrapper module) absent from the flax tree; `tools/convert_torch_ckpt.py`
  strips known wrapper prefixes automatically, so do not pass `--strip-prefix`
  by hand.
- **Orbax `partial_restore=True` returns unmatched leaves unchanged** — still
  `model.init`'s random values, no error, no warning — so a mismatched key set
  evaluates at chance (sudoku showed `all/accuracy` 0.0907 = 1/11) and reads as
  a modelling problem. **Never add a restore path bypassing
  `utils/ckpt_util.assert_tree_matches` (key sets and shapes) or
  `assert_restored_differs` (unreadable metadata).**
- **Restore with explicit `RestoreArgs(restore_type=np.ndarray)`**, or orbax
  infers a placement per array and raises `sharding ... Got None` on a
  multi-host job. Older orbax reads the checkpoint's `_sharding` file and only
  warns, so a single-device CPU box cannot reproduce it.
- The published checkpoint **does** carry an EMA shadow at
  `blob["ema"]["shadow"]` (mu=0.999, ~5e-3 from the raw params), so EMA never
  explains a large gap.
- **The released sudoku checkpoint was not trained with the released recipe** —
  though its `pos_encodings: none` against the recipe's `rope` is NOT the
  deviation, both running `mlp_t: true`. The difference is the puzzle embedding:
  the checkpoints set `puzzle_emb_ndim/len` 512/16 (hence `seq_len` 97, not 81)
  with a NON-ZERO table and the reference yaml never mentions the knob, so
  reproducing the paper by training requires the checkpoint's arch.
- **Compare against the right upstream baseline:** upstream `README.md` reports
  both a 2048-example smoke eval (`cumulative_exact_acc_top1` 99.19) and the
  423,168-example full set (99.79). `different_init/any_correct` is
  mathematically `pass@n` and is the only one reported (`pass@k` is emitted only
  for `k < n`), while `cumulative_exact_acc_topN` is the mean over the N
  most-converged samples, so `...top4` equals `convergence_top_k/acc`.

## Experiment Tracking

Config fields keep historical `wandb` names; no API key is needed, and there is
no real external tracker unless current code proves one was created.

- **`import wandb` resolves to a mock** implementing only `init`, `log`,
  `finish`, `Table`, `plot`, `Video`, whose `log()` stores nothing; every other
  attribute raises **at call time** — on Borg, after packaging and scheduling
  succeeded. Route calls through `utils/wandb_util.py`, whose `safe_log()`
  swallows failures; telemetry must not kill a run.
- Metrics reach a UI through Datatables via `clu.metric_writers`; URLs and the
  explicit-opt-in trap are `../research/result_logging.md` §Chart Links.
  Specific to this code: only `process_index()==0` may build a writer (all tasks
  of a work unit share one key), and it must flush periodically, CLU's
  destructor cancelling the writer thread rather than draining it.
- **Anything that builds a logging handler unhooks the remote log mirror**,
  which under Borg is the ONLY log. `main.py` tees stdout/stderr to
  `$CHECKPOINT_BUCKET/logs/rank_<n>.log`, but stdlib handlers capture the stream
  they were constructed with, so a metric writer steals it back and the log
  stops dead mid-run. Call `logging_util.reattach_absl_handlers()` afterwards,
  repointing `get_absl_handler().python_handler` — not the outer object, which
  has no `setStream`.
- Resume uses the experiment identity (`resume_xid`) and its workdir; verify
  checkpoint and config continuity before treating appended charts as one run.
  Checkpoints go to `$CHECKPOINT_BUCKET`, never `workdir`;
  `main.py::_apply_borg_autoresume` rediscovers the newest complete one at
  startup, and `../jobs.md` owns the env-var contract.
- A run that reaches a conclusion is logged to the **`EqR-refactored`** tab,
  never `EqR-reproduction` (history); `../research/result_logging.md` owns how,
  including which column holds per-token versus whole-board accuracy.
- **Maze runs use `v7-32`**: the 16-chip half buys half the compute for the same
  wall clock, and the family's published rows are all v7-32. The arch makes this
  expensive to get wrong — one ACT step is
  `H_cycles * (L_cycles + 1) * L_layers` layers (84 at the 3/6/4 default),
  training unrolls the full `halt_max_steps`, and a 100k-step maze leg already
  runs ~8 hours at v7-16's measured 3.53 steps/s.

## Metric Names, Divisors, And Denominators

`../research/result_logging.md` owns the general discipline; the checkout's
`README.md` §metrics describes this surface and holds the full divisor table —
keep it true, and read it before hand-reducing any raw key.

**A logged key is not a delivered column, and nothing says so.**
`_flatten_scalars` in `utils/wandb_util.py` silently DROPS anything not
float-able (histogram, figure, array, bool, string, NaN) on the way to
Datatables, and the `wandb` mock stores nothing either — so a metric can be
computed every step for a feature's whole life and reach no reader, with no
error at either end. **Verify a new metric by printing the payload the run
actually logs, not by testing the function that builds it.**

### Which key is it

**Every logged eval column names its point and its weights**, as
`D<depth>[B<breadth>]/{ema,online}/...`, and appears exactly once; charts use
`D16/ema/acc`. The sweep path carries the same point tag as the in-training
eval, so the two are directly comparable. Two levels are gone from the sink: the
`eval/depth`-style coordinates, which print to the log, and the dataset `set`
level, dropped from column, `evaluate()`'s return value and results json alike
(every corpus declares `sets=["all"]`; a dataset with two sets makes it
reappear).

**Several keys are called `lm_loss`. Name the one you mean** — they differ in
split, weights, denominator and cadence, the eval ones being ~30 points against
~1500, and quoting the train curve at an eval-chart reader has inverted a real
conclusion.

| Key | Source |
|---|---|
| `train/lm_loss` | train split, train cadence |
| `D<k>/{ema,online}/all/lm_loss` | online eval, per depth and weight set |
| `{ema,online}/all/lm_loss` | standalone eval; `all/lm_loss` in its results json |

**`token_acc` is not comparable across output formats:** a grid head's covers
900 board cells of which ~884 copy the observation, an AR head's `n_predict + 1`
real predictions — two runs of one task can differ 53x in denominator. `acc`
(whole answer right) is the comparable column.

### Divisors and cadence

- **Loss keys are SUMS over rows and the divisor is `global_batch_size`, not
  `count`.** `train.py::process_metrics` picks per key: keys ending in `loss`
  divide by `global_batch_size`, most others by `count`, which counts only the
  rows that HALTED that step — dividing a loss by it inflates the number ~100x
  and still looks plausible.
- **A logged `train/*` value is the WHOLE INTERVAL, not one batch:**
  `StepAccumulator` folds every step and the step on the `log_per_step` grid
  drains it, divisor scaled by the interval. The FINAL point is still one
  interval, so **compare runs on a tail-window mean over the logged curve, not
  the last row**. There is deliberately no smoothing knob — the one that existed
  averaged the pre-denominator sums, making its "smoothed loss"
  ~`global_batch_size` times real.
- **`train/lm_loss` is not comparable across runs that halt at different
  depths**: a run pinned at `halt_max_steps` buys its lower loss with more
  compute. Check `train/act_loops_mean` first; if the depths differ, use a
  fixed-depth eval.

### Denominators and padding rows

**An eval's denominator is its REAL rows, not the rows it was fed.** Feeding
more rows than the split holds is legal — a `512 x 2` maze eval feeds 1024 for
1000 puzzles — and `puzzle_dataset._collate_batch` pads the tail with
`labels = IGNORE_LABEL_ID`. Pad rows are EXCLUDED rather than scored (loss head
gates on `valid = loss_counts > 0`, tallies filter through
`eval_fn._drop_unscorable`, `different_init/total_samples` reports the real
count), so padding costs compute, not correctness. **Do not apply a hand
correction on top — that now UNDER-reports.** Before the fix a pad row satisfied
`((pred == labels) | ~mask).all(-1)` vacuously and counted as a perfect solve
for every replica, once manufacturing a whole maze accuracy out of 24 pad rows.

Two cross-checks: **read `total_samples`** to confirm which regime a number came
from, and check `different_init/avg_pass_rate` against `acc` **of the same
weight set** (`ema/` with `ema/`, never across) — one quantity by two routes, so
they agree exactly or something is wrong. On a unique-solution split the
solution metric and `acc` must also agree exactly (§Maze Scoring).

## Checkpoint Retention: Keep The Peak

**The retained set is the result.** A peak whose weights were deleted cannot be
re-evaluated, published, or recovered by re-scoring — retention loss is
IRREVERSIBLE, which makes every rule here load-bearing.

- **`training.checkpoint_best_metric` promotes the best-scoring step** to
  `checkpoint_best_<metric>_<n>/`, deliberately OUTSIDE the `step_<N>` namespace
  every retention rule matches on, so the in-job pruner, `tpu gc` and
  auto-resume all ignore it and no future sweeper must learn about it. Without
  it the default policy (newest 2 plus a 50k ladder) deletes exactly the
  checkpoint a peak-reporting row needs: **this family peaks off the ladder** —
  120k of 150k on maze, 40-45k of 50k on sudoku. **Auto-resume still restores
  the NEWEST checkpoint, never the best.**
- **`checkpoint_interval_steps` must DIVIDE `eval_interval_steps`**, so every
  evaluated step has a checkpoint behind it — the peak is promoted from the
  checkpoint saved at that same step, and there is no substitute source. Report
  the peak for a family that rises then collapses; a peak with no checkpoint can
  be neither re-evaluated nor published. Nothing checks the relation at config
  load: `promote_best_checkpoint` warns and skips, so a violated ratio costs the
  peak silently, one eval at a time.

  | relation | consequence |
  |---|---|
  | `ckpt` divides `eval` | every evaluated step is promotable |
  | `ckpt` a multiple of `eval` | only every `ckpt/eval`-th eval can promote |
  | otherwise | promotion is sporadic; read the warning, not the curve |

  Both intervals default to the same value in `configs/default.py`, which
  satisfies the relation; a config that overrides one must re-check the ratio.
  Verify by reading the two keys in the config you are launching —
  `grep -n '_interval_steps' configs/<name>_config.yml` — never by assuming the
  last run's numbers, since `remote_run_config.yml` is overwritten by every
  launch and the smoke templates run intervals of single digits.
- **Track SEVERAL metrics: a retention policy driven by ONE inherits that
  metric's bugs.** The selected step is kept and the rest go on the ladder, so
  an over-reporting scorer does not merely mis-state a number, it keeps the
  wrong checkpoint — paid once, when `auto` resolved to the single buggy key
  `solution_acc`. `auto` now keeps the best under EVERY headline key the run
  reports (`walk_acc`, `solution_acc`, `acc`), one deduplicated directory each,
  so a metric fix costs a re-score rather than the run. **Still re-rank the
  retained steps against the run's own logged curve after ANY metric fix**, and
  expect pre-change peaks to be unrecoverable.
- **`"auto"` resolves against the FIRST REAL METRICS DICT, not the config**,
  since which accuracy a run reports depends on its dataset and its head.
  `_BEST_METRIC_PREFERENCE` in `utils/ckpt_util.py` is the list, in headline
  order; `resolve_best_metrics` in the same file is the resolution. **Read the
  tuple in the checkout you are launching rather than trusting a copy** — its
  spelling differs across branches, and the two spellings behave differently:

  | spelling of an entry | how it matches |
  |---|---|
  | fully qualified (`D16/ema/acc`) | exact key; a run at another depth matches NOTHING |
  | bare name (`acc`) | `<point>/ema/<name>`, shallowest breadth-1 point, so the depth comes from the run |

  Finding nothing disables retention behind ONE warning at the first eval, after
  which the ordinary ladder deletes the peak. **A CPU smoke only catches it if
  it carries the run's real `halt_max_steps` and `online_eval`** — smoke the
  LAUNCHED graph, and read the "tracking …" line the first eval prints.
- **Never point an eval at a LADDER checkpoint of a job that is still running.**
  It races that job's `checkpoint_keep_last` and always loses — packaging and
  scheduling take minutes, in which two more checkpoint intervals delete the
  named step — and surfaces as `FileNotFoundError` on a path that existed when
  typed, reading like a typo. Target what retention exempts: a milestone
  (`checkpoint_milestone_every`) or a `checkpoint_best_*`. A finished run is
  safe, but keep the habit.
- **Never sweep a name you do not recognise.** The older single-metric
  `checkpoint_best_<n>` is still on CNS, and for most runs that have one it
  names a step no `step_<N>` on the ladder still holds, so the job and `tpu gc`
  match both shapes and neither deletes an unfamiliar one. When a retention rule
  cannot PROVE a copy is superseded (unreadable sidecar, no metric named) it
  keeps it: a kept copy costs disk a tool can report, a deleted one costs
  weights nobody can reproduce.

## Eval Protocol: Report B=1 First

**The headline number for any EqR run is accuracy at B=1** (one restart, no
selection) at both depths the paper uses: **D=16**, the arch's own
`halt_max_steps`, and **D=64**, its depth-scaling point. Breadth is an extra —
it multiplies eval cost by B and answers a different question. **Which accuracy
depends on the dataset:** `acc` on sudoku, `solution_acc` / `walk_acc` on a maze
(§Maze Scoring), both from the same eval.

**A run reports its own headline; a second job is not required.**
`evaluation.online_eval` names the (depth, breadth) points the in-training eval
scores every `training.eval_interval_steps`, and its default `[16, 64]` at B=1
on both weight sets IS the protocol above — so a run's result is
`D16/{ema,online}/acc` (or `walk_acc`) on its own training curve.
`online_eval: []` restores the old single-point behaviour; each point rebuilds
the module via `model_copy` (a frozen dataclass cannot be re-depthed in place),
so it costs a recompile, not a reload. The `EqR-refactored` tab matches:
`Acc B=1 D=16`, `Acc B=1 D=64`, `Acc-any-correct (B=1)`, then
`additional results`.

### Comparability rests on the sample count

`online_eval` does not control it: the population is
`evaluation.global_batch_size x max_eval_steps`, and the test loader walks the
split in order from the start, so two evals with the same product score
literally the same rows at any batch size. **Keep a training config's product
equal to the standalone protocol's**, or its curve is not comparable to an
`eval_only` row:

| Dataset | Population | Note |
|---|---|---|
| sudoku | 2048 rows of 422,786 | FIXED-SIZE SUBSET — comparable to upstream's 2048-sample figure, not its full-split one |
| maze | the whole 1000-puzzle split | covered entirely |

Leaving `max_eval_steps` unset walks the entire split every interval — a few
hundred times the work on sudoku. Verify sizing in the config: a differing
product measured a different population, whichever way the number moved.

**An eval batch is only correct against a DEVICE COUNT, and a chip count is not
one.** `check_eval_batch_layout` refuses a per-process batch that `pmap` cannot
lay out, at STARTUP: it needs `global_batch / process_count % local_devices ==
0`. A v6p/v7 chip carries TWO cores, so a `v7-32` is **64 devices over 8 hosts**
and the natural-looking `500` gives `500/8 = 62`, `62 % 8 != 0` — it raises
before step 1. An eval batch inherited from another run's config carries that
run's slice shape with it, and nothing in the yaml records which slice it was
sized for.

**Prefer over-feeding to a batch that divides the split**, because on a
1000-row maze split the two constraints are incompatible: no divisor of 1000 is
a multiple of 64 (125, 200, 250, 500 all fail). `512 x 2 = 1024` is the maze
answer — `TEST_POPULATIONS` caps the walk at the split's first 1000 rows
whatever the batch shape, `_iter_test` pads the tail and `drop_unscorable`
removes the padding, so the SCORED population is unchanged and the cost is
compute on pad rows. The comparability rule above is about the *scored* rows,
not the batch product, whenever a `TEST_POPULATIONS` entry binds.

### Breadth, in the same job

**Set `evaluation.final_eval: true` with a non-empty `evaluation.sweep`.** It
runs the full cartesian product against the final checkpoint after the last
training step, through the engine a standalone eval uses, so breadth and
convergence-top-k columns arrive without a second launch to match back by hand.
Off by default (the sweep is expensive), and an empty sweep with it on is
rejected at config load rather than ending a long run with a log line.

**A breadth eval can silently deliver less breadth than you asked for.** Restart
latents come from a key broadcast to every device, so a draw is a function of
the WITHIN-DEVICE row index only and effective breadth is
`min(per_device_rows, n_init)` — B replicas straddling devices get duplicate
latents. Nothing in the metrics shows it (`total_samples` stays right,
`avg_pass_rate` still matches `acc`); only diversity shrinks, so
`different_init/any_correct` and `convergence_top_k` under-report by that
factor. Config load refuses such a layout; apply the rule when sizing by hand.

### What the paper reports for breadth

**The paper's B=128 figure (Maze 93.0) is top-1 convergence accuracy** — the
restart with the smallest mean residual over the last L=3 iterations — NOT
majority vote, which the paper never reports. **Do not "improve" a reproduction
row by swapping in the higher number:** majority vote does score higher
(released maze checkpoint at D16/B128: 99.2 against conv-top1's 94.9), but the
weaker selector is the point, conv-top1 testing the paper's own claim that
latent convergence predicts solution quality. Majority vote here is over the
ENTIRE token sequence (`tuple(row)` keys `eval_fn._update_di`), not per-token —
hence its strength on a maze, which has one correct path against many wrong
ones.

**A breadth metric going DOWN as depth goes up is expected, not a bug.**
`convergence_top_k=4` caps the candidate pool before top-1 is taken and the cap
binds (`convergence_top_k/any_correct` is 95.70 at both D=16 and D=64 for the
released checkpoint), while deeper reasoning makes restarts agree MORE, so
diversity falls and vote-style metrics worsen slightly. Base capability does
improve (`acc` 82.61 -> 89.30, reproducing the paper's 82.2 -> 88.9).

## Maze Scoring: Is The Output A Solution

A generative loop *produces* an answer, so the question is "is what it produced
a solution", not "does it equal the stored one". Those coincide only when the
answer is unique, and every stock maze split here is `perfect` (acyclic, one
simple S->G path) — so `acc` has been answering the reproduction question while
read as the solving one: harmless there, badly wrong off it.

- **`solution_acc` (grid heads) / `walk_acc` (`final_head_type: ar`) is THE MAZE
  HEADLINE**, with `acc` beside it as a diagnostic: the loss head emits `acc`
  for every dataset, so it tells you whether a model with `walk_acc` 0 learned
  anything. Scoring auto-enables on a maze dataset,
  `evaluation.solution_scoring` forces it either way, and both reach the
  periodic eval — a maze run's result is `D16/ema/walk_acc` where `D16/ema/acc`
  is for sudoku.
- **On a unique-solution split the solution metric and `acc` must agree EXACTLY,
  row for row; a divergence is a bug in the scorer, not a finding.** One simple
  path plus labels differing from their input only on path cells fully determine
  the grid. Use it as the scorer's test before trusting either metric off such a
  split.
- **Use `Maze-30x30-multi` whenever the claim is about solving** — 1000 fixed
  braided mazes, each with >=2 shortest paths, built and verified per puzzle by
  `tools/build_maze_multisolution_testset.py`. One checkpoint scores **40.2
  exact vs 99.3 solution** (D16, EMA; the latter pre-completeness, so a
  ceiling): a solver picking uniformly among shortest paths matches the label
  only 36.5% of the time.
- **Every cell of a grid head's output is an answer, so a cell painted that
  should not be is an ERROR.** `solution_acc` needs both halves — a legal S->G
  route in the painted cells, AND every unpainted cell still equal to the input
  board — since without the second, a correct route over a board with S painted
  over scored solved while `acc` said wrong. It constrains cells AROUND the
  route, never which route was drawn, so `Maze-30x30-multi` still separates the
  two metrics.
- **That rule has NO counterpart in `walk_acc`, and the asymmetry is the
  format's:** a move sequence has no off-path cells to get wrong (the board is
  an input the head cannot write to), and a walk may enter a dead end and come
  back where a painting cannot. So on a unique split `solution_acc` equals `acc`
  while `walk_acc` is looser.
- **Both scorers check against the INPUT board, never the label**, which is how
  the metric demands a whole correct grid without becoming exact match.
  `maze_solution.py` (grid heads) and `maze_walk.py` (AR heads) are one
  definition for two formats — keep them so, minus the rule only one can state.
- **A longer legal route counts as solved, deliberately** — requiring the
  shortest path puts the label back into a metric whose purpose is to not need
  one. `shortest_solution_acc` / `shortest_walk_acc` carry the strict number,
  their reference BFSed **from the row's own input board**, not the split's spec
  file; it constrains the ROUTE only, and cannot bite on a `perfect` maze.
- **The empty prediction must be rejected explicitly:** a pad row decodes to no
  path, and "the cells form a route from S to G" is vacuously true for the empty
  set when S adjoins G — the trap `_row_exact_correct` guards with
  `supervised > 0`.
- **A test-only split still needs a `train/` directory:** `just_evaluate` builds
  a train dataloader purely to read `vocab_size`/`seq_len`. One puzzle is
  enough, and keeps the split unusable for training.

### Which number is a bound, and which must be re-scored

- **A scorer that reads only part of the output can only OVER-report**, so its
  numbers are upper bounds that no arithmetic repairs: re-score. On a
  unique-solution split the corrected value is that run's own `acc`, already
  reported.
- **A `shortest_*` number from before the input-board BFS is a LOWER BOUND:**
  the spec array is in split order and the scorer indexed it by
  row-within-batch, aligning only the first batch at breadth 1. A wrong
  reference can only flip `shortest` True->False, so re-scoring is the only fix;
  non-strict columns never read it.
- **Two one-directional errors in OPPOSITE directions do not compose into a
  bound.** `shortest_solution_acc` from before both the BFS reference and the
  completeness rule is pushed down by one and up by the other: not a bound in
  either direction and not correctable. **State which fixes a number predates
  before calling it a bound.**

### Periodic-wall (Setting-A) corpora

**`Maze-period-easy` / `Maze-period-hard` are the dynamic-maze corpora** — 20M
train + 1k test each, mirrored to all four full data metros (cbf/tul/lpp/dfw;
plus partial `las`) and registered in `_SETTINGA_MIRRORS`, same 30x30 geometry as
the static corpora and so drop-in
comparable, plus **period-P blinking walls**, one token per phase (`easy` P=2,
vocab 8; `hard` P=3, vocab 9). The solution is still a drawable wait-free line,
so image-to-image is unchanged; full definition in
`~/work/maze_settingA_data/DATASET_SPEC.md`. Two things do not transfer: the
score is `2^-floor(e/2)` for `easy` but `2^-e` for `hard` (the parity argument
behind floor-halving fails at P=3, where one WAIT shifts the residue), and
**`hard` exists because P=2 admits an O(1) shortcut** — wall lethality is
`phase == (row+col+parity(S)) % 2`, 100% on `easy` and chance on `hard`.

**A periodic-wall corpus needs the CLOCKED scorer, and the wrong one scores the
GROUND TRUTH zero.** Clockless, phase-blind `maze_solution.py` rejects a painted
phase cell as "not OPEN", scoring the corpus's own labels 0/1000, so
`eval_fn.maze_scoring` picks `maze_periodic.py` whenever the SPLIT's
`vocab_size` implies `P = vocab - 6 > 0` — from that number, not from a board,
which need not use every residue. The symptom is not a crash but `solution_acc`
at 0.0 all run while `acc` climbs: **check the `[eval] maze solution scoring ON`
line and the first eval's value against `acc` before believing a zero.**
`walk_acc` has no timing rule, so an AR head here reports an upper bound and
says so.

## Close-Loop: The Headline Scores ONE Decision Point

A close-loop puzzle (`dataset.closeloop`) is an EPISODE. **The default
`dataset.closeloop_mode: persistent` gives one ROW one whole episode**, the ACT
latent `z` walking its decision points and KEEPING its value across each world
timestep, reset only when the episode is exhausted — so training covers every
decision point of every episode it touches, in order. The older
flatten-to-independent-rows behaviour, where every timestep started from a fresh
random `z`, survives only as the ablation arm `closeloop_mode: flat`.

**The TEST split is FLAT in both modes** (`eval_fn`, `_pad_batch` and the
rollout all take 2-D rows) and fixes its timestep, an eval having to score the
same rows every run. So **the reported `acc` describes ONE decision point per
episode** — the easiest one, since at the first decision the phase rotation
`(phase - t) % P` is the IDENTITY and the observation is bit-identical to the
stored board, while every later frame is rotated. Under `flat` that point is
1/18 of the training distribution; under `persistent` training sees all ~18 and
the eval scores one — a mismatch either way.

**An optimizer step advances a row by one ACT step, not by one decision**, and
runs must be sized from it: an episode occupies `n_decisions x halt_max_steps`
steps — on the staged P=2 split, 104 at the shortest route, **144.50 at the
mean**, 288 at the longest, i.e. ~9x fewer puzzles per step than open-loop
D=16's 16. `dataset.closeloop_refresh_every` (default 16) reuses one device
batch for K steps; config load REFUSES `K >= min_decisions x D` (104 at
`n_execute 8, halt_max_steps 8`), above which one row slot silently gets two
episodes.

### Reading a close-loop number

- **A saturated `acc` is the expected outcome here, not a strong result:** the
  per-decision task carries no signal for this arch — a stratified sweep found
  1.0000 at every decision point. The information is in the ROLLOUT
  (`evaluators/closeloop_eval.py`), where the model's own errors take it off the
  GT trajectory into frames no training row contained, whereas every
  periodic-eval frame sits ON it. **Budget the next run against the rollout
  metric, not `acc`.**
- **`acc ** d` is NOT an estimate of episode success:** it assumes every
  decision point is as hard as the one measured, and the others have not been
  measured. Do so with `dataset.test_decision_index` — an INDEX into the
  episode's own decision points (negative counts from the end), not a world
  time, since episodes differ in length; it clamps rather than dropping short
  ones, so every stratum scores one population. **Index `-1` is structurally
  different, not merely later**: the route runs out and the ground truth paints
  a PARTIAL segment, so report it separately.
- **`solution_acc` / `walk_acc` are both refused under close-loop** by
  `eval_fn.maze_scoring`, for one reason covering both formats: a segment stops
  `n_predict` moves along and never reaches G, so "do the emitted cells/moves
  form a route to G" is false on the CORPUS'S OWN LABEL, and reporting it would
  print a hard 0.0 for a whole run while `acc` climbed. `acc` and `token_acc`
  are the columns until the rollout metric lands; say so in the config header.
- **`state_token_acc` has a do-nothing floor of ~0.998 on the P=2 split**, so it
  is not a headline number there: `arch.state_head` predicts the frame
  `k = n_execute = 8` ticks ahead, and a P=2 rotation by 8 ticks is the
  IDENTITY. Score changed cells only, pick a `k` that is not a multiple of `P`,
  or measure on P=3.
- **`arch.train_halt_head` defaults OFF under close-loop** (True open-loop): the
  halt head decides when a TIMESTEP is settled, not when a puzzle is answered.
  Config load prints which way it resolved; an explicit yaml setting is
  honoured.
- **`configs/local_debug_closeloop_config.yml` needs `--timeout 5400`**, against
  `scripts/local_debug.sh`'s 300 s default: the template needs ~30 min, nearly
  all of it the rollout eval, which is slow rather than broken and completes
  with scoring ON at 5400 s. If the claim under test is only "the pipeline
  runs", `evaluation.closeloop_scoring: false` finishes in ~7 min; use scoring
  ON for any number you quote.

## RoboTwin DP Baseline

The RoboTwin 2.0 Diffusion-Policy (DP-CNN) baseline lives on branch
`dp_dataloader_rewrite` (`dp_train.py`, `dataset/robotwin_dataset.py`,
`configs/remote_run_dp_config.yml` + `configs/dp_default.py`). It is a
single-device REPLICATED model (every host runs an identical seeded replica, one
chip does the work), so it is HOST/DATA-bound, not TPU-bound — a small
single-host slice runs it at the same speed as a big one. `../storage.md` and
`../jobs.md` own launching; the DP-specific facts are here.

**The 5 ablation tasks are FIXED — always use these five, never re-pick.** Running
all 50 `clean_50` tasks costs ~26 h of accelerator time (~32 min/task); these 5
were chosen once to span the
benchmark's skill families with NO family repeated (RoboTwin 2.0 has no official
skill taxonomy — the 50 tasks are a flat "dual-arm" list, so this grouping is
derived and code-verified against `envs/*.py`). Diversity axes: skill family ×
arm × object type × horizon × difficulty.

| Task | Skill family (unique) | Arm | Object | Horizon (steps) | DP-Easy |
|---|---|---|---|---:|---:|
| `open_microwave` | articulated open (revolute door) | single | articulated | 537 (longest) | ? |
| `handover_block` | dual-arm handover | dual | rigid | 283 | 10% |
| `stack_blocks_three` | stacking (precise, long) | single | rigid | 481 | ? |
| `dump_bin_bigbin` | pour / granular (only non-rigid) | dual | granular | 265 | 49% |
| `beat_block_hammer` | tool-use (strike) | single | rigid+tool | 113 (shortest) | 42% |

Why this set: five DISJOINT skills (articulated / handover / stacking / pour /
tool-use) — deliberately NO plain pick-and-place, which is 15 of the 50 tasks and
would waste a diversity slot. Arm mix 3 single / 2 dual; object types cover
articulated + rigid + granular (RoboTwin 2.0 has NO deformable tasks —
`dump_bin_bigbin`'s granular pour is the closest non-rigid case); horizon 113→537;
known DP-Easy 10/42/49% is a real low→mid spread (not saturated >95% like
`grab_roller`, not dead-0 like `blocks_ranking_rgb`), so an ablation has signal.

**Dataloader is eager-decode-to-RAM (`dataset.eager_images: true`,
`num_workers: 0`).** A `clean_50` task is tiny (~3855 rows, 173 MB JPEG on disk,
888 MB/camera decoded); the loader decodes the whole split into RAM once (~2.6 s)
then serves every frame by O(1) index. This beat the worker-pool path outright:
MEASURED single-process 2.65 → 12.1 batches/s local (the `num_workers=16` spawn
pool only reached 5.0 — it is IPC-bound, pickling ~88 MB of decoded uint8 per
batch back to the parent, not CPU-bound). End-to-end on a v7-8 the run holds
**~10.4 steps/s** (was ~3.1 host-bound), so one task is ~29 min of training +
~4 min startup. Leave eager OFF only for a corpus too large to hold in host RAM.

**v7 minimum slice is 8 chips**, even though `tpu preflight v7-4` reports GREEN —
the allocator's min-slice rule blocks v7-4 with no work unit created. Use `v7-8`
for a single-host-class DP probe (2 hosts × 4 chips; the model runs on 1
chip/host). yumrnel g9 PROD is the proven-hold cell; its co-located bucket is
`/cns/qo-d`.

**DP logging matches the EqR `train.py` progress line** on purpose:
`[step/total pct%] loss=, lr=, steps_per_second=`, throughput as
`steps_per_second` over the log interval (NOT s/step). Do NOT wrap the train loop
in `prefetch_to_device`: its background thread runs the loader cursor ahead of the
trainer, so the checkpoint's `dataloader_state` sidecar records a cursor that far
ahead and a resume then SKIPS those batches — not bit-identical, breaking the O(1)
resume contract. The async loss de-sync (defer `float(loss)` to log boundaries)
already overlaps host work with device compute without touching resume.

### Close-loop eval on the A100 (SAPIEN)

**The GPU-side close-loop evaluator is a SEPARATE manual step, not auto-triggered.**
Training publishes each checkpoint to the GCS rendezvous bucket
(`gs://qiaos-robotwin-eval-us-east4/runs/<xid>/checkpoints/step_<n>/`, state +
`extra.json` with the normalizer + `dataloader_state`) — a Borg task cannot open
an IPv4 socket to the VM and the VM cannot read CNS, so GCS is the only
rendezvous. But nothing runs the eval automatically: it is a worker on the A100
VM `deepflow-1a100-80gb-jh-baseline` (34.186.64.63, us-east4-c, project
`viscam-cloud`), code at `~/work/robotwin_eval_bridge`.

- **SSH from a restricted agent shell CANNOT `gcert`** (no ssh-agent socket), but
  the metadata key works: `ssh -i ~/.ssh/google_compute_engine -o
  ProxyCommand="/usr/bin/corp-ssh-helper --proxy-mode=grue %h %p" qiaos@34.186.64.63`.
  Network gate and auth gate fail separately (`../gcp_gpu_ssh.md`).
- **Run:** `~/work/jax_venv/bin/python eval_worker.py --task <T> --xid <X>
  --rollouts 50 --on-backlog latest --interval 0`. It auto-spawns `sim_server.py`
  in `rt_venv` (numpy-1.x, SAPIEN). ONE worker maps ONE `--task` to ALL its
  XIDs, so a fleet of different-task XIDs needs **one invocation per (task,xid)**.
  Drive them serially from a `setsid` script (N=1 concurrency is optimal; N>=2
  drops throughput ~30%). Use a FRESH `--state` file or a re-eval is skipped.
- **Speed ~60 s/rollout** (400-step episode; ~32 s on an early success), so 50
  rollouts ~= 50 min/task. Uses EMA weights + the checkpoint's own normalizer
  (self-sufficient). wandb on the VM is NOT logged in — training is `mode:
  offline` anyway, so eval runs `WANDB_MODE=offline` (local run dirs) or
  `--no-wandb`; online needs the API key on the VM.
- Reference: click_bell (prior run 279324385) step_17400 scored **0.50 (25/50)**;
  the task's scripted expert hit 20/20 on the same seeds, so the harness is sound
  and 0.50 is the model's real score.

### Per-Task Cost And Where Results Go

**Per-task training cost varies ~4.3x** because total_steps = floor(n_windows/128)
*600 and n_windows spans 5572 (beat_block_hammer) to 23902 (open_microwave). For
an EQUAL-COST ablation across the 5, cap with `training.max_steps` instead of
fixed `num_epochs`. Results are logged to the **`RoboTwin-DP` tab** of the EqR
workbook (`17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`) — one row per task,
training metrics + close-loop `success_rate` (50 rollouts, final EMA ckpt); read
the tab for current numbers, not this file.
