# HANDOFF — TRM torch-on-Borg port → next session (v1)

Author: the trm-torch-port line, run_id `20260827-203122-f64d40b7`.
Written 2026-08-28 ~03:05Z at monitor-v42's request (context over the 400k bar).
Reader assumption: **ZERO context.** Every path, id, branch, commit spelled out.

---

## 1. WHAT THIS LINE IS, IN ONE PARAGRAPH

Port the TRM (Tiny Recursive Model) research line onto our Borg GPU infra in
PyTorch. **The model is NOT being rewritten** — official TRM is already torch.
The work is: wrap the upstream trainer in our launcher contract, make its
logging and checkpoints match the JAX sibling so the two are comparable on one
dashboard, and then run it on H100.

**The acceptance chain is three segments, and only the first is done:**

| # | Segment | State |
|---|---|---|
| 1 | **Semantic alignment, locally verifiable** | ✅ DONE — 12/12 local tests, all with negative controls |
| 2 | **Run on real GPUs and prove it works** | ⏳ NOT STARTED — waiting on price only (see §7) |
| 3 | **Reproduce the official numbers** | ⏳ NOT STARTED — needs §2 first |

Nothing is blocked on a decision. Segment 2 waits on the h100 budget window,
which opens by itself.

---

## 2. WHERE EVERYTHING IS

| Thing | Path |
|---|---|
| **Your code** | `~/work/trm-torch`, branch **`torch`**, HEAD **`da3dd74`** — 7 commits, all mine |
| Launch dir (enqueue FROM here) | `~/work/trm-torch/torch_impl/` — holds `main.py`, `BUILD`, `config.sh` |
| Vendored upstream (verbatim) | `torch_impl/trm_upstream/`, sha in `UPSTREAM_SHA.txt` = `c01103738605ba39d1430519b1ee0c62f4c707f8` |
| **JAX sibling** (the thing to match) | `~/work/EqR-jax-trm-arc1`, branch `trm-arc1-repro-unroll` — **DIRTY worktree, do not clobber** |
| Frozen protocol | `~/work/EqR-jax-trm-arc1/TRM_ARC1_PROTOCOL.md` |
| CitC staging workspace | `/google/src/cloud/qiaos/elt_jax/google3` (= `STAGE_WS_ROOT`) |
| Local build target | `//experimental/qiaos/eqr_jax_final_stages/trm_torch_localbuild:main` |
| ARC corpus (cbf metro) | `/cns/is-d/home/qiaos/lyy_eqr_data/data/arc1concept-aug-1000` |
| Checkpoint bucket | `/cns/is-d/home/qiaos/eqr_data` |

`torch_impl/` layout: `main.py` (Borg entry) · `trainer.py` (the loop) ·
`metrics_sink.py` + `metric_bridge.py` (Datatables, JAX keys) · `checkpoint.py` ·
`adam_atan2_shim.py` · `callsite_optim.py` + `callsite_model.py` (unroll
optimizer) · `h_loop.py` (gradient topology) · `data_locality.py` ·
`corpus_compat.py` · `gpu_sanity.py` · `import_check.py` · `configs/` ·
`tests_*.py` + `run_all_tests.sh` · `tools_audit_dropped_keys.py`.

---

## 3. ★ THE `last2` QUESTION IS SETTLED — DO NOT REDO IT

The reference run's config carries `arch.h_loop_train_mode: last2`, which made
it look as though the JAX baseline trained a **different gradient topology**
from upstream torch. An earlier revision of my own notes recorded this as a
known gap ("D=14 there, D=5 here"). **That was wrong and I retracted it.**

**The key is INERT on TRM.** Three independent proofs:

1. **Config arithmetic, using the reference's OWN arch dict.** `TRMConfig` is
   `extra="forbid"` and declares no such field; `train.py` filters the arch dict
   to `k in allowed_model_fields` BEFORE constructing it. Apply that filter to
   xid 282307626's own config: 19 keys in, 17 out, and the results with and
   without the key are **identical — symmetric difference empty**.
2. **Source.** TRM's `deep_recursion` has no branch on the key. EqR's does.
3. **Why nobody noticed.** `configs/default.py` declares it in the UNION schema,
   so `check_known_keys` passes it and nothing ever warns.

