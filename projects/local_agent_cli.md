# Local Agent CLIs

Read this before changing how an agent CLI is launched or managed here. The
`agent-island` checkout and the live `~/.bashrc` are authoritative for current
wiring; the agent web app is `agent_web.md`. Since 2026-09-08 all of this runs
on `sqa-large.c.googlers.com`, not `sqa`; the amply gateway URL is in
`~/.amply/dashboard_url` (the port changes per start), and the migration,
the re-sync recipe and what still runs on `sqa` are in `workstation.md`.

## `clod`, And The Jail It Runs In

**A command named `claude` is blocked by this host's `ai_agent_execution`
policy, so Claude Code is exposed as `clod`.** Only the name is refused. The
binary runs fine, so never conclude Claude Code is unavailable here. Same shape
for `amp` (Amply chat), `gemini` (Jetski), `gpt` (Codex): each dispatches
`list / search / resume / rename / clear` to a session helper, else launches the
agent.

`clod` runs Claude Code in a bubblewrap jail under `--permission-mode auto`.
Both layers are deliberate: the classifier catches bad tool calls, bwrap
contains what escapes it. Management subcommands only read/rewrite `~/.claude`,
outside the jail; `resume` re-enters it, so a resumed session gets a fresh
session's policy.

| Rule | Consequence of ignoring it |
|---|---|
| A wrapper imposing a permission policy must stop the session helper adding its own: `CLAUDE_LAUNCH_ARGS=""` drops the helper's `--dangerously-skip-permissions` | The two fight and the jail's auto mode is silently bypassed |
| The jail hides `/google/data`, `/google/bin`, `/google/src/head`, `/cns`, and other users' homes. `$HOME` and `/google/src/cloud/qiaos` are read-write, `/tmp` is a private tmpfs, the network is shared with the host | A task needing those runs outside the jail with `CLOD_NO_SANDBOX=1`; it is not a missing-file bug. `--unshare-pid` also hides host processes, tmux included, so the agent cannot signal them |
| `effortLevel` in `settings.json` stops at `xhigh`; only the CLI flag `--effort max` reaches the model, so `clod` passes it | `"max"` in settings is ignored and the session falls back to `high`. Claude Code accepts unknown settings values silently, so never read "it started fine" as evidence a setting took effect. The `effort` field of a `PreToolUse` hook's stdin payload reports the effective level |

## Named Startup: Registration, Readiness, And Native Names

The 2026-09-07 repairs are deployed in `agent-island/claude-amply.py` and
`codex-session-name.mjs`; `.bashrc` and `~/.local/bin/gpt` use them on each new
invocation. No gateway or database restart is needed for these CLI changes.

`amp new NAME` now applies `/annotate/title` as soon as the exact run ID is
registered. Registration is not readiness: an independent read-only status
observer can detect a ready worker after a quiet or lost startup stream and
attach that same run. Never repeat run creation to repair the display. Explicit
worker failure still wins over a live observation. The configurable default
600-second observation budget is not a hard deadline for every HTTP operation.
See `~/work/.amply_new_sync_fix_20260907/README.md` and its installed CLI tests.

`gpt new NAME` now creates one empty native thread, sets and reads back its
native name, then enters the TUI with that exact thread ID. Updating only the
SQLite title or a sidecar while a new TUI is already running can lose to native
automatic naming on the first prompt. Native 0.153.4 tests verified the name
survives actual first input. Unsupported named-start options, including
`--profile`, fail before creating a thread; use unnamed `gpt new` followed by
the TUI's `/rename` for those options. Original unnamed new/resume behavior is
preserved. See `~/work/.gpt_new_name_fix_20260907/README.md`, including private
app-server cleanup and compatibility limits. Do not restore the rejected
global newest-thread or background title-watcher approaches.

The slow skill scan and missing in-memory skill index are separate server-side
issues. `~/work/.amply_skill_cache_fix_20260907/README.md` owns the current
atomic v2 snapshot candidate and build/publication status; the older two-file
flock candidate in `.amply_startup_investigation_20260907` is superseded.

## `amp` / Amply: Diagnosing A Dead Session

