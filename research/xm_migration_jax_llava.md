# Migrating `jax_llava` To XM/Borg Infra

Living progress file for the "run jax_llava on xm infra and reproduce the
result" program. Owns the plan, the decisions, and what is verified vs assumed.
Delete or fold into a project guide once the migration lands.

## Goal

Run `jax_llava` (the simpler prototype: stage-1 cc12m pretrain, then stage-2 SFT)
on Borg via `tpu queue` / `xm_launcher.py`, reading data from CNS, and reproduce
the existing kmh-infra result. Code changes go on a branch named
`<current-branch>_xm`.

## Verified Facts

**Data reachability.** `gs://kmh-gcp-*` is unreachable from Borg. In google3,
`gs://` is rewritten to `/bigstore/` (`third_party/py/etils/epath/gpath.py:33`)
and the job's principal is `<user>@prod.google.com`; the kmh buckets 403 even
for `<user>@google.com` from the workstation. The existing pipeline additionally
opens shards through `fsspec`/`gcsfs` (`input_pipeline.py: register_gcsfs`),
which needs ADC and public egress -- neither exists on a Borg task. So the data
must be re-materialized on CNS; there is no credential trick that avoids it.

**The workstation has no kmh NFS mount.** `/kmh-nfs-ssd-us-mount` does not
exist here. Anything the old scripts read from NFS is not reachable from this
machine, and the upload toolkit's TPU-VM/SSH launch model does not apply.

**cc12m IS reproducible -- via the recap dataset's own declared source.** An
earlier reading of `data_upload/datasets.json` (`enabled: false`,
`safety: external-provenance`) led me to call cc12m unreproducible. That is
wrong, and the correction matters. The catalog's `metadata_source`,
`CaptionEmporium/conceptual-captions-cc12m-llavanext`, states in its own README:
"In the interest of reproducibility, an archive found here on Huggingface was
used (cc12m-wds)." So the chain closes:

- images = HF `pixparse/cc12m-wds`, a STATIC archive (996 tars, 504.1 GiB) with
  no link rot;
- captions = the recap `train.jsonl.gz`, joined on the 9-digit `key`, field
  `caption_llava` (long) / `caption_llava_short`.

What is unreproducible is only kmh's own copy, because kmh took that metadata
and RE-CRAWLED the URLs with img2dataset -- which is why it lands at 62-66%
success. Recorded kmh sanity numbers: 10,968,539 metadata rows, 1097 shards,
6.80M-7.25M successes per region, 1545-1656 GiB per region, ~227-234 KiB/sample,
original resolution (`resize_mode=no`).

**A pre-crawled WDS mirror exists.** HF `pixparse/cc12m-wds`: 996 tars,
504.1 GiB total, plus `_info.json`. Downloading this is a file transfer, not a
crawl, so it is reproducible and ~3x smaller than a regional kmh copy. It is a
DIFFERENT dataset from the kmh one (different crawl, and its captions are the
ORIGINAL CC12M alt-text, not the LLaVA-NeXT recaption) -- see Open Questions.

## Cross-Region Cost: The Rule And The Trap

The operator pays for egress out of his own external GCP project, so a
cross-region read is a real bill, not a slowdown. Treat every copy as
same-region-or-abort.

**Do not trust an LLM's claim that internal `/bigstore` reads are exempt from
egress billing.** That claim was offered and is plausible, but a wrong negative
here costs money. Design as if egress is always billed, and make it $0 by
staying physically in one region.

**metro <-> GCP region, verified from google3 source** (six independent files
agree; this is NOT an LLM answer):
`//depot/google3/production/borg/cloud_iam/slicer_regions/slicer_metros.pi`
lines 9 and 12, plus
`//depot/google3/net/fabric/monitoring/cloud_sdn_management/ai/artifacts/location_mapping.csv`.

| metro | GCP region |
|---|---|
| `cbf` | `us-central1` (Iowa) |
| `cmh` | `us-east5` (Columbus) |
| `tul` | **none** -- Tulsa maps to no GCP region |

**The trap: the launcher's default is cross-region.** `xm_launcher.py` defaults
to `/cns/yutulpz-d/...`, which is metro `tul`. Copying a kmh bucket there is a
cross-region transfer of the whole payload. Every job in this program must pin
its cell and its CNS root explicitly; never accept the default.

**The constraint is three-way**, because the training job re-reads the data:
bucket region == CNS cell metro == Borg cell metro. Satisfying only two of the
three still pays.

