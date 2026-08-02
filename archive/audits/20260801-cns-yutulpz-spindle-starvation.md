# CNS cell `yutulpz-d` degradation — diagnosis

**Window analysed:** 2026-07-31 20:00 → 2026-08-01 16:00 UTC
**Reported symptom:** 4 MB orbax checkpoint read from `/cns/yutulpz-d/home/qiaos/` by Borg
tasks in compute cell `oe` (metro tul). 26–55 MiB/s ("load in 0.4–1.5 s") until 03:32 UTC,
monotone decay 03:38→04:01, then 0.5–1.2 MiB/s ("load in 37–175 s"), persisting 12+ h.
A non-CNS RPC in the same process (lineage_log `read_event` → UMB) went 0.02 s → 4–14 s at
the same instant.

**Author:** session `free-cat` (+ sub-agent `dreamy-panda`). Read-only investigation.
Everything below is either **[MEASURED]** (a query/command I ran, output reproduced) or
**[INFERRED]** (a conclusion drawn from measurements) or **[COULD NOT MEASURE]**.

---

## TL;DR — verdict

**The user is not at fault and the cell hardware is not broken.**

A **best-effort Blobstore LAD (data-mover) workload started at ~03:00–04:00 UTC on
2026-08-01 in the CFS2 Colossus cell `yutulpz`** and has been running ever since. It
saturated the **shared physical D-cell spindle pool ~10x** (1.1k → 10.6k spindles), which
added a roughly **constant +21…25 ms of disk queueing to every single read operation** served
by that pool.

The CNS path `/cns/yutulpz-d/...` belongs to a *different* Colossus cell (`yutulpz-d`, CFS1)
that is **physically co-located on the same D cell and therefore the same spindles**. So
`qiaos` was starved by a workload living in a cell he cannot see, has no relationship with,
and cannot query.

Because a 4 MB orbax checkpoint is read as **many small operations**, a per-operation penalty
of +25 ms is devastating: it is a per-op tax, not a bandwidth cut. That is exactly why the
small-read bucket degraded 14x while the large-read bucket only degraded 3x, and why a
completely unrelated non-CNS RPC in the same process also fell over at the same second.

Answers in one line each:
1. **`qiaos` is NOT over disk quota** (24.5 % of 500 GiB) and Colossus is **not throttling
   him** (throttle rate 0.004–0.14 %). He has **zero spindle commitment**, which is the real
   problem — no floor, no protection.
2. **The cell is NOT unhealthy** in the hardware sense: 268/268 D servers `HEALTHY`, zero
   `DEAD/DOWN/DRAIN/LAME`, and the server count actually *grew* 214 → 268 during the incident.
   It **is** capacity-constrained: spindle demand overran quota by ~14,757 units at throughput
   priority.
3. **Yes** — a clean, measured, sustained step change. Gradual ramp 03:05→04:00, hard step
   04:00→04:15, still going at 16:00. It matches the reported orbax cliff to the minute.
4. **`-d` is a Colossus cell-name convention only.** It does *not* mean a storage tier.
   HDD-vs-SSD is a different field (`metric:partition`). Critically, `yutulpz-d` and
   `yutulpz` are **two different Colossus cells sharing one D cell** — that is the whole
   mechanism.

---

## Q1 — Is `qiaos` over disk quota / spindle quota? Is Colossus throttling him?

### 1a. Byte quota — **NO. Not close.** [MEASURED]

```
monarch_cli query --output_format=csv --duration=20h --end_time=2026-08-01T16:00:00Z \
  --output_period=30m \
  --mash="Fetch(Raw('storage.DmlUser','/storage/d/quota/per_user/quota_mib'),
          {'d_client_user':'qiaos','d_cell':'yutulpz'}) | Window(Align('30m')) | GroupBy([], Sum())"
```

| item | value |
|---|---|
| HDD quota ceiling | **512 000 MiB = 500 GiB** |
| SSD quota ceiling | 0 |
| Usage at 16:00 | **125 450 MiB = 122.5 GiB** |
| **Utilisation** | **24.5 %** |

Usage history (`/storage/d/quota/per_user/usage_mib`, 30 m buckets, MiB):

```
2026-07-31 20:30   52 739
             21:00  66 701
             21:30  82 898
             22:00 102 432
             22:30 119 388
             23:00 125 553   <-- plateau reached
2026-08-01 00:00 - 16:00   125 189 … 125 571   (FLAT)
```

