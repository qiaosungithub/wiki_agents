# Storage: Placement, Latency, And Cleanup

Owns where data and checkpoints live, quota and accounting, copy sizing,
distributed-read latency, and safe cleanup. Job launching is `jobs.md`, chip
prices `infra/quota_market.md`, per-project data schemas `projects/`. Read before
choosing a location, before putting a remote read on an interactive path, and
before deleting anything.

## Placement Policy By Project Type

Classify the checkout in `projects/README.md` first.

| Category | Rule |
|---|---|
| Type 1: Kaiming Group code | Data, checkpoints, and compute stay in one region; match the zone too for zonal disks and local paths. Do not open or copy payloads across locations by default. Derive locality from current VM/job metadata and fail closed on a mismatch. |
| Type 2: Google internal research code | The Type 1 prohibition does not apply, but the scheduler may place work in several cells, so runtime data must be reachable from **every eligible cell**. A local VM path, persistent disk, or source checkout is not globally accessible runtime storage. |

For large Type 2 datasets consumed by globally scheduled jobs, prefer an
appropriate multi-region bucket, and verify the current project, identity, and
target before every write. Multi-region availability does not make a location
legal for Type 1 data.

## Co-Locate Compute With Storage, Or The Job Dies

**A job far from its data does not merely run slowly: its accelerators idle on
remote checkpoint writes, it drops below the platform's utilization threshold,
and the pruner deletes it mid-run** — no crash, no bug to find. Compute in
Europe against storage in North America lost 4-5x throughput here and was killed
at half completion.

| Rule | Why |
|---|---|
| Read the checkpoint library's startup lines before diagnosing a slow job | It names the compute cluster and the storage cluster, a continent each |
| Treat low utilization as the pruner's trigger | Its deletion message links the policy it applied; read it rather than guessing |
| Mirror the dataset into every compute metro, select it at runtime from the cell | Beats pinning one global path; research datasets usually copy in under a minute |
| Choose the checkpoint destination first — it matters more than the dataset | The dataset is staged once; checkpoints are written for the life of the run |

**When an accelerator has no storage next to it, move the compute before
requesting quota — and ask that question at `metro` granularity**: enumerate
every cell the accelerator lives in, join it against the accounting group's
registered cells by metro, and escalate only if the whole intersection is empty.
A generation is turned up cell by cell while storage registration lags, so the
narrow question (*does this exact cell have quota*) reports failure for
placements that are fine; a registration takes days, the sibling metro that
already works takes minutes to find. `research/v7_storage_placement.md` holds the
current survey and how to redo it.

## Deciding Whether Two Locations Are "Far Apart"

**Cost and latency are different stakes.** Cost applies only when one end is a
GCS bucket in an externally-billed project, and is a step function — same region
free, anything else billed, no "close enough" (§Copying From A Bucket Someone
Else Pays For). Latency applies to internal-to-internal traffic (CNS to CNS,
compute to CNS): unbilled, a gradient, and cells that look unrelated can be
neighbours.

`mach_locality -k <kind> <cell>` exposes a hierarchy, not a scalar:

| kind | example values | meaning |
|---|---|---|
| `cluster` | `yucmhcg`, `go` | the individual cell |
| `campus` | `clb`, `nby`, `pry` | a building/site; several per metro |
| `metro` | `cmh`, `tul`, `phx` | metropolitan area — the unit that maps to a GCP region |
| `continent` | `na`, `eu` | coarsest |

- **`metro` is the primary decision boundary.** Same-metro cross-cell reads are
  effectively free even across campuses (`go-d`/`nby` and `yucmhcg-d`/`clb` are
  both metro `cmh`), and only `metro` maps to a GCP region, so the cost rule keys
  on it too.
- **Do not measure cross-metro latency from a workstation**: its own RTT
  dominates. Measure from a job inside a metro, or reason from the hierarchy.
- **A real cross-metro copy is fast enough not to fear** (CNS-to-CNS runs at
  ~GiB/s). What kills a job is a training loop crossing a metro boundary for
  hours, not copy time.

## Charge The Group, Not Your 500 GiB Personal Ceiling

**A personal CNS ceiling is 500 GiB per cell and the team's accounting group
holds PiB, so the first question about a large copy is not "will it fit" but
"whose quota is it charged to".** Any dataset worth staging exceeds the personal
ceiling once replication is counted; charging the group makes the next section's
arithmetic an efficiency question, not a feasibility one.