So the reference ran the RELEASED topology: `H_cycles-1` detached, one
differentiable, **D = L_cycles+1 = 5** — exactly what upstream torch does and
what this port already does.

**Negative control (the reason this is a real finding, not a tautology)** —
measured on the real torch TRM, `tests_verify_h_loop_grad.py`:

| comparison | max\|Δgrad\| | relative |
|---|---|---|
| D=5 vs D=10 | 2.041800e-01 | 43.39% |
| D=5 vs D=15 | 3.018040e-01 | 66.90% |
| D=10 vs D=15 | 2.935515e-01 | 53.58% |
| **D=5 vs D=5** | **0.000000e+00** | determinism control |

The topologies **are** distinguishable, so "the reference ran mode 1" could
have been false. Second control: EqR's `deep_recursion` really does read the
key — if the checker called it inert on both sides it could not fail.

The mechanism is implemented anyway as **`arch.h_grad_cycles`** (`h_loop.py`),
default 1 = released = installs nothing. Verified for {1,2,3} → D ∈ {5,10,15}.

---

## 4. ★ THE TRAP THAT PRODUCED IT: SILENTLY DROPPED CONFIG KEYS

`configs/default.py` is a **union schema** over EqR/HRM/TRM, so
`check_known_keys` accepts any key it declares — but each model builds a strict
`extra="forbid"` config and `train.py` filters first. **A key belonging to
another model is accepted by the validator, dropped before the model, and never
warned about.** It then sits in the config, in the checkpoint's `extra.json`,
and in every reader's mental model of the experiment, doing nothing.

Scale: **33 of the union's 54 arch keys are dropped for TRM.**

Auditing the reference run: 56 arch keys, 20 reach `TRMConfig`, 33 dropped, and
**two dropped keys carry non-default values**:

- `h_loop_train_mode='last2'` (default `'last1'`) — §3.
- `q_head_sg=False` (default `True`) — harmless **only by luck**. On EqR it
  detaches the q-head read-out; on TRM the field does not exist and the q-head
  already reads the trunk without a stop-gradient, which is what `false` asks
  for. **Intent and behaviour agree by coincidence.**

That is the lesson: a dropped key can be harmless, harmful, or accidentally
right, and nothing in the pipeline tells you which.

**Tool:** `python3 torch_impl/tools_audit_dropped_keys.py <extra.json|config.yml>`
— exits 1 if any dropped key is non-default. **Run it on any config before
trusting what it says an experiment did.**

---

## 5. ★ BASELINE — WHAT THE REFERENCE ACTUALLY IS (AUTHORITATIVE)

**The most expensive bug on a porting line is aligning to the wrong reference.**
parcae-torch-port hit exactly this tonight: it believed its canonical baseline
was `nobos`, checked, and found it was **`strict-4d1138c`**. Never trust a
remembered baseline; read the run's own artefacts.

My equivalent check, done by reading the `config` each finished run embeds in
its own orbax `extra.json`:

- **Every ARC-1 run that exists on CNS is a Phase-2 UNROLL arm**, not a
  baseline. All report `optimizer: adam_atan2_callsite_sqrt`. Their names read
  like baselines (`trm_arc1_v6p_1e4_wd0p1`); they are not.

| XID | last ckpt | optimizer | h_loop | lr | wd |
|---|---|---|---|---|---|
| **282307626** | **step_518070 (COMPLETE)** | callsite_sqrt | last2 | 1e-4 | 0.1 |
| 282313894 | step_252000 | callsite_sqrt | last2 | 1e-4 | 0.2 |
| 283033385 | step_428000 | callsite_sqrt | last1 | 8e-4 | 0.2 |

- **The Phase-1 paper baseline has NEVER RUN** — one "Phase 0 wiring" commit, no
  checkpoint anywhere on CNS.

**Consequence, and it is written into the config headers so it cannot be lost:**
`remote_run_config.yml` is the paper protocol and **the JAX run it would be
compared against does not exist**. The torch run may legitimately be that
protocol's first execution, but **nobody may claim "torch matches JAX" from
it.** For a real comparison use `unroll_arm_config.yml`, generated from
282307626's own embedded config.

Reference path:
`/cns/oi-d/home/qiaos/eqr_data/logs/EqR-jax/xid_282307626_20260822_220315_trm_arc1_v6p_1e4_wd0p1/checkpoints/step_518070/extra.json`

