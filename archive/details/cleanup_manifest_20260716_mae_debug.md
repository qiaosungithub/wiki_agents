# MAE debug checkout cleanup — 2026-07-16

User-authorized cleanup recorded and verified at 2026-07-16 02:41:45 UTC. This manifest
covers only top-level debug/ablation directories created during the MAE-L loss
and stage-transition investigation. Infra staging snapshots, run logs,
checkpoints, primary checkouts, and all Git branches/commits were excluded.

## Removed directories

| Path under `/kmh-nfs-ssd-us-mount/code/qiao/work` | Bytes before removal | Recovery / rationale |
|---|---:|---|
| `PaliGemma-fix-v2-stage3` | 2,484,200 | Tracked source remains on `codex/mae-fix-v2-stage3` at `4ca9fdd`; superseded v2 monitor artifacts under untracked `ops/` (87,405 bytes) were intentionally discarded. |
| `PaliGemma-fix-v4-s3-lr2e6` | 2,354,033 | Branch `codex/mae-fix-v4-s3-lr2e6` at `3d73e4e`; associated job was killed after reproducing the spike. |
| `PaliGemma-fix-v4-s3-lr1e6` | 2,354,081 | Branch `codex/mae-fix-v4-s3-lr1e6` at `ee76522`; superseded configuration. |
| `PaliGemma-fix-v4-s3-wholelm-warmup0` | 2,385,502 | Branch `codex/mae-fix-v4-s3-wholelm-warmup0` at `a21ca77`; associated job was killed and the baseline checkout now carries the intended zero-start/whole-LM configuration. |
| `PaliGemma-spike-debug-instrument` | 2,456,421 | Branch `codex/mae-spike-debug-instrument` at `a72cf67`; its instrumentation is an ancestor of the retained, more complete `PaliGemma-spike-debug-wd0-clip5` checkout. |
| `PaliGemma-spike-debug-lr5e7` | 2,385,735 | Branch `codex/mae-spike-debug-lr5e7` at `ca43e39`; completed/killed ablation. |
| `PaliGemma-fix-v4-s3-s2lr5e5` | 1,315,289 | Non-Git scratch copy. Its code/config matches retained `PaliGemma-fix-v4-s3-lowerparent-warmup0` except for `wandb_notes`; old immutable snapshot remains at `staging/sqa/260715095241-0c7a83-nogit-code`. |
| `.ruff_cache` | 8,388 | Generated formatter/linter cache. |

Total recorded size: 15,743,649 bytes.

## Retained experiment/debug checkouts

- `PaliGemma-fix-v4-s2-elated-warmup0` (`adc3be7`): source provenance for live job `1d3ffa4c`.
- `PaliGemma-fix-v4-s2-lr2p5e5` (`26140ac`): source provenance for pending-resume job `5a6bed50`.
- `PaliGemma-fix-v4-s3-lowerparent-warmup0` (`62308cb`): source provenance for pending-resume job `5a057ad5`.
- `PaliGemma-spike-debug-wd0-clip5` (`be15b3d`): most complete reusable per-block/output/gradient norm diagnostics.

The primary `PaliGemma-baseline`, `beifen-Paligemma`, `tpu_scripts`, all live
job stage directories, logs, and checkpoint paths were deliberately untouched.

## Infra records cleaned

After an `infra clean --dry-run` preview, the following ten terminal debug
job records were forgotten with `infra clean --yes`:

- `0937b241` — killed fix-v2/fix-v4 detached-center Stage 3 attempt
- `0463e53f` — cancelled LM-1e-6 Stage 3 attempt
- `108b3898` — killed 5e-7 spike-debug attempt
- `15207871` — cancelled superseded lower-parent scratch attempt
- `3e052656` — killed 2e-6 Stage 3 spike reproduction
- `3fb5daf2` — killed whole-LM warmup0 spike reproduction
- `af613315` — killed wd0/clip5 mask-aware diagnostic attempt
- `f2473cf8` — cancelled earlier wd0/clip5 diagnostic attempt
- `223cc976` — cancelled original exact-Stage-2 queue record, superseded by live chain `1d3ffa4c`
- `04581d0f` — cancelled original lower-parent Stage-3 queue record, superseded by pending chain `5a057ad5`

`infra clean` removed only terminal job records and their infra worker logs. NFS
training logs, staging snapshots, W&B records, and GCS checkpoints were not
deleted. The active/pending jobs `1d3ffa4c`, `5a057ad5`, and `5a6bed50`, plus
their shared immutable stage snapshots, were retained and verified after cleanup.
