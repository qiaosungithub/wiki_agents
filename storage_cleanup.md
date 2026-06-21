# Storage Cleanup

Use this guide for disk pressure that can break TPU tooling. There are two very
different cleanup targets:

- Shared NFS/SSD: `/kmh-nfs-ssd-us-mount`, where logs, staging snapshots, data,
  and code checkouts live.
- Local root/home disk: `/`, `/home/sqa`, and `/tmp` on the orchestrator VM,
  where Codex logs, tool caches, and monitor temp files live.

Always identify which filesystem is full before deleting anything:

```bash
df -h / /tmp /home /kmh-nfs-ssd-us-mount
```

## Shared NFS/SSD

The shared SSD is mounted at `/kmh-nfs-ssd-us-mount` (NFS). When it gets close to
full, first check overall usage and then the big top-level dirs:

```bash
df -h /kmh-nfs-ssd-us-mount
du -sh /kmh-nfs-ssd-us-mount/*/ 2>/dev/null | sort -rh | head
```

`du` over NFS is slow, especially `code/` (conda envs) — run the per-dir measurements
as separate parallel background jobs instead of one sequential `du`. You may use
`sudo` to inspect or remove other users' files when reclaiming space.

The three usual offenders:

1. **`logs/`** — usually big for two reasons:
   - Someone saved **checkpoints** to the SSD instead of GCS. These should be
     uploaded to the corresponding bucket path, then removed from the SSD.
   - Many **`wandb/` folders** accumulate and bloat logs. These `wandb/` folders can
     be deleted directly.
   - (Also watch for large JAX `profile/` trace dirs inside run dirs; a single
     profiled run can be 10G+. They are safe to delete once not needed.)
2. **`code/`** — check who is big. A large conda/`anaconda3` env is normal and
   expected, but people sometimes leave inexplicably huge `tmp/` or `debug/` dirs
   in their checkout; inspect and clean those.
3. **`staging/`** — normally small. If it is large, someone accidentally copied a
   big file into their code each time they staged, so the large file is duplicated
   across many staging copies. Track down the oversized file and stop it from being
   copied. Staging snapshots live at `staging/<user>/<timestamp>-<hash>-code/`. To
   find the offending big file, inspect one snapshot: `du -sh <snapshot>/* | sort -rh`.
   **Important under unified_infra:** a job re-dispatches from its recorded
   `stage_dir` on every resume (it does **not** re-stage from the work dir). So a
   staging snapshot still referenced by an **active or resumable** job-chain must
   **not** be deleted, or resume fails with `cd … No such file or directory`. Only
   snapshots not referenced by any live `pool.json`/`jobs.json` job are safe to
   remove; prefer deleting the large *files* inside old snapshots (below) over whole
   dirs, and cross-check `gest <id>` / `infra info <id>` (which lists each chain's
   `stage_dir` and its `nodes`/`dead_runs` stage_dirs) before mass-deleting.

Practical notes from a 2026-06-08 cleanup:
- The SSD had `staging/` at ~987G (the biggest abnormal consumer), `code/` ~929G
  (mostly normal conda envs, evenly spread across users), `data/` ~647G, and
  `logs/` ~226G.
- `du` and especially `rm -rf` over this NFS mount are very slow: deleting one 30G
  snapshot made of many tiny files took ~14 minutes. Prefer targeting the few large
  snapshots (`find <dir> -type f -size +100M`) over blindly `rm -rf`-ing tens of
  thousands of small snapshot dirs. Run `du`/`rm` as background jobs and poll.
- The fastest, safest staging cleanup is to delete the large *files* (not whole
  snapshot dirs): real source code is never >50M, so any file above that threshold in
  a `-code` staging snapshot is accidental junk (checkpoints, logs, datasets, model
  weights). Build a manifest first as a record, then delete from it:
  ```bash
  sudo find /kmh-nfs-ssd-us-mount/staging -type f -size +50M -printf '%s\t%p\n' \
    2>/dev/null > /tmp/staging_large_files.txt
  cut -f2- /tmp/staging_large_files.txt | sudo xargs -d '\n' rm -f
  ```
  Deleting ~1448 large files this way took only ~20s (vs hours for whole dirs),
  because it is a small number of unlinks. Always keep a copy of the manifest (e.g.
  under `tpu_manager/staging_large_files_deleted_<ts>.txt`) so there is a record of
  exactly what was removed.
- On 2026-06-09 this freed ~564GB and took the SSD from 87% to 70% full. The deleted
  large files were dominated by `.pth` (148G), orbax checkpoint shards (126G),
  `.msgpack` (105G), `.log` (85G), plus `.npz`/`.pkl`/`.wandb`/`.pt`, repeated
  `Miniconda3-latest-Linux-x86_64.sh` installers, etc. — all confirmed non-source.
