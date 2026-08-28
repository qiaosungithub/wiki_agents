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

**A GPU job stages through the same shared CitC workspace as every TPU job, so
probe that workspace before you enqueue — a drained one accepts your writes and
discards them.** A CitC workspace can enter a state where a write returns `rc=0`
and reads back correctly for a few seconds, then is gone; the stagedir is left
empty (or is `mkdir`-ed and never filled) and the launch dies looking for its
`config.sh`. This is **per-workspace, not per-filesystem** — the fix is to stage
somewhere else, via the wrapper's escape hatch:

```bash
# the wrapper reads ${STAGE_WS_ROOT:-<its default>}, so export overrides it,
# no edit to the shared wrapper needed. The staging subdir must already exist.
export STAGE_WS_ROOT=/google/src/cloud/<user>/<workspace>/google3
S=$STAGE_WS_ROOT/experimental/qiaos/eqr_jax_final_stages
mkdir -p "$S" && echo probe-$$ > "$S/__probe" && sleep 5 && cat "$S/__probe"
# prints the payload -> usable; "No such file" after rc=0 -> drained, pick another
# and probe a KNOWN-BAD root too: if both look fine, the probe is what is broken
```

What this does and does not buy you:

- **The export only reaches a launch your own shell performs.** A job drained
  from the queue is staged by the long-lived build-worker, which uses the
  environment frozen at *its* start — so exporting in your shell changes
  nothing for a queued entry, and neither does editing the wrapper without
  restarting the worker. Check `/proc/<worker-pid>/environ`, not your own.
- **A failed write needs a cause, exactly like a successful one.** `rc=1` on a
  fresh root usually means the staging subdir does not exist yet (`mkdir -p`
  and it works), not that the workspace is unhealthy — identical observation,
  opposite remedy. Conversely `rc=0` is the drained case's signature.
- **Which workspace is healthy is a fact with a shelf life — probe, never
  inherit.** The wrapper's default was itself switched after the previous
  default was found dropping writes, and defaults go stale the same way; the
  comment recording one as verified healthy is a log entry, not a guarantee.
  The same applies to "this directory does not exist": someone may have created
  it a minute after you looked.
- **Every CitC workspace lives on the same `fuse.srcfsd` mount, so the hatch
  changes workspaces, not filesystems.** It does nothing about an srcfs restart
  cutting the staging→launch window (that yields a task with no work units);
  the only lever there is keeping the window short.
- **Moving workspaces does not buy you quota, only distance from a workspace
  that is already broken.** The CreateSnapshot token bucket is **per-user**, so
  concurrent stage-writes drain the same bucket whichever workspaces they target
  — which is why the wrapper serializes stage-writes under a per-user lock, and
  why staging in parallel across roots reproduces the storm rather than
  escaping it.
- **Staging is checked when you enqueue, but consumed after the build lock
  releases — minutes to hours later.** Re-verify the stagedir (`config.sh`
  present and non-empty, checked twice a few seconds apart) *after* acquiring
  the lock. A one-shot check cannot see a failure mode whose whole signature is
  "correct for a few seconds".

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

**Side effect worth knowing, because it lands on other lanes: running
`blaze build --config=cuda` yourself in a shared workspace repoints that
workspace's `blaze-bin` symlink at the cuda output tree, and any script holding
a hardcoded `blaze-bin/...` path silently stops finding its binary.** CPU and
CUDA builds write to sibling trees (`blaze-out/k8-fastbuild/bin` vs
`.../k8-fastbuild-cuda/bin`), only one is linked at a time, and a GPU-only tree
contains none of the CPU-side tools. Nothing is deleted — they are still on disk
in the other tree.

**Enqueueing a GPU job does NOT do this — measured, and the distinction is the
whole point.** A queued job is packaged into its own stagedir and built through
xmanager from there, so it never runs `blaze` in the shared workspace and the
symlink does not move (verified across a full claim → build → XID cycle on a
GPU entry). **The hazard is the interactive build you run by hand while
debugging**, which is also the one that feels private: your own target, your own
shell, a flag the docs told you to pass, no shared file touched — and `blaze`
rewrites the symlink on your behalf. Hence the containment: **do hand-run CUDA
builds in a workspace of your own**, and treat `blaze-bin` in a shared checkout
as belonging to whoever built there last.

