# Agent Web And Jetski

**This file describes `~/work/agent-web-gemini` (branch `gemini-amply`)** — the
active Gemini/Amply/Claude agent web checkout, identifiable by its agent union
`amply | claude | gemini` and the `JETSKI_LS_PORT` pin in its `run.sh`. The
sibling `~/work/agent-web` is an older checkout of the same remote on `main`
with no Amply and no Jetski wiring; nothing here is a claim about it. The
checkout's own code, native docs, process manager, and live environment stay
authoritative over this file; the workstation CLIs are `local_agent_cli.md`.

## Two Things That Look Like Bugs And Are Not

| Looks broken | Actually |
|---|---|
| `CODEX_HOME`, `CODEX_NAME_HELPER`, `CODEX_WEB_BIN`, `CODEX_MODEL` and friends pointing at `~/.gemini` | **These are the *Gemini* slots**: Codex was replaced by Gemini without renaming the keys. There is no `codex` agent — the union is `amply \| claude \| gemini`, and tests or fixtures still naming one are stale. |
| A failing test on a feature you cannot find a caller for | **This codebase carries features that are written but never called**, so a failing test is not proof of a regression — and a name on any old "dead" list may since have been wired. **Grep for a call site before believing either story.** For a websocket message require a sender *and* a handler on both sides (`*_get` in the browser store, its branch in the server's message switch, the reply handled back in the store). Only-the-definition = the feature never ran and its bugs were never observable; has-callers = a real regression. Test files are not call sites. |

## What A Child Process Gets, And Must Not Inherit

**`--permission-mode auto` does not make the Claude CLI ask the browser; the
escalation only reaches a client launched with `--permission-prompt-tool
stdio`** — the sentinel the Agent SDK passes when a host supplies a `canUseTool`
callback, turning an ask-decision into a `can_use_tool` control_request on
stdout, answered by a control_response on stdin. **Without that flag every ask
is auto-denied and no prompt appears**, looking like the classifier deciding
alone. **Answer `allow` by echoing the model's own `input` back as
`updatedInput`** (the CLI validates it against the tool's schema), and **never
forward the CLI's `permission_suggestions` to a browser** — acting on one writes
a permanent rule into settings on behalf of whoever holds the web token.

**When a backend invocation represents a human UI message, remove peer-agent
identity variables such as `ANTIGRAVITY_CONVERSATION_ID` and
`ANTIGRAVITY_AGENT_NAME` from that child process**, or the target classifies it
as agent-to-agent traffic and returns tool-oriented content the human message
view does not render. Clear only variables whose semantics you have verified;
do not strip the whole service environment as a generic fix.

## Two Instances, Separated By Session Name Prefix

**The collaborator site (`run-lyy.sh`, port 8889, `lyy.kaiming.me`, token
`.lyy.token`, cwd `~/lyy-work`) shares every agent home and login with the main
site; the only separation is the session display name.** An instance with
`AGENT_WEB_SESSION_NAME_PREFIX="[lyy]"` lists only prefixed sessions, forces the
prefix onto renames, and auto-names a new session `[lyy] <first user message>`
after its first turn; the main `run.sh` hides the prefix via
`AGENT_WEB_SESSION_NAME_HIDE`. Renaming across the prefix boundary hands a
session to the other site. This is cooperative list-level separation only —
both instances run as the same Unix user with the same credentials, so a token
IS full access to this machine. `tests/session-prefix.mjs` (zero inference) is
the regression test.

## DNS For A New Subdomain

**Every new `*.kaiming.me` hostname needs its own proxied CNAME to
`<tunnel-id>.cfargotunnel.com` in the domain owner's Cloudflare dashboard —
this machine has no `~/.cloudflared/cert.pem`, so `cloudflared tunnel create` /
`route dns` cannot run here.** A `cloudflared tunnel login` link dies with its
process after ~10 minutes ("Failed to fetch resource"), so it only works with
the operator standing by; the dashboard record has no such deadline. Prefer a
`path:` ingress rule on an existing hostname over a new subdomain — a path route
needs no DNS change, only a tunnel restart.

## Verifying A Web Instance Without Spending Inference

**A fresh Claude runner emits NO `init` event until its first user turn — a
probe that opens a session and waits for `init` times out against a healthy
server.** The correct zero-inference health check: ws `open` (a broken spawn
answers `agent_exited code=spawn-error` in the replay within seconds), then
`attach since:0`, confirm several seconds of silence, then `close` and expect
`runner_closed`/`gone` — which only subscribers receive, so the `attach` is not
optional. Confirm separately that `server.log` gained no `spawn-error` lines.

## Claude Binary Resolution

**Never let the backend resolve `claude` from an inherited PATH.** A server
started under a tmux whose PATH lacked `~/.npm-global/bin` answered every web
"launch Claude" with `spawn claude ENOENT` while terminal sessions kept working,
so the failure looked like anything but PATH. `run.sh` now pins `CLAUDE_WEB_BIN`
to an absolute path and refuses to start without one; keep it that way.

## A Web-Launched Agent Cannot Redeploy These Servers

**An agent session launched from the web runs inside a bwrap jail (clod): a
private PID namespace and private `/tmp` mean it sees neither the host's
processes nor the tmux socket; `crontab`, `systemd --user`, setuid binaries, and
key-based `ssh localhost` are all unavailable.** It can edit files, commit,
build, and reach shared-namespace ports over localhost — but cannot kill or
restart the backend serving it. Redeploys go through `deploy-restart.sh` in a
real terminal; the jailed agent verifies over HTTP afterwards. The network
namespace IS shared, so port probes and `curl` from inside the jail tell the
truth.

## Jetski Language Server Address

**Never inherit `$ANTIGRAVITY_LS_ADDRESS`.** `agentapi` dials it with no
discovery fallback (unset, the only reply is
`{"error": "ANTIGRAVITY_LS_ADDRESS is not set"}`), and it names a language
server the jetski CLI hosts on a **random** port (`--http_server_port ... 0
means random`) that dies with the CLI session owning it. A backend started
inside a CLI session freezes that soon-dead port into its environment.

**Recognise it**: creating a web session appears to succeed and only the FIRST
message fails, with `session id missing` — `GeminiRunner.runTurn` finding no
session id. The real failure is upstream in `start()`, which swallows the
`agentapi` error into one `console.error` and emits an init with an undefined
session id anyway. Confirm by running `agentapi new-conversation` by hand under
the backend's own environment
(`tr '\0' '\n' < /proc/<pid>/environ | grep ANTIGRAVITY_LS_ADDRESS`): a dead LS
answers `connection refused`.

**Resolution**: `run.sh` pins `JETSKI_LS_PORT` (default 39899), exports
`ANTIGRAVITY_LS_ADDRESS` itself, and keeps a persistent LS on that port in the
`jetski-ls` tmux session — `--persistent_mode` makes the CLI outlive its client.
Clear the inherited `ANTIGRAVITY_*` variables when starting it, or the new CLI
adopts the dead session's identity. That port is durable only because we own the
listener: **never copy a port observed from someone else's session.**

When the checkout runs through ESM/`tsx`, keep child-process imports in ESM form
(`import { execFileSync } from "node:child_process"`), not CommonJS `require`.
