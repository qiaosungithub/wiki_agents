# Agent Web And Jetski

**This page describes `~/work/agent-web-gemini` (branch `gemini-amply`)**, the
active Gemini/Amply/Claude agent web checkout. Identify it by its agent union
`amply | claude | gemini` and the `JETSKI_LS_PORT` pin in its `run.sh`. The
sibling `~/work/agent-web` is an older checkout of the same remote on `main`,
with no Amply and no Jetski wiring; nothing here is a claim about it. The
checkout's own code, native docs, process manager, and live environment outrank
this page. Workstation CLIs: [knowledge/codebases/local-agent-cli.md](local-agent-cli.md). This page is
how the stack is wired; how to run and move it, and the misleading symptoms and
their fixes, are [agent-web-operations skill](../../harness/skills/agent-web-operations/SKILL.md)
and [agent-web-operations skill §Classic bugs and what to do](../../harness/skills/agent-web-operations/SKILL.md#classic-bugs-and-what-to-do).

## One hub owns the whole stack

**`jetski-hub.service` starts `run.sh`, so stopping the hub stops the web app and
the public tunnel together.** Its `sar.server` process runs
`~/work/agent-web-gemini/run.sh`, which starts `node`, `esbuild`, the `jetski-ls`
tmux session, and `cloudflared ... cloudflared-named.yml tunnel run`.

A tmux server first created by `run.sh` belongs to the hub's cgroup, so
`systemctl --user stop jetski-hub` kills every tmux session on that server, not
just `jetski-ls`. Start other long-lived tmux servers from a login or ssh
session.

## Two instances share one identity, separated only by session-name prefix

**The collaborator site shares every agent home and login with the main site;
the only separation is the session display name.** It is `run-lyy.sh`, port
8889, `lyy.kaiming.me`, token `.lyy.token`, cwd `~/lyy-work`. An instance with
`AGENT_WEB_SESSION_NAME_PREFIX="[lyy]"` lists only prefixed sessions, forces the
prefix onto renames, and auto-names a new session `[lyy] <first user message>`
after its first turn. The main `run.sh` hides the prefix via
`AGENT_WEB_SESSION_NAME_HIDE`. Renaming across the boundary hands a session to
the other site; the separation is cooperative and list-level only. Both
instances run as the same Unix user with the same credentials, so a token is
full access to this machine. `tests/session-prefix.mjs` (zero inference) is the
regression test.

## The Claude permission handshake

**`--permission-mode auto` does not make the Claude CLI ask the browser; the
escalation only reaches a client launched with `--permission-prompt-tool
stdio`** — the sentinel the Agent SDK passes when a host supplies a `canUseTool`
callback, turning an ask-decision into a `can_use_tool` control_request on
stdout, answered by a control_response on stdin. Without it every ask is
auto-denied and no prompt appears, looking like the classifier deciding alone.
Answer `allow` by echoing the model's own `input` back as `updatedInput`; the
CLI validates it against the tool's schema. Never forward the CLI's
`permission_suggestions` to a browser: acting on one writes a permanent rule
into settings on behalf of whoever holds the web token.

## The Jetski language server address

**Never inherit `$ANTIGRAVITY_LS_ADDRESS`.** `agentapi` dials it with no
discovery fallback: unset, the only reply is
`{"error": "ANTIGRAVITY_LS_ADDRESS is not set"}`. It names a language server the
jetski CLI hosts on a random port (`--http_server_port ... 0 means random`) that
dies with the CLI session owning it, so a backend started inside a CLI session
freezes that soon-dead port into its environment.

Recognise it: creating a web session appears to succeed and only the first
message fails, with `session id missing`, from `GeminiRunner.runTurn` finding no
session id. The real failure is upstream in `start()`, which swallows the
`agentapi` error into one `console.error` and emits an init with an undefined
session id anyway. Confirm by running `agentapi new-conversation` by hand under
the backend's own environment
(`tr '\0' '\n' < /proc/<pid>/environ | grep ANTIGRAVITY_LS_ADDRESS`): a dead LS
answers `connection refused`.

Resolution: `run.sh` pins `JETSKI_LS_PORT` (default 39899), exports
`ANTIGRAVITY_LS_ADDRESS` itself, and keeps a persistent LS on that port in the
`jetski-ls` tmux session; `--persistent_mode` makes the CLI outlive its client.
Clear the inherited `ANTIGRAVITY_*` variables when starting it, or the new CLI
adopts the dead session's identity. That port is durable only because we own the
listener: never copy a port observed from someone else's session. When the
checkout runs through ESM/`tsx`, keep child-process imports in ESM form
(`import { execFileSync } from "node:child_process"`), not CommonJS `require`.
