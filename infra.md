# TPU And Unified Infra

Owns queueing, inspecting, resuming, and cleaning up TPU jobs through
`unified_infra`. Its repository and live state are the source of truth; the old
xibo manager and `MONITOR.py` are not current schedulers. The trainer's side of a
resume is `vlm_training.md` §The save log line is an interface and
`vlm_training.md` §Resume enters only through the environment. Disk space and
artifact completeness are `storage.md`.

Chapter 1 is how infra works; Chapter 2 is queueing and operating jobs; Chapter 3
is failures, cards, and hard stops.

---

## Chapter 1 — How Infra Works

### The mental model

**The daemon is the only authoritative writer of `pool.json`, `jobs.json`, and
`tpus.json` under `$INFRA_STATE_DIR`, so never hand-edit these files.**

- Queueing creates an immutable staged code snapshot. The same snapshot is used again after preemption, so an active job depends on its recorded `stage_dir`.
- A job id represents one logical chain. Infra failures requeue the same job; `nodes` record checkpoint progress and `dead_runs` retain terminated attempts.
- A checkpoint is valid only after the model checkpoint completion message. A started save or a dataloader sidecar message is not sufficient.
- Once a checkpoint exists, the chain is pinned to its checkpoint's TPU type and exact zone. Before that, it can use its original type and region allow-lists.
- Ready TPU signals feed one shared pool. A person's name in a TPU lease name is not ownership; the daemon may schedule any matching user's job onto that card.
- Infra shares reservation locks with legacy xibo. It owns `unified` locks and must treat other holders as foreign rather than expiring them.

### Services on the central host

**On the central host, systemd runs infra as `unified-infra-` services, so inspect
and restart them through `systemctl` and never start a second supervisor beside
them.**

| Service | Responsibility |
|---|---|
| `daemon` | Scheduling, job recovery, HTTP control on port 8765, the internal hot watcher, and the daily watchdog |
| `tpu-watcher` | Refreshes the shared TPU inventory used by scheduling and the dashboard |
| `request-manager` | Maintains TPU demand and the reclaim policy, and signals the daemon when cards arrive |
| `qr-keeper` | Maintains v5p queued-resource demand and signals ready cards into the shared pool |
| `webui` | The dashboard on port 8099 |

- Inspect them with `sudo systemctl status 'unified-infra-*'`. The daemon unit uses `KillMode=process`, so restarting it preserves job workers and tmux windows.
- Do not run `infrad start/stop/restart`, a legacy supervisor, or a manual loop alongside systemd; `bin/infrad status` remains safe. `infrad` is for hosts without systemd supervision.
- A healthy daemon keeps updating `state/daemon.health`, and a healthy watcher advances `code/qiao/work/tpu_dls/.tpu_audit_records.json` every audit cycle. An `active` watcher stuck at `Acquiring lock...` is not healthy.

### The deployed checkout

**The live CLI and services run from `/kmh-nfs-ssd-us-mount/code/infra/unified_infra`,
while `code/qiao/work/unified_infra` is a development clone, so first establish
which checkout a change landed in.**

- Live state is that checkout's `state/` directory, the `$INFRA_STATE_DIR` default, which also holds `errors.log` and each service's output, such as `daemon.out`.
- A running service keeps the code it loaded at start. After changing the deployed checkout, compare the unit's `ActiveEnterTimestamp` with the changed file's mtime before trusting the change.
- Ask the user before restarting a shared service. Then run `sudo systemctl restart unified-infra-<role>` and check the health signals in §Services on the central host again.
- For implementation work, read `unified_infra/README.md`, `docs/resume_rules.md`, and `docs/robustness.md` rather than relying on archived incident descriptions.

### How resume state reaches a job

**Infra hands resume state to a job only through environment variables that it
sets on every attempt.**

- Each attempt unsets `LOAD_FROM`, `LOAD_FROM_STEP`, `LOAD_FROM_DEVICES`, and `WANDB_RESUME_ID`, then exports `LOAD_FROM` only when the chain has a resume point and `WANDB_RESUME_ID` only when it has a run to resume.
- With `LOAD_FROM`, infra also exports, when known, `LOAD_FROM_STEP`, the step it parsed from the last `saved to` line, and `LOAD_FROM_DEVICES`, the JAX device count of the TPU type that wrote that checkpoint.
- A job record keeps the command but not the environment of the shell that ran `infra queue`, so a variable exported in that shell never reaches the job.
- Whether a checkout reads these variables is `vlm_training.md` §Resume enters only through the environment.

### How infra reads progress

**Infra finds completed saves by scanning the attempt's `output.log` for `saved
to` lines that carry a step, skips any line containing `pretrained`, and resumes
from the highest such step.** The line contract a trainer must follow is
`vlm_training.md` §The save log line is an interface.

- `infra check` shows one row per chain, with `RST` as restarts·lastCkptStep. A chain whose restarts climb while its last checkpoint step stays put is looping, not recovering.

### Limits that end or flag a chain

**These knobs, read from the daemon's environment, decide when infra kills,
resumes, gives up on, or flags a chain.**

| Knob | Default | Effect |
|---|---|---|
| `INFRA_HANG_SECONDS` | `60 * 60` | A running non-debug job whose `output.log` has not advanced this long is torn down, marked failed, and classified for resume, unless it was queued with `--no-liveness`, which requires `--max-runtime` |
| `INFRA_MAX_RESUME` | `100` | The cap on total restarts of the whole chain (`MAX_RESUME_ATTEMPTS`); at the cap infra gives up |
| `INFRA_WATCH_RESUME_STORM` | `max(3, config.MAX_RESUME_ATTEMPTS // 4)` | The watchdog lists a chain with this many restarts as a `resume_storm` anomaly and takes no action |
| `INFRA_RESUME_DEFAULT` | `resume` | What happens to a failure that matches no known signature; `code_bug` makes it terminal instead |

---

## Chapter 2 — Queueing And Operating Jobs

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

- Before seeding a chain through the config's `load_from`, check how the checkout treats a config that disagrees with `LOAD_FROM`: `jax_llava` raises at the first resume that exports one (`vlm_training.md` §Resume enters only through the environment).
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

## Chapter 3 — Failures, Cards, And Hard Stops

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
