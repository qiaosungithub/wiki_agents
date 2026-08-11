# TPU Quick Reference

Naming, memory, legal shapes, and per-chip equivalence, plus the invariants that
make them safe to use. Every layer of the stack calls the same chip a different
name, so all the aliases live in one table. Launching is `jobs.md`, pool and CLI
internals `infra/tpu_cli.md`, prices `infra/quota_market.md`.

## Name Mapping

| Marketing | Codename | XM `ResourceType` | `tpu quota` label | Borg locus prefix | Topology prefix |
|---|---|---|---|---|---|
| v4 | Pufferfish | `PUFFERFISH` (34) | TPU v4 | `pufferfish` | `pf` |
| v5e | Viperlite | `VIPERLITE` (60) | TPU v5e | `viperlite` | – |
| v5e Pod | Viperlite Pod | `VIPERLITE_POD` (62) | TPU v5e Pod | `viperlite_pod` | `vlp` |
| v5p | Viperfish | `VIPERFISH` (59) | TPU v5p | `viperfish` | `vf` |
| v6e | Ghostlite Pod | `GHOSTLITE_POD` (63) | TPU v6e | `ghostlite_pod` | `glp` |
| v6p | Ghostfish | `GHOSTFISH` (92) | TPU v6p | `ghostfish` | `gf` |
| v7 | Ghostfishlite | `GHOSTFISHLITE` (101) | – | `ghostfishlite` | – |

| Trap | Rule |
|---|---|
| `GHOSTFISHLITE` (101) is **v7, NOT v5e** | A launcher mapping `v5e` to `ghostfishlite` builds a request for the wrong hardware |
| The literal `v6p` raises `Unknown ResourceType 'v6p'` at submit time | v6p must be `ghostfish` |
| `ResourcePrices` and other Spanner tables key on the **numeric ids** | Use them when querying GQM directly (`infra/quota_market.md`) |
| A generation reaches `tpu queue`/`tpu preflight` before this table mentions it | Verify rather than assume: `tpu preflight --tpu_type=<gen>-<n> --json` either returns a `cells_ok` list or names the type unknown |
| `v7x` is an EXTERNAL name and does **not** mean v7 | Cloud vocabulary maps `V7X`→`TPU7X` onto `GHOSTFISH` (92) = **v6p**; internal v7 is `GHOSTFISHLITE` (101). Nothing in the launcher emits or accepts `v7x` |

