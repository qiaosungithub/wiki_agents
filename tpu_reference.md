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

Size the slice from **per-chip** HBM, not the total: a model whose per-chip
working set exceeds the column above OOMs no matter how many chips are added.
Run an AOT memory estimate before launching anything expensive.

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

`1 v6e chip ≈ 1 v6p ≈ 2 v5p ≈ 2 v4`, so `v6e-16 ≈ v6p-16 ≈ v5p-32 ≈ v4-32`.
Used by `tpu route --power=`.

## Batch Size Constraint

Global batch size must be a non-zero multiple of the chip count, or the job
dies with `ValueError: Batch size <B> must be a non-zero multiple of the number
of chips`. Check this against the *slice* you requested, not the one you meant
to request.
