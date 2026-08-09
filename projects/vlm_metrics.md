# VLM Benchmark Reporting

Read this before a VLM result reaches the shared spreadsheet, or when a
benchmark number looks wrong. This file owns *which number* each benchmark name
means; `../research/result_logging.md` owns the write mechanics, the "settle the
protocol first" rule, and every column map — rebuild that map from the live
header each time rather than from either file.

## One Benchmark Name, Several Numbers

**Report the variant named here; the alternatives are different numbers, not
rounding.** Pretraining rows take stage-1 final metrics and SFT rows stage-2
final metrics, as two adjacent rows even when one run covers both stages.

| Benchmark | The number that counts | Trivial floor |
|---|---|---|
| POPE | **adversarial F1**, not macro F1 | — |
| MMVP | official 150-pair both-correct accuracy, not 300-item | `25%` |
| CVBench | official source-balanced score | `42.4889%` protocol-aligned, displayed `42.49` |
| VLMs Are Blind | official eight-task mean | `24.00%` published uniform-random |
| ImageNet KNN | raw and PCA-whitened are separate protocols | — |
| VStar / VisWiz | greedy and beam-search are separate protocols | — |
| DocVQA | ANLS per `vlm_data.md`; Stage-3 training already includes DocVQA-train through the OV1.5 grouped stream, so this is in-domain supervised evaluation, **never zero-shot document generalization** | — |
| RefCOCOg valid answers | a diagnostic: note it when already logged, else `n/a`; never open result data solely to compute it | — |

**Red on a metric means strictly below its OWN floor above** — each follows from
its benchmark's protocol, so one borrowed from a neighbour raises false alarms —
while **red on a label means a verified encoder misconfiguration.** Two
different signals, and inserting a row inherits both, so clear inherited
backgrounds before reapplying either. A result produced under a superseded
protocol is marked protocol-invalid instead, never scored against a floor.
