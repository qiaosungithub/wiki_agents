# Migrating `jax_llava` To XM/Borg Infra

Living progress file for "run `jax_llava` on xm infra and reproduce the
result": current state, the decisions that still bind, the traps worth carrying
forward. **Fold into `../projects/vlm_training.md` once the migration lands.**
Branches `sqa.late_fusion_xm` (`jax_llava`) and `data_upload_xm`
(`paligemma-data-upload`).

## Where This Stands

| Piece | State |
|---|---|
| Data (cc12m + eval bundle + stage-2 SFT mix) | **Done**: three metros, verified per object |
| Stage 1 (cc12m pretrain, 2180 steps) | **Reproduced** within ±0.009 of the reference curve; ends loss ~1.444 / acc ~0.630, 1.37 steps/s on v7-32 (~26 min) |
| Stage 2 (SFT, 75000 steps) | **Trains** at 0.357 steps/s on v7-32; the full-coverage smoke **passes end to end** |
| Long stage-2 run | **Running**: XID 278496995, v7-32 @ cbf, resumed at step 12800 on the FIXED mesh |

Reference: WandB `sqa24-massachusetts-institute-of-technology/jax-llava`, run
`gtqntg5g` (`worthy-bird-70`), compared at every logged step; ours is marginally
ahead, consistent with the reference reading a 150-shard slice where we read all
1097.

**Stage 2 costs 4x stage 1 per step** (bs256 / image 336 / `max_txt_len` 512:
longer sequences, 12-source mix, periodic sampling) — that is the 57 h.
**Checkpointing is 11% of it** (236 s every 800 steps), and widening the
interval is the wrong trade on a preemptible slice: it buys 4 h and costs 3200
steps per preemption. **v7-32 is the ceiling**: Borg registers v7 at 4/8/16/32
only and preflight rejects v7-64 (`../tpu_reference.md`).

**The full smoke passes** (XID 278211441): `g3_full_smoke` runs 12 steps (10
stage-1 + 2 stage-2) over the **production** stage-2 mix and the production eval
lists — 45 shard roots, all 17 benchmarks, sampling, image logging, and the
stage boundary. Artifacts verified rather than inferred from the status: 7 viz
PNGs, checkpoints 5/10/12, 383 eval result files, durable pretrained checkpoint.

**Production stage-2 is running**: **XID 278259733**, v6p-64 @ `yutulpz` (tul),
started from the stage-1 `checkpoint_2180` mirrored into `nm-d`. It enters
stage 2 directly at global step 2180 with a params-only restore, and **acc
picks up continuous with the stage-1 endpoint** — 0.578 → 0.620 → 0.637 against
stage-1's 0.630. v6p-64 was chosen over v7-32 for ~2x the per-step throughput;
**v6p also exposes two cores per chip**, so `jax.device_count()` is 128 and
bs256 still divides evenly. It was preempted around step 2400 with the
checkpoint intact — normal, not a failure.

Open items:

1. Confirm the end-of-run benchmark numbers reproduce the reference.
2. `scienceqa_img` and `vizwiz` have no CNS replica — declared in `default.py`,
   used by no config, never copied. Copy them before enabling either.

## The Data: Final Layout

One crawl (`gs://kmh-gcp-us-east5`) fanned out to three metros, each replica
byte-identical and verified **per object** (name + size) against the `go-d`
copy, each carrying a `_SUCCESS` this program wrote.

| | cc12m | eval bundle | stage-2 SFT mix |
|---|---|---|---|
| objects | 1097 tars + 1097 sidecars | 1309 | 12 sources |
| payload | 1.5044 TiB | 170 GiB | -- |

Roots `/cns/is-d/home/qiaos/data` (cbf), `/cns/nm-d/…` (tul), `/cns/li-d/…`
(lpp), from the `/cns/go-d/…` (cmh) source copy. All of it charges to
`deepmind-resources-colossus`, not the 500 GiB personal ceiling — which is why
`fileutil quota qiaos <cell>` answers *no such user* in every one. Known
imperfection, deliberately not fixed: 27 files under 1 MiB landed at `rs=9.4`
instead of `r=3.2` (1.4 MiB total; the size-based encoding split was never
ported to the CNS-to-CNS copier). Not a partial copy.

