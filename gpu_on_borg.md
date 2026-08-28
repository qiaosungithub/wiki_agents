# Running A GPU Job On Borg (via `tpu enqueue`)

NVIDIA GPU training on the internal cluster, through the SAME `tpu enqueue` +
serial `tpu build-worker` path as TPU jobs (`jobs.md` owns that path; this file
owns only what is DIFFERENT for GPU). This is Borg/XManager GPU — NOT the
hand-run GCE A100 VMs (`gcp_gpu_ssh.md` owns those; the two share nothing but
the word "GPU").

**One-line orientation:** a GPU job is a normal `tpu enqueue` with an explicit
`--tpu_type=<gpu>-<n>` (e.g. `h100-8`) and `--archs=<gpu>`; the launcher
recognises the GPU arch and builds a CUDA binary. Everything below is the set of
places where "GPU" and "TPU" diverge — get these wrong and the failure is
usually a silent pre-`main()` death behind the Borg log wall.

## The Submission, End To End

```bash
cd <the checkout whose config.sh + BUILD + main.py you want packaged>
source ~/work/tpu_cmd/tpu_wrapper.sh
tpu enqueue \
  --power=h100-8 --archs=h100 \        # h100-only: NO --power router substitution
  --tier=BATCH \                        # or PROD (see Tiers below)
  --launch=group=9,config=<mode>,app.<flag>,exp_name=<name>
# a running `tpu build-worker` drains it; watch `tpu queue-status`.
```

The chain is identical to TPU (`enqueue → local queue → route_check worker →
tpu queue → preflight → xm_launcher → Borg`). What the GPU arch changes at each
stage is the rest of this doc.

## Rule 1 — Explicit `--tpu_type`, NEVER `--power` Router For The Arch

**Give a GPU job an explicit `--tpu_type=<gpu>-<n>` and pin `--archs=<gpu>` to
that ONE gpu.** The local-queue router's `--power` machinery is TPU
power-equivalence (v5p-normalised chip math with arch substitution): left to
substitute, it can silently swap a GPU request for a TPU (or vice versa). With
`--archs=h100` the candidate set is h100-only, so the router can only emit
`--tpu_type=h100-8` — no substitution is possible. `--power=h100-8` is fine as
the SIZE spec (it parses to arch=h100, chips=8 via `route_lib.LEGAL_SIZES`); the
safety comes from `--archs` pinning the family.

## Rule 2 — A GPU Bazel Binary Needs `--config=cuda` (The Launcher Adds It)

torch's CUDA kernels are `if_cuda`-gated in `//third_party/py/torch`, and
xmanager's `apply_default_bazel_args` does **not** infer `--config=cuda` from the
accelerator — it must be passed explicitly. The shared launcher
(`~/work/tpu_cmd/xm_launcher.py`) does this for you: in the `package_mode=bazel`
branch it appends `xm_abc.bazel_args.gpu(<resource>)` (→ `--config=cuda`,
`--define=cuda_compress=1`, per-SM enables, e.g. h100→sm90) whenever the arch is
a GPU. TPU/CPU builds are byte-for-byte unchanged.

**Verify it fired:** the launcher log prints
`[gpu] bazel CUDA build flags for h100: (... --config=cuda ...)`. If that line is
absent on a GPU job, the binary is CPU-only and will report
`torch.cuda.device_count()==0` at runtime — the torch twin of the JAX
`tpu_support` trap (a CPU-only build that does not say so). This distinction
(bazel/Borg vs python_container/GCP) matters: `base_image('pytorch')` only
covers the GCP `python_container` path; a Borg job gets CUDA from the build flag,
not the image.

## Rule 3 — BUILD A Torch GPU `py_binary` The Staging Way

The wrapper rsyncs the launch dir into a renamed stagedir and builds
`//<stagedir>:main`, so the target MUST be named `main`, entry `main.py`, both at
the launch root (`jobs.md` §Debugging owns the renamed-stagedir idiom; it is the
same for GPU). A minimal working torch GPU `BUILD`:

