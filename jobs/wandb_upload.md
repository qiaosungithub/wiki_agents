# Automatic W&B Upload From A Finished TPU Job

Owns the tpu-side automatic Weights & Biases upload: when one of the operator's
own `tpu`-launched training jobs finishes, a W&B run is created from the job's
Flatboard datatable using the job's own `config.wandb` identity — unattended.
The hub is `../jobs.md`; the npu/git-push twin and the poller that feeds it are
`../projects/remote_control.md`. Siblings: `submit.md`, `resume.md`,
`liveness.md`, `diagnose.md`, `report.md`; reading curves by hand is
`../research/result_logging.md`.

In one line: a finished tpu job's datatable is replayed into a W&B run named
`xid-<XID>`, using the identity the launcher stashed in `~/.tpu_jobs.json`. The
code is `~/work/remote-control-pipeline/wandb-daemon/` (`tpu_daemon.py` +
`uploader.py`) and `~/work/tpu_cmd/xm_launcher.py` (the launcher half).

---

## Chapter 1 — How It Works

### On-Borg jobs never reach W&B, so the run is rebuilt offline from the datatable

**A training job on Borg cannot talk to W&B, so its curves are reconstructed
after it finishes from the Flatboard datatable it wrote instead.** Every xm-run
repo builds against a wandb *mock* (`//third_party/py/scamper:wandb_mock` and its
per-repo equivalents) whose `init`/`log`/`finish` are pure no-ops, so nothing a
job calls on `wandb` ever leaves Borg. The scalars survive by a separate path:
the job writes them to its datatable at `/datatable/xid/<XID>/data` through
`clu.metric_writers` (JAX) or the torch `DatatableSink`, keyed by `(wid, step)`.
This daemon reads that datatable back and replays it into a genuine W&B run.
Reading the datatable is codebase-agnostic — no training code emits a special
log line, and no per-repo log format has to be unified.

### Identity comes from the registry on tpu, from a frozen config on npu

**The tpu side has no config dump on CNS, so the launcher serializes
`config.wandb.*` into the job registry at launch and the daemon reads it back by
xid.** `xm_launcher._wandb_identity_from_cfg` copies `project`, `entity`,
`notes`, `run_name`, and `tags` into the `"wandb"` field of the job's
`~/.tpu_jobs.json` entry. The daemon passes that block to `build_plan` as
`wandb_override`, which skips the git-sha lookup entirely. The two sides diverge
only here:

| Side | Board / registry | Identity source | Terminal-state signal | tmux session | State file |
|---|---|---|---|---|---|
| tpu | `~/.tpu_jobs.json` | `config.wandb.*` recorded in the registry at launch | XManager `get_experiment` (registry never advances) | `wandb-upload-tpu` | `state/tpu_uploaded.json` |
| npu | `~/lyy-work/.npu_jobs.json` | git sha → frozen `runs/<sha>/run_config.yml` | the registry `status` field (reconciled on the npu side) | `wandb-upload` | `state/uploaded.json` |

### XManager is the completion authority, never the registry status

**The tpu registry never advances past `SUBMITTED` — nothing reconciles it — so
the daemon asks XManager directly for ground truth.** `uploader.xm_status` runs
`xmanager_tool get_experiment` and parses the `Status:` line plus the
`Work units (N total, M COMPLETED)` line; it reads neither the registry `status`
nor the rotating `~/.tpu_local_queue.json`. The parsed state decides the job's
fate:

| XManager says | Daemon does |
|---|---|
| finished, ≥1 work unit COMPLETED | upload (replay datatable → W&B run) |
| finished, 0 COMPLETED | record permanently skipped (a failed run) |
| still RUNNING, or not visible yet | leave it for the next tick |
| registry entry has no `wandb` block | record permanently skipped — never guessed into a fallback project |

### Curves come from the datatable; images from the job's CNS `viz/`

