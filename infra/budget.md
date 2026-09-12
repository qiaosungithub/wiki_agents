# The income/10 Budget Gates

Two gates keep active PROD spend under a hard cap of one tenth of rolling G9
income. `budget_check.py` gates every NEW launch; `budget_enforcer.py` is a
resident daemon that pauses ALREADY-RUNNING jobs when a price rise pushes the
aggregate over the cap. Both live in `../tools/`. This is the spend policy that
sits on top of the market in `market.md`; the tool that enforces it is
`tpu_cli.md`.

**The cap is income/10, and it applies to both operators.** Operator boss
directive (2026-08-25) set the credit hard cap at one tenth of G9 income
(tightened from 1/5, and 1/3 before that). Both the `tpu` and `npu`/lyy agents
run through the same gate, so each is capped at income/10 independently. `bar =
income / 10`; a job counts against it as `chips × price`, where BATCH costs 0
against the bar (see below).

## Principle

### Two Gates, One Cap

**`budget_check` stops a job from starting; `budget_enforcer` stops a running
job from staying started when the price rises under it.** The launch gate cannot
cover a market move that lands after admission, so the daemon closes that gap by
periodically recomputing active PROD cost and shedding load when it goes over.

Both share one accounting caliber (`compute_current_cost` / `get_job_cost` /
`chip_price` in `budget_check.py`), so the two gates price a job identically:

- **`current`** = projected cost of all your live SUBMITTED/RUNNING jobs, summed
  from the registry, zombie-filtered against the check cache and XM truth.
- **Pricing basis is market-when-fresh, else the policy cap.** The market price
  is read from the money cache (`~/.tpu_quota_cache_dir/money.txt`) when it is
  under 6 h old; otherwise each family falls back to a conservative per-arch
  policy cap. Both paths are announced in the output, because a silent switch
  between two costing bases later reads as "the numbers changed for no reason".
- **Accounting is at spot price, so admission is time-dependent**: the same
  batch can pass now and be refused twenty minutes later. That is a deliberate
  trade the operator asked for, not a bug.

### What Is Exempt From The Bar

**Four kinds of demand do not draw on the G9 income/10 bar. Each is a positive
test on the job's identity, never `new_cost == 0`** — a parse miss (`v7_32`,
a typo) also yields 0 cost, and keying on cost would wave those through as an
unbounded spend path.

| Exempt | Why | Caveat |
|---|---|---|
| g3 / g5 groups | separate dynamic pools with their own credit balance; they never spend G9 income | fail-closed: an unknown/absent group is treated as capped G9 |
| BATCH tier | draws 0 against the **PROD** income/10 bar | **still billable** at the BATCH clearing price — BATCH is a paying best-effort tier, not "free" (`../AGENTS.md`) |
| CPU-only | no chips, so it cannot consume a chip budget; runs in a static pool with no credit balance | keyed on the `cpu` name, so an unparseable TPU type stays on the refusing side |
| free-pool family (cleared at 0.00 this cycle) | adds no credits/hr, so refusing it protects nothing | only the single incoming job skips the comparison; free-pool families still contribute their policy cap to `current`, and spend stays bounded by the per-XID limit order |

### budget_enforcer Pauses, It Does Not Kill

**When active PROD cost exceeds the cap, the enforcer cancels the fewest jobs
(most-expensive-first) and re-enqueues each as a resume, so the price drop later
relaunches it from its checkpoint.** A cancelled job frees chips and stops
billing; the re-queued resume costs nothing while PENDING, so the pause itself
never violates the cap, and `budget_check` gates the eventual relaunch. Removing
the most expensive jobs first clears the overage with the fewest cancellations.

**It is a resident armed daemon, not a hand-run script.** The ops watchdog
(`~/.tpu_bin/tpu_ops_watchdog.sh`, cron `*/2`) keeps it up alongside the rest of
the pipeline (`../projects/local_agent_cli.md`); it loops every `--interval`
(default 120 s).

The safety design is layered, because cancelling a running training is
irreversible:

