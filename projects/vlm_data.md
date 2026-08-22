# VLM Data And Benchmarks

Read this when uploading a dataset, auditing an adapter, handling bbox/point
coordinates, or preparing a benchmark mirror for the VLM checkouts. Training and
resume are `vlm_training.md`; reporting a score is `vlm_metrics.md`.

## Replica Validation Rule

**A regional replica is usable only when every physical root carries a verified
`_SUCCESS` marker and its summary/size/checksum metadata validates.** Shards
visible without that marker are partial data, and shards arriving later cannot
repair a started stream — loaders resolve and cache the shard glob at startup.
**Never infer completeness from a listing, and never trust a remembered mirror
status**: re-verify live before scheduling.

**A metro appearing in `g3_env`'s cell->data map does NOT mean its data is
complete — verify the stage-1 datasets per cell before choosing a landing
cell.** The map records where a replica is *intended*, not where it is whole.
Measured: `is-d` (cbf) and `li-d` (lpp) carry the full stage-1 set
(laion-aesthetic, BLIP3o-Short, visual_genome, openimages-detection) with
`data/_SUCCESS`; `go-d` (cmh) is a PARTIAL replica — it has visual_genome and
the Qwen model but is MISSING laion-aesthetic / BLIP3o-Short /
openimages-detection and has no `data/_SUCCESS`, so a from-scratch stage-1 run
launched there fails on a missing dataset. Consequence for placement: an
accelerator whose only co-located candidate cells sit in cmh is not actually
ready without a data copy first. Confirm `_SUCCESS` plus each required dataset
dir on the specific data cell (`fileutil ls /cns/<cell>-d/home/qiaos/data`)
before committing a job there.

## Dataset Uploads

**Upload with `beifen/upload_data.py` plus `beifen/data_upload/datasets.json`,
queued through the job scheduler**; the old per-dataset launchers are legacy and
their adapters refuse direct use. Only worker 0 writes, every payload/cache/tmp
path stays under `/dev/shm`, and **Type 1 locality is enforced here too**:
derive it from VM metadata, restrict payload access to the matching
`gs://kmh-gcp-${ZONE_SHORT}/data`, fail closed otherwise. **Payloads are
deterministic tar shards, never scattered records** — only bounded
manifest/summary/progress/commit/checksum/`_SUCCESS` metadata is loose.

## Coordinates

**Internally a box is absolute `xyxy` on the decoded original-image canvas with
an explicit `(width, height)`, and a point is `(x, y)` on its declared source
canvas.** Convert to Qwen `0..1023` or PaliGemma `<loc>` only after the exact
resize/letterbox transform, then clamp; a drawn raster box and the emitted text
coordinates must consume the same canonical box. PaliGemma loc text serializes
`y` then `x`, Qwen serializes `(x,y)`.

| Rule | Why |
|---|---|
| **Declare each source schema; never infer one from observed values** | PixMo validation found points far outside `[0,1]`, and slightly negative |
| **Every stateful and legacy loader path must forward `dataset.coord_format`** | A config saying `qwen` is not enough if some iterator silently takes the default `loc_tokens` path |
| **Keep the LLaVA-OV1.5 normalized-textual-bbox conversion hard-whitelisted** | So unrelated math arrays and graph-coordinate pairs stay untouched; rewrite questions, answers, and coordinate-format prose together |
| **Dense PixMo answers can exceed the Stage-2 `max_txt_length=256` budget** | Generic truncation then cuts a multi-point answer between its y and x tokens. Still open: dense targets need a pair-aware truncation, sampling, or drop policy |
| Multi-box exposure is sparse in the mixes we train on | Sourcing colored multi-region supervision (CVBench-like) means reaching outside them, and the candidates are research releases — **check the non-commercial/research license before mirroring one** |

Audited schemas; per-config lists and evidence in `../archive/audits/`:

| Source | Schema |
|---|---|
| Visual Genome regions | absolute `xywh` |
| legacy `jxu124/refcoco` WDS | untagged absolute `xyxy`, despite an uploader comment claiming `xywh` |
| existing RefCOCOg train WDS, local eval JSON | explicit/legacy COCO `xywh` |
| Hugging Face RefCOCOg source | `xyxy` |
| PixMo-Points | `(x, y)` on an explicit `0..100` canvas (`point_scale=100` in the official Molmo adapter) — not `[0,1]` fractions, not decoded pixels. Convert those percentages to the decoded-image canvas *first*, keeping the source scale explicit, before the stretch/letterbox transform |
| LLaVA-OV1.5 | no structured point field; a broad same-region config scan found no Molmo-style `<point>`/`<points>` target (its Visual7W "pointing" items are textual multiple choice). Broad config coverage, not an exhaustive row scan |
| Open Images detection, relationships | `openimages_grounding_v1`, canonical decoded-image absolute `xyxy` |

## Open Images Grounding Data

**Both physical train roots are per-region, and each must pass replica
validation before training in that region:**
`gs://kmh-gcp-${ZONE_SHORT}/data/openimages-{detection,relationships}/image_records_wds/train`.
Expected global counts and the relationship filter signature are in
`../archive/audits/`. `beifen-Paligemma` aliases them, both optionally `-train`:

| Alias | Stage semantics |
|---|---|
| `openimages-detection` | Stage 1 expands every box into a short class-word/phrase target, adds an available official attribute with 50% probability, and conditions on location tokens or a raster box with equal probability. Drawn boxes sample red, green, or blue uniformly. |
| `openimages-relationship(s)` | Stage 3 consumes uploader-produced structured subject-predicate-object data and **never parses free-form answers to recover roles**. Both boxes share one representation per example (coordinates or drawn, 50/50); the two drawn colors are distinct RGB choices with no fixed subject color. Prompts are short variants 80% of the time, explicit role-anchor variants 20%. The target is a mechanically rendered single SPO sentence. |

## Evaluation Benchmarks

**Zone-local eval roots are
`gs://kmh-gcp-${ZONE}/data/vlm_eval_benchmarks/{docvqa,realworldqa}`; apply the
replica validation rule to each before scheduling a final eval**, and mirror
only the two splits below — DocVQA test has hidden gold, and its official
download terms bind whatever a convenience mirror's dataset card says. Together
they are the default Stage-3 final eval in `beifen-Paligemma` and
`PaliGemma-baseline`; **both evaluators demand the exact expected count of
unique scored predictions**, so a partial WDS root is an error rather than a
smaller eval, and the baseline JIT/HSDP path pins these loaders to
`num_workers=0` to keep its exact-count schedule globally deterministic.

| | DocVQA | RealWorldQA |
|---|---|---|
| Split, size | 2020 single-page validation, `5,349` questions | xAI test, `765` questions |
| Prompt | question + `Answer the question using a single word or phrase.`, max 32 generated tokens | already carries its output-format instruction: feed unchanged, never prepend another |
| Score | case-insensitive ANLS 0--100 (best accepted answer, character Levenshtein, strict normalized-distance cutoff `<0.5`); exact accuracy secondary | A--D through the public lmms-eval ranked choice extractor, otherwise lowercased trimmed exact match (the prediction may drop one terminal period) |
| Licence | official download terms | images CC BY-ND 4.0: preserve bytes and xAI attribution |