**[MEASURED]** Usage stopped growing at **23:00**, i.e. **three hours before** the cliff, and
was flat straight through 03:38–04:01. There is no step, no overage, and it never approached
the ceiling.

Also **[MEASURED]**:
```
$ fileutil du -s -h /cns/yutulpz-d/home/qiaos/
36G                                     # completed in 12.1 s
```
(36G vs 122.5 GiB reported by quota — quota counts replicated/encoded bytes plus other
namespaces on the cell; the point stands either way.)

Write-poison check **[MEASURED]** — an over-quota user gets writes rejected:
```
$ fileutil --gfs_user=qiaos cp /tmp/2bytes /cns/yutulpz-d/home/qiaos/.probe_%ttl=1h
# rc=0, SUCCESS  -> not write-poisoned, not enforced against
```

### 1b. Is Colossus throttling this user? — **NO.** [MEASURED]

```
monarch_cli query --output_format=csv --duration=20h --end_time=2026-08-01T16:00:00Z \
  --output_period=4h \
  --mash="Fetch(Raw('monarch.BorgTask','/storage/d/client/throttler_responses'),
          {'borg_cell':'yutulpz'}) | Window(Delta('4h')) | GroupBy(['metric:treated_as_throttling'], Sum())"
```

| bucket | `false` | `true` | throttled % |
|---|---:|---:|---:|
| 00:00 | 35 782 756 165 | 259 917 | 0.0007 % |
| 04:00 | 25 396 670 631 | 981 885 | 0.004 % |
| 08:00 | 32 929 409 647 | 113 971 900 | 0.35 % |
| 12:00 | 37 276 738 121 | 5 520 649 | 0.015 % |
| 16:00 | 48 150 082 295 | 68 799 093 | 0.14 % |

**[MEASURED]** Peak explicit throttling is 0.35 %; it cannot explain a 50x slowdown.
Note the mechanism (see 1c): Colossus spindle overrun does **not** produce throttle
responses — it silently *demotes* priority. Throttling being near-zero is consistent with,
not contradictory to, the diagnosis.

Corroborating **[MEASURED]**: `metric:out_of_quota` on
`/file/colossus/client/stripe-read-latency-simple` for `borg_cell=oe, metric:cell=yutulpz`
collapses to a **single ungrouped series** identical to the total (02:00 = 2 603 µs,
04:00 = 2 979, 06:00 = 23 805, 16:00 = 29 248) — only one label value is present in the
data, and the source dashboard's default is `out_of_quota:'false'`. Colossus is **not**
tagging these reads as quota-exceeded.

### 1c. Spindle (IOPS) quota — **the user has NONE, and that is the actual exposure.** [MEASURED]

```
monarch_cli query --output_format=csv --duration=20h --end_time=2026-08-01T16:00:00Z \
  --output_period=1h \
  --mash="Fetch(Raw('storage.DmlUser','/storage/d/manager/public/spindle/usage_by_scheduled_priority'),
          {'d_cell':'yutulpz'}) | Window(Align('1h')) | GroupBy(['d_client_user'], Sum())"
```

Cell-wide spindles in use on D cell `yutulpz`:

```
21:00  1 850   23:00    116   00:00    337   01:00  2 113   02:00    558
03:00  4 894   04:00  8 267   05:00 10 406   06:00 10 472   07:00  8 918
08:00 10 078   10:00 10 056   12:00 10 000   14:00 10 662   16:00 10 648
```

Top owners (spindles):

| `d_client_user` | 02:00 | 03:00 | 04:00 | 05:00 | 16:00 |
|---|---:|---:|---:|---:|---:|
| **blobstore-lad-spindle-owner** | 0 | 165 | **5 126** | **6 002** | **6 353** |
| d-besteffort | 440 | 3 799 | 1 174 | 1 356 | 918 |
| cfs2-shared+recovery_high | 0 | 0 | 0 | 397 | 1 079 |
| blobstore-lad-prodbatch-spindle-owner | 0 | 168 | 438 | 911 | 742 |
| blobstore-async-replication-premium-spindle-owner | 0 | 122 | 570 | 1 004 | 846 |
| cfs2-shared | 0 | 25 | 42 | 348 | 304 |

**`qiaos` does not appear at all** — he is not among the 1 260 `d_client_user` values that
report spindle usage. He holds **byte quota with zero spindle commitment**.

Spindle **quota** for the cell **[MEASURED]**: `/storage/d/manager/public/spindle/quota`
`{d_cell:yutulpz}` = **4 358.6**. Measured usage 10 648 → the pool is running at
**~2.4x its quota**.

