# Running Jobs On The Cluster

Queue, inspect, resume, and debug a job on the internal XManager/Borg stack.
`storage.md` owns where data and checkpoints live, `tpu_reference.md`
accelerator naming and shapes, `infra/` the market, allocator, and CLI
internals. Read those only when the rules here do not explain what you see.

**Before you submit anything after a large code change, run the CPU
`local_debug` path first** (`engineering.md` §Local debug, then remote, before a
real run). A build plus a queue wait plus a schedule is the
expensive way to find a bug a workstation finds in two minutes.

This is a hub. The detail lives in `jobs/`, one file per lifecycle phase; read
only the one your task names. `jobs/README.md` indexes them.

| Your task | Read |
|---|---|
| Submit / batch a job; pick tier, group, cell; the `tpu enqueue` + serial build-worker path; the pre-launch budget gate | `jobs/submit.md` |
| Resume a job: `LOAD_FROM` (eval / warm-start), `restart_from` (training), the new-training-package startup contract | `jobs/resume.md` |
| Survive preemption; tell a live job from a dead `state: RUN`; where the storage CLI exists; worker identity / paths / local disk | `jobs/liveness.md` |
| A job failed or went silent: diagnosis order, is one XID alive, no-log debugging, launcher-side failures, metrics and curves | `jobs/diagnose.md` |
| Report job status to the operator (the minimal live-jobs list; `tpu check` only, never npu) | `jobs/report.md` |

Current wrapper code, allocator configuration, work-unit state, and logs outrank
these guides whenever implementation details change.
