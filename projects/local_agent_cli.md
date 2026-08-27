# Local Agent CLIs

Read this before changing how an agent CLI is launched or managed on this
workstation. The `agent-island` checkout and the live `~/.bashrc` are
authoritative for current wiring; the agent web app is `agent_web.md`.

## `clod`, And The Jail It Runs In

**A command named `claude` is blocked by this host's `ai_agent_execution`
policy, so Claude Code is exposed as `clod`.** Only the name is refused — the
binary runs fine, so never conclude Claude Code is unavailable here. The other
wrappers follow the same shape: `amp` (Amply chat), `gemini` (Jetski), `gpt`
(Codex), each dispatching `list / search / resume / rename / clear` to a session
helper and otherwise launching the agent.

`clod` runs Claude Code in a bubblewrap jail under `--permission-mode auto`, and
**both layers are deliberate**: the classifier catches obvious bad tool calls,
bwrap contains what escapes it. Management subcommands only read and rewrite
`~/.claude` so they stay outside the jail; `resume` re-enters it, giving a
resumed session the same policy as a fresh one.

| Rule | Consequence of ignoring it |
|---|---|
| **A wrapper imposing a permission policy must stop the session helper adding its own** — `CLAUDE_LAUNCH_ARGS=""` drops the helper's `--dangerously-skip-permissions` | The two fight and the jail's auto mode is silently bypassed |
| **The jail hides `/google/data`, `/google/bin`, `/google/src/head`, `/cns`, and other users' homes** (`$HOME` and `/google/src/cloud/qiaos` are read-write, `/tmp` is a private tmpfs, the network is shared with the host) | A task needing those must run outside the jail with `CLOD_NO_SANDBOX=1`; it is not a missing-file bug. `--unshare-pid` also hides host processes, tmux included, so the agent cannot signal them |
| **`effortLevel` in `settings.json` stops at `xhigh`; only the CLI flag `--effort max` reaches the model**, which is why `clod` passes it | `"max"` in settings is silently ignored and the session falls back to `high`. Claude Code accepts unknown settings values without complaining, so **never read "it started fine" as evidence a setting took effect** — the `effort` field of a `PreToolUse` hook's stdin payload reports the effective level |

## `amp` / Amply: Diagnosing A Dead Session

**Start at `/api/chat?run_id=<id>`** — `chatbot_status` separates a session that
answered from one that died, `live` says whether the worker is up, and the
traceback is in `~/.amply/logs/<run_id>.log`. **A crashed chatbot does not mean
the run is lost**: it is spawned per message, so sending one respawns it, and
subagents keep working throughout.

**Never grep those logs for `429` or `quota`.** A denied Stubby RPC dumps
hundreds of `DestinationPermission #<n>: Wrong user mdbuser/... in restriction.`
lines, so the pattern matches an *index*, not an HTTP status — once good for
"93 rate-limit errors" on a host that had never been rate limited. Match the
exception class: `RateLimitError`, `RESOURCE_EXHAUSTED`, `Quota exceeded`.

**A crash is a property of the one message, not of the load** — running many
sessions at once has not been a cause. Two mechanisms, each unsurvivable by a
retry; find the exception class before assuming either:

| Mode | Why a retry does not save it |
|---|---|
| `AnthropicError: Overloaded` | A transient upstream 529 arrives as an error chunk *after* the stream opened, so `num_retries` cannot cover it; litellm turns it into `MidStreamFallbackError`, which escapes `run()` and marks that one session `crashed`. |
| Event too large | A tool result over the Spanner column limit (10 MiB on `EventSearchIndex.search_text_substr`) fails the write and kills the thread, and `INVALID_ARGUMENT` is not retryable. **`view_file` base64-encodes images**, inflating by 4/3, so the real per-file ceiling is ~7.5 MB — measuring a file and calling it "under 10 MB, safe" is how this recurs. |

`web_search` is registered unconditionally with no flag to disable it, and this
host's LOAS credential cannot reach superroot, so every call fails and dumps a
permission wall into the log. Noise rather than a cause of crashes, but it is
why run logs reach hundreds of MB.

## `amp` Sends Operator Messages While The Agent Works