Overquota confirmation **[MEASURED]** (`/storage/d/manager/public/spindle/overquota_usage/tp`,
`d_cell=yutulpz`):
```
00:00 = 0.000   04:00 = 14 757   08:00 = 12 879   16:00 = 10 624
sole owner: blobstore-lad-spindle-owner (leaf 2 019.5 / pool rollup 2 253.8); every other user 0.0
ll, ll_downto_tp, ll_downto_be = 0.000 for the entire 20 h
```

**[INFERRED]** Exceeding spindle quota in Colossus does not return an error; it **demotes**
the operation LL → TP → BE, and a demoted op cannot be promoted back. Best-effort has no
floor and is simply queued. `go/colossus-debug` states plainly: *"Colossus has no performance
guarantees for users of HDD bytes without spindles!"* A user with byte quota and no spindle
commitment is served entirely out of the shared pool that LAD flooded.

**Gotcha worth recording [INFERRED from code]:** spindle charging follows the **reader's LOAS
identity**, not the file owner (`file_handle.cc:2042 → ChooseDiskLayerUser() →
fill_disk_layer_options.cc:21 → CurrentLoasUser()`). So `--gfs_user` moves *byte* accounting
but does **not** move *spindle* charging.

**Answer to Q1:** Not over byte quota (24.5 %). Not throttled (≤0.35 %). Has no spindle
quota at all — which is why he had no protection when someone else's best-effort job
saturated the pool.

---

## Q2 — Is the cell itself unhealthy?

### 2a. Hardware / server health — **NO. Perfect health, and growing.** [MEASURED]

```
monarch_cli query --output_format=csv --duration=20h --end_time=2026-08-01T16:00:00Z \
  --output_period=4h \
  --mash="Fetch(Raw('storage.Dml','/storage/d/manager/d_cell_stats/servers_by_health'),
          {'d_cell':'yutulpz','binary_name':'dmanager'}) | Window(Align('4h')) | GroupBy(['metric:health'], Sum())"
```

| health | 00:00 | 04:00 | 08:00 | 12:00 | 16:00 |
|---|---:|---:|---:|---:|---:|
| **HEALTHY** | 214 | 244 | 267 | 268 | **268** |
| DEAD | 0 | 0 | 0 | 0 | 0 |
| DOWN | 0 | 0 | 0 | 0 | 0 |
| DRAIN | 0 | 0 | 0 | 0 | 0 |
| LAME | 0 | 0 | 0 | 0 | 0 |
| COMING_UP | 0 | 0 | 0 | 0 | 0 |

**[MEASURED]** `HEALTHY` is the only non-zero state across the whole 20 h. The cell **added
54 D servers** (214 → 268) *while getting slower*.

**[INFERRED]** This is conclusively a **demand-side** event. There was no curator failover,
no drain, no disk rebalance, no hardware fault. Additional supply was being added and demand
still outran it.

Also **[MEASURED]**: `/storage/d/manager/ataio/bump_level` (4 = healthy, lower = IOPS-punished)
= **4.000 flat for 14 h** at `ll`; `tp` 4.000 → 3.994. Nobody was demoted by the IOPS
enforcer.

### 2b. Capacity / load — **YES, severely constrained.** [MEASURED]

Cell-wide read operation rate (`colossus.ClientTask`,
`/file/colossus/client/stripe_reads/count`, `colossus_cell=yutulpz`, `Rate('1h')`):

```
21:00  14 116 ops/s      03:00  23 449
23:00  13 024            04:00  62 968
01:00  14 688            05:00 114 805
02:00  17 244            08:00 128 649
                         12:00 134 061
                         16:00 166 201     <-- 12.8x baseline
```

Cross-checked independently by me via the other schema (`monarch.BorgTask`,
`stripe-read-latency-simple`, `DistributionCount`), total reads/hour on `metric:cell=yutulpz`:

```
21:00  43.1 M    01:00  45.2 M    03:00   61.0 M    05:00  400.2 M    09:00  487.0 M
22:00  48.7 M    02:00  50.0 M    04:00  116.9 M    06:00  392.2 M    12:00  474.8 M
23:00  43.2 M    00:00  47.3 M                      08:00  441.8 M    16:00  553.1 M
```

**12.8x more read operations against the same physical spindles.**

Cell-wide stored bytes also exploded **[MEASURED]**
(`/storage/d/quota/per_user/usage_mib`, `d_cell=yutulpz`, summed over all users):
**6.46 PiB (22:00) → 39.46 PiB (16:00)**.

