# VLM Data And Benchmarks

Owns dataset uploads, adapter source schemas, bbox and point coordinates, and
benchmark mirrors for `jax_llava`, `PaliGemma-baseline`, and `beifen-Paligemma`.
Training, checkpointing, and resume are `vlm_training.md`; which benchmark
number to report is `vlm_metrics.md`; the checkout map is `projects.md`.

Chapter 1 is what the coordinates, source schemas, and benchmarks are; Chapter 2
is uploading, validating, and mirroring data; Chapter 3 is the traps that load
and train without an error.

---

## Chapter 1 — What The Coordinates, Schemas, And Benchmarks Are

### Bounding boxes

**The only internal bbox representation is absolute `xyxy` on the decoded
original-image canvas, carried with an explicit `(width, height)`.** Every dataset
adapter declares its source schema; never infer `xyxy` versus `xywh` from the
numeric values.

- Convert the canonical box to Qwen `0..1023` coordinates or PaliGemma `<loc>` tokens only after applying the exact image resize/letterbox transform.
- A drawn raster box and the emitted text coordinates must consume the same canonical box.

### Points

**A PixMo-Points point is `(x, y)` on an explicit `0..100` source canvas
(`point_scale=100` in the official Molmo adapter), not a `[0,1]` fraction and not
decoded-image pixels.**

1. Convert the percentages to the decoded-image canvas, keeping the source scale explicit.
2. Apply the exact stretch/letterbox transform.
3. Quantize to `0..1023`, clamping after conversion.

PaliGemma loc text serializes each point as the `y` token then the `x` token;
Qwen text serializes `(x,y)`.

### Audited source schemas

**Take a source schema from an audit, never from observed values:** shard
validation found PixMo values far outside `[0,1]` and slightly negative outliers.
Audit evidence and per-config lists are in `archive/audits/`.

| Source | Schema |
|---|---|
| Visual Genome regions | Absolute `xywh` |
| Legacy `jxu124/refcoco` WDS | Untagged absolute `xyxy`, despite an uploader comment claiming `xywh` |
| Existing RefCOCOg train WDS and local eval JSON | Explicit/legacy COCO `xywh` |
| Hugging Face RefCOCOg source | `xyxy` |
| PixMo-Points | `(x, y)` on the `0..100` canvas above |
| LLaVA-OV1.5 | Several configs carry normalized textual bboxes. There is no structured point field in the mirrored record schema, and a broad same-region config scan found no Molmo-style `<point>`/`<points>` targets; Visual7W "pointing" examples are textual multiple choice. That is broad config coverage, not an exhaustive scan of all source rows |
| Open Images detection and relationships | Schema `openimages_grounding_v1`, canonical decoded-image absolute `xyxy` |

### Open Images grounding aliases

**`beifen-Paligemma` aliases `openimages-detection[-train]` to the detection root
and `openimages-relationship(s)[-train]` to the relationships root.** The
physical roots are in Chapter 2.

| Alias | Stage | What the stage builds |
|---|---|---|
| `openimages-detection[-train]` | 1 | Expands every box into a short class-word/phrase target, includes an available official attribute with 50% probability, and conditions on location tokens or a raster box with equal probability. Drawn boxes sample red, green, or blue uniformly. |
| `openimages-relationship(s)[-train]` | 3 | Consumes uploader-produced structured subject-predicate-object data and never parses free-form answers to recover roles. Both boxes use one representation per example, coordinates or drawn boxes at 50/50, and the two drawn colors are distinct RGB choices without a fixed subject color. Prompts use short variants 80% of the time and explicit role-anchor variants 20%. The target is a mechanically rendered single SPO sentence. |

### Final-eval benchmarks

**DocVQA and RealWorldQA are the default Stage-3 final eval in both
`beifen-Paligemma` and `PaliGemma-baseline`; MMStar is a final eval in
`PaliGemma-baseline` Stage 3 and `jax_llava` Stage 2.**