Verified cells, `mach_locality -b -k metro <cell>` plus a live `fileutil ls`:

| GCP region | metro | CNS cell | Borg cell |
|---|---|---|---|
| `us-east5` | `cmh` | `/cns/go-d/` (OK) | `go` |
| `us-central1` | `cbf` | `/cns/nz-d/`, `/cns/yucbfpv-d/` (OK) | `yucbfpv`, `yucbfrl` |

**Stage 1 only consumes a fraction of cc12m.** `remote_run_config.yml`:
`stage1_steps: 2180`, `batch_size: 256` -> 558,080 samples, about 8% of one
region's ~6.8M successes. At ~230 KiB/sample that is roughly 125 GiB of shards
actually touched, not 1.5 TiB.

**CNS is the only durable store the job can use, and it has no floor.** Prior
audit (`archive/audits/20260801-cns-yutulpz-spindle-starvation.md`): no spindle
commitment, so a neighbouring workload on the same D cell dropped throughput
9.63 -> 0.04 MiB/s for 12+ h. Cost is per-operation, so large sequential WDS
shard reads are the favourable access pattern (the >64 KiB bucket degraded 3x
where the 0-16 KiB bucket degraded 14x), but there is no guarantee.

**Compute/storage co-location is enforced by the launcher.** `xm_launcher.py`
maps cell -> same-metro CNS bucket (`_CELL_BUCKETS`); a mismatch previously
caused a pruner kill (XID 275990419). Data placement must follow the same map.

## Decisions Taken

**Region: `us-east5` / metro `cmh` / Borg cell `go` / CNS `/cns/go-d/home/qiaos/`.**
Chosen on live market data (`tpu route`), for emptiness at equal price.

The PROD tier is useless here: every PROD candidate is YELLOW and sits in the
wrong metro (`yuphxrp`=phx, `yulhrp`=**lhr, Europe**, `rs`=dfw, `ej`=**grq,
Europe**). The BATCH tier, by contrast, lands exactly in the two metros we need:

| cell | metro | region | type | obtainable | price | status |
|---|---|---|---|---|---|---|
| `go` | cmh | us-east5 | v5p-64 | **2181 (34x)** | 0.00 | GREEN |
| `yucbfpv` | cbf | us-central1 | v6p-16 | 291 (18x) | 0.00 | GREEN |
| `yucbfrl` | cbf | us-central1 | v6e-32 | 372 (11x) | 0.16 | GREEN |

`go` has ~7.5x the obtainable chips at the same zero price; the only priced
option is on the cbf side. **v7 has no BATCH supply** -- asking for `v7-16`
makes the router fall back to v5p/v6p, and the only v7 offer (`yuphxrp`, phx) is
both YELLOW and in the wrong metro. us-central1/cbf is kept as the fallback
region, fully mapped above.

Caveat to carry into the training phase: BATCH is reclaimed first, so a long run
needs an explicit scheduling policy (`jobs.md`). Fine for restartable copy jobs.

**Scope: stage 1 only** (cc12m pretrain), one region, one copy. Stage 2 deferred.

**Payload: the first 150 tar shards, 199.2 GiB** (measured with
`gcloud storage ls -l`, avg 1.33 GiB/shard), not the full 1545.1 GiB. Stage 1 is
`stage1_steps: 2180` x `batch_size: 256` = 558,080 samples, roughly 8% of a
region's ~6.8M successes (~125 GiB), so 150 shards leaves headroom and still
copies 8x less than the full set -- which matters because hop 2 replicates it
again.

**Two-hop copy, so the paid boundary stays inside one region:**

| hop | path | crosses the user's GCP egress? | cost |
|---|---|---|---|
| 1 | `gs://kmh-gcp-us-east5` -> `/cns/go-d` (both metro `cmh`) | same-region only | $0 |
| 2 | `/cns/go-d` -> `/cns/yuphxrp-d` | no -- pure internal network | $0 |

Hop 1 MUST be initiated from a task in metro `cmh`. Letting a job in the
destination metro pull directly from the bucket is exactly the cross-region read
that bills.

**Hop-2 destination: `/cns/yuphxrp-d/home/qiaos/` (metro `phx`, us-west8).**

> **Superseded on the v7 claim.** "`phx` is the only place v7 exists" was an
> artefact of reading the market table's *sample* cells instead of the full
> cache: v7 is in 17 cells across 12 metros, and `phx` is one of the four with
> **no** team storage quota. If this hop is redone, pick a metro that has both
> -- see `v7_storage_placement.md`. The cost reasoning below still holds.

