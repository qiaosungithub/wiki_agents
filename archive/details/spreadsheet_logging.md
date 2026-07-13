# Spreadsheet / WandB Result Logging

Use this guide when the user sends a WandB run name, run link, or log path and
asks to record benchmark results into the experiment spreadsheet. For the
step-by-step procedure intended for a new agent, read
`spreadsheet_logging_playbook.md` after this file.

## Primary Sheet

- Spreadsheet:
  `https://docs.google.com/spreadsheets/d/1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ/edit?gid=1739404389#gid=1739404389`
- Default tab for PaliGemma / JAX LLaVA tracking:
  `PaliGemma-baseline-cleaned-20260608`, gid `1739404389`.
- Legacy source tab, no longer the default logging target:
  `PaliGemma-baseline`, gid `1146448969`.

## Hard Stop Rule

Before writing to the spreadsheet, compare the run's observed metrics and log
behavior against the expected spreadsheet schema and prior runs.

If there is any out-of-distribution behavior, stop immediately, do not write to
the sheet, and ask the user for a decision. Examples:

- A benchmark appears that is not already represented by the expected columns.
- An expected benchmark is missing, renamed, split differently, or logged under
  a new metric key.
- A metric is not directly comparable to the sheet value, such as online vs
  final eval, capped/sample eval vs full eval, greedy vs beam, raw KNN vs
  whitened KNN, POPE macro F1 vs adversarial F1, or a new benchmark split.
- Training or eval loss is discontinuous, has an unexplained step reset, has a
  large unexplained spike/drop, or conflicts with the run note.
- Multiple final evals disagree and it is not clear which one should be logged.
- Existing spreadsheet cells already contain conflicting values.
- Logging the result would require scanning/copying benchmark data or
  checkpoints across regions.

Stopping means: report the exact anomaly, cite the affected metric/step/cell if
available, and wait for the user's instruction before any spreadsheet write.

## Normal Logging Workflow

1. Read `wiki_agents/AGENTS.md`, this file, and
   `spreadsheet_logging_playbook.md`.
2. Identify the target spreadsheet tab and row before writing.
   - Default to the cleaned tab, not the legacy source tab.
   - Insert results into the comparable experiment block rather than appending
     to the end. For pretrain+SFT pairs in the PaliGemma ablation block, use
     two adjacent rows: the pretrain run row first, then the SFT run row.
3. Pull metrics from WandB/logs only; avoid reading benchmark datasets. If VLM
   data or checkpoint locality matters, read `vlm_data.md` and
   `vlm_checkpointing.md`.
4. Normalize metric names to the sheet columns. For the current VLM table:
   `MME-P / MME-S`, `VQAv2`, `TextVQA`, `RefCOCOg`, `MMBench`,
   `POPE (adv F1)`, `ImageNet KNN`, `VStar`, `OCRBench`, `MMVP`,
   `CountBench`, `VisWiz`, `SEED-Bench`, `ScienceQA-IMG`, and `GQA`.
   - For RefCOCOg evals, also record the valid-answer / parse-valid count when
     it is already present in WandB summary or output logs. Put it in the row
     `Note` cell as `RefCOCOg valid ans: <valid>/<total>` because it is an
     instruction-following diagnostic rather than a benchmark score. Do not
     open result JSONs or benchmark data solely to compute it; if unavailable,
     record `RefCOCOg valid ans: n/a` and mention that in the final summary.
5. Run the hard-stop checks above.
6. If all checks pass, write the row and preserve the WandB run/link.
7. After writing, read back the changed range and summarize what was logged.

## Sheet Safety

- If the task involves reorganizing, bulk formatting, or cleaning existing
  spreadsheet structure, duplicate the worksheet first and edit only the copy
  unless the user explicitly says to modify the original.
- For ordinary single-run logging, it is acceptable to write to the target row
  directly only after the hard-stop checks pass and the target row is clear.
- Keep values comparable across rows. Do not silently substitute macro metrics
  for split metrics or partial evals for final evals.

## Known Metric Notes

- POPE values in the LLaVA-1.5 reproduction rows are adversarial F1, not macro
  F1. The target `84.2` and row-148-style values should be compared to the
  adversarial split.
- VStar, OCRBench, MMVP, CountBench, RefCOCOg, and ImageNet KNN are additional
  probes, not original LLaVA-1.5 paper metrics.
- Trivial-score highlighting in the cleaned sheet uses rough baselines:
  random multiple-choice where applicable, always-yes F1 for POPE, random
  ImageNet-1k top-1 for KNN, and zero for open-ended / grounding metrics unless
  the user requests a more exact baseline.