**Start at `/api/chat?run_id=<id>`**: `chatbot_status` separates a session that
answered from one that died, `live` says whether the worker is up, and the
traceback is in `~/.amply/logs/<run_id>.log`. A crashed chatbot does not lose
the run: it is spawned per message, so sending one respawns it, and subagents
keep working throughout.

Never grep those logs for `429` or `quota`. A denied Stubby RPC dumps hundreds
of `DestinationPermission #<n>: Wrong user mdbuser/... in restriction.` lines,
so the pattern matches an *index*, not an HTTP status (once misread as "93
rate-limit errors" on a never-rate-limited host). Match the exception class:
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

## `amp` Sends Operator Messages While The Agent Works

**A message typed at the `amp` spinner is sent immediately, mid-turn, not queued
until the turn ends.** `/chat/send` appends a `MessageEvent` and wakes the
session. The chatbot's `run()` loop re-reads its context every iteration. Within
seconds the message folds into the running turn at the next tool-call boundary,
surfacing as the `[STATUS]` NEW OPERATOR MESSAGE banner. A tool boundary is not
preemption: a long in-flight tool or the current LLM generation finishes first.
That is not a hang.

Slash commands are the one exception, still deferred to the idle prompt.
`/status`, `/help`, `/compact`, `/quit` print to the screen or mutate turn
state, unsafe while the hand-drawn spinner owns the bottom rows. See
`claude-amply.py` `_compose_submit_draft`: slash → `_queued_messages`, else
`_send_operator_message(..., begin_turn=False)`, so the in-flight turn's clock
is neither reset nor torn down on a send failure. The contract is pinned by
`agent-island/tests/test_queue.py`.

## Amply Workers Segfault Overnight

**A run that reads `Stopped` was usually not stopped, its worker segfaulted.**
29 segfaulted in one overnight burst, and it recurs: always inside 02:00–05:30,
never during the day. In `/api/runs` it is indistinguishable from an operator
pause, because `/api/run/stop` is a pause that also leaves `status: ongoing`
with a dead process.

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

## A Turn That Wrote A Tool Call Instead Of Making One

Another way a session stops, identical from outside: worker up, run `Running`,
nothing happens. The model wrote its tool call as XML-ish markup in the message
text (`invoke` / `parameter` tags) and made no actual call, ending the turn with
nothing executed.

**It is the model, not amply.** Amply drives tools through structured
`tool_calls`. `invoke name=` appears nowhere in the amply tree or
`~/.amply/AGENTS.md`, so nothing teaches or parses that syntax; the transport
cannot turn a real tool_use block into text. Affected messages carry
`tool_calls: []` with the markup in `content`. Not context exhaustion either:
across 43 live runs, sessions at 617k/510k/505k prompt tokens had zero, the
worst offender 195k.

What amply does wrong is not noticing. The malformed text is stored verbatim and
becomes an in-context example the model copies. After the first slip at turn 51,
one session did it in 96 of 187 turns. Nothing retries; in 95 of those 96 the
run sat until an external poke, a median of 24.7 minutes later (every gap
>5min). Most `已静置(idle)` monitor alerts are this.

`amp watchdog` nudges those sessions: last message from the chatbot, empty
`tool_calls`, markup present, run live but not working. The nudge describes the
mistake rather than quoting it, since quoting the markup back adds another
example to copy. Same reason `tests/test_watchdog.py` builds its fixture from
fragments.

`event_loop.py` now also catches the leak inline, so the idle gap above should
not recur on this workstation: after an assistant turn with no `tool_calls`, it
regex-matches the content for `invoke name` / `function_calls` / `parameter
name` markup, appends a `UserEvent` system correction, and continues the loop
without sleeping. Two caveats before relying on it. It is a LOCAL change in the
CitC workspace, absent from submitted HEAD, so a fresh workspace or a rebuilt
binary from depot does not have it. And it is an inline `re.search`, not a
named constant, so grep for the warning string `Detected malformed tool call
markup` to check whether a given binary carries it. The 24.7-minute figure and
the rule behind it (`engineering.md` §A Tool Call Only Fires As A Structured
Call) describe model behaviour and still hold; this guard only shortens the
recovery.

## Restarting The Amply UX Server

**Source recovery, 2026-09-06:** `run_amply_workspace` has a Fig snapshot-write
failure that repeatedly rolls back Hg metadata. A verified Amply source copy
is available at
`/google/src/cloud/qiaos/hg_recovery_20260906/google3/third_party/py/simply/amply`.
Native Hg status works in that new workspace. The running Amply service and its
launch configuration were not switched or restarted. This copy preserves
readable source content, not the old workspace's local commit history; see
`~/work/.hg_status_recovery_20260906/README.md` before using it for development.

**`amply` and `amply-launch` are `blaze run`, so they work only inside a google3
workspace.** They are shell functions, not aliases: typed from `~/work`, they
`cd` to `$AMPLY_WORKSPACE` in a subshell. `amp`'s automatic restart drives tmux
for that reason and one more. The function needs an *interactive* shell, and a tmux
pane outlives the `amp` process that started it.

When srcfsd restarts, every new worker dies at startup inside `sysconfig` at
`os.getcwd()`. The server's cwd sits inside a citc client and workers inherit
it: `ux/server.py` deliberately passes no `cwd=` to `subprocess.Popen`, and the
google3 embedded interpreter leaves `sys.executable` empty, so CPython falls
back to `_PROJECT_BASE = _safe_realpath(os.getcwd())` while importing `ctypes`
— before any `--working_dir` chdir can run. `/api/run/new` still answers 200;
the worker dies afterwards with `exit=1`. Two errnos, one disease: `[Errno 107]
Transport endpoint is not connected` when srcfsd died and stayed down, `[Errno
2] No such file or directory` when srcfsd came back as a NEW mount and left the
old dentry dangling (2026-09-01). One probe covers both: `readlink
/proc/<ux-server-pid>/cwd` shows `(deleted)`, or a path missing its
`/google/src` prefix. Running workers are unaffected — they chdir'd to `~/work`
long ago — so the symptom is "no new sessions, every old one fine". Workers
reparent to init and survive the UX server dying, so a run that looks lost
usually needs the server back, not `amp start`.

**Give the gateway a cwd in `~/work`, not in the citc workspace, and this
cannot recur.** `blaze run` forces the workspace cwd on it; running the
already-built binary directly (below) does not. Note who creates the hazard:
the srcfs convoy sentinel used to auto-restart srcfs on its convoy and D-count
triggers and print a warning that the gateway's cwd was just severed — but
nothing consumed that warning, which is exactly how the 2026-09-01 outage began.
(That sentinel was retired with the monitor mechanism on 2026-09-10; see the
note at the gateway-watchdog paragraph below.)

**`amply-launch` now does this itself** (`~/.bashrc` `_amply_blaze`, rewritten
2026-09-01), so the one-line revive in the tmux pane is enough and the `cd` in
front of it is redundant. It `blaze build`s in `$AMPLY_WORKSPACE` (blaze needs
that cwd), resolves `blaze-bin/.../amply` through `readlink -f` to its objfs
inode, then `( cd ${AMPLY_RUN_CWD:-$HOME/work} && exec "$bin" "$@" )`. Every
revive path inherits the fix: `~/.amply/bin/restart-amply-ux.sh` and `amp`'s
own `_launch_ux_in_tmux` both drive `amply-launch`. If the build fails or times
out but a built binary exists, it warns and runs that binary rather than
leaving the gateway down — the 2026-09-01 case, where a stalled dbip build sat
12 minutes beside a perfectly good binary.

Two traps that rewrite hit, both worth keeping:

*`blaze run` leaks the host build lock for the gateway's whole lifetime.* The
`blaze` on PATH is `~/.tpu_bin/shims/blaze`, which holds
`/tmp/host_heavy.<uid>.lock` on fd 210 and then runs blaze WITHOUT `exec`, so
the fd is inherited all the way down into the binary `blaze run` execs. Measured
2026-09-01: `readlink /proc/<gateway>/fd/210` pointed at the lock, and every
`blaze` and `hg status` on the box queued behind the gateway (up to `-w 1800`,
then degrading to parallel). Building and exec'ing separately drops the fd with
the build subshell, so the gateway holds nothing.

This is not an amply bug — it is every `blaze run` through the shim. The lock is
meant to cover a BUILD; `blaze run` makes it cover the whole RUN. Caught live
the same evening on an unrelated line: `blaze run
//experimental/qiaos/elt_dit_pkg:persite_prodarch_test` held the lock for the
test's entire execution while two other builds queued on `flock -w 1800 210`.
So for anything long-lived — a server, a soak test, a watcher — `blaze build`
the target and run the binary yourself; reserve `blaze run` for things that
exit in seconds. `readlink /proc/<pid>/fd/210` names the culprit in one command.

*Bounding that build needs `timeout -k`, not `timeout`.* The shim blocks in
`flock -w 1800`, and bash defers SIGTERM while a foreground child runs, so a
plain `timeout` cannot interrupt it — two test runs sat the full 120 s with a
1-second bound. SIGKILL cannot be deferred: `timeout --foreground -k 15 <secs>`.

### When `amply-launch` Prints Nothing At All

Two independent faults compose into one symptom: a terminal parked on a blank
line, indefinitely.

*You cannot see the output.* `~/.tpu_bin/serialize_heavy.sh` ended its lock
setup with `exec 210>"$LOCK" 2>/dev/null`, and `exec` with no command applies
every redirection to the shell permanently — so blaze's whole progress stream
landed in `/dev/null` (fixed 2026-09-01; `engineering.md` §Serialize `blaze`).
On any copy that still has it, `TPU_SERIAL_HEAVY=0` skips the shim, and
`/usr/local/google/tmp/rabbit*.log.INFO.*` holds what stderr lost.

*The build never starts.* With `~/.redirect_to_dbip_on` present, `/usr/bin/blaze`
rewrites `blaze run` into `rabbit run` (go/dbip). A healthy dbip request logs
`Using locally-generated Source URI` and a `build_request_id` inside a second
and finishes in ~25s. When srcfs or piper-api is throttled (`blade:srcfs ...
Service is overloaded`, `Regurgitator disconnected`, `piper-api
DEADLINE_EXCEEDED`), rabbitd logs `Received request` and then nothing at all,
for as long as you let it — 12 minutes, twice, on 2026-09-01.

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

Any agent can self-restart the gateway with `~/.amply/bin/restart-amply-ux.sh`
(bashrc: `amp-restart-ux`), bypassing `amp`. It mirrors the internal `amp` tmux
sequence (`claude-amply.py:_launch_ux_in_tmux`): settle,
`tmux kill-session -t amply_ux`, fresh detached session at the workspace, wait
for `~/.bashrc`, `send-keys` `cd <ws> && amply-launch`. The tmux indirection is
mandatory. `amply-launch` is a bashrc function existing only in an interactive
shell (`bash -lc` misses it, bashrc returning early when non-interactive), and
the detached session outlives the agent that ran it. The agent's bash tool
shares the operator's default tmux socket, so plain `tmux` reaches `amply_ux`.
Use `--dry-run` when unsure; the script bounded-verifies revival (polls
`dashboard_url` + `/api/runs` 200) unless `--no-verify`. Flags/env:
`--warmup`/`--wait`, `AMP_UX_TMUX` / `AMP_UX_WORKSPACE` / `AMP_UX_ALIAS`. Never
use the deprecated `~/.amply/bin/ux_launch.py`: it used to exec a server on any
invocation, the 3-server split-brain footgun, and is now gated behind
`AMPLY_UX_LAUNCH=really-launch` (verify with `grep AMPLY_UX_LAUNCH` on the
script; without the gate it exits 2).

**Never start a second UX server to work around an unreachable one; find the
one already running** (`ss -ltnp | grep amply`; wildcard 0.0.0.0 binds are
servers, 127.0.0.1 are workers). Every boot rewrites `~/.amply/dashboard_url`,
so with two alive the file tracks whichever booted last. When that one dies,
clients follow the file to a dead server while a healthy one keeps serving
unlisted. This machine once ran three at once, splitting live sessions between
them. `amp` now
heals this: re-ping once (a load blip is not an outage), adopt a live server by
repointing the file, launch only when nothing is adoptable. Two footguns with
prior incidents. `~/.amply/bin/ux_launch.py` used to exec a real server on any
invocation: an agent ran `ux_launch.py --help` for usage text and started
server #3 (now gated behind `AMPLY_UX_LAUNCH=really-launch`). And a TUI/window
keeps the base URL it read at startup, so after a server change, windows spewing
`Connection refused` just need quitting and reopening.

A cold gateway takes minutes to answer `/api/runs`, so a concurrent `amp` that
pings and misses launches a duplicate: the same split-brain, self-inflicted by
the client. The server binds its HTTP port and writes `~/.amply/dashboard_url`
only after the skill-index + embedder build finishes. Under load that cold start
hit ~4 minutes, against ~30s normally. The second `amp new` reads a stale or
absent `dashboard_url`, its two 3s pings both miss the not-yet-serving gateway,
and it launches gateway #2 that steals `dashboard_url`. The fix is a
cross-process launch lock: `~/.amply/ux.launching.lock`, JSON
`{pid,host,started_at}`, 6-min TTL plus
dead-pid steal. The first `amp` claims it; every concurrent `amp` waits, polling
`dashboard_url` plus a port scan to adopt. A stale lock (launcher died, or past
TTL) is stolen. Claim with `write-temp-then-os.link`, not `O_EXCL`-then-write.
`O_EXCL` creates an empty file first, and a racer reading it mid-write gets
`json.loads('')` → "stale" → steals it → two winners (3/30 concurrent races
doubled). `os.link` publishes the payload atomically. Two subtleties the tests
pin: on lock-clear a waiter must re-check `dashboard_url` before taking over,
and the winner re-checks once more under the lock (double-checked locking)
before spending a launch. See `claude-amply.py`
`_try_acquire_launch_lock` / `_wait_for_peer_launch` / `ensure_ux_server`, tests
in `agent-island/tests/test_launch_lock.py` (including a 3-way-race E2E
asserting exactly one gateway launches). Separately, `amp stop <id|latest>` now
exists (resumable pause, mirrors the web Stop button) for shedding a worker's
RAM/CPU without losing state.

**`amp new` / `amp resume` 500 with `FileNotFoundError: .../amply` is the
gateway's spawn path gone stale after a concurrent build; restart the gateway,
do not blame version skew.** The ux server caches the worker binary path at
import time, historically `sys.argv[0]`, pointing into the checkout's blaze
`execroot/.../blaze-out` symlink. Any `blaze build` under the same
`$AMPLY_WORKSPACE` checkout republishes that symlink to a fresh objfs namespace
and GCs the old one. The cached path dangles, so every spawn
(`_spawn_new_run_subprocess` → `subprocess.Popen`) dies with
`FileNotFoundError`. That 500s `/api/run/new` and `/api/run/start` while the
read path (`/api/chat`, `/chat/messages`) stays 200 — so only "open/restart a
line" breaks. Tell it apart from the version-skew 500 (`engineering.md` §Gateway
Version Skew, which 500s the *read/status* path) by grepping the server log for
the endpoint + traceback (`E.... Exception on /api/run/new [POST]` in
`/usr/local/google/tmp/amply.*.INFO.*`). `_AMPLY_BIN` now resolves from
`os.path.realpath('/proc/self/exe')`, the inode this process holds open and
objfs keeps alive, falling back to `sys.argv[0]`. See
`third_party/py/simply/amply/ux/server.py:_resolve_amply_bin`. A gateway running
the old cached path must still be restarted once: the value was captured at
import time, and the patch only helps future boots.

