# Project AGENTS.md Archive

Generated on 2026-06-11 from AGENTS.md files under `/kmh-nfs-ssd-us-mount/code/qiao/work`.

This archive preserves source agent instructions verbatim for cross-repo memory.
Many scattered project-local `AGENTS.md` files were later removed after their
content was centralized into topic guides. Treat this file as an exact historical
archive, not as the primary starting point.


---

## `AGENTS.md`

# Workspace Agent Index

This workspace contains multiple project checkouts. Project-local `AGENTS.md`
files remain the source of repo-specific coding rules. For shared operational
memory, read:

- Shared agent memory:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/AGENTS.md`
- Project checkout index:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/project_index.md`
- TPU operations:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/tpu.md`
- TPU monitor / xibo internals:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/xibo_monitor.md`
- VLM training memory:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/vlm_training.md`
- Spreadsheet / WandB result logging:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/spreadsheet_logging.md`
- Research-loop operations:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/research_loop.md`
- SSD cleanup:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/storage_cleanup.md`

## General Rules

- Read the relevant project-local `AGENTS.md` before changing code in a project
  directory.
- Do not push code changes unless the user explicitly asks for a push in the
  current request.
- Avoid cross-region / cross-zone GCS transfer. Prefer run logs, WandB, and
  spreadsheet metadata over scanning benchmark datasets. If data access is
  unavoidable, use the same-zone bucket for the run and stop before any
  cross-region copy or bulk read.
- For spreadsheet result logging, obey the stop-on-OOD rule in
  `wiki_agents/spreadsheet_logging.md`: if a WandB run has new benchmarks,
  missing/renamed metrics, non-comparable eval settings, discontinuous loss, or
  any other out-of-distribution behavior, do not write to the sheet; report the
  anomaly and wait for the user's decision.


---

## `PaliGemma-baseline/AGENTS.md`

# Repository Notes For Agents

## Active Training Path

- `main.py` loads configs through `configs/load_config.py:<mode>`. The usual remote
  training entry is `--config=configs/load_config.py:remote_run`, backed by
  `configs/remote_run_config.yml`.
- The user-facing queue helper is `qsqa` from `/home/sqa/.bash_aliases`. Run it from
  this repo root. It stages the current working tree first, so patch
  `remote_run_config.yml` to the exact variant before each queue call.
- `just_staging.sh` copies this checkout to `/kmh-nfs-ssd-us-mount/staging/$USER/...`
  and `qsqa <dir>` records that staged directory as the xibo dir before adding a local
  monitor queue entry.

## Current Remote Run Baseline

- As of 2026-06-08, `configs/remote_run_config.yml` is a runnable
  `training.curriculum: pretrain_sft_two_stage` config under `sharding: hsdp`.
  Stage 1 is a 150K-step 512-resolution sandwich MAE-L + Gemma3-1B pretrain setup with
  `laion-aes`, `cc12m`, `blip3o-short`, `rendered-text-512`, Visual Genome QA/grounded
  captions/detect, `textcaps-train`, `tallyqa`, and `dvqa-train` mixed as
  `[50, 12, 5, 20, 1.7, 5.4, 5.4, 0.1, 0.25, 2.3]`. Stage 2 is 90K-step SFT on
  shuffled image-level LLaVA-OV1.5 plus VQAv2/OKVQA/A-OKVQA/OCRVQA/GQA/TextCaps/
  Visual Genome QA/VG detection/RefCOCO, using Adam `1e-5` and weight decay `0.002`.
- `pure und baseline` means `vlm_loss_weight=1.0`, `text_only_loss_weight=0.0`,
  `cfg_loss_weight=0.0`, and `recon_loss_weight=0.0`. Do not leave a `CFG 1+1+1`
  note on this baseline unless those loss weights are intentionally changed.
- For heavy mixed-data remote runs, `dataset.num_workers` was reduced from 16 to 8
  before queueing to lower dataloader pressure.
- On 2026-05-28, two Adam ablations were staged and queued from this baseline:
  xibo dir `27` uses Adam LR `2e-5`, and xibo dir `31` uses Adam LR `1e-5`.

## Resume Data Seed

- `train.py` computes `step_offset = checkpoint_step(config.load_from)` for resume jobs
  and passes `dataset.data_seed_offset + step_offset` into
  `input_pipeline.create_split(...)`.
- `input_pipeline.py` folds that offset into PyTorch worker seeds, WebDataset shuffle
  RNGs, and custom VQA/Genome shard ordering. A normal xibo resume that injects
  `--config.load_from=<previous logdir>` should therefore use a different dataloader
  seed after checkpoint progress.
- `load_from_pretrained` starts new training from params only and intentionally keeps
  `step_offset=0`; it is not the resume path.

## SFT Dataset / Eval Sync

- As of 2026-06-01, the finetune config is aligned with the current `jax_llava`
  SFT data recipe: shuffled image-level LLaVA-OV1.5 plus VQAv2, OKVQA, A-OKVQA,
  OCRVQA, GQA, TextCaps, Visual Genome QA, Visual Genome detection, and RefCOCO.
- `utils/data_util.py` registers `okvqa-train`, `aokvqa-train`, `ocrvqa-train`,
  and `refcoco-train`; `input_pipeline.py` expands A-OKVQA into rotated
  multiple-choice items and RefCOCO into phrase-to-box detection items.
- Grounded detection training and RefCOCOg eval intentionally share
  `format_detection_prompt()`: `Locate the region described by this phrase: ...`
  followed by `Output exactly four location tokens, indicating up, left, down, right.`
- `configs/finetune_config.yml` samples 10 Visual Genome detection regions per
  image with `dataset.genome_det_regions_per_image: 10`.
- Online VQAv2 eval is intentionally capped at 10% through
  `eval.online_vqav2_sample_fraction = 0.1`; final eval still uses the full
  `eval.vqav2_num_samples` unless explicitly overridden.
- MMBench uses a separate longer prompt length via `eval.mmbench_max_txt_len=512`
  and structurally shortens hints/question/options before raw truncation, so
  answer choices and the final option-letter instruction are preserved.

## Durable Checkpoint Notes

- Final training checkpoints should be mirrored to the same regional bucket
  under `pretrained-ckpts/qiao_zhicheng_hanhong_files/...`; this matches the
  shell helper `ltgcp` and protects checkpoints from ordinary bucket cleanup.
- Finetune `load_from_pretrained` restore should first use the normal zone-local
  checkpoint path and then fall back to the same-zone `pretrained-ckpts` path.
  Known `gs://kmh-gcp-*` checkpoint paths are rewritten to the current target
  zone before restore to avoid cross-zone reads.

## Pretrain + SFT Two-Stage Curriculum

- Set `training.curriculum: pretrain_sft_two_stage` with `finetune: False` to run
  pretrain then SFT in one workdir and one global checkpoint stream. Legacy
  `finetune: True` still loads `configs/finetune_config.yml` and remains the
  finetune-only path.
- Two-stage resumes use the numeric global step in `load_from` to decide the
  stage. `step < stage1_steps` restores pretrain fully; `step == stage1_steps`
  restores params only into the SFT/no-decoder model and starts a fresh optimizer;
  `stage1_steps < step <= stage1_steps + stage2_steps` restores SFT fully.
- Two-stage does not support `load_from_pretrained`; use `finetune: True` for a
  standalone SFT run from a pretrain checkpoint. It also does not support legacy
  standalone SFT checkpoint steps in the two-stage `load_from` path.
- Stage 2 logs and saves with global steps, but the SFT dataloader and LR schedule
  use the stage-local offset `global_step - stage1_steps`.
- The stage-1 boundary checkpoint is copied to the durable
  `pretrained-ckpts/...` path before switching to SFT, and the final checkpoint is
  copied there at the end as before.
- The HSDP two-stage loop saves a checkpoint when `(step + 1) == stage_end_step`
  regardless of `checkpoint_per_step`; this explicitly covers the old jax_llava-style
  bug where a non-divisible stage-1 length could switch to stage 2 without a boundary
  checkpoint.

## HSDP Memory Notes

- `utils/pjit_util.py` treats the last mesh axis as the model axis for `hsdp`.
  Batch/data arrays are sharded only over the preceding data axes; do not shard
  batch over every mesh axis or activations can conflict with model sharding and
  get gathered back to global-batch-sized attention buffers.
- Training loss should use `token_xent_loss_from_hidden(...)`, not a full
  `embedder.decode(out)` over `(B, K + T, vocab)`. The chunked loss only scans
  labeled text positions and avoids the large Gemma3 full-vocab logits tensor.
- PrefixMAE attention uses best-effort `constrain_batch_model(...)` constraints
  on q/k/v, attention maps, and hidden activations. Keep these constraints when
  editing HSDP paths; they are there to prevent XLA from choosing high-HBM
  replicated activation layouts.


---

## `beifen-Paligemma/AGENTS.md`

# Repository Notes For Agents

## Active Training Path

- `main.py` loads configs through `configs/load_config.py:<mode>`. The usual remote
  training entry is `--config=configs/load_config.py:remote_run`, backed by
  `configs/remote_run_config.yml`.
- The user-facing queue helper is `qsqa` from `/home/sqa/.bash_aliases`. Run it from
  this repo root. It stages the current working tree first, so patch
  `remote_run_config.yml` to the exact variant before each queue call.
- `just_staging.sh` copies this checkout to `/kmh-nfs-ssd-us-mount/staging/$USER/...`
  and `qsqa <dir>` records that staged directory as the xibo dir before adding a local
  monitor queue entry.

## HSDP / PJIT Notes

- `utils/pjit_util.py` prefers a process-major mesh layout so the final model
  axis stays host-local when the topology allows it. This avoids host-local
  dataloaders producing fewer rows than `make_array_from_process_local_data`
  expects on multi-host HSDP meshes.

## Current Remote Run Baseline

- As of 2026-06-08, `configs/remote_run_config.yml` is a runnable
  `training.curriculum: pretrain_sft_two_stage` config: stage 1 is the
  150K-step 512-resolution 1d-MAE-B pretrain setup with
  `laion-aes`, `cc12m`, `blip3o-short`, `rendered-text-512`, Visual Genome QA/grounded
  captions/detect, `textcaps-train`, `tallyqa`, and `dvqa-train` mixed as
  `[50, 12, 5, 20, 1.7, 5.4, 5.4, 0.1, 0.25, 2.3]`; stage 2 is 90K-step SFT on
  shuffled image-level LLaVA-OV1.5 plus VQAv2/OKVQA/A-OKVQA/OCRVQA/GQA/TextCaps/
  Visual Genome QA/VG detection/RefCOCO, using Adam `1e-5` and weight decay `0.002`.
- `pure und baseline` means `vlm_loss_weight=1.0`, `text_only_loss_weight=0.0`,
  `cfg_loss_weight=0.0`, and `recon_loss_weight=0.0`. Do not leave a `CFG 1+1+1`
  note on this baseline unless those loss weights are intentionally changed.
- For heavy mixed-data remote runs, `dataset.num_workers` was reduced from 16 to 8
  before queueing to lower dataloader pressure.
- On 2026-05-28, two Adam ablations were staged and queued from this baseline:
  xibo dir `27` uses Adam LR `2e-5`, and xibo dir `31` uses Adam LR `1e-5`.

## Pretrain Efficiency Notes

- On 2026-06-10, CC12M text length was measured by streaming `.txt` members from
  three same-zone GCS shards without downloading full shards:
  `gs://kmh-gcp-us-central1/data/cc12m/{00000,00500,01096}.tar`, 500 texts each.
  With the current Gemma3 tokenizer and the actual CC12M caption prompt sampler,
  train full text length was: mean 94.71 tokens, median 96, p75 124, p90 148,
  p95 162, p99 229, max 410. Truncation at 64 tokens would affect 69.67% of
  sampled examples and retain 61.09% of tokens; 128 affects 20.73% and retains
  93.61%; 160 affects 5.73% and retains 97.73%; 256 affects 0.47% and retains
  99.77%. Recommendation: do not use stage-1 `max_txt_length=64` if CC12M has
  meaningful weight; `128` is a reasonable speed/coverage tradeoff, and `160`
  preserves nearly all sampled CC12M text while still shorter than 256.
- Perception Encoder scale should be recorded as samples/examples seen, not
  unique dataset size and not text tokens. The paper uses 5.4B public image
  alt-text pairs and reports 58B samples seen for B/L and 86B for G, i.e. many
  training instances over repeated/long schedules.

## Resume Data Seed

- `train.py` computes `step_offset = checkpoint_step(config.load_from)` for resume jobs
  and passes `dataset.data_seed_offset + step_offset` into
  `input_pipeline.create_split(...)`.
- `input_pipeline.py` folds that offset into PyTorch worker seeds, WebDataset shuffle
  RNGs, and custom VQA/Genome shard ordering. A normal xibo resume that injects
  `--config.load_from=<previous logdir>` should therefore use a different dataloader
  seed after checkpoint progress.
- `load_from_pretrained` starts new training from params only and intentionally keeps
  `step_offset=0`; it is not the resume path.

## Stateful Dataloader Resume

- `model.prompt_causal` defaults to `True`. This is the standard LLaVA-style
  mask: image prefix tokens are bidirectional, while prompt/text tokens remain
  causal. Set it to `False` only to reproduce the older local behavior where the
  entire image+prompt prefix was bidirectional.
- The projector/connector is its own optimizer group. Use
  `training.connector_learning_rate` (or legacy alias
  `training.projector_learning_rate`) to set its LR separately from the LM main
  group and vision encoder group.
- Eval generation uses task-specific token budgets:
  `eval_tokens_shortqa`, `eval_tokens_mid`, `eval_tokens_ocr`,
  `eval_tokens_refcoco`, `eval_tokens_pixelbench`, and
  `eval_tokens_mmbench`. These samplers respect `sampling.beam_size`, so a
  deliberate beam-search final eval should set that once rather than patching
  every task.
- Branch `sqa.late_fusion_dataloader_state` adds an exact same-topology dataloader
  resume path. Enable it with `dataset.stateful_dataloader: True`; the branch's
  `configs/remote_run_config.yml` enables it by default.
- This path requires `torchdata.stateful_dataloader` (`torchdata==0.8.0` is listed in
  `requirements.txt`). If `torchdata` is missing, loader creation fails immediately
  rather than silently falling back to the old non-exact resume behavior.
- Stateful resume intentionally does not fold `checkpoint_step` into
  `data_seed_offset`. The model checkpoint restores the model/optimizer step, and the
  dataloader sidecar restores per-worker iterator cursors and RNG states.
- Dataloader state is saved beside each model checkpoint as
  `checkpoint_<step>/dataloader_state/process_<rank>.pkl`. Every JAX process writes its
  own sidecar. Resume validates process count, process-local batch size, worker count,
  prefetch factor, data roots/types, mix weights, and seed offset before loading.
- Exact state is only valid for same topology. Do not expect a v5p-64 checkpoint to
  resume exactly on a v6-32 topology unless a future canonical-stream remapping is
  implemented.
- The stateful train path replaces WebDataset's opaque iterator state with explicit
  cursor objects for active train datasets: regular WebDataset pretrain streams,
  VQA/LLaVA/GQA-style grouped QA streams, Visual Genome grounded captions/detection,
  and RandomMix. Shuffle buffers are serialized as lightweight `(url, key)` references
  instead of raw image bytes; normal training still keeps raw samples in memory.
- On restore, buffered references are hydrated by opening the recorded same-zone shard
  and searching for the key. This may make the first resumed batches slower but avoids
  large checkpoint sidecars and avoids per-step overhead.
- To avoid accidental cross-region GCS reads, `input_pipeline.create_split` validates
  that every `gs://kmh-gcp-*` training root bucket matches `config.zone` before any
  glob/listing or WebDataset read. A mismatch raises immediately.
- Missing or inaccessible WebDataset paths must not be retried forever. The existing
  `make_stop_after_n_errors(..., fatal_on_missing=True)` treats 404/403/bucket-missing
  errors as fatal, and GCS glob expansion asserts after one listing attempt if a glob
  has zero matches. Do not replace these guards with retry loops around nonexistent
  buckets or paths.

## SFT Dataset / Eval Sync

- As of 2026-06-01, the finetune config is aligned with the current `jax_llava`
  SFT data recipe: shuffled image-level LLaVA-OV1.5 plus VQAv2, OKVQA, A-OKVQA,
  OCRVQA, GQA, TextCaps, Visual Genome QA, Visual Genome detection, and RefCOCO.
- `utils/data_util.py` registers `okvqa-train`, `aokvqa-train`, `ocrvqa-train`,
  and `refcoco-train`; `input_pipeline.py` expands A-OKVQA into rotated
  multiple-choice items and RefCOCO into phrase-to-box detection items.
- Grounded detection training and RefCOCOg eval intentionally share
  `format_detection_prompt()`: `Locate the region described by this phrase: ...`
  followed by `Output exactly four location tokens, indicating up, left, down, right.`
- `configs/finetune_config.yml` samples 10 Visual Genome detection regions per
  image with `dataset.genome_det_regions_per_image: 10`.
- Online VQAv2 eval is intentionally capped at 10% through
  `eval.online_vqav2_sample_fraction = 0.1`; final eval still uses the full
  `eval.vqav2_num_samples` unless explicitly overridden.
- MMBench uses a separate longer prompt length via `eval.mmbench_max_txt_len=512`
  and structurally shortens hints/question/options before raw truncation, so
  answer choices and the final option-letter instruction are preserved.

## Durable Checkpoint Notes

- Final training checkpoints should be mirrored to the same regional bucket
  under `pretrained-ckpts/qiao_zhicheng_hanhong_files/...`; this matches the
  shell helper `ltgcp` and protects checkpoints from ordinary bucket cleanup.
- Finetune `load_from_pretrained` restore should first use the normal zone-local
  checkpoint path and then fall back to the same-zone `pretrained-ckpts` path.
  Known `gs://kmh-gcp-*` checkpoint paths are rewritten to the current target
  zone before restore to avoid cross-zone reads.

