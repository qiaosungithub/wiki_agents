# Project Map

Identify the checkout here, read the guide it names, then read that checkout's
own docs and git state before editing. This directory holds per-project
semantics; the parent directory holds the rules common to all of them.

## Data Locality Follows The Category, Not The Task

**Classify the checkout Type 1 or Type 2 before placing any data, checkpoint, or
job; the two obey different storage law.** `../storage.md` owns the detail.

| Category | Members | Rule |
|---|---|---|
| **Type 1: Kaiming Group code** | `jax_llava`, `PaliGemma-baseline`, `beifen-Paligemma`, `beifen` | Data, checkpoints, and compute stay in ONE region. Never move a payload across regions by default. |
| **Type 2: Google internal research code** | `project_one_ssl`, `one-benchmark-suite`, `nnflow_jax`, `EqR`, `EqR-jax` | The Type 1 cross-region prohibition does not apply, but runtime storage must be reachable from every cell the scheduler may pick. |

## Checkout To Guide

"The VLM set" is `vlm_training.md` (training, checkpointing, resume, eval code),
`vlm_data.md` (datasets, adapters, coordinates, mirrors), `vlm_metrics.md`
(reporting conventions, score floors).

| Checkout | Type | What it is | Read |
|---|---|---|---|
| `jax_llava/` (+ late-fusion snapshots) | 1 | JAX LLaVA training, data, evaluation | the VLM set |
| `PaliGemma-baseline/` | 1 | PaliGemma and PrefixMAE baseline, JIT/HSDP | the VLM set |
| `beifen-Paligemma/` | 1 | Sibling pmap PaliGemma and its data pipeline | the VLM set |
| `beifen/` | 1 | Dataset upload and visual checks | `vlm_data.md` |
| `project_one_ssl/` | 2 | Project One v5 three-stream MAE/DAE baseline | that checkout's own `CLAUDE.md`, `docs/REPO_GUIDE.html`, `docs/AGENT_CONTEXT.md` |
| `one-benchmark-suite/` | 2 | Benchmark registry and CPU sanity checks. **Not** a training framework; do not grow it into one | native docs; `../archive/` for old context only |
| `nnflow_jax/` | 2 | JAX Generative Modeling Through Drifting | native docs; `../archive/` for old context only |
| `EqR/`, `EqR-jax/` | 2 | PyTorch and JAX continuous-space reasoning (Sudoku, mazes) | `eqr_jax.md` — invariants, packaging traps, checkpoints, metrics, eval protocol; `../jobs.md` to launch |
| `tpu_cmd/` | n/a | XManager wrapper, launcher, job tracking — **half the tool only**: its Blaze-built checkers live in google3 under `experimental/users/qiaos/tpu_utils/`, in a separate git repo | `../infra/tpu_cli.md`, then native code |
| Agent web / Jetski (resolve the live path) | n/a | Web interface for Gemini, Amply, Claude agents | `agent_web.md`, then native docs |
| `agent-island/` | n/a | Terminal session managers for `clod`, `amp`, `gpt`, `gemini` | `local_agent_cli.md`, then native docs |
| `work/reports/` | n/a | Paper deep-reading reports | `../reports/paper_reading.md` |
| `rnn_unroll/` | 2 | RNN unroll-optimizer science line: gradient propagation / adding problem (vanilla RNN). Remote A100 box, not Borg. | `rnn_unroll_adding.md` |

## Boundaries That Are Easy To Miss

| Boundary | Rule |
|---|---|
| Sibling pairs diverge on purpose | **Never port across one as cleanup.** `PaliGemma-baseline` (JIT/HSDP) vs `beifen-Paligemma` (pmap) share ideas, not execution semantics; `EqR` (PyTorch) vs `EqR-jax` are separate builds. |
| `project_one_ssl` is architecturally constrained | Joint transformer from scratch, frozen Gemma text stream always present, Stream 1 and Stream 3 not sharing mask tokens, reconstruction loss over all patches. **Never "clean up" one of those**, and check its launch instructions against `../jobs.md` and the current wrapper. |
| Snapshots and backups | **A snapshot or backup checkout is not automatically the active source**; confirm target path and branch before transferring a fix into it. |
| Local instructions | **A repository's own instructions win on implementation details**, including the narrow `AGENTS.md` a generated run directory such as `.arc3-runs/` may carry — read that one only while inside that run. The exact memory snapshots under `../archive/legacy/` recover provenance, never behavior. |
