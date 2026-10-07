# CitC Write Failures

Supporting reference for the [storage-operations skill](../SKILL.md). Owns
diagnosing a CitC/srcfs workspace that drops writes and recovering a workspace
that has exhausted its revision history. A slow staging build that this causes
is triaged from [machine-health skill §How Slow Is A Build Too Slow](../../machine-health/SKILL.md#how-slow-is-a-build-too-slow).

## Before Blaming CitC For Dropping Writes, Find Out Who Is Writing

**`CreateSnapshot failure ... dropping local changes` means the write was
rejected after local tools could already have reported success.** Count actual
writers and recent drops, then obtain the server's full rejection reason.
`Service is overloaded` messages support overload; their absence does NOT prove
that a current local writer is responsible. **`code: 104` is CitC's application
error `ACCESS_DENIED`, not Linux errno ECONNRESET.** The mapping is in
`devtools/citc/proto/citc.proto`; srcfs converts a permanent rejection into this
number and discards the pending resource.

One common trigger is a staging `rsync -aL ./ "$stagedir/"` whose SOURCE is
the CWD while the DESTINATION sits *inside* that same tree: it walks the whole
depot into a subdirectory of itself, never converges, is killed by its timeout,
is removed, and starts again. One such queue entry produced 76% of a day's
CreateSnapshot failures — measured 1.1 GB in 3 min, ~140 files/s. Historical
staging accumulation can also exhaust a workspace after the writer has stopped.

Guard it in the code, not with a sentinel: refuse to rsync when `realpath(dest)`
is under `realpath(src)`, and refuse when the source is too big to be a project
workdir. Both are needed and catch different shapes — a `workdir=/tmp` entry
has its destination *outside* the source and still copies ~9,000 top-level
entries. Calibration is not delicate: a real project workdir has ~20 top-level
entries, a google3 checkout root ~417, `/tmp` ~9,300. Resolve symlinks first
(`[ -d ]` and string prefixes both lie about them) and compare with a trailing
slash so `/a/bc` is not read as inside `/a/b`.

"Which workspace" is not the interesting question: the error line answers it.
Each 104 line names the depot path and the workspace id it was
dropped for (`... to workspace (qiaos/3202) ... dropping local changes`), so a
read-only, zero-side-effect audit of who is losing writes is a `grep`, and it
beats a write-probe, which perturbs the counter you are reading. Do not use a
directory's `mtime` as a health fingerprint: every CitC workspace root stats as
epoch-0 (measured 18/18, healthy and sick alike), a 100% false-positive test.

The `bt`-style "backend throttling" alarms on this box double-count: glog's
severity cascade writes every ERROR into `.WARNING` too, so a sentinel that
`cat`s both files sees each event twice. Halve any such number before reasoning
about it, and prefer counting distinct *builds* over counting *file paths*.

## A Workspace Can Exhaust Its Revision History; Diagnose Before Replacing It

A fresh workspace that persists both creation and overwrite isolates the
failure to the original workspace's state. It does **not** establish an
unrepairable snapshot stream or a particular server bug. `forceupdate` and an
srcfs restart cannot remove a server-enforced history limit; a restart also
severs every CitC CWD on the workstation.

**Measured 2026-09-06: `run_amply_workspace` (`qiaos/402`) stopped advancing at
snapshot 18233.** A fresh client persisted writes, while the old client dropped
even a tiny file. Sending a uniquely named probe through the ordinary
`citctools create_snapshot` API exposed the complete rejection:

```text
Workspace qiaos/402 has too many revisions since last keyframe
(700001, max is 700000, keyframing should have happened at 10000)
```

A keyframe is the service's checkpoint of resource history. The current server
code counts both writes and resource removals toward the revision limit, so
cleanup inside an already full workspace is also blocked. Automatic keyframing
has a separate live-resource limit (100000 in the inspected defaults).
This workspace had 785949 resources: 783587 below
`experimental/qiaos/eqr_jax_final_stages/`, and only 2362 outside it.
Its 312 MiB manifest explains why blindly cloning everything is not a lasting
repair. The direct keyframe command exists, but the measured call
`citctools create_keyframe qiaos/402 18233` was denied because it requires
`citc-impersonators`; do not assume the workspace owner can run it.

Recovery within ordinary user permissions:

1. Retain the original (`citctools retain -w qiaos/402 -t 365`) and preserve
   source files, Fig metadata, the manifest, and verification results on local
   ext4. Retention is explicit; a snapshot URL alone is not a durable backup.
2. Copy a reviewed selection of resources from a fixed snapshot into a NEW
   workspace, including ViewConfig, Fig annotations, and all source edits.
   Keep the oversized historical staging tree in the retained original.
   The native CitC uploader supports copying selected resource IDs, including
   annotations and tombstones; do not use a recursive depot-root rsync.
3. Compare resource types, content checksums, and executable bits. Verify
   creation AND overwrite from the new workspace's immutable snapshot after
   flushing; `fsync` or an immediate reread alone did not detect this failure.
4. Preserve an archive alias before moving the working alias. Fig has both
   `alias` and `fig_ws` tags; update them consistently using the native tools.
   Reopen CWDs that still resolve to the old numeric workspace. Keep staging
   separate from the source workspace to avoid repeating the accumulation.

Also inspect Fig's two narrow-spec files after a selective recovery. Here both
still contained 65057 includes for the archived staging tree (9.1 MB each),
which made even `hg log -r .` spend minutes constructing its matcher. With the
original metadata backed up and no tracked files in that subtree, removing
only those includes from both files reduced each to 11965 bytes. Do metadata
recovery serially: an interrupted Fig query can leave an abandoned transaction;
use `hg recover` and wait for it before probing or changing metadata again.
The final native `hg log -r .` and scoped `hg status` passed in 5.38 s and
2.11 s respectively, with the original parent unchanged.

The incident's tools, reviewed resource manifest, local source backup, and
repair evidence live in `~/work/.citc_recovery_20260906/`. Diagnose the next
incident from its actual API error, not from this one's numeric code alone.

A pending CitC CL is snapshot-backed in the client, NOT in Piper:
`g4 print`/`files` can return "no such file(s)" while `describe` lists files
without diff content. Preserve to ext4 before deleting or re-creating any
client. A submitted and landed CL is another recovery source. A giant
`.citc/manifest.rawproto` can fail `g4 reconcile` with `File too large`;
`g4 --disable_reconcile` avoids reconciliation when inspecting opened files,
but does not repair dropped writes.