## Pretrain + SFT Two-Stage Curriculum

- Set `training.curriculum: pretrain_sft_two_stage` with `finetune: False` to run
  pretrain then SFT in one workdir and one global checkpoint stream. Legacy
  `finetune: True` still loads `configs/finetune_config.yml` and remains the
  finetune-only path.
- Two-stage resumes use the numeric global step in `load_from` to decide the
  stage. `step < stage1_steps` restores pretrain fully; `step == stage1_steps`
  restores params only into the SFT/no-decoder model and starts a fresh optimizer;
  `stage1_steps < step <= stage1_steps + stage2_steps` restores SFT fully.
- Two-stage does not support `load_from_pretrained`; use `finetune: True` for a
  standalone SFT run from a pretrain checkpoint. It also does not support legacy
  standalone SFT checkpoint steps in the two-stage `load_from` path.
- Stage 2 logs and saves with global steps, but the SFT dataloader and LR schedule
  use the stage-local offset `global_step - stage1_steps`.
- The stage-1 boundary checkpoint is copied to the durable
  `pretrained-ckpts/...` path before switching to SFT, and the final checkpoint is
  copied there at the end as before.
- The pmap two-stage loop saves a checkpoint when `(step + 1) == stage_end_step`
  regardless of `checkpoint_per_step`; this explicitly covers the old jax_llava-style
  bug where a non-divisible stage-1 length could switch to stage 2 without a boundary
  checkpoint.

## Remote Debug Procedure

### Checking Job Status and Logs

- **List all jobs**: run `tcs` (alias for `tpu check sqa`). This shows window numbers,
  tags, TPU assignments, status, and directory info.
  Full command: `/kmh-nfs-ssd-us-mount/code/hanhong/miniforge3/bin/python /home/jzc/zhichengjiang/working/xibo_tpu_manager/tpu.py check sqa`
- **Get log directory for a window**: run
  `/kmh-nfs-ssd-us-mount/code/hanhong/miniforge3/bin/python /kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager/see_log.py <window_number>`
  This returns the NFS path to the log directory. The main output is at `<logdir>/output.log`.
- **"Window 7446"** means the queue window with ID 7446. Use the commands above to find
  its log directory and read `output.log` for training metrics (steps_per_second, loss, etc).

To run a quick debug job on a remote TPU:

1. **Find a free READY TPU** — list with `gcloud compute tpus tpu-vm list --zone=<zone> --project=he-vision-group | grep READY`.
   Check the TPU is not already in use: SSH and run `sudo lsof -w /dev/vfio/0`.
2. **Reserve the TPU** — create a lock file in `/kmh-nfs-ssd-us-mount/code/qiao/tpu_lock/`
   with format `{user}_{vm_name}_{YYYY-MM-DD_HH-MM-SS}`. Locks expire after 30 minutes.
3. **Set up the environment** — run `tpu mount-disk <vm_name> --zone=<zone>` using:
   `/kmh-nfs-ssd-us-mount/code/hanhong/miniforge3/bin/python /home/jzc/zhichengjiang/working/xibo_tpu_manager/tpu.py mount-disk <vm_name> --zone=<zone>`
   This mounts NFS, installs the Python wheel environment from GCS, and sets wandb.
   Do NOT manually `pip install` packages — the wheel bundle from
   `gs://kmh-gcp-<zone>/hanhong/v5_wheels_xin.tar.gz` is the canonical environment.
   For v5p TPUs, env-check is skipped automatically.
4. **Stage code** — run `just_staging.sh` from the repo root (or rsync manually).
5. **Run the job** — SSH to all workers with the command from `run_remote.sh` pattern:
   ```
   cd <STAGEDIR>
   export ZONE=<zone>
   export GOOGLE_APPLICATION_CREDENTIALS=/kmh-nfs-ssd-us-mount/code/qiao/<zone_short>.json
   export PYTHONUNBUFFERED=1
   python main.py --workdir=<LOGDIR> --config=configs/load_config.py:<config_mode>
   ```
   The workdir MUST contain the zone string (e.g. `us-central1`) so `infer_zone_card`
   can detect it. The run_remote.sh embeds VM_NAME and ZONE in JOBNAME for this purpose.

### Common Pitfalls

- Fresh spot TPUs have NO packages and NO NFS mount. Always run `tpu mount-disk` first.
- Do not manually `pip install jax` etc. — it leads to version conflicts (e.g.
  `google-cloud-storage` pulling in Python 3.13-only `email.errors.HeaderWriteError`).
- Spot TPUs can be preempted (state → DELETING) at any time. Check status before use.
- All katelyn/xtiange/zander v5p-8 TPUs in us-central1-a are shared pool. Reserve with
  the lock mechanism before use; check `sudo lsof -w /dev/vfio/0` to verify no process
  is already using the TPU chips. As of 2026-06-09, katelyngan uses ALL katelyn-1-*
  TPUs for long-running jobs; prefer xtiange-* TPUs for short debug runs.
- `config.dataset.stateful_dataloader: True` requires `torchdata==0.8.0` (included in
  the wheel bundle). If missing, loader creation fails immediately.


---

## `beifen/AGENTS.md`

# Beifen Dataset Operations Notes

This directory contains dataset upload and visual sanity report scripts for VLM
training/eval data. Follow these notes when editing or running the scripts here.

## Region And Storage Rules

- Never move dataset payloads across regions. Run upload/report jobs on a TPU VM
  in the same region/zone family as the target bucket.
- Target bucket convention is `gs://kmh-gcp-${ZONE_SHORT}/data`, where
  `ZONE_SHORT` is derived from the VM zone, for example `us-central1`,
  `us-east5`, or `asia-northeast1-b`.
- Keep all download/cache/staging paths under `/dev/shm`. Do not stage dataset
  images on NFS, SSD, or home directories.
- Upload datasets as tar shards only. Do not upload scattered single-image
  files to the bucket.
- For datasets with multiple questions/refs per image, store one image record
  with grouped `qas` or `refs`; do not duplicate the same image for every
  question.
- After uploads, verify the remote VM has no remaining upload process before
  considering the card free. If `tpu.py release` reports a conflicting owner,
  do not force-release; re-check the TPU table and avoid releasing another
  user's lock.

## Missing LLaVA SFT Dataset Upload

- Use `upload_vlm_sft_missing.sh` as the launcher and
  `VLM-SFT-Missing-upload.py` as the implementation for OKVQA, A-OKVQA,
  OCRVQA, and RefCOCO.
- The launcher enforces same-region bucket prefixes and `/dev/shm` cache roots.
- Enable W&B with `ENABLE_WANDB=1`; pass `WANDB_ENTITY` when needed.
- Useful environment knobs:
  `VM_NAME`, `ZONE`, `GCS_DATA_ROOT`, `DATASETS`, `TMP_ROOT`, `HF_HOME`,
  `CLEAR_TMP_ROOT`, `CLEAR_HF_HOME`, `EXTRA_UPLOAD_ARGS`.
- Verified us-central1 upload counts:
  OKVQA train = 8,998 image records / 9,009 QA items / 5 tar shards;
  A-OKVQA train = 16,540 image records / 17,056 QA items / 9 tar shards;
  OCRVQA train = 166,022 image records / 801,579 QA items / 84 tar shards;
  RefCOCO train = 16,994 image records / 42,404 ref items / 9 tar shards.
- Verified us-east5 and asia-northeast1-b uploads have the same counts and tar
  shard counts as us-central1, with `_SUCCESS` present under each dataset train
  prefix.
- Upload logs for the additional regions:
  `vlm-sft-missing-upload-us-east5-kmh-tpuvm-v6e-16-kaiminghe-43ba4c.log`
  and
  `vlm-sft-missing-upload-asia-northeast1-b-kmh-tpuvm-v6e-16-kaiminghe-4a7318.log`.
- OCRVQA is uploaded as the full train split. LLaVA-1.5 uses an approximately
  80K sample, so training should control scale with sampling/mix weights.

## Visual Report

- Use `run_vlm_data_visual_report.sh` and `VLM-Data-Visual-Report.py` for visual
  sanity checks.
- The report script samples normal WDS tar shards plus special eval formats:
  PixelBench `images.tar` + `metadata.tar`, MME parquet, POPE local JSON + COCO
  images, RefCOCOg annotations + COCO tar shards, and MMBench TSV/base64 images.
- The generated report should include 3 visual samples per dataset. Check the
  sidecar JSON for any dataset with fewer than 3 samples or non-empty warnings.
- If WeasyPrint fails on the full CSS-grid HTML, use the simplified print HTML
  fallback generated by the report script.

## Current Report Artifact

- Current us-central1 visual report:
  `reports/vlm_data_visual_report_us-central1_20260531T205902Z.html`
- Its sidecar confirms 32 dataset entries with 3/3 samples and no warnings,
  including `okvqa-train`, `aokvqa-train`, `ocrvqa-train`, and `refcoco-train`.


---

## `eue3a5qr-sft-new-pipeline/AGENTS.md`

# Repository Notes For Agents

## Active Training Path

- `main.py` loads configs through `configs/load_config.py:<mode>`. The usual remote
  training entry is `--config=configs/load_config.py:remote_run`, backed by
  `configs/remote_run_config.yml`.
- The user-facing queue helper is `qsqa` from `/home/sqa/.bash_aliases`. Run it from
  this repo root. It stages the current working tree first, so patch
  `remote_run_config.yml` to the exact variant before each queue call.
- `just_staging.sh` copies this checkout to `/kmh-nfs-ssd-us-mount/staging/$USER/...`
  and `qsqa <dir>` records that staged directory as the xibo dir before adding a local
  monitor queue entry.

## Current Remote Run Baseline

- The 2026-05-28 queue baseline is the 150K-step 512-resolution 1d-MAE-B setup with
  `laion-aes`, `cc12m`, `blip3o-short`, `rendered-text-512`, Visual Genome QA/grounded
  captions/detect, `textcaps-train`, `tallyqa`, and `dvqa-train` mixed as
  `[50, 12, 5, 20, 1.7, 5.4, 5.4, 0.1, 0.25, 2.3]`.
- `pure und baseline` means `vlm_loss_weight=1.0`, `text_only_loss_weight=0.0`,
  `cfg_loss_weight=0.0`, and `recon_loss_weight=0.0`. Do not leave a `CFG 1+1+1`
  note on this baseline unless those loss weights are intentionally changed.
- For heavy mixed-data remote runs, `dataset.num_workers` was reduced from 16 to 8
  before queueing to lower dataloader pressure.

## Resume Data Seed

- `train.py` computes `step_offset = checkpoint_step(config.load_from)` for resume jobs
  and passes `dataset.data_seed_offset + step_offset` into
  `input_pipeline.create_split(...)`.
- `input_pipeline.py` folds that offset into PyTorch worker seeds, WebDataset shuffle
  RNGs, and custom VQA/Genome shard ordering. A normal xibo resume that injects
  `--config.load_from=<previous logdir>` should therefore use a different dataloader
  seed after checkpoint progress.
- `load_from_pretrained` starts new training from params only and intentionally keeps
  `step_offset=0`; it is not the resume path.


## eue3a5qr SFT Launch Notes

- This worktree was copied from pretrain stagedir `/kmh-nfs-ssd-us-mount/staging/sqa/260531023922-t0f7nu--code` for W&B run `eue3a5qr`.
- Fresh SFT must use `configs/finetune_config.yml` with `load_from_pretrained` pointing at the step-150000 pretrain logdir. Do not set `load_from` or `wandb_resume_id` unless resuming the SFT run itself.
- SFT data/prompt/eval files were synced from `/kmh-nfs-ssd-us-mount/code/qiao/work/muon2e-5-sft-stage-lr2e-5`, which is aligned with current `jax_llava` SFT pipeline.


---

## `jax_llava/AGENTS.md`

# JAX LLaVA Project Notes

Follow these notes when editing the JAX LLaVA training/data code in this repo.

## SFT Dataset Loader Notes

- The stage-2/SFT mix includes the LLaVA-OV1.5 image-shuffled data plus VQAv2,
  OKVQA, A-OKVQA, OCRVQA, GQA, TextCaps, Visual Genome QA, Visual Genome
  detection, and RefCOCO.
- Dataset aliases for the four LLaVA-1.5 missing SFT datasets are registered in
  `utils/data_util.py` as `okvqa-train`, `aokvqa-train`, `ocrvqa-train`, and
  `refcoco-train`.
- OKVQA and OCRVQA use the short-answer VQA prompt:
  `Answer the question using a single word or phrase.`
- A-OKVQA uses multiple-choice augmentation in the input pipeline: one grouped
  QA expands to four cyclic choice rotations, and the training target is the
  correct option letter. This matches the LLaVA-1.5 reported ~66K A-OKVQA SFT
  scale better than treating the stored grouped records as direct-answer only.
- OCRVQA is uploaded as the full train split, but SFT mix weights intentionally
  sample it at the LLaVA-1.5 ~80K scale. Do not infer the mix weight from the
  full uploaded 801K QA count unless explicitly changing the recipe.
- RefCOCO records store COCO absolute `xywh` boxes and grouped refs per image.
  The input pipeline expands one phrase-to-box training item per ref and formats
  targets as `<loc....>` tokens with the same `format_detection_prompt()` used
  by RefCOCOg eval.

## LLaVA-1.5 Reproduction Tracking

- Experiment spreadsheet:
  `https://docs.google.com/spreadsheets/d/1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ/edit?gid=1146448969#gid=1146448969`.
- Rows 146-148 on gid `1146448969` track the first LLaVA-1.5 reproduction
  run. Row 147 is the 7B target line; row 148 is the first init run:
  `CLIP-L @ 336 + gemma3-1B`, blip-3o pretrain, and SFT over LLaVA-OV1.5,
  VQA, GQA, and TextCaps style data.
- Row 148 WandB run: `exalted-haze-9 | Sqa24's workspace | jax-llava`.
- Row 147 target metrics recorded in the sheet:
  MME-P `1511`, VQAv2 `78.5`, TextVQA `58.2`, MMBench `64.3`,
  POPE `84.2`, VStar `~48.7`, OCRBench `29.7`, MMVP `24.7`,
  CountBench `~47.0`, VisWiz `50.0`, SEED-Bench image `66.1`,
  ScienceQA-IMG `66.8`, and GQA `62.0`.
- VStar, OCRBench, MMVP, CountBench, RefCOCOg, and ImageNet KNN are not
  original LLaVA-1.5 paper table metrics. Use them as additional probes only.
- The sheet POPE target `84.2` matches the paper's adversarial POPE split.
  Row 148 records `pope_adversarial_f1_stage2_final=80`, not the macro F1.
  The evaluator also logs macro F1 (`82.58` in the same final eval), but the
  spreadsheet value is adversarial and should be compared to the adversarial
  target.
- First row-148 run data: stage 1 used `blip3o-short`; stage 2 used
  LLaVA-OV1.5, VQAv2, GQA train, TextCaps train, and Visual Genome QA with
  weights `[22, 0.4, 0.94, 0.022, 1.7]`. It did not include OKVQA,
  A-OKVQA, OCRVQA, VG detection, RefCOCO, or ShareGPT text-only.
- Current `configs/remote_run_config.yml` differs from the first run: stage 1
  uses `cc12m`, and stage 2 adds `okvqa-train`, `aokvqa-train`,
  `ocrvqa-train`, `visual-genome-det`, and `refcoco-train` with weights
  `[22, 0.4, 0.009, 0.068, 0.08, 0.94, 0.022, 1.7, 0.86, 0.048]`.
- KNN ImageNet TFDS preprocessing should follow `config.dataset.resize_mode`.
  `stretch` directly resizes to the square canvas; `letterbox` preserves aspect
  ratio and pads, matching the normal train/eval transform family. Do not
  silently use center-crop KNN when the run config says `stretch` or `letterbox`.
- A gist-ready summary of the current image-shuffled LLaVA-OV1.5 dataloader is
  kept at `ideas/llava_ov15_dataloader_gist.md`.
- Parsed v5p-64 throughput for first LLaVA-style curriculum jobs:
  stage 1 median `5.63` steps/s all points (`5.69` filtered >2 steps/s);
  stage 2 median `3.91` steps/s all points (`3.94` filtered >2 steps/s).
  Finished row-148 stage-2 segment `20260531_004908_ggu3cd...` median was
  `3.84` steps/s over 17 logged points.

## Durable Checkpoint Notes

- Final training checkpoints should be mirrored to the same regional bucket
  under `pretrained-ckpts/qiao_zhicheng_hanhong_files/...`; this matches the
  shell helper `ltgcp` and protects checkpoints from ordinary bucket cleanup.
- `load_from_pretrained` params-only restore should first use the normal
  zone-local checkpoint path and then fall back to the same-zone
  `pretrained-ckpts` path. Known `gs://kmh-gcp-*` checkpoint paths are
  rewritten to the current target zone before restore to avoid cross-zone reads.

## HSDP Memory Notes

- `model.prompt_causal` defaults to `True`. This is the standard LLaVA-style
  mask: image prefix tokens are bidirectional, while prompt/text tokens remain
  causal. Set it to `False` only to reproduce the older local behavior where the
  entire image+prompt prefix was bidirectional.
- The projector/connector is its own optimizer group. Use
  `training.connector_learning_rate` (or legacy alias
  `training.projector_learning_rate`) to set its LR separately from the LM main
  group and vision encoder group.
- Eval generation uses task-specific token budgets:
  `eval_tokens_shortqa`, `eval_tokens_mid`, `eval_tokens_ocr`,
  `eval_tokens_refcoco`, `eval_tokens_pixelbench`, and
  `eval_tokens_mmbench`. These samplers still respect `sampling.beam_size`, so a
  deliberate beam-search final eval should set that once rather than patching
  every task.
- `utils/pjit_util.py` treats the last mesh axis as the model axis for `hsdp`.
  Batch/data arrays are sharded only over the preceding data axes; do not shard
  batch over every mesh axis or activations can conflict with model sharding and
  get gathered back to global-batch-sized attention buffers.
