# VLM Data And Benchmarks

Read this when uploading a dataset, auditing an adapter, handling bbox/point
coordinates, or preparing a benchmark mirror for the VLM checkouts. Training and
resume are [knowledge/codebases/vlm-training.md](vlm-training.md); reporting a score is
[knowledge/codebases/vlm-metrics.md](vlm-metrics.md). Validating replicas, uploading, and mirroring
are procedures:
[vlm-data-operations skill](../../harness/skills/vlm-data-operations/SKILL.md).

Chapter 1 is what the datasets, adapters, and coordinates are; Chapter 2 is the
handling gotchas.

---

## Chapter 1 — What The Datasets, Adapters, And Coordinates Are

### Coordinate conventions

**Internally a box is absolute `xyxy` on the decoded original-image canvas with
an explicit `(width, height)`; a point is `(x, y)` on its declared source
canvas.** Convert to Qwen `0..1023` or PaliGemma `<loc>` only after the exact
resize/letterbox transform, then clamp. A drawn raster box and the emitted text
coordinates must consume the same canonical box. PaliGemma loc text serializes
`y` then `x`; Qwen serializes `(x,y)`.

### Audited source schemas

**Declare each source schema; never infer one from observed values** — PixMo
validation found points far outside `[0,1]`, and slightly negative. Per-config
lists and evidence in [archive/audits/](../../archive/audits/):

| Source | Schema |
|---|---|
| Visual Genome regions | absolute `xywh` |
| legacy `jxu124/refcoco` WDS | untagged absolute `xyxy`, despite an uploader comment claiming `xywh` |
| existing RefCOCOg train WDS, local eval JSON | explicit/legacy COCO `xywh` |
| Hugging Face RefCOCOg source | `xyxy` |
| PixMo-Points | `(x, y)` on an explicit `0..100` canvas (`point_scale=100` in the official Molmo adapter) — not `[0,1]` fractions, not decoded pixels. Convert those percentages to the decoded-image canvas *first*, keeping the source scale explicit, before the stretch/letterbox transform |
| LLaVA-OV1.5 | no structured point field; a broad config scan found no Molmo-style `<point>`/`<points>` target (its Visual7W "pointing" items are textual multiple choice). Config coverage, not an exhaustive row scan |
| Open Images detection, relationships | `openimages_grounding_v1`, canonical decoded-image absolute `xyxy` |

### Open Images grounding aliases

**`beifen-Paligemma` aliases the Open Images grounding data as
`openimages-detection` (Stage 1) and `openimages-relationship(s)` (Stage 3),
both optionally `-train`.**

| Alias | Stage semantics |
|---|---|
| `openimages-detection` | Stage 1 expands every box into a short class-word/phrase target, adds an available official attribute with 50% probability, and conditions on location tokens or a raster box with equal probability. Drawn boxes sample red/green/blue uniformly. |
| `openimages-relationship(s)` | Stage 3 consumes uploader-produced structured subject-predicate-object data and never parses free-form answers to recover roles. Both boxes share one representation per example (coordinates or drawn, 50/50); the two drawn colors are distinct RGB with no fixed subject color. Prompts are short variants 80% of the time, explicit role-anchor variants 20%. Target: a mechanically rendered single SPO sentence. |

### The two final-eval benchmarks

**DocVQA and RealWorldQA are the default Stage-3 final eval in `beifen-Paligemma`
and `PaliGemma-baseline`.** Scoring definitions:

| | DocVQA | RealWorldQA |
|---|---|---|
| Split, size | 2020 single-page validation, `5,349` questions | xAI test, `765` questions |
| Prompt | question + `Answer the question using a single word or phrase.`, max 32 generated tokens | already carries its output-format instruction: feed unchanged, never prepend another |
| Score | case-insensitive ANLS 0--100 (best accepted answer, character Levenshtein, strict normalized-distance cutoff `<0.5`); exact accuracy secondary | A--D through the public lmms-eval ranked choice extractor, otherwise lowercased trimmed exact match (the prediction may drop one terminal period) |
| Licence | official download terms | images CC BY-ND 4.0: preserve bytes and xAI attribution |

---

## Chapter 2 — Data Gotchas

| Rule | Why |
|---|---|
| Every stateful and legacy loader path must forward `dataset.coord_format` | A config saying `qwen` is not enough if some iterator silently takes the default `loc_tokens` path |
| Keep the LLaVA-OV1.5 normalized-textual-bbox conversion hard-whitelisted | So unrelated math arrays and graph-coordinate pairs stay untouched; rewrite questions, answers, and coordinate-format prose together |
| Dense PixMo answers can exceed the Stage-2 `max_txt_length=256` budget | Generic truncation then cuts a multi-point answer between its y and x tokens. Still open: dense targets need a pair-aware truncation, sampling, or drop policy |
| Multi-box exposure is sparse in the mixes we train on | Sourcing colored multi-region supervision (CVBench-like) means reaching outside them, and the candidates are research releases: check the non-commercial/research license before mirroring one |
