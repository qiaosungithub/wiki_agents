# Migrating `jax_llava` To XM/Borg Infra

Living progress file for "run `jax_llava` on xm infra and reproduce the result".
Owns the current state, the decisions that still bind, and the traps worth
carrying forward. Fold into `projects/vlm_training.md` once the migration lands.

Branch: `sqa.late_fusion_xm` (`jax_llava`), `data_upload_xm`
(`paligemma-data-upload`).

## Where This Stands

| Piece | State |
|---|---|
| Data (cc12m + eval bundle + stage-2 SFT mix) | **Done**, three metros, verified per object |
| Stage 1 (cc12m pretrain, 2180 steps) | **Reproduced**, matches the WandB reference within ±0.009 |
| Stage 2 (SFT, 75000 steps) | **Trains**, but the full-coverage smoke still fails on eval/IO paths |
| Long stage-2 run | Not launched |

**Stage-1 end state: loss ~1.444, acc ~0.630**, at 1.37 steps/s on v7-32
(2180 steps in ~26 min). Reference: WandB
`sqa24-massachusetts-institute-of-technology/jax-llava`, run `gtqntg5g`
(`worthy-bird-70`); compared at every logged step, ours marginally ahead,
consistent with the reference having read a 150-shard slice where we read all
1097.

**Stage-2 measured cost: 0.357 steps/s on v7-32** at bs256 / image 336 /
`max_txt_len` 512 -- 4x slower than stage 1 (longer sequences, 12-source mix,
periodic sampling). 75000 steps ~= **57 h of compute**, plus queue time.
Checkpointing is 11% of that (236 s every 800 steps); widening the interval
buys 4 h and costs 3200 steps per preemption, which is the wrong trade on a
preemptible slice.

**v7-32 is the ceiling.** Borg supports v7 slices of 4/8/16/32 only; preflight
rejects v7-64.

## The Data: Final Layout

One crawl (`gs://kmh-gcp-us-east5`), fanned out to three metros. Every replica
byte-identical, verified **per object** (name + size) against the `go-d` copy,
each carrying a `_SUCCESS` this program wrote.

| | cc12m | eval bundle | stage-2 SFT mix |
|---|---|---|---|
| objects | 1097 tars + 1097 sidecars | 1309 | 12 sources |
| payload | 1.5044 TiB | 170 GiB | -- |

Roots: `/cns/is-d/home/qiaos/data` (cbf), `/cns/nm-d/…` (tul),
`/cns/li-d/…` (lpp); `/cns/go-d/…` (cmh) is the source copy.
`fileutil quota qiaos <cell>` answers *no such user* in every one, i.e. every
byte is charged to `deepmind-resources-colossus`, not to the 500 GiB personal
ceiling.

Known imperfection, deliberately not fixed: 27 files under 1 MiB landed at
`rs=9.4` instead of `r=3.2` in the replicas (the size-based encoding split was
never ported to the CNS-to-CNS copier). 1.4 MiB total; not a partial copy.

### The Cost Rule That Produced That Shape

The operator pays egress out of his own external GCP project, so a
cross-region read is a real bill. Design as if egress is always billed and make
it $0 by staying in one region.

```
hop 1   gs://kmh-gcp-us-east5  ->  /cns/go-d       same region (cmh), $0
hop 2   /cns/go-d              ->  is-d/nm-d/li-d  CNS->CNS, internal, $0
```

Hop 1 must be initiated from a task in the bucket's own metro. Hop 2 is
deliberately cross-metro and free because both ends are internal Colossus
(proven: `bigstore_paths_used: 0` in its `_SUCCESS`). CNS-to-CNS is also the
FAST leg -- 878 / 647 / 303 MiB/s to cbf / tul / lpp against 120 MiB/s for the
bigstore read.

**The three `kmh-gcp-us-*` buckets are three independent crawls, not
replicas.** `00000.tar` is 943 MB in us-east5, 1584 MB in us-central1, 1683 MB
in us-central2 (kmh re-crawled the metadata with img2dataset, 62-66% success).
Sourcing each metro from "its own same-region bucket" therefore produces three
DIFFERENT datasets and makes loss curves incomparable -- the exact property a
reproduction must not lose. Verify sameness by comparing a shard's size across
buckets before calling a bucket a replica.