Full v6p/v7 market scan:

| type | tier | cell | metro | region | obtainable | price |
|---|---|---|---|---|---|---|
| v7-16 | PROD | `yuphxrp` | phx | us-west8 | quota 384, headroom **0** | 0.00 |
| v6p-16/64/256 | PROD | `yulhrp` | lhr | **europe-west2** | 0 | 49.92 |
| v6p-256 | BATCH | `yuchspe` | chs | us-east1 | 953 (3x) | 0.00 |
| v6e-32/128 | BATCH | `yucbfrl` | cbf | us-central1 | 2173 (67x) | 0.15 |

Two caveats the table hides: **v6p and v7 are in different metros**, so one data
replica cannot serve both -- PROD v6p is only in Europe, and a third replica in
`chs` would be needed for the free BATCH v6p-256. And **v7 headroom is currently
0**, so the data can be staged there before the chips are actually obtainable.
`/cns/yuphxrp-d` verified reachable.

The scan above lists one cell per accelerator because it came from the market
summary table. **That table samples; it does not enumerate.** Read
`~/.tpu_quota_cache_dir/market.json` for the full cell list before concluding
anything about where an accelerator does or does not exist.

**The 500 GiB personal ceiling no longer binds: `/cns/go-d/home/qiaos` is now
charged to `deepmind-resources-colossus`.** Membership was proven by the
filesystem itself -- `chstat` accepts that group while rejecting `youtube-eng`
and `search-eng` with an explicit *"qiaos is not a member of"*, so the accept is
a real permission check, not a silent no-op. The whole home directory was set
recursively and new subdirectories and files inherit it, verified by `stat`; the
copy and training code needs no change. Group headroom in the cells that matter:
`go-d` 20.74 / 26.15 PiB used, `nz-d` 8.00 / 14.06 PiB, `yutulpz-d` 724 GiB /
100 TiB; `yucbfpv-d` has no record. A 199 GiB payload at 3x replication is
~0.01% of the `go-d` pool, so default `r=3.2` is now acceptable and Reed-Solomon
is an optimisation rather than a prerequisite.

**Per-user quota records were absent in `go-d` and `nz-d`** while writes still
succeeded. That is moot for capacity now, but it still signals no spindle
commitment, so watch throughput during the first real copy rather than assuming
it scales.

**Branches:** `sqa.late_fusion_xm` in `jax_llava`, `data_upload_xm` in
`paligemma-data-upload`.

## Open Questions

1. Does the PROD identity (`qiaos@prod.google.com`) actually reach the kmh
   bucket through `/bigstore`? Both grants are in place and the workstation
   (corp identity) can now list `gs://kmh-gcp-us-east5/data/cc12m/`, but the
   prod identity cannot be tested from here -- only from a Borg job.
2. If A works, is a same-metro `/bigstore` -> CNS copy actually free? Assume not;
   the same-region design makes it moot.
3. Do `jax_llava`'s deps (`torch`, `torchdata==0.8.0`, `webdataset`, `fsspec`,
   `transformers`, `pycocotools`) exist as google3 targets under the mandatory
   `PACKAGE_MODE=bazel`? If the loader must be rewritten, that dwarfs the data
   problem and reorders the whole plan.

## Plan

Ordered so the cheapest thing that can fail, fails first.

1. **Probe (IN FLIGHT, session `breezy-cat`).** CPU-only Borg job pinned to cell
   `go`, reading exactly one few-KB object
   (`gs://kmh-gcp-us-east5/data/cc12m/00000_stats.json`) through `/bigstore`, and
   writing a marker to `/cns/go-d/home/qiaos/probe/`. Carries a fail-closed guard
   that aborts before any read unless the task's metro is `cmh`. Answers Open
   Question 1 for a few KB. No `.tar` may be read.
2. **Dependency feasibility** (Open Question 3), in parallel: can the binary be
   built with Bazel and survive `--help` on Borg?
3. Decide A (kmh -> CNS same-metro copy) vs B (rebuild from HF pixparse + recap
   join). A is ~1.5 TiB over internal network; B is 504 GiB over public egress
   but needs no kmh access. Probe result decides.
4. Copy ONE shard, measure, verify, then scale out. Copy jobs are Borg jobs, not
   workstation jobs -- local bandwidth is the wrong resource.
5. Port the loader: replace the `gcsfs` `gopen_schemes["gs"]` hook with a
   CNS/`epath` opener; keep the fail-closed locality guard but teach it cells.
