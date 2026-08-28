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
usually a silent pre-`main()` death behind the Borg log wall (§The Startup
Contract classifies that whole family).

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

## The Startup Contract — Failures Before Your Code Runs

**A failure that happens before your code runs measures your launch, not your
hardware.** Three separate rules below are the same trap at three different
moments of startup, and all three mimic a hardware, capacity, or permission
problem — which is why they are expensive. Name the phase first, then read the
rule that owns it:

| startup phase | what happens there | how it fails | rule |
|---|---|---|---|
| module import | imports run before `InitGoogle` finishes | SIGABRT / exit 134, empty app log | Rule 4 |
| flag parsing, inside `app.run` | absl parses argv — including the launcher's own selectors | `Task exited with code 1`, **zero** bytes on CNS, output dir never created | Rule 4b |
| process fan-out, before the first collective | your own multi-GPU spawn/fork | a google3 assertion (e.g. on `fork`) | Rule 5, trap (i) |

Two consequences worth stating separately:

- **A step that never ran proves nothing about the step after it — record that
  as UNTESTED, never as FAILED.** A probe killed at fan-out says nothing about
  NCCL; a binary killed at flag parsing says nothing about the card. The two
  words send the next reader in opposite directions: *failed* abandons the
  path, *untested* fixes the harness.
- **The cheap discriminator is whether the job wrote its own first line to
  CNS.** No output dir at all means the death precedes user code, so look here;
  a `start` record followed by silence means the hardware stage was reached and
  the rules below do not apply. Run the launcher's argv shape on the
  workstation first (Rule 4b) — the whole class is reproducible in seconds
  without a build+queue cycle.

A startup failure this table does not name belongs **here**, next to its phase,
not appended to whichever rule happened to catch it.

## Rule 4 — No File/RPC At Module Import (InitGoogle Not Done)

**Any CNS/file/RPC op at MODULE-LOAD time aborts the task before `main()`** with
`InitGoogle() has not finished yet ... go/no_file_or_rpc_during_init` — a SIGABRT
(exit 134) with an empty application log, indistinguishable from an infra fault.
The threshold is **InitGoogle completing (inside `app.run`)**, not "imports
finished". So a log-mirror / heartbeat / checkpoint-dir `RecursivelyCreateDir`
must be **deferred into `main()`**, never run at import. (This bit even a file
whose comment claimed "after imports is safe" — the rule is after `app.run`.)
Parse flags with `known_only=True` for the same class of reason: the launcher
forwards selectors the binary never declares — see the next rule, which cost two
B200 jobs.

**A GPU job MUST write its own evidence (verdict / heartbeat with device_count +
NCCL result) to CNS — the Borg log is behind restricted-LOAS and `analog` is
blocked too** (`PERMISSION_DENIED owner=analog-rdl-engine`, same LOAS class as
`aclcheck`/`ganpati`). So on this workstation you cannot read a GPU task's stdout
after the fact by any means; if the job did not write to CNS, a failure leaves
you with nothing but the one-line `tpu check` reason. Write the proof from inside
`main()` (post-InitGoogle, per above) and flush it EARLY — a soak/train job
should land `start` (with `device_count`) and a first NCCL-probe within the first
minute, so a later preemption still leaves the evidence on disk.

## Rule 4b — `app.run` MUST Use `known_only=True`, Or The Job Dies Before `main()`

**Every job binary launched through the shared launcher must parse flags with
`known_only=True`; a bare `app.run(main)` is a latent job-killer.** The launcher
forwards its own selectors (`--xm_resource_alloc`, `--cell`, ...) to every
binary it starts. A binary that has not declared them dies inside absl's flag
parser:

```python
# WRONG — dies on the launcher's own flags
app.run(main)

# RIGHT — the launcher contract
app.run(main, flags_parser=lambda argv: FLAGS(argv, known_only=True))
```

What the failure looks like, and why it is so expensive to diagnose:

| symptom | why |
|---|---|
| `Task exited with code 1` and nothing else | absl exits during parsing |
| **zero** bytes written to CNS — the output dir is never even created | user code never ran |
| empty application log | the death precedes the first `print` |
| dies seconds after RUNNING | parsing is the first thing that happens |