**Design as if egress is always billed, then make it $0 by staying in one
region.** The operator pays egress from his own external GCP project, so a
cross-region read is a real bill (`../storage.md` owns the general rule):

```
hop 1   gs://kmh-gcp-us-east5  ->  /cns/go-d       same region (cmh), $0
hop 2   /cns/go-d              ->  is-d/nm-d/li-d  CNS->CNS, internal, $0
```

**Hop 1 must be initiated from a task in the bucket's own metro.** Hop 2 is
deliberately cross-metro and free because both ends are internal Colossus
(proven by `bigstore_paths_used: 0` in its `_SUCCESS`), and it is also the fast
leg: 878 / 647 / 303 MiB/s to cbf / tul / lpp, against 120 MiB/s for the
bigstore read.

**The three `kmh-gcp-us-*` buckets are three independent crawls, not
replicas**: `00000.tar` is 943 MB in us-east5, 1584 MB in us-central1 and
1683 MB in us-central2, because kmh re-crawled with img2dataset at 62-66%
success. This is why the layout above crawls once and fans out;
`../storage.md` owns the general rule.

**Never accept the launcher's default CNS root** (`/cns/yutulpz-d/...`): pin
`--cell` and the CNS path together every time, since `xm_launcher.py` maps cell
to a same-metro bucket and a mismatch has already caused a pruner kill. Metro to
GCP region, verified from google3 source rather than an assistant's answer:
`cbf`=us-central1, `cmh`=us-east5, `tul`=us-central2, `lpp`=europe-north1 — and
`tul` maps to no GCP region for egress purposes. Which metros to keep data in:
`v7_storage_placement.md`.

## Traps: Copiers

| Rule | Evidence / detail |
|---|---|
| **When adapting a copier to a new data shape, re-audit every place the old shape is assumed** | Three inherited assumptions each cost a launch: work split by filename suffix (`.tar`/`_stats.json` matched nothing in a mixed bundle, so both worker groups got empty lists and the run "succeeded" having copied nothing); a root-level `manifest.jsonl` demanded of a multi-prefix source; an encoding canary hard-coded to that manifest. |
| **A partition that can drop work silently should not exist** | Split on SIZE, which is total by construction, and assert the halves re-sum. |
| **A `_SUCCESS` you did not write proves nothing** | These datasets ship upstream markers inside each prefix, so a recursive copy lands the marker as soon as the small files do — long before the shards. |
| **For a copy, completion is a property of the filesystem, not the scheduler** | `tpu check` said `SUBMITTED` for an hour after Borg had the work unit as `BORG_STATE_SUCCESS`. Gate on artifacts: object count against the source, plus your own marker. |
| **A copy does not inherit the destination directory's encoding; a directory the job creates does not inherit group accounting** | Name the encoding per file and READ IT BACK — a 3-shard smoke landed `r=3.2` where `rs=9.4` was configured, 4.6 TiB instead of 2.2 TiB at full scale. Set `quota_accounting` recursively on the home root, which fixes existing files and everything written later. `../storage.md` owns both. |
| **A workstation cannot test the write half of a bigstore -> CNS copy** | Corp credential: `DestinationPermission: Wrong type CORP in restriction`. It still tests imports, flags, planning and every guard — where the bugs above were caught in seconds. Read a local write failure as "cannot test here", not "the copy is broken". |
| `gfile` has no `ListRecursively` | The recursive walk is `gfile.Walk`, with `os.walk` semantics. |

## Traps: Borg vs. The GCP Cluster

Every stage-2 failure had one shape: code written for a cluster where data sits
on NFS or in `gs://`, meeting Borg, where only CNS exists.

| Rule | Evidence / detail |
|---|---|
| **Every dataset root must resolve to CNS** | Including sidecars (`region_descriptions.json`), COCO vis images, and the eval roots. An upstream `_SUCCESS` can sit three levels down, beside the shards. |
| **`gcloud` does not exist on a task** | Anything shelling out to it dies. |
| **Colossus does not glob** | `unexpected '*' at p 6`. Expand shard globs explicitly, on CNS as well as on `gs://`. |
| **Fix at the chokepoint, not at each source** | OV1.5 shard roots are assembled across several modules; patching resolution, then the glob expander, each fixed one route and left the others. The durable fix went into the **webdataset opener**, where every shard converges. |
| **When the error names no path, make it name one** | Three launches died in fsspec with `No module named 'gcsfs'` and only fsspec frames. Four lines that raise with the offending URL turned every later occurrence into a one-look diagnosis. |
| **Enumerate the whole surface offline before launching** | Resolving every dataset against CNS in one pass caught ten failures at once: fifteen lines and one minute, against ~10 min per remote attempt. |

