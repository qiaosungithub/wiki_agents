# The Workstation: `sqa-large` (Migrated From `sqa` On 2026-09-08)

**The Cloudtop is `sqa-large.c.googlers.com`** (n2d-custom-64-122880: 64 AMD
vCPUs, 120 GiB RAM, 2 TiB SSD, us-east4-b, created via `ctop migrate`, trip
13169052229). `sqa.c.googlers.com` (24 vCPU / 96 GiB / 1 TiB) is the machine it
replaced. Amply, the `tpu` CLI daemons, the submission workers and the crontab
now run on `sqa-large`; the agent web app and its public tunnel still run on
`sqa` until they are cut over (last section). The live system outranks this
page: `creation_status.json` in the migration folder below is the running
status record.

## Reaching It

`gcert`, then `ssh sqa-large.c.googlers.com`. There is nothing to set up: the
corp `/etc/ssh/ssh_config` routes `*.c.googlers.com` through
`corp-ssh-helper` with the LOAS certificate, and the host key is signed by the
corp CA (a `BatchMode=yes` connection from `sqa` worked on the first try). An
alias in a laptop's `~/.ssh/config` is `Host sqa-large` /
`HostName sqa-large.c.googlers.com`. Desktop: http://cloudtop/crd/sqa-large .

Outbound from the new machine already works because `~/.ssh` was copied whole
(`id_ed25519` for GitHub, `google_compute_engine` for the viscam VMs, the
`lyy_*` deploy keys, `config`). Run `gcert` once after the first login; the
migration tool cannot do that for you, and blaze, CitC, `ctop` and internal
ssh all need it. `gcloud auth list` shows the copied accounts; keep passing
`--account=qiaos@google.com` as before.

## What Runs Where

| Thing | `sqa-large` | `sqa` |
|---|---|---|
| Amply: `amply-localdb.service` + `amply-ux.service` | running; gateway URL in `~/.amply/dashboard_url` (port 44127 on 2026-09-08; it picks its own) | stopped |
| crontab (19 active lines after the 2026-09-10 monitor retirement; was 44) | installed | removed (copies under `~/migrate_backup_20260907_175207/system/`) |
| tmux `npu-daemon`, `tpu-dispatch`, `tpu-reroute`, `tpu-build-worker`, `npu-build-worker` | running, one `route_check` per role | killed |
| `tpu_utils` binaries | `/usr/local/google/_blaze_qiaos/c99224759024385897e236938d1772c2_buildrabbit/...` (+ compat symlink `bb5e05891304127daf0b480f4298d971_buildrabbit` for `tpu_reroute_loop_v17.sh`, which hardcodes that root) | old roots, no longer used |
| `jetski-hub.service` | **kept inactive on purpose** (see below) | running |
| agent web (`~/work/agent-web-gemini/run.sh`, node, cloudflared tunnel, `jetski-ls` / `webchat-tunnel` tmux) | not yet | running, hosts every web chat session |
| Custom user units (12) | released via the marker `~/.migration_target_before_copy_20260907/allow_custom_services`; without it every unit stays inactive by a `ConditionPathExists` drop-in | as before |

`~/.bashrc` is per machine. The copy on `sqa-large` starts with a 3-line
`cloudtop-disk-tmp` block that points `TMPDIR` at `~/tmp` (also in
`~/.config/environment.d/90-cloudtop-disk-tmp.conf` and the systemd user
environment), because `/tmp` is a RAM disk. Every full home sync overwrites
that file with the source copy; re-run
`~/migrate_backup_20260907_175207/configure_target_tmp.py` on the target
afterwards (idempotent, self-verifying). `/usr/local/google/_blaze_qiaos` and
`/usr/local/google/tmp` are outside home and were not migrated: rebuild blaze
targets (`tpu_utils` took 54 s from the Forge cache), and treat old build logs
under `/usr/local/google/tmp` on `sqa` as the only copy.

## How The Home Copy Was Done, And How To Re-Sync

Everything is in `~/migrate_backup_20260907_175207/` on both machines:
`README.md` (narrative), `creation_status.json` (machine-readable status and
remaining steps), `system/` (crontab copies, unit files, pre-cutover process
and tmux inventories), `cutover_final_sync.sh` (the re-sync command, detached
from the terminal, log to `final_sync_<ts>.log`, then re-applies the TMPDIR
helper). The copy itself is `ctop migrate --skip_create --skip_pkg_copy`, which
is `rsync -ahHz --no-i-r` of `~/` with `.cache` (snapshotted to
`.cache_snapshot`), `chrome-remote-desktop/`, Chrome `Singleton*`, Endpoint
Verification, DriveFileStream, Trash and `chromiumos/chroot/` excluded, no
`--delete`; the per-file log lands on the TARGET at `~/migration.log`, there is
no local log. 525 GB allocated / 9.6M entries took about 4.5 h of transfer at
25-45 MB/s plus ~4 min per pass to build the file list; a re-sync pass over an
unchanged tree is about 10 min.

