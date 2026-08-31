# Running A GPU Job On Borg (via `tpu enqueue`)

NVIDIA GPU training on the internal cluster uses the same `tpu enqueue` + serial
`tpu build-worker` path as TPU jobs. `jobs.md` owns that path; this file owns
only what differs for GPU. This is Borg/XManager GPU, not the hand-run GCE A100
VMs (`gcp_gpu_ssh.md` owns those; the two share nothing but the word "GPU").

**A GPU job is a normal `tpu enqueue` with an explicit `--tpu_type=<gpu>-<n>`
(e.g. `h100-8`) and `--archs=<gpu>`; the launcher recognizes the GPU arch and
builds a CUDA binary.** Everything below is where GPU and TPU diverge. Get one
wrong and the failure is usually a silent pre-`main()` death behind the Borg log
wall, classified in §The Startup Contract.

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

## Rule 1 — Explicit `--tpu_type`, NEVER `--power` Router For The Arch

**Give a GPU job an explicit `--tpu_type=<gpu>-<n>` and pin `--archs=<gpu>` to
that ONE gpu.** The local-queue router's `--power` machinery is TPU
power-equivalence (v5p-normalized chip math with arch substitution); left to
substitute, it can swap a GPU request for a TPU or the reverse. `--archs=h100`
makes the candidate set h100-only, so the router can only emit
`--tpu_type=h100-8`. `--power=h100-8` is fine as the SIZE spec (it parses to
arch=h100, chips=8 via `route_lib.LEGAL_SIZES`); `--archs` supplies the safety.

## Rule 2 — A GPU Bazel Binary Needs `--config=cuda` (The Launcher Adds It)

torch's CUDA kernels are `if_cuda`-gated in `//third_party/py/torch`, and
xmanager's `apply_default_bazel_args` does not infer `--config=cuda` from the
accelerator. The shared launcher (`~/work/tpu_cmd/xm_launcher.py`) adds it: on a
GPU arch, `package_mode=bazel` appends `xm_abc.bazel_args.gpu(<resource>)`
→ `--config=cuda`, `--define=cuda_compress=1`, per-SM enables (h100→sm90). TPU
and CPU builds are unchanged.

Verify: the launcher log prints
`[gpu] bazel CUDA build flags for h100: (... --config=cuda ...)`. Without it the
binary is CPU-only: `torch.cuda.device_count()==0`, the torch twin of the JAX
`tpu_support` trap. `base_image('pytorch')` covers only the GCP
`python_container` path; on Borg, CUDA comes from the build flag, not the image.

**A hand-run `blaze build --config=cuda` in a shared workspace repoints its
`blaze-bin` symlink at the cuda output tree, so scripts with a hardcoded
`blaze-bin/...` path stop finding their binary.** CPU and CUDA builds write to
sibling trees (`blaze-out/k8-fastbuild/bin` vs `.../k8-fastbuild-cuda/bin`),
only one linked at a time, and a GPU-only tree has no CPU-side tools. Nothing is
deleted; the files are in the other tree.

Enqueueing a GPU job does NOT do this. It builds through xmanager in its own
stagedir and never runs `blaze` in the shared workspace, so the symlink survives
(verified over a full claim → build → XID cycle on a GPU entry). The hazard is
your own debug build: `blaze` rewrites the symlink even in your own shell. Build
by hand in your own workspace. A shared `blaze-bin` belongs to whoever built
last.

Two quiet failure modes:

- A tool that cannot find its helper usually skips the feature instead of
  failing: a mild log line, and that guard gone. Check the guard, not the log.
- Running processes hold a resolved inode, so breakage lands at the next
  restart. A supervisor re-resolving `blaze-bin` each loop keeps "restarting"
  into a missing binary while looking alive. Unlike the stale-import trap,
  restarting is the trigger, not the fix.

Before deciding a binary is gone, resolve the symlink: `readlink blaze-bin`,
then `ls blaze-out/*/bin/<path>`. Relinking is instant. Rebuilding burns
shared-lane minutes and only fixes the link, which the next GPU build undoes.
Durable fix: name the output tree explicitly in long-lived code (supervisor,
wrapper, daemon).

## Rule 3 — BUILD A Torch GPU `py_binary` The Staging Way

The wrapper rsyncs the launch dir into a renamed stagedir and builds
`//<stagedir>:main`. Name the target `main`, the entry `main.py`, both at the
launch root (`jobs.md` §Debugging owns the renamed-stagedir idiom). Minimal
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
build plus `--help`. Do it FIRST (`jobs.md` §Debugging):

| Trap | Symptom | Fix |
|---|---|---|
| `from ml_collections import config_flags` with only the base `ml_collections` dep | `ImportError: cannot import name 'config_flags'` | Add `//third_party/py/ml_collections/config_flags`, a separate target; the JAX side gets it transitively via flax/optax |
| Using `//learning/brain/research/jax:gpu_support` for "CUDA runtime" | drags JAX's CUDA plugins into a torch-only job | Use `//third_party/gpus/cuda:cuda_runtime`: pure CUDA runtime, no JAX |

### The Dependency Versions Come From The Staging Workspace, Not From You

**The CitC workspace where the build happens decides which `torch` you link
against, so changing `STAGE_WS_ROOT` silently changes your dependencies.**
Workspaces sync to different google3 revisions, so `third_party` trees drift:
one `BUILD`, `main.py` and workdir gave `torch 2.15.0a0` from one staging root
and `torch 2.13.0` from another, same day. Two minor versions can change NCCL
and `torch.distributed` behavior, so yesterday's job can hang today with your
code untouched.

```bash
# what a workspace actually pins (semantic version AND upstream commit)
grep -m1 -A2 'version:' \
  /google/src/cloud/<user>/<workspace>/google3/third_party/py/<pkg>/METADATA
```