## Traps: v7-32 Topology

A v7-32 exposes **64 devices, not 32** (`../tpu_reference.md` owns the geometry
and the chip-vs-device rule). Two JAX consequences that only show up here:

- `global_array_to_host_local_array` requires each host's devices to form a
  contiguous subcube, which a v7-32 does not satisfy, and it raises rather than
  falling back. The working form is `multihost_utils.process_allgather`
  (`tiled=True` for an already-sharded array). **When a helper raises on a
  topology, ask whether the surrounding code needs the sharded round-trip at
  all** — both call sites were moving a handful of values to a log line.
- **The generation KV cache must take its dtype from the embeddings.**
  Hard-coded `bfloat16` against float32 params raises inside
  `lax.dynamic_update_slice`, invisible in stage 1 because generation only runs
  when eval or sampling is on.

## Traps: A Smoke Is Only As Wide As The Run It Gates

The earlier smoke used cc12m for stage 2 and three benchmarks, so it passed
while the real run would still have died: it never reached the twelve loaders
or eleven of the seventeen evals. **A smoke narrower than the run it gates
cannot gate it.** Widening it to the production mix and eval lists cost two
launches and closed seven bugs.

**`os.access` is POSIX and Colossus is not.** MMBench died with
`PermissionError: result cache dir is not writable` on a directory gfile writes
to happily — 40 min in, at the second-to-last final-eval task. `os.access`, the
stdlib `glob`, and `os.path.isfile` all answer *no* for `/cns/` instead of
raising, so each reads as a data or permission problem rather than as "wrong
filesystem API". The stdlib `glob` is the nastiest: `[]` means "this benchmark
has no shards".

**When one member of a family has the bug, check the whole family.** The same
six files (`eval_vlm_benchmarks`: gqa, seed_bench, cambrian_cvbench,
vlms_are_blind, docvqa, realworldqa) were missed both when four other evals were
converted to CNS-aware helpers and again here. All six sit AFTER the task that
crashed, so none had ever run; fixing them by reading the code instead of one
45-minute launch at a time was the difference between one relaunch and seven.

**A cap is only a cap if something reads it.** The smoke's eval block set
`max_eval_steps`, which nothing reads. Replacing it exposed a second layer of
the same mistake: `debug_max_samples` covers seven evals, but the
`eval_vlm_benchmarks` family takes `<benchmark>_num_samples`, defaulting to the
whole set — so the widened smoke still scored 8016 and 5349 samples on two
benchmarks. Two mechanisms; check each reader.

**`knn_full` and `mmbench` needed no copy — the data was already there.** The
143 GiB TFDS ImageNet tree is 1094 of the eval bundle's 1309 objects, and the
two MMBench TSVs are 90 MB fetched once from a workstation. Both were
unreachable only because the code resolved them through `gs://`, an NFS mount,
or HTTPS. **Prove the filesystem premise before writing the fix**: a 15-line
probe (`tools/g3_knn_tfds_probe`, no torch/JAX) confirmed google3's TF sees
`/cns/`, lists 1024+64 shards and decodes a tfrecord, in seconds.

**The config probe must model the runtime, not a stricter rule.**
`tools/g3_config_probe` now checks every dataset root, every root of an ENABLED
eval task, and the KNN data_dir — 45 + 17 + 1 locally in minutes, against 10-45
min per remote attempt. Three ways it was wrong first: it expanded only
`root[0]` (one of twelve sources proven); it condemned `gs://` by spelling,
reporting 34 false failures, when the durable fix rewrites `gs://` -> CNS inside
the webdataset opener and a `gs://` root is therefore correct; and it read the
RAW config, still carrying the zone placeholder, instead of the resolved one.

## Traps: A Second Metro Is A Different Code Path

Moving the production run from cbf to tul (v6p obtainability 3596 vs 936)
broke on resolution code that had never run, because **cbf was accidentally the
easy case**.