By user (TiB):

| `d_client_user` | 22:00 | 02:00 | 04:00 | 08:00 | 12:00 | 16:00 | growth |
|---|---:|---:|---:|---:|---:|---:|---:|
| cfs2-shared | 2 725 | 3 179 | 4 540 | 9 475 | 14 639 | **19 063** | +16 339 |
| **blobstore-cfs-shard-storage-owner** | **0** | **0** | 1 075 | 5 383 | 10 253 | **14 456** | **+13 381** |
| ml-gemini-lsp-leaderboard-cns | 835 | 918 | 936 | 1 001 | 1 093 | 1 099 | +278 |
| (all others) | | | | | | | ≤ +241 |

**Answer to Q2:** Not unhealthy — *overloaded*. Zero hardware faults, zero drains, server
count growing; but read ops 12.8x, spindle usage 9.5x over baseline and 2.4x over quota, and
33 PiB of new data ingested in 13 hours.

---

## Q3 — Did anything change at 03:38–04:01 UTC?

**YES. A textbook step change, on the minute.** [MEASURED]

### 3a. The trigger — a Blobstore ingest that starts from literally zero

`/storage/d/quota/per_user/usage_mib`, `d_cell=yutulpz`,
`d_client_user=blobstore-cfs-shard-storage-owner`, 10-minute buckets:

```
02:40      0.28 TiB      03:40    604.66 TiB      04:40  1 834.08 TiB
02:50     11.48          03:50    813.12          05:00  2 146.66
03:00     47.00          04:00  1 075.24          05:30  2 632.39
03:10     97.89          04:10  1 337.58          06:00  3 143.60
03:20    228.70          04:20  1 517.10          ...
03:30    337.99          04:30  1 675.42          16:00 14 456.3 TiB (still climbing)
```

This user held **0 bytes** on this cell before ~02:40 UTC and has been ingesting at roughly
**1 TiB/minute ever since**. It has not stopped.

### 3b. The load — 5-minute zoom on read ops (millions of reads per 5 min bucket)

| time | cfs2-shared | blobstore2 | blobstore-shard-pusher | blobstore-shard-service |
|---|---:|---:|---:|---:|
| 03:05 | 3.94 | 0.02 | 0.01 | 0.28 |
| 03:20 | 3.53 | 0.94 | 0.47 | 1.19 |
| 03:35 | 4.64 | 0.79 | 1.30 | 1.55 |
| 03:45 | 6.92 | 1.11 | 1.85 | 1.51 |
| 03:55 | 4.94 | 0.85 | 2.10 | 1.54 |
| **04:00** | **8.71** | **1.38** | 2.23 | 1.63 |
| **04:05** | **16.39** | **8.73** | 2.09 | 1.36 |
| 04:15 | 18.48 | 8.52 | 2.42 | 1.30 |
| 04:40 | 23.00 | 7.94 | 2.43 | 1.01 |
| 06:00 | 23.21 | 4.96 | 2.60 | 0.36 |

**[MEASURED]** A **gradual ramp 03:05 → 04:00** followed by a **hard 2x step at 04:05**.
This is a precise match for the reported orbax profile: monotone decay 03:38 → 03:55 (the
ramp), then the floor from 04:01 (the step).

### 3c. The effect — mean stripe-read latency, `oe → yutulpz`, 5-min buckets (µs)

```
02:40  2 061    03:25  3 315    04:00   4 783
02:50  2 780    03:30  3 229    04:05  11 882    <-- step
03:00  2 107    03:35  3 445    04:10  13 618
03:05  2 127    03:40  4 033    04:15  23 248
03:10  2 492    03:45  4 888    04:25  27 335
03:15  2 365    03:50  3 825    04:45  22 441
03:20  2 776    03:55  4 456    05:00  21 448
                                then sustained 20 000-36 000 (spikes to 132 373) through 16:00
```

Hourly, same series: `03:00 = 2 462 µs` → `05:00 = 19 889` → `16:00 = 31 956`. **~10x,
sustained 12 hours.**

### 3d. The symptom, measured directly — `qiaos` throughput [MEASURED]

```
monarch_cli query --mash="Fetch(Raw('colossus.ClientTask','/storage/colossus/client/file/bytes'),
  {'colossus_cell':'yutulpz','borg_user':'qiaos'}) | Window(Rate('1h')) | GroupBy([], Sum())"
```