Two properties make the damage quiet:

- **A tool that cannot find its helper binary usually skips the feature rather
  than failing**, so the symptom is a mild log line and the guard that helper
  implemented is simply gone. Check the guard, not the log.
- **Already-running processes are unaffected — they hold a resolved inode — so
  the breakage only cashes in at the next restart.** A supervisor loop that
  re-resolves a `blaze-bin` path each iteration keeps "restarting" into a
  missing binary while looking alive. **That is the reverse of the stale-import
  trap: there, restarting is the fix; here, restarting is when it bites** — and
  it bites exactly when something has just crashed and most needs to come back.

**So when a binary looks "missing", resolve the symlink and check the sibling
tree before concluding anything was lost** (`readlink blaze-bin`, then
`ls blaze-out/*/bin/<path>`). Relinking is instant; rebuilding costs minutes of
the shared build lane and repairs only the link, which the next GPU build undoes
again. **The durable fix is to name the output tree explicitly** in anything
long-lived — a supervisor, a wrapper, a daemon — rather than depending on which
config was built last.

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

**And one phase fails without failing: a flag you did not pass takes its
default, and the default is somebody else's idea of what you meant.** Omitting
`--config` does not reliably kill the job — the launcher supplies its own
default and assembles it into a full `configs/load_config.py:<name>` path, so
the binary receives something syntactically valid either way. What happens next
depends entirely on **the checkout the entry packages** — which is the one named
in its `workdir`, not necessarily the one you are standing in:

| the packaged `configs/` | outcome | how you find out |
|---|---|---|
| no file matching the default | dies loading the config | loudly, at startup |
| a file matching the default, but not your arm | **runs the wrong experiment to completion** | only by reading which config it loaded |
| the binary never declares `config` at all | `FATAL: Unknown command line flag` before `main()` — **fixed by Rule 4b**, then the injected flag is simply ignored | exit 1, zero CNS bytes, empty log — reads as hardware or permissions |
| the file you wanted | fine | — |

**The second row is the expensive one, and every state-based check calls it
green**: the work unit does not fail, the task reaches RUNNING, a logdir
appears, checkpoints grow. Nothing distinguishes it from success except the
identity of the config. So verify a defaulted flag in five steps, and finish all
five:

| step | do | why it is not optional |
|---|---|---|
| 0 | read the queue entry's **`workdir`** — every `ls` below happens *there* | that directory is what gets packaged; your own checkout may be a different tree entirely, and an entry built from a stub `workdir` has no `configs/` at all |
| 1 | read the launcher's `DEFINE_string` default for `config` | it changes; read it, do not recall it |
| 2 | assemble the full path the launcher will build from it | the launcher composes `configs/load_config.py:<name>`; you are not passing a bare name |
| 3 | `ls` that **exact filename** | `grep`-ing the directory returns near-misses — at the level of names, **similar is more dangerous than absent** |
| 4 | open it and confirm it is *this* run | existence, then correct content, then **the version carrying your edits** — otherwise the config is right and the code is stale, and everything still reports green |

**Stopping after step three yields "there is a default, so it is fine", and
"fine" is precisely the bad row.** Whether the same omission is fatal or silent
differs per checkout, so another line's answer to this question is not evidence
about yours — and it can differ across *time* in one checkout too: **whether an
entry will die is a property of what its `workdir` contains right now, not a
property of the entry.** A "this will fail" verdict reached hours ago expires
when the source under that path changes.

Only the last row has a known fix (Rule 4b, running in production). The others
are not launcher bugs to be worked around — they are the entry disagreeing with
its own checkout, and the check above is how you find out which.

**Symmetrically: disproving a stated cause of death does not prove survival.**
When the reason given for "this will fail" turns out to be wrong, what has been
refuted is that mechanism, not the outcome — the job can still die of something
else, and it can also succeed at the wrong thing. Withdraw the mechanism and
re-derive the outcome; they are separate claims.

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

