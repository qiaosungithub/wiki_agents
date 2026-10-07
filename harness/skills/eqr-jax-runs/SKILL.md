---
name: eqr-jax-runs
description: Launch, triage, place, harvest, and keep the peak checkpoint of an EqR-jax sudoku or maze run, and run the RoboTwin Diffusion-Policy baseline and its A100 close-loop eval.
---

# EqR-jax Runs — Launching, Triaging, And Harvesting

This skill relies on [the EqR knowledge page](../../../knowledge/codebases/eqr-jax.md) for the
model, data, and loader invariants, the resolver and mirror tables, the logging
surface, what each metric key, divisor, and denominator means, the eval
protocol, maze and close-loop scoring, and the RoboTwin baseline facts. Read
[knowledge/codebases/eqr-jax.md §Loader and sampler state](../../../knowledge/codebases/eqr-jax.md#loader-and-sampler-state) before trusting a resume,
and [knowledge/codebases/eqr-jax.md §Eval protocol: report B=1 first](../../../knowledge/codebases/eqr-jax.md#eval-protocol-report-b1-first) before reporting
a result. Generic launches and job diagnosis are [knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md), placement is
[knowledge/infrastructure/storage.md](../../../knowledge/infrastructure/storage.md), and spreadsheet discipline is
[result-logging skill](../result-logging/SKILL.md). Rules here describe EqR-jax unless they name
the torch side.

## Launch and packaging

- **Edit the unrestricted home checkout, launch from a `/tmp` copy.** Packaging
  is a unique CitC snapshot, so post-package edits never reach the job, and
  several agents share the checkout ([knowledge/infrastructure/cluster-jobs.md §The launcher, config, and packaging](../../../knowledge/infrastructure/cluster-jobs.md#the-launcher-config-and-packaging)).
  `rsync -aL` the tree minus `.git`/`data`/`logs`, write the config there, then
  `tpu enqueue` *from* that copy: the default serial path ([knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md)), which
  records the copy as the entry `workdir`. `-aL` is required because
  `xm_launcher.py` is an absolute symlink and Bazel will not glob a package
  containing one. Delete the copy only *after* the build-worker has built it (`tpu
  queue-status` shows SUBMITTED) — a `workdir` that vanishes before its turn is
  parked HELD, not packaged.
- Write the run into `configs/remote_run_config.yml` and launch without a config
  argument ([knowledge/infrastructure/cluster-jobs.md §The launcher, config, and packaging](../../../knowledge/infrastructure/cluster-jobs.md#the-launcher-config-and-packaging)). EqR-jax consequence: `configs/`
  holds only templates (`local_debug`, `remote_run`, per-task); recover a
  finished experiment's config from its snapshot with `sexy <xid>`. Launching by
  config name leaves a file behind.
- EqR-jax uses XManager service tiers (`PROD` / `BATCH`), not legacy
  `xm_priority`; resource selection and allocator constraints are [knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md).
- Treat the active BUILD target and launcher as authoritative: entry point in
  `srcs`, other Python/config files as `data`, `testonly` deps excluded from the
  production target, configs resolved through runfiles. Keep ordinary local
  imports working through the entry point's execution-directory setup; do not
  rewrite them to a hard-coded google3 staging package.

## Dies before `main()`

Every trap below fails at module-import time, which on Borg means an empty
`status.message` and no log at all. **Reproduce locally in ~45s instead of
guessing** ([job-diagnose skill §Debugging A Job That Dies With No Log](../job-diagnose/SKILL.md#debugging-a-job-that-dies-with-no-log)).
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

## Add a compute cell, or pin a job to a partial mirror

**Adding a compute cell means mirroring the data and adding both entries**: one
in each resolver of [knowledge/codebases/eqr-jax.md §Data and checkpoint locality](../../../knowledge/codebases/eqr-jax.md#data-and-checkpoint-locality),
and the cell in all five mirror dicts. Since `las`/`dl-d` is partial, [storage-operations skill §Existence Is Not Completeness](../storage-operations/SKILL.md#existence-is-not-completeness)
bites: check `_MIRRORED`/`_SUCCESS` on `dl-d` before pinning a job there.

## Harvesting Final Train Metrics

[result-logging skill §Every Row Carries Its Train Metrics](../result-logging/SKILL.md#every-row-carries-its-train-metrics) owns *why*
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
   ([§Divisors and cadence](../../../knowledge/codebases/eqr-jax.md#divisors-and-cadence)). Field map to `EqR-refactored` columns: `lm_loss=` →
   `final train/lm_loss`; `acc=` → `final train/token_acc`; `exact=` →
   `final train/acc` (whole-board exact).
3. `extra.json` in the checkpoint dir confirms `step` / `total_steps` (proof the
   run finished) but carries no metrics.

Two traps the size sort avoids: rank count follows topology, not a fixed 8 (a
`v6p-32` maze run has 64 hosts, so jax process 0 can be `rank_33`; derive the
range, never hard-code `seq 0 7`); and the last attempt is often eval-only
(after the final preemption the run reloads `step_<budget>` and evaluates, so
the final training segment is in an *earlier* attempt).

## Checkpoint retention: keep the peak

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

## Running the RoboTwin DP baseline

The baseline's branch, files, and five fixed ablation tasks are
[knowledge/codebases/eqr-jax.md §Chapter 4 — The RoboTwin DP Baseline](../../../knowledge/codebases/eqr-jax.md#chapter-4--the-robotwin-dp-baseline); its dataloader
and train-loop invariants are
[the DP dataloader and train loop](../../../knowledge/codebases/eqr-jax.md#the-dp-dataloader-and-train-loop).

- The v7 minimum slice is 8 chips, though `tpu preflight v7-4` reports GREEN:
  the allocator's min-slice rule blocks v7-4 with no work unit created. Use
  `v7-8` for a single-host-class DP probe (2 hosts x 4 chips). yumrnel g9 PROD
  is the proven-hold cell; its co-located bucket is `/cns/qo-d`.
- **Per-task training cost varies ~4.3x** (`total_steps =
  floor(n_windows/128) * 600`, n_windows 5572 for `beat_block_hammer` to 23902
  for `open_microwave`). For an EQUAL-COST ablation, cap with
  `training.max_steps`, not a fixed `num_epochs`. Results log to the
  `RoboTwin-DP` tab of the EqR workbook
  (`17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`): one row per task, training
  metrics + close-loop `success_rate`.

## Close-loop eval on the A100 (SAPIEN)

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
  separately, [gcp-gpu-ssh skill](../gcp-gpu-ssh/SKILL.md)).
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
