# Workspace Knowledge

Describes the user's codebases, infrastructure, environment, and research.
Current source and live state outrank these notes. How to do a task lives in the
[harness](../harness/README.md); a skill links back to the facts here instead of
copying them. A codebase or infra invariant belongs here even when it is phrased
as a constraint.

## Codebases

| Page | Owns |
|---|---|
| [projects.md](codebases/projects.md) | The checkout map: Type 1 / Type 2 data-locality classification, checkout to page, and the boundaries that are easy to miss |
| [eqr-jax.md](codebases/eqr-jax.md) | `EqR` / `EqR-jax`: model, q-head, dataset and run-length invariants, metric keys, divisors, eval protocol, maze and close-loop scoring, the RoboTwin baseline |
| [raft.md](codebases/raft.md) | RAFT-small reproduction: reference recipe, targets, the per-site optimizer, findings, the JAX port |
| [charlm.md](codebases/charlm.md) | char-LM torch-rnn reproduction: configuration, split protocol, metrics, findings |
| [rnn-unroll.md](codebases/rnn-unroll.md) | RNN unroll adding problem: the question, metrics, the per-site unroll mechanism, findings |
| [nanogpt-depth.md](codebases/nanogpt-depth.md) | nanoGPT call/loss diagonal: gradient contract, two-band optimizer, reference configuration, findings |
| [nanochat.md](codebases/nanochat.md) | nanochat full-pipeline testbed (Base → SFT → RL → Maj@k): stages, metrics, findings |
| [vlm-training.md](codebases/vlm-training.md) | VLM training, mesh and data stream, checkpoint transaction, stage boundaries, final eval |
| [vlm-data.md](codebases/vlm-data.md) | VLM coordinates, source schemas, grounding aliases, final-eval benchmarks |
| [vlm-metrics.md](codebases/vlm-metrics.md) | Which VLM benchmark number to report, trivial floors, the VLM tab's colours |
| [paper-with-agent.md](codebases/paper-with-agent.md) | The paper repo: the hie1 / hie2 / hie3 layers (hie1 is user-only) and the ICML template |
| [agent-web.md](codebases/agent-web.md) | How the agent web / Jetski stack is wired |
| [local-agent-cli.md](codebases/local-agent-cli.md) | The agent CLIs (`clod`, `amp`, `gpt`, `gemini`) and the amply database |
| [remote-control.md](codebases/remote-control.md) | The git-driven remote-control job interface |
| [survival.md](codebases/survival.md) | The survival game and its sqa-remote commit-to-run wrapper |

## Infrastructure

| Page | Owns |
|---|---|
| [cluster-jobs.md](infrastructure/cluster-jobs.md) | How submission works (queues, serial builder, router, tiers, groups, budget gate, launcher), preemption, and the worker environment |
| [resume-contracts.md](infrastructure/resume-contracts.md) | `LOAD_FROM`, `restart_from`, the `CHECKPOINT_BUCKET` write path, the New Training Package Startup Contract |
| [wandb-upload.md](infrastructure/wandb-upload.md) | How the tpu-side automatic W&B upload rebuilds a finished job's run |
| [storage.md](infrastructure/storage.md) | Placement, co-location, the cell -> metro -> bucket table rule, quota, checkpoint path shapes, `/tmp` |
| [market.md](infrastructure/market.md) | The accelerator market: allocator model, tiers, price caps, why a job will not schedule |
| [budget.md](infrastructure/budget.md) | The income/10 budget gates: `budget_check`, `budget_enforcer`, exemptions, failure modes |
| [router.md](infrastructure/router.md) | The smart cell-picker, local queue and auto-reroute, serial build-worker |
| [tpu-cli.md](infrastructure/tpu-cli.md) | Internals of the `tpu` tool: two repos, `npu`, cache daemon, registry, preflight |
| [tpu-reference.md](infrastructure/tpu-reference.md) | Accelerator names, per-chip capability, conversion ratios, legal shapes, NVIDIA GPUs |
| [accelerator-choice.md](infrastructure/accelerator-choice.md) | Measured evidence that obtainability beats peak FLOPs, and the rules that follow |
| [v7-storage-placement.md](infrastructure/v7-storage-placement.md) | Which metros carry data mirrors for v7 runs |
| [gpu-on-borg.md](infrastructure/gpu-on-borg.md) | How an NVIDIA GPU job on Borg behaves: startup contract, build, topology, tiers, capacity |

## Environment

| Page | Owns |
|---|---|
| [workstation.md](environment/workstation.md) | The `sqa-large` workstation: reaching it, what runs where, reboot survival, the migration from `sqa` |
| [gcp-gpu-vms.md](environment/gcp-gpu-vms.md) | The GCP GPU VMs (viscam-cloud): access gates, our own boxes, quota readings |
| [result-workbooks.md](environment/result-workbooks.md) | Which results workbook and tab each project writes to |

## Research

| Page | Owns |
|---|---|
| [research/README.md](research/README.md) | Index of the research pages |
| [looped_nanogpt_per_site.md](research/looped_nanogpt_per_site.md) | The core research idea page |
