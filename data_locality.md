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
