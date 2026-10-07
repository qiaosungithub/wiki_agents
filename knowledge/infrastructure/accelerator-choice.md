# Choosing An Accelerator: Obtainability Beats Peak FLOPs

Owns the measured evidence that a slice you can hold beats peak FLOPs when
choosing an accelerator family, and the rules that follow from it. The live
checks that pick a family, and probing before you commit, are
[unschedulable-job skill §There Is No Fixed Ranking — Decide Live, Every Time](../../harness/skills/unschedulable-job/SKILL.md#there-is-no-fixed-ranking--decide-live-every-time)
and [unschedulable-job skill §Probing Before You Commit](../../harness/skills/unschedulable-job/SKILL.md#probing-before-you-commit) in the
[unschedulable-job](../../harness/skills/unschedulable-job/SKILL.md) skill. Per-chip ratios are
[knowledge/infrastructure/tpu-reference.md](tpu-reference.md); why a job will not schedule is [knowledge/infrastructure/market.md](market.md).

Measured 2026-08-10 21:02 → 08-11 15:44 UTC (18.7 h) by really queueing, not from
a capacity table: 180 Borg-verified v6p-64 acquisitions over four probes, plus a
v5p-128 probe and two observed v6e-64 jobs. Holds are keyed on the Borg `started`
epoch. Raw data: `$AMPLY_ARTIFACT_DIR` of run `20260810-151959-5eb6c14e`
(`episodes.tsv`, `REPORT.md`, `FINDINGS.md`).

A slice you cannot hold has no throughput. [knowledge/infrastructure/tpu-reference.md](tpu-reference.md) rates v6p at 4.34x
a v5p chip, yet v6p finished less work than either alternative here: its median
hold was under one checkpoint interval.

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
Details and the price-cache trap: [knowledge/infrastructure/market.md](market.md).

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
