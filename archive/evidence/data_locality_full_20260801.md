# Data And Compute Locality

Read this before choosing XManager cells or accessing, copying, or uploading a
dataset or checkpoint. Classify the checkout in `projects.md` first; project
data guides add schema and validation rules but do not change this policy.

## Policy Matrix

| Category | Compute and payload rule |
|---|---|
| Type 1: Kaiming Group code | Keep data, checkpoints, and compute in the same region. For zonal disks or local paths, also match the zone. Do not open or copy payloads across locations by default; derive locality from current VM/job metadata and fail closed on a mismatch. |
| Type 2: Google internal research code | The Type 1 prohibition does not apply. XManager may place work in multiple eligible cells, so runtime data must be accessible from every selected cell. Do not treat a local VM path, persistent disk, or CitC checkout as globally accessible runtime storage. |

For large Type 2 datasets used by globally scheduled XManager jobs, prefer an
appropriate multi-region GCS bucket. The recorded shared destination is
`gs://qiaos-viscam-data-multi` in project `viscam-cloud`; verify the current
project configuration, identity, and target before every write. It is not a
destination for Type 1 data merely because it is multi-region.

## Before Touching A Payload

1. Resolve the exact project category, payload, source, destination, and
   compute placement.
2. Inspect bounded metadata first: location, size, completion marker, manifest,
   and checksums. Do not read a large payload merely to discover locality.
3. For Type 1, prove source and compute locality before access. A cross-location
   copy requires explicit authorization and a cost-aware, verified plan.
4. For Type 2, prove every eligible execution cell can reach the chosen runtime
   storage; pin cells when the data is intentionally regional.
5. Treat uploads and copies as transactions: write the smallest scope, validate
   object counts, sizes, checksums, and completion markers, then record the
   durable location in the project source of truth.

Never turn current mirror completeness or cell assignment into permanent
memory. Record how to verify it and re-check live state before scheduling.

## Cross-Continent Storage Gets Jobs Deleted, Not Just Slowed

Type 2 code is exempt from the Type 1 region prohibition, but "may run anywhere"
is not "may run far from its data". A real measurement, EqR-jax XID 275990419:
compute on `yuskedq` (metro ske, EU), data and checkpoints on `yutulpz` (metro
tul, NA). Checkpoint writes ran at 10 MiB/s and blocked the TPU ~10s per save
(plus 33-56s of background flush) every 2500 steps. The two-hour duty cycle fell
to 0.082, below the WIM pruner's 0.20 threshold, and Borg DELETED the job at
step 72500 of 150000. Co-located, the same recipe ran 47-48 steps/s against
10-11 and finished.

Practical rules:

- **orbax tells you at startup.** `Compute cluster: ... Storage cluster: ...`
  with a `continent:` on each. Read those two lines before diagnosing anything
  else about a slow job.
- **Mirror the dataset to each compute metro you use** and select it from the
  cell at runtime, rather than pinning one global path. Datasets of this size
  (~700 MB) copy in under a minute with
  `fileutil cp -R -parallel_copy=16 <src> <dst>/`. `-parallel_copy` takes a
  NUMBER; passing it bare swallows the next argument and the copy silently
  does nothing.
- **The checkpoint bucket matters more than the dataset**, because the dataset
  is staged once into `/tmp` while checkpoints are written for the life of the
  run.
- A low duty cycle is the symptom the pruner acts on. `go/wim_dc_aggregation`
  plots it per SCU, and the deletion message links to the exact policy.

`eqr_jax.md` records how EqR-jax implements the automatic per-cell selection
(`_local_data_root`, `_local_bucket`); this section owns the underlying rule.
