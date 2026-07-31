# Agent Web And Jetski

Read this only for the Gemini/Amply/Claude agent web checkout. Its current code,
native docs, process manager, and live environment remain authoritative.

## Legacy Names

`CODEX_HOME`, `CODEX_NAME_HELPER`, `CODEX_WEB_BIN`, `CODEX_MODEL` and friends
are the **Gemini** slots. Codex was replaced by Gemini without renaming the
config keys, so a `CODEX_*` value pointing at `~/.gemini` is correct, not a bug.
There is no `codex` agent: the union is `amply | claude | gemini`. Tests and
fixtures still mentioning one are stale.

## Unwired Features

This codebase carries functions and tests for features that were written but
never called from anywhere — `resolveClaudeResumeSettings`, the
`account_status` and `codex_settings` ws messages, `removeClaudeSessionSettings`
and the `inheritedSnapshot` write were all in that state at once. A failing test
here is therefore not proof of a regression. Before debugging one, grep for a
call site: if the only hit is the definition, the feature never ran, and its
bugs (a `Math.max` over two fields nothing populated, for instance) were never
observable.

## Claude Permission Prompts

Running the Claude CLI under `--permission-mode auto` is not enough to make it
ask the browser. The escalation only reaches a client that was launched with
`--permission-prompt-tool stdio` — the sentinel the Agent SDK passes when a host
supplies a `canUseTool` callback. It turns an ask-decision into a
`can_use_tool` control_request on stdout, answered with a control_response on
stdin. **Without that flag every ask is auto-denied and no prompt appears**,
which looks exactly like the classifier deciding on its own.

Answer `allow` by echoing the model's own `input` back as `updatedInput`: the
CLI validates it against the tool's schema, and anything else risks rejection.
Do not forward the CLI's `permission_suggestions` to a browser — acting on one
writes a permanent rule into settings on behalf of whoever holds the web token.

## Sender Identity

When a backend invocation represents a human UI message, remove peer-agent
identity variables such as `ANTIGRAVITY_CONVERSATION_ID` and
`ANTIGRAVITY_AGENT_NAME` from that child process. Otherwise the target can
classify the request as agent-to-agent traffic and return tool-oriented content
that the human message view does not render.

Clear only the variables whose semantics have been verified. Do not strip the
entire service environment as a generic fix.

## Jetski Language Server Address

`agentapi` dials `$ANTIGRAVITY_LS_ADDRESS` and has no discovery fallback: unset
it and the only reply is `{"error": "ANTIGRAVITY_LS_ADDRESS is not set"}`. That
address is a language server the jetski CLI hosts on a **random** port
(`--http_server_port ... 0 means random`) which dies with the CLI session owning
it. An inherited address is therefore a liability — a backend started from
inside a CLI session freezes that session's port into its environment and keeps
dialing it long after the session is gone.

**Recognise it:** creating a web session appears to succeed and only the FIRST
message fails, with `session id missing`. That string is `GeminiRunner.runTurn`
finding no session id; the real failure is upstream in `start()`, which swallows
the `agentapi` error into one `console.error` and emits an init carrying an
undefined session id anyway. Confirm by running `agentapi new-conversation` by
hand under the backend's own environment
(`tr '\0' '\n' < /proc/<pid>/environ | grep ANTIGRAVITY_LS_ADDRESS`); a dead LS
answers `connection refused`.

**Resolution:** do not inherit the address. `run.sh` pins `JETSKI_LS_PORT`
(default 39899), exports `ANTIGRAVITY_LS_ADDRESS` itself, and keeps a persistent
LS on that port in the `jetski-ls` tmux session — `--persistent_mode` is the flag
that makes the CLI outlive its client. Clear the inherited `ANTIGRAVITY_*`
variables when starting it, or the new CLI adopts the dead session's identity.
The port is durable only because we own the listener; never copy a port observed
from someone else's session.

When the checkout runs through ESM/`tsx`, keep child-process imports in ESM form
(for example, `import { execFileSync } from "node:child_process"`) rather than
mixing in CommonJS `require`.
