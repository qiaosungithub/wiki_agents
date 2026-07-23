# Workspace Memory

This folder contains the small amount of shared context an agent needs before
working under `/kmh-nfs-ssd-us-mount/code/qiao/work`.

## Start Here

1. Read this file.
2. Read `projects.md` to identify the checkout and its native documentation.
3. Read one topic guide that matches the task. Do not read every guide.
4. Inspect the current code, git state, and live system before acting. These
   guides explain intent and invariants; they are not a substitute for current
   source or runtime state.

## Workspace Model

- This is a shared research workspace with many independent repositories and a
  shared NFS mount. A task's scope is the checkout the user named, not the whole
  workspace.
- `unified_infra` and its `infra` CLI are the current TPU job system. Legacy
  xibo tools remain only for a few inspection, mount, copy, and cleanup tasks.
- Training data and checkpoints are region-local. Metadata is cheap to inspect;
  large payloads are not safe to move or read across regions by default.
- Agent memory should capture durable decisions and non-obvious invariants.
  Exact commands, incident timelines, job ids, and old configurations belong in
  source docs, live state, experiment records, or `archive/`.

## Global Rules

- Push only when the user's current request explicitly asks for a push.
- Preserve user changes. Never revert, overwrite, or clean a dirty worktree as
  collateral work.
- Avoid cross-region or cross-zone data and checkpoint access. If payload access
  is necessary, first prove compute and storage locality.
- Before deleting shared or local data, identify the filesystem, owner, active
  references, and recovery path. Use a manifest for shared or bulk deletion.
- Treat external writes as transactions: establish identity and target, validate
  assumptions, write the smallest scope, then read back the result.
- Follow repository-local `AGENTS.md` or `CLAUDE.md` files for project-specific
  code semantics. The shared infra, locality, storage, and external-write rules
  here supersede stale operational sections in old project notes. Surface any
  remaining conflict rather than guessing.

## Topic Router

| Task | Read |
|---|---|
| Find a checkout or understand project boundaries | `projects.md` |
| Queue, inspect, resume, debug, or clean up TPU jobs | `infra.md` |
| Change VLM training, checkpointing, resume, or eval code | `vlm_training.md` |
| Upload VLM datasets, audit adapters/coordinates, prepare eval mirrors | `vlm_data.md` |
| Log WandB results into the experiment spreadsheet | `spreadsheet.md` |
| Manage a long-running experiment loop | `research.md` |
| Write a paper deep-reading report | `paper_reading.md` |
| Lay out or debug a report's HTML/PDF rendering | `paper_rendering.md` |
| Reclaim shared NFS or local disk space | `storage.md` |

## Evidence Order

When facts disagree, prefer this order:

1. The user's current request.
2. Current repository code and repository-native docs.
3. Live infra state, logs, WandB, and the spreadsheet.
4. The core guides in this folder.
5. `archive/`, which is historical evidence only.

## Maintaining Memory

- Keep core guides short and decision-oriented.
- Record a rule only when a future agent cannot cheaply infer it from code or
  when violating it has a meaningful cost.
- Replace stale facts instead of appending incident diaries. Never record live
  state (mirror completeness, job status) in a guide; record how to verify it.
- Put dated audit evidence (scan counts, validation numbers, status snapshots)
  under `archive/audits/` and keep only the derived rule plus a pointer in the
  guide. Delete audit snapshots once they are too old to be evidence.
- Preserve detailed or superseded text under `archive/` when it remains useful
  for forensics. Never route a new agent there by default.
