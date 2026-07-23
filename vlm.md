# VLM Training

This guide covers the non-obvious invariants shared by JAX LLaVA,
`PaliGemma-baseline`, and `beifen-Paligemma`. Current code and project-native
configs remain authoritative.

## First Principles

- Keep data, checkpoints, and compute in the same region. Validate locality
  before listing or opening GCS payloads, and fail fast on missing paths.
- Preserve each checkout's execution model. A correct pmap checkpointing pattern
  is not automatically correct for a globally sharded JIT/HSDP TrainState.
- Treat the staged config as the experiment definition. WandB and the tracking
  spreadsheet record what ran; old row numbers and incident job ids are not
  architectural truth.
- When porting between related checkouts, copy behavior deliberately and retain
  project-specific sharding, dependency, and initialization choices.

## HSDP And Model Semantics

- In HSDP, derive process-local batch shape from data mesh axes. The final mesh
  axis is the model axis and should not be counted as data parallelism.
- Use explicit mesh-aware sharding for activation constraints and checkpoint
  restore. Do not assume a mesh context exists during shape evaluation.
- Avoid materializing full vocabulary logits when hidden-space token loss is
  available, and avoid gathering a full sharded TrainState onto every host.
- Preserve deliberate model behavior such as prompt-causal masking, connector
  optimizer separation, late-fusion gradient stops, and task-specific generation
  budgets unless the task explicitly changes them.

## Data And Exact Resume

- A stateful dataloader checkpoint is valid only for a compatible data recipe:
  process topology, local batch, workers, roots, mix weights, shuffle state, and
  seeds must agree. Remap only known same-dataset regional replicas, never
  arbitrary GCS paths.
- Restoring exact loader state means its saved RNG and cursor define the stream;
  do not also advance the seed by checkpoint step.
- Missing dataset shards are configuration errors, not transient failures to hide
  behind retries.
- Large WebDataset shuffle state is expensive to serialize. Keep snapshot cadence
  aligned with durable checkpoints unless explicitly testing replay.

## Dataset Uploads

- Use `beifen/upload_data.py` with `beifen/data_upload/datasets.json`; old
  per-dataset launchers are legacy and retained adapters refuse direct use.
- Queue through unified infra. Only worker 0 writes, and all payload/cache/tmp
  paths stay under `/dev/shm`.
- Derive locality from VM metadata and restrict GCS payload access to the
  matching `gs://kmh-gcp-${ZONE_SHORT}/data`; fail closed otherwise.
- Payload objects are deterministic tar shards, never scattered records. Only
  bounded manifest/summary/progress/commit/checksum/`_SUCCESS` metadata is loose.
- Verify uploaded size/checksum and require `_SUCCESS` before using a replica.

## Bounding-Box Coordinate Invariant

- The only internal bbox representation is absolute `xyxy` on the decoded
  original-image canvas, accompanied by an explicit `(width, height)`. Dataset
  adapters must declare their source schema; never infer `xyxy` versus `xywh`
  from numeric values.
- Convert from the canonical box to Qwen `0..1023` coordinates or PaliGemma
  `<loc>` tokens only after applying the exact image resize/letterbox transform.
  Drawing a raster box and emitting text coordinates must consume the same
  canonical box.
- Audited source adapters: Visual Genome regions are absolute `xywh`; legacy
  `jxu124/refcoco` WDS stored untagged absolute `xyxy` despite an uploader comment
  claiming `xywh`; the existing RefCOCOg train WDS and local eval JSON store
  explicit/legacy COCO `xywh`; the Hugging Face RefCOCOg source itself is `xyxy`.
- In the 2026-07-16 audit of all 159 active LLaVA-OV1.5 configs, normalized
  textual bboxes were confirmed in `coco`, `sherlock`, `vg`,
  `vision_oritented`, `llava_cot_100k`, and the ten `svit-part-*` configs. Most
  use `[x1,y1,x2,y2]`; COCO also uses prose such as `between coordinates
  (x1,y1) and (x2,y2)`. Keep conversion hard-whitelisted so unrelated math
  arrays and graph-coordinate pairs are untouched, and rewrite both questions
  and answers plus any coordinate-format prose.
