# Quota, Price Caps, And Why A Job Will Not Schedule

Read this when a job will not schedule and `../jobs.md` does not explain it, or
before setting any price cap. This is allocator internals; most work never needs
it. Source-verified against the scheduling pipeline in mid-2026 — re-verify
before relying on a mechanism, and prefer live state over this text.

**This file is about the ACCELERATOR market only.** Everything below prices
chip-hours and is irrelevant to a CPU-only job: those are billed in GCU against
a different ledger, and an unschedulable CPU job is almost never a market
outcome — see `../jobs.md` §Requirements And Runtime for the pool it should be
in instead.

## The Model To Hold In Your Head

On a dynamic (market) pool, **quota is an output of the market, not an input**.
Credits fund a bid, a periodic auction clears a price, and your protected floor
is recomputed each cycle from that result. Static pools are the opposite: fixed,
human-configured floors and no credits at all. So on a dynamic pool money
genuinely buys quota — that is the definition — while on a static pool asking
for more money is meaningless.

Three consequences that repeatedly surprise people:

- **A floor is a floor, not a ceiling.** You may exceed it opportunistically.
  There is no per-allocation hard chip ceiling; caps that exist are pool-level,
  lead-level, or economic (they cap the *bill*, not usage).
- **The two tiers are one pipeline, not two.** They differ in *which scheduling
  pass they enter*, not in whether the market is involved.
- **The admission test is neither AND nor OR.** It is an ordered multi-pass
  pipeline over one shared pool capacity. Money and floor decide *which bucket
  you are in* — your place in line. When your turn comes, the only test is
  whether stock is left.

## The Two Tiers Behave Differently

**The guaranteed tier** enters the lease bucket first (free, no bidding) and
then the market bucket (needs credits). Lease-covered demand is subtracted
before the market sees it, which also exempts it from price caps. It can be
*queued* rather than rejected, re-evaluated each cycle. It is still not
preemption-proof — same-priority defragmentation can evict it.

**The batch tier is processed last, and that pass never checks your floor.** The
only test is whether the request fits in what remains of the root pool.
Therefore a batch job runs fine with a floor of zero, and **"batch quota" is a
meaningless number**: only live pool headroom matters, waiting does not help,
and asking for more batch quota helps even less. Being above floor by
construction, it is also the first thing reclaimed. An empty allotment for the
batch tier is a designed state, not a broken allocation.

The one lever that trades schedulability for immunity — forcing within-floor
placement so you are never reclaimed — **is unavailable on dynamic pools**. You
cannot buy determinism there.

## Price Caps (Limit Orders)

A **limit order** is a maximum price per chip-hour that a workload will pay. It
is not a system parameter; it is a number a person typed.

- When the market clears above it, a **pending** job is pulled from the queue
  **before any capacity check** — free capacity and idle chips do not help.
- A **running** job is paused and resumes automatically when the price drops.
  This is reversible; the job does not die.

**The comparison uses the pool-wide price, not a per-cell price.** The auction
merges every cell into one synthetic global layer before running, so both sides
of the comparison are that same constant, and the cap table has no cell column
at all. **Moving a job to a cheaper cell does not unblock a triggered cap.** Pin
cells for cost, never as a fix for a cap. Real fixes: a different allocation, a
different tier, or raise/remove the cap.

Other properties worth knowing: the comparison is per chip-hour and is *not*
multiplied by the chip count; it is a strict greater-than, so clearing exactly
at the cap is affordable; the lease exemption is all-or-nothing, so mostly-leased
demand is still fully paused; and the batch tier is **not** exempt. A pool price
of zero can mean "no price computed this cycle" rather than "free".

### Scope: whose jobs a cap affects

Resolution is **most-granular-wins**: schedulable unit, then experiment, then
group.

| Level | Who it affects |
|---|---|
| Schedulable unit | one unit; only the low-level tool can set it |
| **Experiment** | **one experiment — yours** |
| Group | **every job in the group, everyone's** |

An experiment-level cap overrides the group baseline and is not overwritten by
the periodic group push. That is the intended escape hatch for urgent work:
prefer it over raising the team's cap, which requires no permission but changes
everyone's spend.

**Because a teammate's group-wide cap silently applies to your jobs, "my job is
pending for no reason" is frequently someone else's cap. Check that before
debugging anything else.** There is no implicit default cap — no row means the
reason can never fire.

### Setting one

The convenience CLI takes positional targets where a number is an experiment id,
a couple of keywords mean "your recent / running experiments", and **anything
else is a group name** — the one dangerous case. Always preview with a dry run
first: it flags the rows where the proposed cap sits below the current market
price, i.e. where applying it would immediately pause running work.

The cap is computed as a multiple of a reference quantile of recent prices.
Choosing the multiple matters: a median reference means the job runs roughly half
the time, and prices on a dynamic pool move several fold within a day, so the
tool's non-urgent default will pause jobs during ordinary swings. **Prefer
raising the multiple over raising the quantile** — a very high quantile
effectively disables the cap. Our launcher sets a per-experiment cap
automatically at launch, with flags to change or skip it; failing to set it never
fails the launch, because a submitted uncapped job beats a launch that looks
broken.

**Known blocker:** the convenience CLI calls an RPC that a *restricted*
credential cannot reach. This is not an expiry problem and re-authenticating does
not fix it — the credential carries a destination allowlist that this service is
not on. The lower-level binary reaches the same state over a different path and
works under plain credentials. The same restriction is why some read paths keep
working: they query the database directly instead of calling the RPC.

### Verifying from the client side

The money command shows each allocation's cap against the live price range,
flags it as fine / partially blocking / fully blocking, and names who set it.
The router lists candidates excluded by a triggered cap. Ground truth is the
quota database: the cap table names the responsible user, the price table holds
the current cleared price per cell and tier, and the per-unit decision table
holds the authoritative verdict. **Do not trust the "paused by limit order" flag
on the unit record** — it is written at a different pipeline stage and reads
false while the decision row already carries a cap price.

## Money Buys Two Different Things

| Form | Buys | Shape |
|---|---|---|
| **Bid** (a flow, from income times leverage) | your protected floor | floor is downstream of it |
| **Balance** (a stock) | your opportunistic share above floor | scales the importance factor |

Do not conflate them: a large balance with tiny income still bids well for a
while. Prices are per **chip**-hour, so multiply by the slice size to get an
hourly cost. Raising a cap costs nothing by itself, but you are then charged the
clearing price for actual usage, draining the team's balance faster.

Cells still matter for **cost** even though they do not matter for a cap —
charging reads per-cell rates and the spread is real, which is why the router
picks the cheapest cell while deciding *blocked* from the global price.

Any floor number you read anywhere is a snapshot of one auction cycle, not an
entitlement. A configuration file and live state disagreeing is normal.

## Reading The Underlying Data

Prices, floors, caps, and per-unit decisions live in the quota database and are
readable directly with plain credentials, which is the reliable path from a
workstation. Resource types are keyed by numeric id in some tables and by enum
name in others — `../tpu_reference.md` has the mapping. Per-cycle price history
exists; one aggregated history table is empty and misleads.

The browser resource UI is authoritative for allocations, one allocation's
detail, and whole-pool usage; a command-line fetch will just redirect through
the SSO proxy.

## Known Tooling Gaps

- The quota table's compact notation marks the *smaller* number as quota, which
  is easy to misread.
- The bidding-power figure the CLI prints does not reproduce from the database;
  re-verify the formula before trusting it.
