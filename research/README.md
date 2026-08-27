# Research Workflow

How to run an experiment program and record what it produced. A run that reaches
a **conclusion** is logged to the spreadsheet; one that only exposed a code bug
or an infra failure is not — see `result_logging.md`.

| Read | When |
|---|---|
| `result_logging.md` | Writing a result into the shared experiment spreadsheet, or finding the chart for a job. Read it **every** time you log — headers and layout drift. |
| `accelerator_choice.md` | Choosing between v6p / v6e / v5p, or a preemptible slice keeps being lost: measured hold times, why a capacity table does not predict acquisition, and how to probe before committing. |
| `v7_storage_placement.md` | Choosing a metro for a v7 run: the standing three-metro decision, and how to regenerate the survey behind it. |

## The Research Loop Preserves Reasoning, Not Just Jobs

Keep a stable objective/constraints note and a living results table in the
project, and revisit both every cycle. One cycle:

1. Re-read the objective, active hypotheses, budget, and previous conclusions.
2. Inspect each active chain's status; use logs to investigate anything changed
   or terminal.
3. Record new metrics and checkpoint facts **before** interpreting them.
4. Separate code/config failures from transient infra ones — classify per
   `../engineering.md`; a traceback string alone is not a code bug.
5. Compare runs at equivalent steps and protocols; prefer one-variable
   ablations and state the evidence for the next decision.
6. Launch, stop, or wait, then update the results and next-action notes before
   ending the cycle.

**Do not kill a run from one noisy point** — require a sustained trend against a
truly comparable baseline, unless there is a hard failure or an urgent budget
need. Do not hand-relaunch preempted work the infra already retries, and prefer
scheduled checks over busy waiting, at a cadence matching checkpoint/eval
frequency.

**Durable records, per run**: job id, tracker identity, staged config or commit,
key hyperparameters, data recipe, region/accelerator, logdir, metric timeline,
status, conclusion. Prose notes never override the effective staged config
observed in the tracker or logs. A run that reaches a conclusion is logged to
the spreadsheet with its chart link (`result_logging.md`).

**Identify the actual tracking backend before querying it** (`EqR-jax` routes
WandB-shaped calls to DeepMind Datatables — `../projects/eqr_jax.md`;
`result_logging.md` §Chart Links owns URL forms and metric-verification). For a
real external WandB run, resolve the exact entity/project/run and enumerate
`run.files()` before downloading (`output.log` is common, not guaranteed). Never
assume a crashed process uploaded complete console logs; compare tracker
artifacts against the job's authoritative logs and staged config.
