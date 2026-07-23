# Project Map

Use this file to find the right source of truth. Read the checkout's own docs
and git state before editing it.

## Code Categories

Workspace repositories fall into two categories:
1. **Kaiming Group Code (Type 1)**: Code from the Kaiming group (e.g., `PaliGemma-baseline`, `jax_llava`, `beifen-Paligemma`, `beifen`). This machine is used solely to execute TPU tasks for these repositories.
2. **Google Internal Research Code (Type 2)**: Code natively for Google internal research (e.g., `project_one_ssl`, `one-benchmark-suite`, `nnflow_jax`).

*Note: Certain global constraints, such as the strict prohibition of cross-region data/checkpoint transfer, apply **only** to Type 1 (Kaiming Group) code.*

## Repositories

| Project family | Purpose | Core context |
|---|---|---|

| `jax_llava/` and its late-fusion snapshots | JAX LLaVA training, data, and evaluation | `vlm_training.md`, `vlm_data.md` |
| `PaliGemma-baseline/` | JIT/HSDP PaliGemma and PrefixMAE baseline | `vlm_training.md`, `vlm_data.md` |
| `beifen-Paligemma/` | Related pmap PaliGemma implementation and data pipeline | `vlm_training.md`, `vlm_data.md` |
| `beifen/` | Dataset upload and visual checks | `vlm_data.md` |
| `project_one_ssl/` | Project One v5 three-stream MAE/DAE baseline | Native `CLAUDE.md`, `docs/REPO_GUIDE.html`, and `docs/AGENT_CONTEXT.md` |
| `one-benchmark-suite/` | Benchmark registry, not a training framework | Native docs; archives only for old context |
| `nnflow_jax/` | JAX implementation of Generative Modeling Through Drifting | Native docs; archives only for old context |
| `readings/vision-related/tutorials/` | Paper deep-reading reports | `paper_reading.md` |

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


## Native Instructions

Repository-local instructions are authoritative for implementation details.
Generated run directories such as `.arc3-runs/` can also contain narrow local
`AGENTS.md` files; read the nearest one only when working inside that run.

The old exact memory snapshots are under `archive/legacy/`. They are useful for
recovering provenance, not for deciding how the current system works.
