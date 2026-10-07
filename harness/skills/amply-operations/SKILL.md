---
name: amply-operations
description: Restart or revive the amply UX gateway, check and repair its local Spanner database, read host health, and diagnose an `amp` session that only looks dead.
---

# Operate The Amply Service

Read [knowledge/codebases/local-agent-cli.md](../../../knowledge/codebases/local-agent-cli.md)
first for the agent CLIs, how a named session starts, and where the gateway URL
lives, and
[knowledge/codebases/local-agent-cli.md §The Amply Database Is A Local Spanner Test Universe](../../../knowledge/codebases/local-agent-cli.md#the-amply-database-is-a-local-spanner-test-universe)
for how the gateway's database, its client flags, snapshots, history migration,
and restart order are built. This skill owns the runbook for the gateway and
its local database, and the classic ways a run only looks dead.

Chapter 1 is the runbook for the gateway and its local database. Chapter 2 is
the classic ways a run only looks dead.

---

## Chapter 1 — Operating The Amply Service

### Restarting The Amply UX Server

**`amply` and `amply-launch` are `blaze run`, so they work only inside a google3
workspace.** They are shell functions, not aliases: typed from `~/work`, they
`cd` to `$AMPLY_WORKSPACE` in a subshell. `amp`'s automatic restart drives tmux
for that reason and one more. The function needs an *interactive* shell, and a
tmux pane outlives the `amp` process that started it.

**When srcfsd restarts, every new worker dies at startup inside `sysconfig` at
`os.getcwd()`.** The server's cwd sits inside a citc client and workers inherit
it: `ux/server.py` deliberately passes no `cwd=` to `subprocess.Popen`, and the
google3 embedded interpreter leaves `sys.executable` empty, so CPython falls
back to `_PROJECT_BASE = _safe_realpath(os.getcwd())` while importing `ctypes`
— before any `--working_dir` chdir can run. `/api/run/new` still answers 200;
the worker dies afterwards with `exit=1`. Two errnos, one disease: `[Errno 107]
Transport endpoint is not connected` when srcfsd died and stayed down, `[Errno
2] No such file or directory` when srcfsd came back as a NEW mount and left the
old dentry dangling. One probe covers both: `readlink /proc/<ux-server-pid>/cwd`
shows `(deleted)`, or a path missing its `/google/src` prefix. Running workers
are unaffected — they chdir'd to `~/work` long ago — so the symptom is "no new
sessions, every old one fine". Workers reparent to init and survive the UX
server dying, so a run that looks lost usually needs the server back, not
`amp start`.

**Give the gateway a cwd in `~/work`, not in the citc workspace, and this cannot
recur.** `blaze run` forces the workspace cwd on it; running the already-built
binary directly (below) does not.

**`amply-launch` now does this itself** (`~/.bashrc` `_amply_blaze`), so the
one-line revive in the tmux pane is enough and the `cd` in front of it is
redundant. It `blaze build`s in `$AMPLY_WORKSPACE` (blaze needs that cwd),
resolves `blaze-bin/.../amply` through `readlink -f` to its objfs inode, then
`( cd ${AMPLY_RUN_CWD:-$HOME/work} && exec "$bin" "$@" )`. Every revive path
inherits the fix: `~/.amply/bin/restart-amply-ux.sh` and `amp`'s own
`_launch_ux_in_tmux` both drive `amply-launch`. If the build fails or times out
but a built binary exists, it warns and runs that binary rather than leaving the
gateway down.

Two traps that any `blaze run` through the shim hits, both worth keeping:

**`blaze run` leaks the host build lock for the gateway's whole lifetime.** The
`blaze` on PATH is `~/.tpu_bin/shims/blaze`, which holds
`/tmp/host_heavy.<uid>.lock` on fd 210 and then runs blaze WITHOUT `exec`, so
the fd is inherited all the way down into the binary `blaze run` execs, and every
`blaze` and `hg status` on the box queues behind the gateway (up to `-w 1800`,
then degrading to parallel). The lock is meant to cover a BUILD; `blaze run`
makes it cover the whole RUN. So for anything long-lived — a server, a soak
test, a watcher — `blaze build` the target and run the binary yourself; reserve
`blaze run` for things that exit in seconds. `readlink /proc/<pid>/fd/210` names
the culprit in one command, and building/exec'ing separately drops the fd with
the build subshell.

**Bounding that build needs `timeout -k`, not `timeout`.** The shim blocks in
`flock -w 1800`, and bash defers SIGTERM while a foreground child runs, so a
plain `timeout` cannot interrupt it. SIGKILL cannot be deferred:
`timeout --foreground -k 15 <secs>`.

#### When `amply-launch` Prints Nothing At All

Two independent faults compose into one symptom: a terminal parked on a blank
line, indefinitely.

**You cannot see the output.** `~/.tpu_bin/serialize_heavy.sh` ended its lock
setup with `exec 210>"$LOCK" 2>/dev/null`, and `exec` with no command applies
every redirection to the shell permanently — so blaze's whole progress stream
landed in `/dev/null` ([knowledge/infrastructure/tpu-cli.md §Serializing Heavy Verbs: Separate Blaze And Hg Locks](../../../knowledge/infrastructure/tpu-cli.md#serializing-heavy-verbs-separate-blaze-and-hg-locks)).
On any copy that still has it, `TPU_SERIAL_HEAVY=0` skips the shim, and
`/usr/local/google/tmp/rabbit*.log.INFO.*` holds what stderr lost.

**The build never starts.** With `~/.redirect_to_dbip_on` present, `/usr/bin/blaze`
rewrites `blaze run` into `rabbit run` (go/dbip). A healthy dbip request logs
`Using locally-generated Source URI` and a `build_request_id` inside a second
and finishes in ~25s. When srcfs or piper-api is throttled (`blade:srcfs ...
Service is overloaded`, `Regurgitator disconnected`, `piper-api
DEADLINE_EXCEEDED`), rabbitd logs `Received request` and then nothing at all,
for as long as you let it.

**Revive without blaze.** `blaze run` only builds the binary and execs it; when
the binary is already built, skip both:

    BIN=$(ls /usr/local/google/_blaze_qiaos/*_buildrabbit/execroot/google3/blaze-out/k8-fastbuild/bin/third_party/py/simply/amply/amply)
    "$BIN" version                     # rc=0 proves objfs can still serve it
    tmux send-keys -t amply_ux:0 -l -- "cd ~/work && $BIN ux"
    tmux send-keys -t amply_ux:0 Enter

45 seconds to `/api/runs` 200, no CitC snapshot, no blaze lock, and the cwd is
right. The objfs-GC exposure is identical to `blaze run`'s, not worse: the
blaze-out tree is reclaimed once blaze goes idle, which is why
`~/.tpu_bin/money_check_keepwarm.sh` exists. Refresh it with one `blaze build
//third_party/py/simply/amply:amply` after the backend recovers; the running
gateway needs no restart for that, because `_AMPLY_BIN` resolves through
`realpath('/proc/self/exe')` and holds its own inode open.

#### Reviving The Gateway Yourself

**Any agent can self-restart the gateway with
`~/.amply/bin/restart-amply-ux.sh` (bashrc: `amp-restart-ux`), bypassing
`amp`.** It mirrors the internal `amp` tmux sequence
(`claude-amply.py:_launch_ux_in_tmux`): settle, `tmux kill-session -t amply_ux`,
fresh detached session at the workspace, wait for `~/.bashrc`, `send-keys`
`cd <ws> && amply-launch`. The tmux indirection is mandatory. `amply-launch` is
a bashrc function existing only in an interactive shell (`bash -lc` misses it,
bashrc returning early when non-interactive), and the detached session outlives
the agent that ran it. The agent's bash tool shares the operator's default tmux
socket, so plain `tmux` reaches `amply_ux`. Use `--dry-run` when unsure; the
script bounded-verifies revival (polls `dashboard_url` + `/api/runs` 200) unless
`--no-verify`. Flags/env: `--warmup`/`--wait`, `AMP_UX_TMUX` /
`AMP_UX_WORKSPACE` / `AMP_UX_ALIAS`. Never use the deprecated
`~/.amply/bin/ux_launch.py`: it used to exec a server on any invocation, the
3-server split-brain footgun, and is now gated behind
`AMPLY_UX_LAUNCH=really-launch` (verify with `grep AMPLY_UX_LAUNCH` on the
script; without the gate it exits 2).

#### Never Run A Second UX Server

**Never start a second UX server to work around an unreachable one; find the one
already running** (`ss -ltnp | grep amply`; wildcard 0.0.0.0 binds are servers,
127.0.0.1 are workers). Every boot rewrites `~/.amply/dashboard_url`, so with two
alive the file tracks whichever booted last; when that one dies, clients follow
the file to a dead server while a healthy one keeps serving unlisted. This
machine once ran three at once, splitting live sessions between them. `amp` now
heals this: re-ping once (a load blip is not an outage), adopt a live server by
repointing the file, launch only when nothing is adoptable. Two footguns with
prior incidents: `ux_launch.py` used to exec a real server on any invocation, so
running it for usage text started server #3 (now gated behind
`AMPLY_UX_LAUNCH=really-launch`); and a TUI/window keeps the base URL it read at
startup, so after a server change, windows spewing `Connection refused` just
need quitting and reopening.

**A cold gateway takes minutes to answer `/api/runs`, so a concurrent `amp` that
pings and misses launches a duplicate** — the same split-brain, self-inflicted
by the client. The server binds its HTTP port and writes `~/.amply/dashboard_url`
only after the skill-index + embedder build finishes; under load that cold start
hit ~4 minutes, against ~30s normally. The second `amp new` reads a stale or
absent `dashboard_url`, its two 3s pings both miss the not-yet-serving gateway,
and it launches gateway #2 that steals `dashboard_url`. The fix is a
cross-process launch lock: `~/.amply/ux.launching.lock`, JSON
`{pid,host,started_at}`, 6-min TTL plus dead-pid steal. The first `amp` claims
it; every concurrent `amp` waits, polling `dashboard_url` plus a port scan to
adopt. A stale lock (launcher died, or past TTL) is stolen. Claim with
`write-temp-then-os.link`, not `O_EXCL`-then-write: `O_EXCL` creates an empty
file first, and a racer reading it mid-write gets `json.loads('')` → "stale" →
steals it → two winners (3/30 concurrent races doubled), while `os.link`
publishes the payload atomically. Two subtleties the tests pin: on lock-clear a
waiter must re-check `dashboard_url` before taking over, and the winner re-checks
once more under the lock (double-checked locking) before spending a launch. See
`claude-amply.py` `_try_acquire_launch_lock` / `_wait_for_peer_launch` /
`ensure_ux_server`, tests in `agent-island/tests/test_launch_lock.py` (including
a 3-way-race E2E asserting exactly one gateway launches). Separately,
`amp stop <id|latest>` exists (resumable pause, mirrors the web Stop button) for
shedding a worker's RAM/CPU without losing state.

#### `amp new` / `amp resume` 500 With `FileNotFoundError`

**`amp new` / `amp resume` 500 with `FileNotFoundError: .../amply` is the
gateway's spawn path gone stale after a concurrent build; restart the gateway,
do not blame version skew.** The ux server caches the worker binary path at
import time, historically `sys.argv[0]`, pointing into the checkout's blaze
`execroot/.../blaze-out` symlink. Any `blaze build` under the same
`$AMPLY_WORKSPACE` checkout republishes that symlink to a fresh objfs namespace
and GCs the old one, so the cached path dangles and every spawn
(`_spawn_new_run_subprocess` → `subprocess.Popen`) dies with `FileNotFoundError`.
That 500s `/api/run/new` and `/api/run/start` while the read path (`/api/chat`,
`/chat/messages`) stays 200 — so only "open/restart a line" breaks. Tell it apart
from the version-skew 500 ([harness/engineering.md](../../engineering.md), which 500s the *read/status*
path) by grepping the server log for the endpoint + traceback (`E.... Exception
on /api/run/new [POST]` in `/usr/local/google/tmp/amply.*.INFO.*`). `_AMPLY_BIN`
now resolves from `os.path.realpath('/proc/self/exe')`, the inode this process
holds open and objfs keeps alive, falling back to `sys.argv[0]`; see
`third_party/py/simply/amply/ux/server.py:_resolve_amply_bin`. A gateway running
the old cached path must still be restarted once, because the value was captured
at import time and the patch only helps future boots.

### Checking And Repairing The Amply Database

How the universe is built, why its restart order is automatic, and what the ops
watchdog does about a dead database are
[knowledge/codebases/local-agent-cli.md §The Amply Database Is A Local Spanner Test Universe](../../../knowledge/codebases/local-agent-cli.md#the-amply-database-is-a-local-spanner-test-universe).
This section is what you check and run by hand.

Health in one line: `cat ~/.amply/localdb/ready ~/.amply/localdb/client_flags.txt`
and `amp-ux-ok`. A query by hand:
`span $(cat ~/.amply/localdb/client_flags.txt) sql /span/test-universe/qiaos:amply`
(it spends a minute failing to reach corp chubby first; the query still runs).

**A reboot kills this database until something repoints its runfiles MANIFEST.**
`bin/localdb` and `bin/dbtool` are `par_binary` launchers: they import their own
Python through `<bin>.runfiles/MANIFEST`, which maps every runfiles key to an
ABSOLUTE path -- into the blaze output tree
(`/usr/local/google/_blaze_qiaos/<md5>_buildrabbit/execroot/google3/blaze-out/...`,
itself a symlink into objfs) and into the CitC workspace. `refresh_bin.sh` copies
the binaries AND their runfiles onto local disk, but the copied MANIFEST still
names those originals, so the local copy is local in its bytes and remote in its
imports. Both originals are missing exactly when this service needs them: objfs
is not mounted for the first minutes after a reboot, and any later build repoints
`blaze-out` at a different namespace, which retires the old one. Past
`StartLimitBurst` systemd stops retrying on its own: only `systemctl --user
reset-failed` clears it, so an outage outlives its cause.
`~/.amply/localdb/fix_manifest.py` repoints every external entry at the local copy; it is idempotent, and it refuses
to write anything if some key has no local file, because a half-repointed
MANIFEST is worse than an honestly broken one. `run_localdb.sh` runs it before
every start and `refresh_bin.sh` after every copy, so a rebuild cannot bring the
problem back. Audit by hand with `fix_manifest.py --check` (exit 1 means a repair
is due).

Traps met while building the local database:

- **Startup can fail on a port collision** (`bind() failed ... Address already
  in use`, then `lamprey(SpannerTestEnv) startup failed`): the universe picks
  ports with `PickUnusedPort` on a host with hundreds of listeners.
  `run_localdb.sh` retries up to 6 times with a fresh `TEST_TMPDIR`; reusing a
  scratch dir also fails.
- **The universe runs SQL in strict name resolution mode**: `SELECT run_id
  FROM Run` is rejected, `SELECT r.run_id FROM Run AS r` is fine. amply's own
  queries all alias their tables; hand-written ones must too.
- **`pgrep -f 'amply worker'` / `pkill -f` match the shell that runs them**,
  because the pattern is in that shell's own command line. Anchor on the
  binary path (`pgrep -f '^/.../bin/amply worker'`) or the wrapper kills
  itself.
- **systemd expands `$VAR` in `ExecStart` itself**: `bash -lic '$HOME/x.sh'`
  became `bash -lic ''` ("Invalid environment variable name evaluates to an
  empty string"), five fast failures, `start-limit-hit`. Use `%h`, and
  `systemctl --user reset-failed` before the next start.
- `tmux kill-session` does not kill a gateway that was `exec`'d in the pane;
  it ignores SIGHUP and keeps its port and `dashboard_url`. `kill -9` it.
- `POST /api/run/new` returning 200 proves nothing about the database; follow
  `/api/run/new/stream?op=` until `[amply-startup 2/6]`. A worker stuck at 1/6
  ignores SIGTERM (blocked in a C++ RPC) and needs `kill -9`.

### Host Health In One Line (`memavail` / `cpuload` / `hstat`)

**One-line host health from `~/.bashrc`, read straight from `/proc` (no deps,
works in any shell).** Check pressure before launching work on this shared
workstation, which overloads (load has hit 102); the cause is the
amply-gateway-restart-loop in
[harness/engineering.md §Guards and diagnostics must not kill the job](../../engineering.md#guards-and-diagnostics-must-not-kill-the-job).

| Util | Shows |
|---|---|
| `memavail` | Available RAM (allocatable) + used/total + %avail, from `MemAvailable` |
| `cpuload` | Load average + core count + per-core 1-min load; flags `** OVERSUBSCRIBED **` when >1.0/core |
| `hstat` | Both of the above in one call |

Read `cpuload` per-core, not raw. A raw load of 20 is healthy on a 24-core box
(0.83/core) and on fire on an 8-core one (2.5/core). It is meaningless without
its denominator ([harness/engineering.md §Communicating a result](../../engineering.md#communicating-a-result)). The util divides
for you; trust `/core`, not the first column.

---

## Chapter 2 — Classic Bugs: A Run That Only Looks Dead

A run can read `Stopped`, `Running`, or idle from outside and be fine, or be dead
for a reason no retry fixes. Start every diagnosis the same way, then match the
mechanism below.

### Diagnosing A Dead `amp` Session

**Start at `/api/chat?run_id=<id>`**: `chatbot_status` separates a session that
answered from one that died, `live` says whether the worker is up, and the
traceback is in `~/.amply/logs/<run_id>.log`. A crashed chatbot does not lose
the run: it is spawned per message, so sending one respawns it, and subagents
keep working throughout.

**Never grep those logs for `429` or `quota`.** A denied Stubby RPC dumps
hundreds of `DestinationPermission #<n>: Wrong user mdbuser/... in restriction.`
lines, so the pattern matches an *index*, not an HTTP status (once misread as
"93 rate-limit errors" on a never-rate-limited host). Match the exception class:
`RateLimitError`, `RESOURCE_EXHAUSTED`, `Quota exceeded`.

A crash belongs to the one message, not the load; many concurrent sessions have
never been a cause. Two mechanisms, neither survivable by a retry:

| Mode | Why a retry does not save it |
|---|---|
| `AnthropicError: Overloaded` | A transient upstream 529 arrives as an error chunk *after* the stream opened, so `num_retries` cannot cover it. litellm turns it into `MidStreamFallbackError`, which escapes `run()` and marks that one session `crashed`. |
| Event too large | A tool result over the Spanner column limit (10 MiB on `EventSearchIndex.search_text_substr`) fails the write and kills the thread; `INVALID_ARGUMENT` is not retryable. `view_file` base64-encodes images, inflating by 4/3, so the real per-file ceiling is ~7.5 MB. Measuring a file and calling it "under 10 MB, safe" is how this recurs. |

`web_search` is registered unconditionally with no disable flag, and this host's
LOAS credential cannot reach superroot, so every call fails and dumps a
permission wall into the log. Noise, not a crash cause, but it is why run logs
reach hundreds of MB.

### Amply Workers Segfault Overnight

**A run that reads `Stopped` was usually not stopped, its worker segfaulted.** It
recurs in overnight bursts, always inside 02:00–05:30, never during the day. In
`/api/runs` it is indistinguishable from an operator pause, because
`/api/run/stop` is a pause that also leaves `status: ongoing` with a dead
process.

Do not hunt for a resource limit. `/proc/vmstat` reported `oom_kill 0`, and
systemd-oomd logged no kills. `unauthenticated: invalid credentials` in syslog
is constant background noise at 200–400/hour, correlating with everything and
explaining nothing. A mass die-off whose last heartbeats land within the same
five seconds is a reboot: check `/proc/uptime` first.

The stack, from a core — `zstd -d` the dump, then
`gdb -batch -ex 'bt -45' <binary> <core>`:

```
#178 absl::MakeStatusRepImpl<...>                              <- SIGSEGV here
#180 util::MakeStatus
#181 rpc2::NetClientChannel::AbortNonRestartableRPCsWithError
#183 rpc2::NetClientChannel::ShutdownOnError_Locked
#184 rpc2::NetClientChannel::HandleRead
#189 eventmanager::EventManager2::Worker::Run
```

An RPC connection drops, and building the `absl::Status` that aborts the
in-flight RPCs faults. `FailureSignalHandler` re-faults ~90 frames deep until
the kernel prints `signal: DefaultEventMan[…] overflowed sigaltstack`. That
kernel line, and the "stack trace" systemd records, name only the crash handler.
The real frames are the outermost ones, so read `bt -45`.

`amp watchdog` mitigates it: restart `ongoing` runs whose worker is dead **and**
whose last heartbeat sits within seconds of an `amply` coredump in
`/var/lib/systemd/coredump`. The coredump is the only thing separating a crash
from a pause; without it the watchdog overrides the operator every 60 seconds.

### A Turn That Wrote A Tool Call Instead Of Making One

Another way a session stops, identical from outside: worker up, run `Running`,
nothing happens. The model wrote its tool call as XML-ish markup in the message
text (`invoke` / `parameter` tags) and made no actual call, ending the turn with
nothing executed.

**It is the model, not amply.** Amply drives tools through structured
`tool_calls`. `invoke name=` appears nowhere in the amply tree or
`~/.amply/AGENTS.md`, so nothing teaches or parses that syntax; the transport
cannot turn a real tool_use block into text. Affected messages carry
`tool_calls: []` with the markup in `content`. Not context exhaustion either:
sessions at 500k+ prompt tokens had zero while the worst offender sat at 195k.

What amply does wrong is not noticing. The malformed text is stored verbatim and
becomes an in-context example the model copies, so one slip snowballs across a
session. Nothing retries; the run sits until an external poke, a median of 24.7
minutes later. Most `已静置(idle)` monitor alerts are this.

`amp watchdog` nudges those sessions: last message from the chatbot, empty
`tool_calls`, markup present, run live but not working. The nudge describes the
mistake rather than quoting it, since quoting the markup back adds another
example to copy. Same reason `tests/test_watchdog.py` builds its fixture from
fragments.

`event_loop.py` also catches the leak inline, so the idle gap above should not
recur on this workstation: after an assistant turn with no `tool_calls`, it
regex-matches the content for `invoke name` / `function_calls` / `parameter
name` markup, appends a `UserEvent` system correction, and continues the loop
without sleeping. Two caveats before relying on it. It is a LOCAL change in the
CitC workspace, absent from submitted HEAD, so a fresh workspace or a rebuilt
binary from depot does not have it. And it is an inline `re.search`, not a named
constant, so grep for the warning string `Detected malformed tool call markup`
to check whether a given binary carries it. The 24.7-minute figure and the rule
behind it ([harness/engineering.md §A tool call only fires as a structured call](../../engineering.md#a-tool-call-only-fires-as-a-structured-call))
describe model behaviour and still hold; this guard only shortens the recovery.
