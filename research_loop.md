# AI Research Loop — Experiment Management

A pattern for running long-horizon ML experiments with an autonomous agent loop. The agent wakes on a timer, checks job status, reads logs, records results, and decides what to do next.

---

## Core loop (every wake cycle)

1. **Re-read the research notes file** — prevents context drift and keeps goals in focus.
2. **Check job status** — identify which jobs are running, errored, or finished.
3. **Read latest eval logs** — extract new metric values from log files.
4. **Update results tracking** — record new checkpoints in the results file.
5. **Diagnose errors** — distinguish real code bugs from false positives (e.g. checkpoint-save noise).
6. **Plan next steps** — decide whether to launch new experiments, kill underperformers, or wait.
7. **Clean up** — close stale tmux windows from replaced/fixed jobs.

---

## File structure

Keep two agent-facing files in an `agents/` directory at the project root:

| File | Purpose |
|------|---------|
| `agents/notes.md` | Research goals, codebase overview, infra how-tos, gotchas. Re-read every cycle. |
| `agents/results.md` | Per-run eval tables, ablation matrix, conclusions, next steps. |

`notes.md` is the **stable reference** (updated rarely). `results.md` is the **living log** (updated every cycle with new evals).

---

## Diagnosing "Error" status

Not all `Error` statuses are real bugs. Before taking action:

1. Read the actual log file (`grep "Error\|Traceback" <logdir>/output.log`).
2. Check whether the job is still producing training metrics (step counts, loss values).
3. Checkpoint-save output (e.g. orbax messages) is often misclassified as errors by monitoring tools.

Real bugs show Python tracebacks. Preemptions show infra-level failure messages. Both need different responses.

---

## Responding to errors

| Error type | Action |
|------------|--------|
| Python traceback (code bug) | Fix the code, commit, relaunch in a new window |
| Preemption / infra failure | Do nothing — auto-resume handles it |
| False positive (checkpoint noise) | Ignore, confirm job is training normally |

When relaunching after a code fix:
- Make sure you're on the correct branch before staging.
- Close the old error window after the new job is confirmed running.

---

## Tracking experiments

For each run, record:
- **Window ID** (tmux handle)
- **TPU name and alias**
- **Config** (key hyperparams: model, lr, batch size, epochs)
- **Architecture** (any non-default choices)
- **Eval checkpoints table** (epoch → accuracy, with notes on trends)
- **Status** (Running / Finished / Killed + current epoch)
- **LogDir** (full path)
- **WandB notes** (the string passed at launch for experiment tracking)

### Ablation matrix format

Use a markdown table with one row per run and one column per eval checkpoint. Add emoji annotations:
- ✅ good result / recovery
- ⚠️ plateau, dip, or concerning trend

---

## Deciding when to kill a run

Kill a run early if:
- It is consistently 3–5% behind comparable runs at the same epoch.
- The trend is declining (not just a temporary plateau).
- The TPU slot is needed for a higher-priority experiment.

A single dip is not sufficient — check at least 2–3 consecutive evals before concluding a run is failing.

---

## Launching new experiments

Before launching:
- Verify you are on the right git branch.
- Set `wandb_notes` at launch via `--config.logging.wandb_notes="..."` — do not rely on config files.
- Check the TPU budget cap for the project and count currently active jobs.
- Prefer incremental ablations (change one variable at a time).
- For hyperparameter search, doubling is a reasonable step size (don't over-tune early).

---

## WandB notes convention

Always pass a descriptive `wandb_notes` string at launch:

```bash
tpu run <tpu> <user> dir=N --config.logging.wandb_notes="<experiment-tag>"
```

This becomes the WandB run description and is the primary way to identify runs in the tracking system. Do not leave it as the default.

---

## Loop cadence

- **30-minute cycles** work well for long-running training jobs (eval every 20 epochs, ~2h apart).
- Use a cron-based or scheduled wakeup to avoid busy-waiting.
- At each wakeup, execute the full loop even if no new evals are expected — catches preemptions and false errors early.