**`_rewrite_bucket_to_cns` probed a path that exists nowhere.** It strips a
shard spec at `{`, leaving `.../laion_220k/shard-`, and the `.`-test meant to
tell a file from a directory sees no dot in `shard-` and keeps it. So the
rewrite returned None for 34 OV1.5 roots whose shards are present, and the
locality guard read that as "no replica in this metro" and refused to start.
It never fired in cbf: there the `gs://kmh-gcp-us-central1` bucket matches the
zone's own bucket, the guard accepts the path, and the rewrite is never
reached. tul has no bucket of its own, so every OV1.5 root took the rewrite
path at once. **When a guard passes, check whether it passed for the reason you
think** — a path can be accepted by the branch that never examines it.

**The locality guard judged `gs://` by spelling, like the config probe did.**
Same correction: rewrite first, then require a real CNS target. It stays
fail-closed, and the rejection now reads "no CNS replica" rather than "zone has
no bucket registered".

**A hardcoded region allowlist in `_init_run` rejected tul outright** — three
GCP regions named in an assert that predates the CNS replicas. The real
question on Borg is "is there a data replica local to this zone", which
`g3_env` already answers fail-closed. Behind it sat a second zone table that
would not have fired until the FIRST CHECKPOINT ~40 min in: the dataloader's
replica regex listed only `go-d`/`yucmhcg-d`, so a state written in `nm-d`
could not have been resumed under strict mode. **Grep for every table keyed by
zone or cell before moving metro** — they fail at different depths, and the
shallow one hides the rest.

**A deterministic crash must not be auto-resumed.** `CODE BUG: AssertionError`
fails identically on the next attempt, because `--resume_xid` restages the same
snapshot; the supervisor retried it and burned a schedule slot for nothing. A
supervisor should classify: preemption and infra faults are resumable, a code
bug is not.

**A mirror is per metro.** The MMBench TSVs were copied to `is-d` only, so tul
failed on them until `nm-d` and `li-d` got their own copies. Anything added to
one replica has to be added to all three, or the next metro move finds it.

## Traps: Three Launches, One Shape — Code That Only Ran In cbf

Moving production from cbf to tul cost three launches, and every failure was
code whose cbf path had never been exercised. They fail at DIFFERENT DEPTHS,
which is why they surfaced one at a time:

| Failure | Where it hid |
|---|---|
| `AssertionError`: a zone allowlist naming three GCP regions | `_init_run`, 4 min in |
| `FileNotFoundError`: `COCO_val2014` absent from tul (40504 files, 6.2 GB) | stage-2 phase start |
| (latent) dataloader replica regex listing only `go-d`/`yucmhcg-d` | would have fired at the FIRST CHECKPOINT, ~40 min in |

**Grep for every table keyed by zone, cell, or bucket before moving metro**, and
**diff the top level of both data roots** — one command, and it would have caught
the COCO gap before the launch. The resolution code was right in every case; the
probe simply never asked, so the probe now covers all three.

**A warm start must not survive the run's own progress.** `load_from` pinned
the stage-1 checkpoint, and `resolve_borg_autoresume` treated ANY explicit
`load_from` as "the user asked for this, do not redirect". So every Borg task
restart began again at step 2180 and then died with
`Destination checkpoint_2400 already exists` — the checkpoint the previous
attempt had written. Eleven attempts, ~3 h of v6p-64, one loop.

The wiki already said "a resume must not carry `--load_from`", but that rule
was written for a HUMAN re-submitting. **Borg restarts a task for reasons
nobody chose** — preemption, drain — and each restart re-reads the config, so
the config itself has to be safe. The precedence is about whose checkpoint it
is: no progress of our own → honour the warm start; progress exists → it
supersedes a warm start from another run; a `load_from` inside our own
checkpoint root → left alone. `tests/test_autoresume` covers all three, runs
in seconds, and is the kind of check that repays itself the first time.

**Preemption is normal and is not a failure.** PROD is preemptible: the run was
preempted at ~2400 with its checkpoint intact and returned to PENDING. A
supervisor must read PENDING/SUBMITTED/STARTING as healthy — and must NOT
auto-resume a `CODE BUG`, which is deterministic and fails identically on the
next attempt, burning a schedule slot and hiding the signal.

## The 7x Slowdown Was A Silent Mesh Fallback

Stage-2 ran at **0.312 steps/s where the reference did 1.871** — same recipe,
same 64 devices, same bs256/336/512. Config was identical; the difference was
the mesh.

