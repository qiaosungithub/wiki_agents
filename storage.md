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

## Never Hand-Maintain A Cell -> Metro -> Bucket Table

**There is exactly one measured source of truth for which metro a cell is in and which CNS
prefix is co-located with it: `google3_tpu_utils/cell_locality.py`, seeded from
`mach_locality` and regenerable with `remeasure_cell_locality.py --diff/--write`. Query it;
never write a new table, and never fall back to a guess.**

Hand-maintained copies of this mapping caused two separate job deaths, and the shape of both
was the same: **the code answered when it should have refused.**

| Fallback | What it did | Cost |
|---|---|---|
| `metro_of()` returned the cell name as its own metro | scored `oe`, `nf`, `nm`, `oi` as four metros instead of all being `tul` | `--metro` silently dropped valid cells and looked like a capacity shortage |
| launcher fell back to a `_DEFAULT_BUCKET` | an unlisted cell got a bucket a continent away | duty cycle fell under the floor, the pruner deleted the job mid-run |

Both fallbacks looked defensive. Neither could be seen from the outside: one under-supplied
candidates (reads as "no capacity"), the other silently relocated the data.

**Resolve buckets by metro, not by cell.** A per-cell table is wrong the moment a new cell
appears — and 88% of schedulable cells were missing from at least one table. Storage belongs
to a metro, so keying on the metro covers every cell in it, including ones nobody has listed
yet.

**An unknown cell must fail closed, and `UNKNOWN` must be a value that cannot be mistaken for
an answer** — not `''`, not the cell name, not a plausible default. Check what the consumer
does with it: a sentinel object reaching code that calls `.lower()` turns a clean refusal
into a crash in an unrelated loop, so cross a string boundary that can never equal a real
metro.

**Before folding several tables into one, prove the fold changes no existing answer.** Verify
that the old per-cell entries were already a function of the metro, then compare every prior
lookup before and after. Report the two groups separately: rows that must not change, and
rows whose change is the entire point — a single mixed list hides a regression among the
intended fixes.

**A snapshot without a regeneration command is the next stale default.** Record the command
and the timestamp in the file, ship the re-measure script beside it, and give it a
`--diff` mode that exits non-zero — verified by injecting a wrong row and seeing it caught.

**Widening a candidate set and fixing its storage mapping must land together.** A cell
readmitted to candidacy but still missing a bucket lands on the silent default — the fix
manufactures the very failure it was meant to remove.

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

## Asking Whether A Path Exists

**Judge existence by `rc` and STDOUT ONLY; never grep the output for the path
name, and never merge stderr into stdout first.** `fileutil` reports a missing
path by printing an error *that quotes the path you asked about*, so a check
shaped like `out=$(fileutil ls "$p" 2>&1); echo "$out" | grep -c "$name"` returns
a match for **both** outcomes and the predicate is dead:

| outcome | rc | stdout | stderr |
|---|---|---|---|
| exists | 0 | the listing | empty |
| missing | 1 | **empty** | ~300 B *containing the path string* |

This fails in the expensive direction — it reads "missing" as "present", so it
produces a table of green rows that looks like corroboration. The safe form
keeps the streams apart and never inspects the text:

```
fileutil ls -l "$path" >/tmp/o.txt 2>/dev/null; rc=$?
[ "$rc" -eq 0 ] && [ -s /tmp/o.txt ]     # exists
```

**A bulk existence sweep must carry a known-missing row.** One path at a time,
a human notices the error text; a `for cell in ...` loop compresses each answer
to one word and the broken predicate becomes invisible. Include a path you know
is absent and require it to report absent — the sweep is only evidence once its
negative control has fired (`engineering.md` §A Test That Cannot Fail).

**And an absent tree is not the same shape as an empty one.** `.../data/` listing
nothing can mean the directory is empty *or* that its parent never existed; the
error text distinguishes them (`no <path>` vs `No parent directory <prefix>`) but
only if you read stderr deliberately instead of folding it into the answer.

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

## Mirroring A Live Tree To Another Metro

**A long-running copy driver runs the script it read at startup; editing the file
on disk changes nothing until you relaunch.** `bash` slurps the script at exec
and never re-reads it: a driver launched a day earlier held a stale in-memory row
list and copied the whole directory instead of the intended 69 GB subset,
ignoring every later edit. After editing any driver, **kill and relaunch** — do
not assume a running loop picked up the change.

