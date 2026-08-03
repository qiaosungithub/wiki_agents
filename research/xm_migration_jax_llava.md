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

**Hop-2 destination: `/cns/yuphxrp-d/home/qiaos/` (metro `phx`, us-west8),
because that is the only place v7 exists.** Full v6p/v7 market scan:

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

**CNS quota records are absent in `go-d` and `nz-d`** (`fileutil quota qiaos
<cell>` reports no such user) while writes still succeed -- verified by writing a
28-byte file to `/cns/go-d/home/qiaos/probe/`. Only `yutulpz-d` has a record
(39.77 GiB used, effectively unlimited limit). Missing record != write blocked,
but it likely means no spindle commitment, so watch throughput during the first
real copy rather than assuming it scales.

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
