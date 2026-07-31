# XManager And Borg Jobs

Read this for queueing, inspecting, resuming, or debugging jobs on the Google
internal XManager/Borg stack. Read `data_locality.md` before choosing cells or
runtime storage, plus the target project's own guide.

## Submission Contract

- Agents submit through
  `source ~/work/tpu_cmd/tpu_wrapper.sh && tpu queue ...`. Never call
  `xm launch` or `xmanager launch` directly. Only the wrapper may do so
  internally.
- The shared `~/work/tpu_cmd/xm_launcher.py` owns common packaging, staging, and
  job registration. Project checkouts provide versioned configuration and a
  link or reference to the shared launcher; do not grow independent launcher
  implementations without an explicit design change.
- Put model, data, and training semantics in versioned config. Wrapper-level
  resource routing and explicit transient selectors such as `load_from` or
  `resume_xid` may remain CLI arguments.
- Confirm the source checkout, branch, dirty state, effective config, allocator,
  and target before launch. Use the project's real Research Hub attribution;
  never insert a placeholder merely to suppress an interactive prompt.
- A wrapper may create a unique CitC source snapshot before packaging. The
  resulting Bazel package is immutable: edits after packaging do not change a
  queued or running job.
- The wrapper records the XManager id and associated metadata for `tpu check`.
  Verify that registration after submission instead of assuming the launch
  transaction completed.

## Where The `tpu` Tooling Lives (two halves, two git repos)

The `tpu` CLI is split across two locations, and the split is forced by Blaze,
not by preference. Know which half you are editing before you touch anything.

| Half | Path | Contents |
|---|---|---|
| Shell / launcher | `~/work/tpu_cmd/` | `tpu_wrapper.sh`, `xm_launcher.py`, `README.md` |
| Blaze-built checkers | `/google/src/cloud/qiaos/xm_test/google3/experimental/users/qiaos/tpu_utils/` | `money_check.py`, `quota_check.py`, `infra_check.py`, `group_utils.py`, `preflight/` (topology, capacity, market, router + tests), `pydcheck/`, probes |

The google3 half cannot be moved into `~/work`: it imports
`google3.experimental.users.qiaos.tpu_utils.*`, its BUILD depends on targets
like `//learning/agents/orcas/tools/gqm_tool`, and `tpu_check_daemon.sh` runs
the compiled `blaze-bin/...` binaries every ~60s.

**Symlinking the google3 half out to `~/work` does not work.** All three
variants were tested and fail: an absolute directory symlink is rejected
outright (`Absolute symlinks are forbidden`), a relative one escapes the source
root (`BUILD file not found`), and per-file symlinks fail at action execution
(`missing input file`). Only the reverse direction works -- real files in
google3, a symlink in `~/work` pointing at them. `~/work/tpu_cmd/google3_tpu_utils`
is exactly that, for navigation only.

### Git layout

Both halves are versioned, by two separate repos:

- `~/work/tpu_cmd/` -- an ordinary git repo.
- The google3 half -- a git repo created with
  `git init --separate-git-dir=~/work/tpu_utils.git <path>`. The worktree stays
  in google3 so Blaze and CitC are unaffected; only a ~56-byte `.git` *file*
  (a `gitdir:` pointer) sits in the google3 directory, and Blaze builds fine
  with it present. Run `git` commands from inside the google3 directory as
  usual.

Why `--separate-git-dir` rather than one repo plus a symlink: git records a
symlink as mode `120000`, i.e. the link itself, so committing
`google3_tpu_utils` would back up zero of the files behind it. That symlink is
gitignored for this reason.

CitC is not a backup, and the google3 half was originally unknown to Piper
(`g4 files` reported `no such file(s)` for the whole directory). It is now
checked in as `cl/956103898` -- 24 files; `pydcheck/` is deliberately excluded
as an unrelated one-off EqR-jax pydantic probe with a hardcoded staged-run
path. Until that CL submits, the git repo is the only recovery path.

The `preflight/*_test.py` files are self-asserting scripts (they `sys.exit(1)`
on failure), not absltest. They must be declared `pytype_strict_contrib_test`;
as `pytype_strict_binary` they silently never run and `blaze test` answers
"No test targets were found".

## Requirements And Runtime

- A job intended to consume guaranteed PROD quota must set
  `service_tier=xm.ServiceTier.PROD` in `xm.JobRequirements`. Do not substitute
  a legacy `xm_priority` field or silently accept BATCH/FREE.
- `xm.python_container` requires the selected pool to have a mapped GCP project.
  Use the allocator's supported packaging mode; native Borg allocators without
  that mapping require `xm_abc.Borg` with Bazel packaging.
- In JAX applications using `xm_jax.JaxFlags`, parse Abseil flags before
  distributed initialization. Call `jax.distributed.initialize()` inside
  `main(argv)`, never at module import time.

## Metrics And Curves (the internal W&B)

There is no Weights & Biases inside google3. The equivalent is **DeepMind
Datatables** for storage and **Flatboard** for plots, both keyed by XID.

### Where to look

`spreadsheet.md` §Chart Links owns the canonical URL table and the rules for
verifying a run actually wrote metrics. In short: curves at
`http://flatboard/xid/<XID>`, raw table at `http://datatable/xid/<XID>/data`.

Two things that table does not cover:

- `http://flatboard/autodash/<XID>` gives **one plot per column** (capped at 20),
  which is the better entry point when exploring an unfamiliar run;
  `flatboard/xid/` synthesises a single plot and guesses the axes.
- **An empty page means no data was written, not a broken link.** There is no
  404 for a missing table, so a blank Flatboard is a writer problem to diagnose
  in the job, not a URL to retype.

### Reading from the CLI

