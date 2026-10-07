---
name: storage-operations
description: Copy, verify, or mirror data on distributed storage, recover from an over-quota cell or a CitC workspace that drops writes, build a multi-gigabyte artifact, and clean up local disk without losing data.
---

# Storage Operations

Relies on [knowledge/infrastructure/storage.md](../../../knowledge/infrastructure/storage.md)
for placement policy by project type, co-location, the cell -> metro -> bucket
table, distance, group quota, disk-byte sizing, checkpoint path shapes and
retention, and the RAM-backed `/tmp`; and on
[knowledge/infrastructure/v7-storage-placement.md](../../../knowledge/infrastructure/v7-storage-placement.md) for the metro -> storage cell survey.
This skill owns the procedures that touch the data. Two long procedures are
supporting references:
[references/large-artifacts.md](references/large-artifacts.md) (building a
multi-gigabyte artifact; two writers on one output path) and
[references/citc-write-failures.md](references/citc-write-failures.md) (CitC
dropping writes; a workspace exhausting its revision history).

Chapter 1 is copying and verifying data; Chapter 2 is a write that fails;
Chapter 3 is reading distributed paths and cleaning up local disk.

---

## Chapter 1 — Copying And Verifying Data

### Before Touching A Payload

1. Resolve the exact category, payload, source, destination, and compute
   placement.
2. Inspect bounded metadata first — location, size, completion marker, manifest,
   checksums. Never read a large payload just to find where it is.
3. For Type 1, prove source and compute locality before access; a cross-location
   copy needs explicit authorization and a cost-aware, verified plan.
4. For Type 2, prove every eligible execution cell can reach the chosen runtime
   storage; pin cells when the data is intentionally regional.
5. Treat the copy as a transaction: write the smallest scope, validate object
   counts, sizes, checksums, completion markers, then record the durable location
   in the project's source of truth.

**A replica is usable only when every physical root carries its verified
completion marker.** Visible shards without it are partial data, and a loader
that resolved its shard list at startup will not pick up shards appearing later.
Never infer completeness from a directory listing, and never hold mirror status
in memory — re-verify live before scheduling.