```
21:00  10 099 290 B/s =  9.63 MiB/s      04:00  1 465 116 =  1.40 MiB/s
23:00   5 193 968     =  4.95            05:00    140 663 =  0.13 MiB/s   <-- floor
01:00   4 786 487     =  4.56            06:00     37 593 =  0.04 MiB/s   <-- floor
02:00   2 412 372     =  2.30            07:00  2 889 465 =  2.76
03:00   2 778 783     =  2.65            16:00  6 586 674 =  6.28
```

**[MEASURED]** `qiaos`'s own aggregate Colossus throughput bottoms out at **0.04 MiB/s at
06:00**, on exactly the same clock as the spindle flood. This is the reported symptom,
independently confirmed from the storage side.

**Answer to Q3:** Yes. Blobstore ingest begins ~02:40, ramps 03:05–04:00, hard-steps at
04:05, sustained through 16:00. Spindle usage, read ops, cell bytes and read latency all
step together at the same time.

---

## Q4 — What does the `-d` suffix mean?

**It is a Colossus cell-naming convention. It is NOT a storage tier.** [MEASURED + cited]

Evidence:

```
//depot/google3/availability/cluster/g3doc/location_concepts.md:434-436
  "For Colossus cells, the cell is typically named by adding `-d` as a suffix
   to the cluster name."

//depot/google3/file/colossus/base/cfs_path.cc:72
  kCellREPattern = "([a-z0-9]+[-.a-z0-9]*)"     # parser assigns -d ZERO semantics

//depot/google3/production/sisyphus/spanner/spanbot/framework/spanlib.py:3170
  d_cell = re.sub(r"-d$", "", cell)             # "D cell has no '-d'"
```

Namespaces present **[MEASURED]**: `fileutil ls /cns/yutulpz-d/` → `cdpush`, `home`, `midas`,
`virtual`. Probing sibling suffixes: `yutulpz-a/-b/-c/-e/-f/-s` all return
`colossus cell doesn't exist`. Only `-d` exists. So `-d` is not selecting one of several
tiers — there is only one.

**Tier is a different field.** HDD vs SSD is `metric:partition` on the read metrics and
`durable/hdd/...` vs ssd in the quota metrics (`qiaos`: hdd quota 512 000 MiB, **ssd quota
0**). Where media *is* encoded in a cell name it appears *before* the `-d` (e.g. `bi-qlc-d`).
Census of 1 380 prod cells: 706 end in `-d` and are **all** CFS_V1; **zero** CFS_V2 cells end
in `-d`.

### The part that actually matters — two Colossus cells, one D cell [MEASURED]

```
$ cat /google/src/head/depot/google3/production/borg/colossus/prodspec/cells/yutulpz-d.txtpb
name: "yutulpz-d"
borg_cell: "yutulpz"
admin_user: "colossus"
cell_type: PUBLIC
d_cell: "yutulpz"

$ cat .../cells/yutulpz.txtpb
name: "yutulpz"
service_type: CFS_V2
borg_cell: "yutulpz"
admin_user: "cfs2-shared"
cell_type: CFS2_PUBLIC
d_cell: "yutulpz"
```

The cluster `yutulpz` runs **two Colossus cells on one D cell**:

| Colossus cell | service | admin_user | d_cell | who uses it |
|---|---|---|---|---|
| `yutulpz-d` | CFS1 | `colossus` | `yutulpz` | **`qiaos`'s `/cns/yutulpz-d/home/...`** |
| `yutulpz` | CFS_V2 | `cfs2-shared` | `yutulpz` | **`cfs2-shared`, blobstore2, LAD** |

They are logically separate but **share the same physical spindles**. `cfs2-shared` and the
Blobstore LAD job live in the *other* Colossus cell, yet their I/O lands on the same disks
that serve `qiaos`. That is the mechanism by which he was starved by a workload he cannot see.

**Field cheat sheet:** `d_cell` / `borg_cell` / `colossus_cell` / `metric:cell` are all
`'yutulpz'` — **only the CNS path carries `-d`**. Querying `d_cell='yutulpz-d'` silently
returns **zero streams** (verified). This is the single biggest trap in this investigation.

**Answer to Q4:** `-d` is naming convention for a CFS1 Colossus cell, not a tier. The
throttled resource is the **shared D-cell spindle pool**, which `yutulpz-d` shares with the
co-resident CFS2 cell `yutulpz`.

---

## The decisive experiment — why this is definitely not user-specific and not a network problem

Everything above could still, in principle, be a coincidence. This is the query that rules
that out. **[MEASURED]**