Two things bit us:

- **The first copy died with the agent session that launched it.** `ctop`
  was a child of a Codex process; when that process exited, its pty closed and
  `ctop`, rsync and the ssh mux all got SIGHUP at 36%. rsync has no `--delete`
  and skips already-copied files by size and mtime, so the restart cost only
  the rescan, but anything that runs for hours goes in a tmux session, never
  as a child of an agent.
- **Exit code 24 is not a failure.** Files that live writers delete between
  list build and transfer (`.amply/localdb`, `.claude/backups`, git reftables,
  `work/.raft_stage`) make rsync return 24, and `ctop` then asks "retry data
  copy (Y/n)?" on every pass, forever. Answer n after one refresh pass and do
  `ctop`'s last step yourself on the target (`rm -rf ~/.cache && mv
  ~/.cache_snapshot ~/.cache`). A quiesced source still returns 24 because the
  Claude session driving the sync writes its own backups.

## Quiescing The Source For The Final Sync

What to stop on the old machine, in this order, and what to leave alone. Save
the crontab first (`crontab -l > file`); on the target install it with
`cat file | crontab -` -- passing the filename to `crontab` on `sqa-large`
mangled it (`...T1421Z.txt` became `...T1421`, "No such file").

1. `crontab -r`. Cron-spawned loops keep running after this (they are
   `setsid`/`flock` wrappers with parent 1): `queue_sentinel_v49_loop`,
   `tpu_check_daemon`, chipwatch `watchloop`, `srcfsd_wedge_sentinel`,
   `credit_audit_sentinel`, `tpu_congestion_sentinel`. List them, then kill by
   PID.
2. `systemctl --user stop amply-ux amply-localdb` and the
   `overnight-repair-report` timer. `amply-ux` reports `failed` (exit 143 on
   SIGTERM); that is stopped.
3. Kill the worker tmux sessions. The `route_check` binaries inside them
   survive the session kill; SIGTERM them by PID. They shut down cleanly: both
   queue files were rewritten before exit, and a `tpu queue` that the dispatch
   worker had in flight finished first (its XID was already in the queue
   file). Wait for an in-flight `tpu queue` child before killing the dispatch
   worker.
4. Leave `jetski-hub.service`, `agent-web-gemini`, cloudflared and every
   `claude` process alone: they are the web chat, including the session doing
   the migration.

**A remote `pkill -f <pattern>` kills the shell running it.** The pattern is on
that `bash -c` command line too, so nothing after the `pkill` runs and the
command prints nothing. Kill by PID, or match on something the command line
itself does not contain.

## Jetski Hub Starts The Web App; Start It On One Machine Only

**`jetski-hub.service` is the parent of the whole agent web stack.** Its
`sar.server` runs `~/work/agent-web-gemini/run.sh`, which starts node, esbuild,
the `jetski-ls` tmux session and `cloudflared ... cloudflared-named.yml tunnel
run`. The tunnel is one named tunnel (94201537-...) serving `gemini.kaiming.me`
and `lyy.kaiming.me`; two connectors on two machines split the traffic, and the
sessions live on only one of them. Starting the hub on `sqa-large` during the
cutover did exactly that and had to be undone.

Two consequences. Stopping the hub stops the web app and the tunnel. And a tmux
server that was FIRST started from inside the hub's cgroup (run.sh creates
`jetski-ls`) belongs to `jetski-hub.service`: `systemctl --user stop
jetski-hub` killed it together with every session later attached to that
server, including the five worker sessions. Start long-lived tmux servers from
an ssh or login session, and check `/proc/<tmux pid>/cgroup` if in doubt. Two
`route_check --worker` processes outlived their sessions and had to be killed
by PID before the recreated workers double-claimed the queues.

## Cutting Over The Web App (Not Done Yet)

On `sqa`: stop `jetski-hub.service`, `run.sh`, node, esbuild and cloudflared
(by PID), and the `jetski-ls` / `webchat-tunnel` sessions. Then on
`sqa-large`: `systemctl --user start jetski-hub.service`; it launches the rest.
DNS needs no change (same tunnel id). Every web chat session ends when the old
side stops, so do it from a real terminal, not from a web session. Retire `sqa`
only after the web app is verified on `sqa-large`; missing packages are listed
in `~/migrate_backup_20260907_175207/evidence/package_diff.json`.
