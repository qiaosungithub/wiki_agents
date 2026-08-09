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
| Long stage-2 run | Not launched: ~57 h of compute plus queue time |

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

Open items:

1. Launch the 57-hour stage-2 run from stage 1 (fresh xid, `--load_from` the
   stage-1 `checkpoint_2180`).
2. Whether a 57-hour run needs an explicit supervisor for the PENDING /
   preemption cycles below.
3. `scienceqa_img` and `vizwiz` have no CNS replica — declared in `default.py`,
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
