# Experiment Management

A long-running research loop should preserve reasoning, not just launch jobs.
Keep a stable objective/constraints note and a living results table in the
project, then revisit both every cycle.

## One Cycle

1. Re-read the objective, active hypotheses, budget, and previous conclusions.
2. Inspect each active chain to check its status; use logs to investigate
   anything changed or terminal.
3. Record new metrics and checkpoint facts before interpreting them.
4. Separate code/config failures from transient infra failures. Code bugs and
   OOMs require a fix and a new execution.
5. Compare runs at equivalent steps and protocols. Prefer one-variable ablations
   and state the evidence for the next decision.
6. Launch, stop, or wait. Update the results and next-action notes before ending
   the cycle.

## Durable Records

For every run, retain the job id, tracker identity (WandB, XManager, or another
backend), staged config or commit, important hyperparameters, data recipe,
region/accelerator type, logdir, metric timeline, status, and conclusion.

Use descriptive run notes so humans can identify the purpose and cost class
without reconstructing the launch command. Do not let prose notes override the
effective staged config observed in the tracker or logs.

## Tracker Evidence

- Identify the actual tracking backend before querying it. `EqR-jax` routes
  WandB-shaped calls to DeepMind Datatables; `spreadsheet.md` §Chart Links owns
  the URL forms and how to verify a run actually wrote metrics.
- For a real external WandB run, resolve the exact entity/project/run and
  enumerate `run.files()` before downloading. `output.log` is common, not
  guaranteed; use a run-scoped temporary directory when it exists.
- Do not assume redirected stdout, child-process output, an offline run, or a
  crashed process uploaded complete console logs. Compare tracker artifacts with
  the job's authoritative logs and staged config.
- Preserve the original trace or log pointer when recording a conclusion.
  Summaries are navigation aids, not substitutes for evidence.
- A run that reaches a conclusion is also logged to the project's experiment
  spreadsheet, with its chart link; see `spreadsheet.md`. Runs that only exposed
  a code bug or an infra failure are not.

## Decision Discipline

- Do not kill from one noisy point; require a sustained trend against a truly
  comparable baseline unless there is a hard failure or urgent budget need.
- Do not treat a traceback string alone as a code bug; read the deepest relevant
  failure and check for an earlier OOM or environment error.
- Do not relaunch preempted work manually if the infrastructure handles retry.
- Prefer scheduled checks over busy waiting. The cadence should match checkpoint
  and evaluation frequency, not an arbitrary timer.
