# Debugging A Slow Or Overloaded Workstation

Load, memory, swap, and the standing processes that eat them on the Cloudtop.
Read this when the box is slow, `tpu check` shows builds crawling, or VSCode-SSH
keeps dropping. Sibling of `workstation.md` (which owns the host's identity, what
runs where, and boot persistence); this page owns diagnosis and mitigation. The
live system outranks this page — re-measure before acting.

## Principle

**What takes this box down is almost never a running build; it is standing
consumers and orphaned scanners.** `sqa-large` has 64 vCPUs and 120 GiB RAM
(`workstation.md`), so a load average in the teens is only ~15-25% CPU — high
load here means many processes *blocked* (on FUSE, on the LLM, on I/O) or
*scanning*, not CPU saturation. Before blaming a build, enumerate the standing
consumers: idle blaze heaps, a leaking `srcfsd`, dozens of idle agent workers,
and orphaned `find`s all cost memory or FUSE bandwidth while doing nothing
useful.

**Swap sitting full is not the alarm; the paging RATE is.** A high `swap used`
with `si/so ≈ 0` is cold pages parked by a cache, harmless. Thrashing needs both
`si >= ~5 MB/s` (`vmstat`) and `load15 >= ~0.8/core`. Read the rate before you
reach for a kill.

## Triage: the first five reads

**Run these in order; each is FUSE-safe (only `/proc`, `free`, `ps`, `vmstat` —
never `stat`/`ls` on `/google/src`).** Stop as soon as one names the culprit.

| Step | Command | What it tells you |
|---|---|---|
| 1. pressure | `uptime; free -h` | load vs. 64 cores; RAM used and swap used |
| 2. cold-or-thrash | `vmstat 1 5` | `si/so` ≈ 0 → cold cache, do not kill; ≥ 5 MB/s → real thrash |
| 3. RSS by name | `ps -eo rss,comm \| awk 'NR>1{a[$2]+=$1}END{for(k in a)print a[k]/1024"MB",k}' \| sort -rn \| head` | which program owns the memory (usually `amply`, `srcfsd`, `blaze`) |
| 4. orphaned scanners | `ps -eo pid,ppid,etimes,cmd \| grep -E 'find /google/(src\|obj)' \| grep -v grep` | recursive `find`s on FUSE, orphaned to `systemd --user` (ppid = the user systemd) |
| 5. queue drainers | `pgrep -af 'route_check.*tpu_local_queue' \| grep -v npu` | must be exactly ONE `--dispatch_worker`; two drainers = churn |

## The recurring problems

**Most slowdowns on this box are one of these five; check them before inventing a
new cause.**

| Symptom | Cause | Fix |
|---|---|---|
| `tpu check` shows many QUEUED, few BUILD_REQUESTED; builds "stuck" 20-30 min; worker log floods `released slot, back to QUEUED` | TWO drainers on one tpu queue — the current `route_check --dispatch_worker` plus a legacy `route_check --worker` from an old tmux session — racing to claim each build | Keep only `--dispatch_worker`; kill the legacy `--worker`, its tmux session, and its restart loop. Design in `infra/router.md` §The Serial Build-Worker |
| load high, FUSE/staging slow, srcfs bandwidth contended | orphaned recursive `find` on `/google/src` (see below) | kill the orphans; do not scan FUSE recursively |
| RAM used tens of GB, many `amply worker` processes | idle agent sessions never reaped (each worker holds ~0.5-1.4 GB) | reap sessions idle ≥ 6 h (see below) |
| `srcfsd` RSS+swap tens of GB | `srcfsd` metadata/anon leak (NOT the content cache) | restart sentinel handles it (see below) |
| first build after idle very slow; memory tight | an idle blaze server was evicted and cold-respawns a multi-GB JVM | bound blaze heaps in `~/.blazerc`; see §Idle Blaze Heaps |

## Never Recursively Scan A FUSE Mount

**A recursive `find` on `/google/src` or `/google/obj` stats every entry as a
separate RPC, so it runs for tens of minutes and starves build staging of srcfs
bandwidth — and it outlives the shell that started it.** CitC and objfs are FUSE
mounts; walking them is thousands of round-trips, not a local disk scan. When the
agent or ssh session that launched the `find` ends, the process is reparented to
`systemd --user` (it shows `ppid` = the user-systemd pid, not `1`) and keeps
scanning for hours with nobody reading its output. Several such orphans
accumulating is a common, self-inflicted cause of a slow box.

**These are ad-hoc commands, not a daemon — no script in the tree emits them, so
there is nothing to "fix" except the habit.** To find a file in the source tree
use `code_search`, `grep`, or `glob`; for a distributed path use `fileutil ls` /
`fileutil find` scoped to a specific directory. If you truly must `find` under
`/google/src`, bound it (`-maxdepth`, a `timeout`) and never leave it running
past your session. Detect and clear existing orphans with step 4 above, then
`kill` them by PID (they are read-only scans; killing is safe).

