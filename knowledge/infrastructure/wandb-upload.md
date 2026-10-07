# Automatic W&B Upload From A Finished TPU Job

Owns how the tpu-side automatic Weights & Biases upload works: when one of the
operator's own `tpu`-launched training jobs finishes, a W&B run is created from
the job's Flatboard datatable using the job's own `config.wandb` identity —
unattended. Using, checking, and repairing it, and its known bugs, are the
[wandb-upload skill](../../harness/skills/wandb-upload/SKILL.md). Sibling pages:
[cluster-jobs.md](cluster-jobs.md) (queueing, placement, preemption) and
[resume-contracts.md](resume-contracts.md) (resume and the write path). The
npu/git-push twin and the poller that feeds it are
[knowledge/codebases/remote-control.md](../codebases/remote-control.md); reading curves by hand is
[result-logging skill](../../harness/skills/result-logging/SKILL.md).

In one line: the datatables of every XID a finished tpu job ran under are
stitched into one W&B run of the id family `xid-<XID>`, using the identity the
launcher stashed in `~/.tpu_jobs.json`. The code is
`~/work/remote-control-pipeline/wandb-daemon/` (`tpu_daemon.py`, `uploader.py`,
`stitch.py`), `~/work/xid2wandb/xid2wandb/emit.py`, and
`~/work/tpu_cmd/xm_launcher.py` (the launcher half).

## On-Borg jobs never reach W&B, so the run is rebuilt offline from the datatable

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

## Identity comes from the registry on tpu, from a frozen config on npu

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

## XManager is the completion authority, never the registry status

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

## Curves come from the datatable; images from the job's CNS `viz/`

**Scalars are read over SSO from the datatable, and rendered boards are folded
in from the job's CNS `viz/` directory.** The workstation cannot reach the
datatable over Stubby (restricted LOAS) but can over the same UberProxy SSO the
Flatboard web UI uses — `ffhttp.py` replays that HTTP call via `gosso`. The tpu
daemon also uploads any rendered boards at CNS `<bucket>/viz/viz_<name>_step<N>.png`
(`uploader._segment_images` + `discover_images`, per segment, keyed by step). Most tpu jobs
render no `viz/`, so discovery returns nothing and the rows pass through
untouched — a true no-op, not a special case.

## A re-upload replaces the run under a new id

**Every upload writes the whole curve to a never-used id of the family
`xid-<XID>`, `-full`, `-v2`, ..., so the current link is the one
`state/tpu_uploaded.json` records, never one built by hand.** W&B cannot rewrite
a run's history: a resumed run drops every step at or below its last one, rewind
works only where W&B has enabled it, and a deleted id is tombstoned forever. So
`emit(..., replace=True)` never touches an existing run. It creates the fresh
id, uploads, reads the history back until it equals the planned steps, and only
then deletes the family's older runs. A failure at any point deletes the
unverified new run and keeps the old one. A re-upload also stays in the
entity/project of the URL the state file already holds for the job. The identity
sources (registry block, repo `default.py`) can change after the first upload.

## The first tick baselines the board

**On its very first tick the daemon marks every xid already on the board as
baselined and uploads none, so only jobs that FINISH AFTER it starts are ever
uploaded.** It therefore does not probe XManager for thousands of historical xids.
A registry entry with no `wandb` block is recorded as permanently skipped rather
than uploaded into the `remote-control` fallback project, which would be wrong
for a tpu run.

## Multi-XID runs automatically stitch their entire lineage chain

**When a job was preempted, rerouted across cells, or followed by a standalone
eval XID, `build_plan` traces the entire ancestor chain
`[xid_1, xid_2, ..., xid_final]` and merges every segment's datatable and `viz/`
images into one continuous `step 0 .. end` W&B run.** Cross-metro reroutes create
a new XID so `$CHECKPOINT_BUCKET` stays co-located with the new compute cell
([knowledge/infrastructure/resume-contracts.md](resume-contracts.md)), which splits the Flatboard datatables into one
`/datatable/xid/<seg_xid>/data` per segment. Before uploading `xid_final`:

| Stage | Mechanism |
|---|---|
| 1. Lineage resolution | `xid2wandb.registry.resolve_xid_chain` walks backwards across `~/.tpu_local_queue.json` (`prior_xids`, `submissions`, `launch_kwargs`), archived `queue_row` blocks in `~/.tpu_jobs.json` + `~/.tpu_jobs_legacy.json`, shared `jobid:<ID>` tags in `xm_launch.log`, and XManager's `Launch command:` (`--load_from` / `--restart_from` / `--resume_xid`) to assemble the oldest-to-newest chain. |
| 2. Identity inheritance | `tpu_daemon.load_tpu_registry` merges live `~/.tpu_jobs.json` and `~/.tpu_jobs_legacy.json` (`tpu clear` archive). If `xid_final` lacks a `wandb` block or `stagedir`, the daemon inherits them from the closest ancestor in the resolved chain. |
| 3. Read EVERY segment | `uploader.read_chain_segments` reads each segment's physical datatable rows (uncollapsed, wall-clock order) and CNS `<bucket>/viz/`. No segment is skipped on a guess that a later one supersedes it. Only Flatfish NOT_FOUND counts as an empty segment; any other read failure aborts the upload for a retry next tick. |
| 4. Replay stitch | `stitch.stitch_segments` (pure, tested in `test_stitch.py`) replays all rows as one stream. A row carrying a training curve (a `train/*` key logged at 2+ steps) whose step is below the highest kept step is a restart: rows above it are the dead branch and are dropped. Eval rows and one-step constants overlay by step and never roll back, which is why a standalone eval XID or ELT's step-1 `train/num_params` does not rewind the run. Remaining step gaps are logged and written to the run config as `xm_stitch_gaps`. |
| 5. Replace and verify | `emit(replace=True)`, §A re-upload replaces the run under a new id. |