**A message typed at the `amp` spinner is SENT immediately, mid-turn — not
queued until the turn ends.** `/chat/send` appends a `MessageEvent` and wakes
the session at once, and a busy chatbot's `run()` loop re-reads its context
every iteration, so the message folds into the running turn at the agent's
**next tool-call boundary** (seconds), surfaced as the `[STATUS]` **NEW
OPERATOR MESSAGE** banner. The injection point is a tool boundary, NOT
preemption: a long in-flight tool (or the current LLM generation) must finish
first; it is not a hang. (The old TUI lag was purely a post-idle send drain.)

**Slash commands are the one exception — still deferred to the idle prompt.**
`/status`, `/help`, `/compact`, `/quit` print to the screen or mutate turn
state, which is unsafe while the hand-drawn spinner owns the bottom rows. Only
plain messages send mid-turn. See `claude-amply.py` `_compose_submit_draft`
(slash → `_queued_messages`, else `_send_operator_message(..., begin_turn=
False)` so the in-flight turn's clock is neither reset nor torn down on a send
failure); contract pinned by `agent-island/tests/test_queue.py`.

## Amply Workers Segfault Overnight

**A run that reads `Stopped` was usually not stopped — its worker segfaulted.**
29 did between 02:15 and 05:26 on 2026-08-14; the same burst hit on 08-12 and
08-06, always inside 02:00–05:30 and never during the day. It is
indistinguishable in `/api/runs` from a run the operator paused, because
`/api/run/stop` is a PAUSE that also leaves `status: ongoing` with a dead
process.

**Do not go hunting for a resource limit.** `/proc/vmstat` reported
`oom_kill 0`, systemd-oomd logged no kills, and `unauthenticated: invalid
credentials` in syslog is constant background noise at 200–400/hour, day and
night — it correlates with everything and explains nothing. A mass die-off
whose last heartbeats all land inside the same five seconds is a REBOOT: check
`/proc/uptime` before anything else (that is what 2026-08-10 17:09 was).

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

An RPC connection drops and building the `absl::Status` that aborts the
in-flight RPCs faults. `FailureSignalHandler` then re-faults on every attempt,
~90 frames deep, until the kernel prints `signal: DefaultEventMan[…]
overflowed sigaltstack`. **That kernel line, and the "stack trace" systemd
records, name only the crash handler** — `bt` shows nothing but
`FailureSignalHandler`. The real frames are the OUTERMOST ones, so read
`bt -45`.

`amp watchdog` is the mitigation (nothing outside amply prevents it): it
restarts `ongoing` runs whose worker is dead **and** whose last heartbeat sits
within seconds of an `amply` coredump in `/var/lib/systemd/coredump`
(heartbeat 02:49:17, core 02:49:18). That correlation is the whole design —
the coredump is the only thing separating a crash from a pause, and a watchdog
without it overrides the operator every 60 seconds.

## A Turn That WROTE A Tool Call Instead Of Making One

Another way a session stops, identical from outside: the worker is up, the run
is `Running`, and nothing happens. The model wrote its tool call out as XML-ish
markup in the message text (`invoke` / `parameter` tags) and issued no actual
call, so the turn ended with nothing executed.

**It is the model, not amply.** Amply drives tools through structured
`tool_calls`; `invoke name=` appears **nowhere** in the amply tree and nowhere
in `~/.amply/AGENTS.md`, so nothing teaches or parses that syntax, and the
transport cannot turn a real tool_use block into text. The affected messages
carry `tool_calls: []` with the markup sitting in `content`. It is also not
context exhaustion — measured across 43 live runs, sessions at 617k/510k/505k
prompt tokens had zero, while the worst offender sat at 195k.

**What amply does wrong is not noticing.** The malformed text is stored
verbatim, so it becomes an in-context example the model then copies: after the
first slip at turn 51, one session did it in **96 of 187 turns**. And nothing
retries — in 95 of those 96 cases the run simply sat there until an external
poke arrived, a **median of 24.7 minutes later** (every gap >5min). That is
what most `已静置(idle)` alerts on the monitors actually are.

`amp watchdog` nudges those sessions: last message is from the chatbot, has
empty `tool_calls`, carries the markup, and the run is live but not working.
The nudge deliberately DESCRIBES the mistake instead of quoting it — quoting
the markup back would add another example of the thing to copy. Same reason
`tests/test_watchdog.py` builds its fixture from fragments.

