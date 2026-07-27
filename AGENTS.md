# Workspace Memory

This folder contains the small amount of shared context an agent needs before
working under `/usr/local/google/home/qiaos/work`.

## Start Here

1. Read this file.
2. Read `projects.md` to identify the checkout and its native documentation.
3. Read one topic guide that matches the task. Do not read every guide.
4. Inspect the current code, git state, and live system before acting. These
   guides explain intent and invariants; they are not a substitute for current
   source or runtime state.

## Workspace Model

- This is a shared research workspace with many independent repositories. A task's
  scope is the checkout the user named, not the whole workspace.
- Training data and checkpoints for **Kaiming Group Code (Type 1)** are region-local.
  For these projects, large payloads are not safe to move or read across regions by default.
  This restriction does NOT apply to Google Internal Research Code (Type 2).
- Agent memory should capture durable decisions and non-obvious invariants.
  Exact commands, incident timelines, job ids, and old configurations belong in
  source docs, live state, experiment records, or `archive/`.

### Google Cloud & XManager Infrastructure
- **TPU Scheduling & Regions**: Borg schedules TPUs across global datacenter cells (regions). Jobs missing explicit cell affinities are distributed globally. Therefore, training code running on XManager could land anywhere.
- **Data Storage Locality**: Local VM paths, persistent disks, and CitC checkouts (e.g., `/google/src/cloud/...`) are strictly tied to the regional datacenter where the VM or workspace lives (usually `us-east4`). XManager tasks scattered across the globe CANNOT efficiently access data on CitC or local folders.
- **Dataset Storage Rule**: Heavy datasets (e.g. TFRecords, large files) MUST be stored in a **Multi-Region GCS Bucket** (e.g. `US` multi-region). They will be streamed/read by XManager TPUs globally.
- **Official Bucket**: User's dedicated Multi-Region dataset bucket is `gs://qiaos-viscam-data-multi` in GCP project `viscam-cloud`. Use this for all uploads and data preparations.
- **Unified XManager Launching (xm_launcher)**: Do not maintain codebase-specific `xm_launch.py` scripts. Instead, a central, generic launcher `~/work/tpu_cmd/xm_launcher.py` coordinates all codebase packaging and staging. Local codebases should simply hold a `config.sh` (defining variables like `PROJECT_NAME`, `PACKAGE_MODE`, and `TARGET_LABEL`) and soft-link `xm_launcher.py`. Command lines (like `tpu_wrapper.sh`) should execute `xmanager launch xm_launcher.py` within the codebase dir.
- **XManager Job Tier Requirement**: When launching jobs intended to consume guaranteed quota (such as PROD capacity), you MUST explicitly specify `service_tier=xm.ServiceTier.PROD` in the `xm.JobRequirements()` inside the launcher script. If omitted, XManager defaults to a `BATCH` or `FREE` priority, causing the job to fail to consume the intended quota and get perpetually stuck in `awaiting resources` despite sufficient PROD capacity existing.
- **XManager Job Mapping**: The unified `xm_launcher.py` enforces a strict mapping of `xid` to job metadata (bucket checkpoint path, logdir, stagedir, etc.). Upon launch, it securely appends this mapping into a unified JSON file `~/.tpu_jobs.json` with process locking. Tools like `tpu check` read this JSON to quickly view queued jobs instead of performing slow global sweeps.
- **XManager Status Interpretation (RUNNING vs PENDING)**: When a job is submitted to the Borg PROD queue (e.g. v4-8, v6e-16), XManager UI or `xm status` may show it as `RUNNING` because the experiment itself is active. However, this actually means the job is **PENDING (排队领号)** waiting for a Borg hardware node assignment. It is pure waiting time with no environment setup or execution underway. Only when a node is fully allocated will it pull the Bazel image, execute `main.py`, and begin outputting logs (verifiable via `xmanager tail_logs`).
- **JAX Distributed via XManager**: `jax.distributed.initialize()` MUST NOT be called at the module level! In XManager jobs, `xm_jax.JaxFlags().flags()` passes JAX routing information (like `jax_controller_address`) as command-line arguments to the Python application. These arguments must be parsed by `absl.app.run(main)` before JAX is initialized. Therefore, `jax.distributed.initialize()` MUST be called inside the `def main(argv):` function. If it is called at the module level (import time), it will fail with `coordinator_address should be defined`.
- **TPU v4lite / Dragonfish Limitation**: When requesting TPU v4 resources, `v4lite` (mapped to `dragonfish` platform) does NOT support slice size 8 (e.g. `v4lite-8`). Doing so crashes with `dragonfish 8 is not supported`. Always use `v4-8` instead.

