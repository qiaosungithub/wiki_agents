# Workspace Memory

Shared context for working under `/usr/local/google/home/qiaos/work`. Everything
here is a durable rule or a pointer; current code, live state, and the user's
request always outrank it.

## Start Here

1. Read this file.
2. Read `engineering.md` — the working discipline that applies to every task.
3. Read `projects/README.md` to identify the checkout and its native docs.
4. Read the guides named by the matching router row, and no unrelated guides.
5. Inspect the current code, git state, and live system before acting.

## Layout

Files in this directory apply to **every** task. Subdirectories are read on
demand and each has a `README.md` index.

| Path | Scope |
|---|---|
| `engineering.md` | How to verify, diagnose, port, and report. Read for any task. |
| `jobs.md` | Queue, inspect, resume, or debug a cluster job. |
| `storage.md` | Where data lives, how to read it fast, how to clean up safely. |
| `tpu_reference.md` | Accelerator names, memory, legal shapes, performance ratios. |
| `infra/` | Allocator and CLI internals. Only when `jobs.md` cannot explain what you see. |
| `research/` | Running an experiment program and recording its results. |
| `reports/` | Writing and rendering paper deep-reading reports. |
| `projects/` | Per-checkout semantics and invariants. |
| `archive/` | Historical evidence. Never routed to by default. |

## Global Rules

**Working with the user**

- Converse in Chinese. Write repository artifacts in English unless a task guide
  requires otherwise, as `reports/paper_reading.md` does.
- Lead with the outcome. Keep responses concise and plain; explain a technical
  term only when it helps the user decide or act.
- Preserve user changes. Never revert, overwrite, or clean a dirty worktree as
  collateral work.

**Committing**

- Default policy is "push whenever you like" — do not ask before pushing routine
  work. Push at natural checkpoints: a feature works end to end, a bug is fixed,
  a session is ending.
- Push **immediately, without asking**, at any sign of edit-tool file corruption
  (partial writes, rename failures, duplicated blocks, syntax errors after a
  supposedly successful edit), so the working state is preserved before the next
  edit compounds the damage.

**Infrastructure**

- Submit cluster jobs through `tpu queue`. Never call `xm launch` or
  `xmanager launch` directly; only the wrapper may do so internally. See
  `jobs.md`.
- **A chip count is not a size. Convert before you launch.** Per chip,
  `v7 = v6p ≈ 2x v6e ≈ 4.34x v5p ≈ 7.23x v4`. The run matching a `v6p-16`
  baseline is **`v6e-32`**, not `v6e-16` — asking for `v6e-16` silently buys
  HALF the compute, and the result is then compared against its siblings as if
  the hardware were equal. Restate every request in the baseline's units when
  the accelerator changes, and put the equivalence in the run name.
  `tpu route --power=v6p-16` does the arithmetic; `tpu_reference.md` owns the
  table and the caveats a single scalar cannot express.
- Keep compute and storage co-located, and never move Type 1 payloads across
  regions or zones by default. See `storage.md`.
- Before deleting shared or local data, identify the filesystem, owner, active
  references, and recovery path. Use a manifest for shared or bulk deletion.

**Logging results to the experiment spreadsheet**

- Every run that reaches a conclusion is and should be logged to the shared experiment
  spreadsheet. **Re-read the tab's header and its neighboring rows every time**
  — columns and layout change between sessions, and a stale column map writes a
  number into the wrong benchmark without erroring.
- **Place the row before filling it.** Find the baseline block this run varies,
  insert next to its comparison target, and describe a variant as `- <change>`
  relative to that baseline. Appending at the end destroys the comparison.
- **Do not write essays in a spreadsheet.** Keep Settings and Notes short; a
  delta row states only what changed and never restates the baseline. What makes
  brevity safe is recording `logdir` / `stagedir` — those recover the exact code
  and config, so the prose does not have to. Explanations of why a bug happened
  belong in the commit message.
- Formatting and color are part of the result. Match the block's conventions,
  clear formatting inherited from an inserted row, never repurpose a color that
  already has a defined meaning, and keep the metric columns visible.
- Helper scripts for reading metrics or writing rows are worth keeping, but must
  re-derive the column map from the live sheet on every run. See
  `research/result_logging.md`.

**Project-local instructions**

Follow a repository's own `AGENTS.md` / `CLAUDE.md` for its code semantics. The
shared infrastructure, storage, and external-write rules here supersede stale
operational sections in old project notes. Surface a remaining conflict rather
than guessing.

## Topic Router

| Task | Read |
|---|---|
| Anything — before you start | `engineering.md` |
| Find a checkout or understand project boundaries | `projects/README.md` |
| Queue, inspect, resume, or debug a job | `jobs.md`; then the project guide |
| Choose where data or checkpoints live; copy or upload a payload | `storage.md`; then the project guide |
| Read a distributed path from a CLI, watch loop, or anything interactive | `storage.md` §Distributed Reads |
| Reclaim local disk space | `storage.md` §Local Disk Cleanup |
| Look up a TPU codename, HBM capacity, legal shape, or equivalence | `tpu_reference.md` |
| A job will not schedule, or you are capping what it pays | `infra/quota_market.md` |
| Change the `tpu` CLI, its checkers, or its daemon | `infra/tpu_cli.md` |
| Manage a long-running experiment or inspect tracker evidence | `research/experiment_loop.md` |
| Log a result to the experiment spreadsheet, or find a job's chart link | `research/result_logging.md` |
| Write or render a paper deep-reading report | `reports/README.md` |
| Change or run `EqR` / `EqR-jax` | `projects/eqr_jax.md` |
| Change VLM training, data, or benchmark reporting | `projects/vlm_training.md`, `projects/vlm_data.md`, `projects/vlm_metrics.md` |
| Operate the agent web app, or an agent CLI on this workstation | `projects/agent_web.md`, `projects/local_agent_cli.md` |

## Evidence Order

When facts disagree: the user's current request, then current repository code
and its native docs, then live infra state and logs, then the guides here, then
`archive/` — which is historical evidence only.

## Maintaining Memory

**Record a rule only when a future agent cannot cheaply infer it from the code,
or when violating it has a real cost.** Everything else is noise that dilutes
what matters.

- **Write the rule, not the incident.** An event earns a place here only as the
  general lesson it teaches. Keep the minimum evidence that makes the rule
  credible — usually one sentence — and put the forensics in `archive/`.
- **Prefer the abstract statement.** If a note only makes sense for one paper,
  one job id, or one config, it belongs in the project guide or the archive, not
  in a shared guide.
- **One canonical owner per rule.** Other guides point at it; they do not
  restate it with different scope or strength.
- **Replace stale facts; never append a diary.** No "fixed on <date>", no live
  state (mirror completeness, job status, current prices). Record how to verify
  it instead.
- **No source line numbers, job ids, or measured tables in a core guide.** They
  age badly and invite false precision. Keep the shape of the conclusion; move
  the numbers to `archive/audits/` if they are worth keeping at all.
- Delete audit snapshots once they are too old to be evidence.