6. Swap WandB for the internal metric writer (`research/result_logging.md`).
7. Stage-1 smoke on a small slice, then the real run.

## Operational Rules For This Program

- **Never accept the launcher's default CNS root.** Pin `--cell` and the CNS
  path together, every time.
- **The metro guard belongs in the code, fail-closed**, not in a human's memory:
  assert the task's metro matches the bucket's region before the first read.
- Read metadata (list, stat) freely; those are metadata ops. Bytes are the thing
  that costs.
- `/tmp` on a Borg task is a RAM disk sized by `--tmp_ram_fs_gib` (default 16
  GiB in this launcher), and every task stages its own copy. WDS is a sequential
  streaming read and needs no full-shard spool; only tokenizer/CLIP weights need
  fast local access, and those are better baked into the Bazel package.

## Full cc12m: Three Regional Copies, No Cross-Region Byte

**Decision: mirror into `cbf`, `tul`, `lpp`** -- the metros picked in
`v7_storage_placement.md`. Stage 1 is being reproduced for real, so the 150-shard
slice is retired in favour of the full 1097 shards.

**The bucket owner's regions line up with two of the three metros, so hop 1 is
free by construction and not by care:**

| metro | GCP region | source bucket (same region) | CNS destination |
|---|---|---|---|
| `cbf` | us-central1 | `gs://kmh-gcp-us-central1` | `/cns/is-d/home/qiaos/data/cc12m` |
| `tul` | us-central2 | `gs://kmh-gcp-us-central2` | `/cns/nm-d/home/qiaos/data/cc12m` |
| `lpp` | europe-north1 | **none** | `/cns/li-d/...` -- must come CNS->CNS |

Each regional bucket holds 1097 tars + 1097 `_stats.json`; payload measured at
1.52 TiB (us-central1) and 1.62 TiB (us-central2). At `rs=9.4` (1.4505x) that
is ~2.2 and ~2.4 TiB of disk against 12.0 and 11.8 PiB of free group quota --
not a constraint. `lpp` has no regional bucket, so it is fed by a CNS-to-CNS
hop, which is internal network and free.

**The copier is `cc12m_full`, a destination-table version of `cc12m_copy`.**
The original hard-coded bucket, region, cell, metro and path as constants,
reasoning that a flag is a way to read the wrong thing. That reasoning survives:
the new `--dest` selects a whole ROW, and a row fixes all five together, so no
combination of flags can express a cross-region pair. `--num_shards` below the
full count marks the copy partial and suppresses `_SUCCESS`, so a smoke can
never be mistaken for a complete dataset.

All three reject branches were exercised locally before submitting: wrong cell
(`BORG_CELL=yuskedq` against `dest=cbf`), unreadable cell (no `BORG_CELL`), and
a faked bucket location (`--test_force_bucket_region=us-east5`) -- each aborts
before any open. The guard also proved it reads the LIVE bucket location rather
than trusting the name.

**`tpu queue` needed a passthrough channel.** Its parser is an allowlist, which
is correct -- a mistyped flag should be refused, not silently dropped on Borg --
but it cannot know every packaged binary's flags. Added `--app.<flag>=<v>`,
which forwards one named flag verbatim; a typo in a *wrapper* flag still errors.

**Preflight cannot verdict a CPU-only job** (`Unknown accelerator arch 'cpu'`),
so copy jobs submit with `--skip-preflight`. That is not a warning being
ignored: preflight only models TPU allocations.

### Result: cbf and tul hold the full dataset (2026-08-05)

| | `is-d` (cbf) | `nm-d` (tul) |
|---|---|---|
| objects | **2194 / 2194 verified**, `objects_bad: []` | **2194 / 2194 verified**, `objects_bad: []` |
| payload | 1.52 TiB | 1.62 TiB |
| encoding | `rs=9.4` on every sampled shard | `rs=9.4` |
| charged to | `deepmind-resources-colossus` | same |
| throughput | 81 MiB/s (5.4 h) | 129 MiB/s (3.7 h) |
| `_SUCCESS` | written, carries the guard's proof | written |

**The personal quota was never touched**: `fileutil quota qiaos is-d` answers
*no such user in cell*, which is the strongest possible confirmation that every
byte landed on the group. Each `_SUCCESS` records `bucket_region_proved_by:
live bigstore metadata`, so same-region is evidenced per run rather than
assumed.

