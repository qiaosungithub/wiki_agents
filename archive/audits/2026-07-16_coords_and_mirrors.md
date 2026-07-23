# Audit Snapshot: Coordinates And Data Mirrors (2026-07-16)

Dated evidence behind the rules in `vlm_data.md`. Counts and completion status
describe the state on 2026-07-16; re-verify mirrors live (`_SUCCESS` markers)
before relying on them.

## Textual bbox audit (LLaVA-OV1.5 configs)

Scan of all 159 active LLaVA-OV1.5 configs confirmed normalized textual bboxes
in `coco`, `sherlock`, `vg`, `vision_oritented`, `llava_cot_100k`, and the ten
`svit-part-*` configs. Most use `[x1,y1,x2,y2]`; COCO also uses prose such as
`between coordinates (x1,y1) and (x2,y2)`.

## PixMo-Points shard validation

Real `us-central1` shard-000000 validation covered 11,447 annotations /
418,222 points. Only 22 point pairs had both raw coordinates in `[0,1]`;
418,200 had at least one coordinate above 1, and a few annotations were
slightly negative. This is the evidence for the explicit `0..100` source-scale
rule. A verified dense shard example has 165 points / 330 loc tokens,
exceeding the Stage-2 `max_txt_length=256` budget.

## OV1.5 structured-point scan

A same-region first-shard scan of all 159 active configs covered 308,563
records / 6,529,858 conversation turns and found no Molmo-style
`<point>`/`<points>` target. Visual7W "pointing" examples in this mirror are
textual multiple choice. Broad config coverage, not an exhaustive scan of all
22M source rows.

## Open Images finalization counts

Global finalization requires exactly `1,743,042` detection images and
`14,610,229` boxes, plus `110,405` relationship images and `235,245` retained
relationships (`at`: `23,524`). The relationship filter signature is
`17c4db8c0a12483891a38f1a99a12952e942d57b30f8572790321a6378aef032`.

Mirror status on 2026-07-16: complete in `us-central1` and `us-east5` (all 16
prefix commits plus root `_SUCCESS`); the `asia-northeast1-b` replica was still
in progress while a Spot `v6e-8` capacity request retried.

## DocVQA / RealWorldQA mirrors

On 2026-07-16 the DocVQA/RealWorldQA mirrors were complete and marker-verified
in `us-central1`, `us-east5`, and `asia-northeast1-b`.