- Host-local input/output specs may temporarily fall back to all mesh axes when
  the current TPU logical mesh does not give each process exactly
  `1/process_count` of the data-axis positions. This is only an input boundary
  compatibility fallback for `global_batch/process_count` dataloaders; model
  activations still use the HSDP data-axis/model-axis constraints.
- The HSDP mesh must be process-major with the final model axis host-local when
  possible. `utils/pjit_util.py` now builds such a mesh before falling back to
  JAX's default `create_device_mesh`; this keeps `global_batch / process_count`
  dataloader batches compatible with `make_array_from_process_local_data`. The
  failure signature from the old default mesh was `process data has 32 elements.
  Process addresses 64 elements and global_shape=(256, 64)` on v5p-64.
- Training loss should use `token_xent_loss_from_hidden(...)`, not a full
  `embedder.decode(out)` over `(B, K + T, vocab)`. The chunked loss only scans
  labeled text positions and avoids the large Gemma3 full-vocab logits tensor.
- CLIP/LLaVA and PrefixMAE paths use best-effort `constrain_batch_model(...)`
  constraints around image features, q/k/v, attention maps, and hidden
  activations. Keep these constraints when editing HSDP paths.
- `LlavaGemma.generate_beam_search(...)` is a real cumulative-logprob beam search,
  not a greedy alias. It keeps EOS beams alive, supports `txt_feature_layer > 0`,
  and decodes only the last prompt hidden state during prefill to avoid a
  `[B, prompt_len, vocab]` logits tensor.

## Stateful Dataloader Resume

- `jax_llava` now carries the same full stateful dataloader infrastructure as
  `beifen-Paligemma`. Enable it with `dataset.stateful_dataloader: True`;
  `configs/remote_run_config.yml` enables it by default.
- This requires `torchdata==0.8.0`. Missing `torchdata.stateful_dataloader`
  should fail fast instead of silently falling back to non-exact resume.
- Stateful resume saves sidecars at
  `checkpoint_<step>/dataloader_state/process_<rank>.pkl` and restores WebDataset
  cursors, shuffle buffers, RandomMix state, worker RNGs, and topology metadata.
  It is exact only for the same process count, process-local batch size, worker
  count, prefetch factor, roots/types, mix weights, and seed offset.
- `input_pipeline.create_split` validates that training GCS roots match
  `config.zone` before reading/listing shards. Keep this guard to avoid
  cross-region transfer and accidental loops over nonexistent paths.

## TPU Manager & Job Queue

- **Check job status**: use `tcs` (alias) or `tpu check sqa` to view running/errored/finished jobs, their window IDs, TPU assignments, and log dirs. Do NOT manually parse xibo `data.json` to get job info — `tcs` is the canonical interface.
- **Queue a job**: `qsqa <dir_num>` from the working directory. This stages code (rsync to `/kmh-nfs-ssd-us-mount/staging/sqa/...`), registers with xibo (`tpu set-cur`), and adds to the MONITOR queue.
- **MONITOR queue file**: `/kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager/queue.json`. MONITOR dispatches pending jobs by calling `tpu run <alias> <user> dir=<dir_no>`, which re-stages from the working directory at dispatch time.
- **Directory numbers**: xibo maps dir numbers to working directory paths in `data.json`. `set-cur` only works for dir 1-100; for dir>100, register directly in `data['users']['sqa']['working_dir']`.
- **Eval-only jobs**: set `eval_only: True` and `load_from: <log_dir_path>` in `remote_run_config.yml`. The code resolves checkpoint paths from log dirs via GCS mirror.
- **Multiple jobs from the same codebase**: since MONITOR re-stages from the live working dir at dispatch time, use separate dir numbers pointing to separate directory copies to avoid config conflicts between queued jobs.


---

## `jax_llava_late_fusion_13_5ed73eb/AGENTS.md`

# JAX LLaVA Project Notes

Follow these notes when editing the JAX LLaVA training/data code in this repo.

## SFT Dataset Loader Notes

- The stage-2/SFT mix includes the LLaVA-OV1.5 image-shuffled data plus VQAv2,
  OKVQA, A-OKVQA, OCRVQA, GQA, TextCaps, Visual Genome QA, Visual Genome
  detection, and RefCOCO.
- Dataset aliases for the four LLaVA-1.5 missing SFT datasets are registered in
  `utils/data_util.py` as `okvqa-train`, `aokvqa-train`, `ocrvqa-train`, and
  `refcoco-train`.
- OKVQA and OCRVQA use the short-answer VQA prompt:
  `Answer the question using a single word or phrase.`
- A-OKVQA uses multiple-choice augmentation in the input pipeline: one grouped
  QA expands to four cyclic choice rotations, and the training target is the
  correct option letter. This matches the LLaVA-1.5 reported ~66K A-OKVQA SFT
  scale better than treating the stored grouped records as direct-answer only.
- OCRVQA is uploaded as the full train split, but SFT mix weights intentionally
  sample it at the LLaVA-1.5 ~80K scale. Do not infer the mix weight from the
  full uploaded 801K QA count unless explicitly changing the recipe.
- RefCOCO records store COCO absolute `xywh` boxes and grouped refs per image.
  The input pipeline expands one phrase-to-box training item per ref and formats
  targets as `<loc....>` tokens with the same `format_detection_prompt()` used
  by RefCOCOg eval.

## LLaVA-1.5 Reproduction Tracking

- Experiment spreadsheet:
  `https://docs.google.com/spreadsheets/d/1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ/edit?gid=1146448969#gid=1146448969`.
- Rows 146-148 on gid `1146448969` track the first LLaVA-1.5 reproduction
  run. Row 147 is the 7B target line; row 148 is the first init run:
  `CLIP-L @ 336 + gemma3-1B`, blip-3o pretrain, and SFT over LLaVA-OV1.5,
  VQA, GQA, and TextCaps style data.
- Row 148 WandB run: `exalted-haze-9 | Sqa24's workspace | jax-llava`.
- Row 147 target metrics recorded in the sheet:
  MME-P `1511`, VQAv2 `78.5`, TextVQA `58.2`, MMBench `64.3`,
  POPE `84.2`, VStar `~48.7`, OCRBench `29.7`, MMVP `24.7`,
  CountBench `~47.0`, VisWiz `50.0`, SEED-Bench image `66.1`,
  ScienceQA-IMG `66.8`, and GQA `62.0`.
- VStar, OCRBench, MMVP, CountBench, RefCOCOg, and ImageNet KNN are not
  original LLaVA-1.5 paper table metrics. Use them as additional probes only.
- The sheet POPE target `84.2` matches the paper's adversarial POPE split.
  Row 148 records `pope_adversarial_f1_stage2_final=80`, not the macro F1.
  The evaluator also logs macro F1 (`82.58` in the same final eval), but the
  spreadsheet value is adversarial and should be compared to the adversarial
  target.
- First row-148 run data: stage 1 used `blip3o-short`; stage 2 used
  LLaVA-OV1.5, VQAv2, GQA train, TextCaps train, and Visual Genome QA with
  weights `[22, 0.4, 0.94, 0.022, 1.7]`. It did not include OKVQA,
  A-OKVQA, OCRVQA, VG detection, RefCOCO, or ShareGPT text-only.
- Current `configs/remote_run_config.yml` differs from the first run: stage 1
  uses `cc12m`, and stage 2 adds `okvqa-train`, `aokvqa-train`,
  `ocrvqa-train`, `visual-genome-det`, and `refcoco-train` with weights
  `[22, 0.4, 0.009, 0.068, 0.08, 0.94, 0.022, 1.7, 0.86, 0.048]`.
- KNN ImageNet TFDS preprocessing should follow `config.dataset.resize_mode`.
  `stretch` directly resizes to the square canvas; `letterbox` preserves aspect
  ratio and pads, matching the normal train/eval transform family. Do not
  silently use center-crop KNN when the run config says `stretch` or `letterbox`.
- A gist-ready summary of the current image-shuffled LLaVA-OV1.5 dataloader is
  kept at `ideas/llava_ov15_dataloader_gist.md`.
- Parsed v5p-64 throughput for first LLaVA-style curriculum jobs:
  stage 1 median `5.63` steps/s all points (`5.69` filtered >2 steps/s);
  stage 2 median `3.91` steps/s all points (`3.94` filtered >2 steps/s).
  Finished row-148 stage-2 segment `20260531_004908_ggu3cd...` median was
  `3.84` steps/s over 17 logged points.

## Durable Checkpoint Notes

- Final training checkpoints should be mirrored to the same regional bucket
  under `pretrained-ckpts/qiao_zhicheng_hanhong_files/...`; this matches the
  shell helper `ltgcp` and protects checkpoints from ordinary bucket cleanup.
- `load_from_pretrained` params-only restore should first use the normal
  zone-local checkpoint path and then fall back to the same-zone
  `pretrained-ckpts` path. Known `gs://kmh-gcp-*` checkpoint paths are
  rewritten to the current target zone before restore to avoid cross-zone reads.

## HSDP Memory Notes

- `model.prompt_causal` defaults to `True`. This is the standard LLaVA-style
  mask: image prefix tokens are bidirectional, while prompt/text tokens remain
  causal. Set it to `False` only to reproduce the older local behavior where the
  entire image+prompt prefix was bidirectional.
- The projector/connector is its own optimizer group. Use
  `training.connector_learning_rate` (or legacy alias
  `training.projector_learning_rate`) to set its LR separately from the LM main
  group and vision encoder group.
- Eval generation uses task-specific token budgets:
  `eval_tokens_shortqa`, `eval_tokens_mid`, `eval_tokens_ocr`,
  `eval_tokens_refcoco`, `eval_tokens_pixelbench`, and
  `eval_tokens_mmbench`. These samplers still respect `sampling.beam_size`, so a
  deliberate beam-search final eval should set that once rather than patching
  every task.
- `utils/pjit_util.py` treats the last mesh axis as the model axis for `hsdp`.
  Batch/data arrays are sharded only over the preceding data axes; do not shard
  batch over every mesh axis or activations can conflict with model sharding and
  get gathered back to global-batch-sized attention buffers.
- Host-local input/output specs may temporarily fall back to all mesh axes when
  the current TPU logical mesh does not give each process exactly
  `1/process_count` of the data-axis positions. This is only an input boundary
  compatibility fallback for `global_batch/process_count` dataloaders; model
  activations still use the HSDP data-axis/model-axis constraints.
- The HSDP mesh must be process-major with the final model axis host-local when
  possible. `utils/pjit_util.py` now builds such a mesh before falling back to
  JAX's default `create_device_mesh`; this keeps `global_batch / process_count`
  dataloader batches compatible with `make_array_from_process_local_data`. The
  failure signature from the old default mesh was `process data has 32 elements.
  Process addresses 64 elements and global_shape=(256, 64)` on v5p-64.
- Training loss should use `token_xent_loss_from_hidden(...)`, not a full
  `embedder.decode(out)` over `(B, K + T, vocab)`. The chunked loss only scans
  labeled text positions and avoids the large Gemma3 full-vocab logits tensor.
- CLIP/LLaVA and PrefixMAE paths use best-effort `constrain_batch_model(...)`
  constraints around image features, q/k/v, attention maps, and hidden
  activations. Keep these constraints when editing HSDP paths.
- `LlavaGemma.generate_beam_search(...)` is a real cumulative-logprob beam search,
  not a greedy alias. It keeps EOS beams alive, supports `txt_feature_layer > 0`,
  and decodes only the last prompt hidden state during prefill to avoid a
  `[B, prompt_len, vocab]` logits tensor.

## Stateful Dataloader Resume

- `jax_llava` now carries the same full stateful dataloader infrastructure as
  `beifen-Paligemma`. Enable it with `dataset.stateful_dataloader: True`;
  `configs/remote_run_config.yml` enables it by default.
- This requires `torchdata==0.8.0`. Missing `torchdata.stateful_dataloader`
  should fail fast instead of silently falling back to non-exact resume.
- Stateful resume saves sidecars at
  `checkpoint_<step>/dataloader_state/process_<rank>.pkl` and restores WebDataset
  cursors, shuffle buffers, RandomMix state, worker RNGs, and topology metadata.
  It is exact only for the same process count, process-local batch size, worker
  count, prefetch factor, roots/types, mix weights, and seed offset.
- `input_pipeline.create_split` validates that training GCS roots match
  `config.zone` before reading/listing shards. Keep this guard to avoid
  cross-region transfer and accidental loops over nonexistent paths.

## TPU Manager & Job Queue

- **Check job status**: use `tcs` (alias) or `tpu check sqa` to view running/errored/finished jobs, their window IDs, TPU assignments, and log dirs. Do NOT manually parse xibo `data.json` to get job info — `tcs` is the canonical interface.
- **Queue a job**: `qsqa <dir_num>` from the working directory. This stages code (rsync to `/kmh-nfs-ssd-us-mount/staging/sqa/...`), registers with xibo (`tpu set-cur`), and adds to the MONITOR queue.
- **MONITOR queue file**: `/kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager/queue.json`. MONITOR dispatches pending jobs by calling `tpu run <alias> <user> dir=<dir_no>`, which re-stages from the working directory at dispatch time.
- **Directory numbers**: xibo maps dir numbers to working directory paths in `data.json`. `set-cur` only works for dir 1-100; for dir>100, register directly in `data['users']['sqa']['working_dir']`.
- **Eval-only jobs**: set `eval_only: True` and `load_from: <log_dir_path>` in `remote_run_config.yml`. The code resolves checkpoint paths from log dirs via GCS mirror.
- **Multiple jobs from the same codebase**: since MONITOR re-stages from the live working dir at dispatch time, use separate dir numbers pointing to separate directory copies to avoid config conflicts between queued jobs.


---

## `jax_llava_late_fusion_22_5ed73eb/AGENTS.md`

# JAX LLaVA Project Notes

Follow these notes when editing the JAX LLaVA training/data code in this repo.

## SFT Dataset Loader Notes

- The stage-2/SFT mix includes the LLaVA-OV1.5 image-shuffled data plus VQAv2,
  OKVQA, A-OKVQA, OCRVQA, GQA, TextCaps, Visual Genome QA, Visual Genome
  detection, and RefCOCO.
- Dataset aliases for the four LLaVA-1.5 missing SFT datasets are registered in
  `utils/data_util.py` as `okvqa-train`, `aokvqa-train`, `ocrvqa-train`, and
  `refcoco-train`.
- OKVQA and OCRVQA use the short-answer VQA prompt:
  `Answer the question using a single word or phrase.`
- A-OKVQA uses multiple-choice augmentation in the input pipeline: one grouped
  QA expands to four cyclic choice rotations, and the training target is the
  correct option letter. This matches the LLaVA-1.5 reported ~66K A-OKVQA SFT
  scale better than treating the stored grouped records as direct-answer only.
- OCRVQA is uploaded as the full train split, but SFT mix weights intentionally
  sample it at the LLaVA-1.5 ~80K scale. Do not infer the mix weight from the
  full uploaded 801K QA count unless explicitly changing the recipe.
- RefCOCO records store COCO absolute `xywh` boxes and grouped refs per image.
  The input pipeline expands one phrase-to-box training item per ref and formats
  targets as `<loc....>` tokens with the same `format_detection_prompt()` used
  by RefCOCOg eval.

## LLaVA-1.5 Reproduction Tracking

- Experiment spreadsheet:
  `https://docs.google.com/spreadsheets/d/1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ/edit?gid=1146448969#gid=1146448969`.
- Rows 146-148 on gid `1146448969` track the first LLaVA-1.5 reproduction
  run. Row 147 is the 7B target line; row 148 is the first init run:
  `CLIP-L @ 336 + gemma3-1B`, blip-3o pretrain, and SFT over LLaVA-OV1.5,
  VQA, GQA, and TextCaps style data.
- Row 148 WandB run: `exalted-haze-9 | Sqa24's workspace | jax-llava`.
- Row 147 target metrics recorded in the sheet:
  MME-P `1511`, VQAv2 `78.5`, TextVQA `58.2`, MMBench `64.3`,
  POPE `84.2`, VStar `~48.7`, OCRBench `29.7`, MMVP `24.7`,
  CountBench `~47.0`, VisWiz `50.0`, SEED-Bench image `66.1`,
  ScienceQA-IMG `66.8`, and GQA `62.0`.
- VStar, OCRBench, MMVP, CountBench, RefCOCOg, and ImageNet KNN are not
  original LLaVA-1.5 paper table metrics. Use them as additional probes only.
- The sheet POPE target `84.2` matches the paper's adversarial POPE split.
  Row 148 records `pope_adversarial_f1_stage2_final=80`, not the macro F1.
  The evaluator also logs macro F1 (`82.58` in the same final eval), but the
  spreadsheet value is adversarial and should be compared to the adversarial
  target.
- First row-148 run data: stage 1 used `blip3o-short`; stage 2 used
  LLaVA-OV1.5, VQAv2, GQA train, TextCaps train, and Visual Genome QA with
  weights `[22, 0.4, 0.94, 0.022, 1.7]`. It did not include OKVQA,
  A-OKVQA, OCRVQA, VG detection, RefCOCO, or ShareGPT text-only.
- Current `configs/remote_run_config.yml` differs from the first run: stage 1
  uses `cc12m`, and stage 2 adds `okvqa-train`, `aokvqa-train`,
  `ocrvqa-train`, `visual-genome-det`, and `refcoco-train` with weights
  `[22, 0.4, 0.009, 0.068, 0.08, 0.94, 0.022, 1.7, 0.86, 0.048]`.
- KNN ImageNet TFDS preprocessing should follow `config.dataset.resize_mode`.
  `stretch` directly resizes to the square canvas; `letterbox` preserves aspect
  ratio and pads, matching the normal train/eval transform family. Do not
  silently use center-crop KNN when the run config says `stretch` or `letterbox`.