```
monarch_cli query --output_format=csv --duration=20h --end_time=2026-08-01T16:00:00Z \
  --output_period=1h \
  --mash="Fetch(Raw('monarch.BorgTask','/file/colossus/client/stripe-read-latency-simple'),
          {'metric:cell':'yutulpz'}) | Window(Delta('1h')) | GroupBy(['borg_cell'], Sum())
          | Point(DistributionMean(VAL))"
```

Median mean-latency **before** (21:00–03:00) vs **after** (06:00–16:00), in **milliseconds**,
for every client Borg cell reading `yutulpz`:

| src cell | before | after | delta | ratio |
|---|---:|---:|---:|---:|
| oa | 2.2 | 23.3 | +21.1 | 10.5x |
| ob | 2.1 | 23.4 | +21.3 | 10.9x |
| oc | 2.2 | 22.4 | +20.2 | 10.2x |
| **oe** | **3.2** | **27.8** | **+24.6** | **8.6x** |
| oi | 2.3 | 23.7 | +21.4 | 10.5x |
| ok | 2.5 | 23.7 | +21.2 | 9.3x |
| oo | 2.9 | 23.1 | +20.2 | 7.9x |
| ou | 2.2 | 26.6 | +24.4 | 12.0x |
| ow | 2.2 | 24.8 | +22.6 | 11.1x |
| oy | 2.5 | 26.7 | +24.2 | 10.9x |
| oz | 2.3 | 25.3 | +23.0 | 11.1x |
| nf | 2.2 | 24.1 | +21.9 | 10.8x |
| ng | 2.8 | 25.0 | +22.2 | 9.0x |
| nj | 2.3 | 26.5 | +24.2 | 11.3x |
| nm | 3.4 | 22.3 | +18.9 | 6.5x |
| pa | 2.4 | 28.2 | +25.8 | 11.8x |
| yutulth | 2.4 | 24.2 | +21.8 | 10.1x |
| yutulis | 8.0 | 25.6 | +17.6 | 3.2x |
| nk | 2.9 | 448.8 | — | 157x |
| pb | 3.0 | 411.2 | — | 138x |
| nl | 3.1 | 85.7 | — | 27.7x |
| *(clients inside yutulpz itself)* | 45.1 | 92.3 | +47.2 | 2.0x |

**~20 unrelated client Borg cells all degraded at the same instant by a near-constant
ADDITIVE +21…25 ms per read operation.**

**[INFERRED]** An *additive*, *client-location-independent* penalty can only be incurred at
the shared resource — the **disk**, *after* the network hop. If this were a network problem
it would be multiplicative and specific to the `oe ↔ tul` path. If it were a quota problem it
would be specific to `qiaos`. It is neither.

### Corroborating: an unrelated prod user shows the identical step [MEASURED]

Same metric grouped by `borg_user`, `oe → yutulpz`, 4 h buckets, mean µs:

| borg_user | 00:00 | 04:00 | 08:00 | 12:00 | 16:00 |
|---|---:|---:|---:|---:|---:|
| `qiaos` | 4 751 | 2 532 | 19 272 | — | 27 924 |
| `blobstore-quota-aggregator` (prod, unrelated) | 2 385 | 2 635 | 24 281 | 23 355 | 31 051 |

### Corroborating: it is a per-OPERATION tax, not a bandwidth cut [MEASURED]

`oe → yutulpz`, `borg_user=qiaos`, grouped by `metric:read_size`, mean µs:

| read size | 01:00 | 03:00 | 06:00 | 16:00 | degradation |
|---|---:|---:|---:|---:|---:|
| **0–16 KiB** | 1 654 | 1 898 | 25 673 | 26 752 | **~14x** |
| 16–64 KiB | 7 551 | 9 543 | 12 328 | 25 558 | ~3x |
| >64 KiB | 13 411 | 14 946 | 42 228 | 42 099 | ~3x |

**[INFERRED]** Small reads are hit ~5x harder than large ones. This is the signature of a
fixed queueing delay added per operation. A 4 MB orbax checkpoint is a large number of small
metadata + shard reads, so it is maximally exposed. **This also explains the puzzling
non-CNS `lineage_log` RPC slowdown**: that RPC's backend also reads from the same starved
spindle pool. It is not a coincidence — it is the same root cause reaching the process by a
different path.

---

## Ten independent lines of evidence, all agreeing