- **Dry-run by default; `--arm` is required to cancel anything.** Without it the
  pass only prints the plan.
- **`--max-cancels` bounds one pass** (default 3), so a bad price spike cannot
  mass-cancel the fleet in one tick.
- **`--sustained-over-seconds` debounces income jitter.** Income can swing 2x
  within minutes, and `cap = income/10` swings with it, so the aggregate can be
  transiently "over" while cost barely moved. The timer requires the overage to
  persist N consecutive seconds; any pass back under cap resets it. Default 0
  keeps the original act-on-first-over behaviour.
- **Every candidate is verified against XM before acting.** The ledger keeps
  dead jobs `SUBMITTED` long after they die, and cancelling a corpse books its
  cost as savings that never materialise — the pass then reports success, stops
  early, and the job actually burning money is never touched. A candidate XM
  cannot confirm as `RUNNING` is treated as dead and skipped (fail-safe: cutting
  the wrong job destroys work; skipping one only defers to the next pass).

### The Checkpoint Safety Gate

**A pause is only safe if the job can later resume from a checkpoint, so the
enforcer physically verifies the checkpoint exists before cutting, and refuses
otherwise.** `_has_checkpoint_on_disk` runs `fileutil ls` on the ledger's
`bucket_cp_path`. The direction is fail-safe: a confirmed checkpoint allows the
pause; a confirmed absence or an unreachable CNS both refuse it — "can't confirm
→ don't cut", because cutting a job with no checkpoint is permanent loss of
progress, not a pause. The over-cap simply pauses one fewer job that round.

**Blind auto-resume is off by default, because it would overwrite the real
checkpoint with the wrong recipe.** The enforcer's re-queue entry carries only
`resume_xid`, with no `--config`; `xm_launcher` then falls back to its default
recipe (`remote_run`) and writes over the original checkpoint prefix. That is
worse than leaving the job stuck. So by default the enforcer records a
pending-resume note (`~/lyy-work/.npu_pending_resumes.json`, written atomically)
for a human to relaunch with the correct config, rather than resuming blind.
`--unsafe-blind-resume` restores the old behaviour and is named to warn.

Two more gates guard the re-queue target: the ledger and the local queue must be
a known pair (a resume enqueued into the wrong operator's queue is HELD forever,
because the build-worker looks up the stagedir under its own `TPU_JOBS_FILE`),
and a resume must go behind fresh work (`--priority=-1`) so the enforcer's own
re-queue never jumps the line.

## Usage

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
the launcher runs before every launch (`../jobs/submit.md`).

### Running The Enforcer

Inspect a single pass without touching anything:

```
budget_check_dir=~/work/wiki_agents/tools
python3 $budget_check_dir/budget_enforcer.py --once           # dry-run, prints the plan
```

Arm it only deliberately, and always point `--jobs-file` / `--local-queue-file`
at the right operator (the defaults are the `tpu` agent's; `npu`/lyy has its own
registry and queue). The watchdog already runs the armed daemon, so a hand-run
armed instance is for recovery, not routine.

## Errors

### Mispricing Kills Jobs — The Biggest Measured Survival Threat On GPU

**A family missing from the price table falls through to the 100 cr/chip-hr
catch-all, which ranks a free job with the fleet's priciest and gets it cut
first.** Measured: a `b200-8` PROD soak ran 6 h 18 min with zero preemptions,
then the enforcer stopped it at `cost=800` (8 chips × 100) while
`budget_check --query b200-8 PROD` returned 11.4 and the router happily admitted
a sibling at that price. Mispricing, not preemption, was the biggest measured
survival threat on GPU. **If a long GPU job vanishes, grep your XID in the
enforcer log before assuming preemption**, and compare numbers against
`budget_check`, not the enforcer's header comment. The GPU and v7 families now
have their own policy caps, but treat any family newly added to the fleet as a
mispricing suspect until its row exists.

### A Daemon Prices From The Table It Imported At Startup