```python
load("//third_party/bazel_rules/rules_python/python:py_binary.bzl", "py_binary")
py_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    data = glob(["**/*.py", "**/*.yml", "**/*.yaml", "**/*.json"], exclude = ["main.py"]),
    strict_deps = False,          # runfiles tree resolves bare-name sibling imports
    deps = [
        "//third_party/py/torch:pytorch",
        "//third_party/gpus/cuda:cuda_runtime",          # CUDA runtime libs; NOT jax:gpu_support
        "//third_party/py/ml_collections",
        "//third_party/py/ml_collections/config_flags",  # SEPARATE target, not re-exported
        "//third_party/py/absl:app",
        "//third_party/py/absl/flags:flags",
        "//third_party/py/etils/epath",                  # CNS reads
        "//third_party/py/numpy", "//third_party/py/yaml",
    ],
)
```

Two dep traps that each cost a silent pre-`main()` death, both caught only by a
local build + `--help` (do this FIRST — `jobs.md` §Debugging):

| Trap | Symptom | Fix |
|---|---|---|
| `from ml_collections import config_flags` with only the base `ml_collections` dep | `ImportError: cannot import name 'config_flags'` | Add `//third_party/py/ml_collections/config_flags` — it is a separate target; the JAX side only gets it transitively via flax/optax |
| Using `//learning/brain/research/jax:gpu_support` for "CUDA runtime" | drags JAX's CUDA plugins into a torch-only job | Use `//third_party/gpus/cuda:cuda_runtime` — pure CUDA runtime, no JAX |

## Rule 4 — No File/RPC At Module Import (InitGoogle Not Done)

**Any CNS/file/RPC op at MODULE-LOAD time aborts the task before `main()`** with
`InitGoogle() has not finished yet ... go/no_file_or_rpc_during_init` — a SIGABRT
(exit 134) with an empty application log, indistinguishable from an infra fault.
The threshold is **InitGoogle completing (inside `app.run`)**, not "imports
finished". So a log-mirror / heartbeat / checkpoint-dir `RecursivelyCreateDir`
must be **deferred into `main()`**, never run at import. (This bit even a file
whose comment claimed "after imports is safe" — the rule is after `app.run`.)
Parse flags with `known_only=True` for the same class of reason: the launcher
forwards selectors the binary never declares.

## Rule 5 — GPU Topology: One Task, N Local GPUs, You Own NCCL

A single `--tpu_type=h100-8` is **one Borg task with 8 local GPUs in one
process** — NOT 8 tasks, and the launcher sets no `torchrun`/`RANK` for it (GPU
is not a TPU multi-task job; the launcher's `is_tpu_job` is False for GPU, so it
injects no JAX-coordination flags). Multi-GPU coordination is YOURS: for a
single-host job, spawn one process per GPU yourself (`torch.multiprocessing`
`fork` — a `spawn` child re-imports the bazel `__main__` and re-registers absl
flags → `DuplicateFlagError`; and the parent must touch NO CUDA before fork,
only `device_count()`). NVLink domain caps the fully-connected single slice
(table below); above it, chips talk network RDMA (legal, not faster for
comms-bound work — the launcher warns, does not block).

## Rule 6 — Tiers: BATCH Preempts, PROD For A Clean Finish

GPU inverts the usual TPU cost intuition: **GPU PROD is cheap** (H100 PROD
~0.36–0.46 cr/chip-hr; A100 ~0.42; GB200/GB300/H200 free pool; B200 ~11), and
**BATCH is the free pool for most GPUs (0.00)** — but BATCH is preemptible and
gets `guarantee reclaim`-preempted the instant a PROD floor-holder wants the
chips. Observed directly: an `h100-8` BATCH smoke reached RUNNING in `mf`, then
was preempted mid-run (`Preempted. Due to guarantee reclaim -- we were ABOVE`).

- **Short smoke you can restart:** BATCH is fine and free.
- **A clean, uninterrupted finish (a real result, or a definitive smoke exit
  0):** use **`--tier=PROD`** — it is non-preemptible and, for GPU, still cheap.
  GPU PROD does NOT compete with the TPU v6p/v7 pools that arc1/maze/elt train
  on, so it does not starve them.

The unqualified "BATCH is eval-only / never train on BATCH" rule
(`jobs.md`, `AGENTS.md`) is about the *contended TPU* pools; for a GPU free-pool
smoke it is not the hazard — the hazard is preemption cutting a run short, which
is why PROD is the right call the moment you need the run to actually complete.

