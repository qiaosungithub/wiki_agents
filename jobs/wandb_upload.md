# Automatic W&B Upload From A Finished TPU Job

Owns the tpu-side automatic Weights & Biases upload: when one of the operator's
own `tpu`-launched training jobs finishes, a W&B run is created from the job's
Flatboard datatable using the job's own `config.wandb` identity — unattended.
The hub is `../jobs.md`; the npu/git-push twin and the poller that feeds it are
`../projects/remote_control.md`. Siblings: `submit.md`, `resume.md`,
`liveness.md`, `diagnose.md`, `report.md`; reading curves by hand is
`../research/result_logging.md`.

In one line: the datatables of every XID a finished tpu job ran under are
stitched into one W&B run of the id family `xid-<XID>`, using the identity the
launcher stashed in `~/.tpu_jobs.json`. The code is
`~/work/remote-control-pipeline/wandb-daemon/` (`tpu_daemon.py`, `uploader.py`,
`stitch.py`), `~/work/xid2wandb/xid2wandb/emit.py`, and
`~/work/tpu_cmd/xm_launcher.py` (the launcher half).

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
(`uploader._segment_images` + `discover_images`, per segment, keyed by step). Most tpu jobs
render no `viz/`, so discovery returns nothing and the rows pass through
untouched — a true no-op, not a special case.

### A re-upload replaces the run under a new id

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

### The first tick baselines the board

**On its very first tick the daemon marks every xid already on the board as
baselined and uploads none, so only jobs that FINISH AFTER it starts are ever
uploaded.** It therefore does not probe XManager for thousands of historical xids.
A registry entry with no `wandb` block is recorded as permanently skipped rather
than uploaded into the `remote-control` fallback project, which would be wrong
for a tpu run.

### Multi-XID runs automatically stitch their entire lineage chain

**When a job was preempted, rerouted across cells, or followed by a standalone
eval XID, `build_plan` traces the entire ancestor chain
`[xid_1, xid_2, ..., xid_final]` and merges every segment's datatable and `viz/`
images into one continuous `step 0 .. end` W&B run.** Cross-metro reroutes create
a new XID so `$CHECKPOINT_BUCKET` stays co-located with the new compute cell
(`resume.md`), which splits the Flatboard datatables into one
`/datatable/xid/<seg_xid>/data` per segment. Before uploading `xid_final`:

| Stage | Mechanism |
|---|---|
| 1. Lineage resolution | `xid2wandb.registry.resolve_xid_chain` walks backwards across `~/.tpu_local_queue.json` (`prior_xids`, `submissions`, `launch_kwargs`), archived `queue_row` blocks in `~/.tpu_jobs.json` + `~/.tpu_jobs_legacy.json`, shared `jobid:<ID>` tags in `xm_launch.log`, and XManager's `Launch command:` (`--load_from` / `--restart_from` / `--resume_xid`) to assemble the oldest-to-newest chain. |
| 2. Identity inheritance | `tpu_daemon.load_tpu_registry` merges live `~/.tpu_jobs.json` and `~/.tpu_jobs_legacy.json` (`tpu clear` archive). If `xid_final` lacks a `wandb` block or `stagedir`, the daemon inherits them from the closest ancestor in the resolved chain. |
| 3. Read EVERY segment | `uploader.read_chain_segments` reads each segment's physical datatable rows (uncollapsed, wall-clock order) and CNS `<bucket>/viz/`. No segment is skipped on a guess that a later one supersedes it. Only Flatfish NOT_FOUND counts as an empty segment; any other read failure aborts the upload for a retry next tick. |
| 4. Replay stitch | `stitch.stitch_segments` (pure, tested in `test_stitch.py`) replays all rows as one stream. A row carrying a training curve (a `train/*` key logged at 2+ steps) whose step is below the highest kept step is a restart: rows above it are the dead branch and are dropped. Eval rows and one-step constants overlay by step and never roll back, which is why a standalone eval XID or ELT's step-1 `train/num_params` does not rewind the run. Remaining step gaps are logged and written to the run config as `xm_stitch_gaps`. |
| 5. Replace and verify | `emit(replace=True)`, §A re-upload replaces the run under a new id. |

---

## Chapter 2 — Using It

### Prerequisite: the config must expose the unified `wandb` block

**At least one segment in the XID chain must carry
`config.wandb.{project,entity,notes,tags}` (the unified xm-run contract) or the
job is skipped.** The launcher copies that block into the registry at launch;
`notes` doubles as the XManager experiment name (`exp_name`). A repo that has
not migrated exposes no `wandb` block on any segment, so its jobs carry no
identity and the daemon records them as permanently skipped.

### Upload or repair one job now

