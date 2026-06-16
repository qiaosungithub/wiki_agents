# Xibo Monitor Overview

Use this guide for the architecture and shared invariants of the SQA monitor and
external xibo TPU manager. For detailed queue scheduling rules, read
`xibo_queue.md`. For resume/rerun and checkpoint-source behavior, read
`xibo_resume.md`. For user-facing TPU commands, read `tpu.md`.

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

## What Lives Where

| Topic | File |
|---|---|
| User-facing TPU commands, `tou`, `detect_zombie`, stale holder diagnosis | `tpu.md` |
| Queue entries, `qsqa`, TPU selection, `tou` refresh, alias cleanup | `xibo_queue.md` |
| Resume/rerun state, checkpoint-source selection, failure markers | `xibo_resume.md` |
| VLM checkpoint and dataloader details that affect monitor decisions | `vlm_checkpointing.md` |
| Cleanup of stagedirs, local disk, and monitor temp dirs | `storage_cleanup.md` |

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

## ka Spreadsheet Authority

Do not use the ka spreadsheet as an authoritative live TPU status source for
automatic scheduling. Its `running/free/reserved` state can lag behind real TPU
usage.

For SQA monitor decisions, prefer these signals:

- `tou`/`wrap_master.py` output for live TPU visibility, zone, IDLE/BUSY, and
  holder users.
- `/kmh-nfs-ssd-us-mount/code/qiao/tpu_lock` reservation files via xibo
  `check_reserved_user()` / `zhan()` as the fast mutual-exclusion signal.
- xibo `data.json` for alias mapping, known TPU lists, active tmux windows, and
  persisted job metadata such as `spreadsheet_notes`.
- `queue.json` for local SQA queue state.

As of 2026-06-12, the active xibo script checkout has its ka sheet interface
disabled:

- `utils/sheet.py` no longer imports `gspread` or calls Google Sheet APIs.
- `read_sheet_info()` / `get_tpu_info_sheet()` synthesize spreadsheet-shaped
  rows from local `data.json`.
- `write_sheet_info()`, `set_spreadsheet_notes()`, `add_spreadsheet_notes()`,
  `release_tpu()`, and `write_tpu_usage_to_sheet()` are compatibility no-ops.
- `logger.register_tpu_and_write_spreadsheet()` still keeps the historical
  function name, but only registers the TPU in local `data.json`.

Old command names such as `tpu gtis`, `tpu find`, and `tpu uss` may still
exist, but they no longer query or update the ka sheet. Treat their status
output as local registry/debug information only, not live scheduling truth.
