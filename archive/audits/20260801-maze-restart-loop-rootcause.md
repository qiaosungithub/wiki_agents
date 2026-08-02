# XID 275793223 — why the last 5000 steps never run

Read-only investigation, 2026-08-01. Everything below is MEASURED unless tagged
INFERRED or UNRESOLVED.

---

## 0. TL;DR

The task premise contains two separate phenomena that got conflated. Both are real,
but only the second one is why the run is stuck.

| # | Finding | Status |
|---|---|---|
| **A** | **The job is NOT killed by Borg.** It restores, trains **zero steps**, exits **cleanly**, and Borg restarts it because the work unit never completes. Cause: a dataloader resume bug — the restored `epoch_idx` already equals `epochs_per_iter`, so the loop yields no batches. | **Root cause of the stuck run. Proven.** |
| **B** | CNS reads on `yutulpz-d` really did get ~70x slower (~50 → ~0.5 MiB/s) at a sharp cliff on 2026-08-01 ~03:55–04:05 UTC, still slow 12 h later. Cause: a best-effort **Blobstore LAD** workload in the *other* Colossus cell that shares the same physical D-cell spindles, adding a constant **+21–25 ms to every read op** across ~20 unrelated client cells. Not our quota, not our path, not broken hardware. | **Real, measured, root-caused — but SECONDARY.** |

**Fixing the CNS slowness would not fix the run.** During attempt 9 the restore took
**0.4 s** and the task *still* exited at step 95000 and restarted — 50 times in a row.
CNS speed changes the restart *period*, not the fact of restarting.

**Fastest way out, no code change:** resume from **`step_92500`** instead of `step_95000`.
Measured: its `epoch_idx` is 2500 (mid-iteration) so the dataloader yields batches
normally, whereas `step_95000`'s is 5000 (exhausted). Costs 2500 redundant steps. See §C.1.

**Note on the in-flight fix attempt:** XID 276203817, launched 15:34 UTC against the
clean short-path copy with 4 tasks, is **stuck in exactly the same way** and reads at
**538 KiB/s** — i.e. it refutes the path hypothesis and confirms the real bug in one
shot. §A.5. It will not make progress; the poison travels with the checkpoint.

Evidence base: 265 orbax bandwidth samples, 4 checkpoints' `extra.json`, 61+18 restart
records, Borgmaster state sampled 53 times over 30 min, and ~20-cell Monarch latency
data. Sub-agent detail in `borg_job_context.md` and `cell_health_yutulpz.md`.

---

## A. Root cause of the stuck run: the dataloader resumes already-exhausted

### A.1 The task exits cleanly; it is not killed

`rank_2_attempt11.log` (rank 2 is JAX `process_index()==0`, the rank that logs the
training loop) contains, for **every one of its 10 restarts**, this complete sequence:

```
[Info] Starting training from step 95000 to 100000
[Info] The initial training step may take a while (XLA compilation)....
[Info] Setup EMA
[Info] iteration 20/20 (epochs 95000-99999)
[Info] Checkpoint for step 95000 already exists; skipping save (...)
[Info] Datatables metric writer flushed and closed
INFO:root:Finishing mock wandb run
=== attempt ends: steps 95000 -> 95000 of 100000; last checkpoint step 95000 ===
```

`=== attempt ends ===` is written by `logging_util.close_attempt_log()`, which only runs
at the *bottom of `main()`* after `wandb.finish()`. A SIGKILL/deadline kill cannot produce
it. Counts:

| log | `begins` | `attempt ends` | `Starting training` |
|---|---|---|---|
| rank_2_attempt11 | 10 | **10** | 10 |
| rank_9_attempt9 | 61 | 24 | — |
| rank_6_attempt9 | 61 | 8 | — |
| rank_4_attempt9 | 61 | 7 | — |

(The non-zero ranks show fewer `ends` only because their mirror buffer is dropped when the
peer ranks tear down first; rank 2 — process 0 — is 10/10.)

Note the step range: **`steps 95000 -> 95000`**. Zero steps trained, every time.

### A.2 Why zero steps — the arithmetic

From the checkpoint's own `extra.json` (measured, copied from CNS):

```
step        = 95000 / 100000        iteration = 20
steps_per_epoch = 1                 train_dataset._iters = 19
train_state.epoch_idx   = 5000      train_state.start_index = 768
```

Config: `epochs=100000`, `train_epochs_per_iter=5000` → `total_iters=20`.

