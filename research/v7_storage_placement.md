# Where v7 Can Run With Storage Next To It

Owns the choice of metro for a v7 run, and the survey that decides it.
`../storage.md` owns why co-location matters at all and how quota is charged.
Read this before pinning a cell; **re-run the survey rather than trusting a row
below** — obtainability moves daily, and the v7 fleet is still turning up.
Delete this file once the placement is settled and recorded in the project
guide.

## The Standing Decision: Three Metros

**Datasets are mirrored into `cbf`, `tul`, `lpp` and nowhere else**, chosen on
the intersection of live obtainability, storage headroom, and a verified smoke,
weighting *breadth of cells* because a metro with one cell is one stockout away
from useless.

| metro | v7 cells live | chips | storage cell | smoke | role |
|---|---|---|---|---|---|
| **`cbf`** | `yucbfiv`, `yucbful` (+`je`, `yucbfwv` idle) | 6804 | `is-d` 69.1 PiB sp50 | completed 12/12 | **primary** — four cells, the only redundancy anywhere |
| **`tul`** | `yutulpz` | 2388 | `nm-d` 44.0 PiB sp50 | scheduled, 8 tasks | second NA metro; existing `jax_llava` work sits here |
| **`lpp`** | `yulpptr` | 1552 | `li-d` 85.2 PiB sp50 | ran to step 6 | European leg; largest storage of the three |

Rejected, with the reason, so this is not re-litigated:

| Rejected | Why |
|---|---|
| `ske` (13724 chips), `kul`, `phx` | **Most chips of all, zero team storage.** Compute without co-located storage is the pruner-kill case. |
| `grq` / `el` | The best storage anywhere (95.4 PiB, same cell as the chips), but obtainability swung 0 -> 937 across a day. A single cell that thin cannot be a primary. |
| `sin` | Completed its smoke, but one cell, 9.7 PiB, and far from the others. |
| `ckv`, `dfw` | Good storage, **zero obtainable** in every sample taken. |

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
registration there is the only way forward" — in fact v7 is in 17 cells across
12 metros, 8 already hold PiB-scale quota, and `ske` is one of only four with
nothing. **Move the compute, do not request the quota.**

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
5. **Confirm with a real job**, not just the numbers: submit the same smoke to
   each candidate metro. Checkpoints should land on CNS with
   `capacity_quota_user: deepmind-resources-colossus`, keeping the 500 GiB
   personal ceiling out of the picture.

### Last survey, for shape only — re-run before relying on it

Group `deepmind-resources-colossus`; storage is the largest same-metro cell,
`obtainable` a single preflight sample.

| metro | GCP region | v7 cells | largest same-metro storage | obtainable | smoke |
|---|---|---|---|---|---|
| `grq` | europe-west4 | `el` | **`el-d` 95.4 PiB / sp50** — same cell | 0 | — |
| `lpp` | europe-north1 | `yulpptr` | `li-d` 85.2 PiB, `lu-d` 85.1 PiB / sp50 | 1488 | to step 6 |
| `ckv` | *(none)* | `mb` | `mg-d` 77.9 PiB / sp10; `mb-d` 10.7 PiB / sp50 (same cell) | 0 | — |
| `cbf` | us-central1 | `je`, `yucbfiv`, `yucbful`, `yucbfwv` | `is-d` 69.1 PiB / sp50 | 3864 | 12/12 |
| `dfw` | us-south1 | `yudfwra` | `rs-d` 49.3 PiB / sp50 | 0 | — |
| `tul` | us-central2 | `yutulpz` | `nm-d` 44.0 PiB / sp50 | 2388 | scheduled |
| `sin` | asia-southeast1 | `sk`, `sn`, `so` | `si-d` 9.69 PiB / sp50 | 3792 | 12/12 |
| `mrn` | *(none)* | `yumrnel` | `qo-d` 8.80 PiB / sp50 | 1104 | to step 6 |
| `ske` | *(none)* | `yuskedq` | **none** | — | — |
| `phx` | us-west8 | `yuphxrp` | **none** (only the cell's own 100 TiB, sp0) | — | — |
| `lhr` | europe-west2 | `yulhrp` | **none** (only the cell's own 500 TiB) | — | — |
| `kul` | *(none)* | `yukulwh` | **none** | — | — |