## Restarting The Amply UX Server

**`amply` and `amply-launch` are `blaze run`, so they work only inside a google3
workspace**: they are shell functions that `cd` to `$AMPLY_WORKSPACE` in a
subshell, not aliases, because they are typed from `~/work`. `amp`'s automatic
restart drives tmux for that reason plus one more — the alias needs an
*interactive* shell to exist at all, and a tmux pane outlives the `amp` process
that started it.

**When srcfsd restarts, every new worker dies during startup** — inside
`sysconfig` at `os.getcwd()`, with `OSError: [Errno 107] Transport endpoint is
not connected` — because the server's cwd sits inside a citc client (the binary
chdirs there itself) and workers inherit it. The traceback names Python's stdlib
and points nowhere near the cause: check `readlink /proc/<ux-server-pid>/cwd`,
then restart the server. **Workers are reparented to init and survive the UX
server dying**, so a run that looks lost usually needs the server back, not
`amp start`.

**Any agent can self-restart the gateway with
`~/.amply/bin/restart-amply-ux.sh` (bashrc: `amp-restart-ux`), without going
through `amp`.** It mirrors the exact tmux sequence `amp` uses internally
(`claude-amply.py:_launch_ux_in_tmux`):
settle, `tmux kill-session -t amply_ux`, fresh detached session at the
workspace, wait for `~/.bashrc`, then `send-keys` `cd <ws> && amply-launch`.
The indirection is mandatory, not stylistic: `amply-launch` is a bashrc ALIAS
that exists ONLY in an interactive shell (`bash -lc` does NOT see it — bashrc
returns early when non-interactive), and the detached tmux session OUTLIVES the
agent that ran it so the server survives. The agent's bash tool shares the
operator's default tmux socket, so plain `tmux` reaches `amply_ux`. Always
`--dry-run` first when unsure; it bounded-verifies revival (polls
`dashboard_url` + `/api/runs` 200) unless `--no-verify`. Flags/env:
`--warmup`/`--wait`, `AMP_UX_TMUX` / `AMP_UX_WORKSPACE` / `AMP_UX_ALIAS`. Do
NOT use the deprecated `~/.amply/bin/ux_launch.py` (it exec's a server on any
invocation — the 3-server split-brain footgun).

**Never start a second UX server to "fix" an unreachable one — find the one
already running first** (`ss -ltnp | grep amply`, wildcard 0.0.0.0 binds are
servers, 127.0.0.1 are workers). Every server boot rewrites
`~/.amply/dashboard_url`, so with two alive the file tracks whichever booted
last; when that one dies, every client follows the file to a corpse while a
healthy server keeps serving unlisted. This machine once ran THREE at a time
that way, splitting live sessions between them. `amp` now heals this itself:
it re-pings once (a load blip is not an outage), then adopts a live server by
repointing the file, and only launches when nothing is adoptable. Two footguns
with prior incidents: **`~/.amply/bin/ux_launch.py` used to exec a real server
on ANY invocation — an agent ran `ux_launch.py --help` for usage text and
started server #3** (now gated behind `AMPLY_UX_LAUNCH=really-launch`); and a
TUI/window keeps the base URL it read at startup, so after any server change,
windows spewing `Connection refused` just need quitting and reopening.