`utils/pjit_util.get_mesh()` looks `device_kind` up in a `TOPOLOGIES` table and,
on no match, falls back to a flat `(N,)` mesh intended for CPU/GPU debug. v7 was
not in the table. Under `hsdp`/`hsdp_legacy_data` the model axis is
`axis_names[-1]`, which on a 1-D mesh is the ONLY axis — so every parameter was
sharded across all 64 devices, every matmul paid a full-mesh collective, and the
data axis resolved to that same axis. **Nothing failed. A 1-D mesh trains and
converges; it is merely several-fold slower**, which is why it survived a full
production run.

Fixed: v7 gets the v5-style 3-D shapes (its slice geometry is identical to
v6p), so 64 devices → `(4,4,4)`. Measured **0.312 → 1.136 steps/s, 3.6x**.
Confirmed in production (XID 278496995): mesh `(4,4,4)`, resumed at step 12800
rather than restarting, **0.878 steps/s true wall-clock including checkpoints
and eval** — 83% of the reference's 1.056 overall pace, ETA ~20 h.

**Checkpointing became the dominant overhead once training got fast.** A save
is ~245 s and the interval is 800 steps: that was 9% of a 3.2 s/step run and
is ~28% of a 0.88 s/step one. The right interval is a function of step time,
not a constant — but widening it also widens what a preemption discards, so it
is only worth revisiting on a slice that holds (this one has not been
preempted).

Three things worth carrying:

- **Match v7 as `tpu7`, not `v7`** — see `../tpu_reference.md`. The wrong key
  would have looked like a fix and changed nothing.
- **A fallback that preserves correctness is the hardest kind of bug.** Make it
  loud: `get_mesh` now warns when a TPU kind is unknown, and
  `tools/g3_mesh_probe` reports the mesh a real slice builds.
- **Async dispatch misattributes profiling.** `p_train_step` returns
  immediately, so the first op that touches its result — here
  `metrics_tracker.update` — absorbs the entire device wait. Timing that call
  said "metrics cost 2.78 s"; the step did. Time the WHOLE iteration too, so
  the parts must reconcile against the total, and block explicitly before
  attributing anything.

A separate fix landed on the way: `MetricsTracker` was calling
`jax.device_get` on 33 leaves EVERY step, which serialises the async pipeline.
It was not this bottleneck (metrics come back already-reduced and replicated)
but it is a real one at other shapes; the accumulation is now device-side with
one transfer per log interval, value-equality checked by
`tools/g3_metrics_tracker_probe`.

## Stage-2 Is Tracking The Reference Curve

The strongest available evidence that the port is faithful, and it is a
per-step comparison over the WHOLE trajectory rather than an endpoint one.
`llava_repro/compare_curve.py` diffs every shared step against the reference's
771-point history:

| | value |
|---|---|
| shared steps compared (at step 20600) | **79** |
| mean acc delta | **-0.00031** (sd 0.00018, max abs 0.0008) |
| mean loss delta | **+0.00153** (sd 0.00053, max abs 0.0031) |
| outside tolerance | **0/79** |

Same recipe, same 2180-step stage-1 start (acc 0.630) — on Borg/CNS instead of
the GCP cluster, reading CNS replicas instead of `gs://`. Reference endpoint is
acc 0.746 / loss 1.081 at 77180.

**The loss offset is systematic, and that is fine — because it is FLAT.**
79/79 loss deltas are positive, which is not noise; a +0.0015 bias that size is
what bf16 accumulation order on a different mesh looks like. The test that
matters is whether it COMPOUNDS: first half +0.00147, second half +0.00158,
slope +3.0e-8 per step, extrapolating to +0.0023 over the full 77180. A real
divergence (wrong data mix, wrong LR schedule, a shard reading the wrong split)
grows with training; a numerics offset stays put. **Report the trend, not just
the magnitude** — a small delta that is quietly widening is the dangerous one,
and a single matching point cannot tell the two apart.

**Compare on the GLOBAL step counter.** Our log prints `[<global>]` and also
`stage_step = global - 2180`; the reference's `_step` is global. Lining up
`stage_step` against `_step` shifts every pair by 2180 and manufactures a
divergence that is not there.

**Compare mid-run against WandB history, not against the final number.** The
spreadsheet only records the stage boundary, so a run that is silently diverging
looks fine until it ends; the per-step curve says so within an hour.

