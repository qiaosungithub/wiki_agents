# Research Workflow

How to run an experiment program and record what it produced.

| Read | When |
|---|---|
| `experiment_loop.md` | Managing a long-running experiment: what to check each cycle, what to keep, when to kill a run. |
| `result_logging.md` | Writing a result into the shared experiment spreadsheet, or finding the chart for a job. |

A run that reaches a **conclusion** is logged to the spreadsheet. A run that only
exposed a code bug or an infra failure is not — that belongs in the commit
message or the project guide.
