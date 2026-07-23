# Project Map

Use this file to find the right source of truth. Read the checkout's own docs
and git state before editing it.

| Project family | Purpose | Core context |
|---|---|---|
| `unified_infra/` | Current TPU scheduler, daemon, state store, dispatch, and resume | `infra.md`; then `unified_infra/README.md`, `docs/resume_rules.md`, and `docs/robustness.md` |
| `jax_llava/` and its late-fusion snapshots | JAX LLaVA training, data, and evaluation | `vlm_training.md`, `vlm_data.md` |
| `PaliGemma-baseline/` | JIT/HSDP PaliGemma and PrefixMAE baseline | `vlm_training.md`, `vlm_data.md` |
| `beifen-Paligemma/` | Related pmap PaliGemma implementation and data pipeline | `vlm_training.md`, `vlm_data.md` |
| `beifen/` | Dataset upload and visual checks | `vlm_data.md` |
| `project_one_ssl/` | Project One v5 three-stream MAE/DAE baseline | Native `CLAUDE.md`, `docs/REPO_GUIDE.html`, and `docs/AGENT_CONTEXT.md` |
| `one-benchmark-suite/` | Benchmark registry, not a training framework | Native docs; archives only for old context |
| `nnflow_jax/` | JAX implementation of Generative Modeling Through Drifting | Native docs; archives only for old context |
| `tpu_manager/` and xibo snapshots | Legacy scheduler/monitor code | `infra.md`; do not treat old JSON as current job state |
| `readings/vision-related/tutorials/` | Paper deep-reading reports | `paper_reading.md` |
| `/kmh-nfs-ssd-us-mount/code/sqa/agent-web/` | Deployed Claude Code + Codex web chats at `chat.kaiming.me` and the session-isolated family site `family-chat.kaiming.me` (outside this workspace) | Native `README.md`; live tmux sessions `webchat` and `webchat_family` |

## Project Boundaries That Are Easy To Miss

- `PaliGemma-baseline` and `beifen-Paligemma` share ideas but not execution
  semantics. Preserve the former's JIT/HSDP path and the latter's pmap path when
  porting changes.
- `one-benchmark-suite` owns benchmark definitions and CPU sanity checks. Do not
  turn it into a training framework.
- `project_one_ssl` has deliberate architectural constraints: the joint
  transformer starts from scratch, the frozen Gemma text stream is always
  present, Stream 1 and Stream 3 do not share mask tokens, and reconstruction
  loss covers all patches. Do not alter those choices as incidental cleanup.
  Its `CLAUDE.md` still names an older project-specific launch flow; verify the
  current scheduler instead of copying that launch section blindly.
- Snapshot and backup checkouts are not automatically the active source. Confirm
  the user's target path and branch before transferring a fix between them.
- The live agent chat is `code/sqa/agent-web` (React/Vite + Node/TS), not the
  older dirty rollback checkout `code/sqa/claude-web-chat`. Confirm tmux
  `webchat` (or `webchat_family`) and runner busy state before restarting
  either instance, and treat every session created for testing as disposable
  with full teardown. Operational detail (build step, family-instance
  isolation, test-session hygiene) is in that repository's `AGENTS.md`.

## Native Instructions

Repository-local instructions are authoritative for implementation details.
Generated run directories such as `.arc3-runs/` can also contain narrow local
`AGENTS.md` files; read the nearest one only when working inside that run.

The old exact memory snapshots are under `archive/legacy/`. They are useful for
recovering provenance, not for deciding how the current system works.