### Scoring The Final Benchmarks: Harvest The RANK LOG, Not `metrics.json`

`tpu_scripts/llava_repro/compare_final_metrics.py` diffs a finished run's 17
final benchmarks against the reference (`reference_gtqntg5g_final.json`, pulled
from WandB `gtqntg5g`). Three things it had to get right:

* **`vqav2`, `textvqa` and `refcocog` write NO `metrics.json`** — only
  `results_final.json`, which holds raw predictions. Their scores exist solely
  as `key=value` pairs on the `logging_writer` line of the rank log. Harvesting
  `eval_results/*.metrics.json`, the obvious approach, silently drops three of
  the headline numbers.
* **Scan EVERY rank log, not `rank_0`.** That filename tracks Borg task order,
  not JAX process index: in the smoke run the final-metric block landed in
  `rank_1_attempt1.log`.
* **Four tasks have no baseline at all.** `docvqa`, `realworldqa`,
  `cambrian_cvbench` and `vlms_are_blind` were added to `final_eval_tasks`
  after the reference run finished, so they are reported `NO-REF` and
  distinguished from a genuinely `MISSING` number (an eval that crashed) —
  which is treated as a reproduction failure, same as a wrong value.

Validated against the smoke run (XID 278211441): all 17 tasks harvested, 0
unexpectedly absent. The supervisor runs it automatically when the run reaches
`completed`, so the verdict is recorded whether or not anyone is watching.

Units are NOT rescaled anywhere. Both sides are the same key namespace emitted
by the same code, so they match by construction; a rescale is exactly the kind
of fixup that would hide a real regression. (GQA reading `0.087` in the smoke is
not a fraction/percent bug — it is 0.087%, 11 correct out of 12578, from a
12-step model.)

## Traps: Running The Jobs

| Rule | Evidence / detail |
|---|---|
| **A resume used to submit twice** (fixed; the shape is the lesson) | The post-submit check grepped the launch log for `Launched experiment`, which XManager prints only when it CREATES an experiment — a `--resume_xid` launch goes through `get_experiment()` and prints `Added N work unit(s) to` instead. The check read that as a dead launch and re-ran the identical command, `--resume_xid` included, so a second work unit joined the same experiment and the two raced for one checkpoint path (`Destination … already exists`); registration sat under the same test, so neither reached `tpu check`. It survived because the retry's `tee` had no `-a` and overwrote the evidence. **A liveness check keyed to one exact string fails on the variant path it never saw** — accept every success line, and never let a retry overwrite the log it is diagnosing. |
| **Stopping is per experiment unless you name the work unit** | `xmanager stop --experiment_id=<xid> --work_unit_id=<n>` is the granular form; `tpu cancel` and a bare `xmanager stop` take the whole experiment. `borg … jobs` is NOT a subcommand and silently finds nothing. |
| **A resume must not carry `--load_from`** | Use `--resume_xid` and let autoresume find the newest complete checkpoint. Exception: a CODE CHANGE needs a fresh xid *and* an explicit `--load_from`, because `--resume_xid` restages the ORIGINAL run's snapshot — three fixes once landed in git and none reached the cluster. |
| **Queued is not failed** | Over-subscribed v7 quota leaves work units PENDING for hours, and a supervisor reading "not running" as "dead" resubmits, every resubmission adding colliding work units. `tpu preflight` reports GLOBALLY obtainable chips, which says nothing about this alloc; the honest answer is the work unit's own `GQM_RESOURCE_DEFICIT_INFO`. |
| **PROD is preemptible** | Slice defrag killed a run at step 220. Resume must be automatic, and bounded, so a real crash cannot loop. |
| **Verify a watcher against live output before trusting it** | Four supervisors in a row misreported, each from an unverified command: `borg … jobs`, a `tpu check` pattern with the columns in the wrong order (it prints `XID STATUS NAME`), a status vocabulary missing `SUBMITTED`/`unknown`, `blaze run --cwd=`. Each produced a plausible EMPTY result rather than an error. Run the predicate against current output and assert the answer you expect. |
| Preflight cannot verdict a CPU-only job | `Unknown accelerator arch 'cpu'`; submit those with `--skip-preflight`. |
| `tpu queue`'s parser is an allowlist | `--app.<flag>=<v>` forwards one named flag verbatim to the packaged binary. |

