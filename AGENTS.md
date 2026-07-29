# Workspace Memory

This folder contains the small amount of shared context an agent needs before
working under `/usr/local/google/home/qiaos/work`.

## Start Here

1. Read this file.
2. Read `projects.md` to identify the checkout and its native documentation.
3. Read every guide named by the matching router row, and no unrelated guides.
4. Inspect the current code, git state, and live system before acting. These
   guides explain intent and invariants; they are not a substitute for current
   source or runtime state.

## Workspace Model

- This is a shared research workspace with many independent repositories. A
  task's scope is the checkout the user named, not the whole workspace.
- Classify the checkout in `projects.md` before applying infrastructure rules.
  Type 1 and Type 2 projects have different data-locality policies.
- Agent memory should capture durable decisions and non-obvious invariants.
  Exact commands, incident timelines, job ids, and old configurations belong in
  source docs, live state, experiment records, or `archive/`.

## Global Rules

- Converse with the user in Chinese. Write repository artifacts in English
  unless a task guide explicitly requires another content language, as
  `paper_reading.md` does.
- Keep user-facing responses concise and natural. Lead with the outcome, use
  plain Chinese, and avoid jargon, repetition, long preambles, or unnecessary
  structure. Explain technical terms only when they help the user decide or act.
- The operator's default policy is "push whenever you like" — do not ask
  before `git push` for routine work. Push proactively at natural
  checkpoints (a feature works end-to-end, a bug is fixed, a session is
  about to end). Push IMMEDIATELY without asking if the edit tooling has
  shown any sign of file corruption (partial writes, `Rename failed`
  errors, unexpected duplicated blocks, syntax errors after a supposedly
  successful edit) so the working state is preserved on the remote before
  the next edit potentially compounds the damage.
- Preserve user changes. Never revert, overwrite, or clean a dirty worktree as
  collateral work.
- Before changing code, verify the task premise against the current state:
  reproduce when feasible, inspect the relevant code, tests, and recent history,
  and compare current behavior with the acceptance criteria. "No change needed"
  is a valid outcome, but failed reproduction alone is not proof; account for
  partial or incorrect prior fixes.
- Before claiming completion, re-read the original request and acceptance
  criteria, run the most relevant available checks, read their complete output,
  and compare the result with the request, not with the patch. State anything
  that remains unverified.
- For Type 1 projects, never read or move data and checkpoint payloads across
  regions or zones by default. Prove compute and storage locality first; see
  `data_locality.md`.
- Submit XManager jobs through `tpu queue`, never by calling `xm launch` or
  `xmanager launch` directly. Only the wrapper may invoke them internally; see
  `xmanager.md`.
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
| Choose cells/buckets or access, copy, or upload payloads | `data_locality.md`; then the data guide/native docs listed in `projects.md`, if any |
| Queue, inspect, resume, or debug XManager/Borg jobs, including `deepmind-dynamic` | `xmanager.md`; then the guide/native docs listed in `projects.md`, if any |
| Look up a TPU codename, HBM capacity, legal slice shape, or topology string | `tpu_reference.md` |
| Cap what a job pays, or debug a job stuck pending on a dynamic pool | `limit_orders.md`; then `xmanager.md` |
| Change or run `EqR` / `EqR-jax` | `eqr_jax.md`; also `xmanager.md` when launching |
| Operate or debug the Gemini/Amply/Claude agent web app | `agent_web_gemini.md` |
| Launch or manage an agent CLI on this workstation (`clod`, `amp`, `gemini`) | `local_agent_cli.md` |
| Change VLM training, checkpointing, resume, or eval code | `vlm_training.md` |
| Upload VLM datasets, audit adapters/coordinates, prepare eval mirrors | `vlm_data.md` |
| Log WandB results into the experiment spreadsheet | `spreadsheet.md` |
| Manage a long-running experiment or inspect WandB/tracker evidence | `research.md` |
| Write a paper deep-reading report | `paper_reading.md` |
| Lay out or debug a report's HTML/PDF rendering | `paper_rendering.md` |
| Reclaim local disk space | `storage.md` |

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
- Give each durable rule one canonical owner. Other guides should point to it,
  not restate it with different scope or strength.
- Replace stale facts instead of appending incident diaries. Never record live
  state (mirror completeness, job status) in a guide; record how to verify it.
- Put dated audit evidence (scan counts, validation numbers, status snapshots)
  under `archive/audits/` and keep only the derived rule plus a pointer in the
  guide. Delete audit snapshots once they are too old to be evidence.
- Preserve detailed or superseded text under `archive/` when it remains useful
  for forensics. Never route a new agent there by default.
