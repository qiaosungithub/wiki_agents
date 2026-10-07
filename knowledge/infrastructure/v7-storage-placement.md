# Where v7 Can Run With Storage Next To It

Owns the choice of metro for a v7 run, and the survey behind it. [knowledge/infrastructure/storage.md](storage.md)
owns why co-location matters and how quota is charged. Read this before pinning a
cell. **Re-run the survey rather than trusting a row below**: obtainability moves
daily and the v7 fleet is still turning up. Delete this file once the placement
is settled and recorded in the project guide. How to re-run the survey is
[unschedulable-job skill §How To Regenerate The v7 Placement Survey](../../harness/skills/unschedulable-job/SKILL.md#how-to-regenerate-the-v7-placement-survey) in the
[unschedulable-job](../../harness/skills/unschedulable-job/SKILL.md) skill.

## The Standing Decision: Four Full Data Metros (+ two partial)

**The full mirror set is `cbf`, `tul`, `lpp`, `dfw`: four metros** (was three;
`dfw` added to unlock cheap v4). Two more carry PARTIAL mirrors and are not full:
`las` (the maze v4 working set) and `sin` (the four GPU/B200-line corpora). Each
was chosen on live obtainability, storage headroom and a verified smoke,
weighting *breadth of cells*: a one-cell metro is one stockout from useless.

| metro | v-family | v7 cells live | storage cell | smoke | role |
|---|---|---|---|---|---|
| `cbf` | v7 | `yucbfiv`, `yucbful`, `yucbfwv`, `je`, `yucbfrl` | `is-d` 67.3 PiB sp50 | completed 12/12 | primary; the only metro with cell redundancy, and the generation source |
| `tul` | v7 | `yutulpz`, `nl`, `nk` | `oi-d` 31.4 PiB (nm-d's quota is FULL, see below) | scheduled, 8 tasks | second NA metro; existing `jax_llava` work sits here |
| `lpp` | v7 | `yulpptr` | `li-d` 85.6 PiB sp50 | ran to step 6 | European leg; largest storage of the three originals |
| `dfw` | v4 | `yudfwra` | `rs-d` 45.0 PiB sp50 | loader-resolve + read PASS | 4th FULL mirror (all 16 datasets). v4 is ~8x cheaper/chip than v7; ckpt bucket `_CELL_BUCKETS['yudfwra']` → rs-d |
| `las` | v4 | `dl` | `dl-d` 32.0 PiB sp10 | loader-resolve + read PASS | PARTIAL: only the maze v4 working set (64x64-offline + companions + settingA/B), NOT settingB_v3 / 128x128. Non-oversold fallback when `dfw` v4 fragments. ckpt bucket `dl` → dl-d |
| `sin` | B200 + v7 | `sk`, `sn`, `so` (v7); `sj` (B200) | `si-d` 9.25 PiB sp50 | completed 12/12; crc32c mirror verified | PARTIAL: the only metro with B200 compute next to data. Holds ARC-1, ARC-2, parcae (`strict-4d1138c` + `nobos` + eval-assets), codi/`coconut_data`; NOT the maze or VLM sets |

**`las`/`dl-d` and `sin`/`si-d` are partial mirrors, so do not assume a dataset
is there.** `las` holds maze64's v4 working set. `sin` holds only the four
GPU-line corpora above, and has ARC-1 *and* ARC-2, where `las` and `dfw` carry
ARC-1 only. [storage-operations skill §Existence Is Not Completeness](../../harness/skills/storage-operations/SKILL.md#existence-is-not-completeness) applies: check the
dataset's `_MIRRORED`/`_SUCCESS` on the cell before pinning a job there.
`dfw`/`rs-d` is the complete 4th mirror.

Naming trap for `las`: only `dl-d` is the true `las` storage cell. `la-d`/`lb-d`
resolve to `lpp`, and `mg-d` (looks like `cmh`) is `ckv`. Verify any new cell with
`mach_locality -k metro <cell>` before trusting its name.

`sin` is the B200 metro, and `sj`, the only cell with B200s in quantity, has ZERO
storage registrations of its own. A B200 job therefore reads a sibling cell, and
the mirror map must name it; unlisted, it falls to the far default, the
pruner-kill case.
`si-d` is that sibling: of the nine registered `sin` storage cells it has both
the most free space and an sp50 spindle commitment, 3.3x the runner-up's free
space. Do not pick storage by campus adjacency to the compute. `sj` sits on
campus `lyw` and `si-d` on `wen`, but metro is the boundary that matters, and
same-metro cross-campus reads are free. The campus-mate (`sh-d`, sp10) would
trade a 5x lower throughput floor for nothing.

Live chip and slice counts are not repeated here; the survey table below owns
them, and they move daily.

`tul` writes to `oi-d`, NOT `nm-d`. `nm-d`'s group quota
(`deepmind-resources-colossus`) hit its ceiling (47.9P/48.2P), poisoning every
write with `over Colossus bytes HDD quota`. The fix was to point `tul`'s bucket
at `oi-d`, the same-metro sibling with headroom, not to abandon `tul`. The swap
is lossless: same-metro cross-cell reads are free. When a metro's storage
cell fills, look for a second cell in the same metro before rejecting the compute
([storage-operations skill §An Over-Quota Cell Looks Like A Broken Program](../../harness/skills/storage-operations/SKILL.md#an-over-quota-cell-looks-like-a-broken-program)). Verify with `fileutil quota
deepmind-resources-colossus <cell>` (the bill goes to the GROUP, so query the
group, not your username) and a write probe.

Rejected, with the reason, so this is not re-litigated:

| Rejected | Why |
|---|---|
| `ske`, `kul`, `phx` | Most chips of all, zero team storage. Compute without co-located storage is the pruner-kill case. |
| `grq` / `el` | The best storage anywhere (`el-d`, same cell as the chips; see the survey table), but obtainability swung 0 -> 937 in a day. A single cell that thin cannot be a primary. |
| ~~`sin`~~ | No longer rejected; now a PARTIAL data metro (`si-d`), stood up as the only metro with B200 compute. Its storage is the thinnest of any candidate (9.25 PiB), so it carries the GPU-line corpora, not a full mirror. See the standing-decision table above. |
| `ckv` | Good storage; obtainability has since recovered from zero (2398 on a later sample), so re-check rather than treat the rejection as settled. |
| ~~`dfw`~~ | No longer rejected; now the 4th FULL data metro (`rs-d`), stood up for cheap v4. See the standing-decision table above. |

The launcher's `_CELL_BUCKETS` maps every v7 cell to a same-metro bucket, so
`--cell=<v7 cell>` alone picks the right storage and prints the choice at
launch.

## Two Rules The Survey Established

**Ask the question at METRO granularity, not per cell**: "does this cell's METRO
contain a storage cell with quota", never "does this TPU cell have storage
quota". A metro holds several cells and same-metro cross-cell reads are free, so
the metro decides co-location; [knowledge/infrastructure/storage.md](storage.md) owns the general statement. Asked
narrowly, it once produced a plan built on "v7 exists only in `ske`", when v7
spans 20 cells in 14 metros, 10 already holding PiB-scale quota. Move the compute
rather than requesting quota.

**Obtainability, not the quota table, decides whether a job starts, and it
inverts the storage ranking** ([knowledge/infrastructure/cluster-jobs.md](cluster-jobs.md) states this generally). The
group-level `tpu quota` view showed v7 fully consumed (477/477) while preflight
reported ~50k chips obtainable across 10 cells. `el`, the best storage answer,
had zero obtainable chips; middling `cbf` and `sin` each ran a job to completion.
Re-run preflight before committing, and prefer a metro good on both axes over the
best on either.

`sp<N>` in these tables is the spindle commitment. `sp0` means no throughput
floor, the condition behind a 12-hour collapse recorded in [archive/audits/](../../archive/audits/).

## Last survey, for shape only — re-run before relying on it

Group `deepmind-resources-colossus`; storage is the largest same-metro cell.
`obtainable` is one sample of PROD availability for the team alloc, and `free
v7-32` one sample of contiguous `2_4_4` slices (step 4b of [unschedulable-job skill §How To Regenerate The v7 Placement Survey](../../harness/skills/unschedulable-job/SKILL.md#how-to-regenerate-the-v7-placement-survey)). Both move daily; the
storage column is the slow one. Smokes are not repeated per row:
`cbf` and `sin` completed 12/12, `tul` was scheduled, `lpp` and `mrn` ran to step
6, no other metro has been smoked.

| metro | GCP region | v7 cells (obtainable chips) | Σ obtainable | free v7-32 slices | largest same-metro team storage |
|---|---|---|---:|---:|---|
| `ske` | *(none)* | `yuskedq`(17646) | 17646 | 164 | none |
| `kul` | *(none)* | `yukulwh`(14158) | 14158 | 341 | none |
| `cbf` | us-central1 | `yucbful`(4024) `yucbfiv`(4003) `yucbfwv`(2314) `je`(2028) `yucbfrl`(84) | 12453 | 43 | `is-d` 67.3 PiB sp50, `jq-d` 23.8 PiB sp10 |
| `phx` | us-west8 | `yuphxrp`(7344) | 7344 | 6 | none team-wide (only `yuphxrp-d` 500 TiB sp20) |
| `sin` | asia-southeast1 | `sk`(4048) `so`(2530) `sn`(662) | 7240 | 121 | `si-d` 9.25 PiB sp50, `sm-d` 1.57 PiB sp50 (9 registered cells in all — enumerate, do not guess) |
| `dfw` | us-south1 | `yudfwra`(2885) | 2885 | 11 | `rs-d` 45.0 PiB sp50, `rw-d` 5.12 PiB sp20 |
| `lpp` | europe-north1 | `yulpptr`(2612) | 2612 | 34 | `li-d` 85.6 PiB sp50, `lu-d` 91.8 PiB sp50 |
| `ckv` | *(none)* | `mb`(2398) | 2398 | 21 | `mg-d` 71.0 PiB sp10, `me-d` 29.6 PiB sp20 |
| `tul` | us-central2 | `yutulpz`(2004) | 2004 | **1** | `nm-d` 57.2 PiB sp50, `oi-d` 31.4 PiB sp50 |
| `mrn` | *(none)* | `yumrnel`(1168) | 1168 | 67 | `qo-d` 9.71 PiB sp50, `qr-d` 0.14 PiB sp0 |
| `uos` | us-east7 | `gc`(960) | 960 | 14 | `gd-d` 22.7 PiB sp10, `ge-d` 17.3 PiB sp1 |
| `grq` | europe-west4 | `el`(915) | 915 | 13 | `el-d` 94.2 PiB sp50, `ej-d` 11.8 PiB sp50 |
| `lhr` | europe-west2 | `yulhrp`(154) | 154 | 3 | none team-wide (only `yulhrp-d` 500 TiB sp20) |
| `atl` | us-east2 | `yo`(112) | 112 | 0 | `yo-d` 64.7 PiB sp500, `ym-d` 6.56 PiB sp50 |

Storage ceilings above were read together on 2026-08-31 with `flex.par ls
--group=deepmind-resources-colossus --service=colossus`, so they are one
snapshot rather than a stitched history. They move by a few PiB a month; re-read
them rather than quoting these.

A chip count cannot see fragmentation, so read the slice column beside it. `tul`
carries thousands of obtainable chips and, on this sample, exactly ONE placeable
v7-32: rich in chips, unable to start your job. That is the green-preflight then
allocator-reject failure [knowledge/infrastructure/cluster-jobs.md](cluster-jobs.md) describes. `atl` is the mirror case, the
deepest spindle commitment anywhere (sp500) with almost no chips.
