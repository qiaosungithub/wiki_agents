# Storage Cleanup

Disk cleanup is a data-safety task. First identify which filesystem is full:
shared NFS (`/kmh-nfs-ssd-us-mount`) or the local host (`/`, `/home`, `/tmp`).
Measure targeted directories before running broad recursive scans.

## Shared NFS

- Common large consumers are checkpoints accidentally written to NFS, WandB
  caches, profiler traces, dependency environments, and junk copied into many
  staged snapshots.
- An infra job resumes from its recorded stagedir. Build the set of stagedirs
  referenced by pending, running, or resumable jobs before touching staging.
- Prefer finding a small number of anomalously large derived files over deleting
  whole snapshot trees containing many tiny files.
- Preserve a path-and-size manifest for bulk cleanup. Upload and verify any
  checkpoint that is meant to survive before deleting its NFS copy.
- Do not assume another user's data is disposable merely because it is old or
  large. Establish ownership and authorization.

## Local Host

Local root pressure can break Codex, gcloud, and infra dispatch even when shared
NFS has space. Check caches, `/tmp`, and large files under the affected user's
home without crossing filesystem boundaries unnecessarily.

Codex SQLite WAL files can become very large. The recovery principle is:

1. Check which process has the database open.
2. Run SQLite integrity checking and a WAL checkpoint.
3. Confirm frames were checkpointed before truncating a remaining oversized WAL.
4. Recheck database integrity and free space.

Never delete the main Codex SQLite database as routine cleanup, and do not kill
unrelated sessions solely to release a WAL. Do not hand-delete live
`unified_infra` state or arbitrary TPU `/tmp` contents while jobs are running.

Detailed diagnostics and prior cleanup manifests are historical references in
`archive/details/storage_cleanup.md`; re-derive current paths and ownership
before using any command from them.
