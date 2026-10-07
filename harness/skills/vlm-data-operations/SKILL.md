---
name: vlm-data-operations
description: Validate a regional VLM data replica, upload a dataset with the beifen uploader, or mirror the Open Images grounding and DocVQA/RealWorldQA eval roots before training or final eval in a region.
---

# VLM Data Operations

Read [knowledge/codebases/vlm-data.md](../../../knowledge/codebases/vlm-data.md) for source schemas, coordinates, aliases, and
the final-eval benchmark definitions before uploading or mirroring. Locality is
Type 1 ([knowledge/codebases/projects.md §Data Locality Follows The Category, Not The Task](../../../knowledge/codebases/projects.md#data-locality-follows-the-category-not-the-task),
[knowledge/infrastructure/storage.md](../../../knowledge/infrastructure/storage.md)); queue the work per [knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md). This skill owns
validating replicas, uploading, and mirroring.

## Validate every replica before you use it

**A regional replica is usable only when every physical root carries a verified
`_SUCCESS` marker and its summary/size/checksum metadata validates.** Shards
without that marker are partial data. Later shards cannot repair a started
stream, because loaders cache the shard glob at startup. Never infer completeness
from a listing, never trust a remembered mirror status: re-verify live before
scheduling.

A metro appearing in `g3_env`'s cell->data map does not mean its data is
complete. The map records where a replica is *intended*, not where it is whole,
so verify the stage-1 datasets per cell before choosing a landing cell:

- `is-d` (cbf), `li-d` (lpp): full stage-1 set (laion-aesthetic, BLIP3o-Short,
  visual_genome, openimages-detection) with `data/_SUCCESS`.
- `go-d` (cmh): partial. Has visual_genome and the Qwen model, missing
  laion-aesthetic / BLIP3o-Short / openimages-detection, no `data/_SUCCESS`; a
  from-scratch stage-1 run there fails on a missing dataset.

So an accelerator whose only co-located candidates sit in cmh needs a data copy
first. Confirm `_SUCCESS` plus each required dataset dir on the specific data
cell (`fileutil ls /cns/<cell>-d/home/qiaos/data`) before committing a job there.

## Uploading a dataset

**Upload with `beifen/upload_data.py` plus `beifen/data_upload/datasets.json`,
queued through the job scheduler.** The old per-dataset launchers are legacy;
their adapters refuse direct use. Only worker 0 writes, and every
payload/cache/tmp path stays under `/dev/shm`. Type 1 locality applies here too:
derive it from VM metadata, restrict payload access to the matching
`gs://kmh-gcp-${ZONE_SHORT}/data`, fail closed otherwise. Payloads are
deterministic tar shards, never scattered records; only bounded
manifest/summary/progress/commit/checksum/`_SUCCESS` metadata is loose.

## Mirroring the grounding and eval roots

**Both Open Images physical train roots are per-region, and each must pass
replica validation before training in that region:**
`gs://kmh-gcp-${ZONE_SHORT}/data/openimages-{detection,relationships}/image_records_wds/train`.
Expected global counts and the relationship filter signature are in
[archive/audits/](../../../archive/audits/).

Eval roots are zone-local at
`gs://kmh-gcp-${ZONE}/data/vlm_eval_benchmarks/{docvqa,realworldqa}`; apply the
replica validation rule to each before scheduling a final eval. Mirror only the
two splits: DocVQA test has hidden gold, and its official download terms bind
whatever a convenience mirror's dataset card says. Both evaluators demand the
exact expected count of unique scored predictions, so a partial WDS root is an
error, not a smaller eval. The baseline JIT/HSDP path pins these loaders to
`num_workers=0`, keeping its exact-count schedule globally deterministic.
