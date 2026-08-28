# HANDOFF — codi-torch-port (v1 → v2)

> **I am at my most authoritative the moment I hand off — I just finished the
> investigation, my evidence is fresh, and you know nothing. That is exactly
> when my errors are most likely to be inherited whole. "Verify it yourself" is
> not politeness; it is the only defence against authority amplifying across a
> handoff.**
> (Rule from monitor-v42's retirement. It caught two real errors tonight,
> including one of v42's own conclusions.)

## ⚡ START HERE — state as of 2026-08-28 17:20Z

**Three sentences:**
1. Code: `~/work/codi-torch` (git worktree, branch `codi-torch`, 22 commits),
   launch dir `torch_impl/`. Purpose: port CODI (arXiv 2502.21074) from JAX/TPU
   to PyTorch on Borg GPU, aligned key-for-key with the JAX baseline XID
   284048646.
2. Target: the official CODI GPT-2 latent-greedy GSM8k ≈43.7%. **This half is
   DONE** — the official released checkpoint loads (251 keys, 0 mismatch) and
   scores **46.00% (N=150, 95% CI [38.0, 54.0])** through our eval, so the eval
   is independently validated and a training-side miss can be attributed.
3. GPU: one step away. Five runs cleared staging / CUDA (`8 GPU visible`) /
   `stdlib/fork` / NCCL `set_device` ordering; #5 hung because the per-rank
   logging I added *to diagnose* the previous hang wrote to CNS from a forked
   child. Fixed in `7d2f913` (writes to local `/tmp` instead), verified
   locally. The scheduler is down for a rewrite by infra-v12; one launch after
   it returns should produce the first `codi_train] step`.

**Do this first when the scheduler is back:**
```bash
cd ~/work/codi-torch/torch_impl
source ~/work/tpu_cmd/tpu_wrapper.sh
# probe the staging root FIRST (health is a fact with an expiry date):
S=$STAGE_WS_ROOT/experimental/qiaos/eqr_jax_final_stages   # default may have changed
echo p-$(date +%s) > /tmp/p && cp -f /tmp/p $S/__probe && sleep 6 && cat $S/__probe
tpu enqueue --power=h100-8 --archs=h100 --tier=PROD --cell=yucbfad \
  --launch=group=9,exp_name=codi_torch_h100_v4,app.smoke_steps=60
```
★ **`--cell=yucbfad`, NOT `--metros`.** `yucbfad` (cbf) is the only h100 cell
inside a data metro; `--metros` silently does nothing whenever the `pick_cell`
binary is missing, which happened today.

**Then, to read the result:** `bash $ART/check_gpu_run.sh <XID>`, and remember
an XID proves LAUNCH only — confirm with `xmanager.par list` AND a logdir on
CNS. The bucket differs per run; read `bucket_cp_path` from `~/.tpu_jobs.json`
for that XID.

**The five runs and what each proved** (details in §7 and §15):

| XID | died of | what it established |
|---|---|---|
| 284313288 | ghost staging + missing `utils/` erased the evidence | — |
| 284359695 | bad root → ran ELT DiT's target | the `[launcher] config.sh=` tell |
| 284360081 | `absl_forkserver` | **CUDA works: `8 GPU(s) visible`** |
| 284367273 | 8× SIGABRT | **`stdlib/fork` works on the real machine** |
| 284380582 | my own CNS-write diagnostic | NCCL ordering fix held (no SIGABRT) |

---

**Evidence grades used throughout — every claim carries one:**
- `[V]` VERIFIED — I ran it and read the output.
- `[C]` CODE-READ — I inferred it from source I read; not executed.
- `[T]` TOLD — someone told me; I did not verify.
- `[F]` FALSIFIED — I believed it, then disproved it. Do not pick it back up.

---

## 0. What this line is

Port the CODI line (arXiv 2502.21074, continuous chain-of-thought via
self-distillation) to PyTorch on Borg GPU, aligned to the JAX/TPU baseline so
the two are comparable, and reproduce the published **~43.7%** latent-greedy
GSM8k accuracy.

**Not a model rewrite.** Upstream is already torch; the work is infra + exact
alignment.

| thing | where |
|---|---|
| my code | `~/work/codi-torch`, branch `codi-torch` (git worktree of `~/work/codi-jax`), 18 commits on top of the JAX line's `codi-repro` |
| launch dir | `~/work/codi-torch/torch_impl/` — enqueue FROM HERE |
| JAX baseline source | `~/work/codi-jax`, branch `codi-repro` |
| official torch reference | `~/work/codi-jax/_codi_reference/torch_{model,train,test}.py` (untracked; I copied it into codi-torch too) |
| my artifacts | `~/.amply/artifacts/20260827-203017-6f6f4471/` |

---

## 1. Acceptance chain — WHAT LAYER EACH IS AT, and what is still missing

The operator's three stages, stated as "how far, and what the gap will cost".

### ① Semantic alignment — DONE to the level of "every number I could check matches"
`[V]` all of the following, each with a negative control:

| property | result | test |
|---|---|---|
| parameter count | **exact**: 20,057,088 = LoRA 18,874,368 + prj 1,182,720, total 144,499,200 | arithmetic reproduces observed |
| first-step losses vs baseline | KD term within 12% (0.49645 vs 0.44497) | `tests/test_model.py` |
| DP gradient | 4 ranks × 4 rows == full batch to **3e-08** | `tests/test_dp_semantics.py` |
| bf16 split | 22 trainable fp32 / 28 frozen bf16, zero exceptions | `tests/test_mixed_precision.py` |
| weight-decay mask | JAX name-rule and torch shape-rule agree on EVERY leaf | `tests/test_weight_decay_mask.py` |
| preemption | survives 3 SIGKILL cycles, monotonic progress | `tests/test_preemption_resume.py` |
| tokenization | byte-identical to the JAX line on 64 real rows | `tests/test_pipeline_parity.py` |

**STILL MISSING, and when it bites:** the loss *trajectory* has only been
compared at step 1 vs the baseline's step 20 — i.e. same regime, not same curve.
The tool to do it properly exists (§4) but has never been run against real torch
GPU output. **If the port has a subtle scale error, this is where it shows, and
nothing so far would have caught it.**

### ② GPU run works — NOT DONE. Never executed on a GPU. Zero GPU seconds so far.
`[V]` everything below is CPU or bazel-on-CPU only:
build ✅ · `--help` ✅ · `--sanity_only` ✅ · full training smoke on real CNS
data ✅ · `--eval_only` ✅ · `--smoke_steps` early stop ✅ · `known_only`
absorbing two undeclared flags ✅ · clu Datatables writer live in bazel ✅.

**STILL MISSING, in priority order:**
1. **CUDA actually reaching the process.** `--config=cuda` is added by the
   launcher `[T]` (gpu_on_borg.md; I never saw the log line myself). A CPU-only
   build reports `device_count()==0` and looks otherwise fine.
2. **The 8-way fork + NCCL DDP path.** `[V]` the topology DECISION logic
   (`num_gpus=0` → 8, over-request clamped). `[C]` the fork itself — never
   executed, because CPU gives `world_size=1`. **A `spawn` child would hit
   `DuplicateFlagError`; I use `fork` and the parent touches no CUDA before it,
   but this is code-read, not verified.**
3. **Measured sps.** Everything in `REAL_RUN_PLAN.md` about hours-to-finish is
   ARITHMETIC (§5).

### ③ Reproduce the official number — DONE for the EVAL half, NOT STARTED for training
`[V]` The official released checkpoint (`zen-E/CODI-gpt2`, already in the local
HF cache) loads into this model with **251 keys, 0 missing, 0 unexpected**, and
scores **46.00% (69/150)**, se 4.07, **95% CI [38.0, 54.0]** — the published
43.7% is inside it.

**What that does and does NOT establish.** It establishes the eval is correct,
independently of any training run, for minutes of CPU. It establishes NOTHING
about whether our training produces such a checkpoint. **The value is
diagnostic: a from-scratch run that misses 43.7% now implicates the TRAINING,
and the eval can be ruled out without argument.**

---

## 2. Five real bugs found. Each would have looked like success, or like a model problem.

`[V]` all five — found by a test that failed, not by reading.

1. **Weight snapshot aliased the live params.** `.detach().cpu()` on a CPU
   tensor is a VIEW. The resume assertion compared a tensor with itself and
   reported "all 22 tensors unchanged" against a checkpoint that had
   demonstrably trained (nonzero lora_B; peft inits B=0). Same aliasing would
   have let the ASYNC saver serialise weights the trainer had already moved
   past — a file labelled step N holding step N+k's parameters. Fixed with
   `.clone()` in three places; `tests/test_ckpt.py` has a regression.
2. **Restart after the schedule completed** re-entered the loop, wrote another
   checkpoint, exited 0. On a preemptible run: an infinite loop wearing the
   costume of a successful job.
3. **Eval padded to a fixed 192** (copied from the JAX line, where it is an XLA
   constraint). With `fix_attn_mask=False` the latent loop sends NO attention
   mask, so pad tokens corrupt the continuous thought. 2/6 → 3/6 on the official
   weights by changing only this.
4. **Eval batch_size > 1.** Same mechanism one level up — the reference's
   `DataArguments.batch_size` defaults to **1**, so the published number has NO
   cross-row padding. **32.50% → 42.50%.**
5. **`coconut/` was absent from the launch dir.** `data.py`/`evaluate.py`/
   `jax_free_pipeline.py` import `coconut.data_util`, which lives in the REPO
   ROOT. The launcher rsyncs ONLY `torch_impl/`. On Borg the task would have
   died at import, pre-main, behind the log wall, with no traceback. **Every
   local bazel run had hidden this because I populated the isolated checkout
   with an explicit `cp` — I propped the door open myself.** Fixed by vendoring
   `data_util.py` in, with `tests/test_data_util_copy.py` failing on sha256
   drift.

Bugs 3 and 4 are the expensive ones: from scratch they present as "our
reproduction misses 43.7%" and the model takes the blame for days.

---

## 3. Baseline: what it IS, verified from its own artifacts

`[V]` Baseline = XID **284048646** (`codi_train_false_gpt2_v7`, v7-32 PROD).
Evidence is the job's OWN runtime output — `logs/rank_0_attempt{1,9}.log` and
`checkpoints/step_13500` — **not a yaml, not a memory**. (This check exists
because the parcae line discovered it had assumed the wrong baseline.)

19 config keys matched. **Two diverged:**

| key | baseline observed | mine | verdict |
|---|---|---|---|
| `seed` | **11** | was 0 | REAL BUG, fixed |
| `save_every_n_steps` | **500** | 2000 | deliberate — baseline predates the fix commit. **CONSEQUENCE: `sps` is NOT comparable between the two runs. Every loss column still is.** |

`[V]` Also: the baseline resumed from its own `step_5000`, so **its curve's
origin is not step 0**. Do not align curves at zero.

---

## 4. The trajectory comparator — AND ITS CALIBRATION BASIS

`$ART/compare_to_baseline.py` + `$ART/baseline_first_steps.txt` (46 real points,
steps 20→920, from the baseline's COLD-START attempt1).

`[V]` Three-tier verdict, and **why the thresholds are where they are**:

| median \|rel loss\| | verdict | basis |
|---|---|---|
| < 8% | trajectories track | **The JAX line's own audit found two HIGH bugs (train wd-mask, eval encode mask). Both move the curve by MORE than 8%. The threshold is set so that a bug of the class this project has actually shipped would be caught.** Below that is framework/accelerator numerical scatter. |
| 8–40% | LOOSE — a systematic offset this size is not scatter | check seed, warmup fraction, wd mask |
| > 40% | DIVERGENT — do not start a long run | suspect seed, data order, wd mask, KD normalisation, warmup |

`[V]` Negative controls run: baseline-vs-itself → 0.0% (track); synthetic +15%
→ LOOSE; synthetic +60% → DIVERGENT.

`[V]` **The negative control caught a bug in the tool itself**: the first
version's 15% threshold classified a synthetic 15% systematic offset as "track".
**If you change the threshold, re-run the three controls.**

---

## 5. `[F]` FALSIFIED / DOWNGRADED — do not pick these back up

1. **`[F]` "H100 is representative of GPU-vs-data locality."** I checked h100
   only, found 0/5 data metros, and concluded GPU and data are fundamentally
   misplaced. **Wrong.** `[V]` A100 hits **4/5** (js=cbf, nf/oa=tul, rw=dfw) and
   is 3.5–4.5× cheaper (0.14 vs 0.49–0.64 cr/chip-hr). H100 is the outlier, not
   the rule. **Lesson: I generalised from one family.**

1b. **`[F]` "H100 has NO data metro at all" — the correction above is ALSO
   wrong, and this one changed the decision.** `[V]` `tpu preflight
   --tpu_type=h100-8` lists candidates td(tpe) / gd(uos) / lcsydv(syd) /
   mf(ckv) / yurnoaa(rno) — none near our data, every time I ran it. But
   `tpu queue-status` on a LIVE h100 job reports:

       h100-8-a0f015  PLACEABLE now: h100-8 -> yucbfad (4 free slice(s))

   and `[V]` `mach_locality -k metro yucbfad` = **cbf** — the same metro as
   `is-d`, our PRIMARY data mirror. **`yucbfad` never appears in preflight's
   candidate list.** This is `gpu_on_borg.md`'s "obtainable is a forecast,
   live-free is the only truth", caught in the act.

   `[V]` Sampled three times, 25s apart, stable: a100-8 "no placeable cell"
   every time; h100-8 "PLACEABLE now -> yucbfad" every time. So I enqueued
   `h100-8-c27e8f` with `--metros=cbf` and kept the a100 job queued alongside
   (costs nothing, whichever lands first wins). h100 is 1.55x more expensive per
   unit of compute but 3.16x faster AND placeable; an unplaceable bargain is
   worth nothing.
2. **`[V]`→DOWNGRADED: the hours-to-finish table in `REAL_RUN_PLAN.md` is
   ARITHMETIC, not measurement.** It rescales the baseline's v7-32 sps by
   v5p-units, stacking three assumptions (perfect DP efficiency at every width;
   a torch step costs the same as an XLA step per unit; the baseline's 4.0 sps
   is clean — it is not, its cumulative read 2.1). **Do not quote those hours as
   observed.** I tried to shortcut with the CPU real-model smoke and abandoned
   it: batch 2 on CPU says nothing about batch 128 on 8 GPUs. **The queued smoke
   carries `app.smoke_steps=60` precisely to produce the honest number.**
3. **`[F]` "the build queue is stuck / nobody claimed my job."** `[T]`→`[V]`
   monitor-v42 corrected this and I confirmed: `worker_id: null` is normal
   "not your turn yet" under a deliberately SERIAL builder.

---

## 6. ★ Live infra finding that CONFLICTS with monitor-v43's briefing — verify before using either

`[V]` measured 2026-08-28 ~06:10Z, while my job waited:

```
/tmp/tpu_build.host.lock  → HELD
lock holder  = xmanager.par pid 1837129, running 1h48m
  syscw       60708 → 61006 over 6s   (increasing → issuing syscalls)
  write_bytes 154243072 → unchanged    (not writing)
  %CPU        0.7                      (not computing)
pgrep blaze  → NONE (only amply workers)
```

### `[F]` MY FIRST READING OF THIS WAS WRONG — and it is the best illustration of why every line here carries an evidence grade

From those numbers I concluded "the holder is not compiling; `xmanager.par` is
stalled in RPC while holding the lock" and reported that to v43 as a conflict
with their briefing. **That inference was wrong.**

`[V]` Twenty minutes later, on the NEXT lock holder (pid 2760013, holding 29
min), I followed the child processes instead of the counters and found:

```
child: tee -> ~/logs/eqr_run_260828_054625_0349f5/xm_launch.log
that log's last three lines:
  This build is running in Skybuild mode (http://go/skybuild-dbip)
  INFO: Streaming build results to: http://sponge2/cabc9187-...
  INFO: See http://go/buildz/dbip-b30454a5-... for more information
log size 288 bytes, unchanged over 8s; local syscw frozen; no local blaze process
```

**It IS building — remotely, via Skybuild.** Every signal I had used as proof of
"not compiling" (no local blaze process, flat `write_bytes`, ~0% CPU) is exactly
what a REMOTE build looks like from the local box. My three indicators could not
distinguish "not compiling" from "compiling elsewhere", and I did not notice.

`[V]` And in the same snapshot, both of v43's halves were present at once:

```
pid 2760013  holds the lock, 29 min, in Skybuild
pid 2975003  `flock -w 1800 201`, BLOCKED 4m54s   <- genuinely queueing for the lock
```

So v43's model ("BUILDING does not distinguish compiling from waiting-for-lock")
is right, and my "third pathology" was an artifact of my own measurement.

**The lesson for you, successor:** I applied v43's own recommended judgment
criteria — lock holder, `/proc/<pid>/io`, blaze presence — correctly, and still
reached a false conclusion, because the criteria have a blind spot for remote
builds. **Follow the child processes and read their logs; counters on the parent
are not enough.** This is what `[V]` vs `[C]` is for: I had marked the
measurement `[V]` (it was real) but the CONCLUSION drawn from it was `[C]`, and
I had not separated them.

`[V]` My job is UNHARMED by all of it: `attempts: 0`, `last_reason` full text
has no timeout string.

`[T]` (unverified, from v43, worth knowing): `HELD` is recoverable —
`requeue_held()` resets attempts to 0; only `FAILED` is terminal. Do not take
anxious action over rising attempts.

`[T]`+`[C]` v43's stagedir-cache hypothesis: `tpu_wrapper.sh:744-755` makes a
new random-suffixed stagedir per build → Blaze caches by label path → 100% miss
→ ~47min cold builds. **`[C]` I read that the wrapper does rewrite TARGET_LABEL
to `//<stagedir>:main`, consistent with the hypothesis. NOT verified by me.**
**Successor task worth doing:** evaluate whether this torch target can live at a
STABLE label (e.g. under `//experimental/users/qiaos/...`, which is how I built
locally) instead of a random stagedir. `[V]` My local isolated build at a fixed
label took **26s warm** vs the wrapper's cold-build wall. If that works, this
line skips the whole problem.

---

## 6b. ★ THE PATTERN BEHIND BOTH OF MY WRONG CONCLUSIONS — read this one

Twice tonight I stated something confidently and had to retract it:

  * "the lock holder is not compiling" — it was, remotely, via Skybuild;
  * "H100 has no data metro" — it does, `yucbfad`/cbf, invisible to preflight.

**Same failure both times: I drew a conclusion from ONE source and did not look
for a second one that could contradict it.** Local process counters cannot see a
remote build. A preflight forecast cannot see live-free capacity. Neither source
was WRONG — each was simply blind in a direction I did not check.

**The rule, for you:** before writing a conclusion into this document, name the
second, independent source that would have shown it false — and go look at it.
If you cannot name one, mark the claim `[C]`, not `[V]`.


## 7. Current state / immediate next steps

`[V]` **THREE jobs queued (state as of 12:05Z), all PROD, both from
`~/work/codi-torch/torch_impl`, both `app.smoke_steps=60`:**

| job | shape | metros | state at 12:05Z |
|---|---|---|---|
| `a100-8-84f798` | a100-8 | cbf,tul,dfw | `QUEUED`, attempts 0 |
| `h100-8-c27e8f` | h100-8 | cbf | `QUEUED`, **attempts 1** (lock starvation, NOT a build failure) |
| `h100-8-d21148` | h100-8 | ckv,rno,uos | `QUEUED`, attempts 0 — **the one to watch**; it is the only one built from the code that has `utils/` vendored |

A queued job is free and they do not conflict; whichever the serial builder
reaches first wins. **Set the others to HELD once one lands** (never dequeue).

### ★ The one GPU job that DID run, and why it failed — read before relaunching
`[V]` **XID `284313288`** (`codi_torch_h100_na`, h100-8 PROD, cell **`yurnoaa`**,
logdir `/cns/yutulpz-d/home/qiaos/eqr_data/logs/codi-torch/xid_284313288_20260828_092526_codi_torch_h100_na`).
Reached `RUNNING`, then `NOT_RUNNING 1/1`. **Zero CNS bytes, zero logs, logdir
never created.**

`[V]` The launcher side was clean — the launch log
(`~/logs/eqr_run_260828_092059_3d8228/xm_launch.log`) shows
`[gpu] bazel CUDA build flags for h100: (... --config=cuda ... sm90=1)`. So
Rule 2 was satisfied and the CUDA trap is NOT the explanation.

`[V]` **Root cause: `main.py:113` does `from utils import log_mirror`, and
`utils/` lived in the REPO ROOT while the launcher rsyncs only `torch_impl/`.**
The import sits in a `try/except`, so it was not fatal — it meant THE LOG MIRROR
NEVER STARTED ON BORG. **The zero logs were not a symptom of the crash; they
were a second, independent defect that destroyed the evidence of the first.**

`[V]` Fixed in commit `0252c68` by vendoring `utils/{__init__,log_mirror}.py`
(pure stdlib), verified by rsyncing `torch_impl/` alone to `/tmp` and running
with no parent repo on the path: `log mirror -> /tmp/wd2/logs/rank_0_attempt1.log`
now appears. `[V]` I then audited EVERY parent-relative import in the launch
root — only `coconut.data_util` and `utils.log_mirror` — and verified both
import in an isolated stagedir.

★ **UPDATED 12:32Z — there is now a stronger suspect than anything below, and
it is NOT in my code.** `[V]` I reproduced, on the shared staging root every
line's build goes through:

```
S=/google/src/cloud/qiaos/elt_jax/google3/experimental/qiaos/eqr_jax_final_stages
cp -f /tmp/probe $S/__codi_probe.txt   -> rc=0
cat  (immediately)                     -> probe-codi-1787920268   <- reads back!
cat  (t+5s)                            -> No such file or directory
```

**`elt_jax` — the wrapper's DEFAULT `STAGE_WS_ROOT` — is silently discarding
writes.** `rc=0`, correct read-back, gone seconds later. Only a DELAYED re-read
catches it; a content hash would also have said green.

`[T]` codi-v6 traced the full chain and it fits my failure exactly: staging
lands -> wrapper's completeness guard passes (it checks at submit time only) ->
**the job waits 30-90 min for the build lock** -> CitC rolls the writes back ->
by the time the lock arrives the stagedir is empty -> launcher cannot find
config.sh -> dies. **So `Errno 2` / empty logs are the symptom of a symptom.**

**Revised attribution for XID 284313288:** the missing `utils/` was a REAL
defect and is fixed (`0252c68`), but it explains only why there was no
evidence, not why the task died. The likely primary cause is an empty stagedir.
`[V]` Five other workspaces (clip_probe, gemma_probe, mlcr_probe,
jax_llava_probe, run_amply_workspace) all passed the same 5s probe; only
`elt_jax` fails it. A minute-scale probe is running because `[T]` v45 warns the
5s form cannot detect the "token drained" variant.

★ **OPEN: the actual cause of the task's death is still not PROVEN.** With the log
mirror dead there is no evidence, and Borg's `lookupterminations` is
LOAS-blocked on this workstation (tried `yurnoaa`/`mf`/`gd`: "job cannot be
found"). `h100-8-d21148` is the retry that should finally produce a log. **If it
also dies silently, the next suspects in order are: (1) `absl_forkserver` being
broken under runfiles (see §7b — parcae measured this), (2) the two-layer flags
issue, (3) something in the CNS write path from a cell with no bucket mapping.**

★ **KNOWN DEFECT, unfixed:** the checkpoint bucket resolves to
`/cns/yutulpz-d/...` (**tul**) while these jobs land in ckv/rno/uos — A100/H100
cells are absent from `xm_launcher.py::_CELL_BUCKETS`, so it falls back to the
default. **Harmless for a 60-step smoke that barely writes; for a long run this
is exactly the cross-metro checkpoint pattern `storage.md` says the pruner
kills.** Fixing it means either passing an explicit `--bucket` or getting the
cells added to the shared launcher (operator-level; the red lines forbid editing
it unilaterally).

**Next, in order:**
1. When it lands, run `$ART/check_gpu_run.sh <XID>` — it answers, in order:
   did CUDA reach the process / did fork+NCCL work / what is the MEASURED sps.
2. Feed the run's log to `$ART/compare_to_baseline.py` for the trajectory
   verdict. **Needs `log_every_n_steps=20` to line up with the baseline's
   points** — the remote_run config already uses 20.
3. Re-derive `REAL_RUN_PLAN.md`'s table from the measured sps. **Only then**
   choose hardware for the full 40-epoch run.
4. Open operator decision: where the full run goes. a100 = data-local but slow;
   b200 = only GPU finishing in ~a day but needs a CNS dir + 650MB mirror first
   (`/cns/sj-d/home/qiaos` does not exist `[V]`); h100 = no data metro at all.

## 7b. ★ TONIGHT'S HARD-WON FLEET FACTS — these will bite you, verify each yourself

`[T]` from monitor-v44 unless marked otherwise. Each is here because a line
already paid for it.

### The flags fix is TWO layers, not one
`[T]` (trm-torch-port-v2, measured) The single line I was given and used —
`app.run(main, flags_parser=lambda argv: FLAGS(argv, known_only=True))` — covers
only the SECOND parse. `app.run()` re-parses argv, so the complete form is:

```python
flags.FLAGS(sys.argv, known_only=True)              # layer 1: eat unknown flags
app.run(main, argv=_parse_known_only(sys.argv))     # layer 2
```

`[V]` **MY BINARY PASSES THE EXECUTION TEST WITH THE SINGLE-LAYER FORM** — I ran
`main.py --sanity_only --xm_resource_alloc=group:x/y --cell=sj
--xm_deployment_env=alphabet --noxm_monitor_on_launch` in BOTH the venv and the
bazel binary and got `PASSED`, exit 0. **OPEN:** I do not know whether that is
because the single layer suffices here or because my flag set happens not to
trigger the second parse. **Successor: do not "fix" this on the strength of the
briefing alone — re-run the execution test, and if it still passes, leave it and
record why.**

### `absl_forkserver` — the fix I applied MAY BE WRONG
`[V]` I measured that plain `fork` is blocked in the bazel binary
(`AssertionError: Use of 'fork' is discouraged in Google3, go/python-tips/018`)
while the venv forks happily, and that `absl_forkserver` reports `context OK`
there. I changed `train.py` to prefer `absl_forkserver`.

`[T]` **parcae then measured that `absl_forkserver` is BROKEN under g3 bazel
runfiles** — `TypeError: expected bytes, NoneType found`, dying in the resource
tracker — and that `absl_spawn` requires `g3_multiprocessing.handle_main()`
instead of `app.run()`, which conflicts with the launcher contract. **Their
conclusion: the only working option is stdlib `import multiprocessing` →
`get_context("fork")`, because only `torch.multiprocessing` is patched.**

★ **OPEN, AND IT WILL BITE ON THE FIRST MULTI-GPU RUN.** My `probe_mp` only
called `get_context()`; it never started a child under `absl_forkserver`.
`context OK` and `works` are different claims and I conflated them — the same
error shape as everything else tonight. **Successor, do this FIRST:**
`main --probe_mp` in the bazel binary, and extend `_probe_multiprocessing()` to
actually START a child under each method, not just fetch the context. Then try
stdlib `multiprocessing.get_context("fork")` as parcae recommends.
`train.py::_worker_context()` already walks a preference list, so the fix is to
reorder it — but **measure before reordering**.

### Judging whether a lock holder is stuck (four rounds of correction)
`[T]` Final version, after maze128-v7 / v44 / parcae each got it wrong once:
- `STAT=D`, `age`, `waiter count` — **none distinguish dead from slow**;
- process-aggregate `syscw` — polluted by unrelated threads (a 67-thread process
  can show progress while the ONE build thread issues zero syscalls);
- `write_bytes` over a 3-5s window — **false negatives** from page-level
  buffering; needs ≥60s;
- ★ the judgement that held: **find the D-state THREAD, read
  `/proc/<pid>/task/<tid>/io` over ≥60s, AND check the size of the BUILD PRODUCT
  (`xm_launch.log`), not an internal log (`BINARY_INFO`)**.

`[T]` And the exit-condition assumption everyone shared was wrong: srcfs
recovering does NOT free the lock. A holder blocked on an old-mount inode is
waiting for a reply that will never come. Only its own timeout, or another
srcfsd restart, releases it.

**`[V]` What this cost me:** `h100-8-c27e8f` went to `attempts=1` with no build
of its own ever running. That is LOCK STARVATION, not a build failure — my own
build takes 26s warm (§10). `last_reason` containing `timed out after 1800.0
seconds` means "waited for the lock", not "your code is broken".

### Queue hygiene
`[T]` **Never `dequeue`** — a concurrent writer rolls deletions back (six
entries across three lines came back tonight). To retire an entry, set it to
`HELD`. **Never `tpu requeue`** — it silently drops `load_from` and `metros`.
`HELD` is reversible and loses no progress.
`[T]` To ask "was this XID re-queued", match `launch_kwargs.resume_xid == <xid>`
— NOT the `xid` field (that is the predecessor, not the successor), and never
`grep <xid> queue.json` (hits other entries' free text).
`[V]` I checked my three jobs this way: all have `resume_xid=None`, so none was
ever enforcer-paused, and their `load_from=None` is correct (a 60-step smoke has
no progress to resume).

### Do not submit new builds while the lock is starved
`[T]` As of 12:12Z the build lock is held by pid **2016059** and **v44 measured
both escape routes closed**: it has `ppid=1`, no timeout wrapper, belongs to the
NPU-side queue and is already 3x past 1800s (so it will not end itself); and the
sentinel will not restart srcfs (D-count 4 vs threshold 15, srcfsd 4.8G vs 18G,
srcfs itself healthy). ★ **So this lock does not come back without manual
intervention — not "not soon", but not at all.** Fleet-wide builds have been
stopped ~90 min.

**Consequence for you:** every queued job of mine is waiting on that lock, and a
NEW submission would burn its full 1800s budget waiting and take an
`attempts+1`. **I stopped submitting. Do not resume until that pid is gone** —
check with `lsof -t /tmp/tpu_build.host.lock`. Processing is otherwise unchanged:
**do not kill it, do not jump the queue, do not requeue.** It is another line's
resource, its main thread is in D-state (SIGKILL would produce a zombie that
still holds the lock), and an earlier well-meant intervention at 09:14Z burned a
92-minute build that was actually progressing.

### ★ The meta-lesson worth more than any of the facts above
`[T]` v44's closing note, after one judgement took four rounds across four lines
to settle (`STAT=D` → process `syscw` → `write_bytes` → per-thread I/O of the
D-state thread), each round wrong in a different way:

> **Reaching for a finer instrument is not the same as asking a better question.
> Ask HORIZONTALLY — "am I measuring the thing that is actually blocked?" —
> rather than asking the same wrong question with more precision.**

`[V]` My own two retractions tonight (§6b) and my `absl_forkserver` mistake
(§7b) are all this shape: `context OK` measured something adjacent to "fork
works", local process counters measured something adjacent to "is it
compiling", and a preflight forecast measured something adjacent to "can this
be placed". **Before you trust a measurement, name the thing you actually want
to know and check that your instrument is pointed at it.**

### Reaching the monitor
`[T]`+`[V]` The monitor rotates several times a day and **two lines
mis-delivered reports tonight because `send11` returns success for a dead
recipient**. Never hardcode the rid; look it up, and note it is NOT the last
line of the file:

```bash
grep -a "# THIS MONITOR" ~/work/.monitor_watch/runs.txt \
  | grep -oE "20260[0-9]{3}-[0-9]{6}-[0-9a-f]{8}" | head -1
```

`[V]` Verified against the v44→v45 handover: the command returned
`20260828-121031-f8fa5ceb`, matching the broadcast, and the handoff md5 on disk
matched the one broadcast (`93096f98ec59ec3dbc03257e59d0f409`). **Cross-check
both before believing either.**


## 8. Red lines (verbatim, unmodified)
- **NO `set_limit_order` job-level price raising.** Price is high → wait.
- **BATCH is eval-only. Every training job `--tier=PROD`.**
- Never `xm launch` / `xmanager launch` — only `tpu enqueue`.
- Do not modify shared `~/work/tpu_cmd/tpu_wrapper.sh` or `xm_launcher.py`.
- Do not touch lyy's sealed CUDA oracle gate.
- Serial builder: one build at a time. Do not requeue to jump the line.
- `elt_jax` is a SHARED checkout — protect dirty worktrees.
- ⚠️ Board has `codi_train_false_gpt2_v4/v7 HELD by the CODI v5 line` — that is
  the JAX TPU line, a DIFFERENT session. Do not touch it.
- **Never `dequeue`; never `tpu requeue`.** Retire an entry by setting `HELD`.
- **Do not hardcode the monitor rid.** Look it up:
  `grep -a "# THIS MONITOR" ~/work/.monitor_watch/runs.txt | grep -oE "20260[0-9]{3}-[0-9]{6}-[0-9a-f]{8}" | head -1`
  (do NOT "take the last line" — the last line is another line's entry, and two
  lines mis-delivered reports that way tonight).

## 9. Environments
- torch+peft: `~/.codi_venv/bin/python` (torch 2.13.0+cu130, peft 0.13.2, transformers 4.46.2)
- JAX (for the parity test only): `~/miniforge3/envs/hanhong-miniforge3-base-clone/bin/python`
- isolated bazel checkout: `/google/src/cloud/qiaos/clip_probe/google3/experimental/users/qiaos/codi_torch_build`
  `[V]` **NOT exclusively mine** — a build-worker wiped my `blaze-bin` there once. Source survived; just rebuild.
- notify: `~/.amply/bin/amply_notify <session_id> "msg"` (NOT `$AMPLY_NOTIFY`)
- watcher: `$ART/codi_torch_watcher.sh`, 20-min ticks, running as a background job

---

## 10. `[V]`+`[C]` The stable-label idea: measured upside, and the trap in it

monitor-v43 asked whether this line could dodge the cold-build wall by using a
target at a STABLE bazel label instead of the wrapper's randomly-suffixed
stagedir. **Measured upside is large; the naive version of the fix is unsafe.**

### The upside, measured `[V]`
My isolated build at the fixed label
`//experimental/users/qiaos/codi_torch_build:main`, same machine, same blaze,
same torch dependency tree:

| build | wall time |
|---|---|
| first (cold) | **26.7 s** — Forge reported 55159/55167 actions CACHED |
| incremental after a code edit | 2.3 s / 5.1 s |
| after `blaze-bin` was wiped by another worker | 59 s (96439 actions) |

Against `[V]` a wrapper build observed holding the fleet's build lock for 29+
minutes (and `[T]` v43's report of a 1800 s timeout being hit). The gap is not
subtle.

### ★ The trap: the random suffix is a FIX, not an oversight `[V]` (read the source)
`tpu_wrapper.sh:721-730` documents exactly why it is there:

> a bare second-granularity timestamp is NOT unique — the documented "launch a
> batch in PARALLEL" workflow fires several `tpu queue` processes at once, and
> any starting within the same second (or while a sibling is still rsyncing)
> collided on ONE stagedir, so every work unit built from whichever config
> rsync'd last — **silently running an N-arm sweep as N copies of a SINGLE arm**
> (observed 2026-08-17: 4 XIDs → 1 stagedir → 1 arch).

**So "make the label stable" as stated would reintroduce a bug that silently
turned a 4-arm sweep into 4 copies of one arm.** That is a worse failure than a
slow build: it produces results that look fine and mean nothing.

### What a SAFE version would have to look like `[C]` — not implemented, not tested
The requirement is a label that is stable *per distinct payload* rather than
per invocation. Options, in the order I would try them:

1. **Content-addressed suffix**: hash the rsync'd tree, not the clock. Identical
   payload → identical label → cache hit; two different configs launched in the
   same second → different labels → no collision. Keeps the 2026-08-17 fix.
2. **Per-line fixed label** (what I did locally): each project owns one label
   and serialises its own builds. Safe only if the line never launches two
   different payloads concurrently — true for this line today, NOT true for the
   sweep workflow the comment describes.
3. Leave the wrapper alone and land the torch target in the depot at a normal
   path, launching by resume/label rather than staging.

**All three touch shared infra, which is an operator-level decision** — the red
lines forbid modifying `tpu_wrapper.sh` without approval, and this note exists
to make the tradeoff legible, not to authorise the change.

---

## 11. `[F]` NOT A BUG: the `transformers` "circular import" traceback

**A traceback that prints on every run and is completely harmless.** Recorded
here so the next person does not spend an hour on it, as I nearly did.

```
Traceback (most recent call last):
  File ".../third_party/py/transformers/__init__.py", line 20, in <module>
    from transformers import v5 as _version
ImportError: cannot import name 'v5' from partially initialized module
'transformers' (most likely due to a circular import)
```

`[V]` It comes from google3's own `transformers/__init__.py`, lines 19-22:

```python
try:
    from transformers import v5 as _version
except ImportError:
    traceback.print_exc()          # <- prints the scary traceback ON PURPOSE
    from transformers import v4 as _version
```

**It is a version probe that falls back to v4 and prints the traceback while
doing so.** `[V]` The run continues normally: `step 1/4 loss=21.7812` and
`training finished`.

**Why it nearly cost an hour.** It first appeared during the 07:2x-07:37Z srcfs
wedge, alongside a genuinely wiped `blaze-bin`, and "partially initialized
module" is exactly what a half-read runfiles tree would look like. Two
plausible-but-wrong stories (FUSE corruption; a real dependency cycle) fit the
evidence, and both would have sent me somewhere useless. What settled it was
reading the SOURCE that emits the message rather than reasoning about the
message — the same move infra-v11 used to overturn the enforcer statistics
(mechanism, not conclusion).

**Rule of thumb this yields:** a traceback is not the same thing as a failure.
Check the exit path — here, `except ImportError: pass`-style handling three
lines below the raise — before treating printed output as a diagnosis.

---

## 12. `[T]`+`[V]` The queue's "concurrent writer" — root-caused, and it has a fix

`[T]` monitor-v45 12:54Z, from `route_check.py:226-243`'s own docstring:

> "The old pattern — `load_queue()` then (much later) `save_queue()` as two
> separate calls — each took the lock only briefly, leaving a wide window in
> which another writer's save clobbered entries added in between... the tick
> wrote back its **stale in-memory snapshot** over the freshly enqueued row."

Some read-modify-write caller is not wrapped in `with_queue_lock`, so it writes
its whole stale snapshot back. The lock must be taken on the SIDECAR
`~/.tpu_local_queue.json.lock` — never the queue file itself, because
`os.replace` invalidates a lock held on that inode.

`[V]` **My own contribution to the evidence:** at 12:49Z I observed
`h100-8-c27e8f` go from `attempts=1` back to `attempts=0`, with `last_reason`
verbatim-restored to an older snapshot. **`attempts` is a monotonically
increasing counter; it decreasing has exactly one explanation.** That reading is
now the hardest detector for this bug (docs-v4 made the same point).

**Two consequences for you, successor:**

1. ★ **Overwrites are EVENT-driven, not periodic** (12s, 8min and 3.5h windows
   all observed). So "write, wait N seconds, re-verify" is insufficient for any
   N. If you must change a queue entry, take the sidecar lock AND run a
   continuous re-verify/repair loop — treat it as a state to be maintained, not
   a write to be made.
2. ★ **A rollback fabricates a more optimistic history than the truth.** My
   record of `c27e8f` being lock-starved (attempts=1) was erased. It survives
   only because I had written it into this document at the time. **Do not use
   queue `attempts` as evidence of what happened to a job — snapshot it
   elsewhere the moment you see it.**

`[T]` Related, same family: `BUILDING` means "someone once claimed this", not
"someone is building it now" — the claimant can be long dead
(`ls /proc/<pid from worker_id>` is the only live check). `[V]` I confirmed one:
the queue's single `BUILDING` entry pointed at pid 3307639, which no longer
exists. And stale BUILDING markers are reclaimed LAZILY (only when someone
claims the next build), so they linger but do NOT block the queue.

---

## 13. Watchers: the three tests, and why each is needed

`[V]` My watcher failed a different check at each of three rounds tonight, and
**the first two rounds were both green when the third bug was present.** That is
the whole point of this section.

Run `$ART/selfcheck_watcher.sh <your-watcher.sh>` for the static half (7 checks;
it carries its own negative control — a deliberately broken watcher it must
flag). The three behavioural tests must be run by hand:

| test | what it catches | how mine failed |
|---|---|---|
| **A. synthesise a FAILURE** → must SPEAK | a success-only watcher is indistinguishable from a dead one at the moment things fail | `[V]` mine had no terminal branch until I added one |
| **B. set a NORMAL state** → must STAY QUIET | a watcher that cries wolf trains its reader to ignore it, which equals no watcher | `[V]` passed |
| **C. ★after it speaks, what STATE did it change?** | a CORRECT alert with a fatal side effect passes both A and B | `[V]` mine did `FAILED\|HELD) alert; break` — and **HELD is reversible and flips every few minutes tonight**, so one spurious "TERMINAL" would have permanently abandoned a live job |

★ **A and B fail in the same visible way — silence — so neither alone tells you
whether the watcher is healthy or dead.** C leaves no trace in the alert log at
all, because the alert itself looked right.

### The "rendered a failure as a value" family — nine instances in one night
`[T]` Collected across the fleet; `[V]` two of them were mine:

- `grep -q RUNNING` matches `NOT_RUNNING` — reports a DEAD job as alive `[V] mine`
- `$(cat hb || echo 0)` renders a missing file as the value 0
- `ls | grep remote` renders a near-miss name as "the file exists"
- `grep -c` counts matching LINES, not independent processes
- a CLI that cannot run returns empty, which renders as "the job is gone" `[V] mine`
- `$?` read after `$(date)` — the rc lies
- a fallback `|| curl` protects against command failure, not against referencing
  the wrong object

★ **Common shape:** *a matching/counting tool used as an existence test — "does
it look like it" answering "is it".*
★ **Fix:** a fallback sentinel must be a value that cannot legitimately occur
(`-1`), never `0`. And separate "did the read succeed" from "what does the value
mean" — merged into one layer, a failed read is absorbed as "no change".

---

## 14. Finding your job's output — and a trap in the obvious check

`[V]` My four GPU XIDs landed in TWO different buckets, following the cell:

| XID | bucket in `~/.tpu_jobs.json` | directory actually there? |
|---|---|---|
| 284313288 | `/cns/yutulpz-d/` | **no** |
| 284359695 | `/cns/mb-d/` | **no** |
| 284360081 | `/cns/yutulpz-d/` | yes |
| 284367273 | `/cns/mb-d/` | yes |

Two lessons, both cheap and both cost me a wrong statement to the monitor:

1. **There is no single root to look in.** The launcher picks the checkpoint
   bucket from the landing cell (`xm_launcher.py::_CELL_BUCKETS`), and A100/H100
   cells are not in that table, so it falls back — differently per run. **Read
   `bucket_cp_path` out of `~/.tpu_jobs.json` for the specific XID; never assume
   a fixed root.**

2. ★ **`bucket_cp_path` records INTENT, not output.** The two XIDs with no
   directory are exactly the two that died before writing anything. So:

   - `[T]` parcae's 4-second check — `fileutil ls <default bucket> | grep <line>`
     — is worth running, **but a directory-name hit proves only that SOME job of
     that project once wrote there.**
   - `[T]` arc1's correction, which caught me: **grep for TODAY'S XID, not the
     project name.** `[V]` Run on my own data it immediately downgraded my
     "output is all in the default bucket" report from four runs to two.
   - `[V]` My own addition: a MISS is not automatically a leak-elsewhere either
     — it can mean the job produced nothing at all. Distinguish with
     `xmanager.par list`: terminal with no directory anywhere = died before
     writing.

★ **The general shape, which is this whole night in one line: a directory name
is a claim about the past, an XID hit is a claim about this run, and a registry
field is a claim about intent. Three different tenses, and the obvious check
reads all three as "where my output is".**

---

## 15. `[F]` The "it is just reading data across metros" explanation — I disproved my own

XID 284380582 (h100-8, cell `mb`) cleared every earlier gate — 8 GPUs visible,
`stdlib/fork` started all eight ranks, no SIGABRT — and then produced a
364-byte log and nothing else for 69 minutes while XM still reported `RUNNING`.

`[V]` I explained it as a cross-metro data pull: `mb` (ckv) has no mirror, so
all eight ranks fall back to `is-d` (cbf) for 548MB of weights + 104MB of
corpus. The mechanism is real and I fixed three genuine defects because of it
(commit `0a70243`: register `yucbfad`, warn on a far cell, `flock` the stage).

★ **But the explanation does not survive its own arithmetic, and I checked:**

| check | result |
|---|---|
| single-stream read to is-d | 50MB in 12s ≈ **4 MB/s** |
| 8 ranks × 652MB at 4 MB/s | ≈ **22 minutes** — but 69 had elapsed |
| second hypothesis: 8 concurrent readers thrash | `[V]` measured — 8 parallel readers of 20MB each: 160MB in 11s ≈ **13 MB/s aggregate**, i.e. concurrency HELPS, not hurts |
| 5.1GB at 13 MB/s | ≈ **7 minutes** |

**Both hypotheses are refuted by measurements I took myself. Whatever those 69
minutes were, they were not the data pull.**

### `[V]` A THIRD correction: the frozen parent log is EXPECTED, not a symptom

Reading my own `launch()`: after forking, the parent does
`for proc in procs: proc.join()` and only then prints `worker exit codes`.
**The parent is blocked in join() by construction — it says nothing until every
worker has exited.** So a parent log frozen right after
`stdlib/fork (verified...)` is not evidence of a hang at all; it is what a
NORMALLY RUNNING multi-GPU job looks like from the parent's side.

★ This is a third wrong reading of the same 88 minutes, and the most
embarrassing: I treated "the only log I can see has stopped" as "the job has
stopped", when the log's own design guarantees silence during the entire run.
**The observable I was watching could not distinguish "training fine for 88
minutes" from "wedged after 3 seconds".**

⇒ It also raised the possibility that the run was HEALTHY all along and merely
slow. `[V]` **That is now ruled out, by the one argument that actually
discriminates — magnitude:**

```
h100-8 = 8 x 2.15 = 17.2 v5p-units; the baseline's v7-32 = 138.9 at ~4.0 sps
  => h100-8 ~ 0.50 sps  =>  60 steps ~ 2 minutes
  => the FIRST log line (log_every_n_steps=20) ~ 1 minute
  + model load / CUDA init, generously 10 minutes
  => a healthy run should have finished inside ~12 minutes
observed: 128 minutes, no metrics.jsonl, no checkpoints/, only logs/
```

★ **So it IS wedged — but note what established that.** Not the frozen parent
log (which proves nothing, see above), and not the absence of output (same).
**It was an order-of-magnitude argument against an independently-derived
expectation.** The three earlier readings all tried to interpret the silence
itself; silence has no information content. **Predicting what the number should
be, and comparing, is what turned an unreadable observation into a conclusion.**

⇒ The fix already committed (every rank writes its own file, including rank 0)
is what makes the next run legible. Until then, treat this XID's outcome as
UNKNOWN, not FAILED.

★ **OPEN — do not inherit my explanation.** The still-unexplained observation is:
process alive, XM `RUNNING`, 8 ranks forked, log frozen at 364 bytes for 69+
minutes. The next run carries per-rank logs for ALL ranks including rank 0
(the previous gap: rank 0's child output went nowhere) plus `faulthandler`, so
the next occurrence should say something. Candidate directions, none verified:
NCCL rendezvous hanging with no timeout; a CNS read that blocks rather than
fails; the fixed-shape collate blocking on a first batch that never arrives.

### `[V]` What I tried in order to see inside those 88 minutes, and why none of it worked

Recorded so the next person does not spend the time again:

| attempt | outcome |
|---|---|
| read the CNS log | frozen at 364 bytes; the last line is `stdlib/fork (verified...)` |
| `fileutil ls` the logdir for other ranks | only `rank_0_attempt1.log` — ranks 1-7 wrote nowhere (the gap fixed in the next build) |
| `xmanager.par list` | `RUNNING 0/1` throughout — tells you it exists, not that it progresses |
| `borg --borg=mb jobs --user=qiaos` | LOAS-blocked on this workstation, as `gpu_on_borg.md` documents |
| check for checkpoints/metrics | none written |

★ **Every external observation channel is either blocked or blind. The only
instrument that could have answered this is one the JOB ITSELF writes** — which
is exactly what `jobs.md` §Debugging says, and exactly the thing my code was
missing for ranks 1-7 and, worse, for rank 0 inside the fork. **A job on Borg
can only be debugged by evidence it produced before it stopped producing
evidence.**

★ **The lesson is the one this whole night kept teaching, and this time the
victim was my own inference:** the fixes I made were correct and worth making —
an unregistered cell IS a real hazard, the stage race IS real — but *a real
defect found in the right area is the most convincing wrong answer there is*.
I only caught it by asking "does the magnitude actually work out?" — and it
did not, by a factor of three, then by a factor of ten.
