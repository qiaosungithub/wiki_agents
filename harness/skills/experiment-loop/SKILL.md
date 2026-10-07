---
name: experiment-loop
description: Run a long experiment program cycle by cycle (objective note, results table, compare at matched protocols, launch/stop/wait) and keep durable run records and tracker evidence.
---

# Research Workflow

How to run an experiment program and record what it produced. A run that reaches
a **conclusion** is logged to the spreadsheet; one that only exposed a code bug
or an infra failure is not ([result-logging skill](../result-logging/SKILL.md)). The research ideas behind the
experiments are indexed in [knowledge/research/README.md](../../../knowledge/research/README.md).

## The Research Loop Preserves Reasoning, Not Just Jobs

Keep a stable objective/constraints note and a living results table in the
project; revisit both every cycle. One cycle:

1. Re-read the objective, active hypotheses, budget and previous conclusions.
2. Inspect each active chain's status; use logs to investigate anything changed
   or terminal.
3. Record new metrics and checkpoint facts **before** interpreting them.
4. Separate code/config failures from transient infra ones, classifying per
   [harness/engineering.md](../../engineering.md). A traceback string alone is not a code bug.
5. Compare runs at equivalent steps and protocols. Prefer one-variable ablations,
   and state the evidence for the next decision.
6. Launch, stop or wait, then update the results and next-action notes before
   ending the cycle.

Do not kill a run from one noisy point. Require a sustained trend against a truly
comparable baseline, unless there is a hard failure or an urgent budget need. Do
not hand-relaunch preempted work the infra already retries, and prefer scheduled
checks over busy waiting, at a cadence matching checkpoint/eval frequency.

Durable records, per run: job id, tracker identity, staged config or commit, key
hyperparameters, data recipe, region/accelerator, logdir, metric timeline,
status, conclusion. Prose notes never override the effective staged config seen
in the tracker or logs. A run that reaches a conclusion is logged to the
spreadsheet with its chart link ([result-logging skill](../result-logging/SKILL.md)).

Identify the actual tracking backend before querying it. `EqR-jax` routes
WandB-shaped calls to DeepMind Datatables ([knowledge/codebases/eqr-jax.md](../../../knowledge/codebases/eqr-jax.md)), and
[harness/skills/result-logging/references/chart-links.md §Chart Links](../result-logging/references/chart-links.md#chart-links) owns URL forms and metric-verification. For a
real external WandB run, resolve the exact entity/project/run and enumerate
`run.files()` before downloading: `output.log` is common, not guaranteed. Never
assume a crashed process uploaded complete console logs; compare tracker
artifacts against the job's authoritative logs and staged config.
