# SSD Disk Cleanup


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
   copied. Staging snapshots live at `staging/<user>/<timestamp>-<hash>-code/`; old
   snapshots (more than a few days old) are safe to delete since the code has already
   been pushed to the TPU and resume re-stages from the work dir. To find the
   offending big file, inspect one snapshot: `du -sh <snapshot>/* | sort -rh`.

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