```bash
alias dtt='/google/bin/releases/deepmind/datatables/dtt/dtt'
dtt ls --name=/datatable/xid/<XID>/     # what tables exist
dtt show /datatable/xid/<XID>/data      # schema and primary keys
dtt scan -n 20 /datatable/xid/<XID>/data
```

**`dtt` does not work from this workstation** — restricted LOAS blocks
DatatableService, and every local binary hits the same wall. This is a
workstation limitation only; a Borg job writes fine. Use the browser URLs above,
which authenticate with EUC.

### Getting a job to write anything

A job that never calls a metric writer produces no table and therefore an empty
Flatboard. Writing is one BUILD dep
(`//third_party/py/clu/metric_writers:notf`) plus
`metric_writers.create_default_writer(...)`. The settings that are easy to get
wrong are owned by `spreadsheet.md` §Chart Links (explicit `write_to_datatable`,
no XM Measurements) and `eqr_jax.md` §Experiment Tracking (rank-0 only, periodic
flush).

Tables expire 180 days after **last access** and renew on every read or write;
pin one with `dtt setexpiry <table> never`.

## Quota, Money & GQM Marketplace

### Underlying allocation logic: it is one pipeline, not two

The old "PROD = pure quota, BATCH = pure market" model is **wrong** for
`deepmind-dynamic/*`. Both tiers go through GQM. What differs is which
scheduling pass they enter.

**The pipeline** (`credits → floor → admission`):

    credits ──autobid──► auction (every 30s) ──► clearing price
                                                      │
                       floor = lease_floors + min(demand, bid / clearing_price)
                                       ↑ this IS "quota" (`floor_v2`)
                                                      │
                     XBorg admission: within-floor is protected, above-floor is opportunistic
                                                      │
                          Borg: ServiceTier preemption + physical cell capacity/topology

- **Quota is an OUTPUT of the market, not an input.** For a GQM pool,
  `ResourceAllocationDetails.floor_v2` is recomputed every market cycle from the
  auction result and pushed to XBorg
  (`update_prices_and_floors_handler.cc` → `DynamicMdbFloors` →
  `Allotment.global_resource_guarantee` → `floor_v2`). `MdbAssignedFloorsProto`
  splits it into `market_floors` (bought with credits) and `lease_floors`
  (administratively granted). Money genuinely buys quota; that is the definition
  of a dynamic alloc. Static (non-GQM) pools are the opposite: fixed,
  human-configured floors and no credits at all
  (`go/xborg-why` §"Requirements size increase" states both cases explicitly).
- **`floor_v2` is a floor, not a ceiling.** go/gqm FAQ: "Floors are neither an
  upper or a lower bound... Users can exceed their floor opportunistically."
  There is **no per-alloc hard chip ceiling** anywhere in the protos — only
  pool-level and lead-level ceilings, plus an economic cap
  (`credit_charges_limit_factor`, which caps the BILL, not usage; the excess is
  forgiven).
- **Prices are per `(resource_type, cell, priority)`.** `priority` IS the tier
  (`brain.quota.ResourceSpec`). PROD prices are real and binding — e.g. VIPERFISH
  PROD in `deepmind-dynamic-pool` cleared at 37–75 credits/chip-hour on
  2026-07-28. Do **not** treat the PROD price as a shadow price.

**PROD (`ServiceTier.PROD` / HighlyAvailable / Borg priority 200)**
- Enters the lease and market buckets: `FULLY_COVERED_BY_LEASE` first (free, no
  bidding), then `*_WITHIN_GLOBAL_MARKET` (needs credits). Lease-covered demand
  is subtracted from `num_chips` before the market sees it, so it is also exempt
  from limit orders (`market_algorithm/limit_order.cc:238-248`).
- Can be **queued**, not just rejected. `GQM_RESOURCE_DEFICIT_INFO` is a queue
  state that re-evaluates every 30s cycle.
- Still not preemption-proof: equal-priority `SLICE_DEFRAGMENTATION` can evict it.

**BATCH (`ServiceTier.BATCH` / NonProd / Borg priority 100)**
- `BUCKET_ID_BATCH_TIER` is the **last** bucket processed
  (`scu_decision_structs.h:24-28` — enum order == pass order), and
  `scu_bucketizer.cc:305-310` says explicitly: "To reserve resources for PROD
  tier SCUs, SCUs with BATCH tier TPU demand will be placed in the BATCH_TIER
  bucket, which has the lowest priority."
- **That pass never checks your floor.** The only test is
  `DemandFitsInRootPoolCapacity(...)` against what is left of the root pool
  (`scu_scheduler.cc:285-296`). This is why a BATCH job runs fine with
  `floor_v2 == 0` — and why "BATCH quota" is a meaningless number. Its GQM
  capacity type is `SPILLOVER`; on the XBorg side it is `NOT_ADMITTED`
  (= ABOVE_FLOOR). Being above floor, it is the first thing reclaimed
  (`go/xborg-why-descheduled#resource-guarantee-reclaim`).
- Consequence: for BATCH, **only live pool headroom matters**. Waiting does not
  help; nor does asking for more BATCH quota.
- `floor_v2` shows *no* NonProd key at all (rather than `0`) because
  `xborg_config_utils.cc:551` skips populating `global_resource_guarantee` when
  the auction floor is 0 (`// If floor is 0, add an empty allotment.`). An empty
  allotment is a designed state, not a broken alloc.

**The admission predicate is neither AND nor OR.** It is an ordered multi-pass
pipeline over one shared `remaining_root_pool_capacity_tensor`. Money and floor
decide *which bucket you are in* — i.e. your place in line. When your turn comes,
the only test is "is there stock left".

**`minimum_duration` — the one lever that trades schedulability for immunity
(forces within-floor-only, so you are never reclaimed) — is explicitly
unavailable on dynamic/GQM pools** (go/xborg-minimum_duration). On
`deepmind-dynamic/*` you cannot buy determinism this way.

