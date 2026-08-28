# TPU Quick Reference

Naming, memory, legal shapes, and per-chip equivalence. Every layer of the
stack calls the same chip a different name, so all the aliases live in one
table. Launching is `jobs.md`, pool and CLI internals `infra/tpu_cli.md`,
prices `infra/quota_market.md`.

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
that falls back to a default rather than raising. One silent miss (a mesh table
with no v7 entry falling back to a flat 1-D mesh) cost a 5.8x slowdown in
`jax_llava` for a full production run. **Match on `tpu7`, and assert the mapping
against the real strings before trusting it.**

**v7's slice geometry is identical to v6p** (3-D torus, 4 chips/host):
`platforms/accelerator_metadata/platforms/ghostfishlite.gcl` declares the same
static sub-cubes as `ghostfish.gcl`, differing only in the locus name. Registered
sizes are **4/8/16/32** (`v7-16` → `2x2x4`); 64+ exists only via dynamic slice
creation through the OCS manager, so it is not claimed.

**v7 is usually the cheapest generation on this pool** — it has cleared at 0.00
(free pool) in every sample taken, while v6p clears in the single credits/hr.
Read that as a price difference, not a capacity one: v6p is obtainable in tens of
thousands of chips at the same moment. Check the market before assuming which
generation you can get — `tpu money`, or
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
you keep the slice: a v6p-64 whose median hold was 2.3 min (shorter than one
checkpoint interval) finished less work than v6e or v5p despite 4.34x the
per-chip compute. Before choosing a family for a long preemptible run, read
`research/accelerator_choice.md`.

## Converting Between Generations

Per chip, `v7 = v6p ≈ 2x v6e ≈ 4.34x v5p ≈ 7.23x v4`, so
`v6p-8 ≈ v7-8 ≈ v6e-16 ≈ v5p-32`. `tpu route --power=` does the arithmetic and
encodes this table in `router.py::_V5P_MULTIPLIER`.

**Read the relation the other way when SIZING a run against a baseline**:
matching a `v6p-16` needs **`v6e-32`**, `v5p-64`, or `v4-128` (115.7 chips
rounded up to the next legal v4 shape — the conversion gives a number, the
legal-shape table decides what you can ask for). Getting this wrong is silent:
the job runs at half the compute and is compared against siblings as if the
hardware were equal; `AGENTS.md` carries it as a hard rule. Three traps in using
a single scalar:

| Trap | Detail |
|---|---|
| **Compute ratio ≠ speedup** — decide from the bound your job is actually in | HBM bandwidth does not track compute: v6e scores 2x v5p on compute but **0.58x** its bandwidth, so memory-bound work (long-context attention, small-batch decode) runs *slower* on v6e than on v5p. v6p/v7 gain 2.66x bandwidth against 4.34x compute — real, but not the headline number |
| **int8 does not carry over** | v4/v5e/v5p/v6e accelerate int8 (2x) and int4 (4x); v6p/v7 accelerate fp8 (2x) and give int8 **no speedup at all** (1x). An int8-tuned model moved from v5p to v6p/v7 must switch to fp8 to gain anything |
| **v6p is 4.34x v5p, not 2x** — re-derive the ratio rather than repeating a remembered one | An earlier table here said 2x and made the router recommend twice the hardware a request needed |
| **Equivalent compute is not equivalent price** — `v7 = v6p` says nothing about what they cost | Measured on one afternoon: `v7-32` PROD priced **8x** its `v6p-32` equivalent, and the same family's price moved ~2x within an hour. So "v7 ≈ v6p, take either" is a compute statement being read as a procurement one. If a job's `allowed_archs` spans both, check the live market before assuming the router picked the cheap side — and **timestamp any price you quote**, because it expires in minutes (`infra/quota_market.md`) |

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

**`v5e` tops out at 64 chips in `deepmind-dynamic`, so it cannot match a
v7-32.** A `v5e-256` request is rejected outright — `preflight: RED, "v5e-256
is not a supported slice size (Borg has no legal locus for it). Supported sizes
for v5e: [8, 16, 32, 64]"` — this is a shape/pool ceiling, NOT a quota or
credit shortfall (credit only lets you bid; the topology must be legal first).
The 256 row above is the physical torus; this pool caps the obtainable slice
lower. Since v7 = 8x v4 = 8x v5e per chip, one v7-32 needs 256 v5e chips — four
v5e-64 slices, not power-equivalent as a single job. **Treat v5e as unusable for
v7-scale training and skip it in surveys.**

**Global batch size must be a non-zero multiple of the chip count**, or the job
dies with `ValueError: Batch size <B> must be a non-zero multiple of the number
of chips`. Check against the *slice* you requested, not the one you meant to.

## NVIDIA GPUs

Running a GPU job on Borg is `gpu_on_borg.md`; this section is the naming +
shape + capability reference (the GPU analogue of the tables above). GPUs go
through the same `tpu enqueue` path but with an explicit `--tpu_type=<gpu>-<n>`
and `--archs=<gpu>` (never the `--power` router — `gpu_on_borg.md` Rule 1).

### Name Mapping

`xm.ResourceType` is case-insensitive and the kwarg name IS the lowercase enum
name, so `JobRequirements(h100=8)` works directly. Card codes key the GQM /
market Spanner tables (`infra/quota_market.md`).