**v7's `device_kind` is `TPU7x` — no space, no `v`.** Every earlier generation
reports `TPU v5p` / `TPU v6e` / `TPU v4`, and JAX itself special-cases the
break (`third_party/py/jax/.../pallas/ops/tpu/megablox/common.py`: *"TPU v7 has
a different pattern (i.e. TPU7x)"*). Any code keying a topology or capability
table on `"v7"` therefore MISSES, and the miss is usually silent — a lookup
that falls back to a default rather than raising. This cost a 5.8x slowdown in
`jax_llava`, undetected for a full production run: the mesh table had no v7
entry, `get_mesh()` fell back to a flat 1-D mesh, and under HSDP that shards
every parameter across all devices so each matmul pays a full-mesh collective.
Training still converged — only throughput complained. **Match on `tpu7`, and
assert the mapping against the real strings before trusting it.**

**v7's slice geometry is identical to v6p** (3-D torus, 4 chips/host):
`platforms/accelerator_metadata/platforms/ghostfishlite.gcl` declares the same
static sub-cubes as `ghostfish.gcl`, differing only in the locus name. Registered
sizes are **4/8/16/32** (`v7-16` → `2x2x4`); 64+ exists only via dynamic slice
creation through the OCS manager, so it is deliberately not claimed.

**v7 is usually the cheapest generation on this pool** — it has cleared at 0.00
(free pool) in every sample taken, while v6p clears in the single credits/hr and
moves round to round. Read that as a price difference, not a capacity one: v6p
is obtainable in tens of thousands of chips at the same moment. Check the market
before assuming which generation you can get — `tpu money`, or
`prices.<pool>|101|PROD` in `~/.tpu_quota_cache_dir/market.json` (v7 is card code
101, v6p 92).

**A chip is not a device: v7 and v6p expose TWO cores per chip.** A v7-32 is 8
hosts x 4 chips over a `2x4x4` torus, so `jax.device_count()` returns **64**,
not 32. A chip count, a device count, and a mesh size are three different
numbers, and every batch size must divide the real device count.

## Per-Chip Capability

Normalized to v5p from the `vle` field in
`borg/util/reports/gxu/gxus_by_platform_ga.textproto`, agreeing to three digits
with per-chip MXU bf16 FLOPs in
`platforms/deepsea/ffds/art/performance/systems/configs/`.

| Chip | HBM | bf16 TFLOPs | Compute (v5p=1) | HBM BW | HBM BW (v5p=1) |
|---|---:|---:|---:|---:|---:|
| v5e | 16 GB | 197 | 0.43 | 0.82 TB/s | 0.30 |
| v4 | 32 GB | 275 | 0.60 | 1.23 TB/s | 0.44 |
| v5p | 96 GB | 459 | 1.00 | 2.77 TB/s | 1.00 |
| v6e | 32 GB | 918 | 2.00 | 1.61 TB/s | 0.58 |
| v6p | 192 GB | 1992 | 4.34 | 7.37 TB/s | 2.66 |
| v7 | 192 GB | 1992 | 4.34 | 7.37 TB/s | 2.66 |

**Size the slice from per-chip HBM, not the total**: a model whose per-chip
working set exceeds the column above OOMs however many chips are added, so run an
AOT memory estimate before launching anything expensive. **Host RAM per chip
differs even where HBM matches** — v6p carries 256 GiB/chip, v7 only
~128 GiB/chip (512 GB machines, 481/464 GiB usable) — so a large host-side cache
or heavy input pipeline can fit v6p and OOM the host on v7 despite identical HBM.

**Peak capability is not obtainable throughput.** These ratios hold only while
you keep the slice. Measured over 18.7 h, v6p-64's median hold was 2.3 min --
shorter than one checkpoint interval -- so it finished less work than v6e or
v5p despite 4.34x the per-chip compute. Before choosing a family for a long
preemptible run, read `research/accelerator_choice.md`.

## Converting Between Generations

Per chip, `v7 = v6p ≈ 2x v6e ≈ 4.34x v5p ≈ 7.23x v4`, so
`v6p-8 ≈ v7-8 ≈ v6e-16 ≈ v5p-32`. `tpu route --power=` does the arithmetic and
encodes this table in `router.py::_V5P_MULTIPLIER`.

**Read the relation the other way when SIZING a run against a baseline**:
matching a `v6p-16` needs **`v6e-32`**, `v5p-64`, or `v4-128` (115.7 chips
rounded up to the next legal v4 shape — the conversion gives a number, the
legal-shape table decides what you can ask for). Getting this wrong is silent:
the job runs at half the compute and is compared against siblings as if the
hardware had been equal; `AGENTS.md` carries it as a hard rule. Three traps in
using a single scalar:

| Trap | Detail |
|---|---|
| **Compute ratio ≠ speedup** — decide from the bound your job is actually in | HBM bandwidth does not track compute: v6e scores 2x v5p on compute but **0.58x** its bandwidth, so memory-bound work (long-context attention, small-batch decode) runs *slower* on v6e than on v5p. v6p/v7 gain 2.66x bandwidth against 4.34x compute — real, but not the headline number |
| **int8 does not carry over** | v4/v5e/v5p/v6e accelerate int8 (2x) and int4 (4x); v6p/v7 accelerate fp8 (2x) and give int8 **no speedup at all** (1x). An int8-tuned model moved from v5p to v6p/v7 must switch to fp8 to gain anything |
| **v6p is 4.34x v5p, not 2x** — re-derive the ratio rather than repeating a remembered one | An earlier table here said 2x and made the router recommend twice the hardware a request needed |

## Legal Shapes

3-D torus (`x*y*z`): v4, v5p, v6p, and v7 (v6p's column, registered only to
32 chips). 2-D (`x_y`): v5e, v6e.

| Chips | v4 / v5p / v6p | v5e / v6e |
|---:|---|---|
| 8 | `2x2x2` | `2_4` |
| 16 | `2x2x4` | `4_4` |
| 32 | `2x4x4` | `4_8` |
| 64 | `4x4x4` | `8_8` |
| 128 | `4x4x8` | `8_16_wrap_y` |
| 256 | `4x8x8` | `16_16_wrap_xy` |
| 512 | `4x8x16` | – |

**Borg wants the shaped string, never the scalar chip count.** Source of truth is
`borg/common/locus_info.cc`, mirrored in `tpu_utils/preflight/topology.py`.

**Allocator policy is stricter than physics**: `deepmind-dynamic/*` enforces a
**16-chip minimum at PROD** for v4/v5p/v6e/v6p, so a smaller request is rejected
instantly by pool policy — not by Borg — even though the topology is valid. BATCH
usually allows the architecture minimum; `infra/tpu_cli.md` owns where these
rules are encoded.

**Global batch size must be a non-zero multiple of the chip count**, or the job
dies with `ValueError: Batch size <B> must be a non-zero multiple of the number
of chips`. Check against the *slice* you requested, not the one you meant to.