- Every stateful and legacy loader path must forward `dataset.coord_format` to
  preprocessing. A config that says `qwen` is not sufficient if an iterator
  silently calls the default `loc_tokens` path.
- Current true multi-box exposure is sparse and mostly comes from Sherlock/SVIT.
  For CVBench-like colored multi-region training, the most practical external
  sources are ViP-LLaVA Visual7W/VG Relations followed by SPHINX-V MDVP VCR and
  relationship subsets. Check the non-commercial/research licenses before
  mirroring them.

## Point Coordinate Invariant

- PixMo-Points stores each point as `(x, y)` on an explicit `0..100` source
  canvas (`point_scale=100` in the official Molmo adapter), not as `[0,1]`
  fractions or decoded-image pixels. Convert percentages to the decoded-image
  canvas first, apply the exact stretch/letterbox transform, then quantize to
  `0..1023`. PaliGemma loc text serializes each point as `y` token then `x`
  token; Qwen text serializes `(x,y)`.
- Real `us-central1` shard-000000 validation on 2026-07-16 covered 11,447
  annotations / 418,222 points. Only 22 point pairs had both raw coordinates
  in `[0,1]`; 418,200 had at least one coordinate above 1, and a few annotations
  were slightly negative. Keep the source scale explicit and clamp after
  conversion rather than inferring the schema from observed values.
- LLaVA-OV1.5 has no structured point field in the mirrored record schema. A
  same-region first-shard scan of all 159 active configs covered 308,563 records
  / 6,529,858 conversation turns and found no Molmo-style `<point>`/`<points>`
  target. Visual7W “pointing” examples in this mirror are textual multiple
  choice; arrow/needle questions and ordinary uses of the word “point” are not
  coordinate supervision. Treat this as broad config coverage, not an
  exhaustive scan of all 22M source rows.
- Dense PixMo annotations can exceed the Stage-2 `max_txt_length=256` budget
  (a verified shard example has 165 points / 330 loc tokens). The generic text
  truncation can therefore cut a multi-point answer between its y/x tokens.
  This is separate from coordinate normalization and still needs a pair-aware
  truncation, sampling, or drop policy before treating all dense targets as
  well-formed.

## Open Images Grounding Data

- The 2026-07-16 mirror is complete in `us-central1` and `us-east5`: both
  datasets have all 16 prefix commits and root `_SUCCESS` markers. The
  `asia-northeast1-b` replica is still in progress while a Spot `v6e-8` capacity
  request retries; do not treat it as complete based on visible shards. In each
  region, the physical train roots are
  `gs://kmh-gcp-${ZONE_SHORT}/data/openimages-detection/image_records_wds/train`
  and
  `gs://kmh-gcp-${ZONE_SHORT}/data/openimages-relationships/image_records_wds/train`.
  Both use schema `openimages_grounding_v1` and canonical decoded-image
  absolute `xyxy` boxes.
- `beifen-Paligemma` aliases `openimages-detection[-train]` to the detection
  root. Stage 1 expands every box into a short class-word/phrase target, includes
  an available official attribute with 50% probability, and conditions on
  either location tokens or a raster box with equal probability. Drawn boxes
  sample red, green, or blue uniformly.
- Aliases `openimages-relationship(s)[-train]` map to the relationships root.
  Stage 3 consumes uploader-produced structured subject-predicate-object data;
  it never parses free-form answers to recover roles. Both boxes use the same
  representation per example--coordinates or drawn boxes, 50/50--and the two
  drawn colors are distinct RGB choices without a fixed subject color. Prompt
  sampling uses short variants 80% of the time and explicit role-anchor variants
  20% of the time. The target is a mechanically rendered single SPO sentence.