| | DocVQA | RealWorldQA | MMStar |
|---|---|---|---|
| Split, size | Original 2020 single-page validation, `5,349` questions | xAI test, `765` questions | `1,500` rows |
| Prompt, budget | The question plus `Answer the question using a single word or phrase.`; at most 32 generated tokens | The question already carries its output-format instruction: feed it unchanged and add no other prompt | 512 input tokens, 8 decode tokens, zero loader workers |
| Score | Case-insensitive ANLS as the primary 0--100 metric (best accepted answer, character Levenshtein, strict normalized-distance cutoff `<0.5`); exact accuracy is secondary | A--D questions through the public lmms-eval ranked choice extractor; other answers by lowercased, trimmed exact match (the prediction may drop one terminal period) | Official prefix-only scorer plus category/axis metrics |
| Terms | The official download terms apply, whatever a convenience mirror's dataset card says | Images are CC BY-ND 4.0: preserve image bytes and xAI attribution | Upstream redistribution terms are unreviewed (Chapter 2) |

### MMStar ownership

**MMStar logic lives in the two internal suites, and training repos call the
benchmark adapter instead of copying either implementation.**
`one-benchmark-suite` owns the prompt, exact-count schedule, official
prefix-only scorer, and category/axis metrics. `one-dataset-suite` owns artifact
construction and the shared commit contract.

---

## Chapter 2 — Uploading, Validating, And Mirroring Data

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

| Root | Path | Rule |
|---|---|---|
| Open Images detection train | `gs://kmh-gcp-${ZONE_SHORT}/data/openimages-detection/image_records_wds/train` | Expected global counts are in `archive/audits/` |
| Open Images relationships train | `gs://kmh-gcp-${ZONE_SHORT}/data/openimages-relationships/image_records_wds/train` | Expected global counts and the relationship filter signature are in `archive/audits/` |
| Eval benchmarks | `gs://kmh-gcp-${ZONE}/data/vlm_eval_benchmarks/{docvqa,realworldqa,mmstar}` | Zone-local. Mirror only DocVQA validation and RealWorldQA test; DocVQA test has hidden gold |

The baseline JIT/HSDP path keeps the DocVQA and RealWorldQA WDS loaders at
`num_workers=0`, so its synchronized exact-count schedule stays globally
deterministic.

### Keep the MMStar artifact and its pins honest

**The existing MMStar artifact is read through a narrow compatibility exception,
and that exception is not a license attestation.**

- The artifact uses a pre-publisher thin manifest. Read compatibility is limited to its exact committed marker fingerprint, while revision, split, count, payload SHA/MD5, and object metadata still validate.
- Upstream redistribution terms remain unreviewed, so do not publish a new mirror or publisher spec.
- Training checkouts pin both internal suites in `requirements-eval.txt`. The package versions stay stable across commits, so verify the installed direct-URL commit rather than trusting the version string.

---

## Chapter 3 — Data Traps

**Each of these loads and trains without an error, so only the rule catches it.**

| Trap | Why it is silent | Rule |
|---|---|---|
| Shards appear after a job started | Loaders resolve and cache the shard glob at startup | Later shards will not repair an already-started partial stream; validate `_SUCCESS` before launch |
| A partial eval root | It looks like a smaller eval | The DocVQA and RealWorldQA evaluators require the exact expected number of unique scored predictions, so a partial WDS root is an error |
| A loader path ignores `dataset.coord_format` | A config saying `qwen` is not enough if an iterator silently calls the default `loc_tokens` path | Every stateful and legacy loader path forwards `dataset.coord_format` to preprocessing |
| LLaVA-OV1.5 normalized textual bboxes | A broad conversion also rewrites unrelated math arrays and graph-coordinate pairs | Keep the conversion hard-whitelisted, and rewrite questions, answers, and any coordinate-format prose together |
| Dense PixMo annotations exceed the Stage-2 `max_txt_length=256` budget | Generic text truncation cuts a multi-point answer between its `y` and `x` tokens | Separate from coordinate normalization, and still open: dense targets need a pair-aware truncation, sampling, or drop policy before they count as well-formed |
| Multi-box supervision is scarce | True multi-box exposure is sparse and mostly comes from Sherlock/SVIT | For CVBench-like colored multi-region training, the practical external sources are ViP-LLaVA Visual7W/VG Relations, then SPHINX-V MDVP VCR and relationship subsets. Check their non-commercial/research licenses before mirroring |
