# Where v7 Can Run With Storage Next To It

Owns the choice of metro for a v7 run, and the survey that decides it.
`../storage.md` owns why co-location matters at all and how quota is charged.
Read this before pinning a cell; **re-run the survey rather than trusting a row
below** — obtainability moves daily, and the v7 fleet is still turning up.
Delete this file once the placement is settled and recorded in the project
guide.

## The Standing Decision: Four Full Data Metros (+ one partial)

**The full mirror set is now `cbf`, `tul`, `lpp`, `dfw` — four metros** (was
three: `dfw` was added to unlock cheap v4). A fifth, `las`, carries a PARTIAL
mirror (the maze v4 working set only, not every dataset). Each was chosen on the
intersection of live obtainability, storage headroom, and a verified smoke,
weighting *breadth of cells* because a metro with one cell is one stockout away
from useless.

| metro | v-family | v7 cells live | storage cell | smoke | role |
|---|---|---|---|---|---|
| **`cbf`** | v7 | `yucbfiv`, `yucbful`, `yucbfwv`, `je`, `yucbfrl` | `is-d` 68.1 PiB sp50 | completed 12/12 | **primary** — the only metro with cell redundancy; generation source |
| **`tul`** | v7 | `yutulpz`, `nl`, `nk` | **`oi-d` 29.6 PiB** (nm-d's quota is FULL — see below) | scheduled, 8 tasks | second NA metro; existing `jax_llava` work sits here |
| **`lpp`** | v7 | `yulpptr` | `li-d` 85.3 PiB sp50 | ran to step 6 | European leg; largest storage of the three originals |
| **`dfw`** | **v4** | `yudfwra` | `rs-d` 48.5 PiB sp50 | loader-resolve + read PASS | **4th FULL mirror** (all 16 datasets). v4 is ~8x cheaper/chip than v7; ckpt bucket `_CELL_BUCKETS['yudfwra']` → rs-d |
| `las` | **v4** | `dl` | `dl-d` 31.6 PiB sp10 | loader-resolve + read PASS | **PARTIAL** — only the maze v4 working set (64x64-offline + companions + settingA/B), NOT settingB_v3 / 128x128. Non-oversold fallback when `dfw` v4 fragments. ckpt bucket `dl` → dl-d |

**`las`/`dl-d` is a partial mirror — do not assume a dataset is there.** It holds
maze64's v4 working set only. `storage.md` §Existence Is Not Completeness applies:
check for the dataset's `_MIRRORED`/`_SUCCESS` on `dl-d` before pinning a job
there. `dfw`/`rs-d` is the complete 4th mirror.

**Naming trap for `las`:** only `dl-d` is the true `las` storage cell —
`la-d`/`lb-d` resolve to `lpp`, and `mg-d` (looks like `cmh`) is `ckv`. Verify
any new cell with `mach_locality -k metro <cell>` before trusting its name.

Live chip and slice counts are deliberately not repeated here — the survey table
below owns them, and they move daily.

**`tul` writes to `oi-d`, NOT `nm-d`.** A metro can hold several storage cells,
and `nm-d`'s group quota (`deepmind-resources-colossus`) filled to its ceiling
(47.9P/48.2P), poisoning every write with `over Colossus bytes HDD quota`. The
fix was NOT to abandon `tul` but to point its bucket at `oi-d`, the same-metro
sibling with headroom — a lossless swap, because same-metro cross-cell reads are
free. **When a metro's storage cell fills, check for a second cell in the same
metro before rejecting the compute** (`../storage.md` §An Over-Quota Cell). Verify
with `fileutil quota deepmind-resources-colossus <cell>` (the bill is charged to
the GROUP, so query the group, not your username) and a write probe.

Rejected, with the reason, so this is not re-litigated:

| Rejected | Why |
|---|---|
| `ske`, `kul`, `phx` | **Most chips of all, zero team storage.** Compute without co-located storage is the pruner-kill case. |
| `grq` / `el` | The best storage anywhere (95.7 PiB, same cell as the chips), but obtainability swung 0 -> 937 across a day. A single cell that thin cannot be a primary. |
| `sin` | Completed its smoke, but the thinnest storage of any candidate (under 10 PiB) and far from the others. |
| `ckv` | Good storage; obtainability has since recovered from zero (2398 on a later sample), so re-check rather than treating the rejection as settled. |
| ~~`dfw`~~ | **No longer rejected — now the 4th FULL data metro** (`rs-d`), stood up for cheap v4. See the standing-decision table above. |

**The launcher's `_CELL_BUCKETS` maps every v7 cell to a same-metro bucket**, so
`--cell=<v7 cell>` alone picks the right storage; it prints the choice at
launch, which is worth reading as confirmation.

## Two Rules The Survey Established

**Ask the question at METRO granularity, not per cell** — *"does this cell's
METRO contain a storage cell with quota"*, never *"does this TPU cell have
storage quota"*. A cell is one cluster, a metro holds several, and same-metro
cross-cell reads are effectively free, so the metro is the unit that decides
co-location; `../storage.md` owns the general statement. Asked narrowly, it
once produced a plan built on "v7 exists only in `ske`, so a new flex
registration there is the only way forward" — in fact v7 spans 20 cells in 14
metros, 10 of which already hold PiB-scale quota, and `ske` is one of only two
with nothing at all. **Move the compute, do not request the quota.**

**Obtainability, not the quota table, decides whether a job starts — and it
inverts the storage ranking** (`../jobs.md` states this generally). Here it
meant: the group-level `tpu quota` view showed v7 fully consumed (477/477) while
preflight reported ~50k chips obtainable across 10 cells, and `el`, the best
storage answer, had **zero** obtainable chips during the test while middling
`cbf` and `sin` each ran a job to completion. **Re-run preflight before
committing, and prefer a metro currently good on both axes over the best on
either.**

`sp<N>` in these tables is the spindle commitment: **`sp0` means no throughput
floor**, the condition behind a 12-hour collapse recorded in
`../archive/audits/`.

## How To Regenerate The Survey

1. **v7 cells** — read `~/.tpu_quota_cache_dir/market.json` under
   `prices.<pool>|<code>|PROD`, keyed by an internal card code (v7 was `101`;
   verify by checking a known v7 cell appears under it). The `tpu money` table
   prints only a few sample cells per card, so read the cache, not the table.
2. **Storage cells with a ceiling** — `flex.par ls --group=<accounting-group>
   --service=colossus` gives every registered cell with its disk ceiling and
   spindle commitment. This is authoritative; `fileutil quota` is not
   (`../storage.md`).
3. **Join on metro** — `mach_locality -k metro <cell>` for both sides;
   parallelise with `xargs -P`, it is one RPC per cell.
4. **Obtainable chips per cell** — `tpu preflight --tpu_type=v7-32 --group=<g>
   --json` returns a `cells_ok` list with an obtainable count each.

   **4b. Free contiguous slices per cell** — `stubby call
   master.<cell>.borg:9413 BorgMaster.ProbeSliceAvailability 'slices {
   locus_type: "locus:DEPLOYMENT_TYPE_GHOSTFISH_LITE:2_4_4" } priority: 200'`,
   summing `num_free_slices` over the pods. Reachable on an ordinary credential,
   one RPC per cell; the shape uses UNDERSCORES (`2x4x4` is rejected as an
   invalid locus). Do this one too — a metro can hold thousands of obtainable
   chips and **one** placeable v7-32.

5. **Confirm with a real job**, not just the numbers: submit the same smoke to
   each candidate metro. Checkpoints should land on CNS with
   `capacity_quota_user: deepmind-resources-colossus`, keeping the 500 GiB
   personal ceiling out of the picture.

### Last survey, for shape only — re-run before relying on it

Group `deepmind-resources-colossus`; storage is the largest same-metro cell.
`obtainable` is one sample of PROD availability for the team alloc, and `free
v7-32` one sample of contiguous `2_4_4` slices (step 4b). Both are
point-in-time and move daily — the storage column is the slow one. Smokes are
not repeated per row: `cbf` and `sin` completed 12/12, `tul` was scheduled,
`lpp` and `mrn` ran to step 6, and no other metro has been smoked.

| metro | GCP region | v7 cells (obtainable chips) | Σ obtainable | free v7-32 slices | largest same-metro team storage |
|---|---|---|---:|---:|---|
| `ske` | *(none)* | `yuskedq`(17646) | 17646 | 164 | **none** |
| `kul` | *(none)* | `yukulwh`(14158) | 14158 | 341 | **none** |
| `cbf` | us-central1 | `yucbful`(4024) `yucbfiv`(4003) `yucbfwv`(2314) `je`(2028) `yucbfrl`(84) | 12453 | 43 | `is-d` 68.1 PiB sp50, `jq-d` 18.9 PiB sp10 |
| `phx` | us-west8 | `yuphxrp`(7344) | 7344 | 6 | **none team-wide** (only `yuphxrp-d` 500 TiB sp20) |
| `sin` | asia-southeast1 | `sk`(4048) `so`(2530) `sn`(662) | 7240 | 121 | `si-d` 9.5 PiB sp50, `sm-d` 1.67 PiB sp50 |
| `dfw` | us-south1 | `yudfwra`(2885) | 2885 | 11 | `rs-d` 49.3 PiB sp50, `rw-d` 4.94 PiB sp20 |
| `lpp` | europe-north1 | `yulpptr`(2612) | 2612 | 34 | `li-d` 85.3 PiB sp50, `lu-d` 85.1 PiB sp50 |
| `ckv` | *(none)* | `mb`(2398) | 2398 | 21 | `mg-d` 77.5 PiB sp10, `me-d` 26.9 PiB sp20 |
| `tul` | us-central2 | `yutulpz`(2004) | 2004 | **1** | `nm-d` 44.2 PiB sp50, `oi-d` 28.4 PiB sp50 |
| `mrn` | *(none)* | `yumrnel`(1168) | 1168 | 67 | `qo-d` 8.77 PiB sp50, `qr-d` 0.14 PiB sp0 |
| `uos` | us-east7 | `gc`(960) | 960 | 14 | `gd-d` 21.5 PiB sp10, `ge-d` 17.8 PiB sp1 |
| `grq` | europe-west4 | `el`(915) | 915 | 13 | `el-d` 95.7 PiB sp50, `ej-d` 13.3 PiB sp50 |
| `lhr` | europe-west2 | `yulhrp`(154) | 154 | 3 | **none team-wide** (only `yulhrp-d` 500 TiB sp20) |
| `atl` | us-east2 | `yo`(112) | 112 | 0 | `yo-d` 65.8 PiB sp500, `ym-d` 6.81 PiB sp50 |

**A chip count cannot see fragmentation, so read the slice column beside it**:
`tul` carries thousands of obtainable chips and, on this sample, exactly ONE
placeable v7-32 — a metro can be rich in chips and unable to start your job,
which is the failure `../jobs.md` describes as a green preflight followed by an
allocator reject. `atl` is the mirror case worth watching rather than promoting:
the deepest spindle commitment anywhere (sp500) with almost no chips.