### Limit orders can block a PROD job (`NOT_SCHEDULED_TRIGGERED_LIMIT_ORDER`)

**`limit_orders.md` is the canonical guide** — how to set one, scope rules, the
`dynlo` CLI, and the restricted-LOAS blocker. Summary only here.

A **limit order** is a user-set maximum price (credits/hour) per
`(ResourcePool, Mdb, XManagerExperimentId, ScuId, ResourceType, Priority)`.
It triggers when `market_price > limit_order_price`, and the workload is
**paused** (`PAUSED_BY_LIMIT_ORDER`), resuming automatically when the price
drops. A **running** job is stopped too, not just a pending one.


- **Precedence is SCU > XID > MDB** (`team_queues.cc:536-570`; most granular
  wins). **An MDB-wide limit order set by a teammate silently applies to every
  job in the group, including yours.** This is a real and easy-to-miss failure
  mode — G9 hit exactly this.
- **There is no implicit default.** No row ⇒ no `milli_credit_limit_price` ⇒ the
  reason can never fire (`limit_order.cc:233`). `tpu_cmd` does not set one.
- **You can set/remove it yourself** if your MDB is in
  `limit_orders_enrolled_mdbs` (quota_config.pbtxt); the CLI only checks LOAS,
  not job ownership. Prebuilt binary, no build needed:
  `/google/bin/releases/brain-quota/set_limit_order/set_limit_order`
  - `--xid=<xid> --price=<credits_per_hour>` (infers pool/mdb/type/tier)
  - `--price=-1` removes it; `--dry_run` previews safely.
  - Prefer a per-XID override over raising the group-wide floor.
- Raising it costs nothing by itself — but you are then charged the **clearing
  price** for actual usage (floor + opportunistic) every 5 min, draining
  `MdbCreditBalance` faster for the whole team.
- To diagnose, read Spanner directly (plain LOAS, ~15s; the `GetLimitOrders` RPC is
  NOT reachable from a workstation):
  `/google/bin/releases/spanner/public/span/span sql /span/global/brain-quota:quota
   --span_sql_disable_sdl_and_dml "SELECT ... FROM LimitOrders WHERE Mdb='<mdb>'"`
  (`span` is a directory; `ResourceType` accepts the enum NAME).
  `LimitOrderUser` tells you who set it. `ResourcePrices` = current cleared price
  per cell/tier (no timestamp column); `PriceEstimatesHistory` = per-cycle history
  (`AggregatedResourcePricesHistory` is empty); `DynamicMdbFloors` = your real
  current floor; `ScuChunkDecisions` = the authoritative per-SCU verdict.
  **Do not trust `ScuInfo.is_paused_by_limit_order`** — it is written at a
  different pipeline stage and reads `false` while the decision row already
  carries `limit_order_price`.
- **Moving cells does NOT clear a triggered limit order.** (Corrected
  2026-07-29; the earlier "just pin a cheap cell" advice here was wrong.) Every
  production cycle runs the V2 auction (`cron_trigger/trigger_server.cc:222`
  hardcodes `run_v2_auction=true`), which calls
  `TransfromMarketSpecsToSingleCell` *before* the auction and rewrites every
  spec and queued SCU to the synthetic cell `single-global-layer`
  (`cron_service/utils/quota_auction_utils.cc:438`, `:132`; constant in
  `data/consts.h:45`). The trigger then matches
  `spec.cell() == scu_info.cell()` (`market_algorithm/limit_order.cc:265`) with
  both sides equal to that constant, so **the cell you pinned never enters the
  comparison**. Post-auction the name is rewritten to `global`, which is the row
  that lands in Spanner. Corroboration: `LimitOrders` has no Cell column at all,
  so a per-cell cap is not expressible.
  - So the number to compare your cap against is
    `ResourcePrices WHERE Cell='global'`, not the per-cell minimum.
  - Real fixes for a triggered cap: a different card, a different tier, or
    raise/remove the cap.
  - Cells still matter for **cost** — charging reads the per-cell hourly rows
    (`mdb_charges_utils.cc:55-65`), and the spread is real (v6e PROD on
    2026-07-29: 22.23 in 117 cells, 48.93 in nine). `tpu route` therefore picks
    the cheapest cell to save credits, while deciding *blocked* from the global
    price.
- Other GQM details worth knowing (all source-verified 2026-07-29):
  - The comparison is **per chip-hour**, is **not** multiplied by `num_chips`,
    and does **not** include `scu_bidding_buffer` (that only applies when
    bidding, `bidding.cc:148-152`). It is a strict `>`; clearing exactly at the
    cap is affordable.
  - Lease exemption is all-or-nothing: only `num_chips == 0` skips the check
    (`limit_order.cc:236-248`). 80%-lease-covered demand is still fully paused.
  - **BATCH is not exempt** from limit orders; there is no priority filter in
    the chain. Our MDBs simply have no BATCH rows today.
  - A `global` price of 0 can mean "no price computed this cycle", not "free"
    (`resource_prices.cc:244-258` writes 0 when no price was found).
- `floor_v2` you read anywhere (cdpush textpb, `tpu quota` cache, the UI) is a
  **snapshot of one 30s cycle**, not an entitlement. A depot config showing 256
  and the live `DynamicMdbFloors` showing 128 is normal, not a bug.

### Money buys two different things

| Money form | Buys | Mechanism |
|---|---|---|
| **bid** (a flow, from income × leverage) | your **floor** (protected quota) | `floor = min(demand, bid/price)` |
| **balance** (a stock) | your **opportunistic share** above floor | `Allotment.opportunistic_importance_factor = balance/1000` (`xborg_config_utils.cc:263-292`) |

