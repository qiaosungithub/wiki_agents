---
name: gpu-on-borg
description: Run an NVIDIA GPU job on Borg with `tpu enqueue --tpu_type=h100-8` (stage, BUILD, smoke, preflight, place) and diagnose one that dies before `main()` or trains far slower than the bench.
---

# Running A GPU Job On Borg (via `tpu enqueue`)

This skill relies on [knowledge/infrastructure/gpu-on-borg.md](../../../knowledge/infrastructure/gpu-on-borg.md)
for how the CUDA build, the startup contract, GPU topology, tiers and preemption,
and the budget gate behave, and which cards are obtainable. GPU arch tokens,
NVLink domains, and card codes are [knowledge/infrastructure/tpu-reference.md §NVIDIA GPUs](../../../knowledge/infrastructure/tpu-reference.md#nvidia-gpus).

NVIDIA GPU training on the internal cluster uses the same `tpu enqueue` + serial
`tpu build-worker` path as TPU jobs. [The jobs pages](../../../knowledge/infrastructure/cluster-jobs.md) own that path; this skill and its knowledge page own
only what differs for GPU. This is Borg/XManager GPU, not the hand-run GCE A100
VMs ([the gcp-gpu-ssh skill](../gcp-gpu-ssh/SKILL.md) owns those; the two share nothing but the word "GPU").

**A GPU job is a normal `tpu enqueue` with a GPU board spec `--power=<gpu>-<n>`
(e.g. `h100-8`) and `--archs=<gpu>[,<gpu>...]`; the launcher recognizes the GPU
arch and builds a CUDA binary.** A GPU board spec keeps the chip count verbatim
and only emits the listed GPU archs at that width (`route_lib.candidate_shapes`
GPU special case, 2026-09-11): `--power=h100-8 --archs=h100,b200` lands on a
full h100-8 or b200-8, never b200-4 or a TPU. Do not use a bare-number
`--power` (TPU power math: `17` gives b200-4) or `--topology_locked` (a GPU job
is then never placed). Everything below is where GPU and TPU diverge. Get one
wrong and the failure is usually a silent pre-`main()` death behind the Borg log
wall, classified in [§The Startup Contract](../../../knowledge/infrastructure/gpu-on-borg.md#the-startup-contract--failures-before-your-code-runs).

## The Submission, End To End

```bash
cd <the checkout whose config.sh + BUILD + main.py you want packaged>
source ~/work/tpu_cmd/tpu_wrapper.sh
tpu enqueue \
  --power=h100-8 --archs=h100 \        # or --archs=h100,b200 (b200-8 tried first)
  --tier=BATCH \                        # or PROD (see Tiers below)
  --launch=group=9,config=<mode>,app.<flag>,exp_name=<name>
# a running `tpu build-worker` drains it; watch `tpu queue-status`.
```

Same chain as TPU (`enqueue → local queue → route_check worker →
tpu queue → preflight → xm_launcher → Borg`). Below: what the GPU arch changes
at each stage.

**A GPU job stages through the same shared CitC workspace as every TPU job.
Probe it before you enqueue: a drained workspace takes writes and drops them.**
It returns `rc=0`, reads back for a few seconds, then loses the write. The
stagedir stays empty (or `mkdir`-ed, never filled) and the launch dies looking
for `config.sh`. Per-workspace, not per-filesystem: stage elsewhere via the
wrapper's escape hatch.

```bash
# the wrapper reads ${STAGE_WS_ROOT:-<its default>}, so export overrides it,
# no edit to the shared wrapper needed. The staging subdir must already exist.
export STAGE_WS_ROOT=/google/src/cloud/<user>/<workspace>/google3
S=$STAGE_WS_ROOT/experimental/qiaos/eqr_jax_final_stages
mkdir -p "$S" && echo probe-$$ > "$S/__probe" && sleep 5 && cat "$S/__probe"
# prints the payload -> usable; "No such file" after rc=0 -> drained, pick another
# and probe a KNOWN-BAD root too: if both look fine, the probe is what is broken
```

Scope and limits:

- The export only reaches launches from your own shell. The build-worker stages
  queued jobs with the environment frozen at *its* start; editing the wrapper
  without restarting it does nothing. Read `/proc/<worker-pid>/environ`, not
  your own. That `exec` snapshot holds what the parent passed: a self-`export`ed
  variable never appears (verified both ways), and `/proc/environ` shows the old
  value. Check end-to-end: make the process act on it.
- `rc=1` on a fresh root usually means the staging subdir is missing, not a sick
  workspace: `mkdir -p` and it works. `rc=0` is the drained signature.
- Probe, never inherit. The wrapper's default changed after the old root dropped
  writes, so a note calling a root healthy proves nothing. Nor does "this
  directory does not exist".
- All CitC workspaces share one `fuse.srcfsd` mount: the hatch changes
  workspace, not filesystem. An srcfs restart in the staging→launch window still
  yields a task with no work units. Keep it short.
- Moving workspaces buys distance from a broken one, not quota. The
  CreateSnapshot token bucket is per-user: stage-writes drain one bucket
  wherever they go. The wrapper serializes them under a per-user lock; parallel
  staging across roots reproduces the storm.
- Staging is checked at enqueue, consumed minutes to hours later when the build
  lock releases. Re-verify then: `config.sh` present and non-empty, checked
  twice a few seconds apart. One check misses a write that lives a few seconds.

## The Rules, Checked Before Every Enqueue

The numbered rules are where a GPU job differs from a TPU job; the rest of this skill cites them by number.
Rule 3 is the BUILD section of this skill. The others, and the startup contract they enforce, are facts
in [knowledge/infrastructure/gpu-on-borg.md](../../../knowledge/infrastructure/gpu-on-borg.md).

- [Rule 2 — A GPU Bazel Binary Needs `--config=cuda` (The Launcher Adds It)](../../../knowledge/infrastructure/gpu-on-borg.md#rule-2--a-gpu-bazel-binary-needs---configcuda-the-launcher-adds-it)
- [Rule 3 — BUILD A Torch GPU `py_binary` The Staging Way](#rule-3--build-a-torch-gpu-py_binary-the-staging-way)
- [The Startup Contract — Failures Before Your Code Runs](../../../knowledge/infrastructure/gpu-on-borg.md#the-startup-contract--failures-before-your-code-runs)
- [Rule 4 — No File/RPC At Module Import (InitGoogle Not Done)](../../../knowledge/infrastructure/gpu-on-borg.md#rule-4--no-filerpc-at-module-import-initgoogle-not-done)
- [Rule 4b — `app.run` MUST Use `known_only=True`, Or The Job Dies Before `main()`](../../../knowledge/infrastructure/gpu-on-borg.md#rule-4b--apprun-must-use-known_onlytrue-or-the-job-dies-before-main); its local smoke is [§Smoke The Launcher's Argv On The Workstation](#smoke-the-launchers-argv-on-the-workstation)
- [Rule 5 — GPU Topology: One Task, N Local GPUs, You Own NCCL](../../../knowledge/infrastructure/gpu-on-borg.md#rule-5--gpu-topology-one-task-n-local-gpus-you-own-nccl)
- [Rule 6 — Tiers: BATCH Preempts Freely, PROD Preempts Rarely](../../../knowledge/infrastructure/gpu-on-borg.md#rule-6--tiers-batch-preempts-freely-prod-preempts-rarely)
- [Rule 7 — The Real Wall Is The Budget Gate, Not Capacity Or Preemption](../../../knowledge/infrastructure/gpu-on-borg.md#rule-7--the-real-wall-is-the-budget-gate-not-capacity-or-preemption)

## Rule 3 — BUILD A Torch GPU `py_binary` The Staging Way

The wrapper rsyncs the launch dir into a renamed stagedir and builds
`//<stagedir>:main`. Name the target `main`, the entry `main.py`, both at the
launch root ([job-diagnose skill §Debugging A Job That Dies With No Log](../job-diagnose/SKILL.md#debugging-a-job-that-dies-with-no-log) owns the renamed-stagedir idiom). Minimal
torch GPU `BUILD`:

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

Two dep traps each cost a silent pre-`main()` death, caught only by a local
build plus `--help`. Do it FIRST ([job-diagnose skill §Debugging A Job That Dies With No Log](../job-diagnose/SKILL.md#debugging-a-job-that-dies-with-no-log)):

| Trap | Symptom | Fix |
|---|---|---|
| `from ml_collections import config_flags` with only the base `ml_collections` dep | `ImportError: cannot import name 'config_flags'` | Add `//third_party/py/ml_collections/config_flags`, a separate target; the JAX side gets it transitively via flax/optax |
| Using `//learning/brain/research/jax:gpu_support` for "CUDA runtime" | drags JAX's CUDA plugins into a torch-only job | Use `//third_party/gpus/cuda:cuda_runtime`: pure CUDA runtime, no JAX |

Which `torch` this build links, and when FlashAttention is usable, are [§The Dependency Versions Come From The Staging Workspace](../../../knowledge/infrastructure/gpu-on-borg.md#the-dependency-versions-come-from-the-staging-workspace-not-from-you) and [§FlashAttention Is Available](../../../knowledge/infrastructure/gpu-on-borg.md#flashattention-is-available-with-two-conditions).

## Smoke The Launcher's Argv On The Workstation

This is the check for [Rule 4b](../../../knowledge/infrastructure/gpu-on-borg.md#rule-4b--apprun-must-use-known_onlytrue-or-the-job-dies-before-main).

Verify it locally in ten seconds instead of spending a build+queue cycle:

```bash
python3 your_main.py --your_flag=1 --xm_resource_alloc=group:x/y --cell=sj
# bare app.run  -> FATAL Flags parsing error: Unknown command line flag
# known_only    -> reaches main() with --your_flag parsed correctly
```

Any new job binary should get this smoke before it is ever enqueued: the same
argv shape the launcher will use, run on the workstation, must reach `main()`.

## Preflight, Placement, Capacity (Same Tools, GPU-Aware)

- `tpu preflight --tpu_type=h100-8 --group=9 --tier=BATCH` → GREEN plus candidate
  cells with chips obtainable. It validates GPU topology too: `h100-16` is RED
  ("supported [1,2,4,8]"), because 16 exceeds the 8-GPU H100 NVLink domain.
- `tpu queue-status` printing `PLACEABLE now: h100-8 -> <cell> (<n> free slice(s))`
  only proves the availability RPC returned a cell. It does not test the budget
  gate (Rule 7), the IMEX grant (GB200), or preemption (Rule 6). One GB200 job sat
  `PLACEABLE` for hours while budget-deferred, then crashed on IMEX.
  **The only proof the end-to-end path works is a real job reaching RUNNING and
  writing its own success verdict**, so PLACEABLE is necessary, never sufficient.
- `obtainable` vs live-free works as on TPU ([the jobs pages](../../../knowledge/infrastructure/cluster-jobs.md),
  [accelerator choice](../../../knowledge/infrastructure/accelerator-choice.md)): the capacity table is a forecast, and only a
  real short enqueue is a 100%-accurate placement test. GB200 is the sharp case:
  quota `Obtainable` badly understates live-free, and NVL72 large slices are often
  "not approved for borg scheduling". Treat gb200-8/16/32 as the safe obtainable
  shapes, and prove anything larger with a real enqueue.
- `tpu money` / `tpu quota` render GPU rows (card + tier + clearing price +
  in-force limit-order cap). As on TPU, read price before assuming which GPU you
  can get.

## Quick Diagnosis Map (GPU-specific)

Rule numbers are the ones listed in [§The Rules, Checked Before Every Enqueue](#the-rules-checked-before-every-enqueue).

| Symptom | Most likely cause |
|---|---|
| `device_count()==0` on a GPU host | `--config=cuda` missing (Rule 2); CPU-only build |
| SIGABRT / exit 134, empty app log, "InitGoogle has not finished" | file/RPC at import time (Rule 4) |
| `ImportError: config_flags` pre-main | missing `ml_collections/config_flags` dep (Rule 3) |
| anything that dies before the job's own first CNS line | a startup-phase failure, not the hardware; [§The Startup Contract](../../../knowledge/infrastructure/gpu-on-borg.md#the-startup-contract--failures-before-your-code-runs) |
| job silently a TPU, or half a board (b200-4), when you asked a GPU board | bare-number `--power` (TPU power math); give a GPU board spec like `--power=h100-8` |
| reached RUNNING then died `guarantee reclaim` | BATCH preemption (Rule 6); resubmit PROD |
| `analog` / `borg tasklog` = `PERMISSION_DENIED` (restricted-LOAS) | expected here; the log wall means the app MUST self-write evidence to CNS (Rule 4). Read state via `tpu check`, not the Borg log |
| enqueued PROD, placeable, but never builds; `BUDGET_DEFERRED` | budget gate: `new_cost > headroom` (Rule 7); wait for a window / size down |
| `gb200` build never starts, worker claims→releases fast | almost always Rule 7 budget, NOT ARM build failure; check `.tpu_local_queue.json` `last_reason` for `over bar` |
| `init_process_group` fails `errno: 97 - Address family not supported`, rank 0 appears to hang | `MASTER_ADDR=127.0.0.1` on an IPv6-only host; use `::1` (Rule 5) |
| a collective raises `ncclRemoteError ... Connection closed by remote peer` | usually a *victim's* view of another rank dying; find the child the parent never had to kill (Rule 5, and [§Debugging A Multi-GPU Probe](#debugging-a-multi-gpu-probe)) |
| rank 0 dies with SIGSEGV in its first collective; NCCL logs `Init COMPLETE` and no WARN | torch's `LOG(INFO)` hitting a broken debug-log sink, not NCCL; raise absl `minloglevel` in each child before the first collective ([B200 notes](../../../knowledge/infrastructure/gpu-on-borg.md#gb200--gb300-are-not-obtainable--do-not-plan-around-them)) |
| a `faulthandler` dump file is created but stays 0 bytes | absl owns SIGSEGV from import time; capture fd 2 with `dup2` instead ([B200 notes](../../../knowledge/infrastructure/gpu-on-borg.md#gb200--gb300-are-not-obtainable--do-not-plan-around-them)) |

## Measure The Container's Input Path Before Blaming It; Co-Located CNS Is Fast

**A GPU container reads its co-located CNS mirror at hundreds of MB/s (measured
in cell sm from `si-d`: 341 MB/s on one `epath` stream, 1.96 GB/s aggregate on
eight, tar parse 0.16 s per 84.5 MB shard on a 224-core host), so a job that
trains 25x under the bench is not explained by "CNS is slow" unless the read is
cross-metro; cross-metro reads from the same class of container measured 4-13
MB/s (codi-torch, ckv to cbf).** The maze-128 torch arms sat at 0.19 steps/s
with the loader costing 0.4 s per shard per rank; the arithmetic that blamed
the reads (676 MB per shard-set at 13 MB/s) fit the symptom exactly and was
wrong, because it took a cross-metro number as a property of the container.
`EqR-torch-maze128/infra/io_probe.py` (`config=io_probe`) is the ten-minute
measurement that settles it from inside the task shape; run it, or the
equivalent, before re-encoding a corpus or re-architecting a loader.

What still holds: compare bytes-per-step against ms-per-step before a long
launch, harvest the FIRST smoke's `train/samples_per_second` beside the bench
(the maze-128 smoke had the 5 s/step in it a day early and nobody read it),
and split the wall time into data-wait and train-step inside the run rather
than inferring it from outside. A slow step with a fast loader points at the
GPU work or the collective: NCCL's transport choice (NVLink/P2P, shared memory,
or a socket fallback) is visible only in NCCL's own log, so route it to a file
and excerpt it into the beacon.

## Debugging A Multi-GPU Probe

These lessons come from the B200 bring-up; its measured results stay in [the B200 notes](../../../knowledge/infrastructure/gpu-on-borg.md#gb200--gb300-are-not-obtainable--do-not-plan-around-them).

- A shrunk reproducer finds a bug but cannot verify the fix along the shrunk
  dimension. Two processes on two GPUs reproduced the rank-0 SIGSEGV crash at a tenth the
  cost per iteration; signing off still needed a full-size re-run.
- Instrument entry into every blocking step before you re-run: a probe logging
  only its result makes "blocked inside the collective" and "died on the line
  before it" byte-identical. The rank-0 SIGSEGV diagnosis took three runs: one hit the
  `fork` assertion of Rule 5; one hung with no way to say where; one named its
  own failure, once a breadcrumb marked ENTRY to each blocking call.
- Order a diagnostic arm designed to PASS last if the runner stops at the first
  passing arm: otherwise it cancels the arms behind it and the run looks
  complete.
- A broken instrument looks like a broken subject, accusing whatever ran LAST. A
  parent collecting results over `select()` dies at `FD_SETSIZE` (1024) once
  descriptors accumulate: later arms fail while their children write `ok=true`
  and exit 0; short runs never reach it. To find it, give the subject a channel
  off the collection path: a per-rank verdict breadcrumb.
  To rule it out, re-run the same configuration first: green-early red-late fits
  a real defect and a decaying harness alike. Use `poll()`, with no descriptor
  ceiling.
- A negative control that can fail for the wrong reason is not a control: "did
  not pass" also describes every rank dying at startup. Require it to reach its
  verdict *and* produce the predicted wrong answer: for an un-reduced gradient,
  each rank's own local value.
- Account for running jobs by enumerating the RESOURCE, not your record of
  launches: a cancel you never issued leaves no failed return code. Two audits
  each missed a different job, one burning eight B200s for over four hours; the
  true count came from listing the output directory. A cancel returning SUCCESS
  only means the request was accepted; the proof it died is a heartbeat file not
  growing across two samples.
- Dead and hung children look the same unless the parent records which ones it
  killed. Log a breadcrumb before killing a still-running child, and again when
  reaping each, with the exit code. A child the parent never killed, carrying a
  negative exit code, died on its own: `-11` is a kernel SIGSEGV and a *cause*,
  while a peer's `Connection closed by remote peer` is only a *consequence*.
