# TPU Quick Reference

Naming, memory, and legal shapes. Every layer of the stack calls the same chip
a different name, and picking the wrong one fails in a different place each
time, so all the aliases live in one table here.

## Name Mapping

| Marketing | Codename | XM `ResourceType` | `tpu quota` label | Borg locus prefix | Topology prefix |
|---|---|---|---|---|---|
| v4 | Pufferfish | `PUFFERFISH` (34) | TPU v4 | `pufferfish` | `pf` |
| v5e | Viperlite | `VIPERLITE` (60) | TPU v5e | `viperlite` | – |
| v5e Pod | Viperlite Pod | `VIPERLITE_POD` (62) | TPU v5e Pod | `viperlite_pod` | `vlp` |
| v5p | Viperfish | `VIPERFISH` (59) | TPU v5p | `viperfish` | `vf` |
| v6e | Ghostlite Pod | `GHOSTLITE_POD` (63) | TPU v6e | `ghostlite_pod` | `glp` |
| v6p / v7x | Ghostfish | `GHOSTFISH` (92) | TPU v6p | `ghostfish` | `gf` |
| v7 | Ghostfishlite | `GHOSTFISHLITE` (101) | – | `ghostfishlite` | – |

Traps this table exists to prevent:

- **`GHOSTFISHLITE` (101) is v7, NOT v5e.** A launcher that maps `v5e` to
  `ghostfishlite` builds a request for the wrong hardware.
- **v7 is supported by `tpu queue`/`tpu preflight` as of 2026-07-30.** Its slice
  geometry is identical to v6p (3-D torus, 4 chips/host):
  `platforms/accelerator_metadata/platforms/ghostfishlite.gcl` declares the same
  static sub-cubes as `ghostfish.gcl` and differs only in the locus name.
  Registered sizes are **4/8/16/32** (`v7-16` → `2x2x4`); 64+ exists only through
  dynamic slice creation via the OCS manager, so it is deliberately not claimed.
  v7 is frequently the cheapest option — it has repeatedly cleared at 0.00
  (free pool) while v6p had zero availability.
- **v6p must be `ghostfish`.** Passing the literal string `v6p` raises
  `Unknown ResourceType 'v6p'` at submit time.
- The numeric ids are what `ResourcePrices` and other Spanner tables key on;
  use them when querying GQM directly (see `xmanager.md`).

## HBM Per Chip

| Chip | HBM |
|---|---:|
| v5e (Viperlite Pod) | 16 GB |
| v4 (Pufferfish) | 32 GB |
| v6e (Ghostlite Pod) | 32 GB |
| v5p (Viperfish) | 96 GB |
| v6p (Ghostfish) | 192 GB |
| v7 (Ghostfishlite) | 192 GB |

Size the slice from **per-chip** HBM, not the total: a model whose per-chip
working set exceeds the column above OOMs no matter how many chips are added.
Run an AOT memory estimate before launching anything expensive.

Host RAM per chip differs even where HBM matches: v6p hosts carry 256 GiB/chip,
v7 hosts only ~128 GiB/chip (512 GB machines, 481/464 GiB usable). A job with a
large host-side cache or heavy input pipeline can fit v6p and OOM the host on
v7 despite identical HBM.

## Legal Shapes

3-D torus (`x*y*z`): v4, v5p, v6p. 2-D (`x_y`): v5e, v6e.

| Chips | v4 / v5p / v6p | v5e / v6e |
|---:|---|---|
| 8 | `2x2x2` | `2_4` |
| 16 | `2x2x4` | `4_4` |
| 32 | `2x4x4` | `4_8` |
| 64 | `4x4x4` | `8_8` |
| 128 | `4x4x8` | `8_16_wrap_y` |
| 256 | `4x8x8` | `16_16_wrap_xy` |
| 512 | `4x8x16` | – |

Source of truth is `borg/common/locus_info.cc`, mirrored in
`tpu_utils/preflight/topology.py`. Borg wants the shaped string, never the
scalar chip count.

`deepmind-dynamic/*` allocations enforce a **16-chip minimum at PROD** for
v4/v5p/v6e/v6p; smaller slices are rejected instantly by pool policy (not by
Borg). BATCH usually allows the architecture minimum.

## Performance Equivalence

Per-chip, normalized to v5p. Derived from the `vle` field Borg publishes in
`borg/util/reports/gxu/gxus_by_platform_ga.textproto`, cross-checked against
per-chip MXU bf16 FLOPs in `platforms/deepsea/ffds/art/performance/systems/configs/`.
The two derivations agree to three digits.

| Chip | bf16 TFLOPs | Compute (v5p=1) | HBM BW | HBM BW (v5p=1) |
|---|---:|---:|---:|---:|
| v5e | 197 | 0.43 | 0.82 TB/s | 0.30 |
| v4 | 275 | 0.60 | 1.23 TB/s | 0.44 |
| v5p | 459 | 1.00 | 2.77 TB/s | 1.00 |
| v6e | 918 | 2.00 | 1.61 TB/s | 0.58 |
| v6p | 1992 | 4.34 | 7.37 TB/s | 2.66 |
| v7 | 1992 | 4.34 | 7.37 TB/s | 2.66 |

So `v6p-8 ≈ v7-8 ≈ v6e-16 ≈ v5p-32`. Used by `tpu route --power=`, which
encodes this table in `router.py::_V5P_MULTIPLIER`.

Three traps in using a single scalar:

- **Compute ratio ≠ speedup.** HBM bandwidth does not track compute. v6e scores
  2× v5p on compute but has **0.58×** its bandwidth, so memory-bound work
  (long-context attention, small-batch decode) runs *slower* on v6e than on v5p.
  v6p/v7 gain 2.66× bandwidth against 4.34× compute — real, but not the headline
  number. Decide from the bound your job is actually in.
- **int8 does not carry over.** v4/v5e/v5p/v6e accelerate int8 (2×) and int4
  (4×). v6p/v7 accelerate fp8 (2×) and give int8 **no speedup at all** (1×). An
  int8-tuned model moved from v5p to v6p/v7 must switch to fp8 to gain anything.
- **v6p ≠ 2× v5p.** An earlier version of this table claimed that, understating
  v6p by more than half and causing `tpu route` to recommend twice the hardware
  a request needed. v6p/v7 are 4.34×.

## Batch Size Constraint

Global batch size must be a non-zero multiple of the chip count, or the job
dies with `ValueError: Batch size <B> must be a non-zero multiple of the number
of chips`. Check this against the *slice* you requested, not the one you meant
to request.
