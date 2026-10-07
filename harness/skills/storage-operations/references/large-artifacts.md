# Large Artifacts And Concurrent Writers

Supporting reference for the [storage-operations skill](../SKILL.md). Owns
assembling, verifying, and protecting a multi-gigabyte artifact on distributed
storage. Placement, quota, and disk-byte sizing are
[knowledge/infrastructure/storage.md](../../../../knowledge/infrastructure/storage.md).

## Building A Multi-Gigabyte Artifact On Distributed Storage

**Assemble large payloads with SERVER-SIDE concatenation, in resumable units,
and never let two writers share an output path.** Producing three 20M-row
corpora (27-37 GB per array) turned every rule below into a lost night.

The unit must fit the preemption window and the whole must be resumable.
[knowledge/infrastructure/cluster-jobs.md §Preemption, Restart, And Resume](../../../../knowledge/infrastructure/cluster-jobs.md#preemption-restart-and-resume) sizes a work unit; an *output file* needs the same treatment. A 2.5-hour
single-task merge writing all 27,200,000,128 bytes was preempted twice, restarting
from zero each time. Cut the merge into contiguous PARTS written by separate tasks
(each ~10 min, run concurrently), then concatenate: a part costs one retry, not
the corpus.

The destination's SIZE is a resume ledger. With a fixed header and parts of known
length, `header + sum(len(part[:k]))` identifies "the first k parts landed" and
nothing else produces that number. A size *between* two boundaries is a torn
append: cut back to the last boundary and continue. A size *below* the boundary
you expect cannot be a torn append, since an append cannot shrink a file, so it
means another writer; refuse and investigate rather than continue onto rubble.

Verify the storage layer's primitives yourself. Two assumptions that cost hours:

| Assumption | Reality |
|---|---|
| "`append src dst` copies" | It is **move-and-concatenate**: `src` is DELETED. On a retried assembly it eats the very parts that make a retry cheap. Append a throwaway duplicate instead. |
| "distributed storage has no cheap truncate" | It does, and it is a metadata operation. Believing otherwise turned every torn append into a full restart, and one tier made **net zero progress across three attempts** because of it. |

Server-side beats streaming by enough to change where the job runs: `append`/`cp`
inside the storage layer is roughly two orders of magnitude faster than a
read-and-write loop carrying every byte through the process, at seconds of local
CPU. The "big copy" job is a controller, not a pipe; [knowledge/infrastructure/cluster-jobs.md §Where The Storage CLI Exists, And Where It Does Not](../../../../knowledge/infrastructure/cluster-jobs.md#where-the-storage-cli-exists-and-where-it-does-not)
owns the placement consequence and the throughput numbers.

Mirrors must compare CONTENT, not size: a size-only check accepts a destination
whose bytes are wrong, and the realistic corruption (a second writer rewriting a
file) changes content long before length. Checksum every file server-side after
the copy and publish the completion marker only if all match. Use size alone for
the *skip* decision on a resumed mirror, since checksumming both sides costs a
full read of each, ~10 min per 27 GB file, to decide not to copy it.

Verify a finished artifact by reading it BACK and gate publication on that; the
producer only asserts what it believes it wrote. Re-read the split: headers
agreeing with each other and with every metadata file, payload exactly
`header + rows*width`, one distinct key per row, index-array lengths, and a
stratified content sample -- random rows plus both rows either side of every part
boundary, where a mis-ordered or duplicated append shows. Sample by ranged reads
(`-input_startpos`), not a forward scan: a forward pipe pays the whole prefix, so
row 19,000,000 costs 26 GB *per row*. Batch adjacent sampled rows into one call,
since each CLI invocation costs ~2 s of startup.

Make that verification the precondition for mirroring. A marker is not evidence:
the payload destroyed here was exactly the right size while being overwritten, so
mirroring on marker-presence would have replicated the damage into two more
metros and stamped each copy verified.

## Two Writers On One Output Path

**Before writing a large artifact, kill everything that writes that path — not
just the thing you started.** A finished payload was silently truncated by a
*previous* generation of the pipeline, still alive and rewriting it from byte 0:
four failures at the identical offset, looking like a flaky storage layer under
concurrency. Enumerate live writers by name at the cluster layer (a launcher log is
unreliable — a wiped `/tmp` loses the job-id-to-purpose mapping), and retire a
keepalive when its work is done (a `/tmp` marker is not enough on a box that
wipes `/tmp`; delete the entry). The arithmetic names the culprit: a size that
grew from zero, or sits *below* the expected boundary, is not a torn append —
an append cannot shrink a file, so it means another writer, and the two have
opposite fixes.

The second writer can be a job you already buried: the scheduler may restart a
task hours after you judged it dead, and auto-resume makes it read the
CHECKPOINT ITS SUCCESSOR WROTE. Measured: a job whose output stopped at 01:00 was
rescheduled at 02:52, logged `RESUMED from step 12288` — the replacement run's
own checkpoint — and raced it toward the same `step_13312`, ~1000 steps behind.
Whoever writes last wins, both logs stay clean, and the damage surfaces only as a
curve that jumps at the next eval. A checkpoint-gap rule cannot see it: a gap
opens when NOBODY writes, never when two do. Watch the output path, not the job —
enumerate every producer directory under it and alarm when two show recent
writes — and treat `RESUMED from <a step your other run produced>` as the trip
wire, because by the time a duplicate checkpoint lands the corruption is on disk.
