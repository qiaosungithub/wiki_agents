# Storage: Placement, Quota, And Checkpoints

Owns where data and checkpoints live, quota and accounting, copy sizing, the
distance facts that decide placement, and what `/tmp` costs on the workstation.
The procedures (copying and verifying data, mirroring, over-quota recovery,
building a multi-gigabyte artifact, CitC write failures, distributed reads, and
safe cleanup) are the
[storage-operations skill](../../harness/skills/storage-operations/SKILL.md).
Job launching is [knowledge/infrastructure/cluster-jobs.md](cluster-jobs.md), chip prices [knowledge/infrastructure/market.md](market.md),
and per-project data schemas [`projects/`](../codebases/projects.md). Read
before choosing a location, before putting a remote read on an interactive
path, and before deleting anything.

Chapter 1 is placement and locality; Chapter 2 is quota and accounting;
Chapter 3 is checkpoints; Chapter 4 is local temporary space.

---

## Chapter 1 — Placement And Locality

### Placement Policy By Project Type

Classify the checkout in [knowledge/codebases/projects.md](../codebases/projects.md) first.

| Category | Rule |
|---|---|
| Type 1: Kaiming Group code | Data, checkpoints, and compute stay in one region; match the zone too for zonal disks and local paths. Do not open or copy payloads across locations by default. Derive locality from current VM/job metadata and fail closed on a mismatch. |
| Type 2: Google internal research code | The Type 1 prohibition does not apply, but the scheduler may place work in several cells, so runtime data must be reachable from **every eligible cell**. A local VM path, persistent disk, or source checkout is not globally accessible runtime storage. |

For large Type 2 datasets consumed by globally scheduled jobs, prefer a suitable
multi-region bucket, and verify project, identity, and target before every write.
Multi-region availability does not make a location legal for Type 1 data.

### Co-Locate Compute With Storage, Or The Job Dies

**A job far from its data does not merely run slowly: its accelerators idle on
remote checkpoint writes, it drops below the platform's utilization threshold,
and the pruner deletes it mid-run** — no crash, no bug to find. Compute in Europe
against storage in North America lost 4-5x throughput and died at half
completion.

| Rule | Why |
|---|---|
| Read the checkpoint library's startup lines before diagnosing a slow job | It names the compute cluster and the storage cluster, a continent each |
| Treat low utilization as the pruner's trigger | Its deletion message links the policy it applied; read it rather than guessing |
| Mirror the dataset into every compute metro, select it at runtime from the cell | Beats pinning one global path; research datasets usually copy in under a minute |
| Choose the checkpoint destination first — it matters more than the dataset | The dataset is staged once; checkpoints are written for the life of the run |

When an accelerator has no storage next to it, move the compute before
requesting quota, and ask at `metro` granularity: enumerate the cells the
accelerator lives in, join against the group's registered cells by metro, escalate
only if that intersection is empty. A generation is turned up cell by cell while
storage registration lags, so the narrow question (does this exact cell have
quota) reports failure for placements that are fine. Registration takes days; the
sibling metro that already works takes minutes to find.
[knowledge/infrastructure/v7-storage-placement.md](v7-storage-placement.md) holds the survey and how to redo it.

### Never Hand-Maintain A Cell -> Metro -> Bucket Table

**There is exactly one measured source of truth for which metro a cell is in and which CNS
prefix is co-located with it: `google3_tpu_utils/cell_locality.py`, seeded from
`mach_locality` and regenerable with `remeasure_cell_locality.py --diff/--write`. Query it;
never write a new table, and never fall back to a guess.**

Hand-maintained copies caused two job deaths, both the same shape: the code answered when it
should have refused.

| Fallback | What it did | Cost |
|---|---|---|
| `metro_of()` returned the cell name as its own metro | scored `oe`, `nf`, `nm`, `oi` as four metros instead of all being `tul` | `--metro` silently dropped valid cells and looked like a capacity shortage |
| launcher fell back to a `_DEFAULT_BUCKET` | an unlisted cell got a bucket a continent away | duty cycle fell under the floor, the pruner deleted the job mid-run |

