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
| `gcp_gpu_ssh.md` | SSH to the GCP GPU VMs (viscam-cloud); OS Login vs metadata keys. |
| `monitoring.md` | The monitor role: watcher, DEAD/idle alerts, handoffs, escalation. |
| `projects/` | Per-checkout semantics and boundaries. |
| `research/` | Running experiments; logging results. |
| `reports/` | Writing and rendering paper reports. |
| `infra/` | Allocator, market, and CLI internals, when `jobs.md` falls short. |
| `tools/` | Executable helpers (price caps); prose elsewhere. |
| `archive/` | History. Never routed to by default. |

## Topic Router

| Task | Read |
|---|---|
| Anything, before you start | `engineering.md` |
| Find a checkout or its boundaries | `projects/README.md` |
| Queue, inspect, resume, debug a job | `jobs.md`, then the project guide |
| Submit a job or a batch (default `tpu enqueue` + serial `tpu build-worker`; auto cell / `--metro`) | `jobs.md` §The Submission Queue In One Screen |
| A CPU-only batch job will not schedule | `jobs.md` §Requirements And Runtime |
| Choose a cell (now auto-picked); preflight before packaging | `jobs.md` §Choosing Where To Run |
| A job will not schedule; capping spend | `infra/quota_market.md`, `tools/limit_order.sh` |
| Change the `tpu` CLI or its daemon | `infra/tpu_cli.md` |
| TPU codename, HBM, legal shape, equivalence | `tpu_reference.md` |
| SSH to a GCP GPU VM; `Permission denied`; OS Login vs metadata keys | `gcp_gpu_ssh.md` |
| **Choose an accelerator family**; a preemptible slice will not hold | `research/accelerator_choice.md` |
| Place data or checkpoints; copy or upload | `storage.md`, then the project guide |
| Pick a cell/metro for a v7 run | `research/v7_storage_placement.md` |
| Read a distributed path interactively | `storage.md` §Distributed Reads |
| A write fails, or a job produced 0-byte logs | `storage.md` §An Over-Quota Cell Looks Like A Broken Program |
| Resume skips work, or a 0-byte file counts as done | `storage.md` §Existence Is Not Completeness |
| Reclaim local disk, or prune checkpoints | `storage.md` §Local Disk Cleanup, §Checkpoints Are The Default Reason A Cell Fills Up |
| Manage a long experiment; tracker evidence | `research/README.md` |
| Build or verify a multi-GB artifact on distributed storage | `storage.md` §Building A Multi-Gigabyte Artifact |
| A big write is silently truncated or keeps restarting | `storage.md` §Two Writers On One Output Path |
| A data-movement job: workstation or cluster? | `jobs.md` §Where The Storage CLI Exists |
| A job says `RUN` but produces nothing | `jobs.md` §`state: RUN` Is Not Evidence |
| Write a checker, or a verification keeps saying OK | `engineering.md` §A Test That Cannot Fail |
| **Log a result to the spreadsheet**; find a chart | `research/result_logging.md` |
| Write or render a paper report | `reports/README.md` |
| **Monitor a fleet of autonomous runs**; watcher, handoffs, DEAD/idle alerts | `monitoring.md` |
| A watched run shows DEAD/500; hand a heavy line to a fresh session | `monitoring.md` |
| Monitor got a request mid-task; track it so it isn't dropped | `monitoring.md` §Track Every Request In The Todo List |
| Write a handoff doc; retire an old session (kill its worker) | `monitoring.md` §Handoffs: Let The Line Summarize Itself |
| `EqR` / `EqR-jax` | `projects/eqr_jax.md` |
| RNN unroll optimizer / adding problem / gradient propagation science line | `projects/rnn_unroll_adding.md` |
| VLM training, data, benchmark reporting | `projects/vlm_training.md`, `projects/vlm_data.md`, `projects/vlm_metrics.md` |
| Agent web app, or a local agent CLI | `projects/agent_web.md`, `projects/local_agent_cli.md` |

## Global Rules

Each rule below is enforced in full by the guide named beside it. These are the
ones expensive enough to state twice.

**With the user** — Converse in Chinese; write artifacts in English, except
paper reports (`reports/README.md`). Lead with the outcome; stay concise and
plain.

**Delegating work — default to a NEW amply session, not a sub-agent** — When
the user asks to "open a session", "hand this off", or otherwise delegate a task,
the default is a brand-new top-level amply run (equivalent to `amp new <name>`),
NOT `spawn_*` sub-agents. Launch it as a chat-only run with an empty task and a
descriptive title via `/tmp/launch_chatonly_run.py "<workdir>" "<title>"` (POSTs
`/api/run/new`), then inject the task/handoff over the chat channel
(`POST $DB/chat/send?run_id=<RID>`). Reserve `spawn_*` sub-agents for the
monitor's own short read-only fan-out. Only skip the new-session default if the
user explicitly asks for a sub-agent.

**Never destroy the user's work** — Do not revert, overwrite, or clean a dirty
worktree as collateral. Before deleting anything shared, identify the
filesystem, owner, active references, and recovery path; use a manifest for bulk
deletion (`engineering.md` §External Writes Are Transactions).

**Committing** — git push is your friend. You can push regularly, but need to be
careful which branch to push.

**Jobs** — On this SHARED workstation, submit through `tpu enqueue` + one serial `tpu build-worker` (the default that dodges the concurrent-build zombie XID); `tpu queue` one-shot only when no other build is in flight. Never call `xm launch` / `xmanager launch` directly (`jobs.md` §Submission Contract).

**BATCH tier is EVAL-ONLY** — Every TRAINING job passes `--tier=PROD`
explicitly; `BATCH` is only ever for eval jobs. `BATCH` is a *paying*
best-effort tier (it bills the group, it is not the free option), and any PROD
demand preempts it the instant a slot is contested — so a training run on BATCH
is silently starved AND still costs. Never train on BATCH (`jobs.md`
§Requirements And Runtime).

**A chip count is not a size** — Per chip, `v7 = v6p ≈ 2x v6e ≈ 4x v5p ≈
8x v4`, so matching a `v6p-16` needs a **`v6e-32`**. Asking for `v6e-16`
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
