# Storage Cleanup

Disk cleanup is a data-safety task. First identify which filesystem is full.
Measure targeted directories before running broad recursive scans.

## Local Host

Local root pressure can break Codex, gcloud, and job dispatch. Check caches,
`/tmp`, and large files under the affected user's home without crossing
filesystem boundaries unnecessarily.

Codex SQLite WAL files can become very large. The recovery principle is:

1. Check which process has the database open.
2. Run SQLite integrity checking and a WAL checkpoint.
3. Confirm frames were checkpointed before truncating a remaining oversized WAL.
4. Recheck database integrity and free space.

Never delete the main Codex SQLite database as routine cleanup, and do not kill
unrelated sessions solely to release a WAL. Do not hand-delete live
job state or arbitrary `/tmp` contents while jobs are running.

Detailed diagnostics and prior cleanup manifests are historical references in
`archive/details/storage_cleanup.md`; re-derive current paths and ownership
before using any command from them.
