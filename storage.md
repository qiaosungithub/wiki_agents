# Storage And Artifact Integrity

Owns reclaiming disk space safely and deciding whether an artifact or a copy is
complete. Stagedirs, infra state, and cross-region copy policy are `infra.md`; a
checkpoint's commit marker is `vlm_training.md` §Resume only from a committed
checkpoint; eval mirrors are `vlm_data.md`.

Chapter 1 is finding what is full and what must not be touched; Chapter 2 is
reclaiming space; Chapter 3 is artifacts and copies that look complete but are
not.

---

## Chapter 1 — What Is Full And What Must Not Be Touched

### Find the full filesystem first

**Identify which filesystem is full before deleting anything, because shared NFS
and the local host fill for different reasons and belong to different people.**

- Shared NFS is `/kmh-nfs-ssd-us-mount`; the local host is `/`, `/home`, and `/tmp`. Run `df` on the path that failed to confirm which one it is.
- Measure targeted directories before running broad recursive scans, and use `du -x` so a scan stays on one filesystem.
- A zero-byte file where data was expected is the signature of a full disk or quota, so rule that out before blaming the writer.

### What fills shared NFS

**Look first at the usual large consumers on shared NFS: checkpoints accidentally
written there, WandB caches, profiler traces, dependency environments, and junk
copied into many staged snapshots.** Prefer finding a small number of anomalously
large derived files over deleting whole snapshot trees containing many tiny files.

### What must not be touched

**Before deleting shared or local data, establish its filesystem, owner, active
references, and recovery path, because age and size say nothing about whether
data is disposable.**

- An infra job resumes from its recorded stagedir, so build the set of stagedirs referenced by pending, running, or resumable jobs before touching staging (`infra.md` §Hard stops).
- Do not assume another user's data is disposable merely because it is old or large. Establish ownership and authorization.
- Do not hand-delete live `unified_infra` state or arbitrary TPU `/tmp` contents while jobs are running.
- Check live command lines as well as `lsof` before deleting a file a job may use, because a job can open the file later. Write the pattern as `[m]ain.py` so `grep` does not match its own process.

---

## Chapter 2 — Reclaiming Space

### Bulk deletion keeps a manifest

**Preserve a path-and-size manifest for bulk cleanup, and upload and verify any
checkpoint that is meant to survive before deleting its NFS copy.**

- Detailed diagnostics and prior cleanup manifests are historical references in `archive/details/storage_cleanup.md`. Re-derive current paths and ownership before using any command from them.

### Local host pressure

**Check the local root disk when Codex, gcloud, or infra dispatch breaks, because
a full local root breaks them even when shared NFS has space.** Check caches,
`/tmp`, and large files under the affected user's home.

### A Codex WAL is checkpointed, never deleted

**Codex SQLite WAL files can become very large, and recovering the space must
keep the database intact.**

1. Check which process has the database open.
2. Run SQLite integrity checking and a WAL checkpoint.
3. Confirm frames were checkpointed before truncating a remaining oversized WAL.
4. Recheck database integrity and free space.

Never delete the main Codex SQLite database as routine cleanup, and do not kill
unrelated sessions solely to release a WAL.

### Checkpoint retention

**Keep the newest checkpoint, the one before it in case the newest is torn or
still being written, and a sparse ladder of older ones.**

- Never delete the newest committed checkpoint to free space.
- When a run keeps too many checkpoints, fix the retention in the writer instead of pruning behind it.

### Finish an interrupted move with rsync

**Finish an interrupted cross-filesystem `mv` with `rsync -a`, and delete the
source only after a dry run shows nothing left to copy.**

```bash
rsync -a <src>/ <dst>/
rsync -a --checksum --dry-run --itemize-changes <src>/ <dst>/
```

- An interrupted `mv` can leave the file it was copying truncated at the destination. `--ignore-existing` would skip that file, while the default size-and-time check copies it again.
- The second command must list no file transfers, which are the lines starting with `>f`.
- Do not compare the two trees with `du`, because two filesystems account blocks differently.

---

## Chapter 3 — Artifacts And Copies That Look Complete

### Existence is not completeness

**Decide that an output is complete from its size and a completion marker, never
from its presence, because a distributed write is not atomic.**

- Write the completion marker last, under a temporary name renamed into place, so a reader never sees a partial marker.
- Use one completion predicate in every stage and every reader, because two predicates drift and then disagree about the same file.
- Judge completeness against the producer's own manifest, not a listing count, and never while a writer is still running.
- Fail conservatively: a partial listing may undercount finished work, but must never mark missing work done.

### A verifier must be seen to fail

**Run a verifier on a known-bad input before trusting its pass, because a
verifier that compares the wrong field passes unconditionally, as
`"empty" == "empty"` does.** The general rule is `engineering.md` §A test that
cannot fail proves nothing.

- Scale a verification timeout with the batch size, because a fixed timeout truncates a large batch and the truncation then looks like missing data.

### One output path, one writer

**Stop every process that writes an output path before writing a large artifact
there, because a second writer silently overwrites or interleaves with the
first.**

- An output smaller than its expected bound points to a second writer, because appending never shrinks a file.
- The second writer can be an old job rescheduled hours later that resumes from a checkpoint its successor run produced. Watch the output path rather than the job list.
- A resume log that names a step produced by a different run is an alarm, not a recovery.

### Mirrors

**The destination's marker inventory is the only record of what a mirror landed,
because a driver's progress count records what it attempted.**

- Repair gaps with an idempotent driver that checks the destination marker for each item.
- Compare content, not only size, before publishing a mirror's completion marker. Skipping an item on resume may rely on size alone.
- Exclude non-payload files, such as probe files and destination-only markers, from checksum comparison.
- Recheck the source before relying on an old mirror, because the source can change after the mirror was verified.
- Verify a finished artifact by reading it back: headers, payload sizes, unique keys, and sampled shard boundaries. A marker proves only that the writer reached its end.

### The same name is not the same data

**Two datasets with the same name in different regions are copies only when their
shard sizes match, because a re-crawl changes the payload.** The regional cc12m
datasets, for example, are independent crawls rather than mirrors. When regional
copies must match, fan them out from one source.