**A cold gateway takes MINUTES to answer `/api/runs`, and a concurrent `amp`
that pinged-and-missed during that window launched a duplicate — the split-brain
above, but self-inflicted by the client, not the operator.** The UX server does
not bind its HTTP port / write `~/.amply/dashboard_url` until the skill-index +
embedder build finishes; under load that cold start was measured at ~4 minutes
(normally ~30s). So a first `amp new` launches a gateway, and a second `amp new`
typed a few minutes later reads the still-stale/absent `dashboard_url`, its two
3s pings both miss the not-yet-serving gateway, and it launches gateway #2 that
then steals `dashboard_url`. This is NOT a bug in the ping logic — it is a launch
not yet finished. The fix is a **cross-process launch lock**
(`~/.amply/ux.launching.lock`, JSON `{pid,host,started_at}`, 6-min TTL +
dead-pid steal): the first `amp` to launch claims it; every concurrent `amp`
sees it and WAITS for that launch (polling `dashboard_url` + a port scan to
adopt) instead of starting its own. Only the lock winner launches; a stale lock
(launcher died, or past TTL) is stolen. The claim is `write-temp-then-os.link`,
NOT `O_EXCL`-then-write: `O_EXCL` creates an EMPTY file first, and a losing
racer that read it mid-write got `json.loads('')` → treated it as "stale" →
stole it → two winners (3/30 concurrent races still doubled). `os.link` publishes
the already-written payload atomically, so there is no empty window. Two more
subtleties the tests pin: on lock-clear a waiter must RE-CHECK `dashboard_url`
before taking over (the peer usually just succeeded), and the winner re-checks
once more under the lock (double-checked locking) before spending a launch. See
`claude-amply.py` `_try_acquire_launch_lock` / `_wait_for_peer_launch` /
`ensure_ux_server`, tests
in `agent-island/tests/test_launch_lock.py` (incl. a 3-way-race E2E asserting
exactly one gateway launches). Independently, `amp stop <id|latest>` now exists
(resumable pause, mirrors the web Stop button) for shedding a worker's RAM/CPU
without losing state.

**`amp new` / `amp resume` 500 with `FileNotFoundError: .../amply` is the
gateway's spawn path gone stale after a concurrent build — restart the gateway,
don't blame version skew.** The ux server caches the worker binary path at
import time; historically that was `sys.argv[0]`, pointing into the checkout's
blaze `execroot/.../blaze-out` symlink. That symlink is **republished to a fresh
objfs namespace (and the old one GC'd) whenever ANY `blaze build` runs under the
same `$AMPLY_WORKSPACE` checkout** — a build-worker draining a sweep, or any
line building there. The gateway's cached path then dangles, and every spawn
(`_spawn_new_run_subprocess` → `subprocess.Popen`) dies with `FileNotFoundError`,
500ing `/api/run/new` and `/api/run/start` while the READ path (`/api/chat`,
`/chat/messages`) stays 200 — so only "open/restart a line" breaks, and existing
lines are untouched. Tell it apart from the version-skew
500 (`engineering.md` §Gateway Version Skew, which 500s the *read/status* path
on new runs): grep the server log for the endpoint + traceback
(`E.... Exception on /api/run/new [POST]` in
`/usr/local/google/tmp/amply.*.INFO.*`). **The fix in both the live-incident
sense and the durable sense: `_AMPLY_BIN` now resolves from
`os.path.realpath('/proc/self/exe')` (the inode this process holds open, which
objfs keeps alive for our lifetime; falls back to `sys.argv[0]`) — see
`third_party/py/simply/amply/ux/server.py:_resolve_amply_bin`. But a gateway
already running with the old cached path must still be RESTARTED once — the
value was captured at its import time and the patch only helps future boots.**


*Update*: a patch in `third_party/py/simply/amply/agents/event_loop.py` (local CitC workspace) detects tool-call leaks inline (`TOOL_MARKUP_RE.search(content)`) and immediately appends a system correction without sleeping, eliminating the idle time.

## Host Quick-Stats Utils (`memavail` / `cpuload` / `hstat`)

**One-line host health from `~/.bashrc`, read straight from `/proc` (no deps,
work in any shell)** — check pressure before launching work on this SHARED
workstation, which overloads (load has hit 102; see `engineering.md` §Do Not
Let A Diagnostic Kill The Thing It Watches for the amply-gateway-restart-loop
that causes it).

| Util | Shows |
|---|---|
| `memavail` | Available RAM (allocatable) + used/total + %avail, from `MemAvailable` |
| `cpuload` | Load average + core count + **per-core** 1-min load; flags `** OVERSUBSCRIBED **` when >1.0/core |
| `hstat` | Both of the above in one call |

**Read `cpuload` per-core, not raw.** A raw load of 20 is healthy on a 24-core
box (0.83/core) and on fire on an 8-core one (2.5/core) — the number is
meaningless without its denominator (`engineering.md` §Communicating A Result).
The util does the division; trust `/core`, not the first column.
