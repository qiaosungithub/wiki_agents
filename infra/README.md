# Infra Internals

Deep background on the cluster's allocation and tooling. **Read `../jobs.md`
first** — it covers launching, inspecting, resuming, and debugging a job. Come
here only when the basics do not explain what you see, or when changing the
tooling itself. These mechanisms change: live state and current source outrank
them, so re-verify before depending on a detail.

| Read | When |
|---|---|
| `quota_market.md` | A job will not schedule and `../jobs.md` does not explain it; you are setting a price cap; you need credits, floors, or tier behavior; you need the quota database or the router's market cache. |
| `tpu_cli.md` | You are changing, rebuilding, or debugging the `tpu` CLI, its checkers, its cache daemon, its job registry, or preflight. |
