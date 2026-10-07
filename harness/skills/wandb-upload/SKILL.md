---
name: wandb-upload
description: Force, repair, re-upload, or verify the automatic W&B upload of a finished tpu job (`tpu_daemon.py --xid`, the `wandb-upload-tpu` daemon), and match its known traps.
---

# Using The TPU W&B Upload

How the upload works — the datatable source, registry identity, XManager as
completion authority, the `xid-<XID>` id family, first-tick baselining, and the
multi-XID stitch — is
[knowledge/infrastructure/wandb-upload.md](../../../knowledge/infrastructure/wandb-upload.md).
This skill owns using, checking, and repairing it, and its bugs. The sheet side
of a changed run id is
[result-logging skill §The W&B Link Column](../result-logging/SKILL.md#the-wb-link-column); the npu twin is
[knowledge/codebases/remote-control.md](../../../knowledge/codebases/remote-control.md).

---

## Chapter 1 — Using It

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
the state file; the sheet side of a changed id is
[result-logging skill §The W&B Link Column](../result-logging/SKILL.md#the-wb-link-column). Add `--dry-run --verbose` to preview without touching W&B
or state. The dry run prints the resolved chain and the segments that held rows,
the project / name / notes, and the stitched step count and range. It also
prints the restarts it rolled back, any step gaps, and the metric keys.

### Check the daemon — never assume an upload happened

**The daemon dies or goes stale, so verify that each finished run reached W&B
with no hole anywhere in its curve.** A check that the first step is `<= 100`
passes a curve that lost a stretch in the middle. Compare the step count `--dry-run`
prints with the W&B run's stored step set (read it as Chapter 2 says), and treat
an `xm_stitch_gaps` key in the run config as a hole no datatable could fill. The
daemon is live when the last line of `logs/tpu_daemon.log` is a `tick done: ...`
under ~20 min old (it ticks every 900 s). `tmux has-session -t =wandb-upload-tpu`
confirms the session; keep the `=`, since a bare name prefix-matches
([knowledge/environment/workstation.md](../../../knowledge/environment/workstation.md)). What was uploaded, and what was permanently skipped and
why, is in `state/tpu_uploaded.json` (`uploaded` and `skipped` maps, keyed by
xid). A run in neither map is merely not handled yet on a live daemon. On a dead
or stale daemon it needs a manual upload (§Upload or repair one job now).
Restart a dead daemon by re-running `~/bootstrap_daemons.sh`, which starts only
the missing sessions through `bash -lic` ([knowledge/environment/workstation.md](../../../knowledge/environment/workstation.md)).

### Re-upload after the daemon already handled a job

**Use `--xid <XID>`; it overrides state, so no file editing is needed.** This
covers a job the loop uploaded, baselined, or skipped. Deleting the WHOLE
`state/tpu_uploaded.json` does NOT re-upload everything — it clears the
`initialized` flag, so the next tick re-baselines the current board and uploads
nothing new.

---

## Chapter 2 — Bugs And Findings

**Non-obvious traps across W&B history ingestion, multi-XID splicing, and
datatable reads are handled in `stitch.py`, `uploader.py`, `emit.py`, and
`ffhttp.py`:** "Stage N" below names a row of the stitch table in
[knowledge/infrastructure/wandb-upload.md §Multi-XID runs automatically stitch their entire lineage chain](../../../knowledge/infrastructure/wandb-upload.md#multi-xid-runs-automatically-stitch-their-entire-lineage-chain).

| Symptom | Cause | Fix / Rule |
|---|---|---|
| A stitched curve is missing a stretch in the MIDDLE | Skipping a segment on the belief that a later one supersedes it; a middle segment can hold the only copy of some steps | Read and replay every segment (Stage 3). Audit by comparing a fresh stitch with the W&B step set, not by eye. |
| Early steps vanish, or the run disappears, when re-uploading over an existing run | W&B drops `run.log(step=s)` for `s <=` a resumed run's last step and tombstones deleted ids, so delete-then-recreate loses the run if the upload fails | `emit(replace=True)`: fresh id, verify, then delete the old run ([§A re-upload replaces the run under a new id](../../../knowledge/infrastructure/wandb-upload.md#a-re-upload-replaces-the-run-under-a-new-id)). |
| Standalone eval XID at tail of chain wipes the prior training curve | Its step (the final checkpoint's, or 1) was treated as a restart point | Only training-curve rows can roll back; eval rows overlay by step (Stage 4). |
| A re-upload lands in a different W&B project than the original | Identity followed the repo's CURRENT `default.py`, which can change after the first upload | `pin_identity_to_existing_run` keeps the entity/project of the state file's recorded URL. |
| Verification says a complete run is missing its FINAL step | `scan_history()` pages by step and can omit the last row (cache on or off); `history(samples=N)` downsamples when `N` < row count | Read the stored step set as the union of `history(samples>=rows)` and `scan_history(use_cache=False)`. |
| `wandb.Api().run.scan_history(keys=["_step"])` returns `0` rows on a populated run | W&B's `scan_history` omits rows when `_step` is queried without at least one real metric column | Never pass `keys=["_step"]`; read full rows (see the row above). |
| `tpu_daemon.py` or batch repair hangs indefinitely during datatable read | `ffhttp._curl` invokes `gosso` subprocesses that can block forever on transient corp SSO stalls | `ffhttp._curl` enforces `timeout=45` seconds with 2 retries per RPC. |
| Registry `status` stays at `SUBMITTED` forever for finished TPU jobs | Nothing reconciles `~/.tpu_jobs.json` back from the cluster | Always query XManager (`uploader.xm_status`), never the registry `status` field. |
| Images are missing on a job without CNS `viz/` | The datatable carries scalar columns only; `_segment_images` reads `<bucket>/viz/viz_<name>_step<N>.png` on CNS | Expected behavior: a job that writes no `viz/` gets a scalars-only run. |
| Pointing the npu daemon at a tpu XID fails to find identity | The tpu (`wandb-upload-tpu`) and npu (`wandb-upload`) daemons share `uploader.py` but use different identity sources | Always use `tpu_daemon.py` for TPU XIDs; the npu daemon takes the git-sha → `run_config.yml` path and cannot resolve TPU registry entries. |