- A gist-ready summary of the current image-shuffled LLaVA-OV1.5 dataloader is
  kept at `ideas/llava_ov15_dataloader_gist.md`.
- Parsed v5p-64 throughput for first LLaVA-style curriculum jobs:
  stage 1 median `5.63` steps/s all points (`5.69` filtered >2 steps/s);
  stage 2 median `3.91` steps/s all points (`3.94` filtered >2 steps/s).
  Finished row-148 stage-2 segment `20260531_004908_ggu3cd...` median was
  `3.84` steps/s over 17 logged points.

## Durable Checkpoint Notes

- Final training checkpoints should be mirrored to the same regional bucket
  under `pretrained-ckpts/qiao_zhicheng_hanhong_files/...`; this matches the
  shell helper `ltgcp` and protects checkpoints from ordinary bucket cleanup.
- `load_from_pretrained` params-only restore should first use the normal
  zone-local checkpoint path and then fall back to the same-zone
  `pretrained-ckpts` path. Known `gs://kmh-gcp-*` checkpoint paths are
  rewritten to the current target zone before restore to avoid cross-zone reads.

## HSDP Memory Notes

- `model.prompt_causal` defaults to `True`. This is the standard LLaVA-style
  mask: image prefix tokens are bidirectional, while prompt/text tokens remain
  causal. Set it to `False` only to reproduce the older local behavior where the
  entire image+prompt prefix was bidirectional.
- The projector/connector is its own optimizer group. Use
  `training.connector_learning_rate` (or legacy alias
  `training.projector_learning_rate`) to set its LR separately from the LM main
  group and vision encoder group.
- Eval generation uses task-specific token budgets:
  `eval_tokens_shortqa`, `eval_tokens_mid`, `eval_tokens_ocr`,
  `eval_tokens_refcoco`, `eval_tokens_pixelbench`, and
  `eval_tokens_mmbench`. These samplers still respect `sampling.beam_size`, so a
  deliberate beam-search final eval should set that once rather than patching
  every task.
- `utils/pjit_util.py` treats the last mesh axis as the model axis for `hsdp`.
  Batch/data arrays are sharded only over the preceding data axes; do not shard
  batch over every mesh axis or activations can conflict with model sharding and
  get gathered back to global-batch-sized attention buffers.
- Host-local input/output specs may temporarily fall back to all mesh axes when
  the current TPU logical mesh does not give each process exactly
  `1/process_count` of the data-axis positions. This is only an input boundary
  compatibility fallback for `global_batch/process_count` dataloaders; model
  activations still use the HSDP data-axis/model-axis constraints.
- The HSDP mesh must be process-major with the final model axis host-local when
  possible. `utils/pjit_util.py` now builds such a mesh before falling back to
  JAX's default `create_device_mesh`; this keeps `global_batch / process_count`
  dataloader batches compatible with `make_array_from_process_local_data`. The
  failure signature from the old default mesh was `process data has 32 elements.
  Process addresses 64 elements and global_shape=(256, 64)` on v5p-64.
- Training loss should use `token_xent_loss_from_hidden(...)`, not a full
  `embedder.decode(out)` over `(B, K + T, vocab)`. The chunked loss only scans
  labeled text positions and avoids the large Gemma3 full-vocab logits tensor.
- CLIP/LLaVA and PrefixMAE paths use best-effort `constrain_batch_model(...)`
  constraints around image features, q/k/v, attention maps, and hidden
  activations. Keep these constraints when editing HSDP paths.
- `LlavaGemma.generate_beam_search(...)` is a real cumulative-logprob beam search,
  not a greedy alias. It keeps EOS beams alive, supports `txt_feature_layer > 0`,
  and decodes only the last prompt hidden state during prefill to avoid a
  `[B, prompt_len, vocab]` logits tensor.

## Stateful Dataloader Resume

- `jax_llava` now carries the same full stateful dataloader infrastructure as
  `beifen-Paligemma`. Enable it with `dataset.stateful_dataloader: True`;
  `configs/remote_run_config.yml` enables it by default.
- This requires `torchdata==0.8.0`. Missing `torchdata.stateful_dataloader`
  should fail fast instead of silently falling back to non-exact resume.
- Stateful resume saves sidecars at
  `checkpoint_<step>/dataloader_state/process_<rank>.pkl` and restores WebDataset
  cursors, shuffle buffers, RandomMix state, worker RNGs, and topology metadata.
  It is exact only for the same process count, process-local batch size, worker
  count, prefetch factor, roots/types, mix weights, and seed offset.
- `input_pipeline.create_split` validates that training GCS roots match
  `config.zone` before reading/listing shards. Keep this guard to avoid
  cross-region transfer and accidental loops over nonexistent paths.

## TPU Manager & Job Queue

- **Check job status**: use `tcs` (alias) or `tpu check sqa` to view running/errored/finished jobs, their window IDs, TPU assignments, and log dirs. Do NOT manually parse xibo `data.json` to get job info — `tcs` is the canonical interface.
- **Queue a job**: `qsqa <dir_num>` from the working directory. This stages code (rsync to `/kmh-nfs-ssd-us-mount/staging/sqa/...`), registers with xibo (`tpu set-cur`), and adds to the MONITOR queue.
- **MONITOR queue file**: `/kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager/queue.json`. MONITOR dispatches pending jobs by calling `tpu run <alias> <user> dir=<dir_no>`, which re-stages from the working directory at dispatch time.
- **Directory numbers**: xibo maps dir numbers to working directory paths in `data.json`. `set-cur` only works for dir 1-100; for dir>100, register directly in `data['users']['sqa']['working_dir']`.
- **Eval-only jobs**: set `eval_only: True` and `load_from: <log_dir_path>` in `remote_run_config.yml`. The code resolves checkpoint paths from log dirs via GCS mirror.
- **Multiple jobs from the same codebase**: since MONITOR re-stages from the live working dir at dispatch time, use separate dir numbers pointing to separate directory copies to avoid config conflicts between queued jobs.


---

## `jax_llava_master_39b30fb_before_late_fusion/AGENTS.md`

# JAX LLaVA Project Notes

Follow these notes when editing the JAX LLaVA training/data code in this repo.

## SFT Dataset Loader Notes

- The stage-2/SFT mix includes the LLaVA-OV1.5 image-shuffled data plus VQAv2,
  OKVQA, A-OKVQA, OCRVQA, GQA, TextCaps, Visual Genome QA, Visual Genome
  detection, and RefCOCO.
- Dataset aliases for the four LLaVA-1.5 missing SFT datasets are registered in
  `utils/data_util.py` as `okvqa-train`, `aokvqa-train`, `ocrvqa-train`, and
  `refcoco-train`.
- OKVQA and OCRVQA use the short-answer VQA prompt:
  `Answer the question using a single word or phrase.`
- A-OKVQA uses multiple-choice augmentation in the input pipeline: one grouped
  QA expands to four cyclic choice rotations, and the training target is the
  correct option letter. This matches the LLaVA-1.5 reported ~66K A-OKVQA SFT
  scale better than treating the stored grouped records as direct-answer only.
- OCRVQA is uploaded as the full train split, but SFT mix weights intentionally
  sample it at the LLaVA-1.5 ~80K scale. Do not infer the mix weight from the
  full uploaded 801K QA count unless explicitly changing the recipe.
- RefCOCO records store COCO absolute `xywh` boxes and grouped refs per image.
  The input pipeline expands one phrase-to-box training item per ref and formats
  targets as `<loc....>` tokens with the same `format_detection_prompt()` used
  by RefCOCOg eval.

## LLaVA-1.5 Reproduction Tracking

- Experiment spreadsheet:
  `https://docs.google.com/spreadsheets/d/1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ/edit?gid=1146448969#gid=1146448969`.
- Rows 146-148 on gid `1146448969` track the first LLaVA-1.5 reproduction
  run. Row 147 is the 7B target line; row 148 is the first init run:
  `CLIP-L @ 336 + gemma3-1B`, blip-3o pretrain, and SFT over LLaVA-OV1.5,
  VQA, GQA, and TextCaps style data.
- Row 148 WandB run: `exalted-haze-9 | Sqa24's workspace | jax-llava`.
- Row 147 target metrics recorded in the sheet:
  MME-P `1511`, VQAv2 `78.5`, TextVQA `58.2`, MMBench `64.3`,
  POPE `84.2`, VStar `~48.7`, OCRBench `29.7`, MMVP `24.7`,
  CountBench `~47.0`, VisWiz `50.0`, SEED-Bench image `66.1`,
  ScienceQA-IMG `66.8`, and GQA `62.0`.
- VStar, OCRBench, MMVP, CountBench, RefCOCOg, and ImageNet KNN are not
  original LLaVA-1.5 paper table metrics. Use them as additional probes only.
- The sheet POPE target `84.2` matches the paper's adversarial POPE split.
  Row 148 records `pope_adversarial_f1_stage2_final=80`, not the macro F1.
  The evaluator also logs macro F1 (`82.58` in the same final eval), but the
  spreadsheet value is adversarial and should be compared to the adversarial
  target.
- First row-148 run data: stage 1 used `blip3o-short`; stage 2 used
  LLaVA-OV1.5, VQAv2, GQA train, TextCaps train, and Visual Genome QA with
  weights `[22, 0.4, 0.94, 0.022, 1.7]`. It did not include OKVQA,
  A-OKVQA, OCRVQA, VG detection, RefCOCO, or ShareGPT text-only.
- Current `configs/remote_run_config.yml` differs from the first run: stage 1
  uses `cc12m`, and stage 2 adds `okvqa-train`, `aokvqa-train`,
  `ocrvqa-train`, `visual-genome-det`, and `refcoco-train` with weights
  `[22, 0.4, 0.009, 0.068, 0.08, 0.94, 0.022, 1.7, 0.86, 0.048]`.
- KNN ImageNet TFDS preprocessing should follow `config.dataset.resize_mode`.
  `stretch` directly resizes to the square canvas; `letterbox` preserves aspect
  ratio and pads, matching the normal train/eval transform family. Do not
  silently use center-crop KNN when the run config says `stretch` or `letterbox`.
- A gist-ready summary of the current image-shuffled LLaVA-OV1.5 dataloader is
  kept at `ideas/llava_ov15_dataloader_gist.md`.
- Parsed v5p-64 throughput for first LLaVA-style curriculum jobs:
  stage 1 median `5.63` steps/s all points (`5.69` filtered >2 steps/s);
  stage 2 median `3.91` steps/s all points (`3.94` filtered >2 steps/s).
  Finished row-148 stage-2 segment `20260531_004908_ggu3cd...` median was
  `3.84` steps/s over 17 logged points.

## Durable Checkpoint Notes

- Final training checkpoints should be mirrored to the same regional bucket
  under `pretrained-ckpts/qiao_zhicheng_hanhong_files/...`; this matches the
  shell helper `ltgcp` and protects checkpoints from ordinary bucket cleanup.
- `load_from_pretrained` params-only restore should first use the normal
  zone-local checkpoint path and then fall back to the same-zone
  `pretrained-ckpts` path. Known `gs://kmh-gcp-*` checkpoint paths are
  rewritten to the current target zone before restore to avoid cross-zone reads.


---

## `one-benchmark-suite/AGENTS.md`

# AGENTS.md

Orientation for Codex / coding agents working in this repository.
Read this before answering repo questions or making edits.

## What This Repo Is

`one-benchmark-suite` is a benchmark registry, not a training framework.
The deliverable is a stable, machine-readable Python package layout that
other projects can import to run vision-related evaluations with minimal
glue code.

The authoritative human documentation is `README.md`. This file captures
the repo conventions that matter while editing.

## Package Shape

There is one Python package: `one_benchmark_suite/`.

- `contract.py`: documented benchmark protocol and sanity helpers.
- `registry.py`: discovers benchmarks by walking for `metadata.yaml`.
- `_pipeline.py`, `_logging.py`: shared heavy-eval helpers with lazy JAX /
  torch imports.
- `_zone.py`: rewrites the literal `💣` zone placeholder in config paths.
- `_sanity.py`: CPU-only mock helpers.
- `<category>/<benchmark>/`: one benchmark per directory.

Do not add training code, launch scripts, model trees, or broad framework
abstractions.

## Benchmark Layout

Every benchmark directory should have this 9-file layout:

```text
__init__.py
README.md
metadata.yaml
config.py
data.py
metrics.py
_impl.py
benchmark.py
sanity_check.py
```

`metrics.py` must stay pure Python / numpy and must not import JAX, torch,
transformers, fsspec, or webdataset. Heavy imports belong in `_impl.py` or
inside lazy helper functions.

## Public Contract

Each benchmark module exposes:

```python
NAME: str
METADATA: dict
get_default_config()
load_dataset(config, *, tokenizer=None, mock=False)
evaluate(predict_fn, config, *, tokenizer=None, **kwargs) -> dict
run_sanity_check(config=None) -> dict
```

Return values from `evaluate` and sanity checks must be JSON-serialisable.
Metric keys should match `metadata.yaml::metrics`.

## Tests

There are two fast, CPU-only layers:

- `python -m tests.run_sanity_checks`
- `python -m unittest discover tests/`

Sanity checks must not import `_impl.py`, touch GCS, require real
tokenizers, or load pretrained checkpoints.

Metric tests use stdlib `unittest` only. They should import pure metric
helpers and avoid JAX/torch/heavy eval code.

## GCS And Zones

Config paths that depend on the TPU zone use the literal `💣` placeholder.
Call `one_benchmark_suite.resolve_zone(cfg, zone)` before real GCS evals.

Do not hardcode a concrete zone bucket unless the benchmark is documenting
an external asset. Remote runs must read from the bucket matching their
zone; local development may list small paths but must not bulk-copy
datasets.

## Editing Rules

- Prefer existing benchmark patterns over new abstractions.
- Keep changes scoped to the requested benchmark.
- Use `rg` / `rg --files` for search.
- Use `apply_patch` for manual file edits.
- Do not revert user changes in a dirty worktree.
- Add concise comments only when they clarify non-obvious behavior.


---

## `tpu_manager/AGENTS.md`

# Repository Notes For Agents

This repository is a lightweight working copy for the local `MONITOR.py` flow.
Do not assume every file in this directory is active production code.

## Active Path

- Treat `MONITOR.py` as the main script for automatic resume and local queue handling.
- `MONITOR.py` intentionally calls `_tpu = 'python /home/jzc/zhichengjiang/working/xibo_tpu_manager/tpu.py'`.
  That external xibo checkout is the desired TPU command backend.
- On 2026-06-10, the copied xibo sandbox
  `/kmh-nfs-ssd-us-mount/code/qiao/work/xibo_tpu_manager_linux_user_sandbox_20260601`
  was applied to the external xibo checkout. Only code/docs were copied:
  `AGENTS.md`, `MONITOR.py`, `tpu.py`, and selected `utils/*.py`; runtime state files
  such as `data.json`, `lock.json`, `queue.json`, and `legacy.json` were intentionally
  not copied. Before future sandbox-to-xibo applies, preserve the remote env installs
  for `promise` and `torchdata==0.8.0`.
- The local queue used by this monitor is `./queue.json`, via `MONITOR.py`'s `QUEUE_FILE`.
  This is separate from the xibo checkout's queue files.
- `find_saving_window.py` is still active: `MONITOR.py` shells out to it when deciding
  which ancestor window has a useful checkpoint.
  Pass the current user to it; window ids are only unique within a tmux/user namespace,
  and different users can have the same numeric window id.
- `see_log.py` is kept for `/home/sqa/.bash_aliases` helper `cl <window_id>`.
- `audit_duplicate_aliases.py` is a read-only helper for xibo `data.json`
  alias hygiene. It prints every TPU lease name with multiple aliases and marks
  groups with more than two aliases or self-aliases as `DIRTY`; these groups can
  make `tpu fang` fail and leave `mount-disk` pointed at a stale old TPU.
- `clean_duplicate_aliases.py` is the write-capable alias hygiene helper. It is
  dry-run by default; `--apply` uses the external xibo `data.json` lock and writes
  a backup under `logs/alias_cleanup/` before modifying xibo state. Its cleanup
  rule keeps one monitor-style tmp alias such as `v5p-64-tmp201` pointing at the
  real TPU, retargets any other monitor-style tmp aliases for that same TPU to
  unique dummy names like `kmh-tpuvm-v5-64-tmp201-do-not-exist`, deletes duplicate
  non-script aliases, and deduplicates `all_tpus` / legacy `zone_tpus` plus
  `pre_info.spot` / `pre_info.preemptible`.
- When `MONITOR.py` is started in its default monitor-loop mode, it runs
  `clean_duplicate_aliases.py --apply --no-wait-lock` once before loop 1. This is
  the "loop 0" hygiene pass so `fang`/`mount-disk` do not see dirty alias groups.
  Queue subcommands do not trigger it. If the xibo data lock is busy, cleanup skips
  and monitor continues; set `MONITOR_SKIP_ALIAS_CLEANUP=1` only for debugging.
- The only active local `utils` modules are:
  - `utils/constants.py`: external xibo paths, log labels, allowed TPU regions.
  - `utils/data_io.py`: minimal reads from the external xibo `data.json` and `lock.json`.

## Queue Semantics

- Queue jobs are consumed only by `USER == "sqa"` in `MONITOR.py`.
- The monitor handles resume work before queue work. Queue priority is only used among
  queued jobs after resume handling has finished for the loop.
- Queue entries may have:
  - `priority`: any integer; larger values are tried first.
  - `wandb_notes`: copied from the job config for `queue.json` readability.
- The usual user-facing helper is `qsqa` from `/home/sqa/.bash_aliases`.
  It stages the current directory, runs `tpu set-cur`, then calls local `MONITOR.py queue`.
  Supported forms include `qsqa <dir>`, `qsqa <dir> 10`, `qsqa <dir> priority=10`,
  and `qsqa <dir> p=10`.