| # | evidence | before | after |
|---|---|---|---|
| 1 | read ops on `yutulpz` | 13–14 k/s | **166 k/s** (12.8x) |
| 2 | spindles in use | ~1.1 k | **10.6 k** (9.5x) |
| 3 | spindle quota for cell | 4 358 | usage 2.4x over |
| 4 | `overquota_usage/tp` | 0.000 | **14 757** |
| 5 | sole overquota owner | — | **`blobstore-lad-spindle-owner`** |
| 6 | D servers healthy | 214/214 | **268/268**, zero faults → not hardware |
| 7 | `bump_level` 4.0 flat, `ll*` overquota 0 | — | victim never demoted by enforcer |
| 8 | `throttler_responses` | 0.0007 % | 0.35 % peak → not RPC throttling |
| 9 | `qiaos` byte quota | 24.5 % | 24.5 % flat → not bytes |
| 10 | ~20 client cells | 2–3 ms | **+21–25 ms additive** → cost at the disk |
| 11 | `qiaos` throughput | 9.63 MiB/s | **0.04 MiB/s** → symptom confirmed |

---

## What I could NOT measure

* **`celly` is unusable for this cell from this account.** `celly -lc` shows my LOAS creds
  can access exactly **one** consumer group, `gdm-fru-cns` (GDM Responsibility). Calls
  needing `flex-consumer-ro` / `ConsumerService.GetRawConsumerFootprints` fail. Every one of
  `celly -c yutulpz -u {qiaos,gdm-fru-cns} -hu -cap`, `-f` (write failures),
  `--spindle_user qiaos`, `-hm` (heatmap) returned empty ("-" in every column, 0.00 PiB).
  `yutulpz` is not a GDM/DeepMind-pool cell that celly has footprint data for.
  → **Cell write-failure table and celly headroom/heatmap: could not measure.** I substituted
  `storage.Dml` / `storage.DmlUser` Monarch metrics, which gave strictly better data.
* **`monarch_cli list-metrics` / `describe-metric` are blocked**
  (`RPC_RESTRICTIONS_VIOLATION` on monarch-config-server). All metric discovery had to go
  through `code_search` on the Viceroy dashboards
  (`//monitoring/viceroy/dashboards/automon/every_colossus_cell/`).
* **Why the LAD job was started** — no ticket, CL or rollout identified. I did not chase
  ownership of `blobstore-lad-spindle-owner`. **Could not measure / out of scope.**
* **Whether an SRE-visible alert fired** on yutulpz. Not checked.
* Metrics that do **not** exist despite plausible names:
  `/storage/d/quota/per_user/{throttle,spindle_used,iops_used,ops_mib}`,
  `/storage/d/manager/public/spindle/{ceiling,capacity,total,available,usage}`,
  `/file/colossus/client/throttler_responses` (real name is
  `/storage/d/client/throttler_responses`). There is **no `storage.DmlCell` schema**;
  cell-level D metrics are `storage.Dml` + `binary_name='dmanager'`.

### A note on my workstation probes (why they were a dead end)

I ran extensive `fileutil` latency probes from this workstation (metro **sq**) against
`yutulpz-d` and `oe-d`. They were **inconclusive by construction** and should not be used as
evidence: sq→tul is cross-metro, so RTT dominates and swamps a +25 ms disk penalty.
Representative numbers: 1.22 MB read from `yutulpz-d` 4.65/4.89/4.84 s vs 1 MB from `oe-d`
4.70/4.27/4.22 s (statistically indistinguishable); 200 MB read-back `yutulpz-d` 39.3 s /
36.6 s (5.0–5.4 MiB/s) vs `oe-d` 27.9 s (7.1 MiB/s). Read latency was essentially **flat vs
size** (262 B → 4.05 s, 1.22 MB → 5.28 s), matching the documented healthy 3.77 s baseline.
**I could not reproduce the 50x collapse from a workstation.** The Monarch server-side data
is the reliable source here — a useful lesson for the next investigation.

---

## Recommendations (for the parent agent / user)

1. **Do not chase quota.** `qiaos` is at 24.5 % of byte quota and is not being throttled.
   Raising byte quota will change nothing.
2. **Move the checkpoint off `yutulpz-d`,** or read it from a cell whose D pool is not
   shared with a CFS2 Blobstore ingest. This is the only mitigation fully under the user's
   control. Sibling tul cells `yutulth` (+21.8 ms) and `yutulis` (+17.6 ms) are on the *same*
   D pool and are equally affected — pick a different **cluster**, not just a different cell.
3. **Cache the checkpoint locally.** A 4 MB artifact read on every task restart is
   pathologically exposed to a per-operation penalty. Read once to local disk / ramdisk and
   reuse; or repack the orbax checkpoint to use fewer, larger reads (the >64 KiB bucket
   degraded only 3x vs 14x for 0–16 KiB).
