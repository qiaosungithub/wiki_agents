# XManager And Borg Jobs

Read this for queueing, inspecting, resuming, or debugging jobs on the Google
internal XManager/Borg stack. Read `data_locality.md` before choosing cells or
runtime storage, plus the target project's own guide.

## Submission Contract

- Agents submit through
  `source ~/work/tpu_cmd/tpu_wrapper.sh && tpu queue ...`. Never call
  `xm launch` or `xmanager launch` directly. Only the wrapper may do so
  internally.
- The shared `~/work/tpu_cmd/xm_launcher.py` owns common packaging, staging, and
  job registration. Project checkouts provide versioned configuration and a
  link or reference to the shared launcher; do not grow independent launcher
  implementations without an explicit design change.
- Put model, data, and training semantics in versioned config. Wrapper-level
  resource routing and explicit transient selectors such as `load_from` or
  `resume_xid` may remain CLI arguments.
- Confirm the source checkout, branch, dirty state, effective config, allocator,
  and target before launch. Use the project's real Research Hub attribution;
  never insert a placeholder merely to suppress an interactive prompt.
- A wrapper may create a unique CitC source snapshot before packaging. The
  resulting Bazel package is immutable: edits after packaging do not change a
  queued or running job.
- The wrapper records the XManager id and associated metadata for `tpu check`.
  Verify that registration after submission instead of assuming the launch
  transaction completed.

## Requirements And Runtime

- A job intended to consume guaranteed PROD quota must set
  `service_tier=xm.ServiceTier.PROD` in `xm.JobRequirements`. Do not substitute
  a legacy `xm_priority` field or silently accept BATCH/FREE.
- `xm.python_container` requires the selected pool to have a mapped GCP project.
  Use the allocator's supported packaging mode; native Borg allocators without
  that mapping require `xm_abc.Borg` with Bazel packaging.
- In JAX applications using `xm_jax.JaxFlags`, parse Abseil flags before
  distributed initialization. Call `jax.distributed.initialize()` inside
  `main(argv)`, never at module import time.

## Quota, Money & GQM Marketplace

### Underlying Allocation Logic: PROD vs BATCH
- **PROD (`ServiceTier.PROD` / HighlyAvailable)**:
  - **Non-preemptible**.
  - Strict hard quota limit (**Quota-based**). Uses guaranteed group allocations assigned by Org/Team. Cannot be expanded infinitely via money/bidding power. Exhaustion causes immediate admission failure (`RESOURCE_EXHAUSTED`).
- **BATCH (`ServiceTier.BATCH` / NonProd)**:
  - **Preemptible**.
  - Governed by GQM (Global Quotas Marketplace) bidding power (**Money-based**).
  - **Market Clearing Price**:
    - **0.00 Credits/hr (Free Pool)**: Triggered when cell capacity supply $\ge$ demand. Allows running large batch workloads without consuming bidding power.
    - **> 0.00 Credits/hr (Auction)**: Triggered during resource crunch/high demand. Workloads are scheduled based on group **Bidding Power (Money)** $\ge$ Market Clearing Price.

### `tpu money` CLI Usage
- **Command**: `tpu money` (Aliases: `tpu m`, `tpu price`).
- **Features**:
  - **Zero-latency offline fetch**: Pre-cached and updated every 60s by the background daemon (`tpu_check_daemon.sh`).
  - **Group Money Table (`G1`-`G7`)**: Displays real-time GQM Bidding Power (Credits/hr) and PROD/BATCH usages for each user allocation.
  - **Accelerator Market Clearing Prices**: Shows active clearing rates for major cards (**v4**, **v5p**, **v6e**, **v6p**) per cell location.
- **Related Commands**:
  - Use `tpu quota` to check guaranteed PROD/BATCH limits.
  - Use `tpu quota -l` to map `G1`-`G7` group indices to full MDB allocation paths.

## TPU Topology & Performance Equivalences

| Request | Constraint |
|---|---|
| `v4lite-8` | Dragonfish does not support slice size 8; request `v4-8` instead. |
| v6e | Borg expects a supported 2-D topology, such as `4x4` for v6e-16, rather than an arbitrary scalar. `v6e-8` can be rejected immediately by capacity/admission policy. |
| PROD v5p | PROD service tier requires at least `v5p-16` (requesting `v5p-8` under PROD tier will be rejected). |
| v5p larger than 8 | Borg expects 3-D topology, such as `2x2x4` for 32 or `4x4x4` for 64, rather than scalar core count `v5p-64` (otherwise rejected with Unsupported Topology). |
| v4 larger than 8 | Borg expects the supported 3-D topology, such as `2x2x1` for 32 or `2x2x2` for 64, rather than the scalar core count. |

### Performance Equivalence Heuristic
- **1 v6e chip ≈ 2 v5p chips** in compute/throughput.
- Consequently, **`v6e-16` is roughly equivalent to `v5p-32`** in compute capability (and `v6e-32` ≈ `v5p-64`).

For `deepmind-dynamic/vqfree-xm`, first verify the current allocator
configuration. The recorded constraints are PROD service tier, native
`xm_abc.Borg` plus Bazel packaging, and v6e-16 or larger; v6e-8 can be rejected
immediately by capacity/admission policy. Keep this allocator-specific rather
than treating v6e-8 as globally invalid.


## Status And Diagnosis

1. Start with `tpu check` and resolve the exact experiment and work unit.
   Experiment-level `RUNNING` does not prove that hardware was allocated; use
   work-unit state, allocation, logs, and activity to distinguish queued from
   executing.
2. Read the complete relevant failure, not only the final status string. An
   immediate failure without logs can be allocator, topology, packaging, or
   authorization related.
3. If the error explicitly indicates expired or invalid credentials, ask the
   user to run `gcert`, then retry the read. Do not diagnose every access or
   missing-log failure as a credential problem.
4. If normal log access still fails after identity is valid, use the supported
   XManager API or `tpu_utils` in the current Google3 checkout to inspect the
   work-unit status message. Do not patch shared scripts with hard-coded job ids,
   and do not assume an alternate API bypasses authorization.

### TPU Check Error Rules & Auto-Retry Mechanism

The backend `tpu_check_daemon.sh` parses XManager launch logs and classifies errors as follows:

*   **Preempted by Defag**: Greps for `SLICE_DEFRAGMENTATION`.
*   **Resource Exhausted (Topology/Quota)**: Greps for `RESOURCE_EXHAUSTED` or `RESOURCES_EXCEEDED`.
*   **Rejected by Allocator/Borg**: Fallback for `FAILED` status with an empty or `unknown reason`.
*   **Unknown failure**: Greps for `FAILED` when `Preempted` is not present.

**Auto-Retry Policy**:
If a job is queued in the **PROD** tier and fails specifically with **"Rejected by Allocator/Borg"**, the daemon will automatically retry launching the job up to **5 times**, waiting 5 minutes (300 seconds) between each attempt.

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this guide whenever implementation details change.