- Queue/staging dir numbers must stay in xibo's accepted range `1..100`. Do not use
  `101`, `102`, etc.; `qsqa` can still add a local pending queue entry after `tpu set-cur`
  rejects those numbers, but that entry has no usable xibo working-dir mapping.
- Missing `priority` and `wandb_notes` are backfilled lazily for old pending/running
  entries when queue list/run logic reads them.
- `preferred_zone` exists in the queue schema but is not a current workflow dependency.
- A queue dispatch is considered consumed once the external `tpu run` output shows that
  a tmux job was created. Later `[FAIL]` lines from sheet/alias bookkeeping should not
  put the queue entry back into pending, or the same queued job can create many windows.
- Conversely, `tpu run` returning code 0 is not enough. The xibo backend can print
  `TPU ... is reserved by <user>` and `Quiting...` with returncode 0; without a tmux
  creation signal, the queue entry must stay pending.
- Before queue creates a job, `MONITOR.py` first runs `zhan/fang/mount-disk`, treats
  `[FAIL]`/error text in that output as failure even if returncode is 0, then SSHes to
  all TPU workers and requires `python -c "import jax"` to print `JAX_OK`.
- `tpu mount-disk` must not trust `/home/sqa/.disk_mounted` alone. That marker can
  survive while `/kmh-nfs-ssd-us-mount` is not actually mounted, causing staged code
  copies to fail with `cp: cannot stat ... staging/sqa/...` and then
  `/home/sqa/main.py` missing. The xibo mount guard should require both the marker and
  `mountpoint -q /kmh-nfs-ssd-us-mount`; monitor's `tmd` wrapper also verifies the
  mount on all workers and reruns `tpu mount-disk --force` once if the check fails.
  The `resume_next_round` direct-old-TPU path must do the same check explicitly because
  external `tpu resume ... tpu=<old_tpu>` creates the child tmux window without running
  `mount-disk` first.
  For the xibo CLI, put `--force` after the TPU/alias (`tpu mount-disk <name> --force`);
  `tpu.py` reads `args[2]` as the TPU name.
- Some xibo alias rows are dirty: one old TPU can have more than the normal pair of
  tmp aliases, for example `v5-64-tmp201`, `v5p-64-tmp201`, and the real TPU name.
  The external `fang` command refuses these with "found more than 2 aliases for the old
  TPU"; `MONITOR.py` should skip those aliases when selecting a new alias.
- Before queue runs any destructive `mount-disk`/`tmd` step, it SSHes to the candidate
  TPU and runs a remote occupancy probe. The probe first checks whether TPU device files
  are held (`/dev/vfio/*` or `/dev/accel0`), then falls back to a narrow xibo
  training-command signature (`python main.py --workdir=/kmh-nfs-ssd-us-mount/logs/...`).
  If that probe is `busy` or `unknown`, skip the candidate. This guards against
  xianbang-style cases where two lease names point at the same physical VM without
  treating every unrelated Python process as a TPU job.
- The remote occupancy probe may time out while still returning partial stdout from
  workers that did answer. If stdout contains matching processes, classify it as `busy`
  rather than `unknown`; the important signal is that at least one worker is occupied.
- The central xibo reserve locks live under `/kmh-nfs-ssd-us-mount/code/qiao/tpu_lock`
  and are keyed by exact TPU lease name with a 30-minute lifetime. They are useful as an
  extra same-name race guard, but they do not prove a physical worker is free: a lock for
  `...-b6da37` will not block `...-c63dcd` even if both lease names reach the same VM.
- Within each queue selection pass, non-Asia candidates are tried before
  `asia-northeast1-b`. Queue jobs are from-scratch launches and must use exact
  cost classes, not "any larger card": low-cost jobs use only `v6e-32` or
  `v5/v5p-64`, high-cost jobs use only `v6e-64` or `v5/v5p-128`, and GPT-B/DeiT
  jobs keep the small-card rule (`v6e<=16` or `v5/v5p<=32`). A queue
  `preferred_type` is only a preference inside these allowed classes; it must not
  force a larger low/high-cost card.
- TPU selection must not trust `tou`/`wrap_master.py` IDLE alone. Newly-created jobs can
  look IDLE before worker-side processes appear. Before queue uses an idle TPU, also
  check external `data.json` plus local tmux windows; TPUs with existing `status=running`
  windows or `status=error` windows that are judged false-positive errors are occupied.
- `tou` is backed by the `yizhitou` tmux session, which continuously refreshes
  `wrap_master.py`'s cache. `/home/sqa/.bashrc` `yizhitou` now runs local
  `run_yizhitou_loop.sh`: each successful `tou --cache false` audit writes
  `/tmp/yizhitou_refresh_sqa.event`, then sleeps 60 seconds before the next audit.
  `MONITOR.py` waits on that event file between loops instead of always sleeping five
  minutes; if `yizhitou` refreshes while a monitor loop is still running, monitor starts
  the next loop immediately after the current loop finishes. A watchdog fallback still
  starts a loop after `MONITOR_TOU_EVENT_TIMEOUT_SECONDS` (default 900 seconds) if the
  event is missing. `MONITOR.py` also parses reported cache age and treats ages above
  `TOU_MAX_CACHE_AGE_SECONDS` (currently 120 seconds) as stale. If the cache is stale
  but a `wrap_master.py --cache false` refresh process is already running, do not kill
  it; just abort the current monitor loop and wait for the refresh event.

## Resume State

- `sqa.json` is the monitor's local memory. `running` is only an in-progress lock,
  while `finished` means "this window has already been handled by the monitor".
- When reporting the user's current active jobs, do not summarize every historical
  `data.json` entry. The user's active jobs are the leaf jobs whose tmux windows still
  exist in the `sqa` tmux session and have not been superseded by `extra_msgs.child`.
  Old `data.json` records can remain `error` or even stale `running` after their tmux
  windows are gone; those are history, not current work.
- When reporting active job status, immediately diagnose any active `Error` leaf enough
  to classify it. No-card / TPU preempt / deleted-card failures are expected operational
  churn; code, config, checkpoint, environment, or data-loader errors are abnormal and
  should be called out instead of only reporting `Error`.
- `tpu check` can show a false `Staging` status for a `data.json status=running` leaf
  whose tmux pane is actually idle at a shell prompt after a bare `^C`. In that case,
  inspect the pane/log for the last real training step and checkpoint. `mer <window>`
  only appends the resume-needed `Retrying: SSH command error` marker; if xibo still
  reports `Staging`, also mark that leaf `status: error` in external `data.json`, keep
  pretty JSON formatting, and ensure the window is not in local `sqa.json` `running` or
  `finished` so the monitor can resume it.
- To manually re-enable a historical error leaf that the user still wants resumed,
  recreate an empty tmux window with the same id in the `sqa` session and remove that
  window id from local `sqa.json.finished` / `sqa.json.running` if present. The monitor
  will then see it in `tpu check sqa` and apply the normal checkpoint-source logic.
  The recreated tmux pane does not need to run the old command.
- A resume/rerun attempt is considered consumed once the external command output shows
  that a tmux job was created. The triggering failed window must then be moved to
  `finished`, even if later sheet/alias bookkeeping prints `[FAIL]`.
- If a child fails before writing a complete checkpoint, `find_saving_window.py` can
  resolve back to the same parent checkpoint. That is expected; the important invariant
  is that each successful child creation marks the triggering failed window finished.
- `find_saving_window.py` must not treat a bare `Saving checkpoint...` line as usable.
  A checkpoint is usable only after a later `saved to` line. If the latest `Saving`
  step is newer than the latest `saved to` step, remove the corresponding
  `checkpoint_<step>` candidate from the logdir/GCS path before returning that window;
  otherwise the external xibo resume path may load an empty half-written checkpoint.
- `MONITOR.py` must treat `find_saving_window.py` stderr text saying
  `no complete checkpoint found anywhere in chain; reached root window N` as
  action `rerun` for root `N`. Older monitors only matched the legacy text
  `no 'saving' found anywhere in chain`, which caused checkpoint-free failures
  such as LLaVA window `7443` to be incorrectly handled as `resume` from an empty
  failed logdir.
- After walking a window's father chain, `find_saving_window.py` also does a conservative
  same-logical-job scan using `(job_dir_id, spreadsheet_notes/job_tags)` and chooses the
  highest complete checkpoint if it is newer than the father-chain checkpoint. This catches
  stale duplicate branches such as window `6886`, whose father was old `6833` even though
  sibling branch `6852 -> 6856 -> 6871` had already produced a newer complete checkpoint.
- The external xibo backend used by `_tpu` should strip inherited resume-only config
  overrides (`--config.load_from`, `--config.wandb_resume_id`, `--config.stage`) before
  composing a resume/rerun command. Otherwise a window whose own logdir has no usable
  checkpoint can still launch with an old parent `--config.load_from`, causing stale
  checkpoint restores and WandB monotonically-increasing-step warnings.
- If an error window already has a recorded `child`, or its checkpoint source has a newer
  child than this window, treat it as stale and mark it handled locally instead of
  resuming it again.
- When checking whether a checkpoint source's child supersedes an error window, first
  walk the error window's `extra_msgs.father` chain. If that child is on the father
  chain, it is an ancestor path to the current leaf, not a competing newer child.
- Do not add retry cooldowns to solve duplicate resumes. The desired behavior is to try
  a still-failed job again on the next loop. The real invariant is: once a new tmux job is
  created, the source window must be marked finished locally.
- Resume selection follows the same extra occupancy check as queue selection: an idle TPU
  is unavailable if `data.json` and tmux show an existing running window on that card, or
  an error window whose recent log tail does not contain a resume-needed marker.
- Resume-needed error markers include `Retrying: SSH command error`,
  `Unable to initialize backend 'tpu': ABORTED`, and random JAX distributed aborts such
  as `Fatal Python error: Aborted` / `JAX distributed service detected fatal errors` /
  `CoordinationService/Heartbeat` with `DEADLINE_EXCEEDED`. These random aborts often
  leave the TPU visible, so the monitor should try the old TPU first when it is idle,
  while still respecting `tou`, data/tmux occupancy, and remote busy probes.
- Failed worker startup where the staged code is missing, for example
  `python: can't open file '/home/sqa/main.py'` or `cp: cannot stat ... staging/sqa`,
  is also a resume-needed marker. This usually means not all TPU workers received the
  staged code before distributed JAX startup; treating it as a false-positive running
  error strands the job.
- Failed worker startup with `ModuleNotFoundError: No module named 'jax'` is also a
  resume-needed marker. It usually means a launch raced an incomplete or wrong
  `mount-disk`/alias environment; first force-mount the correct alias/TPU and verify
  all workers can `import jax`, then rerun from the same root window if no checkpoint
  was ever written.
- For random JAX aborts, `tou` may still report the old TPU as busy under `sqa` because
  dead worker processes have not fully cleared. If the busy users are only the current
  user and `data.json` plus tmux do not show any other active window on that TPU, the
  monitor may resume directly on the old TPU instead of treating it as unavailable.
- Before resume/rerun creates a child tmux job, `MONITOR.py` runs the same
  `zhan/fang/mount-disk` output check and all-worker JAX import sanity check as queue.
  If that check fails, clear the local `running` marker and retry the failed source in a
  later loop instead of creating a doomed child window.
- Resume/rerun also runs the same pre-`mount-disk` remote occupancy probe as queue. A
  candidate whose TPU devices or xibo training command are active, or whose occupancy
  cannot be checked, must be skipped before `tmd`, because `mount-disk` can remove
  `/home/sqa/.local` and kill jobs on the same physical worker.
- Training-phase checkpoint resume is exact-type: if `find_saving_window.py` returns
  action `resume` and the job is still in training, `MONITOR.py` must only choose the
  same TPU type as the original job, although it may use another allowed zone/region
  with that same type. Do not fall back from a checkpointed training `v6e-64` run to
  `v5p-64`, or from any checkpointed training topology to a different TPU type.
- Eval-phase resume is topology-flexible. If the failed/root job is `eval_only` or its
  log shows it has entered final eval, `MONITOR.py` may resume/rerun on a different TPU
  type and may use a larger TPU than the normal cost class. This still respects allowed
  zones and hard job constraints such as the LLaVA-1.5 reproduction v5-only rule.
- Checkpoint-free training `rerun` may choose a new type by exact cost class, because
  it is starting from scratch. The cost classes are exact: low-cost `v6e-32` or
  `v5/v5p-64`; high-cost `v6e-64` or `v5/v5p-128`; GPT-B/DeiT `v6e<=16` or
  `v5/v5p<=32`. `--same-type-only` still forces checkpoint-free reruns to keep the
  original type.
- Jobs whose notes contain `llava-1.5 reproduction` are low-cost but v5-only:
  from-scratch launches should use exactly `v5/v5p-64` and must not use v6/v6e,
  because the reproduction job OOMs on v6. This restriction applies to queue,
  resume fallback, and direct old-TPU resume buffers; queue `preferred_type`
  must not override it.
- If `tou` cache is stale during any resume path, do not continue selecting TPUs from
  that output. Restart `yizhitou`, clear any local in-progress marker for the current
  window, and let the next monitor loop retry with fresh cache.
- `resume_next_round` buffer resumes must still run the remote occupancy probe before
  directly reusing the old TPU. `tou` can report the old TPU as idle while worker-side
  `python main.py --workdir=...` processes are still alive. If the old TPU is remotely
  busy, remove the buffer entry and treat the job like the old TPU is unavailable so it
  falls back to a different card.
- `tou` may omit a TPU whose GCP state is `DELETING`; this is not a true ambiguous
  state. `check_job_status` should classify `DELETING`/`deleted` as `deleted`, and
  `_get_tpu_usage_from_tou` should distinguish a missing lease from a malformed visible
  line. Missing old TPUs should go through the normal deleted-card fallback path instead
  of being skipped as "状态不确定". This happened on 2026-06-02 for window `7154` on
  `kmh-tpuvm-v5p-64-kangyang-01-5bdd6a4b`.

## Duplicate Window Incident

- On 2026-05-14, repeated queue/resume windows were caused by success misclassification:
  the external `tpu run`/`resume` command created a tmux window, then later printed
  `[FAIL] get_zone_pre...` or sheet/alias bookkeeping errors. Older monitor logic treated
  any `[FAIL]` as command failure, moved queue entries back to pending, or failed to
  mark the source error window as finished.
- Correct handling is based on creation signals such as `Successfully created job in
  tmux window` or `run/resume/rerun job ... with new windows id N`. Once those appear,
  queue entries are consumed and source resume windows are finished, regardless of later
  bookkeeping errors.
- Manual cleanup for duplicate error windows should be non-destructive. Group current
  `status == "error"` windows by logical job, usually `(job_dir_id, spreadsheet_notes or
  job_tags)`. Ignore `resumed` and `rerunned` windows when counting how many error
  windows remain.
- When choosing which duplicate error leaf to keep, use an effective step, not only the
  error leaf's own log. Read the leaf's `log_dir/output.log` and also walk
  `extra_msgs.father` through its resume/rerun ancestry, reading each ancestor
  `output.log`. Keep the error leaf whose leaf-plus-ancestor chain has the largest parsed
  step; this preserves leaves like `6528` whose own resume failed early but whose father
  `6517` had trained much farther than another duplicate branch. Ties should prefer the
  latest leaf window.
- Step parsing must handle more than `step N` text. Training logs also use bracketed
  metric lines such as `logging_util.py:105] [75300] train_...`, and restored checkpoint
  paths like `checkpoint_400320` are meaningful progress signals for failed resume
  attempts.
- If `spreadsheet_notes`/`job_tags` are empty, do not blindly merge all errors with the
  same `job_dir_id`. Inspect `extra_configs`, `stage_dir`, `log_dir`, and the loaded
  checkpoint before deciding whether they are the same logical job.
- Mark the other duplicate error windows as `killed` with `extra_msgs.dedupe_*` metadata.
- The 2026-05-14 cleanup wrote a backup of the external xibo `data.json` and a report
  under local `logs/manual_dedupe_error_windows_*.json`. The cleanup intentionally did
  not delete historical job records or logs.
- On 2026-05-17, window `6623` failed with `ModuleNotFoundError: No module named 'jax'`
  because the preceding `ftmd` step printed `[FAIL] Failed to fang new TPU...` while
  returning 0. The monitor treated that as success, then `resume` quick-registered the
  TPU and created a tmux job on a card that had not actually received the mounted JAX
  environment. This is why `ftmd` output markers and explicit JAX checks matter.

## TPU Region Policy

- Resume and local queue dispatch should only use TPUs in:
  - `us-central1`
  - `us-east5`
  - `asia-northeast1-b`
- When more than one idle TPU is available, prefer non-`asia-northeast1-b` TPUs
  before Asia TPUs. LAION-400M is only available in Asia and Kaiming wants to
  preserve those cards for that workload. If Asia is the only viable idle
  capacity, monitor/queue may still use it.
- There is no longer a special LLaVA-OV1.5 restriction to `us-central1`; datasets are
  available in all allowed regions.
- Parse resume target zones from the real zone suffix in `log_dir`, not from the first
  zone-like string in the TPU name. TPU names can contain text such as
  `us-central1-spot-...`; that is not a zone. Prefer the last allowed zone match from
  the log path, such as the `_<zone>__...` suffix.
- On 2026-06-02, quota was being held by stale GCP TPU nodes stuck in `DELETING`.
  To audit this, run `gcloud compute tpus locations list` and query each location with
  `gcloud compute tpus tpu-vm list --zone=<zone> --filter=state=DELETING`. A second
  `gcloud compute tpus tpu-vm delete <name> --zone=<zone> --quiet --async` can unblock
  stale deletes. This cleanup removed old `DELETING` nodes including several v5p-64s in
  `us-east5-a` from 2026-05-28 and `kmh-tpuvm-v5p-64-spot-llqakha3n` from 2026-04-12;
  final full-location scan showed no remaining `DELETING` TPU VMs.

## ImageNet kNN / Remote Environment Notes

