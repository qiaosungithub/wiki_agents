# Choosing An Accelerator: Obtainability Beats Peak FLOPs

Measured 2026-08-10 21:02 → 08-11 15:44 UTC (18.7 h) by **really queueing**, not
by reading a capacity table: 180 Borg-verified v6p-64 acquisitions across four
probes, plus a v5p-128 probe and read-only observation of two v6e-64 jobs. Every
hold is keyed on the Borg `started` epoch and cross-checked against the raw
sample log. Raw data: `$AMPLY_ARTIFACT_DIR` of run `20260810-151959-5eb6c14e`
(`episodes.tsv`, `REPORT.md`, `FINDINGS.md`).

**The headline: a slice you cannot hold has no throughput, whatever its peak
FLOPs.** `tpu_reference.md` says v6p is 4.34x a v5p chip. Over this window v6p
delivered *less finished work than either alternative*, because the median hold
was shorter than one checkpoint interval.

## Pick In This Order

1. **v6e** — the default when it fits. One observed job ran **249 min
   continuous, 0 job/task failures**. Per chip it is half a v6p, and it is the
   only one of the three that reliably finishes.
2. **v5p** — a real fallback. Preempted 3 times (8.0 / 0.2 / 1.1 min) then got
   an 11.1 min window and **ran to SUCCESS**, writing its checkpoint.
3. **v6p** — only with the guard rails below. 180 acquisitions, **median hold
   2.3 min**, and long stretches of literally zero completed checkpoints.

Do not read this as a permanent ranking: it is one 18.7 h window on a market
that moves. Re-measure with a short probe before committing a long run — the
method matters more than the numbers.

## v6p-64, Measured

| | |
|---|---:|
| acquisitions | 180 |
| median hold | **2.3 min** |
| mean / p90 / max | 4.0 / 9.3 / 36.2 min |
| holds under 4 min | **68%** |
| holds over 10 min | 9% |
| median wait between grants | 6.2 min |
| duty cycle (hold / (hold+wait)) | **18%**, before cold-start cost |

Getting chips was never the problem — 180 grants in 18.7 h. **Keeping** them
was. With a 100-step (~6.3 min) checkpoint interval against a 2.3 min median
hold, most episodes cannot save anything before being preempted: over one
2-hour stretch, 12 acquisitions produced **zero** completed checkpoints, and one
was killed mid-write leaving a `.orbax-checkpoint-tmp` directory. Warm
throughput was a healthy 16 steps/min; net throughput was ~5% of a v7-32 running
the same code.

## Rules That Follow

**Judge a slice by finished checkpoints, not by hold time, and never by
`state: RUN`.** Hold time flatters a job that saves nothing. Join your episode
log against checkpoint mtimes and count only completed directories — a
`.orbax-checkpoint-tmp` is negative progress: time spent, preempted while
blocked on I/O.

**Keep the checkpoint interval below the median hold.** This is the whole
ballgame on a preemptible slice. Interval > median hold means the expected
number of saved steps is ~0 no matter how fast the chip is. Measure the hold
first, then set the interval — not the reverse.

**A capacity table does not predict acquisition.** Aligning the monitor's
verdict against the real queue minute by minute: **14 of 16 live-price samples
said `capped` while the queue was holding or granting v6p-64** — 12.5% accurate.
The cause is a granularity mismatch: preflight reads a *group*-level window
while grants are *cell*-level and opportunistic. At one instant tul granted,
cbf reported a 24-chip deficit, and nl a 15-chip one. Details and the price-cache
trap in `../infra/quota_market.md`.

> To know whether you can get a slice, **queue for one**. Use the table for
> price trends, never for a go/no-go.

**Availability moves by the hour, and no cell escapes it.** Every hold ≥10 min
began before 23:21; after that the pool degraded across all cells simultaneously
(exact permutation test, p=0.0187). Within the good era one cell was genuinely
better (tul median 23.9 vs 2.5 min, p=0.0130) — but in the bad era *that same
cell was the worst*. So "just use tul" is wrong. A short probe now beats any
remembered ranking.

**Beware confounds when comparing cells.** The strong cell effect above was
half an artifact: tul was also the cell sampled earliest and most, so "cell" and
"hour of night" were confounded. Before believing any grouping, ask whether the
groups differ in *when* they were sampled. Deconfound by launching the same ask
into a second cell/group in the same window.

## Probing Before You Commit

Cheap and worth it before any long run on a preemptible tier:

```bash
tpu queue --tpu_type=<type> --group=<g> --tier=PROD --cell=<cell> \
          --bucket=<co-located CNS path> -n <probe-name>
```

- Use the **real workload**, not a trivial one. A sleep loop cannot show whether
  preemption is interrupting useful work, and gives no comparable throughput.
- Pick a bucket in the **compute cell's own metro** (`../storage.md`); a
  cross-metro checkpoint path silently costs 4-5x and can get the job pruned.
- Judge from **Borg** (`borg --borg=<cell> findjobs --user_re=<user>`), whose
  `state:` and `started` are authoritative. XManager reported RUNNING for jobs no
  cell knew about (`../jobs.md` §`state: RUN` Is Not Evidence).
- A terminal state (`SUCCESS`/`FAILURE`) **persists in `findjobs` output**. Use
  the first terminal sample as the end time; "last seen" over-counts a finished
  job by hours.
- Never run `tpu queue` in a foreground call that can time out: **a killed
  `tpu queue` still submits**, leaving an orphan XID.
