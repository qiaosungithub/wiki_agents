# Reporting Job Status To The Operator

How to answer when the operator asks for job status. Two chapters: **Chapter 1**
is what a good answer looks like, **Chapter 2** is how to build one. Part of the
`jobs/` set; the hub is `../jobs.md`. Siblings: `submit.md`, `resume.md`,
`liveness.md`, `diagnose.md`.

The default in one line: a board the operator can scan in five seconds, never
prose.

---

## Chapter 1 — What A Good Answer Looks Like

### The answer is a board, not an essay

**When the operator asks for job status, emit these blocks in order and nothing
else: one table of the operator's own LIVE jobs, a short list of anything WRONG,
the few most-recently FINISHED jobs, and every PENDING and HELD job by name.**
The default length is the tables themselves. Do not add a preamble, emoji, bold,
or a per-job heading or commentary; do not write a "worth noting" or "two
things stand out" summary; do not narrate what you are about to check; and do
not end with a question unless a real decision is the operator's to make. If a
value needs a metrics read, do it now rather than promising to look later.

### The template

**Copy this template, fill every column, and invent nothing; use `—` where a
value does not yet exist (a job that is not RUNNING has no progress and no ETA),
never a guess.**

```
Live jobs (N)
NAME                                XID        TPU     TIER  STATUS    PROGRESS       ETA (approx)
raft-small-C-betahi-b095b09b09      288691820  h100-8  PROD  running   38k/100k  38%  ~5h
parcae-140m-fixed8-lr8e3            288694113  b200-4  PROD  starting  —              —

Problems (N)          # omit this block entirely if there are none
- <name> (<xid>): <one line: what is wrong and, if the operator must decide, the option>

Recently finished (most recent first, order approximate)
- <name> (<xid>) <tpu>   # DONE, finished normally

Pending (N)
- <name> (<xid>) <tpu>: <one line: total wait since first submit, and why still queued>

Held (N)
- <name> (<xid>) <tpu>: <one line: what it is and why held>
```

---

## Chapter 2 — How To Build It

### Filling the live-jobs table

**PROGRESS and ETA are the point of the report, and neither comes from
`tpu check`:** its STEP column reads 0 even for a job that has run for a day, and
its AGE resets when a job re-routes, so never transcribe either.

| Column | Where it comes from |
|---|---|
| Scope | Only jobs `tpu check` shows. The `npu` aliases drive a SEPARATE fleet with its own `npu check`; never fold npu jobs in. |
| Owner | Only the operator's OWN jobs. Drop every `lyy-*` (colleague) or otherwise non-owner prefix; mention the shared-budget fact once only if it matters. |
| PROGRESS | `step / target` as a percent. Read the current step from the job's OWN metrics: resolve its bucket from `~/.tpu_jobs.json` (`bucket_cp_path`) and read via `../research/result_logging.md` §Reading The Curves From The Workstation, route 1. Take the target from the job's launch config. If the target is genuinely unknown, report the raw step and rate and mark the percent unknown; never substitute `tpu check`'s STEP. |
| ETA | remaining steps ÷ current rate, always flagged approximate. The rate wanders, so this is a rough figure. A long wall-clock age next to a low percent means the job was preempted and reset its clock, not that it stalled. |
| STATUS | `running` / `starting` / `building` as `tpu check` reports it. A non-RUNNING job's PROGRESS and ETA are `—`. |

### Finished, pending, and held

**List every PENDING and HELD job BY NAME, even one that looks like junk;
whether to drop a redundant job is the operator's call, not the report's.**

- **Finished**: read from `~/.tpu_local_queue.json`, not from `tpu check`'s
  "recent done", which mixes genuinely-finished jobs with CANCELLED ones
  (superseded by a fix or rerun) and FAILED ones. A truly-finished row has
  `state: DONE` and `last_reason: ... XM reports COMPLETED ... finished normally`;
  a CANCELLED sibling is a supersede, not a result. The store keeps only
  `submitted_at` (no finish time), so order by submit time, flag the ordering
  approximate, and list the few most recent.
- **Held**: say what it is and why it is held (redundant/superseded, or a real
  job that needs recovery). A HELD row means the re-router gave up on placement
  and it needs a human.
- **Pending is a market state, not automatically a fault.** Before flagging one,
  assess three things and report the first that applies: (1) the TOTAL time
  queued since the job's FIRST submission, not the current work unit's age, since
  a re-routed job resets its per-WU clock while the real wait runs on; read the
  earliest ancestor's submit time; (2) whether any accelerator the job may use is
  currently UNDER its limit-order cap (`../tools/limit_order.sh status`); if every
  eligible arch reads `BLOCKING`, PENDING is the expected outcome and nothing is
  wrong; (3) whether it was submitted spec-compliant (SEVERAL `--archs`, ALL data
  `--metros`).

### What to flag as a problem

**Flag a job only when it is SLOW, STUCK, or OUT OF SPEC, and give it one line.**

- **SLOW**: throughput far below a sibling on the same hardware.
- **STUCK**: HELD; or PENDING despite the three checks above (it has waited long,
  at-price capacity exists, and it is spec-compliant yet still not scheduling);
  or sitting in `starting` / `building` far longer than its siblings (minutes,
  not hours). For a long `starting`, check the launch log rather than reporting
  the age alone.
- **OUT OF SPEC**: a TRAINING job not on `--tier=PROD`, or any job pinned to a
  SINGLE arch or SINGLE metro. Every job should name SEVERAL `--archs` and
  SEVERAL data `--metros` (`submit.md` Chapter 3 §Router and placement flags); a
  lone arch re-places into the same contested pool and sits PENDING for hours.
  When the operator authorizes a re-enqueue, use
  `--power=<same> --archs=v7,v6p,v5p --metros=<several data metros>` and do NOT
  add `--group`: the router auto-selects it and prefers g3/g5 over g9 at PROD to
  spare the regulated g9 budget (`../infra/tpu_cli.md` `_GROUP_PREF`; `submit.md`
  Chapter 1 §The budget gate). `tpu enqueue`'s "pass --group=9 to pin it" line is
  a tradeoff hint, not a requirement.