`bidding_power_hourly = daily_credit_income / 24 * income_leverage` is
independent of floor — floor is downstream of it, not an input.
Empirically confirmed on `deepmind-dynamic/fr-dna-grand-challenge-team-resource`:
`MdbCreditBalance` = 6,578,508 credits and the allotment's
`opportunistic_importance_factor` = 6,587,067 — a 0.13% match.

**Prices are per CHIP-hour** (`bidding.cc:151`:
`price_estimate * scu.num_chips() * (1.0 + buffer)`), so a v5p-16 at 40
credits/chip-hr costs ~640 credits/hr.

### Known tooling gaps

Fixed 2026-07-28: `tpu money` now shows **both** tiers' clearing prices plus a
`Limit order` column that flags caps as `ok` / `blocks dear cells` /
`BLOCKS ALL` against the observed price range, and names who set them.
`tpu queue --cell=<name>` can pin a job to a specific cell.

Still open:

- `tpu quota`'s `~` marks the **smaller** number as Quota — easy to misread.
- `tpu money`'s bidding-power figure does not reproduce from Spanner; re-verify
  the formula before trusting it.

---

### GQM Bidding Power: how it is computed
`bidding_power_hourly = daily_credit_income / 24 * income_leverage`.
- `daily_credit_income` = `SUM(UserAllocations.Weight) + SUM(LeadAllocations.Weight)` for this MDB in the target pool.
- `income_leverage` default = 2× (per-MDB overrides exist in `BiddingIncomeLeverageLimitOverrides`).
- The formula lives in `learning/agents/orcas/tools/gqm_tool/gqm_tool.py:get_bidding_power`
  and `//quota/marketplace/handlers/get_bidding_power_handler.cc`.

### `tpu money` CLI Usage
- **Command**: `tpu money` (Aliases: `tpu m`, `tpu price`).
- **Features**:
  - **Zero-latency offline fetch**: the CLI only `cat`s a cache file, so it is
    instant; all latency lives in the background daemon
    (`tpu_check_daemon.sh`), which refreshes on a loop.
  - **Group Money Table**: per MDB alloc, PROD/BATCH chip usage plus two
    distinct money figures — **Bidding Power** (credits earned per hour, a
    *flow*) and **Balance** (accumulated credits, a *stock*, from Spanner
    `MdbCreditBalance`). Do not conflate them: a large balance with tiny income
    still bids well for a while. Static-pool MDBs have no balance row and are
    shown as `n/a (static pool)` rather than `0`.
  - **Clearing Prices in Your Pools**: **both PROD and BATCH**, for major cards
    (v4, v5p, v6e, v6p), filtered to the pools you actually participate in.
    PROD prices are real and binding on dynamic pools — they were hidden until
    2026-07-28 on the disproven "shadow price" theory, which removed the only
    panel that explains a PROD job stuck in `TRIGGERED_LIMIT_ORDER`.
  - **Limit order column**: the group's MDB-level price cap per (card, tier),
    compared against the live price range, plus the `LimitOrderUser` who set
    it. Since resolution order is SCU > XID > MDB, a teammate's cron can cap
    your jobs without you knowing.
- **Related Commands**:
  - `tpu quota` — per-alloc guaranteed floor, usage, and obtainable forecast.
  - `tpu quota -l` — map G1..GN to full MDB allocation paths.

### Cache daemon: keep the round shorter than the staleness threshold

`tpu quota` / `tpu money` warn when their cache is older than **180s**. The
daemon must therefore finish a full round well inside that budget.

- Each checker binary pays a **~15s Python/par cold start** while its actual
  RPCs cost <1s. Running the checkers serially paid that tax three times and
  pushed a round past the threshold, so the alarm fired every cycle. They are
  independent and write to disjoint outputs, so they run **concurrently**.
- When the alarm fires, check the round duration the daemon logs before
  believing its "LOAS/gcert expired" hint — that message is a guess, and
  `gcertstatus` usually disproves it.
- Rebuild **all** checker binaries in one `blaze build` invocation. Building a
  single target evicts the other binaries from `blaze-bin`, and the daemon then
  reports failures that look like data or auth bugs.

### Web UI for quota

Authoritative browser view (uberproxy 302 on `curl` is expected; open in a
browser):

- All allocs for a user: `https://xmanager.corp.google.com/resources/users/$USER`
- One alloc: `https://xmanager.corp.google.com/resources/pools/<pool>/allocations/<url-encoded alloc>`
- Whole pool usage: `https://xmanager.corp.google.com/resources/pools/<pool>/usage`

## Debugging A Job That Dies With No Log

### Reproduce locally first — a staged package is a normal Bazel target

`tpu queue` snapshots the checkout into
`//experimental/<user>/<project>_stages/<run>/` and packages *that*. The snapshot
is an ordinary Bazel target, so the exact artifact Borg will run can be built and
executed on the workstation:

```bash
cd /google/src/cloud/<user>/<workspace>/google3
D=experimental/<user>/<project>_stages/<run_dir>
blaze build $D:main --define=PYTYPE=FALSE --norun_validations
blaze-bin/$D/main --help          # exercises the whole import graph
```

`--help` is enough: Abseil parses flags only after every module-level import has
run, so import-time failures surface in seconds. This costs ~3 minutes and
catches the entire class of "died before `main()`" bugs that are nearly
undiagnosable remotely. **Do this before every launch that changes imports or
BUILD deps.**

### `strict_deps = False` makes the build lie

A missing dependency is not a build error under `strict_deps = False`; it is a
runtime `ModuleNotFoundError` on the TPU worker. The build passing proves
nothing about importability — only running the binary does.

### Why such a failure is invisible from outside

A process that dies during module import produces:

- `WorkUnit.status.message` == `''` (XManager has nothing to report)
- no application log anywhere, including any GCS mirroring the app installs —
  `main()` never ran, so nothing was installed