## The Amply Database Is A Local Spanner Test Universe

**Since 2026-09-05 amply's database is `/span/test-universe/qiaos:amply`,
served by a Spanner test universe (`spanner::test::Env`) running on this
workstation, not by `/span/tmp`.** `/span/tmp/qiaos:amply` lost its write
path on 2026-09-04 (every commit hung, `span getsafetime` deadline-missed,
new workers sat forever at `[amply-startup 1/6]`) and `/span/tmp` stopped
allocating new databases, so the recovery does not depend on Spanner at all.
Old history is still in the old path and is copied over opportunistically
(below).

| Piece | Where | What it does |
|---|---|---|
| Universe host | `~/.amply/localdb/run_localdb.sh` → `bin/localdb` (unit `amply-localdb.service`, or tmux `amply-localdb`) | Starts the universe with CHUBBY_LOCAL, creates the database from `bin/amply_local.sdl.bundle`, restores `snapshots/`, then writes `ready` and `client_flags.txt` |
| Client flags | `~/.amply/localdb/client_flags.txt` | `--spanner_master_lockservice=localhost:<port> --default_ls_watcher=lockservice --lockservice_use_proxy=never`. Every amply process, and `span`, needs them to see the universe. **The port changes on every localdb start, so restart the gateway after localdb.** |
| Gateway | `~/.amply/bin/launch-ux-localdb.sh` (unit `amply-ux.service`, or tmux `amply-ux-local`) | Runs `bin/amply ux --spanner_db=... <flags>` from `~/work`; exports `AMPLY_WORKER_EXTRA_ARGS=<flags>` |
| Worker flags | local patch in `ux/server.py` (`_worker_extra_args`) | Appends `$AMPLY_WORKER_EXTRA_ARGS` to every spawned/resumed worker argv. Without it workers cannot reach the universe |
| Persistence | `~/.amply/localdb/snapshots/` (JSONL per run + `manifest.json`) | The universe is in-memory. localdb writes a delta every 5 min, a full re-dump every 6 h, and a final delta on SIGTERM. On start it publishes `ready` FIRST (gateway back in ~1 min) and restores history in the background, newest runs first, 4 threads (~300 rows/s; 120 runs ≈ 5 min). A crash loses at most 5 minutes; snapshots pause while a restore runs |
| History migration | `~/.amply/localdb/dump_loop.sh` (tmux `amply-dump-loop`) | Every 10 min: `dbtool dump` from the old database with `--schema_bundle` (its metadata path is dead, so the schema comes from the bundle), then `dbtool restore --skip_existing` into the universe. Progress: `dump_loop.log`, `snapshots/runs/*.jsonl` |
| Source | `//experimental/users/qiaos/amply_localdb` (`localdb.py`, `dbtool.py`, `amply_local.sdl`) | Rebuild with `blaze build`, then `~/.amply/localdb/refresh_bin.sh` copies binaries onto local disk (objfs GCs blaze outputs) and repoints their runfiles MANIFEST at that copy |

