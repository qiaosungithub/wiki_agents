# Xibo Monitor And Queue Internals

Use this guide when editing or diagnosing the local `MONITOR.py` flow, xibo TPU
manager state, queue dispatch, resume/rerun behavior, remote Linux users, or TPU
alias hygiene. For basic user-facing TPU operations, read `tpu.md` first.

Project-local source snapshots are preserved verbatim in
`project_agents_archive.md`. Legacy sandbox notes are preserved verbatim in
`external_memory_archive.md`.

## Active Code Paths

- Local monitor checkout:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager`.
- External xibo backend:
  `/home/jzc/zhichengjiang/working/xibo_tpu_manager/`.
- Local monitor `MONITOR.py` intentionally shells out to the external backend:
  `python /home/jzc/zhichengjiang/working/xibo_tpu_manager/tpu.py`.
- Local queue file:
  `/kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager/queue.json`.
  This is separate from the external xibo checkout's queue files.
- `find_saving_window.py` is active. It is used by `MONITOR.py` to find a usable
  checkpoint source. Pass the current user because numeric window ids are only
  unique within a tmux/user namespace.
- `see_log.py` backs the `/home/sqa/.bash_aliases` helper `cl <window_id>`.
- The copied sandbox
  `/kmh-nfs-ssd-us-mount/code/qiao/work/xibo_tpu_manager_linux_user_sandbox_20260601`
  was applied to the external checkout on 2026-06-10 for selected code/docs only.
  Runtime state files such as `data.json`, `lock.json`, `queue.json`, and
  `legacy.json` were intentionally not copied.

## Queue Semantics

- Queue jobs are consumed only by `USER == "sqa"` in local `MONITOR.py`.
- Resume work runs before queue work. Queue priority only orders queued jobs after
  resume handling finishes for the loop.
- Queue entries may include integer `priority` and `wandb_notes`.
- The user-facing helper is `qsqa` from `/home/sqa/.bash_aliases`. It stages the
  current directory, runs `tpu set-cur`, then calls local `MONITOR.py queue`.
  Supported forms: `qsqa <dir>`, `qsqa <dir> 10`,
  `qsqa <dir> priority=10`, and `qsqa <dir> p=10`.
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
- Before queue creates a job, `MONITOR.py` runs `zhan/fang/mount-disk`, treats
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
- `MONITOR.py` parses reported cache age and treats ages above
  `TOU_MAX_CACHE_AGE_SECONDS` (currently 120 seconds) as stale.
- If cache is stale but a `wrap_master.py --cache false` refresh process is
  already running, do not kill it; abort the current monitor loop and wait for
  the refresh event.

## Resume State And Invariants

- `sqa.json` is monitor local memory. `running` is an in-progress lock;
  `finished` means the window has already been handled by monitor.
- Active jobs are leaf jobs whose tmux windows still exist in the `sqa` session
  and have not been superseded by `extra_msgs.child`.
- Old `data.json` records can remain `error` or stale `running` after tmux
  windows disappear; those are history, not current work.
- Immediately diagnose any active `Error` leaf enough to classify it. No-card,
  TPU preempt, and deleted-card failures are operational churn; code, config,
  checkpoint, environment, and data-loader errors are abnormal.
- A resume/rerun attempt is consumed once external output shows a tmux job was
  created. The triggering failed window must then move to local `finished`, even
  if later sheet/alias bookkeeping prints `[FAIL]`.
- Do not add retry cooldowns to solve duplicate resumes. Desired behavior is to
  retry still-failed jobs on the next loop. The key invariant is that source
  windows are marked finished once a new child window is created.
- If an error window already has a recorded child, or its checkpoint source has a
  newer child than this window, treat it as stale and mark it handled locally.
- When checking whether a checkpoint source's child supersedes an error window,
  first walk the error window's `extra_msgs.father` chain. A child on the father
  chain is an ancestor path, not a competing newer child.

## Checkpoint Source Selection

- `find_saving_window.py` must not treat a bare `Saving checkpoint...` line as
  usable. A checkpoint is usable only after a later `saved to` line.
- If a latest `Saving` step is newer than the latest `saved to` step, remove that
  `checkpoint_<step>` candidate before returning the source.
- If stderr says `no complete checkpoint found anywhere in chain; reached root
  window N`, treat it as action `rerun` for root `N`.
- After walking a father chain, `find_saving_window.py` also scans same logical
  job using `(job_dir_id, spreadsheet_notes/job_tags)` and picks the highest
  complete checkpoint if newer than the father-chain checkpoint.
- The external backend should strip inherited resume-only overrides
  (`--config.load_from`, `--config.wandb_resume_id`, `--config.stage`) before
  composing resume/rerun commands.

## Resume/Rerun TPU Choice

- Training-phase checkpoint resume is exact-type: if action is `resume` and the
  job is still training, choose only the same TPU type as the original job,
  although another allowed zone/region with the same type is okay.
- Eval-phase resume is topology-flexible. If the failed/root job is `eval_only`
  or the log shows final eval has started, monitor may resume/rerun on another
  type or larger TPU, still respecting allowed zones and hard constraints.
- Checkpoint-free training `rerun` may choose a new type by exact cost class.
  `--same-type-only` forces checkpoint-free reruns to keep original type.
- `resume_next_round` buffer resumes must run the remote occupancy probe before
  directly reusing the old TPU. If old TPU is remotely busy, remove the buffer
  entry and fall back to normal different-card selection.
- If `tou` omits a TPU whose GCP state is `DELETING`, classify it as
  deleted/missing, not ambiguous. Deleted-card fallback should proceed.

## Resume-Needed Error Markers

Treat these as resume-needed infra or startup failures rather than permanent code
bugs when consistent with logs/state:

- `Retrying: SSH command error`
- `Unable to initialize backend 'tpu': ABORTED`
- `Fatal Python error: Aborted`
- `JAX distributed service detected fatal errors`
- `CoordinationService/Heartbeat` with `DEADLINE_EXCEEDED`
- `python: can't open file '/home/sqa/main.py'`
- `cp: cannot stat ... staging/sqa`
- `ModuleNotFoundError: No module named 'jax'`

