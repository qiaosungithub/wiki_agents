---
name: infra-operations
description: Queue, inspect, resume, and clean up TPU jobs through unified infra; use for scheduler operations and job triage.
---

# Unified Infra Operations

Read [knowledge/infrastructure/unified-infra.md](../../../knowledge/infrastructure/unified-infra.md) for the scheduler and deployment
model before operating jobs. Trainer resume semantics are in [knowledge/codebases/vlm-training.md](../../../knowledge/codebases/vlm-training.md);
artifact integrity is in [harness/skills/storage-cleanup/SKILL.md](../storage-cleanup/SKILL.md).

## Chapter 1 — Queueing And Operating Jobs

### The daily interface

**Every client command goes through the daemon's private-network HTTP control
endpoint, so set `INFRA_DAEMON_URL` on every machine, including the daemon
host.**

```bash
infra check
infra info <job_id>
infra logs <job_id> [-f]
infra logs <job_id> --what dispatch
infra queue --types=<types> --regions=<regions> -- <command>
infra debug --types=<type> --minutes=<n>
infra cancel <job_id>   # pending
infra kill <job_id>     # running or reserved
infra clean <job_id>    # terminal history (bulk clean without a job id prompts to confirm)
```

- Useful shell helpers already exist: `ics`, `ka`, `cl`, `gl`, `tl`, and `gest`.
- "Clean up a job" means `infra clean` on a terminal chain, which forgets it from infra's records. `infra clean -n` previews without deleting.

### Queueing policy

**Put run-defining parameters in the staged checkout's config files so the
snapshot alone describes the experiment; `wandb_notes` is the intended CLI
exception because it names the run.**

- Before seeding a chain through the config's `load_from`, check how the checkout treats a config that disagrees with `LOAD_FROM`: `jax_llava` raises at the first resume that exports one ([knowledge/codebases/vlm-training.md](../../../knowledge/codebases/vlm-training.md#resume-enters-only-through-the-environment) §Resume enters only through the environment).
- Queue from the exact branch and worktree the user intends. Staging captures current files, including uncommitted files allowed by the staging rules.
- Choose TPU types and regions explicitly from model memory needs and data or checkpoint locality. `laion-400m` work is restricted to its Asia-local copy; LLaVA-1.5 reproduction is v5-family work; large MAE plus large LM models may require v5p memory.
- After queueing, read the job back from `pool.json` and check its `config_args`. A dropped `--config` arrives as `--config=None`, the job dies at start in a restart loop, and only a cancel and a fresh queue fix it.
- If `infra queue` is killed or times out, look for the job in `pool.json` before queueing again, because the daemon may already have accepted it.

### Checkpoint locality

**Before every launch, determine whether the job consumes a checkpoint, and make
an explicit locality decision before queueing.** Either pin compute to the
checkpoint's region, or *copy the checkpoint* into all possible regions with
suitable capacity. Please note that **cross-region copying is by default not allowed**. Cross region data transfer **costs money**. Only one-time, small amount copy is allowed, where copying one checkpoint is allowed.

- For eval-only work, you do not need to pin to the source region by default when compatible idle compute exists elsewhere.
- A copy plan must also cover any missing region-local eval data. Queue only after validating the checkpoint's completion marker and the copied object set, sizes, and checksums.

### Choosing a preemptible type

**Use a preemptible TPU type only when its launch time plus one checkpoint
interval is well below the median time a card survives in that zone, or the
chain restarts without saving progress.**

- Card lifetime differs by zone, so measure it for the zone you will use rather than assuming a type behaves the same everywhere.
- Google preemption appears in Cloud Audit Logs as `tpu.nodes.terminate`. Check there before blaming a local reaper (§Every actor that removes a job or card).

---

## Chapter 2 — Failures, Cards, And Hard Stops

### The failure model

**Preemption, SSH, dispatch, lost-card, and hang failures normally auto-resume,
so do not create a second job merely because the first attempt disappeared.**

- A job whose worker dies before the job starts running is always requeued. Among failures, only a code bug in a job that ran, or the resume cap, ends a chain.
- An attempt that exits with `rc==0` but whose log shows a launch-never-ran signature, and no sign that remote Python started, is recorded as failed and resumed.
- A source-code bug or compile OOM is terminal and needs a code/config change followed by a fresh queue action. Secondary SSH errors can hide an earlier OOM, so inspect the full attempt log before accepting the final tail message.
- `infra info <id>` is the first diagnostic: it connects status, placement, stagedir, current output, dispatch output, checkpoints, and old attempts.
- Use `errors.log` and daemon status for control-plane or teardown failures. A control timeout can mean a busy daemon, not a dead daemon.

### Every actor that removes a job or card

**Before blaming one component for a vanished job or card, list every actor that
can remove one and rule each out.**

| Actor | What it removes |
|---|---|
| Google preemption | A preemptible card, recorded as `tpu.nodes.terminate` in Cloud Audit Logs |
| The `request-manager` reclaim policy | Cards its policy reclaims, such as idle cards of a type outside its demand |
| The hang detector | A running job whose `output.log` stopped advancing (`INFRA_HANG_SECONDS`) |
| Infra teardown | Every process holding the card's accelerator devices, plus the login user's `python .*main.py` processes |

### Cards and zombies

**`tou` is visibility, not authority.** Before killing a supposed zombie, establish
every condition below.

- No active infra owner holds the exact TPU.
- No tmux window owns it.
- A real remote process still holds accelerator devices, and its workdir or log is stale.

Prefer user-scoped cleanup. Never infer ownership from `IDLE`, a cached audit, or
the remote Linux username alone.

- Act on a kill sweep only after a positive live confirmation for each card, because a stale listing can name a live job.
- Teardown kills only device holders and the login user's `main.py` processes, so a helper that holds no device and runs under another name survives it.
- Legacy helpers still useful for narrow tasks are `tou`, `detect_zombie`, `tpu cc`, `tpu mount-disk`, and `tpu kill-remote`.
- Do not use legacy `tpu run`, `tpu resume`, `tpu rerun`, `qsqa`, or old manager JSON to schedule current work.

### Hard stops

**Stop at each of these lines, because crossing one can destroy a live job, its
data, or shared state.**

- Never delete a stagedir referenced by a pending, running, or resumable chain.
- Never read or copy a large checkpoint/dataset across regions just to diagnose a job; logs and metadata should be enough for initial triage.
- Never kill a remote device holder until live ownership has been disproved.
- Never restart a shared infra service without asking the user first.