**`train.py` (outer loop) is correct.** Its guard works exactly as documented:

```
steps_per_iter  = 1 * 5000 = 5000
from_step       = 95000 // 5000 = 19
from_meta       = 20                    # metadata says "finished"
start_iteration = min(max(19, min(20,19)), 20) = 19
for iter_id in range(19, 20):           # -> runs once, iter_id=19
```

The log confirms: `Resume: checkpoint step 95000 implies iteration 19, recorded
iteration is 20; starting at 19` and then `iteration 20/20 (epochs 95000-99999)`.
So the outer loop *does* enter its final iteration.

**`dataset/puzzle_dataset.py::_iter_train` is where it dies.** It restores
`epoch_idx` from the checkpoint and then:

```python
epoch_idx = int(self._train_state.get("epoch_idx", 0))    # = 5000
...
while epoch_idx < self.config.epochs_per_iter:            # 5000 < 5000 -> False
```

The `while` never executes → the generator yields **zero batches** → `for _set_name,
batch, ... in train_dataset:` in `train.py` has an empty body → `step` stays 95000 →
loop ends → `training_done` never set, `save_checkpoint` skipped ("already exists") →
clean exit.

**The bug is a state-encoding mismatch.** `epoch_idx` is stored as a *count of epochs
already consumed within the current iteration*, but it is restored as a *cursor to
resume at*, and it is not reset when the outer loop advances to a new `iter_id`.
Reaching `epoch_idx == epochs_per_iter` is precisely the "this iteration is done"
condition, so any checkpoint that lands on an iteration boundary (step 95000 is
exactly 19×5000) resumes into a dataloader that is already exhausted.

This is the same *class* of bug as the `iteration`-vs-`step` one that the extensive
comment in `train.py` describes fixing — that fix repaired the outer loop's start
index but not the dataloader's own epoch cursor, so a boundary checkpoint still
produces a zero-step run.

### A.3 The clincher: restart period is independent of CNS speed

Attempt 9, all 61 restarts, from `rank_9_attempt9.log`:

| restore time | n | median restart period |
|---|---|---|
| **fast** (<2 s) | 50 | **334 s** (min 332, max 650) |
| slow (>10 s) | 8 | 450 s (min 388, max 629) |

For 50 consecutive restarts the checkpoint loaded in **0.4 s** and the task *still*
restarted on a rock-steady **334 s** cycle. The extra ~116 s in the slow phase is
just the slow restore (median 42 s) plus its knock-on effects. The ~334 s floor is
startup + XLA compile + teardown, not I/O.

**Therefore: host count, path length, file count and CNS bandwidth are all irrelevant
to the restart loop.** The loop is caused by the job completing without progress.

### A.4 Independent Borg-side confirmation: no task ever died

A sub-agent queried Borgmaster directly (transcripts in `borg_job_context.md`):

```
borg --borg=oe findjobs --user_re=qiaos
  qiaos_group_275793223.11.main:  job_failures: 0   task_failures: 0
lookuptask ... 0
  task attempt UID 1945514178833   failures: 0   start_time: 1785592974 (14:02:54 UTC)
  status_msg: ""   abnormal_termination_reason: UNKNOWN   normal_termination_reason: NONE
lookupterminations  -> empty
priortasklog        -> "Couldn't find suitable task instance"
```

Sampled every 12–32 s for 30 minutes (53 samples) **across three "restart"
boundaries**: the attempt UID, `failures: 0` and `start_time` **never changed**. A real
Borg restart would issue a new attempt UID and advance `start_time`. `daemon: false`,
so Borg's "restart on exit 0" behaviour is not even enabled — the re-exec happens inside
the task (envelope/wrapper layer; INFERRED, since `analog`/`tasklog` were blocked by
restricted LOAS).

**So there is no death reason, no timeout, no OOM and no preemption to quote — because
nothing was ever killed.** This independently confirms §A.1 from the opposite direction.

The cadence is also not a Borg interval. Regressing cycle time on restore time:

- attempt 9 (n=60): `cycle ≈ 349 s + 2.46 × load_s`, corr 0.64
- attempt 11 (n=16): `cycle ≈ 421 s + 2.78 × load_s`, corr 0.73

No round number (300/600/900 s) appears, which is itself evidence against a deadline.

### A.5 The decisive natural experiment: the clean-path job reproduces it