Set the owner once, on the directory; every file written beneath it inherits it,
including files a job writes later, so no training or copy code changes:

```
fileutil chstat -R "quota_accounting{capacity_quota_user: '<mdb-group>'}" \
    /cns/<cell>-d/home/<user>
```

`chgrp -R <group>` accounts the same way but also grants the whole group read
access; prefer `chstat` when you only mean to move the bill.

**Gate 1 — membership is cheaper to test than to look up.** The directory-lookup
CLIs sit behind a restricted-LOAS wall a workstation credential does not clear,
but the filesystem answers directly: attempt the `chstat` on a scratch directory
and read the error — *not a valid ACL group* (no such group), ***\<user\> is not
a member of \<group\>*** (real group, not yours), or success. Confirm it landed
with `fileutil stat`, which echoes the `quota_accounting` block; being able to
*read* a group's quota with `fileutil quota <group> <cell>` is not evidence of
membership.

**Gate 2 — the group must have a ceiling in that specific cell, and failing this
is worse than not trying**: a group with no flex registration in the destination
accounts to an entity with no quota, so the write dies with *"Group \<g\> has no
quota (partition=hdd)"* and leaves a **poisoned file handle** (reproduced in two
independent cells). `fileutil quota <group> <cell>` cannot warn you — it reports
a plausible `500.00G` for an unregistered group, which is the default bucket it
falls through to. **Only the flex registry is authoritative; no registration
means no quota, whatever the filesystem says:**

```
flex.par list_ceiling -p <pool> -s colossus -g <group> -l <cell>-d
```

| Property of group quota | What it forces you to do |
|---|---|
| Three-level hierarchy: parent pool, team pool, accounting group; a cell can be missing at any level | When a whole metro looks unusable check the *team* pool first — a new cell often has the parent pool with PiBs free and no team beneath it |
| Ceilings are named size circles, and **the default circle carries zero spindle commitment** (the condition behind a documented 12-hour throughput collapse) | Never accept the default on a cell you will read from in a loop |
| Raising a circle is self-service only up to a policy limit; past it the tool names the request process in its own error | Probe with **`--validate_only`**, which runs the full authorisation and policy check without mutating anything — how to find a permission boundary without filing |
| Per cell and not uniform: near its ceiling in one cell, empty in another, absent in a third | Check the destination cell specifically before assuming headroom |
| A shared pool with fair-usage expectations | Stage a working slice; do not park a multi-TiB dataset indefinitely. Delete what the experiment no longer reads |
| A raised ceiling reaches Colossus asynchronously — flex updates at once, `fileutil quota` lags | Verify by writing, never by reading the quota back |

## Size A Copy In Disk Bytes, Not Payload Bytes

**The quota counts bytes after replication, so the encoding decides whether a
copy fits.** Default replication costs ~3x — a 199 GiB dataset becomes ~600 GiB
against a 500 GiB per-user ceiling and dies four-fifths of the way in.
Reed-Solomon costs ~1.45x, fits comfortably, and tolerates *more* simultaneous
chunk losses than 3-way replication: cheaper and more durable, not a trade.
**Compute payload x amplification against the ceiling as a fail-closed assert
before the first byte, and put the arithmetic in the abort message.**

| Trap | Rule |
|---|---|
| Going over is not a clean stop — quota is checked per stripe, so the write dies mid-file and leaves a truncated object a size-only check may accept | Stage to a temporary name, verify size and checksum, then rename |
| Going over poisons the cell for everything else you run | See §An Over-Quota Cell Looks Like A Broken Program for the signature and recovery |
| A copy call does not inherit the destination directory's encoding; inheritance is invisible state a re-run in a fresh directory loses | Name the encoding per file, then read it back |
| A cell may silently downgrade an encoding it cannot place, and the fallback is the expensive one | Verify the encoding landed, not that you asked for it. Pick from the user-facing recommended list — one appearing only in the internal *stable* set is a downgrade target, not a menu option |
| Erasure coding pads small files enormously (a ~9 KB file can occupy several MB) | Use it for large shards, never for a directory of sidecars |

## Before Touching A Payload

1. Resolve the exact category, payload, source, destination, and compute
   placement.
2. Inspect bounded metadata first — location, size, completion marker, manifest,
   checksums. Never read a large payload merely to discover where it is.
