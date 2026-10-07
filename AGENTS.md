# Workspace Agent Bootstrap

Durable rules for working under `/usr/local/google/home/qiaos/work`. Current
code, live state, and the user's request always outrank this folder. The wiki
separates the agent harness (how to work) from knowledge about the user's
systems and research.

## Start Here

1. Read [harness/policy.md](harness/policy.md) (the rules for every task, including the language rule), [harness/engineering.md](harness/engineering.md) (the working method), and [harness/evidence.md](harness/evidence.md) (the evidence rules). These are required for every task.
2. For repository work, identify the checkout, its category, and its page in [knowledge/codebases/projects.md](knowledge/codebases/projects.md), then read that checkout's own `AGENTS.md` or `CLAUDE.md`.
3. Pick the task skill and only the knowledge the router below names. Do not load the whole wiki.
4. Then the actual code, git state, and live system.

## Ownership

| Path | Owns |
|---|---|
| `AGENTS.md` | This bootstrap and the task router |
| `harness/policy.md`, `harness/engineering.md`, `harness/evidence.md` | Rules for every task, the working method, the evidence rules |
| `harness/skills/<name>/SKILL.md` | One task workflow each, with `references/` where a skill needs long supporting detail ([index](harness/README.md)) |
| `knowledge/codebases/` | Each checkout's semantics, invariants, metrics, and findings, plus the checkout map |
| `knowledge/infrastructure/` | How the cluster, scheduler, market, budget, storage, and `tpu` tooling work; reference tables |
| `knowledge/environment/` | The workstation, the GCP GPU VMs, the results workbooks |
| `knowledge/research/` | The research idea page ([knowledge index](knowledge/README.md)) |
| `tools/` | Executable helpers; prose lives elsewhere ([tools/README.md](tools/README.md)) |
| `archive/` | History. Never routed to by default |

A skill explains how to do the work and links to the knowledge it needs.
Knowledge describes the user's systems and research; a codebase or infra
invariant stays knowledge even when it is phrased as a constraint. Where a new
note belongs is [maintain-wiki](harness/skills/maintain-wiki/SKILL.md).

## Task Router

