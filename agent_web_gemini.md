# Agent Web (Gemini)

This project contains a web interface for Gemini / Codex / Claude agents. This document persists lessons learned and potential pitfalls during deployment and configuration.

## Key Troubleshooting Takeaways & Gotchas

### 1. Jetski `agentapi` Sender Identity Confusion (Subagent vs Human User)
- **Symptom:** When a message is sent to a target Jetski conversation via the UI, the target agent successfully replies, but the UI fails to render the message (showing up as a "Tool Use" or remaining blank). In the conversation logs, the agent generates a `<SYSTEM_MESSAGE>` or `send_message` tool execution instead of natural conversational `content`.
- **Root Cause:** Background environments (like the CLI or backend `node` process) spawned by a Jetski Agent will unknowingly inherit the parent agent's `ANTIGRAVITY_CONVERSATION_ID`, `ANTIGRAVITY_AGENT_NAME`, etc. When `agentapi send-message` executes with these inherited environment variables, the target session reads the metadata and perceives the message as a subagent request/peer-to-peer transmission rather than a human prompt. Consequently, it defaults to using the `send_message` API tool directly to write a programmatic response, thereby bypassing the typical human-facing `text` UI pipeline.
- **Fix:** Purge `ANTIGRAVITY_CONVERSATION_ID` and `ANTIGRAVITY_AGENT_NAME` from the environment when wrapping `agentapi` execution inside application code to ensure the target session interprets it as standard human user interaction.

### 2. Tmux Environment Variable Inheritance / Port Expiry (`ANTIGRAVITY_LS_ADDRESS`)
- **Symptom:** Server execution arbitrarily throws `connection refused` on a specific port (e.g. `39489`) when trying to dial Jetski Hub. The port was historically valid but expired when Hub daemon restarted and claimed a new port.
- **Root Cause:** `tmux` implements a client/server architecture. `tmux new-session` inherently copies the environment from the **original `tmux` server process** at its inception, *not* from the local shell creating the session. If the daemon restarted and you merely kill the `tmux` session and recreate it using a shell carrying the fresh `ANTIGRAVITY_LS_ADDRESS`, the new session will unexpectedly inherit the outdated port from the background server.
- **Fix:** Explicitly inject the environment variables needed when passing the bash command argument, such as: `tmux new-session -d -s session_name "env ANTIGRAVITY_LS_ADDRESS=$ANTIGRAVITY_LS_ADDRESS bash run.sh"`, or preferably, wrap the service inside a managed **Jetski Sidecar** (`~/.gemini/config/sidecars/`) which correctly propagates dynamic environment variables on daemon resets.

### 3. Node ESM vs. CommonJS execution via `tsx`
- **Symptom:** `require is not defined` traceback when spawning standard Node built-in child processes.
- **Root Cause:** Trying to execute `.ts` scripts or dynamic scripts requiring inline execution within a `tsx` loaded environment using CommonJS `require(...)` constructs.
- **Fix:** Enforce standard ESM static imports (`import { execFileSync } from "node:child_process";`) globally at module tops when operating within NextJS-like or `tsx`-transpiled environments.