**Scalars are read over SSO from the datatable, and rendered boards are folded
in from the job's CNS `viz/` directory.** The workstation cannot reach the
datatable over Stubby (restricted LOAS) but can over the same UberProxy SSO the
Flatboard web UI uses — `ffhttp.py` replays that HTTP call via `gosso`. The tpu
daemon also uploads any rendered boards at CNS `<bucket>/viz/viz_<name>_step<N>.png`
(`_attach_images` + `discover_images`, keyed onto rows by step). Most tpu jobs
render no `viz/`, so discovery returns nothing and the rows pass through
untouched — a true no-op, not a special case.

### Re-uploads update the same run, and the first tick baselines the board

**The run id is `xid-<XID>` with `resume="allow"`, so re-running the daemon
UPDATES a job's run instead of forking a second one** — true even if the state
file is lost. On its very first tick the daemon marks every xid already on the
board as baselined and uploads none, so only jobs that FINISH AFTER it starts are
ever uploaded (and it does not probe XManager for thousands of historical xids).
A registry entry with no `wandb` block is recorded as permanently skipped rather
than uploaded into the `remote-control` fallback project, which would be wrong
for a tpu run.

---

## Chapter 2 — Using It

### Prerequisite: the config must expose the unified `wandb` block

**The training repo's config must carry `config.wandb.{project,entity,notes,tags}`
(the unified xm-run contract) or its jobs are skipped.** The launcher copies that
block into the registry at launch; `notes` doubles as the XManager experiment
name (`exp_name`). A repo that has not migrated exposes no `wandb` block, so its
jobs carry no identity and the daemon records them as permanently skipped.

### Upload or repair one job now

**`python3 tpu_daemon.py --xid <XID>` forces one job through, overriding both the
first-run baseline and the state file.** Re-upload is idempotent (run_id
`xid-<XID>`, `resume="allow"`), so this is the repair path for a job that was
baselined, already uploaded, or previously skipped — no need to hand-edit state
first. Preview without touching W&B or state by adding `--dry-run --verbose`;
the dry run prints the resolved project / name / notes, the step range, and the
metric keys it would write. `--xid` still requires a `wandb` block in the
registry entry; it cannot supply identity for an old job that has none.

### Check the daemon

**`tmux attach -t wandb-upload-tpu`, or `tail -f logs/tpu_daemon.log`.** The
resident loop runs `python3 tpu_daemon.py --once` every 900s. What has been
uploaded, and what was permanently skipped and why, is in
`state/tpu_uploaded.json` (`uploaded` and `skipped` maps, keyed by xid).

### Re-upload after the daemon already handled a job

**Use `--xid <XID>`; it overrides state, so no file editing is needed.** This
covers a job the loop uploaded, baselined, or skipped. Deleting the WHOLE
`state/tpu_uploaded.json` does NOT re-upload everything — it clears the
`initialized` flag, so the next tick re-baselines the current board and uploads
nothing new. There is no bulk re-upload; repair one xid at a time.

---

## Chapter 3 — Bugs And Findings

**Only jobs launched after the launcher began recording `wandb` carry an
identity.** Older `~/.tpu_jobs.json` entries have no `wandb` block and are skipped
by design — even `--xid` records them as permanently skipped. Re-launch such a
job under the current launcher to get a W&B run; there is no CLI path to inject
identity for a legacy entry.

**The registry `status` field is not a completion signal on the tpu side.**
Nothing reconciles `~/.tpu_jobs.json` back from the cluster, so every entry sits
at `SUBMITTED` forever, including long-finished ones. Trust XManager
(`xm_status`), never the registry status — that is the whole reason the tpu
daemon exists as a file separate from the npu one, which can trust its reconciled
registry.

**It is a separate daemon from the npu one.** They share `uploader.py` but have
separate registries, state files, and tmux sessions (see the Chapter 1 table), so
operating one never affects the other. Do not point the npu daemon at a tpu xid:
it would take the git-sha → `run_config.yml` path and find no identity.

**Images upload only from CNS `viz/`, not from the datatable.** The tpu daemon
passes `with_images=True`, so `_attach_images` folds in any
`<bucket>/viz/viz_<name>_step<N>.png` a job rendered. A job that writes no `viz/`
gets a scalars-only run — not an error, just nothing to attach. The datatable
carries no image columns, so it is never a fallback image source.