- Record the version at runtime: write `torch.__version__` into the first
  heartbeat. Otherwise two runs of one binary disagree and neither names its
  library.
- Do not compare workspaces with `third_party/py/torch/torch_version.py`: a
  template, identical everywhere, it reports "no difference" for differing
  trees. `METADATA` carries the real value.
- Packages do not move together: in that pair `torch` differed while `numpy`
  matched. Check the one you depend on.

First check what your code calls. The three torch ports pin nothing and need
nothing recent: plain `//third_party/py/torch:pytorch`, stable core only
(`F.scaled_dot_product_attention`, `F.rms_norm`, `F.cross_entropy`,
`torch.cuda.*`, `torch.autocast`, `torch.compile`,
`torch.distributed.init_process_group`). Both roots have all of it, `_dynamo`
included, so any port builds from either; standardizing makes "same code,
different behavior" impossible.

Different behavior across roots is a library bug, not a reason to keep both. Pin
everyone to one root and file the divergence; splitting the fleet debugs your
code for a difference that was never in it. Pick for health and sharing, not
newness: this fleet's root has an *older* torch than another on the same
machine. Fine, since the ports pin nothing, but rederiving as "newest wins"
picks differently. Worse than any version gap: a drained root that takes writes
and loses them minutes later.

### FlashAttention Is Available, With Two Conditions

**`//third_party/py/flash_attn` builds against the in-tree torch, but its
`py_library` is visibility-restricted and its version drifts per workspace.**
Three caveats, in the order they bite (the heading says two; it predates the
version-skew row):

| | |
|---|---|
| arch floor | sm80 and up: the build explicitly drops `sm_60`/`sm_70` as unsupported stubs, so A100 (sm80), H100 (sm90) and B200 (sm100) all qualify |
| visibility | the `flash_attn` target is limited to a `friends` package group. An experimental target is not in it and fails at analysis time; getting added is a review request to the owner, not a build flag |
| version skew | it moves with the workspace exactly like torch (two staging roots differed by several beta revisions), so pin the same expectations as above |

## The Startup Contract — Failures Before Your Code Runs

**A failure before your code runs measures your launch, not your hardware.**
The three rules below are one trap at three startup moments. Each mimics a
hardware, capacity, or permission problem. Name the phase, then read its rule:

| startup phase | what happens there | how it fails | rule |
|---|---|---|---|
| module import | imports run before `InitGoogle` finishes | SIGABRT / exit 134, empty app log | Rule 4 |
| flag parsing, inside `app.run` | absl parses argv, including the launcher's own selectors | `Task exited with code 1`, zero bytes on CNS, output dir never created | Rule 4b |
| process fan-out, before the first collective | your own multi-GPU spawn/fork | a google3 assertion (e.g. on `fork`) | Rule 5, trap (i) |

Consequences:

- A step that never ran proves nothing about the step after it, so record it as
  UNTESTED, not FAILED. A probe killed at fan-out says nothing about NCCL, one
  killed at flag parsing nothing about the card. A reader who sees *failed*
  abandons the path; one who sees *untested* fixes the harness.
- The cheap test is whether the job wrote its own first line to CNS. No output
  dir means it died before user code, so look here. A `start` record then
  silence means it reached the hardware stage, so these rules do not apply.
  Reproduce the launcher's argv shape on the workstation first (Rule 4b): it
  takes seconds, not a build+queue cycle.
- No status query puts "RUNNING with no output yet" in this table. XM state
  records scheduling, not progress, so XM-healthy with empty CNS fits a slow
  startup or a death above. Check the queue, because the two systems use the
  word differently. XM `RUNNING` with the queue at `SUBMITTED` usually means the
  job is waiting for accelerators, and minutes of silence are expected. Name the
  system you mean, or "RUNNING but producing nothing" sounds worse than reality.
  Queue history separates the cases:

  | queue history | what it means |
  |---|---|
  | never yet `RUNNING` | waiting for chips |
  | `RUNNING`, then an earlier state | the row was overwritten under a running task |
  | `xid` cleared | the entry can be claimed twice, putting two jobs on one workload |

  Once the queue agrees, you are waiting rather than diagnosing. Only the job's
  own output ends the wait, so put the heartbeat first in `main()`. Judge that
  wait against a measured startup for this binary. A first run has no baseline,
  so "it feels slow" is not evidence; that run supplies the baseline. A job that
  once heartbeat in half a minute and is now silent for several is stuck, not
  slow.
- Log your entry into anything that can block, not just the result. A probe that
  writes only when it finishes (an NCCL collective, a checkpoint restore, a
  large read) leaves the previous step's record and nothing after. A crash one
  line earlier leaves the same trace. One line saying *starting X* tells them
  apart.

A startup failure this table does not name belongs here, by phase, not under
whichever rule caught it.

One phase fails without failing: a flag you did not pass takes someone else's
default. Omitting `--config` does not reliably kill the job. The launcher
supplies its own default and assembles a full `configs/load_config.py:<name>`
path, so the binary gets something syntactically valid. The rest depends on the
checkout the entry packages, named in its `workdir`, not always yours:

| the packaged `configs/` | outcome | how you find out |
|---|---|---|
| no file matching the default | dies loading the config | loudly, at startup |
| a file matching the default, but not your arm | runs the wrong experiment to completion | only by reading which config it loaded |
| the binary never declares `config` at all | `FATAL: Unknown command line flag` before `main()`, fixed by Rule 4b, after which the injected flag is ignored | exit 1, zero CNS bytes, empty log; reads as hardware or permissions |
| the file you wanted | fine | — |

