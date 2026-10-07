# Unified Infra Architecture And Deployment

Owns the scheduler model, deployment, resume interface, and failure limits.
For operating jobs, read [harness/skills/infra-operations/SKILL.md](../../harness/skills/infra-operations/SKILL.md).
Current repository code and live state outrank this knowledge. `unified_infra`
is the current scheduler; legacy xibo and `MONITOR.py` are not current schedulers.

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
- Whether a checkout reads these variables is [knowledge/codebases/vlm-training.md](../codebases/vlm-training.md#resume-enters-only-through-the-environment) §Resume enters only through the environment.

### How infra reads progress

**Infra finds completed saves by scanning the attempt's `output.log` for `saved
to` lines that carry a step, skips any line containing `pretrained`, and resumes
from the highest such step.** The line contract a trainer must follow is
[knowledge/codebases/vlm-training.md](../codebases/vlm-training.md#the-save-log-line-is-an-interface) §The save log line is an interface.

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