**A long-lived daemon holds the pricing tables it imported at process start, so
a fix on disk lands only after a restart.** Same job, same enforcer, two minutes
apart across a restart: `cost=800` before, `cost=6` after, while the corrected
table sat on disk for an hour and the daemon kept killing jobs at the stale one.
This is not only `environ`; any imported Python module is frozen at start, and
nothing in the code hints at a one-time read. Check the daemon's start time
against the mtime of what it imports, and verify a fix from the running process,
not the file.

The memo has a second face inside one process: `chip_price` caches the parsed
market for 60 s and re-reads after, but an earlier version read once and never
again. That froze the enforcer (a days-long daemon) on a day-old price while the
launch gate — a fresh process each time — saw the current one, so the two gates
disagreed 3x at the same instant: launches blocked on the high price while the
enforcer, whose whole job is to shed load when prices rise, sat idle on a stale
one saying "nothing to pause". A wrong number that never changes is worse than
no number.

### The Two Gates Disagreeing Is A Pump

**When the launch gate and the enforcer price a family differently, the launcher
admits jobs the enforcer then kills — and it runs fastest exactly when chips are
cheapest.** A free-pool family is admitted precisely because it is free; the
jobs accumulate; then an enforcer that prices free chips at the policy cap kills
them for a cost they do not have. Measured with v7 at 0.00: 15 running jobs
cancelled in 10 minutes. The fix is that both sides skip free-pool families
identically. Any change that reprices one gate must reprice the other, or it
reopens this pump.

### A Free PROD Row Read As BATCH's Price

**Parsing the money board must stop at the next tier row, or a PROD row with no
price of its own reads the neighbouring BATCH number.** A tier block is three
rows; a blind four-row window reaches into the next tier. It only bites when
PROD carries no parsable price — i.e. `0.00 (free pool)` — and then the fallback
reads BATCH's figure as PROD's. Measured: v7 PROD "free pool" priced at BATCH's
556 cr/chip-hr, 5.6x the policy cap, and the enforcer cancelled 15 running jobs
over two passes to defend a budget they were not spending. The error is
one-directional: the cheaper PROD really is, the more expensive it reports,
because a free PROD row is exactly the one with no number of its own.

### The Projection Trap: A Cheap Job Priced As Expensive At The Gate

**The router queries budget with `lo_price=0`, so `new_cost` is the full
on-demand projection, but the wrapper auto-caps the submitted job to the
per-arch policy price — so the gate can reject on a price the job never pays.**
A `gb200-8` projected at 800 (the catch-all) with `lo_price=0`; the same
`--query` with `lo_price=0.20` returns `new_cost=1.6, fits=true`, because
`_tpu_set_limit_order` caps `gb200` at 20 cr/GPU-hr. This is a gate-precision
gap, not real unaffordability. **Do not patch the shared wrapper/router budget
logic without operator sign-off** — it is a fleet-global lever.

### A Stale Ledger Manufactures An Overage That Is Not Live Spend

**The ledger keeps dead jobs `SUBMITTED` with no timestamp and absent from the
check cache, so both existing zombie filters miss them, and their phantom cost
reads as an overage.** The check-cache filter needs the XID to be in the cache
(these are absent); the `STALE_HOURS` filter needs a parseable timestamp (these
carry none). The enforcer's XM-verification step is what catches them: it
confirms each candidate is `RUNNING` before cutting, so a pass over an
all-dead candidate set correctly pauses nothing and reports the overage as an
accounting artefact, not live spend. If the enforcer reports "over cap" but
every candidate is skipped as dead, reconcile the registry — the money is not
actually being spent.

### A Stop That Reports OK May Not Have Re-Queued

**The pause path stops first and re-enqueues second; if the second half fails,
the log still shows the pause succeeding and the job never returns.** Read the
lines after the `OK`: a two-step operation reporting only step one is a silent
success (`../AGENTS.md` §Evidence Order). With blind resume off (the default),
"cancelled; auto-resume WITHHELD ... NEEDS MANUAL RESUME" is the expected,
correct outcome — the job is waiting in the pending-resume file, not lost.