The second row is expensive because every state-based check calls it green. The
work unit does not fail, the task reaches RUNNING, a logdir appears, checkpoints
grow. Only the config's identity tells it from success. Verify a defaulted flag
in all five steps:

| step | do | why it is not optional |
|---|---|---|
| 0 | read the queue entry's `workdir`; every `ls` below happens *there* | that directory is what gets packaged; your own checkout may be a different tree, and an entry built from a stub `workdir` has no `configs/` at all |
| 1 | read the launcher's `DEFINE_string` default for `config` | it changes; read it, do not recall it |
| 2 | assemble the full path the launcher builds from it | the launcher composes `configs/load_config.py:<name>`; you are not passing a bare name |
| 3 | `ls` that exact filename | `grep`-ing the directory returns near-misses, and for names, similar is more dangerous than absent |
| 4 | open it and confirm it is *this* run | existence, then correct content, then the version carrying your edits; otherwise the config is right, the code is stale, and everything still reports green |

Stopping after step three gives you "there is a default, so it is fine", and
fine is the bad row. Fatal or silent differs per checkout, so another line's
answer says nothing about yours. It also differs over *time* within one
checkout. An entry dies by what its `workdir` holds right now, so an hours-old
"this will fail" verdict expires when that source changes.

Only the last row has a known fix (Rule 4b, running in production). The others
are not launcher bugs but the entry disagreeing with its own checkout; the check
above says which.

Disproving a stated cause of death does not prove survival. You refuted that
mechanism, not the outcome: the job can still die of something else, or succeed
at the wrong thing. Withdraw the mechanism, then re-derive the outcome.

## Rule 4 — No File/RPC At Module Import (InitGoogle Not Done)

**Any CNS/file/RPC op at MODULE-LOAD time aborts the task before `main()`** with
`InitGoogle() has not finished yet ... go/no_file_or_rpc_during_init`. You get a
SIGABRT (exit 134) with an empty application log, which looks exactly like an
infra fault. The threshold is InitGoogle completing (inside `app.run`), not
"imports finished". So defer any log-mirror, heartbeat or checkpoint-dir
`RecursivelyCreateDir` into `main()`. This bit even a file whose comment claimed
"after imports is safe"; the rule is after `app.run`. Parse flags with
`known_only=True` for the same reason: the launcher forwards selectors the
binary never declares. See the next rule, which cost two B200 jobs.

A GPU job MUST write its own evidence to CNS: a verdict or heartbeat with
device_count and NCCL result. The Borg log sits behind restricted-LOAS and
`analog` is blocked too (`PERMISSION_DENIED owner=analog-rdl-engine`, same LOAS
class as `aclcheck`/`ganpati`). Nothing here reads a GPU task's stdout after the
fact, and a failure leaves only the one-line `tpu check` reason. Write the proof
inside `main()` (post-InitGoogle, per above) and flush it EARLY. A soak/train job
should land `start` (with `device_count`) and a first NCCL-probe within the first
minute, so a later preemption still leaves evidence on disk.

Early is not enough. The evidence file must be append-only, never opened for
truncation and never read-modify-written. Writing early defeats "the job died
before it wrote anything" but not "the write destroyed what was there". A GPU job
restarts far more often than it fails (Rule 6: PROD migrates, and
`max_task_failures=-1` silently re-runs). The two self-destructing patterns fail
on different schedules:

| pattern | when you lose data |
|---|---|
| `open(path, "w")` per attempt | at every restart; one round survives, the current one |
| read whole file, append line, write whole file back | at every write; one interrupted rewrite truncates the lot, no restart needed |
| `open(path, "a")`, or one path per attempt | you don't |

Either destructive pattern leaves only the latest round, so the more a job
restarts, the likelier you are reading the round that needs no explanation. The
attempt worth keeping is the one with no successor to preserve it.

When you cannot change the producer (someone else's binary, a run too valuable
to restart), poll from outside and keep your own snapshots. That needs no
cooperation and no change to a running job, and after a destructive write it is
often the only surviving copy of the round that mattered. Size it honestly: its
resolution is your polling interval, so events between polls are lost just as
completely. It is a stopgap until the producer appends. One job showed both
regimes. While it truncated, a restart had to be reconstructed from two external
polls and an earlier one was missed entirely. Once it appended, the next restart
recorded itself. The only change was how the producer opened the file.

## Rule 4b — `app.run` MUST Use `known_only=True`, Or The Job Dies Before `main()`

**Every job binary launched through the shared launcher must parse flags with
`known_only=True`; a bare `app.run(main)` is a latent job-killer.** The launcher
passes flags the binary never declared: its own selectors
(`--xm_resource_alloc`, `--cell`, ...) plus, unconditionally, `--config` and
`--workdir`. It injects those into every job's `executable_args` without
checking whether the binary defines them. This is not only a large-binary
problem: `--config` alone kills a self-contained 200-line probe that declares
three flags of its own and wants nothing to do with the config system. A binary
that has not declared them dies inside absl's flag parser:

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
| zero bytes written to CNS; the output dir is never even created | user code never ran |
| empty application log | the death precedes the first `print` |
| dies seconds after RUNNING | parsing is the first thing that happens |

This failure is arch- and code-independent, so it mimics a hardware or
permission problem. Two B200 jobs from different binaries, one importing a
training stack and one a self-contained 200-line soak, died identically and
briefly looked like "B200 is broken". It was the startup contract above, at
flag-parsing time.

Verify it locally in ten seconds instead of spending a build+queue cycle:

```bash
python3 your_main.py --your_flag=1 --xm_resource_alloc=group:x/y --cell=sj
# bare app.run  -> FATAL Flags parsing error: Unknown command line flag
# known_only    -> reaches main() with --your_flag parsed correctly
```