## Rule 7 — The Real Wall Is The Budget Gate, Not Capacity Or Preemption

On a saturated fleet, a GPU job that is *placeable* (capacity exists) and
*PROD* (won't be preempted) can STILL never run, because a third gate stops it
before it ever builds: the **1/10-G9-income budget bar**. Observed live
(2026-08-28): every `gb200-{8,16,32,64}` PROD enqueue sat in
`BUDGET_DEFERRED`, never reaching BUILD, for hours.

**What BUDGET_DEFERRED means.** The dispatch/build worker calls
`budget_check.py --query <type> <tier> <lo_price> <group>` before building. It
returns `{income, bar, current, headroom, new_cost, fits}`:

- `bar = income / 10` — the budget ceiling is **one tenth of the rolling G9
  income** (income ~25 811 → bar ~2 581). This is a shared, fleet-wide number.
- `current` = the projected cost of ALL your live SUBMITTED/RUNNING jobs
  (XM-truth, zombie-filtered). With ~16 live jobs `current` was ~2 132 = **83 %
  of the bar already spent** before the GPU job is even considered.
- `headroom = bar - current`, and it **oscillates violently** (seen swinging
  `-211 ↔ +469` within one minute as other jobs start/stop). A job dispatches
  only in the instant `headroom >= new_cost`.
- `fits = new_cost <= headroom`. If false → `BUDGET_DEFERRED`, requeued every
  round (the fixed worker does NOT count these as build attempts, so the job is
  never HELD — it waits forever for a window).

**The projection trap (why a cheap job looks expensive).** The router queries
budget with `lo_price=0`, so `new_cost` is the **full on-demand projection**
(`gb200-8` → 800), even though the job, once submitted, is auto-capped by
`_tpu_set_limit_order` to the per-arch policy price (`gb200`=20 cr/GPU-hr) and
its REAL projected cost is ~1.6. Verified: the same `budget_check --query` with
`lo_price=0.20` returns `new_cost=1.6, fits=true`. So the gate rejects on a
price the job will never actually pay. This is a **gate-precision gap**, not a
real affordability problem — but do NOT patch the shared wrapper/router budget
logic to fix it without operator/monitor sign-off (it is a fleet-global lever).

**What actually works.**
- **Size down** lowers `new_cost` linearly (`≈ 100·chips + fixed`), so
  `gb200-8` needs the smallest window — but on a fully-saturated bar even the
  fixed component can exceed headroom, so sizing down is necessary-not-
  sufficient.
- **Wait for a window.** Leave the job enqueued; the fixed dispatch worker
  re-tests every round and fires the instant `headroom >= new_cost`. This is
  the in-policy path (`monitor`: "don't idle waiting for price — queue it and
  go do other work").
- **Free headroom you own:** draining your OWN dead-weight live jobs lowers
  `current` and raises headroom. Terminal jobs (failed/CANCELLED) do NOT count,
  so there is nothing to reclaim there — only live SUBMITTED/RUNNING jobs do.
  Never drain another agent's live experiment to make room.
- Raising the bar (more G9 income / a separate GPU budget line) is an
  **operator-level** decision, same class as the anti-preemption floor.

**Distinguish the three GPU stalls** (they look similar in `tpu queue-status`):

| Queue state | Meaning | Lever |
|---|---|---|
| `QUEUED … no placeable cell` | no contiguous slice right now (capacity) | wait / smaller shape / other cell |
| `BUDGET_DEFERRED … over bar` | budget gate: `new_cost > headroom` | wait for window / size down / free own headroom |
| reached RUNNING then `Preempted` | BATCH lost chips to higher prio | `--tier=PROD` (Rule 6) |

## Preflight, Placement, Capacity (Same Tools, GPU-Aware)

- `tpu preflight --tpu_type=h100-8 --group=9 --tier=BATCH` → GREEN + candidate
  cells with chips obtainable. GPU topology is validated too: `h100-16` is RED
  ("supported [1,2,4,8]") because 16 exceeds the 8-GPU H100 NVLink domain.
- `tpu queue-status` shows `PLACEABLE now: h100-8 -> <cell> (<n> free slice(s))`
  once enqueued — that IS the live proof the GPU availability path works.
- **`obtainable` vs live-free** is the same distinction as TPU (`jobs.md`,
  `research/accelerator_choice.md`): the capacity table is a forecast; a real
  short enqueue is the only 100%-accurate placement test. GB200 is the sharp
  case — the quota `Obtainable` badly understates live-free, and NVL72 large
  slices are often "not approved for borg scheduling", so treat gb200-8/16/32 as
  the safe obtainable shapes and prove anything larger with a real enqueue.
- `tpu money` / `tpu quota` render GPU rows (card + tier + clearing price +
  in-force limit-order cap). Read price before assuming which GPU you can get,
  exactly as for TPU.

## Quick Diagnosis Map (GPU-specific)

| Symptom | Most likely cause |
|---|---|
| `device_count()==0` on a GPU host | `--config=cuda` missing (Rule 2) — CPU-only build |
| SIGABRT / exit 134, empty app log, "InitGoogle has not finished" | file/RPC at import time (Rule 4) |
| `ImportError: config_flags` pre-main | missing `ml_collections/config_flags` dep (Rule 3) |
| job silently a TPU when you asked GPU (or vice versa) | used `--power` without pinning `--archs` (Rule 1) |
| reached RUNNING then died `guarantee reclaim` | BATCH preemption (Rule 6) — resubmit PROD |
| `analog`/`borg tasklog` = `PERMISSION_DENIED` (restricted-LOAS) | expected on this workstation; make the app write its own diagnostics to CNS (`jobs.md` §Debugging), or read state via `tpu check` |
| enqueued PROD, placeable, but never builds; `BUDGET_DEFERRED` | budget gate: `new_cost > headroom` (Rule 7) — wait for a window / size down |
| `gb200` build never starts, worker claims→releases fast | almost always Rule 7 budget, NOT ARM build failure — check `.tpu_local_queue.json` `last_reason` for `over bar` |

## GB200 Is ARM (Grace) — The Build Cross-Compiles To aarch64

`gb200`/`gb300` are Grace(ARM CPU)+Blackwell(GPU). `xm.ResourceType.GB200`
has `architecture() == ARM`, so `xm_abc.bazel_args.gpu(GB200)` automatically
adds `--cpu=arm` **and** `--define=cuda_target_sm100=1` (Blackwell sm100; the
launcher delegates the per-SM enables to xmanager's `GPU_TO_SM` table, so you do
NOT hardcode sm90 as for H100). Consequence: a `gb200` job cross-compiles the
WHOLE torch binary + CUDA deps to **aarch64** — a heavier, less-trodden path
than x86 H100. If a dep lacks an ARM build the job goes HELD at BUILD; that is a
real build gap (fix the dep), distinct from the Rule-7 budget stall (which never
reaches BUILD). Verify sizing first: `gb200-72` rounds to the nearest legal
slice (`gb200-64`) at placement time (see `tpu_reference.md`
round-to-nearest-legal-slice rule).

### Per-cell GB200 capacity is NOT the bottleneck (2026-08-28 snapshot)

`slice_probe --accel=gb200 --topology=<n> --group=9` gives free chips +
obtainable slices per cell. Live snapshot showed capacity is ample — the block
was always Rule 7 budget, never chips:

| cell | free chips | gb200-64 | -32 | -16 | -8 |
|---|---|---|---|---|---|
| `yuiadtq` | 116 | 1 | 3 | 7 | 14 |
| `yucbfcd` | 64 | 1 | 2 | 4 | 8 |
| `yuchstz` | 43 | 0 | 1 | 2 | 5 |
| `yuphxer` | 18 | 0 | 0 | 1 | 2 |

`yuiadtq` had the most (116 free) and could place every shape down to `gb200-8`.
Use `slice_probe` to pick the cell with the most free chips, but remember the
budget gate (Rule 7) decides whether it ever builds.

## Accelerator Names, NVLink Domains, Capability

See `tpu_reference.md` §NVIDIA GPUs for the arch tokens, `xm.ResourceType`
kwargs, NVLink domain sizes, and per-chip capability. The credit-limit caps live
in `~/work/tpu_cmd/tpu_wrapper.sh::_tpu_limit_price_for_arch` (a100=5,
h100/h200=10, b200/b300/gb200/gb300=20 cr/GPU-hr — blast-radius bounds far above
market, not trackers).
