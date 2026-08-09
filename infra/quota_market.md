# Quota, Price Caps, And Why A Job Will Not Schedule

Allocator internals: the accelerator market, tier behavior, price caps, and the
data behind them. Read this when a job will not schedule and `../jobs.md` does
not explain it, or before setting any price cap; most work never needs it.

**This file is about the ACCELERATOR market only.** Everything below prices
chip-hours and is irrelevant to a CPU-only job: those bill in GCU against a
different ledger, and an unschedulable CPU job is almost never a market outcome
— see `../jobs.md` §Requirements And Runtime for the pool it belongs in.

## The Model To Hold In Your Head

**On a dynamic (market) pool, quota is an output of the market, not an input.**
Credits fund a bid, a periodic auction clears a price, and your floor is
recomputed each cycle from that result. Static pools are the opposite — fixed,
human-configured floors, no credits — so money genuinely buys quota on a dynamic
pool, while on a static pool asking for more of it is meaningless.

- **A floor is a floor, not a ceiling.** You may exceed it opportunistically;
  there is no per-allocation hard chip ceiling, and the caps that exist are
  pool-level, lead-level, or economic (capping the *bill*, not usage). Any floor
  number you read is one auction cycle's snapshot, not an entitlement — a config
  file and live state disagreeing is normal.
- **The two tiers are one pipeline, not two**, differing in *which scheduling
  pass they enter*, not in whether the market is involved.
- **The admission test is neither AND nor OR.** It is an ordered multi-pass
  pipeline over one shared pool capacity: money and floor decide *which bucket
  you are in*, and when your turn comes the only test is whether stock is left.

| | Guaranteed tier | Batch tier |
|---|---|---|
| Passes | lease bucket first (free, no bidding), then market bucket (needs credits) | processed last, and that pass **never checks your floor** |
| Admission test | lease-covered demand is subtracted before the market sees it | only whether the request fits what remains of the root pool |
| Price caps | exempt for the lease-covered part | **not** exempt |
| On rejection | can be *queued* instead, re-evaluated each cycle | — |
| Reclaim | not preemption-proof; same-priority defragmentation evicts it | above floor by construction, so first reclaimed |

So a batch job runs fine with a floor of zero, and **"batch quota" is a
meaningless number**: only live pool headroom matters, waiting does not help,
asking for more helps even less, and an empty batch allotment is a designed
state, not a broken allocation. The one lever trading schedulability for
immunity — forcing within-floor placement so you are never reclaimed — **is
unavailable on dynamic pools.**

## An Adjusted Ceiling Is A Pool Cap, Not A Cell Shortage

A job can sit PENDING, or be preempted every few minutes, because the
**dynamic root pool** is capped below its nominal size. The work unit's own
message is the only place this is legible:

```
RESOURCE_EXHAUSTED: [accounting_user:deepmind-dynamic-xm]
  dynamic root pool dynamic-ml-dedicated-flex-pool ... capped by the
  adjusted ceiling due to power capping event or insufficient bonus capacity.
  The current deficit of the dynamic root pool is (m0 d0 s(ghostfish:46)).
```

Read it structurally: the deficit is per **platform** (`ghostfish` = v6p) and
names **no cell**. So neither changing cell nor changing group routes around
it — measured, not assumed: g1/g5/g9 report identical obtainability because
they share the one pool, and the same numbers appear in every cell.
`go/borg-admission-control-ml#adjusted-ceilings-in-admission-control` documents
the mechanism.

**Obtainability does not measure this, and reading it as if it did inverts the
answer.** While a v6p-64 job was being preempted every 15 minutes, preflight
still reported 2123 obtainable chips in that cell. Obtainable says a slice can
be *got*; the cap decides how long it can be *held*. The cheap proxy for the
cap is the pool-wide PRICE — a capped pool clears high because demand exceeds
the adjusted ceiling (17-29 credits/chip-hr while capped here) — and the
authoritative answer is the deficit string from `deep_probe` on a live work
unit.

**Hold time is the number that decides usability, and it is only measurable
from a real run.** Take the attempt timestamps and difference them; the
`_startup` markers or per-attempt logs give this for free. At a 15.1-minute
mean hold, a v6p-64 slice with 2x the raw compute of a v7-32 delivered a
QUARTER of its net throughput, because each preemption discards ~half a
checkpoint interval and shortening the interval trades that for save overhead
(a 236 s save against a 15 min hold). Compute ratio is not throughput when the
slice keeps being taken away.

## Price Caps (Limit Orders)

A **limit order** is a maximum price per chip-hour that a workload will pay. It
is not a system parameter; it is a number a person typed.