- On 2026-05-28, `PaliGemma-baseline` and `beifen-Paligemma` moved their
  PyTorch-based ImageNet kNN eval loaders to zone-local TFDS. The intended behavior is
  to read ImageNet from `gs://kmh-gcp-<region>/tensorflow_datasets` and avoid copying
  ImageNet into each new logdir or stagedir.
- For remote eval sanity, prefer a finished stagedir from `tpu check sqa`, copy only that
  small code stagedir, set `eval_only: True`, `final_eval_tasks: [knn_full]`, clear
  `wandb_resume_id`, and point `load_from` at the finished run's logdir/checkpoint.
- Before debugging remote eval on a reused TPU, run `tpu mount-disk <tpu> --force` and
  verify all workers can import the required Python modules. A missing package can look
  like a model/eval bug while the real issue is an incomplete mount environment.
- The xibo `mount-disk` v5/v6 Python env must include `promise`, because
  `tensorflow_datasets` imports it. Requirement strings containing shell metacharacters,
  such as `huggingface-hub<1.0,>=0.23.0`, must be quoted in the generated remote shell
  command or bash interprets `<` as redirection.
- The first TFDS kNN sanity used window `6952` as the reference finished job. The final
  correct run restored `checkpoint_150000` from the same us-east5 run and reported
  `knn_full_acc_final=1.488` versus the old loader's `1.628`. This is close in absolute
  percentage points but not bit-identical, likely due TFDS/TF resize/decode versus the
  old PyTorch/PIL preprocessing path.
- On 2026-05-31, `jax_llava` and `beifen-Paligemma` added PCA whitening for ImageNet
  kNN after feature extraction. On 2026-06-01 this was changed to report both normal
  raw-feature cosine KNN and PCA-whitened cosine KNN from one feature extraction.
  The legacy metric name, for example `knn_full_acc_final`, is the raw/normal KNN;
  the explicit duplicate `knn_full_acc_raw_final` is also logged, and
  `knn_full_acc_pca_whitened_final` is the whitened result. Fit whitening on the KNN
  train/reference features only, then apply the same transform to train and validation
  features: `(x - train_mean) @ eigvecs / sqrt(eigvals + eps)`. Defaults:
  `eval.knn_eval_raw_and_pca_whitened=True`, `eval.knn_pca_whitening=True`,
  `eval.knn_pca_whitening_eps=1e-5`, `eval.knn_pca_whitening_dim=0` (keep all dims),
  `eval.knn_pca_whitening_batch_size=65536`.
- On 2026-06-01, run `z8ceupo9` was re-evaluated with the copied stagedir plus current
  TFDS/PCA-whitened KNN code. Because the original checkpoint lived in `us-central1` but
  no clean us-central1 card was available, only `checkpoint_150000` was copied to the
  same relative path under `gs://kmh-gcp-us-east5/...`, then eval ran on
  `kmh-tpuvm-v6e-16-kaiminghe-269fe1` in `us-east5-b` using
  `gs://kmh-gcp-us-east5/tensorflow_datasets`. Result:
  `knn_full_acc_final=56.73` at step `150000`, W&B eval run `8pzhuygq`, logdir
  `/kmh-nfs-ssd-us-mount/logs/sqa/paligemma-baseline/20260601_0044_z8ceupo9_whitened_knn_kmh-tpuvm-v6e-16-kaiminghe-269fe1_us-east5-b__eval_only`.

## PaliGemma SFT From Pretrain

- To run an SFT stage from a finished pretrain job, start from the finished pretrain
  job's stagedir rather than the current worktree. Copy only the small code stagedir
  into `/kmh-nfs-ssd-us-mount/code/qiao/work/...`, then patch configs. This keeps model
  code and checkpoint structure matched to the pretrain run.
- In that copied stagedir, set `configs/remote_run_config.yml` `finetune: True`.
  `configs/load_config.py:remote_run` will then load `configs/finetune_config.yml`.
- Keep the finetune model architecture aligned with the pretrain checkpoint before
  setting `load_from_pretrained`: `patch_size`, `image_size`, `txt_feature_layer`,
  encoder depth, and `enc_cross_attn_split` must match. Training-only choices such as
  optimizer, LR, weight decay, and whether to freeze LM can be changed for SFT.
- SFT is an explicit exception to pretrain soft-cap matching: disable soft caps by
  setting `model.attn_logits_soft_cap = 0.0` and `model.final_logit_softcap = 0.0`
  in `configs/finetune_config.yml` unless the user explicitly asks otherwise.
- Use `load_from_pretrained` for the pretrain logdir when starting a fresh SFT run.
  Reserve `load_from` and `wandb_resume_id` for resuming an interrupted SFT run.
- `PaliGemma-baseline` and `beifen-Paligemma` also support an in-process
  pretrain->SFT curriculum through `training.curriculum: pretrain_sft_two_stage`
  with `finetune: False`. This keeps one workdir and global checkpoint stream:
  `load_from` step `< stage1_steps` resumes pretrain, `== stage1_steps` restores
  params only into the SFT/no-decoder model with a fresh optimizer, and
  `> stage1_steps` resumes SFT fully. Do not use `load_from_pretrained` in this
  two-stage path; keep it for the legacy `finetune: True` finetune-only config.
  The stage-1 boundary checkpoint is copied to durable `pretrained-ckpts/...`
  before switching stages.
- As of 2026-06-08, `beifen-Paligemma/configs/remote_run_config.yml` is the active
  runnable two-stage config: 150K-step 512px MAE-B pretrain followed by 90K-step SFT
  on shuffled LLaVA-OV1.5 plus the current VQA/grounding mix, with stage-2 Adam
  `1e-5` and weight decay `0.002`.
- As of 2026-06-08, `PaliGemma-baseline/configs/remote_run_config.yml` is also an
  active runnable two-stage config under `sharding: hsdp`: 150K-step 512px sandwich
  MAE-L + Gemma3-1B pretrain followed by 90K-step SFT on the same shuffled
  LLaVA/current VQA/grounding mix, with stage-2 Adam `1e-5` and weight decay `0.002`.
- Before queueing full SFT runs across the normal monitor, copy the chosen pretrain
  checkpoint to every allowed zone with `tpu cc` so cross-zone restore can work:
  `us-central1`, `us-east5`, and `asia-northeast1-b`.
- Before launching eval-only jobs from an existing `load_from` checkpoint, also copy
  the latest complete checkpoint to all three allowed zones with `tpu cc`. The eval
  code resolves `load_from` into the current TPU zone's bucket, so a same-path
  checkpoint must exist under `gs://kmh-gcp-us-central1/...`,
  `gs://kmh-gcp-us-east5/...`, and `gs://kmh-gcp-asia-northeast1-b/...` before launch.
  On 2026-06-10, eval window `7457` failed because it ran in `us-central1-a` while the
  source run `20260601_032005_3g1urd...` only had `checkpoint_7375` in `us-east5`.
- For the 2026-05-30 SFT follow-up to
  `[150K steps, muon 2e-5 wd2e-3]`, keep the newer expanded eval set from
  `beifen-Paligemma`, including `gqa`, `vizwiz`, `scienceqa_img`, and `seed_bench`.
  The SFT training mix is `llava-ov-1.5-instruct`, `vqav2`, and `gqa-train`; use the
  GQA question count in millions as its mix weight, currently `0.94`.
- Before queueing the real sweep, run a lightweight remote finetune debug config that
  restores the pretrain checkpoint and exercises all three paths: a train step, online
  eval, and final eval. Keep KNN and VLM eval sample counts capped in that smoke run.
- On 2026-05-30, the SFT runs showed an apparent train-accuracy spike/drop around
  steps 15k-18k. This was not a plain dataloader seed reset: the staged
  `beifen-Paligemma` code sets `data_seed_offset = dataset.data_seed_offset +
  checkpoint_step(load_from)` for `load_from` resumes, and the logs showed offsets
  `15000` and `18000` after resume. The artifact came from logging steps past the last
  complete checkpoint, then resuming from that older checkpoint with the same WandB run
  id. Example: window `7056` logged through `17900` but only had a complete checkpoint
  at `15000`; window `7061` resumed from `15000` and re-ran `15100..18000`, producing
  lower train acc and W&B warnings like `Tried to log to step 17400 that is less than
  the current step 17701`. Treat these duplicate-step ranges as W&B/history artifacts
  unless eval metrics or later accepted logical checkpoints show a real regression.
- Current dataloader resume seeding is a non-repetition heuristic, not exact replay of
  the infinite mixed data stream. Exact continuation would require saving DataLoader /
  WebDataset / RandomMix worker RNG state or skipping the stream by global sample count.
  For SFT, shorter checkpoint intervals reduce the amount of logged-but-uncheckpointed
  work that can be replayed after preemption.
- On 2026-06-11, window `7471` showed very slow SFT throughput after resuming from
  `7435`: `7435` ran around `0.6-0.8` steps/s and `7471` first logged step `3100` at
  `0.048` steps/s, while comparable older v5p-64 SFT runs with the same 512/256,
  `batch_size=256`, `freeze_lm=False`, and `360M` trainable params reached about
  `8` steps/s. The culprit was not TPU compute or full LM finetuning; the staged code
  for `7471` was an old stateful dataloader copy without `batch_hydrate` and without
  scaling `item_shuffle_size.llava_ov15=50000` by `world * num_workers`. On v5p-64 this
  means 8 processes x 16 workers = 128 streams, so every worker tried to keep a 50k
  raw-image buffer. Current `beifen-Paligemma/input_pipeline.py` fixes this with
  `_scaled_shuffle_size` (50k becomes about 12.5k for 128 streams) and batched hydration
  of restored refs. Existing resume windows that were staged before that patch will not
  pick it up; re-stage/requeue from the patched worktree instead of plain-resuming the
  old staged directory.
- On 2026-06-11, fresh from-pretrained SFT window `7476` exposed a config/model
  compatibility bug: `finetune_config.yml` contained
  `model.rope_scale_when_interpolate`, but the finetune path constructed
  `PaliGemmaEncDec(**config.model, ...)` directly, so Flax raised
  `unexpected keyword argument 'rope_scale_when_interpolate'`. Keep
  `_create_model(...)` as the single constructor path for eval-only and finetune; it
  strips training-only model config keys before creating the module.
- Be careful with `rerun` on interrupted SFT windows. A plain `rerun` may keep the old
  `wandb_resume_id` but drop `load_from`, causing a fresh train-from-pretrain run whose
  early-step logs are ignored by WandB because the run already reached later steps.
  For interrupted SFT continuation, prefer `resume` from the latest complete finetune
  checkpoint and keep `wandb_resume_id`; use a fresh WandB id only for an intentional
  restart from pretrain.
- Also on 2026-05-30, SFT `valid_tokens_per_sample` decreased steadily over training.
  `valid_tokens` is computed directly from `labels != -100`, so this is a data-stream
  effect, not model behavior. Audits were same-region only (`us-east5` TPU reading
  `gs://kmh-gcp-us-east5/...`). Shard-level audits did not show a simple per-shard
  monotonic sort: all-shard prefix audit `u8hxsbpk`, deep first-position audit
  `yytlsvoj`, and light first-12-position audit `j1g964fg` all had near-flat
  first-vs-last shard curves. The decisive reproduction was the stream-level simulator
  `1oqq2dm5`: no model, no image decode, just the runtime-like `RandomMix` /
  `VQAv2IterableDataset` label stream, and rank0 still dropped from
  `valid_tokens_per_sample ~= 85` at step 100 to `~=65` at step 5000 while
  `llava_ov15_fraction` stayed around `0.94`. Therefore the drift is from the actual
  iterable stream order/buffering, not W&B, optimizer, eval, or dataset-source mix.
- Be careful when auditing SFT stagedirs after the fact. The running windows' `output.log`
  `FLAGS.config` is the source of truth. Some SFT windows ran an older staged copy whose
  log showed `input_pipeline.py:1358`, `dataset.num_workers: 32`, `prefetch_factor: 4`,
  only `item_shuffle_size.default: 512`, and no `stream_start_skip`, even though the NFS
  stagedir later visible to agents had been patched to `num_workers: 16`, per-type
  `item_shuffle_size: 1024`, and `stream_start_skip`. Do not assume the current stagedir
  contents are exactly what an already-running remote process imported.
- The mitigation added to `beifen-Paligemma` is a per-worker `dataset.stream_start_skip`
  plus larger per-type `item_shuffle_size`; SFT configs use `num_workers: 16`,
  `prefetch_factor: 2`, `item_shuffle_size` 1024 for `llava_ov15`/`vqav2`/`gqa`, and
  startup skip 2048/1024/1024 respectively. Existing already-running jobs do not pick
  this up until restarted/resumed from patched code. A same-region stream audit of this
  patched config, W&B `yjugt0wy`, did not flatten the metric: rank0 went
  `86 -> 64 -> 82` over the first 5000 simulated steps while the source mix stayed
  stable. Treat `stream_start_skip` as a phase/jitter mitigation only. It cannot remove
  long-range length drift caused by sequential per-worker tar streams plus finite local
  shuffle buffers. A real fix should shuffle after `RandomMix` with a larger mixed
  buffer, or otherwise make batching draw from a stationary cross-stream pool.
- A test-only "resample one random shard per worker epoch" simulation, W&B `o40migae`,
  was not a fix either: it started high but dropped to about `54` tokens/sample by
  step 5000 with the same stable source mix. Do not assume random shard order alone
  solves the SFT length curriculum; the fix needs example-level mixing or an offline
  globally shuffled dataset.
- A QA-expanded mixed shuffled dataset experiment was tried and abandoned because it
  duplicated image bytes and was too slow/heavy for the workflow. The related
  `sft_mix` reader, aliases, and builder were removed from `beifen-Paligemma`; the
  active path is the lighter raw LLaVA image-level shuffle below.
- The replacement one-time shuffle should only shuffle `llava-ov-1.5-instruct`, because
  the length drift appears to come from that source. Keep `vqav2`/`gqa` on their
  original roots. The shuffle unit is one raw LLaVA image-level WebDataset sample
  containing the image plus all conversations/questions; do not expand to QA turns
  offline, because that duplicates image bytes and creates TB-scale waste.
- Builder: `beifen-Paligemma/tools/build_llava_image_shuffle_wds.py`. It reads source
  LLaVA shards once in random shard order, keeps a bounded raw-sample buffer, randomly
  emits image-level samples into new tar shards, and preserves original LLaVA sample
  fields while rewriting only tar sample keys. Temporary tar files must stay under
  `/dev/shm`.
- Region launcher: `beifen-Paligemma/tools/run_llava_image_shuffle_region.sh`.
  Run it on a TPU VM in the same region as the source/target bucket:
  `bash tools/run_llava_image_shuffle_region.sh <zone> gs://kmh-gcp-<zone>/data/llava-ov-1.5-instruct-image-shuffled-v1 16`.
  It launches 16 parallel parts, uses seed `20260531`, `shuffle_buffer_samples=25000`,
  `samples_per_shard=10000`, and writes root `_SUCCESS` after all parts finish.
  If a spot card dies after writing partial shards, restart with `NO_CLOBBER=1`; the
  build deterministically replays the same seed and skips already-present tar uploads.
  The launcher also supports `MAX_PARALLEL`; use it when increasing the per-part
  buffer, because the buffer stores raw image bytes in Python memory while `/dev/shm`
  is only for temporary tar files.
- The pilot in `us-east5` wrote
  `gs://kmh-gcp-us-east5/data/llava-ov-1.5-instruct-image-shuffled-v1-pilot`:
  `200000` raw samples, `20` shards, `34.7GB`, duration `1039s`, `_SUCCESS` present.
  It validated schema compatibility with the existing `llava_ov15` dataloader. Do not
  overinterpret its token-length curve: with only `20` shards it is too small for the
  production `world*num_workers` stream partitioning and has visible buffer-fill/drain
  boundary effects.
- Full `us-east5` generation was started on 2026-05-31 on
  `kmh-tpuvm-v6e-16-kaiminghe-40c143` in tmux `llava_image_shuffle_full`, with a local
  lock refresher tmux `llava_image_shuffle_full_lock`. It runs 16 parallel parts using
  one shared shuffled source-shard order and `--shard-offset i --shard-stride 16`,
  writing to `gs://kmh-gcp-us-east5/data/llava-ov-1.5-instruct-image-shuffled-v1/part-XX`.
  Each part uses `shuffle_buffer_samples=25000`, `samples_per_shard=10000`, seed
  `20260531`. The root alias `llava-ov-1.5-instruct-image-shuffled-v1` resolves
  `part-*/shard-*.tar`; the full build does not have root-level `shard-*.tar` files.
- The `us-east5` full image-level shuffle completed on 2026-05-31 with root `_SUCCESS`,
  `16/16` part `_SUCCESS` files, and `1483` tar shards. The remote tmux exited cleanly,
  `/dev/shm` was empty afterward, and the local manual lock was removed.
- On 2026-06-01 the same full image-level shuffle was completed for the remaining
  regions without cross-region data reads:
  `gs://kmh-gcp-us-central1/data/llava-ov-1.5-instruct-image-shuffled-v1` and
  `gs://kmh-gcp-asia-northeast1-b/data/llava-ov-1.5-instruct-image-shuffled-v1`
  both have root `_SUCCESS`, `summary.json`, `16/16` part `_SUCCESS` files, and
  `1483` tar shards. `us-central1` used
  `kmh-tpuvm-v6e-16-kaiminghe-4b4bd1`; all part outputs finished but the final root
  marker was missing after the remote session ended, so root `_SUCCESS`/`summary.json`
  were manually written after verifying `16/16` parts and `1483` tar shards. Asia first
  wrote `368` partial tar shards on `kmh-tpuvm-v6e-16-kaiminghe-b95139`, which was then
  deleted/preempted; it was resumed on `kmh-tpuvm-v6e-16-kaiminghe-69d29b` with
  `NO_CLOBBER=1` and completed normally. The manual TPU locks for both cards were
  removed after verification.