`lpp` completed too (XID 277230370): **2196/2196 verified, `objects_bad: []`,
1.52 TiB, `rs=9.4`, group-charged, `bigstore_paths_used: 0`**, with each end's
metro proved by a live lookup. Its `_SUCCESS` reports only 65 s of wall time
because the task had restarted: `{copied: 8, skipped_already_correct: 2188}`.
That is the `.inflight`-plus-size-check design working as intended -- a resumed
run re-verifies every object and re-copies only what is missing -- but it does
mean **wall time in a resumed run is not the transfer cost**; read
`bytes_copied_this_run` instead.

All three replicas now agree at 1097 tars each (1.52 / 1.62 / 1.52 TiB; tul
differs because its bucket holds a different crawl). `fileutil quota qiaos
<cell>` answers *no such user* in all three, so no byte landed on a personal
ceiling anywhere.

That hop is
**deliberately cross-metro** and safe on cost alone: both ends are internal
Colossus, so nothing is billed however far apart they are. The predecessor
asserted `src.metro == dst.metro == <one literal>`, which is right for a copy
meant to stay local and wrong here -- it would reject the intended transfer. The
guard was therefore restated rather than relaxed: **each end is pinned to its
own named metro**, both queried live, and the compute cell must sit with the
SOURCE because that is the leg read shard by shard. Both reject branches were
exercised locally before submitting.

### Two Traps The Smoke Caught, Which A Direct Full Run Would Not Have

Worth keeping because both were invisible until a real file existed:

- **A copy does not inherit the destination directory's encoding.** The
  3-shard smoke landed `r=3.2` (3.02x) despite the directory being set up for
  it, because `gfile.Copy` needs the encoding named in its own options. On
  1097 shards that is 4.6 TiB instead of 2.2 TiB. The fix names it per file and
  then **reads it back**, since a cell may silently downgrade.
- **A directory created by the job does not inherit group accounting.** The
  copier's own `MakeDirs` created `data/cc12m` fresh, so the shards were
  charged to the 500 GiB personal ceiling and would have died about a third of
  the way in. Setting `quota_accounting` on the *home root* recursively fixes
  both the existing files and everything created later.

The general lesson is the one already in `../storage.md`: verify the property on
a real object, never on the request that was supposed to produce it.

### Watching A Long Job: Match The Status Column, And Self-Test The Matcher

Two false "it finished" reports came from the watcher script, not the jobs, and
both were avoidable:

- **`tpu check` prints `XID STATUS NAME`.** A pattern like `<name>.*running`
  can never match, so the watcher concluded "not running" on its first poll and
  fired immediately. Match the status *before* the name.
- **The status vocabulary is wider than the common cases**: `SUBMITTED` and
  `unknown` both appear before `running`, so a matcher listing only
  `running|starting|PENDING` reports a just-launched job as finished.

The habit that catches both: **run the matcher against real current output and
assert the count you expect before trusting the watcher.** One command, and it
converts "the script looks right" into "the script agrees with reality".
Copying a watcher for a second job also needs its labels and paths updated, or
it reports the previous job's cells under the new job's name.

## Correction: The Regional Buckets Are Different Datasets, Not Replicas

**The three `kmh-gcp-us-*` buckets hold three independent crawls.** The same
shard index differs in size across them -- `00000.tar` is 943,411,200 bytes in
`us-east5`, 1,584,363,520 in `us-central1` and 1,682,739,200 in `us-central2`.
This follows directly from a fact already recorded above (kmh RE-CRAWLED the
metadata with img2dataset, landing at 62-66% success), but it was not carried
through when choosing where to copy from.

Sourcing each metro from its own same-region bucket therefore produced **three
different datasets**, which makes a loss curve in one metro incomparable to
another -- the exact property a reproduction must not lose. Verify sameness by
comparing a shard's size across buckets before assuming a bucket is a replica.

**The corrected shape is the two-hop one, and it was the instruction all
along:**

```
hop 1   gs://kmh-gcp-us-east5  ->  /cns/go-d      same region (cmh), $0
hop 2   /cns/go-d              ->  is-d/nm-d/li-d CNS->CNS, internal, $0
```

Hop 2 is deliberately cross-metro and costs nothing because both ends are
internal Colossus -- proven on the earlier lpp leg, whose `_SUCCESS` recorded
`bigstore_paths_used: 0`. **A same-region bucket read is not the only free
option, and picking a bucket per metro to chase "same region" trades dataset
identity for a saving that CNS-to-CNS already provides.**

The wrong replicas were deleted from `is-d`, `nm-d` and `li-d`, and all three
are being refilled from the single `go-d` copy of the us-east5 crawl. Each
fan-out binary pins compute to `go` (with the SOURCE, the leg read shard by
shard), asserts `src.metro == cmh` and `dst.metro == <its own literal>`, both
queried live; all three reject branches were exercised before submitting.

