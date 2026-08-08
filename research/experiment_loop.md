# Experiment Management

Owns the cycle of a long-running research loop: what to check each pass, what to
keep, and what evidence a tracker can and cannot give you. `../engineering.md`
owns diagnosis and how to report a result; `result_logging.md` owns the
spreadsheet. **A research loop preserves reasoning, not just launched jobs**:
keep a stable objective/constraints note and a living results table in the
project, and revisit both every cycle.

## One Cycle

1. Re-read the objective, active hypotheses, budget, and previous conclusions.
2. Inspect each active chain's status; use logs to investigate anything changed
   or terminal.
3. Record new metrics and checkpoint facts **before** interpreting them.
4. Separate code/config failures from transient infra ones — a code bug or an
   OOM needs a fix and a new execution. Classify per `../engineering.md`; a
   traceback string alone is not a code bug.
5. Compare runs at equivalent steps and protocols. Prefer one-variable ablations
   and state the evidence for the next decision.
6. Launch, stop, or wait, then update the results and next-action notes before
   ending the cycle.

**Do not kill a run from one noisy point**: require a sustained trend against a
truly comparable baseline, unless there is a hard failure or an urgent budget
need. Do not relaunch preempted work by hand if the infrastructure retries, and
**prefer scheduled checks over busy waiting**, at a cadence matching checkpoint
and evaluation frequency rather than an arbitrary timer.

## Durable Records

**Retain per run**: job id, tracker identity (WandB, XManager, or another
backend), staged config or commit, important hyperparameters, data recipe,
region/accelerator type, logdir, metric timeline, status, and conclusion. Use
descriptive run notes, so a human can identify purpose and cost class without
reconstructing the launch command — but **prose notes never override the
effective staged config** observed in the tracker or logs. **A run that reaches
a conclusion is also logged to the project's experiment spreadsheet with its
chart link** (`result_logging.md`); a run that only exposed a code bug or an
infra failure is not.

## Tracker Evidence

**Identify the actual tracking backend before querying it** — `EqR-jax` routes
WandB-shaped calls to DeepMind Datatables, and `result_logging.md` §Chart Links
owns the URL forms and how to verify a run wrote metrics at all. For a real
external WandB run, resolve the exact entity/project/run and enumerate
`run.files()` before downloading: `output.log` is common, not guaranteed, so use
a run-scoped temporary directory when it exists.

**Never assume redirected stdout, child-process output, an offline run, or a
crashed process uploaded complete console logs.** Compare tracker artifacts
against the job's authoritative logs and staged config, and keep the pointer to
the original trace when recording a conclusion.