**A driver that stalls mid-list silently skips every row after it; its own "ALL
DONE" counts skips as done.** Once the wedged driver was killed, the rows after
the stall — including 1.5 TB core training data and four eval dirs — **were never
attempted**, yet the tally read done (opt-out skips and real copies both
increment it). **The `_MIRRORED` marker inventory on the destination is the only
authority on what landed** — walk it and diff against the intended row list; never
trust the driver's progress print or a `(31/33)` counter.

**A fresh, idempotent driver is the cheapest repair.** Rather than hand-copy the
missing rows, relaunch the corrected script: with a per-row marker gate it
skips the 24 verified rows in seconds and re-copies only the gaps. Idempotency
turns "figure out exactly what's missing" into "run it again."

**A crc verifier must ignore files that are not payload, or it fabricates a
failure.** Two benign classes broke an otherwise-correct mirror check, each
`bad=0` (every real file's crc matched) but `missing>0`:

| Verifier false-fail | Why | Fix |
|---|---|---|
| Source held a stale `.write_probe_<ts>.txt` from an earlier quota probe (`§Recover`). `cp -R` skips dot-prefix files but `ls -lall -R` enumerates them, so src listed one more file than dst | The probe is not data; the copy was complete | Filter `\.write_probe_[0-9]+\.txt$` (and tombstones `\.~[0-9]+~$`) out of both listings before diffing |
| `dst_files` is always `src_files + 1` | The `_MIRRORED` marker lives in dst, not src | Join on path and count crc mismatches + real missing; the extra marker is neither |

**A source tree can change AFTER you finish mirroring it; only a final re-verify
catches it.** A file added to the source *after* both metros copied that
directory left both correctly-complete-at-copy-time yet missing it; only a
closing DoD sweep (re-diff every row source-vs-dest) surfaced it — the per-row
marker, written at copy time, never will. Mirror status is a claim about a
moment, not a standing fact.

**`fileutil cp` does not create multiple missing parent levels.** After deleting
a directory to re-copy a subset, `cp src .../a/b/c` fails `no parent directory`;
`mkdir -p` the parent first. And **kill a wedged `fileutil` by exact PID** — a
`pkill -f` on the copy's path also matches your own inspecting shell; enumerate
the PID, confirm its cmdline, then signal it (TERM, then KILL if it ignores TERM
mid-RPC).

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

## A Checkpoint Path Is An Opaque String, And Four Shapes Coexist

**Whatever produced a checkpoint owns the shape of its path. Store the string the job itself
reported and replay it byte for byte; any tool that appends, strips, or "normalises" a
checkpoint path breaks at least one family in this fleet.**

| Family | Shape |
|---|---|
| EqR-jax (maze, trm-arc1, hrm-trm) | `step_<N>/` — the job appends `/state` itself |
| codi, coconut | `step_<N>/` — flat, there is **no** `/state` subdirectory |
| paligemma, jax_llava | `checkpoint_<N>` — a flax file |
| torch ports | `step_<N>.pt` — **a single FILE, not a directory** |

The rule for passing one to a job is in `jobs.md` §The `LOAD_FROM` Contract. Two traps make
this worse than it looks: a path must point at the **leaf** (a bucket root or a
`checkpoints/` parent raises `FileNotFoundError` *after* printing a reassuring metadata
warning), and **identical files are not identical roles** — a `ckpt_util.py` that is
byte-for-byte the same as another checkout's can be dead code there, with the real writer
somewhere else entirely. Comparing md5s answers "is this the same file", never "is this the
code that runs".

**Read a checkpoint from anywhere; write one only to local storage.** The asymmetry is large
and it is the whole rule:

| | Cost | Verdict |
|---|---|---|
| Restore read, cross-metro same continent | ~6x slower | fine, it happens once |
| Restore read, cross-continent | ~2.5x slower (6.0 GiB across the Atlantic ≈ 14 s) | fine, it happens once |
| Training loop **writing** cross-metro | ~94x, blocking saves push duty cycle under the 0.20 floor | **the pruner deletes the job** |

So a resume may start from a checkpoint anywhere, but the job must then write locally. The
safest arrangement is to **copy the checkpoint to the compute cell's own CNS prefix before
launch — swapping the prefix and keeping the tail verbatim** — and point the job at the copy;
skip the copy when it is already co-located. Verify the copy by a **delayed** re-read: a
workspace in a dropped-write state returns `rc=0`, reads back correctly, and loses the file
seconds later. If the copy fails, refuse to launch — falling back to the remote path is how a
job gets pruned an hour later, far from any evidence of the decision.

**A rough ceiling for a blocking save is `0.80 x save_interval x write_rate`.** With
~360 MiB/s local that is roughly 8.5 GiB at a 30 s cadence; at ~10 MiB/s cross-continent it
is 0.23 GiB, i.e. no real training checkpoint qualifies. Treat the 0.20 duty-cycle floor as
the binding constraint, and re-measure the write rate rather than trusting these figures.

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
corpora (27-37 GB per array) turned every rule below into a lost night.

**The unit must fit the preemption window, and the whole must be resumable.**
`jobs.md` states the sizing rule for a work unit; an *output file* needs the
same treatment. A 2.5-hour single-task merge writing all 27,200,000,128 bytes was
preempted twice, each time restarting from zero. Cut the merge into contiguous
PARTS written by separate tasks (each ~10 min, run concurrently), then
concatenate. A part costs one retry, not the corpus.

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
just the thing you started.** A finished payload silently truncated because a
*previous* generation of the pipeline was still alive and rewriting it from byte
0 — four failures at the identical offset that looked exactly like a flaky
storage layer under concurrency. Enumerate live writers by name at the cluster
layer (a launcher log is unreliable — a wiped `/tmp` loses the job-id-to-purpose
mapping), and **retire a keepalive when its work is done** (a `/tmp` marker is
not enough on a box that wipes `/tmp`; delete the entry). The arithmetic names
the culprit: a size that grew from zero, or sits *below* the expected boundary,
is not a torn append — an append cannot shrink a file, so it means another
writer, and the two have opposite fixes.

## Before Blaming CitC For Dropping Writes, Find Out Who Is Writing

**A flood of `CreateSnapshot failure ... dropping local changes` is far more
often a local writer generating an impossible amount of work than a sick
backend — and the two are told apart in one command: count `Service is
overloaded` lines in `srcfsd.ERROR`. Zero of them, with tens of thousands of
`code: 104`, means the writes are ours.** The expensive shape is a staging
`rsync -aL ./ "$stagedir/"` whose SOURCE is the CWD while the DESTINATION sits
*inside* that same tree: it walks the whole depot into a subdirectory of itself,
never converges, is killed by its timeout, is `rm -rf`'d, and starts again. One
such queue entry produced 76% of a day's CreateSnapshot failures — measured
1.1 GB in 3 min, ~140 files/s — while every other job on the box stayed on its
usual baseline.

**Guard it in the code, not with a sentinel: refuse to rsync when
`realpath(dest)` is under `realpath(src)`, and refuse when the source is too
big to be a project workdir.** Both checks are needed and they catch different
shapes — a `workdir=/tmp` entry has its destination *outside* the source and
still copies ~9,000 top-level entries. Calibration is not delicate: a real
project workdir has ~20 top-level entries, a google3 checkout root ~417, `/tmp`
~9,300. Resolve symlinks first (`[ -d ]` and string prefixes both lie about
them) and compare with a trailing slash so `/a/bc` is not read as inside `/a/b`.

**The reason "which workspace" is not the interesting question: the error line
already answers it.** Each 104 line names the depot path and the workspace id it
was dropped for (`... to workspace (qiaos/3202) ... dropping local changes`), so
a read-only, zero-side-effect audit of who is losing writes is a `grep` — and it
beats a write-probe, which perturbs the very counter you are reading. Do **not**
use a directory's `mtime` as a health fingerprint: every CitC workspace root
stats as epoch-0 (measured 18/18, healthy and sick alike), so it is a 100%
false-positive test.

**The `bt`-style "backend throttling" alarms on this box double-count.** glog's
severity cascade writes every ERROR into `.WARNING` too, so a sentinel that
`cat`s both files sees each event twice; halve any such number before reasoning
about it, and prefer counting distinct *builds* over counting *file paths*.

## A Wedged CitC Workspace Is Server-Side, Not Yours To Restart

**This section describes the *other* shape — a genuinely sick workspace with
no local writer to blame. Rule out the section above first (zero `Service is
overloaded` lines plus a huge local writer means it is yours, not the server's).**

**When one CitC workspace silently rolls back writes, the fault is server-side
per-workspace state — it survives an srcfsd restart AND `citctools forceupdate`,
and fleet-restarting srcfs will not fix it.** The signature is not an error: a
write into the checkout reads back gone from a fresh process, while srcfsd logs a
`CreateSnapshot failure ... dropping local changes` (RPC ECONNRESET, code 104)
for that workspace id. It is scoped to the workspace, not the host: another
client on the same host persists fine.

**Prove server-side-per-workspace before touching anything shared.** A
brand-new throwaway client that persists writes rules out the host, srcfsd, and
the backend in one test — leaving stale per-workspace snapshot-stream state that
no client-side action resets. `forceupdate` returning rc=0 with "synced to
snapshot N" (the last good one) and the very next probe still dropping is the
confirmation that it was a no-op. A fleet `srcfs.service` restart severs every
CitC CWD on the box (the amply gateway included) and still will not clear it, so
it is the wrong hammer.

**A pending CitC CL is snapshot-backed in the client, NOT in Piper — so a
wedged workspace's uncommitted work has exactly two real recovery paths: a
submitted+landed CL, or a copy on local ext4.** `g4 print`/`files` at the CL and
at HEAD both return "no such file(s)"; `describe` lists the files but carries no
diff content. And a deleted client's snapshot is GC-eligible (retained only by an
explicit `citctools retain`), so "byte-identical to snapshot N" is not a durable
plan — it evaporates when the client is reclaimed. Preserve to ext4 first, then
re-create the CL in a healthy client and submit.

**Sidestep a wedged workspace; do not resurrect it.** Source files are identical
across clients, so apply the edits in any healthy checkout and build/submit from
there — verifying persistence (an *existing-file overwrite* is the failure mode:
sync, wait, re-read the edit) before building on top. This unblocks the work
without a client recreate or a fleet restart. (A giant `.citc/manifest.rawproto`
in the healthy client can fail `g4 reconcile` with `File too large`; use
`g4 --disable_reconcile` for opened/revert/submit — edit and build are unaffected.)

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

## `/tmp` Is RAM On This Host — Do Not Scatter Build Artifacts Into It

**`/tmp` is a tmpfs: every byte written there is charged to physical memory or
swap, and it has no size limit, so one careless writer can starve the whole
machine.** It reached 47 GB one night — testdeps, torch envs, smoke-test trees,
a CLI's session state — and pushed swap to 100% full. That is the dangerous
state: with no swap headroom the kernel cannot page anything out, so the next
memory spike is an immediate OOM-kill rather than a gradual slowdown. Clearing
24 GB of it moved MemAvailable from 10 GB to 34 GB and restored 15 GB of swap.

**Put build artifacts, test dependencies, and any payload over ~100 MB in a
project directory or under `~/work/`, never in `/tmp`.** Reserve `/tmp` for lock
files and small logs. If a tool insists on `/tmp`, point its `TMPDIR` elsewhere
— and verify by checking that the tool stopped creating files there, not by
echoing the variable back.

**Before deleting anything under `/tmp`, check the live command lines, not just
`lsof`.** A job that will `open()` a file in a minute holds no descriptor now,
so `lsof` reads clean on a file that is about to be needed — a 2.2 GB tarball
looked orphaned by every static check while two live PROD jobs had it on their
argv. And `grep`ping `ps` for the path matches your own grep: exclude your own
pid, or "3 references" is really zero. **A matching tool answers "does this
string appear", never "is anyone using this".**

**A cross-filesystem `mv` is a copy, so an interrupted one leaves a half in
both places** — and the second attempt fails with `unable to remove target:
Directory not empty`, which reads like a permissions problem. Recover with
`rsync -a --ignore-existing` then delete the source, and verify by **file count
and total bytes, not `du`**: block accounting differs between tmpfs and ext4, so
identical trees legitimately report different `du` sizes.

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