---

## 6. WHAT IS BUILT, AND THE 11 REAL BUGS FOUND LOCALLY

All found before spending a single GPU-hour.

| # | Bug | Consequence if shipped |
|---|---|---|
| 1 | `known_only=True` insufficient — `app.run()` re-parses strictly | zero-line death in flag parsing |
| 2 | `argdantic` has no google3 target, unused import in `puzzle_dataset.py` | pre-main ModuleNotFoundError |
| 3 | same import, **load-bearing**: `cli = ArgParser()` at module top level, and `evaluators/arc.py` imports three pure helpers from `build_arc_dataset` | **pass@2 — the headline — unimportable** |
| 4 | `grad_clip_norm: 5.0` missing AND unimplemented | different optimizer trajectory |
| 5 | `q_halt_loss_weight` / `lr_schedule` / `stablemax_dtype` missing | redefines the loss; float32 stablemax underflows |
| 6 | resume collapsed every rank's RNG to one stream | resumed run draws different data than a fresh one |
| 7 | resume had no cross-rank step agreement | ranks enter collectives at different steps → **hang, burning the whole allocation** |
| 8 | loop bounded by the loader, not the step counter | 518,070-step run "finishes" after a few hundred steps, writes a final checkpoint, **exits 0** |
| 9 | corpus schema older than upstream (no `total_puzzles`) | pydantic ValidationError before step 1 |
| 10 | call-site decay applied per copy → **√D+1 = 3.236× too large** | uniform, plausible shrink **no loss curve reveals** |
| 11 | **leaked ranks on preemption** | a held GPU; next attempt presents as "no capacity" |
| 12 | `max_gpus` silently capped the rank count | asks Borg for h100-8, trains on 1, 7 idle until pruned |

### Verification matrix (every item carries a negative control)

| What | Result |
|---|---|
| AdamATan2 vs the CUDA kernel's arithmetic | max err **8.7e-19**; AdamW control detected at 1.0e-4 |
| LR schedule vs upstream | **exactly 0.0** at every probe point |
| Metric reduction | 20 published columns; wrong-GBS control detected |
| Metric bridge | 7 upstream raw keys → 23 bridged → **20 published, all JAX train columns present** |
| Checkpoint | save/restore/prune/promote; refuses no-op restore and wrong optimizer count |
| Call-site aggregation | sum/mean=4.96 (~D=5), sqrt/mean=2.232 (~√5=2.236); decay-once err **3.0e-08** |
| Call-site on real TRM | 5 slots used per forward, **different moments per slot, bit-identical weights** |
| Gradient topology | table in §3 |
| Preemption (1 rank) | SIGKILL mid-run → resumed at the exact checkpoint → ran to completion |
| **Multi-rank (2 ranks)** | all five collectives; both ranks resumed at step 12; torn checkpoint refused on both, parent reports `[1, 1]` |
| **Rank reaping** | **0 leaked processes under BOTH SIGTERM and SIGKILL** |
| End-to-end dry run | cold start → checkpoint → resume → ran on |

Run everything: `cd ~/work/trm-torch/torch_impl && ./run_all_tests.sh` (12 tests,
~100s, no GPU needed). Bazel gate:
```bash
cd /google/src/cloud/qiaos/elt_jax/google3
rsync -a --delete --exclude='__pycache__' ~/work/trm-torch/torch_impl/ \
  experimental/qiaos/eqr_jax_final_stages/trm_torch_localbuild/
blaze build --config=cuda //experimental/qiaos/eqr_jax_final_stages/trm_torch_localbuild:main
TRM_ALLOW_CPU=1 ./blaze-bin/.../trm_torch_localbuild/main --import_check --config=remote_run
```

### The rank-leak fix, since it is subtle
The tree is **three deep**: the parent forks N ranks, and each rank's DataLoader
(`persistent_workers=True`) forks a worker. A reaper that only knows its own
children terminates the ranks and **orphans the grandchildren**. Three layers:
`os.setpgrp()` in every rank (rank + worker in one killable group) ·
`daemon=True` (covers the un-catchable SIGKILL) · a SIGTERM/SIGINT handler plus
`finally` that `killpg`s the whole group (**SIGTERM is what Borg sends first**).

