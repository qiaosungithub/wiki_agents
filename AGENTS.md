# Workspace Memory

Durable rules and pointers for working under
`/usr/local/google/home/qiaos/work`. Current code, live state, and the user's
request always outrank this folder.

## Start Here

1. This file.
2. `engineering.md` — the working discipline, for any task.
3. `projects/README.md` — identify the checkout and its native docs.
4. Only the guides the router below names.
5. Then inspect the actual code, git state, and live system.

## Layout

Files here apply to every task. Subdirectories are read on demand; each has a
`README.md` index.

| Path | Scope |
|---|---|
| `engineering.md` | How to verify, diagnose, port, and report. |
| `jobs.md` | Queue, inspect, resume, debug a cluster job. |
| `storage.md` | Where data lives, reading it fast, cleaning up safely. |
| `tpu_reference.md` | Accelerator names, memory, legal shapes, ratios. |
| `infra/` | Allocator and CLI internals, when `jobs.md` falls short. |
| `research/` | Running experiments; logging results. |
| `reports/` | Writing and rendering paper reports. |
| `projects/` | Per-checkout semantics. |
| `archive/` | History. Never routed to by default. |

## Topic Router

| Task | Read |
|---|---|
| Anything, before you start | `engineering.md` |
| Find a checkout, or its boundaries | `projects/README.md` |
| Queue, inspect, resume, debug a job | `jobs.md`, then the project guide |
| Place data or checkpoints; copy or upload | `storage.md`, then the project guide |
| Pick a cell/metro for a v7 run | `research/v7_storage_placement.md` |
| Read a distributed path interactively | `storage.md` §Distributed Reads |
| Reclaim local disk | `storage.md` §Local Disk Cleanup |
| A write fails, or a job produced 0-byte logs | `storage.md` §An Over-Quota Cell Looks Like A Broken Program |
| Resume skips work, or a 0-byte file counts as done | `storage.md` §Existence Is Not Completeness |
| A CPU-only batch job will not schedule | `jobs.md` §Requirements And Runtime |
| Checkpoints filling a cell; pruning them | `storage.md` §Checkpoints Are The Default Reason A Cell Fills Up |
| TPU codename, HBM, legal shape, equivalence | `tpu_reference.md` |
| A job will not schedule; capping spend | `infra/quota_market.md` |
| Change the `tpu` CLI or its daemon | `infra/tpu_cli.md` |
| Manage a long experiment; tracker evidence | `research/experiment_loop.md` |
| **Log a result to the spreadsheet**; find a chart | `research/result_logging.md` |
| Write or render a paper report | `reports/README.md` |
| `EqR` / `EqR-jax` | `projects/eqr_jax.md` |
| VLM training, data, benchmark reporting | `projects/vlm_training.md`, `projects/vlm_data.md`, `projects/vlm_metrics.md` |
| Agent web app, or a local agent CLI | `projects/agent_web.md`, `projects/local_agent_cli.md` |

## Global Rules

**With the user** — Converse in Chinese; write artifacts in English unless a
guide says otherwise (`reports/paper_reading.md` does). Lead with the outcome,
stay concise and plain. Never revert, overwrite, or clean a dirty worktree as
collateral.

**Committing** — Push whenever you like; do not ask for routine work. Push
**immediately** at any sign of edit-tool file corruption (partial writes, rename
failures, duplicated blocks, syntax errors after a "successful" edit), before
the next edit compounds it.

**Jobs** — Submit through `tpu queue`; never call `xm launch` / `xmanager
launch` directly. **A chip count is not a size:** per chip
`v7 = v6p ≈ 2x v6e ≈ 4.34x v5p ≈ 7.23x v4`, so matching a `v6p-16` needs
**`v6e-32`**. Asking for `v6e-16` silently buys HALF the compute and the run is
then compared as if the hardware were equal. `tpu route --power=` does the
arithmetic. Keep compute and storage co-located; never move Type 1 payloads
across regions by default.

**Deleting** — Identify filesystem, owner, active references, and recovery path
first. Use a manifest for shared or bulk deletion.

**Logging results** — Re-read the tab's header and neighboring rows **every
time**; layout drifts and a stale column map mis-files a number without erroring.
Place the row before filling it: find the baseline block this run varies and
insert beside its comparison target, describing a variant as `- <change>`.
**Keep cells short** — record `logdir` / `stagedir` and let those recover the
detail; shared context goes in the block header once, not in every row.
Formatting and color are part of the result.

**Project-local instructions** — Follow a repository's own `AGENTS.md` /
`CLAUDE.md` for its code semantics. The shared infra, storage, and external-write
rules here supersede stale operational sections in old project notes; surface a
conflict rather than guessing.

## Evidence Order

The user's request, then current code and native docs, then live infra state and
logs, then these guides, then `archive/` (history only).

## Maintaining Memory

**Record a rule only when a future agent cannot cheaply infer it from the code,
or when violating it has a real cost.** Everything else dilutes what matters.

- **Write the rule, not the incident.** Keep the one sentence of evidence that
  makes it credible; forensics go to `archive/`.
- **Prefer the abstract statement.** A note that only makes sense for one paper
  or one job id belongs in a project guide or the archive.
- **One canonical owner per rule**; others point at it.
- **Replace stale facts; never append a diary.** No "fixed on <date>", no live
  state. Record how to verify instead.
- **No source line numbers, job ids, or measured tables in a core guide.**
- Delete audit snapshots once they are too old to be evidence.