- `WorkUnit.borg_job_states` == `[]` once the work unit is GC'd, which removes
  the only handle (`cell` / `user` / `job_name`) that `borg tasklog` needs

Seeing all three at once is itself the diagnosis: **the failure is before
`main()`**. Do not keep re-launching to collect logs that cannot exist.

### Getting logs, in order of reliability

1. **Run the staged binary locally** (above). Highest signal, no queue, no cost.
2. **`WorkUnit.borg_job_states`** — `cell`, `user`, `job_name`,
   `task_state_counts`, `status_message_summary`.
   **Requires `get_work_units(populate_detailed_executable_status=True)`**;
   without that flag the field is silently an empty list, which reads exactly
   like "the job is gone" and sends you down the wrong path.
   `experimental/users/qiaos/tpu_utils:why_probe` sets it and prints a
   ready-made `borg tasklog` command. Note the Borg job itself is GC'd within
   minutes, so `borg getjob` on a dead job returns `Object not found` — the
   work-unit status message survives much longer and usually carries the actual
   Python exception.
3. **Application-level mirroring to GCS** — `utils/logging_util.py::mirror_logs_to_bucket`
   tees stdout/stderr to `$CHECKPOINT_BUCKET/logs/rank_N.log`, flushing on any
   Traceback/Error line so the last words before a crash survive. Outlives the
   task, the work unit, and the experiment — but only covers failures *after*
   `main()` starts.
4. `xmanager tail_logs --experiment_id=<XID> --work_unit_id=1` — works
   sometimes; the CLI itself crashes with an envelope stream error often enough
   that it cannot be relied on.
5. `analog` — blocked by permissions on this workstation (both
   `/google/bin/releases/analog-cli/analog` and per-user copies).

### Read the WHY column before doing anything else

`tpu check` classifies the failure for you. `CODE BUG: <signal>` means the
application died and the fix is in your source, not the infra — do not go
hunting for preemption or quota. A signal that leaves no traceback (SIGSEGV) or
a crash mid-run still needs the log; a `CODE BUG: stdlib I/O on /cns` names the
cause outright.

Two caveats:

- The column is served from `~/.tpu_check_cache.txt`, refreshed by the daemon
  roughly every 60s. For an immediate answer run the binary directly:
  `blaze-bin/experimental/users/qiaos/tpu_utils/infra_check`.
- A **blank** WHY on a PENDING job means "queued, nothing wrong". Only a real
  blocker (GQM price cap, quota deficit, prior preemption) prints text there.

### A crash after packaging is usually a stdlib-vs-remote-path or mock-API bug

The two failure modes that repeatedly survive a green build and a local smoke
test, because both only fire on Borg:

- **stdlib file APIs against `/cns/...`.** `os.makedirs`/`open`/`os.path.isdir`
  raise `PermissionError: [Errno 13] Permission denied: '/cns'` or silently
  answer False. Anything touching `$CHECKPOINT_BUCKET` must go through an
  `etils.epath`-backed helper.
- **Mocked third-party libraries.** google3 substitutes stubs for some external
  packages (e.g. `wandb` → `//third_party/py/scamper:wandb_mock`). Missing
  attributes raise **at call time**, so a code path that only runs every N steps
  fails minutes into a run. Probe with `getattr` and degrade, and never let
  telemetry raise into the training loop.

Both are reproducible in ~1 min locally by putting the real google3 stub first
on `PYTHONPATH`; neither is reproducible by reading the build output.

## Preemption, Restart, And Resume

### What a Borg task restart actually restores: nothing

A restart re-executes the binary from `main()` on a fresh machine with the same
argv and environment. There is **no process state, no memory image, no TPU HBM
snapshot, and no "execution position"**. Transparent migration is a Pathways
feature, not a property of a plain Borg job. Continuity of training is therefore
100% the application's job, via checkpoints.

### A job with no restart budget dies on its first preemption

`xm_abc.BorgScheduling` defaults to `max_task_failures=0` and
`max_per_task_failures=0`, i.e. *never restart*
(`third_party/py/xmanager/xm_abc/executors.py`). The preemption itself is a free
failure that is not counted, but when the TPU gang is torn apart the non-zero
task exit **is** counted, and Borg then declares the job dead. One preemption
kills the experiment.

Always pass an explicit `scheduling=`. `tpu_cmd/xm_launcher.py` sets it for both
tiers, defaulting to `max_task_failures=-1` (unlimited),
`max_per_task_failures=1`, `task_failure_credit_period=7200`.

The asymmetry is deliberate: a long run should survive any number of unrelated
preemptions, while a task that keeps dying is a real bug and should be declared
dead rather than retried forever. The credit period makes it read as "recover
from at most one failure per task every two hours". Shape borrowed from
`mesh_diffusion`'s launcher.

Two more settings worth copying from the same source:

- `logs_read_access_roles=['all']` on the executor, so anyone (including you,
  later) can read the job's logs without an ACL dance.
- `deepsea_ici_resilient=False` for TPU jobs. An ICI-resilient slice costs
  ~35% throughput; failing and being rescheduled onto a healthy slice beats
  finishing 1.5x slower.

### `--resume_xid` resumes; it does not point at a checkpoint

`--resume_xid` appends a work unit to an existing experiment. Because
`CHECKPOINT_BUCKET` is derived from the XID, the new attempt lands on the same
prefix, and the application's in-process autoresume finds the newest complete
checkpoint by itself. **The launcher must not also set `LOAD_FROM`.**

It used to, as `f"{bucket_cp_path}/checkpoints"` — the PARENT of the per-step
directories. orbax restores one checkpoint directory, so it looked for
`.../checkpoints/state` and died with `FileNotFoundError: Checkpoint at
.../checkpoints/state not found.` Guessing a step in the launcher is no better:
only the job can know which step finished writing. Worse, `LOAD_FROM` is an
explicit user request that autoresume deliberately yields to, so the old code
both passed an unusable path and disabled the thing that would have found the
right one. Fixed in `tpu_cmd/xm_launcher.py`.

