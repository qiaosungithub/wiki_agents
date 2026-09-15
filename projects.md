# Project Map

Identify the checkout here, read the page it names, then read that checkout's own
docs and git state before editing it. Rules common to every checkout are in
`AGENTS.md`.

## Checkout To Guide

**Find the checkout's row before editing; the page it names and the checkout's
own docs are the source of truth.** "The VLM set" below is `vlm_training.md`
(training, checkpointing, resume, and eval code), `vlm_data.md` (datasets,
adapters, coordinates, and mirrors), and `vlm_metrics.md` (which benchmark number
to report).

| Project family | Purpose | Core context |
|---|---|---|
| `unified_infra/` | Current TPU scheduler, daemon, state store, dispatch, and resume | `infra.md`; then `unified_infra/README.md`, `docs/resume_rules.md`, and `docs/robustness.md` |
| `jax_llava/` and its late-fusion snapshots | JAX LLaVA training, data, and evaluation | The VLM set |
| `PaliGemma-baseline/` | JIT/HSDP PaliGemma and PrefixMAE baseline | The VLM set |
| `beifen-Paligemma/` | Related pmap PaliGemma implementation and data pipeline | The VLM set |
| `beifen/` | Dataset upload and visual checks | `vlm_data.md` |
| `one-benchmark-suite/` | Benchmark registry | Native docs; archives only for old context |
| `one-dataset-suite/` | Dataset artifact construction and the shared commit contract | Native docs; `vlm_data.md` |
| `project_one_ssl/` | Project One v5 three-stream MAE/DAE baseline | Native `CLAUDE.md`, `docs/REPO_GUIDE.html`, and `docs/AGENT_CONTEXT.md` |
| `nnflow_jax/` | JAX implementation of Generative Modeling Through Drifting | Native docs; archives only for old context |
| `tpu_manager/` and xibo snapshots | Legacy scheduler/monitor code | `infra.md`; do not treat old JSON as current job state |
| `readings/tutorials/` | Paper deep-reading reports | `paper_reading.md`, `paper_rendering.md` |
| `/kmh-nfs-ssd-us-mount/code/sqa/agent-web/` | Deployed Claude Code + Codex web chats at `chat.kaiming.me` and the session-isolated family site `family-chat.kaiming.me` (outside this workspace) | Native `README.md`; live tmux sessions `webchat` and `webchat_family` |

## Boundaries That Are Easy To Miss

**Each boundary below separates things that look interchangeable and are not, so
never change or port across one as incidental cleanup.**

| Boundary | Rule |
|---|---|
| `PaliGemma-baseline` and `beifen-Paligemma` | They share ideas but not execution semantics. Preserve the former's JIT/HSDP path and the latter's pmap path when porting changes (`vlm_training.md`). |
| `one-benchmark-suite` | It owns benchmark definitions and CPU sanity checks. Do not turn it into a training framework. |
| `project_one_ssl` | Its architectural constraints are deliberate: the joint transformer starts from scratch, the frozen Gemma text stream is always present, Stream 1 and Stream 3 do not share mask tokens, and reconstruction loss covers all patches. Do not alter those choices as incidental cleanup. Its `CLAUDE.md` still names an older project-specific launch flow; verify the current scheduler instead of copying that launch section blindly. |
| Snapshot and backup checkouts | They are not automatically the active source. Confirm the user's target path and branch before transferring a fix between them. |
| The live agent chat | It is `code/sqa/agent-web` (React/Vite + Node/TS), not the older dirty rollback checkout `code/sqa/claude-web-chat`. Confirm tmux `webchat` (or `webchat_family`) and runner busy state before restarting either instance, and treat every session created for testing as disposable with full teardown. Operational detail (build step, family-instance isolation, test-session hygiene) is in that repository's `AGENTS.md`. |

## Native Instructions

**Repository-local instructions are authoritative for implementation details.**
Generated run directories such as `.arc3-runs/` can also contain narrow local
`AGENTS.md` files; read the nearest one only when working inside that run. The
old exact memory snapshots under `archive/legacy/` are useful for recovering
provenance, not for deciding how the current system works.