- Global finalization requires exactly `1,743,042` detection images and
  `14,610,229` boxes, plus `110,405` relationship images and `235,245`
  retained relationships (`at`: `23,524`). The relationship filter signature is
  `17c4db8c0a12483891a38f1a99a12952e942d57b30f8572790321a6378aef032`.
- Before starting training in any region, require `_SUCCESS` at **both** physical
  roots and validate those summaries. The loader resolves and caches the shard
  glob at startup, so shards appearing later will not repair an already-started
  partial stream.

## Checkpoint Transaction

For a training checkpoint to count as complete:

1. Each process writes pending dataloader state.
2. The model/optimizer checkpoint completes using the execution model's correct
   Orbax strategy.
3. Dataloader sidecars are finalized under that checkpoint.
4. Only then is the completion marker logged.

Checkpoint discovery must use the final model completion marker, never a
`Saving` line or sidecar path. In JIT/HSDP code, save global sharded arrays with
all processes participating; do not `process_allgather` the whole TrainState.
In the current pmap path, a replicated local replica can use a process-0 host
write. Re-evaluate this distinction if a checkout changes execution model.

## Curriculum And Evaluation

- A same-stage resume restores full state. A stage-boundary transition can be a
  params-only restore with a fresh optimizer and may require shape adaptation
  before sharding. Assert the restored global step rather than inferring it.
- Always save the stage-boundary checkpoint, even when checkpoint cadence does
  not divide the stage length.
- A final-eval-only run should restore model state without constructing or
  restoring the original training dataloader. This allows evaluation on a
  different compatible topology.
- An eval checkpoint still has to be local to the selected region. Copy it
  deliberately or pin the job; do not rely on a remote bucket read.
- The default Stage-3 final eval in both `beifen-Paligemma` and
  `PaliGemma-baseline` includes the original 2020 single-page DocVQA validation
  split (`5,349` questions) and xAI RealWorldQA test (`765` questions). Both
  evaluators require the exact expected number of unique and scored predictions;
  partial WDS roots are errors. The baseline JIT/HSDP path keeps these WDS
  loaders at `num_workers=0` so its synchronized exact-count schedule remains
  globally deterministic.
- DocVQA uses the question plus `Answer the question using a single word or
  phrase.`, generates at most 32 tokens, and reports case-insensitive ANLS as
  the primary 0--100 metric (best accepted answer, character Levenshtein,
  strict normalized-distance cutoff `<0.5`). Exact accuracy is secondary.
  Current Stage-3 training already includes DocVQA-train through the OV1.5
  grouped stream, so report this as standard in-domain supervised evaluation,
  not zero-shot document generalization.
- RealWorldQA questions already contain their output-format instruction. Feed
  that text unchanged; do not add another prompt. Score A--D questions with the
  public lmms-eval ranked choice extractor and other answers with lowercased,
  trimmed exact match (prediction may drop one terminal period). The official
  images are CC BY-ND 4.0; preserve image bytes and xAI attribution.
- Zone-local eval roots are
  `gs://kmh-gcp-${ZONE}/data/vlm_eval_benchmarks/{docvqa,realworldqa}`. Require
  each root's verified `_SUCCESS` marker before scheduling final eval. Mirror
  only DocVQA validation and RealWorldQA test; DocVQA test has hidden gold and
  its official download terms still apply despite any convenience mirror's
  dataset-card license.
- The 2026-07-16 DocVQA/RealWorldQA mirrors are complete and marker-verified in
  `us-central1`, `us-east5`, and `asia-northeast1-b`. A replica is usable only
  when both benchmark roots have a verified `_SUCCESS` marker; visible shards
  without that final commit marker are still partial data.

## Before Changing Training Code

Identify which concern is actually in scope: model semantics, mesh/batch
semantics, data stream, checkpoint transaction, curriculum transition, or final
evaluation. Test that concern with the smallest local or remote smoke that can
exercise the real path, then inspect logs and produced state rather than treating
successful process exit as sufficient proof.