Reserve `--load_from` for a genuinely external checkpoint (an eval target or a
warm start), and point it at a concrete `step_<N>` directory.

### The resume path is only exercised by a run long enough to be preempted

A first-time training tree holds weights; a RESUMED tree also holds optimizer
state, whose leaves include `None`, scalars and small containers. Code that
assumes every leaf is a numeric array works for the entire first attempt and
fails only on restart. `EqR-jax`'s restore guard did exactly this —
`np.asarray` turned those leaves into object arrays and `np.array_equal` raised
`ValueError: The truth value of an array with more than one element is
ambiguous`, killing XID 275793223 at step 45000 after a clean 45% of the run.

Two rules follow:

- A short sanity run does **not** validate resume. 2000-step runs never get
  preempted, so they exercise only the cold-start path. Budget one deliberate
  restart before trusting a multi-hour schedule.
- A diagnostic must never be able to kill the job it is checking. Guards belong
  behind a total comparison that returns "can't tell" instead of raising.

### A Borg job is a different IAM principal from you

The job runs as **`<user>@prod.google.com`**; your workstation is
`<user>@google.com`. They are unrelated principals, so nothing you can read
interactively is automatically readable from a TPU worker. A GCS bucket granted
to you via a project group fails on the worker with

    <user>@prod.google.com does not have storage.objects.get access ...

and the same wall blocks application-level log mirroring to that bucket. This is
by design: a job outliving your login session cannot borrow your credentials.

Ways out, cheapest first:

1. **Use CNS** (`/cns/<cell>-d/home/<user>/...`). The prod identity can read and
   write it natively, no IAM change and nobody to ask. `epath`, orbax and the
   path helpers in `utils/ckpt_util.py` all handle `/cns/` transparently, so
   this is usually a one-line change to a path.
2. Have a bucket **owner** grant `roles/storage.objectAdmin` to
   `<user>@prod.google.com`. Note an org-level **IAM deny policy** may block
   even owners; the giveaway is `due to an IAM deny policy` in the error.
3. Service-account keys are **not** an option: `iam.serviceAccountKeys.create`
   is denied org-wide.

Cross-cell CNS reads work, with latency proportional to distance — check with
`/usr/local/bin/mach_locality --locality_kind=metro <cell>` before assuming two
cells are near each other. Cells in one metro (e.g. `yutulpz`/`yutulis`/`nk`/
`nl` are all `tul`) are effectively free to read across.

### Checkpoints must not live in `workdir`

`workdir` is task-local (`/tmp/...` on a TPU worker) and is wiped by the very
event the restart budget exists to survive. A restart budget without durable
checkpoints only buys you the right to redo the run from step 0.

### `/tmp` is a RAM disk you must size yourself

`/tmp` on a Borg task is backed by `tmp_ram_fs` in `JobRequirements`, and the
default is small. Every task of a multi-task TPU job stages its own private
copy of whatever it downloads, so an undersized value surfaces mid-run as
`OSError: [Errno 28] No space left on device`. `tpu_cmd/xm_launcher.py` requests
16 GiB by default (`--tmp_ram_fs_gib`), matching `//third_party/py/maxtext`.

Also note **`fileutil` does not exist inside a Borg container**. Shelling out to
it dies with `CalledProcessError`. Use `epath` (the same client orbax uses) for
CNS I/O from inside a job.

### The env-var contract between launcher and training code

Resume/eval selectors travel as **environment variables**, not as `--config`
flags. This follows `unified_infra` (`infra/runjob.py`), and EqR-jax's `main.py`
already consumes exactly these names in `_ENV_CONFIG_OVERRIDES`.

| Env var | Set by | Meaning |
|---|---|---|
| `LOAD_FROM` | launcher `--load_from` | Checkpoint to evaluate or warm-start from. Local path or `gs://`. Explicit value always wins over auto-resume. |
| `WANDB_RESUME_ID` | launcher `--wandb_resume_id` | Tracking run to continue. |
| `CHECKPOINT_BUCKET` | launcher, always | Durable GCS prefix for this experiment's own checkpoints. Derived from the XID, so **every restart of a given XID resolves to the same prefix** — that stability is what makes in-process auto-resume well defined. |

Do **not** inject `--config.checkpoint_path`. `configs/default.py` has no such
field and the config flag is declared `lock_config=True`, so passing it makes
every job die at startup. This was a real, long-lived bug.

### Auto-resume has to live in the application

`unified_infra` solves resume from the outside: a 24/7 daemon greps each
attempt's log for the last complete checkpoint and passes it as `--load_from` on
the next launch (`infra/resume.py`, `infra/monitor.py`). Under Borg there is no
external brain in the loop — the launcher runs once, on your workstation, at
submit time — so the equivalent decision must happen **in-process at startup**.

EqR-jax implements this in `main.py::_apply_borg_autoresume` +
`utils/ckpt_util.py::latest_checkpoint`:

1. Read `$CHECKPOINT_BUCKET`; skip entirely if `LOAD_FROM` was set explicitly or
   the run is `eval_only`.
2. Enumerate `step_<N>[_<run_id>]` directories under `<bucket>/checkpoints`.
   Enumerating the prefix beats parsing logs: a rotated or lost log would
   otherwise silently restart from zero and discard real progress.
3. Skip any directory with no `extra.json`. That file is written **last**, so
   its absence marks a checkpoint that was still being written when the task
   died. This mirrors unified_infra's "a bare `Saving` with no `saved to` is
   incomplete and ignored" invariant.
