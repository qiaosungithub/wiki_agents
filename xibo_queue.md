# Xibo Queue And TPU Selection

Use this guide when editing or diagnosing SQA `MONITOR.py` queue dispatch, TPU
selection, `tou` refresh behavior, monitor worker launch, and alias hygiene.
Read `xibo_monitor.md` first for active paths and locking context.

## Queue Semantics

- Queue jobs are consumed only by `USER == "sqa"` in local `MONITOR.py`.
- Resume work runs before queue work. Queue priority only orders queued jobs after
  resume handling finishes for the loop.
- Queue entries may include integer `priority` and `wandb_notes`.
- Queue `wandb_notes` are scheduling metadata, not only human-readable text.
  Before queueing, inspect the source/original working directory's
  `wandb_notes` and preserve the cost-class tokens that the monitor uses for
  TPU selection. Current low-cost tokens include `jit`, `MAE-B`, `unify-base`,
  and `llava-1.5 reproduction`; `gpt-b`/`deit` trigger the small-card rule.
  Missing these tokens makes the job look high-cost, so queue will wait for
  `v6e-64` or `v5/v5p-128` even if the run is eval-only or has
  `preferred_type=v5p-64`.
- The user-facing helper is `qsqa` from `/home/sqa/.bash_aliases`. It stages the
  current directory, runs `tpu set-cur`, then calls local `MONITOR.py queue`.
  Current default usage is plain `qsqa`: it auto-picks the first free xibo
  working-dir id in `2..99`, stages the current checkout there, and queues it.
  If all ids `<100` are occupied it prints `没空的了` and exits.
  Manual ids are still supported as `qsqa <dir>` or `qsqa dir=<dir>`.
  Priority should be passed explicitly as `qsqa priority=10` or `qsqa p=10`;
  bare integer arguments after a manual dir are kept as a compatibility
  shortcut, for example `qsqa 37 10`.
- Queue/staging dir numbers must stay in xibo's accepted range `1..100`.
  Do not use `101`, `102`, etc.; `tpu set-cur` rejects those, leaving unusable
  queue entries.
- Missing `priority` and `wandb_notes` are lazily backfilled for old
  pending/running queue entries.
- `preferred_zone` exists in schema but is not a current workflow dependency.
- Queue dispatch is consumed only after external `tpu run` output shows a tmux
  job was created. Later `[FAIL]` lines from sheet/alias bookkeeping must not
  requeue the job.
- A return code of 0 is not enough: external xibo can print
  `TPU ... is reserved by <user>` and `Quiting...` with return code 0. Without a
  tmux creation signal, the queue entry must remain pending.
- Before queue creates a job, `MONITOR.py` registers the real TPU name as a
  self-alias when needed, runs `zhan` and `mount-disk` on that full name, treats
  `[FAIL]`/error text as failure, SSHes to all TPU workers, and requires
  `python -c "import jax"` to print `JAX_OK`.
- `tpu mount-disk` must not trust `/home/sqa/.disk_mounted` alone. Require both
  the marker and `mountpoint -q /kmh-nfs-ssd-us-mount`. The monitor's `tmd`
  wrapper verifies the mount on all workers and retries with `--force` once.
- For xibo CLI, put `--force` after the TPU/alias:
  `tpu mount-disk <name> --force`.

## TPU Selection And Occupancy

- Queue selection tries non-Asia candidates before `asia-northeast1-b`.
- From-scratch queue jobs must use exact cost classes, not "any larger card":
  low-cost jobs use `v6e-32` or `v5/v5p-64`; high-cost jobs use `v6e-64` or
  `v5/v5p-128`; GPT-B/DeiT jobs use `v6e<=16` or `v5/v5p<=32`.
- A queue `preferred_type` is only a preference inside allowed classes.
- Jobs whose notes contain `llava-1.5 reproduction` are low-cost but v5-only:
  from-scratch launches use exactly `v5/v5p-64` and must not use v6/v6e.
- Jobs whose notes contain `laion-400m` have a data-locality hard constraint:
  queue launch, resume, rerun, and `resume_next_round` old-card reuse may only
  use `asia-northeast1-b`, because the LAION-400M data is only present there.
- TPU selection must not trust `tou`/`wrap_master.py` IDLE alone. Newly-created
  jobs can look IDLE before worker-side processes appear.
- Before queue or resume uses an idle TPU, check external `data.json`, local tmux
  windows, and a remote occupancy probe. TPUs with existing running windows or
  false-positive error windows are occupied.
- The remote occupancy probe checks TPU device holders (`/dev/vfio/*` or
  `/dev/accel0`) and then a narrow xibo training command signature:
  `python main.py --workdir=/kmh-nfs-ssd-us-mount/logs/...`.
