# Moved

This compatibility entry preserves existing links. Edit the canonical pages below.

- [gpu-on-borg skill](harness/skills/gpu-on-borg/SKILL.md)
- [knowledge/infrastructure/gpu-on-borg.md](knowledge/infrastructure/gpu-on-borg.md)

### The Submission, End To End

See [gpu-on-borg skill §The Submission, End To End](harness/skills/gpu-on-borg/SKILL.md#the-submission-end-to-end).

### Rule 2 — A GPU Bazel Binary Needs `--config=cuda` (The Launcher Adds It)

See [knowledge/infrastructure/gpu-on-borg.md §Rule 2 — A GPU Bazel Binary Needs `--config=cuda` (The Launcher Adds It)](knowledge/infrastructure/gpu-on-borg.md#rule-2--a-gpu-bazel-binary-needs---configcuda-the-launcher-adds-it).

### Rule 3 — BUILD A Torch GPU `py_binary` The Staging Way

See [gpu-on-borg skill §Rule 3 — BUILD A Torch GPU `py_binary` The Staging Way](harness/skills/gpu-on-borg/SKILL.md#rule-3--build-a-torch-gpu-py_binary-the-staging-way).

### The Dependency Versions Come From The Staging Workspace, Not From You

See [knowledge/infrastructure/gpu-on-borg.md §The Dependency Versions Come From The Staging Workspace, Not From You](knowledge/infrastructure/gpu-on-borg.md#the-dependency-versions-come-from-the-staging-workspace-not-from-you).

### FlashAttention Is Available, With Two Conditions

See [knowledge/infrastructure/gpu-on-borg.md §FlashAttention Is Available, With Two Conditions](knowledge/infrastructure/gpu-on-borg.md#flashattention-is-available-with-two-conditions).

### The Startup Contract — Failures Before Your Code Runs

See [knowledge/infrastructure/gpu-on-borg.md §The Startup Contract — Failures Before Your Code Runs](knowledge/infrastructure/gpu-on-borg.md#the-startup-contract--failures-before-your-code-runs).

### Rule 4 — No File/RPC At Module Import (InitGoogle Not Done)

See [knowledge/infrastructure/gpu-on-borg.md §Rule 4 — No File/RPC At Module Import (InitGoogle Not Done)](knowledge/infrastructure/gpu-on-borg.md#rule-4--no-filerpc-at-module-import-initgoogle-not-done).

### Rule 4b — `app.run` MUST Use `known_only=True`, Or The Job Dies Before `main()`

See [knowledge/infrastructure/gpu-on-borg.md §Rule 4b — `app.run` MUST Use `known_only=True`, Or The Job Dies Before `main()`](knowledge/infrastructure/gpu-on-borg.md#rule-4b--apprun-must-use-known_onlytrue-or-the-job-dies-before-main).

### Rule 5 — GPU Topology: One Task, N Local GPUs, You Own NCCL

See [knowledge/infrastructure/gpu-on-borg.md §Rule 5 — GPU Topology: One Task, N Local GPUs, You Own NCCL](knowledge/infrastructure/gpu-on-borg.md#rule-5--gpu-topology-one-task-n-local-gpus-you-own-nccl).

### Rule 6 — Tiers: BATCH Preempts Freely, PROD Preempts Rarely

See [knowledge/infrastructure/gpu-on-borg.md §Rule 6 — Tiers: BATCH Preempts Freely, PROD Preempts Rarely](knowledge/infrastructure/gpu-on-borg.md#rule-6--tiers-batch-preempts-freely-prod-preempts-rarely).

### Rule 7 — The Real Wall Is The Budget Gate, Not Capacity Or Preemption

See [knowledge/infrastructure/gpu-on-borg.md §Rule 7 — The Real Wall Is The Budget Gate, Not Capacity Or Preemption](knowledge/infrastructure/gpu-on-borg.md#rule-7--the-real-wall-is-the-budget-gate-not-capacity-or-preemption).

### Preflight, Placement, Capacity (Same Tools, GPU-Aware)

See [gpu-on-borg skill §Preflight, Placement, Capacity (Same Tools, GPU-Aware)](harness/skills/gpu-on-borg/SKILL.md#preflight-placement-capacity-same-tools-gpu-aware).

### Quick Diagnosis Map (GPU-specific)

See [gpu-on-borg skill §Quick Diagnosis Map (GPU-specific)](harness/skills/gpu-on-borg/SKILL.md#quick-diagnosis-map-gpu-specific).

### Measure The Container's Input Path Before Blaming It; Co-Located CNS Is Fast

See [gpu-on-borg skill §Measure The Container's Input Path Before Blaming It; Co-Located CNS Is Fast](harness/skills/gpu-on-borg/SKILL.md#measure-the-containers-input-path-before-blaming-it-co-located-cns-is-fast).

### GB200 / GB300 Are Not Obtainable — Do Not Plan Around Them

See [knowledge/infrastructure/gpu-on-borg.md §GB200 / GB300 Are Not Obtainable — Do Not Plan Around Them](knowledge/infrastructure/gpu-on-borg.md#gb200--gb300-are-not-obtainable--do-not-plan-around-them).

### Accelerator Names, NVLink Domains, Capability

See [knowledge/infrastructure/gpu-on-borg.md §Accelerator Names, NVLink Domains, Capability](knowledge/infrastructure/gpu-on-borg.md#accelerator-names-nvlink-domains-capability).
