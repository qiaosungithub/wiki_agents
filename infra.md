# TPU And Unified Infra

`unified_infra` is the current system for queueing, dispatching, monitoring, and
resuming TPU jobs. Its repository and live state are the source of truth. The
old xibo manager and `MONITOR.py` are not current schedulers.

## Daily Interface

```bash
infra check
infra info <job_id>
infra logs <job_id> [-f]
infra logs <job_id> --what dispatch
infra queue --types=<types> --regions=<regions> -- <command>
infra debug --types=<type> --minutes=<n>
infra cancel <job_id>   # pending
infra kill <job_id>     # running or reserved
infra clean <job_id>    # terminal history
```

Read-only commands inspect shared state directly. Mutating commands go through
the central daemon and require the configured `INFRA_DAEMON_URL`. Useful shell
helpers already exist: `ics`, `ka`, `cl`, `gl`, `tl`, and `gest`.

## Mental Model

- The daemon is the only authoritative writer to `pool.json`, `jobs.json`, and
  `tpus.json` under `$INFRA_STATE_DIR`. Do not hand-edit these files.
- Queueing creates an immutable staged code snapshot. The same snapshot is used
  again after preemption, so an active job depends on its recorded `stage_dir`.
- A job id represents one logical chain. Infra failures requeue the same job;
  `nodes` record checkpoint progress and `dead_runs` retain terminated attempts.
- A checkpoint is valid only after the model checkpoint completion message. A
  started save or a dataloader sidecar message is not sufficient.
- Once a checkpoint exists, the chain is pinned to its checkpoint's TPU type and
  exact zone. Before that, it can use its original type and region allow-lists.
- Ready TPU signals feed one shared pool. A person's name in a TPU lease name is
  not ownership; the daemon may schedule any matching user's job onto that card.
- Infra shares reservation locks with legacy xibo. It owns `unified` locks and
  must treat other holders as foreign rather than expiring them.

## Queueing Policy

- Put run-defining parameters in the staged checkout's config files so the
  snapshot alone describes the experiment. `wandb_notes` is the intended CLI
  exception because it names the run.
- Queue from the exact branch and worktree the user intends. Staging captures
  current files, including uncommitted files allowed by the staging rules.
- Choose TPU types and regions explicitly from model memory needs and data or
  checkpoint locality. `laion-400m` work is restricted to its Asia-local copy;
  LLaVA-1.5 reproduction is v5-family work; large MAE plus large LM models may
  require v5p memory.
- Do not assume a scheduler can move checkpoints across zones. For eval-only
  work, either pin compute to an existing local checkpoint or deliberately make
  region-local copies before queueing.

## Failure Model

- Preemption, SSH, dispatch, lost-card, and hang failures normally auto-resume.
  Do not create a second job merely because the first attempt disappeared.
- A source-code bug or compile OOM is terminal and needs a code/config change
  followed by a fresh queue action. Secondary SSH errors can hide an earlier OOM,
  so inspect the full attempt log before accepting the final tail message.
- `infra info <id>` is the first diagnostic: it connects status, placement,
  stagedir, current output, dispatch output, checkpoints, and old attempts.
- Use `errors.log` and daemon status for control-plane or teardown failures. A
  control timeout can mean a busy daemon, not a dead daemon.
- `infrad restart` is intended to be non-disruptive to running job windows, but
  verify required daemon environment variables from the current repo docs.

## Cards And Zombies

`tou` is visibility, not authority. Before killing a supposed zombie, establish
all three: no active infra owner for the exact TPU, no owning tmux window, and a
real remote process still holding accelerator devices with a stale workdir/log.
Prefer user-scoped cleanup. Never infer ownership from `IDLE`, a cached audit, or
the remote Linux username alone.

Legacy helpers still useful for narrow tasks are `tou`, `detect_zombie`, `tpu
cc`, `tpu mount-disk`, and `tpu kill-remote`. Do not use legacy `tpu run`, `tpu
resume`, `tpu rerun`, `qsqa`, or old manager JSON to schedule current work.

## Hard Stops

- Never delete a stagedir referenced by a pending, running, or resumable chain.
- Never read or copy a large checkpoint/dataset across regions just to diagnose
  a job; logs and metadata should be enough for initial triage.
- Never kill a remote device holder until live ownership has been disproved.
- For implementation work, read `unified_infra/README.md`,
  `docs/resume_rules.md`, and `docs/robustness.md` rather than relying on archived
  incident descriptions.
