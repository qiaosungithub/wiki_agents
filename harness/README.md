# Agent Harness

How agents work here. Shared behavior lives in [policy](policy.md) (rules for
every task), [engineering](engineering.md) (the working method), and
[evidence](evidence.md) (the evidence rules); read all three before any task.
Task skills below describe one workflow each and link to the
[knowledge](../knowledge/README.md) they rely on. The task router is
[AGENTS.md](../AGENTS.md).

## Task Skills

| Skill | Use |
|---|---|
| [agent-web-operations](skills/agent-web-operations/SKILL.md) | Redeploy, move between machines, health-check, or add a subdomain to the agent web / Jetski stack (`~/work/agent-web-gemini`), and triage its classic misleading bugs. |
| [amply-operations](skills/amply-operations/SKILL.md) | Restart or revive the amply UX gateway, check and repair its local Spanner database, read host health, and diagnose an `amp` session that only looks dead. |
| [charlm-runs](skills/charlm-runs/SKILL.md) | Launch, verify, harvest, and log char-LM torch-rnn reproduction runs on the GPU boxes, where one cell is one W&B group of seeds and one spreadsheet row. |
| [eqr-jax-runs](skills/eqr-jax-runs/SKILL.md) | Launch, triage, place, harvest, and keep the peak checkpoint of an EqR-jax sudoku or maze run, and run the RoboTwin Diffusion-Policy baseline and its A100 close-loop eval. |
| [experiment-loop](skills/experiment-loop/SKILL.md) | Run a long experiment program cycle by cycle (objective note, results table, compare at matched protocols, launch/stop/wait) and keep durable run records and tracker evidence. |
| [gcp-gpu-ssh](skills/gcp-gpu-ssh/SKILL.md) | SSH to a GCP GPU VM in `viscam-cloud`, fix `Permission denied` by telling OS Login from metadata keys, and create a new 4-card box with a hunt loop that holds no impossible targets. |
| [gpu-on-borg](skills/gpu-on-borg/SKILL.md) | Run an NVIDIA GPU job on Borg with `tpu enqueue --tpu_type=h100-8` (stage, BUILD, smoke, preflight, place) and diagnose one that dies before `main()` or trains far slower than the bench. |
| [job-diagnose](skills/job-diagnose/SKILL.md) | Diagnose a cluster job that failed, went silent, or reads `state: RUN` but produces nothing — check whether an XID is alive, debug a death with no log, read metrics back, and match launcher-side failures. |
| [job-report](skills/job-report/SKILL.md) | Answer the operator's request for job status with the minimal live-jobs board (`tpu check` only, never npu), real progress and ETA, and every pending and held job by name. |
| [job-submit](skills/job-submit/SKILL.md) | Submit a job or a batch to the cluster with `tpu enqueue`, settle placement, verify it is really running, and fix the classic submission bugs. |
| [local-debug](skills/local-debug/SKILL.md) | Make a large code change fit the fleet's infra contracts, then debug it locally on CPU and with one small remote run before a real run; use after any large code change and before submitting a job. |
| [machine-health](skills/machine-health/SKILL.md) | Diagnose and relieve a slow or overloaded workstation (load, memory, swap, idle blaze heaps, srcfsd, orphaned FUSE scanners, idle amply sessions) and judge whether a build is too slow. |
| [maintain-wiki](skills/maintain-wiki/SKILL.md) | Add to, revise, or reorganize this wiki (`wiki_agents/`), deciding where a note belongs and how to shape the page; use before writing anything into the wiki. |
| [nanochat-runs](skills/nanochat-runs/SKILL.md) | Stage offline assets for, submit, checkpoint, warm-start, and log nanochat Base, SFT, and RL jobs on Borg GPUs, one titled block per job and one row per stage in the nanochat repro tab. |
| [nanogpt-depth-runs](skills/nanogpt-depth-runs/SKILL.md) | Stage, launch, harvest, audit, resume, and log nanoGPT call/loss-diagonal (two-band Adam) runs, where one confirmed configuration is four seeds, one W&B group, and one sheet row. |
| [paper-reading](skills/paper-reading/SKILL.md) | Produce a paper deep-reading report in Simplified Chinese that a reader with no topic context can follow, and lay out, render and inspect its HTML/PDF. |
| [paper-writing](skills/paper-writing/SKILL.md) | Work on the paper in `~/work/paper-with-agent`: start a session, build the ICML PDF with pdflatex/bibtex and check it, and give every number, citation and figure a verified source. |
| [raft-runs](skills/raft-runs/SKILL.md) | Run RAFT-small reproduction and per-site optimizer arms on the GCE box or as a Borg GPU job, stage the FlyingChairs and FlyingThings3D data, record a results row, and keep the JAX port's launch mirror buildable. |
| [remote-control-operations](skills/remote-control-operations/SKILL.md) | Launch a run through the remote-control git interface, run or restart its poller, status-mirror, and W&B daemons, and debug a commit that did not launch or a mirror that stopped updating. |
| [result-logging](skills/result-logging/SKILL.md) | Write an experiment result into its project's shared results spreadsheet (right tab, right row, comparable metrics, train metrics, W&B and chart links, read-back), find a job's chart, or read a job's curves from the workstation. |
| [rnn-unroll-runs](skills/rnn-unroll-runs/SKILL.md) | Set up boxes for, launch, verify, harvest, log, and judge RNN unroll adding-problem sweeps on the GPU boxes, where one (arm, lr) cell is one W&B group of seeds and one tab row. |
| [storage-operations](skills/storage-operations/SKILL.md) | Copy, verify, or mirror data on distributed storage, recover from an over-quota cell or a CitC workspace that drops writes, build a multi-gigabyte artifact, and clean up local disk without losing data. |
| [survival-operations](skills/survival-operations/SKILL.md) | Launch a survival run (by pushing to the sqa-remote branch or by hand), run the survival-pipeline daemon, and debug a commit that never ran, a failed run, or a result that never synced. |
| [tpu-tooling](skills/tpu-tooling/SKILL.md) | Use when changing, rebuilding, or debugging the `tpu` CLI or its parts, namely the checkers, cache daemon, job registry, preflight, the smart router, local queue and serial build-worker, and the budget enforcer. |
| [unschedulable-job](skills/unschedulable-job/SKILL.md) | Use when a job will not schedule, is `BUDGET_DEFERRED`, or was paused or cancelled by the income/10 cap, when checking, setting, or verifying a price cap with `tools/limit_order.sh`, or when choosing and probing an accelerator before committing a long run. |
| [vlm-data-operations](skills/vlm-data-operations/SKILL.md) | Validate a regional VLM data replica, upload a dataset with the beifen uploader, or mirror the Open Images grounding and DocVQA/RealWorldQA eval roots before training or final eval in a region. |
| [vlm-debug](skills/vlm-debug/SKILL.md) | Run and verify a training, checkpoint, resume, or eval change in jax_llava, PaliGemma-baseline, or beifen-Paligemma, and get its telemetry (scalars, images) out of a Borg job and read it back. |
| [wandb-upload](skills/wandb-upload/SKILL.md) | Force, repair, re-upload, or verify the automatic W&B upload of a finished tpu job (`tpu_daemon.py --xid`, the `wandb-upload-tpu` daemon), and match its known traps. |

Read only the selected skill and the references it names. These are
workspace-local skills routed by [AGENTS.md](../AGENTS.md), not global
installations. Adding or changing a skill follows
[maintain-wiki](skills/maintain-wiki/SKILL.md).