---

## 7. HOW TO LAUNCH (segment 2 — do this when the price window opens)

```bash
cd ~/work/trm-torch/torch_impl        # MUST be the CWD: the wrapper stages THIS dir
source ~/work/tpu_cmd/tpu_wrapper.sh
tpu enqueue --power=h100-8 --archs=h100 --tier=PROD --metros=cbf \
  --launch=group=9,bucket=/cns/is-d/home/qiaos/eqr_data,exp_name=trm_arc1_torch_h100
```

**Do a `--sanity_only` run first** — it is short, and short matters (§8).

- ★ **`--power` / `--metros`, NOT `--tpu_type` / `--cell`.** An earlier revision
  of this section printed the latter pair; it dies with `FATAL Flags parsing
  error: Unknown command line flag 'tpu_type'`. Those flags are **`tpu queue`'s**
  (the one-shot direct submit) — `tpu enqueue` is the local queue and defines
  neither. Two subcommands of one tool, both real, answering different
  questions, which is the same shape as `xmanager.par list_artifacts` vs `list`.
  **This one failed loudly; the general case does not.** Had `enqueue` merely
  *accepted* an unknown-but-plausible flag, the result would have been `rc=0`
  and a silently wrong queue entry. ★ **Run `tpu enqueue --helpshort` before
  reusing any command out of any doc — including this one. A command is an
  ACTION, not a conclusion: the reasoning beside it can be sound while the
  invocation is stale.**
- Metro **`cbf`** because **`if` is the h100 cell in metro `cbf`**, the only
  GPU-reachable metro already holding the ARC corpus mirror (`is-d`). Verified
  with `mach_locality -k metro if` → `cbf`. **Zero data copying needed.**
  Enqueue takes the metro and lets the router choose the cell within it.
  ⚠ `metro_util.metro_of()` returns `if` for `if` (short names fall back to the
  cell name) — it MISLED me once. Use `mach_locality`.
- `--bucket` must be **explicit**: the launcher's `_CELL_BUCKETS` has no entry
  for `if`, so the default would put checkpoints in `yutulpz-d`, a metro away —
  4-5× throughput loss and the pruner kills the job.
- Capacity is not the constraint (gpu-survey measured 14 cells with free
  h100-8). **Budget is**, and it swings wildly; once a job is IN the local
  queue the router drains it by itself when a cell can place it. **Do not sit
  and watch it, and do not re-enqueue.**
  ★ **But "the queue will handle it" only applies to a job that is actually IN
  the queue.** Check before assuming one is: `python3 -c` over
  `~/.tpu_local_queue.json`, filtering on `workdir`, **with a negative control**
  (a filter that returns >0 for some other line) so a zero cannot be a broken
  filter. Segment 2 sat "waiting on the price window" for hours while the
  queue held **zero** trm entries — nothing had ever been enqueued.

---

## 8. RED LINES (operator-level, do not violate)

- **★ NO job-level price raising (`set_limit_order`).** Operator, verbatim: a
  previous agent did it, you absolutely must not. **No card = wait. Prices come
  down.**
- **★ NEVER `--tier=BATCH`.** Operator's instruction, and BATCH is eval-only by
  standing rule. GPU sanity and training are both `--tier=PROD`.
- **Never `xm launch` / `xmanager launch`** — only `tpu enqueue`.
- **Never cancel another line's job.**
- Do **not** modify `~/work/tpu_cmd/tpu_wrapper.sh` or `xm_launcher.py` (fleet
  blast radius). Do not touch lyy's sealed CUDA oracle gate.
- **Protect the dirty worktree** at `~/work/EqR-jax-trm-arc1`; do not touch the
  in-flight TRM **TPU** jobs (`trm_arc1_v6p_*`). This line is torch/GPU only.
- Local smoke before every launch. Confirm **VMGROUP_STATE_RUN**, not just an XID.

---

## 9. OPERATING NOTES THAT COST ME TIME