## Traps: Metrics Have To Outlive The Task

**`write_scalars` reaches only the datatable, and once a run ends the Borg task
log is GC'd within minutes while `borg tasklog` is refused by a corp
credential** — two stage-1 runs therefore left no recoverable loss curve.
Training scalars now also go to stdout, mirrored to the checkpoint bucket, which
is how the KV-cache traceback was recovered after its task was gone.

**The results spreadsheet cannot answer a stage-1 question**: its `Train acc /
Train loss` columns hold the *stage-2* endpoint, since a row records one number
per stage boundary. WandB has per-step history for both.

### The Sheet Holds Two Baselines WandB Does Not

Row 325 of `PaliGemma-baseline-cleaned-20260608` IS the reference
(`worthy-bird-70` == `gtqntg5g`; every value matches). But it reports **CVBench
56.67 and VLMs-Are-Blind 12.47, which are absent from the WandB summary** — so
building the baseline from WandB alone writes off two comparable benchmarks as
"no baseline". Both are now folded into `reference_gtqntg5g_final.json`, taking
the tab's own metric conventions, which its notes state explicitly: *"CVBench
uses official prompt plus direct-answer-letter suffix"* → `cambrian_cvbench_acc`
(official, NOT micro); *"VLMs Are Blind task mean N (micro M)"* →
`vlms_are_blind_task_mean` (NOT micro). Picking the wrong variant of either
would land a plausible number in the right cell.

**15 of 17 benchmarks therefore have a target.** Only `docvqa` and
`realworldqa` are genuinely baseline-free — the tab files them as "extra
benchmarks without columns".

`llava_repro/build_sheet_row.py` renders a harvest into that tab's column order
and prints it beside row 325. It **prints and never writes**: placement is a
judgement call and a wrong row looks exactly like a right one. It re-derives the
column map from the live sheet every run (header is row 2, not row 1) rather
than hardcoding it, since code and spreadsheet drift independently.

### Two Ordering Traps In The Harvest

Both are invisible until a run has been preempted enough times to matter, which
is exactly when nobody re-checks the tool.

* **`sorted()` on rank-log paths is lexicographic**, so
  `rank_0_attempt10.log` sorts BEFORE `rank_0_attempt2.log`. A "last file wins"
  harvest therefore returns an EARLY attempt's numbers after ten preemptions.
  Fixed by keying on the training step the metric line was emitted at, which
  states the actual intent (newest evaluation) and does not care how Borg
  numbered the attempts. `test_harvest.py` pins it with no CNS access;
  mutation-checked — the pre-fix code fails 3 of 7 tests, returning 11.0 where
  59.03 is right.
* **The harvest now reports WHICH step produced the numbers** and refuses to
  present a short-checkpoint eval as the run's score. `result_logging.md` is
  explicit that an eval of a short checkpoint is a different, pessimistic
  result; the smoke's step-12 metrics are correctly flagged non-comparable
  against the reference's 77180.

Unrelated but the same shape: **`pgrep -f <script>.sh` matches its own shell**,
because the pattern is in the argv of the `sh -c` running it. It reports one
supervisor too many, which invites killing the only real one.
`tpu_scripts/check_watchers.sh` matches the interpreter+script shape instead.

## The Recovery Path, Drilled While Nothing Was Broken

A recovery mechanism first exercised during the emergency is a guess, and this
one has already failed in production once (XID 278259733: the warm-start
`load_from` was re-applied on every Borg restart, so the job restarted at 12800
and died on `checkpoint_N already exists`, eleven times). So it was drilled
read-only against the LIVE run, mid-flight, touching nothing.

`llava_repro/resume_drill.py` replicates `ckpt_util`'s two completeness
witnesses through `fileutil` — it imports none of the job's code and cannot
perturb it. Every link in the chain checked out:

| Link | Verified |
|---|---|
| A complete checkpoint exists | 4 of them; `_pending_dataloader_state` correctly skipped as not `checkpoint_N` |
| Each carries both witnesses | `commit_timestamp_nsecs` present AND 8 non-empty `dataloader_state` files |
| The warm start is superseded | `load_from` still points at run **prod-e**'s `checkpoint_12800`; since that prefix is outside this run's checkpoint root, self-progress wins → resume from `checkpoint_18400`, NOT 12800. This is the precedence fix doing its job on the real config. |
| A resume can repackage | `stagedir` recorded in `~/.tpu_jobs.json` — without it `tpu queue --resume_xid` REFUSES to package rather than silently shipping the current checkout |
| The snapshot has the mesh fix | `"tpu7"` present in the stagedir's `pjit_util.py`, so a resume cannot regress to the 1-D mesh |
| Preemption budget | `max_task_failures=-1`, unlimited |

