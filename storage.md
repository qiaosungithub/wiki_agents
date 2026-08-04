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
- **A missing CNS quota record is not a write block, and it is not headroom
  either.** Writes can succeed in a cell where the quota tool reports no such
  user — but that reply means *no usage has been recorded yet*, not *no
  ceiling*. Unknown users fall through to a shared default bucket, so a
  never-written-to cell already has the standard per-user limit in force; the
  record merely becomes visible on the first write. Treat an absent record as
  the default ceiling, never as unlimited. A missing record does still suggest
  no spindle commitment and therefore no performance floor, so measure
  throughput during the first large copy and give the job its own floor, armed
  only after startup, so a collapse stops it instead of grinding for hours.
- **A job's own logs may be unreadable from a workstation.** Both the task-log
  and the log-search CLI can fail on a restricted credential, so a copy whose
  only evidence is a log line is a copy you cannot verify. Write the evidence
  to the destination itself — a manifest and a completion marker outlive the
  task, the work unit, and the credential.

## The 500 GiB Ceiling Is The Wrong One — Charge The Group

**A personal CNS ceiling is 500 GiB per cell; the team's accounting group holds
PiB.** Any dataset worth staging exceeds the personal ceiling once replication
is counted, so the first question about a large copy is not "will it fit" but
"whose quota is it charged to". Charging the group removes the constraint
entirely and makes the encoding gymnastics in the next section optional rather
than load-bearing.

Set the accounting owner once, on the directory, and every file written beneath
it inherits it — including files written later by a job, so no training or copy
code changes:

```
fileutil chstat -R "quota_accounting{capacity_quota_user: '<mdb-group>'}" \
    /cns/<cell>-d/home/<user>
```

`chgrp -R <group>` achieves the same accounting via group ownership, but it also
grants the whole group read access. Prefer `chstat` when you only mean to move
the bill.

**Membership is cheaper to test than to look up.** The directory-lookup CLIs sit
behind a restricted-LOAS wall that a workstation credential does not clear, but
the filesystem answers directly and distinguishes three cases: a nonexistent
group fails with *not a valid ACL group*, a real group you do not belong to
fails with ***\<user\> is not a member of \<group\>***, and a group you can
charge to simply succeeds. So attempt the `chstat` on a scratch directory and
read the error — that is the membership check. Confirm it landed with
`fileutil stat`, which echoes the `quota_accounting` block; being able to *read*
a group's quota with `fileutil quota <group> <cell>` is not evidence of
membership.

**Membership is only the first of two gates. The second is whether the group
has a ceiling in that specific cell, and failing it is worse than not trying.**
A group you belong to but which has no flex registration in the destination cell
accounts to an entity with no quota, and the write dies with *"Group \<g\> has
no quota (partition=hdd)"* plus a **poisoned file handle** — strictly worse than
leaving the accounting alone. Two independent cells reproduced this.

The filesystem cannot tell you this in advance: `fileutil quota <group> <cell>`
reports a plausible-looking `500.00G` limit for an unregistered group, because
that is the default bucket it falls through to, not a real ceiling. **Only the
flex registry is authoritative:**

```
flex.par list_ceiling -p <pool> -s colossus -g <group> -l <cell>-d
```

No registration means no quota, whatever the filesystem says.

Quota lives in a three-level hierarchy — a parent pool, a team pool, then the
accounting group — and a cell can be missing at any level. When a whole metro
looks unusable, check whether the *team* pool is registered there before
concluding anything about your own group; a newly turned-up cell often has the
parent pool with PiBs free and simply no team beneath it.

Ceilings come as named size circles, and **the default circle carries zero
spindle commitment** — the condition behind a documented 12-hour throughput
collapse. Never accept the default on a cell you intend to read from in a loop.
Raising a circle is self-service only up to a policy limit; past that the tool
names the request process in its own error. **`--validate_only` runs the full
authorisation and policy check without mutating anything**, so probe with it
first — it is how to discover a permission boundary without filing anything.

Three things to keep in mind once it works:

- **Group quota is per cell and is not uniform.** A group can be near its
  ceiling in one cell and essentially empty in another, and can have no record
  at all in a third. Check the destination cell specifically before assuming
  headroom.
- **It is a shared pool with fair-usage expectations.** Staging a working slice
  is unremarkable; parking a full multi-TiB dataset indefinitely is not. Delete
  what the experiment no longer reads.
