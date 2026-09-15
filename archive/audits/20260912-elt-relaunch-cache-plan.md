# ELT relaunch from scratch with cached latents (2026-09-12)

Operator: rerun the previous ELT runs FROM SCRATCH (no resume) using the new
cached-latent code. "列出来之后直接跑就行，不需要停下问我" (list them, just run,
don't stop to ask). Prior context: cache switch + prefetch + remat flag are
implemented, CPU-validated (cachesmoke green), committed + pushed to ELT-sqa main
(commits 5fc98a9, 9809ea1).

## The 4 runs (from .elt_results/unroll_20260907/launch_plan.json, deduped)
| # | config (add _cache) | exp base name | arch | notes |
|---|---|---|---|---|
| 1 | prod_train_4n8l_cache | elt_baseline_4n8l | 4N x 8L | stock baseline |
| 2 | prod_train_1n32l_cache | elt_baseline_1n32l | 1N x 32L | unlooped baseline |
| 3 | prod_train_persite2_dw1_cache | elt_unroll_dw1_16n2l | 16N x 2L | per-site k=2, depth-weight poly1_late, reldist(distance) |
| 4 | prod_train_8n4l_persite4_dw1_cache | elt_unroll_dw1_8n4l | 8N x 4L | per-site k=4, depth-weight poly1_late |

- `_dw1` needs `_persite<k>`; `_reldist` grouping is baked by the config too.
- persite_conditioning/persite_input default True (load_config.py L1669) -> no
  extra flags needed; `_persiteK_dw1` bakes the arch + optimizer.
- All prior runs: power=v7-32, tier=PROD, archs fallback v7,v6p,v5p, 500k steps.
- Old RUNNING xids (online-encode, being replaced): 287282844 (4n8l),
  287340679 (1n32l), 287351065 (persite2 py314), 287315750 (8n4l py314).

## Deploy divergence (IMPORTANT)
ELT-sqa git (source of truth per operator) and the CitC build pkg
`//experimental/qiaos/elt_dit_pkg` have DIVERGED:
- deploy pkg has files git lacks: load_from_guard.py (+_test), *.bak_* scratch;
  its main_eqr.py imports load_from_guard + an eval-reroute heartbeat.
- deploy pkg's types.py is MISSING persite_loss_grouping (which git has and
  _reldist NEEDS).
- git main_eqr.py has eval_protocol import, eval_checkpoint_step flag,
  _elt_start_log_mirror (durable text log) that deploy lacks.
=> They are divergent lineages. The Sep-7 baselines launched from GIT commit
39b785c (an ancestor of my main). So the intended flow is: sync git checkout ->
CitC pkg -> build //...:main -> launch. Deploy git HEAD as the authoritative
build source; the deploy's extra eval-infra is irrelevant to from-scratch TRAIN.
Backed up the old deploy pkg to $AMPLY_ARTIFACT_DIR/elt_deploy_pkg_backup_*.

## Launch recipe (MEMORY-validated direct path, bypasses the fleet daemon)
cd <CitC>/experimental/qiaos/elt_dit_pkg   # CWD matters (config.sh CWD-relative)
xmanager launch xm_launcher.py -- \
  --config=<prod_train_..._cache> --tpu_type=v7-32 \
  --bucket=/cns/is-d/home/qiaos/eqr_data \
  --xm_resource_alloc=group:gdm-aux/brain-vasp-shared-user-xm \
  --exp_name=<name>_cache_20260912 --tier=PROD --noxm_monitor_on_launch
- xmanager is a bash FUNCTION -> invoke via `bash -lc '...'`.
- from scratch => NO --load_from / --restart_from.
- cbf cell tokens map to bucket is-d: yucbfiv,yucbful,yucbfwv,je. group8 alloc =
  gdm-aux/brain-vasp-shared-user-xm.
- verify TRUE running via CNS logdir mtime advancing (board RUNNING is unreliable):
  {bucket}/logs/elt-dit/xid_<XID>_<ts>_<exp_name>/ ; checkpoints/ appears.

## Status / next
[in progress] confirm launch driver + exact tpu/power flag; deploy git->pkg;
build :main; launch 4; verify step>0 reading cached latents; report XIDs.
Old online-encode runs: cancel after new ones confirmed launched (superseded).