Any new job binary should get this smoke before it is ever enqueued: the same
argv shape the launcher will use, run on the workstation, must reach `main()`.

Pass every boolean as `--flag=true` / `--flag=false`, never as the bare `--flag`
or `--noflag`. The launcher forwards an argument with no `=` as an empty string,
and absl rejects `--flag=` for a bool. The rewrite happens in the launcher's
argv splitter (`arg.split('=', 1)`, with the one-element branch assigning `""`),
so the form that works by hand is the form that dies under the launcher. It
exits 1 inside the flag parser, before `main()`: no log, no CNS line, only
`FailedWorkUnits 1/1`. This has killed jobs three times. A local run does not
prove it runs under the launcher, because the layer in between rewrites your
argv. Smoke-test the argv the launcher *produces*, not the argv you typed.

## Rule 5 — GPU Topology: One Task, N Local GPUs, You Own NCCL

**A single `--tpu_type=h100-8` is one Borg task with 8 local GPUs in one
process, not 8 tasks, and the launcher sets no `torchrun`/`RANK` for it.**
`is_tpu_job` is False for GPU: no JAX-coordination flags are injected. Spawn one
process per GPU yourself. Traps, universal to multicard torch:
- Use `fork`, from STDLIB `multiprocessing`, not `torch.multiprocessing`.
  The wrong one kills the process at fan-out, before any collective (§The
  Startup Contract, last phase). google3 patches `torch.multiprocessing` to
  `g3lib.multiprocessing`, which *asserts* on `get_context("fork")`; its
  `absl_spawn`/`absl_forkserver` replacements want
  `g3_multiprocessing.handle_main()` over `app.run()`, dying in the bazel
  runfiles resource tracker. Both dead-end on real jobs: `absl_forkserver`
  raises `TypeError` there; `absl_spawn` needs
  `g3_multiprocessing.handle_main()`, not `app.run()`, breaking the Rule 4b
  contract. That advice assumes stdlib, not a launcher job. Only stdlib
  `multiprocessing` clears both: `import multiprocessing`,
  `get_context("fork")`.
- `fork`, never `spawn`, and the parent must touch NO CUDA before forking
  (`device_count()` is fork-safe). A `spawn` child re-imports the bazel
  `__main__` and re-registers absl flags → `DuplicateFlagError`. A fork inherits
  the parsed process.
- The TRAINING path needs this fan-out too, not just a sanity smoke. Without
  injected `RANK`/`WORLD_SIZE`, a naive `train.run()` sees `WORLD_SIZE=1` and
  takes the global batch per process, which a strict reader rejects: dead at
  startup, before any step. Per child set `RANK`/`LOCAL_RANK`/`WORLD_SIZE` and
  `MASTER_ADDR`/`MASTER_PORT` (NCCL init), like the smoke.
- These GPU hosts are IPv6-only: the rendezvous address must be `::1`, not
  `127.0.0.1`. A loopback-v4 `MASTER_ADDR` fails every non-zero rank at
  `init_process_group` with `DistNetworkError ... errno: 97 - Address family not
  supported by protocol`, while rank 0 waits in the store for clients that never
  connect: a rank-0 hang, real error on the others. On B200, `::1` got all eight
  to `init_process_group_ok`. Keep the address env-overridable; read errors off
  a *non-zero* rank.
- Tier the probe so a coordination bug cannot pose as a NCCL verdict. Tier 0:
  `torch.cuda.nccl.all_reduce` over all N devices from ONE process, no
  rendezvous, no TCP store, no rank handshake. Tier 1: the real N-process path.
  Tier 0 answers "do the cards talk at all" in seconds; a failure past it is
  coordination, not NCCL. Log each verdict as it lands, or a tier-1 wedge takes
  tier 0's with it.
- Bound the collective once for the whole probe: per-rank timeouts multiply, and
  the per-rank form hides it. A per-worker deadline (`q.get(timeout=T)` over N
  ranks) drains them in sequence: worst case `N x T`, eight ranks at five
  minutes each is forty, not five. If the heartbeat only starts after the probe
  returns, that span looks like a startup death. Budget the whole probe from the
  worst case, under the interval after which people here call a job dead: how
  long silence goes unquestioned, not the operation's limit. One probe budgeted
  at eight ranks x five minutes ran 40 minutes against a fleet that starts
  asking after 5–10, reading as dead most of its life.

NVLink domain caps the fully-connected single slice (table below). Above it
chips talk network RDMA: legal, not faster for comms-bound work. The launcher
warns, does not block.

## Rule 6 — Tiers: BATCH Preempts, PROD For A Clean Finish

GPU inverts the usual TPU cost intuition. Most GPU PROD is cheap (H100 PROD
~1.0–1.2 cr/chip-hr; A100 ~0.16; GB200/GB300/H200 free pool). Most GPU BATCH is
free (0.00) but preemptible: a PROD floor-holder wanting the chips triggers a
`guarantee reclaim`. An `h100-8` BATCH smoke hit RUNNING in `mf`, then died
mid-run (`Preempted. Due to guarantee reclaim -- we were ABOVE`).

**B200 inverts the inversion. B200 PROD is ~100–120 cr/chip-hr, above its own
limit order (20.00), so it reads `BLOCKS ALL` and never launches. Yet B200 BATCH
is ~2.15, cheaper than H100 PROD.** On B200, PROD is unusable and only a BATCH
eval affordable. Numbers and their measurement live in `tpu_reference.md`
§NVIDIA GPUs; a copy here goes stale. (This paragraph said "B200 ~0.4" until it
was measured at ~250x that.)

