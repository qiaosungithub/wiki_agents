# Project Map

Find the right source of truth here, then read the checkout's own docs and git
state before editing it. Guides in this directory hold project semantics; the
files in the parent directory hold rules that apply to every project.

| Guide | Covers |
|---|---|
| `eqr_jax.md` | `EqR` / `EqR-jax`: invariants, packaging traps, checkpoints, metrics, eval protocol |
| `vlm_training.md` | VLM training, checkpointing, resume, evaluation code |
| `vlm_data.md` | VLM datasets, adapters, coordinate invariants, benchmark mirrors |
| `vlm_metrics.md` | VLM benchmark reporting conventions and score floors |
| `agent_web.md` | The Gemini/Amply/Claude agent web checkout |
| `local_agent_cli.md` | Agent CLIs on this workstation (`clod`, `amp`, `gemini`, `gpt`) |

## Code Categories

| Category | Scope | Shared data rule |
|---|---|---|
| Type 1: Kaiming Group code | `jax_llava`, `PaliGemma-baseline`, `beifen-Paligemma`, `beifen` | Data, checkpoints, and compute stay in one region; read `../storage.md` |
| Type 2: Google internal research code | `project_one_ssl`, `one-benchmark-suite`, `nnflow_jax`, `EqR`, `EqR-jax` | The Type 1 cross-region prohibition does not apply; read `../storage.md` before choosing runtime storage |

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
| `EqR/` and `EqR-jax/` | PyTorch and JAX continuous-space reasoning for Sudoku and mazes | `eqr_jax.md`; `jobs.md` for launches |
| `tpu_cmd/` | Shared XManager wrapper, launcher, and job tracking. Only half the tool: the Blaze-built checkers live in google3 under `experimental/users/qiaos/tpu_utils/`, versioned by a separate git repo | `infra/tpu_cli.md`; then native code |
| Agent web / Jetski checkout (resolve the live path) | Web interface for Gemini, Amply, and Claude agents | `agent_web.md`; then native docs |
| `agent-island/` | Terminal session managers for the agent CLIs (`clod`, `amp`, `gpt`, `gemini`) | `local_agent_cli.md`; then native docs |
| `work/reports/` | Paper deep-reading reports | `reports/paper_reading.md` |

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
  Verify any launch section against `jobs.md` and the current wrapper.
- `EqR` and `EqR-jax` are distinct PyTorch and JAX implementations. Do not port
  runtime, data, or checkpoint behavior between them as incidental cleanup.
- Snapshot and backup checkouts are not automatically the active source. Confirm
  the user's target path and branch before transferring a fix between them.

## Native Instructions

Repository-local instructions are authoritative for implementation details.
Generated run directories such as `.arc3-runs/` can also contain narrow local
`AGENTS.md` files; read the nearest one only when working inside that run.

The old exact memory snapshots are under `../archive/legacy/`. They are useful
for recovering provenance, not for deciding how the current system works.