- If the remote probe times out but partial stdout contains matching processes,
  classify as `busy`, not `unknown`.
- Central reserve locks live under `/kmh-nfs-ssd-us-mount/code/qiao/tpu_lock`,
  keyed by exact TPU lease name with a 30-minute lifetime. They are useful for
  same-name races but do not prove a physical worker is free because different
  lease names can point to the same VM.
- If `tou` cache is stale, do not continue selecting TPUs from it. Restart
  `yizhitou`, clear local in-progress marker for the current window, and let the
  next monitor loop retry.

## `tou` / `yizhitou` Refresh Flow

- `tou` is backed by the `yizhitou` tmux session, which refreshes
  `wrap_master.py` cache.
- `/home/sqa/.bashrc` `yizhitou` runs local `run_yizhitou_loop.sh`: each
  successful `tou --cache false` writes `/tmp/yizhitou_refresh_sqa.event`, then
  sleeps 60 seconds.
- `MONITOR.py` waits on that event file between loops. If refresh happens while a
  loop is running, the next loop starts immediately after the current loop.
- Watchdog fallback starts a loop after `MONITOR_TOU_EVENT_TIMEOUT_SECONDS`
  (default 900 seconds) if the event is missing.
- `MONITOR.py` parses reported cache age with a soft/hard split. Ages above
  `TOU_SOFT_CACHE_AGE_SECONDS` (default 120 seconds) are warnings if a fresh
  `wrap_master.py --cache false` audit is already running; selection can
  continue because launch workers still re-check reservations and environment.
  Ages above `TOU_MAX_CACHE_AGE_SECONDS` (default 300 seconds), or soft-stale
  ages with no fresh audit running, abort the loop and restart/wait for
  `yizhitou`.
- If cache is stale but a `wrap_master.py --cache false` refresh process is
  already running, do not kill it.
- Since 2026-06-12, queue and resume launch work is non-blocking. The monitor
  picks TPUs from one fresh `tou` snapshot, marks queue entries running or
  windows in-progress, and launches detached `_queue-worker` / `_resume-worker`
  subprocesses to run `ftmd`, JAX import checks, and `tpu run/resume/rerun`.
  Workers update `queue.json` / `sqa.json` under local file locks when they
  succeed or fail. Each worker uses a small copied `CLOUDSDK_CONFIG` under
  `/tmp/tpu_monitor_gcloud_configs/...` to avoid gcloud sqlite lock races.
- Important 2026-06-13 race fix: non-blocking workers must not share or mutate
  monitor-style tmp aliases such as `v5p-64-tmp5`. A bad loop launched several
  workers that all used the same tmp alias through `tpu fang`. The active
  monitor now registers each chosen real TPU as a self-alias
  `alias == kmh-tpuvm-...` under xibo's `data` lock, then passes that full TPU
  name to `tmd`, `tpu run`, `tpu resume`, or `tpu rerun`. Do not reintroduce
  `fang` in queue/deleted-resume launch paths.

## Alias Hygiene

- `audit_duplicate_aliases.py` is read-only and prints TPU lease names with
  multiple aliases. Groups with more than two aliases or self-aliases are
  `DIRTY` and can make `tpu fang` fail.
- `clean_duplicate_aliases.py` is write-capable, dry-run by default. `--apply`
  uses external xibo `data.json` lock and writes a backup under
  `logs/alias_cleanup/`.
- Cleanup keeps one monitor-style tmp alias pointing at the real TPU, retargets
  other monitor-style tmp aliases to dummy names ending `-do-not-exist`, deletes
  duplicate non-script aliases, and deduplicates `all_tpus`, legacy `zone_tpus`,
  `pre_info.spot`, and `pre_info.preemptible`.
- Default monitor-loop mode runs `clean_duplicate_aliases.py --apply --no-wait-lock`
  once before loop 1 as loop-0 hygiene. Queue subcommands do not trigger it.
  `MONITOR_SKIP_ALIAS_CLEANUP=1` is for debugging only.
- Since 2026-06-13, normal queue/deleted-resume scheduling does not allocate
  tmp aliases at all. The monitor self-registers real TPU names and periodically
  removes stale self-alias registrations every 20 loops when a fresh enough
  `tou` snapshot shows the TPU is gone and xibo/tmux/queue state has no active
  job on it. This cleanup only touches `alias == full_tpu_name`; human aliases
  and legacy tmp aliases are left to `clean_duplicate_aliases.py`.
- The same stale self-alias cleanup also removes only this monitor user's local
  reservation locks matching `sqa_<full_tpu_name>_*` after the TPU has already
  passed the stale/protected-set checks. Do not delete other users' lock files
  from monitor cleanup.