Write a copy's evidence to the destination, not to a log. A job's own logs may be
unreadable from a workstation ([job-diagnose skill §Debugging A Job That Dies With No Log](../job-diagnose/SKILL.md#debugging-a-job-that-dies-with-no-log)
covers which log paths fail on a restricted credential), while a manifest and completion marker outlive the task,
the work unit, and the credential.

### Asking Whether A Path Exists

**Judge existence by `rc` and STDOUT ONLY; never grep the output for the path
name, and never merge stderr into stdout first.** `fileutil` reports a missing
path by printing an error *that quotes the path you asked about*, so a check
shaped like `out=$(fileutil ls "$p" 2>&1); echo "$out" | grep -c "$name"` returns
a match for both outcomes and the predicate is dead:

| outcome | rc | stdout | stderr |
|---|---|---|---|
| exists | 0 | the listing | empty |
| missing | 1 | **empty** | ~300 B *containing the path string* |

It fails in the expensive direction, reading "missing" as "present", so it
produces a table of green rows that looks like corroboration. The safe form keeps
the streams apart and never inspects the text:

```
fileutil ls -l "$path" >/tmp/o.txt 2>/dev/null; rc=$?
[ "$rc" -eq 0 ] && [ -s /tmp/o.txt ]     # exists
```

A bulk sweep must carry a known-missing row. One path at a time a human notices
the error text, but a `for cell in ...` loop compresses each answer to one word
and hides the broken predicate. Include a path you know is absent and require it
to report absent: the sweep is evidence only once its negative control has fired
([harness/engineering.md §A test that cannot fail proves nothing](../../engineering.md#a-test-that-cannot-fail-proves-nothing)).

An absent tree is also not the same shape as an empty one. `.../data/` listing
nothing can mean the directory is empty *or* that its parent never existed. The
error text distinguishes them (`no <path>` vs `No parent directory <prefix>`),
but only if you read stderr deliberately instead of folding it into the answer.

### Existence Is Not Completeness

**A distributed write is not atomic, so every "do we already have this?" check on
a distributed path must test size, not presence.** A task killed mid-copy leaves
a file that exists and is zero bytes, and `exists()` cannot tell it from a good
one; a name-only check makes a truncated write permanent, because resume then
skips it forever. The silent failures seen here, each with its fix:

| Silent failure | Fix |
|---|---|
| A completion marker written last but not atomically: preemption left a 0-byte marker that counted as done and surfaced hours later as `json.loads("")` | Write the marker to a temporary name and **rename** — rename is atomic, so the marker is absent or complete |
| A staging check listed four filenames while the reader needed five, so a truncated fifth still counted as present | **One shared predicate** called by every stage and by the reader, so the lists cannot drift |
| A mirror verifier compared field 4 of `fileutil ls -l` — the mdb group, `empty` for every file — so it compared `"empty" == "empty"` and **passed unconditionally**, even against a nonexistent destination | **Size is field 5.** A verifier that cannot fail is worse than none, because a completion marker then certifies nothing |
| A copy timeout tuned for one file, applied to a 2000-directory batch, killed the transfer partway and left truncated files | Scale any timeout with the batch, or the timeout becomes the corruption source |
| `fileutil ls \| grep -c` was used to accept a replica: on a large directory the CLI **truncates and returns an unstable count** (three consecutive calls gave three different numbers), and while the job still runs the count is a mid-copy snapshot. The two together fabricated a "shards missing" verdict against data that was in fact complete | **Verify completeness from the producer's own `_SUCCESS`/manifest JSON** — the field it wrote after a recursive `Walk` + per-object size+crc32c re-read (`payload_shards_found`, `objects_bad`). Never accept or reject a replica by `fileutil ls`; and never verify a count while the writer is still running |

Two habits close the class. Give every checker a reverse test — point it at a
deliberately corrupt file and require it to fail, since the mirror bug lived only
while nobody watched the check say no. And make failure conservative: a partial
listing must under-count completed work, never invent it, so a crash
mid-verification is safe.

### Mirroring A Live Tree To Another Metro

**A long-running copy driver runs the script it read at startup; editing the file
on disk changes nothing until you relaunch.** `bash` slurps the script at exec and
never re-reads it: a driver launched a day earlier held a stale in-memory row list
and copied the whole directory instead of the intended 69 GB subset, ignoring
every later edit. After editing any driver, kill and relaunch.

A driver that stalls mid-list silently skips every row after it, and its own
"ALL DONE" counts skips as done. Once one wedged driver was killed, the rows after
the stall — including 1.5 TB core training data and four eval dirs — had never
been attempted, yet the tally read done (opt-out skips and real copies both
increment it). The `_MIRRORED` marker inventory on the destination is the only
authority on what landed: walk it and diff against the intended row list. Never
trust the driver's progress print or a `(31/33)` counter.

A fresh, idempotent driver is the cheapest repair: rather than hand-copy the
missing rows, relaunch the corrected script. With a per-row marker gate it skips
the 24 verified rows in seconds and re-copies only the gaps.

A crc verifier must ignore files that are not payload, or it fabricates a
failure. Two benign classes broke an otherwise-correct mirror check, each with
`bad=0` (every real file's crc matched) but `missing>0`:

| Verifier false-fail | Why | Fix |
|---|---|---|
| Source held a stale `.write_probe_<ts>.txt` from an earlier quota probe ([§Recover, cheapest first](#recover-cheapest-first)). `cp -R` skips dot-prefix files but `ls -lall -R` enumerates them, so src listed one more file than dst | The probe is not data; the copy was complete | Filter `\.write_probe_[0-9]+\.txt$` (and tombstones `\.~[0-9]+~$`) out of both listings before diffing |
| `dst_files` is always `src_files + 1` | The `_MIRRORED` marker lives in dst, not src | Join on path and count crc mismatches + real missing; the extra marker is neither |

A source tree can change after you finish mirroring it, and only a final
re-verify catches that. A file added to the source *after* both metros copied that
directory left both correctly-complete-at-copy-time yet missing it; only a closing
DoD sweep (re-diff every row source-vs-dest) surfaced it, and the per-row marker
written at copy time never will. Mirror status is a claim about a moment, not a
standing fact.

`fileutil cp` does not create multiple missing parent levels: after deleting a
directory to re-copy a subset, `cp src .../a/b/c` fails `no parent directory`, so
`mkdir -p` the parent first. And kill a wedged `fileutil` by exact PID — a
`pkill -f` on the copy's path also matches your own inspecting shell. Enumerate
the PID, confirm its cmdline, then signal it (TERM, then KILL if it ignores TERM
mid-RPC).

### Copying From A Bucket Someone Else Pays For

**When the source bucket belongs to an external GCP project, a cross-region read
is a bill, not a slowdown, and the payer is not the person who launched the
job.** Same-region reads are free, so the whole safety property is "prove both
ends are in one region before the first byte moves".

Assert both ends explicitly, as literal constants, fail-closed, before the first
open — two separate asserts. The compute cell equals the cell pinned at submit
time, and the bucket's region equals the region that cell lives in. A metro *set*
is not enough, and neither is one end alone: the metro-to-region relation is
indirect and invisible in a path string, so a reschedule, a copy-pasted prefix,
or an edited default moves one end while the other still looks right.

Two buckets with the same dataset name are not replicas until you prove it.
Independently produced copies of one public dataset differ shard for shard — a
re-crawl changes the payload, so the same shard index came out 943 MB in one
region and 1683 MB in another. Sourcing each metro from "its own same-region
copy" therefore trains three different datasets and makes the loss curves
incomparable, which a reproduction must not lose. Compare a shard's size across
both ends before calling either a replica; when they differ, crawl once and fan
out from that copy.

Fan out in two hops so neither is billed: one same-region read out of the
external bucket into internal storage, then internal-to-internal copies to every
other metro. The second hop is cross-metro and still free because both ends are
internal, and it is the FAST leg — internal-to-internal ran several times the
throughput of the external read.

| Rule | Qualification |
|---|---|
| **The guard belongs in the program**, not in the submit command or a reviewer's memory | A launch flag can be dropped by the packaging path and an operator cannot re-check it on a restart. An unknown or unreadable cell must exit non-zero before any read, the same as a wrong one |
| **Verify the region mapping from source**, not from memory or an assistant's answer | `production/borg/cloud_iam/slicer_regions/slicer_metros.pi` maps metro to GCP region; `mach_locality -k metro <cell>` resolves a cell to its metro. Not every metro has a GCP region at all — the launcher's default checkpoint root is one of these, so accepting the default is a silent cross-region transfer |
| **Assert the bucket's region by querying it, not by reading its name** | A stat of the bucket root returns its location and moves no object bytes, so it is safe *before* the region is proven and is the only in-job proof. A name is a weaker claim that happens to be true: keep it as the fallback for unreachable metadata, and make the program say which of the two it used |
| **The default bigstore client sends no usable credential**, so the server records the caller as anonymous and a correctly-ACLed bucket returns 403 | The fix is the flag that reads as "anonymous" but means "send no credential, so the ambient LOAS identity is used". Set it in-process, or an access test reports a false negative and the real identity is never presented |
| **"No such user in cell X" can also mean the bill goes somewhere else entirely** | When a directory carries a `quota_accounting{capacity_quota_user: '<group>'}` block, everything beneath it is charged to that GROUP, and `fileutil quota <you> <cell>` then reports no record for you no matter how many TB sit there. Seen on a cell holding ~70 GB of corpora with the personal record absent. So read the DIRECTORY's accounting (`fileutil stat`) before concluding either "nothing here" or "I am over quota" — the personal figure and the directory's owner answer different questions |
| **A missing CNS quota record is not a write block, and not headroom either** | "No such user" means *no usage recorded yet*, not *no ceiling*: unknown users fall through to a shared default bucket, so a never-written-to cell already has the standard per-user limit in force and the record becomes visible on the first write. Treat an absent record as the default ceiling, never as unlimited. It does suggest no spindle commitment and so no performance floor — measure throughput during the first large copy and give the job its own floor, armed only after startup, so a collapse stops it instead of grinding for hours |

---

## Chapter 2 — When A Write Fails

### An Over-Quota Cell Looks Like A Broken Program

**Rule out quota before believing any "the writer is broken" story** — this cost
a 130,000-step run its entire log and sent two investigations after the wrong
suspect.

The signature is a 0-byte file, not an error. Colossus checks quota when it
allocates a stripe — the *first write*, not the open — so `mkdir` succeeds, the
file is created, the first byte is refused, and what survives has length zero,
indistinguishable at a glance from a process that died before logging. Anything
creating its files up front and writing later shows this shape.

Asymmetries that decide the diagnosis:

| Asymmetry | What it means for you |
|---|---|
| **Reads keep working** on a cell you cannot write | This is what makes a full cell recoverable — you can still copy the data out |
| **A writer that retries survives; one that does not dies permanently** — poison expires. Checkpoints every few thousand steps kept landing while a 20-second log flush with no retry latched `broken` on its first refusal and stayed silent for the rest of the run | Two writers in one process disagreeing about whether storage works is a quota symptom, not a bug in either |
| **It is time-dependent, so it splits identical jobs** — two jobs from the same code differing only in a config value look like "this feature breaks logging" when the real variable is which one flushed inside the poisoned window | Before blaming a code path, check whether the *other* job also lost output later |

#### Confirm it in one command

```bash
fileutil quota <user> <cell>-d                                   # usage vs limit
echo probe > /tmp/qprobe.txt                                     # cp has no stdin form
fileutil cp -f /tmp/qprobe.txt /cns/<cell>-d/home/<user>/qprobe.txt
```

A refused write names the condition outright: `Poisoned file handle: "<user>" is
over Colossus bytes HDD quota`. (`fileutil cp -` does NOT read stdin — it looks
for a file literally named `-` and fails with `not_found` before reaching the
quota, which reads like a completely different problem. Stage a real file.)

`fileutil quota` prints two pairs, usage then limit; compare **`disk_bytes`**,
never `data_bytes`, since the ceiling applies after replication — 144 G of
payload can be 417 G against a 500 G limit. `fileutil stat` on the directory
shows the encoding responsible (`r=3.2` ⇒ multiply payload by ~2.9).

#### Recover, cheapest first

1. **Delete what nothing reads.** Usually enough and needs no permissions;
   checkpoint accumulation is the normal cause
   ([knowledge/infrastructure/storage.md §Checkpoints Are The Default Reason A Cell Fills Up](../../../knowledge/infrastructure/storage.md#checkpoints-are-the-default-reason-a-cell-fills-up)).
2. Move the bill to the group — the real fix, since the group holds PiB against
   a personal 500 GiB. Use the `chstat` form in
   [knowledge/infrastructure/storage.md §Charge The Group, Not Your 500 GiB Personal Ceiling](../../../knowledge/infrastructure/storage.md#charge-the-group-not-your-500-gib-personal-ceiling), but verify the group is
   registered in that cell first (`flex.par list_ceiling`): accounting to an
   unregistered group is *worse* than leaving it alone.
3. Switch to a same-metro sibling cell — the first move when the GROUP quota (not
   just yours) is full, so deleting your own files cannot help. A metro often
   holds several storage cells (e.g. `tul` has both `nm-d` and `oi-d`), and
   pointing the bucket at a sibling with headroom is lossless: same-metro
   cross-cell reads are free and the compute does not move, which beats
   abandoning the compute cell. `fileutil quota deepmind-resources-colossus
   <cell>` on each candidate finds one with room; [knowledge/infrastructure/v7-storage-placement.md](../../../knowledge/infrastructure/v7-storage-placement.md)
   records the metro→cell map. Only after exhausting same-metro options do you
   move the DATA to another metro (a Type-1 cross-region copy, expensive).
4. Move the data to a cell where the group has a ceiling, when the current metro
   has no registration at all. Some accelerator cells have no team storage
   whatsoever; [knowledge/infrastructure/v7-storage-placement.md](../../../knowledge/infrastructure/v7-storage-placement.md) records which.

The poisoned handle is sticky (retrying never succeeds) and release is not
instant: the block clears minutes after usage actually drops, and human accounts
get no soft-excess grace. Verify recovery by writing, not by re-reading the
quota.

---

## Chapter 3 — Reading And Cleaning Up

### Distributed Reads On An Interactive Path

Applies to any status table, watch loop, or progress display reading a
distributed filesystem. Measure before trusting any figure below; the shape of
the conclusion outlasts the number.

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

- A pip/conda build of the path library cannot see the distributed filesystem and
  does not say so: the open-source build strips the backend, so a remote path is
  treated as ordinary POSIX and `exists()` returns False. Only a build depending
  on the internal target has the real backend.
- No file or RPC access before framework initialization completes. Touching
  remote storage at module import time aborts the process; do it inside the entry
  point, never at module scope.

### Local Disk Cleanup

**Disk cleanup is a data-safety task.** Identify which filesystem is actually
full before measuring anything, and measure targeted directories before broad
recursive scans. Local root pressure breaks agent CLIs, cloud tooling, and job
dispatch, so check caches, temporary directories, and large files under the
affected home, without crossing filesystem boundaries needlessly.

For a database whose write-ahead log has grown large, checkpoint it through its
own engine (find the holder, integrity-check, checkpoint, verify frames flushed,
then truncate) — never truncate the WAL by hand.

Never delete a live database as routine cleanup, never kill unrelated sessions
to release a lock, and never hand-delete job state or temporary files while jobs
are running.

Why `/tmp` needs this care on this host is
[knowledge/infrastructure/storage.md §`/tmp` Is RAM On This Host — Do Not Scatter Build Artifacts Into It](../../../knowledge/infrastructure/storage.md#tmp-is-ram-on-this-host--do-not-scatter-build-artifacts-into-it).

Before deleting anything under `/tmp`, check the live command lines, not just
`lsof`. A job that will `open()` a file in a minute holds no descriptor now, so
`lsof` reads clean on a file about to be needed: a 2.2 GB tarball looked orphaned
by every static check while two live PROD jobs had it on their argv. And
`grep`ping `ps` for the path matches your own grep, so exclude your own pid or
"3 references" is really zero. A matching tool answers "does this string appear",
never "is anyone using this".

A cross-filesystem `mv` is a copy, so an interrupted one leaves a half in both
places and the second attempt fails with `unable to remove target: Directory not
empty`, which reads like a permissions problem. Recover with
`rsync -a --ignore-existing`, delete the source, and verify by file count and
total bytes, not `du`: block accounting differs between tmpfs and ext4, so
identical trees legitimately report different `du` sizes.
