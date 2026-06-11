# VLM Training Memory

Shared memory for JAX LLaVA, PaliGemma-baseline, Beifen dataset operations, and related VLM reproduction work. Project-local `AGENTS.md` files remain authoritative for edits inside a checkout.

## Read Order

When working on VLM training code:

1. Read this shared memory.
2. Read the project-local `AGENTS.md` in the checkout you are editing.
3. For TPU launch/resume work, also read `tpu.md` and `xibo_monitor.md`.
4. For result logging, also read `spreadsheet_logging.md`.

The exact project-local source snapshots are preserved in
`project_agents_archive.md`.

## Active LLaVA-1.5 Reproduction Tracking

- Spreadsheet:
  `https://docs.google.com/spreadsheets/d/1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ/edit?gid=1146448969#gid=1146448969`.
- Rows 146-148 on gid `1146448969` contain the current reproduction-progress
  checkpoint. Row 147 is the LLaVA-1.5 7B target line; row 148 is the first
  init run.
- First init run: `CLIP-L @ 336 + gemma3-1B`, blip-3o pretrain, SFT mix of
  LLaVA-OV1.5, VQA, GQA, and TextCaps style data. WandB:
  `exalted-haze-9 | Sqa24's workspace | jax-llava`.
- Target metrics from row 147:
  MME-P `1511`, VQAv2 `78.5`, TextVQA `58.2`, MMBench `64.3`,
  POPE `84.2`, VStar `~48.7`, OCRBench `29.7`, MMVP `24.7`,
  CountBench `~47.0`, VisWiz `50.0`, SEED-Bench image `66.1`,
  ScienceQA-IMG `66.8`, and GQA `62.0`.
- POPE in row 148 is adversarial F1 (`pope_adversarial_f1_stage2_final=80`),
  not macro F1. The same final eval also logs macro F1 `82.58`.
- Non-original LLaVA-1.5-paper probes in the current sheet/report:
  VStar, OCRBench, MMVP, CountBench, RefCOCOg, and ImageNet KNN.
- First row-148 run data: stage 1 `blip3o-short`; stage 2 LLaVA-OV1.5,
  VQAv2, GQA train, TextCaps train, and Visual Genome QA with weights
  `[22, 0.4, 0.94, 0.022, 1.7]`.
- Current JAX LLaVA `remote_run_config.yml` changes stage 1 to `cc12m` and
  adds OKVQA, A-OKVQA, OCRVQA, Visual Genome detection, and RefCOCO to stage 2.
- Parsed v5p-64 throughput for first LLaVA-style curriculum jobs:
  stage 1 median `5.63` steps/s all points (`5.69` filtered >2 steps/s);
  stage 2 median `3.91` steps/s all points (`3.94` filtered >2 steps/s).

## Durable Pretrained Checkpoint Convention

- Shell helper `ltgcp <absolute_local_logdir>` maps `ltg(local_logdir)` from
  `gs://<regional-bucket>/qiao_zhicheng_hanhong_files/...` to
  `gs://<same-regional-bucket>/pretrained-ckpts/qiao_zhicheng_hanhong_files/...`
  and copies recursively.
- Buckets under `pretrained-ckpts/` are treated as durable and should not be
  cleaned with ordinary run logs. When a training job successfully finishes,
  mirror the latest final `checkpoint_<step>` into the same bucket's
  `pretrained-ckpts/qiao_zhicheng_hanhong_files/...` prefix.
- `jax_llava` and `beifen-Paligemma` checkpoint loaders should resolve
  `load_from_pretrained` params-only restores by first checking the normal
  zone-local bucket path, then the same-zone `pretrained-ckpts` fallback.
- xibo launch should preflight finetune configs with `load_from_pretrained`:
  if the normal target-zone checkpoint and same-zone pretrained checkpoint are
  both missing, but another zone has the pretrained copy, copy latest
  `checkpoint_<step>` from pretrained to pretrained before starting the job.

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

## HSDP / PJIT / Memory Rules

- `model.prompt_causal` defaults to `True`: image prefix tokens are
  bidirectional while prompt/text tokens remain causal.
- The projector/connector has its own optimizer group. Use
  `training.connector_learning_rate` or legacy `training.projector_learning_rate`.
- Eval generation uses task-specific token budgets:
  `eval_tokens_shortqa`, `eval_tokens_mid`, `eval_tokens_ocr`,
  `eval_tokens_refcoco`, `eval_tokens_pixelbench`, and `eval_tokens_mmbench`.
  Set `sampling.beam_size` once for deliberate beam-search final evals.
- `utils/pjit_util.py` treats the final mesh axis as the model axis for HSDP.
  Batch/data arrays are sharded only over preceding data axes.
