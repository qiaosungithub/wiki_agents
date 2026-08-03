# Storage: Placement, Latency, And Cleanup

Read this before choosing where data or checkpoints live, before putting a
remote read on an interactive path, or before freeing disk. Project data
schemas live in `projects/`; this file owns placement and access.

## Placement Policy By Project Type

Classify the checkout in `projects/README.md` first.

| Category | Rule |
|---|---|
| Type 1: Kaiming Group code | Data, checkpoints, and compute stay in one region; match the zone too for zonal disks and local paths. Do not open or copy payloads across locations by default. Derive locality from current VM/job metadata and fail closed on a mismatch. |
| Type 2: Google internal research code | The Type 1 prohibition does not apply, but the scheduler may place work in several cells, so runtime data must be reachable from every eligible cell. A local VM path, persistent disk, or source checkout is not globally accessible runtime storage. |

For large Type 2 datasets consumed by globally scheduled jobs, prefer an
appropriate multi-region bucket, and verify the current project, identity, and
target before every write. Multi-region availability does not make a location
legal for Type 1 data.

## Co-Locate Compute With Storage, Or The Job Dies

Type 2 may run anywhere; it may not run **far from its data**. Distance is not
merely slow — a job whose accelerators sit idle waiting on remote checkpoint
writes falls below the platform's utilization threshold and gets **deleted by
the pruner**, mid-run, with no crash and no bug to find. This has happened here:
compute in Europe against storage in North America dropped throughput roughly
4-5x and the job was killed at half completion. Co-located, the same recipe
finished.

Practical rules:

- **The checkpoint library announces the mismatch at startup**, naming the
  compute cluster and the storage cluster with a continent for each. Read those
  lines before diagnosing anything else about a slow job.
- **Mirror the dataset into every compute metro you use** and select it at
  runtime from the cell, rather than pinning one global path. Research datasets
  are usually small enough to copy in under a minute.
- **The checkpoint destination matters more than the dataset**: the dataset is
  staged once, checkpoints are written for the life of the run.
- Low utilization is the symptom the pruner acts on, and its deletion message
  links the policy it applied. Read it rather than guessing.

## Copying From A Bucket Someone Else Pays For

When the source bucket belongs to an external GCP project, a cross-region read
is a bill, not a slowdown, and the person who pays is not the person who
launched the job. Same-region reads are free, so the entire safety property is
"prove both ends are in one region before the first byte moves".

**Assert both ends explicitly, as literal constants, fail-closed, before the
first open.** Two separate asserts, not one:

1. the **compute cell** equals the cell that was pinned at submit time, and
2. the **bucket's region** equals the region that cell lives in.

Asserting a metro *set* is not sufficient, and neither is asserting only one
end. The metro-to-region relation is indirect and invisible in a path string, so
a reschedule, a copy-pasted prefix, or an edited default can move one end while
the other still looks right. Two literal asserts fail loudly on exactly that.

The guard belongs **in the program**, not in the submit command or a reviewer's
memory: a launch flag can be dropped by the packaging path, and an operator
cannot re-check it on a restart. An unknown or unreadable cell must exit
non-zero before any read, the same as a wrong one.

Verify the region mapping from source rather than from memory or from an
assistant's answer: `production/borg/cloud_iam/slicer_regions/slicer_metros.pi`
maps metro to GCP region, and `mach_locality -k metro <cell>` resolves a cell to
its metro. Note that not every metro has a GCP region at all, so a cell can be
"near" nothing — the launcher's default checkpoint root is one of these, which
makes accepting the default a silent cross-region transfer.

**Assert the bucket's region by querying it, not by reading its name.** A stat
of the bucket root returns its location, and that is a metadata operation — it
moves no object bytes, so it is safe to issue *before* the region is proven and
is the only way to prove it from inside the job. A name is a weaker claim that
happens to be true; keep it as the fallback for when the metadata is
unreachable, and make the program say which of the two it used.

**Exercise the guard's failing branch, not just its passing one.** A guard
whose reject path has never run is trusted on faith: the happy path proves the
comparison finds equality, not that inequality stops anything. Give each assert
a test hook that substitutes a wrong value, and make the hook incapable of
relaxing the guard — it discards the real answer, so it can only ever abort.

Two related traps on the same path:

- **The default bigstore client sends no usable credential** and the server
  records the caller as anonymous, so a correctly-ACLed bucket still returns 403.
  The fix is the flag that reads as "anonymous" but means "send no credential in
  the request, so the ambient LOAS identity is used". Set it in-process. Without
  it, an access test reports a false negative and the real identity is never
  presented.
- **A missing CNS quota record is not a write block.** Writes can succeed in a
  cell where the quota tool reports no such user, but that likely means no
  spindle commitment and therefore no performance floor. Measure throughput
  during the first large copy instead of assuming it holds — and give the job
  its own floor, armed only after startup, so a collapse stops it instead of
  grinding for hours.
- **A job's own logs may be unreadable from a workstation.** Both the task-log
  and the log-search CLI can fail on a restricted credential, so a copy whose
  only evidence is a log line is a copy you cannot verify. Write the evidence
  to the destination itself — a manifest and a completion marker outlive the
  task, the work unit, and the credential.

## Before Touching A Payload

1. Resolve the exact category, payload, source, destination, and compute
   placement.
2. Inspect bounded metadata first — location, size, completion marker, manifest,
   checksums. Never read a large payload merely to discover where it is.
3. For Type 1, prove source and compute locality before access. A cross-location
   copy needs explicit authorization and a cost-aware, verified plan.
4. For Type 2, prove every eligible execution cell can reach the chosen runtime
   storage; pin cells when the data is intentionally regional.
5. Treat the copy as a transaction: write the smallest scope, validate object
   counts, sizes, checksums, and completion markers, then record the durable
   location in the project's source of truth.

**A replica is usable only when every physical root carries its verified
completion marker.** Visible shards without it are partial data, and a loader
that resolved its shard list at startup will not pick up shards that appear
later. Never infer completeness from a directory listing, and never record
mirror status in memory — re-verify live before scheduling.

## Distributed Reads On An Interactive Path

Applies to any status table, watch loop, or progress display that reads a
distributed filesystem. Measure before trusting any figure below; the shape of
the conclusion is what lasts.

- **Cost is round trips, not bytes.** A small read costs about the same as a
  large one, so seeking to the tail is worth doing mainly because the naive
  "read everything, slice the end" form grows with the file.
- **Never hide a per-file stat inside a sort key.** It forces the calls serial
  and is invisible in the source. This was the single largest cost in our own
  status tool.
- **Fan out with a thread pool.** The client releases the GIL, so this is real
  concurrency and worth roughly an order of magnitude. Reuse one module-level
  pool; building one per call costs more than the reads.
- **Distance is second-order; per-cell load dominates.** A local cell measured
  three times slower than a remote one here. Do not diagnose a slow read as a
  locality problem without measuring another cell.
- **A shell utility pays about a second of startup before it does anything**,
  plus first-connection setup. If you must shell out, batch every path into one
  invocation.
- **The in-process client wins only in a long-lived process.** Cold it is
  comparable to shelling out; hot it is dozens of times faster, and it stays hot
  across a minute of idle. A bash loop that re-execs a binary each round is a
  one-shot caller no matter how long the loop runs — put the read inside a
  resident process.
- **Always bound the wait.** A log tail is a nicety; a status table that blocks
  on it is a regression.

Two silent traps:

- **A pip/conda build of the path library cannot see the distributed
  filesystem and does not say so** — the open-source build strips the backend,
  so a remote path is treated as an ordinary POSIX path and `exists()` simply
  returns False. Only a build depending on the internal target has the real
  backend.
- **No file or RPC access before framework initialization completes.** Touching
  remote storage at module import time aborts the process. Do the work inside
  the entry point, never at module scope.

## Local Disk Cleanup

Disk cleanup is a data-safety task. Identify which filesystem is actually full
before measuring anything, and measure targeted directories before running broad
recursive scans. Local root pressure breaks agent CLIs, cloud tooling, and job
dispatch, so check caches, temporary directories, and large files under the
affected home without crossing filesystem boundaries unnecessarily.

For a database whose write-ahead log has grown large, the sequence is: find the
process holding it open, run an integrity check and a checkpoint, confirm frames
were actually checkpointed, only then truncate, and re-verify integrity and free
space afterwards. Never delete a live database as routine cleanup, never kill
unrelated sessions to release a lock, and never hand-delete job state or
temporary files while jobs are running.