metro -> GCP region, verified from google3 source (not an LLM answer):
`cbf`=us-central1, `cmh`=us-east5, `tul`=us-central2, `lpp`=europe-north1;
`tul` maps to no GCP region for egress purposes.

**Never accept the launcher's default CNS root** (`/cns/yutulpz-d/...`). Pin
`--cell` and the CNS path together, every time; `xm_launcher.py` maps cell ->
same-metro bucket and a mismatch has already caused a pruner kill.

## Traps Worth Carrying Forward

### Copiers

- **A copy does not inherit the destination directory's encoding.** Name it in
  the copy options per file, then READ IT BACK -- a cell may silently
  downgrade. (3-shard smoke landed `r=3.2` where `rs=9.4` was configured:
  4.6 TiB instead of 2.2 TiB at full scale.)
- **A directory created by the job does not inherit group accounting.** Set
  `quota_accounting` on the home root recursively; that fixes existing files
  and everything created later.
- **When adapting a copier to a new data shape, re-audit every place the old
  shape is assumed.** Three separate inherited assumptions each cost a launch:
  work split by filename suffix (`.tar`/`_stats.json` matched nothing in a
  mixed bundle, so both worker groups got empty lists and the run "succeeded"
  having copied nothing), a root-level `manifest.jsonl` demanded from a
  multi-prefix source, and an encoding canary hard-coded to the manifest.
  A partition that can drop work silently should not exist: split on SIZE,
  which is total by construction, and assert the halves re-sum.
- **A `_SUCCESS` you did not write proves nothing.** These datasets ship their
  own upstream markers inside each prefix, so a recursive copy lands the marker
  as soon as the small files do -- long before the shards. Gate on object count
  against the source.
- **For a copy, completion is a property of the filesystem, not the scheduler.**
  `tpu check` reported `SUBMITTED` for an hour after Borg had the work unit as
  `BORG_STATE_SUCCESS`. Gate on artifacts (object count + marker).
- `gfile` has no `ListRecursively`; the recursive walk is `gfile.Walk`, with
  `os.walk` semantics.
- **A workstation cannot test the write half of a bigstore -> CNS copy** (corp
  credential: `DestinationPermission: Wrong type CORP in restriction`). It can
  test imports, flags, planning and every guard -- which is where the two bugs
  above were caught in seconds. Read a local write failure as "cannot test
  here", not "the copy is broken".

### Borg vs. the GCP cluster

Every stage-2 failure had one shape: code written for a cluster where data sits
on NFS or in `gs://`, meeting Borg, where only CNS exists.

- `gcloud` does not exist on a task; anything shelling out to it dies.
- Every dataset root must resolve to CNS, including sidecars
  (`region_descriptions.json`), COCO vis images, and the eval roots.
- Upstream `_SUCCESS` can sit three levels down, beside the shards.
- Colossus does not glob: `unexpected '*' at p 6`. Expand shard globs
  explicitly, on CNS as well as on `gs://`.
- **Fix at the chokepoint, not at each source.** OV1.5 shard roots are
  assembled across several modules; patching resolution, then the glob
  expander, each fixed one route and left the others. The durable fix went into
  the **webdataset opener**, where every shard converges.
- **When the error names no path, make it name one.** Three launches died in
  fsspec with `No module named 'gcsfs'` and only fsspec frames. Four lines that
  raise with the offending URL turned every later occurrence into a one-look
  diagnosis.
- **Enumerate the whole surface offline before launching.** Resolving every
  dataset against CNS in one pass caught ten failures at once; the check is
  fifteen lines and runs in a minute, against ~10 min per remote attempt.

### v7-32 topology

A v7-32 is 8 hosts x 4 chips over a 2x4x4 torus, and each chip exposes TWO
cores -- so `jax.device_count()` is **64**, not 32. A chip count is not a
device count and neither is a mesh size; batch sizes must divide the real
number.

