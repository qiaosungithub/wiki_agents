# Tools

Executable helpers. Everything else in `wiki_agents/` is prose. A tool lives
here when a script enforces a rule more reliably than a paragraph someone has
to remember.

| Tool | Use it when | Owning guide |
|---|---|---|
| `jetski_send.py` | You need to message a Jetski conversation, or feed it several messages one per turn. `find` and `status` are read-only; `send` and `feed` wait for IDLE, always pass `--model`, and exit non-zero unless an assistant reply follows each message. `--interrupt` is the only way to send into a running turn. | [agent-messaging skill](../harness/skills/agent-messaging/SKILL.md) |
| `limit_order.sh` | A job is pending and you suspect a GQM price cap; or you need to set/remove one. Read-first: `status` shows live price vs every cap and marks each BLOCKING/ok. Writes are dry-run unless `--apply`; group scope also needs `--i-understand-group-scope`. | [knowledge/infrastructure/market.md §Price Caps (Limit Orders)](../knowledge/infrastructure/market.md#price-caps-limit-orders) |

**A tool here must be safe to run blind.** Default to read-only, make the
destructive path opt-in with an explicit flag, and print what it compares
against, not only a verdict.
