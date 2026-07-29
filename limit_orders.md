# Limit Orders: Capping What A Job Pays

Read this when a PROD job will not schedule, when planning spend on a dynamic
(GQM) pool, or before setting any price cap. Background on the admission
pipeline is in `xmanager.md` §Quota, Money & GQM Marketplace.

## What a limit order is

A **maximum price per chip-hour** that a workload will pay. It is not a system
parameter — it is a number a person typed. When the market clears above it:

- A pending job is pulled from the queue **before any capacity check**
  (`NOT_SCHEDULED_TRIGGERED_LIMIT_ORDER`). Free floor and idle chips do not
  help.
- A **running** job is stopped and rescheduled when the price drops again
  (`PAUSED_BY_LIMIT_ORDER`). This is reversible and automatic; the job does not
  die.

The cap is compared against the **pool-wide (`global`) price, not a per-cell
price**. The V2 auction merges every cell into one synthetic layer
(`single-global-layer`) before the auction runs, so both sides of the comparison
are that constant. Corroboration: the `LimitOrders` table has no `Cell` column.
**Moving a job to a cheaper cell does not unblock a triggered limit order.**
Pin cells for cost, never as a fix for a cap.

## Scope: per-XID by default, group-wide if you ask for it

Resolution is **SCU > XID > MDB**, most granular wins.

| Level | Who it affects | How to set |
|---|---|---|
| SCU | one schedulable unit | `set_limit_order` only; `dynlo` cannot |
| **XID** | **one experiment — yours** | `dynlo <xid>` |
| MDB | **every job in the group, everyone's** | `dynlo <mdb-group-name>` |

An XID-level cap **overrides the group-wide baseline and is not overwritten by
the periodic group push**. That is the intended escape hatch for urgent work:
prefer it over raising the team's cap, which needs no permission but changes
everyone's spend.

Because a teammate's group-wide cap silently applies to your jobs, "my job is
pending for no reason" is frequently someone else's cap. Check before debugging
anything else.

## `dynlo`

`alias dynlo='/google/bin/users/marcusbrubaker/dynlo/dynlo.par'` (already in
`.bashrc`). Full docs: `//depot/google3/gdm/devtools/dynamic_limit_orders/`
(`README.md`, `g3doc/usage.md`, `g3doc/mdb_managers.md`).

Positional targets: a **number** is an XID, `last` and `running` are your most
recent / all running experiments, **anything else is an MDB group name** — the
one dangerous case.

```bash
dynlo last --dry_run                    # preview, change nothing
dynlo <xid> --price_multiple=3.0        # cap one experiment at 3x median
dynlo running --price_multiple=2.0      # all your running experiments
dynlo <xid> --price_multiple=-1         # remove the cap
```

Price formula: `limit_price = (ref_price + min_limit_price) * price_multiple`,
where `ref_price` is the `--quantile` (default 0.50) of `--history` (default
14d) of prices.

**Always `--dry_run` first.** It flags rows with `⚠ PAUSED` where the proposed
cap sits below the current market price — i.e. where applying it would
immediately pause running work.

### Choosing a multiple

The 50th quantile means the job runs roughly 50% of the time. `dynlo`'s default
`--price_multiple=1.5` is calibrated for non-urgent work and will pause jobs
during ordinary intraday swings; prices on `deepmind-dynamic-pool` move several
fold within a day. Prefer raising the multiple over raising the quantile — a
quantile like 0.99 effectively disables the cap. `tpu queue` uses **3.0**.

## Automatic cap on launch (`tpu queue`)

`tpu queue` sets a per-XID cap at `3.0x` median automatically, right after the
XID is registered. Flags: `--lo-multiple=N` to change it, `--no-limit-order` to
skip. A failure to set the cap never fails the launch — the job is already
submitted, and running uncapped beats a launch that looks broken.

## Known blocker: restricted LOAS credentials

`dynlo` calls `QuotaMarketplaceDataService.GetLimitOrders`, which a
**restricted** LOAS credential cannot reach:

```
SERVER_ERROR Credential does not permit access to owner=quota-marketplace-data
... (see go/loas-restricted-credentials)
```

This is **not** an expiry problem — re-running `gcert` does not fix it. Verify
with `gcertstatus -format=loas2`; a `restrictions: { destination_restriction:` block
means the credential carries a destination allowlist. `quota-marketplace-data`
is not on the default list (note `mdbuser/brain-quota` *is*, which is a
different service — this is why `tpu quota` and `tpu money` keep working: they
read Spanner directly rather than calling this RPC).

Workaround while unresolved: `set_limit_order` reaches the same state over a
different path and works under plain LOAS.

```bash
/google/bin/releases/brain-quota/set_limit_order/set_limit_order \
  --xid=<xid> --price=<credits_per_hour>     # --price=-1 removes; --dry_run previews
```

## Verifying from the client side

`tpu money` shows each card's cap against the live price range and flags it
`ok` / `blocks dear cells` / `BLOCKS ALL`, plus who set it. `tpu route
--explain` lists candidates excluded by a triggered cap. Ground truth is
Spanner:

```bash
/google/bin/releases/spanner/public/span/span sql \
  /span/global/brain-quota:quota --span_sql_disable_sdl_and_dml \
  "SELECT ResourceType, Priority, MilliCreditsPerUnitHour, LimitOrderUser, CreatedTime
     FROM LimitOrders WHERE Mdb='<mdb>' ORDER BY CreatedTime DESC"
```

`LimitOrderUser` names the person responsible. Do not trust
`ScuInfo.is_paused_by_limit_order` — it is written at a different pipeline stage
and reads `false` while the decision row already carries a limit price.