4. Resume from the highest surviving step.

### `gs://` paths and the stdlib

Orbax reads and writes `gs://` natively through tensorstore, so checkpoint
payloads never need downloading. The stdlib is the problem:
`os.path.isdir("gs://...")` is always False, and `os.path.abspath` mangles the
URI into `"<cwd>/gs:/bucket/..."` — which is exactly how a remote `load_from`
turns into a bogus "directory does not exist" error. Route every existence check
through the `is_remote_path` / `resolve_path` / `path_is_dir` / `path_exists` /
`read_text` / `write_text` / `join_path` helpers in `utils/ckpt_util.py`
(backed by `etils.epath`, an orbax dependency).

## Preflight & Router (client-side pre-check before packaging)

Bazel packaging of an XM job costs ≈5 min. Submitting a job that the allocator
will reject in seconds wastes that time. `tpu preflight` runs client-side
checks in ≈15s to catch common failure modes BEFORE packaging.

### `tpu preflight` verdict layers

1. **L1 (µs, in-process)**: topology whitelist + per-alloc PROD min-slice
   rules (e.g. `deepmind-dynamic/*` forbids v6e slice < 16 chips). Catches
   `v6e-8`, `v6e-13`, `v7-8`, `v5p-8192`, and similar.
2. **L2 (~1 RPC, ~1–2s)**: `GoodputService.GetCellAvailability` → do any
   cells in this alloc + tier have ≥ request-chip count *obtainable*? Catches
   `alloc has 0 chips of this platform`, `all cells drained`, etc.
3. **L2.5 (heuristic)**: PROD headroom — if `remaining_quota < 2× request`,
   warn (YELLOW). If the pool is bursty this may still succeed; if not, expect
   `RESOURCES_EXCEEDED`. On `deepmind-dynamic/*` this warning is near-permanent
   and low-signal; see "Dynamic allocs: `Available = 0` is normal".

Verdict is one of **GREEN / YELLOW / RED**. `tpu queue` refuses to submit on
RED unless `--force` is passed. YELLOW proceeds with a warning. Use
`--skip-preflight` to bypass entirely.

### What preflight canNOT catch (important)

**Topology fragmentation** — e.g. the alloc has 1000 free v6e chips *in total*
across many cells, but no single cell has a contiguous `4x4` slice free. The
allocator will accept the submit, then reject seconds later with `Rejected by
Allocator/Borg`. **A GREEN preflight verdict is therefore a necessary but NOT
sufficient condition for success.**

The only API that reports free-slice topology counts is
`BorgMaster.ProbeSliceAvailability`, which is C++ only (no Python stubby
wrapper) and requires per-cell fan-out plus ACL grants. Building this is
tracked; today the workaround is the existing daemon auto-retry loop for
`PROD + "Rejected by Allocator/Borg"` (5 retries, 5-min gap).

Other things preflight cannot see: the exact GQM auction outcome for BATCH
(nobody can), transient BCID/attribution rejects, Research Hub attribution
prompts.

### `tpu route` (local router)

Given a desired *power class* (compute-equivalent), suggest the best
`(group, tpu_type, CELL)` combo across your allocations:

```
tpu route --power=v5p-32 [--tier=PROD] [--groups=1,3,5] [--top=3] [--explain]
# power can be 'v5p-32', 'v6e-16', 'v6p-8', 'v7-8' (all equivalent), or a bare int.
```

Power equivalence (heuristic, v5p-chip units):
`1 v4 = 1 v5p = 0.5 v5e = 0.5 v6e = 0.5 v6p` chips.

Router fans out preflight checks in parallel (≈30s for 9 groups × 5 archs),
then ranks survivors by:

1. Not blocked by a limit order (a blocked combo is never recommended, but it
   is kept and explained rather than silently dropped — `--explain` lists them
   with the cap, the pool price, and who set the cap).
2. Verdict status (GREEN > YELLOW; RED filtered out).
3. Headroom — **and this differs by tier on purpose**: PROD uses
   `remaining_quota / requested_chips`; BATCH uses obtainable chips, because the
   BATCH pass never consults `floor_v2` at all, so "BATCH quota" is noise.
4. `cost_per_hour` = `chips × per-cell price` — prefer cheaper cells.
5. Accelerator preference (v6e > v6p > v5p > v4 > v5e).

Market data (per-cell prices + limit orders) comes from
`~/.tpu_quota_cache_dir/market.json`, written by `money_check` on each daemon
round, so the router stays offline and fast. If it is missing or stale the
router says so loudly and falls back to price-blind ranking rather than failing.

`tpu queue --power=` forwards the recommended cell as `--cell=<name>` (an
explicit `--cell` always wins) and refuses to submit when every candidate is
blocked, unless `--force`.

**Router does not solve L3 fragmentation either.** It picks the group with
the most headroom, but if all groups' available chips are fragmented, the
top-1 pick will still fail post-packaging. Consider running the router with
`--top=3` and manually preferring cells that historically succeed for you.

### `tpu queue --power=` shortcut

Instead of specifying `--group` and `--tpu_type`, pass `--power=` and the
wrapper will call the router internally, pick top-1, print the choice, then
preflight + submit.

### Full command reference

See `~/work/tpu_cmd/README.md` for exhaustive flag documentation and common
workflows. Highlights:

- `tpu queue --force` — override RED verdict.
- `tpu queue --skip-preflight` — skip the check entirely.
- `tpu preflight --json` — machine-readable verdict.
- `tpu route --verbose` — stream per-candidate probe results.

## TPU Topology & Performance Equivalences

> Codenames, `ResourceType` ids, HBM per chip, and the legal shape table now
> live in `tpu_reference.md`. The allocator-policy notes below stay here.


