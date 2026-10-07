# Moved

This compatibility entry preserves existing links. Edit the canonical pages below.

- [knowledge/infrastructure/wandb-upload.md](../knowledge/infrastructure/wandb-upload.md)
- [wandb-upload skill](../harness/skills/wandb-upload/SKILL.md)

### Chapter 1 — How It Works

See [knowledge/infrastructure/wandb-upload.md](../knowledge/infrastructure/wandb-upload.md).

### On-Borg jobs never reach W&B, so the run is rebuilt offline from the datatable

See [knowledge/infrastructure/wandb-upload.md §On-Borg jobs never reach W&B, so the run is rebuilt offline from the datatable](../knowledge/infrastructure/wandb-upload.md#on-borg-jobs-never-reach-wb-so-the-run-is-rebuilt-offline-from-the-datatable).

### Identity comes from the registry on tpu, from a frozen config on npu

See [knowledge/infrastructure/wandb-upload.md §Identity comes from the registry on tpu, from a frozen config on npu](../knowledge/infrastructure/wandb-upload.md#identity-comes-from-the-registry-on-tpu-from-a-frozen-config-on-npu).

### XManager is the completion authority, never the registry status

See [knowledge/infrastructure/wandb-upload.md §XManager is the completion authority, never the registry status](../knowledge/infrastructure/wandb-upload.md#xmanager-is-the-completion-authority-never-the-registry-status).

### Curves come from the datatable; images from the job's CNS `viz/`

See [knowledge/infrastructure/wandb-upload.md §Curves come from the datatable; images from the job's CNS `viz/`](../knowledge/infrastructure/wandb-upload.md#curves-come-from-the-datatable-images-from-the-jobs-cns-viz).

### A re-upload replaces the run under a new id

See [knowledge/infrastructure/wandb-upload.md §A re-upload replaces the run under a new id](../knowledge/infrastructure/wandb-upload.md#a-re-upload-replaces-the-run-under-a-new-id).

### The first tick baselines the board

See [knowledge/infrastructure/wandb-upload.md §The first tick baselines the board](../knowledge/infrastructure/wandb-upload.md#the-first-tick-baselines-the-board).

### Multi-XID runs automatically stitch their entire lineage chain

See [knowledge/infrastructure/wandb-upload.md §Multi-XID runs automatically stitch their entire lineage chain](../knowledge/infrastructure/wandb-upload.md#multi-xid-runs-automatically-stitch-their-entire-lineage-chain).

### Chapter 2 — Using It

See [wandb-upload skill §Chapter 1 — Using It](../harness/skills/wandb-upload/SKILL.md#chapter-1--using-it).

### Prerequisite: the config must expose the unified `wandb` block

See [wandb-upload skill §Prerequisite: the config must expose the unified `wandb` block](../harness/skills/wandb-upload/SKILL.md#prerequisite-the-config-must-expose-the-unified-wandb-block).

### Upload or repair one job now

See [wandb-upload skill §Upload or repair one job now](../harness/skills/wandb-upload/SKILL.md#upload-or-repair-one-job-now).

### Check the daemon — never assume an upload happened

See [wandb-upload skill §Check the daemon — never assume an upload happened](../harness/skills/wandb-upload/SKILL.md#check-the-daemon--never-assume-an-upload-happened).

### Re-upload after the daemon already handled a job

See [wandb-upload skill §Re-upload after the daemon already handled a job](../harness/skills/wandb-upload/SKILL.md#re-upload-after-the-daemon-already-handled-a-job).

### Chapter 3 — Bugs And Findings

See [wandb-upload skill §Chapter 2 — Bugs And Findings](../harness/skills/wandb-upload/SKILL.md#chapter-2--bugs-and-findings).