3. For Type 1, prove source and compute locality before access; a cross-location
   copy needs explicit authorization and a cost-aware, verified plan.
4. For Type 2, prove every eligible execution cell can reach the chosen runtime
   storage; pin cells when the data is intentionally regional.
5. Treat the copy as a transaction: write the smallest scope, validate object
   counts, sizes, checksums, and completion markers, then record the durable
   location in the project's source of truth.

**A replica is usable only when every physical root carries its verified
completion marker.** Visible shards without it are partial data, and a loader
that resolved its shard list at startup will not pick up shards appearing later.
Never infer completeness from a directory listing, and never hold mirror status
in memory — re-verify live before scheduling.

**Write a copy's evidence to the destination, not to a log.** A job's own logs
may be unreadable from a workstation (`jobs.md` covers which log paths fail on a
restricted credential); a manifest and a completion marker outlive the task, the
work unit, and the credential.

## Existence Is Not Completeness

**A distributed write is not atomic, so every "do we already have this?" check on
a distributed path must test size, not presence.** A task killed mid-copy leaves
a file that **exists and is zero bytes**, and `exists()` cannot tell it from a
good one; a name-only check makes a truncated write permanent, because resume
then skips it forever. Four silent failures here, each with its fix:

| Silent failure | Fix |
|---|---|
| A completion marker written last but not atomically: preemption left a 0-byte marker that counted as done and surfaced hours later as `json.loads("")` | Write the marker to a temporary name and **rename** — rename is atomic, so the marker is absent or complete |
| A staging check listed four filenames while the reader needed five, so a truncated fifth still counted as present | **One shared predicate** called by every stage and by the reader, so the lists cannot drift |
| A mirror verifier compared field 4 of `fileutil ls -l` — the mdb group, `empty` for every file — so it compared `"empty" == "empty"` and **passed unconditionally**, even against a nonexistent destination | **Size is field 5.** A verifier that cannot fail is worse than none, because a completion marker then certifies nothing |
| A copy timeout tuned for one file, applied to a 2000-directory batch, killed the transfer partway and left truncated files | Scale any timeout with the batch, or the timeout becomes the corruption source |
| `fileutil ls \| grep -c` was used to accept a replica: on a large directory the CLI **truncates and returns an unstable count** (three consecutive calls gave three different numbers), and while the job still runs the count is a mid-copy snapshot. The two together fabricated a "shards missing" verdict against data that was in fact complete | **Verify completeness from the producer's own `_SUCCESS`/manifest JSON** — the field it wrote after a recursive `Walk` + per-object size+crc32c re-read (`payload_shards_found`, `objects_bad`). Never accept or reject a replica by `fileutil ls`; and never verify a count while the writer is still running |

Two habits close the class. **Give every checker a reverse test** — point it at a
deliberately corrupt file and require it to fail; the mirror bug lived only
because nobody watched the check say no. And **make failure conservative**: a
partial listing must under-count completed work, never invent it, so a crash mid
verification is safe.

## An Over-Quota Cell Looks Like A Broken Program

**Rule out quota before believing any "the writer is broken" story** — this cost
a 130,000-step run its entire log and sent two investigations after the wrong
suspect.

**The signature is a 0-byte file, not an error.** Colossus checks the quota when
it allocates a stripe — the *first write*, not the open — so `mkdir` succeeds,
the file is created, the first byte is refused, and what survives is a file that
exists with length zero, indistinguishable at a glance from a process that died
before logging anything. Anything creating its files up front and writing later
shows this shape.

Asymmetries that decide the diagnosis:

| Asymmetry | What it means for you |
|---|---|
| **Reads keep working** on a cell you cannot write | This is what makes a full cell recoverable — you can still copy the data out |
| **A writer that retries survives; one that does not dies permanently** — poison expires. Checkpoints every few thousand steps kept landing while a 20-second log flush with no retry latched `broken` on its first refusal and stayed silent for the rest of the run | Two writers in one process disagreeing about whether storage works is a quota symptom, not a bug in either |
| **It is time-dependent, so it splits identical jobs** — two jobs from the same code differing only in a config value look like "this feature breaks logging" when the real variable is which one flushed inside the poisoned window | Before blaming a code path, check whether the *other* job also lost output later |

### Confirm it in one command

