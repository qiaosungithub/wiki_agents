# Research Workflow

How to run an experiment program and record what it produced.

| Read | When |
|---|---|
| `experiment_loop.md` | Managing a long-running experiment: what to check each cycle, what to keep, when to kill a run. |
| `result_logging.md` | Writing a result into the shared experiment spreadsheet, or finding the chart for a job. Read it **every** time you log — headers and layout drift. |
| `v7_storage_placement.md` | Choosing a metro for a v7 run: which cells have storage quota beside the chips, and how to regenerate the survey. |

A run that reaches a **conclusion** is logged to the spreadsheet. A run that only
exposed a code bug or an infra failure is not — that belongs in the commit
message or the project guide.
