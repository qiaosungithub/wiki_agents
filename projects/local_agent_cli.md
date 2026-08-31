# Local Agent CLIs

Read this before changing how an agent CLI is launched or managed here. The
`agent-island` checkout and the live `~/.bashrc` are authoritative for current
wiring; the agent web app is `agent_web.md`.

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

## A Turn That WROTE A Tool Call Instead Of Making One

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

**`amply` and `amply-launch` are `blaze run`, so they work only inside a google3
workspace.** They are shell functions, not aliases: typed from `~/work`, they
`cd` to `$AMPLY_WORKSPACE` in a subshell. `amp`'s automatic restart drives tmux
for that reason and one more. The alias needs an *interactive* shell, and a tmux
pane outlives the `amp` process that started it.

When srcfsd restarts, every new worker dies at startup inside `sysconfig` at
`os.getcwd()`, with `OSError: [Errno 107] Transport endpoint is not
connected`. The server's cwd sits inside a citc client (the binary chdirs there
itself) and workers inherit it. The traceback names Python's stdlib, nowhere
near the cause: check `readlink /proc/<ux-server-pid>/cwd`, then restart the
server. Workers reparent to init and survive the UX server dying, so a run that
looks lost usually needs the server back, not `amp start`.

Any agent can self-restart the gateway with `~/.amply/bin/restart-amply-ux.sh`
(bashrc: `amp-restart-ux`), bypassing `amp`. It mirrors the internal `amp` tmux
sequence (`claude-amply.py:_launch_ux_in_tmux`): settle,
`tmux kill-session -t amply_ux`, fresh detached session at the workspace, wait
for `~/.bashrc`, `send-keys` `cd <ws> && amply-launch`. The tmux indirection is
mandatory. `amply-launch` is a bashrc alias existing only in an interactive
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