Both looked defensive and neither was visible from outside: one under-supplied candidates
(reads as "no capacity"), the other silently relocated the data.

Resolve buckets by metro, not by cell. A per-cell table is wrong the moment a new cell
appears, and 88% of schedulable cells were missing from at least one table. Storage belongs
to a metro, so keying on the metro covers every cell in it, unlisted ones included.

**Before adding a metro to any `--metros` list, check it against
`_METRO_STORAGE_CELL` in that table; a metro with no storage entry does not
queue slowly, it kills the car silently.** The launcher's `_local_bucket()`
raises `SystemExit`, so the experiment is created but the work unit is never
added: an empty shell in XM and zero bytes on CNS, which reads as "the job
never started" rather than "that metro cannot hold data". One line lost seven
cars to this. As of this writing the storage metros are `cbf ckv cmh dfw grq
las lpp mrn sin tul`; query the table rather than trusting that list.

**A metro's HISTORICAL LANDINGS are not the set of metros you may use, because
the history contains the failures too.** The dead cars above landed in
`uos`/`tpe`/`nrt` and stayed in the record, so a survey of "where have GPU jobs
run" returns metros that are guaranteed to fail. The scheduler being able to
PLACE a job there says nothing about the job being able to WRITE there. Same
trap in the other direction: `market.json` quotes h100 in only two metros while
real h100 jobs run in a third, so a missing quote is not an unusable metro.
Neither the landing history nor the price table is the authority; the storage
table is.

An unknown cell must fail closed, and `UNKNOWN` must be a value nobody can mistake for an
answer: not `''`, not the cell name, not a plausible default. Check what the consumer does
with it — a sentinel object reaching code that calls `.lower()` turns a clean refusal into a
crash in an unrelated loop — so cross a string boundary that can never equal a real metro.

Before folding several tables into one, prove the fold changes no existing answer: verify
the old per-cell entries were already a function of the metro, then compare every prior
lookup before and after. Report two groups separately — rows that must not change, rows
whose change is the point — because one mixed list hides a regression among the fixes.

A snapshot without a regeneration command is the next stale default. Record the command and
timestamp in the file, ship the re-measure script beside it, and give it a `--diff` mode
that exits non-zero, verified by injecting a wrong row and seeing it caught.

Widening a candidate set and fixing its storage mapping must land together: a cell
readmitted to candidacy but still missing a bucket lands on the silent default, so the fix
manufactures the failure it was meant to remove.

### Deciding Whether Two Locations Are "Far Apart"

