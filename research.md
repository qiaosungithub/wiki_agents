# Experiment Management

Owns how to run a long experiment program. Queueing, resume, and failure handling
are `infra.md`; writing a result into the sheet is `spreadsheet.md`; which VLM
benchmark number to report is `vlm_metrics.md`; research idea pages are under
`research/`.

Chapter 1 is the loop; Chapter 2 is what each run leaves behind; Chapter 3 is the
decisions that most often go wrong.

---

## Chapter 1 — The Research Loop

### Preserve reasoning, not just jobs

**A long-running research loop keeps a stable objective/constraints note and a
living results table in the project, and revisits both every cycle.**

### One cycle

**Each cycle runs these steps in order, and records facts before interpreting
them.**

1. Re-read the objective, active hypotheses, budget, and previous conclusions.
2. Inspect each active chain with `infra check`; use `infra info` and logs for anything changed or terminal.
3. Record new metrics and checkpoint facts before interpreting them.
4. Separate code/config failures from infra failures. Infra normally resumes the same chain; code bugs and OOMs require a fix and a new queued snapshot.
5. Compare runs at equivalent steps and protocols. Prefer one-variable ablations, and state the evidence for the next decision.
6. Launch, stop, or wait. Update the results and next-action notes before ending the cycle.

---

## Chapter 2 — What Each Run Leaves Behind

### Durable records

**For every run, retain the job id, WandB identity, staged config or commit,
important hyperparameters, data recipe, TPU region/type, logdir, metric timeline,
status, and conclusion.** The job id remains stable across automatic resumes; old
attempt logs are available through `dead_runs`.

Use descriptive `wandb_notes` so humans can identify the purpose and cost class
without reconstructing the launch command. Do not let prose notes override the
effective stage config observed in WandB or logs.

### Check tracker artifacts against the job's own logs

**Resolve the exact WandB entity/project/run and enumerate `run.files()` before
downloading, because `output.log` is common, not guaranteed.** Never assume a
crashed process uploaded complete console logs; compare tracker artifacts with the
job's authoritative logs and staged config.

---

## Chapter 3 — Decisions That Go Wrong

### Common wrong moves

**Before you kill, relaunch, clean up, or wait on a run, check the matching row.**

| Wrong move | Do instead |
|---|---|
| Kill a run from one noisy point | Require a sustained trend against a truly comparable baseline, unless there is a hard failure or an urgent budget need |
| Treat a traceback string alone as a code bug | Read the deepest relevant failure, and check for an earlier OOM or environment error |
| Relaunch preempted work manually | Verify that the same chain requeued |
| Clean terminal infra records right away | Clean them only after their failed-attempt logs are no longer needed for diagnosis |
| Busy-wait on a run | Schedule checks at a cadence that matches checkpoint and evaluation frequency, not an arbitrary timer |

### A split that selects is not held out

**If a split chose the checkpoint, the hyperparameter, or the arm, a number
measured on it is optimistically biased, so report the selected model and the
selection-free one (the final model at the step budget) side by side.** Selecting
on such a split can still be the right protocol, but the difference between the
two numbers must be visible. Never compare one arm's selected number against
another arm's unselected one.

- Loss and accuracy do not peak at the same step, so "the best checkpoint" is best only on the metric that chose it. When a table carries both metrics, carry both models too.
- When a study pre-registers two metrics, check whether they peak at different rows before writing "single peak". Two metrics that disagree are the finding, and collapsing them re-picks the metric after seeing the data.
- An upstream repository's split names can mislead: `torch-rnn` calls its selection split "val" and never touches its "test" split. When you re-role a split, version the prepared-data directory and make the loader refuse the old layout, because the same file name now means different bytes.
