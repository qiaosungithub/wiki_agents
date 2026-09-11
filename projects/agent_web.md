# Agent Web And Jetski

**This file describes `~/work/agent-web-gemini` (branch `gemini-amply`)**, the
active Gemini/Amply/Claude agent web checkout. Identify it by its agent union
`amply | claude | gemini` and the `JETSKI_LS_PORT` pin in its `run.sh`. The
sibling `~/work/agent-web` is an older checkout of the same remote on `main`,
with no Amply and no Jetski wiring; nothing here is a claim about it. The
checkout's own code, native docs, process manager, and live environment outrank
this file. Workstation CLIs: `local_agent_cli.md`. Chapter 1 is how the stack is
wired, Chapter 2 how to run and move it, Chapter 3 the misleading symptoms and
their fixes.

---

## Chapter 1 — How The Stack Is Wired

### One hub owns the whole stack

**`jetski-hub.service` starts `run.sh`, so stopping the hub stops the web app and
the public tunnel together.** Its `sar.server` process runs
`~/work/agent-web-gemini/run.sh`, which starts `node`, `esbuild`, the `jetski-ls`
tmux session, and `cloudflared ... cloudflared-named.yml tunnel run`.

A tmux server first created by `run.sh` belongs to the hub's cgroup, so
`systemctl --user stop jetski-hub` kills every tmux session on that server, not
just `jetski-ls`. Start other long-lived tmux servers from a login or ssh
session.

### Two instances share one identity, separated only by session-name prefix

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

### The Claude permission handshake

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

### The Jetski language server address

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

---

## Chapter 2 — Operating The Stack

### Redeploy from a real terminal; the web agent is jailed

**An agent session launched from the web runs inside a bwrap jail (clod): a
private PID namespace and private `/tmp` mean it sees neither the host's
processes nor the tmux socket, so it cannot restart the backend serving it.**
`crontab`, `systemd --user`, setuid binaries, and key-based `ssh localhost` are
all unavailable. It can edit files, commit, build, and reach shared-namespace
ports over localhost. Redeploys go through `deploy-restart.sh` in a real
terminal; the jailed agent verifies over HTTP afterwards. The network namespace
is shared, so port probes and `curl` from inside the jail tell the truth.

### Move the stack between machines: keep the hub on exactly one

**Keep `jetski-hub` inactive on any machine that is not serving the chat.**
Starting the hub on a second machine brings up a second connector for the same
named tunnel, and Cloudflare then splits `gemini.kaiming.me` / `lyy.kaiming.me`
between two hosts while every session lives on one. Move the stack by stopping
hub + `run.sh` + `cloudflared` on the old host before starting the hub on the
new one (`workstation.md`).

### Verify a web instance without spending inference

**A fresh Claude runner emits no `init` event until its first user turn**, so a
probe that opens a session and waits for `init` times out against a healthy
server. The zero-inference health check: ws `open`, then `attach since:0`,
confirm several seconds of silence, then `close` and expect
`runner_closed`/`gone`. A broken spawn answers `agent_exited code=spawn-error`
in the replay within seconds. Only subscribers receive the close events, so the
`attach` is not optional. Confirm separately that `server.log` gained no
`spawn-error` lines.

### Add a new subdomain

**Every new `*.kaiming.me` hostname needs its own proxied CNAME to
`<tunnel-id>.cfargotunnel.com` in the domain owner's Cloudflare dashboard.**
This machine has no `~/.cloudflared/cert.pem`, so `cloudflared tunnel create`
and `route dns` cannot run here. A `cloudflared tunnel login` link dies with its
process after ~10 minutes ("Failed to fetch resource"), so it needs the operator
standing by; the dashboard record has no such deadline. Prefer a `path:` ingress
rule on an existing hostname over a new subdomain: a path route needs no DNS
change, only a tunnel restart.

---

## Chapter 3 — Classic Bugs And What To Do

**This codebase carries features written but never called, so a failing test is
not proof of a regression, and a name on an old "dead" list may since have been
wired: grep for a call site before believing either story.** A websocket message
needs a sender and a handler on both sides — `*_get` in the browser store, its
branch in the server's message switch, the reply handled back in the store.
Definition only means the feature never ran and its bugs were never observable;
has-callers means a real regression. Test files are not call sites.

| Symptom | Cause | Fix |
|---|---|---|
| `CODEX_HOME`, `CODEX_NAME_HELPER`, `CODEX_WEB_BIN`, `CODEX_MODEL` and friends point at `~/.gemini` | these are the *Gemini* slots — Codex was replaced by Gemini without renaming the keys; no `codex` agent exists (the union is `amply \| claude \| gemini`) | nothing to fix; tests or fixtures still naming `codex` are stale |
| Every web "launch Claude" answers `spawn claude ENOENT` while terminal sessions keep working | the backend resolved `claude` from an inherited PATH that lacked `~/.npm-global/bin`; the failure looks like anything but PATH | `run.sh` pins `CLAUDE_WEB_BIN` to an absolute path and refuses to start without one; keep it that way |
| A human UI message gets a tool-oriented reply the message view cannot render | the child carrying it inherited peer-agent identity vars (`ANTIGRAVITY_CONVERSATION_ID`, `ANTIGRAVITY_AGENT_NAME`), so the target reads it as agent-to-agent traffic | remove those vars from that child process; clear only variables whose semantics you have verified, never strip the whole service environment as a generic fix |
