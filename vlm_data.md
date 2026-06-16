# VLM Data And Dataset Locality

Use this guide for VLM dataset recipes, upload/count/report jobs, same-region
GCS access, and dataset-scale notes. For model and curriculum rules, read
`vlm_training.md`. For checkpoint and dataloader resume state, read
`vlm_checkpointing.md`.

## SFT Dataset Loader Notes

- Stage-2/SFT mixes use shuffled image-level LLaVA-OV1.5 plus VQAv2, OKVQA,
  A-OKVQA, OCRVQA, GQA, TextCaps, Visual Genome QA, Visual Genome detection,
  and RefCOCO.
- Dataset aliases for the four LLaVA-1.5 missing SFT datasets are registered in
  `utils/data_util.py` as `okvqa-train`, `aokvqa-train`, `ocrvqa-train`, and
  `refcoco-train`.
- OKVQA and OCRVQA use the short-answer VQA prompt:
  `Answer the question using a single word or phrase.`
- A-OKVQA expands each grouped QA into four cyclic multiple-choice rotations;
  the target is the correct option letter. This preserves the LLaVA-1.5
  reported ~66K A-OKVQA SFT scale.
- OCRVQA is uploaded as the full 801K-QA train split, but the SFT recipe samples
  it near the LLaVA-1.5 ~80K scale through mix weights.
- RefCOCO stores COCO absolute `xywh` boxes and grouped refs per image. Training
  expands one phrase-to-box item per ref and formats targets as `<loc....>`
  tokens using the same `format_detection_prompt()` used by RefCOCOg eval.
- Grounded detection training and RefCOCOg eval share this instruction:
  `Locate the region described by this phrase: ...` followed by
  `Output exactly four location tokens, indicating up, left, down, right.`
- `configs/finetune_config.yml` samples 10 Visual Genome detection regions per
  image via `dataset.genome_det_regions_per_image: 10`.
- Online VQAv2 eval may be capped at 10% with
  `eval.online_vqav2_sample_fraction = 0.1`; final eval uses the configured full
  `eval.vqav2_num_samples` unless explicitly overridden.
- MMBench uses `eval.mmbench_max_txt_len=512` and shortens hints/questions/options
  structurally before raw truncation so answer choices and the final option-letter
  instruction survive.

## Pretrain Efficiency Notes

- On 2026-06-10, CC12M text length was sampled from same-zone GCS shards. With
  Gemma3 tokenizer and actual caption prompt sampler, mean was 94.71 tokens,
  median 96, p75 124, p90 148, p95 162, p99 229, max 410.
- Truncation at 64 tokens affects 69.67% of sampled examples and retains 61.09%
  of tokens; 128 affects 20.73% and retains 93.61%; 160 affects 5.73% and
  retains 97.73%; 256 affects 0.47% and retains 99.77%.
- Recommendation: do not use stage-1 `max_txt_length=64` when CC12M has
  meaningful weight. `128` is a reasonable speed/coverage tradeoff, while `160`
  preserves nearly all sampled text.
- Perception Encoder scale should be recorded as samples/examples seen, not
  unique dataset size and not text tokens. The paper reports 58B samples seen
  for B/L and 86B for G over repeated long schedules.

## Beifen Dataset Operations

- Never move dataset payloads across regions. Upload/report jobs should run on a
  TPU VM in the same region/zone family as the target bucket.
- Dataset counting must follow the same rule: use `summary.json` or manifest
  sidecars when they answer the question. If exact question counts require
  opening tar shards, run the counter on a TPU VM in the bucket's same
  region/zone-family; do not stream GCS tar payloads to a control VM in a
  different region.
- Bucket convention: `gs://kmh-gcp-${ZONE_SHORT}/data`, where `ZONE_SHORT` is
  derived from the VM zone.
- Keep download/cache/staging under `/dev/shm`; do not stage images on NFS, SSD,
  or home directories.
- Upload datasets as tar shards only, not scattered single-image files.
- For datasets with multiple questions/refs per image, store one image record
  with grouped `qas` or `refs`.
- `upload_vlm_sft_missing.sh` and `VLM-SFT-Missing-upload.py` upload OKVQA,
  A-OKVQA, OCRVQA, and RefCOCO. The launcher enforces same-region bucket prefixes
  and `/dev/shm` cache roots.
- RefCOCO and RefCOCOg are different referring-expression datasets. RefCOCOg
  train is uploaded with `beifen/upload_refcocog_train.sh`, using
  Hugging Face `jxu124/refcocog` metadata plus same-region COCO train2014 tar
  shards. Run it from a same-region TPU VM; keep `TMP_ROOT` and `HF_HOME` under
  `/dev/shm`; output is
  `gs://kmh-gcp-${ZONE_SHORT}/data/refcocog/image_records_wds/train/shard-*.tar`.
  The uploader stores `bbox`/`bbox_xywh` as xywh and `bbox_xyxy` for audit.
- Verified upload counts per region:
  OKVQA train `8,998` image records / `9,009` QA / 5 shards;
  A-OKVQA train `16,540` image records / `17,056` QA / 9 shards;
  OCRVQA train `166,022` image records / `801,579` QA / 84 shards;
  RefCOCO train `16,994` image records / `42,404` refs / 9 shards;
  RefCOCOg train `21,899` image records / `42,226` refs / 11 shards
  in `us-central1`, `us-east5`, and `asia-northeast1-b`.
- LLaVA-OV1.5 config shards are mirrored in the three usual regions. AI2D has
  `25,281` image/conversation samples / 13 shards and expands to `33,849`
  assistant-answer training examples with current `expand_llava_sample`
  semantics. This AI2D question count was verified on a same-region
  `asia-northeast1-b` TPU VM reading `gs://kmh-gcp-asia-northeast1-b/...`;
  do not recompute it from a cross-region control VM.
- UReader is registered in `beifen-Paligemma` and `jax_llava` as one combined
  `ureader` alias over `ureader_tr`, `ureader_ocr`, `ureader_qa`,
  `ureader_chart`, `ureader_cap`, `ureader_ie`, and `ureader_kg`; the combined
  upload has `923,123` samples / 465 tar shards. Current `expand_llava_sample`
  expands UReader by assistant turn; exact expanded question counts should be
  computed only from a same-region TPU/VM if needed.
- `laion-400m` exists only under
  `gs://kmh-gcp-asia-northeast1-b/data/laion-400m/part-{00000..00127}/{00000..00282}.tar`.
  Dataset path resolution asserts `zone == "asia-northeast1-b"` when this alias
  is used, because it is intentionally not mirrored to `us-central1` or
  `us-east5`.
- Visual sanity reports use `run_vlm_data_visual_report.sh` and
  `VLM-Data-Visual-Report.py`; current us-central1 report is
  `reports/vlm_data_visual_report_us-central1_20260531T205902Z.html` and covers
  32 dataset entries with 3/3 samples and no warnings.

## Legacy Deep Dives In The Archive

Some older investigations are too long for this operational guide but remain
useful when debugging specific regressions. Search `project_agents_archive.md`
for these headings or phrases:

- `PaliGemma SFT From Pretrain` for stagedir-based SFT launch, KNN eval, and
  pretrain-to-SFT compatibility notes.
- `valid_tokens_per_sample` for the 2026-05-30/06-01 SFT length-drift audits.
- `llava-ov-1.5-instruct-image-shuffled-v1` for the image-level shuffle build,
  region completion notes, and why the v2 buffer experiment should not become
  the default.
- `ImageNet kNN / Remote Environment Notes` for TFDS/PCA whitening history and
  same-zone eval rerun details.
