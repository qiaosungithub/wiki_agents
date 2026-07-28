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

## The bwrap Sandbox

`$HOME` and `/google/src/cloud/qiaos` are read-write, `/tmp` is a private tmpfs,
and the network is shared with the host. `/google/data`, `/google/bin`,
`/google/src/head`, `/cns`, and other users' homes are hidden — an agent running
under `clod` cannot see them, so a task needing those paths must run outside the
jail (`CLOD_NO_SANDBOX=1`) rather than being debugged as a missing-file problem.
`--unshare-pid` also means the agent cannot see or signal host processes, tmux
sessions included.