- Short smoke you can restart: BATCH is fine and free.
- A clean finish (a real result, or a definitive smoke exit 0): use
  `--tier=PROD`, far more durable than BATCH and still cheap for GPU. Not
  immune: it has an eviction SLO (bounded frequency, advance notice). A
  fleet-wide sweep found over a hundred PROD jobs taking a `guarantee reclaim`,
  most returning. Checkpoint/resume every long run.

  GPU PROD does NOT compete with, or starve, the TPU v6p/v7 pools arc1/maze/elt
  train on.
- BATCH is preempted even inside a g9-floor slice: a higher-priority job in the
  same floor evicts it; membership is no immunity. PRIORITY is the lever:
  train/sanity GPU work goes PROD, BATCH is eval only.
- Duty cycle and the SIGTERM window rule BATCH out for training, not eviction.
  An evicted job re-queues and continues; measured runs took several and still
  held chips for hours. Not survivable:

  | | |
  |---|---|
  | **Duty cycle** | measured median **~7%** of wall-clock actually holding chips on the comparable pool: a job parked ten hours computed well under an hour. BATCH trades credits for wall-clock, the wrong trade whenever anything downstream has a deadline |
  | **Grace period** | the launcher sets no `stop_time`, so a preempted task gets the **15 s default** to react, nowhere near enough to write a real checkpoint. It is raisable to a few minutes (`Borg(stop_time=...)`, capped at 300 s below priority 120), but the effective value is `min(yours, the preemptor's wait)`, so design the checkpoint for the worst case, not the cap |

  Both are yours, not BATCH's: unusable at 15 seconds of notice and 7% duty
  cycle, only the first a one-line fix.
- Tier maps to a Borg priority in code shared by GPU and TPU, read before
  accelerator kind: no GPU-specific preemption policy exists. Family differences
  are *data*: your allocation's floor for that card in that cell, plus PROD
  pressure. So a large `Obtainable` does not predict low preemption: the BATCH
  pool mirrors PROD quota at ~100% oversubscription and counts no idle
  chips. And with no floor for a card, an allocation is all above-floor, losing
  to any within-floor claimant however long it waited.
- `--tier=PROD` does not stop MIGRATION, invisible to every status query.
  MEASURED on a `b200-8` PROD soak: 2.19 h on one host, gone ~9 minutes, back on
  a *different* host (new `hostname`, new `borg_task` id). `xmanager list` said
  `RUNNING 0/1` throughout: no failed work unit, no enforcer hit, no pruner
  signature. The *task* moved, not the work unit, and repeated: 2.19 h, ~1.3 h
  and 0.43 h between moves, ~9 minute gaps, `FailedWorkUnits` at `0/1`. Three
  lessons. (i) Checkpoint on PROD too, even when nothing fails. Three unequal
  stretches rule out a schedule, so assume no safe window. (ii) Only the job's
  per-heartbeat `uptime` caught it, via the counter reset. Emit uptime or
  restarts pass unnoticed. (iii) `uptime` gives THIS round, not total time on the
  slice; only the latter says whether an accelerator carries a long run.
  Count migrations from a record that survives them (Rule 4: append-only). Off a
  self-truncating heartbeat a count is only a floor: one lost file already hid a
  migration, an overwritten round end understates it. The truncation-proof
  tell is (`hostname`, `borg_task`): new host id, new round. Measure a round from
  its own `start` to its own last heartbeat: `start` to next `start` adds the
  migration gap, overstating by minutes. And check `FailedWorkUnits` first, since
  never failing means migration, not crash.
- The budget enforcer can kill a GPU job for a price it does not cost. MEASURED:
  a `b200-8` PROD soak ran 6 h 18 min with zero preemptions and zero failed work
  units, then `budget_enforcer` stopped it at `cost=800`. But
  `budget_check --query b200-8 PROD` returns `11.4`, and the router admitted a
  sibling at `11.4`. 800 = 8 chips x 100: a GPU family falling through to the
  generic `mapping.get(arch, 100)` default. The enforcer's header claims
  `budget_check` pricing, so compare numbers, not comments. At 800 cr/hr a
  free-pool GPU job ranks with the fleet's priciest and dies first.
  Mispricing, not preemption, is the biggest measured survival threat on GPU. If
  a long GPU job vanishes, `grep` your XID in the enforcer log first.
- A long-lived daemon prices from the table it imported at startup, not the one
  on disk, so a fix lands only on restart. Same job, same enforcer, two minutes
  apart across a restart: `cost=800` before, `cost=6` after. The fixed table sat
  on disk an hour while the daemon kept killing jobs at the stale one. A value
  frozen at process start is not only `environ` but any imported Python module,
  and nothing in the code hints at a one-time read. Check the daemon's start time
  against the mtime of what it imports. Verify the fix from the running process,
  not the file.
- A stop that reports `OK` may not have re-queued. The pause path stops first,
  re-enqueues second. If the second half fails (e.g. its CLI binary is not
  built), the log still shows the pause succeeding and the job never returns.
  Read the lines *after* the `OK`: a two-step operation reporting only step one
  is a silent success (`AGENTS.md` §Evidence Order).
- If a PROD job is held `Queued (GQM price over limit order)`, WAIT; do not raise
  its limit order. A per-job `set_limit_order` bump is banned policy. The cap is
  a blast-radius bound against overpaying at a market peak, and the price falls
  back on its own. Hand-bumping is unscalable toil that end-runs the cap. See
  `tpu_reference.md` on cap vs market.

The blanket "BATCH is eval-only / never train on BATCH" rule (`jobs.md`,
`AGENTS.md`) covers the *contended TPU* pools. For a GPU free-pool smoke the
hazard is preemption, not cost: go PROD once the run must finish.

## Rule 7 — The Real Wall Is The Budget Gate, Not Capacity Or Preemption