**Early is not enough — the evidence file must be APPEND-ONLY: never opened for
truncation, and never read-modify-written.** Writing early defeats *"the job
died before it wrote anything"*; it does nothing about *"the write destroyed
what was already there"*, and a GPU job restarts far more often than it fails
(Rule 6: PROD migrates, and `max_task_failures=-1` silently re-runs). The two
self-destructing patterns fail on different schedules:

| pattern | when you lose data |
|---|---|
| `open(path, "w")` per attempt | at every restart — one round survives, the current one |
| read whole file, append line, write whole file back | at **every write** — one interrupted rewrite truncates the lot, no restart needed |
| `open(path, "a")`, or one path per attempt | you don't |

Under either destructive pattern the file describes the latest round only — so
**the more times a job restarts, the more certain you are to be reading the one
round that needs no explanation.** The attempt worth keeping is precisely the
one with no successor to preserve it.

**When you cannot change how the evidence is produced — someone else's binary, a
run too valuable to restart — poll it from outside and keep your own
snapshots.** An external record needs no cooperation from the producer and no
change to a running job, and after a destructive write it is often the only
surviving copy of the round that mattered. But size it honestly: **an external
snapshot preserves what it saw, it does not make you see everything** — its
resolution is your polling interval, so events between two polls are lost just
as completely. It is a stopgap until the producer appends, not a substitute.
The two regimes were measured back to back on one job: while it truncated, a
restart had to be **reconstructed after the fact from two external polls, and
an earlier one was missed entirely**; once it appended, the next restart
**recorded itself** — same system, same observer, same class of event, and the
only change was how the producer opened the file.

## Rule 4b — `app.run` MUST Use `known_only=True`, Or The Job Dies Before `main()`

**Every job binary launched through the shared launcher must parse flags with
`known_only=True`; a bare `app.run(main)` is a latent job-killer.** The launcher
passes flags the binary never declared — both its own selectors
(`--xm_resource_alloc`, `--cell`, ...) and, unconditionally, `--config` and
`--workdir`, which it injects into every job's `executable_args` **without
checking whether the binary defines them**. So this is not a defensive habit for
large binaries: a self-contained 200-line probe that declares three flags of its
own and wants nothing to do with the config system is killed by `--config`
alone. A binary that has not declared them dies inside absl's flag parser:

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
  `get_context("fork")` is the working path. **Both alternatives the assertion
  itself recommends are dead ends here, each measured on a real job:**
  `absl_forkserver` raises `TypeError` in the bazel runfiles resource tracker,
  and `absl_spawn` requires `g3_multiprocessing.handle_main()` in place of
  `app.run()`, which breaks the launcher contract of Rule 4b. **An error
  message's own suggested fix is written for the stdlib case, not for a job
  under the launcher** — stdlib `multiprocessing` is the only path that clears
  both.
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
  *task* was moved. It kept happening: over a single soak the same job was moved
  repeatedly, with measured stretches of **2.19 h, ~1.3 h and 0.43 h** between
  moves and a **~9 minute** gap each time, while `FailedWorkUnits` stayed `0/1`
  from first launch to last. Consequences: (i) **checkpoint even on PROD, even
  when nothing is "failing"** — and size the interval for *no* safe period:
  three unequal stretches rule out a schedule, so the risk is not "you lose
  about two hours of work", it is **"you can lose it at any time, with no
  plannable gap"**; (ii) the only reason this was caught is that the job wrote
  its own `uptime` on every heartbeat and the counter reset, so **a long GPU job
  should emit its own uptime** or a restart will pass unnoticed; (iii)
  **`uptime` answers "how long has THIS round lasted", never "how long has
  the job held the slice"** — the two diverge at the first migration, and it is
  the second that answers whether an accelerator can carry a long run. Counting
  migrations therefore needs a record that survives them (Rule 4: append-only);
  **a migration count read off a self-truncating heartbeat is a floor, not a
  total** — one lost file has already hidden an entire migration here, and a
  round whose end was overwritten yields a lower bound on its length, never its
  duration. The tell that survives truncation is the pair (`hostname`,
  `borg_task`): **a new host id means a new round, whether or not you witnessed
  the changeover.** Two more reading traps once you are counting rounds:
  **measure a round from its own `start` to its own last heartbeat, never from
  one `start` to the next** — the second span silently includes the migration
  gap and overstates the stretch by minutes; and **a work unit that never fails
  is what distinguishes migration from crash**, so check `FailedWorkUnits`
  before calling a restart either one.
