# Shared Agent Memory

This folder is the cross-repository operational wiki for
`/kmh-nfs-ssd-us-mount/code/qiao/work`. It is meant to get a new agent oriented
quickly from one place.

Exact snapshots of discovered source `AGENTS.md` files are preserved in
`project_agents_archive.md`. Exact snapshots of other agent-memory files such
as `CLAUDE.md`, `NOTES.md`, and `agents_*.md` are preserved in
`external_memory_archive.md`.

## Quick Start For A New Agent

1. Read `/kmh-nfs-ssd-us-mount/code/qiao/work/AGENTS.md`.
2. Read this file.
3. Read `project_index.md` for the checkout you will edit.
4. If a project-local `AGENTS.md` still exists, read it before editing that
   subtree; after the centralization cleanup, absence is expected for many
   checkouts.
5. Read the topic guide that matches the task:
   - TPU status, queue, launch, resume, zombie holders: `tpu.md`
   - MONITOR internals, xibo state, remote Linux users: `xibo_monitor.md`
   - VLM/PaliGemma/JAX LLaVA training memory: `vlm_training.md`
   - Spreadsheet and WandB result logging: `spreadsheet_logging.md`
   - Long-running experiment loop practices: `research_loop.md`
   - Remote debug jobs and common JAX/TPU pitfalls: `debug.md`
   - Shared SSD cleanup: `storage_cleanup.md`
   - Project checkout index: `project_index.md`
   - Verbatim legacy memory archive: `project_agents_archive.md`,
     `external_memory_archive.md`

## Hard Rules

- Do not push code changes unless the user explicitly asks for a push in the
  current request.
- Before editing a project, read that project's local `AGENTS.md` if it exists;
  otherwise use `project_index.md` plus the relevant topic guide.
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
  `wiki_agents/*.md` topic file and update the exact archive.
- If the user asks to align or update SFT code from a `tmp` folder, interpret
  the target as that `tmp` folder unless they explicitly say to modify the
  current repository.
- When comparing current code with a stagedir copy such as `../tmp`, ask before
  making ambiguous cross-repo changes, and keep local repo changes uncommitted
  unless instructed otherwise.

## Task Routing

| Task | Read |
|---|---|
| Find or claim TPU, check jobs, read logs, handle stale holders | `tpu.md` |
| Modify local MONITOR queue/resume logic | `xibo_monitor.md`, `project_agents_archive.md` |
| Modify xibo manager sandbox / remote Linux user support | `xibo_monitor.md`, `project_agents_archive.md`, `external_memory_archive.md` |
| Edit JAX LLaVA / PaliGemma training code | `vlm_training.md`, `project_agents_archive.md` |
| Upload VLM datasets or generate visual reports | `vlm_training.md`, `project_agents_archive.md` |
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
- Non-AGENTS legacy agent memory is archived exactly in
  `external_memory_archive.md`, including one-benchmark-suite Claude guidance,
  nnflow_jax Claude guidance, root agent notes, and xibo sandbox mistake notes.

## Maintenance Checklist

When adding or changing shared memory:

1. Put cross-repo operational knowledge in the narrowest topic file here.
2. Add or update `project_index.md` if a new checkout-level memory file appears.
3. Update `project_agents_archive.md` or `external_memory_archive.md` when exact
   source text should be preserved.
4. Keep this file short; it should remain a routing page, not a history dump.