```bash
fileutil quota <user> <cell>-d                                   # usage vs limit
echo probe > /tmp/qprobe.txt                                     # cp has no stdin form
fileutil cp -f /tmp/qprobe.txt /cns/<cell>-d/home/<user>/qprobe.txt
```

A refused write names the condition outright: `Poisoned file handle: "<user>" is
over Colossus bytes HDD quota`. (`fileutil cp -` does **not** read stdin — it
looks for a file literally named `-` and fails with `not_found` before reaching
the quota, which reads like a completely different problem. Stage a real file.)

`fileutil quota` prints two pairs, usage then limit; compare **`disk_bytes`**,
never `data_bytes`, since the ceiling applies after replication — 144 G of
payload can be 417 G against a 500 G limit. `fileutil stat` on the directory
shows the encoding responsible (`r=3.2` ⇒ multiply payload by ~2.9).

### Recover, cheapest first

1. **Delete what nothing reads.** Usually enough and needs no permissions;
   checkpoint accumulation is the normal cause (next section).
2. **Move the bill to the group** — the real fix, since the group holds PiB
   against a personal 500 GiB. Use the `chstat` form above, but **verify the
   group is registered in that cell first** (`flex.par list_ceiling`): accounting
   to an unregistered group is *worse* than leaving it alone.
3. **Switch to a same-metro sibling cell** — the first move when the GROUP quota
   (not just yours) is full, so deleting your own files cannot help. A metro
   often holds several storage cells (e.g. `tul` has both `nm-d` and `oi-d`);
   pointing the bucket at a sibling with headroom is **lossless**, because
   same-metro cross-cell reads are free and the compute does not move. This beats
   abandoning the compute cell. `fileutil quota deepmind-resources-colossus
   <cell>` on each candidate finds one with room; `research/v7_storage_placement.md`
   records the metro→cell map. Only after exhausting same-metro options do you
   move the DATA to another metro (a Type-1 cross-region copy, expensive).
4. **Move the data to a cell where the group has a ceiling**, when the current
   metro has no registration at all. Some accelerator cells have no team storage
   whatsoever; `research/v7_storage_placement.md` records which.

**The poisoned handle is sticky — retrying never succeeds — and release is not
instant**: the block clears minutes after usage actually drops, and human
accounts get no soft-excess grace. Verify recovery by writing, not by re-reading
the quota.

## Checkpoints Are The Default Reason A Cell Fills Up

**A checkpoint writer with no retention policy will eventually take down every
write in the cell**. In orbax, retention (`max_to_keep`) can help but cleaning will still be needed.

**Keep, per run:** the **newest** checkpoint (auto-resume restores from it), a
**second** in case the newest is a torn write, and a coarse ladder (every
25k-50k steps) for re-evaluating a finished run. Everything between is dead
weight.

**Never delete the newest checkpoint, no need to decide whether a run is
still alive**.

`tpu gc` (`~/work/tpu_cmd/scripts/ckpt_gc.py`) applies exactly these rules,
dry-run by default, `--go` to delete, `--no-size` to skip the slow `du` pass. Fix
retention in the writer too, or the backlog rebuilds.

## Building A Multi-Gigabyte Artifact On Distributed Storage

**Assemble large payloads with SERVER-SIDE concatenation, in resumable units,
and never let two writers share an output path.** Producing three 20M-row
corpora (27-37 GB per array) turned every one of these into a lost night.

**The unit must fit the preemption window, and the whole must be resumable.**
`jobs.md` states the sizing rule for a work unit; an *output file* needs the
same treatment. A 2.5-hour single-task merge wrote all 27,200,000,128 bytes --
the final byte -- and was preempted twice, each time restarting from zero. Cut
the merge into contiguous PARTS written by separate tasks (each ~10 min, run
concurrently), then concatenate. A part costs one retry, not the corpus.

**The destination's SIZE is a resume ledger.** With a fixed header and parts of
known length, `header + sum(len(part[:k]))` identifies "the first k parts
landed" and nothing else can produce that number. Resume by reading the size.
A size *between* two boundaries is a torn append: cut back to the last boundary
and continue. A size *below* the boundary you expect is not a torn append at
all -- an append cannot shrink a file -- so it means **another writer**; refuse
and investigate rather than continuing onto rubble.

**Verify the storage layer's primitives yourself; the obvious assumption is
often wrong.** Two that cost hours:

