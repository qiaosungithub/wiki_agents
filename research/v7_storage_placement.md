# Where v7 Can Run With Storage Next To It

Snapshot of a placement survey, kept because the v7 fleet is new and its
storage coverage is uneven. Delete once the placement is settled and recorded
in the project guide. Method matters more than the numbers: re-run it rather
than trusting a stale row.

## The Question To Ask

Not *"does this TPU cell have storage quota"* but *"does this TPU cell's
**metro** contain a storage cell with quota"*. A cell is one cluster; a metro
holds several. Same-metro cross-cell reads are effectively free, so the metro
is the unit that decides whether compute and data are co-located. Asking the
narrow question hides most of the answer -- two cells that look unusable are
fine because a neighbour in the same metro holds PiBs.

## How To Regenerate

1. **v7 cells** -- the market cache lists every cell with a price, keyed by an
   internal card code (v7 was `101`; verify by checking that a known v7 cell
   appears under it):
   `~/.tpu_quota_cache_dir/market.json`, under `prices.<pool>|<code>|PROD`.
   The `tpu money` table only prints a few sample cells per card, so read the
   cache, not the table.
2. **Storage cells with a ceiling** -- `flex.par ls --group=<accounting-group>
   --service=colossus` lists every registered cell with its disk ceiling and
   spindle commitment. This is authoritative; `fileutil quota` is not (see
   `../storage.md`).
3. **Join on metro** -- `mach_locality -k metro <cell>` for both sides.
   Parallelise with `xargs -P`; it is one RPC per cell.

## Result (2026-08-04, group `deepmind-resources-colossus`)

| metro | GCP region | v7 cells | largest same-metro storage |
|---|---|---|---|
| `grq` | europe-west4 | `el` | **`el-d` 95.4 PiB / sp50** -- same cell |
| `lpp` | europe-north1 | `yulpptr` | `li-d` 85.2 PiB, `lu-d` 85.1 PiB / sp50 |
| `ckv` | *(none)* | `mb` | `mg-d` 77.9 PiB / sp10; `mb-d` 10.7 PiB / sp50 (same cell) |
| `cbf` | us-central1 | `je`, `yucbfiv`, `yucbful`, `yucbfwv` | `is-d` 69.1 PiB / sp50 |
| `dfw` | us-south1 | `yudfwra` | `rs-d` 49.3 PiB / sp50 |
| `tul` | us-central2 | `yutulpz` | `nm-d` 44.0 PiB / sp50 |
| `sin` | asia-southeast1 | `sk`, `sn`, `so` | `si-d` 9.69 PiB / sp50 |
| `mrn` | *(none)* | `yumrnel` | `qo-d` 8.80 PiB / sp50 |
| `ske` | *(none)* | `yuskedq` | **none** |
| `phx` | us-west8 | `yuphxrp` | **none** (only the cell's own 100 TiB, sp0) |
| `lhr` | europe-west2 | `yulhrp` | **none** (only the cell's own 500 TiB) |
| `kul` | *(none)* | `yukulwh` | **none** |

Read `sp<N>` as the spindle commitment: **`sp0` means no throughput floor**,
the condition behind a 12-hour collapse recorded in `../archive/audits/`.

## What It Changed

The prior plan assumed v7 existed only in `ske` and that a new flex
registration there was the only way forward. Both were wrong: v7 is in 17
cells across 12 metros, and 8 of those metros already have PiB-scale quota.
`ske` is one of only four with nothing -- so **move the compute, do not
request the quota**.

`el` is the strongest single answer: v7 and 95.4 PiB in the *same* cell, still
in Europe. `cbf` and `ckv` are the North American equivalents.

## Verified End To End (2026-08-05)

The other half -- *are the chips actually obtainable, and does a real job run
there* -- was then tested by submitting the same smoke to each metro.

**Per-cell obtainable chips come from preflight, not from the quota table.**
`tpu preflight --tpu_type=v7-32 --group=<g> --json` returns a `cells_ok` list of
every cell with its obtainable count. The group-level `tpu quota` view showed
v7 quota fully consumed (477/477) while preflight reported ~50k chips
obtainable across 10 cells -- the alloc's guaranteed floor and what is
schedulable right now are different numbers, and only the second one decides
whether a job starts.

| metro | v7 cell | obtainable | storage | smoke result |
|---|---|---|---|---|
| `cbf` | `yucbfiv` | 3864 | `is-d` | **completed, 12/12 steps** |
| `sin` | `sk` | 3792 | `si-d` | **completed, 12/12 steps** |
| `lpp` | `yulpptr` | 1488 | `li-d` | ran to step 6 |
| `mrn` | `yumrnel` | 1104 | `qo-d` | ran to step 6 |
| `tul` | `yutulpz` | 2388 | `nm-d` | scheduled, 8 tasks |
| `ckv` | `mb` | **0** | `mb-d` | not schedulable now |
| `grq` | `el` | **0** | `el-d` | not schedulable now |
| `dfw` | `yudfwra` | **0** | `rs-d` | not schedulable now |

Checkpoints were confirmed on CNS with `capacity_quota_user:
deepmind-resources-colossus` -- the 500 GiB personal ceiling is out of the
picture on these paths.

**Obtainability is volatile and inverts the storage ranking.** `el` (95.4 PiB,
the best storage answer) had **zero** obtainable chips during this test, while
`cbf` and `sin` -- middling on storage -- both ran a job to completion. Neither
list is stable: re-run preflight before committing, and prefer a metro that is
currently good on *both* rather than the best on either.

The launcher's `_CELL_BUCKETS` now maps every v7 cell to a same-metro bucket,
so `--cell=<v7 cell>` alone picks the right storage; it prints the choice at
launch, which is worth reading as confirmation.

## Decision (2026-08-05): Three Metros To Maintain Data In

Datasets are mirrored into **`cbf`, `tul`, `lpp`** and nowhere else. Chosen on
the intersection of live obtainability, storage headroom, and a verified smoke,
weighting *breadth of cells* because a metro with one cell is one stockout away
from useless.

| metro | v7 cells live | chips | storage cell | smoke |
|---|---|---|---|---|
| **`cbf`** | `yucbfiv`, `yucbful` (+`je`, `yucbfwv` idle) | 6804 | `is-d` 69.1 PiB sp50 | completed 12/12 |
| **`tul`** | `yutulpz` | 2388 | `nm-d` 44.0 PiB sp50 | scheduled, 8 tasks |
| **`lpp`** | `yulpptr` | 1552 | `li-d` 85.2 PiB sp50 | ran to step 6 |

`cbf` is the primary: **four v7 cells, two live**, the only metro with any
redundancy, plus PiB-scale storage and a completed run. `tul` is the second NA
metro and is where the existing `jax_llava` work already sits. `lpp` is the
European leg, and carries the largest storage of the three.

Rejected, with the reason, so this is not re-litigated:

- `ske` (13724 chips) and `kul`, `phx` -- **most chips of all, zero team
  storage**. Compute without co-located storage is the pruner-kill case.
- `grq` / `el` -- the best storage (95.4 PiB) but obtainability swung 0 -> 937
  across a day. A single cell that thin cannot be a primary.
- `sin` -- completed its smoke, but one cell, 9.7 PiB, and far from the others.
- `ckv`, `dfw` -- good storage, **zero obtainable** in every sample taken.

