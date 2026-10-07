# The Accelerator Market

How chip-hours are priced and why a job will not schedule: the allocator model,
tiers, price caps, and the data behind them. The income/10
spend gates that sit on top of this market are [knowledge/infrastructure/budget.md](budget.md), and the `tpu` tool
that reads it is [knowledge/infrastructure/tpu-cli.md](tpu-cli.md). Read this when a job will not schedule and
[knowledge/infrastructure/cluster-jobs.md](cluster-jobs.md) does not explain it, or before setting any price cap. The procedure for a job that will not
schedule, including checking, setting, and verifying a price cap, is the
[unschedulable-job](../../harness/skills/unschedulable-job/SKILL.md) skill.

**This file prices the accelerator market only.** Everything here is chip-hours
and is irrelevant to a CPU-only job, which bills in GCU against a different
ledger; an unschedulable CPU job is almost never a market outcome
([knowledge/infrastructure/cluster-jobs.md §Groups](cluster-jobs.md#groups)). These mechanisms change: live state and
current source outrank this page, so re-verify before depending on a detail.

This page is also the entry point to the infra pages: deep background on the
cluster's allocation and tooling. **Read [knowledge/infrastructure/cluster-jobs.md](cluster-jobs.md) first**: it covers
launching, inspecting, resuming, and debugging a job. Come here only when the
basics do not explain what you see, or when changing the tooling itself. Each
infra page is organized into **Principle** (how it works), **Usage** (how to
drive it), and **Errors** (what breaks and the fix); a Usage or Errors section that is a
step-by-step procedure lives in one of the two skills in the table.

| Read | When |
|---|---|
| This page | A job will not schedule and [knowledge/infrastructure/cluster-jobs.md](cluster-jobs.md) does not explain it; you are setting a price cap; you need credits, floors, or tier behavior; you need the quota database or the router's market cache. |
| [knowledge/infrastructure/budget.md](budget.md) | A job is `BUDGET_DEFERRED`, or a running job was paused/cancelled and you suspect the income/10 cap; you are touching `budget_check.py` or the `budget_enforcer` daemon. |
| [knowledge/infrastructure/tpu-cli.md](tpu-cli.md) | You are changing, rebuilding, or debugging the `tpu` CLI, its checkers, its cache daemon, its job registry, or preflight. |
| [knowledge/infrastructure/router.md](router.md) | You are changing the smart cell-picker, the local queue and auto-reroute, or the serial build-worker; a concurrent-build zombie or a HELD/BUDGET_DEFERRED queue entry. |
| [unschedulable-job](../../harness/skills/unschedulable-job/SKILL.md) | The procedure: a job will not schedule or was paused by the income/10 cap; checking, setting, or verifying a price cap; choosing and probing an accelerator before committing. |
| [tpu-tooling](../../harness/skills/tpu-tooling/SKILL.md) | The procedure: rebuilding the checkers or the router, running the worker and the queue, invoking `npu`, running the enforcer by hand, debugging a frozen board. |

Chapter 1 is the principle: the allocator model and what money buys. Chapter 2
is price caps and the data behind them. Chapter 3 is why a job will not
schedule.

---

## Chapter 1 — Principle

### The Allocator Model

**On a dynamic (market) pool, quota is an output of the market, not an input.**
Credits fund a bid, a periodic auction clears a price, and your floor is
recomputed each cycle from that result. Static pools are the opposite: fixed,
human-configured floors, no credits. Money buys quota on a dynamic pool; on a
static pool, asking for more of it is meaningless.

- A floor is a floor, not a ceiling. You may exceed it opportunistically. There
  is no per-allocation hard chip ceiling; the caps that exist are pool-level,
  lead-level, or economic (they cap the bill, not usage). Any floor number is
  one auction cycle's snapshot, not an entitlement, so a config file and live
  state disagreeing is normal.
- The two tiers are one pipeline, not two systems. They differ in which
  scheduling pass they enter, not in whether the market is involved.
- The admission test is neither AND nor OR. It is an ordered multi-pass pipeline
  over one shared pool capacity: money and floor decide which bucket you are in,
  and when your turn comes the only test is whether stock is left.

| | Guaranteed tier | Batch tier |
|---|---|---|
| Passes | lease bucket first (free, no bidding), then market bucket (needs credits) | processed last, and that pass **never checks your floor** |
| Admission test | lease-covered demand is subtracted before the market sees it | only whether the request fits what remains of the root pool |
| Price caps | exempt for the lease-covered part | **not** exempt |
| On rejection | can be *queued* instead, re-evaluated each cycle | — |
| Reclaim | not preemption-proof; same-priority defragmentation evicts it | above floor by construction, so first reclaimed |

**A batch job therefore runs fine with a floor of zero, and "batch quota" is a
meaningless number**: only live pool headroom matters, and an empty batch
allotment is a designed state, not a broken allocation. Neither waiting nor
asking for more helps.

### Money Buys Two Different Things

**Bid and balance are not the same money.** Do not conflate them: a large
balance with tiny income still bids well for a while.

| Form | Buys | Shape |
|---|---|---|
| Bid (a flow, from income times leverage) | your protected floor | floor is downstream of it |
| Balance (a stock) | your opportunistic share above floor | scales the importance factor |

**Prices are per chip-hour**, so multiply by the slice size for an hourly cost.
Raising a cap costs nothing by itself, but you are then charged the clearing
price for usage, draining the balance faster. Cells still matter for cost though
not for a cap: charging reads per-cell rates, so the router picks the cheapest
cell while deciding blocked-or-not from the global price.

---

## Chapter 2 — Usage

### Price Caps (Limit Orders)

**A limit order is a maximum price per chip-hour a workload will pay; it is a
number a person typed, not a system parameter.**

- When the market clears above it, a pending job is pulled from the queue before
  any capacity check, so free capacity and idle chips do not help. A running job
  is paused and resumes automatically when the price drops; the job does not
  die.
- The comparison uses the pool-wide price, not a per-cell price. The auction
  merges every cell into one synthetic global layer, so the cap table has no
  cell column. Moving a job to a cheaper cell does not unblock a triggered cap;
  pin cells for cost only. The real fixes are a different allocation, a different
  tier, or raising/removing the cap.
- The comparison is per chip-hour, not multiplied by the chip count. It is a
  strict greater-than, so clearing exactly at the cap is affordable, and the
  lease exemption is all-or-nothing, so mostly-leased demand is still fully
  paused. A pool price of zero can mean "no price computed this cycle" rather
  than "free".

**Scope resolves most-granular-wins: schedulable unit, then experiment, then
group.**

| Level | Who it affects |
|---|---|
| Schedulable unit | one unit; only the low-level tool can set it |
| Experiment | one experiment, yours. Overrides the group baseline and is not overwritten by the periodic group push, so it is the intended escape hatch for urgent work |
| Group | every job in the group, everyone's. Raising it requires no permission but changes everyone's spend |

There is no implicit default cap: no row means the
reason can never fire.

The cap is a multiple of a reference quantile of recent prices, and the multiple
matters: a median reference means the job runs roughly half the time. Prices
move several-fold within a day, so a non-urgent default pauses jobs during
ordinary swings. Prefer raising the multiple over raising the quantile, because
a very high quantile disables the cap. The launcher sets a per-experiment cap at
launch, with flags to change or skip it; failing to set it never fails the
launch, because a submitted uncapped job beats a launch that looks broken.

Checking whether a cap is what blocks your job, and setting and verifying
one, is the [unschedulable-job](../../harness/skills/unschedulable-job/SKILL.md#check-for-someone-elses-cap-first) skill.

### Reading The Underlying Data

**Prices, floors, caps, and per-unit decisions live in the quota database and
are readable directly with plain credentials — the reliable path from a
workstation.** Resource types are keyed by numeric id in some tables and enum
name in others ([knowledge/infrastructure/tpu-reference.md](tpu-reference.md) has the mapping).

- **To answer "where does this accelerator exist at all", read the router's
  market cache** (`~/.tpu_quota_cache_dir/market.json`), which lists every cell
  with a price. The money command's summary only samples cells per accelerator,
  so its table understates availability. Entries are keyed by an internal card
  code; confirm the code by checking that a cell you already run on appears
  under it.
- The browser resource UI is authoritative for allocations, one allocation's
  detail, and whole-pool usage; a command-line fetch just redirects through the
  SSO proxy.
- Known blocker: the convenience CLI calls an RPC a restricted credential cannot
  reach, and re-authenticating does not fix it (the credential carries a
  destination allowlist this service is not on). The lower-level binary reaches
  the same state under plain credentials over a different path (querying the
  database instead of the RPC), which is why some read paths keep working.
- Known gaps: per-cycle price history exists but one aggregated history table is
  empty and misleads; the quota table's compact notation marks the smaller
  number as quota, easy to misread; and the bidding-power figure the CLI prints
  does not reproduce from the database, so re-verify the formula before trusting
  it.

---

## Chapter 3 — Errors: Why A Job Will Not Schedule

### An Adjusted Ceiling Is A Pool Cap, Not A Cell Shortage

**A job can sit PENDING, or be preempted every few minutes, because the dynamic
root pool is capped below its nominal size — and the work unit's own message is
the only place this is legible.** Read it structurally: the deficit is per
platform (`ghostfish` = v6p) and names no cell, so g1/g5/g9 report identical
obtainability because they share the one pool.

```
RESOURCE_EXHAUSTED: [accounting_user:deepmind-dynamic-xm]
  dynamic root pool dynamic-ml-dedicated-flex-pool ... capped by the
  adjusted ceiling due to power capping event or insufficient bonus capacity.
  The current deficit of the dynamic root pool is (m0 d0 s(ghostfish:46)).
```

`go/borg-admission-control-ml#adjusted-ceilings-in-admission-control` documents
the mechanism.

**Do not generalize this into "changing cell or group cannot help".** A
pool-wide adjusted ceiling is only one of the verdicts that stops a v6p job; the
others are cell- and group-scoped, and the allocator names the cell in its own
text. A live-queue probe falsified the generalization: the same PROD ask,
minutes apart, drew a `resource-guarantee-reclaim` in one cell, a
`GQM_OVERSOLD_MARKET` in another group's copy of it, a `GQM_RESOURCE_DEFICIT_INFO`
with a smaller per-cell deficit in a third cell, and then a full granted slice
that trained and wrote checkpoints. **Read the work unit's message with
`deep_probe`/`why_probe` before concluding anything is pool-wide**; the
obtainability table cannot distinguish these cases, and moving cell is what
obtained the slice.

**A quota floor is not shared even when obtainability is.** One group can hold
hundreds of guaranteed chips with none used while another holds a handful all
used, so the same 64-chip ask is nearly all opportunistic (reclaimable) in one
and fits inside an idle guarantee in the other. Identical obtainability numbers
hide that difference.

### Obtainability Says A Slice Can Be Got; The Cap Decides How Long It Is Held

**Reading obtainability as if it measured hold time inverts the answer.** While
a v6p-64 job was preempted every 15 minutes, preflight still reported thousands
of obtainable chips in that cell. The cheap proxy for the cap is the pool-wide
price (a capped pool clears high because demand exceeds the adjusted ceiling);
the authoritative answer is the deficit string from `deep_probe` on a live work
unit.

**Hold time decides usability, and only a real run measures it.** Compute ratio
is not throughput when the slice keeps being taken away: a v6p-64 with twice the
raw compute of a v7-32 delivered a quarter of its net throughput, because each
preemption discards about half a checkpoint interval, and shortening the
interval trades that for save overhead.

### Measuring Hold Time: Three Traps That Each Fabricate A Number

**Measure hold time from Borg's `started` epoch, key episodes on `(xid,
started)`, and count a slice as held only once Borg says `RUN`.** Borg stamps
`started` when the gang begins running, independent of anyone watching, so a
restart during a blind window shows up afterwards as a changed value. Also
verify the run computed: a written checkpoint is the only artifact that cannot
exist without a step having executed.

| Trap | What it fabricates |
|---|---|
| Differencing per-attempt log timestamps | Counts startup as holding. Attempts averaging "15 min" can contain zero training steps, dying during JAX/dataloader startup. Describes time-to-teardown, not holding. |
| Treating `PENDING` (or "the work unit exists") as holding | The allocator can build a gang and cancel it without ever reaching `RUN`. Counting that reports capacity the pool never delivered. |
| Differencing your own poll samples | A gap in your polling reads as one long hold. A sampler outage once manufactured a "74.6 min" episode that Borg's `started` disproved. |