| Assumption | Reality |
|---|---|
| "`append src dst` copies" | It is **move-and-concatenate**: `src` is DELETED. On a retried assembly it eats the very parts that make a retry cheap. Append a throwaway duplicate instead. |
| "distributed storage has no cheap truncate" | It does, and it is a metadata operation. Believing otherwise turned every torn append into a full restart, and one tier made **net zero progress across three attempts** because of it. |

**Server-side beats streaming by enough to change where the job runs** —
`append`/`cp` inside the storage layer is roughly two orders of magnitude faster
than a read-and-write loop carrying every byte through the process, and it costs
seconds of local CPU. So the "big copy" job is a controller, not a pipe;
`jobs.md` §Where The Storage CLI Exists owns the placement consequence and the
measured throughput numbers.

**Mirrors must compare CONTENT, not size.** A size-only check accepts a
destination whose bytes are wrong, and the realistic corruption -- a second
writer rewriting a file -- changes content long before length. Checksum every
file server-side after the copy and **publish the completion marker only if
they all match**. Use size alone for the *skip* decision on a resumed mirror,
though: checksumming both sides to decide whether to copy costs a full read of
each, ~10 min per 27 GB file, to decide not to copy it.

**Verify a finished artifact by reading it BACK, and gate publication on that.**
The producer asserts what it believes it wrote. Re-read the split: headers
agreeing with each other and with every metadata file, payload exactly
`header + rows*width`, one distinct key per row, index-array lengths, and a
**stratified content sample -- random rows plus both rows either side of every
part boundary**, which is where a mis-ordered or duplicated append shows. Sample
by ranged reads (`-input_startpos`), not a forward scan: a forward pipe pays the
whole prefix, so row 19,000,000 costs 26 GB *per row*. Batch adjacent sampled
rows into one call, since each CLI invocation costs ~2 s of startup.

Then make that verification the **precondition for mirroring**. A marker is not
evidence: the payload destroyed here was exactly the right size at the moment it
was being overwritten, so mirroring on marker-presence would have replicated the
damage into two more metros and stamped each copy verified.

## Two Writers On One Output Path

**Before writing a large artifact, kill everything that writes that path — not
just the thing you started.** A finished payload silently truncated to a fraction
of its size because a *previous* generation of the pipeline was still alive and
rewriting it from byte 0 — four failures at the identical offset that looked
exactly like a flaky storage layer under concurrency. Enumerate live writers by
name at the cluster layer (a launcher log is unreliable — a wiped `/tmp` loses
the job-id-to-purpose mapping), and **retire a keepalive when its work is done**
(a `/tmp` marker file is not enough on a box that wipes `/tmp`; delete the
entry). The arithmetic names the culprit: a size that grew from zero, or sits
*below* the boundary you expect, is not a torn append onto a large prefix — an
append cannot shrink a file, so it means another writer, and the two have
opposite fixes.

## Copying From A Bucket Someone Else Pays For

**When the source bucket belongs to an external GCP project, a cross-region read
is a bill, not a slowdown, and the payer is not the person who launched the
job.** Same-region reads are free, so the whole safety property is "prove both
ends are in one region before the first byte moves".

**Assert both ends explicitly, as literal constants, fail-closed, before the
first open — two separate asserts:** the **compute cell** equals the cell pinned
at submit time, and the **bucket's region** equals the region that cell lives in.
A metro *set* is not sufficient, and neither is one end alone: the
metro-to-region relation is indirect and invisible in a path string, so a
reschedule, a copy-pasted prefix, or an edited default moves one end while the
other still looks right.

**Two buckets with the same dataset name are not replicas until you prove it.**
Independently produced copies of one public dataset differ shard for shard — a
re-crawl changes the payload, so the same shard index came out 943 MB in one
region and 1683 MB in another. Sourcing each metro from "its own same-region
copy" therefore trains three different datasets and makes the loss curves
incomparable, which is exactly what a reproduction must not lose. Compare a
shard's size across both ends before calling either one a replica; when they
differ, crawl once and fan out from that copy.

**Fan out in two hops so neither hop is billed**: one same-region read out of
the external bucket into internal storage, then internal-to-internal copies to
every other metro. The second hop is cross-metro and still free because both
ends are internal, and it is also the FAST leg — internal-to-internal ran
several times the throughput of the external read.

