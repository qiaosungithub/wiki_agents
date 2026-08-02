# VLM Benchmark Reporting

Read this when writing a VLM result into the shared spreadsheet, or when a
benchmark number looks wrong. The general "settle the protocol first" rule is in
`research/result_logging.md`; this file holds the specific conventions that tab
uses. Verify column letters against the live sheet — a layout note ages.

## Protocol Choices That Are Not Interchangeable

- Use stage-1 final metrics for pretraining rows and stage-2 final metrics for
  SFT rows. Represent a pretrain/SFT pair as adjacent rows even when one
  tracking run contains both stages.
- The main POPE column is **adversarial F1**, not macro F1.
- ImageNet KNN protocols (raw versus PCA-whitened) are different numbers.
- Greedy and beam-search VStar / VisWiz values are different numbers.
- MMVP uses the official 150-pair both-correct accuracy, not 300-item accuracy.
- CVBench uses the official source-balanced score. VLMs Are Blind uses the
  official eight-task mean.
- RefCOCOg valid-answer count is a diagnostic. Note it when already logged;
  write `n/a` rather than opening result data solely to compute it.

## Trivial-Score Floors

Each benchmark's random-choice floor comes from its own protocol, so a threshold
borrowed from another protocol raises false alarms. Mark a value red only when
it is **strictly below its own floor**: MMVP `25%`, CVBench `42.4889%`
(protocol-aligned, displayed `42.49`), VLMs Are Blind `24.00%` (published
uniform-random). Results produced under a superseded protocol are marked as
protocol-invalid instead, never scored against the current floor.

## Formatting

Label cells and metric cells carry two *different* signals: labels are red only
for a verified encoder misconfiguration, metrics for a below-trivial score.
Inserting a row inherits both formats, so clear inherited backgrounds before
reapplying either.
