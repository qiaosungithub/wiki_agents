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

**Two failure modes explain every crash so far, and neither comes from running
many sessions at once:**

| Mode | Why a retry does not save it |
|---|---|
| `AnthropicError: Overloaded` | A transient upstream 529 arrives as an error chunk *after* the stream opened, so `num_retries` cannot cover it; litellm turns it into `MidStreamFallbackError`, which escapes `run()` and marks that one session `crashed`. |
| Event too large | A tool result over the Spanner column limit (10 MiB on `EventSearchIndex.search_text_substr`) fails the write and kills the thread, and `INVALID_ARGUMENT` is not retryable. **`view_file` base64-encodes images**, inflating by 4/3, so the real per-file ceiling is ~7.5 MB — measuring a file and calling it "under 10 MB, safe" is how this recurs. |

`web_search` is registered unconditionally with no flag to disable it, and this
host's LOAS credential cannot reach superroot, so every call fails and dumps a
permission wall into the log. Noise rather than a cause of crashes, but it is
why run logs reach hundreds of MB.

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
