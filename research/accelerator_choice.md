# Choosing An Accelerator: Obtainability Beats Peak FLOPs

**Do not ask the operator which card or cell to use; they do not know, and the
answer moves daily.** Decide from three live checks.
Price: `tpu route --power=<slice>` prints cost/hr, crossed with
`budget_check.py`.
Locality: `tpu preflight --json` `cells_ok` ∩ the metro of your CNS bucket, via
`mach_locality -k metro`, so the cell sits in the DATA's own metro.
Obtainability: is the slice free there.
Escalate only what the checks cannot settle, e.g. every affordable cell is
cross-metro. Re-run them each time; a remembered ranking is a day stale. "v4 is
cheapest" flipped when v6p PROD cleared at ~2/chip (cost/hr 64 for a v6p-32)
against ~1600 for a v4-256.

Measured 2026-08-10 21:02 → 08-11 15:44 UTC (18.7 h) by really queueing, not from
a capacity table: 180 Borg-verified v6p-64 acquisitions over four probes, plus a
v5p-128 probe and two observed v6e-64 jobs. Holds are keyed on the Borg `started`
epoch. Raw data: `$AMPLY_ARTIFACT_DIR` of run `20260810-151959-5eb6c14e`
(`episodes.tsv`, `REPORT.md`, `FINDINGS.md`).

A slice you cannot hold has no throughput. `tpu_reference.md` rates v6p at 4.34x
a v5p chip, yet v6p finished less work than either alternative here: its median
hold was under one checkpoint interval.

## There Is No Fixed Ranking — Decide Live, Every Time

**Which card holds best flips hour to hour, so never carry a ranking between
runs.** Run these checks in order and let them pick:

| # | Check | How |
|---|---|---|
| 1 | Which cards a limit order blocks now | `tools/limit_order.sh status`, or read `tpu money`. A card clearing pool-wide above an in-force cap is un-gettable at PROD, whatever capacity it shows; a cheaper cell does not help, the cap is pool-wide. The blocked set changes daily, so this rules out fastest. |
| 2 | Price you can afford | `tpu route --power=<slice>` for cost/hr, crossed with `tools/budget_check.py`. The cheapest card is not yesterday's. |
| 3 | Obtainability in your data's metro | See below: a capacity table does not predict acquisition. Probe with the real workload; judge on Borg. |

How stale: the 18.7 h window below (2026-08-10) found v6e most reliable, v6p
worst. Ten days later (2026-08-21) v6e and v5e PROD were limit-order-blocked
pool-wide (un-gettable at any cell), v5p cleared at 0.0 and v7 cheaper than v6p:
the exact inversion. Keep the window as method evidence, not a card
recommendation.

## v6p-64, Measured

| | |
|---|---:|
| acquisitions | 180 |
| median hold | 2.3 min |
| mean / p90 / max | 4.0 / 9.3 / 36.2 min |
| holds under 4 min | 68% |
| holds over 10 min | 9% |
| median wait between grants | 6.2 min |
| duty cycle (hold / (hold+wait)) | 18%, before cold-start cost |

**Getting chips was never the problem (180 grants in 18.7 h); keeping them was.**
A 100-step (~6.3 min) checkpoint interval against a 2.3 min median hold means
most episodes cannot save before preemption. One 2-hour stretch of 12
acquisitions produced zero completed checkpoints. Warm throughput 16 steps/min,
net ~5% of a v7-32 on the same code.

## Rules That Follow

**Judge a slice by finished checkpoints, not hold time, and never by
`state: RUN`.** Hold time flatters a job that saves nothing. Join your episode
log against checkpoint mtimes and count only completed directories. A
`.orbax-checkpoint-tmp` is negative progress: preempted while blocked on I/O.

Keep the checkpoint interval below the median hold. A longer interval means ~0
expected saved steps, however fast the chip. Measure the hold first, then set the
interval.

A capacity table does not predict acquisition. Minute by minute against the real
queue, 14 of 16 live-price samples said `capped` while the queue was holding or
granting v6p-64: 12.5% accurate. The cause is a granularity mismatch. Preflight
reads a *group*-level window, while grants are *cell*-level and opportunistic.
Details and the price-cache trap: `../infra/quota_market.md`.

> To know whether you can get a slice, queue for one. Use the table for price
> trends, never for a go/no-go.

Availability moves by the hour, and no cell escapes it. Every hold ≥10 min began
before 23:21; after that the pool degraded across all cells at once (exact
permutation test, p=0.0187). In the good era one cell was better (tul median 23.9
vs 2.5 min, p=0.0130); in the bad era that same cell was worst. So "just use tul"
is wrong: run a short probe now.

Beware confounds when comparing cells. That effect was half an artifact: tul was
sampled earliest and most, confounding "cell" with "hour of night". Ask whether
groups differ in *when* they were sampled, and deconfound by launching the same
ask into a second cell/group in the same window.

## Probing Before You Commit

Cheap, and worth it before any long run on a preemptible tier:

```bash
tpu enqueue --power=<type> --metros=<data-metro[,metro2]> \
  --launch=group=<g>,tier=PROD,bucket=<co-located CNS path>,exp_name=<probe-name>
tpu build-worker start   # serial worker drains it (the default path — ../jobs.md)
```

- **Data-locality is `--metros`, not a hand-pinned `cell=`.** `--power` picks the
  cheapest obtainable (arch, chips, cell); `--metros=<m>` confines that pick to
  your data's metro(s), comma-separated for several. A full metro makes it refuse
  rather than roam to a no-data cell (fail-closed). Pin `cell=` in `--launch`
  only to hit one exact cell; `--metros` is less brittle. Before 2026-08
  `--power` ignored `--metro` and you hand-pinned; fixed, and `--power`+`--metros`
  compose (`../infra/tpu_cli.md`).
- Use the real workload. A sleep loop shows neither whether preemption
  interrupts useful work nor comparable throughput.
- Bucket in the compute metro you named (`../storage.md`). A cross-metro
  checkpoint path silently costs 4-5x and can get the job pruned.
- Judge on Borg (`borg --borg=<cell> findjobs --user_re=<user>`): its `state:`
  and `started` are authoritative. XManager reported RUNNING for jobs no cell
  knew of (`../jobs.md` §`state: RUN` Is Not Evidence).
- A terminal state (`SUCCESS`/`FAILURE`) persists in `findjobs` output. Take the
  first terminal sample as the end time; "last seen" over-counts by hours.
- `tpu enqueue` returns instantly, so a timed-out launch no longer risks the
  orphan submit a foreground `tpu queue` did (a killed `tpu queue` still
  submits). A failed build can still leave a 0-work-unit zombie XID. Spot it (no
  work units) with `tpu queue-status` / `tpu check`, and read it as launcher-side
  failure (`../jobs.md`).
