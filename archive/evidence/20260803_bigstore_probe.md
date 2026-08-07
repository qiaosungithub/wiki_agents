<!-- Archived 2026-08-06 from ~/work/bigstore_probe/FINDINGS.md before deleting the checkout.
     The GO/NO-GO that unblocked the whole migration: a Borg job CAN read an external
     GCS bucket through /bigstore with the prod identity. Code remains in google3 at
     //experimental/users/qiaos/bigstore_probe. -->

# GO/NO-GO: Borg job reading an external GCS bucket via /bigstore/ — VERDICT: **GO**

Decisive run: **XID 276774269** ("bigstore-probe-cmh3"), work unit 1, COMPLETED.
Code: `//experimental/users/qiaos/bigstore_probe:main`
(CitC `/google/src/cloud/qiaos/xm_test/google3`, mirrored to `~/work/bigstore_probe`).

## Result

| Check | Result |
|---|---|
| Cell the task ran in | `go` (metro cmh = GCP us-east5 = bucket region) |
| Job identity | `qiaos`, host `fa0d56657752f336-1e37494ffc.borgtask.google.com` |
| `/bigstore` Exists | True |
| `/bigstore` Stat | 8603 bytes |
| **`/bigstore` READ** | **OK — 8603 bytes, == stat length** |
| `/bigstore` List | OK — 3291 entries |
| CNS write to `/cns/go-d/home/qiaos/probe/` | OK (the result file itself) |

Content read back is a genuine cc12m shard record:
`count=10000, successes=6497, failed_to_download=3006, failed_to_resize=497`,
84 status_dict entries.

Total bucket bytes read across the WHOLE task: **8603 (8.4 KiB)**. Zero .tar reads.

## THE FINDING THAT MATTERED

The default bigstore client presents **no credential**; the server logs the
caller as **"Anonymous caller"** and returns 403 ACCESS_DENIED even when the
bucket ACL is correct. Caught on the workstation before any Borg spend. Without
this, the Borg run would have reported a **false NO-GO**.

Fix: `--bigstore_anonymous=true`, whose name inverts its meaning — per
`//cloud/bigstore/util/bigstore_credentials.cc:24-28` it sends no credential
*in the request* so the **LOAS security-context** identity authenticates. On
Borg that is `<user>@prod.google.com`. Precedent:
`//experimental/users/geran/bigstore/bigstore_writing_lib.py` ("Required to use
LOAS auth"). The probe sets it in-process so it cannot be lost in plumbing.

**So: the prod identity IS granted on the kmh project — but only reachable with
this flag. Any future job reading this bucket must set it.**

## Required BUILD deps
`//cloud/bigstore/util:bigstore_file_register` (registers the /bigstore
FileFactory), `//file/colossus/public:cns`, `//pyglib:gfile`.

## Cost-safety guard (in code, fail-closed, before any read)
Reads `$BORG_CELL`/`$BORG_PHYSICAL_CELL`, asserts membership in the metro-cmh
set {go, yucmhcg, yucmhfq, yucmhqa}. Verified all three paths locally:
exit 2 (cell unknown), exit 3 (cell yucbfsr = cbf = us-central1, cross-region),
pass in cmh. Metro-to-region from
`//production/borg/cloud_iam/slicer_regions/slicer_metros.pi` (CMH -> us-east5).

## Two infra bugs found and fixed (committed, `~/work/tpu_cmd` 3186c36)

1. **`--tmp_ram_fs_gib` was unreachable.** The launcher accepts it; the wrapper
   had no case and rejects unknown flags, so every job silently took the 16 GiB
   TPU-training default. On BATCH that is charged as cell-wide shared RAM, so a
   CPU-only probe needing kilobytes queued behind it:
   `QUEUED: ... Resources exceeded by 17314086912 bytes RAM (16.12GiB)`
   (XID 276768092). Dropping to 1 GiB moved the shortfall to exactly 1.12 GiB —
   confirming the *ask*, not the alloc, was the blocker.
2. **The launcher forwarded that flag to the application.** It is consumed when
   building JobRequirements; passing it on hands the binary an undeclared flag —
   survivable only under `known_only=True`, fatal for a locked config schema.

## Tier note
g5/BATCH has zero best-effort RAM headroom in `go`: queue position went
9->4->6 (backwards) over ~12 min. PROD ran in well under a minute. The wrapper
already auto-injects PROD for g5 "to prevent hanging in BATCH priorities" — I
had overridden that with an explicit `--tier=BATCH`.

## Cross-region risk noticed
`xm_launcher.py`'s `--bucket` default is `/cns/yutulpz-d/...` (metro tul, no GCP
region). It is unused by this probe (paths are constants) but it DID appear in
the job env as `CHECKPOINT_BUCKET=/cns/yutulpz-d/...`. Any future data job must
override `--bucket=/cns/go-d/...`.
