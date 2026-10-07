---
name: unschedulable-job
description: Use when a job will not schedule, is `BUDGET_DEFERRED`, or was paused or cancelled by the income/10 cap, when checking, setting, or verifying a price cap with `tools/limit_order.sh`, or when choosing and probing an accelerator before committing a long run.
---

# A Job Will Not Schedule

This skill relies on knowledge pages for the facts: [knowledge/infrastructure/market.md](../../../knowledge/infrastructure/market.md) owns
the allocator model, tiers, price-cap semantics, and why a job will not schedule;
[knowledge/infrastructure/budget.md](../../../knowledge/infrastructure/budget.md) owns the income/10 gates and the enforcer;
[knowledge/infrastructure/accelerator-choice.md](../../../knowledge/infrastructure/accelerator-choice.md) owns the measured hold times and the rules
that follow from them; [knowledge/infrastructure/v7-storage-placement.md](../../../knowledge/infrastructure/v7-storage-placement.md) owns where v7 can
run next to its data; [knowledge/infrastructure/tpu-reference.md](../../../knowledge/infrastructure/tpu-reference.md) owns names, legal shapes, and
per-chip ratios. This skill owns the checks and the commands. A CPU-only batch
job that will not schedule is [job-submit skill §Tiers and CPU-only](../job-submit/SKILL.md#tiers-and-cpu-only).

Chapter 1 is triage for a job that will not schedule or was paused. Chapter 2 is
choosing and probing an accelerator before committing a long run.

---

## Chapter 1 — Triage

### Check for someone else's cap first

**Because a teammate's group-wide cap silently applies to your jobs, "my job is
pending for no reason" is frequently someone else's cap. Check that before
debugging anything else.** The scope rules are
[knowledge/infrastructure/market.md §Price Caps (Limit Orders)](../../../knowledge/infrastructure/market.md#price-caps-limit-orders).

### Set a cap with limit_order.sh

**Set a cap with [`tools/limit_order.sh`](../../../tools/limit_order.sh); it is read-first and refuses group
scope by default.** `status [accel]` prints the live clearing price beside every
cap in force and marks each `BLOCKING` or `ok`, answering "is a cap even the
problem?" before you change anything. `show-xid <xid>` resolves which group and
accelerator a cap would attach to. Writes are dry-run unless `--apply`, and
`set-group` additionally demands `--i-understand-group-scope`. The experiment
level (`--xid`) is verified available; group level is unverified on purpose,
because testing it honestly means writing a cap that hits every member's jobs.

How the cap value is derived (a multiple of a reference quantile) is
[knowledge/infrastructure/market.md §Price Caps (Limit Orders)](../../../knowledge/infrastructure/market.md#price-caps-limit-orders).

### Verify a cap from the client side

**Verify from the client side, but do not trust the unit record's "paused by
limit order" flag** — it is written at a different pipeline stage and reads
false while the decision row already carries a cap price. The money command
shows each allocation's cap against the live price range, flags it
fine/partially/fully blocking, and names who set it; the router lists candidates
excluded by a triggered cap. Ground truth is the quota database: the cap table
names the responsible user, the price table the cleared price per cell and tier,
the per-unit decision table the verdict.

### Querying The Gate Before You Launch

**`budget_check.py --query <type> <tier> <lo_price> <group>` prints one JSON
line and exits 0 (fits) or 3 (over bar).** It is the machine-readable probe the
router's greedy loop calls per candidate; it reads the registry live every call,
so each just-submitted job is reflected in `current`.

```
$ budget_check.py --query gb200-8 PROD 0.20 g9
{"income": 25811.0, "bar": 2581.1, "current": 2132.4, "headroom": 448.7,
 "new_cost": 1.6, "exempt": false, "fits": true}
```

- `bar = income/10`, shared fleet-wide. `current` is your live aggregate.
  `headroom = bar - current`, and it swings hard (it can read negative one
  minute and positive the next as other jobs start and stop).
- A job dispatches only when `headroom >= new_cost`. If it does not fit, the
  launch path prints `[[BUDGET_DEFERRED]]` and the router parks the job
  `BUDGET_DEFERRED` (auto-retried every round, never counted as a build attempt,
  so it is never HELD) rather than treating it as a build failure.

Run `budget_check.py <type> <tier>` (no `--query`) for the human-readable gate
the launcher runs before every launch ([knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md)).

### Match the symptom to its cause

Find what you see in the left column and read the section it names.

| You see | Read |
|---|---|
| PENDING for hours with no failure | [job-submit skill §PENDING that is not a failure](../job-submit/SKILL.md#pending-that-is-not-a-failure) |
| PENDING, or preempted every few minutes, and the deficit names a platform but no cell | [knowledge/infrastructure/market.md §An Adjusted Ceiling Is A Pool Cap, Not A Cell Shortage](../../../knowledge/infrastructure/market.md#an-adjusted-ceiling-is-a-pool-cap-not-a-cell-shortage) |
| Preflight reports obtainable chips, yet the slice keeps being taken away | [knowledge/infrastructure/market.md §Obtainability Says A Slice Can Be Got; The Cap Decides How Long It Is Held](../../../knowledge/infrastructure/market.md#obtainability-says-a-slice-can-be-got-the-cap-decides-how-long-it-is-held) |
| You need a hold-time number to compare cells or families | [knowledge/infrastructure/market.md §Measuring Hold Time: Three Traps That Each Fabricate A Number](../../../knowledge/infrastructure/market.md#measuring-hold-time-three-traps-that-each-fabricate-a-number) |
| A PROD job is held because its family's price is over the fixed per-family cap | the closing paragraphs of [knowledge/infrastructure/tpu-reference.md §Per-Chip Capability (v5p-normalised)](../../../knowledge/infrastructure/tpu-reference.md#per-chip-capability-v5p-normalised) |
| A cheap job is deferred on a price it never pays | [knowledge/infrastructure/budget.md §The Projection Trap: A Cheap Job Priced As Expensive At The Gate](../../../knowledge/infrastructure/budget.md#the-projection-trap-a-cheap-job-priced-as-expensive-at-the-gate) |
| A long GPU job vanished | [knowledge/infrastructure/budget.md §Mispricing Kills Jobs — The Biggest Measured Survival Threat On GPU](../../../knowledge/infrastructure/budget.md#mispricing-kills-jobs--the-biggest-measured-survival-threat-on-gpu) |
| Running jobs in a free-pool family were cancelled | [knowledge/infrastructure/budget.md §The Two Gates Disagreeing Is A Pump](../../../knowledge/infrastructure/budget.md#the-two-gates-disagreeing-is-a-pump), [knowledge/infrastructure/budget.md §A Free PROD Row Read As BATCH's Price](../../../knowledge/infrastructure/budget.md#a-free-prod-row-read-as-batchs-price) |
| A pricing fix is on disk but the enforcer still prices the old way | [knowledge/infrastructure/budget.md §A Daemon Prices From The Table It Imported At Startup](../../../knowledge/infrastructure/budget.md#a-daemon-prices-from-the-table-it-imported-at-startup) |
| The enforcer reports over cap but skips every candidate as dead | [knowledge/infrastructure/budget.md §A Stale Ledger Manufactures An Overage That Is Not Live Spend](../../../knowledge/infrastructure/budget.md#a-stale-ledger-manufactures-an-overage-that-is-not-live-spend) |
| The pause logged OK but the job never came back | [knowledge/infrastructure/budget.md §A Stop That Reports OK May Not Have Re-Queued](../../../knowledge/infrastructure/budget.md#a-stop-that-reports-ok-may-not-have-re-queued) |

---

## Chapter 2 — Choose And Probe An Accelerator Before Committing

### Do not ask the operator which card to use

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

### There Is No Fixed Ranking — Decide Live, Every Time

**Which card holds best flips hour to hour, so never carry a ranking between
runs.** Run these checks in order and let them pick:

| # | Check | How |
|---|---|---|
| 1 | Which cards a limit order blocks now | `tools/limit_order.sh status`, or read `tpu money`. A card clearing pool-wide above an in-force cap is un-gettable at PROD, whatever capacity it shows; a cheaper cell does not help, the cap is pool-wide. The blocked set changes daily, so this rules out fastest. |
| 2 | Price you can afford | `tpu route --power=<slice>` for cost/hr, crossed with `tools/budget_check.py`. The cheapest card is not yesterday's. |
| 3 | Obtainability in your data's metro | See below: a capacity table does not predict acquisition. Probe with the real workload; judge on Borg. |

The evidence that no ranking lasts a day is [knowledge/infrastructure/accelerator-choice.md](../../../knowledge/infrastructure/accelerator-choice.md);
why a capacity table does not predict acquisition is
[knowledge/infrastructure/accelerator-choice.md §Rules That Follow](../../../knowledge/infrastructure/accelerator-choice.md#rules-that-follow).

### Probing Before You Commit

Cheap, and worth it before any long run on a preemptible tier:

```bash
tpu enqueue --power=<type> --metros=<data-metro[,metro2]> \
  --launch=group=<g>,tier=PROD,bucket=<co-located CNS path>,exp_name=<probe-name>
# the always-on tpu dispatch-worker drains the queue on its own — no build-worker to start (../jobs.md)
```

- **Data-locality is `--metros`, not a hand-pinned `cell=`.** `--power` picks the
  cheapest obtainable (arch, chips, cell); `--metros=<m>` confines that pick to
  your data's metro(s), comma-separated for several. A full metro makes it refuse
  rather than roam to a no-data cell (fail-closed). Pin `cell=` in `--launch`
  only to hit one exact cell; `--metros` is less brittle. Before 2026-08
  `--power` ignored `--metro` and you hand-pinned; fixed, and `--power`+`--metros`
  compose ([knowledge/infrastructure/router.md](../../../knowledge/infrastructure/router.md)).
- Use the real workload. A sleep loop shows neither whether preemption
  interrupts useful work nor comparable throughput.
- Bucket in the compute metro you named ([knowledge/infrastructure/storage.md](../../../knowledge/infrastructure/storage.md)). A cross-metro
  checkpoint path silently costs 4-5x and can get the job pruned.
- Judge on Borg (`borg --borg=<cell> findjobs --user_re=<user>`): its `state:`
  and `started` are authoritative. XManager reported RUNNING for jobs no cell
  knew of ([job-diagnose skill §`state: RUN` Is Not Evidence That Anything Runs](../job-diagnose/SKILL.md#state-run-is-not-evidence-that-anything-runs)).
- A terminal state (`SUCCESS`/`FAILURE`) persists in `findjobs` output. Take the
  first terminal sample as the end time; "last seen" over-counts by hours.
- `tpu enqueue` returns instantly, so a timed-out launch no longer risks the
  orphan submit a foreground `tpu queue` did (a killed `tpu queue` still
  submits). A failed build can still leave a 0-work-unit zombie XID. Spot it (no
  work units) with `tpu queue-status` / `tpu check`, and read it as launcher-side
  failure ([knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md)).

### How To Regenerate The v7 Placement Survey

The survey this regenerates, and the standing decision drawn from it, are
[knowledge/infrastructure/v7-storage-placement.md](../../../knowledge/infrastructure/v7-storage-placement.md).

1. **v7 cells**: read `~/.tpu_quota_cache_dir/market.json` under
   `prices.<pool>|<code>|PROD`, keyed by an internal card code (v7 was `101`;
   verify a known v7 cell appears under it). The `tpu money` table prints only a
   few sample cells per card, so read the cache, not the table.
2. **Storage cells with a ceiling**: `flex.par ls --group=<accounting-group>
   --service=colossus` lists every registered cell with its disk ceiling and
   spindle commitment. It is authoritative; `fileutil quota` is not
   ([knowledge/infrastructure/storage.md](../../../knowledge/infrastructure/storage.md)).
3. **Join on metro**: `mach_locality -k metro <cell>` for both sides;
   parallelize with `xargs -P`, one RPC per cell.
4. **Obtainable chips per cell**: `tpu preflight --tpu_type=v7-32 --group=<g>
   --json` returns a `cells_ok` list with an obtainable count each.

   **4b. Free contiguous slices per cell**: `stubby call
   master.<cell>.borg:9413 BorgMaster.ProbeSliceAvailability 'slices {
   locus_type: "locus:DEPLOYMENT_TYPE_GHOSTFISH_LITE:2_4_4" } priority: 200'`,
   summing `num_free_slices` over the pods. Reachable on an ordinary credential,
   one RPC per cell; the shape uses UNDERSCORES (`2x4x4` is rejected as an
   invalid locus). Do this one too: a metro can hold thousands of obtainable
   chips and **one** placeable v7-32.

5. **Confirm with a real job**, not just numbers: submit the same smoke to each
   candidate metro. Checkpoints should land on CNS with
   `capacity_quota_user: deepmind-resources-colossus`, which keeps the 500 GiB
   personal ceiling out of the picture.