**On a saturated fleet, a GPU job that is *placeable* (capacity exists) and
*PROD* (top scheduling priority) can STILL never run: the 1/10-G9-income budget
bar stops it before it ever builds.** Seen live (2026-08-28): every
`gb200-{8,16,32,64}` PROD enqueue sat in `BUDGET_DEFERRED` for hours, never
reaching BUILD.

What BUDGET_DEFERRED means: before building, the dispatch/build worker calls
`budget_check.py --query <type> <tier> <lo_price> <group>`, which returns
`{income, bar, current, headroom, new_cost, fits}`:

- `bar = income / 10`: one tenth of rolling G9 income (income ~25 811 → bar
  ~2 581), shared fleet-wide.
- `current` = projected cost of ALL your live SUBMITTED/RUNNING jobs (XM-truth,
  zombie-filtered). In one sample with ~16 live jobs `current` read ~2 132 = 83 % of the bar,
  spent before the GPU job is even considered.
- `headroom = bar - current`, and it swings hard: `-211 ↔ +469` within a minute
  as other jobs start and stop. Those two readings are different instants, not
  one snapshot: the 2 132 sample sits at headroom +449, inside that range. A job dispatches only when
  `headroom >= new_cost`.
- `fits = new_cost <= headroom`. If false → `BUDGET_DEFERRED`, requeued every
  round. The fixed worker does not count these as build attempts, so the job is
  never HELD and waits forever.

The projection trap: why a cheap job looks expensive. The router queries
budget with `lo_price=0`, so `new_cost` is the full on-demand projection
(`gb200-8` → 800, from the 100 cr/chip-hr catch-all that applied before
infra-v11 gave the GPU families their own policy caps; re-derive it from
`budget_check.py` rather than reusing 800). But `_tpu_set_limit_order` auto-caps a submitted job to the
per-arch policy price (`gb200`=20 cr/GPU-hr), so its real projected cost is
~1.6. The same `budget_check --query` with `lo_price=0.20` returns
`new_cost=1.6, fits=true`. The gate rejects on a price the job never pays: a
gate-precision gap, not real unaffordability. Do NOT patch the shared wrapper/router
budget logic without operator/monitor sign-off: it is a fleet-global lever.

What actually works.
- Sizing down lowers `new_cost` linearly (`≈ 100·chips + fixed`), so `gb200-8`
  needs the smallest window. Even the fixed part can exceed a saturated bar's
  headroom, so it is necessary but not sufficient.
- Wait for a window. Left enqueued, the fixed dispatch worker re-tests every
  round and fires the instant `headroom >= new_cost`. That is in-policy
  (`monitor`: "don't idle waiting for price — queue it and go do other work").
- Free headroom you own: draining your OWN dead-weight live jobs lowers
  `current`. Terminal jobs (failed/CANCELLED) do not count, so only live
  SUBMITTED/RUNNING jobs are reclaimable. Never drain another agent's
  experiment.
- Raising the bar (more G9 income, or a separate GPU budget line) is an operator
  call, like the anti-preemption floor.

The three GPU stalls look alike in `tpu queue-status`:

| Queue state | Meaning | Lever |
|---|---|---|
| `QUEUED … no placeable cell` | no contiguous slice right now (capacity) | wait / smaller shape / other cell |
| `BUDGET_DEFERRED … over bar` | budget gate: `new_cost > headroom` | wait for window / size down / free own headroom |
| reached RUNNING then `Preempted` | BATCH lost chips to higher prio | `--tier=PROD` (Rule 6) |

A quota headroom of `0` can mean "no capacity" or "could not read the quota",
which need opposite responses. The router's floor lookup returns 0 in both
cases. The allocation has spent its floor, or it holds no floor for that chip at
all (usually, it does not play in that market). Preflight says
`Cannot verify
headroom` in the second case, but a summary that prints `0/32 = 0x` hides it.
That is an "I don't know" shown as a confident zero. Never size or reroute off
that number. Read the reason text, which does separate the cases:

| reason says | what is true | what helps |
|---|---|---|
| `your group is 99% full` | the pool is exhausted | wait; another cell may help |
| `Could not read ... quota ... Cannot verify` | nothing is known | cross-check (below) |
| `Excluded by a triggered limit order` | the price gate stopped it | another cell will not help |
| `quota=N, used=N, remaining=0` | your own alloc is spent | another cell will not help; this is per-allocation, not per-cell, so wait for your own jobs, or others on the same alloc, to release |

The last two rows open with the same phrase as the second (`PROD quota
headroom is thin`). The first clause alone puts you in the wrong row. Read on
for `quota=/used=/remaining=` numbers (alloc really spent) or `Cannot verify`
(nothing was read).

The cross-check for the unreadable case is free but narrow. A RUNNING job proves
capacity only if it is in your own group/alloc, because quota is per allocation.
Another's job of the same arch and tier shows the fleet has chips, not that you
may have any. "In stock" and "out of budget" are true at the same time, routinely.

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
- `obtainable` vs live-free works as on TPU (`jobs.md`,
  `research/accelerator_choice.md`): the capacity table is a forecast, and only a
  real short enqueue is a 100%-accurate placement test. GB200 is the sharp case:
  quota `Obtainable` badly understates live-free, and NVL72 large slices are often
  "not approved for borg scheduling". Treat gb200-8/16/32 as the safe obtainable
  shapes, and prove anything larger with a real enqueue.
- `tpu money` / `tpu quota` render GPU rows (card + tier + clearing price +
  in-force limit-order cap). As on TPU, read price before assuming which GPU you
  can get.

## Quick Diagnosis Map (GPU-specific)

