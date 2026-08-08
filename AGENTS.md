# Workspace Memory

Durable rules for working under `/usr/local/google/home/qiaos/work`. Current
code, live state, and the user's request always outrank this folder.

## Start Here

1. This file, then `engineering.md` — the working discipline, for any task.
2. `projects/README.md` — identify the checkout, its category, and its guide.
3. Only the guides the router below names.
4. Then the actual code, git state, and live system.

## Layout

Files in this directory apply to every task; subdirectories are read on demand
and each has a `README.md` index.

| Path | Owns |
|---|---|
| `engineering.md` | Method: how to verify, diagnose, port, and report. |
| `jobs.md` | Queue, inspect, resume, debug a cluster job. |
| `storage.md` | Where data lives, reading it fast, cleaning up safely. |
| `tpu_reference.md` | Accelerator names, memory, legal shapes, ratios. |
| `projects/` | Per-checkout semantics and boundaries. |
| `research/` | Running experiments; logging results. |
| `reports/` | Writing and rendering paper reports. |
| `infra/` | Allocator, market, and CLI internals, when `jobs.md` falls short. |
| `archive/` | History. Never routed to by default. |

## Topic Router

| Task | Read |
|---|---|
| Anything, before you start | `engineering.md` |
| Find a checkout or its boundaries | `projects/README.md` |
| Queue, inspect, resume, debug a job | `jobs.md`, then the project guide |
| A CPU-only batch job will not schedule | `jobs.md` §Requirements And Runtime |
| Choose a cell; preflight before packaging | `jobs.md` §Choosing Where To Run |
| A job will not schedule; capping spend | `infra/quota_market.md` |
| Change the `tpu` CLI or its daemon | `infra/tpu_cli.md` |
| TPU codename, HBM, legal shape, equivalence | `tpu_reference.md` |
| Place data or checkpoints; copy or upload | `storage.md`, then the project guide |
| Pick a cell/metro for a v7 run | `research/v7_storage_placement.md` |
| Read a distributed path interactively | `storage.md` §Distributed Reads |
| A write fails, or a job produced 0-byte logs | `storage.md` §An Over-Quota Cell Looks Like A Broken Program |
| Resume skips work, or a 0-byte file counts as done | `storage.md` §Existence Is Not Completeness |
| Reclaim local disk, or prune checkpoints | `storage.md` §Local Disk Cleanup, §Checkpoints Are The Default Reason A Cell Fills Up |
| Manage a long experiment; tracker evidence | `research/experiment_loop.md` |
| **Log a result to the spreadsheet**; find a chart | `research/result_logging.md` |
| Write or render a paper report | `reports/README.md` |
| `EqR` / `EqR-jax` | `projects/eqr_jax.md` |
| VLM training, data, benchmark reporting | `projects/vlm_training.md`, `projects/vlm_data.md`, `projects/vlm_metrics.md` |
| Agent web app, or a local agent CLI | `projects/agent_web.md`, `projects/local_agent_cli.md` |

## Global Rules

Each rule below is enforced in full by the guide named beside it. These are the
ones expensive enough to state twice.

**With the user** — Converse in Chinese; write artifacts in English, except
paper reports (`reports/README.md`). Lead with the outcome; stay concise and
plain.

**Never destroy the user's work** — Do not revert, overwrite, or clean a dirty
worktree as collateral. Before deleting anything shared, identify the
filesystem, owner, active references, and recovery path; use a manifest for bulk
deletion (`engineering.md` §External Writes Are Transactions).

**Committing** — Push whenever you like; do not ask for routine work. Push
**immediately** at any sign of edit-tool file corruption (partial writes, rename
failures, duplicated blocks, syntax errors after a "successful" edit), before
the next edit compounds it. In a shared worktree, `git commit -- <pathspec>`
ignores the index and will steal a peer's hunk (`engineering.md` §Sharing One
Worktree).

**Jobs** — Submit through `tpu queue`; never call `xm launch` / `xmanager
launch` directly (`jobs.md` §Submission Contract).

**A chip count is not a size** — Per chip, `v7 = v6p ≈ 2x v6e ≈ 4.34x v5p ≈
7.23x v4`, so matching a `v6p-16` needs a **`v6e-32`**. Asking for `v6e-16`
silently buys HALF the compute, and the run is then compared as if the hardware
were equal. `tpu route --power=` does the arithmetic (`tpu_reference.md`).

**Storage** — Keep compute and storage co-located; a job far from its data is
killed by the pruner, not merely slowed. Never move Type 1 payloads across
regions (`storage.md`, `projects/README.md` for the category).

**Logging results** — Re-read the tab's header and neighboring rows **every
time**; layout drifts and a stale column map mis-files a number without
erroring. Place the row before filling it, keep cells short, and treat
formatting as part of the result (`research/result_logging.md`).

**Project-local instructions** — A repository's own `AGENTS.md` / `CLAUDE.md` is
authoritative for its code semantics. The shared infra, storage, and
external-write rules here supersede stale operational sections in old project
notes; surface a conflict rather than guessing.

## Evidence Order

The user's request, then current code and native docs, then live infra state and
logs, then these guides, then `archive/` (history only).

## Maintaining Memory

**Record a rule only when a future agent cannot cheaply infer it from the code,
or when violating it has a real cost.** Everything else dilutes what matters.

- **Write the rule, not the incident.** Keep the one clause of evidence that
  makes it credible; forensics go to `archive/`, or to git history.
- **Prefer the abstract statement.** A note that only makes sense for one paper
  or one job id belongs in a project guide or the archive.
- **One canonical owner per rule**; everyone else points at it by file name.
- **Replace stale facts; never append a diary.** No "fixed on <date>", no live
  state, no source line numbers, no job ids. Record how to verify instead.
- **Lead a section with its rule in bold.** A reader who stops after the first
  sentence must not be misled.
- **Prefer a table to five parallel bullets.** Delete audit snapshots once they
  are too old to be evidence.