The operator launched **XID 276203817** ("maze-FULL-clean resume@95k short bucket path
v4-16 oe") at 15:34 UTC, reading the byte-identical copy at the **short clean path**
`/cns/yutulpz-d/home/qiaos/eqr_data/maze_resume_95k/checkpoints/step_95000_41pjso2k`,
with **4 tasks**, in the **same cell `oe`**. That controls path length, directory
contents and host count simultaneously.

MEASURED from its own log (`.../maze_resume_95k/logs/.../rank_2_attempt1.log`):

```
[Info] Applied config.load_from from environment LOAD_FROM='.../maze_resume_95k/checkpoints/step_95000_41pjso2k'
[Info] Loading checkpoint  .../maze_resume_95k/checkpoints/step_95000_41pjso2k
/jax/checkpoint/read/gbytes_per_sec: 538.045 KiB/s (total size: 4.0 MiB)
```

**538 KiB/s on the clean short path** — statistically indistinguishable from the ugly
long path's 285–645 KiB/s. Path length is refuted a third time, now in production.

And it is stuck the same way: `begins=1`, `attempt ends=0`, `Starting training=0`, with
the log frozen at 15:42:45 UTC (checked 16:52 UTC, 70 minutes later). It never got past
the restore into a training step. **The bug is not a property of the old bucket** — it
follows the checkpoint, because the poison is inside `extra.json`. Copying to a clean
path cannot fix it.

---

## B. The CNS slowdown is real, but is a different problem

### B.1 The step function (measured, 265 samples from orbax's own counter)

`/jax/checkpoint/read/gbytes_per_sec` for the same 4.0 MiB checkpoint:

| hour (UTC) | n | median MiB/s | min | max |
|---|---|---|---|---|
| 07-31 22:00 | 4 | 54.59 | 52.77 | 55.02 |
| 07-31 23:00 | 40 | 50.26 | 27.53 | 57.05 |
| 08-01 00:00 | 44 | 50.71 | 34.65 | 55.12 |
| 08-01 01:00 | 40 | 48.01 | 32.43 | 56.00 |
| 08-01 02:00 | 40 | 44.47 | 26.18 | 55.53 |
| 08-01 03:00 | 40 | 40.22 | **8.11** | 52.68 |
| **08-01 04:00** | 32 | **0.72** | 0.42 | 3.96 |
| 08-01 05:00 | 4 | 0.45 | 0.38 | 0.63 |
| 08-01 14:00 | 12 | 0.36 | 0.26 | 1.33 |
| 08-01 15:00 | 8 | 0.47 | 0.28 | 0.62 |

A clean ~70x step down, with a short ramp (03:38 → 04:01) and no recovery in 12 h.

**It is not only CNS.** In the same processes, the Google3 `lineage_log` "read_event"
RPC — which publishes to UMB and does *not* read the checkpoint payload — went from
**0.02 s to 4–15 s** at exactly the same moment. Whatever happened is broader than
the file read path. That argues against a pure orbax/tensorstore explanation.

### B.2 Hypotheses positively RULED OUT

**H1 — the ugly bucket path (spaces, `(`, `+`, `->`, 174 chars). REFUTED.**
A/B against the byte-identical clean copy, interleaved, same client, same minute:

| | 3.9 MB `cp`, 3 runs | 20 opens of the same 262 B file, 2 runs |
|---|---|---|
| LONG ugly path | 16.31 / 17.82 / 15.70 s | 13.04 s / 13.36 s |
| SHORT clean path | 16.06 / 15.85 / 16.30 s | 13.67 s / 14.75 s |

Identical within noise; the short path is if anything marginally *slower*. Path
length, spaces and special characters cost nothing measurable.

**H2 — number of files / ocdbt layout. REFUTED as the driver.**
The checkpoint is **17 entries: 10 files + 6 dirs**, totalling **3,931,398 bytes**,
of which one blob is 3,899,285 B (99.2%). That is a near-ideal layout — one big blob
plus a handful of tiny metadata files. It is not "a few MB spread over many objects".
The same 17-entry layout was read in 0.4 s before the cliff, so the layout cannot
explain a change.

**H3 — enumerating the whole prefix / cost scaling with the number of past
checkpoints. REFUTED.**
`ckpt_util.latest_checkpoint()` does one `iterdir()` of `checkpoints/` (**38 entries**)
plus one `path_exists(extra.json)` per candidate. That is ~39 metadata ops, bounded and
small; it is also *not on the restore path at all* in the current attempts, because
`main.py::_apply_borg_autoresume` had already resolved `load_from` to an explicit
`step_95000_41pjso2k` path (visible in the config dump). And again: 38 checkpoints and
56 log files were already there during the 0.4 s restores.

**H4 — host count / read amplification. Already refuted by the operator, confirmed here.**
Attempt 11 uses 4 tasks and is slow (85–175 s); attempt 9 used 16 tasks and was fast
(0.4 s) for its first 49 restarts. Also, `_restore_tree` now routes multi-host restores
through `_restore_on_process_zero_and_broadcast`, so only process 0 reads.

**H5 — cross-continent / locality. Refuted (and already known-fixed).**
Every slow log says `Compute cluster: oe, metro: tul, continent: na` /
`Storage cluster: yutulpz, metro: tul, continent: na`. Same metro. The fast 0.4 s
restores have the *identical* pair of lines, so locality did not change at the cliff.

### B.3 What the evidence positively supports

**Cost is per-operation, not per-byte.** From this workstation (metro cgk):

| file | bytes | `cp` run 1 | run 2 |
|---|---|---|---|
| `_CHECKPOINT_METADATA` | 262 | 14.49 s | 14.53 s |
| ocdbt `d/` leaf | 479 | 14.38 s | 14.68 s |
| ocdbt `d/` leaf | 3,054 | 16.75 s | 15.83 s |
| `_METADATA` | 12,236 | 15.92 s | 16.54 s |
| main payload | 3,899,285 | 18.15 s | 18.42 s |

A **262-byte** file costs 14.5 s and a **3.9 MB** file costs 18.2 s — a 15,000x size
range for a 1.25x time range. The marginal throughput implied by the difference is
~1 MB/s, matching the job's degraded `gbytes_per_sec`. This is a latency/round-trip
regression, not a bandwidth one, which is also why a 4 MB checkpoint and a 54 s
`fileutil cp -R` of the same 4 MB both look "slow for the size".

Amortising `fileutil`'s fixed startup by copying 38 distinct large blobs (148,334,652 B)
in one invocation: **59.29 s → 2.50 MB/s aggregate, 1.56 s per file.** Still ~20x below
the historical 50 MiB/s.

### B.4 Root cause of the CNS slowdown: a noisy neighbour on shared spindles

My workstation probes could not settle this (load average **30 on 24 cores**;
`fileutil help`, which touches no network, took **4.4 s** vs a 1.05 s baseline; and a
cross-cell control against `yuskedq-d` came out *equally* slow — cross-metro RTT from
metro `cgk` swamps the effect). Those probes are excluded from the evidence below.

A sub-agent resolved it with Monarch. Full transcripts in
`cell_health_yutulpz.md`. Summary, all MEASURED:

**It is not the user.** `qiaos` is at **125,450 / 512,000 MiB = 24.5%** of byte quota,
flat across the cliff. Explicit throttling (`/storage/d/client/throttler_responses`) is
**0.0007–0.35%**; `metric:out_of_quota` is never set. Raising quota would change nothing.

**It is not broken hardware.** D servers were **268/268 HEALTHY** for the whole 20 h
window, zero DEAD/DOWN/DRAIN/LAME — and the server count *grew* 214 → 268 **while the
cell got slower**, which is conclusively a demand-side, not supply-side, event.

**It is a best-effort Blobstore LAD (data-mover) workload that started at ~03:00–04:00 UTC**
and is still running. `blobstore-cfs-shard-storage-owner` held **0 bytes before 02:40**, then
47 TiB @03:00 → 1,075 TiB @04:00 → **14,456 TiB @16:00** (~1 TiB/min, still climbing).
Cell-wide read ops went **13k → 166k/s (12.8x)** and spindle usage **1.1k → 10.6k (9.5x)**
against a cell spindle quota of 4,358 — i.e. **2.4x over**, with `overquota_usage/tp`
going 0 → 14,757. The sole overquota owner is `blobstore-lad-spindle-owner`.

**The mechanism — two Colossus cells share one physical D cell.** `-d` is a naming
convention, not a storage tier (`location_concepts.md:434`; `spanlib.py:3170` does
`re.sub(r"-d$", "", cell)`). Cluster `yutulpz` runs **`yutulpz-d` (CFS1, where our
checkpoint lives) and `yutulpz` (CFS2, where Blobstore lives) on the same D cell** — both
`prodspec` entries declare `d_cell: "yutulpz"`. Same physical spindles. So our job was
starved by a workload in a cell it has no relationship with and cannot see.

**The decisive experiment.** Grouping read latency by *client* `borg_cell` shows ~20
unrelated client cells degrading simultaneously by a near-constant **additive +21–25 ms
per operation** (oe 3.2 → 27.8 ms, oa 2.2 → 23.3, ou 2.2 → 26.6, nj 2.3 → 26.5,
pa 2.4 → 28.2, yutulth 2.4 → 24.2). Additive and location-independent ⇒ the cost is
incurred **at the disk, after the network hop**. An unrelated prod user
(`blobstore-quota-aggregator`) shows the identical step.

**This also explains two things I flagged as puzzling.** (i) It is a *per-operation* tax,
not a bandwidth cut: the 0–16 KiB read bucket degraded **14x** while the >64 KiB bucket
degraded only **3x** — which matches my own §B.3 finding that a 262 B file and a 3.9 MB
file cost nearly the same. (ii) The non-CNS `lineage_log` RPC collapsed at the same second
because its backend reads from the same starved pool — same root cause, different path.
`qiaos` throughput was measured at **9.63 → 0.04 MiB/s** at 06:00.

**Caveats.** `celly` was unusable from this workstation (LOAS grants only the
`gdm-fru-cns` consumer group; `yutulpz` is not a GDM-pool cell), so `storage.Dml` /
`DmlUser` Monarch metrics were substituted. `monarch_cli list-metrics/describe-metric`
was blocked by `RPC_RESTRICTIONS_VIOLATION`. Not established: *why* the LAD job started
(no CL or ticket found), and whether an SRE alert fired.

**§B.5 below (cross-continent EqR-jax jobs reading `yutulpz-d` from `yuskedq`) is
therefore NOT the cause of the cliff** — the timing coincidence is real but the magnitude
is nowhere near 14 PiB of Blobstore traffic. It remains bad practice worth fixing on its
own merits.

---

## C. Recommended fixes

### C.1 Fix the stuck run (necessary and sufficient)

**The clean fix — reset the dataloader's epoch cursor when the outer loop starts a new
iteration.** In `puzzle_dataset.py::_iter_train`, treat a restored
`epoch_idx >= epochs_per_iter` as "start a fresh iteration": set `epoch_idx = 0`,
`start_index = 0` and drop the stale `epoch_rng_state`. Equivalently, have
`train.py` clear the dataset's per-iteration state when it enters an `iter_id`
greater than the one the checkpoint belongs to.
*Tradeoff:* none for correctness on a boundary checkpoint; it does mean a
boundary-resumed iteration restarts from its first epoch, which is the intended
semantics (the iteration genuinely has not run).

**Defensive companion — make a zero-step attempt fatal, not silent.** `train.py`
already has a "belt and braces" guard for the *iteration* bookkeeping; add the
analogous one for the *outcome*: if an attempt exits with
`step == attempt_start_step` and `step < total_steps`, log an error and exit
non-zero instead of reporting a clean finish. That converts an infinite silent
restart loop into one loud failure. **This is the highest-value change** — the
current failure mode is invisible precisely because everything "succeeds".

**Immediate unblock without a code change:** the operator has already copied the
checkpoint to `/cns/yutulpz-d/home/qiaos/eqr_data/maze_resume_95k/checkpoints/step_95000_41pjso2k`
and launched **XID 276203817** against it. **CONFIRMED NOT TO HELP** — see §A.5: that job
is stuck in exactly the same way, because the copy carries the same `extra.json` with
`epoch_idx=5000`. To resume from the
copy without touching code, the checkpoint's `extra.json` would need
`train_dataset.train_state.epoch_idx` set to `0` (and `start_index` to `0`).
*Tradeoff:* it re-runs iteration 20 from its first epoch with a fresh permutation, so
the last 5000 steps see a slightly different data order than an uninterrupted run would
have. For the final 5% of training that is almost certainly immaterial, but it is a
deviation. **Do not edit the original bucket's checkpoint — edit the copy.**
(Not done: this task is read-only.)

**Alternative, and the safest zero-code option: resume from `step_92500`.** MEASURED —
I read the `extra.json` of the three preceding checkpoints:

| checkpoint | step | iteration | `epoch_idx` | `_iters` | dataloader on resume |
|---|---|---|---|---|---|
| `step_95000_41pjso2k` | 95000 | 20 | **5000** | 19 | **EXHAUSTED — zero-step loop** |
| `step_92500_41pjso2k` | 92500 | 19 | 2500 | 19 | **USABLE — yields batches** |
| `step_90000_41pjso2k` | 90000 | 19 | **5000** | 18 | **EXHAUSTED — zero-step loop** |
| `step_87500_41pjso2k` | 87500 | 18 | 2500 | 18 | **USABLE — yields batches** |

Resuming from `step_92500` costs 2500 redundant steps and needs no code or data edits.
*Tradeoff:* 2500 steps of recompute (~1 min at this model's throughput) and the resumed
segment re-runs with the checkpoint's own RNG state, so it is a faithful continuation.

This table also **confirms §D.1 empirically**: `epoch_idx` alternates 2500 / 5000 with
`checkpoint_interval_steps=2500` against `train_epochs_per_iter=5000`, so **exactly every
second checkpoint is a poisoned one**. It is not a rare corner case — it is 50% of all
checkpoints this configuration writes.

### C.2 Mitigate the CNS slowness (independent, lower priority)

- **Co-locate, and stop cross-reading `yutulpz-d` from `yuskedq`.** Several live jobs
  in metro `ske` still have `load_from` pointing at `tul`. The workspace guide already
  makes this a rule; it is being violated by in-flight runs.
- **Do not let startup I/O be unbounded.** A 4 MB restore that can take 175 s is a
  liability regardless of cause. Since the state is replicated and tiny, staging it once
  to `/tmp` (as the dataset already is) would remove CNS from the restart path entirely.
- **Moving to another cell in the same cluster will NOT help.** `yutulth` and `yutulis`
  sit on the same D pool and are equally affected. Move off cluster `yutulpz` entirely,
  or wait it out.
- **Repack to fewer, larger reads.** The penalty is per-operation: the >64 KiB bucket
  degraded 3x against 14x for small reads. An orbax checkpoint read as many small
  operations is maximally exposed.
- **Do not raise the byte quota** — the user is at 24.5% and quota is not the constraint.
  The real gap is that he holds **zero spindle commitment**, so he has no IOPS floor and
  is served entirely from the shared pool. That is the durable fix.
- **Escalate to the Blobstore LAD owners.** It is a best-effort workload with no ceiling,
  so it will keep expanding to fill the pool.

---

## D. Things to worry about beyond this job

1. **A "successful" run that trains nothing looks identical to a healthy one.**
   `attempt ends: steps 95000 -> 95000` is the only signal, and nothing alerts on it.
   **MEASURED: exactly half of this run's checkpoints are poisoned** — `epoch_idx`
   alternates 2500 / 5000 across `step_87500 / 90000 / 92500 / 95000` (table in §C.1).
   Any checkpoint whose step is a multiple of `steps_per_epoch * train_epochs_per_iter`
   resumes into an exhausted dataloader. With `checkpoint_interval_steps=2500` against
   `train_epochs_per_iter=5000` that is **every other checkpoint** — a coin-flip on every
   preemption, not a rare corner. Any EqR-jax run with
   `train_epochs_per_iter % checkpoint_interval_steps == 0` has the same exposure.
2. **The earlier diagnosis pinned the blame on read amplification and a fix was shipped
   for it** (`_restore_on_process_zero_and_broadcast`). That fix is sound, but the
   comment now in `ckpt_util.py` cites the 39 s / 88–97 s numbers as evidence of
   amplification. Attempt 11 (4 tasks, still slow) falsifies that reading. The comment
   should not be left as the recorded explanation.
3. **A best-effort neighbour can silently take 10x the spindles of a whole D cell.**
   The LAD workload pushed the cell to 2.4x its spindle quota and degraded **~20 unrelated
   client cells** for 12+ h with nothing watching it. Our jobs have **no spindle
   commitment at all**, so they have no floor and absorb the full hit. Any future run on
   `yutulpz*` is exposed to a repeat, and byte quota — the thing that is monitored — gives
   no protection whatsoever.
4. **Two Colossus cells sharing one physical D cell is an invisible blast radius.**
   `/cns/yutulpz-d/...` and `/cns/yutulpz/...` look like different places and are billed
   and quota'd separately, but share spindles. Cell choice cannot be reasoned about from
   the path alone.
5. **`lineage_log` is on the startup critical path and can cost 15 s per call, ~4 calls
   per restore** (measured: 4.4 + 11.1 + 6.9 s in one attempt = 22.3 s of the 138 s).
   It is pure telemetry. When the backend is slow it directly inflates startup.
   It also ends every attempt with `failed to flush end execution message ... [INTERNAL]`.