**`python3 tpu_daemon.py --xid <XID>` forces one job through (including jobs
already `tpu clear`ed into `~/.tpu_jobs_legacy.json`), stitching its full
ancestor chain and overriding both the first-run baseline and the state file.**
For multi-XID runs, pass the final XID in the chain (`<XID_final>`); `tpu_daemon`
automatically discovers all predecessor segments across `~/.tpu_jobs.json` and
`~/.tpu_jobs_legacy.json` and writes the complete `step 0 .. end` curve into a
single W&B run. It prints the new run id on its `UPLOADED` line and records it in
the state file; the sheet side of a changed id is `../research/result_logging.md`
§The W&B Link Column. Add `--dry-run --verbose` to preview without touching W&B
or state. The dry run prints the resolved chain and the segments that held rows,
the project / name / notes, and the stitched step count and range. It also
prints the restarts it rolled back, any step gaps, and the metric keys.

### Check the daemon — never assume an upload happened

**The daemon dies or goes stale, so verify that each finished run reached W&B
with no hole anywhere in its curve.** A check that the first step is `<= 100`
passes a curve that lost a stretch in the middle. Compare the step count `--dry-run`
prints with the W&B run's stored step set (read it as Chapter 3 says), and treat
an `xm_stitch_gaps` key in the run config as a hole no datatable could fill. The
daemon is live when the last line of `logs/tpu_daemon.log` is a `tick done: ...`
under ~20 min old (it ticks every 900 s). `tmux has-session -t =wandb-upload-tpu`
confirms the session; keep the `=`, since a bare name prefix-matches
(`../workstation.md`). What was uploaded, and what was permanently skipped and
why, is in `state/tpu_uploaded.json` (`uploaded` and `skipped` maps, keyed by
xid). A run in neither map is merely not handled yet on a live daemon. On a dead
or stale daemon it needs a manual upload (§Upload or repair one job now).
Restart a dead daemon by re-running `~/bootstrap_daemons.sh`, which starts only
the missing sessions through `bash -lic` (`../workstation.md`).

### Re-upload after the daemon already handled a job

**Use `--xid <XID>`; it overrides state, so no file editing is needed.** This
covers a job the loop uploaded, baselined, or skipped. Deleting the WHOLE
`state/tpu_uploaded.json` does NOT re-upload everything — it clears the
`initialized` flag, so the next tick re-baselines the current board and uploads
nothing new.

---

## Chapter 3 — Bugs And Findings

**Non-obvious traps across W&B history ingestion, multi-XID splicing, and
datatable reads are handled in `stitch.py`, `uploader.py`, `emit.py`, and
`ffhttp.py`:**

| Symptom | Cause | Fix / Rule |
|---|---|---|
| A stitched curve is missing a stretch in the MIDDLE | Skipping a segment on the belief that a later one supersedes it; a middle segment can hold the only copy of some steps | Read and replay every segment (Stage 3). Audit by comparing a fresh stitch with the W&B step set, not by eye. |
| Early steps vanish, or the run disappears, when re-uploading over an existing run | W&B drops `run.log(step=s)` for `s <=` a resumed run's last step and tombstones deleted ids, so delete-then-recreate loses the run if the upload fails | `emit(replace=True)`: fresh id, verify, then delete the old run (§A re-upload replaces the run under a new id). |
| Standalone eval XID at tail of chain wipes the prior training curve | Its step (the final checkpoint's, or 1) was treated as a restart point | Only training-curve rows can roll back; eval rows overlay by step (Stage 4). |
| A re-upload lands in a different W&B project than the original | Identity followed the repo's CURRENT `default.py`, which can change after the first upload | `pin_identity_to_existing_run` keeps the entity/project of the state file's recorded URL. |
| Verification says a complete run is missing its FINAL step | `scan_history()` pages by step and can omit the last row (cache on or off); `history(samples=N)` downsamples when `N` < row count | Read the stored step set as the union of `history(samples>=rows)` and `scan_history(use_cache=False)`. |
| `wandb.Api().run.scan_history(keys=["_step"])` returns `0` rows on a populated run | W&B's `scan_history` omits rows when `_step` is queried without at least one real metric column | Never pass `keys=["_step"]`; read full rows (see the row above). |
| `tpu_daemon.py` or batch repair hangs indefinitely during datatable read | `ffhttp._curl` invokes `gosso` subprocesses that can block forever on transient corp SSO stalls | `ffhttp._curl` enforces `timeout=45` seconds with 2 retries per RPC. |
| Registry `status` stays at `SUBMITTED` forever for finished TPU jobs | Nothing reconciles `~/.tpu_jobs.json` back from the cluster | Always query XManager (`uploader.xm_status`), never the registry `status` field. |
| Images are missing on a job without CNS `viz/` | The datatable carries scalar columns only; `_segment_images` reads `<bucket>/viz/viz_<name>_step<N>.png` on CNS | Expected behavior: a job that writes no `viz/` gets a scalars-only run. |
| Pointing the npu daemon at a tpu XID fails to find identity | The tpu (`wandb-upload-tpu`) and npu (`wandb-upload`) daemons share `uploader.py` but use different identity sources | Always use `tpu_daemon.py` for TPU XIDs; the npu daemon takes the git-sha → `run_config.yml` path and cannot resolve TPU registry entries. |
