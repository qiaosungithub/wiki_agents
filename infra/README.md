# Infra Internals

Deep background on the cluster's allocation and tooling. **Read `../jobs.md`
first** — it covers everything needed to launch, inspect, resume, and debug a
job. Come here only when the basics do not explain what you are seeing, or when
you are changing the tooling itself.

| Read | When |
|---|---|
| `quota_market.md` | A job will not schedule and `../jobs.md` does not explain it; you are about to set a price cap; you need to reason about credits, floors, or tier behavior. |
| `tpu_cli.md` | You are changing, rebuilding, or debugging the `tpu` CLI, its checkers, its cache daemon, or its job registry. |

These files describe mechanisms that change. Live state and current source
outrank them; re-verify before depending on a detail.
