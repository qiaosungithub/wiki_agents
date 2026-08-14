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

Nothing outside amply prevents it. `amp watchdog` is the mitigation: it
restarts `ongoing` runs whose worker is dead **and** whose last heartbeat sits
within seconds of an `amply` coredump in `/var/lib/systemd/coredump`
(heartbeat 02:49:17, core 02:49:18). That correlation is the whole design —
the coredump is the only thing separating a crash from a pause, and a watchdog
without it overrides the operator every 60 seconds.

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