Health in one line: `cat ~/.amply/localdb/ready ~/.amply/localdb/client_flags.txt`
and `amp-ux-ok`. A query by hand:
`span $(cat ~/.amply/localdb/client_flags.txt) sql /span/test-universe/qiaos:amply`
(it spends a minute failing to reach corp chubby first; the query still runs).

**Do not restore with the search indexes of the real schema.** `amply_local.sdl`
drops the `search_text_substr` n-gram tokenlist (3..12-grams over multi-MB event
JSON): with it, the single-process universe wrote ~15 rows/s and a 120-run
restore took hours with the gateway waiting. Full-text `SEARCH()` still works;
only `include_substring=True` searches fail on the local database.

**Restart order is automatic**: `amply-ux.service` is `PartOf=` +
`After=amply-localdb.service` (a crash-triggered auto-restart of localdb was
observed to restart the gateway too), and `launch-ux-localdb.sh` additionally
exits with 75 when `client_flags.txt` changes under it, so a gateway can never
outlive the universe it was pointed at. `amply_notify` keeps working on the
local database (it reaches the worker's control port, not Spanner).

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
`blaze-out` at a different namespace, which retires the old one. On 2026-09-07
the 17:09 reboot for the sqa-large migration left the database down for 2h11m on
`FileNotFoundError: .../devtools/python/context/__pycache__/g3_context.cpython-313.pyc`
-- a file sitting in `bin/localdb.runfiles/` the whole time. Six failed starts in
seven minutes then hit `StartLimitBurst`, and past that systemd stops retrying on
its own: only `systemctl --user reset-failed` clears it, which is why the outage
outlived the cause by two hours. `~/.amply/localdb/fix_manifest.py` repoints every
external entry at the local copy; it is idempotent, and it refuses to write
anything if some key has no local file, because a half-repointed MANIFEST is
worse than an honestly broken one. `run_localdb.sh` runs it before every start
and `refresh_bin.sh` after every copy, so a rebuild cannot bring the problem
back. Audit by hand with `fix_manifest.py --check` (exit 1 means a repair is
due). The 2026-09-07 repair receipts and the pre-fix MANIFESTs are in
`~/.monitor_prompts/amply_repair_20260907T1924/`.

**A gateway watchdog cannot fix a dead database, so it now checks both.** The
ops watchdog is `~/.tpu_bin/tpu_ops_watchdog.sh` (cron `*/2`, lock
`/tmp/tpu-ops-watchdog.lock`), relocated and slimmed from the retired
`~/work/.monitor_watch/watchdog_selfheal.sh` on 2026-09-10 when the monitor
mechanism was retired; it now supervises ONLY the TPU pipeline + amply infra
(amply-localdb, gateway, tpu-check-daemon, dispatch worker, budget_enforcer) and
no longer starts any monitor alert loop. Its logs are in `~/.tpu_bin/logs/`. The
earlier version (cron, every 2 min) probed only the gateway. Through those 2h11m it therefore restarted the GATEWAY eleven times,
each new one pointed at a database that did not exist, and reported nothing about
the thing that was actually broken. It now also reads `amply-localdb.service`'s
`ActiveState` and, on `failed` or `inactive` only, issues `reset-failed` +
`start`. It deliberately does nothing when the unit is `activating` (a restore
runs for ~40 min after every start, and a restart throws that work away), when
the user bus is unreachable (cron has no `XDG_RUNTIME_DIR`, and an unreadable
state must not read as death), or when the host is starved -- the same guard the
gateway check uses.

**`amp new` takes 75 s on this database, 135 s when the corp-chubby timeout
hits; only the timeout is ours.** Measured 2026-09-06 (load 50-80): ~45 s
importing the worker's Python dependency graph out of the compressed par (55 s
CPU; an uncompressed par saved CPU but not wall time, so it was not adopted),
2 s to create the run, 13 s skill index, 17 s until the first heartbeat makes
the run "live". The extra 60 s comes from the env's
`--lockservice_use_proxy=never`: every client then tries the CORP chubby cell
directly (ACL lookups under `/ls/corp/...`), which is unreachable from a
workstation, and waits out `--lockservice_mount_timeout_secs`. Publishing
`--lockservice_direct_connection_regex=localhost.*` instead (local cell direct,
corp via the proxy) removes it with zero timeouts; localdb now writes that
form, and `~/.amply/localdb/apply_client_flags.sh` switches a running gateway
(which restarts it, killing live runs, so pick the moment).

Traps met while building it:

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

## Host Quick-Stats Utils (`memavail` / `cpuload` / `hstat`)

**One-line host health from `~/.bashrc`, read straight from `/proc` (no deps,
works in any shell).** Check pressure before launching work on this shared
workstation, which overloads (load has hit 102); the cause is the
amply-gateway-restart-loop in `engineering.md` §Do Not Let A Diagnostic Kill The
Thing It Watches.

| Util | Shows |
|---|---|
| `memavail` | Available RAM (allocatable) + used/total + %avail, from `MemAvailable` |
| `cpuload` | Load average + core count + per-core 1-min load; flags `** OVERSUBSCRIBED **` when >1.0/core |
| `hstat` | Both of the above in one call |

Read `cpuload` per-core, not raw. A raw load of 20 is healthy on a 24-core box
(0.83/core) and on fire on an 8-core one (2.5/core). It is meaningless without
its denominator (`engineering.md` §Communicating A Result). The util divides for
you; trust `/core`, not the first column.