- **Preemption is the real adversary on H100, not build or budget.** gpu-survey
  had six consecutive h100 smokes killed by `higher-priority job taking the
  chips`, `FailedWorkUnits=0` (not a crash). So: **keep verification runs short
  and write the verdict to CNS as you go.** `--sanity_only` now appends to
  `<bucket>/sanity/<XID>_<WID>.json` after EVERY stage, because
  `analog`/`borg tasklog` are `PERMISSION_DENIED` from this workstation —
  whatever survives the preemption IS the diagnosis. Verified landing on
  `/cns/is-d` with `"complete": false` plus the stage list.
- **The builder is serial and shared.** A job sitting in the queue behind
  another line's build is normal, not a bug.
- **`--import_check` is the cheapest gate that exists.** It imports the whole
  graph, resolves the model classes the config names, reaches the corpus, checks
  the optimizer name and the gradient topology — in seconds, with no GPU. It
  found bugs 2, 3 and 9. Run it after every change.
- `TRM_ALLOW_CPU=1` (workstation only) lets `main.py` past the
  `device_count()==0` guard; `TRM_FORCE_CPU=1` makes `trainer.py` run on CPU.
  **Neither is ever set on Borg** — a GPU job that trains on CPU silently is the
  failure the guard exists for.
- torch env for local tests:
  `~/miniforge3/envs/hanhong-miniforge3-base-clone/bin/python3`.
- GB200 is unusable (IMEX permission wall at any size). H100 is fine.

---

## 10. WHAT I WOULD DO NEXT, IN ORDER

1. **`--sanity_only` on h100-8 PROD** when the budget window opens. Acceptance:
   `VMGROUP_STATE_RUN`, and `<bucket>/sanity/<XID>_<WID>.json` with
   `"complete": true` and `nccl_allreduce` passing on 8 GPUs.
2. **A short real training run** (`--config=smoke`, `--max_steps` a few hundred)
   from the same package. Acceptance: metrics on
   `http://flatboard/xid/<XID>` carrying the JAX column names, a checkpoint on
   CNS, and a successful resume from it.
3. **`--config=unroll_arm`**, the arm comparable to xid 282307626. Compare
   curves against that run's datatable. **Expect curve-level agreement, not
   bitwise** — different framework, RNG and kernels.
4. **Then** `--config=remote_run` for the paper protocol (segment 3, ~3 days on
   4×H100 per upstream's README; we have 8).
5. Optional, pure local: run `tools_audit_dropped_keys.py` over the other lines'
   configs — the union-schema trap is not TRM-specific.

---

## 11. COMMIT LOG (branch `torch`, newest first)

```
da3dd74  multi-rank drill, leaked-GPU fix, audit for silently dropped keys
4e40e91  close the h_loop gap -- and retract the gap itself
32c041e  end-to-end dry run of the assembled trainer, and three bugs it found
28d4d8d  port the call-site unroll optimizer (adam_atan2_callsite_*)
2427cc8  preemption drill, and two resume bugs it exposed
bb29393  reference-frame audit against REAL run artefacts
e3f59d1  fix three pre-main() deaths found by the local gate
cc8acd3  metric bridge -- upstream keys -> the JAX run's column set
79cb40e  Borg GPU port of TRM (upstream c0110373 vendored)
```

Every commit message states what was verified and how. Read them before
changing the file they touch.

---

## 12. CONTACTS

- **The monitor** — its approval is the operator's. ★ **DO NOT hardcode a
  monitor run-id, including the one below.** Monitors retire every few hours,
  and `send11` returns SUCCESS when it delivers to a retired session, so a
  report to a dead monitor looks exactly like a report nobody objected to.
  **Read the current id first, every time after a handoff:**
  `grep "THIS MONITOR" ~/work/.monitor_watch/runs.txt | tail -1`.
  If a broadcast announces a successor that `runs.txt` does not yet list, the
  file is lagging — use the announced id and say so. (Historical, already stale
  by the time you read this: v42 `20260828-022909-924bce46`, v43
  `20260828-050035-02edec20`, v44 `20260828-071601-4ce2a82d`.)
  **Silence has two forms — "read it, no objection" and "never arrived" — and
  they look identical. Before a launch, do not read silence as consent.**
- **gpu-survey-v2** — `20260827-164854-2c1e76b8`. Brought up the first torch
  job on H100; owns `~/work/wiki_agents/gpu_on_borg.md`. Ask it anything GPU.
- Send: `echo "msg" | timeout 20 python3 ~/work/.monitor_watch/tools/send11.py <run-id>`