| Arch token (`--tpu_type`) | `xm.ResourceType` | Card code | HBM | NVLink domain |
|---|---|---:|---:|---:|
| `a100` | `A100` | 46 | 40 GB | 16 |
| `a100_80gib` | `A100_80GIB` | 66 | 80 GB | 8 |
| `h100` | `H100` | 70 | 80 GB | 8 |
| `h200` | `H200` | 86 | 141 GB | 8 |
| `b200` | `B200` | 87 | 180 GB | 8 |
| `b300` | `B300` | 112 | 288 GB | 8 |
| `gb200` | `GB200` | 89 | 186 GB | 72 |
| `gb300` | `GB300` | 100 | 288 GB | 72 |

### NVLink Domain = The Largest Fully-Connected Single Slice

The **NVLink domain** (device_group in the platform GCL) is the biggest slice
whose GPUs are all NVLink-connected; beyond it, chips communicate over network
RDMA — legal, but not faster for comms-bound work. So the largest *full-speed*
single slice is `h100-8` / `b200-8` (8-GPU HGX/Neutron domain) and `gb200-72` /
`gb300-72` (72-GPU Oberon NVL72 rack). `a100`-40G is the odd one at 16.

**Why 72 is not a power of two — GPU NVLink is NOT a torus.** A TPU slice is a
dimensional torus (`2x4x4`), so its sizes are products of small factors. A GPU
NVLink domain is the opposite: the platform GCL declares
`connectivity = 'FULLY_CONNECTED'`, `locus_type = 'locus:SCALE_NVLINK_DOMAIN'`
(`platforms/accelerator_metadata/platforms/templates/nvl.gcl`) — every GPU in
the domain reaches every other through an NVSwitch fabric, so there is **no
shape**, just a flat count. `gb200-8` means "8 mutually-connected GPUs", not a
`2x2x2` cube. The ceiling is 72 because that is the physical GPU count of one
Oberon **NVL72** rack (the unit the switch layer spans); any count up to 72 in
one rack is a legal fully-connected slice — 72 is a hardware maximum, not a
torus dimension. (H100/B200 are the same idea at a smaller ceiling: one 8-GPU
HGX/Neutron NVLink board, flat all-to-all, so `[1,2,4,8]`.)

- **Legal shapes** are `[1,2,4,8]` for the 8-domain cards (`h100-16` is RED at
  preflight, "supported [1,2,4,8]"). GB200/GB300 go up to 72 in principle, but
  NVL72 large slices are frequently "not approved for borg scheduling" — treat
  `gb200-8/16/32` as the safe obtainable shapes and prove larger with a real
  enqueue (`gpu_on_borg.md`).
- **A GPU chip is one device** — no two-cores-per-chip subtlety (unlike v6p/v7
  TPU). `JobRequirements(h100=8)` → 8 devices, `torch.cuda.device_count()==8`,
  one Borg task. Batch size must divide the device count.

### Per-Chip Capability (v5p-normalised)

From the `vle` field in `gxus_by_platform_ga.textproto` (same source as the TPU
table). Use it for the credit-limit cap tiers and rough cross-family sizing —
NOT as an obtainability or price signal (read `tpu money` / `tpu preflight` live,
same as TPU).

| Chip | Compute (v5p=1) | Cap tier (`tpu_wrapper.sh`) |
|---|---:|---|
| a100 | 0.68 | 5 (v5p tier) |
| h100 / h200 | 2.15 | 10 (v6e tier) |
| b200 / b300 / gb200 / gb300 | 4.90 | 20 (v6p/v7 tier) |

**Round to the NEAREST legal slice when converting, and re-derive both ways.**
The scalar (`v5p=1`) gives a chip-count *estimate*; the legal-shape table (GPU
`[1,2,4,8]` per NVLink board, TPU torus sizes) decides what you can actually
ask for, so round the estimate to the nearest legal count — do not floor it and
silently buy less compute (the same trap as the TPU §Converting rule). Worked
examples: **h100=2.15**, so one v6p/v7 chip (4.34) ≈ **2× H100** — matching a
`v7-8` (34.7 v5p-units) needs ~16 H100, i.e. **two h100-8 NVLink boards**
(16 rounds to 2×8, since h100 has no legal 16-in-one-domain slice). **b200=4.90**
≈ one v6p chip, so `gb200-8 ≈ v7-8` in raw compute; a `v7-32` (139 v5p-units)
≈ **28 B200/GB200**, round to the nearest legal slice **gb200-32** (not 28).
**a100=0.68**: a `v5p-16` (16 units) ≈ 24 A100 → round to a100 legal shapes.
Always cross the rounded count with a live `tpu preflight` — the legal ceiling
(H100 board = 8) may force MULTIPLE boards + network RDMA between them, which is
not the same as one fully-connected slice (see NVLink Domain above).

**Price inverts the TPU intuition:** GPU PROD is cheap (H100 ~0.5–0.8
cr/chip-hr; A100 ~0.16; B200 ~0.4; GB200/GB300/H200 free pool) and most GPUs have
a **free (0.00) BATCH pool** — but BATCH is preemptible (`gpu_on_borg.md`
Rule 6).

**The fixed per-family price caps (`_tpu_limit_price_for_arch` /
`cap_policy.py`) can sit BELOW market at a price peak, and that is by design.**
They are blast-radius bounds, not trackers, so on a spike the market clears
above the cap and a PROD job in that family is held `Queued (GQM price over
limit order)` until the price falls back. The GPU caps stay far above their
(cheap) market; several TPU caps (v5p, v7, v6e, and v6p at peaks) are routinely
pierced — verify with a live `market.json` read vs the cap. **The correct
response to a price-hold is to WAIT, never a per-job `set_limit_order` bump**
(that overpays and end-runs the bound). Changing a cap is an operator decision;
the knob is `cap_policy.py` + its LINT-synced shell twin, never `budget_check`.