### Done: One Crawl, Three Metros, Byte-Identical (2026-08-06)

`gs://kmh-gcp-us-east5` -> `/cns/go-d` (same region, $0) -> `is-d` / `nm-d` /
`li-d` (CNS-to-CNS, internal, $0). Every replica now carries the SAME crawl.

| | go-d (cmh) | is-d (cbf) | nm-d (tul) | li-d (lpp) |
|---|---|---|---|---|
| tars | 1097 | 1097 | 1097 | 1097 |
| payload | 1.5044 TiB | 1.5044 | 1.5044 | 1.5044 |
| verified | 2194/2194 | 2196/2196 | 2196/2196 | 2196/2196 |
| `bigstore_paths_used` | n/a | 0 | 0 | 0 |
| throughput | 120 MiB/s | 878 | 647 | 303 |

**Identity was checked per object, not per total.** All 2194 names were
compared against `go-d` with their sizes: zero missing, zero extra, zero size
mismatch, on all three. Equal totals would not have proved this -- three
different crawls can sum to similar numbers.

All three are `rs=9.4`, charged to `deepmind-resources-colossus`, and
`fileutil quota qiaos <cell>` still answers *no such user* in every one.

Note the throughput spread on an identical payload out of one source: 878 / 647
/ 303 MiB/s to cbf / tul / lpp. Distance shows up, but even the European leg
beat the 120 MiB/s bigstore read -- **CNS-to-CNS is the fast leg as well as the
free one**, which is the second reason to prefer one crawl fanned out over
per-metro bucket reads.

### A Cached Job Status Stalled The Pipeline For An Hour

The `go-d` copy finished at 22:51 and wrote its `_SUCCESS`; `tpu check` still
reported `SUBMITTED` an hour later, while Borg had the work unit as
`BORG_STATE_SUCCESS`. An orchestrator waiting for the status to change waited
for nothing.

**For a copy, completion is a property of the filesystem, not of the scheduler.**
Gate on the artifacts -- expected object count plus the completion marker --
and the answer is both correct and available the instant it becomes true. Job
status is a convenience view with a cache behind it; `deep_probe` on the XID
gives the authoritative state when it is genuinely needed.

## Eval Bundle: The Same Two-Hop Shape

Every dataset any `jax_llava` config enables, taken from the **same us-east5
crawl** as cc12m and fanned out to the same three metros. The union across all
configs is 19 eval tasks, which reduce to 13 source prefixes:

`vqav2`, `mme`, `textvqa`, `pope`, `coco/train2014` (refcocog images),
`eval/pixelbench` (this one bundle supplies `mmvp`, `vstar`, `ocrbench` and
`countbenchqa`), plus `gqa-balanced`, `seed-bench-image`, `cambrian-cvbench`,
`vlms-are-blind`, `docvqa`, `realworldqa` under `vlm_eval_benchmarks/`, and
`tensorflow_datasets/imagenet2012` for `knn_full` / `knn_partial`.

Sizes: ~27 GiB for the benchmarks, **143 GiB for TFDS ImageNet**, so KNN
dominates the bundle. Total ~170 GiB, about a ninth of cc12m.

Two structural differences from the cc12m copier, both of which change how
completeness is judged:

- **The bundle is a nested tree, not a flat numbered shard set.** Members are
  discovered by walking each prefix, and an empty prefix is a hard abort --
  otherwise a `_SUCCESS` could cover a bundle that silently omits a dataset
  some eval config enables. Destination paths mirror the bucket layout, so a
  config only has to swap the root.
- **"Partial" is a cap on object count** (`--max_objects`), and any cap
  suppresses `_SUCCESS`, same contract as `--num_shards` had.

Nested output also means the parent directory of each object may not exist:
`MakeDirs` per file, idempotent.

### `gfile` Has No `ListRecursively`

The first attempt used it, failed on Borg with `AttributeError`, and produced a
work-unit status carrying no exception text at all -- a shape that reads like
the job vanished. **Running the staged binary locally named the missing
attribute in three seconds**, against roughly ten minutes per remote attempt.
The recursive walk is `gfile.Walk`, with `os.walk` semantics.

This is the case `../jobs.md` already describes: reproduce locally first,
because flags parse only after every import has run. Worth re-reading before
the next remote launch of new code -- the cost asymmetry is an order of
magnitude even when the bug is one line.

