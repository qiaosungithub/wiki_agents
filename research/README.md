# Research Workflow

How to run an experiment program and record what it produced. A run that reaches
a **conclusion** is logged to the spreadsheet; one that only exposed a code bug
or an infra failure is not — see `result_logging.md`.

| Read | When |
|---|---|
| `experiment_loop.md` | Managing a long-running experiment: what to check each cycle, what to keep, when to kill a run. |
| `result_logging.md` | Writing a result into the shared experiment spreadsheet, or finding the chart for a job. Read it **every** time you log — headers and layout drift. |
| `v7_storage_placement.md` | Choosing a metro for a v7 run: the standing three-metro decision, and how to regenerate the survey behind it. |
| `xm_migration_jax_llava.md` | The in-flight `jax_llava` XM/Borg migration: where it stands, plus its copier, Borg-path, v7-32 topology, and job-running traps. |