- Prefer a process-major HSDP mesh with the final model axis host-local when
  topology allows. This keeps `global_batch / process_count` dataloader batches
  compatible with `make_array_from_process_local_data`; the old failure looked
  like `process data has 32 elements. Process addresses 64 elements`.
- Training loss should use `token_xent_loss_from_hidden(...)`, not a full
  `embedder.decode(out)` over `(B, K + T, vocab)`.
- CLIP/LLaVA and PrefixMAE paths use best-effort
  `constrain_batch_model(...)` constraints around image features, q/k/v,
  attention maps, and hidden activations. Keep these when editing HSDP paths.
- `LlavaGemma.generate_beam_search(...)` is cumulative-logprob beam search, not
  a greedy alias. It keeps EOS beams alive and decodes only the last prompt
  hidden state during prefill to avoid `[B, prompt_len, vocab]` logits.

## Stateful Dataloader Resume

- Enable with `dataset.stateful_dataloader: True`; current JAX LLaVA remote
  config enables it by default.
- Requires `torchdata==0.8.0`. Missing `torchdata.stateful_dataloader` should
  fail fast.
- Sidecars are written beside model checkpoints at
  `checkpoint_<step>/dataloader_state/process_<rank>.pkl`.
- Exact restore is valid only for the same process count, process-local batch
  size, worker count, prefetch factor, data roots/types, mix weights, seed
  offset, and topology.
- Stateful resume serializes WebDataset cursors, shuffle buffers, RandomMix
  state, worker RNGs, and topology metadata. Buffer entries use `(url, key)`
  references rather than raw image bytes and hydrate by searching the same-zone
  shard on restore.
- Normal `load_from` resume folds checkpoint step into `dataset.data_seed_offset`.
  `load_from_pretrained` is params-only and starts with `step_offset=0`.
- GCS training roots must match `config.zone` before glob/listing or WebDataset
  reads; mismatches raise immediately to prevent cross-region transfer.
- Missing/inaccessible WebDataset paths are fatal. Do not replace these guards
  with retry loops around nonexistent buckets or paths.

## PaliGemma / Two-Stage Curriculum

- The active remote entry is `main.py --config=configs/load_config.py:remote_run`,
  backed by `configs/remote_run_config.yml`.
- `qsqa <dir>` stages the current working tree and queues through MONITOR. Patch
  `remote_run_config.yml` to the exact variant before each queue call.
- As of 2026-06-08, the runnable baseline is
  `training.curriculum: pretrain_sft_two_stage`.
- Stage 1 is a 150K-step 512-resolution pretrain mix with `laion-aes`, `cc12m`,
  `blip3o-short`, `rendered-text-512`, Visual Genome QA/grounded captions/detect,
  `textcaps-train`, `tallyqa`, and `dvqa-train`, with weights
  `[50, 12, 5, 20, 1.7, 5.4, 5.4, 0.1, 0.25, 2.3]`.
- Stage 2 is 90K-step SFT on the LLaVA/VQA/VG/RefCOCO recipe, Adam `1e-5`, weight
  decay `0.002`.
- `pure und baseline` means `vlm_loss_weight=1.0`,
  `text_only_loss_weight=0.0`, `cfg_loss_weight=0.0`, and
  `recon_loss_weight=0.0`.
- For heavy mixed-data runs, `dataset.num_workers` was reduced from 16 to 8.
- Two-stage resumes use global step to choose stage:
  `< stage1_steps` restores pretrain fully; `== stage1_steps` restores params
  only into SFT and starts a fresh optimizer; between stage boundary and final
  step restores SFT fully.
- Two-stage does not support `load_from_pretrained`; use `finetune: True` for a
  standalone SFT from a pretrain checkpoint.
- Stage 2 logs/saves global steps but uses stage-local offset for SFT dataloader
  and LR schedule.
- The stage-1 boundary checkpoint is copied to durable `pretrained-ckpts/...`
  before SFT, and final checkpoint is copied there at the end.
- The stage boundary checkpoint must be saved even when the stage length is not
  divisible by `checkpoint_per_step`.

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
- Verified upload counts per region:
  OKVQA train `8,998` image records / `9,009` QA / 5 shards;
  A-OKVQA train `16,540` image records / `17,056` QA / 9 shards;
  OCRVQA train `166,022` image records / `801,579` QA / 84 shards;
  RefCOCO train `16,994` image records / `42,404` refs / 9 shards.
- Visual sanity reports use `run_vlm_data_visual_report.sh` and
  `VLM-Data-Visual-Report.py`; current us-central1 report is
  `reports/vlm_data_visual_report_us-central1_20260531T205902Z.html` and covers
  32 dataset entries with 3/3 samples and no warnings.
