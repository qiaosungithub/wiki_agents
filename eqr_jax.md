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

## Experiment Tracking

- Config fields may retain historical `wandb` names, but EqR-jax uses a local
  compatibility layer that routes metrics to TensorBoard/XManager. It does not
  require `WANDB_API_KEY`.
- `wandb.log()`-style calls become TensorBoard scalars in the XManager workdir.
  Notes and names are persisted with the staged configuration metadata rather
  than an external WandB run.
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