**The trap is that this failure is arch- and code-independent, so it mimics a
hardware or permission problem.** Two B200 jobs from two completely different
binaries — one importing a training stack, one a self-contained 200-line soak —
died identically this way, which briefly looked like "B200 is broken". It was
not — this is the startup contract above, at the flag-parsing phase.

**Verify it locally in ten seconds** rather than spending a build+queue cycle:

```bash
python3 your_main.py --your_flag=1 --xm_resource_alloc=group:x/y --cell=sj
# bare app.run  -> FATAL Flags parsing error: Unknown command line flag
# known_only    -> reaches main() with --your_flag parsed correctly
```

Any new job binary should get this smoke before it is ever enqueued: the same
argv shape the launcher will use, run on the workstation, must reach `main()`.

## Rule 5 — GPU Topology: One Task, N Local GPUs, You Own NCCL

A single `--tpu_type=h100-8` is **one Borg task with 8 local GPUs in one
process** — NOT 8 tasks, and the launcher sets no `torchrun`/`RANK` for it (GPU
is not a TPU multi-task job; the launcher's `is_tpu_job` is False for GPU, so it
injects no JAX-coordination flags). Multi-GPU coordination is YOURS: for a
single-host job, spawn one process per GPU yourself. Two non-obvious traps here,
both of which every GPU-multicard torch line hits:
- **(i) Use `fork`, and take it from STDLIB `multiprocessing`, not
  `torch.multiprocessing`.** This one kills the process at fan-out, before any
  collective — §The Startup Contract, last phase. google3 patches
  `torch.multiprocessing` to
  `g3lib.multiprocessing`, which *asserts* on `get_context("fork")` and whose
  `absl_spawn`/`absl_forkserver` replacements demand the process be started by
  `g3_multiprocessing.handle_main()` (not `app.run()`) and die in the bazel
  runfiles resource tracker. Importing plain `import multiprocessing` and calling
  `get_context("fork")` is the working path.
- **It must be `fork`, never `spawn`, and the parent must touch NO CUDA before
  forking** (only `device_count()`, which is fork-safe). A `spawn` child
  re-imports the bazel `__main__` and re-registers absl flags →
  `DuplicateFlagError`; a forked child inherits the already-parsed process.
- **The TRAINING path needs this fan-out too, not just a sanity smoke.** With no
  injected `RANK`/`WORLD_SIZE`, a naive `train.run()` sees `WORLD_SIZE=1`, so the
  per-process batch becomes the full global batch and a strict data reader
  rejects it — the job dies at startup, before any step. Set `RANK`/`LOCAL_RANK`/
  `WORLD_SIZE` per forked child (and `MASTER_ADDR`/`MASTER_PORT` for NCCL init)
  the same way the smoke does.

NVLink domain caps the fully-connected single slice
(table below); above it, chips talk network RDMA (legal, not faster for
comms-bound work — the launcher warns, does not block).

## Rule 6 — Tiers: BATCH Preempts, PROD For A Clean Finish

GPU inverts the usual TPU cost intuition: **GPU PROD is cheap** (H100 PROD
~0.5–0.8 cr/chip-hr; A100 ~0.16; B200 ~0.4; GB200/GB300/H200 free pool), and
**BATCH is the free pool for most GPUs (0.00)** — but BATCH is preemptible and
gets `guarantee reclaim`-preempted the instant a PROD floor-holder wants the
chips. Observed directly: an `h100-8` BATCH smoke reached RUNNING in `mf`, then
was preempted mid-run (`Preempted. Due to guarantee reclaim -- we were ABOVE`).

- **Short smoke you can restart:** BATCH is fine and free.
- **A clean, uninterrupted finish (a real result, or a definitive smoke exit
  0):** use **`--tier=PROD`** — it is non-preemptible and, for GPU, still cheap.

  GPU PROD does NOT compete with the TPU v6p/v7 pools that arc1/maze/elt train
  on, so it does not starve them.