- Important result: full image-level shuffle did **not** fully fix the SFT
  `valid_tokens_per_sample` drift. Same-zone stream audit
  `llava-full-image-shuffle-us-east5-rank0-stream-sim-5k-20260531`, W&B `rn36i3xu`,
  used `world=8`, `rank0`, `num_workers=16`, current online item buffer `1024`, full
  shuffled LLaVA plus original us-east5 VQAv2/GQA. It still declined from about
  `83-85` tokens/sample in the first few hundred steps to about `61` by step `5000`,
  while the LLaVA mix fraction stayed stable around `0.94`. Do not spend time generating
  extra variants from this image-level shuffle as a presumed fix. The likely next fix
  needs shuffling after LLaVA conversation expansion, or another QA-level/mixed-token
  buffer that avoids duplicating image bytes on disk.
- Follow-up: the `1024` online item buffer above was too small, roughly one global batch.
  Re-running the same full shuffled LLaVA root with `item_shuffle_size.llava_ov15=50000`
  and `num_workers=4` showed the image-level shuffle is useful: first 500-step mean
  `valid_tokens_per_sample ~=80.9`, last 500-step mean `~=76.4`, fitted slope
  `~-1.08 tokens/sample/1k steps`, with LLaVA fraction still around `0.94`. This is much
  better than the `1024` buffer curve (`~83-85 -> ~61` by 5k), though not perfectly flat.
  The 50k audit had a substantial startup cost because each worker must fill 50k raw
  image samples before emitting. With production `num_workers=16`, startup/memory cost
  scales up, but each worker's buffer drains more slowly than in the 4-worker audit.
- `beifen-Paligemma` and `jax_llava` were updated to use this policy for LLaVA SFT:
  `llava-ov-1.5-instruct-image-shuffled-v1` as the LLaVA dataset alias and
  `item_shuffle_size.llava_ov15=50000`. `jax_llava` also ports the `beifen` raw
  image-level buffer logic so the 50k buffer holds image samples plus pending QA groups
  rather than many expanded copies of the same image. As of 2026-06-01, the full
  shuffled dataset alias exists and is verified in all three allowed regions:
  `us-east5`, `us-central1`, and `asia-northeast1-b`.
- On 2026-06-02 the larger `us-east5` one-time shuffle trial completed:
  `gs://kmh-gcp-us-east5/data/llava-ov-1.5-instruct-image-shuffled-v2-buf125k`.
  It uses the same image-level shuffle unit and seed `20260531`, but with
  `SHUFFLE_BUFFER_SAMPLES=125000` (5x the v1 per-part buffer). The final layout is a
  mixed resume layout: original `part-00..11` plus split `part-*-of-64` subparts for
  the remaining offsets. The root has `_SUCCESS`, `summary.json`, and `1493` tar shards
  under `part-*/shard-*.tar`; a schema spot-check showed paired `.jpg`/`.json` image
  samples. Do **not** switch training configs to this alias: same-zone 50k online-buffer
  sanity did not beat the v1 baseline.
- The v2 build took much longer than expected for operational reasons, not because the
  final dataset was huge: two spot TPUs disappeared mid-build, dirty idle entries made
  xibo aliases unreliable, `gcloud storage ls .../_SUCCESS` could hang without a timeout,
  and xibo SSH returned false 255s even while direct SSH to worker0 was healthy. The
  launcher now supports `SUCCESS_CHECK_TIMEOUT`, `MAX_PARALLEL`, `SHARD_STRIDE`, and
  `SHARD_OFFSETS`; use these instead of hand-editing loops when resuming partial builds.
- The same-zone v2 sanity run
  `llava-v2-buf125k-us-east5-rank0-stream-sim-2k-1worker-20260602`, W&B `8sa4ql3z`,
  used `world=8`, `rank0`, `num_workers=1`, `item_shuffle_size.llava_ov15=50000`,
  v2 LLaVA plus original us-east5 VQAv2/GQA. Result: first 500-step mean
  `valid_tokens_per_sample=80.974`, last 500-step mean `77.758`, fitted slope
  `-2.11 tokens/sample/1k steps`, LLaVA fraction mean `0.943`. This is still a
  downward drift, so a 5x larger offline image-level buffer is not the fix.
- Be careful when running the stream simulator as a sanity check. The current
  token-only preprocessing path supports only `llava_ov15`, `vqav2`, and `gqa`; running
  it on the expanded current SFT mix with OKVQA/AOKVQA/OCRVQA/TextCaps/etc. can spin
  while filtering unsupported samples. Use explicit `--override-roots`,
  `--override-types`, and `--override-mix-weights` for comparable audits, or extend the
  simulator before auditing the full mix.
- A 50k online buffer sanity has high startup and memory cost because each worker must
  fill a raw image-level buffer containing JPEG bytes before yielding samples. A
  `num_workers=4` sanity reached about `31GB` RSS and still had no first bin after
  12 minutes because it needed four 50k buffers before step 100. For quick diagnostics,
  start with `num_workers=1`; for production representativeness, expect long warmup or
  write a metadata-only audit that does not buffer image bytes.

## JAX LLaVA HSDP Notes

- On 2026-05-29, the LLaVA two-stage curriculum failed when resuming stage 2 from a
  stage-1 checkpoint saved on a different topology. The immediate error was Orbax
  restoring with checkpoint-saved sharding after `restore_checkpoint(None, ...)`:
  `sharding passed to deserialization ... Got None`, with old metadata from 64 devices
  and current availability of 32 devices.
- For jit/HSDP code, params-only restore should pass the current params tree as the
  restore target and also pass `ocp.checkpoint_utils.construct_restore_args(target)` to
  `PyTreeRestore`. Passing only `item=target` is insufficient with Orbax 0.11.32: a
  v6e-64 checkpoint resumed on v5p-64 can still fail with
  `sharding passed to deserialization ... Got None`. Do not use target-less restore for
  topology-portable params-only loads.
- HSDP checkpoint saves should follow the `text-jit` pattern: all-gather the sharded
  train state to host with `multihost_utils.process_allgather(..., tiled=True)`, then
  save the host tree. This avoids baking one TPU topology's sharding into checkpoints
  that may later be resumed on v5p/v6e cards with different device layouts.
- The LLaVA HSDP kNN eval failure after stage-1 training was not fundamentally a
  checkpoint-save issue. The kNN path used host-local TFDS loops around HSDP/pjit feature
  extraction, and could trigger `unexpected peer shows up in the launch group with a
  different launch id` when hosts did not execute the same compiled steps. Keep kNN
  feature extraction in the jit/HSDP style, but force a synchronized fixed number of
  pjit steps on every process, pad exhausted local batches, all-gather train/val features,
  then run the JAX KNN computation on every process instead of rank 0 only.
- `jax_llava/debug_remote_knn_eval.sh` is the small remote smoke launcher for this path.
  It accepts `none`/`fresh` as a no-checkpoint eval-only run, creates one launcher-side
  workdir for every worker, and caps TFDS ImageNet reads with `KNN_IMAGES_PER_CLASS`,
  `KNN_VAL_EXAMPLES`, and `KNN_BATCH_SIZE`.
- If remote debug uses a TPU lease name that is not registered in xibo aliases, pass the
  zone explicitly to mount setup, e.g. `tpu mount-disk <tpu> --force --zone=us-central1-a`;
  otherwise xibo `get_zone_pre` can fail even though the TPU exists. Do not trust a broad
  `MOUNTED` label if one worker cannot see `/kmh-nfs-ssd-us-mount`; force mount before
  blaming JAX.
- On 2026-05-29, a tiny LLaVA HSDP kNN smoke passed on
  `kmh-tpuvm-v5p-64-spot-llql5v63k` in `us-central1-a` after force-mounting:
  `KNN_IMAGES_PER_CLASS=8`, `KNN_VAL_EXAMPLES=32`, no `load_from`, TFDS from
  `gs://kmh-gcp-us-central1/tensorflow_datasets`, gathered train features `(8000, 1024)`,
  gathered val features `(32, 1024)`, replicated `KNN-1`, and ended with
  `knn_partial_acc_final=53.125` / `Eval Over.`. This validates plumbing, not model
  quality, because the no-checkpoint path initializes pretrained CLIP/Gemma plus a random
  projector.
- For the original queued LLaVA run, window `7034` did not save a new checkpoint; it
  failed while restoring. The latest complete checkpoint before that failure is window
  `6962`, step `2180`, from
  `/kmh-nfs-ssd-us-mount/logs/sqa/paligemma-baseline/20260528_170253_qr1pu0_kmh-tpuvm-v6e-64-dmy-0e3f_us-central1-b__b_lr_ep_eval`,
  and the WandB resume id is `q043krc3`. Requeueing this logical run should set
  `load_from` to that logdir and `wandb_resume_id` to `q043krc3`.
- Do not schedule ImageNet kNN as an online eval for the LLaVA curriculum when the
  image encoder is frozen. In `jax_llava/configs/remote_run_config.yml`, keep stage 1
  kNN disabled and remove `knn_partial` / `knn_full` from stage 2 eval lists as well;
  current already-running staged jobs can be left alone.
- For `jax_llava` SFT detection/refcocog, use the exact shared suffix
  `Output exactly four location tokens, indicating up, left, down, right.` Do not use
  older "Return exactly..." / "Do not output any other text" wording. The order is
  verified against the code: targets are emitted as `ymin, xmin, ymax, xmax`, i.e.
  up, left, down, right. Training `genome_det` and RefCOCOg eval share
  `input_pipeline.format_detection_prompt`, while bbox targets are transformed through
  the same deterministic resize/letterbox transform before conversion to 0..1023 loc
  bins. MMBench eval uses a separate prompt-fitting path and compiled sampler shape:
  default `eval.mmbench_max_txt_len=512`, short "option letter only" suffix, drop hint
  first, then truncate question/options structurally instead of blindly chopping off the
  tail.

## Non-Goals In Current Flow

- `preempted` jobs are intentionally not handled by this monitor. Another script deletes
  those TPUs, and the next monitor loop should see them as `deleted`.
- `job["rules"]` is not used by the active monitor path.
- The old local TPU manager implementation (`tpu.py`, `web_cli.py`, old shell helpers,
  and legacy `utils/*` modules for users/jobs/sheet/queue/etc.) was removed from this
  lightweight checkout. Use the external xibo `_tpu` backend for those operations.

## Editing Guidance

- Keep changes focused in `MONITOR.py`, `find_saving_window.py`, or the two retained
  `utils` modules unless the active path proves otherwise.
- Preserve the external xibo `_tpu` path unless explicitly asked to change it.
- Keep `queue.json` backwards compatible; old entries without new fields should still run.
- When manually editing the external xibo `data.json`, prefer xibo's Python lock
  interface (`utils.data_io.read_and_lock_data`, `write_and_unlock_data`, and
  `release_lock_data` in a `finally` path) instead of bare file reads/writes. This
  avoids races with monitor/xibo scripts that also touch `data.json`.
- If a fallback raw write is truly necessary, preserve `data.json`'s pretty JSON format
  (`indent=4`, `ensure_ascii=False`). A bare `json.dump` rewrites it as one very long
  line, which is valid JSON but bad for inspection and review.


---

## `wiki_agents/AGENTS.md`

# Shared Agent Memory

This folder is the cross-repository operational wiki for
`/kmh-nfs-ssd-us-mount/code/qiao/work`. It is meant to get a new agent oriented
quickly without replacing project-local `AGENTS.md` files.

Project-local `AGENTS.md` files remain authoritative for coding rules inside
their subtrees. Exact snapshots of all discovered source `AGENTS.md` files are
preserved in `project_agents_archive.md`.

## Quick Start For A New Agent

1. Read `/kmh-nfs-ssd-us-mount/code/qiao/work/AGENTS.md`.
2. Read this file.
3. Read the project-local `AGENTS.md` for the directory you will edit.
4. Read the topic guide that matches the task:
   - TPU status, queue, launch, resume, zombie holders: `tpu.md`
   - MONITOR internals, xibo state, remote Linux users: `xibo_monitor.md`
   - VLM/PaliGemma/JAX LLaVA training memory: `vlm_training.md`
   - Spreadsheet and WandB result logging: `spreadsheet_logging.md`
   - Long-running experiment loop practices: `research_loop.md`
   - Remote debug jobs and common JAX/TPU pitfalls: `debug.md`
   - Shared SSD cleanup: `storage_cleanup.md`
   - Project checkout index: `project_index.md`

## Hard Rules

- Do not push code changes unless the user explicitly asks for a push in the
  current request.
- Before editing a project, read that project's local `AGENTS.md`.
- Avoid cross-region or cross-zone GCS transfer. Prefer run logs, WandB, and
  spreadsheet metadata over scanning benchmark datasets. If data access is
  unavoidable, use the same-zone bucket and stop before any cross-region copy or
  bulk read.
- For spreadsheet result logging, obey the stop-on-OOD rule in
  `spreadsheet_logging.md`: new benchmarks, missing/renamed metrics,
  non-comparable eval settings, discontinuous loss, conflicting existing cells,
  or any other out-of-distribution behavior means do not write to the sheet;
  report the anomaly and wait.
- For TPU work, do not decide ownership or zombie status from `tou` alone. Use
  manager state, tmux state, and remote process/device-holder state.
- For shared operational records, preserve exact source details when possible.
  If a local project rule becomes broadly reusable, add it to the matching
  `wiki_agents/*.md` topic file and keep the local source file intact.

## Task Routing

| Task | Read |
|---|---|
| Find or claim TPU, check jobs, read logs, handle stale holders | `tpu.md` |
| Modify local MONITOR queue/resume logic | `xibo_monitor.md`, `tpu_manager/AGENTS.md` |
| Modify xibo manager sandbox / remote Linux user support | `xibo_monitor.md`, sandbox `AGENTS.md` |
| Edit JAX LLaVA / PaliGemma training code | `vlm_training.md`, project-local `AGENTS.md` |
| Upload VLM datasets or generate visual reports | `vlm_training.md`, `beifen/AGENTS.md` |
| Log WandB results into the sheet | `spreadsheet_logging.md`, `vlm_training.md` |
| Run a long experiment-management loop | `research_loop.md`, project notes/results |
| Debug on a remote TPU with a toy config | `debug.md`, `tpu.md` |
| Clean NFS/SSD disk pressure | `storage_cleanup.md` |
| Understand which checkout has which rules | `project_index.md` |

## Current High-Value Memory

- LLaVA-1.5 reproduction tracking, target metrics, SFT data recipe, HSDP memory
  constraints, stateful dataloader resume, two-stage PaliGemma curriculum, and
  durable checkpoint conventions are consolidated in `vlm_training.md`.
- TPU user-facing operations and zombie-holder diagnosis are in `tpu.md`.
- Low-level queue/resume invariants, alias hygiene, `tou`/`yizhitou` refresh
  flow, remote Linux user isolation, and xibo lock semantics are in
  `xibo_monitor.md`.
- Spreadsheet logging defaults to
  `PaliGemma-baseline-cleaned-20260608` and must follow the hard stop rule in
  `spreadsheet_logging.md`.
- Shared SSD cleanup guidance, including the 2026-06-08/09 staging cleanup
  incident and safe large-file deletion procedure, is in `storage_cleanup.md`.

## Maintenance Checklist

When adding or changing shared memory:

1. Keep the relevant project-local `AGENTS.md` as the source for repo-specific
   coding constraints.
2. Put cross-repo operational knowledge in the narrowest topic file here.
3. Add or update `project_index.md` if a new checkout-level `AGENTS.md` appears.
4. Update `project_agents_archive.md` when exact source text should be preserved.
5. Keep this file short; it should remain a routing page, not a history dump.


---

## `xibo_tpu_manager_linux_user_sandbox_20260601/AGENTS.md`

# AGENTS.md — xibo_tpu_manager (Quick on-boarding for agents)

This repo is a multi-user **Google Cloud TPU job manager**: it shells out
`gcloud compute tpus tpu-vm ...` to apply / reapply / SSH into TPU VMs,
runs each user's training job inside a per-user `tmux` session, and keeps
a global JSON state (`data.json`) describing every job. A background
**MONITOR** daemon polls the state and auto-resumes / reapplies jobs.

This file is meant for *other AI / human agents* who need to navigate
the codebase quickly. The full user-facing docs live in `README.md`.

---

## 1. Top-level layout

