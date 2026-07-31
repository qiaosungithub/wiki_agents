# EqR And EqR-jax

Read this for the `EqR` and `EqR-jax` checkouts. They are distinct PyTorch and
JAX implementations; inspect the target checkout's native docs and git state
before porting behavior. Read `xmanager.md` for all launches and job diagnosis.

## Data And Model Invariants

- `EqR-jax` maps configured dataset aliases in `data_util.py`; verify the live
  mapping for names such as `Maze-dynamic` and `Sudoku-aug1000` instead of
  rewriting paths in launch commands.
- The maze library's `grid_n=15` sample is `31 x 31`, while EqR consumes
  `30 x 30`. Preserve the existing top-left crop and path-length scaling unless
  the task explicitly changes the representation.
- Do not transfer checkpoint, logging, or runtime assumptions between the
  PyTorch and JAX implementations without checking both code paths.
- **Never sync a file from another checkout by copying it wholesale.** Re-apply
  the local change as a hunk on top of the other side's version instead. Whole-
  file "sync:" commits silently revert whatever the local side had added, and
  the loss is invisible because the file still imports and the tests still pass.
  This produced a dead config knob that survived eleven commits: `train.py` lost
  `_online_eval` while `default.py` and nine yamls kept setting
  `evaluation.online_eval`, so the config promised a D16/D64 curve and the code
  measured one point. When a knob looks suspicious, check that some module
  actually reads it (`grep -c` the reader, not the setter).

## Launch And Packaging

- Edit the unrestricted home checkout. `tpu queue` creates a unique CitC source
  snapshot, repoints the staged target, and packages that snapshot. Post-package
  edits to the home checkout do not affect the job.
- EqR-jax uses XManager service tiers (`PROD` or `BATCH`), not legacy
  `xm_priority`. Resource selection and allocator constraints are in
  `xmanager.md`.
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
of guessing (see `xmanager.md` §Debugging A Job That Dies With No Log):

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
  `spreadsheet.md` §Chart Links owns the URL forms and the
  `write_to_datatable=True` ACL trap. Two constraints specific to this code:
  only `process_index()==0` may construct a writer (the key is `(wid, step)` and
  all tasks of a work unit share one `wid`), and it must flush periodically —
  CLU's destructor cancels the writer thread instead of draining it.
- Every run that reaches a conclusion is logged to the `EqR-reproduction` tab
  with its chart link; see `spreadsheet.md`.
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
  by `xmanager.md` §Preemption, Restart, And Resume.
- Do not query the WandB API for EqR-jax unless current code proves that a real
  external WandB run was created.

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

### Online eval during training

`evaluation.online_eval` names the (depth, breadth) points the in-training eval
scores every `training.eval_interval_steps`; it defaults to `[16, 64]` at B=1.
Metrics arrive prefixed `D<depth>[B<breadth>]/`, and the first point is also
emitted unprefixed for backward compatibility. Set `online_eval: []` to restore
the old single-point behaviour. Each point rebuilds the module via `model_copy`
(a frozen dataclass cannot be re-depthed in place), so a point costs a recompile,
not a checkpoint reload.