| Rule | Qualification |
|---|---|
| **The guard belongs in the program**, not in the submit command or a reviewer's memory | A launch flag can be dropped by the packaging path and an operator cannot re-check it on a restart. An unknown or unreadable cell must exit non-zero before any read, the same as a wrong one |
| **Verify the region mapping from source**, not from memory or an assistant's answer | `production/borg/cloud_iam/slicer_regions/slicer_metros.pi` maps metro to GCP region; `mach_locality -k metro <cell>` resolves a cell to its metro. Not every metro has a GCP region at all — the launcher's default checkpoint root is one of these, so accepting the default is a silent cross-region transfer |
| **Assert the bucket's region by querying it, not by reading its name** | A stat of the bucket root returns its location and moves no object bytes, so it is safe *before* the region is proven and is the only in-job proof. A name is a weaker claim that happens to be true: keep it as the fallback for unreachable metadata, and make the program say which of the two it used |
| **The default bigstore client sends no usable credential**, so the server records the caller as anonymous and a correctly-ACLed bucket returns 403 | The fix is the flag that reads as "anonymous" but means "send no credential, so the ambient LOAS identity is used". Set it in-process, or an access test reports a false negative and the real identity is never presented |
| **"No such user in cell X" can also mean the bill goes somewhere else entirely** | When a directory carries a `quota_accounting{capacity_quota_user: '<group>'}` block, everything beneath it is charged to that GROUP, and `fileutil quota <you> <cell>` then reports no record for you no matter how many TB sit there. Seen on a cell holding ~70 GB of corpora with the personal record absent. So read the DIRECTORY's accounting (`fileutil stat`) before concluding either "nothing here" or "I am over quota" — the personal figure and the directory's owner answer different questions |
| **A missing CNS quota record is not a write block, and not headroom either** | "No such user" means *no usage recorded yet*, not *no ceiling*: unknown users fall through to a shared default bucket, so a never-written-to cell already has the standard per-user limit in force and the record becomes visible on the first write. Treat an absent record as the default ceiling, never as unlimited. It does suggest no spindle commitment and so no performance floor — measure throughput during the first large copy and give the job its own floor, armed only after startup, so a collapse stops it instead of grinding for hours |

## Distributed Reads On An Interactive Path

Applies to any status table, watch loop, or progress display reading a
distributed filesystem. Measure before trusting any figure below; the shape of
the conclusion is what lasts.

| Rule | Why |
|---|---|
| Cost is round trips, not bytes | A small read costs about what a large one does; tail-seeking earns its place because the naive "read everything, slice the end" form grows with the file |
| Never hide a per-file stat inside a sort key | It forces the calls serial and is invisible in the source — the single largest cost in our own status tool |
| Fan out with a thread pool, reusing one module-level pool | The client releases the GIL, so this is real concurrency worth roughly an order of magnitude; building a pool per call costs more than the reads |
| Put the read inside a resident process | The in-process client only wins in a long-lived one: cold it matches shelling out, hot it is dozens of times faster and stays hot across a minute of idle. A bash loop re-execing a binary is a one-shot caller however long it runs |
| If you must shell out, batch every path into one invocation | A shell utility pays about a second of startup before it does anything, plus first-connection setup |
| Measure another cell before blaming locality | Distance is second-order; per-cell load dominates, and a local cell can measure slower than a remote one |
| Always bound the wait | A log tail is a nicety; a status table that blocks on it is a regression |

Two silent traps:

- **A pip/conda build of the path library cannot see the distributed filesystem
  and does not say so** — the open-source build strips the backend, so a remote
  path is treated as ordinary POSIX and `exists()` returns False. Only a build
  depending on the internal target has the real backend.
- **No file or RPC access before framework initialization completes.** Touching
  remote storage at module import time aborts the process; do it inside the entry
  point, never at module scope.

## Local Disk Cleanup

**Disk cleanup is a data-safety task.** Identify which filesystem is actually
full before measuring anything, and measure targeted directories before broad
recursive scans. Local root pressure breaks agent CLIs, cloud tooling, and job
dispatch, so check caches, temporary directories, and large files under the
affected home, without crossing filesystem boundaries unnecessarily.

For a database whose write-ahead log has grown large, checkpoint it through its
own engine (find the holder, integrity-check, checkpoint, verify frames flushed,
then truncate) — never truncate the WAL by hand.

**Never delete a live database as routine cleanup, never kill unrelated sessions
to release a lock, and never hand-delete job state or temporary files while jobs
are running.**
