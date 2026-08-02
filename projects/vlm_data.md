# VLM Data And Benchmarks

Read this when uploading datasets, writing or auditing dataset adapters,
handling bbox/point coordinates, or preparing evaluation benchmark mirrors for
the VLM checkouts. Training, checkpointing, and resume semantics are in
`vlm_training.md`.

## Replica Validation Rule

A regional data replica is usable only when every physical root has a verified
`_SUCCESS` marker and the summary/size/checksum metadata validates. Visible
shards without the final commit marker are partial data. Loaders resolve and
cache the shard glob at startup, so shards appearing later will not repair an
already-started partial stream. Never infer completeness from listing output,
and never record mirror status in memory — re-verify live before scheduling.

## Dataset Uploads

- Use `beifen/upload_data.py` with `beifen/data_upload/datasets.json`; old
  per-dataset launchers are legacy and retained adapters refuse direct use.
- Queue through the job scheduler. Only worker 0 writes, and all payload/cache/tmp
  paths stay under `/dev/shm`.
- For Kaiming Group Code (Type 1), derive locality from VM metadata and restrict
  GCS payload access to the matching `gs://kmh-gcp-${ZONE_SHORT}/data`; fail
  closed otherwise.
- Payload objects are deterministic tar shards, never scattered records. Only
  bounded manifest/summary/progress/commit/checksum/`_SUCCESS` metadata is loose.

## Bounding-Box Coordinate Invariant

- The only internal bbox representation is absolute `xyxy` on the decoded
  original-image canvas, accompanied by an explicit `(width, height)`. Dataset
  adapters must declare their source schema; never infer `xyxy` versus `xywh`
  from numeric values.
- Convert from the canonical box to Qwen `0..1023` coordinates or PaliGemma
  `<loc>` tokens only after applying the exact image resize/letterbox transform.
  Drawing a raster box and emitting text coordinates must consume the same
  canonical box.
- Audited source schemas: Visual Genome regions are absolute `xywh`; legacy
  `jxu124/refcoco` WDS stored untagged absolute `xyxy` despite an uploader
  comment claiming `xywh`; the existing RefCOCOg train WDS and local eval JSON
  store explicit/legacy COCO `xywh`; the Hugging Face RefCOCOg source itself is
  `xyxy`. Several LLaVA-OV1.5 configs additionally carry normalized textual
  bboxes; keep their conversion hard-whitelisted so unrelated math arrays and
  graph-coordinate pairs are untouched, and rewrite questions and answers plus
  any coordinate-format prose together. Audit evidence and per-config lists are
  in `archive/audits/`.
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
  `0..1023`. Keep the source scale explicit and clamp after conversion; shard
  validation confirmed values far outside `[0,1]` and slightly negative
  outliers, so never infer the schema from observed values.
- PaliGemma loc text serializes each point as `y` token then `x` token; Qwen
  text serializes `(x,y)`.
- LLaVA-OV1.5 has no structured point field in the mirrored record schema, and a
  broad same-region config scan found no Molmo-style `<point>`/`<points>`
  targets; Visual7W "pointing" examples are textual multiple choice. Treat this
  as broad config coverage, not an exhaustive scan of all source rows.
- Dense PixMo annotations can exceed the Stage-2 `max_txt_length=256` budget, so
  generic text truncation can cut a multi-point answer between its y/x tokens.
  This is separate from coordinate normalization and still needs a pair-aware
  truncation, sampling, or drop policy before treating all dense targets as
  well-formed.

## Open Images Grounding Data

- Physical train roots in each region are
  `gs://kmh-gcp-${ZONE_SHORT}/data/openimages-detection/image_records_wds/train`
  and
  `gs://kmh-gcp-${ZONE_SHORT}/data/openimages-relationships/image_records_wds/train`.
  Both use schema `openimages_grounding_v1` and canonical decoded-image absolute
  `xyxy` boxes. Before training in any region, apply the replica validation rule
  to **both** roots; expected global counts and the relationship filter
  signature are in `archive/audits/`.
- `beifen-Paligemma` aliases `openimages-detection[-train]` to the detection
  root. Stage 1 expands every box into a short class-word/phrase target, includes
  an available official attribute with 50% probability, and conditions on either
  location tokens or a raster box with equal probability. Drawn boxes sample
  red, green, or blue uniformly.
- Aliases `openimages-relationship(s)[-train]` map to the relationships root.
  Stage 3 consumes uploader-produced structured subject-predicate-object data;
  it never parses free-form answers to recover roles. Both boxes use the same
  representation per example--coordinates or drawn boxes, 50/50--and the two
  drawn colors are distinct RGB choices without a fixed subject color. Prompt
  sampling uses short variants 80% of the time and explicit role-anchor variants
  20% of the time. The target is a mechanically rendered single SPO sentence.

## Evaluation Benchmarks

- Zone-local eval roots are
  `gs://kmh-gcp-${ZONE}/data/vlm_eval_benchmarks/{docvqa,realworldqa}`. Apply
  the replica validation rule to each root before scheduling final eval. Mirror
  only DocVQA validation and RealWorldQA test; DocVQA test has hidden gold and
  its official download terms still apply despite any convenience mirror's
  dataset-card license.
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