- **BATCH is preempted even while it holds a g9-floor slice** — floor membership
  does not confer preemption immunity; a higher-priority job in the same floor
  still evicts it. The lever against preemption is PRIORITY, so **train/sanity
  GPU work goes PROD; BATCH is for eval only.**
- **`--tier=PROD` stops preemption, but NOT migration — and the migration is
  invisible in every status query.** MEASURED on a `b200-8` PROD soak: it ran
  **2.19 h** on one host, vanished for **~9 minutes**, then resumed on a
  *different* host (new `hostname`, new `borg_task` id) and kept going.
  Throughout, `xmanager list` said `RUNNING 0/1`, unchanged; no failed work
  unit, no enforcer hit, no pruner signature — the work unit never failed, the
  *task* was moved. Consequences: (i) **checkpoint even on PROD, even when
  nothing is "failing"** — anything unsaved at the ~2 h mark is gone; (ii) the
  only reason this was caught is that the job wrote its own `uptime` on every
  heartbeat and the counter reset from 2.192 to 0.192, so **a long GPU job
  should emit its own uptime** or a restart will pass unnoticed. Sample size is
  one migration in 3.2 h, so read "~2 h" as an order of magnitude, not a period.
- **If a PROD job is held `Queued (GQM price over limit order)`, WAIT — do not
  raise its limit order.** A per-job `set_limit_order` bump is banned policy: the
  price cap is a blast-radius bound doing its job (refusing to overpay at a
  market peak), and the price falls back on its own. Hand-bumping is toil that
  does not scale and end-runs the cap. See the cap-vs-market note in
  `tpu_reference.md`.

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
- `tpu queue-status` showing `PLACEABLE now: h100-8 -> <cell> (<n> free slice(s))`
  proves only that the availability RPC returned a cell — NOT that the job will
  run. It is a status query about capacity; it does not test the budget gate
  (Rule 7), the IMEX grant (GB200), or preemption (Rule 6). A GB200 job sat
  `PLACEABLE` for hours while budget-deferred, then crashed on IMEX. **The only
  proof the end-to-end path works is a real job reaching RUNNING and writing its
  own success verdict** — treat PLACEABLE as necessary, never sufficient.
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
| anything that dies before the job's own first CNS line | a startup-phase failure, not the hardware — §The Startup Contract |
| job silently a TPU when you asked GPU (or vice versa) | used `--power` without pinning `--archs` (Rule 1) |
| reached RUNNING then died `guarantee reclaim` | BATCH preemption (Rule 6) — resubmit PROD |
| `analog` / `borg tasklog` = `PERMISSION_DENIED` (restricted-LOAS) | expected here; the log wall means the app MUST self-write evidence to CNS (Rule 4) — read state via `tpu check`, not the Borg log |
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

### Chips Are Not The GB200 Bottleneck — The Budget Gate Is

**What holds a GB200 job back is the Rule 7 budget gate, not free chips.** Read
the current free chips and obtainable slices per cell with `slice_probe
--accel=gb200 --topology=<n> --group=9` and pick the cell with the most free
chips — but whether the job ever builds is decided by the budget gate, not by
the chip count, so a placeable cell is not a schedulable one.

## GB200 Needs IMEX NVLink Authorization; B200 Does Not

**A GB200 job runs on Borg but crashes at CUDA/NVLink init unless your MDB role
is in the IMEX authorization group — B200 and the single-node GPUs have no such
dependency.** GB200 is NVL72: its NVLink domain spans nodes, so the runtime must
set up an IMEX (Internode Memory EXchange) fabric, which authenticates to a
per-region IMEX-proxy CA pool. Without membership the task reaches RUNNING, then
dies with a real crash (a failed work unit, not a preemption):

```
PERMISSION_DENIED: MDB role <user> is not allowed to send request to CA pool
  projects/mn-nvlink-imex-proxy/locations/<region>
```

Key facts:

| arch | NVLink domain | IMEX proxy needed? |
|---|---|---|
| `gb200` / `gb300` | cross-node (NVL72) | **yes** — at ANY size, even a single 8-GPU slice |
| `b200` / `b300` | single node (8 GPU) | no |
| `h100` / `h200` / `a100` | single node | no |