- When the market clears above it, a **pending** job is pulled from the queue
  **before any capacity check** — free capacity and idle chips do not help. A
  **running** job is paused and resumes automatically when the price drops:
  reversible, and the job does not die.
- **The comparison uses the pool-wide price, not a per-cell price.** The auction
  merges every cell into one synthetic global layer, so both sides of the
  comparison are that constant and the cap table has no cell column at all.
  **Moving a job to a cheaper cell does not unblock a triggered cap** — pin
  cells for cost only. The real fixes are a different allocation, a different
  tier, or raising/removing the cap.
- The comparison is per chip-hour, *not* multiplied by the chip count; it is a
  strict greater-than, so clearing exactly at the cap is affordable; and the
  lease exemption is all-or-nothing, so mostly-leased demand is still fully
  paused. A pool price of zero can mean "no price computed this cycle" rather
  than "free".

### Scope: whose jobs a cap affects

Resolution is **most-granular-wins**: schedulable unit, then experiment, then
group.

| Level | Who it affects |
|---|---|
| Schedulable unit | one unit; only the low-level tool can set it |
| **Experiment** | **one experiment — yours.** Overrides the group baseline and is not overwritten by the periodic group push — the intended escape hatch for urgent work |
| Group | **every job in the group, everyone's.** Raising it requires no permission but changes everyone's spend |

**Because a teammate's group-wide cap silently applies to your jobs, "my job is
pending for no reason" is frequently someone else's cap. Check that before
debugging anything else.** There is no implicit default cap — no row means the
reason can never fire.

### Setting one

**Always dry-run first.** The convenience CLI takes positional targets where a
number is an experiment id, a couple of keywords mean "your recent / running
experiments", and **anything else is a group name** — the one dangerous case. A
dry run flags rows where the proposed cap sits below the current market price,
i.e. where applying it would immediately pause running work.

The cap is a multiple of a reference quantile of recent prices, and the multiple
matters: a median reference means the job runs roughly half the time, and prices
move several fold within a day, so the tool's non-urgent default pauses jobs
during ordinary swings. **Prefer raising the multiple over raising the
quantile** — a very high quantile effectively disables the cap. Our launcher
sets a per-experiment cap at launch, with flags to change or skip it; failing to
set it never fails the launch, because a submitted uncapped job beats a launch
that looks broken.

**Known blocker:** the convenience CLI calls an RPC a *restricted* credential
cannot reach, and re-authenticating does not fix it — the credential carries a
destination allowlist this service is not on. The lower-level binary reaches the
same state over a different path under plain credentials; the same restriction
is why some read paths keep working, querying the database instead of the RPC.

### Verifying from the client side

The money command shows each allocation's cap against the live price range,
flags it fine / partially / fully blocking, and names who set it; the router
lists candidates excluded by a triggered cap. Ground truth is the quota
database: the cap table names the responsible user, the price table the cleared
price per cell and tier, the per-unit decision table the authoritative verdict.
**Do not trust the "paused by limit order" flag on the unit record** — it is
written at a different pipeline stage and reads false while the decision row
already carries a cap price.

## Money Buys Two Different Things

| Form | Buys | Shape |
|---|---|---|
| **Bid** (a flow, from income times leverage) | your protected floor | floor is downstream of it |
| **Balance** (a stock) | your opportunistic share above floor | scales the importance factor |

Do not conflate them: a large balance with tiny income still bids well for a
while. **Prices are per chip-hour**, so multiply by the slice size for an hourly
cost. Raising a cap costs nothing by itself, but you are then charged the
clearing price for usage, draining the balance faster. Cells still matter for
**cost** even though they do not matter for a cap — charging reads per-cell
rates and the spread is real, which is why the router picks the cheapest cell
while deciding *blocked* from the global price.

## Reading The Underlying Data

Prices, floors, caps, and per-unit decisions live in the quota database and are
readable directly with plain credentials — the reliable path from a workstation.
Resource types are keyed by numeric id in some tables and enum name in others
(`../tpu_reference.md` has the mapping).

**To answer "where does this accelerator exist at all", read the router's market
cache** (`~/.tpu_quota_cache_dir/market.json`), which lists every cell with a
price. The money command's summary only *samples* cells per accelerator, so
reading its table as a complete list understates availability. Entries are keyed
by an internal card code — confirm the code by checking that a cell you already
run on appears under it.

The browser resource UI is authoritative for allocations, one allocation's
detail, and whole-pool usage; a command-line fetch just redirects through the
SSO proxy.

Known gaps: per-cycle price history exists but one aggregated history table is
empty and misleads; the quota table's compact notation marks the *smaller*
number as quota, easy to misread; and the bidding-power figure the CLI prints
does not reproduce from the database, so re-verify the formula before trusting
it.