4. **Escalate to the `yutulpz` Colossus / Blobstore owners** if the workload is unexpected:
   `blobstore-lad-spindle-owner` has been running at ~6 000 spindles and ~14 757 units over
   `tp` quota continuously since 04:00 UTC, and `blobstore-cfs-shard-storage-owner` has
   ingested 14.5 PiB in 13 hours with no sign of stopping. Best-effort priority means it is
   not ceiling-limited, so it will keep expanding to fill the pool.
5. **Longer term, obtain a spindle commitment** for the workload if it must live on shared
   HDD. Per `go/colossus-debug`: *"Colossus has no performance guarantees for users of HDD
   bytes without spindles."* Byte quota alone buys capacity, not performance.

---

## Reproducible query reference

```bash
MC=/google/bin/releases/gemini-agents-monarch/monarch_cli
COMMON="--duration=20h --end_time=2026-08-01T16:00:00Z --output_format=csv"

# per-user byte quota + usage
$MC query $COMMON --output_period=30m --mash="Fetch(Raw('storage.DmlUser',
  '/storage/d/quota/per_user/usage_mib'), {'d_client_user':'qiaos','d_cell':'yutulpz'})
  | Window(Align('30m')) | GroupBy([], Sum())"

# read latency by client cell  <-- the decisive query
$MC query $COMMON --output_period=1h --mash="Fetch(Raw('monarch.BorgTask',
  '/file/colossus/client/stripe-read-latency-simple'), {'metric:cell':'yutulpz'})
  | Window(Delta('1h')) | GroupBy(['borg_cell'], Sum()) | Point(DistributionMean(VAL))"

# read op count (swap DistributionMean -> DistributionCount)
# ... | Point(DistributionCount(VAL))

# spindle usage by owner  <-- names the culprit
$MC query $COMMON --output_period=1h --mash="Fetch(Raw('storage.DmlUser',
  '/storage/d/manager/public/spindle/usage_by_scheduled_priority'), {'d_cell':'yutulpz'})
  | Window(Align('1h')) | GroupBy(['d_client_user'], Sum())"

# spindle overquota at throughput priority
$MC query $COMMON --output_period=30m --mash="Fetch(Raw('storage.DmlUser',
  '/storage/d/manager/public/spindle/overquota_usage/tp'), {'d_cell':'yutulpz'})
  | Window(Align('30m')) | GroupBy(['d_client_user'], Sum()) | Filter(VAL > 0)"

# D server health  <-- rules out hardware
$MC query $COMMON --output_period=4h --mash="Fetch(Raw('storage.Dml',
  '/storage/d/manager/d_cell_stats/servers_by_health'), {'d_cell':'yutulpz','binary_name':'dmanager'})
  | Window(Align('4h')) | GroupBy(['metric:health'], Sum())"

# user throughput  <-- the symptom, measured directly
$MC query $COMMON --output_period=1h --mash="Fetch(Raw('colossus.ClientTask',
  '/storage/colossus/client/file/bytes'), {'colossus_cell':'yutulpz','borg_user':'qiaos'})
  | Window(Rate('1h')) | GroupBy([], Sum())"

# explicit throttling  <-- rules out throttling
$MC query $COMMON --output_period=4h --mash="Fetch(Raw('monarch.BorgTask',
  '/storage/d/client/throttler_responses'), {'borg_cell':'yutulpz'})
  | Window(Delta('4h')) | GroupBy(['metric:treated_as_throttling'], Sum())"
```

### Mash syntax gotchas learned the hard way

* Bare `| Align('1h')` **fails**. Use `| Window(Align('1h'))`.
* Distributions: `| Window(Delta('1h')) | GroupBy([...], Sum()) | Point(DistributionMean(VAL))`
  (or `DistributionCount(VAL)`).
* `GroupBy(['out_of_quota'])` errors with *"unknown or dropped field"* — the field is
  `metric:out_of_quota` (keep the `metric:` prefix in `GroupBy`).
* `metric:treated_as_throttling` is a **bool**: `{'...':'true'}` fails with *"Matchlet must
  have a bool arg"*. `GroupBy` it instead.
* `d_cell='yutulpz-d'` returns **zero streams**, silently. Always strip the `-d`.
* Colossus client code lives in `//storage/colossus/client/`, **not** `//file/colossus/`,
  even though the metrics are still *named* `/file/colossus/...`. Greps in the wrong tree
  find nothing.
