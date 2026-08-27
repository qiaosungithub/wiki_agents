# Choosing An Accelerator: Obtainability Beats Peak FLOPs

**Do not ask the operator which card or cell to use — they do not know, and
the answer moves daily. Decide it yourself from three live checks:** the
clearing price is affordable (`tpu route --power=<slice>` prints cost/hr; cross
with `budget_check.py`), a cell in the DATA's own metro can hold it (`tpu
preflight --json` `cells_ok` ∩ the metro of your CNS bucket, via `mach_locality
-k metro`), and the slice is actually obtainable there. Only escalate a genuine
tradeoff the checks cannot settle (e.g. every affordable cell is cross-metro).
Re-run the checks each time; a remembered ranking is wrong within a day — e.g.
"v4 is cheapest" flipped when v6p PROD cleared at ~2/chip (cost/hr 64 for a
v6p-32) while v4-256 cost ~1600.

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

## There Is No Fixed Ranking — Decide Live, Every Time

**Which card holds best flips day to day and hour to hour; never carry a
ranking between runs.** Any list of "use X, then Y" in this file is stale within
a day. Before every long run, run these live checks and let *them* pick, in this
order:

1. **Which cards a limit order is blocking RIGHT NOW** — `tools/limit_order.sh
   status` (or read `tpu money`). A card whose pool-wide clearing price sits
   above an in-force cap is un-gettable at PROD *no matter how much capacity it
   shows*, and moving to a cheaper cell does NOT help (the cap is pool-wide).
   Which cards are blocked changes daily and is the single fastest way to rule
   options out.
2. **Price you can afford** — `tpu route --power=<slice>` for cost/hr, crossed
   with `tools/budget_check.py`. Cheapest card ≠ same card as yesterday.
3. **Obtainability in your data's metro** — a capacity table does not predict
   acquisition (see below). Queue a short probe with the REAL workload and
   judge from Borg.

How wrong a remembered ranking gets, concretely: the 18.7 h window below
(2026-08-10) found v6e the most reliable and v6p the worst — and on 2026-08-21
v6e and v5e PROD were **limit-order-blocked pool-wide** (un-gettable at any
cell), v5p cleared at **0.0**, and v7 cleared **cheaper than v6p** — i.e. the
exact inversion of that ranking, ten days later. The window is kept below only
as *method evidence* for the durable rule (**a slice you cannot hold has no
throughput**), never as a card recommendation. Re-measure every time; the
method is the asset, the numbers are disposable.

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
tpu enqueue --power=<type> \
  --launch=group=<g>,tier=PROD,cell=<cell>,bucket=<co-located CNS path>,exp_name=<probe-name>
tpu build-worker start   # serial worker drains it (the default path — ../jobs.md)
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
- **`tpu enqueue` returns instantly**, so a timed-out launch call no longer
  risks the orphan submit a foreground `tpu queue` did (a killed `tpu queue`
  still submits). The serial build-worker can still yield a 0-work-unit zombie
  XID if a build fails — spot it (no work units) with `tpu queue-status` /
  `tpu check` and read it as a launcher-side failure (`../jobs.md`).