- **The budget enforcer can kill a GPU job for a price it does not actually
  cost.** MEASURED: a `b200-8` PROD soak ran 6 h 18 min with zero preemptions and
  zero failed work units, and was then stopped by `budget_enforcer` at
  `cost=800` — while `budget_check --query b200-8 PROD` returns `11.4` and the
  router admitted a sibling job at `11.4`. **800 = 8 chips x 100**, the
  signature of a GPU family falling through to the generic
  `mapping.get(arch, 100)` default. The enforcer's own header claims it reuses
  `budget_check`'s pricing, so **a comment asserting a shared basis is not
  evidence of one** — compare the numbers. Practical effect: at 800 cr/hr a
  free-pool GPU job looks like one of the priciest PROD jobs in the fleet and
  gets picked first, so **on GPU the largest measured survival threat is not
  preemption, it is being mispriced.** If a long GPU job disappears, `grep` your
  XID in the enforcer log before blaming the scheduler.
- **And a long-lived daemon prices from the table it imported at start, not the
  one on disk — fixing the table changes nothing until the daemon restarts.**
  Same job, same enforcer, two minutes apart across a restart: `cost=800`
  before, `cost=6` after. The corrected price table had been on disk for an hour
  while the daemon kept killing jobs at the stale one. This is the environment
  trap one layer in: a value frozen at process start is not only `environ` — it
  is **any Python module the process imported**, and unlike a config file
  nothing about the code hints that it was read once. **Check the daemon's start
  time against the mtime of what it imports**, and verify a fix by making the
  running process print the new value, never by confirming the file changed.
- **A stop that reports `OK` may have stopped without re-queueing.** The pause
  path stops the job first and re-enqueues second; when the second half fails
  (e.g. its CLI binary is not built) the log still shows the pause succeeding,
  so the job is gone and nothing is scheduled to bring it back. Read the lines
  *after* the `OK` before assuming a paused job will return — **a two-step
  operation that reports the first step's status is a silent success in the
  sense of `AGENTS.md` §Evidence Order.**
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

**A quota headroom of `0` does not mean "no capacity" — it also renders "could
not read the quota", and the two need opposite responses.** The router computes
it from a floor lookup that returns 0 both when an allocation has spent its
floor and when the allocation holds no floor for that chip at all (typically:
it does not participate in that market); preflight says `Cannot verify
headroom` in the second case, but a summary that prints `0/32 = 0x` erases the
distinction — **an "I don't know" rendered as a confident zero.** Do not size or
reroute off that number; read the reason text, which does separate the cases:

| reason says | what is true | what helps |
|---|---|---|
| `your group is 99% full` | the pool is exhausted | wait; another cell may help |
| `Could not read ... quota ... Cannot verify` | **nothing is known** | cross-check (below) |
| `Excluded by a triggered limit order` | the price gate stopped it | **another cell will not help** |
| `quota=N, used=N, remaining=0` | **your own alloc is spent** | **another cell will not help** — this is per-allocation, not per-cell; wait for your own jobs, or others on the same alloc, to release |

**The last two rows share an opening phrase with the second (`PROD quota
headroom is thin`), so reading only the first clause puts you in the wrong
row** — read on until you see either concrete `quota=/used=/remaining=` numbers
(your alloc really is spent) or the words `Cannot verify` (nothing was read).

The cross-check for the unreadable case is free but narrower than it looks: **a
RUNNING job proves capacity only if it belongs to your own group/alloc.** Quota
is granted per allocation, so someone else's job of the same arch and tier shows
that the fleet has the chips, not that you may have any — "in stock" and "you
are out of budget" are simultaneously true all the time.

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
