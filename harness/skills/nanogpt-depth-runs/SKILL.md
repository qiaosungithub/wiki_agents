---
name: nanogpt-depth-runs
description: Stage, launch, harvest, audit, resume, and log nanoGPT call/loss-diagonal (two-band Adam) runs, where one confirmed configuration is four seeds, one W&B group, and one sheet row.
---

# nanoGPT Call/Loss Diagonal Runs — Running Research Against This Line

This skill relies on
[the nanoGPT call/loss diagonal knowledge page](../../../knowledge/codebases/nanogpt-depth.md)
for the gradient contract, the two-band optimizer, the reference configuration,
what the metrics mean, and the findings so far, including the baseline gate that
comes before any treatment experiment.

## One configuration = four seeds = one W&B group = one row

**One confirmed configuration = four seeds = one W&B group = one sheet row.**
W&B entity `zhh24-massachusetts-institute-of-technology`, project
`nanogpt-depth`. The shared workbook is
`17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`. This line logs to its own
`nanoGPT (qiaos)` tab (call/loss diagonal), which is NOT being replaced. The separate looped-methods program (parcae / loopformer / ouro), and new
nanoGPT-setting work generally, default to the `looped nanogpt (cleaned 2)` tab of a
DIFFERENT workbook, `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20`
([knowledge/environment/result-workbooks.md §Which Tab](../../../knowledge/environment/result-workbooks.md#which-tab), which owns the routing rule and
governs the writes). Resolve any tab by title and
re-read its live header.

## Stage, launch, harvest, audit

**A PID or a result file alone is not completion; `audit_remote.py` is what
certifies a run.** `stage.py` creates a hash-verified immutable source snapshot.
`launch.py` records the exact commands, GPU / PID and output paths, and rejects
busy GPUs. `harvest.py` archives the exact manifest jobs. `audit_remote.py`
verifies successful exit, checkpoint-reload equality and online W&B history.

## Resuming and GPU hosts

**`LOAD_FROM` / `--resume` restores both band moments, the ordinary optimizer and
the batch RNG; never reuse an existing output for a cold run.** Resume derives w
from the absolute optimizer update. GPU hosts and zones come from the current
launch manifests, so recheck live occupancy before a launch; SSH with
`--ssh-flag=-oIdentityAgent=none` to bypass a stalled local SSH agent without
disturbing shared authentication services (see [gcp-gpu-ssh skill](../gcp-gpu-ssh/SKILL.md)).