**Cost and latency are different stakes.** Cost applies only when one end is a
GCS bucket in an externally-billed project, and is a step function: same region
free, anything else billed, no "close enough"
([storage-operations skill §Copying From A Bucket Someone Else Pays For](../../harness/skills/storage-operations/SKILL.md#copying-from-a-bucket-someone-else-pays-for)).
Latency applies to internal-to-internal traffic (CNS to CNS,
compute to CNS): unbilled, a gradient, and cells that look unrelated can be
neighbours.

`mach_locality -k <kind> <cell>` exposes a hierarchy, not a scalar:

| kind | example values | meaning |
|---|---|---|
| `cluster` | `yucmhcg`, `go` | the individual cell |
| `campus` | `clb`, `nby`, `pry` | a building/site; several per metro |
| `metro` | `cmh`, `tul`, `phx` | metropolitan area — the unit that maps to a GCP region |
| `continent` | `na`, `eu` | coarsest |

- `metro` is the primary decision boundary. Same-metro cross-cell reads are
  effectively free even across campuses (`go-d`/`nby` and `yucmhcg-d`/`clb` are
  both metro `cmh`), and only `metro` maps to a GCP region, so the cost rule
  keys on it too.
- Do not measure cross-metro latency from a workstation: its own RTT dominates.
  Measure from a job inside a metro, or reason from the hierarchy.
- A real cross-metro copy is fast enough not to fear (CNS-to-CNS runs at
  ~GiB/s). What kills a job is a training loop crossing a metro boundary for
  hours, not copy time.

---

## Chapter 2 — Quota And Accounting

### Charge The Group, Not Your 500 GiB Personal Ceiling

**A personal CNS ceiling is 500 GiB per cell and the team's accounting group
holds PiB, so the first question about a large copy is not "will it fit" but
"whose quota is it charged to".** Any dataset worth staging exceeds the personal
ceiling once replication is counted, making the next section's arithmetic an
efficiency question, not a feasibility one.

Set the owner once, on the directory; every file beneath inherits it, including
files a job writes later, so no training or copy code changes:

```
fileutil chstat -R "quota_accounting{capacity_quota_user: '<mdb-group>'}" \
    /cns/<cell>-d/home/<user>
```

`chgrp -R <group>` accounts the same way but also grants the whole group read
access, so prefer `chstat` when you only mean to move the bill.

Gate 1 — membership is cheaper to test than to look up. The directory-lookup
CLIs sit behind a restricted-LOAS wall a workstation credential does not clear,
but the filesystem answers directly: run the `chstat` on a scratch directory and
read the error — *not a valid ACL group* (no such group), ***\<user\> is not a
member of \<group\>*** (real group, not yours), or success. Confirm with
`fileutil stat`, which echoes the `quota_accounting` block. Reading a group's
quota with `fileutil quota <group> <cell>` is not evidence of membership.

Gate 2 — the group needs a ceiling in that specific cell, and failing this is
worse than not trying. A group with no flex registration in the destination
accounts to an entity with no quota, so the write dies with *"Group \<g\> has no
quota (partition=hdd)"* and leaves a poisoned file handle (reproduced in two
independent cells). `fileutil quota <group> <cell>` cannot warn you: it reports a
plausible `500.00G` for an unregistered group, the default bucket it falls
through to. Only the flex registry is authoritative:

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

### Size A Copy In Disk Bytes, Not Payload Bytes

**The quota counts bytes after replication, so the encoding decides whether a
copy fits.** Default replication costs ~3x: a 199 GiB dataset becomes ~600 GiB
against a 500 GiB per-user ceiling and dies four-fifths in. Reed-Solomon costs
~1.45x, fits comfortably, and tolerates *more* simultaneous chunk losses than
3-way replication — cheaper and more durable, not a trade. Assert payload x
amplification against the ceiling before the first byte, fail closed, and put the
arithmetic in the abort message.

| Trap | Rule |
|---|---|
| Going over is not a clean stop — quota is checked per stripe, so the write dies mid-file and leaves a truncated object a size-only check may accept | Stage to a temporary name, verify size and checksum, then rename |
| Going over poisons the cell for everything else you run | See [storage-operations skill §An Over-Quota Cell Looks Like A Broken Program](../../harness/skills/storage-operations/SKILL.md#an-over-quota-cell-looks-like-a-broken-program) for the signature and recovery |
| A copy call does not inherit the destination directory's encoding; inheritance is invisible state a re-run in a fresh directory loses | Name the encoding per file, then read it back |
| A cell may silently downgrade an encoding it cannot place, and the fallback is the expensive one | Verify the encoding landed, not that you asked for it. Pick from the user-facing recommended list — one appearing only in the internal *stable* set is a downgrade target, not a menu option |
| Erasure coding pads small files enormously (a ~9 KB file can occupy several MB) | Use it for large shards, never for a directory of sidecars |

---

## Chapter 3 — Checkpoints

### A Checkpoint Path Is An Opaque String, And Four Shapes Coexist

**Whatever produced a checkpoint owns the shape of its path. Store the string the job itself
reported and replay it byte for byte; any tool that appends, strips, or "normalises" a
checkpoint path breaks at least one family in this fleet.**

| Family | Shape |
|---|---|
| EqR-jax (maze, trm-arc1, hrm-trm) | `step_<N>/` — the job appends `/state` itself |
| codi, coconut | `step_<N>/` — flat, there is **no** `/state` subdirectory |
| paligemma, jax_llava | `checkpoint_<N>` — a flax file |
| torch ports | `step_<N>.pt` — **a single FILE, not a directory** |

The rule for passing one to a job is in [knowledge/infrastructure/resume-contracts.md §The `LOAD_FROM` Contract](resume-contracts.md#the-load_from-contract). Two traps make
it worse. A path must point at the leaf: a bucket root or a `checkpoints/` parent raises
`FileNotFoundError` *after* printing a reassuring metadata warning. And identical files are
not identical roles — a `ckpt_util.py` byte-for-byte the same as another checkout's can be
dead code there, with the real writer elsewhere. Comparing md5s answers "is this the same
file", never "is this the code that runs".

Read a checkpoint from anywhere; write one only to local storage. The asymmetry is the whole
rule:

| | Cost | Verdict |
|---|---|---|
| Restore read, cross-metro same continent | ~6x slower | fine, it happens once |
| Restore read, cross-continent | ~2.5x slower (6.0 GiB across the Atlantic ≈ 14 s) | fine, it happens once |
| Training loop **writing** cross-metro | ~94x, blocking saves push duty cycle under the 0.20 floor | **the pruner deletes the job** |

So a resume may start from a checkpoint anywhere, but the job must then write locally. The
safest arrangement copies the checkpoint to the compute cell's own CNS prefix before launch
— swapping the prefix, keeping the tail verbatim — and points the job at the copy; skip that
when it is already co-located. Verify by a delayed re-read: a workspace in a dropped-write
state returns `rc=0`, reads back correctly, and loses the file seconds later. If the copy
fails, refuse to launch. Falling back to the remote path is how a job gets pruned an hour
later, far from any evidence of the decision.

A rough ceiling for a blocking save is `0.80 x save_interval x write_rate`. With ~360 MiB/s
local that is roughly 8.5 GiB at a 30 s cadence; at ~10 MiB/s cross-continent it is
0.23 GiB, so no real training checkpoint qualifies. Treat the 0.20 duty-cycle floor as the
binding constraint, and re-measure the write rate rather than trusting these figures.

### Checkpoints Are The Default Reason A Cell Fills Up

**A checkpoint writer with no retention policy will eventually take down every
write in the cell**. In orbax, retention (`max_to_keep`) can help but cleaning will still be needed.

Keep, per run: the newest checkpoint (auto-resume restores from it), a second in
case the newest is a torn write, and a coarse ladder (every 25k-50k steps) for
re-evaluating a finished run. Everything between is dead weight.

Never delete the newest checkpoint; then you need not decide whether a run is
still alive.

`tpu gc` (`~/work/tpu_cmd/scripts/ckpt_gc.py`) applies exactly these rules,
dry-run by default, `--go` to delete, `--no-size` to skip the slow `du` pass. Fix
retention in the writer too, or the backlog rebuilds.

---

## Chapter 4 — Local Temporary Space

### `/tmp` Is RAM On This Host — Do Not Scatter Build Artifacts Into It

**`/tmp` is a tmpfs: every byte written there is charged to physical memory or
swap, and it has no size limit, so one careless writer can starve the whole
machine.** It reached 47 GB one night — testdeps, torch envs, smoke-test trees,
a CLI's session state — and pushed swap to 100% full. With no swap headroom the
kernel cannot page anything out, so the next memory spike is an immediate
OOM-kill rather than a gradual slowdown. Clearing 24 GB of it moved MemAvailable
from 10 GB to 34 GB and restored 15 GB of swap.

Put build artifacts, test dependencies, and any payload over ~100 MB in a
project directory or under `~/work/`, never in `/tmp`. Reserve `/tmp` for lock
files and small logs. If a tool insists on `/tmp`, point its `TMPDIR` elsewhere
and verify that the tool stopped creating files there, not by echoing the
variable back.

Deleting files under `/tmp` safely and recovering an interrupted
cross-filesystem `mv` are procedures in [storage-operations skill §Local Disk Cleanup](../../harness/skills/storage-operations/SKILL.md#local-disk-cleanup).
