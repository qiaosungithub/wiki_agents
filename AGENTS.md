# Shared Agent Memory

This folder is the canonical operational memory for
`/kmh-nfs-ssd-us-mount/code/qiao/work`. The root workspace `AGENTS.md` is only a
bootstrap pointer into this folder.

Use this file as a router. It should stay short. Task-specific rules belong in
the narrowest topic file listed below, and exact legacy source text belongs only
in the archive files.

## How To Start

1. Read this file.
2. Use `project_index.md` to identify the checkout or project family.
3. Read the topic guide for the task before acting.
4. Read archive files only when you need the old verbatim source text or want to
   recover context not yet summarized into a topic guide.

## General Hard Rules

- Do not push code changes unless the user explicitly asks for a push in the
  current request.
- Do not overwrite, revert, or clean up user changes in a dirty worktree unless
  the user explicitly asks for that exact operation.
- Avoid cross-region or cross-zone GCS payload movement. Prefer run logs, WandB,
  sidecar manifests, summaries, and spreadsheet metadata. If payload access is
  unavoidable, prove the job is running in the same region/zone-family as the
  bucket before reading or copying data.
- Before destructive cleanup, identify the filesystem and owner, preserve a
  manifest when deleting shared data, and use the storage guide.
- If a task-specific guide defines a hard stop, follow that guide. Examples:
  spreadsheet out-of-distribution behavior, TPU zombie ownership, and xibo
  resume safety are not general rules; they live in their topic files.

## Task Routing

| Task | Read |
|---|---|
| Find/claim TPU, check jobs, inspect logs, diagnose stale holders | `tpu.md` |
| Modify or diagnose SQA monitor queue dispatch | `xibo_monitor.md`, `xibo_queue.md` |
| Modify or diagnose xibo resume/rerun/checkpoint-source behavior | `xibo_monitor.md`, `xibo_resume.md` |
| Work with remote Linux users, xibo locks, or ka sheet compatibility | `xibo_monitor.md` |
| Edit JAX LLaVA / PaliGemma / VLM training code | `vlm_training.md` |
| Work on VLM datasets, upload/count/report data, or dataset locality | `vlm_data.md` |
| Work on VLM checkpointing, dataloader resume, final eval restore | `vlm_checkpointing.md` |
| Log WandB results into the spreadsheet | `spreadsheet_logging.md`, `spreadsheet_logging_playbook.md` |
| Run a long experiment-management loop | `research_loop.md` |
| Run remote TPU debug/smoke jobs | `debug.md`, `tpu.md` |
| Clean shared SSD, local root/home, Codex WALs, or monitor temp dirs | `storage_cleanup.md` |
| Understand checkout/project-specific rules | `project_index.md` |
| Recover exact legacy instructions | `project_agents_archive.md`, `external_memory_archive.md` |

## File Map

| File | Purpose |
|---|---|
| `project_index.md` | Compact map from checkout names to the docs that matter. |
| `tpu.md` | User-facing TPU operations and ownership/zombie diagnosis. |
| `xibo_monitor.md` | Xibo/SQA monitor architecture, active paths, remote users, locks. |
| `xibo_queue.md` | Queue semantics, TPU selection, `tou` refresh, alias hygiene. |
| `xibo_resume.md` | Resume/rerun invariants, checkpoint-source logic, recovery incidents. |
| `vlm_training.md` | VLM training overview, reproduction targets, model/HSDP/curriculum rules. |
| `vlm_data.md` | VLM dataset recipes, upload/counting rules, region-local data notes. |
| `vlm_checkpointing.md` | Durable checkpoints, stateful dataloader, checkpoint/eval restore notes. |
| `spreadsheet_logging.md` | Spreadsheet logging policy and hard-stop rule. |
| `spreadsheet_logging_playbook.md` | Step-by-step spreadsheet logging workflow. |
| `research_loop.md` | Long-running experiment loop pattern. |
| `debug.md` | Remote TPU debug workflow and common JAX/TPU pitfalls. |
| `storage_cleanup.md` | Shared NFS/SSD and local disk cleanup procedures. |
| `project_agents_archive.md` | Verbatim archived `AGENTS.md` source snapshots. |
| `external_memory_archive.md` | Verbatim archived non-AGENTS memory files. |

## Maintenance

- Keep this file as a router, not a history dump.
- Put new operational knowledge in the narrowest topic file.
- Keep archives append-only unless regenerating them intentionally from source
  snapshots.
- Update `project_index.md` when a new checkout or project family becomes
  active.