Source of truth for legal topologies is `borg/common/locus_info.cc` (NOT
`learning/performance/ace/search_space_utils.py`, which is stale for v6e).
The wrapper's `preflight/topology.py` mirrors the relevant subset; add new
accelerators there.

### Legal shapes per accelerator

| Arch | Codename | Torus | Legal chip counts | Locus example |
|---|---|---|---|---|
| v4 | pufferfish | 3-D | 8, 16, 32, 64, 128, 256, 512, 1024, 2048 | `v4-32` → `2x2x4` |
| v5p | viperfish | 3-D | 8, 16, 32, 64, 128, 256, 512, 1024 | `v5p-64` → `4x4x4` |
| v6p | ghostfish | 3-D | 8, 16, 32, 64, 128, 256, 512 | – |
| v6e | ghostlite_pod | 2-D (8/machine, pod = 16×16) | 8, 16, 32, 64, 128, 256 | `v6e-16` → `4_4` |
| v5e | viperlite_pod | 2-D | 8, 16, 32, 64 | `v5e-16` → `4_4` |

Borg expects the shaped locus string (`2x2x4`, `4_4`, `16_16_wrap_xy`) NOT
the scalar core count. `xm_launcher.py` handles this translation.

### Per-allocator PROD min-slice policies (empirical)

Allocators inside `deepmind-dynamic/*` (including `vqfree-xm`,
`viscam-interns`, `gdm-viscam-goflow-dynamic`, etc.) enforce **min slice = 16
chips** at PROD tier for v4/v5p/v6e/v6p. Below that, the allocator rejects
instantly with `Rejected by Allocator/Borg`. These are pool policies, not
physical Borg rules — `v6e-8` (`locus:...:2_4`) is a valid Borg locus, it's
just disallowed by the deepmind-dynamic admission config.

BATCH tier typically allows down to the arch's minimum legal chip count.

`preflight/topology.py::_ALLOC_MIN_SLICE_RULES` encodes these; if you hit an
allocator with different rules, update that table.

### Performance Equivalence

Canonical table lives in `tpu_reference.md` § Performance Equivalence — read it
there, including the caveats that a single compute scalar cannot express
(memory-bound work does not follow it, and int8 gains do not survive the move
to v6p/v7). Short form: per chip, `v6p = v7 ≈ 4.34× v5p ≈ 2.17× v6e`, so
`v6p-8 ≈ v7-8 ≈ v6e-16 ≈ v5p-32`. `tpu route --power=` encodes it in
`router.py::_V5P_MULTIPLIER`.


## Status And Diagnosis

1. Start with `tpu check` and resolve the exact experiment and work unit.
   Experiment-level `RUNNING` does not prove that hardware was allocated; use
   work-unit state, allocation, logs, and activity to distinguish queued from
   executing.
2. Read the complete relevant failure, not only the final status string. An
   immediate failure without logs can be allocator, topology, packaging, or
   authorization related.
3. If the error explicitly indicates expired or invalid credentials, ask the
   user to run `gcert`, then retry the read. Do not diagnose every access or
   missing-log failure as a credential problem.
4. If normal log access still fails after identity is valid, use the supported
   XManager API or `tpu_utils` in the current Google3 checkout to inspect the
   work-unit status message. Do not patch shared scripts with hard-coded job ids,
   and do not assume an alternate API bypasses authorization.

### Job bookkeeping

`~/.tpu_jobs.json` is the live registry `tpu check` renders from;
`~/xm_job_to_bucket/` is its predecessor and is no longer written to (last
entry 2026-07-26) — only `--resume_xid` still falls back to reading it.

`tpu clear <xid> | all` **archives** rather than deletes, moving entries to
`~/.tpu_jobs_legacy.json`. Keep that file: an entry is the only mapping from an
XID back to its checkpoint bucket, staging dir and launch log once the Borg job
and work unit are gone.

`tpu cancel <xid> [xid...]` (alias `tpu stop`) stops the experiment via
`xmanager stop --skip_confirmation` and pins the registry entry
(`status=CANCELLED`, `retry_count=5`) so the daemon's PROD auto-retry can never
resubmit an explicitly killed job. `--dry-run` previews. Cancel is not clear:
the entry stays on the board until archived.

### TPU Check Error Rules & Auto-Retry Mechanism

The backend `tpu_check_daemon.sh` parses XManager launch logs and classifies errors as follows:

*   **Preempted by Defag**: Greps for `SLICE_DEFRAGMENTATION`.
*   **Resource Exhausted (Topology/Quota)**: Greps for `RESOURCE_EXHAUSTED` or `RESOURCES_EXCEEDED`.
*   **Rejected by Allocator/Borg**: Fallback for `FAILED` status with an empty or `unknown reason`.
*   **Unknown failure**: Greps for `FAILED` when `Preempted` is not present.

**Auto-Retry Policy**:
If a job is queued in the **PROD** tier and fails specifically with **"Rejected by Allocator/Borg"**, the daemon will automatically retry launching the job up to **5 times**, waiting 5 minutes (300 seconds) between each attempt.

That client-side retry is the daemon **resubmitting a new experiment**, which is
a different mechanism from the in-job Borg restart budget described in
§Preemption, Restart, And Resume. Preempted jobs are *not* covered by it.

**A preempted job is dead, not pending.** With `max_task_failures=0` (the old
default, see §Preemption) Borg counts the torn-down gang as a task failure and
never re-queues it. `tpu check` used to render any work unit whose status
message merely contained "preempt" as PENDING, which made dead experiments look
like they were still waiting in a queue for hours. Terminal state must win over
the preemption substring; a genuinely-queued job that was preempted earlier is
labelled `... (was preempted)`. Fixed in `infra_check.py` and `tpu_wrapper.sh`;
`infra_check` must be rebuilt with `blaze build` for the daemon to pick up
changes.

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this guide whenever implementation details change.