- **A raised ceiling reaches Colossus asynchronously.** The flex view updates at
  once; `fileutil quota` can still show the old number. Verify by writing, not
  by reading the quota back.

## Size A Copy In Disk Bytes, Not Payload Bytes

**The storage quota counts bytes after replication, so the encoding decides
whether a copy fits.** Default replication costs about 3x: a 199 GiB dataset
becomes ~600 GiB of disk against a 500 GiB per-user ceiling, and the copy dies
about four-fifths of the way in. Against a group ceiling the same arithmetic is
noise — fix the accounting owner first, then treat this section as an
efficiency question rather than a feasibility one. Reed-Solomon costs about
1.45x, fits comfortably, and tolerates *more* simultaneous chunk losses than 3-way
replication — cheaper and more durable, not a trade. Compute payload x
amplification against the ceiling as a fail-closed assert before the first
byte, and put the arithmetic in the abort message.

Four things make this bite harder than it looks:

- **Going over is not a clean stop.** The quota is checked on every stripe, so
  an over-quota write dies mid-file, leaving one truncated object that a
  size-only check may accept. Stage to a temporary name, verify size and
  checksum, and only then rename.
- **Going over poisons the cell for everything else you run.** The handle is
  sticky — retrying it never succeeds — and the block clears only minutes
  after usage actually drops. Human accounts get no soft-excess grace.
  Crucially, **reads keep working**, which is what makes a full cell
  recoverable: you can still copy the data out.
- **A copy call does not inherit the destination directory's encoding.** Name
  the encoding per file, then read it back — inheritance is invisible state
  that a re-run in a fresh directory silently loses.
- **Verify the encoding landed, rather than that you asked for it.** A cell
  may silently downgrade an encoding it cannot place, and the fallback is the
  expensive one. Pick from the user-facing recommended list; an encoding that
  appears only in the system's internal *stable* set is a downgrade target,
  not a menu option. Erasure coding also pads small files enormously — a
  ~9 KB file can occupy several MB — so it suits large shards, not a
  directory of sidecars.

## Deciding Whether Two Locations Are "Far Apart"

Locality has two different stakes and they need different rules. Getting the
distinction wrong is how a job either pays a surprise bill or silently runs at a
fraction of its throughput.

**Cost** applies only when one end is a GCS bucket in an externally-billed
project. It is a step function, not a gradient: same region is free, anything
else is billed. There is no "close enough" — see the section above.

**Latency** applies to internal-to-internal traffic (CNS to CNS, compute to
CNS), where nothing is billed and the question is only how slow. Here distance
really is a gradient, and some cells that look unrelated are in fact neighbours.

Resolve placement with `mach_locality -k <kind> <cell>`, which exposes a
hierarchy, not a single scalar:

| kind | example values | meaning |
|---|---|---|
| `cluster` | `yucmhcg`, `go` | the individual cell |
| `campus` | `clb`, `nby`, `pry` | a building/site; several per metro |
| `metro` | `cmh`, `tul`, `phx` | metropolitan area — the unit that maps to a GCP region |
| `continent` | `na`, `eu` | coarsest |

**Use `metro` as the primary decision boundary.** Cells sharing a metro are
close enough that cross-cell reads are effectively free, even across different
campuses — `go-d` (campus `nby`) and `yucmhcg-d` (campus `clb`) are both metro
`cmh` and behave as neighbours. Only `metro` has a defined mapping to a GCP
region, which is why the cost rule keys on it too.

**Do not try to measure cross-metro latency from a workstation.** The
workstation's own RTT to any cell dominates and hides the effect: probing three
cells in two metros from here returned 1457 / 1559 / 1536 ms, i.e. no signal at
all. The same trap appeared in an earlier incident investigation, where local
probes had to be discarded because the workstation was cross-metro from every
candidate. Measure from a job inside one of the metros, or reason from the
hierarchy instead.

**A real cross-metro copy is fast enough not to fear.** A same-metro CNS-to-CNS
copy of 199 GiB ran at 1338 MiB/s (152 s), roughly 8.6x a bigstore-to-CNS copy
of the same payload. Internal bandwidth is plentiful; the thing that kills a job
is not copy time but a training loop reading its data or writing its checkpoints
across a metro boundary for hours.

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
