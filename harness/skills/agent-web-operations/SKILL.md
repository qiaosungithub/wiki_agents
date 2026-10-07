---
name: agent-web-operations
description: Redeploy, move between machines, health-check, or add a subdomain to the agent web / Jetski stack (`~/work/agent-web-gemini`), and triage its classic misleading bugs.
---

# Operate The Agent Web Stack

Read [knowledge/codebases/agent-web.md](../../../knowledge/codebases/agent-web.md) first for how the stack is wired: the hub,
the two instances, the Claude permission handshake, and the Jetski language
server address. The workstation side of the hub is
[knowledge/environment/workstation.md §Jetski Hub Starts The Web App; Start It On One Machine Only](../../../knowledge/environment/workstation.md#jetski-hub-starts-the-web-app-start-it-on-one-machine-only);
workstation CLIs are [knowledge/codebases/local-agent-cli.md](../../../knowledge/codebases/local-agent-cli.md). This skill owns
operating the stack and the classic bugs and what to do.

## Redeploy from a real terminal; the web agent is jailed

**An agent session launched from the web runs inside a bwrap jail (clod): a
private PID namespace and private `/tmp` mean it sees neither the host's
processes nor the tmux socket, so it cannot restart the backend serving it.**
`crontab`, `systemd --user`, setuid binaries, and key-based `ssh localhost` are
all unavailable. It can edit files, commit, build, and reach shared-namespace
ports over localhost. Redeploys go through `deploy-restart.sh` in a real
terminal; the jailed agent verifies over HTTP afterwards. The network namespace
is shared, so port probes and `curl` from inside the jail tell the truth.

## Move the stack between machines: keep the hub on exactly one

**Keep `jetski-hub` inactive on any machine that is not serving the chat.**
Starting the hub on a second machine brings up a second connector for the same
named tunnel, and Cloudflare then splits `gemini.kaiming.me` / `lyy.kaiming.me`
between two hosts while every session lives on one. Move the stack by stopping
hub + `run.sh` + `cloudflared` on the old host before starting the hub on the
new one ([knowledge/environment/workstation.md](../../../knowledge/environment/workstation.md)).

## Verify a web instance without spending inference

**A fresh Claude runner emits no `init` event until its first user turn**, so a
probe that opens a session and waits for `init` times out against a healthy
server. The zero-inference health check: ws `open`, then `attach since:0`,
confirm several seconds of silence, then `close` and expect
`runner_closed`/`gone`. A broken spawn answers `agent_exited code=spawn-error`
in the replay within seconds. Only subscribers receive the close events, so the
`attach` is not optional. Confirm separately that `server.log` gained no
`spawn-error` lines.

## Add a new subdomain

**Every new `*.kaiming.me` hostname needs its own proxied CNAME to
`<tunnel-id>.cfargotunnel.com` in the domain owner's Cloudflare dashboard.**
This machine has no `~/.cloudflared/cert.pem`, so `cloudflared tunnel create`
and `route dns` cannot run here. A `cloudflared tunnel login` link dies with its
process after ~10 minutes ("Failed to fetch resource"), so it needs the operator
standing by; the dashboard record has no such deadline. Prefer a `path:` ingress
rule on an existing hostname over a new subdomain: a path route needs no DNS
change, only a tunnel restart.

## Classic bugs and what to do

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
