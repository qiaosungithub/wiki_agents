# Reporting Job Status To The Operator

Part of the `jobs/` set; the hub is `../jobs.md`. Siblings: `submit.md`,
`resume.md`, `liveness.md`, `diagnose.md`.

**When the operator asks for job status, answer with the SHORTEST useful list:
one row per LIVE job carrying its status, progress as a percent of its step
budget, and an approximate finish time; the jobs that recently FINISHED; and a
short list of the jobs that have an obvious problem.** The operator wants a
glance, not a report.

- **Cover only the jobs `tpu check` shows.** The `npu` aliases drive a SEPARATE
  fleet with its own `npu check`; never fold npu jobs into a `tpu check` status
  list.
- **Report only the operator's OWN jobs; filter by owner prefix.** This
  workstation is shared with colleague `lyy`, whose experiments carry an `lyy-`
  name prefix (e.g. `lyy-llava-*`). They appear in the operator's `tpu check`
  because they were launched from the shared registry, and some even run in the
  operator's g9 group (so they DO consume shared budget) — but they are NOT the
  operator's runs. Drop every `lyy-*` (or otherwise non-owner) job from the
  status list; mention the shared-budget fact once only if it matters.
- **The `tpu check` STEP column is not a progress signal** — it reads 0 even for
  a healthy job that has run for a day. Read real progress (`step / target`) from
  the job's own metrics: resolve its bucket from `~/.tpu_jobs.json` and read the
  log/metrics there (`../research/result_logging.md` §Reading The Curves From The
  Workstation, route 1).
- **ETA = remaining steps ÷ current rate, always flagged approximate**: the rate
  wanders and a preempted job resets its wall clock while keeping its step count,
  so a long wall-clock age next to a low percent means preemption, not a stall.
- **Also report the jobs that recently FINISHED, most recent first, and read
  them from `~/.tpu_local_queue.json` (`state: DONE`), NOT from `tpu check`'s
  "recent done" — that bucket mixes genuinely-finished jobs with CANCELLED ones
  (superseded by a fix or a rerun) and FAILED ones.** A truly-finished row
  carries `last_reason: ... XM reports COMPLETED ... finished normally`; a
  CANCELLED sibling is a supersede, not a result, so label the two differently
  and never count a supersede as a completion. The store keeps only
  `submitted_at` (no finish timestamp), so order by submit time and flag the
  ordering approximate.
- **Always list every PENDING and HELD job BY NAME, even one that looks like
  junk.** A HELD row is the operator's decision to make, not the report's to
  drop: say what it is and why it is held (redundant/superseded, or a real job
  that needs recovery), never omit it.
- **A PENDING job is not automatically a problem; queued is a market state, not
  a fault.** Before flagging one, assess three things and
  report the first: (1) the TOTAL time queued since the job's FIRST submission,
  not the current work unit's age — a re-routed or re-enqueued job resets its
  per-WU clock while the real wait runs on, so read the earliest ancestor's
  submit time, not the visible row's AGE; (2) whether any accelerator the job is
  allowed to use is currently UNDER its limit-order cap
  (`../tools/limit_order.sh status`); if every eligible arch reads `BLOCKING`,
  PENDING is the expected outcome and nothing is wrong with the job; (3) whether
  it was submitted spec-compliant (SEVERAL `--archs`, ALL data `--metros`). Call
  it a problem only when it has waited long AND at-price capacity exists AND it
  is spec-compliant yet still not scheduling — or when it is out of spec.
- **Call a job a problem when it is obviously SLOW** (throughput far below a
  sibling on the same hardware), **STUCK** (HELD, or PENDING despite the checks
  above), or
  **OUT OF SPEC** — a TRAINING job not on `--tier=PROD`, OR a job pinned to a
  SINGLE arch / single metro. Every job must name SEVERAL `--archs` and SEVERAL
  `--metros` (`submit.md` §Give The Router More Than One Way To Say Yes); a lone arch (e.g. a
  single `v5p-128`) can only re-place into the same contested pool and sits
  PENDING for hours. When the operator has authorized it, re-enqueue with
  `--power=<same> --archs=v7,v6p,v5p --metros=<several data metros>`. Do NOT add
  `--group`: the router auto-selects it and PREFERS g3/g5 over g9 at PROD to
  spare the regulated g9 budget (`../infra/tpu_cli.md` `_GROUP_PREF`;
  `submit.md` §Budget Checking). `tpu enqueue`'s "no --group given ... pass --group=9 to
  pin it" line is a tradeoff HINT, not a requirement — pinning g9 spends the
  regulated budget AND, on the earlier stuck job, re-landed the bad single
  `v5p-128` pin. Let the router choose the group.

