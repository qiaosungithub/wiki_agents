---
name: vlm-data-operations
description: Upload, validate, or mirror VLM training and evaluation data using the workspace uploader and region-local artifact contracts.
---

# VLM Data Operations

Read [knowledge/codebases/vlm-data.md](../../../knowledge/codebases/vlm-data.md) for schemas, benchmark definitions, and the MMStar artifact
compatibility restriction before uploading or mirroring. Use [harness/skills/infra-operations/SKILL.md](../infra-operations/SKILL.md) to queue
the work and [harness/skills/storage-cleanup/SKILL.md](../storage-cleanup/SKILL.md) to verify artifact integrity.

## Chapter 1 — Uploading, Validating, And Mirroring Data

### Validate every replica before you use it

**A regional data replica is usable only when every physical root has a verified
`_SUCCESS` marker and its summary/size/checksum metadata validates.** Visible
shards without the final commit marker are partial data. Never infer
completeness from listing output, and never record mirror status in a guide:
re-verify live before scheduling.

### Upload a dataset

**Upload with `beifen/upload_data.py` and `beifen/data_upload/datasets.json`,
queued through unified infra.** The old per-dataset launchers are legacy, and the
retained adapters refuse direct use.

- Only worker 0 writes, and every payload, cache, and tmp path stays under `/dev/shm`.
- Derive locality from VM metadata and restrict GCS payload access to the matching `gs://kmh-gcp-${ZONE_SHORT}/data`; fail closed otherwise.
- Payload objects are deterministic tar shards, never scattered records. Only bounded manifest/summary/progress/commit/checksum/`_SUCCESS` metadata is loose.

### Mirror the grounding and eval roots

**Before training in a region, validate both Open Images roots there; before
scheduling a final eval, validate each eval root.**

| Root                            | Path                                                                                 | Rule                                                                                        |
| ------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Open Images detection train     | `gs://kmh-gcp-${ZONE_SHORT}/data/openimages-detection/image_records_wds/train`     | Expected global counts are in[archive/audits/](../../../archive/audits)                                            |
| Open Images relationships train | `gs://kmh-gcp-${ZONE_SHORT}/data/openimages-relationships/image_records_wds/train` | Expected global counts and the relationship filter signature are in[archive/audits/](../../../archive/audits)      |
| Eval benchmarks                 | `gs://kmh-gcp-${ZONE}/data/vlm_eval_benchmarks/{docvqa,realworldqa,mmstar}`        | Zone-local. Mirror only DocVQA validation and RealWorldQA test; DocVQA test has hidden gold |

The baseline JIT/HSDP path keeps the DocVQA and RealWorldQA WDS loaders at
`num_workers=0`, so its synchronized exact-count schedule stays globally
deterministic.