```
xibo_tpu_manager/
├── tpu.py                  # CLI entrypoint -> dispatches to utils/*
├── MONITOR.py              # Long-running daemon: detects + reacts to errors
├── web_cli.py              # Web UI wrapping the same `utils/*` API
├── utils/                  # All real logic lives here (see §3)
├── data.json               # PRIMARY STATE: users, jobs, tpu aliases, MONITOR config
├── legacy.json             # Archived jobs / overflow from data.json
├── queue.json              # Pending jobs waiting for a free TPU
├── lock.json               # fcntl-style locks: code / data / queue / legacy / apply
├── mounted.json            # Cache of which TPUs have their disk mounted
├── apply.json              # Cache used during TPU apply flow
├── secret.json             # Wandb / GCP secrets (do not commit)
├── passwords.json          # web_cli auth
├── README.md               # User-facing docs (the long version)
├── NOTES.md                # Hard-won gotchas, read this once
├── ab.ab / 新.sh / monitor.sh / batch_run.sh / apply_tpu.sh / create_tmux_queue.py
│                           # Misc shell helpers
└── data.json.bak.*         # Manual backups; safe to ignore
```

Other agent breadcrumbs:

- `.git/` — yes this is a git repo.
- `__pycache__/`, `utils/__pycache__/` — generated.
- `utils/dependency.md` — author's view of the import DAG between
  `utils/*.py`. **Respect it when editing**, breaking it causes circular
  imports.
- Several `*.bak_*.py` files in `utils/` are point-in-time snapshots;
  do not edit them, do not import them. Treat as read-only history.

---

## 2. CLI entrypoint (`tpu.py`)

`tpu.py` is one giant `if/elif cmd == "..."` table. There is no Click /
argparse. Conventions:

- `args = sys.argv`, so `args[1]` is the command and `args[2:]` are
  positional flags. Many subcommands accept `username` as one of the
  positional args and find it via `find_user(data, args[1:])`.
- Many user-targeted subcommands first resolve the `user` object, then
  call into `utils.jobs` / `utils.directories` / etc. with `user_obj`.
- The lock check at the top (`data_io.check_code_lock()`) refuses every
  command except `lock` / `unlock` if `lock.json -> code.status` is true.
  This is the "dev freeze" switch used by `develop.py`.

Roughly grouped command families (already grouped in `tpu.py` with
section comments — search for `# ------------`):

- **Users**: `add-user`, `del-user`, `list-users` / `-lu`, `init`,
  `register-web`.
- **Directories**: `set-cur`, `set-dir`, `del-dir`, `swap-dir`, `ls`,
  `get-dir`.
- **Settings**: `get-settings`, `set-settings`, `reset-settings`.
- **Config aliases**: `-a/-alias`, `-sa/-la`, `del-config-alias`.
- **Run / resume / rerun**: `run`, `resume`, `rerun`, `restart-run`,
  `queue`, `dequeue`, `dqr`.
- **Monitor / status** (no side effects on TPU but may write `data.json`):
  `check`, `check-simp`, `monitor`, `caj`, `maj`.
- **Kill / clean**: `kill / kill-job / -k / -kj`, `kill-window / -kw`,
  `clean`, `clear-finished`, `clear-error`, `clear-all / clear`,
  `-czw`, `-czj`, `ignore-error`.
- **TPU lifecycle**: `apply`, `applyy`, `reapply`, `reapplyy`,
  `apply-norm`, `reapply-norm`, `delete`, `restart`, `register`,
  `del-registered/del-reg`, `check-status`, `describe`, `test`,
  `mount-disk`, `mount-disk-new`, `set-wandb`, `kill-remote`,
  `change-ip`, `solve`, `lian`, `find`, `release/rel`, `keng`, `zhan`,
  `fang`, `fmd`.
- **Spreadsheet**: `ssn`, `asn`, `gtis`, `uss/upd-status-spreadsheet`,
  `twsi`.
- **Locks / dev**: `lock`, `unlock/rl`, `lock-data`, `unlock-data`,
  `rm-lock`, `-Ml/-Mc`, `debug-stats`, `debug-kill`,
  `add_global_config/-agc`, `merge_global_config/-mgc`.
- **Job ack to scripts**: `upd-log`, `upd-staging-info`, `finish-job`,
  `fail-job`, `ack`.
- **Misc**: `cp` / `cc` / `cca` (GCS bucket copies), `tldr`, `help/-h`,
  `vq`.

Aliases for the same command (e.g. `kill / kill-job / -k / -kj`,
`-a / -alias / add-config-alias`) live in the same `elif` row.

---

## 3. `utils/` package — what's in each file

Listed in dependency order (see `utils/dependency.md`). When editing,
keep the layering: lower-level files must not import higher-level ones.

| File | Purpose |
|---|---|
| `constants.py` | Paths (`DATA_PATH`, `LOCK_PATH`, ...), TPU type tables, `ZONE_DICT`, `RULE_DICT`, color codes (`RED`, `GOOD`, etc.), `PROJECT`, `REGION_SA_MAP`. |
| `clean.py` | `clean_us` / `clean_eu` — sweep stale TPUs in a region. |
| `autenticate.py` | Password-based auth for `add-user` / `del-user` / `register-web`. |
| `helpers.py` | Tiny utilities re-exported via `from utils.helpers import *`: time helpers (`get_abs_time_str`, `convert_utcstr_to_edtstr`, ...), the color constants, `get_zone_pre_spot`, `is_integer`, `read_data` re-export, ... |
| `data_io.py` | The **only** file that touches `data.json` / `lock.json` directly. `read_data`, `read_and_lock_data`, `write_and_unlock_data`, `release_lock_data`, plus the non-blocking `read_data_if_unlocked` used by `lck`/`ack` to avoid blocking. Locking is fcntl + a status field in `lock.json`. |
| `descriptions.py` | `tldr()` and `explain(cmd)` — help text. |
| `gs_buckets.py` | `cp` / `cc` / `cca` — `gsutil`-based checkpoint copy across regions. |
| `develop.py` | Dev-only tools: lock the codebase, edit metadata safely, dump MONITOR logs. |
| `directories.py` | Per-user working-dir bookkeeping (`set-cur`, `set-dir`, `del-dir`, `swap-dir`, `ls`, `get_dir`, `get_job_stage_dir`). |
| `users.py` | `User` dataclass (`user_from_dict`), `create_user`, `del_user`, `reset_settings`, `reset_window_num`, `list_users`. |
| `sheet.py` | Google Sheets I/O for the TPU spreadsheet (`get_tpu_info_sheet`, `write_sheet_info`, `find_tpu_from_type`, `release_tpu`, `keng_tpu`, spreadsheet notes). |
| `logger.py` | Aliases (TPU and config), `register_tpu*`, `add_tpu_alias`, monitor config, file locks, per-user `logs[]` append. |
| `operate.py` | All `gcloud` shellouts: `apply`, `reapply`, `apply_and_set_env`, `delete_tpu`, `restart`, `check_tpu_status`, `mount_disk`, `set_wandb`, `kill_jobs_tpu`, `describe_tpu`, `lian_tpu`, `check_env`, `test_remote`. **This is where the TPU is actually touched.** |
| `jobs.py` | The thickest file (~2k lines). Defines `Job`, runs the job lifecycle, parses tmux pane output to derive status, writes `error`/`status` back to `data.json`. See §4. |
| `error_handler.py` | `solve_env`, `change_ip`, `clear_zombie_windows`, `initialization`. Higher-level recovery flows. |
| `unit_tests.py` | Sanity checks the daemon runs occasionally (`MONITOR_config.test_freq`). |
| `queue.py` | The job queue (`queue.json`): `Queue.add`, `dequeue`, `dequeue_and_run`, `visualize_queue`, `finish_job`, `fail_job`, `upd_staging_info`. |

---

## 4. `utils/jobs.py` — the core lifecycle

This is what you'll edit most. Important entry points:

- `Job` class + `to_dict()` — the schema written into `data.json`.
- `run(user_obj, args)` — primary `tpu run` flow. Resolves a TPU, builds
  a `Job`, calls `run_job_on_tpu`, optionally opens the monitor window.
- `run_job_on_tpu(job, tpu)` — performs the scoped remote-user kill/mount,
  opens a new tmux window, `cd`s into the stage_dir, runs `staging.sh`.
- `resume(user_obj, args)` / `rerun(user_obj, args)` —
  manual `tpu resume / rerun`. Both call `resume_rerun_job`.
- `resume_rerun_job(job, new_tpu=None, load_ckpt=True)` — the *only*
  function that creates a child job (with `stage = parent_stage + 1`
  and `extra_msgs.father`). It performs scoped remote-user cleanup before
  relaunching.
- `kill_job_or_tpu(user_obj, args)` — `tpu kill <window|tpu>`.
- `kill_window(user_obj, args)` — `tpu kill-window`.
- `check_jobs` / `check_jobs_simp` / `monitor_jobs` — read-side. They
  parse `tmux capture-pane`, classify status, and, **as a side effect**,
  call `write_error_to_job(...)` to persist an error type, and sometimes
  `ack_MONITOR()` to wake the daemon. See §5.
- `_render_rows_for_job(...)` — the same status-detection logic as
  `check_jobs`, but in a row-builder form used by `check_jobs_simp`.
- `clear_finished_jobs`, `clear_error_jobs`, `clear_all_jobs`,
  `clear_zombie_jobs` — list mutators on `user.job_data`. Used by
  `clean`.
- `write_error_to_job(user, job, error)` — idempotent
  `status = 'error', error = '<type>'` writer, opportunistic
  (skips if data lock is held).
- `ack_MONITOR()` — flips `data["ack_MONITOR"] = True` so the MONITOR
  daemon wakes up within 10s. Opportunistic.

Durable pretrained checkpoint convention:
- `ltgcp <absolute_local_logdir>` maps the normal regional run path under
  `qiao_zhicheng_hanhong_files/` to the same bucket's
  `pretrained-ckpts/qiao_zhicheng_hanhong_files/` prefix.
- `utils.gs_buckets.ensure_pretrained_checkpoint_for_launch(...)` preflights
  finetune launches with `load_from_pretrained`: normal target-zone checkpoint
  first, same-zone pretrained fallback second, then copy latest checkpoint from
  another zone's pretrained prefix into the target pretrained prefix if needed.
- `utils.queue.finish_job(...)` mirrors the finished job's latest checkpoint
  into same-zone `pretrained-ckpts/` as a best-effort durable backup.

Status values used on jobs:

```
None | 'starting' | 'running' | 'finished'
'error'   (with non-empty `error` field describing the type)
'killed'  (manual)
'resumed' | 'rerunned'  (this job has a child; child id in extra_msgs.child)
```

`error` field values seen: `'preempted'`, `'grpc'`, `'locked'`, `'OOM'`,
`'file error'`, `'invalid pointer'`, `'deadline exceeded'`, `'unknown'`.

### Remote Linux User Mode

This sandbox copy is being adapted so xibo logical users still live in
`data.json` exactly as before, but TPU VM jobs run under separate Linux
accounts instead of always running as remote `sqa`.

- New jobs default `remote_linux_user` to the xibo user name. For example,
  xibo user `cyx` launches remote training as `cyx@<tpu>`.
- Existing/legacy jobs without `extra_msgs.remote_linux_user` must be treated
  as remote `sqa`. This preserves compatibility for currently running jobs and
  old resume chains.
- `run`, `run_job_on_tpu`, `resume`, and `rerun` store the resolved Linux user
  in `job.extra_msgs.remote_linux_user`.
- `resume`/`rerun` inherit the parent job's remote Linux user unless explicitly
  overridden with `remote_user=<linux_user>` (aliases:
  `linux_user=`, `remote_linux_user=`, `linux-user=`, `remote-linux-user=`).
- Launch commands prepend `export TPU_REMOTE_USER=<linux_user>;` before
  `source staging.sh ...`. The repo `staging.sh` / `run_remote.sh` side must
  honor `TPU_REMOTE_USER` by SSHing to `<linux_user>@<tpu>`.
- `mount_disk(..., remote_user=...)` is remote-user aware. NFS mounting is
  global to the VM, but Python packages, W&B login, and `.disk_mounted` markers
  are per Linux user under `/home/<linux_user>`.
- `mount_disk` must not remove other users' home directories. Separate Linux
  users are the isolation boundary.
- `ensure_remote_linux_user(...)` creates the Linux account on all TPU workers,
  adds passwordless sudo, copies available SSH authorized keys, and verifies
  `whoami` plus `sudo -n true`.
- `kill_jobs_tpu` now supports scoped kills. Default xibo-user kills only target
  the caller's inferred remote Linux user(s). `--all-users` / `--all-remote-users`
  is the explicit all-user kill mode and is the only mode that cleans global
  `/tmp` TPU state.
- `tpu kill-remote <tpu>` remains a legacy all-user kill. Use
  `tpu kill-remote <tpu> remote_user=<linux_user>` for a scoped kill.
- Do not kill PPIDs gathered from `ps`: many training worker processes have
  PPID 1. Only kill matching process PIDs and matching TPU device-holder PIDs.

---

## 5. The MONITOR daemon (`MONITOR.py`)

Long-running process, intended to run all day under the
`monitor.sh` wrapper or a tmux window.

Loop: every `data["MONITOR_config"]["checking_freq"]` seconds
(default ~600s), or immediately whenever `data["ack_MONITOR"] == True`,
it runs `mainloop()`:

1. Walk every user's `job_data`. Skip jobs whose status is
   `finished/rerunned/resumed/killed` or whose `monitor == False`.
2. For each remaining job, decide an `error_type`:
   - If `status == 'error'` and `error != 'unknown'`, trust the
     existing `error` field.
   - Otherwise call `check_job_status(job)` which:
     - asks `operate.check_tpu_status(tpu)` → returns `'preempted'`
       if the TPU is preempted;
     - else greps `<log_dir>/output.log` for `GRPC error`
       (→ `'grpc'`) or `Could not open any log file` (→ `'locked'`).
3. Bucket jobs into `error_jobs = {'preempted': [], 'grpc': [], 'locked': []}`.
   **Errors not in this set (`OOM`, `file error`, `invalid pointer`,
   `deadline exceeded`, `unknown`) are silently dropped by the daemon
   and never auto-handled.**
4. Mark every bucketed job as `status='error', error=<type>` in
   `data.json`.
5. Per job, look up `job['rules'][error_type]` and dispatch:
   - `pass`    — do nothing.
   - `reapply` — `reapply_resume(job)` → spawns `reapply_worker` in a
     subprocess (timeout 1800s) that runs `operate.apply_and_set_env(...,
     delete=True)`, then on success calls
     `jobs.resume_rerun_job(job, load_ckpt=True)`.
   - `resume`  — `kill_resume(job)` does a scoped remote-user kill, then
     `jobs.resume_rerun_job(job, load_ckpt=True)`.
   - `rerun`   — `kill_rerun(job)` does a scoped remote-user kill, then
     `jobs.resume_rerun_job(job, load_ckpt=False)`.
   - `restart` — `restart_rerun(job)` → `operate.restart(tpu)` then rerun.

`RULE_DICT` in `utils/constants.py` shows the rule-name → (per-error
behavior) mapping. The default rule attached to a job is:
- preemptible TPU → `pre` (`preempted: reapply`, `grpc: resume`)
- non-preemptible → `pass` (do nothing)

The daemon also logs to `data["MONITOR_logs"]` (visible via `tpu -Ml`).

---

## 6. `data.json` schema (cheat sheet)

Top-level keys:

```
users: { <name>: <user_dict> }
user_list: [<name>, ...]
id_list / id_user_dict / user_id_dict
tpu_aliases: { "<short>": "<full vm name>" }
all_tpus: { <zone or 'preemptible'>: [<tpu names>] }
monitor_config / MONITOR_config: { checking_freq, test_freq, clean_freq, ... }
ack_MONITOR: bool         # set true by ack_MONITOR() to wake the daemon
MONITOR_logs: [{time, msg}]
wandb_api_key, conda_env_name, monitor_all_check_time
```

`user_dict`:

```
id, name, tmux_name, working_dir: { "1": "/path", ... },
job_data: [Job, ...],
config_aliases: { "lr": "config.training.learning_rate", ... },
settings: { monitor_after_run, monitor_upd_time, monitor_length,
            show_length, monitor_dir, monitor_tpu, monitor_verbose,
            time_zone, extra_settings, ... },
windows_offset: int,      # next free tmux window number
logs: [...]
```

`Job` (see also `utils/jobs.py::Job.to_dict`):

```
user, windows_id, job_dir_id, job_dir, tpu,
job_tags, log_dir, stage_dir, extra_configs,
status, error, stage, monitor,
rules: { preempted, grpc, locked },
extra_msgs: { father?, child?, fail_time*?, spreadsheet_notes?, ... },
customized_settings: { log_stage?, ... },
start_time: { chn, edt, utc }
```

---

## 7. Locking — read first to avoid deadlocks

All locks live in `lock.json` keyed by lock type: `code`, `data`,
`queue`, `legacy`, `apply`. Each is `{ status: bool, user: str|null }`.
Implementation: `utils/data_io.py::_mutate_lock_file` uses `fcntl.LOCK_EX`
on `lock.json` itself for atomic compare-and-set.

Rules to follow (also documented in `NOTES.md`):

- **Once you take a lock you must release it before returning**, even on
  exception. Use try/except + `release_lock_data()` like the rest of the
  codebase.
- `KeyboardInterrupt` is **not** an `Exception` — catch it separately if
  you hold a lock.
- For read-side / status commands (`check`, `ack`), prefer
  `read_data_if_unlocked()` and silently no-op if it returns
  `(None, False)`. Never block `tpu check` behind a writer.
- Lock-acquire helpers spin every 10s and give up after 30 minutes
  (`num_ack > 180`).

To release a stuck lock by hand: `tpu rl/unlock <code|data|queue|legacy|apply>`.

---

## 8. Conventions worth knowing

- All printed output uses the color tags from `constants.py`:
  `GOOD`, `INFO`, `WARNING`, `FAIL`, `LOG`. Stick to them; users grep on
  the brackets.
- TPU names: aliases like `v2-32-p1` resolve via
  `data["tpu_aliases"]`. `helpers.get_zone_pre_spot(tpu)` returns
  `(zone, preemptible, spot, full_name)` and is the canonical resolver.
- All status detection regexes live in `_render_rows_for_job` and in
  `check_jobs`. Keep the two in sync if you add a new pattern.
- Job lookups are still by `str(windows_id)` in some places and by
  `int(windows_id)` in others. Be defensive with the comparison.
- Backups: many files have `*.bak_<reason>_<timestamp>` siblings, e.g.
  `utils/jobs.py.bak_zone_default_20260521_090359`. Treat them as
  read-only history; do not import or `Read` them by accident when
  searching.

---

## 9. Where to start for common asks

- "Add a CLI subcommand" → add a `elif cmd == "..."` row in `tpu.py`,
  implement it in `utils/<area>.py`.
- "Change how errors are detected" → grep for `write_error_to_job` in
  `utils/jobs.py` and the `check_job_status` in `MONITOR.py`.
- "Change auto-resume rules" → `RULE_DICT` in `utils/constants.py` and
  the dispatch table in `MONITOR.py::mainloop`.
- "Touch the TPU itself" → `utils/operate.py`. **Never** call gcloud
  from anywhere else.
- "Change the data layout" → update `users.User.to_dict` /
  `jobs.Job.to_dict`, write a migration in `utils/develop.py`, and
  back up `data.json` first.
- "Debug a stuck lock" → `tpu rl <type>` from the CLI, or edit
  `lock.json` and set the offending `status` to `false`.