## Global Rules

- **Language Rule**: Conversations and dialogue with the user must ALWAYS be in Chinese, but code, comments, documentation, and `README.md` files pushed into the code repository MUST ALL BE in English.
- Push only when the user's current request explicitly asks for a push.
- Preserve user changes. Never revert, overwrite, or clean a dirty worktree as
  collateral work.
- Avoid cross-region or cross-zone data and checkpoint access **for Kaiming Group Code**.
  If payload access is necessary for those projects, first prove compute and storage locality.
- Before deleting shared or local data, identify the filesystem, owner, active
  references, and recovery path. Use a manifest for shared or bulk deletion.
- Treat external writes as transactions: establish identity and target, validate
  assumptions, write the smallest scope, then read back the result.
- **Config over CLI**: Avoid modifying parameters directly via command-line flags when launching jobs (e.g., `xmanager launch`). Prefer hardcoding configurations into the `config` YAML/Python files, except for transient overrides like `load_from` or `resume_xid`.
- **Infrastructure Hermeticity**: Unlike local directory python workflows that copy code into a `~/staging` dir per run, Google3 `xm.bazel_binary` creates perfectly hermetic, statically compiled packages (`.mpm`/`.par`) at the exact moment of launch. Therefore, local staging directories are obsolete inside Google3 workspaces; modifying local files post-launch will NOT affect queued or running XManager jobs.
- **LOAS/gcert Authorization**: If the system cannot access internal endpoints (e.g. `RPC_RESTRICTIONS_VIOLATION` in Moma search or missing XManager logs), it is fundamentally because the user's gLinux/Cloudtop LOAS certificate expired, preventing the underlying worker (or the CodeMind MCP server) from using it. **Do NOT ask for specific `ask_permission` authorization**. Simply instruct the user in one sentence: "Please run `gcert` in your terminal to refresh the credentials."
- Follow repository-local `AGENTS.md` or `CLAUDE.md` files for project-specific
  code semantics. The shared infra, locality, storage, and external-write rules
  here supersede stale operational sections in old project notes. Surface any
  remaining conflict rather than guessing.

## Topic Router

| Task | Read |
|---|---|
| Find a checkout or understand project boundaries | `projects.md` |
| Change VLM training, checkpointing, resume, or eval code | `vlm_training.md` |
| Upload VLM datasets, audit adapters/coordinates, prepare eval mirrors | `vlm_data.md` |
| Log WandB results into the experiment spreadsheet | `spreadsheet.md` |
| Manage a long-running experiment loop | `research.md` |
| Write a paper deep-reading report | `paper_reading.md` |
| Lay out or debug a report's HTML/PDF rendering | `paper_rendering.md` |
| Reclaim shared NFS or local disk space | `storage.md` |

## Evidence Order

When facts disagree, prefer this order:

1. The user's current request.
2. Current repository code and repository-native docs.
3. Live infra state, logs, WandB, and the spreadsheet.
4. The core guides in this folder.
5. `archive/`, which is historical evidence only.

## Maintaining Memory

- Keep core guides short and decision-oriented.
- Record a rule only when a future agent cannot cheaply infer it from code or
  when violating it has a meaningful cost.
- Replace stale facts instead of appending incident diaries. Never record live
  state (mirror completeness, job status) in a guide; record how to verify it.
- Put dated audit evidence (scan counts, validation numbers, status snapshots)
  under `archive/audits/` and keep only the derived rule plus a pointer in the
  guide. Delete audit snapshots once they are too old to be evidence.
- Preserve detailed or superseded text under `archive/` when it remains useful
  for forensics. Never route a new agent there by default.