- **The judge is the runtime crash, not `aclcheck`.** The definitive evidence is
  that a GB200 job reaches RUNNING and then fails 100% at CUDA/NVLink init with
  the `PERMISSION_DENIED ... CA pool ...` above. Do NOT cite an `aclcheck`
  result: in this workspace `aclcheck` typically fails on the environment's own
  LOAS restriction (no access to the ACL-proxy / ganpati-read principal),
  returning a DENIED that is about *whether you may query the ACL*, not *whether
  you are in the group*. That DENIED looks like proof but tests something else,
  and a reviewer will reject it.
- **The grant is MDB group membership, and the CA-pool→group mapping is in
  source** (harder evidence than aclcheck): `security/ca/ra/imex/service/config/
  startup.pi` maps the IMEX CA pool to a `*-imex-ra-users` group, mirrored in
  `production/borg/pod/miba/private-ca-front-end/server.pi`. The request goes
  through the standard MDB/ganpati group-add flow with an owner's approval — an
  operator-level action, not a job flag. **Cover BOTH staging and prod RA** (a
  borglet defaults to the STAGING RA), or the job still fails on the arm you did
  not grant.
- **Single-node `gb200-8` hits the wall too, and that is a source fact, not an
  observation:** the IMEX sidecar starts iff `IsGpuWithNvlinkDomain()` is true,
  which is true only for GB200/GB300/VR200 and keys on CARD TYPE, not node count.
  So every GB200 slice — even one 8-GPU tray — brings up IMEX and needs the grant.
- **IMEX authorization is required only for cross-node NVLink cards
  (GB200/GB300); single-node cards (B200/B300, H100/H200, A100) never start the
  IMEX sidecar** — source-confirmed via the same `IsGpuWithNvlinkDomain()`. It
  follows that `b200` is the shortest Blackwell-class NVLink path while a GB200
  grant is pending — confirmed by a real run, see the next point.
- **CONFIRMED BY A RUNNING JOB — `b200-8` initialises CUDA fully and sees all 8
  GPUs, with no CA-pool authorization of any kind.** A `b200-8` soak on `sj`
  wrote this from inside the task:

  ```json
  {"event":"start","device_count":8,"host":"ti-vm-...","torch":"2.15.0a0+google3"}
  {"event":"alive","uptime_sec":749.9,"step":629813,"device_count":8,
   "device0":"NVIDIA B200","sm":"sm10.0"}
  ```

  Eight devices visible, the card really is a B200 (`sm10.0`), and the bf16
  matmul loop ran 629k steps across 12.5 minutes — all without the
  `PERMISSION_DENIED ... CA pool` that GB200 produces 100% of the time at the
  same stage. **So "B200 is IMEX-exempt" is now a measured result, not an
  inference.** Note the evidence is the job's OWN heartbeat on CNS, not a status
  query — that is the only class of evidence that survives both the Borg log
  wall and a broken CLI.
- **Still untested on B200: multi-GPU NCCL.** The soak's NCCL probe reported
  `nccl_all_ok: false`, but the error was `AssertionError: Use of 'fork' is
  discouraged in Google3 (go/python-tips/018)` — the probe was killed by a
  google3 assertion before it reached NCCL. **A probe that fails to run proves
  nothing about what it was going to measure**, so this is UNTESTED, not failed.
  The cause is trap (i) of Rule 5 and the fix is there: import STDLIB
  `multiprocessing`, not `torch.multiprocessing`. **Do NOT follow the
  assertion's own advice** to switch to `absl_spawn`/`absl_forkserver` — that is
  the wrong direction and fails differently. Worth noting the probe was written
  without reading Rule 5, which already documented this exact trap: the rule
  existed and still cost a run.

## Accelerator Names, NVLink Domains, Capability

See `tpu_reference.md` §NVIDIA GPUs for the arch tokens, `xm.ResourceType`
kwargs, NVLink domain sizes, and per-chip capability. The credit-limit caps live
in `~/work/tpu_cmd/tpu_wrapper.sh::_tpu_limit_price_for_arch` (a100=5,
h100/h200=10, b200/b300/gb200/gb300=20 cr/GPU-hr — blast-radius bounds far above
market, not trackers).