For random JAX aborts, `tou` may still report the old TPU busy under `sqa`
because dead workers have not cleared. If busy users are only current user and
`data.json` plus tmux show no other active window, monitor may resume directly on
the old TPU.

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

## Remote Linux User Mode

The xibo sandbox adapts logical xibo users in `data.json` to separate Linux
accounts on TPU VMs.

- New jobs default `remote_linux_user` to the xibo user name.
- Legacy jobs without `extra_msgs.remote_linux_user` are treated as remote `sqa`.
- `run`, `run_job_on_tpu`, `resume`, and `rerun` store the Linux user in
  `job.extra_msgs.remote_linux_user`.
- Resume/rerun inherit the parent Linux user unless explicitly overridden with
  `remote_user=`, `linux_user=`, `remote_linux_user=`, `linux-user=`, or
  `remote-linux-user=`.
- Launch commands export `TPU_REMOTE_USER=<linux_user>` before sourcing
  `staging.sh`. Repo `staging.sh` / `run_remote.sh` must SSH to that user.
- `mount_disk(..., remote_user=...)` is remote-user aware. NFS mount is global,
  but Python packages, W&B login, and `.disk_mounted` markers are per user under
  `/home/<linux_user>`.
- `mount_disk` must not remove other users' home directories.
- `ensure_remote_linux_user(...)` creates the Linux account on all workers, adds
  passwordless sudo, copies available SSH authorized keys, and verifies `whoami`
  plus `sudo -n true`.
- Scoped kills are default. `--all-users` / `--all-remote-users` is the only
  explicit all-user kill mode and the only mode that cleans global `/tmp` TPU
  state.
- `tpu kill-remote <tpu>` remains legacy all-user kill. Use
  `tpu kill-remote <tpu> remote_user=<linux_user>` for scoped kill.
- Do not kill PPIDs from `ps`; many workers have PPID 1. Kill only matching
  process PIDs and TPU device-holder PIDs.

## Implementation Pitfalls From Sandbox Notes

- `tmux display-message -p '#S:#I'` can report the active window, not the
  intended current pane's window. Use the pane id target:
  `pane_id=$TMUX_PANE; tmux display-message -p -t "$pane_id" '#S:#I'`.
- A function that acquires a lock must not exit while still holding that lock,
  or monitor/queue code can deadlock.
- Resume work should happen in the staged directory because the source checkout
  may have changed after the original job launched.
- For complex command argument passing, prefer positional arguments when that is
  what the existing xibo scripts expect.
- JSON and log parsing must be strict about type and case: `"3" != 3` and
  `"PREEMPTED" != "preempted"`.
- In f-strings, avoid using the same quote character inside expression braces as
  the surrounding string.
- `KeyboardInterrupt` is not caught by `except Exception`.
- `gcloud` can reconnect automatically. For SSH commands that should not keep a
  tmux pane alive, add `--ssh-flag="-n"`. When killing remote processes, also
  kill the parent if it restarts children.
- A remote crash may fail before writing useful text to `output.log`; absence of
  log output is not proof that the command never started.

## External Xibo Locking

In the xibo manager checkout, locks live in `lock.json` keyed by
`code`, `data`, `queue`, `legacy`, and `apply`, each shaped as
`{ status: bool, user: str|null }`.

- `utils/data_io.py::_mutate_lock_file` uses `fcntl.LOCK_EX` on `lock.json` for
  atomic compare-and-set.
- Once you take a lock, release it before returning, including exception paths.
- `KeyboardInterrupt` is not an `Exception`; catch it separately when holding a
  lock.
- For read-side/status commands (`check`, `ack`), prefer `read_data_if_unlocked()`
  and silently no-op if it returns `(None, False)`. Never block `tpu check` behind
  a writer.
- Lock helpers spin every 10s and give up after 30 minutes.
- To release a stuck lock manually: `tpu rl/unlock <code|data|queue|legacy|apply>`.

## Duplicate Window Incident

On 2026-05-14, repeated queue/resume windows were caused by success
misclassification: external `tpu run`/`resume` created a tmux window, then later
printed `[FAIL] get_zone_pre...` or sheet/alias bookkeeping errors. Correct
handling is based on creation signals such as `Successfully created job in tmux
window` or `run/resume/rerun job ... with new windows id N`; once seen, mark the
source/queue item consumed.