| Symptom | Most likely cause |
|---|---|
| `device_count()==0` on a GPU host | `--config=cuda` missing (Rule 2); CPU-only build |
| SIGABRT / exit 134, empty app log, "InitGoogle has not finished" | file/RPC at import time (Rule 4) |
| `ImportError: config_flags` pre-main | missing `ml_collections/config_flags` dep (Rule 3) |
| anything that dies before the job's own first CNS line | a startup-phase failure, not the hardware; §The Startup Contract |
| job silently a TPU when you asked GPU (or vice versa) | used `--power` without pinning `--archs` (Rule 1) |
| reached RUNNING then died `guarantee reclaim` | BATCH preemption (Rule 6); resubmit PROD |
| `analog` / `borg tasklog` = `PERMISSION_DENIED` (restricted-LOAS) | expected here; the log wall means the app MUST self-write evidence to CNS (Rule 4). Read state via `tpu check`, not the Borg log |
| enqueued PROD, placeable, but never builds; `BUDGET_DEFERRED` | budget gate: `new_cost > headroom` (Rule 7); wait for a window / size down |
| `gb200` build never starts, worker claims→releases fast | almost always Rule 7 budget, NOT ARM build failure; check `.tpu_local_queue.json` `last_reason` for `over bar` |
| `init_process_group` fails `errno: 97 - Address family not supported`, rank 0 appears to hang | `MASTER_ADDR=127.0.0.1` on an IPv6-only host; use `::1` (Rule 5) |
| a collective raises `ncclRemoteError ... Connection closed by remote peer` | usually a *victim's* view of another rank dying; find the child the parent never had to kill (Rule 5, and the B200 notes) |
| rank 0 dies with SIGSEGV in its first collective; NCCL logs `Init COMPLETE` and no WARN | torch's `LOG(INFO)` hitting a broken debug-log sink, not NCCL; raise absl `minloglevel` in each child before the first collective (B200 notes) |
| a `faulthandler` dump file is created but stays 0 bytes | absl owns SIGSEGV from import time; capture fd 2 with `dup2` instead (B200 notes) |

## GB200 Is ARM (Grace) — The Build Cross-Compiles To aarch64

`gb200`/`gb300` are Grace(ARM CPU)+Blackwell(GPU). `xm.ResourceType.GB200`
has `architecture() == ARM`, so `xm_abc.bazel_args.gpu(GB200)` automatically
adds `--cpu=arm` and `--define=cuda_target_sm100=1` (Blackwell sm100; the
launcher delegates per-SM enables to xmanager's `GPU_TO_SM` table, so you do NOT
hardcode sm90 as for H100). A `gb200` job therefore cross-compiles the WHOLE
torch binary + CUDA deps to aarch64, a heavier and less-trodden path than x86
H100. A dep with no ARM build sends the job HELD at BUILD. That is a real build
gap (fix the dep), unlike the Rule-7 budget stall, which never reaches BUILD.
Check sizing first: `gb200-72` rounds to the nearest legal slice (`gb200-64`) at
placement time (see `tpu_reference.md` round-to-nearest-legal-slice rule).

### Chips Are Not The GB200 Bottleneck — The Budget Gate Is

**What holds a GB200 job back is the Rule 7 budget gate, not free chips.** Read
free chips and obtainable slices per cell with `slice_probe
--accel=gb200 --topology=<n> --group=9`, then pick the cell with the most free
chips. The budget gate decides whether the job ever builds, so a placeable cell
is not a schedulable one.

## GB200 Needs IMEX NVLink Authorization; B200 Does Not

**A GB200 job runs on Borg but crashes at CUDA/NVLink init unless your MDB role
is in the IMEX authorization group; B200 and the single-node GPUs have no such
dependency.** GB200 is NVL72: its NVLink domain spans nodes, so the runtime
brings up an IMEX (Internode Memory EXchange) fabric that authenticates to a
per-region IMEX-proxy CA pool. Without membership the task reaches RUNNING, then
dies (a failed work unit, not a preemption):

```
PERMISSION_DENIED: MDB role <user> is not allowed to send request to CA pool
  projects/mn-nvlink-imex-proxy/locations/<region>
```

Key facts:

| arch | NVLink domain | IMEX proxy needed? |
|---|---|---|
| `gb200` / `gb300` | cross-node (NVL72) | **yes**, at ANY size, even a single 8-GPU slice |
| `b200` / `b300` | single node (8 GPU) | no |
| `h100` / `h200` / `a100` | single node | no |

- The judge is the runtime crash, not `aclcheck`: a GB200 job reaches RUNNING,
  then fails 100% at CUDA/NVLink init with the
  `PERMISSION_DENIED ... CA pool ...` above. Do NOT cite an `aclcheck` result.
  `aclcheck` fails on the environment's LOAS restriction (no ACL-proxy /
  ganpati-read access). Its DENIED answers *whether you may query the ACL*, not
  *whether you are in the group*.
- The grant is MDB group membership; the CA-pool→group mapping is in
  source: `security/ca/ra/imex/service/config/
  startup.pi` maps the IMEX CA pool to a `*-imex-ra-users` group, mirrored in
  `production/borg/pod/miba/private-ca-front-end/server.pi`. Request it via the
  MDB/ganpati group-add flow with owner approval, not a job flag. Cover BOTH
  staging and prod RA (borglets default to STAGING), or the job fails on the
  ungranted arm.
- Single-node `gb200-8` hits the wall too. From source: the IMEX sidecar starts
  iff `IsGpuWithNvlinkDomain()` is true, only for GB200/GB300/VR200, keyed on
  CARD TYPE not node count. Every GB200 slice, even an 8-GPU tray, needs a
  grant. (`VR200` is quoted from that source predicate; it is not in
  `tpu_reference.md` §NVIDIA GPUs and we have never been able to request one, so
  treat it as a third card behind the same wall, not as an option.)
