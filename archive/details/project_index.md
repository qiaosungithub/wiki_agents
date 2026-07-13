# Project Index

This workspace contains many project checkouts. Agent memory is centralized in
`wiki_agents`; most scattered `AGENTS.md` / `CLAUDE.md` files were archived and
then removed from the checkout tree.

Use this file only to map a project to the right topic docs. Detailed rules live
in those topic docs or in the verbatim archives.

## Always Read First

1. `/kmh-nfs-ssd-us-mount/code/qiao/work/AGENTS.md`
2. `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/AGENTS.md`
3. This index.
4. The topic docs listed for the checkout you are touching.

## Project Groups

| Project / path | What it is | Read |
|---|---|---|
| `jax_llava/` | Current JAX LLaVA training/data/eval code and LLaVA-1.5 reproduction work. | `vlm_training.md`, `vlm_data.md`, `vlm_checkpointing.md`, `infra_scheduling.md`, `spreadsheet_logging.md` |
| `jax_llava_late_fusion_13_5ed73eb/` | JAX LLaVA late-fusion snapshot with same legacy notes as `jax_llava`. | `vlm_training.md`, `vlm_checkpointing.md` |
| `jax_llava_late_fusion_22_5ed73eb/` | JAX LLaVA late-fusion snapshot with same legacy notes as `jax_llava`. | `vlm_training.md`, `vlm_checkpointing.md` |
| `jax_llava_master_39b30fb_before_late_fusion/` | Pre-late-fusion JAX LLaVA snapshot. | `vlm_training.md`, `vlm_data.md`, `vlm_checkpointing.md` |
| `PaliGemma-baseline/` | PaliGemma / PrefixMAE training baseline, two-stage curriculum, HSDP notes. | `vlm_training.md`, `vlm_checkpointing.md`, `tpu.md`, `spreadsheet_logging.md` |
| `beifen-Paligemma/` | PaliGemma worktree with stateful dataloader and two-stage notes. | `vlm_training.md`, `vlm_data.md`, `vlm_checkpointing.md` |
| `eue3a5qr-sft-new-pipeline/` | SFT worktree copied from pretrain stagedir for WandB run `eue3a5qr`. | `vlm_training.md`, `vlm_checkpointing.md`, `project_agents_archive.md` |
| `beifen/` | Dataset upload and visual sanity report scripts. | `vlm_data.md` |
| `one-benchmark-suite/` | Benchmark registry package; not a training framework. | `project_agents_archive.md`, `external_memory_archive.md` |
| `unified_infra/` | Group-wide TPU job scheduler (the `infra` CLI + daemon). The current system for scheduling/running/resuming jobs. | `infra_overview.md`, `infra_scheduling.md`, `infra_resume.md`, `tpu.md` |
| `tpu_manager/` | Legacy local SQA `MONITOR.py` working copy. No longer schedules jobs; `detect_zombie.py` and a few `tpu` helpers still used. | `tpu.md`, `infra_overview.md`, `project_agents_archive.md` |
| `xibo_tpu_manager_linux_user_sandbox_20260601/` | Legacy sandbox copy of xibo manager with remote Linux user support. | `project_agents_archive.md`, `external_memory_archive.md` |
| `nnflow_jax/` | JAX implementation for "Generative Modeling Through Drifting". | `external_memory_archive.md` |
| `wiki_agents/` | Shared cross-repository operational memory. | `AGENTS.md`, then the file being edited |

## Duplicate Legacy Rule Groups

- `jax_llava/AGENTS.md`, `jax_llava_late_fusion_13_5ed73eb/AGENTS.md`, and
  `jax_llava_late_fusion_22_5ed73eb/AGENTS.md` were identical when archived.
- Several PaliGemma/JAX LLaVA worktrees share HSDP, SFT dataset, stateful
  dataloader, durable checkpoint, and queue semantics. Those rules are now
  split across `vlm_training.md`, `vlm_data.md`, `vlm_checkpointing.md`, and
  `infra_scheduling.md`.
- The current scheduling/resume system is `unified_infra`: architecture in
  `infra_overview.md`, queueing/scheduling in `infra_scheduling.md`, and
  resume/single-job-chain in `infra_resume.md`. The legacy `tpu_manager` and xibo
  sandbox AGENTS snapshots (the pre-unified_infra system) are preserved verbatim
  in `project_agents_archive.md`.

## Project-Specific Archives

- All discovered legacy `AGENTS.md` files are preserved in
  `project_agents_archive.md`.
- Legacy non-AGENTS memory files are preserved in `external_memory_archive.md`.
  This includes `one-benchmark-suite/CLAUDE.md`, `nnflow_jax/CLAUDE.md`,
  `xibo_tpu_manager_linux_user_sandbox_20260601/NOTES.md`, and the old root
  agent notes file.
- For `one-benchmark-suite`, the short rule is: keep it a benchmark registry,
  keep benchmark metrics pure Python/numpy, keep sanity checks CPU-only, and do
  not reintroduce training code. Read the archives for full details.
- For `nnflow_jax`, the short rule is: keep interfaces modular/deep, add dummy
  tests before real compute, understand `energy_loss.py` and `energy_bank.py`
  before changing drifting dynamics, and choose GCS service-account keys by
  zone. Read `external_memory_archive.md` for full details.
- For old VLM investigations that are not current daily procedure, search
  `project_agents_archive.md` by heading or phrase. Useful anchors include
  `PaliGemma SFT From Pretrain`, `ImageNet kNN / Remote Environment Notes`,
  `valid_tokens_per_sample`, and `llava-ov-1.5-instruct-image-shuffled-v1`.

## Updating This Index

When a new checkout or project-family memory appears:

1. Add the project to the table.
2. Put reusable operational knowledge in the narrowest topic file.
3. Preserve exact source text in `project_agents_archive.md` or
   `external_memory_archive.md` only when the original wording matters.