**The `load_from` line in the live config is the trap, still armed.** It reads
`.../xid_278366344_...prod-e/checkpoints/checkpoint_12800`. Nothing about that
looks wrong in the yaml, and it is only harmless because
`resolve_borg_autoresume` prefers self-written progress. Do not "tidy" that
precedence rule.

## The Eval Harness Was Lying: Every Rank Scored Process 0's Answers

The single most important finding of the migration, and it nearly produced the
opposite conclusion from the truth.

Online evals showed VQAv2 **16.84** against the reference's 67.63, TextVQA 5.37
against 39.78 — a ~50-point collapse — while the TRAINING curve matched to a
mean of -0.0003 acc. That combination is itself the diagnosis: the teacher-forced
forward pass is what train acc measures and it was right, so the fault had to be
in the autoregressive path the evals use.

**Root cause.** `train.py::run_p_sample_step` returns the GLOBAL gathered batch
(`local_B * 8` rows), but all eight eval files consume it host-locally via
`zip(batch["aux"], out_strs, batch["is_pad"])`. `zip` stops at the shortest, so
every rank consumed `out_strs[0:32]` — **always process 0's slice**. Rank 0 was
correct by coincidence; ranks 1-7 scored process 0's answers against their own
questions, i.e. at chance.

**The probe that found it.** Per-rank accuracy, which separates instantly:

| rank | acc | yes/no answered with a non-yes/no |
|---|---|---|
| 0 | **66.58** | 2/981 |
| 1-7 | 9.2 - 10.5 | ~62% |

`(66.58 + 7*9.6)/8 = 16.72` predicted vs **16.84** observed. Confirmed by rank
r's answer at index i being byte-identical to rank 0's, 2680/2680, on every
rank, despite different questions.

**Why the obvious probe missed it.** Shifting the concatenated predictions
against ground truth by +-1, 2, 4, 8, 16, 32 made accuracy WORSE at every
offset, which reads as "alignment is fine". A constant shift cannot express
"rank r reads rows 0..31 instead of 32r..32r+31". **When a global test says
alignment is fine but the numbers say otherwise, split by the unit the work is
distributed over.**

**Verdict: the migration reproduces the reference.** All 9 corrected cells fall
within 2.4σ; pooled residual -1.43 ± 0.46 points.

**The fix** (`_process_local_rows`) inverts the placement by asking the sharding
which global rows this process addresses, rather than assuming `PRI*B`. The
naive offset is right on today's mesh and wrong on an interleaved one — a layout
assumption of exactly the kind that caused the 1-D mesh bug. It RAISES on a
row-count mismatch, because a misaligned batch is invisible downstream: it just
scores at chance.

**Consequence for this run:** `_stage2_final` calls the same function, so the
17 final benchmarks will be wrong. Training and checkpoints are sound, so a
**final-eval-only pass over the last checkpoint on fixed code** is sufficient —
the 20 h of training does not need repeating.

### A regression the eval fix does NOT repair

prod-f's MME collapses because 164/297 predictions begin `"To determine"`, all
7-8 words, cut off mid-phrase, **0/164 containing a yes/no**. The model has
started emitting chain-of-thought preambles on yes/no prompts and the 8-token
`shortqa` budget truncates them before the answer arrives. That is model-
behaviour drift, not measurement. Raising the token budget would hide it rather
than fix it.

### Tests that only run where they cannot catch anything are worse than none

The regression tests passed under a plain interpreter and failed 7/7 under
blaze: in google3, JAX refuses any call made before `InitGoogle()`, which
`absl.app.run()` triggers, so building a Mesh from a bare `__main__` block dies
with *"Attempted call to JAX before absl.app.run() is called"*. **That failure
reads as the FIX being broken rather than the harness being unportable** — the
worst possible mode for a regression test. Wrapped the runner in `app.run()`;
verified 7/7 pass with the fix present and 6/7 fail with the guard deleted.
