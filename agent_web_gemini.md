# Agent Web And Jetski

Read this only for the Gemini/Codex/Claude agent web checkout. Its current code,
native docs, process manager, and live environment remain authoritative.

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