- `global_array_to_host_local_array` requires each host's devices to form a
  contiguous subcube, which a v7-32 does not satisfy; it raises rather than
  falling back. The working form is `multihost_utils.process_allgather`
  (`tiled=True` for an already-sharded array). **When a helper raises on a
  topology, ask whether the surrounding code needs the sharded round-trip at
  all** -- both call sites were moving a handful of values to a log line.
- The generation KV cache must take its dtype from the embeddings; hard-coded
  `bfloat16` against float32 params raises inside
  `lax.dynamic_update_slice`. Invisible in stage 1 -- generation only runs when
  eval or sampling is on.

### Running the jobs

- **`tpu queue` submits twice.** Its post-submit check misreads success and
  retries; both submissions land, and two work units writing the same
  checkpoint path kill each other with `Destination … already exists`.
  De-duplicate within minutes, well before the first checkpoint interval.
  Work-unit granularity is
  `xmanager stop --experiment_id=<xid> --work_unit_id=<n>`; `tpu cancel` and a
  bare `xmanager stop` both take the whole experiment. `borg … jobs` is NOT a
  subcommand and silently finds nothing.
- **A resume must not carry `--load_from`.** Use `--resume_xid` and let
  autoresume find the newest complete checkpoint. Exception: a CODE CHANGE
  needs a fresh xid *and* an explicit `--load_from`, because `--resume_xid`
  restages the ORIGINAL run's snapshot -- three fixes once landed in git and
  none reached the cluster.
- **Queued is not failed.** Over-subscribed v7 quota leaves work units PENDING
  for hours; a supervisor that treats "not running" as "dead" resubmits and
  every resubmission adds colliding work units. `tpu preflight` reports
  GLOBALLY obtainable chips, which says nothing about this alloc; the honest
  answer is the work unit's own `GQM_RESOURCE_DEFICIT_INFO`.
- **PROD is preemptible** (slice defrag killed a run at step 220). Resume must
  be automatic, and bounded, so a real crash cannot loop.
- **Verify a watcher against live output before trusting it.** Four supervisors
  in a row misreported, each from an unverified command: `borg … jobs`, a
  `tpu check` pattern with the columns in the wrong order (it prints
  `XID STATUS NAME`), a status vocabulary missing `SUBMITTED`/`unknown`, and
  `blaze run --cwd=`. Every one produced a plausible EMPTY result rather than
  an error. Run the predicate against current output and assert the answer you
  expect.
- Preflight cannot verdict a CPU-only job (`Unknown accelerator arch 'cpu'`);
  such jobs submit with `--skip-preflight`.
- `tpu queue`'s parser is an allowlist; `--app.<flag>=<v>` forwards one named
  flag verbatim to the packaged binary.

### Metrics have to outlive the task

`write_scalars` reaches only the datatable, and after a run ends the Borg task
log is GC'd within minutes while `borg tasklog` is refused by a corp
credential. Two stage-1 runs therefore left **no recoverable loss curve**.
Training scalars now also go to stdout, mirrored to the checkpoint bucket --
which is how the KV-cache traceback was recovered after its task was gone.

The results spreadsheet cannot answer a stage-1 question: its
`Train acc / Train loss` columns hold the *stage-2* endpoint, because a row
records one number per stage boundary. WandB has per-step history for both.

## Open Items

1. **The full smoke (`g3_full_smoke`) is the gate for the 57-hour run.** It is
   12 steps (10 stage-1 + 2 stage-2) with sampling, image logging, online eval
   and final eval all on -- deliberately the parts that only break hours in.
2. Stage-2's `final_eval_tasks` includes `mmbench` (fetched over HTTPS from
   `opencompass.openxlab.space`) and `knn_full` (TFDS ImageNet under
   `_KNN_TFDS_DATA_DIRS`, all four entries `gs://`). Neither is reachable from
   a Borg task; the smoke does not cover them.
3. Whether `tpu queue`'s double-submit or the PENDING/preemption cycle needs an
   explicit supervisor for a 57-hour run.