- Only cross-node NVLink cards (GB200/GB300) need IMEX authorization.
  Single-node cards (B200/B300, H100/H200, A100) never start the sidecar, per
  the same `IsGpuWithNvlinkDomain()`. So `b200` is the shortest Blackwell-class
  NVLink path pending a GB200 grant.
- Confirmed by a running job: `b200-8` initializes CUDA and sees all 8 GPUs, no
  CA-pool authorization. A `b200-8` soak on `sj` wrote from inside:

  ```json
  {"event":"start","device_count":8,"host":"ti-vm-...","torch":"2.15.0a0+google3"}
  {"event":"alive","uptime_sec":749.9,"step":629813,"device_count":8,
   "device0":"NVIDIA B200","sm":"sm10.0"}
  ```

  Eight devices visible, the card is a B200 (`sm10.0`), and the bf16 matmul loop
  ran 629k steps across 12.5 minutes. The
  `PERMISSION_DENIED ... CA pool` that GB200 produces 100% at the same stage
  never appeared. That heartbeat on CNS, not a status query, survives the Borg
  log wall and a broken CLI.
- NCCL works across all 8 B200s, single-process and with 8 processes, one per
  GPU. Single-process `torch.cuda.nccl.all_reduce` over 8 devices returns the
  correct result on every card 13 s after start. The 8-process path needs the
  logging workaround below, failing 100% without it, then matches. Prove them
  separately: a multi-process failure does not retract the single-process
  result.
- A multi-process collective dies on rank 0 with SIGSEGV, not in NCCL: torch's
  `LOG(INFO)` in `ProcessGroupNCCL::initNCCLComm()` hits a broken debug-log
  sink. The stack: `allreduce -> initNCCLComm -> LogMessage::Flush
  -> LogToSinks -> BatchingRemoteDebugLogSink::Send -> absl::Mutex::UnlockSlow`.
  NCCL is clean: zero WARN, an `Init COMPLETE` just before it, no P2P channels
  yet. `initNCCLComm()` is lazy, so the first collective triggers it (`barrier`
  too), and rank 0 alone emits that line. **Fix: in each child, after fork
  and before the first collective, `absl.flags._cpp_flags.set_flag('minloglevel',
  '1')`** — the check is the first line of `LogMessage::Flush()`, upstream of the
  sink. Use `1` (kWarning), not `2`: it stops the crashing INFO and keeps
  WARNING, NCCL's error channel. `TORCH_CPP_LOG_LEVEL` does NOT work: torch
  reads it once at import, so a child sets it too late. Two BUILD deps are
  needed, non-transitively
  (`//third_party/py/absl/flags:_cpp_flags`, `//base/python/clif:cpp_flag`); a
  `try/except ImportError` around them fixes nothing. The sink bug stands.
- A shrunk reproducer finds a bug but cannot verify the fix along the shrunk
  dimension. Two processes on two GPUs reproduced the crash above at a tenth the
  cost per iteration; signing off still needed a full-size re-run.
- torch DDP trains on 8 B200s, measured, with bf16 autocast and
  `find_unused_parameters=True`. Test it separately: a passing `all_reduce` does
  not imply a passing DDP step. The single-process form cannot host
  `DistributedDataParallel` (DDP needs one process per GPU), and backward adds
  autograd hooks, gradient buckets and async reduction. Assert against an
  analytic target, not the other ranks: give rank *r* the input `(r+1)^2`, so
  its local gradient differs from the reduced mean. Check the three collectives:
  the constructor broadcast (start each rank at a *different* weight, or a dead
  broadcast passes), the bucketed reduction after backward, and the parameter
  moving by `-lr*grad`. A linear input `r+1` is the trap: at odd world sizes the
  mean lands on the middle rank's own value, so it never fails; even-only
  schedules hide it.
- Instrument entry into every blocking step before you re-run: a probe logging
  only its result makes "blocked inside the collective" and "died on the line
  before it" byte-identical. The diagnosis above took three runs: one hit the
  `fork` assertion of Rule 5; one hung with no way to say where; one named its
  own failure, once a breadcrumb marked ENTRY to each blocking call.
- `faulthandler.enable(file=...)` silently does nothing in a google3 binary, so
  capture fd 2 yourself. `absl/app.py` registers CPython's dump function into
  absl's failure chain at IMPORT time and refuses a second registration. So your
  `enable(file=...)` creates the file and never writes to it. The traceback
  goes to **fd 2**, unreadable on Borg from an agent sandbox (`analog` and
  `borg tasklog` both fail LOAS). `dup2` each child's fd 2 onto your own file
  and upload it; it also catches NCCL's and the driver's writes, which bypass
  Python.
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
- One explanation the evidence does not support: the torch version changed
  underneath. The build did move between staging workspaces, and the linked
  torch went back two minor versions (§The Dependency Versions Come
  From The Staging Workspace). But the probe's whole API surface is
  `dist.{init_process_group,all_reduce,barrier,destroy_process_group}` plus
  `torch.cuda.*`, present in both. The version is a *variable left uncontrolled*,
  not a diagnosis. To settle it, run the identical probe from both workspaces.

## Accelerator Names, NVLink Domains, Capability

See `tpu_reference.md` §NVIDIA GPUs for the arch tokens, `xm.ResourceType`
kwargs, NVLink domain sizes, and per-chip capability. The credit-limit caps live
in `~/work/tpu_cmd/tpu_wrapper.sh::_tpu_limit_price_for_arch` (a100=5,
h100/h200=10, b200/b300/gb200/gb300=20 cr/GPU-hr). Those caps are blast-radius
bounds far above market, not trackers.

