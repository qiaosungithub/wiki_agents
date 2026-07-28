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

## Jetski Hub Address

Treat `ANTIGRAVITY_LS_ADDRESS` as dynamic. Prefer a managed Jetski sidecar; when
using tmux or another long-lived process manager, pass the current address
explicitly to the service and verify the child environment. Recreating a tmux
session does not prove that stale server-global environment was replaced, and a
previous numeric port is never durable configuration.

When the checkout runs through ESM/`tsx`, keep child-process imports in ESM form
(for example, `import { execFileSync } from "node:child_process"`) rather than
mixing in CommonJS `require`.
