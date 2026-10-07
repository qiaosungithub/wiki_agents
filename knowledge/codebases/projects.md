# Project Map

Identify the checkout here, read the guide it names, then read that checkout's
own docs and git state before editing. This page and its sibling pages under
`knowledge/codebases/` hold per-project semantics; the rules common to all of
them live outside this directory ([harness/policy.md §Global Rules](../../harness/policy.md#global-rules),
[harness/engineering.md](../../harness/engineering.md)).

## Data Locality Follows The Category, Not The Task

**Classify the checkout Type 1 or Type 2 before placing any data, checkpoint, or
job.** The two follow different storage rules;
[knowledge/infrastructure/storage.md §Placement Policy By Project Type](../infrastructure/storage.md#placement-policy-by-project-type) has the detail.

| Category | Members | Rule |
|---|---|---|
| Type 1: Kaiming Group code | `jax_llava`, `PaliGemma-baseline`, `beifen-Paligemma`, `beifen` | Data, checkpoints, and compute stay in one region. Never move a payload across regions by default. |
| Type 2: Google internal research code | `project_one_ssl`, `one-benchmark-suite`, `nnflow_jax`, `EqR`, `EqR-jax`, `nanochat` | The Type 1 cross-region ban does not apply, but runtime storage must be reachable from every cell the scheduler may pick. |

## Checkout To Guide

"The VLM set" is [knowledge/codebases/vlm-training.md](vlm-training.md) (training, checkpointing,
resume, eval code), [knowledge/codebases/vlm-data.md](vlm-data.md) (datasets, adapters,
coordinates, mirrors), [knowledge/codebases/vlm-metrics.md](vlm-metrics.md) (reporting conventions,
score floors).

| Checkout | Type | What it is | Read |
|---|---|---|---|
| `jax_llava/` (+ late-fusion snapshots) | 1 | JAX LLaVA training, data, evaluation | the VLM set |
| `PaliGemma-baseline/` | 1 | PaliGemma and PrefixMAE baseline, JIT/HSDP | the VLM set |
| `beifen-Paligemma/` | 1 | Sibling pmap PaliGemma and its data pipeline | the VLM set |
| `beifen/` | 1 | Dataset upload and visual checks | [knowledge/codebases/vlm-data.md](vlm-data.md) |
| `project_one_ssl/` | 2 | Project One v5 three-stream MAE/DAE baseline | that checkout's own `CLAUDE.md`, `docs/REPO_GUIDE.html`, `docs/AGENT_CONTEXT.md` |
| `one-benchmark-suite/` | 2 | Benchmark registry and CPU sanity checks. **Not** a training framework; do not grow it into one | native docs; [archive/](../../archive/) for old context only |
| `nnflow_jax/` | 2 | JAX Generative Modeling Through Drifting | native docs; [archive/](../../archive/) for old context only |
| `EqR/`, `EqR-jax/` | 2 | PyTorch and JAX continuous-space reasoning (Sudoku, mazes) | [knowledge/codebases/eqr-jax.md](eqr-jax.md) — invariants, packaging traps, checkpoints, metrics, eval protocol; [knowledge/infrastructure/cluster-jobs.md](../infrastructure/cluster-jobs.md) to launch |
| `tpu_cmd/` | n/a | XManager wrapper, launcher, job tracking. Half the tool only: its Blaze-built checkers live in google3 under `experimental/users/qiaos/tpu_utils/`, in a separate git repo | [knowledge/infrastructure/tpu-cli.md](../infrastructure/tpu-cli.md), then native code |
| Agent web / Jetski (resolve the live path) | n/a | Web interface for Gemini, Amply, Claude agents | [knowledge/codebases/agent-web.md](agent-web.md), then native docs |
| `agent-island/` | n/a | Terminal session managers for `clod`, `amp`, `gpt`, `gemini` | [knowledge/codebases/local-agent-cli.md](local-agent-cli.md), then native docs |
| `work/reports/` | n/a | Paper deep-reading reports | [paper-reading skill](../../harness/skills/paper-reading/SKILL.md) |
| `rnn_unroll/` | 2 | RNN unroll-optimizer science line: gradient propagation / adding problem (vanilla RNN). Two remote 4×A100 boxes, not Borg. | [knowledge/codebases/rnn-unroll.md](rnn-unroll.md) |
| `charlm/` | 2 | Character-level LM on tiny-shakespeare, reproducing `jcjohnson/torch-rnn`. Dense-supervision counterpart to the adding-problem line. Same 4×A100 boxes. | [knowledge/codebases/charlm.md](charlm.md) |
| `nanogpt_depth/` | 2 | FineWeb-Edu nanoGPT pretraining; exact same-position call/loss gradient and two-band Adam, copied from lyy. | [knowledge/codebases/nanogpt-depth.md](nanogpt-depth.md) |
| `nanochat/` | 2 | Full-pipeline LLM testbed (`Base Pretrain` → `Chat SFT` → `Chat RL` → `Maj@k` scaling, `d12` / `d24`) for studying whether and when recurrent looping is useful. | [knowledge/codebases/nanochat.md](nanochat.md) |
| `paper-with-agent/` | n/a | The paper on the per-site optimizer idea, co-written with the user in three layers; `hie1/` is user-only. | [knowledge/codebases/paper-with-agent.md](paper-with-agent.md) |
| `raft/` | 2 | RAFT-small optical flow (C+T) reproduction and the per-relative-distance optimizer on its 12 tied update calls. Data + runs on `qiaos-4a100` only. | [knowledge/codebases/raft.md](raft.md) |
| `remote-control/`, `remote-control-pipeline/`, `google-job-info/`, `google-job-info-daemon/` | n/a | The git-driven remote job interface for lyy: push a commit to launch a run, read status back as a git repo. Four checkouts, one system. | [knowledge/codebases/remote-control.md](remote-control.md) |
| `survival/`, `survival-pipeline/`, `many-agent-result/` | n/a | Collaborator's stay-alive multi-agent game + the git-driven pipeline: each `sqa-remote` commit == one LOCAL amply run on this box; results pushed back as a git repo. codex→amply adaptation. | [knowledge/codebases/survival.md](survival.md) |

## Boundaries That Are Easy To Miss

| Boundary | Rule |
|---|---|
| Sibling pairs diverge on purpose | **Never port across one as cleanup.** `PaliGemma-baseline` (JIT/HSDP) and `beifen-Paligemma` (pmap) share ideas, not execution semantics; `EqR` (PyTorch) and `EqR-jax` are separate builds. |
| `project_one_ssl` is architecturally constrained | Joint transformer from scratch, frozen Gemma text stream always present, Stream 1 and Stream 3 not sharing mask tokens, reconstruction loss over all patches. Never remove one of those as cleanup, and check its launch instructions against [knowledge/infrastructure/cluster-jobs.md](../infrastructure/cluster-jobs.md) and the current wrapper. |
| Snapshots and backups | A snapshot or backup checkout is not automatically the active source. Confirm target path and branch before transferring a fix into it. |
| Local instructions | A repository's own instructions win on implementation details. That includes the narrow `AGENTS.md` a generated run directory such as `.arc3-runs/` may carry; read that one only while inside that run. The exact memory snapshots under [archive/legacy/](../../archive/legacy/) recover provenance, never behavior. |
