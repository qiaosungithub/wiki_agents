# `jobs/` — Running Jobs On The Cluster

Detail for launching, resuming, keeping alive, and debugging a cluster job,
split by lifecycle phase. The hub `../jobs.md` routes here; read only the file
your task names. `../storage.md` owns data and checkpoint placement,
`../tpu_reference.md` accelerator naming and shapes, `../infra/` the market,
allocator, and CLI internals.

| File | Owns |
|---|---|
| `submit.md` | Submit / batch a job: the submission queue, the smart router (several `--archs`, all data `--metros`), the launch workflow and contract, tier and group choice, choosing where to run, the `tpu enqueue` + serial build-worker path, and the pre-launch budget gate. |
| `resume.md` | Resume contracts: `LOAD_FROM` (read-only, eval / warm-start), `restart_from` + `restart_step` (read/write split, a checkpointing training run), and the new-training-package startup contract. |
| `liveness.md` | Preemption and restart budget, `state: RUN` is not evidence anything runs, where the storage CLI does and does not exist, and worker identity / paths / local disk. |
| `diagnose.md` | A failing or silent job: diagnosis order, is one XID alive, debugging a job that dies with no log, launcher-side failures that look like scheduler failures, and metrics and curves. |
| `report.md` | Reporting job status to the operator: the shortest useful live-jobs list, owner filtering, real progress and ETA, finished / pending / held. |
