# Tools

Executable helpers. Everything else in `wiki_agents/` is prose; these are the
cases where a rule is enforced more reliably by a script than by a paragraph
someone has to remember.

| Tool | Use it when | Owning guide |
|---|---|---|
| `limit_order.sh` | A job is pending and you suspect a GQM price cap; or you need to set/remove one. Read-first: `status` shows live price vs every cap and marks each BLOCKING/ok. Writes are dry-run unless `--apply`; group scope also needs `--i-understand-group-scope`. | `../infra/quota_market.md` §Price Caps |

**A tool here must be safe to run blind.** Default to read-only, make the
destructive path opt-in with an explicit flag, and print what it is comparing
against rather than only a verdict.
