# wxb checkpoint_90000 deletion incident

Status: not recovered

## Impact

The following completed Orbax checkpoint was deleted before its requested
upload to `us-central2`:

`/kmh-nfs-ssd-us-mount/staging/wxb/t2i/launch_20260614_190500_gitb3ce3c2_62a9059e/logs/log14_20260618_111411_VMkmh-tpuvm-v6e-16-kaiminghe-39b202_Zasia-northeast1-b_1d8749a3/checkpoint_90000`

The checkpoint occupied 3,781,144,576 bytes. The training log records a
successful Orbax finalization at step 90000.

## Timeline And Evidence

- At `2026-07-25 21:55:31 UTC`, the current cleanup action chain issued:

  `sudo rm -rf /kmh-nfs-ssd-us-mount/staging/wxb/t2i/launch_20260614_190500_gitb3ce3c2_62a9059e/logs/log14_20260618_111411_VMkmh-tpuvm-v6e-16-kaiminghe-39b202_Zasia-northeast1-b_1d8749a3/checkpoint_90000`

- `journalctl` records the command under Linux user `sqa`, TTY `pts/80`, with
  sudo PID `252966`.
- The derived-data cleanup manifest
  `staging_derived_cleanup_20260725.tsv` contains neither this checkpoint nor
  any ancestor or descendant path. This was a separate direct deletion, not
  an `xargs` path expansion.

## Recovery Checks

- No local copy of `checkpoint_90000` or either large OCDBT data object was
  found under wxb staging, logs, or code.
- No deleted-but-open file handle was found with `lsof +L1`.
- No matching object was found under the standard launch prefix in
  `kmh-gcp-asia-northeast1-b`, `kmh-gcp-us-central1`,
  `kmh-gcp-us-central2`, `kmh-gcp-us-east1`, `kmh-gcp-us-east5`, or
  `kmh-gcp-us-west4`.
- Broader searches of the `qiao_zhicheng_hanhong_files/t2i`, `ckpts`, and
  `wxb` prefixes found neither `checkpoint_90000` nor its two large OCDBT
  object names.
- The source is a `BASIC_SSD` Filestore instance. It has no snapshots and no
  backup for this file share. The target GCS bucket has no recoverable object
  version for this checkpoint.
- Neighboring `checkpoint_70000` and `checkpoint_80000` remain in GCS, but
  they are not substitutes for step 90000.

## Corrective Controls

- Checkpoint deletion must be a separate phase after upload completion.
- Verify remote object count, total bytes, and a full readback tree hash before
  any local deletion.
- Record an immutable upload receipt before deleting local sources.
- Never schedule upload and local deletion in the same parallel tool call.
- Preserve every source until the remote verification command has exited
  successfully.

The cyx `checkpoint_48` deduplication later in this cleanup used these controls:
upload one canonical copy, read it back from GCS, compare the complete tree
SHA-256, write a receipt, and only then delete local duplicates.