**A guard shim is installed at `~/.tpu_bin/shims/find` (on `PATH` ahead of
`/usr/bin`), which refuses any `find` whose start path would descend into a FUSE
mount — `/`, `/google`, `/google/src`, `/google/obj` — and passes everything
else through.** Blocking bare `/` matters: `find / -path '*foo*'` reaches the
FUSE mounts by descent and is the exact runaway that spiked CPU for 18 min. It
fires in the agent bash tool, login shells (`bash -lic`), and interactive
shells; it inspects argv only (never stats a path). It does NOT catch a call by
absolute path (`/usr/bin/find`) or a `subprocess(['/usr/bin/find', ...])` that
bypasses `PATH` — but the orphans this prevents are all ad-hoc `find` typed at a
shell, so that is enough. Same
mechanism as the existing `blaze` / `hg` shims in that dir.

## Reaping Idle Amply Sessions

**When the box is under memory pressure, you may stop every `amply worker` whose
session has been idle ≥ 6 h, without asking first — this is a standing,
operator-approved mitigation.** Each idle agent worker holds ~0.5-1.4 GB; dozens
of them are the largest reclaimable chunk after `srcfsd`. Two hard exclusions:
never kill the worker serving **your own** session, and never kill a **cross-user
`remote-chat-ws`** session (a colleague's) — list those and ask the operator
first.

**Judge idle by the run's log and artifact mtime, never by process age or CPU
time.** An agent spends most of its life blocked waiting on the LLM, so both CPU
delta and wall-clock age read "idle" for a busy session and a dead one alike. The
truthful signal is the newest mtime of `~/.amply/logs/<run-id>.log` and
`~/.amply/artifacts/<run-id>/`, both on local disk (FUSE-safe).

Procedure (the `amply` CLI has no `list`/`stop`; sessions are worker processes,
children of `amply ux`):

1. Enumerate: `pgrep -f "amply worker"`.
2. Map each PID to its run id: from an open fd,
   `ls -l /proc/<pid>/fd | grep -oE '[0-9]{8}-[0-9]{6}-[0-9a-f]+' | head -1`, or
   the `--resume=<run-id>` on its cmdline.
3. Last activity = newest mtime of `~/.amply/logs/<run-id>.log` and
   `~/.amply/artifacts/<run-id>/`; idle = now − that.
4. Skip your own worker (walk up from your shell's `$PPID`) and every
   `remote-chat-ws` worker.
5. `SIGTERM` the rest that are idle ≥ 6 h; wait a few seconds; `SIGKILL` any
   survivor. Write a ledger of what you stopped to `~/.amply/logs/`.

They shut down cleanly and are resumable later from the web UI, so this loses no
work.

## srcfsd: Restart, Do Not Cap

**`srcfsd` leaks in metadata/anonymous memory, which no content-cache cap bounds,
so capping the content cache does NOT hold its growth — the only fix is
`sudo systemctl restart srcfs`.** The FUSE daemon starts with
`--srcfs_content_cache_max_mem_bytes=-1` ("auto-size to system RAM"), and an
override in `/etc/default/srcfs` can shrink the *content cache* — but the leak
lives elsewhere, so RSS+swap climbs back to tens of GB regardless. (An earlier
note claimed an 8 GiB cap fixed it; it does not.) The restart is passwordless-
authorized and operator-blessed as "basically harmless".

**This is already automated — do not hand-restart unless the sentinel is down.**
`~/.tpu_bin/srcfsd_autoheal.sh` runs from cron every 2 min and restarts `srcfs`
when `srcfsd` (RSS+VmSwap) ≥ ~30 GB *and* the machine is tight (MemAvailable low
or SwapFree low), debounced over two samples with a 30 min cooldown. Two
consequences of a restart, both self-healing: objfs GCs the freshly-unreferenced
checker binaries (`money_check` keepwarm cron rebuilds them), and any build whose
cwd sits on the FUSE mount is killed (the build-worker retries; its own cwd is
`$HOME`, off FUSE, so it survives).

**A health probe must never `stat`/`ls`/`readlink` anything under `/google/src`
or `/google/obj`.** Those calls are exactly what hangs when `srcfsd` wedges, so a
probe that touches them creates the failure it is meant to detect. Read only
`/proc`, `free`, `ps`, and local JSON.

## Idle Blaze Heaps, Swap, And OOM

**A serial build pipeline does not bound memory; standing servers do.** Each
checkout's blaze server holds a multi-GB JVM heap for its whole `max_idle_secs`,
one per checkout, whether or not a build runs.
`learning/deepmind/config/blazerc` sets 7 days with an 18 G heap and leans on
`--shutdown_on_low_sys_mem`, which fires only once memory is already tight and
cold-respawns the heap, deepening the dip. Bound it in `~/.blazerc` AFTER the
DeepMind `import` (last startup flag wins; binds only NEW servers).

**Count blaze SERVERS by process identity, never by grepping "blaze" in argv.**
Every binary blaze ever built runs from a path containing `blaze-out/`, so
`ps | grep blaze | wc -l` counts agent workers and daemons and reads as a build
storm. Match the JVM (`blaze(NNN)` / `BlazeServer_deploy.jar`) or count
`blaze (build|test|run)` invocations, and say which you measured. Judge a server
idle by `command*.profile.gz` mtime in its `output_base` (one per command), not
by a missing `command.log` (stats as epoch 0 → reads maximally idle → reaps live
servers) and not by CPU-time delta (never zero; highest on the fattest idle heap,
inverting the ranking).

**`timeout` kills the blaze CLIENT; the SERVER builds on and often succeeds** — a
nonzero exit can describe a build that produced a good binary. Gate any "done"
stamp on the artifact, not the rc, and size the timeout for a cold build on a
loaded host.

**A cron `flock` fd is inherited by any blaze server it spawns, so the lock is
held for the server's whole `max_idle_secs`, not the script's run.** A `*/5` cron
then fires once per idle window and writes no log line (the script is never
exec'd), so "no errors in the log" is the symptom, not the refutation. Fix with
`flock -n -o` in the crontab line (`-o` closes the fd before exec), never by
lowering `max_idle_secs`.

**A memory cap without a swap cap is not a cap.** `MemoryMax` alone excludes
swap: the job holds its RAM allowance plus tens of GB of swap, whose paging trips
`systemd-oomd` (which kills on PSI, not on the limit). Always set both, and
prefer `~/.tpu_bin/memcap [-m LIMIT] <cmd...>`:

```bash
systemd-run --scope -p MemoryMax=8G -p MemorySwapMax=0 <cmd>
```

The blast radius is the whole scope, not the offender: one uncapped local eval
reached 46.7 G and oomd took out 31 processes in one tmux scope, including the
operator's own amply server. A script heavy enough to matter should refuse to run
uncapped.

**`systemd-oomd` kills do NOT increment `/proc/vmstat`'s `oom_kill`, so a counter
check stays silent through an outage.** Detect it in the journal instead:

```bash
journalctl --since '-1h' | grep -E 'systemd-oomd.*(Marked .* for killing|killed [0-9]+ process)'
```

A whole `tmux-spawn-*.scope` dies at once, so every background job from that tmux
dies together silently — their simultaneous death is the tell. `/tmp` is tmpfs
and counts against RAM (`df -h /tmp`); never `rm -rf /tmp/*` blindly.

## How Slow Is A Build Too Slow

**A per-run TPU build floors near ~40s and scales with the PACKAGE, so 50-55s
for a big package is normal; but a build over 60s is never normal — treat >60s as
a hard signal that something is wrong, and check the cause immediately (the
triage below) rather than waiting to see whether it recovers.** Below 60s the
tell that a build is healthy is `CPU used ≈ Elapsed` with `queue time 0.0s` in the
blaze `Elapsed time:` / `Forge stats:` line. Each launch builds a uniquely-named
per-run target (`eqr_run_ca_<hash>:main`), so `0/9 actions cached` every time and
the ~7 GB `.par` relinks from zero; that single relink is the whole critical path
and cannot be cached while the target name is per-run (mechanism in
`infra/router.md`). What varies build-to-build below 60s is the package's own
size, not the host:

| Signal (from the blaze log) | Big package (elt eval) | Small package (parcae h100) |
|---|---|---|
| `Elapsed time` | ~52 s | ~39 s |
| targets configured | 653 | 107 |
| link critical path | ~39 s forge | ~25 s forge |
| novel bytes | ~30 MB | ~1 MB |
| `CPU used` vs Elapsed | 54 s vs 52 s | 41 s vs 39 s |
| `queue time` | 0.0 s | 0.0 s |

**`CPU used ≈ Elapsed` and `queue time 0` is the proof it is NOT load-bound**: an
overloaded host shows wall-clock far above CPU time (the build waiting on
contention) and/or nonzero queue time. When they track each other, the build is
running flat-out on its own single-threaded relink and the extra seconds are the
bigger package, nothing to fix on the machine. Measure blaze's own
`Elapsed`/`Forge stats` line, captured in the job's `xm_launch.log`, never the
end-to-end wall time (which also carries staging and launch).

**Once a build crosses 60s — or `Elapsed` >> `CPU used`, or `queue time` is
nonzero, or the SAME package suddenly takes much longer — the host is the suspect
and the cause is outside blaze, one of three:**

| Symptom | Cause | Where to look |
|---|---|---|
| blaze `Elapsed` ~40s but end-to-end wall is minutes | staging rsync drained the CitC CreateSnapshot token bucket | `[[STAGE_RSYNC_TIMEOUT]]` / `[[STAGE_INCOMPLETE]]` in the worker log; `storage.md` §Before Blaming CitC |
| `Elapsed` itself inflates (100s+) while critical path stays ~40-50s | CPU contention from too many concurrent heavy processes (e.g. a duplicate check-daemon running `infra_check` twice) | load average + daemon count; `infra/tpu_cli.md` §The Cache Daemon |
| first build after idle is far slower | memory pressure evicted the idle blaze server (`--shutdown_on_low_sys_mem`), so it cold-respawns a multi-GB JVM | `workstation.md` §Reclaiming Memory |
