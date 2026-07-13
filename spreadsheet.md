# Spreadsheet Result Logging

Use this guide when the user asks to put WandB or job results into the shared VLM
experiment spreadsheet. The default target is the cleaned PaliGemma/JAX LLaVA
tab in spreadsheet `1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ`; inspect the
live workbook before trusting a saved tab name or row number.

## Core Rule

Do not write when the run and sheet are not directly comparable. Stop and report
the discrepancy if a metric is missing or renamed, uses a different split or
protocol, final evaluations disagree, training continuity is unexplained, the
target cells conflict, or the task would require cross-region benchmark or
checkpoint access.

The user should decide how to represent an out-of-distribution result. An agent
must not silently force it into the existing schema.

## Transaction

1. Resolve the input to an exact WandB run and, when relevant, an exact infra job
   attempt. An 8-character id is normally unified infra; a 4-digit id may be a
   legacy tmux window.
2. Read the nearby sheet rows before choosing a target. Reuse a clearly matching
   blank row or insert beside the closest comparable experiment, not at the end
   by default.
3. Pull identity, config, final metrics, and step/loss continuity from WandB and
   logs. Do not scan benchmark datasets merely to fill a diagnostic.
4. Normalize only metrics whose semantics are known, then run the comparability
   hard stop above.
5. Write the smallest range, preserve the WandB link, apply only intentional
   formatting, and read back values, formulas, and colors.
6. Report the changed row, run id/name, missing diagnostics, and any caveat.

## Semantics That Must Stay Explicit

- Use stage-1 final metrics for pretraining rows and stage-2 final metrics for
  SFT rows. Represent a pretrain/SFT pair as adjacent rows even if one WandB run
  contains both stages.
- The main POPE column is adversarial F1, not macro F1.
- ImageNet KNN protocols such as raw and PCA-whitened are not interchangeable.
- Greedy and beam-search VStar/VisWiz values are not interchangeable.
- RefCOCOg valid-answer count is a diagnostic placed in the note when already
  logged; write `n/a` rather than opening result data solely to compute it.
- Label cells `A:D` are red only for a verified encoder misconfiguration. Metric
  cells `F:V` use a separate below-trivial-score signal. Inserting a row can
  inherit both formats, so clear inherited backgrounds before reapplying either.

For bulk reformatting or structural cleanup, duplicate the worksheet first
unless the user explicitly authorizes changing the original. Historical column
maps, thresholds, and API snippets are in `archive/details/` if the live sheet
alone is insufficient.
