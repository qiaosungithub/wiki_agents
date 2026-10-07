---
name: vlm-debug
description: Validate VLM training, checkpoint, resume, or evaluation changes locally and with a small remote run before a real training job.
---

# Validate VLM Changes

Read the relevant contracts in [knowledge/codebases/vlm-training.md](../../../knowledge/codebases/vlm-training.md) and [knowledge/codebases/vlm-data.md](../../../knowledge/codebases/vlm-data.md) first.
This skill owns the local-then-remote drill and its command hazards.

## Chapter 1 — Running And Verifying A Change

### Name the concern before you test

**Identify which concern a change touches before testing it: model semantics,
mesh/batch semantics, data stream, checkpoint transaction, curriculum transition,
or final evaluation.** Test that concern with the smallest local or remote smoke
that exercises the real path, then inspect logs and produced state rather than
treating a clean process exit as proof.

### Run the debug drill before the real job

**Pass `local_debug.sh` and then one `debug_remote.sh` run before queueing the
real job; the drill and its hazards are described below.**

- A resume change needs a smoke that saves, stops, and resumes, because a run that never restarts never exercises the resume path. In `jax_llava`, `debug_remote_full_pipeline.sh` does this.
- A checkpoint change needs a run that restores the step it just saved and asserts that step, because a `saved to` line proves only that the save returned.

---

## Chapter 2 — Local Debug, Then Remote, Before A Real Run

**After any large code change, run the whole path locally, then one small remote
debug run on an idle card you own, and only then queue the real run.** A remote
round trip costs a staged snapshot, a queue wait, and a card, while a local run
costs minutes and catches most of what dies on the accelerator.

### Run the local debug runner first

**Run the checkout's `local_debug.sh` only from that checkout's root, because it
runs `sudo rm -rf` on a work directory built from the current directory.**

| What the VLM runner does | Detail |
|---|---|
| Clears state | `sudo rm -rf $WORKDIR` and `sudo rm -rf ./wandb`. `WORKDIR` is `$(pwd)/tmp/us-central1-local-debug`, except in `jax_llava`, where it is all of `$(pwd)/tmp` |
| Runs | `python main.py --config configs/load_config.py:local_debug` with `--mode local_debug`; `load_config.py:<mode>` reads `configs/<mode>_config.yml` |
| Picks the platform | `# export JAX_PLATFORMS=cpu` is commented out, so the runner uses whatever accelerator the machine has |

- To force CPU, set `JAX_PLATFORMS=cpu` before `import jax`, and add `XLA_FLAGS=--xla_force_host_platform_device_count=N` to simulate N devices in one process.
- The `local_debug` config should shrink steps, batch, and data but keep every stage the real config has. Read your checkout's copy before trusting that it does.
- Cover the side paths, not just the training step: logging, visualization, checkpoint save and restore, and online and offline eval. The bugs that appear only remotely live there.
- A single process cannot exercise a multi-host barrier, and a non-chief rank that skips a checkpoint save hangs rather than fails, so the remote run is the first place that shows it.
- Give any distributed path a timeout, because a deadlock produces no traceback.
- Judge the run by a token it prints only on success, not by the status of a pipe or a wrapper; a timeout kills the wrapper, not the child.

### Then one small remote debug run

**Once the local run is green, run `debug_remote.sh <vm> [zone]` from the checkout
root, once, on an idle card you own.** It catches what a CPU cannot see: real
device topology, cross-host collectives, and the staged code path. The VLM
checkouts share one script:

| Step | What it runs |
|---|---|
| Locate | `source config.sh`, then `source ka.sh` for `VM_NAME` and `ZONE` |
| Stage | `sudo rm -rf $STAGEDIR/*`, then an `rsync` of the checkout into `STAGEDIR=/$DATA_ROOT/staging/$(whoami)/debug-$VM_NAME-$ZONE`, excluding `tmp`, `.git`, `__pycache__`, `*.png`, `wandb`, `big_vision`, and `gemma` |
| Clear logs | `gsutil -m rm -r ${GCS_LOGDIR}` on `gs://${BUCKET}/qiao_zhicheng_hanhong_files/debug-${VM_NAME}-${ZONE}/log` |
| Clear the card | `pgrep -f '[m]ain.py' \| xargs -r sudo kill -9`, then `sudo rm -rf /tmp/tpu_logs` |
| Run | `main.py` on every worker with `--config=configs/load_config.py:${config_name}`, `WANDB_MODE=disabled`, and `/kmh-nfs-ssd-us-mount/code/hanhong/shared` prepended to `PYTHONPATH` |
| Judge | Each worker prints `__REMOTE_EXIT_STATUS__:<status>`; then `check_dataloader_state 3` counts dataloader state files, and the script prints `Remote debug three-stage smoke passed.` |

- It kills every user's `main.py` on the VM, so never point it at a card that runs someone else's job.
- Its verdict fails on any nonzero status but needs only one worker to print `:0`, so a worker that printed nothing still passes. Read each worker's status line yourself.
- `check_dataloader_state 3` is hard-coded for a three-stage `remote_debug` config. In `jax_llava`, run `debug_remote_full_pipeline.sh`, which runs `remote_debug_full_pipeline` fresh and then resumes it with `--config.load_from=${WORKDIR}`.

### Then the real run

**Queue the real run through `infra` only after both debug runs are green
([harness/skills/infra-operations/SKILL.md](../infra-operations/SKILL.md)).** To hold a card for interactive debugging instead,
`infra debug --types=<type> --minutes=<n>` reserves one.
