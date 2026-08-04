# Local Agent CLIs

Read this before changing how an agent CLI is launched or managed on this
workstation. The `agent-island` checkout and the live `~/.bashrc` remain
authoritative for the current wiring.

## Command Names

A command named `claude` is blocked by this host's `ai_agent_execution` policy.
Claude Code is exposed as **`clod`** instead. The binary itself runs fine — only
the name is refused — so do not conclude that Claude Code is unavailable here.

The other wrappers follow the same shape: `amp` for Amply's chat CLI, `gemini`
for Jetski, `gpt` for Codex. Each dispatches `list / search / resume / rename /
clear` to a session helper and otherwise launches the agent.

## `clod`

`clod` runs Claude Code inside a bubblewrap jail with `--permission-mode auto`.
The two layers are deliberate: the classifier catches obvious bad tool calls,
bwrap contains whatever escapes it. Management subcommands only read and rewrite
`~/.claude`, so they stay outside the jail; `resume` re-enters it, so a resumed
session gets the same policy as a fresh one.

When a wrapper already imposes a permission policy, it must stop the session
helper from adding its own: `CLAUDE_LAUNCH_ARGS=""` drops the helper's
`--dangerously-skip-permissions`. Otherwise the two fight and the jail's auto
mode is silently bypassed.

## Effort

`settings.json`'s `effortLevel` enum stops at `xhigh`. Writing `"max"` there is
**silently ignored** and the session falls back to `high` — no warning, no error.
Only the CLI flag `--effort max` actually reaches the model, which is why `clod`
passes it. Claude Code accepts unknown settings values without complaining, so
never treat "it started fine" as evidence a setting took effect.

To verify what a session is really running with, read the `effort` field of a
`PreToolUse` hook's stdin payload; it reports the session's effective level.

## `amp` / Amply: Diagnosing A Dead Session

`/api/chat?run_id=<id>` is the first stop: `chatbot_status` distinguishes a
session that answered from one that died, and `live` says whether the worker is
still up. The traceback is in `~/.amply/logs/<run_id>.log`. A crashed chatbot
does **not** mean the run is lost — the chatbot is spawned per message, so
sending one respawns it, and subagents keep working throughout.

Do not grep those logs for `429` or `quota`. A denied Stubby RPC dumps hundreds
of `DestinationPermission #<n>: Wrong user mdbuser/... in restriction.` lines,
so those patterns match an *index*, not an HTTP status. Counting them once
produced "93 rate-limit errors" from a host that had never been rate-limited.
Match on the exception class instead (`RateLimitError`, `RESOURCE_EXHAUSTED`,
`Quota exceeded`).

Two failure modes account for the crashes seen so far, and neither is caused by
running many sessions at once:

* **`AnthropicError: Overloaded`.** A transient upstream 529 that arrives as an
  error chunk *after* the stream opened, so `num_retries` cannot cover it;
  litellm turns it into `MidStreamFallbackError`, which escapes `run()` and
  flips the session to `crashed`. One blip costs one session.
* **Event too large.** A tool result over the Spanner column limit
  (10 MiB on `EventSearchIndex.search_text_substr`) fails the write and kills
  the thread. `INVALID_ARGUMENT` is not retryable, so it fails again on retry.
  **`view_file` base64-encodes images**, inflating by 4/3 — the real ceiling on
  a file is ~7.5 MB, not 10. Measuring the file and concluding "under 10 MB, safe"
  is how this recurs.

`web_search` is registered unconditionally with no flag to disable it, and this
host's LOAS credential cannot reach superroot, so every call fails and dumps the
permission wall into the log. It is noise, not a cause of crashes — but it is
why run logs reach hundreds of MB.

## Restarting The Amply UX Server

`amply` and `amply-launch` are `blaze run`, which only works from inside a
google3 workspace — as plain aliases they failed from `~/work`, where they are
actually typed. They are shell **functions** now, each `cd`-ing to
`$AMPLY_WORKSPACE` in a subshell. `amp`'s automatic restart drives tmux for the
same reason plus one more: the alias needs an *interactive* shell to exist at
all, and a tmux pane outlives the `amp` process that started it.

The server's cwd ends up inside a citc client either way (the binary chdirs
there itself), and workers inherit it. So when srcfsd restarts, every new worker
dies during startup — inside `sysconfig`, at `os.getcwd()`, with
`OSError: [Errno 107] Transport endpoint is not connected`, long before any
amply code runs. The traceback names Python's stdlib and points nowhere near the
cause; check `readlink /proc/<ux-server-pid>/cwd` and restart the server.

Workers are reparented to init, so they survive the UX server dying — a run that
looks lost usually just needs the server back, not `amp start`.

## The bwrap Sandbox

`$HOME` and `/google/src/cloud/qiaos` are read-write, `/tmp` is a private tmpfs,
and the network is shared with the host. `/google/data`, `/google/bin`,
`/google/src/head`, `/cns`, and other users' homes are hidden — an agent running
under `clod` cannot see them, so a task needing those paths must run outside the
jail (`CLOD_NO_SANDBOX=1`) rather than being debugged as a missing-file problem.
`--unshare-pid` also means the agent cannot see or signal host processes, tmux
sessions included.