| Task | Skill or shared method | Knowledge |
|---|---|---|
| Anything, before you start | [policy](harness/policy.md), [engineering](harness/engineering.md), [evidence](harness/evidence.md) | |
| **Add to or reorganize this wiki**; where a note belongs; how to shape a page | [maintain-wiki](harness/skills/maintain-wiki/SKILL.md) | [knowledge index](knowledge/README.md) |
| **After a large code change, before submitting a job** | [local-debug](harness/skills/local-debug/SKILL.md#local-debug-then-remote-before-a-real-run) | |
| Find a checkout or its boundaries | | [projects.md](knowledge/codebases/projects.md) |
| Queue, inspect, resume, debug a job | [job-submit](harness/skills/job-submit/SKILL.md), [job-diagnose](harness/skills/job-diagnose/SKILL.md) | [cluster-jobs.md](knowledge/infrastructure/cluster-jobs.md), [resume-contracts.md](knowledge/infrastructure/resume-contracts.md), then the project page |
| **Report job status to the operator** (the minimal live-jobs list; `tpu check` only, never npu) | [job-report](harness/skills/job-report/SKILL.md) | |
| **Resume a job / write anything that passes a checkpoint to a job** | | [resume-contracts.md §The `LOAD_FROM` Contract](knowledge/infrastructure/resume-contracts.md#the-load_from-contract) |
| **Resume a TRAINING run that keeps checkpointing** (never `LOAD_FROM`) | | [resume-contracts.md §The `restart_from` Contract](knowledge/infrastructure/resume-contracts.md#the-restart_from-contract) |
| **Write / port a training package** (checkpoint layout, resume flags, boot banner, `main.py` fail-closed) | [local-debug §Adapt new code to the fleet's infra](harness/skills/local-debug/SKILL.md#adapt-new-code-to-the-fleets-infra) | [resume-contracts.md Chapter 2 — New Training Package Startup Contract](knowledge/infrastructure/resume-contracts.md#chapter-2--new-training-package-startup-contract) |
| Submit a job or a batch (default `tpu enqueue`; the always-on dispatch-worker is the sole builder and drains it — never start a `tpu build-worker`; auto cell / `--metro`) | [job-submit §Submitting A Job, Step By Step](harness/skills/job-submit/SKILL.md#submitting-a-job-step-by-step) | [cluster-jobs.md Chapter 1](knowledge/infrastructure/cluster-jobs.md#chapter-1--how-submission-works) |
| A CPU-only batch job will not schedule | [job-submit §Tiers and CPU-only](harness/skills/job-submit/SKILL.md#tiers-and-cpu-only) | [cluster-jobs.md §Groups](knowledge/infrastructure/cluster-jobs.md#groups) |
| Choose a cell (now auto-picked); preflight before packaging | [job-submit §Submitting A Job, Step By Step](harness/skills/job-submit/SKILL.md#submitting-a-job-step-by-step) | [cluster-jobs.md §The smart router](knowledge/infrastructure/cluster-jobs.md#the-smart-router-picks-the-cell-and-the-group) |
| Survive preemption; restart budget; worker identity, paths, local disk | | [cluster-jobs.md Chapter 2](knowledge/infrastructure/cluster-jobs.md#chapter-2--preemption-and-the-worker-environment) |
| A job failed or went silent: diagnosis order, is one XID alive, no-log debugging, launcher-side failures, metrics and curves | [job-diagnose](harness/skills/job-diagnose/SKILL.md) | |
| A job says `RUN` but produces nothing | [job-diagnose §`state: RUN` Is Not Evidence](harness/skills/job-diagnose/SKILL.md#state-run-is-not-evidence-that-anything-runs) | |
| **Clean up a job / 清理 job** (`tpu clear`); a refused `tpu dequeue` | [job-diagnose](harness/skills/job-diagnose/SKILL.md) | |
| A data-movement job: workstation or cluster? | | [cluster-jobs.md §Where The Storage CLI Exists](knowledge/infrastructure/cluster-jobs.md#where-the-storage-cli-exists-and-where-it-does-not) |
| A finished tpu job should auto-upload to W&B; multi-XID chain stitching (`step 0..end`); the `wandb-upload-tpu` daemon | [wandb-upload](harness/skills/wandb-upload/SKILL.md) | [wandb-upload.md](knowledge/infrastructure/wandb-upload.md) |
| A job will not schedule; capping spend (`tools/limit_order.sh`) | [unschedulable-job](harness/skills/unschedulable-job/SKILL.md) | [market.md](knowledge/infrastructure/market.md) |
| **A job is `BUDGET_DEFERRED`, or a running job was paused/cancelled and you suspect the income/10 cap** | [unschedulable-job](harness/skills/unschedulable-job/SKILL.md) | [budget.md](knowledge/infrastructure/budget.md) |
| Change the `tpu` CLI or its daemon | [tpu-tooling](harness/skills/tpu-tooling/SKILL.md) | [tpu-cli.md](knowledge/infrastructure/tpu-cli.md) |
| Change the smart cell-picker, the local queue and auto-reroute, or the serial build-worker | [tpu-tooling](harness/skills/tpu-tooling/SKILL.md) | [router.md](knowledge/infrastructure/router.md) |
| Touch `budget_check.py` or the `budget_enforcer` daemon | [tpu-tooling](harness/skills/tpu-tooling/SKILL.md) | [budget.md](knowledge/infrastructure/budget.md) |
| TPU codename, HBM, legal shape, equivalence | | [tpu-reference.md](knowledge/infrastructure/tpu-reference.md) |
| GPU arch token, NVLink domain, legal shape, card code | | [tpu-reference.md §NVIDIA GPUs](knowledge/infrastructure/tpu-reference.md#nvidia-gpus) |
| **Run a GPU job on Borg** (`tpu enqueue --tpu_type=h100-8`); CUDA build, NCCL, device_count==0, GPU preemption | [gpu-on-borg](harness/skills/gpu-on-borg/SKILL.md) | [gpu-on-borg.md](knowledge/infrastructure/gpu-on-borg.md) |
| **A GPU job trains far slower than the bench**; `samples_per_second` 10-30x under; is it the data path or the GPU/NCCL? | [gpu-on-borg §Measure The Container's Input Path Before Blaming It](harness/skills/gpu-on-borg/SKILL.md#measure-the-containers-input-path-before-blaming-it-co-located-cns-is-fast) | |
| SSH to a GCP GPU VM; `Permission denied`; OS Login vs metadata keys | [gcp-gpu-ssh](harness/skills/gcp-gpu-ssh/SKILL.md) | [gcp-gpu-vms.md](knowledge/environment/gcp-gpu-vms.md) |
| **Which machine am I on / ssh to the workstation**; `sqa` vs `sqa-large`; where amply, the crontab and the tpu workers run; re-sync home; jetski-hub and the web app | | [workstation.md](knowledge/environment/workstation.md) |
| **The box is slow / high load / swapping / VSCode-SSH keeps disconnecting**; builds crawling; **is a build too slow** (the ~40s floor; >60s never normal); reclaim idle blaze heaps or memory; a recursive `find` on `/google/src`; reap idle amply sessions | [machine-health](harness/skills/machine-health/SKILL.md) | [workstation.md](knowledge/environment/workstation.md) |
| **Choose an accelerator family**; a preemptible slice will not hold | [unschedulable-job Chapter 2](harness/skills/unschedulable-job/SKILL.md#chapter-2--choose-and-probe-an-accelerator-before-committing) | [accelerator-choice.md](knowledge/infrastructure/accelerator-choice.md) |
| Pick a cell/metro for a v7 run | [unschedulable-job §How To Regenerate The v7 Placement Survey](harness/skills/unschedulable-job/SKILL.md#how-to-regenerate-the-v7-placement-survey) | [v7-storage-placement.md](knowledge/infrastructure/v7-storage-placement.md) |
| Place data or checkpoints; copy or upload | [storage-operations §Before Touching A Payload](harness/skills/storage-operations/SKILL.md#before-touching-a-payload) | [storage.md](knowledge/infrastructure/storage.md), then the project page |
| **Map a cell to its metro or its CNS bucket**; add a cell to any such table | | [storage.md §Never Hand-Maintain A Cell -> Metro -> Bucket Table](knowledge/infrastructure/storage.md#never-hand-maintain-a-cell---metro---bucket-table) |
| **Copy, move, or hand off a checkpoint**; resume across metros | [storage-operations §Before Touching A Payload](harness/skills/storage-operations/SKILL.md#before-touching-a-payload) | [storage.md §A Checkpoint Path Is An Opaque String](knowledge/infrastructure/storage.md#a-checkpoint-path-is-an-opaque-string-and-four-shapes-coexist) |
| Read a distributed path interactively | [storage-operations §Distributed Reads](harness/skills/storage-operations/SKILL.md#distributed-reads-on-an-interactive-path) | |
| **CitC/srcfs is dropping writes**; `CreateSnapshot failure`; a staging rsync that never converges | [storage-operations: citc-write-failures.md](harness/skills/storage-operations/references/citc-write-failures.md#before-blaming-citc-for-dropping-writes-find-out-who-is-writing) | |
| A write fails, or a job produced 0-byte logs | [storage-operations §An Over-Quota Cell Looks Like A Broken Program](harness/skills/storage-operations/SKILL.md#an-over-quota-cell-looks-like-a-broken-program) | [storage.md §Charge The Group](knowledge/infrastructure/storage.md#charge-the-group-not-your-500-gib-personal-ceiling) |
| Resume skips work, or a 0-byte file counts as done | [storage-operations §Existence Is Not Completeness](harness/skills/storage-operations/SKILL.md#existence-is-not-completeness) | |
| Reclaim local disk, or prune checkpoints | [storage-operations §Local Disk Cleanup](harness/skills/storage-operations/SKILL.md#local-disk-cleanup) | [storage.md §Checkpoints Are The Default Reason A Cell Fills Up](knowledge/infrastructure/storage.md#checkpoints-are-the-default-reason-a-cell-fills-up) |
| Build or verify a multi-GB artifact on distributed storage | [storage-operations: large-artifacts.md](harness/skills/storage-operations/references/large-artifacts.md#building-a-multi-gigabyte-artifact-on-distributed-storage) | [storage.md §Size A Copy In Disk Bytes](knowledge/infrastructure/storage.md#size-a-copy-in-disk-bytes-not-payload-bytes) |
| A big write is silently truncated or keeps restarting | [storage-operations: §Two Writers On One Output Path](harness/skills/storage-operations/references/large-artifacts.md#two-writers-on-one-output-path) | |
| Write a checker, or a verification keeps saying OK | [engineering §A test that cannot fail proves nothing](harness/engineering.md#a-test-that-cannot-fail-proves-nothing) | |
| **An edit reported success but the change is missing**; deleting a file breaks an unrelated build | [engineering §Trust artifacts, not success returns](harness/engineering.md#trust-artifacts-not-success-returns), [§Make edits atomic](harness/engineering.md#make-edits-atomic) | |
| Fault-inject safely; a killed script left a broken shared file | [engineering §A test that cannot fail proves nothing](harness/engineering.md#a-test-that-cannot-fail-proves-nothing) | |
| **Two measurements disagree**; a cached green build; a retracted number | [engineering §When a reading is wrong, fix the predicate, not the command](harness/engineering.md#when-a-reading-is-wrong-fix-the-predicate-not-the-command), [§Trust artifacts, not success returns](harness/engineering.md#trust-artifacts-not-success-returns) | |
| **The core research idea / the "idea page"** — per-site (untied) gradients for weight-shared models and the looped-nanoGPT benchmark; points at the user's `hie1/` files in the paper repo | | [looped_nanogpt_per_site.md](knowledge/research/looped_nanogpt_per_site.md) |
| Manage a long experiment; tracker evidence | [experiment-loop](harness/skills/experiment-loop/SKILL.md) | [research index](knowledge/research/README.md) |
| **Log a result to the spreadsheet**; find a chart | [result-logging](harness/skills/result-logging/SKILL.md) | [result-workbooks.md](knowledge/environment/result-workbooks.md) |
| **Read a job's curves / harvest `train/*` from the workstation**; the urge to write "the workstation cannot read the datatable" | [result-logging: §Reading The Curves From The Workstation](harness/skills/result-logging/references/chart-links.md#reading-the-curves-from-the-workstation) | |
| **Write the paper** (`~/work/paper-with-agent`): the hie1 / hie2 / hie3 layers, hie1 is user-only, ICML LaTeX build | [paper-writing](harness/skills/paper-writing/SKILL.md) | [paper-with-agent.md](knowledge/codebases/paper-with-agent.md) |
| Write or render a paper report | [paper-reading](harness/skills/paper-reading/SKILL.md), its [rendering reference](harness/skills/paper-reading/references/rendering.md) | |
| `EqR` / `EqR-jax` | [eqr-jax-runs](harness/skills/eqr-jax-runs/SKILL.md) | [eqr-jax.md](knowledge/codebases/eqr-jax.md) |
| RNN unroll optimizer / adding problem / gradient propagation science line | [rnn-unroll-runs](harness/skills/rnn-unroll-runs/SKILL.md) | [rnn-unroll.md](knowledge/codebases/rnn-unroll.md) |
| **char-LM / torch-rnn reproduction**; which "char-RNN" repo; the 4-seed cell -> wandb group -> spreadsheet row pipeline | [charlm-runs](harness/skills/charlm-runs/SKILL.md) | [charlm.md](knowledge/codebases/charlm.md) |
| **nanoGPT call/loss diagonal** (`~/work/nanogpt_depth`, two-band Adam); the four-seed configuration -> W&B group -> row pipeline | [nanogpt-depth-runs](harness/skills/nanogpt-depth-runs/SKILL.md) | [nanogpt-depth.md](knowledge/codebases/nanogpt-depth.md) |
| **RAFT optical flow reproduction / per-site optimizer on RAFT**; FlyingChairs / FlyingThings3D data on the GPU box | [raft-runs](harness/skills/raft-runs/SKILL.md) | [raft.md](knowledge/codebases/raft.md) |
| **`nanochat` full-pipeline testbed (`Base` → `SFT` → `RL`, when is looping useful)**; `d12` / `d24` metrics, SFT forgetting, SFT-to-RL inversion, `Maj@k` scaling | [nanochat-runs](harness/skills/nanochat-runs/SKILL.md) | [nanochat.md](knowledge/codebases/nanochat.md) |
| VLM training, data, benchmark reporting | [vlm-debug](harness/skills/vlm-debug/SKILL.md), [vlm-data-operations](harness/skills/vlm-data-operations/SKILL.md) | [vlm-training.md](knowledge/codebases/vlm-training.md), [vlm-data.md](knowledge/codebases/vlm-data.md), [vlm-metrics.md](knowledge/codebases/vlm-metrics.md) |
| **The amply gateway is down**; `amp new` worker dies at `os.getcwd()`; `amply-launch` prints nothing | [amply-operations §Restarting The Amply UX Server](harness/skills/amply-operations/SKILL.md#restarting-the-amply-ux-server) | |
| **Amply's database, snapshots, the local Spanner universe**; `/span/tmp` is dead; restart localdb / gateway order; migrate old runs | [amply-operations §Checking And Repairing The Amply Database](harness/skills/amply-operations/SKILL.md#checking-and-repairing-the-amply-database) | [local-agent-cli.md §The Amply Database Is A Local Spanner Test Universe](knowledge/codebases/local-agent-cli.md#the-amply-database-is-a-local-spanner-test-universe) |
| Agent web app, or a local agent CLI; a dead-looking `amp` session | [agent-web-operations](harness/skills/agent-web-operations/SKILL.md), [amply-operations](harness/skills/amply-operations/SKILL.md) | [agent-web.md](knowledge/codebases/agent-web.md), [local-agent-cli.md](knowledge/codebases/local-agent-cli.md) |
| **The remote-control job interface** (lyy launches runs by `git push`; status mirrored back as a git repo); the poller / status daemon; `run_config.yml` schema | [remote-control-operations](harness/skills/remote-control-operations/SKILL.md) | [remote-control.md](knowledge/codebases/remote-control.md) |
| **Survival game / the sqa-remote run pipeline** (collaborator's stay-alive multi-agent sim; each `sqa-remote` commit == one LOCAL amply run; codex→amply adaptation; results pushed to many-agent-result) | [survival-operations](harness/skills/survival-operations/SKILL.md) | [survival.md](knowledge/codebases/survival.md) |

## Paths And Compatibility

**The old paths (`engineering.md`, `storage.md`, `jobs/`, `infra/`, `projects/`,
`research/`, `reports/`, and the other former top-level pages) are now redirect
stubs; edit the canonical page they name, never the stub.** Code comments and
notes in other checkouts cite those paths and their `§` headings, so each stub
keeps every old heading and points it at its new home. New links use canonical
paths. Markdown links are relative to their containing file; literal runtime
paths such as `~/work/wiki_agents/tools/budget_check.py` keep their original
meaning.

The sections this file used to carry moved as follows; a reference such as
"`AGENTS.md` §Evidence Order" means the page on the right.

| Former `AGENTS.md` section | Now |
|---|---|
| Global Rules | [harness/policy.md §Global Rules](harness/policy.md#global-rules) |
| Evidence Order | [harness/evidence.md](harness/evidence.md) |
| Maintaining Memory | [maintain-wiki §Maintaining Memory](harness/skills/maintain-wiki/SKILL.md#maintaining-memory) |
| Layout, Topic Router | §Ownership and §Task Router above |