- Concrete staging offenders seen: `staging/sqa` had ~300 snapshots each carrying a
  328M `resources/checkpoints` copy, plus one 30G snapshot that had accidentally
  captured a whole home/dev environment (`.codex/*.sqlite-wal`, HuggingFace
  `refcoco` datasets, `.npm-global`, `.cache/ms-playwright`). Other users' staging
  was far larger (`chris` 248G, `zky` 214G); cleaning those needs sudo / their okay.
- In `logs/`, the biggest run dirs were dominated by JAX `profile/` trace dirs
  (10G+ each), not checkpoints or `wandb/`. Those profile traces are safe to delete
  once not needed.

## Local Root/Home Disk

The local root filesystem can fill independently of the shared NFS mount. On the
infra host this can break the daemon's dispatch workers before a TPU job even
starts. Symptoms include:

- `df -h /` shows 100%.
- Dispatch workers fail with `No space left on device` (see a job's dispatch log
  via `infra info <id>` / `errors.log` category `dispatch_failed`).
- gcloud commands (mount/zhan/ssh) fail before the job reaches RUNNING.

Do not start with a full recursive `du -sh /` unless you are prepared to wait.
Prefer targeted local-only checks:

```bash
df -h / /tmp /home
du -sh /home/sqa/.cache /home/sqa/.local /home/sqa/.config /home/sqa/.codex /tmp 2>/dev/null
find /home/sqa -xdev -maxdepth 4 -type f -size +200M -printf '%s %p\n' 2>/dev/null | sort -n | tail -40
du -h -d1 /tmp 2>/dev/null | sort -h | tail -30
```

If a broad local scan is accidentally started and hangs, kill only that diagnostic
process, not training or monitor processes:

```bash
pgrep -af 'du -h -x -d1 /|find / -xdev'
kill <diagnostic_pid>
```

### Codex SQLite WAL Cleanup

On 2026-06-13, `/home/sqa/.codex/logs_2.sqlite-wal` grew to 29GB and filled `/`.
This is a local Codex log WAL file, not model data. The safe cleanup sequence is:

1. Check whether anything has the database open:

   ```bash
   lsof /home/sqa/.codex/logs_2.sqlite /home/sqa/.codex/logs_2.sqlite-wal \
     /home/sqa/.codex/logs_2.sqlite-shm 2>/dev/null || true
   ```

2. Use Python's stdlib sqlite module to checkpoint and verify the DB. The machine
   may not have the `sqlite3` CLI installed.

   ```bash
   python - <<'PY'
   import sqlite3, os
   path = '/home/sqa/.codex/logs_2.sqlite'
   conn = sqlite3.connect(path, timeout=30, isolation_level=None)
   print('integrity', conn.execute('PRAGMA integrity_check').fetchone())
   print('passive', conn.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchall())
   print('restart', conn.execute('PRAGMA wal_checkpoint(RESTART)').fetchall())
   print('truncate', conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchall())
   conn.close()
   print('wal_size', os.path.getsize(path + '-wal'))
   PY
   ```

3. Interpret the checkpoint output before deleting or truncating anything.
   SQLite returns rows like `(busy, log_frames, checkpointed_frames)`.
   If `checkpointed_frames == log_frames` and `integrity_check` is `ok`, the WAL
   content has already been written back to the main DB. If `busy` is still `1`,
   another Codex/agent process may be keeping WAL mode open.

4. If the WAL remains huge after a complete checkpoint, truncate only the WAL file
   and immediately re-run integrity/df checks:

   ```bash
   truncate -s 0 /home/sqa/.codex/logs_2.sqlite-wal
   python - <<'PY'
   import sqlite3
   conn = sqlite3.connect('/home/sqa/.codex/logs_2.sqlite', timeout=10)
   print(conn.execute('PRAGMA integrity_check').fetchone())
   conn.close()
   PY
   df -h /
   ```

Do not remove the main `logs_2.sqlite` database unless the user explicitly asks.
Do not kill unrelated Codex/agent sessions just to release the WAL; checkpoint,
verify, and truncate the WAL is the lower-risk recovery when the root disk is
already full.

### Infra Daemon / Worker Temp Cleanup

`unified_infra` keeps its working state under `$INFRA_STATE_DIR`
(`unified_infra/state/`), not in `/tmp`: dispatch workers log to `worker_logs/`,
mount locks live in `mount_locks/`, and hard failures go to `errors.log`. These are
small and self-managed; do not hand-delete them while the daemon is running. If the
infra host's `/` fills, the usual culprit is still Codex WAL / tool caches under
`/home/sqa` (above), not infra state.

If gcloud sqlite-lock or config races appear, the daemon's workers isolate their
gcloud config per worker; let the daemon recycle them rather than clearing files
under a running worker. Check `infrad status` and `errors.log` first.

Do not clear arbitrary `/tmp` training state while jobs are running. On the TPU VMs
themselves, only an explicit all-user kill path (legacy `tpu kill-remote <tpu>` with
no `remote_user=`) is allowed to clean global `/tmp` TPU state — per-job remote
Linux-user state is otherwise isolated and should not be wiped.
